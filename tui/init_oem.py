# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# 'Init' text user interface
#
# written by Andrew Peace

from snack import *
from version import *

import tui
import init_constants
import generalui
import uicontroller
from uicontroller import LEFT_BACKWARDS, RIGHT_FORWARDS, REPEAT_STEP
import tui.network
import repository
import snackutil
import os
import os.path
import stat
import diskutil
import util
import glob
import re
import tempfile
import constants

def get_keymap():
    entries = generalui.getKeymaps()

    (button, entry) = ListboxChoiceWindow(
        tui.screen,
        "Select Keymap",
        "Please select the keymap you would like to use:",
        entries,
        ['Ok'], height = 8, scroll = 1)

    return entry

def choose_operation(menu_option):
    entries = [ 
        (' * Install %s to flash disk' % BRAND_SERVER, init_constants.OPERATION_INSTALL_OEM_TO_FLASH),
        (' * Install %s to hard disk' % BRAND_SERVER, init_constants.OPERATION_INSTALL_OEM_TO_DISK),
        (' * Reset the password for an existing installation', init_constants.OPERATION_RESET_PASSWORD)
        ]

    # Menu options: all, none, hdd, flash
    if menu_option = "none":
        del entries[0:2]
    if menu_option = "hdd":
        del entries[0]
    if menu_option = "flash":
        del entries[1]
    # Nothing to do for 'all'. 'all' is default.

    (button, entry) = ListboxChoiceWindow(tui.screen,
                                          "Welcome to %s" % PRODUCT_BRAND,
                                          """Please select an operation:""",
                                          entries,
                                          ['Ok', 'Exit and reboot'], width=70)

    if button == 'ok' or button == None:
        return entry
    else:
        return -1

# Set of questions to pose if install "to flash disk" is chosen
def recover_pen_drive_sequence():
    answers = {}
    uic = uicontroller
    seq = [
        uic.Step(get_flash_blockdev_to_recover),
        uic.Step(get_image_media),
        uic.Step(get_remote_file, predicates = [lambda a: a['source-media'] != 'local']),
        uic.Step(get_local_file,  predicates = [lambda a: a['source-media'] == 'local']),
        uic.Step(confirm_recover_blockdev),
        ]
    rc = uicontroller.runSequence(seq, answers)

    if rc == -1:
        return None
    else:
        return answers


# Set of questions to pose if install "to hard disk" is chosen
def recover_disk_drive_sequence():
    answers = {}
    uic = uicontroller
    seq = [
        uic.Step(get_disk_blockdev_to_recover),
        uic.Step(get_image_media),
        uic.Step(get_remote_file, predicates = [lambda a: a['source-media'] != 'local']),
        uic.Step(get_local_file,  predicates = [lambda a: a['source-media'] == 'local']),
        uic.Step(confirm_recover_blockdev),
        ]
    rc = uicontroller.runSequence(seq, answers)

    if rc == -1:
        return None
    else:
        return answers

# Set of questions to pose if "reset password" is chosen
def reset_password_sequence():
    answers = {}
    uic = uicontroller
    seq = [
        uic.Step(get_installation_blockdev),
        uic.Step(get_state_partition),
        uic.Step(get_new_password),
        uic.Step(confirm_reset_password)
        ]
    rc = uicontroller.runSequence(seq, answers)

    if rc == -1:
        return None
    else:
        return answers

# Offer a list of block devices to the user
def get_blockdev_to_recover(answers, flashonly, alreadyinstalled = False):

    TYPE_ROM = 5
    def device_type(dev):
        try:
            return int(open("/sys/block/%s/device/type" % dev).read())
        except:
            return None

    # create a list of the disks to offer
    if flashonly:
        disks = [ dev for dev in diskutil.getRemovableDeviceList() if device_type(dev) not in [None, TYPE_ROM] ]
    else:
        disks = diskutil.getDiskList()

    # Create list of (comment,device) tuples for listbox
    entries = [ ("%s %s %d MB" % diskutil.getExtendedDiskInfo(dev,inMb=1), dev) for dev in disks ]

    if entries:
        result, entry = ListboxChoiceWindow(
            tui.screen,
            flashonly and "Select removable device" or "Select drive",
            alreadyinstalled and "Please select the device containing the installed software:" or "Please select on which device you would like to install:",
            entries, ['Ok', 'Back', 'Rescan'])
    else:
        result = ButtonChoiceWindow(
            tui.screen, "No drives found",
            flashonly and "No writable and removable drives were discovered" or "No hard drives found",
            ['Rescan','Back'])
        if result in [None, 'rescan']: return REPEAT_STEP
        if result == 'back':           return LEFT_BACKWARDS

    answers['primary-disk'] = "/dev/" + entry
    if result in [None, 'ok']: return RIGHT_FORWARDS
    if result == 'back':       return LEFT_BACKWARDS
    if result == 'rescan':     return REPEAT_STEP

