# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this
# copyrighted material is governed by and subject to terms and conditions
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Functions to perform restore from backup partition, including UI.
#
# written by Andrew Peace

import backend
from disktools import *
import xelogging
import util
import os
import os.path
import constants
import re
import bootloader

def restoreFromBackup(backup_partition, disk, progress = lambda x: ()):
    """ Restore files from backup_partition to the root partition on disk.
    Call progress with a value between 0 and 100.  Re-install bootloader.  Fails if 
    backup is not same version as the CD in use."""

    assert backup_partition.startswith('/dev/')
    assert disk.startswith('/dev/')

    label = None
    primary_partnum, _, __ = backend.inspectTargetDisk(disk, [])
    restore_partition = partitionDevice(disk, primary_partnum)
    xelogging.log("Restoring to partition %s." % restore_partition)

    # determine current location of bootloader
    current_location = 'unknown'
    try:
        root_fs = util.TempMount(restore_partition, 'root-', options = ['ro'])
        try:
            boot_config = bootloader.Bootloader.loadExisting(root_fs.mount_point)
            current_location = boot_config.location
            xelogging.log("Bootloader currently in %s" % current_location)
        finally:
            root_fs.unmount()
    except:
        pass

    # mount the backup fs
    backup_fs = util.TempMount(backup_partition, 'restore-backup-', options = ['ro'])
    try:        
        # extract the bootloader config
        boot_config = bootloader.Bootloader.loadExisting(backup_fs.mount_point)
        if boot_config.src_fmt == 'grub':
            raise RuntimeError, "Backup uses grub bootloader which is no longer supported - " + \
                "to restore please use a version of the installer that matches the backup partition"

        # format the restore partition:
        if util.runCmd2(['mkfs.ext3', restore_partition]) != 0:
            raise RuntimeError, "Failed to create filesystem"

        # mount restore partition:
        dest_fs = util.TempMount(restore_partition, 'restore-dest-')
        try:

            # copy files from the backup partition to the restore partition:
            objs = filter(lambda x: x not in ['lost+found', '.xen-backup-partition'], 
                          os.listdir(backup_fs.mount_point))
            for i in range(len(objs)):
                obj = objs[i]
                xelogging.log("Restoring subtree %s..." % obj)
                progress((i * 100) / len(objs))

                # Use 'cp' here because Python's copying tools are useless and
                # get stuck in an infinite loop when copying e.g. /dev/null.
                if util.runCmd2(['cp', '-a', os.path.join(backup_fs.mount_point, obj),
                                 dest_fs.mount_point]) != 0:
                    raise RuntimeError, "Failed to restore %s directory" % obj

            xelogging.log("Data restoration complete.  About to re-install bootloader.")

            location = boot_config.location
            m = re.search(r'root=LABEL=(\S+)', boot_config.menu[boot_config.default].kernel_args)
            if m:
                label = m.group(1)
            if location == 'partition' and current_location == 'mbr':
                # if bootloader in the MBR it's probably not safe to restore with it
                # on the partition
                xelogging.log("Bootloader is currently installed to MBR, restoring to MBR instead of partition")
                location = 'mbr'

            mounts = {'root': dest_fs.mount_point, 'boot': os.path.join(dest_fs.mount_point, 'boot')}
            backend.installBootLoader(mounts, disk, primary_partnum, None, False, [], location)

            # restore bootloader configuration
            dst_file = boot_config.src_file.replace(backup_fs.mount_point, dest_fs.mount_point, 1)
            util.assertDir(os.path.dirname(dst_file))
            boot_config.commit(dst_file)
        finally:
            dest_fs.unmount()
    finally:
        backup_fs.unmount()

    if not label:
        raise RuntimeError, "Failed to find label required for root filesystem."

    if util.runCmd2(['e2label', restore_partition, label]) != 0:
        raise RuntimeError, "Failed to label partition"

    xelogging.log("Bootloader restoration complete.")
    xelogging.log("Restore successful.")
