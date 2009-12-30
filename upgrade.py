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
import re

import product
from disktools import *
import util
import constants
import xelogging

def upgradeAvailable(src):
    return __upgraders__.hasUpgrader(src.name, src.version, src.variant)

def getUpgrader(src):
    """ Returns an upgrader instance suitable for src. Propogates a KeyError
    exception if no suitable upgrader is available (caller should have checked
    first by calling upgradeAvailable). """
    return __upgraders__.getUpgrader(src.name, src.version, src.variant)(src)

class Upgrader(object):
    """ Base class for upgraders.  Superclasses should define an
    upgrades_product variable that is the product they upgrade, an 
    upgrades_variants list of Retail or OEM install types that they upgrade, and an 
    upgrades_versions that is a list of pairs of version extents they support
    upgrading."""

    requires_backup = False
    optional_backup = True
    repartition = False
    prompt_for_target = False

    def __init__(self, source):
        """ source is the ExistingInstallation object we're to upgrade. """
        self.source = source
        self.restore_list = []

    def upgrades(cls, product, version, variant):
        return (cls.upgrades_product == product and
                variant in cls.upgrades_variants and
                True in [ _min <= version <= _max for (_min, _max) in cls.upgrades_versions ])

    upgrades = classmethod(upgrades)

    prepTargetStateChanges = []
    prepTargetArgs = []
    def prepareTarget(self, progress_callback):
        """ Modify partition layout prior to installation. """
        return

    doBackupStateChanges = []
    doBackupArgs = []
    def doBackup(self, progress_callback):
        """ Collect configuration etc from installation. """
        return

    prepStateChanges = []
    prepUpgradeArgs = []
    def prepareUpgrade(self, progress_callback):
        """ Collect any state needed from the installation, and return a
        tranformation on the answers dict. """
        return

    def buildRestoreList(self):
        """ Add filenames to self.restore_list which will be copied by
        completeUpgrade(). """
        return

    completeUpgradeArgs = ['mounts', 'primary-disk', 'backup-partnum']
    def completeUpgrade(self, mounts, target_disk, backup_partnum):
        """ Write any data back into the new filesystem as needed to follow
        through the upgrade. """

        def restore_file(src_base, f, d = None):
            if not d: d = f
            src = os.path.join(src_base, f)
            dst = os.path.join(mounts['root'], d)
            if os.path.exists(src):
                xelogging.log("Restoring /%s" % f)
                if os.path.isdir(src):
                    util.runCmd2(['cp', '-rp', src, os.path.dirname(dst)])
                else:
                    util.assertDir(os.path.dirname(dst))
                    util.runCmd2(['cp', '-p', src, dst])
            else:
                xelogging.log("WARNING: /%s did not exist in the backup image." % f)

        backup_volume = PartitionTool.partitionDevice(target_disk, backup_partnum)
        tds = util.TempMount(backup_volume, 'upgrade-src-', options = ['ro'])
        try:
            self.buildRestoreList()

            xelogging.log("Restoring preserved files")
            for f in self.restore_list:
                if isinstance(f, str):
                    restore_file(tds.mount_point, f)
                elif isinstance(f, dict):
                    if 'src' in f:
                        assert 'dst' in f
                        restore_file(tds.mount_point, f['src'], f['dst'])
                    elif 'dir' in f:
                        pat = 're' in f and f['re'] or None
                        src_dir = os.path.join(tds.mount_point, f['dir'])
                        if os.path.exists(src_dir):
                            for ff in os.listdir(src_dir):
                                fn = os.path.join(f['dir'], ff)
                                if not pat or pat.match(fn):
                                    restore_file(tds.mount_point, fn)
        finally:
            tds.unmount()


