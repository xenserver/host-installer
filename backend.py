###
# XEN CLEAN INSTALLER
# Functions to perform the XE installation
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import os
import os.path
import subprocess
import datetime
import time

import tui
import generalui
from generalui import runCmd
import uicontroller
from version import *
import version
import logging

################################################################################
# CONFIGURATION

# TODO - get this passed in somehow.
ui_package = tui

rws_size = 15000
rws_name = "RWS"
dropbox_size = 15000
dropbox_name = "Files"
dropbox_type = "ext3"

boot_size = 65
vgname = "VG_XenSource"
xen_version = "3.0.1"

# location of files on the CDROM
CD_DOM0FS_TGZ_LOCATION = "/opt/xensource/clean-installer/dom0fs-%s-%s.tgz" % (version.dom0_name, version.dom0_version)
CD_KERNEL_TGZ_LOCATION = "/opt/xensource/clean-installer/kernels-%s-%s.tgz" % (version.dom0_name, version.dom0_version)

CD_XGT_LOCATION = "/opt/xensource/xgt/"
CD_RHEL41_GUEST_INSTALLER_LOCATION = CD_XGT_LOCATION + "install/rhel41/"
CD_RHEL41_INSTALL_INITRD = CD_RHEL41_GUEST_INSTALLER_LOCATION + "rhel41-install-initrd.img"
CD_UPDATE_MODULES_SCRIPT = "/opt/xensource/guest-installer/update-modules"
CD_RPMS_LOCATION = "/opt/xensource/rpms/"
CD_VENDOR_KERNELS_LOCATION = "/opt/xensource/vendor-kernels"
CD_XEN_KERNEL_LOCATION = "/opt/xensource/xen-kernel"

#location/destination of files on the dom0 FS
DOM0_FILES_LOCATION_ROOT = "%s/files/"
DOM0_VENDOR_KERNELS_LOCATION = DOM0_FILES_LOCATION_ROOT + "vendor-kernels/"
DOM0_XEN_KERNEL_LOCATION = DOM0_FILES_LOCATION_ROOT + "xen-kernel/"
DOM0_GUEST_INSTALLER_LOCATION = DOM0_FILES_LOCATION_ROOT + "guest-installer/"

DOM0_GLIB_RPMS_LOCATION = DOM0_FILES_LOCATION_ROOT + "glibc-rpms/"
DOM0_XGT_LOCATION = "%s/xgt"
DOM0_PKGS_DIR_LOCATION = "/opt/xensource/packages"

#file system creation constants
dom0tmpfs_name = "tmp-%s" % version.dom0_name
dom0tmpfs_size = 500
bootfs_type = 'ext2'
dom0tmpfs_type = 'ext3'
ramdiskfs_type = 'squashfs'
rwsfs_type = 'ext3'

grubroot = '(hd0,0)'


#files that should be writeable in the dom0 FS
writeable_files = [ '/etc/yp.conf',
                    '/etc/ntp.conf',
                    '/etc/resolv.conf',
                    '/etc/hosts',
                    '/etc/issue',
                    '/etc/adjtime' ]

#directories to be created in the dom0 FS
asserted_dirs = [ '/etc',
                  '/etc/sysconfig',
                  '/etc/sysconfig/network-scripts',
                  '/etc/lvm' ]

#directories that should be writeable in the dom0 FS
writeable_dirs = [ '/etc/ntp',
                   '/etc/lvm/archive',
                   '/etc/lvm/backup',
                   '/etc/ssh',
                   '/root' ]

################################################################################
# FIRST STAGE INSTALLATION:

