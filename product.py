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
import constants
import version
import re
import tempfile
import xelogging

class SettingsNotAvailable(Exception):
    pass

class Version(object):
    ANY = -1
    INF = 999
    
    def __init__(self, major, minor, release, suffix = ""):
        assert type(major) is int
        assert type(minor) is int
        assert type(release) is int
        self.major = major
        self.minor = minor
        self.release = release
        self.suffix = suffix

    def from_string(cls, vstr):
        """ Create a version object, given an input string.  vstr should be of the
        form a.b.cs where a, b, c are numbers, and s is an alphanumeric, possibly
        empty, string. """
        version_substrings = vstr.split(".")
        assert len(version_substrings) == 3
        match = re.match("([0-9]+)(.*)", version_substrings[2])
        return cls(int(version_substrings[0]),
                   int(version_substrings[1]),
                   int(match.group(1)),
                   match.group(2))
    
    from_string = classmethod(from_string)

    def __lt__(self, v):
        assert not self.ANY in [self.major, self.minor, self.release]
        return ( self.major < v.major or
                 (self.major == v.major and self.minor < v.minor) or
                 (self.major == v.major and self.minor == v.minor and self.release < v.release) or
                 (self.major == v.major and self.minor == v.minor and self.release == v.release and self.cmp_suffix(self.suffix,v.suffix) == -1) )

    def __eq__(self, v):
        return ( self.cmp_version_number(self.major, v.major) == 0 and
                 self.cmp_version_number(self.minor, v.minor) == 0 and
                 self.cmp_version_number(self.release, v.release) == 0  and
                 self.suffix == v.suffix )

    def __le__(self, v):
        return self < v or self == v

    def __ge__(self, v):
        return self > v or self == v
    
    def __gt__(self, v):
        assert not self.ANY in [self.major, self.minor, self.release]
        return ( self.major > v.major or
                 (self.major == v.major and self.minor > v.minor) or
                 (self.major == v.major and self.minor == v.minor and self.release > v.release) or
                 (self.major == v.major and self.minor == v.minor and self.release == v.release and self.cmp_suffix(self.suffix, v.suffix) == 1) )

    def __str__(self):
        return "%d.%d.%d%s" % (self.major, self.minor, self.release, self.suffix)

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

    cmp_suffx = classmethod(cmp_suffix)

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
XENSERVER_3_1_0 = Version(3,1,0)

