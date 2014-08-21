# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Manage product installations
#
# written by Andrew Peace

import os

import diskutil
import util
import netutil
from netinterface import *
import constants
import version
import re
import stat
import xelogging
import repository
from disktools import *
import hardware
import xcp
import xcp.bootloader as bootloader
from xcp.version import *
import xml.dom.minidom
import simplejson as json

class SettingsNotAvailable(Exception):
    pass

THIS_PRODUCT_VERSION = Version.from_string(version.PRODUCT_VERSION)
THIS_PLATFORM_VERSION = Version.from_string(version.PLATFORM_VERSION)
XENSERVER_5_6_0 = Version([5, 6, 0])
XENSERVER_5_6_100 = Version([5, 6, 100])
XCP_1_6_0 = Version([1, 6, 0])

class ExistingInstallation:
    def __init__(self, primary_disk, boot_device, state_device):
        self.primary_disk = primary_disk
        self.boot_device = boot_device
        self.state_device = state_device
        self.state_prefix = ''
        self.settings = None
        self.root_fs = None

    def __str__(self):
        return "%s %s" % (
            self.brand, str(self.version))

    def mount_state(self):
        """ Mount main state partition on self.state_fs. """
        self.state_fs = util.TempMount(self.state_device, 'state-', )

    def unmount_state(self):
        self.state_fs.unmount()
        self.state_fs = None

    def join_state_path(self, *path):
        """ Construct an absolute path to a file in the main state partition. """
        return os.path.join(self.state_fs.mount_point, self.state_prefix, *path)

    def getInventoryValue(self, k):
        return self.inventory[k]

    def isUpgradeable(self):
        self.mount_state()
        try:
            # CA-38459: handle missing firstboot directory e.g. Rio
            if not os.path.exists(self.join_state_path('etc/firstboot.d/state')):
                return False
            firstboot_files = [ f for f in os.listdir(self.join_state_path('etc/firstboot.d')) \
                                if f[0].isdigit() and os.stat(self.join_state_path('etc/firstboot.d', f))[stat.ST_MODE] & stat.S_IXUSR ]
            missing_state_files = filter(lambda x: not os.path.exists(self.join_state_path('etc/firstboot.d/state', x)), firstboot_files)

            result = (len(missing_state_files) == 0)
            if not result:
                xelogging.log('Upgradeability test failed:')
                xelogging.log('  Firstboot:     '+', '.join(firstboot_files))
                xelogging.log('  Missing state: '+', '.join(missing_state_files))
        finally:
            self.unmount_state()
        return result

    def settingsAvailable(self):
        try:
            self.readSettings()
        except SettingsNotAvailable, text:
            xelogging.log("Settings unavailable: %s" % text)
            return False
        except Exception, e:
            xelogging.log("Settings unavailable: unhandled exception")
            xelogging.log_exception(e)
            return False
        else:
            return True

    def _readSettings(self):
        """ Read settings from the installation, returns a results dictionary. """
        
        results = { 'host-config': {} }

        self.mount_state()
        try:

            # timezone:
            tz = None
            clock_file = self.join_state_path('etc/sysconfig/clock')
            if os.path.exists(clock_file):
                fd = open(clock_file, 'r')
                lines = fd.readlines()
                fd.close()
                for line in lines:
                    if line.startswith("ZONE="):
                        tz = line[5:].strip()
            if not tz:
                # No timezone found: 
                # Supply a default and for interactive installs prompt the user.
                xelogging.log('No timezone configuration found.')
                results['request-timezone'] = True
                tz = "Europe/London"
            results['timezone'] = tz

            # hostname.  We will assume one was set anyway and thus write
            # it back into the new filesystem.  If one wasn't set then this
            # will be localhost.localdomain, in which case the old behaviour
            # will persist anyway:
            fd = open(self.join_state_path('etc/sysconfig/network'), 'r')
            lines = fd.readlines()
            fd.close()
            for line in lines:
                if line.startswith('HOSTNAME='):
                    results['manual-hostname'] = (True, line[9:].strip())
            if not results.has_key('manual-hostname'):
                results['manual-hostname'] = (False, None)

            # nameservers:
            domain = None
            if not os.path.exists(self.join_state_path('etc/resolv.conf')):
                results['manual-nameservers'] = (False, None)
            else:
                ns = []
                fd = open(self.join_state_path('etc/resolv.conf'), 'r')
                lines = fd.readlines()
                fd.close()
                for line in lines:
                    if line.startswith("nameserver "):
                        ns.append(line[11:].strip())
                    elif line.startswith("domain "):
                        domain = line[8:].strip()
                    elif line.startswith("search "):
                        domain = line.split()[1]
                results['manual-nameservers'] = (True, ns)

            # ntp servers:
            fd = open(self.join_state_path('etc/ntp.conf'), 'r')
            lines = fd.readlines()
            fd.close()
            ntps = []
            for line in lines:
                if line.startswith("server "):
                    ntps.append(line[7:].strip())
            results['ntp-servers'] = ntps

            # keyboard:
            keyboard_file = self.join_state_path('etc/sysconfig/keyboard')
            if os.path.exists(keyboard_file):
                fd = open(keyboard_file, 'r')
                lines = fd.readlines()
                fd.close()
                for line in lines:
                    if line.startswith('KEYTABLE='):
                        results['keymap'] = line[9:].strip()
            # Do not error here if no keymap configuration is found.
            # This enables upgrade to still carry state on hosts without
            # keymap configured: 
            # A default keymap is assigned in the backend of this installer.
            if not results.has_key('keymap'):
                xelogging.log('No existing keymap configuration found.')

            # root password:
            fd = open(self.join_state_path('etc/passwd'), 'r')
            root_pwd = None
            for line in fd:
                pwent = line.split(':')
                if pwent[0] == 'root':
                    root_pwd = pwent[1]
                    break
            fd.close()
            if len(root_pwd) == 1:
                root_pwd = None
                try:
                    fd = open(self.join_state_path('etc/shadow'), 'r')
                    for line in fd:
                        pwent = line.split(':')
                        if pwent[0] == 'root':
                            root_pwd = pwent[1]
                            break
                    fd.close()
                except:
                    pass

            if not root_pwd:
                raise SettingsNotAvailable, "no root password found"
            results['root-password'] = ('pwdhash', root_pwd)

            # don't care about this too much.
            results['time-config-method'] = 'ntp'

            # read network configuration.  We only care to find out what the
            # management interface is, and what its configuration was.
            # The dev -> MAC mapping for other devices will be preserved in the
            # database which is available in time for everything except the
            # management interface.
            mgmt_iface = self.getInventoryValue('MANAGEMENT_INTERFACE')

            networkdb_path = constants.NETWORK_DB
            if not os.path.exists(self.join_state_path(networkdb_path)):
                networkdb_path = constants.OLD_NETWORK_DB
            dbcache_path = constants.DBCACHE
            if not os.path.exists(self.join_state_path(dbcache_path)):
                dbcache_path = constants.OLD_DBCACHE

            if os.path.exists(self.join_state_path(networkdb_path)):
                networkd_db = constants.NETWORKD_DB
                if not os.path.exists(self.join_state_path(networkd_db)):
                    networkd_db = constants.OLD_NETWORKD_DB

                args = ['chroot', self.state_fs.mount_point, '/'+networkd_db, '-bridge', mgmt_iface, '-iface', mgmt_iface]
                rv, out = util.runCmd2(args, with_stdout = True)

                d = {}
                for line in ( x for x in out.split('\n') if len(x.strip()) ):
                    var = line.split('=', 1)
                    d[var[0]] = var[1]

                results['net-admin-bridge'] = mgmt_iface
                results['net-admin-interface'] = d.get('interfaces').split(',')[0]

                if_hwaddr = netutil.getHWAddr(results['net-admin-interface'])

                proto = d.get('mode')
                if proto == 'static':
                    ip = d.get('ipaddr')
                    netmask = d.get('netmask')
                    gateway = d.get('gateway')
                    dns = d.get('dns', '').split(',')
                    if ip and netmask:
                        results['net-admin-configuration'] = NetInterface(NetInterface.Static, if_hwaddr, ip, netmask, gateway, dns)
                elif proto == 'dhcp':
                    results['net-admin-configuration'] = NetInterface(NetInterface.DHCP, if_hwaddr)
                else:
                    results['net-admin-configuration'] = NetInterface(None, if_hwaddr)

                protov6 = d.get('modev6')
                if protov6 == 'static':
                    ipv6 = d.get('ipaddrv6')
                    gatewayv6 = d.get('gatewayv6')
                    if ipv6:
                        results['net-admin-configuration'].addIPv6(NetInterface.Static, ipv6, gatewayv6)
                elif protov6 == 'dhcp':
                    results['net-admin-configuration'].addIPv6(NetInterface.DHCP)
                elif protov6 == 'autoconf':
                    results['net-admin-configuration'].addIPv6(NetInterface.Autoconf)
                    
            elif os.path.exists(self.join_state_path(dbcache_path)):
                def getText(nodelist):
                    rc = ""
                    for node in nodelist:
                        if node.nodeType == node.TEXT_NODE:
                            rc = rc + node.data
                    return rc.strip().encode()
                
                xmldoc = xml.dom.minidom.parse(self.join_state_path(dbcache_path))

                pif_uid = None
                for node in xmldoc.documentElement.childNodes:
                    if node.nodeType == node.ELEMENT_NODE and node.tagName == 'network':
                        network = node
                    else:
                        continue
                    # CA-50971: handle renamed networks in MNR
                    if len(network.getElementsByTagName('bridge')) == 0 or \
                       len(network.getElementsByTagName('PIFs')) == 0 or \
                       len(network.getElementsByTagName('PIFs')[0].getElementsByTagName('PIF')) == 0:
                        continue
                
                    if getText(network.getElementsByTagName('bridge')[0].childNodes) == mgmt_iface:
                        pif_uid = getText(network.getElementsByTagName('PIFs')[0].getElementsByTagName('PIF')[0].childNodes)
                        break
                if pif_uid:
                    for node in xmldoc.documentElement.childNodes:
                        if node.nodeType == node.ELEMENT_NODE and node.tagName == 'pif':
                            pif = node
                        else:
                            continue
                        if pif.getAttribute('ref') == pif_uid:
                            results['net-admin-interface'] = getText(pif.getElementsByTagName('device')[0].childNodes)
                            results['net-admin-bridge'] = mgmt_iface
                            results['net-admin-configuration'] = NetInterface.loadFromPif(pif)
                            break
            else:
                for cfile in filter(lambda x: True in [x.startswith(y) for y in ['ifcfg-eth', 'ifcfg-bond']], \
                                   os.listdir(self.join_state_path(constants.NET_SCR_DIR))):
                    devcfg = util.readKeyValueFile(self.join_state_path(constants.NET_SCR_DIR, cfile), strip_quotes = False)
                    if devcfg.has_key('DEVICE') and devcfg.has_key('BRIDGE') and devcfg['BRIDGE'] == mgmt_iface:
                        brcfg = util.readKeyValueFile(self.join_state_path(constants.NET_SCR_DIR, 'ifcfg-'+devcfg['BRIDGE']), strip_quotes = False)
                        results['net-admin-interface'] = devcfg['DEVICE']
                        results['net-admin-bridge'] = devcfg['BRIDGE']

                        # get hardware address if it was recorded, otherwise look it up:
                        if devcfg.has_key('HWADDR'):
                            hwaddr = devcfg['HWADDR']
                        elif devcfg.has_key('MACADDR'):
                            # our bonds have a key called MACADDR instead
                            hwaddr = devcfg['MACADDR']
                        else:
                            # XXX what if it's been renamed out of existence?
                            try:
                                hwaddr = netutil.getHWAddr(devcfg['DEVICE'])
                            except:
                                hwaddr = None

                        ifcfg = NetInterface.loadFromIfcfg(self.join_state_path(constants.NET_SCR_DIR, 'ifcfg-'+devcfg['BRIDGE']))
                        if not ifcfg.hwaddr:
                            ifcfg.hwaddr = hwaddr
                        if ifcfg.isStatic() and not ifcfg.domain and domain:
                            ifcfg.domain = domain
                        results['net-admin-configuration'] = ifcfg
                        break

            repo_list = []
            if os.path.exists(self.join_state_path(constants.INSTALLED_REPOS_DIR)):
                try:
                    for repo_id in os.listdir(self.join_state_path(constants.INSTALLED_REPOS_DIR)):
                        try:
                            repo = repository.Repository(repository.FilesystemAccessor(self.join_state_path(constants.INSTALLED_REPOS_DIR, repo_id)))
                            repo_list.append((repo.identifier(), repo.name(), (repo_id != constants.MAIN_REPOSITORY_NAME)))
                        except repository.RepoFormatError:
                            # probably pre-XML format
                            repo = open(self.join_state_path(constants.INSTALLED_REPOS_DIR, repo_id, repository.Repository.REPOSITORY_FILENAME))
                            repo_id = repo.readline().strip()
                            repo_name = repo.readline().strip()
                            repo.close()
                            repo_list.append((repo_id, repo_name, (repo_id != constants.MAIN_REPOSITORY_NAME)))
                except Exception, e:
                    xelogging.log('Scan for driver disks failed:')
                    xelogging.log_exception(e)

            results['repo-list'] = repo_list

            results['ha-armed'] = False
            try:
                db_path = "var/lib/xcp/local.db"
		if not os.path.exists(self.join_state_path(db_path)):
                    db_path = "var/xapi/local.db"
                db = open(self.join_state_path(db_path), 'r')
                if db.readline().find('<row key="ha.armed" value="true"') != -1:
                    results['ha-armed'] = True
                db.close()
            except:
                pass

            try:
                network_conf = open(self.join_state_path("etc/xensource/network.conf"), 'r')
                network_backend = network_conf.readline().strip()
                network_conf.close()

                if network_backend == constants.NETWORK_BACKEND_BRIDGE:
                    results['network-backend'] = constants.NETWORK_BACKEND_BRIDGE
                elif network_backend in [constants.NETWORK_BACKEND_VSWITCH, constants.NETWORK_BACKEND_VSWITCH_ALT]:
                    results['network-backend'] = constants.NETWORK_BACKEND_VSWITCH
                else:
                    raise SettingsNotAvailable, "unknown network backend %s" % network_backend
            except:
                pass

            results['master'] = None
            try:
                pt = open(self.join_state_path("etc/xensource/ptoken"), 'r')
                results['pool-token'] = pt.readline().strip()
                pt.close()
                pc = open(self.join_state_path("etc/xensource/pool.conf"), 'r')
                line = pc.readline().strip()
                if line.startswith('slave:'):
                    results['master'] = line[6:]
                pc.close()
            except:
                pass

        finally:
            self.unmount_state()

        # read bootloader config to extract various settings
        boot_fs = None
        try:
            # Boot device
            boot_fs = util.TempMount(self.boot_device, 'boot-', ['ro'], 'ext3')
            boot_config = bootloader.Bootloader.loadExisting(boot_fs.mount_point)

            # Serial console
            if boot_config.serial:
                results['serial-console'] = hardware.SerialPort(boot_config.serial['port'],
                                                                baud = str(boot_config.serial['baud']))
            results['bootloader-location'] = boot_config.location
            if boot_config.default != 'upgrade':
                results['boot-serial'] = (boot_config.default == 'xe-serial')

            # Subset of hypervisor arguments
            xen_args = boot_config.menu[boot_config.default].getHypervisorArgs()

            #   - cpuid_mask
            results['host-config']['xen-cpuid-masks'] = filter(lambda x: x.startswith('cpuid_mask'), xen_args)

            #   - dom0_mem
            dom0_mem_arg = filter(lambda x: x.startswith('dom0_mem'), xen_args)
            (dom0_mem, dom0_mem_min, dom0_mem_max) = xcp.dom0.parse_mem(dom0_mem_arg[0])
            if dom0_mem:
                results['host-config']['dom0-mem'] = dom0_mem / 1024 / 1024
        except:
            pass
        if boot_fs:
            boot_fs.unmount()

        return results

    def readSettings(self):
        if not self.settings:
            self.settings = self._readSettings()
        return self.settings


