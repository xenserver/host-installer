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
import constants
import re

def restoreFromBackup(backup_partition, disk, progress = lambda x: ()):
    """ Restore files from backup_partition to the root partition on disk.
    Call progress with a value between 0 and 100.  Re-install bootloader.  Fails if 
    backup is not same version as the CD in use."""

    assert backup_partition.startswith('/dev/')
    assert disk.startswith('/dev/')

    primary_partnum, _, __ = backend.inspectTargetDisk(disk, [])
    restore_partition = PartitionTool.partitionDevice(disk, primary_partnum)
    xelogging.log("Restoring to partition %s." % restore_partition)

    # first, format the primary disk:
    if util.runCmd2(['mkfs.ext3', restore_partition]) != 0:
        raise RuntimeError, "Failed to create filesystem"

    # mount both volumes:
    dest_fs = util.TempMount(restore_partition, 'restore-dest-')
    try:
        backup_fs = util.TempMount(backup_partition, 'restore-backup-', options = ['ro'])
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

            if os.path.exists(os.path.join(backup_fs.mount_point, "boot/grub/menu.lst")):
                bootloader = constants.BOOTLOADER_TYPE_GRUB
                bootloader_config = "boot/grub/menu.lst"
            elif os.path.exists(os.path.join(backup_fs.mount_point, "boot/extlinux.conf")):
                bootloader = constants.BOOTLOADER_TYPE_EXTLINUX
                bootloader_config = "boot/extlinux.conf"
            else:
                raise RuntimeError, "Unable to determine boot loader"

            xelogging.log("Bootloader is %s" % bootloader)

            # preserve bootloader configuration
            if util.runCmd2(['cp', os.path.join(backup_fs.mount_point, bootloader_config), '/tmp/bootloader.tmp']) != 0:
                raise RuntimeError, "Failed copy bootloader configuration"
            mounts = {'root': dest_fs.mount_point, 'boot': os.path.join(dest_fs.mount_point, 'boot')}
            backend.installBootLoader(mounts, disk, primary_partnum, bootloader, None, None)
            if util.runCmd2(['cp', '/tmp/bootloader.tmp',
                             os.path.join(dest_fs.mount_point, bootloader_config)]) != 0:
                raise RuntimeError, "Failed restore bootloader configuration"
        finally:
            backup_fs.unmount()
    finally:
        dest_fs.unmount()
            
    # find out the label
    rc, out = util.runCmd2(['grep', 'root=LABEL', '/tmp/bootloader.tmp'], with_stdout = True)
    if rc != 0:
        raise RuntimeError, "Failed to find disk label"
    p = re.compile('root=LABEL=root-\w+')
    labels = p.findall(out)

    if len(labels) == 0:
        raise RuntimeError, "Failed to find label required for root filesystem."
    else:
        # just take the first one
        newlabel = labels[0]
        if util.runCmd2(['e2label', restore_partition, newlabel[len('root=LABEL='):]]) != 0:
            raise RuntimeError, "Failed to label partition"

        xelogging.log("Bootloader restoration complete.")
        xelogging.log("Restore successful.")
