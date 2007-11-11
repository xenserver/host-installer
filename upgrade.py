# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Upgrade paths
#
# written by Andrew Peace

# This stuff exists to hide ugliness and hacks that are required for upgrades
# from the rest of the installer.

import os
import tempfile

import product
import diskutil
import util
import constants
import xelogging

class UpgraderNotAvailable(Exception):
    pass

def upgradeAvailable(src):
    return __upgraders__.hasUpgrader(src.name, src.version)

def getUpgrader(src):
    """ Returns an upgrader instance suitable for src. Propogates a KeyError
    exception if no suitable upgrader is available (caller should have checked
    first by calling upgradeAvailable). """
    return __upgraders__.getUpgrader(src.name, src.version)(src)

class Upgrader(object):
    """ Base class for upgraders.  Superclasses should define an
    upgrades_product variable that is the product they upgrade, and an 
    upgrades_versions that is a list of pairs of version extents they support
    upgrading."""

    requires_backup = False

    def __init__(self, source):
        """ source is the ExistingInstallation object we're to upgrade. """
        self.source = source

    def upgrades(cls, product, version):
        return (cls.upgrades_product == product and
                True in [ _min <= version <= _max for (_min, _max) in cls.upgrades_versions ])

    upgrades = classmethod(upgrades)

    prepStateChanges = []
    prepUpgradeArgs = []
    def prepareUpgrade(self):
        """ Collect any state needed from the installation, and return a
        tranformation on the answers dict. """
        return

    completeUpgradeArgs = ['mounts']
    def completeUpgrade(self, mounts):
        """ Write any data back into the new filesystem as needed to follow
        through the upgrade. """
        pass

