#!/usr/bin/env python
# Copyright (c) Citrix Systems 2008, 2009.  All rights reserved.
# Xen, the Xen logo, XenCenter, XenMotion are trademarks or registered
# trademarks of Citrix Systems, Inc., in the United States and other
# countries.

# This file encapsulates differences between the retail and OEM variants of XenServer,
# and the flash and disk variants of OEM XenServer.
#
# Retail-specific methods live in the VariantRetail object.
# OEM-specific methods live in the VariantOEM object.
# OEM-disk-specific methods live in the VariantOEMDisk object.
# OEM-flash-specific methods live in the VariantOEMFlash object.
#
# The Variant superclass object can contain code/strategy common to all but doesn't have to.
#
# The installer sets up an instance of the correct type early on, so methods in this file 
# that are to act on the current type that is being installed should be accessed as:
#
# Variant.inst().MethodName(params)

# Please import this file as from variant import *, don't add free functions to this file, and
# try to minimise the amount of code in these objects

# Python library imports
import os, tempfile, re
# Local file imports
import diskutil, util, xelogging, constants

class Variant: # Superclass
    __inst = None # Reference to the singleton object
    
    @classmethod
    def setInstance(cls, instance): # Singleton housekeeping
        cls.__inst = instance
    
    @classmethod
    def inst(cls): # Access to singleton instance
        return cls.__inst

######################################################################
class VariantRetail(Variant):
    ETC_RESOLV_CONF = "etc/resolv.conf"
    ETC_NTP_CONF = "etc/ntp.conf"

    def raiseIfRetail(self, source = ''):
        raise Exception('Operation cannot be performed on retail edition ('+str(source)+')')
         
    def raiseIfOEM(self, source = ''):
        pass
        
    @classmethod
    def runOverRootPartition(cls, partition, procedure, mode = None):
        mountpoint = tempfile.mkdtemp('-runOverRoot')
        try:
            if mode == 'rw':
                options = ['rw']
            else:
                options = ['ro']
            util.mount(partition, mountpoint, options, 'ext3')
            try:
                ret_val = procedure(mountpoint)
            finally:
                util.umount(mountpoint)
        finally:
            os.rmdir(mountpoint)
        return ret_val
    
    @classmethod
    def runOverStatePartition(cls, partition, procedure, build, mode = None):
        # In retail, the root and state partition are the same partition
        return cls.runOverRootPartition(partition, procedure, mode)
    
    @classmethod
    def findInstallation(cls, disk):
        p = diskutil.determinePartitionName(disk, constants.RETAIL_ROOT_PARTITION_NUMBER)
        ret = None

        build_map = {}

        def scanPartition(mountpoint):
            inventory_file = os.path.join(mountpoint, constants.INVENTORY_FILE)
            if os.path.exists(inventory_file):
                inv = util.readKeyValueFile(inventory_file, strip_quotes = True)
                build_map['inv'] = inv
                xelogging.log('Inventory on '+str(p)+': '+str(inv))

        try:
            # Run scanPartition over p, treating it as a root partition
            cls.runOverRootPartition(p, scanPartition)
            ret = (build_map['inv'], p, p, cls)
        except Exception, e:
            xelogging.log('Test for root partition '+p+' negative:')
            xelogging.log_exception(e)

        return ret

