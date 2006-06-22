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
import pickle

import tui
import generalui
import uicontroller
import xelogging
import util
import diskutil
import netutil
from util import runCmd
import shutil
import packaging
import constants

# Product version and constants:
import version
from version import *
from constants import *

mounts = {}

class InvalidInstallerConfiguration(Exception):
    pass

################################################################################
# FIRST STAGE INSTALLATION:

# XXX Hack - we should have a progress callback, not pass in the
# entire UI component.
def performInstallation(answers, ui_package):
    global mounts

    # do some rudimentary checks to make sure the answers we've
    # been given make sense:
    if not os.path.exists(answers['primary-disk']):
        raise InvalidInstallerConfiguration, "The primary disk you specified for installation could not be found."
    if not answers.has_key('source-media'):
        raise InvalidInstallerConfiguration, "You did not fully specify an installation source."

    # create an installation source object for our installation:
    try:
        xelogging.log("Attempting to configure install method: type %s" % answers['source-media'])
        if answers['source-media'] == 'url':
            installmethod = packaging.HTTPInstallMethod(answers['source-address'])
        elif answers['source-media'] == 'local':
            found = False
            while not found:
                try:
                    installmethod = packaging.LocalInstallMethod()
                except packaging.MediaNotFound, m:
                    retry = ui_package.request_media(m.media_name)
                    if not retry:
                        raise
                else:
                    found = True
        elif answers['source-media'] == 'nfs':
            installmethod = packaging.NFSInstallMethod(answers['source-address'])
    except Exception, e:
        xelogging.log("Failed to configure install method.")
        xelogging.log(e)
        raise

    # wrap everything in a try block so we can close the
    # install method if anything fails.
    try:
        if answers.has_key('upgrade'):
            isUpgradeInstall = answers['upgrade']
        else:
            isUpgradeInstall = False

        if isUpgradeInstall:
            xelogging.log("Performing UPGRADE installation")
            pd = ui_package.initProgressDialog('%s Upgrade' % PRODUCT_BRAND,
                                               'Upgrading %s, please wait...' % PRODUCT_BRAND,
                                               25)
        else:
            xelogging.log("Performing CLEAN installation")
            pd = ui_package.initProgressDialog('%s Installation' % PRODUCT_BRAND,
                                               'Installing %s, please wait...' % PRODUCT_BRAND,
                                               25)

        ui_package.displayProgressDialog(0, pd)

        # write out the data we're using for the installation to
        # the log, excluding the root password:
        xelogging.log("Data being used for installation:")
        for k in answers:
            if k == "root-password":
                val = "<not printed>"
            else:
                val = str(answers[k])
            xelogging.log("%s = %s (type: %s)" % (k, val, str(type(answers[k]))))

        if isUpgradeInstall == False:    
            # remove any volume groups 
            removeBlockingVGs([answers['primary-disk']] + answers['guest-disks'])

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
        
        # Mount the system image:
        mounts = mountVolumes(answers['primary-disk'])
        ui_package.displayProgressDialog(5, pd)

        # Install packages:
        progress = 5
        for package in constants.packages:
            packaging.installPackage(package, installmethod, mounts['root'])
            progress += 1
            ui_package.displayProgressDialog(progress, pd)

        # Install the bootloader:
        installGrub(mounts, answers['primary-disk'])
        ui_package.displayProgressDialog(14, pd)

        # Depmod the kernel:
        doDepmod(mounts, answers)
        ui_package.displayProgressDialog(15, pd)
        
        # perform dom0 file system customisations:
        mkLvmDirs(mounts, answers)
        writeResolvConf(mounts, answers)
        writeKeyboardConfiguration(mounts, answers)
        ui_package.displayProgressDialog(16, pd)
        
        configureNetworking(mounts, answers)
        ui_package.displayProgressDialog(17, pd)
        
        writeFstab(mounts, answers)
        ui_package.displayProgressDialog(18, pd)
        
        writeModprobeConf(mounts, answers)
        ui_package.displayProgressDialog(19, pd)
        
        writeInventory(mounts, answers)
        writeDhclientHooks(mounts, answers)
        touchSshAuthorizedKeys(mounts, answers)
        ui_package.displayProgressDialog(20, pd)
        
        #initNfs(mounts, answers)
        ui_package.displayProgressDialog(21, pd)
        
        # set the root password:
        ui_package.suspend_ui()
        setRootPassword(mounts, answers)
        ui_package.resume_ui()
        ui_package.displayProgressDialog(22, pd)
        
        # configure NTP:
        configureNTP(mounts, answers)
        ui_package.displayProgressDialog(23, pd)
        
        # complete the installation:
        makeSymlinks(mounts, answers)    
        ui_package.displayProgressDialog(24, pd)
        
        if isUpgradeInstall:
            removeOldFs(mounts, answers)

        writeAnswersFile(mounts, answers)

        # set local time:
        setTimeZone(mounts, answers)
        setTime(mounts, answers, ui_package)

        # run any required post installation scripts:
        try:
            if answers.has_key('post-install-script'):
                xelogging.log("Detected user post-install script - attempting to fetch from %s" % answers['post-install-script'])
                util.fetchFile(answers['post-install-script'], '/tmp/postinstall')
                os.system('chmod a+x /tmp/postinstall')
                util.runCmd('/tmp/postinstall %s' % mounts['root'])
                os.unlink('/tmp/postinstall')
        except Exception, e:
            xelogging.log("Failed to run post install script")
            xelogging.log(e)

        umountVolumes(mounts)
        finalise(answers)
        ui_package.displayProgressDialog(25, pd)
        ui_package.clearModelessDialog()
        
    finally:
        # if this fails there is nothing we can do anyway
        # except log the failure:
        try:
            installmethod.finished()
        except Exception, e:
            xelogging.log("An exception was encountered when attempt to close the installation source.")
            xelogging.log(str(e))
        