class ExistingRetailInstallation(ExistingInstallation):
    def __init__(self, primary_disk, boot_device, state_device, storage):
        self.variant = 'Retail'
        ExistingInstallation.__init__(self, primary_disk, boot_device, state_device)
        self.root_device = boot_device
        self.readInventory()

    def __repr__(self):
        return "<ExistingRetailInstallation: %s on %s>" % (str(self), self.root_device)

    def mount_root(self, ro = True):
        opts = None
        if ro:
            opts = ['ro']
        self.root_fs = util.TempMount(self.root_device, 'root', opts, 'ext3')

    def unmount_root(self):
        if self.root_fs:
            self.root_fs.unmount()
            self.root_fs = None

    def readInventory(self):
        self.mount_root()
        try:
            self.inventory = util.readKeyValueFile(os.path.join(self.root_fs.mount_point, constants.INVENTORY_FILE), strip_quotes = True)
            if 'PRODUCT_NAME' in self.inventory:
                self.name = self.inventory['PRODUCT_NAME']
                self.brand = self.inventory['PRODUCT_BRAND']
                self.version = Version.from_string("%s-%s" % (self.inventory['PRODUCT_VERSION'], self.inventory['BUILD_NUMBER']))
            else:
                self.name = self.inventory['PLATFORM_NAME']
                self.brand = self.inventory['PLATFORM_NAME']
                self.version = Version.from_string("%s-%s" % (self.inventory['PLATFORM_VERSION'], self.inventory['BUILD_NUMBER']))
            self.build = self.inventory['BUILD_NUMBER']
        finally:
            self.unmount_root()

