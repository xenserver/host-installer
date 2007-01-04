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

# This stuff exists to hide ugliness and hacks that are
# required for upgrades from the rest of the installer.

import os

import product
import diskutil
import util
import constants

class UpgraderNotAvailable(Exception):
    pass

def upgradeAvailable(src):
    return __upgraders__.hasUpgrader(src.name, src.version)

def getUpgrader(src):
    """ Returns an upgrader instance suitable for src. Propogates a KeyError exception
    if no suitable upgrader is available (caller should have checked first by calling
    upgradeAvailable). """
    return __upgraders__.getUpgrader(src.name, src.version)(src)

class Upgrader(object):
    """ Base class for upgraders.  Superclasses should define an upgrades variable that
    is a triple of the product, the lowest version they support upgrading from, and the
    highest version. """

    def __init__(self, source):
        self.source = source

    def upgrades(cls, product, version):
        return (cls.upgrades_product == product and
                True in [ _min <= version <= _max for (_min, _max) in cls.upgrades_versions ])

    upgrades = classmethod(upgrades)

    prepStateChanges = []
    def prepareUpgrade(self):
        """ Collect any state needed from the installation,
        and return a tranformation on the answers dict. """
        return

    def completeUpgrade(self):
        """ Write any data back into the new filesystem
        as needed to follow through the upgrade. """
        pass

class FirstGenUpgrader(Upgrader):
    """ Upgrade between initial product versions. """

    upgrades_product = "xenenterprise"

    upgrades_versions = [ (product.Version(0, 2, 4), product.THIS_PRODUCT_VERSION),
                          (product.Version(3, 1, 0, "b1"), product.Version(3,1,0)) ]

    def __init__(self, source):
        Upgrader.__init__(self, source)

    prepStateChanges = [ 'default-sr-uuid', 'primary-disk' ]
    def prepareUpgrade(self):
        """ Read default SR UUID, and put it into the input
        state for the backend. """

        root = diskutil.determinePartitionName(self.source.primary_disk, 1)
        try:
            mntpoint = "/tmp/mnt"
            if not os.path.isdir(mntpoint):
                os.mkdir(mntpoint)
            util.mount(root, mntpoint)
            inv = product.readInventoryFile(
                os.path.join(mntpoint, constants.INVENTORY_FILE)
                )
            if inv.has_key("DEFAULT_SR"):
                def_sr = inv['DEFAULT_SR']
            else:
                def_sr = None
        finally:
            util.umount(mntpoint)    

        return (def_sr, self.source.primary_disk)

# Upgarders provided here, in preference order:
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
    
__upgraders__ = UpgraderList([ FirstGenUpgrader ])
