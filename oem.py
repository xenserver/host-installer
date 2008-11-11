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
import stat
import os.path
import shutil
import time
import types

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
import md5crypt
import random
import fcntl
import backend
from pbzip2file import *

from version import *
from answerfile import AnswerfileError
from constants import EXIT_OK, EXIT_ERROR, EXIT_USER_CANCEL, OEMHDD_SYS_1_PARTITION_NUMBER, OEMHDD_SYS_2_PARTITION_NUMBER, OEMHDD_STATE_PARTITION_NUMBER, OEMHDD_SR_PARTITION_NUMBER, OEMFLASH_STATE_PARTITION_NUMBER, OEMFLASH_BOOT_PARTITION_NUMBER, INSTALL_TYPE_REINSTALL

scriptdir = os.path.dirname(sys.argv[0]) + "/oem"

def getPartitionNode(disknode, pnum):
    midfix = ""
    if re.search("/cciss/", disknode):
        midfix = "p"
    elif re.search("/disk/by-id/", disknode):
        midfix = "-part"
    return disknode + midfix + str(pnum)

def writeImageWithProgress(ui, devnode, answers):
    image_name = answers['image-name']
    image_fd    = answers['image-fd']
    if re.search(".bz2$", image_name):
        input_fd = PBZ2File(image_fd)
        # Guess compression density
        bzfilesize = int(answers['image-size'] * 1.65)
    else:
        bzfilesize = answers['image-size']
    rdbufsize = 16<<14
    reads_done = 0
    reads_needed = (bzfilesize + rdbufsize - 1)/rdbufsize # roundup

    # See if the target device node is present and wait a while
    # in case it shows up, kicking the udev trigger in the loop
    util.runCmd2(["udevsettle", "--timeout=30"])
    devnode_present = os.path.exists(devnode)
    retries = 3
    while not devnode_present:
        if not os.path.exists(devnode):
            if retries > 0:
                retries -= 1
                util.runCmd2(['udevtrigger'])
                util.runCmd2(['udevsettle', '--timeout=30'])
                time.sleep(2)
            else:
                msg = "Device node %s not present." % devnode
                xelogging.log(msg)
                if ui:
                    ui.OKDialog("Error", msg)
                image_fd.close()
                util.runCmd2(["ls", "-l", "/dev/disk/by-id"])
                return EXIT_ERROR
        else:
            devnode_present = True

    # sanity check that devnode is a block dev
    realpath = os.path.realpath(devnode) # follow if symlink
    if not os.path.exists(realpath) or not stat.S_ISBLK(os.stat(realpath)[0]):
        msg = "Error: %s is not a block device or a symlink to one!" % realpath
        xelogging.log(msg)
        if ui:
            ui.OKDialog("Error", msg)
        image_fd.close()
        util.runCmd2(["ls", "-l", "/dev/disk/by-id"])
        return EXIT_ERROR

    rdbufsize = 16<<14
    reads_done = 0

    if answers.get('install-type', None) == INSTALL_TYPE_REINSTALL:
        installation = answers['installation-to-overwrite']
        partition_info = diskutil.readPartitionInfoFromImageFD(input_fd, 1)
        rc, size = util.runCmd2(['blockdev', '--getsize64', devnode], with_stdout = True)
        if rc != 0:
            raise Exception('Indeterminate size of destination partition: '+str(size))
        else:
            if partition_info.size > size:
                raise Exception('Operation not possible - the new image in larger than the current partition size')
        bzfilesize = partition_info.size
        size_limit = partition_info.size
        input_fd.seek(partition_info.start, PBZ2File.SEEK_SET)
        xelogging.log('Writing image of size '+str(partition_info.size) + ', starting at '+str(partition_info.start) +
        ' bytes to partition '+devnode+', size '+str(size))
    else:
        size_limit = None
    reads_needed = (bzfilesize + rdbufsize - 1)/rdbufsize # roundup


    # sanity check passed - open the block device to which we want to write
    devfd = open(devnode, mode="wb")

    if ui:
        pd = ui.progress.initProgressDialog(
            "Decompressing image",
            "%(image_name)s is being written to %(devnode)s" % locals(),
            reads_needed)
        ui.progress.displayProgressDialog(0, pd)

    bytes_read = 0
    this_read_size = rdbufsize
    try:
        while True:
            if size_limit is not None:
                this_read_size = size_limit - bytes_read
            this_read_size = min(this_read_size, rdbufsize)
            if this_read_size < 0:
                break
                
            buffer = input_fd.read(this_read_size)
            bytes_read += len(buffer)
            reads_done += 1
            if not buffer:
                break
            devfd.write(buffer)
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
    else:
        image_fd.close()
        devfd.close()

    # fresh image written - need to re-read partition table 
    # (0x125F == BLKRRPART):
    devfd = open(devnode, mode="we")
    try:
        fcntl.ioctl(devfd, 0x125F)
    except IOError, e:
        # CA-23402: devfd might have been a partition and we can't tell with 
        # easily so we try the ioctl and ignore IOError exceptions, which is
        # what gets raised in this cause.
        xelogging.log("BLKRRPART failed - expected in HDD installs. Error was %s" % str(e))
        pass
    devfd.close()
    util.runCmd2(['udevsettle', '--timeout=30'])

    # image successfully written
    if ui:
        ui.progress.clearModelessDialog()

    if ui: 
        da = answers['accessor'] 
        if da.canEject():
            rv = ui.OKDialog ("Eject?", "Press OK to eject media", hasCancel = True)
            if rv in [ 'ok', None ]:
                da.eject()

    image_fd.close()
    devfd.close()

    return EXIT_OK

