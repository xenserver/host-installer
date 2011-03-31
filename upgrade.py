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

import product
from xcp.version import *
from xcp.biosdevname import BiosDevName
from disktools import *
from netinterface import *
import util
import constants
import xelogging

def upgradeAvailable(src):
    return __upgraders__.hasUpgrader(src.name, src.version, src.variant)

def getUpgrader(src):
    """ Returns an upgrader instance suitable for src. Propogates a KeyError
    exception if no suitable upgrader is available (caller should have checked
    first by calling upgradeAvailable). """
    return __upgraders__.getUpgrader(src.name, src.version, src.variant)(src)

class Upgrader(object):
    """ Base class for upgraders.  Superclasses should define an
    upgrades_product variable that is the product they upgrade, an 
    upgrades_variants list of Retail install types that they upgrade, and an 
    upgrades_versions that is a list of pairs of version extents they support
    upgrading."""

    requires_backup = False
    optional_backup = True
    repartition = False

    def __init__(self, source):
        """ source is the ExistingInstallation object we're to upgrade. """
        self.source = source
        self.restore_list = []

    def upgrades(cls, product, version, variant):
        return (cls.upgrades_product == product and
                variant in cls.upgrades_variants and
                True in [ _min <= version < _max for (_min, _max) in cls.upgrades_versions ])

    upgrades = classmethod(upgrades)

    prepTargetStateChanges = []
    prepTargetArgs = []
    def prepareTarget(self, progress_callback):
        """ Modify partition layout prior to installation. """
        return

    doBackupStateChanges = []
    doBackupArgs = []
    def doBackup(self, progress_callback):
        """ Collect configuration etc from installation. """
        return

    prepStateChanges = []
    prepUpgradeArgs = []
    def prepareUpgrade(self, progress_callback):
        """ Collect any state needed from the installation, and return a
        tranformation on the answers dict. """
        return

    def buildRestoreList(self):
        """ Add filenames to self.restore_list which will be copied by
        completeUpgrade(). """
        return

    completeUpgradeArgs = ['mounts', 'primary-disk', 'backup-partnum']
    def completeUpgrade(self, mounts, target_disk, backup_partnum):
        """ Write any data back into the new filesystem as needed to follow
        through the upgrade. """

        def restore_file(src_base, f, d = None):
            if not d: d = f
            src = os.path.join(src_base, f)
            dst = os.path.join(mounts['root'], d)
            if os.path.exists(src):
                xelogging.log("Restoring /%s" % f)
                if os.path.isdir(src):
                    util.runCmd2(['cp', '-rp', src, os.path.dirname(dst)])
                else:
                    util.assertDir(os.path.dirname(dst))
                    util.runCmd2(['cp', '-p', src, dst])
            else:
                xelogging.log("WARNING: /%s did not exist in the backup image." % f)

        backup_volume = partitionDevice(target_disk, backup_partnum)
        tds = util.TempMount(backup_volume, 'upgrade-src-', options = ['ro'])
        try:
            self.buildRestoreList()

            xelogging.log("Restoring preserved files")
            for f in self.restore_list:
                if isinstance(f, str):
                    restore_file(tds.mount_point, f)
                elif isinstance(f, dict):
                    if 'src' in f:
                        assert 'dst' in f
                        restore_file(tds.mount_point, f['src'], f['dst'])
                    elif 'dir' in f:
                        pat = 're' in f and f['re'] or None
                        src_dir = os.path.join(tds.mount_point, f['dir'])
                        if os.path.exists(src_dir):
                            for ff in os.listdir(src_dir):
                                fn = os.path.join(f['dir'], ff)
                                if not pat or pat.match(fn):
                                    restore_file(tds.mount_point, fn)
        finally:
            tds.unmount()


