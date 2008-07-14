#!/usr/bin/env python
# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Boot script
#
# written by Mark Nijmeijer and Andrew Peace

import commands
import sys
import os
import os.path
import shutil
import time

# user interface:
import tui
import tui.init_oem
import tui.progress
import generalui

import product
import diskutil
import init_constants
import xelogging
import answerfile
import netutil
import util
import repository
import tempfile
import bz2
import re

from version import *
from constants import EXIT_OK, EXIT_ERROR, EXIT_USER_CANCEL

scriptdir = os.path.dirname(sys.argv[0]) + "/oem"

def getPartitionNode(disknode, pnum):
    midfix = ""
    if re.search("/cciss/", disknode):
        midfix = "p"
    return disknode + midfix + str(pnum)

def writeImageWithProgress(ui, devnode, answers):
    image_name = answers['image-name']
    image_fd    = answers['image-fd']
    if re.search(".bz2$", image_name):
        decompressor = bz2.BZ2Decompressor().decompress
    else:
        decompressor = lambda x: x
    devfd = open(devnode, mode="wb")
    bzfilesize = answers['image-size']
    rdbufsize = 16<<10
    reads_done = 0
    reads_needed = int(float(bzfilesize)/float(rdbufsize))

    if ui:
        pd = ui.progress.initProgressDialog(
            "Decompressing image",
            "%(image_name)s is being written to %(devnode)s" % locals(),
            reads_needed)
        ui.progress.displayProgressDialog(0, pd)

    try:
        while True:
            buffer = image_fd.read(rdbufsize)
            reads_done += 1
            if not buffer:
                break
            devfd.write(decompressor(buffer))
            if ui:
                ui.progress.displayProgressDialog(min(reads_needed, reads_done), pd)
    except Exception, e:
        xelogging.log_exception(e)
        if ui:
            ui.progress.clearModelessDialog()
        image_fd.close()
        devfd.close()
        if ui:
            ui.OKDialog("Error", "Fatal error occurred during write.  Press any key to reboot")
        return EXIT_ERROR

    # image successfully written
    if ui:
        ui.progress.clearModelessDialog()
    image_fd.close()
    devfd.close()

    return EXIT_OK

def post_process_answerfile_data(results):
    "Processing the answerfile entries to derive data"

    dirname  = os.path.dirname(results['source-address'])
    basename = os.path.basename(results['source-address'])

    results['image-name'] = basename

    if results['source-media'] == 'local':

        if len(dirname.split(':')) > 1:
            (dev, dirname) = dirname.split(':', 1)
            device_path = "/dev/%s" % dev
            if not os.path.exists(device_path):
                # Device path doesn't exist (maybe udev renamed it).  Create it now.
                major, minor = map(int, open('/sys/block/%s/dev' % dev).read().split(':'))
                os.mknod(device_path, 0600|stat.S_IFBLK, os.makedev(major,minor))

            da = repository.DeviceAccessor(device_path)
            try:
                da.start()
            except util.MountFailureException:
                raise AnswerfileError, "Could not mount local %s to read image." % device_path

            fulldirpath = da.location + '/' + dirname
            fullpath = os.path.join(fulldirpath, basename)

            # check for existence using stat
            try:
                imageSize = os.stat(fullpath).st_size
            except OSError:
                raise AnswerfileError, "No local OEM image found at %s." % results['source-address']

            results['image-size'] = imageSize
            results['image-fd'] = open(fullpath, "rb")
            results['accessor'] = da

        else:
            # scan all local devices for the file
            # *including* local disk partitions (think: factory install)
            devs_and_ptns = diskutil.getPartitionList()
            devs_and_ptns.extend(diskutil.getRemovableDeviceList())

            for check in devs_and_ptns:
                device_path = "/dev/%s" % check
                if not os.path.exists(device_path):
                    # Device path doesn't exist (maybe udev renamed it).  Create it now.
                    major, minor = map(int, open('/sys/block/%s/dev' % check).read().split(':'))
                    os.mknod(device_path, 0600|stat.S_IFBLK, os.makedev(major,minor))

                da = repository.DeviceAccessor(device_path)
                try:
                    da.start()
                except util.MountFailureException:
                    continue

                fulldirpath = os.path.join(da.location, dirname)
                fullpath = os.path.join(fulldirpath, basename)
                try:
                    imageSize = os.stat(fullpath).st_size
                except OSError:
                    da.finish()
                    continue

                results['image-size'] = imageSize
                results['image-fd'] = open(fullpath, "rb")
                results['accessor'] = da
                break

            if not results.has_key('accessor'):
                raise AnswerfileError, "Scan found no local OEM image at %s." % results['source-address']
    else:
        if results['source-media'] == 'nfs':
            accessor = repository.NFSAccessor(dirname)
        else:
            accessor = repository.URLAccessor(dirname)

        try:
            accessor.start()
        except:
            raise AnswerfileError, "Could not reach image at %s." % results['source-address']

        if not accessor.access(basename):
            accessor.finish()
            raise AnswerfileError, "Could not find image at %s." % basename

        results['image-fd'] = accessor.openAddress(basename)
        results['accessor'] = accessor

        if results['source-media'] == 'nfs':
            fullpath = os.path.join(accessor.location, basename)
            results['image-size'] = os.stat(fullpath).st_size
        else:
            results['image-size'] = 900000000 # FIXME: A GUESS!