# XXX Hack - we should have a progress callback, not pass in the
# entire UI component.
def performInstallation(answers, ui_package):
    
    try:
        isUpgradeInstall = answers['upgrade']
    except:
        isUpgradeInstall = False
    
    pd = ui_package.initProgressDialog('%s Installation' % PRODUCT_BRAND,
                                       'Installing %s, please wait...' % PRODUCT_BRAND,
                                       24)

    ui_package.displayProgressDialog(0, pd)

    if isUpgradeInstall == False:    
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
    else:
        if not CheckInstalledVersion(answers):
            return

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

    # Customise the installation:
    mounts = mountVolumes(answers['primary-disk'])
    ui_package.displayProgressDialog(7, pd)

    # put kernel in /boot and prepare it for use:
    installKernels(mounts, answers)
    ui_package.displayProgressDialog(8, pd)
    doDepmod(mounts, answers)
    ui_package.displayProgressDialog(9, pd)

    # set the root password:
    ui_package.suspend_ui()
    setRootPassword(mounts, answers)
    ui_package.resume_ui()
    ui_package.displayProgressDialog(10, pd)

    # set system time
    setTime(mounts, answers)
    ui_package.displayProgressDialog(11, pd)

    # perform dom0 file system customisations:
    mkLvmDirs(mounts, answers)
    writeResolvConf(mounts, answers)
    ui_package.displayProgressDialog(12, pd)
    
    configureNetworking(mounts, answers)
    ui_package.displayProgressDialog(13, pd)
    
    writeFstab(mounts, answers)
    ui_package.displayProgressDialog(14, pd)
    
    writeModprobeConf(mounts, answers)
    ui_package.displayProgressDialog(15, pd)
    
    copyXgts(mounts, answers)
    ui_package.displayProgressDialog(16, pd)

    copyGuestInstallerFiles(mounts, answers)
    ui_package.displayProgressDialog(17, pd)

    copyVendorKernels(mounts, answers)
    copyXenKernel(mounts, answers)
    ui_package.displayProgressDialog(18, pd)

    copyRpms(mounts, answers)
    ui_package.displayProgressDialog(19, pd)

    writeInventory(mounts, answers)
    ui_package.displayProgressDialog(20, pd)

    initNfs(mounts, answers)
    ui_package.displayProgressDialog(21, pd)
    
    # complete the installation:
    makeSymlinks(mounts, answers)    
    ui_package.displayProgressDialog(23, pd)

    if isUpgradeInstall:
        removeOldFs(mounts, answers)
    
    umountVolumes(mounts)
    finalise(answers)
    ui_package.displayProgressDialog(24, pd)
    

    ui_package.clearModelessDialog()
#    else: 
#        # Do Upgrade
#        pd = ui_package.initProgressDialog('%s Upgrade' % PRODUCT_BRAND,
#                                           'Upgrading %s, please wait...' % PRODUCT_BRAND,
#                                           7)
#
#        ui_package.displayProgressDialog(0, pd)
#                                           
#        if not CheckInstalledVersion(answers):
#            #do something
#            return
#        
#        createDom0Tmpfs(answers['primary-disk'])
#        ui_package.displayProgressDialog(1, pd)
#
#        extractDom0Filesystem(answers['primary-disk'])
#        ui_package.displayProgressDialog(2, pd)
#
#        mounts = mountVolumes(answers['primary-disk'])
#        ui_package.displayProgressDialog(3, pd)
#
#        installKernels(mounts, answers)
#        ui_package.displayProgressDialog(4, pd)
#        
#        doDepmod(mounts, answers)
#        ui_package.displayProgressDialog(5, pd)
#        
#        removeOldFs(mounts, answers)
#
#        umountVolumes(mounts)
#        ui_package.displayProgressDialog(6, pd)
#
#        finalise(answers)
#        ui_package.displayProgressDialog(7, pd)
#
#        ui_package.clearModelessDialog()
        

#will scan all detected harddisks, and pick the first one
#that has a partition with burbank*.img on it.
def CheckInstalledVersion(answers):
    disks = generalui.getDiskList()
    for disk in disks:
        if hasBootPartition(disk):
            answers['primary-disk'] = disk
            return True
    return False

def removeOldFs(mounts, ansers):
    assert runCmd("rm -f %s/%s-%s.img" %
                   (mounts['boot'], dom0_name, dom0_version)) == 0

def hasBootPartition(disk):
    mountPoint = os.path.join("tmp", "mnt")
    rc = False
    assertDir(mountPoint)
    if runCmd("mount %s %s" % (getBootPartName(disk), mountPoint )) == 0:
        if os.path.exists(os.path.join(mountPoint, "xen-3.0.1.gz")):
            rc = True
        runCmd("umount %s" % getBootPartName(disk))
        
    return rc

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
    return determinePartitionName(disk, getBootPartNumber(disk))

