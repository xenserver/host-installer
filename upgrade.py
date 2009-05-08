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
import re
import subprocess
import tempfile

import product
import diskutil
import util
import constants
import xelogging
import backend
from variant import VariantRetail, VariantOEMDisk, VariantOEMFlash

class UpgraderNotAvailable(Exception):
    pass

def upgradeAvailable(src):
    return __upgraders__.hasUpgrader(src.name, src.variant_class, src.version)

def getUpgrader(src):
    """ Returns an upgrader instance suitable for src. Propogates a KeyError
    exception if no suitable upgrader is available (caller should have checked
    first by calling upgradeAvailable). """
    return __upgraders__.getUpgrader(src.name, src.variant_class, src.version)(src)

class Upgrader(object):
    """ Base class for upgraders.  Superclasses should define an
    upgrades_product variable that is the product they upgrade, an 
    upgrades_variants list of Retail or OEM install types that they upgrade, and an 
    upgrades_versions that is a list of pairs of version extents they support
    upgrading."""

    requires_backup = False
    optional_backup = True
    repartition     = False

    def __init__(self, source):
        """ source is the ExistingInstallation object we're to upgrade. """
        self.source = source

    def upgrades(cls, product, variant_class, version):
        return (cls.upgrades_product == product and
                variant_class in cls.upgrades_variants and
                True in [ _min <= version <= _max for (_min, _max) in cls.upgrades_versions ])

    upgrades = classmethod(upgrades)

    prepStateChanges = []
    prepUpgradeArgs = []
    def prepareUpgrade(self, progress_callback):
        """ Collect any state needed from the installation, and return a
        tranformation on the answers dict. """
        return

    completeUpgradeArgs = ['mounts', 'installation-to-overwrite']
    def completeUpgrade(self, mounts, prev_install):
        """ Write any data back into the new filesystem as needed to follow
        through the upgrade. """
        pass