#will scan all detected harddisks, and pick the first one
#that has a partition with burbank*.img on it.
def CheckInstalledVersion(answers):
    disks = diskutil.getQualifiedDiskList()
    answers['guest-disks'] = []
    for disk in disks:
        if hasBootPartition(disk):
            answers['primary-disk'] = disk
            return True
    return False

def removeBlockingVGs(disks):
    if diskutil.detectExistingInstallation():
        util.runCmd2(['vgreduce', '--removemissing', 'VG_XenSource'])
        util.runCmd2(['lvremove', 'VG_XenSource'])
        util.runCmd2(['vgremove', 'VG_XenSource'])

    for vg in diskutil.findProblematicVGs(disks):
        util.runCmd2(['lvremove', vg])
        util.runCmd2(['vgremove', vg])

def removeOldFs(mounts, answers):
    fsname = "%s/%s-%s.img" % (mounts['boot'],
                               version.dom0_name,
                               version.dom0_version)
    if os.path.isfile(fsname):
        os.unlink(fsname)
        
def writeAnswersFile(mounts, answers):
    fd = open(os.path.join(mounts['boot'], ANSWERS_FILE), 'w')
    del answers['root-password']
    pickle.dump(answers, fd)
    fd.close()

def hasBootPartition(disk):
    mountPoint = os.path.join("/tmp", "mnt")
    rc = False
    util.assertDir(mountPoint)
    try:
        util.mount(getBootPartName(disk), mountPoint)
    except:
        rc = False
    else:
        if os.path.exists(os.path.join(mountPoint, "xen-3.gz")):
            rc = True
        util.umount(mountPoint)
        
    return rc

# TODO - get all this right!!
def hasServicePartition(disk):
    return False

def getRWSPartName(disk):
    global rws_name, vgname
    return "/dev/%s/%s" % (vgname, rws_name)

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

    # partition the disk:
    diskutil.writePartitionTable(disk, [boot_size, -1])

def writeGuestDiskPartitions(disk):
    global dom0_size
    global rws_size

    # we really don't want to screw this up...
    assert type(disk) == str
    assert disk[:5] == '/dev/'

    diskutil.writePartitionTable(disk, [ -1 ])
    
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
            y += 1
    if rc != 0:
        raise Exception("Failed to pvcreate on %s. rc = %d" % (x, rc))


    # LVM doesn't like creating VGs if a previous volume existed and left
    # behind device nodes...
    if os.path.exists("/dev/%s" % vgname):
        runCmd("rm -rf /dev/%s" % vgname)
    assert runCmd("vgcreate '%s' %s" % (vgname, " ".join(partitions))) == 0

    assert runCmd("lvcreate -L %s -n %s %s" % (rws_size, rws_name, vgname)) == 0
    assert runCmd("lvcreate -L %s -n %s %s" % (vmstate_size, vmstate_name, vgname)) == 0

    assert runCmd("vgchange -a y %s" % vgname) == 0
    assert runCmd("vgmknodes") == 0