def get_flash_blockdev_to_recover(answers):
    rv = get_blockdev_to_recover(answers, flashonly=True)

    # Placeholders the future.  Not currently used when installing to flash.
    answers['guest-disks'] = [ ]
    answers['sr-type'] = constants.SR_TYPE_LVM

    return rv

def get_disk_blockdev_to_recover(answers):
    rv = get_blockdev_to_recover(answers, flashonly=False)

    # always claim remainder of primary disk for local storage, and no other disks.
    answers['guest-disks'] = [ answers['primary-disk'] ]
    answers['sr-type'] = constants.SR_TYPE_LVM
    
    return rv

def get_installation_blockdev(answers):
    return get_blockdev_to_recover(answers, flashonly=False, alreadyinstalled=True)

def get_image_media(answers):
    entries = [
        ('Removable media', 'local'),
        ('HTTP or FTP', 'url'),
        ('NFS', 'nfs')
        ]
    result, entry = ListboxChoiceWindow(
        tui.screen,
        "Image media",
        "Please select where you would like to load image from:",
        entries, ['Ok', 'Back'])

    answers['source-media'] = entry

    if result in ['ok', None]: return RIGHT_FORWARDS
    if result == 'back': return LEFT_BACKWARDS

def get_remote_file(answers):

    # Bring up networking first
    if tui.network.requireNetworking(answers) != 1:
        return LEFT_BACKWARDS

    if answers['source-media'] == 'url':
        text = "Please enter the URL for your HTTP or FTP image"
        label = "URL:"
    elif answers['source-media'] == 'nfs':
        text = "Please enter the server and path of your NFS share (e.g. myserver:/path/to/file)"
        label = "NFS Path:"
        
    if answers.has_key('source-address'):
        default = answers['source-address']
    else:
        default = ""

    found_file = False
    while found_file == False:

        (button, result) = EntryWindow(
            tui.screen,
            "Specify image",
            text,
            [(label, default)], entryWidth = 50,
            buttons = ['Ok', 'Back'])
            
        if button == 'back':
            return LEFT_BACKWARDS

        dirname   = os.path.dirname(result[0])
        basename  = os.path.basename(result[0])

        if answers['source-media'] == 'nfs':
            accessor  = repository.NFSAccessor(dirname)
        else:
            accessor  = repository.URLAccessor(dirname)

        try:
            accessor.start()
        except:
            ButtonChoiceWindow(
                tui.screen, "Directory inaccessible",
                """Unable to access directory.  Please check the address was valid and try again""",
                ['Back'])
            continue

        if not accessor.access(basename):
            ButtonChoiceWindow(
                tui.screen, "Image not found",
                """The image was not found at the location specified.  Please check the file name was valid and try again""",
                ['Back'])
            accessor.finish()
            continue

        try:
            answers['image-fd'] = accessor.openAddress(basename)
        except:
            ButtonChoiceWindow(
                tui.screen, "File inaccessible",
                """Unable to access file.  Please check the file permissions""",
                ['Back'])
            continue

        answers['image-name'] = basename
        answers['accessor'] = accessor    # This is just a way of stopping GC on this object
        
        # Success!
        found_file = True

    if answers['source-media'] == 'nfs':
        fullpath = os.path.join(accessor.location, basename)
        answers['image-size'] = os.stat(fullpath).st_size
    else:
        answers['image-size'] = 900000000 # A GUESS!

    return RIGHT_FORWARDS
 
def get_local_file(answers):

    # build dalist, a list of accessor objects to mounted CDs and USB partitions
    dev2write = answers["primary-disk"][5:] # strip the 5-char "/dev/" off
    removable_devs = diskutil.getRemovableDeviceList()
    if dev2write in removable_devs: removable_devs.remove(dev2write)
    dalist = []

    removable_devs_and_ptns = []
    for check in removable_devs:
        # if check doesn't end in a numeral, it may have partitions
        # that need to be scanned
        if check[-1] < '0' or check[-1] > '9':
            files = os.listdir('/dev')
            for ptn in filter( lambda x : x[:len(check)] == check, files):
                removable_devs_and_ptns.append(ptn)
        else:
            removable_devs_and_ptns.append(check)

    for check in removable_devs_and_ptns:
        device_path = "/dev/%s" % check
        if not os.path.exists(device_path):
            # Device path doesn't exist (maybe udev renamed it).  Create it now.
            major, minor = map(int, open('/sys/block/%s/dev' % check).read().split(':'))
            os.mknod(device_path, 0600|stat.S_IFBLK, os.makedev(major,minor))
        da = repository.DeviceAccessor(device_path)
        try:
            da.start()
        except util.MountFailureException:
            pass
        else:
            dalist.append(da)

    # build list for entry box.  Displayed value is the file name
    entries = []
    for da in dalist:
        mountpoint = da.location
        files = os.listdir(mountpoint)
        entries.extend([ ("%s (%s)" % (f,da.mount_source), (f,da)) for f in files if f.startswith("oem-") and f.endswith(".img.bz2") ])

    if entries:
        # Create list of (comment,device) tuples for listbox
        vendor, model, _ = diskutil.getExtendedDiskInfo(dev2write)
        result, entry = ListboxChoiceWindow(
            tui.screen,
            "Select Image",
            "Please select which image you would like to copy to \"%(vendor)s, %(model)s\":" % locals(),
            entries, ['Ok', 'Back'])
        if result == 'back': return LEFT_BACKWARDS * 2
    else: 
        ButtonChoiceWindow(
            tui.screen, "No images found",
            "No images were found in any CD/DVD drives",
            ['Back'])
        return LEFT_BACKWARDS * 2

    filename = entry[0]
    da       = entry[1]
    fullpath = os.path.join(da.location, filename)

    answers['image-fd'] = open(fullpath, "rb")
    answers['image-name'] = filename
    answers['image-size'] = os.stat(fullpath).st_size
    answers['accessor'] = da    # This is just a way of stopping GC on this object

    return RIGHT_FORWARDS

