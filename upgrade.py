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

# This stuff exists to hide ugliness and hacks that are required for upgrades
# from the rest of the installer.

import os
import tempfile

import product
import diskutil
import util
import constants
import xelogging
import backend

class UpgraderNotAvailable(Exception):
    pass

def upgradeAvailable(src):
    return __upgraders__.hasUpgrader(src.name, src.version)

def getUpgrader(src):
    """ Returns an upgrader instance suitable for src. Propogates a KeyError
    exception if no suitable upgrader is available (caller should have checked
    first by calling upgradeAvailable). """
    return __upgraders__.getUpgrader(src.name, src.version)(src)

class Upgrader(object):
    """ Base class for upgraders.  Superclasses should define an
    upgrades_product variable that is the product they upgrade, and an 
    upgrades_versions that is a list of pairs of version extents they support
    upgrading."""

    requires_backup = False

    def __init__(self, source):
        """ source is the ExistingInstallation object we're to upgrade. """
        self.source = source

    def upgrades(cls, product, version):
        return (cls.upgrades_product == product and
                True in [ _min <= version <= _max for (_min, _max) in cls.upgrades_versions ])

    upgrades = classmethod(upgrades)

    prepStateChanges = []
    prepUpgradeArgs = []
    def prepareUpgrade(self):
        """ Collect any state needed from the installation, and return a
        tranformation on the answers dict. """
        return

    completeUpgradeArgs = ['mounts']
    def completeUpgrade(self, mounts):
        """ Write any data back into the new filesystem as needed to follow
        through the upgrade. """
        pass

class SecondGenUpgrader(Upgrader):
    """ Upgrader class for series 4 products. """
    upgrades_product = "xenenterprise"
    upgrades_versions = [ (product.Version(4, 0, 0, suffix = 'b2'), product.THIS_PRODUCT_VERSION) ]
    requires_backup = True

    def __init__(self, source):
        Upgrader.__init__(self, source)

    prepUpgradeArgs = ['installation-uuid', 'control-domain-uuid']
    prepStateChanges = ['installation-uuid', 'control-domain-uuid', 'primary-disk']
    def prepareUpgrade(self, installID, controlID):
        """ Try to preserve the installation and control-domain UUIDs from
        xensource-inventory."""
        try:
            installID = self.source.getInventoryValue("INSTALLATION_UUID")
            controlID = self.source.getInventoryValue("CONTROL_DOMAIN_UUID")
            # test for presence:
            _ = self.source.getInventoryValue("BACKUP_PARTITION")

            pd = self.source.primary_disk
        except KeyError:
            raise RuntimeError, "Required information (INSTALLATION_UUID, CONTROL_DOMAIN_UUID) was missing from your xensource-inventory file.  Aborting installation; please replace these keys and try again."

        return installID, controlID, pd

    completeUpgradeArgs = ['mounts']
    def completeUpgrade(self, mounts):
        xelogging.log("Restoring preserved files")
        backup_volume = backend.getBackupPartName(self.source.primary_disk)
        tds = None
        try:
            tds = tempfile.mkdtemp(dir = "/tmp", prefix = "upgrade-src-")
            util.mount(backup_volume, tds)

            util.assertDir(os.path.join(mounts['root'], "var/xapi"))
            util.assertDir(os.path.join(mounts['root'], "etc/xensource"))

            # restore files:
            restore = ['etc/xensource/ptoken', 'etc/xensource/pool.conf', 
                       'etc/xensource/license', 'etc/xensource/db.conf', 'var/xapi/state.db',
                       'etc/ssh/ssh_host_dsa_key', 'etc/ssh/ssh_host_dsa_key.pub',
                       'etc/ssh/ssh_host_key', 'etc/ssh/ssh_host_key.pub',
                       'etc/ssh/ssh_host_rsa_key', 'etc/ssh/ssh_host_rsa_key.pub']
            for f in restore:
                src = os.path.join(tds, f)
                dst = os.path.join(mounts['root'], f)
                if os.path.exists(src):
                    xelogging.log("Restoring /%s" % f)
                    util.runCmd2(['cp', '-p', src, dst])
                else:
                    xelogging.log("WARNING: /%s did not exist in the backup image." % f)
            
            # if we're coming from Rio, we need to move the database config for
            # Rio over the main config file:
            if self.source.version <= product.XENSERVER_4_0_1:
                rio_db_conf = os.path.join(mounts['root'], 'etc', 'xensource', 'db.conf.rio')
                db_conf = os.path.join(mounts['root'], 'etc', 'xensource', 'db.conf')
                os.unlink(db_conf)
                util.runCmd2(['mv', rio_db_conf, db_conf])
        finally:
            if tds:
                if os.path.ismount(tds):
                    util.umount(tds)
                os.rmdir(tds)

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
    
__upgraders__ = UpgraderList([ SecondGenUpgrader ])