class ThirdGenUpgrader(Upgrader):
    """ Upgrader class for series 5 Retail products. """
    upgrades_product = "xenenterprise"
    upgrades_versions = [ (product.Version(5, 5, 0), product.THIS_PRODUCT_VERSION) ]
    upgrades_variants = [ 'Retail' ]
    requires_backup = True
    optional_backup = False
    
    def __init__(self, source):
        Upgrader.__init__(self, source)

    doBackupArgs = ['primary-disk', 'backup-partnum']
    doBackupStateChanges = []
    def doBackup(self, progress_callback, target_disk, backup_partnum):

        # format the backup partition:
        backup_partition = PartitionTool.partitionDevice(target_disk, backup_partnum)
        if util.runCmd2(['mkfs.ext3', backup_partition]) != 0:
            raise RuntimeError, "Backup: Failed to format filesystem on %s" % backup_partition
        progress_callback(10)

        # copy the files across:
        primary_fs = util.TempMount(self.source.root_device, 'primary-', options = ['ro'])
        try:
            backup_fs = util.TempMount(backup_partition, 'backup-')
            try:
                top_dirs = os.listdir(primary_fs.mount_point)
                val = 10
                for x in top_dirs:
                    cmd = ['cp', '-a'] + \
                          [ os.path.join(primary_fs.mount_point, x) ] + \
                          ['%s/' % backup_fs.mount_point]
                    if util.runCmd2(cmd) != 0:
                        raise RuntimeError, "Backup of %d directory failed" % x
                    val += 90 / len(top_dirs)
                    progress_callback(val)
            finally:
                fh = open(os.path.join(backup_fs.mount_point, '.xen-backup-partition'), 'w')
                fh.close()
                backup_fs.unmount()
        finally:
            primary_fs.unmount()

    prepUpgradeArgs = ['installation-uuid', 'control-domain-uuid']
    prepStateChanges = ['installation-uuid', 'control-domain-uuid']
    def prepareUpgrade(self, progress_callback, installID, controlID):
        """ Try to preserve the installation and control-domain UUIDs from
        xensource-inventory."""
        try:
            installID = self.source.getInventoryValue("INSTALLATION_UUID")
            controlID = self.source.getInventoryValue("CONTROL_DOMAIN_UUID")
        except KeyError:
            raise RuntimeError, "Required information (INSTALLATION_UUID, CONTROL_DOMAIN_UUID) was missing from your xensource-inventory file.  Aborting installation; please replace these keys and try again."

        return installID, controlID

    def buildRestoreList(self):
        self.restore_list += ['etc/xensource/ptoken', 'etc/xensource/pool.conf', 
                              'etc/xensource/xapi-ssl.pem']
        self.restore_list.append({'dir': 'etc/ssh', 're': re.compile(r'.*/ssh_host_.+')})

        self.restore_list += [ 'etc/sysconfig/network', constants.DBCACHE ]
        self.restore_list.append({'dir': 'etc/sysconfig/network-scripts', 're': re.compile(r'.*/ifcfg-[a-z0-9.]+')})

        self.restore_list += ['var/xapi/state.db', 'etc/xensource/license']
        self.restore_list.append({'dir': constants.FIRSTBOOT_DATA_DIR, 're': re.compile(r'.*.conf')})

        self.restore_list.append({'src': 'etc/xensource-inventory', 'dst': 'var/tmp/.previousInventory'})

        # CP-1508: preserve AD config
        self.restore_list += [ 'etc/resolv.conf', 'etc/nsswitch.conf', 'etc/krb5.conf', 'etc/krb5.keytab', 'etc/pam.d/sshd' ]
        self.restore_list.append({'dir': 'var/lib/likewise'})

    completeUpgradeArgs = ['mounts', 'installation-to-overwrite', 'primary-disk', 'backup-partnum', 'net-admin-interface', 'net-admin-bridge', 'net-admin-configuration']
    def completeUpgrade(self, mounts, prev_install, target_disk, backup_partnum, admin_iface, admin_bridge, admin_config):

        util.assertDir(os.path.join(mounts['root'], "var/xapi"))
        util.assertDir(os.path.join(mounts['root'], "etc/xensource"))

        Upgrader.completeUpgrade(self, mounts, target_disk, backup_partnum)

        if not os.path.exists(os.path.join(mounts['root'], constants.DBCACHE)):
            # upgrade from 5.5, generate dbcache
            save_dir = os.path.join(mounts['root'], constants.FIRSTBOOT_DATA_DIR, 'initial-ifcfg')
            util.assertDir(save_dir)
            dbcache_file = os.path.join(mounts['root'], constants.DBCACHE)
            dbcache_fd = open(dbcache_file, 'w')

            network_uid = util.getUUID()
                
            dbcache_fd.write('<?xml version="1.0" ?>\n<xenserver-network-configuration>\n')
                
            if admin_iface.startswith('bond'):
                top_pif_uid = bond_pif_uid = util.getUUID()
                bond_uid = util.getUUID()

