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
import install
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

def writeDataWithProgress(ui, filename, answers, is_devnode):
    image_name = answers['image-name']
    image_fd    = answers['image-fd']
    if re.search(".bz2$", image_name):
        input_fd = PBZ2File(image_fd)
        # Guess compression density
        bzfilesize = int(answers['image-size'] * 1.65)
    else:
        input_fd = image_fd
        bzfilesize = answers['image-size']

    if answers.get('install-type', None) == INSTALL_TYPE_REINSTALL:
        installation = answers['installation-to-overwrite']
        partition_info = diskutil.readPartitionInfoFromImageFD(input_fd, 1)
        xelogging.log('Writing image of size '+str(partition_info.size) + ', starting at '+str(partition_info.start) +
        ' bytes to '+filename)
        if is_devnode:
            rc, size = util.runCmd2(['blockdev', '--getsize64', filename], with_stdout = True)
            if rc != 0:
                raise Exception('Indeterminate size of destination partition: '+str(size))
            elif partition_info.size > int(size):
                raise Exception('Operation not possible - the new image is larger than the current partition size')
            xelogging.log('Target partition size is '+str(size))

        bzfilesize = partition_info.size
        size_limit = partition_info.size
        input_fd.seek(partition_info.start, PBZ2File.SEEK_SET)
    else:
        size_limit = None

    rdbufsize = 16<<14
    reads_done = 0
    reads_needed = (bzfilesize + rdbufsize - 1) / rdbufsize # Round up
    bytes_read = 0
    this_read_size = rdbufsize

    if ui:
        pd = ui.progress.initProgressDialog(
            "Decompressing image",
            "%(image_name)s is being written to %(filename)s" % locals(),
            reads_needed)
        ui.progress.displayProgressDialog(0, pd)

    devfd = open(filename, mode="wb")
    try:
        try:
            while True:
                if size_limit is not None:
                    this_read_size = size_limit - bytes_read
                this_read_size = min(this_read_size, rdbufsize)
                if this_read_size <= 0:
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
            # Change exception wording for user, and log the original
            xelogging.log_exception(e)
            raise Exception("Fatal error occurred during write.  Press any key to reboot")
    finally:
        devfd.close()
    if ui:
        ui.progress.clearModelessDialog()

def writeImageWithProgress(ui, devnode, answers):
    # in case it shows up, kicking the udev trigger in the loop
    util.runCmd2(["udevsettle", "--timeout=45"])
    devnode_present = os.path.exists(devnode)
    retries = 3
    while not devnode_present:
        if not os.path.exists(devnode):
            if retries > 0:
                retries -= 1
                util.runCmd2(['udevtrigger'])
                util.runCmd2(['udevsettle', '--timeout=45'])
                time.sleep(2)
            else:
                msg = "Device node %s not present." % devnode
                xelogging.log(msg)
                if ui:
                    ui.OKDialog("Error", msg)
                util.runCmd2(["ls", "-l", "/dev/disk/by-id"])
                raise Exception(msg)
        else:
            devnode_present = True

    # sanity check that devnode is a block dev
    realpath = os.path.realpath(devnode) # follow if symlink
    if not os.path.exists(realpath) or not stat.S_ISBLK(os.stat(realpath)[0]):
        msg = "Error: %s is not a block device or a symlink to one!" % realpath
        xelogging.log(msg)
        util.runCmd2(["ls", "-l", "/dev/disk/by-id"])
        raise Exception(msg)

    writeDataWithProgress(ui, devnode, answers, is_devnode = True)

    # fresh image written - need to re-read partition table 
    # (0x125F == BLKRRPART):
    devfd = open(devnode, mode="we")
    try:
        fcntl.ioctl(devfd, 0x125F)
    except IOError, e:
        # CA-23402: devfd might have been a partition and we can't tell with 
        # easily so we try the ioctl and ignore IOError exceptions, which is
        # what gets raised in this cause.
        xelogging.log("BLKRRPART failed - expected in reinstalls and HDD installs. Error was %s" % str(e))
    devfd.close()
    util.runCmd2(['udevsettle', '--timeout=45'])

