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
import tempfile
import xelogging
from variant import *
import repository
from disktools import *

class SettingsNotAvailable(Exception):
    pass

class Version(object):
    ANY = -1
    INF = 999
    
    def __init__(self, major, minor, release, build = ANY, suffix = "", buildsuffix = ""):
        assert type(major) is int
        assert type(minor) is int
        assert type(release) is int
        self.major = major
        self.minor = minor
        self.release = release
        self.build = build
        self.suffix = suffix
        self.buildsuffix = buildsuffix

    def from_string(cls, vstr):
        """ Create a Version object given an input string vstr.  vstr should be
        of one of the following forms:

            a.b.cs   a.b.cs-bt

        for integers a, b, c, and b representing the major, minor, relase, and
        build number elements of the version.  s and t are alphanumeric strings
        that begin with an alphabetic character to distinguish them from c and
        b respectively.  s and t should NOT contain the hyphen character. """

        if vstr.find("-") != -1:
            vs, bs = vstr.split("-")
        else:
            vs, bs = vstr, None
            vbuild = cls.ANY
            vbuildsuffix = ""

        vmaj_s, vmin_s, vrelsuf_s = vs.split(".")
        match = re.match("([0-9]+)(.*)", vrelsuf_s)
        vrel_s, vsuf_s = match.group(1), match.group(2)

        if bs:
            match = re.match("([0-9]+)(.*)", bs)
            vbuild = int(match.group(1))
            vbuildsuffix = match.group(2)

        return cls(int(vmaj_s), int(vmin_s), int(vrel_s), suffix = vsuf_s,
                   build = vbuild, buildsuffix = vbuildsuffix)
    from_string = classmethod(from_string)

    def __lt__(self, v):
        if not type(v) == type(self): return False
        assert not self.ANY in [self.major, self.minor, self.release]
        return ( self.major < v.major or
                 (self.major == v.major and self.minor < v.minor) or
                 (self.major == v.major and self.minor == v.minor and self.release < v.release) or
                 (self.major == v.major and self.minor == v.minor and self.release == v.release and self.cmp_suffix(self.suffix,v.suffix) == -1) )

    def __eq__(self, v):
        if not type(v) == type(self): return False
        return ( self.cmp_version_number(self.major, v.major) == 0 and
                 self.cmp_version_number(self.minor, v.minor) == 0 and
                 self.cmp_version_number(self.release, v.release) == 0  and
                 self.cmp_version_number(self.build, v.build) == 0 and
                 self.suffix == v.suffix )

    def __le__(self, v):
        if not type(v) == type(self): return False
        return self < v or self == v

    def __ge__(self, v):
        if not type(v) == type(self): return False
        return self > v or self == v
    
    def __gt__(self, v):
        if not type(v) == type(self): return False
        assert not self.ANY in [self.major, self.minor, self.release]
        return ( self.major > v.major or
                 (self.major == v.major and self.minor > v.minor) or
                 (self.major == v.major and self.minor == v.minor and self.release > v.release) or
                 (self.major == v.major and self.minor == v.minor and self.release == v.release and self.cmp_suffix(self.suffix, v.suffix) == 1) )

    def __str__(self):
        if self.build == self.ANY:
            return "%d.%d.%d%s" % (self.major, self.minor, self.release, self.suffix)
        else:
            return "%d.%d.%d%s-%d%s" % (self.major, self.minor, self.release, self.suffix, self.build, self.buildsuffix)

    def cmp_suffix(cls, s1, s2):
        """ Compare suffixes.  Empty suffix is bigger than anything, else
        just do a lexicographic comparison. """
        if s1 == s2:
            return 0
        elif s1 == '':
            return 1
        elif s2 == '':
            return -1
        else:
            return s1 < s2

    cmp_suffix = classmethod(cmp_suffix)

    def cmp_version_number(cls, v1, v2):
        if v1 == cls.ANY or v2 == cls.ANY:
            return 0
        else:
            if v1 < v2:
                return -1
            elif v1 == v2:
                return 0
            elif v1 > v2:
                return 1
            
    cmp_version_number = classmethod(cmp_version_number)