def go_disk(ui, args, answerfile_address):
    "Install oem edition to disk"

    # loading an answerfile?
    assert ui != None or answerfile_address != None

    if answerfile_address:
        answers = answerfile.processAnswerfile(answerfile_address)
        post_process_answerfile_data(answers)

    else:
        xelogging.log("Starting install to disk dialog")
        if ui:
            answers = ui.init_oem.recover_disk_drive_sequence()
        if not answers:
            return None # keeps outer loop going

    xelogging.log("Starting install to disk, partitioning")

    SYS_1_PARTITION_NUMBER = 5
    SYS_2_PARTITION_NUMBER = 6
    STATE_PARTITION_NUMBER = 7
    SR_PARTITION_NUMBER    = 8

    devnode = answers["primary-disk"]

    # Step 1: create system partitions.
    #
    if ui:
        ui.progress.showMessageDialog("Partitioning", "Creating the system image disk partitions ...")
    
    rv, output = util.runCmd('%s/create-partitions %s 2>&1' % (scriptdir,devnode), with_output=True)
    if ui:
        ui.progress.clearModelessDialog()
    if rv:
        if ui:
            ui.OKDialog ("Error", "Fatal error occurred during disk partitioning:\n\n%s\n\n"
                         "Press any key to reboot" % output)
        return EXIT_ERROR

    # Step 2: ensure that the device nodes for the new partitions are available
    xelogging.log("Waiting on new partition device nodes")

    # lookup the boot partition number
    rv, output = util.runCmd('/sbin/fdisk -l %s 2>&1 | /bin/sed -ne \'s,^%sp\\?\\([1-4]\\)  *\\*.*$,\\1,p\' 2>&1' % (devnode, devnode), with_output=True)
    if rv:
        if ui:
            ui.OKDialog ("Error", "Fatal error identifying boot partition:\n\n%s\n\n"
                         "Press any key to reboot" % output)
        return EXIT_ERROR
    BOOT_PARTITION_NUMBER = int(output)

    all_devnodes_present = False
    retries = 5
    while not all_devnodes_present:
        for pnum in (BOOT_PARTITION_NUMBER,
                     SYS_1_PARTITION_NUMBER, SYS_2_PARTITION_NUMBER,
                     STATE_PARTITION_NUMBER, SR_PARTITION_NUMBER):
            p_devnode = getPartitionNode(devnode, pnum)
            if not os.path.exists(p_devnode):
                if retries > 0:
                    retries -= 1
                    time.sleep(1)
                    break
                else:
                    ui.OKDialog("Error", "Partition device nodes failed to appear. Press any key to reboot")
                    return EXIT_ERROR

        else:
            all_devnodes_present = True

    # Step 3: decompress the image into the SR partition (use as tmp dir)
    xelogging.log("Decompressing image")

    sr_devnode = getPartitionNode(devnode, SR_PARTITION_NUMBER)
    rv = writeImageWithProgress(ui, sr_devnode, answers)
    if rv:
        return EXIT_ERROR

    # Step 4: populate the partitions from the decompressed image.
    #
    # The boot partition is a primary FAT16 partition with a well-known label.
    # The extended partition contains:
    #   p5: system image 1
    #   p6: system image 2
    #   p7: writable state
    #   p8: local SR

    xelogging.log("Populating system partitions")

    ###########################################################################
    if ui:
        ui.progress.showMessageDialog("Imaging", "Installing master boot record...")
    
    rv, output = util.runCmd('%s/populate-partition %s %s master-boot-record 2>&1' % (scriptdir,sr_devnode, devnode), with_output=True)
    if ui:
        ui.progress.clearModelessDialog()
    if rv:
        if ui:
            ui.OKDialog ("Error", "Fatal error occurred during installation of master boot record:\n\n%s\n\n" 
                         "Press any key to reboot" % output)
        return EXIT_ERROR

    ###########################################################################
    if ui:
        ui.progress.showMessageDialog("Imaging", "Populating primary system image...")
    
    partnode = getPartitionNode(devnode, SYS_1_PARTITION_NUMBER)
    rv, output = util.runCmd('%s/populate-partition %s %s system-image-1 2>&1' % (scriptdir,sr_devnode, partnode), with_output=True)
    if ui:
        ui.progress.clearModelessDialog()
    if rv:
        if ui:
            ui.OKDialog ("Error", "Fatal error occurred during population of primary system image:\n\n%s\n\n" 
                         "Press any key to reboot" % output)
        return EXIT_ERROR

    ###########################################################################
    if ui:
        ui.progress.showMessageDialog("Imaging", "Populating secondary system image...")
    
    partnode = getPartitionNode(devnode, SYS_2_PARTITION_NUMBER)
    rv, output = util.runCmd('%s/populate-partition %s %s system-image-2 2>&1' % (scriptdir,sr_devnode, partnode), with_output=True)
    if ui:
        ui.progress.clearModelessDialog()
    if rv:
        if ui:
            ui.OKDialog ("Error", "Fatal error occurred during population of secondary system image:\n\n%s\n\n" 
                         "Press any key to reboot" % output)
        return EXIT_ERROR

    ###########################################################################
    if ui:
        ui.progress.showMessageDialog("Imaging", "Initialising writable storage...")
    
    partnode = getPartitionNode(devnode, STATE_PARTITION_NUMBER)
    rv, output = util.runCmd('%s/populate-partition %s %s mutable-state 2>&1' % (scriptdir,sr_devnode, partnode), with_output=True)
    if ui:
        ui.progress.clearModelessDialog()
    if rv:
        if ui:
            ui.OKDialog ("Error", "Fatal error occurred initialising writable storage:\n\n%s\n\n" 
                         "Press any key to reboot" % output)
        return EXIT_ERROR

    ###########################################################################
    if ui:
        ui.progress.showMessageDialog("Imaging", "Initialising boot partition...")
    
    partnode = getPartitionNode(devnode, BOOT_PARTITION_NUMBER)
    rv, output = util.runCmd('%s/populate-partition %s %s boot 2>&1' % (scriptdir,sr_devnode, partnode), with_output=True)
    if ui:
        ui.progress.clearModelessDialog()
    if rv:
        if ui:
            ui.OKDialog ("Error", "Fatal error occurred initialising boot partition:\n\n%s\n\n" 
                         "Press any key to reboot" % output)
        return EXIT_ERROR

    ###########################################################################
    if ui:
        ui.progress.showMessageDialog("VM Storage", "Creating disk partition for local storage...")
    
    # Create a partition containing the remaining disk space and tell XAPI to 
    # initialise it as the Local SR on first boot
    partnode = getPartitionNode(devnode, STATE_PARTITION_NUMBER)
    rv, output = util.runCmd('%s/update-partitions %s %s %s 2>&1' % (scriptdir,devnode,sr_devnode,partnode), with_output=True)
    if ui:
        ui.progress.clearModelessDialog()
    if rv:
        if ui:
            ui.OKDialog ("Error", "Fatal error occurred during SR initialisation:\n\n%s\n\n" 
                         "Press any key to reboot" % output)
        return EXIT_ERROR

    ###########################################################################
    # update the initrds on the bootable partitions to support access to this disk
    if ui:
        ui.progress.showMessageDialog("update-initrd", "Customising startup modules...")
    for part in (SYS_1_PARTITION_NUMBER, SYS_2_PARTITION_NUMBER):
        partnode = getPartitionNode(devnode,part)
        rv, output = util.runCmd('%s/update-initrd %s 2>&1' % (scriptdir,partnode), with_output=True)
        if rv:
            break;
    if rv:
        if ui:
            ui.progress.clearModelessDialog()
            ui.OKDialog ("Error", "Fatal error occurred during customisation of startup modules:\n\n%s\n\n" 
                         "Press any key to reboot" % output)
        return EXIT_ERROR
    
    # success!
    if ui:
        ui.progress.clearModelessDialog()
        ui.OKDialog("Success", "Install complete.  Click OK to reboot")

    return EXIT_OK