class ThirdGenUpgrader(Upgrader):
    """ Upgrader class for series 5 Retail products. """
    upgrades_product = "xenenterprise"
    upgrades_versions = [ (product.Version(5, 0, 0), product.THIS_PRODUCT_VERSION) ]
    upgrades_variants = [ VariantRetail ]
    requires_backup = True
    optional_backup = False

    def __init__(self, source):
        Upgrader.__init__(self, source)

    prepUpgradeArgs = ['installation-uuid', 'control-domain-uuid']
    prepStateChanges = ['installation-uuid', 'control-domain-uuid', 'primary-disk']
    def prepareUpgrade(self, progress_callback, installID, controlID):
        """ Try to preserve the installation and control-domain UUIDs from
        xensource-inventory."""
        try:
            installID = self.source.getInventoryValue("INSTALLATION_UUID")
            controlID = self.source.getInventoryValue("CONTROL_DOMAIN_UUID")
            # test for presence:
            _ = self.source.getInventoryValue("BACKUP_PARTITION")

            pd = self.source.primary_disk
        except KeyError:
            raise RuntimeError, "Required information (INSTALLATION_UUID, CONTROL_DOMAIN_UUID) was missing from your xensource-inventory file.  Aborting installation; please replace these keys and try again."

        return installID, controlID, pd

    completeUpgradeArgs = ['mounts', 'installation-to-overwrite']
    def completeUpgrade(self, mounts, prev_install):
        xelogging.log("Restoring preserved files")
        backup_volume = backend.getBackupPartName(self.source.primary_disk)
        tds = None
        regen_ifcfg = False
        try:
            tds = tempfile.mkdtemp(dir = "/tmp", prefix = "upgrade-src-")
            util.mount(backup_volume, tds)

            util.assertDir(os.path.join(mounts['root'], "var/xapi"))
            util.assertDir(os.path.join(mounts['root'], "etc/xensource"))

            # restore files:
            restore = ['etc/xensource/ptoken', 'etc/xensource/pool.conf', 
                       'etc/xensource/xapi-ssl.pem',
                       'etc/ssh/ssh_host_dsa_key', 'etc/ssh/ssh_host_dsa_key.pub',
                       'etc/ssh/ssh_host_key', 'etc/ssh/ssh_host_key.pub',
                       'etc/ssh/ssh_host_rsa_key', 'etc/ssh/ssh_host_rsa_key.pub']

            restore += [ 'etc/sysconfig/network' ]
            restore += [ 'etc/sysconfig/network-scripts/' + f
                         for f in os.listdir(os.path.join(tds, 'etc/sysconfig/network-scripts'))
                         if re.match('ifcfg-[a-z0-9.]+$', f) or re.match('route-[a-z0-9.]+$', f) ]

            # CP-968: do not copy Express licence
            lic_file = "etc/xensource/license"
            patch = os.path.join(tds, "var/patch/applied/1244e029-4f48-4503-82c7-db4e2ec8f70d")
            lic = os.path.join(tds, lic_file)
            if os.path.exists(patch):
                restore.append(lic_file)
            elif os.path.exists(lic):
                l = open(lic, 'r')
                try:
                    if True not in ['sku_type="XE Express"' in line for line in l]:
                        restore.append(lic_file)
                finally:
                    l.close()

            restore += ['etc/xensource/db.conf', 'var/xapi/state.db']
            restore += [os.path.join(constants.FIRSTBOOT_DATA_DIR, f) for f in 
                        os.listdir(os.path.join(tds, constants.FIRSTBOOT_DATA_DIR))
                        if f.endswith('.conf')]

            save_dir = os.path.join(constants.FIRSTBOOT_DATA_DIR, 'initial-ifcfg')
            util.assertDir(os.path.join(mounts['root'], save_dir))
            if os.path.exists(os.path.join(tds, save_dir)):
                restore += [ os.path.join(save_dir, f)
                             for f in os.listdir(os.path.join(tds, save_dir))
                             if re.match('ifcfg-[a-z0-9.]+$', f) ]
            else:
                regen_ifcfg = True

            for f in restore:
                src = os.path.join(tds, f)
                dst = os.path.join(mounts['root'], f)
                if os.path.exists(src):
                    xelogging.log("Restoring /%s" % f)
                    util.runCmd2(['cp', '-p', src, dst])
                else:
                    xelogging.log("WARNING: /%s did not exist in the backup image." % f)

            v = product.Version(prev_install.version.major,
                                prev_install.version.minor,
                                prev_install.version.release)
            f = open(os.path.join(mounts['root'], 'var/tmp/.previousVersion'), 'w')
            f.write("PRODUCT_VERSION='%s'\n" % v)
            f.close()

            state = open(os.path.join(mounts['root'], constants.FIRSTBOOT_DATA_DIR, 'host.conf'), 'w')
            print >>state, "UPGRADE=true"
            state.close()

            # CA-21443: initial ifcfg files are needed for pool eject
            if regen_ifcfg:
                xelogging.log("Generating firstboot ifcfg files from firstboot data")
                try:
                    net_dict = util.readKeyValueFile(os.path.join(tds, constants.FIRSTBOOT_DATA_DIR, 'network.conf'))
                    if net_dict.has_key('ADMIN_INTERFACE'):
                        mgmt_dict = util.readKeyValueFile(os.path.join(tds, constants.FIRSTBOOT_DATA_DIR, 'interface-%s.conf' % net_dict['ADMIN_INTERFACE']))
                        xelogging.log(mgmt_dict)
                        brname = 'xenbr%s' % mgmt_dict['LABEL'][3:]
                        eth_ifcfg = open(os.path.join(mounts['root'], save_dir, 'ifcfg-%s' % mgmt_dict['LABEL']), 'w')
                        print >>eth_ifcfg, "XEMANAGED=yes"
                        print >>eth_ifcfg, "DEVICE=%s" % mgmt_dict['LABEL']
                        print >>eth_ifcfg, "ONBOOT=no"
                        print >>eth_ifcfg, "TYPE=Ethernet"
                        print >>eth_ifcfg, "HWADDR=%s" % net_dict['ADMIN_INTERFACE']
                        print >>eth_ifcfg, "BRIDGE=%s" % brname
                        eth_ifcfg.close()

                        br_ifcfg = open(os.path.join(mounts['root'], save_dir, 'ifcfg-%s' % brname), 'w')
                        print >>br_ifcfg, "XEMANAGED=yes"
                        print >>br_ifcfg, "DEVICE=%s" % brname
                        print >>br_ifcfg, "ONBOOT=no"
                        print >>br_ifcfg, "TYPE=Bridge"
                        print >>br_ifcfg, "DELAY=0"
                        print >>br_ifcfg, "STP=0"
                        print >>br_ifcfg, "PIFDEV=%s" % mgmt_dict['LABEL']
                        if mgmt_dict['MODE'] == 'static':
                            print >>br_ifcfg, "BOOTPROTO=none"
                            print >>br_ifcfg, "NETMASK=%s" % mgmt_dict['NETMASK']
                            print >>br_ifcfg, "IPADDR=%s" % mgmt_dict['IP']
                            print >>br_ifcfg, "GATEWAY=%s" % mgmt_dict['GATEWAY']
                            i = 1
                            while mgmt_dict.has_key('DNS%d' % i):
                                print >>br_ifcfg, "DNS%d=%s" % (i, mgmt_dict['DNS%d' % i])
                                i += 1
                            if i > 1:
                                print >>br_ifcfg, "PEERDNS=yes"
                        else:
                            print >>br_ifcfg, "BOOTPROTO=dhcp"
                            print >>br_ifcfg, "PERSISTENT_DHCLIENT=yes"
                            print >>br_ifcfg, "PEERDNS=yes"
                        br_ifcfg.close()
                except:
                    pass

        finally:
            if tds:
                if os.path.ismount(tds):
                    util.umount(tds)
                os.rmdir(tds)

