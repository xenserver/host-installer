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
from disktools import *
import xelogging
import tempfile
import shutil
import util
import os
import tui.init
import tui.progress
import constants
import re
import traceback

def go(ui):
    rc = interactiveRestore(ui)
    if rc == constants.EXIT_ERROR:
        ui.progress.OKDialog("Error restoring from backup", "An error occurred when attempting to restore your backup.  Please consult the logs (available in /tmp) for more details.")
    return rc

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

        rc = False
        try:
            rc = restoreFromBackup(backup_partition, disk, progress)

            if pd:
                tui.progress.clearModelessDialog()
        except Exception, e:
            try:
                # first thing to do is to get the traceback and log it:
                ex = sys.exc_info()
                err = str.join("", traceback.format_exception(*ex))
                xelogging.log("RESTORE FAILED.")
                xelogging.log("A fatal exception occurred:")
                xelogging.log(err)

                # now write out logs where possible:
                xelogging.writeLog("/tmp/restore-log")
    
                # collect logs where possible
                xelogging.collectLogs("/tmp")
    
                # now display a friendly error dialog:
                if ui:
                    ui.exn_error_dialog("restore-log", True)
                else:
                    txt = constants.error_string(str(e), 'install-log', True)
                    xelogging.log(txt)
    
            except Exception, e:
                # Don't let logging exceptions prevent subsequent actions
                print 'Logging failed: '+str(e)

        if rc:
            tui.progress.OKDialog("Restore", "The restore operation completed successfully.")
            return constants.EXIT_OK
        else:
            return constants.EXIT_ERROR
    else:
        return constants.EXIT_USER_CANCEL

def restoreFromBackup(backup_partition, disk, progress = lambda x: ()):
    """ Restore files from backup_partition to the root partition (as
    determined by diskutil.getRootPartName(disk)) on disk.  Call progress
    with a value between 0 and 100.  Re-install bootloader.  Fails if 
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

            # Use 'cp' here because Python's copying tools are useless and
            # get stuck in an infinite loop when copying e.g. /dev/null.
            if util.runCmd2(['cp', '-a', os.path.join(backup_mnt, obj),
                             os.path.join(dest_mnt)]) != 0:
                raise RuntimeError, "Failed to restore %s directory" % obj

        xelogging.log("Data restoration complete.  About to re-install bootloader.")

        if os.path.exists(os.path.join(backup_mnt, "boot", "grub", "menu.lst")):
            bootloader = constants.BOOTLOADER_TYPE_GRUB
            bootloader_config = os.path.join("boot", "grub", "menu.lst")
        elif os.path.exists(os.path.join(backup_mnt, "boot", "extlinux.conf")):
            bootloader = constants.BOOTLOADER_TYPE_EXTLINUX
            bootloader_config = os.path.join("boot", "extlinux.conf")
        else:
            raise RuntimeError, "Unable to determine boot loader"

        xelogging.log("Bootloader is %s" % bootloader)

        # preserve bootloader configuration
        if util.runCmd2(['cp', os.path.join(backup_mnt, bootloader_config), '/tmp/bootloader.tmp']) != 0:
            raise RuntimeError, "Failed copy bootloader configuration"
        mounts = {'root': dest_mnt, 'boot': os.path.join(dest_mnt, 'boot')}
        backend.installBootLoader(mounts, disk, primary_partnum, bootloader, None, None)
        if util.runCmd2(['cp', '/tmp/bootloader.tmp',
                         os.path.join(dest_mnt, bootloader_config)]) != 0:
            raise RuntimeError, "Failed restore bootloader configuration"

        # find out the label
        v, out = util.runCmd2(['grep', 'root=LABEL', '/tmp/bootloader.tmp'], with_stdout = True)
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

        success = True
    finally:
        util.umount(backup_mnt)
        util.umount(dest_mnt)
        os.rmdir(backup_mnt)
        os.rmdir(dest_mnt)

    return success