def run_post_install_script(answers):
    if answers.has_key('post-install-script'):
        script = answers['post-install-script']
        try:
            xelogging.log("Running script: %s" % script)
            util.fetchFile(script, "/tmp/script")
            util.runCmd2(["chmod", "a+x" ,"/tmp/script"])
            util.runCmd2(["/tmp/script"])
            os.unlink("/tmp/script")
        except Exception, e:
            xelogging.log("Failed to run script: %s" % script)
            xelogging.log(e)


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

def write_xenrt(ui, answers, partnode):
    xelogging.log("Starting write of XenRT data files")
    mountPoint = tempfile.mkdtemp('.oemxenrt')
    os.system('/bin/mkdir -p "'+mountPoint+'"')

    try:
        util.mount(partnode, mountPoint, fstype='vfat', options=['rw'])
        try:
            f = open(mountPoint + '/xenrt', "w")
            f.write(answers['xenrt'].strip())
            f.close()
            if answers.has_key('xenrt-scorch'):
                f = open(mountPoint + '/xenrt-revert-to-factory', 'w')
                f.write('yesimeanit')
                f.close()
            if answers.has_key('xenrt-serial'):
                serport = int(answers['xenrt-serial'])
                f = open(mountPoint + '/linux.opt', 'w')
                f.write('console=ttyS%u,115200n8' % (serport))
                f.close()
                f = open(mountPoint + '/xen.opt', 'w')
                f.write('com%u=115200,8n1 console=com%u,tty' % (serport+1, serport+1))
                f.close()
        finally:
            util.umount(partnode)
            os.system('/bin/rmdir "'+mountPoint+'"')
    except Exception, e:
        if ui:
            ui.OKDialog("Failed", str(e))
        xelogging.log("Failure: " + str(e))
        return EXIT_ERROR
    xelogging.log("Wrote XenRT data files")