def offer_to_eject(ui, answers):
    if ui: 
        da = answers['accessor'] 
        if da.canEject():
            rv = ui.OKDialog ("Eject?", "Press OK to eject media", hasCancel = True)
            if rv in [ 'ok', None ]:
                try:
                    da.eject()
                except:
                    pass # Ignore failure

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
        install.handle_install_failure(answers)
        return EXIT_ERROR
    xelogging.log("Wrote XenRT data files")

def hdd_create_disk_partitions(ui, devnode):
    rv, output = util.runCmd('%s/create-partitions %s 2>&1' % (scriptdir,devnode), with_output=True)
    if rv != 0:
        raise Exception(output)
    
def hdd_boot_partition_number(devnode):
    # Lookup the boot partition number
    rv, output = util.runCmd('/sbin/fdisk -l %s 2>&1 | /bin/sed -ne \'s,^%sp\\?\\([1-4]\\)  *\\*.*$,\\1,p\' 2>&1' % (devnode, devnode), with_output=True)
    if rv != 0:
        raise Exception(output)
    return int(output)    

def hdd_verify_partition_nodes(devnode): 
    xelogging.log("Ensuring that the device nodes for the new partitions are available")
    all_devnodes_present = False
    retries = 5
    while not all_devnodes_present:
        for pnum in (hdd_boot_partition_number(devnode),
                OEMHDD_SYS_1_PARTITION_NUMBER, OEMHDD_SYS_2_PARTITION_NUMBER,
                OEMHDD_STATE_PARTITION_NUMBER, OEMHDD_SR_PARTITION_NUMBER):
            p_devnode = getPartitionNode(devnode, pnum)
            if not os.path.exists(p_devnode):
                if retries > 0:
                    retries -= 1
                    time.sleep(1)
                    break
                else:
                    raise Exception("Partition device nodes failed to appear")

        else: # This else belongs to the for statement
            all_devnodes_present = True

def hdd_install_mbr(sr_devnode, devnode):
        rv, output = util.runCmd('%s/populate-partition %s %s master-boot-record 2>&1' % (scriptdir,sr_devnode, devnode), with_output=True)
        if rv != 0:
            raise Exception(output)

def hdd_write_root_partition(sr_devnode, partition_node, image_number, writeable):
    xelogging.log("Populating system partition "+partition_node)

    if writeable:
        write_op = "system-image-"+str(image_number)+"-rw"
    else:
        write_op = "system-image-"+str(image_number)

    rv, output = util.runCmd('%s/populate-partition %s %s %s 2>&1' % (scriptdir, sr_devnode, partition_node, write_op),
        with_output=True)
    if rv != 0:
        raise Exception(output)

def hdd_write_state_partition(sr_devnode, partition_node):
    rv, output = util.runCmd('%s/populate-partition %s %s mutable-state 2>&1' % (scriptdir, sr_devnode, partition_node),
        with_output=True)
    if rv != 0:
        raise Exception(output)

def hdd_write_boot_partition(sr_devnode, partition_node):
    rv, output = util.runCmd('%s/populate-partition %s %s boot 2>&1' % (scriptdir, sr_devnode, partition_node),
        with_output=True)
    if rv != 0:
        raise Exception(output)

def hdd_update_initrd(partition_node):
    rv, output = util.runCmd('%s/update-initrd %s 2>&1' % (scriptdir, partition_node), with_output=True)
    if rv != 0:
        raise Exception(output)

def wrap_ui_info(ui, info, function, title = None):
    if ui:
        ui.progress.showMessageDialog(title or "Installing", info)
    xelogging.log(info)
    try:
        function()
    finally:
        if ui:
            ui.progress.clearModelessDialog()

def hdd_install_writeable_root_partition(ui, partition_node, image_number, answers):
    temp_file = tempfile.mkstemp('-rootPart.fs')[1]
    try:
        writeDataWithProgress(ui, temp_file, answers, is_devnode = False)
        hdd_write_root_partition(temp_file, partition_node, 0, writeable = True)
    finally:
        os.remove(temp_file)

