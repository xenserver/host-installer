###
# XEN CLEAN INSTALLER
# Functions to perform the XE installation
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import os
import os.path
import subprocess

import tui
import generalui
from generalui import runCmd
import uicontroller
from version import *
import version

################################################################################
# CONFIGURATION

# TODO - get this passed in somehow.
ui_package = tui

rws_size = 20000
rws_name = "RWS"
dropbox_size = 4000
dropbox_name = "Dropbox"
dropbox_type = "ext3"

boot_size = 65
vgname = "VG_XenEnterprise"

dom0fs_tgz_location = "/opt/xensource/clean-installer/dom0fs-%s-%s.tgz" % (version.dom0_name, version.dom0_version)
kernel_tgz_location = "/opt/xensource/clean-installer/kernels-%s-%s.tgz" % (version.dom0_name, version.dom0_version)
xgt_location = "/opt/xensource/xgt/"

dom0tmpfs_name = "tmp-%s" % version.dom0_name
dom0tmpfs_size = 200

grubroot = '(hd0,0)'

bootfs_type = 'ext2'
dom0tmpfs_type = 'ext3'
ramdiskfs_type = 'cramfs'
rwsfs_type = 'ext3'

writeable_files = [ '/etc/yp.conf',
                                  '/etc/ntp.conf',
                                  '/etc/resolv.conf',
                                  '/etc/hosts',
                                  '/etc/adjtime'
                                ]
                                
writeable_dirs = [ 
                                  '/etc/ntp'
                                ]


################################################################################
# FIRST STAGE INSTALLATION:

