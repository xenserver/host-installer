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

        # look for xensource-inventory (note that in Python the
        # finally block is executed if a continue statement is reached):
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
            else:
                continue
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