THIS_PRODUCT_VERSION = Version.from_string(version.PRODUCT_VERSION)
XENSERVER_5_5_0 = Version(5,5,0)

class ExisitingInstallation:
    def __init__(self, primary_disk, boot_device, state_device):
        self.primary_disk = primary_disk
        self.boot_device = boot_device
        self.state_device = state_device
        self.state_prefix = ''
        self.settings = None

    def __str__(self):
        return "%s v%s on %s" % (
            self.brand, str(self.version), self.root_device)

    def mount_state(self):
        """ Mount main state partition on self.state_mountpoint. """
        self.state_mountpoint = tempfile.mkdtemp('-state')
        util.mount(self.state_device, self.state_mountpoint, ['ro'], 'ext3')

    def unmount_state(self):
        util.umount(self.state_mountpoint)
        os.rmdir(self.state_mountpoint)
        self.state_mountpoint = None

    def join_state_path(self, *path):
        """ Construct an absolute path to a file in the main state partition. """
        return os.path.join(self.state_mountpoint, self.state_prefix, *path)

    def getInventoryValue(self, k):
        return self.inventory[k]

    def isUpgradeable(self):
        try:
            self.mount_state()
            state_files = os.listdir(self.join_state_path('etc/firstboot.d/state'))
            firstboot_files = [ f for f in os.listdir(self.join_state_path('etc/firstboot.d')) \
                                if f[0].isdigit() and os.stat(self.join_state_path('etc/firstboot.d', f))[stat.ST_MODE] & stat.S_IXUSR ]

            result = (len(state_files) == len(firstboot_files))
            if not result:
                xelogging.log('Upgradeability test failed:')
                xelogging.log('  Firstboot:'+', '.join(firstboot_files))
                xelogging.log('  State: '+', '.join(state_files))
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
        
        results = {}
        if self.version < XENSERVER_5_5_0:
            raise SettingsNotAvailable, "version too old"

        try:
            self.mount_state()

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
                # No timezone found: a common case on a default OEM installation.
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
            # keymap configured: a common case being a default OEM installation.
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
            for file in filter(lambda x: True in [x.startswith(y) for y in ['ifcfg-eth', 'ifcfg-bond']], \
                                   os.listdir(self.join_state_path('etc/sysconfig/network-scripts'))):
                devcfg = util.readKeyValueFile(self.join_state_path('etc/sysconfig/network-scripts', file), strip_quotes = False)
                if devcfg.has_key('DEVICE') and devcfg.has_key('BRIDGE') and devcfg['BRIDGE'] == self.getInventoryValue('MANAGEMENT_INTERFACE'):
                    brcfg = util.readKeyValueFile(self.join_state_path('etc/sysconfig/network-scripts', 'ifcfg-'+devcfg['BRIDGE']), strip_quotes = False)
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

                    default = lambda d, k, v: d.has_key(k) and d[k] or v

                    #results['net-admin-configuration'] = {'enabled': True}
                    if (not brcfg.has_key('BOOTPROTO')) or brcfg['BOOTPROTO'] != 'dhcp':
                        ip = default(brcfg, 'IPADDR', None)
                        netmask = default(brcfg, 'NETMASK', None)
                        gateway = default(brcfg, 'GATEWAY', None)

                        if not ip or not netmask:
                            raise SettingsNotAvailable, "IP address or netmask missing"
                        
                        # read resolv.conf for DNS
                        dns = None
                        try:
                            f = open(this.join_state_path('etc/resolv.conf'), 'r')
                            lines = f.readlines()
                            f.close()
                            for line in lines:
                                if line.startswith('nameserver '):
                                    dns = line[11:]
                                    break
                        except:
                            pass

                        results['net-admin-configuration'] = NetInterface(NetInterface.Static, hwaddr, ip, netmask, gateway, dns)
                    else:
                        results['net-admin-configuration'] = NetInterface(NetInterface.DHCP, hwaddr)
                    break

            repo_list = []
            if os.path.exists(self.join_state_path(constants.INSTALLED_REPOS_DIR)):
                try:
                    for repo_id in os.listdir(self.join_state_path(constants.INSTALLED_REPOS_DIR)):
                        repo = repository.Repository(repository.FilesystemAccessor(self.join_state_path(constants.INSTALLED_REPOS_DIR, repo_id)))
                        repo_list.append((repo.identifier(), repo.name(), (repo_id != constants.MAIN_REPOSITORY_NAME)))
                except Exception, e:
                    xelogging.log('Scan for driver disks failed:')
                    xelogging.log_exception(e)

            results['repo-list'] = repo_list

            results['ha-armed'] = False
            try:
                db = open(self.join_state_path("var/xapi/local.db"), 'r')
                if db.readline().find('<row key="ha.armed" value="true"') != -1:
                    results['ha-armed'] = True
                db.close()
            except:
                pass

        finally:
            self.unmount_state()

        return results

    def readSettings(self):
        if not self.settings:
            self.settings = self._readSettings()
        return self.settings