class ThirdGenOEMDiskUpgrader(ThirdGenUpgrader):
    """ Upgrader class for series 5 OEM Disk products. """
    requires_backup = False
    optional_backup = False
    repartition     = True
    upgrades_variants = [ VariantOEMDisk ]

    def __init__(self, source):
        ThirdGenUpgrader.__init__(self, source)

    prepUpgradeArgs = ['installation-uuid', 'control-domain-uuid', 'installation-to-overwrite']
    prepStateChanges = ['installation-uuid', 'control-domain-uuid', 'primary-disk']
    def prepareUpgrade(self, progress_callback, installID, controlID, existing):
        """ Prepare the disk for a Retail XenServer installation. """

        inst_ctrl_pd = ThirdGenUpgrader.prepareUpgrade(self, progress_callback, installID, controlID)
        disk = existing.primary_disk

        progress_callback(10)
        backend.removeExcessOemPartitions(existing)
        progress_callback(20)
        backend.createRootPartitionTableEntry(disk)
        progress_callback(30)
        backend.createDom0DiskFilesystems(disk)
        progress_callback(40)
        backend.transferFSfromBackupToRoot(disk)
        progress_callback(50)
        backend.removeBackupPartition(disk)
        progress_callback(60)
        backend.createBackupPartition(disk)
        progress_callback(70)
        backend.extractOemStatefromRootToBackup(existing)
        progress_callback(80)

        return inst_ctrl_pd

################################################################################

# Upgraders provided here, in preference order:
class UpgraderList(list):
    def getUpgrader(self, product, variant_class, version):
        for x in self:
            if x.upgrades(product, variant_class, version):
                return x
        raise KeyError, "No upgrader found for %s" % version

    def hasUpgrader(self, product, variant_class, version):
        for x in self:
            if x.upgrades(product, variant_class, version):
                return True
        return False
    
__upgraders__ = UpgraderList([ ThirdGenUpgrader, ThirdGenOEMDiskUpgrader ])

def filter_for_upgradeable_products(installed_products):
    upgradeable_products = filter(lambda p: p.isUpgradeable() and upgradeAvailable(p),
        installed_products)
    return upgradeable_products