def go_disk(ui, args, answerfile_address, custom):
    "Install oem edition to disk"

    # loading an answerfile?
    assert ui != None or answerfile_address != None

    if answerfile_address:
        answers = answerfile.Answerfile(answerfile_address).processAnswerfile()
        post_process_answerfile_data(answers)

    else:
        xelogging.log("Starting install to disk dialog")
        if ui:
            answers = ui.init_oem.recover_disk_drive_sequence(ui, custom)
        if not answers:
            return None # keeps outer loop going

    xelogging.log("Starting install to disk, partitioning")
    answers['operation'] = init_constants.OPERATION_INSTALL_OEM_TO_DISK

    reinstall = ( answers.get('install-type', None) == INSTALL_TYPE_REINSTALL )


    # The boot partition is a primary FAT16 partition with a well-known label.
    # The extended partition contains:
    #   p5: system image 1
    #   p6: system image 2
    #   p7: writable state
    #   p8: local SR

    try:
        writeable = (answers.has_key("rootfs-writable") or os.path.exists("/opt/xensource/rw"))
        if reinstall:
            # Reinstall writes a single partition from the image to the target partition directly,
            # so root_partition is typically /dev/sda5 or /dev/sda6
            reinstall_node = answers['installation-to-overwrite'].root_partition
            if writeable:
                # Always write the first root partition from the image
                wrap_ui_info(ui, 'Installing system image ...',
                    lambda: hdd_install_writeable_root_partition(ui, reinstall_node, 1, answers))
            else:
                writeImageWithProgress(ui, reinstall_node, answers)
            wrap_ui_info(ui, 'Customizing startup modules ...', lambda: hdd_update_initrd(reinstall_node))
        else:
            devnode = answers["primary-disk"]
            # Full install first decompresses the entire image into the partition that's going
            # to be used as an SR in the final configuration. 
            wrap_ui_info(ui, 'Creating system image disk partitions ...',
                lambda: hdd_create_disk_partitions(ui, devnode))
            hdd_verify_partition_nodes(devnode)
            sr_devnode = getPartitionNode(devnode, OEMHDD_SR_PARTITION_NUMBER)
            writeImageWithProgress(ui, sr_devnode, answers)
            wrap_ui_info(ui, 'Installing the master boot record ...', lambda: hdd_install_mbr(sr_devnode, devnode))

            wrap_ui_info(ui, 'Installing primary system image ...',
                lambda: hdd_write_root_partition(sr_devnode, getPartitionNode(devnode, OEMHDD_SYS_1_PARTITION_NUMBER), 1, writeable))
            wrap_ui_info(ui, 'Installing secondary system image ...',
                lambda: hdd_write_root_partition(sr_devnode, getPartitionNode(devnode, OEMHDD_SYS_2_PARTITION_NUMBER), 2, writeable))
            wrap_ui_info(ui, 'Initializing storage for configuration information ...',
                lambda: hdd_write_state_partition(sr_devnode, getPartitionNode(devnode, OEMHDD_STATE_PARTITION_NUMBER)))
            wrap_ui_info(ui, 'Installing boot image ...',
                lambda: hdd_write_boot_partition(sr_devnode, getPartitionNode(devnode, hdd_boot_partition_number(devnode))))
            write_oem_firstboot_files(answers) # Completes quickly so no banner
            wrap_ui_info(ui, 'Customizing startup modules ...',
                lambda: hdd_update_initrd(getPartitionNode(devnode, OEMHDD_SYS_1_PARTITION_NUMBER)))
            wrap_ui_info(ui, 'Customizing startup modules ...',
                lambda: hdd_update_initrd(getPartitionNode(devnode, OEMHDD_SYS_2_PARTITION_NUMBER)))
            if answers.has_key("xenrt"):
                wrap_ui_info(ui, 'Writing XenRT information ...',
                    lambda: write_xenrt(ui, answers, getPartitionNode(devnode, hdd_boot_partition_number(devnode))))
            wrap_ui_info(ui, 'Finalizing installation ...',
                lambda: run_post_install_script(answers))
    except Exception, e:
        xelogging.log_exception(e)
        if ui:
            ui.OKDialog ("Error", "Fatal error occurred:\n\n%s\n\nPress any key to reboot" % str(e))
        install.handle_install_failure(answers)
        return EXIT_ERROR

    run_post_install_script(answers)

    answers['image-fd'].close() #  Must close file before ejecting

    if ui:
        if answerfile_address:
            ui.progress.showMessageDialog("Success", "Install complete - rebooting")
            time.sleep(2)
            ui.progress.clearModelessDialog()
        else:
            offer_to_eject(ui, answers)
            ui.OKDialog("Success", "Install complete.  Click OK to reboot")



    return EXIT_OK

