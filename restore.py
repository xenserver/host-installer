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

import product
import backend
import diskutil
import xelogging
import tempfile
import shutil
import util
import os
import tui.init
import tui.progress
import constants
import re

def interactiveRestore(ui):
    backups = product.findXenSourceBackups()

    if len(backups) == 0:
        raise RuntimeError, "No backups found."

    if len(backups) > 1:
        backup = tui.init.select_backup(backups)
    else:
        backup = backups[0]
    backup_partition, disk = backup

    if tui.init.confirm_restore(backup_partition, disk):
        if ui:
            pd = tui.progress.initProgressDialog("Restoring", "Restoring data - this may take a while...", 100)
        def progress(x):
            if ui and pd:
                tui.progress.displayProgressDialog(x, pd)
        rc = restoreFromBackup(backup_partition, disk, progress)
        if pd:
            tui.progress.clearModelessDialog()
        if rc:
            tui.progress.OKDialog("Restore", "The restore operation completed successfully.")

    return rc

def restoreFromBackup(backup_partition, disk, progress = lambda x: ()):
    """ Restore files from backup_partition to the root partition (as
    determined by backend.getRootPartName(disk)) on disk.  Call progress
    with a value between 0 and 100.  Re-install bootloader.  Fails if 
    backup is not same version as the CD in use."""

    assert backup_partition.startswith('/dev/')
    assert disk.startswith('/dev/')

    restore_partition = backend.getRootPartName(disk)
    xelogging.log("Restoring to partition %s." % restore_partition)

    # first, format the primary disk:
    if util.runCmd2(['mkfs.ext3', '-L', constants.rootfs_label, restore_partition]) != 0:
        return False

    # mount both volumes:
    dest_mnt = tempfile.mkdtemp(prefix = 'restore-dest-', dir = '/tmp')
    backup_mnt = tempfile.mkdtemp(prefix = 'restore-backup-', dir = '/tmp')
    
    success = False
    try:
        util.mount(backup_partition, backup_mnt, options = ['ro'])
        util.mount(restore_partition, dest_mnt)

        # copy files from the backup partition to the restore partition:
        objs = filter(lambda x: x not in ['lost+found', '.xen-backup-partition'], 
                      os.listdir(backup_mnt))
        for i in range(len(objs)):
            obj = objs[i]
            xelogging.log("Restoring subtree %s..." % obj)
            progress((i * 100) / len(objs))

            # Use 'cp' here because Python's coyping tools are useless and
            # get stuck in an infinite loop when copying e.g. /dev/null.
            util.runCmd2(['cp', '-a', os.path.join(backup_mnt, obj),
                          os.path.join(dest_mnt)])

        xelogging.log("Data restoration complete.  About to re-install Grub.")

        # preserve menu.lst:
        util.runCmd2(['cp', os.path.join(backup_mnt, "boot", "grub", "menu.lst"), '/tmp'])
        mounts = {'root': dest_mnt, 'boot': os.path.join(dest_mnt, 'boot')}
        backend.installGrub(mounts, disk)
        util.runCmd2(['cp', '/tmp/menu.lst',
                      os.path.join(dest_mnt, 'boot', 'grub', 'menu.lst')])

        #find out the label
        [v,out] = util.runCmd2(['grep', '"root\=LABEL"', '/tmp/menu.lst'], True)
        p = re.compile('root=LABEL=root-\w+')
        labels = p.findall(out)

        if (len(labels)==0):
           raise
        else:
           #just take the first one
            newlabel=labels[0]
            util.runCmd2(['e2label', restore_partition, newlabel[len('root=LABEL=root-'):]])

        xelogging.log("Bootloader restoration complete.")
        xelogging.log("Restore successful.")

        success = True
    finally:
        util.umount(backup_mnt)
        util.umount(dest_mnt)
        os.rmdir(backup_mnt)
        os.rmdir(dest_mnt)

    return success