class ThirdGenUpgrader(Upgrader):
    """ Upgrader class for series 5 Retail products. """
    upgrades_product = "xenenterprise"
    upgrades_versions = [ (product.XENSERVER_5_5_0, product.THIS_PRODUCT_VERSION) ]
    upgrades_variants = [ 'Retail' ]
    requires_backup = True
    optional_backup = False
    
    def __init__(self, source):
        Upgrader.__init__(self, source)

    doBackupArgs = ['primary-disk', 'backup-partnum']
    doBackupStateChanges = []
    def doBackup(self, progress_callback, target_disk, backup_partnum):

        # format the backup partition:
        backup_partition = partitionDevice(target_disk, backup_partnum)
        if util.runCmd2(['mkfs.ext3', backup_partition]) != 0:
            raise RuntimeError, "Backup: Failed to format filesystem on %s" % backup_partition
        progress_callback(10)

        # copy the files across:
        primary_fs = util.TempMount(self.source.root_device, 'primary-', options = ['ro'])
        try:
            backup_fs = util.TempMount(backup_partition, 'backup-')
            try:
                just_dirs = ['dev', 'proc', 'lost+found', 'sys']
                top_dirs = os.listdir(primary_fs.mount_point)
                val = 10
                for x in top_dirs:
                    if x in just_dirs:
                        path = os.path.join(backup_fs.mount_point, x)
                        if not os.path.exists(path):
                            os.mkdir(path, 0755)
                    else:
                        cmd = ['cp', '-a'] + \
                              [ os.path.join(primary_fs.mount_point, x) ] + \
                              ['%s/' % backup_fs.mount_point]
                        if util.runCmd2(cmd) != 0:
                            raise RuntimeError, "Backup of %d directory failed" % x
                    val += 90 / len(top_dirs)
                    progress_callback(val)
            finally:
                # replace rolling pool upgrade bootloader config
                src = os.path.join(backup_fs.mount_point, constants.ROLLING_POOL_DIR, 'menu.lst')
                if os.path.exists(src):
                    util.runCmd2(['cp', '-f', src, os.path.join(backup_fs.mount_point, 'boot/grub')])
                src = os.path.join(backup_fs.mount_point, constants.ROLLING_POOL_DIR, 'extlinux.conf')
                if os.path.exists(src):
                    util.runCmd2(['cp', '-f', src, os.path.join(backup_fs.mount_point, 'boot')])
                
                fh = open(os.path.join(backup_fs.mount_point, '.xen-backup-partition'), 'w')
                fh.close()
                backup_fs.unmount()
        finally:
            primary_fs.unmount()

    prepUpgradeArgs = ['installation-uuid', 'control-domain-uuid']
    prepStateChanges = ['installation-uuid', 'control-domain-uuid']
    def prepareUpgrade(self, progress_callback, installID, controlID):
        """ Try to preserve the installation and control-domain UUIDs from
        xensource-inventory."""
        try:
            installID = self.source.getInventoryValue("INSTALLATION_UUID")
            controlID = self.source.getInventoryValue("CONTROL_DOMAIN_UUID")
        except KeyError:
            raise RuntimeError, "Required information (INSTALLATION_UUID, CONTROL_DOMAIN_UUID) was missing from your xensource-inventory file.  Aborting installation; please replace these keys and try again."

        return installID, controlID

    def buildRestoreList(self):
        self.restore_list += ['etc/xensource/ptoken', 'etc/xensource/pool.conf', 
                              'etc/xensource/xapi-ssl.pem']
        self.restore_list.append({'dir': 'etc/ssh', 're': re.compile(r'.*/ssh_host_.+')})

        self.restore_list += [ 'etc/sysconfig/network', constants.DBCACHE ]
        self.restore_list.append({'dir': 'etc/sysconfig/network-scripts', 're': re.compile(r'.*/ifcfg-[a-z0-9.]+')})

        self.restore_list += ['var/xapi/state.db', 'etc/xensource/license']
        self.restore_list.append({'dir': constants.FIRSTBOOT_DATA_DIR, 're': re.compile(r'.*.conf')})

        self.restore_list += ['etc/xensource/syslog.conf']

        self.restore_list.append({'src': 'etc/xensource-inventory', 'dst': 'var/tmp/.previousInventory'})

        # CP-1508: preserve AD config
        self.restore_list += [ 'etc/resolv.conf', 'etc/nsswitch.conf', 'etc/krb5.conf', 'etc/krb5.keytab', 'etc/pam.d/sshd' ]
        self.restore_list.append({'dir': 'var/lib/likewise'})

        # CA-47142: preserve v6 cache
        self.restore_list += [{'dir': 'var/xapi/lpe-cache'}]

        # CP-2056: preserve RRDs etc
        self.restore_list += [{'dir': 'var/xapi/blobs'}]

        self.restore_list.append('etc/sysconfig/mkinitrd.latches')

        # EA-1069: Udev network device naming
        self.restore_list += [{'dir': '/etc/sysconfig/network-scripts/interface-rename-data'}]
        self.restore_list += [{'dir': '/etc/sysconfig/network-scripts/interface-rename-data/.from_install'}]

    completeUpgradeArgs = ['mounts', 'installation-to-overwrite', 'primary-disk', 'backup-partnum', 'net-admin-interface', 'net-admin-bridge', 'net-admin-configuration']
    def completeUpgrade(self, mounts, prev_install, target_disk, backup_partnum, admin_iface, admin_bridge, admin_config):

        util.assertDir(os.path.join(mounts['root'], "var/xapi"))
        util.assertDir(os.path.join(mounts['root'], "etc/xensource"))

        Upgrader.completeUpgrade(self, mounts, target_disk, backup_partnum)

        if not os.path.exists(os.path.join(mounts['root'], constants.DBCACHE)):
            # upgrade from 5.5, generate dbcache
            save_dir = os.path.join(mounts['root'], constants.FIRSTBOOT_DATA_DIR, 'initial-ifcfg')
            util.assertDir(save_dir)
            dbcache_file = os.path.join(mounts['root'], constants.DBCACHE)
            dbcache_fd = open(dbcache_file, 'w')

            network_uid = util.getUUID()
                
            dbcache_fd.write('<?xml version="1.0" ?>\n<xenserver-network-configuration>\n')
                
            if admin_iface.startswith('bond'):
                top_pif_uid = bond_pif_uid = util.getUUID()
                bond_uid = util.getUUID()