######################################################################
class VariantOEM(Variant):
    ETC_RESOLV_CONF = "etc/freq-etc/etc/resolv.conf"
    ETC_NTP_CONF = "etc/freq-etc/etc/ntp.conf"

    def raiseIfRetail(self, source = ''):
        pass
        
    def raiseIfOEM(self, source = ''):
        raise Exception('Operation cannot be performed on OEM edition ('+str(source)+')')

    @classmethod
    def runOverRootPartition(cls, partition, procedure, mode = None):
        if mode == 'rw':
            raise Exception('OEM root partition is read-only')
        mountpoint = tempfile.mkdtemp('-runOverRoot')
        try:
            util.mount(partition, mountpoint, ['ro'], 'ext3')
            try:
                if os.path.exists(os.path.join(mountpoint, constants.INVENTORY_FILE)):
                    # This is a rootfs-writable installation, so no need to loop-mount rootfs
                    ret_val = procedure(mountpoint)            
                else:
                    rootfs_path = mountpoint+'/rootfs'
                    rootfs_mountpoint = tempfile.mkdtemp('-runOverRootFS')
                    util.mount(rootfs_path, rootfs_mountpoint, ['loop', 'ro'], 'squashfs')
                    
                    try:
                        ret_val = procedure(rootfs_mountpoint)
                    finally:
                        util.umount(rootfs_mountpoint)
                        os.rmdir(rootfs_mountpoint)
            finally:
                util.umount(mountpoint)
        finally:
            os.rmdir(mountpoint)
        return ret_val

    @classmethod
    def runOverStatePartition(cls, partition, procedure, build, mode = None):
        # OEM state partitons have special features:
        # 1.  They contain subdirectories with multiple versions, to support the revert upgrade feature.
        # 2.  Directories are named 'xe-<version>', e.g. xe-11591x
        # 3.  Frequently modified files are symlinked into tmpfs to reduced FLASH writes.
        #     In a running installation these files are found in /var/freq-etc, but copies
        #     are written back to /etc/freq-etc/etc on clean shutdown.
        
        if mode == 'rw':
            options = ['rw']
        else:
            options = ['ro']
        mountpoint = tempfile.mkdtemp('-runOverState')
        util.mount(partition, mountpoint, options, 'ext3')
        try:
            state_path = os.path.join(mountpoint, 'xe-'+build)
            if os.path.exists(state_path):
                ret_val = procedure(state_path)
            else:
                raise Exception('State directory not present')
            
        finally:
            util.umount(mountpoint)
            os.rmdir(mountpoint)
        return ret_val

    @classmethod
    def _findActiveRoot(cls, boot_partition):
        active_root = None
        mountpoint = tempfile.mkdtemp('-findActiveRoot')
        try:
            util.mount(boot_partition, mountpoint, ['ro'],'vfat')
            try:
                syslinux_cfg = os.path.join(mountpoint, constants.SYSLINUX_CFG)
                if os.path.exists(syslinux_cfg):
                    try:
                        sysl_fd = open(syslinux_cfg)
                        expr = re.compile('^\s*DEFAULT\s+([12])\s*$')
                        for line in sysl_fd.readlines():
                            m = expr.match(line)
                            if m:
                                if m.group(1) == "1":   
                                    active_root = cls.getSystemPartition1()
                                elif m.group(1) == "2":   
                                    active_root = cls.getSystemPartition2()
                    finally:
                        sysl_fd.close()
            finally:
                util.umount(mountpoint)
                os.rmdir(mountpoint)
        except Exception, e:
            xelogging.log('Boot partition %s mount failed:' % boot_partition)
            xelogging.log_exception(e)

        return active_root

    @classmethod
    def _findBootAndRoot(cls, disk):
        # 1. Identify the boot partition
        boot_partition = diskutil.getActivePartition(disk)
        if not boot_partition:
            return None

        # 2. Verify that the type is some type of FAT and that
        #    the FAT label is correct
        try:
            if diskutil.readFATPartitionLabel(boot_partition).strip() != \
                constants.OEM_BOOT_PARTITION_FAT_LABEL:
                xelogging.log('Not an OEM XS boot partition: %s' % boot_partition)
                return None
        except:
            xelogging.log('Exception: not an OEM XS boot partition: %s' % boot_partition)
            return None

        # 3. Read the syslinux.cfg file in the boot partition
        #    to determine which installation is active

        active_root = cls._findActiveRoot(boot_partition)
        if not active_root:
            xelogging.log('Could not determine active system root partition from %s' % boot_partition)
            return None
        
        root_partition = diskutil.determinePartitionName(disk, active_root)
        if not os.path.exists(root_partition):
            return None

        return (boot_partition, root_partition)

    @classmethod
    def _findState(cls, partition, build):
        disk = diskutil.diskFromPartition(partition)
        
        state_partition = None
        candidate = diskutil.determinePartitionName(disk, cls.getStatePartition())
        mountpoint = tempfile.mkdtemp('-stateFromRoot')
        try:
            try:
                util.mount(candidate, mountpoint, ['ro'], 'ext3')
                files = os.listdir(mountpoint)
                # Need an exact match on the name for the state directory:
                if 'xe-%s' % build in files:
                    state_partition = candidate
            except Exception, e:
                xelogging.log('Inspection of state partition failed:')
                xelogging.log_exception(e)
        finally:
            util.umount(mountpoint)
            os.rmdir(mountpoint)
 
        if state_partition is None:
            raise Exception('Could not determine state partition from root at '+partition)
        return state_partition

    @classmethod
    def getSystemPartition1(cls):
        raise Exception("Cannot deduce partition from OEM superclass")

    @classmethod
    def getSystemPartition2(cls):
        raise Exception("Cannot deduce partition from OEM superclass")

    @classmethod
    def getStatePartition(cls):
        raise Exception("Cannot deduce partition from OEM superclass")

    @classmethod
    def findInstallation(cls, disk):
        try:
            (boot_partition, root_partition) = cls._findBootAndRoot(disk)
        except:
            return None

        # Read the inventory on the active read-only root partition.
        help_map = {}

        def scanPartition(mountpoint):
            inventory_file = os.path.join(mountpoint, constants.INVENTORY_FILE)
            inv = util.readKeyValueFile(inventory_file, strip_quotes = True)
            help_map['inv'] = inv

        try:
            # Run scanPartition over p, treating it as a root partition.
            # Do this to determine the build number for locating the state.
            cls.runOverRootPartition(root_partition, scanPartition)
        except Exception, e:
            xelogging.log('Test for root partition '+root_partition+' negative:')
            xelogging.log_exception(e)

        try:
            build = help_map['inv']['BUILD_NUMBER']
            state_partition = cls._findState(root_partition, build)
            # Read the _writable_ copy of the xensource-inventory here:
            cls.runOverStatePartition(state_partition, scanPartition, build, mode='ro')
        except:
            return None

        return (help_map['inv'], root_partition, state_partition, cls)

######################################################################
class VariantOEMFlash(VariantOEM):
    @classmethod
    def getSystemPartition1(cls):
        return constants.OEMFLASH_SYS_1_PARTITION_NUMBER

    @classmethod
    def getSystemPartition2(cls):
        return constants.OEMFLASH_SYS_2_PARTITION_NUMBER

    @classmethod
    def getStatePartition(cls):
        return constants.OEMFLASH_STATE_PARTITION_NUMBER

######################################################################
class VariantOEMDisk(VariantOEM):
    @classmethod
    def getSystemPartition1(cls):
        return constants.OEMHDD_SYS_1_PARTITION_NUMBER

    @classmethod
    def getSystemPartition2(cls):
        return constants.OEMHDD_SYS_2_PARTITION_NUMBER

    @classmethod
    def getStatePartition(cls):
        return constants.OEMHDD_STATE_PARTITION_NUMBER