class FirstGenUpgrader(Upgrader):
    """ Upgrade XenServer series products version 3.1 and 3.2. """
    upgrades_product = "xenenterprise"
    upgrades_versions = [ (product.Version(0, 4, 3), product.Version(0,4,9)),
                          (product.Version(3, 1, 0), product.Version(3,2,0)) ]
    mh_dat_filename = '/var/opt/xen/mh/mh.dat'

    def __init__(self, source):
        Upgrader.__init__(self, source)

    prepStateChanges = [ 'default-sr-uuid', 'primary-disk', 'srs-defined' ]
    prepUpgradeArgs = [ 'preserve-settings' ]
    def prepareUpgrade(self, preserve_settings):
        """ Read default SR UUID, and put it into the input state for the
        backend.  Also, get a list of SRs on the box. """

        root = self.source.getRootPartition()
        def_sr = None
        srs = []
        try:
            mntpoint = "/tmp/mnt"
            if not os.path.isdir(mntpoint):
                os.mkdir(mntpoint)
            util.mount(root, mntpoint)
            inv = product.readInventoryFile(
                os.path.join(mntpoint, constants.INVENTORY_FILE)
                )
            if inv.has_key("DEFAULT_SR"):
                def_sr = inv['DEFAULT_SR']

            # preserve vbridges - copy out data from the old mh.dat:
            cmd = ['chroot', mntpoint, 'python', '-c',
                   'import sys; '
                   'sys.path.append("/usr/lib/python"); '
                   'import xen.xend.sxp as sxp; '
                   'print sxp.to_string(["mh"] + '
                   '   sxp.children(sxp.parse(open("' + self.mh_dat_filename + '"))[0], "vbridge"))']
            rc, out = util.runCmd2(cmd, True)
            if rc == 0:
                self.mh_dat = out
            else:
                self.mh_dat = None
                xelogging.log("Unable to preserve virtual bridges - could not parse mh.dat in source filesystem.")

            smtab_path = os.path.join(mntpoint, "etc/smtab")
            if os.path.exists(smtab_path):
                smtab = open(smtab_path, "r")
                for line in smtab:
                    try:
                        srs.append(line.split(" ")[0])
                    except:
                        continue
            smtab.close()
        finally:
            util.umount(mntpoint)

        xelogging.log("SRs to be migrated upon first boot: %s" % str(srs))

        return (def_sr, self.source.primary_disk, srs)

    completeUpgradeArgs = ['mounts', 'preserve-settings', 'srs-defined', 'installation-uuid']
    def completeUpgrade(self, mounts, preserve_settings, srs, inst_uuid):
        if self.mh_dat:
            # we saved vbridge data - write it back to mh.dat:
            mhdfn = self.mh_dat_filename.lstrip('/')
            mh_dat_path = os.path.join(mounts['root'], mhdfn)
            mh_dat_parent = os.path.dirname(mh_dat_path)
            os.makedirs(mh_dat_parent)
            fd = open(mh_dat_path, 'w')
            fd.write(self.mh_dat)
            fd.close()
        else:
            xelogging.log("No data to write to mh.dat.")

        # get a mapping of SR to physical devices, and write a mapping of old
        # invalid LV UUIDs to new valid ones, renaming the volumes as we go:
        pdmap = {}
        lvmap_fd = open(os.path.join(mounts['root'], 'var', 'xapi', 'lv-mapping'), 'w')
        for sr in srs:
            vg_name = "VG_XenStorage-%s" % sr
            rc, out = util.runCmd("vgs -o vg_name,pv_name --noheadings --separator :", with_output = True)
            if rc == 0:
                # we can work with this:
                lines = [x.strip() for x in out.split("\n")]
                related = filter(lambda x: x.startswith(vg_name), lines)
                physdevs = [pv for (_, pv) in [x.split(":") for x in related]]
                pdmap[sr] = physdevs

            # map invalid UUIDs to valid ones:
            rc, out = util.runCmd("lvs -o lv_name --noheadings %s" % vg_name, with_output = True)
            if rc == 0:
                xelogging.log("Renaming volumes with deprecated format for SR %s" % sr)
                lvs = [x.strip() for x in out.split("\n")]
                lvs = filter(lambda x: x.startswith("LV-"), lvs)
                for lv in lvs:
                    uuid = util.getUUID()
                    bad_uuid = lv[3:]
                    gd = bad_uuid.split(".")
                    if len(gd) != 2:
                        continue
                    guest, disk = gd
                    new_lv = "LV-" + uuid
                    xelogging.log("Mapping %s to %s" % (lv, new_lv))
                    print >>lvmap_fd, lv, guest, disk, uuid
                    util.runCmd2(['lvrename', vg_name, lv, new_lv])
        lvmap_fd.close()

        # now write out a first-boot script to migrate user data:
        # - migrate SRs
        upgrade_script = open(os.path.join(mounts['root'], "var", "xapi", "upgrade-commands"), 'w')
        for sr in pdmap:
            pd_string = ",".join(pdmap[sr])
            # - make an SR
            upgrade_script.write("SR=$(/opt/xensource/bin/xe sr-introduce name-label='Automatically migrated from previous installation' physical-size=0 type=lvm content-type='' uuid=%s)\n" % sr)
            # - make a PBD to access the SR
            upgrade_script.write("PBD=$(/opt/xensource/bin/xe pbd-create host-uuid=%s device-config-device='%s' sr-uuid=${SR})\n" % (inst_uuid, pd_string))
            # - plug the PBD to enable scanning:
            upgrade_script.write("/opt/xensource/bin/xe pbd-plug uuid=${PBD}\n")
        
        # - set pool and host paramaters like we would in a standard firstboot
        #   script:
        sr = pdmap.keys()[0]
        upgrade_script.write("POOL_UUID=$(/opt/xensource/bin/xe pool-list params=uuid --minimal)\n")
        upgrade_script.write("HOST_UUID=$(/opt/xensource/bin/xe host-list params=uuid --minimal)\n")
        upgrade_script.write("/opt/xensource/bin/xe pool-param-set uuid=${POOL_UUID} default-SR=${SR}\n")
        upgrade_script.write("/opt/xensource/bin/xe host-param-set uuid=${HOST_UUID} crash-dump-sr-uuid=${SR}\n")
        upgrade_script.write("/opt/xensource/bin/xe host-param-set uuid=${HOST_UUID} suspend-image-sr-uuid=${SR}\n")

        # - migrate database:
        upgrade_script.write("/opt/xensource/bin/metadata_upgrade >/tmp/md_upgrade.sh\n")
        upgrade_script.write("cat /tmp/md_upgrade.sh && echo ---\n")
        upgrade_script.write("bash -x /tmp/md_upgrade.sh\n")
        upgrade_script.write("rm /tmp/md_upgrade.sh\n")

        upgrade_script.close()