###
# Create dom0 disk file-systems:

def createDom0DiskFilesystems(disk):
    global bootfs_type, rwsfs_type, vgname
    assert runCmd("mkfs.%s %s" % (bootfs_type, getBootPartName(disk))) == 0
    assert runCmd("mkfs.%s %s" % (rwsfs_type, getRWSPartName(disk))) == 0
    assert runCmd("mkfs.%s %s" % (vmstatefs_type, "/dev/VG_XenSource/%s" % vmstate_name)) == 0

def createDom0Tmpfs(disk):
    global vgname, dom0tmpfs_name, dom0tmpfs_size
    assert runCmd("vgscan") == 0
    assert runCmd("lvcreate -L %s -n %s %s" % (dom0tmpfs_size, dom0tmpfs_name, vgname)) == 0
    assert runCmd("vgchange -a y %s" % vgname) == 0
    assert runCmd("vgmknodes") == 0
    assert runCmd("mkfs.%s /dev/%s/%s" % (dom0tmpfs_type, vgname, dom0tmpfs_name)) == 0
    
def installGrub(mounts, disk):
    grubroot = getGrUBDevice(disk, mounts)

    # prepare extra mounts for installing GRUB:
    util.bindMount("/dev", "%s/dev" % mounts['root'])
    util.bindMount("/proc", "%s/proc" % mounts['root'])
    util.bindMount("/sys", "%s/sys" % mounts['root'])
    util.bindMount("/tmp", "%s/tmp" % mounts['root'])

    rootdisk = "(%s,%s)" % (getGrUBDevice(disk, mounts), getBootPartNumber(disk) - 1)

    # move the splash screen to a safe location so we don't delete it
    # when removing a previous installation of GRUB:
    hasSplash = False
    if os.path.exists("%s/grub/xs-splash.xpm.gz" % mounts['boot']):
        shutil.move("%s/grub/xs-splash.xpm.gz" % mounts['boot'],
                    "%s/xs-splash.xpm.gz" % mounts['boot'])
        hasSplash = True

    # ensure there isn't a previous installation in /boot
    # for any reason:
    if os.path.isdir("%s/grub" % mounts['boot']):
        shutil.rmtree("%s/grub" % mounts['boot'])

    # grub configuration - placed here for easy editing.  Written to
    # the menu.lst file later in this function.
    grubconf = ""
    grubconf += "default 0\n"
    grubconf += "serial --unit=0 --speed=115200\n"
    grubconf += "terminal --timeout=10 console serial\n"
    grubconf += "timeout 10\n"

    # splash screen?
    # (Disabled for now since GRUB messes up on the serial line when
    # this is enabled.)
    if hasSplash and False:
        grubconf += "\n"
        grubconf += "foreground = 000000\n"
        grubconf += "background = cccccc\n"
        grubconf += "splashimage = %s/xs-splash.xpm.gz\n\n" % rootdisk
    
    grubconf += "title %s\n" % PRODUCT_BRAND
    grubconf += "   root %s\n" % rootdisk
    grubconf += "   kernel /xen-%s.gz lowmem_emergency_pool=16M\n" % version.xen_version
    grubconf += "   module /vmlinuz-%s ramdisk_size=75000 root=/dev/ram0 ro console=tty0\n" % version.kernel_version
    grubconf += "   module /%s-%s.img\n" % (version.dom0_name, version.dom0_version)
    grubconf += "title %s (Serial)\n" % PRODUCT_BRAND
    grubconf += "   root %s\n" % rootdisk
    grubconf += "   kernel /xen-%s.gz com1=115200,8n1 console=com1,tty lowmem_emergency_pool=16M\n" % version.xen_version
    grubconf += "   module /vmlinuz-%s ramdisk_size=75000 root=/dev/ram0 ro console=tty0 console=ttyS0,115200n8\n" % version.kernel_version
    grubconf += "   module /%s-%s.img\n" % (version.dom0_name, version.dom0_version)
    grubconf += "title %s in Safe Mode\n" % PRODUCT_BRAND
    grubconf += "   root %s\n" % rootdisk
    grubconf += "   kernel /xen-%s.gz noacpi nousb nosmp noreboot com1=115200,8n1 console=com1,tty\n" % version.xen_version
    grubconf += "   module /vmlinuz-%s ramdisk_size=75000 root=/dev/ram0 ro console=tty0 console=ttyS0,115200n8\n" % version.kernel_version
    grubconf += "   module /%s-%s.img\n" % (version.dom0_name, version.dom0_version)

    # write the GRUB configuration:
    util.assertDir("%s/grub" % mounts['boot'])
    menulst_file = open("%s/grub/menu.lst" % mounts['boot'], "w")
    menulst_file.write(grubconf)
    menulst_file.close()

    # now perform our own installation, onto the MBR of hd0:
    assert runCmd("chroot %s grub-install --recheck '(%s)'" % (mounts['root'], grubroot)) == 0

    # done installing - undo our extra mounts:
    util.umount("%s/dev" % mounts['root'])
    util.umount("%s/proc" % mounts['root'])
    util.umount("%s/sys" % mounts['root'])
    util.umount("%s/tmp" % mounts['root'])