def getDom0LVMPartNumber(disk):
    if hasServicePartition(disk):
        return 3
    else:
        return 2

def getDom0LVMPartName(disk):
    return determinePartitionName(disk, getDom0LVMPartNumber(disk))

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

    result = runCmd("sfdisk  -q -uM %s </tmp/guestdisk_parts" % disk)

    # clean up:
    assert result == 0
    
def determinePartitionName(guestdisk, partitionNumber):
    if guestdisk.find("cciss") != -1:
        return guestdisk+"p%d" % partitionNumber
    else:
        return guestdisk + "%d" % partitionNumber

def prepareLVM(answers):
    global vgname
    global dom0_size
    global rws_name, rws_size
    global dropbox_name, dropbox_size
    
    partitions = [ getDom0LVMPartName(answers['primary-disk']) ]

    # [ '/dev/sda', '/dev/sdb' ] ==> [ '/dev/sda1', '/dev/sda2' ]
    
#    partitions = partitions + map(lambda x: "%s1" % x, answers['guest-disks'])
    for gd in answers['guest-disks']: 
        partitions.append(determinePartitionName(gd, 1))

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

    assert runCmd("vgchange -a y %s" % vgname) == 0
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
    assert runCmd("vgscan") == 0
    assert runCmd("lvcreate -L %s -C y -n %s %s" % (dom0tmpfs_size, dom0tmpfs_name, vgname)) == 0
    assert runCmd("vgchange -a y %s" % vgname) == 0
    assert runCmd("vgmknodes") == 0
    assert runCmd("mkfs.%s /dev/%s/%s" % (dom0tmpfs_type, vgname, dom0tmpfs_name)) == 0
    
def installGrub(disk):
    global grubroot
    
    # grub configuration - placed here for easy editing.  Written to
    # the menu.lst file later in this function.
    grubconf = ""
    grubconf += "default 0\n"
    grubconf += "serial --unit=0 --speed=115200\n"
    grubconf += "terminal  console serial --timeout=5\n"
    grubconf += "timeout 10\n"
    grubconf += "title %s\n" % PRODUCT_BRAND
    grubconf += "   root (%s,%s)\n" % (getGrUBDevice(disk), getBootPartNumber(disk) - 1)
    grubconf += "   kernel /xen-%s.gz\n" % xen_version
    grubconf += "   module /vmlinuz-2.6.12.6-xen ramdisk_size=65000 root=/dev/ram0 ro console=tty0\n"
    grubconf += "   module /%s-%s.img\n" % (version.dom0_name, version.dom0_version)
    grubconf += "title %s (Serial)\n" % PRODUCT_BRAND
    grubconf += "   root (%s,%s)\n" % (getGrUBDevice(disk), getBootPartNumber(disk) - 1)
    grubconf += "   kernel /xen-%s.gz com1=115200,8n1 console=com1,tty\n" % xen_version
    grubconf += "   module /vmlinuz-2.6.12.6-xen ramdisk_size=65000 root=/dev/ram0 ro console=tty0 console=ttyS0,115200n8\n"
    grubconf += "   module /%s-%s.img\n" % (version.dom0_name, version.dom0_version)
    grubconf += "title %s in Safe Mode\n" % PRODUCT_BRAND
    grubconf += "   root (%s,%s)\n" % (getGrUBDevice(disk), getBootPartNumber(disk) - 1)
    grubconf += "   kernel /xen-%s.gz noacpi nousb nosmp noreboot com1=115200,8n1 console=com1,tty\n" % xen_version
    grubconf += "   module /vmlinuz-2.6.12.6-xen ramdisk_size=65000 root=/dev/ram0 ro console=tty0 console=ttyS0,115200n8\n"
    grubconf += "   module /%s-%s.img\n" % (version.dom0_name, version.dom0_version)

    # install GrUB - TODO better error handling required here:
    # - copy GrUB files into place:
    assert runCmd("mount %s /tmp" % getBootPartName(disk)) == 0
    assertDir("/tmp/grub")
    runCmd("cp /boot/grub/* /tmp/grub") # We should do this in Python...
    runCmd("rm /tmp/grub/menu.lst") # no menu.lst from cd
    runCmd("rm -f /tmp/grub/grub.conf")

    # now install GrUB to the MBR of the first disk:
    # (note GrUB partition numbers start from 0 not 1)
    boot_grubpart = getBootPartNumber(disk) - 1
    grubdest = '(%s,%s)' % (getGrUBDevice(disk), boot_grubpart)
    stage2 = "%s/grub/stage2" % grubdest
    conf = "%s/grub/menu.lst" % grubdest
    assert runCmd("echo 'install %s/grub/stage1 d (hd0) %s p %s' | grub --batch"
              % (grubroot, stage2, conf)) == 0
    
    # write the grub.conf file:
    menulst_file = open("/tmp/grub/menu.lst", "w")
    menulst_file.write(grubconf)
    menulst_file.close()

    assert runCmd("umount /tmp") == 0

