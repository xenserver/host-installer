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
from generalui import runCmd
import uicontroller

################################################################################
# CONFIGURATION

ui_package = tui

dom0_size = 200
dom0_name = "Dom0"
rws_size = 20
rws_name = "RWS"
boot_size = 50
vgname = "VG_XenEnterprise"

dom0fs_tgz_location = "/opt/xensource/clean-installer/dom0fs.tgz"
kernel_tgz_location = "/opt/xensource/clean-installer/kernels.tgz"
kernel_version = "2.6.12.6-xen"

grubroot = '(hd0,0)'
#grubroot = '(cd)'

bootfs_type = 'ext2'
rootfs_type = 'ext3'
rwsfs_type = 'ext3'

################################################################################
# FIRST STAGE INSTALLATION:

def performStage1Install(answers):
    global ui_package

    pd = ui_package.initProgressDialog('Xen Enterprise Installation',
                                       'Installing Xen Enterprise, please wait...',
                                       6)

    ui_package.displayProgressDialog(0, pd)

    # Dom0 Disk partition table
    writeDom0DiskPartitions(answers['primary-disk'])
    ui_package.displayProgressDialog(1, pd)

    # Guest disk partition table
    for gd in answers['guest-disks']:
        writeGuestDiskPartitions(gd)
    ui_package.displayProgressDialog(2, pd)

    # Create volume group and any needed logical volumes:
    prepareLVM(answers)
    ui_package.displayProgressDialog(3, pd)

    # Put filesystems on Dom0 Disk
    createDom0DiskFilesystems(answers['primary-disk'])
    ui_package.displayProgressDialog(4, pd)

    # Extract Dom0 onto disk:
    # TODO - more granularity for progress dialog here
    extractDom0Filesystem(answers['primary-disk'])
    ui_package.displayProgressDialog(5, pd)

    # Install grub and grub configuration to read-write partition
    installGrub(answers['primary-disk'])
    ui_package.displayProgressDialog(6, pd)

    ui_package.clearProgressDialog()


# TODO - get all this right!!
def hasServicePartition(disk):
    return False

def getDom0PartName(disk):
    global dom0_name
    return "/dev/VG_XenEnterprise/%s" % dom0_name

def getRWSPartName(disk):
    global rws_name
    return "/dev/VG_XenEnterprise/%s" % rws_name

def getBootPartNumber(disk):
    if hasServicePartition(disk):
        return 2
    else:
        return 1

def getBootPartName(disk):
    return "%s%s" % (disk, getBootPartNumber(disk))

def getDom0LVMPartNumber(disk):
    if hasServicePartition(disk):
        return 3
    else:
        return 2

def getDom0LVMPartName(disk):
    return "%s%s" % (disk, getDom0LVMPartNumber(disk))

###
# Functions to write partition tables to disk

# TODO - take into account service partitions
def writeDom0DiskPartitions(disk):
    global boot_size

    # we really don't want to screw this up...
    assert type(disk) == str
    assert disk[:5] == '/dev/'

    # for some reason sfdisk wants to run interactively when we do
    # this using pipes, so for now we'll just write the partitions
    # to a file and then use '<' to get sfdisk to read the file.

    parts = open("/tmp/dom0disk_parts", "w")
    parts.write(",%s,L\n" % boot_size)
    parts.write(",,8e\n")
    parts.write("\n")
    parts.write("\n")
    parts.close()

    assert runCmd("sfdisk --no-reread -q -uM %s </tmp/dom0disk_parts" % disk) == 0

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

def prepareLVM(answers):
    global vgname
    global dom0_name, dom0_size
    global rws_name, rws_size
    
    partitions = [ getDom0LVMPartName(answers['primary-disk']) ]

    # [ '/dev/sda', '/dev/sdb' ] ==> [ '/dev/sda1', '/dev/sda2' ]
    partitions = partitions + map(lambda x: "%s1" % x, answers['guest-disks'])

    # TODO - better error handling

    for x in partitions:
        assert runCmd("pvcreate -ff -y %s" % x) == 0

    # LVM doesn't like creating VGs if a previous volume existed and left
    # behind device nodes...
    if os.path.exists("/dev/%s" % vgname):
        runCmd("rm -rf /dev/%s" % vgname)
    assert runCmd("vgcreate '%s' %s" % (vgname, " ".join(partitions))) == 0

    assert runCmd("lvcreate -L %s -C y -n %s %s" % (dom0_size, dom0_name, vgname)) == 0
    assert runCmd("lvcreate -L %s -C y -n %s %s" % (rws_size, rws_name, vgname)) == 0

    os.system("vgmknodes")


