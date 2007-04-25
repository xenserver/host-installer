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
    """ Base class for upgraders.  Superclasses should define an upgrades
    variable that is a triple of the product, the lowest version they support
    upgrading from, and the highest version. """

    def __init__(self, source):
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

        root = diskutil.determinePartitionName(self.source.primary_disk, 1)
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

        # get a mapping of SR to physical devices:
        pdmap = {}
        for sr in srs:
            vg_name = "VG_XenStorage-%s" % sr
            rc, out = util.runCmdWithOutput("vgs -o vg_name,pv_name --noheadings --separator :")
            if rc == 0:
                # we can work with this:
                lines = [x.strip() for x in out.split("\n")]
                related = filter(lambda x: x.startswith(vg_name), lines)
                physdevs = [pv for (_, pv) in [x.split(":") for x in related]]
                pdmap[sr] = physdevs

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

        # - migrate database:
        upgrade_script.write("/opt/xensource/bin/metadata_upgrade >/tmp/md_upgrade.sh\n")
        upgrade_script.write("bash /tmp/md_upgrade.sh\n")
        upgrade_script.write("rm /tmp/md_upgrade.sh\n")

        upgrade_script.close()

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
    
__upgraders__ = UpgraderList([ FirstGenUpgrader ])