##########
# mounting and unmounting of various volumes

def mountVolumes(primary_disk):
    global vgname, dom0tmpfs_name
    
    tmprootvol = "/dev/%s/%s" % (vgname, dom0tmpfs_name)
    bootvol = getBootPartName(primary_disk)
    rwsvol = getRWSPartName(primary_disk)
    vmstatevol = "/dev/VG_XenSource/%s" % vmstate_name
    
    # work out where to bount things (note that rootVol and bootVol might
    # be equal).  Note the boot volume must be mounted inside the root directory
    # as it needs to be accessible from a chroot.    
    rootpath = '/tmp/root'
    bootpath = '/tmp/root/boot'
    rwspath = "/tmp/root/rws"
    dropboxpath = "/tmp/root%s"  % DOM0_PKGS_DIR_LOCATION
    vmstate_path = "/tmp/root/var/opt/xen/vm"

    # mount the volumes (must assertDir in mounted filesystem...)
    util.assertDir(rootpath)
    util.mount(tmprootvol, rootpath)

    util.assertDir(bootpath)
    util.mount(bootvol, bootpath)

    util.assertDir(rwspath)
    util.mount(rwsvol, rwspath)

    util.assertDir(rwspath + "/packages")
    util.assertDir(dropboxpath)
    util.bindMount(rwspath + "/packages", dropboxpath)

    util.assertDir(vmstate_path)
    util.mount(vmstatevol, vmstate_path)

    # ugh - umount-order - what a piece of crap
    return {'boot': bootpath,
            'dropbox': dropboxpath,
            'rws' : rwspath,
            'root': rootpath,
            'vmstate': vmstate_path,
            'umount-order': [vmstate_path, dropboxpath, bootpath, rwspath, rootpath]}
 
def umountVolumes(mounts, force = False):
     for m in mounts['umount-order']: # hack!
        util.umount(m, force)

def cleanup_umount():
    global mounts
    if mounts.has_key('umount-order'):
        umountVolumes(mounts, True)
    # now remove the temporary volume
    runCmd("lvremove -f /dev/%s/tmp-%s" % (vgname, version.dom0_name))
    runCmd("umount /tmp/mnt || true")

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
    runCmd("chroot %s depmod %s" % (mounts['root'], version.kernel_version))

def writeKeyboardConfiguration(mounts, answers):
    util.assertDir("%s/etc/sysconfig/" % mounts['root'])
    if not answers.has_key('keymap'):
        answers['keymap'] = 'us'
        xelogging.log("No keymap specified, defaulting to 'us'")

    kbdfile = open("%s/etc/sysconfig/keyboard" % mounts['root'], 'w')
    kbdfile.write("KEYBOARDTYPE=pc\n")
    kbdfile.write("KEYTABLE=%s\n" % answers['keymap'])
    kbdfile.close()

