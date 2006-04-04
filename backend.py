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
import uicontroller
import version
import logging
import pickle

import util
from util import runCmd

# Product version and constants:
from version import *
from constants import *

mounts = {}

################################################################################
# FIRST STAGE INSTALLATION:

# XXX Hack - we should have a progress callback, not pass in the
# entire UI component.
def performInstallation(answers, ui_package):
    global mounts
    if answers.has_key('upgrade'):
        isUpgradeInstall = answers['upgrade']
    else:
        isUpgradeInstall = False

    if isUpgradeInstall:
        pd = ui_package.initProgressDialog('%s Upgrade' % PRODUCT_BRAND,
                                   'Upgrading %s, please wait...' % PRODUCT_BRAND,
                                   24)
    else:
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

        # Put filesystems on Dom0 Disk
        createDom0DiskFilesystems(answers['primary-disk'])
#    else:
#       if not CheckInstalledVersion(answers):
#            return

    createDom0Tmpfs(answers['primary-disk'])
    ui_package.displayProgressDialog(4, pd)

    # Customise the installation:
    mounts = mountVolumes(answers['primary-disk'])
    ui_package.displayProgressDialog(5, pd)

    # Extract Dom0 onto disk:
    extractDom0Filesystem(mounts, answers['primary-disk'])
    ui_package.displayProgressDialog(6, pd)

    # Install grub and grub configuration to read-write partition
    installGrub(mounts, answers['primary-disk'])
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
    
    if not isUpgradeInstall:
        copyXgts(mounts, answers)
        ui_package.displayProgressDialog(16, pd)

    copyGuestInstallerFiles(mounts, answers)
    ui_package.displayProgressDialog(17, pd)

    copyVendorKernels(mounts, answers)
    copyXenKernel(mounts, answers)
    copyDocs(mounts, answers)
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

    if not isUpgradeInstall:
        writeAnswersFile(mounts, answers)

    
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
    answers['guest-disks'] = []
    for disk in disks:
        if hasBootPartition(disk):
            answers['primary-disk'] = disk
            return True
    return False

def removeOldFs(mounts, answers):
    fsname = "%s/%s-%s.img" % (mounts['boot'],
                               version.dom0_name,
                               version.dom0_version)
    if os.path.isfile(fsname):
        os.unlink(fsname)
        
def writeAnswersFile(mounts, answers):
    fd = open(os.path.join(mounts['boot'], ANSWERS_FILE), 'w')
    pickle.dump(answers, fd)
    fd.close()

def hasBootPartition(disk):
    mountPoint = os.path.join("tmp", "mnt")
    rc = False
    util.assertDir(mountPoint)
    try:
        util.mount(getBootPartName(disk), mountPoint)
    except:
        rc = False
    else:
        if os.path.exists(os.path.join(mountPoint, "xen-3.0.1.gz")):
            rc = True
        util.umount(mountPoint)
        
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
    parts.write(",%s,L,*\n" % boot_size)
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
    if guestdisk.find("cciss") != -1 or \
        guestdisk.find("ida") != -1 or \
        guestdisk.find("rd") != -1 or \
        guestdisk.find("sg") != -1 or \
        guestdisk.find("i2o") != -1 or \
        guestdisk.find("amiraid") != -1 or \
        guestdisk.find("iseries") != -1 or \
        guestdisk.find("emd") != -1 or \
        guestdisk.find("carmel") != -1:
        return guestdisk+"p%d" % partitionNumber
    else:
        return guestdisk + "%d" % partitionNumber

def prepareLVM(answers):
    global vgname
    global dom0_size
    global rws_name, rws_size
    global dropbox_name, dropbox_size

    partitions = [ getDom0LVMPartName(answers['primary-disk']) ]
    partitions += map(lambda x: determinePartitionName(x, 1),
                      answers['guest-disks'])

    rc = 0
    # TODO - better error handling
    for x in partitions:
        y = 0
        while y < 8:
            rc = runCmd("pvcreate -ff -y %s" % x)
            if rc == 0:
                break
            time.sleep(3)
            i += 1
        if rc != 0:
            raise Exception("Failed to pvcreate on %s. rc = %d" % (x, rc))


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
    