def go_disk(ui, args, answerfile_address, custom):
    "Install oem edition to disk"

    # loading an answerfile?
    assert ui != None or answerfile_address != None

    if answerfile_address:
        answers = answerfile.processAnswerfile(answerfile_address)
        post_process_answerfile_data(answers)

    else:
        xelogging.log("Starting install to disk dialog")
        if ui:
            answers = ui.init_oem.recover_disk_drive_sequence(ui, custom)
        if not answers:
            return None # keeps outer loop going

    xelogging.log("Starting install to disk, partitioning")
    answers['operation'] = init_constants.OPERATION_INSTALL_OEM_TO_DISK

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
                     OEMHDD_SYS_1_PARTITION_NUMBER, OEMHDD_SYS_2_PARTITION_NUMBER,
                     OEMHDD_STATE_PARTITION_NUMBER, OEMHDD_SR_PARTITION_NUMBER):
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

    sr_devnode = getPartitionNode(devnode, OEMHDD_SR_PARTITION_NUMBER)
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
    
    partnode = getPartitionNode(devnode, OEMHDD_SYS_1_PARTITION_NUMBER)

    if answers.has_key("rootfs-writable") or os.path.exists("/opt/xensource/rw"):
        write_op = "system-image-1-rw"
    else:
        write_op = "system-image-1"

    rv, output = util.runCmd('%s/populate-partition %s %s %s 2>&1' % (scriptdir,sr_devnode, partnode, write_op), with_output=True)
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
    
    partnode = getPartitionNode(devnode, OEMHDD_SYS_2_PARTITION_NUMBER)

    if answers.has_key("rootfs-writable") or os.path.exists("/opt/xensource/rw"):
        write_op = "system-image-2-rw"
    else:
        write_op = "system-image-2"

    rv, output = util.runCmd('%s/populate-partition %s %s %s 2>&1' % (scriptdir,sr_devnode, partnode, write_op), with_output=True)
    if ui:
        ui.progress.clearModelessDialog()
    if rv:
        if ui:
            ui.OKDialog ("Error", "Fatal error occurred during population of secondary system image:\n\n%s\n\n" 
                         "Press any key to reboot" % output)
        return EXIT_ERROR

    ###########################################################################
    if ui:
        ui.progress.showMessageDialog("Imaging", "Initializing writable storage...")
    
    partnode = getPartitionNode(devnode, OEMHDD_STATE_PARTITION_NUMBER)
    rv, output = util.runCmd('%s/populate-partition %s %s mutable-state 2>&1' % (scriptdir,sr_devnode, partnode), with_output=True)
    if ui:
        ui.progress.clearModelessDialog()
    if rv:
        if ui:
            ui.OKDialog ("Error", "Fatal error occurred initializing writable storage:\n\n%s\n\n" 
                         "Press any key to reboot" % output)
        return EXIT_ERROR

    ###########################################################################
    if ui:
        ui.progress.showMessageDialog("Imaging", "Initializing boot partition...")
    
    partnode = getPartitionNode(devnode, BOOT_PARTITION_NUMBER)
    rv, output = util.runCmd('%s/populate-partition %s %s boot 2>&1' % (scriptdir,sr_devnode, partnode), with_output=True)
    if ui:
        ui.progress.clearModelessDialog()
    if rv:
        if ui:
            ui.OKDialog ("Error", "Fatal error occurred initializing boot partition:\n\n%s\n\n" 
                         "Press any key to reboot" % output)
        return EXIT_ERROR

    ###########################################################################
    if ui:
        ui.progress.showMessageDialog("Configuration Files", "Writing configuration files...")

    try:
        write_oem_firstboot_files(answers)
    except Exception, e:
        message =  "Fatal error occurred:\n\n%s\n\nPress any key to reboot" % str(e)
        xelogging.log(message)
        if ui:
            ui.progress.clearModelessDialog()
            ui.OKDialog ("Error", message)
        return EXIT_ERROR

    if ui:
        ui.progress.clearModelessDialog()

    ###########################################################################
    # update the initrds on the bootable partitions to support access to this disk
    if ui:
        ui.progress.showMessageDialog("update-initrd", "Customizing startup modules...")
    for part in (OEMHDD_SYS_1_PARTITION_NUMBER, OEMHDD_SYS_2_PARTITION_NUMBER):
        partnode = getPartitionNode(devnode,part)
        rv, output = util.runCmd('%s/update-initrd %s 2>&1' % (scriptdir,partnode), with_output=True)
        if rv:
            break;
    if rv:
        if ui:
            ui.progress.clearModelessDialog()
            ui.OKDialog ("Error", "Fatal error occurred during customization of startup modules:\n\n%s\n\n" 
                         "Press any key to reboot" % output)
        return EXIT_ERROR
    
    ###########################################################################
    if answers.has_key("xenrt"):
        partnode = getPartitionNode(devnode, BOOT_PARTITION_NUMBER)
        write_xenrt(ui, answers, partnode)

    run_post_install_script(answers)

    # success!
    if ui:
        ui.progress.clearModelessDialog()
        if answerfile_address:
            ui.progress.showMessageDialog("Success", "Install complete - rebooting")
            time.sleep(2)
            ui.progress.clearModelessDialog()
        else:
            ui.OKDialog("Success", "Install complete.  Click OK to reboot")

    return EXIT_OK

def go_flash(ui, args, answerfile_address, custom):
    "Install oem edition to flash"

    # loading an answerfile?
    assert ui != None or answerfile_address != None

    if answerfile_address:
        answers = answerfile.processAnswerfile(answerfile_address)
        post_process_answerfile_data(answers)

    else:
        xelogging.log("Starting install to flash dialog")
        answers = ui.init_oem.recover_pen_drive_sequence(ui, custom)
        if not answers:
            return None # keeps outer loop going

    xelogging.log("Starting install to flash write")
    answers['operation'] = init_constants.OPERATION_INSTALL_OEM_TO_FLASH

    if answers.get('install-type', None) == INSTALL_TYPE_REINSTALL:
        devnode = answers['installation-to-overwrite'].root_partition
    else:
        devnode = answers["primary-disk"]

    rv = writeImageWithProgress(ui, devnode, answers)
    if rv != EXIT_OK:
        return rv


    if ui:
        ui.progress.showMessageDialog("Configuration Files", "Writing configuration files...")

    try:
        write_oem_firstboot_files(answers)
    except Exception, e:
        message =  "Fatal error occurred:\n\n%s\n\nPress any key to reboot" % str(e)
        xelogging.log(message)
        if ui:
            ui.progress.clearModelessDialog()
            ui.OKDialog ("Error", message)
        return EXIT_ERROR

    if ui:
        ui.progress.clearModelessDialog()

    if answers.has_key("xenrt"):
        partnode = getPartitionNode(devnode, OEMFLASH_BOOT_PARTITION_NUMBER)
        write_xenrt(ui, answers, partnode)

    run_post_install_script(answers)
    
    if ui:
        if answerfile_address:
            ui.progress.showMessageDialog("Success", "Install complete - rebooting")
            time.sleep(2)
            ui.progress.clearModelessDialog()
        else:
            ui.OKDialog("Success", "Install complete.  Click OK to reboot")

    return EXIT_OK

