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

# XXX Having default SR in here is a bit of a hack.
class ExistingInstallation:
    def __init__(self, name, brand, version, build,
                 primary_disk):
        assert type(version) is tuple
        assert type(build) is int
        self.name = name
        self.brand = brand
        self.version = version
        self.build = build
        self.primary_disk = primary_disk

    def __str__(self):
        return "%s v%s-%d on %s" % (
            self.brand, ".".join([str(x) for x in self.version]),
            self.build, self.primary_disk)

def findXenSourceProducts():
    """Scans the host and finds XenSource product installations.
    Returns of list of ExistingInstallation objects.

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
                    tuple([ int(x) for x in inv['PRODUCT_VERSION'].split(".")]),
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
        # if these are in, then our assumption about the format
        # of the inventory file have changed:
        assert value.startswith("'") and value.endswith("'")
        value = value[1:len(value) - 1]
        rv[name] = value

    return rv