class ExistingRetailInstallation(ExisitingInstallation):
    def __init__(self, primary_disk, boot_device, state_device, storage):
        self.variant = 'Retail'
        ExisitingInstallation.__init__(self, primary_disk, boot_device, state_device)
        self.root_device = boot_device
        self.readInventory()

    def __repr__(self):
        return "<ExistingRetailInstallation: %s>" % self

    def mount_root(self):
        self.root_mountpoint = tempfile.mkdtemp('-root')
        util.mount(self.root_device, self.root_mountpoint, ['ro'], 'ext3')

    def unmount_root(self):
        util.umount(self.root_mountpoint)
        os.rmdir(self.root_mountpoint)
        self.root_mountpoint = None

    def readInventory(self):
        try:
            self.mount_root()
            self.inventory = util.readKeyValueFile(os.path.join(self.root_mountpoint, constants.INVENTORY_FILE), strip_quotes = True)
            self.name = self.inventory['PRODUCT_NAME']
            self.brand = self.inventory['PRODUCT_BRAND']
            self.version = Version.from_string("%s-%s" % (self.inventory['PRODUCT_VERSION'], self.inventory['BUILD_NUMBER']))
            self.build = self.inventory['BUILD_NUMBER']
        finally:
            self.unmount_root()

    def backupFileSystem(self, backup_partition):
        # format the backup partition:
        if util.runCmd2(['mkfs.ext3', backup_partition]) != 0:
            raise Exception,  "Backup: Failed to format filesystem on %s" % backup_partition

        # copy the files across:
        primary_mount = '/tmp/backup/primary'
        backup_mount  = '/tmp/backup/backup'
        for mnt in [primary_mount, backup_mount]:
            util.assertDir(mnt)
        try:
            util.mount(self.root_device, primary_mount, options = ['ro'])
            util.mount(backup_partition,  backup_mount)
            cmd = ['cp', '-a'] + \
                  [ os.path.join(primary_mount, x) for x in os.listdir(primary_mount) ] + \
                  ['%s/' % backup_mount]
            assert util.runCmd2(cmd) == 0
        finally:
            for mnt in [primary_mount, backup_mount]:
                util.umount(mnt)