def confirm_recover_blockdev(answers):
    dev = answers["primary-disk"][5:] # strip the 5-char "/dev/" off
    vendor, model, _ = diskutil.getExtendedDiskInfo(dev)
    rc = snackutil.ButtonChoiceWindowEx(
        tui.screen,
        "Confirm Install/Recover",
        "Are you sure you want to write to device \"%(vendor)s, %(model)s\"\n\nAny existing installation will be overwritten\n\nTHIS OPERATION CANNOT BE UNDONE." % locals(),
        ['Confirm', 'Back'], default=1, width=50
        )

    if rc in ['confirm', None]: return RIGHT_FORWARDS

    # Close the file descriptor otherwise it will may not be possible to destroy the accessor
    answers['image-fd'].close()
    return LEFT_BACKWARDS * 3 # back to get image_media

def get_state_partition(answers):
    dev = answers["primary-disk"][5:] # strip the 5-char "/dev/" off
    vendor, model, _ = diskutil.getExtendedDiskInfo(dev)
    partitionList = sorted(diskutil.partitionsOnDisk(dev))
    entries = []
    mountPoint = tempfile.mkdtemp('.oeminstaller')
    os.system('/bin/mkdir -p "'+mountPoint+'"')
    for partition in partitionList:
        partition_dev = '/dev/' + partition.replace("!", "/")
        try:
            util.mount(partition_dev, mountPoint, fstype='ext3', options=['ro'])
            try:
                inventoryFilenames = glob.glob(mountPoint+'/*/etc/xensource-inventory')
                for filename in inventoryFilenames:
                    values = util.readKeyValueFile(filename)
                    # This is a XenServer state partition
                    target = (partition, os.path.basename(os.path.dirname(os.path.dirname(filename))))
                    name = values.get('PRODUCT_BRAND', '')+' '+values.get('PRODUCT_VERSION', '')+' ('+partition+', '+values.get('INSTALLATION_UUID', '')+')'
                    entries.append((name, target))
            finally:
                util.umount(partition_dev)
            
        except Exception, e:
            pass # Failed to mount and read inventory - not a state partition
        
    if len(entries) == 0:
        entries.append(('No installations found', None))
        
    result, entry = ListboxChoiceWindow(
        tui.screen,
        "Installations",
        "Please select the installation for password reset on device \"%(vendor)s, %(model)s\":" % locals(),
        entries, ['Ok', 'Back'])

    answers['partition'] = entry
    if entry is None: return LEFT_BACKWARDS
    if result in ['ok', None]: return RIGHT_FORWARDS
    if result == 'back': return LEFT_BACKWARDS

def get_new_password(answers):
    button, result = snackutil.PasswordEntryWindow(
        tui.screen,
        "New Password",
        "Please enter the new password:",
        ["New Password", "Repeat Password"], entryWidth = 20,
        buttons = ["Ok", "Back"])

    if button == 'back': return LEFT_BACKWARDS

    try:
        if result[0] != result[1]:
            raise Exception('Passwords do not match')
        if len(result[0]) < 6 and result[0] != '!!':
            raise Exception('Password is too short (minimum length is 6 characters)')
        if re.match(r'\s*$', result[0]):
            raise Exception('Passwords containing only spaces are not allowed')

        answers['new-password'] = result[0]
    except Exception, e:
        ButtonChoiceWindow(
            tui.screen, "Failed",
            str(e),
            ['Back'])
        return REPEAT_STEP
        
    if button in ['ok', None]: return RIGHT_FORWARDS
    return LEFT_BACKWARDS

def confirm_reset_password(answers):
    rc = snackutil.ButtonChoiceWindowEx(
        tui.screen,
        "Confirm Reset Password",
        "Are you sure you want to reset the password for this installation?",
        ['Reset Password', 'Back'], default=0, width=50
        )

    if rc in ['reset password', None]: return RIGHT_FORWARDS

    return LEFT_BACKWARDS * 2 # back to the top level

    
