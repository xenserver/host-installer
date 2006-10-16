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
    return __upgraders__.has_key( (src.name, src.version) )

def getUpgrader(src):
    """ Returns an upgrader instance suitable for src. """
    try:
        return __upgraders__[ (src.name, src.version) ](src)
    except KeyError:
        raise UpgraderNotAvailable


class Upgrader:
    """ Base class for upgraders """
    
    def __init__(self, source):
        self.source = source

    prepStateChanges = []
    def prepareUpgrade(self, source):
        """ Collect any state needed from the installation,
        and return a tranformation on the answers dict. """
        return

    def completeUpgrade(self):
        """ Write any data back into the new filesystem
        as needed to follow through the upgrade. """
        pass

class FirstGenUpgrader(Upgrader):
    """ Upgrade between initial product versions. """

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

__upgraders__ = {
    ( "xenenterprise", (0, 2, 4) ) : FirstGenUpgrader,
    ( "xenenterprise", (0, 2, 5) ) : FirstGenUpgrader,
    ( "xenenterprise", (0, 2, 6) ) : FirstGenUpgrader,
    ( "xenenterprise", (0, 3, 0) ) : FirstGenUpgrader,
    }