class ExistingOEMInstallation(ExisitingInstallation):
    def __init__(self, primary_disk, boot_device, state_device):
        self.variant = "OEM"
        ExisitingInstallation.__init__(self, primary_disk, boot_device, state_device)

        # determine active root partition
        mountpoint = tempfile.mkdtemp('-oem-boot')
        try:
            util.mount(boot_device, mountpoint, ['ro'], 'vfat')
            root_part = -1
            try:
                fd = open(os.path.join(mountpoint, constants.SYSLINUX_CFG))
                for line in fd:
                    tokens = line.split()
                    if tokens[0] == 'DEFAULT':
                        root_part = int(tokens[1])
                        break
                fd.close()
            except:
                raise Exception, "Failed to locate root device from %s" % boot_device
        finally:
            util.umount(mountpoint)
            os.rmdir(mountpoint)

        assert root_part > 0
        self.root_device = diskutil.partitionFromDisk(diskutil.diskFromPartition(boot_device), root_part)
        self.readInventory()

        self.auxiliary_state_devices = []
        db_conf = {}
        try:
            # read xapi db config
            self.mount_state()
            dbcf = open(self.join_state_path('etc/xensource/db.conf'), 'r')
            for l in dbcf:
                line = l.strip()
                if line.startswith('[/'):
                    filename = line.strip('[]')
                    db_conf[filename] = {}
                else:
                    tokens = line.split(':')
                    if len(tokens) == 2:
                        db_conf[filename][tokens[0]] = tokens[1]
            dbcf.close()
        finally:
            self.unmount_state()

        # locate any auxiliary state partitions
        tool = LVMTool()
        for k, v in db_conf.items():
            if k.startswith('/var/xsconfig/LV') and v['is_on_remote_storage'] == 'false':
                comps = k.split('/')
                lv = comps[3].replace('--', '-')
                vg = tool.vGContainingLV(lv)
                part = None
                for pv in tool.pvs:
                    if pv['vg_name'] == vg:
                        part = pv['pv_name']
                        break
                assert part
                self.auxiliary_state_devices.append({'device': part, 'vg': vg, 'lv': lv})

        xelogging.log(self.auxiliary_state_devices)

    def __repr__(self):
        return "<ExistingOEMInstallation: %s>" % self

    def mount_root(self):
        self.root_mountpoint2 = tempfile.mkdtemp('-root')
        self.root_mountpoint = tempfile.mkdtemp('-loop')
        util.mount(self.root_device, self.root_mountpoint2, ['ro'], 'ext3')
        util.mount(os.path.join(self.root_mountpoint2, 'rootfs'), self.root_mountpoint, ['loop', 'ro'], 'squashfs')

    def unmount_root(self):
        util.umount(self.root_mountpoint)
        os.rmdir(self.root_mountpoint)
        self.root_mountpoint = None
        util.umount(self.root_mountpoint2)
        os.rmdir(self.root_mountpoint2)

    def join_state_path(self, *path):
        if self.state_prefix != '':
            p = os.path.join(self.state_mountpoint, self.state_prefix, 'etc/freq-etc', *path)
            if os.path.exists(p):
                return p
        return os.path.join(self.state_mountpoint, self.state_prefix, *path)

    def readInventory(self):
        try:
            self.mount_root()
            # read read-only inventory to determine build
            ro_inventory = util.readKeyValueFile(os.path.join(self.root_mountpoint, constants.INVENTORY_FILE), strip_quotes = True)
            self.build = ro_inventory['BUILD_NUMBER']
        finally:
            self.unmount_root()

        self.state_prefix = "xe-%s" % self.build
        try:
            self.mount_state()
            # read inventory in state partition
            self.inventory = util.readKeyValueFile(self.join_state_path(constants.INVENTORY_FILE), strip_quotes = True)
            self.name = self.inventory['PRODUCT_NAME']
            self.brand = self.inventory['PRODUCT_BRAND']
            self.version = Version.from_string("%s-%s" % (self.inventory['PRODUCT_VERSION'], self.inventory['BUILD_NUMBER']))
        finally:
            self.unmount_state()

    def backupFileSystem(self, backup_partition):
        def readDbGen(root_dir):
            gen = -1
            try:
                genfd = open(os.path.join(root_dir, 'var/xapi/state.db.generation'), 'r')
                gen = int(genfd.readline())
                genfd.close()
            except:
                pass
            return gen

        # format the backup partition:
        if util.runCmd2(['mkfs.ext3', backup_partition]) != 0:
            raise Exception,  "Backup: Failed to format filesystem on %s" % backup_partition

        primary_mount = '/tmp/backup/primary'
        backup_mount  = '/tmp/backup/backup'
        for mnt in [primary_mount, backup_mount]:
            util.assertDir(mnt)

        util.mount(backup_partition, backup_mount)

        db_generation = (-1, None, None)
        try:
            # copy from primary state partition:
            util.mount(self.state_device, primary_mount, options = ['ro'])
            root_dir = os.path.join(primary_mount, self.state_prefix)
            gen = readDbGen(root_dir)

            xelogging,log("Copying state from %s" % root_dir)
            cmd = ['cp', '-a'] + \
                  [ os.path.join(root_dir, x) for x in os.listdir(root_dir) ] + \
                  ['%s/' % backup_mount]
            assert util.runCmd2(cmd) == 0
            if gen > db_generation[0]:
                db_generation = (gen, self.state_device, self.state_prefix)
            
            util.umount(primary_mount)
            cmd = ['cp', '-a', os.path.join(root_dir, 'etc/freq-etc/etc'), '%s/' % backup_mount]
            assert util.runCmd2(cmd) == 0

            # copy from auxiliary state partitions:
            for state_device in self.auxiliary_state_devices:
                util.mount(state_device, primary_mount, options = ['ro'])
                root_dir = os.path.join(primary_mount, self.inventory['XAPI_DB_COMPAT_VERSION'])
                gen = readDbGen(root_dir)
                
                xelogging,log("Copying state from %s" % root_dir)
                cmd = ['cp', '-a'] + \
                      [ os.path.join(root_dir, x) for x in os.listdir(root_dir) ] + \
                      ['%s/' % backup_mount]
                assert util.runCmd2(cmd) == 0
                if gen > db_generation[0]:
                    db_generation = (gen, state_device, self.inventory['XAPI_DB_COMPAT_VERSION'])
                util.umount(primary_mount)

            # always keep the state with the highest db generation count
            if db_generation[0] > gen:
                 util.mount(db_generation[1], primary_mount, options = ['ro'])
                 root_dir = os.path.join(primary_mount, db_generation[2])

                 xelogging,log("Copying state from %s" % root_dir)
                 cmd = ['cp', '-a'] + \
                       [ os.path.join(root_dir, x) for x in os.listdir(root_dir) ] + \
                       ['%s/' % backup_mount]
                 assert util.runCmd2(cmd) == 0
        finally:
            for mnt in [primary_mount, backup_mount]:
                util.umount(mnt)