class SecondGenUpgrader(Upgrader):
    """ Upgrader class for series 4 products. """
    upgrades_product = "xenenterprise"
    upgrades_versions = [ (product.Version(4, 0, 0, suffix = 'b2'), product.THIS_PRODUCT_VERSION) ]
    requires_backup = True

    def __init__(self, source):
        Upgrader.__init__(self, source)

    prepUpgradeArgs = ['installation-uuid', 'control-domain-uuid']
    prepStateChanges = ['installation-uuid', 'control-domain-uuid', 'primary-disk']
    def prepareUpgrade(self, installID, controlID):
        """ Try to preserve the installation and control-domain UUIDs from
        xensource-inventory."""
        try:
            installID = self.source.getInventoryValue("INSTALLATION_UUID")
            controlID = self.source.getInventoryValue("CONTROL_DOMAIN_UUID")
            # test for presence:
            _ = self.source.getInventoryValue("BACKUP_PARTITION")

            pd = self.source.primary_disk
        except KeyError:
            raise RuntimeError, "Required information (INSTALLATION_UUID, CONTROL_DOMAIN_UUID) was missing from your xensource-invenotry file.  Aborting installation; please replace these keys and try again."

        return installID, controlID, pd

    completeUpgradeArgs = ['mounts']
    def completeUpgrade(self, mounts):
        xelogging.log("Restoring preserved files")
        backup_volume = self.source.getInventoryValue("BACKUP_PARTITION")
        tds = None
        try:
            tds = tempfile.mkdtemp(dir = "/tmp", prefix = "upgrade-src-")
            util.mount(backup_volume, tds)

            util.assertDir(os.path.join(mounts['root'], "var/xapi"))
            util.assertDir(os.path.join(mounts['root'], "etc/xensource"))

            # restore files:
            restore = ['etc/xensource/ptoken', 'etc/xensource/pool.conf', 'etc/xensource/xapi.conf',
                       'etc/xensource/license', 'etc/xensource/db.conf', 'var/xapi/state.db']
            for f in restore:
                src = os.path.join(tds, f)
                dst = os.path.join(mounts['root'], f)
                if os.path.exists(src):
                    xelogging.log("Restoring /%s" % f)
                    util.runCmd2(['cp', src, dst])
                else:
                    xelogging.log("WARNING: /%s did not exist in the backup image." % f)
            
            # if we're coming from Rio, we need to move the database config for
            # Rio over the main config file:
            if self.source.version <= product.XENSERVER_4_0_1:
                rio_db_conf = os.path.join(mounts['root'], 'etc', 'xensource', 'db.conf.rio')
                db_conf = os.path.join(mounts['root'], 'etc', 'xensource', 'db.conf')
                os.unlink(db_conf)
                util.runCmd2(['mv', rio_db_conf, db_conf])
        finally:
            if tds:
                if os.path.ismount(tds):
                    util.umount(tds)
                os.rmdir(tds)

# Upgarders provided here, in preference order:
class UpgraderList(list):
    def getUpgrader(self, product, version):
        for x in self:
            if x.upgrades(product, version):
                return x
        raise KeyError, "No upgrader found for %s" % version

    def hasUpgrader(self, product, version):
        for x in self:
            if x.upgrades(product, version):
                return True
        return False
    
__upgraders__ = UpgraderList([ FirstGenUpgrader, SecondGenUpgrader ])
