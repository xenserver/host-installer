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

    completeUpgradeArgs = ['mounts', 'installation-to-overwrite']
    def completeUpgrade(self, mounts, prev_install):
        """ Write any data back into the new filesystem as needed to follow
        through the upgrade. """
        pass

class SecondGenUpgrader(Upgrader):
    """ Upgrader class for series 4 products. """
    upgrades_product = "xenenterprise"
    upgrades_versions = [ (product.Version(4, 1, 0), product.THIS_PRODUCT_VERSION) ]
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
                       'etc/xensource/license', 'etc/xensource/xapi-ssl.pem',
                       'etc/ssh/ssh_host_dsa_key', 'etc/ssh/ssh_host_dsa_key.pub',
                       'etc/ssh/ssh_host_key', 'etc/ssh/ssh_host_key.pub',
                       'etc/ssh/ssh_host_rsa_key', 'etc/ssh/ssh_host_rsa_key.pub']

            restore += [ 'etc/sysconfig/network' ]
            restore += [ 'etc/sysconfig/network-scripts/' + f
                         for f in os.listdir(os.path.join(tds, 'etc/sysconfig/network-scripts'))
                         if re.match('ifcfg-[a-z0-9.]+$', f) or re.match('route-[a-z0-9.]+$', f) ]

            # CA-16795: upgrade xapi database if necessary
            upgrade_db = False
            db_conf = os.path.join(tds, 'etc/xensource/db.conf')
            if os.path.exists(db_conf):
                c = open(db_conf, 'r')
                try:
                    for line in c:
                        if  line.strip('\n') == 'format:sqlite':
                            upgrade_db = True
                            break
                finally:
                    c.close()
            if not upgrade_db:
                restore += ['etc/xensource/db.conf', 'var/xapi/state.db']

            save_dir = os.path.join(constants.FIRSTBOOT_DATA_DIR, 'initial-ifcfg')
            if os.path.exists(os.path.join(tds, save_dir)):
                restore += [ save_dir + f
                             for f in os.listdir(os.path.join(tds, save_dir))
                             if re.match('ifcfg-[a-z0-9.]+$', f) ]
            else:
                util.assertDir(os.path.join(mounts['root'], save_dir))
                # Nothing to restore so regenerate the ifcfg files.
                # (Unless primary disk is an iSCSI device that depends on admin i/f.  
                # In this case only the initrd should ever bring up the admin interface.)
                regen_ifcfg = True
                if diskutil.is_iscsi(self.source.primary_disk):
                    ipaddr, port, netdev = util.iscsi_address_port_netdev(self.source.primary_disk)
                    try:
                        net_dict = util.readKeyValueFile(os.path.join(tds, constants.FIRSTBOOT_DATA_DIR, 'network.conf'))
                        mgmt_dict = util.readKeyValueFile(os.path.join(tds, constants.FIRSTBOOT_DATA_DIR, 'interface-%s.conf' % net_dict['ADMIN_INTERFACE']))
                        mgmt_dev = mgmt_dict['LABEL']
                        if mgmt_dev == netdev:
                            regen_ifcfg = False
                    except:
                        pass

            for f in restore:
                src = os.path.join(tds, f)
                dst = os.path.join(mounts['root'], f)
                if os.path.exists(src):
                    xelogging.log("Restoring /%s" % f)
                    util.runCmd2(['cp', '-p', src, dst])
                else:
                    xelogging.log("WARNING: /%s did not exist in the backup image." % f)

            if upgrade_db:
                xelogging.log("Converting xapi database")
                # chroot into the backup partition and dump db to stdout
                new_db = open(os.path.join(mounts['root'], 'var/xapi/state.db'), 'w')
                cmd = ["/usr/sbin/chroot", tds, "/opt/xensource/bin/xapi-db-process", "-xmltostdout"]
                pipe = subprocess.Popen(cmd, stdout = subprocess.PIPE)
                for line in pipe.stdout:
                    new_db.write(line)
                assert pipe.wait() == 0
                new_db.close()

                # upgrade the db config
                old_config = open(db_conf, 'r')
                new_config = open(os.path.join(mounts['root'], 'etc/xensource/db.conf'), 'w')
                try:
                    for line in old_config:
                        if line.startswith('format:'):
                            new_config.write('format:xml\n')
                        else:
                            new_config.write(line)
                finally:
                    new_config.close()
                    old_config.close()

            v = product.Version(prev_install.version.major,
                                prev_install.version.minor,
                                prev_install.version.release)
            f = open(os.path.join(mounts['root'], 'var/tmp/.previousVersion'), 'w')
            f.write("PRODUCT_VERSION='%s'\n" % v)
            f.close()

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

# Upgraders provided here, in preference order:
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
    
__upgraders__ = UpgraderList([ SecondGenUpgrader ])

def filter_for_upgradeable_products(installed_products):
    upgradeable_products = filter(lambda p: p.isUpgradeable() and upgradeAvailable(p),
        installed_products)
    return upgradeable_products