###
# Create dom0 disk file-systems:

def createDom0DiskFilesystems(disk):
    assert runCmd("mkfs.%s %s" % (bootfs_type, getBootPartName(disk))) == 0
    assert runCmd("mkfs.%s %s" % (rootfs_type, getDom0PartName(disk))) == 0
    assert runCmd("mkfs.%s %s" % (rwsfs_type, getRWSPartName(disk))) == 0

def installGrub(disk):
    global grubroot
    
    # grub configuration - placed here for easy editing.  Written to
    # the grub.conf file later in this function.
    grubconf = ""
    grubconf += "default 0\n"
    grubconf += "timeout 3\n"
    grubconf += "hiddenmenu\n"
    grubconf += "title Xen Enterprise\n"
    grubconf += "   root (%s,%s)\n" % (getGrUBDevice(disk), getBootPartNumber(disk))
    grubconf += "   kernel /boot/xen-3.0.0.gz\n"
    grubconf += "   module /boot/vmlinuz-2.6.12.6-xen root=%s ro\n" % getDom0PartName(disk)
    grubconf += "   module /boot/initrd-2.6.12.6-xen.img\n"
    grubconf += "title Xen Enterprise in Safe Mode\n"
    grubconf += "   root (%s,%s)\n" % (getGrUBDevice(disk), getBootPartNumber(disk))
    grubconf += "   kernel /boot/xen-3.0.0.gz noacpi nousb nosmp\n"
    grubconf += "   module /boot/vmlinuz-2.6.12.6-xen root=%s ro\n" % getDom0PartName(disk)
    grubconf += "   module /boot/initrd-2.6.12.6-xen.img\n"


    # install GrUB - TODO better error handling required here:
    # - copy GrUB files into place:
    assert runCmd("mount %s /tmp" % getBootPartName(disk)) == 0
    os.mkdir("/tmp/grub")
    runCmd("cp /boot/grub/* /tmp/grub") # We should do this in Python...
    runCmd("rm -f /tmp/grub/grub.conf")

    # now install GrUB to the MBR of the first disk:
    # (note GrUB partition numbers start from 0 not 1)
    boot_grubpart = getBootPartNumber(disk) - 1
    grubdest = '(%s,%s)' % (getGrUBDevice(disk), boot_grubpart)
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
    assert runCmd("tar -C /tmp -xzf %s" % dom0fs_tgz_location) == 0

    runCmd("umount /tmp")

def installKernels(disk):
    dest = getRWSPartName(disk)
    
    # mount empty filesystem:
    # TODO - better error handling:
    assert runCmd("mount %s /tmp" % dest) == 0

    # TODO - use Python directly here...!
    runCmd("cp /boot/vmlinuz-2.6.12.6-xen /tmp/boot")
    runCmd("cp /boot/xen-3.0.0.gz /tmp/boot")

    runCmd("umount /tmp")


################################################################################
# SECOND STAGE INSTALLATION (i.e. fs customisation etc.)

def performStage2Install(answers):
    mounts = mountVolumes(answers['primary-disk'])

    installKernels(mounts, answers)
    setRootPassword(mounts, answers)
    setTime(mounts, answers)
    configureNetworking(mounts, answers)
    writeFstab(mounts, answers)

    umountVolumes(mounts)

##########
# mounting and unmounting of various volumes

def mountVolumes(primary_disk):
    rootvol = getDom0PartName(primary_disk)
    bootvol = getBootPartName(primary_disk)
    rwsvol = getRWSPartName(primary_disk)
    
    # work out where to bount things (note that rootVol and bootVol might
    # be equal).  Note the boot volume must be mounted inside the root directory
    # as it needs to be accessible from a chroot.    
    rootpath = '/tmp/root'
    bootpath = '/tmp/root/boot'
    rwspath = "/tmp/root/rws"

    # mount the volumes
    assertDir(rootpath)
    os.system("mount %s %s" % (rootvol, rootpath))

    if not rootvol == bootvol:
        assertDir(bootpath)
        os.system("mount %s %s" % (bootvol, bootpath))

    assertDir(rwspath)
    os.system("mount %s %s" % (rwsvol, rwspath))

    # ugh - umount-order - what a piece of crap
    return {'boot': bootpath,
            'rws' : rwspath,
            'root': rootpath,
            'umount-order': [bootpath, rwspath, rootpath]}

def umountVolumes(mounts):
    for m in mounts['umount-order']: # hack!
        os.system("umount %s" % m)

##########
# second stage install helpers:

def installKernels(mounts, answers):
    assert os.system("tar -C %s -xzf %s" % (mounts['boot'], kernel_tgz_location)) == 0
    