def go_flash(ui, args, answerfile_address, custom):
    "Install oem edition to flash"

    # loading an answerfile?
    assert ui != None or answerfile_address != None

    if answerfile_address:
        answers = answerfile.Answerfile(answerfile_address).processAnswerfile()
        post_process_answerfile_data(answers)

    else:
        xelogging.log("Starting install to flash dialog")
        answers = ui.init_oem.recover_pen_drive_sequence(ui, custom)
        if not answers:
            return None # keeps outer loop going

    xelogging.log("Starting install to flash write")
    answers['operation'] = init_constants.OPERATION_INSTALL_OEM_TO_FLASH

    reinstall = (answers.get('install-type', None) == INSTALL_TYPE_REINSTALL)
    if reinstall:
        devnode = answers['installation-to-overwrite'].root_partition
    else:
        devnode = answers["primary-disk"]

    try:
        writeImageWithProgress(ui, devnode, answers)
        if not reinstall:
            write_oem_firstboot_files(answers)
    except Exception, e:
        message =  "Fatal error occurred:\n\n%s\n\nPress any key to reboot" % str(e)
        xelogging.log(message)
        if ui:
            ui.OKDialog ("Error", message)
            
        install.handle_install_failure(answers)
        return EXIT_ERROR

    if answers.has_key("xenrt"):
        partnode = getPartitionNode(devnode, OEMFLASH_BOOT_PARTITION_NUMBER)
        wrap_ui_info(ui, 'Writing XenRT information ...', lambda: write_xenrt(ui, answers, partnode))

    wrap_ui_info(ui, 'Finalizing installation ...', lambda: run_post_install_script(answers))

    answers['image-fd'].close() # Must close file before ejecting

    if ui:
        if answerfile_address:
            ui.progress.showMessageDialog("Success", "Install complete - rebooting")
            time.sleep(2)
            ui.progress.clearModelessDialog()
        else:
            offer_to_eject(ui, answers)
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

def reset_state_partition(ui, args, answerfile_address):
    xelogging.log("Starting reset state partition")
    answers = ui.init_oem.reset_state_partition_sequence()
    if not answers:
        return None # keeps outer loop going
    partition, subdir = answers['partition']
    xelogging.log("Resetting state partition on "+partition)

    mount_point = tempfile.mkdtemp('.oeminstaller')
    partition_dev = '/dev/' + partition.replace("!", "/")
    # Preserve the data directory so that the local SR is recreated
    preserve_path = mount_point+'/installer/etc/firstboot.d/data'
    try:
        util.mount(partition_dev, mount_point, fstype='ext3', options=['rw'])
        try:
            for root, dirs, files in os.walk(mount_point, topdown=False):
                if not root.startswith(preserve_path):
                    # Remove all files not in the preserved directory
                    for name in files:
                        os.remove(os.path.join(root, name))
                    for name in dirs:
                        dir_name = os.path.join(root, name)
                        if not preserve_path.startswith(dir_name):
                            # Remove all directories not in the full path of the preserved directory
                            if os.path.islink(dir_name):
                                os.remove(dir_name)
                            else:
                                os.rmdir(dir_name)

        finally:
            util.umount(partition_dev)
    except Exception, e:
        xelogging.log_exception(e)
        ui.OKDialog("Failed", str(e))
        return EXIT_ERROR

    ui.OKDialog("Success", "The installation has been reset to factory defaults.  Press <Enter> to reboot.")
    return  EXIT_OK
    