class ExistingInstallation(object):
    def __init__(self, name, brand, version, build,
                 primary_disk):
        assert type(build) is int
        self.name = name
        self.brand = brand
        self.version = version
        self.build = build
        self.primary_disk = primary_disk

    def __str__(self):
        return "%s v%s (%d) on %s" % (
            self.brand, str(self.version), self.build, self.primary_disk)

    def settingsAvailable(self):
        try:
            self.readSettings()
        except:
            return False
        else:
            return True
    
    def readSettings(self):
        """ Read settings from the installation, retusn a results dictionary. """
        if not self.version == XENSERVER_3_1_0:
            raise SettingsNotAvailable
        
        mntpoint = tempfile.mkdtemp(prefix="root-", dir='/tmp')
        root = diskutil.determinePartitionName(self.primary_disk, 1)
        results = {}
        try:
            util.mount(root, mntpoint)

            # primary disk:
            results['primary-disk'] = self.primary_disk

            # timezone:
            fd = open(os.path.join(mntpoint, 'rws/etc/sysconfig/clock'), 'r')
            lines = fd.readlines()
            fd.close()
            tz = None
            for line in lines:
                if line.startswith("ZONE="):
                    tz = line[5:].strip()
            if not tz:
                raise SettingsNotAvailable
            results['timezone'] = tz

            # hostname.  We will assume one was set anyway and thus write
            # it back into the new filesystem.  If one wasn't set then this
            # will be localhost.localdomain, in which case the old behaviour
            # will persist anyway:
            fd = open(os.path.join(mntpoint, 'rws/etc/sysconfig/network'), 'r')
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
                fd = open(os.path.join(mntpoint, 'rws/etc/resolv.conf'), 'r')
                lines = fd.readlines()
                fd.close()
                for line in lines:
                    if line.startswith("nameserver "):
                        ns.append(line[11:].strip())
                results['manual-nameservers'] = (True, ns)

            # ntp servers:
            fd = open(os.path.join(mntpoint, 'rws/etc/ntp.conf'), 'r')
            lines = fd.readlines()
            fd.close()
            ntps = []
            for line in lines:
                if line.startswith("server "):
                    ntps.append(line[7:].strip())
            results['ntp-servers'] = ntps

            # keyboard:
            fd = open(os.path.join(mntpoint, 'rws/etc/sysconfig/keyboard'), 'r')
            lines = fd.readlines()
            fd.close()
            for line in lines:
                if line.startswith('KEYTABLE='):
                    results['keymap'] = line[9:].strip()
            if not results.has_key('keymap'):
                raise SettingsNotAvailable, "Error reading keymap data."

            # network:
            network_files = os.listdir(os.path.join(mntpoint, 'rws/etc/sysconfig/network-scripts'))
            network_files = filter(lambda x: x.startswith('ifcfg-eth'),
                                   network_files)

            interfaces = {}
            for nf in network_files:
                fd = open(os.path.join(mntpoint, 'rws/etc/sysconfig/network-scripts', nf), 'r')
                lines = fd.readlines()
                fd.close()
                devvice = bootproto = onboot = None
                netmask = ipaddr = gw = None
                for line in lines:
                    if line.startswith('DEVICE='):
                        device = line[7:].strip()
                    elif line.startswith('BOOTPROTO='):
                        bootproto = line[10:].strip()
                    elif line.startswith('ONBOOT='):
                        onboot = line[7:].strip()
                    elif line.startswith('NETMASK='):
                        netmask = line[8:].strip()
                    elif line.startswith('IPADDR='):
                        ipaddr = line[7:].strip()
                    elif line.startswith('GATEWAY='):
                        gw = line[8:].strip()

                iface = {}
                # now work out what the results version is:
                # - check sanity:
                if onboot not in ['yes', 'no']:
                    xelogging.log("ONBOOT value not recognised - skipping interface file" % nf)
                    continue
                if bootproto not in ['dhcp', 'none']:
                    xelogging.log("BOOTPROTO value not recognised - skipping interface file" % nf)
                    continue

                # enabled?
                iface['enabled'] = onboot == 'yes'

                if bootproto == 'dhcp':
                    iface['use-dhcp'] = True
                elif bootproto == 'none':
                    if None in [ipaddr, netmask, gw]:
                        xelogging.log("Unable to parse interface definition for %s - skipping." % device)
                        continue
                    iface['ip'] = ipaddr
                    iface['subnet-mask'] = netmask
                    iface['gateway'] = gw

                interfaces[device] = iface

            # root password:
            rc, out = util.runCmdWithOutput(
                'chroot %s python -c \'import pwd; print pwd.getpwnam("root")[1]\'' % mntpoint
                )

            if rc != 0:
                raise SettingsNotAvailable
            else:
                results['root-password-type'] = 'pwdhash'
                results['root-password'] = out.strip()

            results['iface-configuration'] = (False, interfaces)

            # don't care about this too much.
            results['time-config-method'] = 'ntp'
        finally:
            util.umount(mntpoint)

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
    if not os.path.exists("/tmp/mnt"):
        os.mkdir("/tmp/mnt")

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

                # parse the version string:
                installs.append(
                    ExistingInstallation(
                    inv['PRODUCT_NAME'],
                    inv['PRODUCT_BRAND'],
                    Version.from_string(inv['PRODUCT_VERSION']),
                    int(inv['BUILD_NUMBER']),
                    diskutil.diskFromPartition(p) )
                    )
        finally:
            util.umount(mountpoint)

    return installs

def readInventoryFile(filename):
    """Reads a xensource-inventory file.  Note that
    'split' is not used to separate name=value as this
    fails if the value has an = in it."""

    f = open(filename, "r")
    lines = [x.rstrip("\n") for x in f.readlines()]
    f.close()

    # Split "a=1" into ("a", "1"), and a=b=c into ("a", "b=c"):
    defs = [ (l[:l.find("=")], l[(l.find("=") + 1):]) for l in lines ]

    rv = {}
    for (name, value) in defs:
        # if these fail, then our assumption about the format
        # of the inventory file have changed:
        assert value.startswith("'") and value.endswith("'")
        value = value[1:len(value) - 1]
        rv[name] = value

    return rv