def writeFstab(mounts, answers):
    util.assertDir("%s/etc" % mounts['rws'])

    # first work out what we're going to write:
    rwspart = getRWSPartName(answers['primary-disk'])
    bootpart = getBootPartName(answers['primary-disk'])

    # write 
    for dest in ["%s/etc/fstab" % mounts["rws"], "%s/etc/fstab" % mounts['root']]:
        fstab = open(dest, "w")
        fstab.write("/dev/ram0   /     %s     defaults   1  1\n" % ramdiskfs_type)
        fstab.write("%s    /boot    %s    nouser,auto,ro,async    0   0\n" %
                     (bootpart, bootfs_type) )
        fstab.write("%s          /rws  %s     defaults   0  0\n" %
                    (rwspart, rwsfs_type))
        fstab.write("none        /dev/pts  devpts defaults   0  0\n")
        fstab.write("none        /dev/shm  tmpfs  defaults   0  0\n")
        fstab.write("none        /proc     proc   defaults   0  0\n")
        fstab.write("none        /sys      sysfs  defaults   0  0\n")
        fstab.close()
        
def writeResolvConf(mounts, answers):
    (manual_hostname, hostname) = answers['manual-hostname']
    (manual_nameservers, nameservers) = answers['manual-nameservers']

    if manual_nameservers:
        resolvconf = open("%s/etc/resolv.conf" % mounts['root'], 'w')
        if manual_hostname:
            # /etc/hostname:
            eh = open('%s/etc/hostname' % mounts['root'], 'w')
            eh.write(hostname + "\n")
            eh.close()

            # 'search' option in resolv.conf
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

def setTime(mounts, answers, ui_package):
    global writeable_files

    # are we dealing with setting the time?
    if (answers.has_key('set-time') and answers['set-time']) or \
       (answers['time-config-method'] == 'manual'):
        # display the Set TIme dialog in the chosen UI:
        rc, time = util.runCmdWithOutput('chroot %s timeutil getLocalTime' % mounts['root'])
        ui_package.set_time(answers, util.parseTime(time))

        newtime = answers['localtime']
        timestr = "%04d-%02d-%02d %02d:%02d:00" % \
                  (newtime.year, newtime.month, newtime.day,
                   newtime.hour, newtime.minute)

        # chroot into the dom0 and set the time:
        assert runCmd('chroot %s timeutil setLocalTime "%s"' % (mounts['root'], timestr)) == 0
        assert runCmd("hwclock --utc --systohc") == 0

def setTimeZone(mounts, answers):
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
    
def configureNTP(mounts, answers):
    if answers['time-config-method'] == 'ntp':
        # read in the old NTP configuration, remove the server
        # lines and write out a new one:
        ntpsconf = open("%s/etc/ntp.conf" % mounts['root'], 'r')
        lines = ntpsconf.readlines()
        ntpsconf.close()

        lines = filter(lambda x: not x.startswith('server '), lines)

        ntpsconf = open("%s/etc/ntp.conf" % mounts['root'], 'w')
        for line in lines:
            ntpsconf.write(line + "\n")
        if answers.has_key('ntp-servers'):
            for server in answers['ntp-servers']:
                ntpsconf.write("server %s\n" % server)
        ntpsconf.close()

        # now turn on the ntp service:
        util.runCmd('chroot %s chkconfig ntpd on' % mounts['root'])
            

