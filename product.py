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
                 (self.major == v.major and self.minor == v.minor and self.release == v.release and self.cmp_version_number(self.build, v.build) == -1) or
                 (self.major == v.major and self.minor == v.minor and self.release == v.release and self.cmp_version_number(self.build, v.build) == 0 and self.cmp_suffix(self.suffix,v.suffix) == -1) )

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
                 (self.major == v.major and self.minor == v.minor and self.release == v.release and self.cmp_version_number(self.build, v.build) == 1) or
                 (self.major == v.major and self.minor == v.minor and self.release == v.release and self.cmp_version_number(self.build, v.build) == 0 and self.cmp_suffix(self.suffix, v.suffix) == 1) )

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
XENSERVER_4_1_0 = Version(4,1,0)

class ExistingInstallation(object):
    def __init__(self, name, brand, version, root_partition, state_partition, inventory, build, variant_class):
        self.name = name
        self.brand = brand
        self.version = version
        self.root_partition = root_partition
        self.state_partition = state_partition
        self.primary_disk = diskutil.diskFromPartition(root_partition)
        self.inventory = inventory
        self.build = build
        self.variant_class = variant_class

    def __str__(self):
        return "%s v%s on %s" % (
            self.brand, str(self.version), self.root_partition)

    def __repr__(self):
        return "<ExistingInstallation: %s>" % self

    def getInventoryValue(self, k):
        return self.inventory[k]

    def isUpgradeable(self):
        def scanPartition(mntpoint):
            state_files = os.listdir(os.path.join(mntpoint, 'etc/firstboot.d/state'))
            firstboot_files = [ f for f in os.listdir(os.path.join(mntpoint, 'etc/firstboot.d')) \
                                    if f[0].isdigit() and os.stat(os.path.join(mntpoint, 'etc/firstboot.d', f))[stat.ST_MODE] & stat.S_IXUSR ]

            result = (len(state_files) == len(firstboot_files))
            if not result:
                xelogging.log('Upgradeability test failed:')
                xelogging.log('  Firstboot:'+', '.join(firstboot_files))
                xelogging.log('  State: '+', '.join(state_files))

            return result
            
        try:
            ret_val = self.variant_class.runOverStatePartition(self.state_partition, scanPartition, self.build)
        except Exception, e:
            xelogging.log('Upgradeability test failed:')
            xelogging.log_exception(e)
            ret_val = False

        if not ret_val:
            xelogging.log("Product %s cannot be upgraded" % str(self))

        return ret_val

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
    
    def readSettings(self):
        """ Read settings from the installation, returns a results dictionary. """
        
        if self.version < XENSERVER_4_1_0:
            raise SettingsNotAvailable, "version too old"
        
        def scanPartition(mntpoint):
            results = {}

            # primary disk:
            results['primary-disk'] = self.primary_disk

            # timezone:
            tz = None
            clock_file = os.path.join(mntpoint, 'etc/sysconfig/clock')
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
            fd = open(os.path.join(mntpoint, 'etc/sysconfig/network'), 'r')
            lines = fd.readlines()
            fd.close()
            for line in lines:
                if line.startswith('HOSTNAME='):
                    results['manual-hostname'] = (True, line[9:].strip())
            if not results.has_key('manual-hostname'):
                results['manual-hostname'] = (False, None)

            # nameservers:
            if not os.path.exists(os.path.join(mntpoint, self.variant_class.ETC_RESOLV_CONF)):
                results['manual-nameservers'] = (False, None)
            else:
                ns = []
                fd = open(os.path.join(mntpoint, self.variant_class.ETC_RESOLV_CONF), 'r')
                lines = fd.readlines()
                fd.close()
                for line in lines:
                    if line.startswith("nameserver "):
                        ns.append(line[11:].strip())
                results['manual-nameservers'] = (True, ns)

            # ntp servers:
            fd = open(os.path.join(mntpoint, self.variant_class.ETC_NTP_CONF), 'r')
            lines = fd.readlines()
            fd.close()
            ntps = []
            for line in lines:
                if line.startswith("server "):
                    ntps.append(line[7:].strip())
            results['ntp-servers'] = ntps

            # keyboard:
            keyboard_file = os.path.join(mntpoint, 'etc/sysconfig/keyboard')
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
            fd = open(os.path.join(mntpoint, 'etc/passwd'), 'r')
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
                                   os.listdir(os.path.join(mntpoint, 'etc/sysconfig/network-scripts'))):
                devcfg = util.readKeyValueFile(os.path.join(mntpoint, 'etc/sysconfig/network-scripts', file), strip_quotes = False)
                if devcfg.has_key('DEVICE') and devcfg.has_key('BRIDGE') and devcfg['BRIDGE'] == self.getInventoryValue('MANAGEMENT_INTERFACE'):
                    brcfg = util.readKeyValueFile(os.path.join(mntpoint, 'etc/sysconfig/network-scripts', 'ifcfg-'+devcfg['BRIDGE']), strip_quotes = False)
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
                            f = open(os.path.join(mntpoint, 'etc/resolv.conf'), 'r')
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
            
            try:
                for repo_id in os.listdir(os.path.join(mntpoint, constants.INSTALLED_REPOS_DIR)):
                    repo = repository.Repository(repository.FilesystemAccessor(os.path.join(mntpoint, constants.INSTALLED_REPOS_DIR, repo_id)))
                    repo_list.append((repo.identifier(), repo.name(), (repo_id != 'xs:main')))
            except Exception, e:
                xelogging.log('Scan for driver disks failed:')
                xelogging.log_exception(e)

            results['repo-list'] = repo_list

            results['ha-armed'] = False
            try:
                db = open(os.path.join(mntpoint, "var/xapi/local.db"), 'r')
                if db.readline().find('<row key="ha.armed" value="true"') != -1:
                    results['ha-armed'] = True
                db.close()
            except:
                pass

            return results
            
        ret_val = self.variant_class.runOverStatePartition(self.state_partition, scanPartition, self.build)

        return ret_val

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
        for v in [VariantRetail, VariantOEMFlash, VariantOEMDisk]:

            found = None
            try:
                found = v.findInstallation(disk)

            except Exception, e:
                xelogging.log("Exception scanning for an installation on %s" % str(disk))
                xelogging.log_exception(e)

            if not found:
                xelogging.log("Test for an installation on %s negative" % str(disk))
                continue

            (inv, rootPartition, statePartition, instVariant) = found

            inst = ExistingInstallation(
                inv['PRODUCT_NAME'],
                inv['PRODUCT_BRAND'],
                Version.from_string("%s-%s" % (inv['PRODUCT_VERSION'], inv['BUILD_NUMBER'])),
                rootPartition,
                statePartition,
                inv,
                inv['BUILD_NUMBER'],
                instVariant
                )

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
            
