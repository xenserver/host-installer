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
    
    def __init__(self, major, minor, release = ANY):
        self.major = major
        self.minor = minor
        self.release = release

    def __lt__(self, v):
        assert not self.ANY in [self.major, self.minor, self.release]
        return ( self.major < v.major or
                 (self.major == v.major and self.minor < v.minor) or
                 (self.major == v.major and self.minor == v.minor and self.release < v.release) )

    def __eq__(self, v):
        return ( self.cmp_version_number(self.major, v.major) == 0 and
                 self.cmp_version_number(self.minor, v.minor) == 0 and
                 self.cmp_version_number(self.release, v.release) == 0 )

    def __le__(self, v):
        return self < v or self == v

    def __ge__(self, v):
        return self > v or self == v
    
    def __gt__(self, v):
        assert not self.ANY in [self.major, self.minor, self.release]
        return ( self.major > v.major or
                 (self.major == v.major and self.minor > v.minor) or
                 (self.major == v.major and self.minor == v.minor and self.release > v.release) )

    def __str__(self):
        return "%d.%d.%d" % (self.major, self.minor, self.release)

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

THIS_PRODUCT_VERSION = Version(*[int(x) for x in version.PRODUCT_VERSION.split(".")])

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
        return "%s v%s-%d on %s" % (
            self.brand, str(self.version), self.build, self.primary_disk)

def findXenSourceProducts():
    """Scans the host and finds XenSource product installations.
    Returns list of ExistingInstallation objects.

    Currently requires supervisor privileges due to mounting
    filesystems."""
    
    partitions = diskutil.getQualifiedPartitionList()
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
                    Version(*[ int(x) for x in re.match("([0-9.]+)", inv['PRODUCT_VERSION']).group(1).split(".")]),
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