def write_oem_firstboot_files(answers):
    # Create a partition containing the remaining disk space and tell XAPI to 
    # initialise it as the Local SR on first boot
    operation = answers['operation']
    is_hdd = init_constants.operationIsOEMHDDInstall(operation)
    if is_hdd:
        partnode = getPartitionNode(answers['primary-disk'], OEMHDD_STATE_PARTITION_NUMBER)
    else:
        partnode = getPartitionNode(answers['primary-disk'], OEMFLASH_STATE_PARTITION_NUMBER)
        
    mntpoint = tempfile.mkdtemp(dir = '/tmp', prefix = 'oem-state-partition-')
    try:
        util.mount(partnode, mntpoint)
        try:
            mounts = {'state': mntpoint}

            if is_hdd:
                backend.prepareStorageRepositories(operation, mounts, answers['primary-disk'], answers['guest-disks'], answers['sr-type'])
        
            nameserver_IPs = []
            man_ns = answers.get('manual-nameservers', [False])
            if man_ns[0]:
                nameserver_IPs = man_ns[1]
                
            hostname = ''
            man_hostname = answers.get('manual-hostname', [False])
            if man_hostname[0]:
                hostname = man_hostname[1]
            
            # prepareNetworking replaces scripts otherwise generated by firstboot.d/nn-detect-nics,
            # so only call it if an interface is configured
            if 'net-admin-interface' in answers:
                backend.prepareNetworking(operation, mounts,
                    answers.get('net-admin-interface', ''), answers.get('net-admin-configuration', None),
                    nameserver_IPs, answers.get('network-hardware', {}))
            if 'root-password' in answers:
                backend.preparePassword(operation, mounts, password_hash(answers.get('root-password', '!!')))
            backend.prepareHostname(operation, mounts, hostname)
            backend.prepareNTP(operation, mounts,
                answers.get('time-config-method', '').lower(), answers.get('ntp-servers', []))
            backend.prepareTimezone(operation, mounts, answers.get('timezone', ''))
        finally:
            util.umount(mntpoint)
    finally:
        os.rmdir(mntpoint)

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

def password_hash(password):
    if password == '!!':
        retval = password # xsconsole will prompt for a new password when it detects this value
    else:
        # Generate a salt value without sed special characters
        salt = "".join(random.sample('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz', 8))
        retval = md5crypt.md5crypt(password, '$1$'+salt+'$')
    return retval

def direct_set_password(password, mountPoint):
    xelogging.log('Setting password in '+mountPoint)
    passwordHash = password_hash(password)
    # sed command replaces the root password entry in /etc/passwd
    sedCommand = '/bin/sed -ie \'s#^root:[^:]*#root:' + passwordHash +'#\' "' + mountPoint+'/etc/passwd"'

    xelogging.log("Executing "+sedCommand)
    if os.system(sedCommand) != 0:
        raise Exception('Password file manipulation failed')

def reset_password(ui, args, answerfile_address):
    xelogging.log("Starting reset password")
    answers = ui.init_oem.reset_password_sequence()
    if not answers:
        return None # keeps outer loop going

    xelogging.log("Resetting password on "+str(answers['partition']))

    password = answers['new-password']
    partition, subdir = answers['partition']
    mountPoint = tempfile.mkdtemp('.oeminstaller')
    os.system('/bin/mkdir -p "'+mountPoint+'"')

    partition_dev = '/dev/' + partition.replace("!", "/")
    try:
        util.mount(partition_dev, mountPoint, fstype='ext3', options=['rw'])
        try:
            direct_set_password(password, mountPoint+'/'+subdir)
        finally:
            util.umount(partition_dev)
    except Exception, e:
        ui.OKDialog("Failed", str(e))
        return EXIT_ERROR

    ui.OKDialog("Success", "The password has been reset successfully.  Press <Enter> to reboot.")
    return EXIT_OK
