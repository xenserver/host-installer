#!/usr/bin/env python
# Copyright (c) Citrix Systems 2008.  All rights reserved.
# Xen, the Xen logo, XenCenter, XenMotion are trademarks or registered
# trademarks of Citrix Systems, Inc., in the United States and other
# countries.

# This file encapsulates differences between the retail and OEM variants of XenServer
#
# Retail-specific methods live in the VariantRetail object.
# OEM-specific methods live in the VariantOEM object.
# Both inherit from the Variant object, which can contain code/strategy common to both but doesn't have to.
# The installer sets up an instance of the correct type early on, so methods in this file should be
# accessed as:
#
# Variant.inst().MethodName(params)

# Please import this file as from variant import *, don't add free functions to this file, and
# try to minimise the amount of code in these objects

# Python library imports
import os, tempfile
# Local file imports
import diskutil, util

class Variant: # Superclass
    __inst = None # Reference to the singleton object
    
    @classmethod
    def setInstance(cls, instance): # Singleton housekeeping
        cls.__inst = instance
    
    @classmethod
    def inst(cls): # Access to singleton instance
        return cls.__inst


class VariantRetail(Variant):
    def rootPartitionCandidates(self):
        # Get a list of disks, then return the first partition of each disk
        partitions = [ diskutil.determinePartitionName(x, 1) for x in diskutil.getQualifiedDiskList() ]
    
        return partitions
    
    def runOverRootPartition(self, partition, procedure, mode = None):
        mountpoint = tempfile.mkdtemp('-runOverRoot')
        if mode == 'rw':
            options = ['rw']
        else:
            options = ['ro']
        util.mount(partition, mountpoint, options, 'ext3')
        try:
            ret_val = procedure(mountpoint)
        finally:
            util.umount(mountpoint)
            os.rmdir(mountpoint)
        return ret_val
    
    def runOverStatePartition(self, partition, procedure, build, mode = None):
        # In retail, the root and state partition are the same partition
        return self.runOverRootPartition(partition, procedure, mode)
    
    def findStatePartitionFromRoot(self, partition):
        # In retail, the root and state partition are the same partition
        return partition
    
    def raiseIfRetail(self, source = ''):
        raise Exception('Operation cannot be performed on retail edition ('+str(source)+')')
         
    def raiseIfOEM(self, source = ''):
        pass
        
        
class VariantOEM(Variant):
    def rootPartitionCandidates(self):
        # Get a list of disks, then return the first, second and third partition of each disk.
        # OEM has two root partitions, and these can be preceded by an OEM utility partition
        partitions = []
        for disk in diskutil.getQualifiedDiskList():
            for i in range(1, 4): # range(1, 4) is [1, 2, 3]
                partitions.append(diskutil.determinePartitionName(disk, i))

        return partitions

    def runOverRootPartition(self, partition, procedure, mode = None):
        if mode == 'rw':
            raise Exception('OEM root partition is read-only')
        mountpoint = tempfile.mkdtemp('-runOverRoot')
        util.mount(partition, mountpoint, ['ro'], 'ext3')
        try:
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
            os.rmdir(mountpoint)
        return ret_val

    def runOverStatePartition(self, partition, procedure, build, mode = None):
        # OEM state partitons have special features:
        # 1.  They contain subdirectories with multiple versions, to support the revert upgrade feature.
        # 2.  Directories are named 'xe-<version>', e.g. xe-11591x
        # 3.  Frequently modified files are symlinked into tmpfs to reduced FLASH writes.  In a running
        # installation these files are found in /var/freq-etc, but should be written back to /etc on shutdown.
        
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

    def findStatePartitionFromRoot(self, partition):
        # In OEM, the state partition is immediately after the root partitions
        
        # Split the partition into disk and partition number
        partitionNumber = diskutil.partitionNumberFromPartition(partition)
        disk = diskutil.diskFromPartition(partition)
        
        state_partition = None
        # Test partitions n+1 and n+2
        for n in [ partitionNumber+1, partitionNumber+2 ]:
            candidate = diskutil.determinePartitionName(disk, n)
            mountpoint = tempfile.mkdtemp('-stateFromRoot')
            try:
                util.mount(candidate, mountpoint, ['ro'],'ext3')
                try:
                    files = os.listdir(mountpoint)
                    # State partitions will not have rootfs, but may be empty
                    if 'rootfs' not in files:
                        state_partition = candidate
                        break
                finally:
                    util.umount(mountpoint)
                    os.rmdir(mountpoint)
            except Exception, e:
                xelogging.log('State partition test mount failed:')
                xelogging.log_exception(e)

        if state_partition is None:
            raise Exception('Could not determine state partition from root at '+partition)
        return state_partition

    def raiseIfRetail(self, source = ''):
        pass
        
    def raiseIfOEM(self, source = ''):
        raise Exception('Operation cannot be performed on OEM edition ('+str(source)+')')
         
    