def installGrub(mounts, disk):
    grubroot = '(hd0,0)'

    # grub configuration - placed here for easy editing.  Written to
    # the menu.lst file later in this function.
    grubconf = ""
    grubconf += "default 0\n"
    grubconf += "serial --unit=0 --speed=115200\n"
    grubconf += "terminal  console serial --timeout=5\n"
    grubconf += "timeout 10\n"
    grubconf += "title %s\n" % PRODUCT_BRAND
    grubconf += "   root (%s,%s)\n" % (getGrUBDevice(disk), getBootPartNumber(disk) - 1)
    grubconf += "   kernel /xen-%s.gz\n" % version.xen_version
    grubconf += "   module /vmlinuz-%s ramdisk_size=65000 root=/dev/ram0 ro console=tty0\n" % version.kernel_version
    grubconf += "   module /%s-%s.img\n" % (version.dom0_name, version.dom0_version)
    grubconf += "title %s (Serial)\n" % PRODUCT_BRAND
    grubconf += "   root (%s,%s)\n" % (getGrUBDevice(disk), getBootPartNumber(disk) - 1)
    grubconf += "   kernel /xen-%s.gz com1=115200,8n1 console=com1,tty\n" % version.xen_version
    grubconf += "   module /vmlinuz-%s ramdisk_size=65000 root=/dev/ram0 ro console=tty0 console=ttyS0,115200n8\n" % version.kernel_version
    grubconf += "   module /%s-%s.img\n" % (version.dom0_name, version.dom0_version)
    grubconf += "title %s in Safe Mode\n" % PRODUCT_BRAND
    grubconf += "   root (%s,%s)\n" % (getGrUBDevice(disk), getBootPartNumber(disk) - 1)
    grubconf += "   kernel /xen-%s.gz noacpi nousb nosmp noreboot com1=115200,8n1 console=com1,tty\n" % version.xen_version
    grubconf += "   module /vmlinuz-%s ramdisk_size=65000 root=/dev/ram0 ro console=tty0 console=ttyS0,115200n8\n" % version.kernel_version
    grubconf += "   module /%s-%s.img\n" % (version.dom0_name, version.dom0_version)

    # install GrUB - TODO better error handling required here:
    # - copy GrUB files into place:
    util.assertDir("%s/grub" % mounts['boot'])
    files = filter(lambda x: x not in ['menu.lst', 'grub.conf'],
                   os.listdir("/boot/grub"))
    for f in files:
        runCmd("cp /boot/grub/%s %s/grub/" % (f, mounts['boot']))

    # now install GrUB to the MBR of the first disk:
    # (note GrUB partition numbers start from 0 not 1)
    boot_grubpart = getBootPartNumber(disk) - 1
    grubdest = '(%s,%s)' % (getGrUBDevice(disk), boot_grubpart)
    stage2 = "%s/grub/stage2" % grubdest
    conf = "%s/grub/menu.lst" % grubdest
    assert runCmd("echo 'install %s/grub/stage1 d (hd0) %s p %s' | grub --batch"
              % (grubroot, stage2, conf)) == 0
    
    # write the grub.conf file:
    menulst_file = open("%s/grub/menu.lst" % mounts['boot'], "w")
    menulst_file.write(grubconf)
    menulst_file.close()

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
    util.assertDir(rootpath)
    util.mount(tmprootvol, rootpath)

    util.assertDir(bootpath)
    util.mount(bootvol, bootpath)

    util.assertDir(rwspath)
    util.mount(rwsvol, rwspath)

    util.assertDir(dropboxpath)
    util.mount(dropboxvol, dropboxpath)

    # ugh - umount-order - what a piece of crap
    return {'boot': bootpath,
            'rws' : rwspath,
            'root': rootpath,
            'dropbox': dropboxpath,
            'umount-order': [dropboxpath, bootpath, rwspath, rootpath]}

def umountVolumes(mounts, force = False):
     for m in mounts['umount-order']: # hack!
        util.umount(m, force)

def cleanup_umount():
    global mounts
    if mounts.has_key('umount-order'):
        umountVolumes(mounts, True)
    # now remove the temporary volume
    runCmd("lvremove -f /dev/%s/tmp-%s" % (vgname, version.dom0_name))
    


##########
# second stage install helpers:

def extractDom0Filesystem(mounts, disk):
    global dom0fs_tgz_location

    # extract tar.gz to filesystem:
    # TODO - rewrite this using native Python so we have a better progress
    #        dialog situation :)
    assert runCmd("tar -C %s -xzf %s" % (mounts['root'], CD_DOM0FS_TGZ_LOCATION)) == 0

def installKernels(mounts, answers):
    assert runCmd("tar -C %s -xzf %s" % (mounts['boot'], CD_KERNEL_TGZ_LOCATION)) == 0
    
def doDepmod(mounts, answers):
    runCmd("chroot %s depmod %s" % (version.kernel_version, version.kernel_version))