def findXenSourceBackups():
    """Scans the host and find partitions containing backups of XenSource
    products.  Returns a list of device node paths to partitions containing
    said backups. """
    Variant.inst().raiseIfOEM('findXenSourceBackups')
    partitions = diskutil.getQualifiedPartitionList()
    backups = []
    try:
        mnt = tempfile.mkdtemp(prefix = 'backup-', dir = '/tmp')
        for p in partitions:
            try:
                util.mount(p, mnt, fstype = 'ext3', options = ['ro'])
                if os.path.exists(os.path.join(mnt, '.xen-backup-partition')):
                    if os.path.exists(os.path.join(mnt, constants.INVENTORY_FILE)):
                        inv = readInventoryFile(os.path.join(mnt, constants.INVENTORY_FILE))
                        if inv.has_key('PRIMARY_DISK'):
                            backups.append((p, inv['PRIMARY_DISK']))
            except util.MountFailureException, e:
                pass
            else:
                util.umount(mnt)
    finally:
        while os.path.ismount(mnt):
            util.umount(mnt)
        os.rmdir(mnt)

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
        if boot[0] == diskutil.INSTALL_RETAIL:
            inst = ExistingRetailInstallation(disk, boot[1], state[1], storage)
        elif boot[0] == diskutil.INSTALL_OEM:
            inst = ExistingOEMInstallation(disk, boot[1], state[1])

        if inst:
            xelogging.log("Found an installation: %s" % str(inst))
            installs.append(inst)

    return installs

def readInventoryFile(filename):
    return util.readKeyValueFile(filename, strip_quotes = True)

def readNetworkScriptFile(filename):
    netkeys = [
        'BOOTPROTO', 'ONBOOT', 'DEVICE', 'TYPE', 'HWADDR', 'BRIDGE', 'LINEDELAY',
        'DELAY', 'STP', 'NETMASK', 'IPADDR', 'NETMASK', 'GATEWAY', 'PEERDNS',
        'NETWORK', 'BROADCAST', 'NAME'
        ]
    return util.readKeyValueFile(filename, allowed_keys = netkeys, strip_quotes = True)

def find_installed_products():
    try:
        installed_products = findXenSourceProducts()
    except Exception, e:
        xelogging.log("A problem occurred whilst scanning for existing installations:")
        xelogging.log_exception(e)
        xelogging.log("This is not fatal.  Continuing anyway.")
        installed_products = []
    return installed_products
            