def setRootPassword(mounts, answers):
    # avoid using shell here to get around potential security issues.
    pipe = subprocess.Popen(["/usr/sbin/chroot", "%s" % mounts["root"],
                             "passwd", "--stdin", "root"],
                            stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    pipe.stdin.write(answers["root-password"])
    assert pipe.wait() == 0

# write /etc/sysconfig/network-scripts/* files
def configureNetworking(mounts, answers):
    check_link_down_hack = True

    def writeDHCPConfigFile(fd, device, hwaddr = None):
        fd.write("DEVICE=%s\n" % device)
        fd.write("BOOTPROTO=dhcp\n")
        fd.write("ONBOOT=yes\n")
        fd.write("TYPE=ethernet\n")
        if hwaddr:
            fd.write("HWADDR=%s\n" % hwaddr)

    def writeDisabledConfigFile(fd, device, hwaddr = None):
        fd.write("DEVICE=%s\n" % device)
        fd.write("ONBOOT=no\n")
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
            writeDHCPConfigFile(ifcfd, i, netutil.getHWAddr(i))
            if check_link_down_hack:
                ifcfd.write("check_link_down() { return 1 ; }\n")
            ifcfd.close()

            # this is a writeable file:
            writeable_files.append("/etc/sysconfig/network-scripts/ifcfg-%s" % i)
    else:
        # no - go through each interface manually:
        for i in mancfg:
            iface = mancfg[i]
            ifcfd = open("%s/etc/sysconfig/network-scripts/ifcfg-%s" % (mounts['rws'], i), "w")
            if not iface['enabled']:
                writeDisabledConfigFile(ifcfd, i, netutil.getHWAddr(i))
            else:
                if iface['use-dhcp']:
                    writeDHCPConfigFile(ifcfd, i, netutil.getHWAddr(i))
                else:
                    ifcfd.write("DEVICE=%s\n" % i)
                    ifcfd.write("BOOTPROTO=none\n")
                    hwaddr = netutil.getHWAddr(i)
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
                          
            if check_link_down_hack:
                ifcfd.write("check_link_down() { return 1 ; }\n")
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
    util.bindMount("/proc", "%s/proc" % mounts['root'])
    util.bindMount("/sys", "%s/sys" % mounts['root'])
    
    #####
    #this only works nicely if the install CD runs the same kernel version as the Carbon host will!!!
    #####
    assert runCmd("chroot %s kudzu -q -k %s" % (mounts['root'], version.kernel_version)) == 0
    util.umount("%s/proc" % mounts['root'])
    util.umount("%s/sys" % mounts['root'])
    
    #TODO: hack
    if os.path.exists("/tmp/module-order"):
        os.system("cp /tmp/module-order %s/etc/modules" % mounts['root'])
    else:
        os.system("cat /proc/modules | awk '{print $1}' > %s/etc/modules" % mounts["root"])
    
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

    # now copy files for pre-rws
    # first, umount rws
    util.umount(mounts['rws'], False)

     # make sure required directories exist:
    for dir in pre_rws_dirs:
        util.assertDir("%s%s" % (mounts['rws'], dir))

    for f in pre_rws_files:
        rws_file = "%s%s" % (mounts['rws'], f)
        dom0_file = "%s%s" % (mounts['root'], f)
        runCmd("cp %s %s" % (dom0_file, rws_file))

    # and remount rws
    rwspath = "/tmp/root/rws"
    rwsvol = getRWSPartName(answers['primary-disk'])
    util.assertDir(rwspath)
    util.mount(rwsvol, rwspath)

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

    #special case for rws passwd file
    #CA-2343
    passwd_file = "%spasswd" % mounts['rws']
    if os.path.isfile(passwd_file):
        os.unlink(passwd_file)
        
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
    inv.write("KERNEL_VERSION='%s'\n" % version.kernel_version)
    inv.write("XEN_VERSION='%s'\n" % version.xen_version)
    inv.write("RHEL35_KERNEL_VERSION='%s'\n" % version.rhel35_kernel_version)
    inv.write("RHEL41_KERNEL_VERSION='%s'\n" % version.rhel41_kernel_version)
    inv.write("SLES_KERNEL_VERSION='%s'\n" % version.sles_kernel_version)
    inv.write("INSTALLATION_DATE='%s'\n" % str(datetime.datetime.now()))
    inv.close()

def writeDhclientHooks(mounts, answers):
    #invokes rc.local to update /etc/issue
    hooks = open("%s/etc/dhclient-exit-hooks" % mounts['root'], "w")
    hooks.write(". /etc/rc.local")
    hooks.close()

def touchSshAuthorizedKeys(mounts, answers):
    assert runCmd("mkdir -p %s/root/.ssh/" % mounts['root']) == 0
    assert runCmd("touch %s/root/.ssh/authorized_keys" % mounts['root']) == 0


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

    xelogging.log("About to compress root filesystem...")
    assert runCmd("mksquashfs /tmp/root /tmp/boot/%s-%s.img" % (version.dom0_name, version.dom0_version)) == 0

    util.umount("/tmp/root")
    util.umount("/tmp/boot")

    # now remove the temporary volume
    assert runCmd("lvremove -f /dev/%s/%s" % (vgname, dom0tmpfs_name)) == 0


################################################################################
# OTHER HELPERS

def getGrUBDevice(disk, mounts):
    devicemap_path = "/tmp/device.map"
    outerpath = "%s%s" % (mounts['root'], devicemap_path)
    
    # if the device map doesn't exist, make one up:
    if not os.path.isfile(devicemap_path):
        runCmd("echo '' | chroot %s grub --device-map %s --batch" %
               (mounts['root'], devicemap_path))

    devmap = open(outerpath)
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
        xelogging.writeLog("/tmp/install-log")
        util.umount("/tmp")
    except:
        pass