# TODO answerfile support - see install.go
def go_flash(ui, args, answerfile_address):
    "Install oem edition to flash"

    xelogging.log("Starting install to flash dialog")
    answers = ui.init_oem.recover_pen_drive_sequence()
    if not answers:
        return None # keeps outer loop going

    xelogging.log("Starting install to flash write")
    devnode = answers["primary-disk"]

    rv = writeImageWithProgress(ui, devnode, answers)
    if rv == EXIT_OK:
        ui.OKDialog("Success", "Install complete.  Click OK to reboot")

    return rv



def OemManufacturerTest(ui, oem_manufacturer):
    """ Returns True if the manufacturer of this machine is the correct OEM.
    If not display an error message to user.
    """

    # get rid of outer quotes if present
    if len(oem_manufacturer) >= 2 and \
            oem_manufacturer[0] == '"' and \
            oem_manufacturer[-1] == '"':
        oem_manufacturer = oem_manufacturer[1:-1]

    rv, output = commands.getstatusoutput("dmidecode -t 1")
    lines = output.split("\n")
    
    dmiinfo = {}
    for line in lines:
        fields = line.split(":",1)
        if len(fields) is 2:
            name = fields[0].strip()
            val  = fields[1].strip()
            dmiinfo[name] = val

    # Check dmidecode returned in the format expected.  (Programmer error if not)
    if not dmiinfo.has_key("Manufacturer"):
        if ui: ui.OKDialog ("Error", "dmidecode -t 1 did not return Manufacturer info\noutput:\n%s" % output)
        return False

    # Check this machine was built by oem_manufacturer
    if dmiinfo["Manufacturer"] != oem_manufacturer:
        if ui: ui.OKDialog ("Error", "This recovery utility only runs on machines built by %s" % oem_manufacturer)
        return False

    return True