def mkInitrd(mounts, answers):
    global kernel_version

    # chroot in and make the initrd:
    os.system("chroot %s depmod %s" % kernel_version)
    os.system("chroot %s mkinitrd -o /boot/initrd-%s.img %s"
              % (mounts['root'], kernel_version, kernel_version))

def writeFstab(mounts, answers):
    assertDir("%s/etc" % mounts['rws'])

    # first work out what we're going to write:
    rootpart = getDom0PartName(answers['primary-disk'])
    rwspart = getRWSPartName(answers['primary-disk'])
    bootpart = getBootPartName(answers['primary-disk'])
    
    fstab = open("%s/etc/fstab" % mounts['rws'], "w")
    fstab.write("%s   /     %s     defaults   1  1\n" % (rootpart, rootfs_type))
    fstab.write("%s   /boot %s     defaults   1  1\n" % (bootpart, rootfs_type))
    fstab.write("%s   /rws  %s     defaults   1  1\n" % (rwspart, rwsfs_type))
    fstab.write("none /proc proc   defaults   1  1\n")
    fstab.write("none /sys  sysfs  defaults   1  1\n")

    fstab.close()
    
def setTime(mounts, answers):
    ### the UI will have to do this, because there would be too big a time-gap
    ### between now and when the question was asked.
    pass

# TODO.
def setRootPassword(mounts, answers):
    pass


# write /etc/sysconfig/network-scripts/* files
def configureNetworking(mounts, answers):
    def writeDHCPConfigFile(fd, device, hwaddr = None):
        fd.write("DEVICE=%s" % device)
        fd.write("BOOTPROTO=dhcp")
        fd.write("ONBOOT=yes")
        fd.write("TYPE=ethernet")
        if hwaddr:
            fd.write("HWADDR=%s" % hwaddr)
            
    assertDirs("%s/etc" % mounts['rws'],
               "%s/etc/sysconfig" % mounts['rws'],
               "%s/etc/sysconfig/network-scripts" % mounts['rws'])

    # write the configuration file for the loopback interface
    out = open("%s/etc/sysconfig/network-scripts/ifcfg-lo" % mounts['rws'], "w")
    out.write("DEVICE=lo\n")
    out.write("IPADDR=127.0.0.1\n")
    out.write("NETMASK=255.0.0.0\n")
    out.write("NETWORK=127.0.0.0\n")
    out.write("BROADCASE=127.255.255.255\n")
    out.write("ONBOOT=yes\n")
    out.write("NAME=loopback\n")
    out.close()

    # are we all DHCP?
    (alldhcp, mancfg) = answers['iface-configuration']
    if alldhcp:
        ifaces = generalui.getNetifList()
        for i in ifaces:
            ifcfd = open("%s/etc/sysconfig/network-scripts/%s" % (mounts['rws'], i), "w")
            writeDHCPConfigFile(ifcfd, i, generalui.getHWAddr(i))
            ifcfd.close()
    else:
        # no - go through each interface manually:
        for i in mancfg:
            iface = mancfg[i]
            ifcfd = open("%s/etc/sysconfig/network-scripts/%s" % (mounts['rws'], i), "w")
            if i['use-dhcp']:
                writeDHCPConfigFile(ifcfd, i, generalui.getHWAddr(i))
            else:
                ifcfd.write("DEVICE=%s\n" % i)
                ifcfd.write("BOOTPROTO=none\n")
                if getHWAddr(i):
                    ifcfd.write("HWADDR=%s\n" % generalui.getHWAddr(i))
                ifcfd.write("ONBOOT=yes\n")
                ifcfd.write("TYPE=Ethernet\n")
                ifcfd.write("NETMASK=%s\n" % i['subnet-mask'])
                ifcfd.write("IPADDR=%s\n" % i['ip'])
                ifcfd.write("GATEWAY=%s\n" % i['gateway'])
                ifcfd.write("PEERDNS=yes\n")
            ifcfd.close()

    

################################################################################
# OTHER HELPERS

def getGrUBDevice(disk):
    devicemap_path = "/tmp/device.map"
    
    # first, make sure the device.map file exists:
    if not os.path.isfile(devicemap_path):
        runCmd("echo '' | grub --device-map %s --batch" % devicemap_path)

    devmap = open(devicemap_path)
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

def assertDir(dirname):
    # make sure there isn't already a file there:
    assert not (os.path.exists(dirname) and not os.path.isdir(dirname))

    if not os.path.isdir(dirname):
        os.mkdir(dirname)

def assertDirs(*dirnames):
    for d in dirnames:
        assertDir(d)