def extractDom0Filesystem(disk):
    global dom0fs_tgz_location
    
    # mount empty filesystem:
    # TODO - better error handling:
    assert runCmd("mount /dev/%s/%s /tmp" % (vgname, dom0tmpfs_name)) == 0

    # extract tar.gz to filesystem:
    # TODO - rewrite this using native Python so we have a better progress
    #        dialog situation :)
    assert runCmd("tar -C /tmp -xzf %s" % CD_DOM0FS_TGZ_LOCATION) == 0

    assert runCmd("umount /tmp") == 0

def installKernels(disk):
    dest = getRWSPartName(disk)
    
    # mount empty filesystem:
    # TODO - better error handling:
    assert runCmd("mount %s /tmp" % dest) == 0

    # TODO - use Python directly here...!
    runCmd("cp /boot/vmlinuz-%s /tmp/boot" % kernel_version) 
    runCmd("cp /boot/xen-%s.gz /tmp/boot" % xen_version)

    assert runCmd("umount /tmp") == 0

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
    dropboxpath = "/tmp/root%s"  % DOM0_PKGS_DIR_LOCATION

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
    assert runCmd("tar -C %s -xzf %s" % (mounts['boot'], CD_KERNEL_TGZ_LOCATION)) == 0
    
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
        fstab.write("%s    /boot    %s    nouser,auto,ro,async    0    0\n" 
                     % (bootpart, bootfs_type) )
        fstab.write("%s          /rws  %s     defaults   0  0\n" % (rwspart, rwsfs_type))
        fstab.write("%s          %s  %s     defaults   0  0\n" % 
                     (dropboxpart, DOM0_PKGS_DIR_LOCATION, dropbox_type))
        fstab.write("none        /proc proc   defaults   0  0\n")
        fstab.write("none        /sys  sysfs  defaults   0  0\n")
        fstab.close()
        
def writeResolvConf(mounts, answers):
    (manual_hostname, hostname) = answers['manual-hostname']
    (manual_nameservers, nameservers) = answers['manual-nameservers']

    if manual_nameservers:
        resolvconf = open("%s/etc/resolv.conf" % mounts['root'], 'w')
        if manual_hostname:
            try:
                dot = hostname.index('.')
                if dot + 1 != len(hostname):
                    dname = hostname[dot + 1:]
                    resolvconf.write("search %s\n" % dname)
            except:
                pass
        for ns in nameservers:
            if ns != "":
                resolvconf.write("nameserver %s\n" % ns)
        resolvconf.close()

