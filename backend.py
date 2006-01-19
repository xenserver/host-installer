###
# XEN CLEAN INSTALLER
# Functions to perform the XE installation
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import os
import os.path

import tui
import generalui
import uicontroller

ui_package = tui

dom0_size = 200
rws_size = 20
vgname = "VG_XenEnterprise"

dom0fs_tgz_location = "/opt/xensource/clean-installer/dom0fs.tgz"

grubroot = '(hd0,0)'

################################################################################
# FIRST STAGE INSTALLATION:

def performStage1Install(answers):
    global ui_package

    pd = ui_package.initProgressDialog('Xen Enterprise Installation',
                                       'Installing Xen Enterprise, please wait...',
                                       7)

    ui_package.displayProgressDialog(0, pd)

    # Dom0 Disk partition table
    writeDom0DiskPartitions(answers['primary-disk'])
    ui_package.displayProgressDialog(1, pd)

    # Guest disk partition table
    for gd in answers['guest-disks']:
        writeGuestDiskPartitions(gd)
    ui_package.displayProgressDialog(2, pd)

    # Put filesystems on Dom0 Disk
    createDom0DiskFilesystems(answers['primary-disk'])
    ui_package.displayProgressDialog(3, pd)

    # Extract Dom0 onto disk:
    # TODO - more granularity for progress dialog here
    extractDom0Filesystem(answers['primary-disk'])
    ui_package.displayProgressDialog(4, pd)

    # Install grub and grub configuration to read-write partition
    installGrub(answers['primary-disk'])
    ui_package.displayProgressDialog(5, pd)

    # Install our kernels:
    installKernels(answers['primary-disk'])
    ui_package.displayProgressDialog(6, pd)

    # Create LVM volume group for guests
    partitions = [ getDom0LVMPartName(answers['primary-disk']) ]
    for extradisk in answers['guest-disks']:
        partitions.append("%s1" % extradisk)
    createLVMVolumeGroup(partitions)
    ui_package.displayProgressDialog(7, pd)

    ui_package.clearProgressDialog()


# TODO - how to do this?
def hasServicePartition(disk):
    return False

def getDom0PartNumber(disk):
    if hasServicePartition(disk):
        return 2
    else:
        return 1

def getDom0PartName(disk):
    return "%s%s" % (disk, getDom0PartNumber(disk))

def getRWSPartNumber(disk):
    if hasServicePartition(disk):
        return 3
    else:
        return 2

def getRWSPartName(disk):
    return "%s%s" % (disk, getRWSPartNumber(disk))

def getDom0LVMPartNumber(disk):
    if hasServicePartition(disk):
        return 4
    else:
        return 3

def getDom0LVMPartName(disk):
    return "%s%s" % (disk, getDom0LVMPartNumber(disk))

###
# Functions to write partition tables to disk

# TODO - take into account service partitions
def writeDom0DiskPartitions(disk):
    global dom0_size
    global rws_size

    # we really don't want to screw this up...
    assert type(disk) == str
    assert disk[:5] == '/dev/'

    # for some reason sfdisk wants to run interactively when we do
    # this using pipes, so for now we'll just write the partitions
    # to a file and then use '<' to get sfdisk to read the file.

    parts = open("/tmp/dom0disk_parts", "w")
    parts.write(",%s,L\n" % dom0_size)   # dom0 partition
    parts.write(",%s,L,*\n" % rws_size)  # rws partition
    parts.write(",,8e\n")                # LVM guest storage
    parts.write("\n")                    # no fourth partition
    parts.close()

    result = runCmd("sfdisk --no-reread -q -uM %s </tmp/dom0disk_parts" % disk)

    # clean up:
    assert result == 0

def writeGuestDiskPartitions(disk):
    global dom0_size
    global rws_size

    # we really don't want to screw this up...
    assert type(disk) == str
    assert disk[:5] == '/dev/'

    # for some reason sfdisk wants to run interactively when we do
    # this using pipes, so for now we'll just write the partitions
    # to a file and then use '<' to get sfdisk to read the file.

    parts = open("/tmp/guestdisk_parts", "w")
    parts.write(",,8e\n")                # LVM guest storage
    parts.write("\n")                    # no second partition
    parts.write("\n")                    # no third partition
    parts.write("\n")                    # no fourth partition
    parts.close()

    result = runCmd("sfdisk --no-reread -q -uM %s </tmp/dom0disk_parts" % disk)

    # clean up:
    assert result == 0

###
# Create dom0 disk file-systems:

def createDom0DiskFilesystems(disk):
    if hasServicePartition(disk):
        dom0part = "%s2" % disk
        rwspart = "%s3" % disk
    else:
        dom0part = "%s1" % disk
        rwspart = "%s2" % disk

    # make filesystems: TODO better error handling
    assert runCmd("mkfs.ext3 %s" % dom0part) == 0
    assert runCmd("mkfs.ext2 %s" % rwspart) == 0 # ext2 as GrUB is going here...

def installGrub(disk):
    global grubroot
    
    # grub configuration - placed here for easy editing.  Written to
    # the grub.conf file later in this function.
    grubconf = ""
    grubconf += "default 0\n"
    grubconf += "timeout 3\n"
    grubconf += "hiddenmenu\n"
    grubconf += "title Xen Enterprise\n"
    grubconf += "   root (%s,1)\n" % getGrUBDevice(disk)
    grubconf += "   kernel /boot/xen-3.0.0.gz\n"
    grubconf += "   module /boot/vmlinuz-2.6.12.6-xen\n"
    grubconf += "   module /boot/initrd-2.6.12.6-xen.img\n"
    grubconf += "title Xen Enterprise\n in Safe Mode"
    grubconf += "   root (%s,1)\n" % getGrUBDevice(disk)
    grubconf += "   kernel /boot/xen-3.0.0.gz noacpi nousb nosmp\n"
    grubconf += "   module /boot/vmlinuz-2.6.12.6-xen\n"
    grubconf += "   module /boot/initrd-2.6.12.6-xen.img\n"


    # install GrUB - TODO better error handling required here:
    # - copy GrUB files into place:
    assert runCmd("mount %s /tmp" % getRWSPartName(disk)) == 0
    os.mkdir("/tmp/grub")
    runCmd("cp /boot/grub/* /tmp/grub") # We should do this in Python...
    runCmd("rm -f /tmp/grub/grub.conf")

    # now install GrUB to the MBR of the first disk:
    # (note GrUB part numbers start from 0 not 1)
    rws_grubpart = getRWSPartNumber(disk) - 1
    grubdest = '(%s,%s)' % (getGrUBDevice(disk), rws_grubpart)
    stage2 = "%s/grub/stage2" % grubdest
    conf = "%s/grub/grub.conf" % grubdest
    runCmd("echo 'install %s/grub/stage1 d (hd0) %s p %s' | grub --batch"
              % (grubroot, stage2, conf))
    
    # write the grub.conf file:
    grubconf_file = open("/tmp/grub/grub.conf", "w")
    grubconf_file.write(grubconf)
    grubconf_file.close()

    runCmd("umount /tmp")

def extractDom0Filesystem(disk):
    global dom0fs_tgz_location
    
    dest = getDom0PartName(disk)

    # mount empty filesystem:
    # TODO - better error handling:
    assert runCmd("mount %s /tmp" % dest) == 0

    # extract tar.gz to filesystem:
    # TODO - rewrite this using native Python so we have a better progress
    #        dialog situation :)
    runCmd("tar -C /tmp -xzf %s" % dom0fs_tgz_location)

    runCmd("umount /tmp")

def installKernels(disk):
    dest = getRWSPartName(disk)
    
    # mount empty filesystem:
    # TODO - better error handling:
    assert runCmd("mount %s /tmp" % dest) == 0

    # TODO - use Python directly here...!
    runCmd("cp /boot/vmlinuz-2.6.12.6-xen /tmp/boot")
    runCmd("cp /boot/initrd-2.6.12.6-xen.img /tmp/boot")
    runCmd("cp /boot/xen-3.0.0.gz /tmp/boot")

    runCmd("umount /tmp")


def createLVMVolumeGroup(partitions):
    global vgname

    # first create physical volumes on the appropriate partitions:
    for p in partitions:
        runCmd("pvcreate -y -ff %s" % p)

    # now create a big volume group that spans the partitions:
    runCmd("vgcreate %s %s" % (vgname, " ".join(partitions)))

################################################################################
# SECOND STAGE INSTALLATION (i.e. fs customisation etc.)

################################################################################
# OTHER HELPERS

def getGrUBDevice(disk):
    devmap = open("/boot/grub/device.map")
    for line in devmap:
        if line[0] != '#':
            # (we get e.g. ['a','','','','','b'] due to multiple spaces unless
            #  we perform the filter operation.)
            (grubdev, unixdev) = filter(lambda x: x != '',
                                        line.expandtabs().strip("\n").split(" "))
            if unixdev == disk:
                devmap.close()
                return grubdev.strip("()")
    devmap.close()
    return None

# TODO - write output to a FIFO whose other end is connected to a VT?
def runCmd(command):
    actualCmd = "%s &>/dev/null" % command
    return os.system(actualCmd)
