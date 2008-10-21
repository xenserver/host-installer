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
XENSERVER_4_1_0 = Version(4,1,0)

class ExistingInstallation(object):
    def __init__(self, name, brand, version, primary_disk, inventory):
        self.name = name
        self.brand = brand
        self.version = version
        self.primary_disk = primary_disk
        self.inventory = inventory

    def __str__(self):
        return "%s v%s on %s" % (
            self.brand, str(self.version), self.primary_disk)

    def getInventoryValue(self, k):
        return self.inventory[k]

    def getRootPartition(self):
        return diskutil.determinePartitionName(self.primary_disk, 1)

    def isUpgradeable(self):
        mntpoint = tempfile.mkdtemp(prefix="root-", dir='/tmp')
        root = self.getRootPartition()
        try:
            util.mount(root, mntpoint, options = ['ro'])

            state_files = os.listdir(os.path.join(mntpoint, 'etc/firstboot.d/state'))
            firstboot_files = [ f for f in os.listdir(os.path.join(mntpoint, 'etc/firstboot.d')) \
                                    if f[0].isdigit() and os.stat(os.path.join(mntpoint, 'etc/firstboot.d', f))[stat.ST_MODE] & stat.S_IXUSR ]

            result = (len(state_files) == len(firstboot_files))
        except:
            result = False

        util.umount(mntpoint)
        os.rmdir(mntpoint)

        if not result:
            xelogging.log("Product %s cannot be upgraded" % str(self))

        return result

    def settingsAvailable(self):
        try:
            self.readSettings()
        except SettingsNotAvailable, text:
            xelogging.log("Settings unavailable: %s" % text)
            return False
        except:
            xelogging.log("Settings unavailable: unhandled exception")
            return False
        else:
            return True
    
    def readSettings(self):
        """ Read settings from the installation, returns a results dictionary. """
        if self.version < XENSERVER_4_1_0:
            raise SettingsNotAvailable, "version too old"
        
        mntpoint = tempfile.mkdtemp(prefix="root-", dir='/tmp')
        root = self.getRootPartition()
        results = {}
        try:
            util.mount(root, mntpoint, options = ['ro'])

            # primary disk:
            results['primary-disk'] = self.primary_disk

            # timezone:
            fd = open(os.path.join(mntpoint, 'etc/sysconfig/clock'), 'r')
            lines = fd.readlines()
            fd.close()
            tz = None
            for line in lines:
                if line.startswith("ZONE="):
                    tz = line[5:].strip()
            if not tz:
                raise SettingsNotAvailable, "timezone missing"
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
            if not os.path.exists(os.path.join(mntpoint, 'etc/resolv.conf')):
                results['manual-nameservers'] = (False, None)
            else:
                ns = []
                fd = open(os.path.join(mntpoint, 'etc/resolv.conf'), 'r')
                lines = fd.readlines()
                fd.close()
                for line in lines:
                    if line.startswith("nameserver "):
                        ns.append(line[11:].strip())
                results['manual-nameservers'] = (True, ns)

            # ntp servers:
            fd = open(os.path.join(mntpoint, 'etc/ntp.conf'), 'r')
            lines = fd.readlines()
            fd.close()
            ntps = []
            for line in lines:
                if line.startswith("server "):
                    ntps.append(line[7:].strip())
            results['ntp-servers'] = ntps

            # keyboard:
            fd = open(os.path.join(mntpoint, 'etc/sysconfig/keyboard'), 'r')
            lines = fd.readlines()
            fd.close()
            for line in lines:
                if line.startswith('KEYTABLE='):
                    results['keymap'] = line[9:].strip()
            if not results.has_key('keymap'):
                raise SettingsNotAvailable, "error reading keymap data"

            # root password:
            rc, out = util.runCmd2(['chroot', mntpoint, 'python', '-c',
                                    'import pwd; print pwd.getpwnam("root")[1]'], 
                                   with_stdout = True)

            if rc != 0:
                raise SettingsNotAvailable, "error retrieving root password"
            else:
                results['root-password-type'] = 'pwdhash'
                results['root-password'] = out.strip()

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
        finally:
            util.umount(mntpoint)
            os.rmdir(mntpoint)

        return results

def findXenSourceBackups():
    """Scans the host and find partitions containing backups of XenSource
    products.  Returns a list of device node paths to partitions containing
    said backups. """

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

    # get a list of disks, then try to examine the first partition of each disk:
    partitions = [ diskutil.determinePartitionName(x, 1) for x in diskutil.getQualifiedDiskList() ]
    util.assertDir("/tmp/mnt")

    mountpoint = "/tmp/mnt"
    inventory_file = os.path.join(mountpoint, constants.INVENTORY_FILE)

    installs = []

    # go through each partition, and see if it is an XS dom0.
    for p in partitions:
        try:
            util.mount(p, mountpoint)
        except:
            # unable to mount it, so ignore it
            continue

        try:
            if os.path.exists(inventory_file):
                inv = readInventoryFile(inventory_file)
                inst = ExistingInstallation(
                    inv['PRODUCT_NAME'],
                    inv['PRODUCT_BRAND'],
                    Version.from_string("%s-%s" % (inv['PRODUCT_VERSION'], inv['BUILD_NUMBER'])),
                    diskutil.diskFromPartition(p),
                    inv
                    )
                xelogging.log("Found an installation: %s" % str(inst))
                installs.append(inst)
        finally:
            util.umount(mountpoint)

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