# find slaves of this bond and write PIFs for them
                slaves = []
                for file in [ f for f in os.listdir(os.path.join(mounts['root'], constants.NET_SCR_DIR))
                              if re.match('ifcfg-eth[0-9]+$', f) ]:
                    slavecfg = util.readKeyValueFile(os.path.join(mounts['root'], constants.NET_SCR_DIR, file), strip_quotes = False)
                    if slavecfg.has_key('MASTER') and slavecfg['MASTER'] == admin_iface:
                            
                        slave_uid = util.getUUID()
                        slave_net_uid = util.getUUID()
                        slaves.append(slave_uid)
                        slave = NetInterface.loadFromIfcfg(os.path.join(mounts['root'], constants.NET_SCR_DIR, file))
                        slave.writePif(slavecfg['DEVICE'], dbcache_fd, slave_uid, slave_net_uid, ('slave-of', bond_uid))

# locate bridge that has this interface as its PIFDEV
                        bridge = None
                        for file in [ f for f in os.listdir(os.path.join(mounts['root'], constants.NET_SCR_DIR))
                                      if re.match('ifcfg-xenbr[0-9]+$', f) ]:
                            brcfg = util.readKeyValueFile(os.path.join(mounts['root'], constants.NET_SCR_DIR, file), strip_quotes = False)
                            if brcfg.has_key('PIFDEV') and brcfg['PIFDEV'] == slavecfg['DEVICE']:
                                bridge = brcfg['DEVICE']
                                break
                        assert bridge
                        
                        dbcache_fd.write('\t<network ref="OpaqueRef:%s">\n' % slave_net_uid)
                        dbcache_fd.write('\t\t<uuid>%sSlaveNetwork</uuid>\n' % slavecfg['DEVICE'])
                        dbcache_fd.write('\t\t<PIFs>\n\t\t\t<PIF>OpaqueRef:%s</PIF>\n\t\t</PIFs>\n' % slave_uid)
                        dbcache_fd.write('\t\t<bridge>%s</bridge>\n' % bridge)
                        dbcache_fd.write('\t\t<other_config/>\n\t</network>\n')

                # write bond
                dbcache_fd.write('\t<bond ref="OpaqueRef:%s">\n' % bond_uid)
                dbcache_fd.write('\t\t<master>OpaqueRef:%s</master>\n' % bond_pif_uid)
                dbcache_fd.write('\t\t<uuid>InitialManagementBond</uuid>\n\t\t<slaves>\n')
                for slave_uid in slaves:
                    dbcache_fd.write('\t\t\t<slave>OpaqueRef:%s</slave>\n' % slave_uid)
                dbcache_fd.write('\t\t</slaves>\n\t</bond>\n')

                # write bond PIF
                admin_config.writePif(admin_iface, dbcache_fd, bond_pif_uid, network_uid, ('master-of', bond_uid))
            else:
                top_pif_uid = util.getUUID()
                # write PIF
                admin_config.writePif(admin_iface, dbcache_fd, top_pif_uid, network_uid)

            dbcache_fd.write('\t<network ref="OpaqueRef:%s">\n' % network_uid)
            dbcache_fd.write('\t\t<uuid>InitialManagementNetwork</uuid>\n')
            dbcache_fd.write('\t\t<PIFs>\n\t\t\t<PIF>OpaqueRef:%s</PIF>\n\t\t</PIFs>\n' % top_pif_uid)
            dbcache_fd.write('\t\t<bridge>%s</bridge>\n' % admin_bridge)
            dbcache_fd.write('\t\t<other_config/>\n\t</network>\n')

            dbcache_fd.write('</xenserver-network-configuration>\n')

            dbcache_fd.close()
            util.runCmd2(['cp', '-p', dbcache_file, save_dir])

        v = product.Version(prev_install.version.major,
                            prev_install.version.minor,
                            prev_install.version.release)
        f = open(os.path.join(mounts['root'], 'var/tmp/.previousVersion'), 'w')
        f.write("PRODUCT_VERSION='%s'\n" % v)
        f.close()

        state = open(os.path.join(mounts['root'], constants.FIRSTBOOT_DATA_DIR, 'host.conf'), 'w')
        print >>state, "UPGRADE=true"
        state.close()

        # CP-1508: preserve AD service state
        ad_on = False
        try:
            fh = open(os.path.join(mounts['root'], 'etc/nsswitch.conf'), 'r')
            for line in fh:
                if line.startswith('passwd:') and 'lsass' in line:
                    ad_on = True
                    break
            fh.close()
        except:
            pass

        if ad_on:
            for service in ['dcerpd', 'eventlogd', 'netlogond', 'npcmuxd', 'lsassd']:
                util.runCmd2(['chroot', mounts['root'], 'chkconfig', '--add', service])