class XenServerBackup:
    def __init__(self, part, mnt):
        self.partition = part
        self.inventory = util.readKeyValueFile(os.path.join(mnt, constants.INVENTORY_FILE), strip_quotes = True)
        if 'PRODUCT_NAME' in self.inventory:
            self.name = self.inventory['PRODUCT_NAME']
            self.brand = self.inventory['PRODUCT_BRAND']
            self.version = Version.from_string("%s-%s" % (self.inventory['PRODUCT_VERSION'], self.inventory['BUILD_NUMBER']))
        else:
            self.name = self.inventory['PLATFORM_NAME']
            self.brand = self.inventory['PLATFORM_NAME']
            self.version = Version.from_string("%s-%s" % (self.inventory['PLATFORM_VERSION'], self.inventory['BUILD_NUMBER']))
        self.build = self.inventory['BUILD_NUMBER']
        self.root_disk = diskutil.partitionFromId(self.inventory['PRIMARY_DISK'])

    def __str__(self):
        return "%s %s" % (
            self.brand, str(self.version))

    def __repr__(self):
        return "<XenServerBackup: %s on %s>" % (str(self), self.partition)

def findXenSourceBackups():
    """Scans the host and find partitions containing backups of XenSource
    products.  Returns a list of device node paths to partitions containing
    said backups. """
    partitions = diskutil.getQualifiedPartitionList()
    backups = []

    for p in partitions:
        b = None
        try:
            b = util.TempMount(p, 'backup-', ['ro'], 'ext3')
            if os.path.exists(os.path.join(b.mount_point, '.xen-backup-partition')):
                backups.append(XenServerBackup(p, b.mount_point))
        except:
            pass
        if b:
            b.unmount()

    return backups

def findXenSourceProducts():
    """Scans the host and finds XenSource product installations.
    Returns list of ExistingInstallation objects.

    Currently requires supervisor privileges due to mounting
    filesystems."""

    installs = []

    for disk in diskutil.getQualifiedDiskList():
        (boot, state, storage) = diskutil.probeDisk(disk)

        inst = None
        try:
            if boot[0] == diskutil.INSTALL_RETAIL:
                inst = ExistingRetailInstallation(disk, boot[1], state[1], storage)
        except Exception, e:
            xelogging.log("A problem occurred whilst scanning for existing installations:")
            xelogging.log_exception(e)
            xelogging.log("This is not fatal.  Continuing anyway.")

        if inst:
            xelogging.log("Found an installation: %s" % str(inst))
            installs.append(inst)

    return installs

def readInventoryFile(filename):
    return util.readKeyValueFile(filename, strip_quotes = True)

def find_installed_products():
    try:
        installed_products = findXenSourceProducts()
    except Exception, e:
        xelogging.log("A problem occurred whilst scanning for existing installations:")
        xelogging.log_exception(e)
        xelogging.log("This is not fatal.  Continuing anyway.")
        installed_products = []
    return installed_products
            