def writeFstab(mounts, answers):
    util.assertDir("%s/etc" % mounts['rws'])

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

    # make the localtime link:
    runCmd("ln -sf /usr/share/zoneinfo/%s %s/etc/localtime" %
           (answers['timezone'], mounts['root']))
    

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
    util.assertDir("%s/etc/sysconfig/network-scripts" %
                  mounts['rws'])

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
    runCmd("mount --bind /proc %s/proc" % mounts['root'])
    runCmd("mount --bind /sys %s/sys" % mounts['root'])
    
    #####
    #this only works nicely if the install CD runs the same kernel version as the Carbon host will!!!
    #####
    assert runCmd("chroot %s kudzu -q -k %s" % (mounts['root'], version.kernel_version)) == 0
    
    #TODO: hack
    os.system("cat /proc/modules | awk '{print $1}' > %s/etc/modules" % mounts["root"])
    
    runCmd("umount %s/{proc,sys}" % mounts['root'])
    
def mkLvmDirs(mounts, answers):
    util.assertDir("%s/etc/lvm/archive" % mounts["root"])
    util.assertDir("%s/etc/lvm/backup" % mounts["root"])

def copyXgts(mounts, answers):
    util.assertDir(DOM0_XGT_LOCATION % mounts['dropbox'])
    util.copyFilesFromDir(CD_XGT_LOCATION, 
                      DOM0_XGT_LOCATION % mounts['dropbox'])
    
def copyGuestInstallerFiles(mounts, answers):
    util.assertDir(DOM0_GUEST_INSTALLER_LOCATION % mounts['dropbox'])
    util.copyFilesFromDir(CD_RHEL41_GUEST_INSTALLER_LOCATION, 
                      DOM0_GUEST_INSTALLER_LOCATION % mounts['dropbox'])


def copyVendorKernels(mounts, answers):
    util.assertDir(DOM0_VENDOR_KERNELS_LOCATION % mounts['dropbox'])
    util.copyFilesFromDir(CD_VENDOR_KERNELS_LOCATION, 
                       DOM0_VENDOR_KERNELS_LOCATION % mounts['dropbox'])

def copyXenKernel(mounts, answers):
    util.assertDir(DOM0_XEN_KERNEL_LOCATION % mounts['dropbox'])
    util.copyFilesFromDir(CD_XEN_KERNEL_LOCATION, 
                       DOM0_XEN_KERNEL_LOCATION % mounts['dropbox'])
                       
def copyDocs(mounts, answers):
    util.copyFile(CD_README_LOCATION, mounts['root'])
   
# make appropriate symlinks according to writeable_files and writeable_dirs:
def makeSymlinks(mounts, answers):
    global writeable_dirs, writeable_files

    # make sure required directories exist:
    for dir in asserted_dirs:
        util.assertDir("%s%s" % (mounts['root'], dir))
        util.assertDir("%s%s" % (mounts['rws'], dir))

    # link directories:
    for d in writeable_dirs:
        rws_dir = "%s%s" % (mounts['rws'], d)
        dom0_dir = "%s%s" % (mounts['root'], d)
        util.assertDir(rws_dir)

        if os.path.isdir(dom0_dir):
            util.copyFilesFromDir(dom0_dir, rws_dir)

        runCmd("rm -rf %s" % dom0_dir)
        assert runCmd("ln -sf /rws%s %s" % (d, dom0_dir)) == 0

    # now link files:
    for f in writeable_files:
        rws_file = "%s%s" % (mounts['rws'], f)
        dom0_file = "%s%s" % (mounts['root'], f)

        # make sure the destination file exists:
        if not os.path.isfile(rws_file):
            if os.path.isfile(dom0_file):
                runCmd("cp %s %s" % (dom0_file, rws_file))
            else:
                fd = open(rws_file, 'w')
                fd.close()

        assert runCmd("ln -sf /rws%s %s" % (f, dom0_file)) == 0
        

def initNfs(mounts, answers):
    exports = open("%s/etc/exports" % mounts['root'] , "w")
    xgt_dir = DOM0_PKGS_DIR_LOCATION + "/xgt"
    exports.write("%s    *(rw,async,no_root_squash)" % (xgt_dir))
    exports.close()
    runCmd("/bin/chmod -R a+w %s" % mounts['dropbox'])

def copyRpms(mounts, answers):
    util.assertDir(DOM0_GLIB_RPMS_LOCATION % mounts['dropbox'])
    util.copyFilesFromDir(CD_RPMS_LOCATION, 
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
    util.assertDir("/tmp/boot")

    util.mount("/dev/%s/%s" % (vgname, dom0tmpfs_name),
               "/tmp/root")
    util.mount(getBootPartName(answers['primary-disk']),
               "/tmp/boot")

    assert runCmd("mksquashfs /tmp/root /tmp/boot/%s-%s.img" % (version.dom0_name, version.dom0_version)) == 0

    util.umount("/tmp/root")
    util.umount("/tmp/boot")

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

def writeLog(answers):
    try: 
        bootnode = getBootPartName(answers['primary-disk'])
        util.mount(bootnode, "/tmp")
        logging.writeLog("/tmp/install-log")
        util.umount("/tmp")
    except:
        pass