class ThirdGenOEMUpgrader(ThirdGenUpgrader):
    """ Upgrader class for series 5 OEM products. """
    requires_backup = False
    optional_backup = False
    repartition = True
    prompt_for_target = True
    upgrades_variants = [ 'OEM' ]

    def __init__(self, source):
        ThirdGenUpgrader.__init__(self, source)

    prepTargetArgs = ['installation-to-overwrite', 'primary-disk', 'primary-partnum', 'backup-partnum', 'storage-partnum']
    prepTargetStateChanges = ['installation-to-overwrite', 'post-backup-delete', 'root-start']
    def prepareTarget(self, progress_callback, existing, primaryDisk, primaryPartnum, backupPartnum, storagePartnum):
        """Modify partition layout prior to installation.  This method must make space on the target disk,
        resizing the SR already present if necessary, and create root and backup partitions."""
        lvmTool = LVMTool()
        partTool = PartitionTool(primaryDisk)
        rootByteSize = constants.root_size * 2 ** 20
        
        # Build a list of partition numbers to preserve at least for now.
        partNumsToPreserve = []
        
        # First add the utility partition if present
        if primaryPartnum == 1 :
            # No utility partition - start at 1
            foundUtilityNumber = None
        else:
            # First partition is a utility partition so preserve it
            partNumsToPreserve.append(1)
            foundUtilityNumber = 1

        firstXSPartition = primaryPartnum

        # Config partitions are found on XenServer-claimed disks in both OEM Flash and HDD installations
        # They must be preserved for now in case we are copying state information from them, but will be
        # deleted later in the upgrade process
        foundConfigDevice = lvmTool.configPartition(primaryDisk)
        if foundConfigDevice is not None:
            foundConfigNumber = partTool.partitionNumber(foundConfigDevice)
            partNumsToPreserve.append(foundConfigNumber)
        # Detect the OEM HDD state partition as a special case
        elif existing and existing.primary_disk == primaryDisk and existing.state_device:
            foundConfigNumber = partTool.partitionNumber(existing.state_device)
            partNumsToPreserve.append(foundConfigNumber)
        else:
            foundConfigNumber = None
        
        foundSRDevice = lvmTool.srPartition(primaryDisk)
        if foundSRDevice is not None:
            foundSRNumber = partTool.partitionNumber(foundSRDevice)
            partNumsToPreserve.append(foundSRNumber)
        else:
            foundSRNumber = None
        
        xelogging.log(
            "prepareTarget found the following:"+
            "\nUtility partition : "+str(foundUtilityNumber) +
            "\nConfig partition  : "+str(foundConfigNumber) +
            "\nSR partition      : "+str(foundSRNumber) +
            "\nand chose to preserve partitions: "+", ".join( [ str(i) for i in partNumsToPreserve ] )
        )
        # Purge redundant partitions on target
        for num, part in partTool.iteritems():
            if num not in partNumsToPreserve:
                lvmTool.deleteDevice(part)
                partTool.deletePartition(num)
        
        if foundConfigNumber > 4:
            partTool.renamePartition(foundConfigNumber, firstXSPartition)
            if existing is not None: # existing can be None in unit testing only
                existing.partitionWasRenamed(partTool._partitionDevice(foundConfigNumber),
                    partTool._partitionDevice(firstXSPartition))
            foundConfigNumber = firstXSPartition

        if foundSRDevice:
            if foundSRNumber <= 4:
                # There is an SR partition on this disk that we need to preserve, as as this is not OEM HDD
                # we need to resize it
                xelogging.log("Reducing %s by %d bytes" % (foundSRDevice, (2 * rootByteSize)))
                lvmSize = lvmTool.deviceSize(foundSRDevice)
                lvmTool.resizeDevice(foundSRDevice, lvmSize - 2 * rootByteSize)
                partitionSize = partTool.partitionSize(foundSRNumber)
                partTool.resizePartition(foundSRNumber, partitionSize - 2 * rootByteSize)
        
            # We must rename the SR partition now and not later, as in OEM HDD the SR lives in an
            # extended partition that we're deleting
            partTool.renamePartition(foundSRNumber, storagePartnum)
            if existing is not None: # existing can be None in unit testing only
                existing.partitionWasRenamed(partTool._partitionDevice(foundSRNumber),
                    partTool._partitionDevice(storagePartnum))
            # Update foundSRNumber to keep track of the SR
            foundSRNumber = storagePartnum

        # Partition creation
        # So far we've deleted everything except utility, config and SR partitions on this disk.
    
        # If an SR is present, root and backup partitions go at the end of the disk for Flash,
        # and the start for OEM HDD.  In either case they have lower numbers than the SR partition
        if foundUtilityNumber is not None:
            availStart = partTool.partitionEnd(foundUtilityNumber)
        else:
            availStart = partTool.sectorSize # First sector stores partition table, so skip it

        if foundSRNumber is not None:
            # SR is present, so root and backup partitions go either before (if there's room) or
            # after it
            if not foundConfigNumber and partTool.partitionStart(foundSRNumber) - availStart > 2 * rootByteSize:
                # Root and backup partitions will fit before the SR...
                xelogging.log("Space for both install and backup partitions at start of disk")
                rootStart = availStart
                backupSize = rootByteSize
            elif partTool.partitionStart(foundSRNumber) - availStart > rootByteSize:
                # Fit the partition between where the new root partition will end and the start
                # of the current config partition
                xelogging.log("Creating reduced size backup partition temporarily")
                rootStart = availStart
                backupStart = rootStart + rootByteSize
                backupSize = partTool.partitionStart(foundConfigNumber) - backupStart
            else:
                # Won't fit - put at the end.  We know there's space because of the resize above
                xelogging.log("Placing install and backup partitions at end of device")
                rootStart = partTool.partitionEnd(foundSRNumber)
                backupSize = rootByteSize
        else:
            # No SR present - just leave space for the root partition
            rootStart = availStart
            backupSize = rootByteSize

        backupStart = rootStart + rootByteSize
        partTool.createPartition(number = backupPartnum, id = partTool.ID_LINUX,
            startBytes = backupStart, sizeBytes = backupSize)
        
        lvmTool.commit(progress_callback) # progress_callback gets values 0..100
        partTool.commit(log = True)

        # Store the number of the state partition so that we can delete it later
        postBackupDelete = []
        if foundConfigNumber is not None:
            postBackupDelete.append(foundConfigNumber)

        return existing, postBackupDelete, rootStart

    doBackupArgs = ['installation-to-overwrite', 'primary-disk', 'backup-partnum']
    doBackupStateChanges = []
    def doBackup(self, progress_callback, existing, primaryDisk, backupPartnum):
        backup_partition = PartitionTool.partitionDevice(primaryDisk, backupPartnum)
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
            raise RuntimeError,  "Backup: Failed to format filesystem on %s" % backup_partition
        progress_callback(10)

        db_generation = (-1, None, None)
        lvmTool = LVMTool()
        backup_fs = util.TempMount(backup_partition, 'backup-')
        try:
            primary_fs = util.TempMount(existing.state_device, 'state-', options = ['ro'])
            try:
                # copy from primary state partition:
                root_dir = os.path.join(primary_fs.mount_point, existing.state_prefix)
                gen = readDbGen(root_dir)

                xelogging.log("Copying state from %s" % root_dir)
                cmd = ['cp', '-a'] + \
                      [ os.path.join(root_dir, x) for x in os.listdir(root_dir) ] + \
                      ['%s/' % backup_fs.mount_point]
                if util.runCmd2(cmd) != 0:
                    raise RuntimeError, "Backup failed"
                if gen > db_generation[0]:
                    db_generation = (gen, existing.state_device, existing.state_prefix)
                progress_callback(30)
            finally:
                primary_fs.unmount()

            freqPath = os.path.join(root_dir, 'etc/freq-etc/etc')
            if os.path.isdir(freqPath): # Present on OEM Flash only
                cmd = ['cp', '-a', freqPath, '%s/' % backup_fs.mount_point]
                if util.runCmd2(cmd) != 0:
                    raise RuntimeError, "Backup of etc/freq-etc/etc directory failed"

            # copy from auxiliary state partitions:
            val = 30
            for state_info in existing.auxiliary_state_devices:
                lvmTool.activateVG(state_info['vg'])
                mountPath = os.path.join('/dev', state_info['vg'], state_info['lv'])
                primary_fs = util.TempMount(mountPath, 'auxstate-', options = ['ro'])
                try:
                    root_dir = os.path.join(primary_fs.mount_point, existing.inventory['XAPI_DB_COMPAT_VERSION'])
                    gen = readDbGen(root_dir)
                
                    xelogging.log("Copying state from %s" % root_dir)
                    cmd = ['cp', '-a'] + \
                          [ os.path.join(root_dir, x) for x in os.listdir(root_dir) ] + \
                          ['%s/' % backup_fs.mount_point]
                    if util.runCmd2(cmd) != 0:
                        raise RuntimeError, "Backup of %s failed" % root_dir
                    if gen > db_generation[0]:
                        db_generation = (gen, state_info, existing.inventory['XAPI_DB_COMPAT_VERSION'])
                finally:
                    primary_fs.unmount()
                val += 10
                progress_callback(val)

            # always keep the state with the highest db generation count
            if db_generation[0] > gen:
                state_info = db_generation[1]
                mountPath = os.path.join('/dev', state_info['vg'], state_info['lv'])
                primary_fs = util.TempMount(mountPath, 'auxstate-', options = ['ro'])
                try:
                    root_dir = os.path.join(primary_fs.mount_point, db_generation[2])
                
                    xelogging.log("Copying state from %s" % root_dir)
                    cmd = ['cp', '-a'] + \
                          [ os.path.join(root_dir, x) for x in os.listdir(root_dir) ] + \
                          ['%s/' % backup_fs.mount_point]
                    if util.runCmd2(cmd) != 0:
                        raise RuntimeError, "Backup of %s failed" % root_dir
                finally:
                    primary_fs.unmount()
        finally:
            backup_fs.unmount()
            lvmTool.deactivateAll()

    prepUpgradeArgs = ['installation-uuid', 'control-domain-uuid', 'primary-disk', 'primary-partnum', 
        'backup-partnum', 'root-start', 'post-backup-delete']
    # Leave prepStateChanges as per superclass
    def prepareUpgrade(self, progress_callback, installID, controlID, primaryDisk, primaryPartnum, backupPartnum,
        rootStart, postBackupDelete):
        # Call the superclass method and store its return value.  This does the backup
        retVal = ThirdGenUpgrader.prepareUpgrade(self, progress_callback, installID, controlID)
        
        rootByteSize = constants.root_size * 2 ** 20
        # Delete partitions after backup
        partTool = PartitionTool(primaryDisk)
        xelogging.log('Backup complete - deleting partitions: '+','.join([str(x) for x in postBackupDelete]))
        partTool.deletePartitions(postBackupDelete)
        
        xelogging.log('Creating new primary partition as primary partition '+str(primaryPartnum))
        partTool.createPartition(number = primaryPartnum, id = partTool.ID_LINUX,
            startBytes = rootStart, sizeBytes = rootByteSize)
        
        # Set primary partition as bootable
        partTool.inactivateDisk()
        partTool.setActiveFlag(True, primaryPartnum)
        
        # Grow the backup partition to its full size, now that the state partition has gone
        partTool.resizePartition(backupPartnum, rootByteSize)
        partTool.commit()
        
        return retVal

    completeUpgradeArgs = ['mounts', 'installation-to-overwrite', 'primary-disk', 'backup-partnum', 'net-admin-interface', 'net-admin-bridge', 'net-admin-configuration']
    def completeUpgrade(self, mounts, prev_install, target_disk, backup_partnum, admin_iface, admin_bridge, admin_config):
        ThirdGenUpgrader.completeUpgrade(self, mounts, prev_install, target_disk, backup_partnum, admin_iface, admin_bridge, admin_config)
        if os.path.realpath(prev_install.primary_disk) != os.path.realpath(target_disk):
            xelogging.log("Deactivating all partitions on %s" % prev_install.primary_disk)
            partTool = PartitionTool(prev_install.primary_disk)
            partTool.inactivateDisk()
            partTool.commit()


################################################################################

# Upgraders provided here, in preference order:
class UpgraderList(list):
    def getUpgrader(self, product, version, variant):
        for x in self:
            if x.upgrades(product, version, variant):
                return x
        raise KeyError, "No upgrader found for %s" % version

    def hasUpgrader(self, product, version, variant):
        for x in self:
            if x.upgrades(product, version, variant):
                return True
        return False
    
__upgraders__ = UpgraderList([ ThirdGenUpgrader, ThirdGenOEMUpgrader ])

def filter_for_upgradeable_products(installed_products):
    upgradeable_products = filter(lambda p: p.isUpgradeable() and upgradeAvailable(p),
        installed_products)
    return upgradeable_products