# find slaves of this bond and write PIFs for them
                slaves = []
                for file in [ f for f in os.listdir(os.path.join(mounts['root'], constants.NET_SCR_DIR))
                              if re.match('ifcfg-eth[0-9]+$', f) ]:
                    slavecfg = util.readKeyValueFile(os.path.join(mounts['root'], constants.NET_SCR_DIR, file), strip_quotes = False)
                    if slavecfg.has_key('MASTER') and slavecfg['MASTER'] == admin_iface:
                            
                        slave_uid = util.getUUID()
                        slave_net_uid = util.getUUID()
                        slaves.append(slave_uid)
                        slave = NetInterface.loadFromIfcfg(os.path.join(mounts['root'], constants.NET_SCR_DIR, file))
                        slave.writePif(slavecfg['DEVICE'], dbcache_fd, slave_uid, slave_net_uid, ('slave-of', bond_uid))

# locate bridge that has this interface as its PIFDEV
                        bridge = None
                        for file in [ f for f in os.listdir(os.path.join(mounts['root'], constants.NET_SCR_DIR))
                                      if re.match('ifcfg-xenbr[0-9]+$', f) ]:
                            brcfg = util.readKeyValueFile(os.path.join(mounts['root'], constants.NET_SCR_DIR, file), strip_quotes = False)
                            if brcfg.has_key('PIFDEV') and brcfg['PIFDEV'] == slavecfg['DEVICE']:
                                bridge = brcfg['DEVICE']
                                break
                        assert bridge
                        
                        dbcache_fd.write('\t<network ref="OpaqueRef:%s">\n' % slave_net_uid)
                        dbcache_fd.write('\t\t<uuid>%sSlaveNetwork</uuid>\n' % slavecfg['DEVICE'])
                        dbcache_fd.write('\t\t<PIFs>\n\t\t\t<PIF>OpaqueRef:%s</PIF>\n\t\t</PIFs>\n' % slave_uid)
                        dbcache_fd.write('\t\t<bridge>%s</bridge>\n' % bridge)
                        dbcache_fd.write('\t\t<other_config/>\n\t</network>\n')

                # write bond
                dbcache_fd.write('\t<bond ref="OpaqueRef:%s">\n' % bond_uid)
                dbcache_fd.write('\t\t<master>OpaqueRef:%s</master>\n' % bond_pif_uid)
                dbcache_fd.write('\t\t<uuid>InitialManagementBond</uuid>\n\t\t<slaves>\n')
                for slave_uid in slaves:
                    dbcache_fd.write('\t\t\t<slave>OpaqueRef:%s</slave>\n' % slave_uid)
                dbcache_fd.write('\t\t</slaves>\n\t</bond>\n')

                # write bond PIF
                admin_config.writePif(admin_iface, dbcache_fd, bond_pif_uid, network_uid, ('master-of', bond_uid))
            else:
                top_pif_uid = util.getUUID()
                # write PIF
                admin_config.writePif(admin_iface, dbcache_fd, top_pif_uid, network_uid)

            dbcache_fd.write('\t<network ref="OpaqueRef:%s">\n' % network_uid)
            dbcache_fd.write('\t\t<uuid>InitialManagementNetwork</uuid>\n')
            dbcache_fd.write('\t\t<PIFs>\n\t\t\t<PIF>OpaqueRef:%s</PIF>\n\t\t</PIFs>\n' % top_pif_uid)
            dbcache_fd.write('\t\t<bridge>%s</bridge>\n' % admin_bridge)
            dbcache_fd.write('\t\t<other_config/>\n\t</network>\n')

            dbcache_fd.write('</xenserver-network-configuration>\n')

            dbcache_fd.close()
            util.runCmd2(['cp', '-p', dbcache_file, save_dir])
        else:
            # upgrade from 5.6
            changed = False
            dbcache_file = os.path.join(mounts['root'], constants.DBCACHE)
            rdbcache_fd = open(dbcache_file)
            wdbcache_fd = open(dbcache_file + '.new', 'w')
            for line in rdbcache_fd:
                wdbcache_fd.write(line)
                if '<pif ref=' in line:
                    wdbcache_fd.write("\t\t<tunnel_access_PIF_of/>\n")
                    changed = True
            rdbcache_fd.close()
            wdbcache_fd.close()
            if changed:
                os.rename(dbcache_file + '.new', dbcache_file)
            else:
                os.remove(dbcache_file + '.new')

        v = Version(prev_install.version.ver)
        f = open(os.path.join(mounts['root'], 'var/tmp/.previousVersion'), 'w')
        f.write("PRODUCT_VERSION='%s'\n" % v)
        f.close()

        state = open(os.path.join(mounts['root'], constants.FIRSTBOOT_DATA_DIR, 'host.conf'), 'w')
        print >>state, "UPGRADE=true"
        state.close()

        # CP-1508: preserve AD service state
        ad_on = False
        try:
            fh = open(os.path.join(mounts['root'], 'etc/nsswitch.conf'), 'r')
            for line in fh:
                if line.startswith('passwd:') and 'lsass' in line:
                    ad_on = True
                    break
            fh.close()
        except:
            pass

        # EA-1069: create interface-rename state from old xapi database if it doesnt currently exist (static-rules.conf)
        if not os.path.exists(os.path.join(mounts['root'], 'etc/sysconfig/network-scripts/interface-rename-data/static-rules.conf')):
            static_text = (
                "# Static rules.  Autogenerated by the installer from either the answerfile or from previous install\n"
                "# WARNING - rules in this file override the 'lastboot' assignment of names,\n"
                "#           so editing it may cause unexpected renaming on next boot\n\n"
                "# Rules are of the form:\n"
                "#   target name: id method = \"value\"\n\n"

                "# target name must be in the form eth*\n"
                "# id methods are:\n"
                "#   mac: value should be the mac address of a device (e.g. DE:AD:C0:DE:00:00)\n"
                "#   pci: value should be the pci bus location of the device (e.g. 0000:01:01.1)\n"
                "#   ppn: value should be the result of the biosdevname physical naming policy of a device (e.g. pci1p1)\n"
                "#   label: value should be the SMBios label of a device (for SMBios 2.6 or above)\n")

            if not os.path.exists(os.path.join(mounts['root'], 'etc/sysconfig/network-scripts/interface-rename-data/.from_install/')):
                os.makedirs(os.path.join(mounts['root'], 'etc/sysconfig/network-scripts/interface-rename-data/.from_install/'), 0775)
            
            fout1 = open(os.path.join(mounts['root'], 'etc/sysconfig/network-scripts/interface-rename-data/static-rules.conf'), "w")
            fout1.write(static_text)
            fout1.close()
            fout2 = open(os.path.join(mounts['root'], 'etc/sysconfig/network-scripts/interface-rename-data/.from_install/static-rules.conf'), "w")
            fout2.write(static_text)
            fout2.close()

            bdn = BiosDevName()
            bdn.run()
            devices = bdn.devices

            # this is a dirty hack but I cant think of much better
            dbcache = open(os.path.join(mounts['root'], constants.DBCACHE), "r")
            past_devs = []
            
            mac_next = False
            eth_next = False

            for line in ( x.strip() for x in dbcache ):

                if mac_next:
                    past_devs.append([line.upper()])
                    mac_next = False
                    continue

                if eth_next:
                    for bdev in devices:
                        if bdev.get('Assigned MAC', None) == past_devs[-1][0] and 'Bus Info' in bdev:
                            past_devs[-1].extend([bdev['Bus Info'], line])
                            break
                    eth_next = False
                    continue
                
                if line == "<MAC>":
                    mac_next = True
                    continue

                if line == "<device>":
                    eth_next = True

            def jsonify(mac, pci, dev):
                return '[ "%s", "%s", "%s" ]' % (mac, pci, dev)

            dynamic_text = ("# Automatically adjusted file.  Do not edit unless you are certain you know how to\n")
            dynamic_text += '{"lastboot":[%s],"old":[]}' % (','.join(map(lambda x: jsonify(*x), past_devs)), )

            fout3 = open(os.path.join(mounts['root'], 'etc/sysconfig/network-scripts/interface-rename-data/dynamic-rules.json'), "w")
            fout3.write(dynamic_text)
            fout3.close()
            fout4 = open(os.path.join(mounts['root'], 'etc/sysconfig/network-scripts/interface-rename-data/.from_install/dynamic-rules.json'), "w")
            fout4.write(dynamic_text)
            fout4.close()

        if ad_on:
            for service in ['dcerpd', 'eventlogd', 'netlogond', 'npcmuxd', 'lsassd']:
                util.runCmd2(['chroot', mounts['root'], 'chkconfig', '--add', service])



################################################################################

# Upgraders provided here, in preference order:
class UpgraderList(list):
    def getUpgrader(self, product, version, variant):
        for x in self:
            if x.upgrades(product, version, variant):
                return x
        raise KeyError, "No upgrader found for %s" % version

    def hasUpgrader(self, product, version, variant):
        for x in self:
            if x.upgrades(product, version, variant):
                return True
        return False
    
__upgraders__ = UpgraderList([ ThirdGenUpgrader ])

def filter_for_upgradeable_products(installed_products):
    upgradeable_products = filter(lambda p: p.isUpgradeable() and upgradeAvailable(p),
        installed_products)
    return upgradeable_products