def performStage1Install(answers):
    global ui_package

    pd = ui_package.initProgressDialog('%s Installation' % PRODUCT_NAME,
                                       'Installing %s, please wait...' % PRODUCT_NAME,
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
    createDom0Tmpfs(answers['primary-disk'])
    ui_package.displayProgressDialog(4, pd)

    # Extract Dom0 onto disk:
    # TODO - more granularity for progress dialog here
    extractDom0Filesystem(answers['primary-disk'])
    ui_package.displayProgressDialog(5, pd)

    # Install grub and grub configuration to read-write partition
    installGrub(answers['primary-disk'])
    ui_package.displayProgressDialog(6, pd)

    ui_package.clearModelessDialog()


# TODO - get all this right!!
def hasServicePartition(disk):
    return False

def getRWSPartName(disk):
    global rws_name, vgname
    return "/dev/%s/%s" % (vgname, rws_name)

def getDropboxPartName(disk):
    global dropbox_name, vgname
    return "/dev/%s/%s" % (vgname, dropbox_name)

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

    assert runCmd("sfdisk -q -uM %s </tmp/dom0disk_parts" % disk) == 0

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

    result = runCmd("sfdisk  -q -uM %s </tmp/dom0disk_parts" % disk)

    # clean up:
    assert result == 0

def prepareLVM(answers):
    global vgname
    global dom0_size
    global rws_name, rws_size
    global dropbox_name, dropbox_size
    
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

    assert runCmd("lvcreate -L %s -C y -n %s %s" % (rws_size, rws_name, vgname)) == 0
    assert runCmd("lvcreate -L %s -C y -n %s %s" % (dropbox_size, dropbox_name, vgname)) == 0

    assert runCmd("vgchange -a y VG_XenEnterprise") == 0
    assert runCmd("vgmknodes") == 0


###
# Create dom0 disk file-systems:

def createDom0DiskFilesystems(disk):
    global bootfs_type, rwsfs_type, vgname, dropbox_name, dropbox_type
    assert runCmd("mkfs.%s %s" % (bootfs_type, getBootPartName(disk))) == 0
    assert runCmd("mkfs.%s %s" % (rwsfs_type, getRWSPartName(disk))) == 0
    assert runCmd("mkfs.%s %s" % (dropbox_type, getDropboxPartName(disk))) == 0

def createDom0Tmpfs(disk):
    global vgname, dom0tmpfs_name, dom0tmpfs_size
    assert runCmd("lvcreate -L %s -C y -n %s %s" % (dom0tmpfs_size, dom0tmpfs_name, vgname)) == 0
    assert runCmd("vgchange -a y VG_XenEnterprise") == 0
    assert runCmd("vgmknodes") == 0
    assert runCmd("mkfs.%s /dev/%s/%s" % (dom0tmpfs_type, vgname, dom0tmpfs_name)) == 0
    
def installGrub(disk):
    global grubroot
    
    # grub configuration - placed here for easy editing.  Written to
    # the grub.conf file later in this function.
    grubconf = ""
    grubconf += "default 0\n"
    grubconf += "timeout 3\n"
    grubconf += "hiddenmenu\n"
    grubconf += "title %s\n" % PRODUCT_NAME
    grubconf += "   root (%s,%s)\n" % (getGrUBDevice(disk), getBootPartNumber(disk) - 1)
    grubconf += "   kernel /xen-3.0.0.gz\n"
    grubconf += "   module /vmlinuz-2.6.12.6-xen ramdisk_size=65000 root=/dev/ram0 ro\n"
    grubconf += "   module /%s-%s.img\n" % (version.dom0_name, version.dom0_version)
    grubconf += "title %s in Safe Mode\n" % PRODUCT_NAME
    grubconf += "   root (%s,%s)\n" % (getGrUBDevice(disk), getBootPartNumber(disk) - 1)
    grubconf += "   kernel /xen-3.0.0.gz noacpi nousb nosmp noreboot\n"
    grubconf += "   module /vmlinuz-2.6.12.6-xen ramdisk_size=50000 root=/dev/ram0 ro\n"
    grubconf += "   module /%s-%s.img\n" % (version.dom0_name, version.dom0_version)

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
    
    # mount empty filesystem:
    # TODO - better error handling:
    assert runCmd("mount /dev/%s/%s /tmp" % (vgname, dom0tmpfs_name)) == 0

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
    global ui_package

    mounts = mountVolumes(answers['primary-disk'])

    ui_package.displayInfoDialog("Completing installation",
                                 "The %s installation is being completed.\nThis may take a while" % PRODUCT_NAME)

    installKernels(mounts, answers)
    doDepmod(mounts, answers)
    setRootPassword(mounts, answers)
    setTime(mounts, answers)
    ui_package.screen.suspend()
    configureNetworking(mounts, answers)
    ui_package.screen.resume()
    writeFstab(mounts, answers)
    writeModprobeConf(mounts, answers)
    mkLvmDirs(mounts, answers)
    copyXgts(mounts, answers)

    umountVolumes(mounts)
    finalise(answers)

    ui_package.clearModelessDialog()

##########
# mounting and unmounting of various volumes

def mountVolumes(primary_disk):
    global vgname, dom0tmpfs_name
    
    tmprootvol = "/dev/%s/%s" % (vgname, dom0tmpfs_name)
    bootvol = getBootPartName(primary_disk)
    rwsvol = getRWSPartName(primary_disk)
    dropboxvol = getDropboxPartName(primary_disk)
    
    # work out where to bount things (note that rootVol and bootVol might
    # be equal).  Note the boot volume must be mounted inside the root directory
    # as it needs to be accessible from a chroot.    
    rootpath = '/tmp/root'
    bootpath = '/tmp/root/boot'
    rwspath = "/tmp/root/rws"
    dropboxpath = "/tmp/root/dropbox"

    # mount the volumes (must assertDir in mounted filesystem...)
    assertDir(rootpath)
    os.system("mount %s %s" % (tmprootvol, rootpath))
    assertDir(bootpath)
    os.system("mount %s %s" % (bootvol, bootpath))
    assertDir(rwspath)
    os.system("mount %s %s" % (rwsvol, rwspath))
    assertDir(dropboxpath)
    os.system("mount %s %s" % (dropboxvol, dropboxpath))

    # ugh - umount-order - what a piece of crap
    return {'boot': bootpath,
            'rws' : rwspath,
            'root': rootpath,
            'dropbox': dropboxpath,
            'umount-order': [dropboxpath, bootpath, rwspath, rootpath]}

def umountVolumes(mounts):
    for m in mounts['umount-order']: # hack!
        assert os.system("umount %s" % m) == 0

##########
# second stage install helpers:

def installKernels(mounts, answers):
    assert runCmd("tar -C %s -xzf %s" % (mounts['boot'], kernel_tgz_location)) == 0
    
def doDepmod(mounts, answers):
    runCmd("chroot %s depmod %s" % (version.kernel_version, version.kernel_version))

def writeFstab(mounts, answers):
    assertDir("%s/etc" % mounts['rws'])

    # first work out what we're going to write:
    rwspart = getRWSPartName(answers['primary-disk'])
    bootpart = getBootPartName(answers['primary-disk'])
    dropboxpart = getDropboxPartName(answers['primary-disk'])

    # write 
    for dest in ["%s/etc/fstab" % mounts["rws"], "%s/etc/fstab" % mounts['root']]:
        fstab = open(dest, "w")
        fstab.write("/dev/ram0   /     %s     defaults   1  1\n" % ramdiskfs_type)
        fstab.write("%s          /rws  %s     defaults   0  0\n" % (rwspart, rwsfs_type))
        fstab.write("%s          /dropbox  %s     defaults   0  0\n" % (dropboxpart, dropbox_type))
        fstab.write("none        /proc proc   defaults   0  0\n")
        fstab.write("none        /sys  sysfs  defaults   0  0\n")
        fstab.close()
    
def setTime(mounts, answers):
    ### the UI will have to do this, because there would be too big a time-gap
    ### between now and when the question was asked.
    pass

def setRootPassword(mounts, answers):
    # avoid using shell here to get around potential security issues.
    pipe = subprocess.Popen(["/usr/sbin/chroot", "%s" % mounts["root"],
                             "passwd", "--stdin", "root"],
                            stdin = subprocess.PIPE, stdout = subprocess.PIPE)
    pipe.stdin.write(answers["root-password"])
    assert pipe.wait() == 0

# write /etc/sysconfig/network-scripts/* files
def configureNetworking(mounts, answers):
    def writeDHCPConfigFile(fd, device, hwaddr = None):
        fd.write("DEVICE=%s\n" % device)
        fd.write("BOOTPROTO=dhcp\n")
        fd.write("ONBOOT=yes\n")
        fd.write("TYPE=ethernet\n")
        if hwaddr:
            fd.write("HWADDR=%s\n" % hwaddr)
            
    assertDirs("%s/etc" % mounts['rws'],
               "%s/etc/sysconfig" % mounts['rws'],
               "%s/etc/sysconfig/network-scripts" % mounts['rws'])

    # are we all DHCP?
    (alldhcp, mancfg) = answers['iface-configuration']
    if alldhcp:
        ifaces = generalui.getNetifList()
        for i in ifaces:
            ifcfd = open("%s/etc/sysconfig/network-scripts/ifcfg-%s" % (mounts['rws'], i), "w")
            writeDHCPConfigFile(ifcfd, i, generalui.getHWAddr(i))
            ifcfd.close()

            # symlink from Dom0 -> RWS:
            assert runCmd("ln -sf /rws/etc/sysconfig/network-scripts/ifcfg-%s %s/etc/sysconfig/network-scripts/ifcfg-%s" %
                          (i, mounts["root"], i)) == 0
    else:
        # no - go through each interface manually:
        for i in mancfg:
            iface = mancfg[i]
            ifcfd = open("%s/etc/sysconfig/network-scripts/%s" % (mounts['rws'], i), "w")
            if iface['use-dhcp']:
                writeDHCPConfigFile(ifcfd, i, generalui.getHWAddr(i))
            else:
                ifcfd.write("DEVICE=%s\n" % i)
                ifcfd.write("BOOTPROTO=none\n")
                hwaddr = generalui.getHWAddr(i)
                if hwaddr:
                    ifcfd.write("HWADDR=%s\n" % hwaddr)
                ifcfd.write("ONBOOT=yes\n")
                ifcfd.write("TYPE=Ethernet\n")
                ifcfd.write("NETMASK=%s\n" % iface['subnet-mask'])
                ifcfd.write("IPADDR=%s\n" % iface['ip'])
                ifcfd.write("GATEWAY=%s\n" % iface['gateway'])
                ifcfd.write("PEERDNS=yes\n")

            # symlink from Dom0 -> RWS:
            assert runCmd("ln -sf /rws/etc/sysconfig/network-scripts/ifcfg-%s %s/etc/sysconfig/network-scripts/ifcfg-%s" %
                          (i, mounts["root"], i)) == 0
                          
            ifcfd.close()

    # write the configuration file for the loopback interface
    out = open("%s/etc/sysconfig/network-scripts/ifcfg-lo" % mounts['rws'], "w")
    out.write("DEVICE=lo\n")
    out.write("IPADDR=127.0.0.1\n")
    out.write("NETMASK=255.0.0.0\n")
    out.write("NETWORK=127.0.0.0\n")
    out.write("BROADCAST=127.255.255.255\n")
    out.write("ONBOOT=yes\n")
    out.write("NAME=loopback\n")
    out.close()
    
    assert runCmd("ln -sf /rws/etc/sysconfig/network-scripts/ifcfg-lo %s/etc/sysconfig/network-scripts/ifcfg-lo" %
                   mounts["root"]) == 0

    # now we need to write /etc/sysconfig/network
    nfd = open("%s/etc/sysconfig/network" % mounts["rws"], "w")
    nfd.write("NETWORKING=yes\n")
    if answers["manual-hostname"][0] == True:
        nfd.write("HOSTNAME=%s\n" % answers["manual-hostname"][1])
    else:
        nfd.write("HOSTNAME=localhost.localdomain\n")
    nfd.close()

    for file in writeable_files:
        # Copy the file if it exists
        if os.path.isfile("%s/%s" % (mounts["root"], file)):
            assert runCmd("cp -f %s/%s %s/%s" % (mounts["root"], file, mounts["rws"], file))
        assert runCmd("ln -sf /rws/%s %s/%s" % (file, mounts["root"], file)) == 0
    for dir in writeable_dirs:
        assert runCmd("ln -sf /rws/%s/ %s/%s" % (dir, mounts["root"], dir)) == 0

    # now symlink from dom0:
    assert runCmd("ln -sf /rws/etc/sysconfig/network %s/etc/sysconfig/network" % mounts["root"]) == 0

def writeModprobeConf(mounts, answers):
    #os.system("discover --data-path=linux/module/name --data-path=linux/module/options --format='%%s %%s' --data-version=$(uname -r) | uniq >%s/etc/modprobe.conf" % mounts["root"])
    os.system("cat /proc/modules | awk '{print $1}' > %s/etc/modules" % mounts["root"])
    
def mkLvmDirs(mounts, answers):
    os.system("mkdir -p %s/etc/lvm/archive" % mounts["root"])
    os.system("mkdir -p %s/etc/lvm/backup" % mounts["root"])
    
def copyXgts(mounts, answers):
    dropboxpath = mounts['dropbox']
    xgtpath = "%s/%s" % (dropboxpath, "/xgt")
    assert(os.system("mkdir -p %s" % xgtpath) == 0)
    assert(os.system("cp  -f %s/*.xgt %s" %(xgt_location, xgtpath)) == 0)
    
def writeEjectRcs():
    for file in ['/etc/rc6.d/S75eject', '/etc/rc0.d/S75eject' ]:
        rcFile = open("%s" % file, "w")
        rcFile.write("#! /bin/sh\n")
        rcFile.write("PATH=/sbin:/bin:/usr/bin\n")
        rcFile.write("[ -f /etc/default/rcS ] && . /etc/default/rcS\n")
        rcFile.write(". /lib/lsb/init-functions\n")
        rcFile.write("do_stop () {\n")
        rcFile.write('    log_begin_msg "Ejecting CD..."\n')
        rcFile.write("    /usr/bin/eject > /dev/null 2>/dev/null\n")
        rcFile.write("    log_end_msg $?\n")
        rcFile.write("}\n")
        rcFile.write('case "$1" in\n')
        rcFile.write("    stop)\n")
        rcFile.write("        do_stop\n")
        rcFile.write("        ;;\n")
        rcFile.write("    *)\n")
        rcFile.write("        ;;\n")
        rcFile.write("esac\n")
        rcFile.write(": exit 0\n")
        rcFile.write("\n")
        rcFile.close()
        os.system("chmod a+x %s" % file)

###
# Compress root filesystem and save to disk:
def finalise(answers):
    global dom0tmpfs_name

    # mount the filesystem parts again - this time in different places (since
    # we are compressing the rootfs into a file in boot, we don't want boot
    # mounted inside root...):
    assert runCmd("mount /dev/VG_XenEnterprise/%s /tmp/root" % dom0tmpfs_name) == 0
    if not os.path.isdir("/tmp/boot"):
        os.mkdir("/tmp/boot")
    assert runCmd("mount %s /tmp/boot" % getBootPartName(answers['primary-disk'])) == 0
    assert runCmd("mkcramfs /tmp/root /tmp/boot/%s-%s.img" % (version.dom0_name, version.dom0_version)) == 0
    assert runCmd("umount /tmp/{root,boot}") == 0

    # now remove the temporary volume
    assert runCmd("lvremove -f /dev/%s/tmp-%s" % (vgname, version.dom0_name)) == 0
    writeEjectRcs()


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