def setTime(mounts, answers):
    global writeable_files

    # are we dealing with setting the time?
    if answers['set-time']:
        # first, calculate the difference between the current time
        # and the time when the user entered their desired time, and
        # find the actual desired time:
        now = datetime.datetime.now()
        delta = now - answers['set-time-dialog-dismissed']
        newtime = answers['localtime'] + delta
        
        # now set the local time zone variable and use it:
        os.environ['TZ'] = answers['timezone']
        time.tzset()
        
        # set the local time according to newtime:
        year = str(newtime.year)[2:]
        timestr = "%s-%s-%s %s:%s" % (year, newtime.month,
                                      newtime.day, newtime.hour,
                                      newtime.minute)
        assert runCmd("date --set='%s'" % timestr) == 0
        assert runCmd("hwclock --utc --systohc") == 0

    # write the time configuration to the /etc/sysconfig/clock
    # file in dom0:
    timeconfig = open("%s/etc/sysconfig/clock" % mounts['root'], 'w')
    timeconfig.write("ZONE=%s\n" % answers['timezone'])
    timeconfig.write("UTC=true\n")
    timeconfig.write("ARC=false\n")
    timeconfig.close()

    writeable_files.append('/etc/sysconfig/clock')
    

def setRootPassword(mounts, answers):
    # avoid using shell here to get around potential security issues.
    pipe = subprocess.Popen(["/usr/sbin/chroot", "%s" % mounts["root"],
                             "passwd", "--stdin", "root"],
                            stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
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

    # make sure the directories in rws exist to write to:
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

            # this is a writeable file:
            writeable_files.append("/etc/sysconfig/network-scripts/ifcfg-%s" % i)
    else:
        # no - go through each interface manually:
        for i in mancfg:
            iface = mancfg[i]
            ifcfd = open("%s/etc/sysconfig/network-scripts/ifcfg-%s" % (mounts['rws'], i), "w")
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

            # this is a writeable file:
            writeable_files.append("/etc/sysconfig/network-scripts/ifcfg-%s" % i)
                          
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

    writeable_files.append("/etc/sysconfig/network-scripts/ifcfg-lo")

    # now we need to write /etc/sysconfig/network
    nfd = open("%s/etc/sysconfig/network" % mounts["rws"], "w")
    nfd.write("NETWORKING=yes\n")
    if answers["manual-hostname"][0] == True:
        nfd.write("HOSTNAME=%s\n" % answers["manual-hostname"][1])
    else:
        nfd.write("HOSTNAME=localhost.localdomain\n")
    nfd.close()

    # now symlink from dom0:
    writeable_files.append("/etc/sysconfig/network")

def writeModprobeConf(mounts, answers):
    # mount proc and sys in the filesystem
    runCmd("mount -t proc none %s/proc" % mounts['root'])
    runCmd("mount -t sysfs none %s/sys" % mounts['root'])
    #####
    #this only works nicely if the install CD runs the same kernel version as the Carbon host will!!!
    #####
    assert runCmd("chroot %s kudzu -q -k 2.6.12.6-xen" % mounts['root']) == 0
    
    #TODO: hack
    os.system("cat /proc/modules | awk '{print $1}' > %s/etc/modules" % mounts["root"])
    
    runCmd("umount %s/{proc,sys}" % mounts['root'])
    
def mkLvmDirs(mounts, answers):
    assertDir("%s/etc/lvm/archive" % mounts["root"])
    assertDir("%s/etc/lvm/backup" % mounts["root"])

def copyXgts(mounts, answers):
    assertDir(DOM0_XGT_LOCATION % mounts['dropbox'])
    copyFilesFromDir(CD_XGT_LOCATION, 
                      DOM0_XGT_LOCATION % mounts['dropbox'])
    
def copyGuestInstallerFiles(mounts, answers):
    assertDir(DOM0_GUEST_INSTALLER_LOCATION % mounts['dropbox'])
    copyFilesFromDir(CD_RHEL41_GUEST_INSTALLER_LOCATION, 
                      DOM0_GUEST_INSTALLER_LOCATION % mounts['dropbox'])


def copyVendorKernels(mounts, answers):
    assertDir(DOM0_VENDOR_KERNELS_LOCATION % mounts['dropbox'])
    copyFilesFromDir(CD_VENDOR_KERNELS_LOCATION, 
                       DOM0_VENDOR_KERNELS_LOCATION % mounts['dropbox'])

def copyXenKernel(mounts, answers):
    assertDir(DOM0_XEN_KERNEL_LOCATION % mounts['dropbox'])
    copyFilesFromDir(CD_XEN_KERNEL_LOCATION, 
                       DOM0_XEN_KERNEL_LOCATION % mounts['dropbox'])
     
   
# make appropriate symlinks according to writeable_files and writeable_dirs:
def makeSymlinks(mounts, answers):
    global writeable_dirs, writeable_files

    # make sure required directories exist:
    for dir in asserted_dirs:
        assertDir("%s%s" % (mounts['root'], dir))
        assertDir("%s%s" % (mounts['rws'], dir))

    # link directories:
    for dir in writeable_dirs:
        rws_dir = "%s%s" % (mounts['rws'], dir)
        dom0_dir = "%s%s" % (mounts['root'], dir)
        assertDir(rws_dir)

        if os.path.isdir(dom0_dir):
	        copyFilesFromDir(dom0_dir, rws_dir)

        runCmd("rm -rf %s" % dom0_dir)
        assert runCmd("ln -sf /rws/%s %s" % (dir, dom0_dir)) == 0

    # now link files:
    for file in writeable_files:
        rws_file = "%s%s" % (mounts['rws'], file)
        dom0_file = "%s%s" % (mounts['root'], file)

        # make sure the destination file exists:
	if not os.path.isfile(rws_file):
	    if os.path.isfile(dom0_file):
                runCmd("cp %s %s" % (dom0_file, rws_file))
            else:
                fd = open(rws_file, 'w')
                fd.close()

        assert runCmd("ln -sf /rws%s %s" % (file, dom0_file)) == 0
        

def initNfs(mounts, answers):
    exports = open("%s/etc/exports" % mounts['root'] , "w")
    exports.write("%s    *(rw,async,no_root_squash)" % DOM0_PKGS_DIR_LOCATION)
    exports.close()
    runCmd("/bin/chmod -R a+w %s" % mounts['dropbox'])

def copyRpms(mounts, answers):
    assertDir(DOM0_GLIB_RPMS_LOCATION % mounts['dropbox'])
    copyFilesFromDir(CD_RPMS_LOCATION, 
                      DOM0_GLIB_RPMS_LOCATION % mounts['dropbox'])

def writeInventory(mounts, answers):
    inv = open("%s/etc/xensource-inventory" % mounts['root'], "w")
    inv.write("PRODUCT_BRAND='%s'\n" % PRODUCT_BRAND)
    inv.write("PRODUCT_NAME='%s'\n" % PRODUCT_NAME)
    inv.write("PRODUCT_VERSION='%s'\n" % PRODUCT_VERSION)
    inv.write("BUILD_NUMBER='%s'\n" % BUILD_NUMBER)
    inv.write("INSTALLATION_DATE='%s'\n" % str(datetime.datetime.now()))
    inv.close()
    
###
# Compress root filesystem and save to disk:
def finalise(answers):
    global dom0tmpfs_name

    # mount the filesystem parts again - this time in different places (since
    # we are compressing the rootfs into a file in boot, we don't want boot
    # mounted inside root...):
    assert runCmd("mount /dev/%s/%s /tmp/root" % (vgname, dom0tmpfs_name)) == 0
    assertDir("/tmp/boot")
    assert runCmd("mount %s /tmp/boot" % getBootPartName(answers['primary-disk'])) == 0
    assert runCmd("mksquashfs /tmp/root /tmp/boot/%s-%s.img" % (version.dom0_name, version.dom0_version)) == 0

    assert runCmd("umount /tmp/{root,boot}") == 0

    # now remove the temporary volume
    assert runCmd("lvremove -f /dev/%s/tmp-%s" % (vgname, version.dom0_name)) == 0


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
        os.makedirs(dirname)

def assertDirs(*dirnames):
    for d in dirnames:
        assertDir(d)

def copyFilesFromDir(sourcedir, dest):
    assert os.path.isdir(sourcedir)
    assert os.path.isdir(dest)

    files = os.listdir(sourcedir)
    for f in files:
        assert runCmd("cp -a %s/%s %s/" % (sourcedir, f, dest)) == 0

def writeLog(answers):
    try: 
        bootnode = getBootPartName(answers['primary-disk'])
        assert os.system("mount %s /tmp" % bootnode) == 0
        logging.writeLog("/tmp/install-log")
        assert os.system("umount /tmp") == 0
    except:
        pass
