# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Functions to perform the XE installation
#
# written by Andrew Peace

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
import hardware

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

    if answers.has_key('upgrade'):
        isUpgradeInstall = answers['upgrade']
    else:
        isUpgradeInstall = False

    # do some rudimentary checks to make sure the answers we've
    # been given make sense:
    if not os.path.exists(answers['primary-disk']):
        raise InvalidInstallerConfiguration, "The primary disk you specified for installation could not be found."
    if not answers.has_key('source-media'):
        raise InvalidInstallerConfiguration, "You did not fully specify an installation source."
    if not isUpgradeInstall and not answers.has_key('root-password'):
        raise InvalidInstallerConfiguration, "You did not specify an acceptable root password.  You must specify a root password of length %d characters." % constants.MIN_PASSWD_LEN

    if answers['time-config-method'] == 'ntp':
        if not answers.has_key('ntp-servers'):
            answers['ntp-servers'] = []

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

        # remove any volume groups 
        removeBlockingVGs([answers['primary-disk']] + answers['guest-disks'])
        
        # Dom0 Disk partition table
        writeDom0DiskPartitions(answers['primary-disk'])
        ui_package.displayProgressDialog(1, pd)
    
        # Guest disk partition table
        for gd in answers['guest-disks']:
            if gd != answers['primary-disk']:
                writeGuestDiskPartitions(gd)
        ui_package.displayProgressDialog(2, pd)
        
        # Create the default storage repository if disks
        # have been selected:
        if answers['guest-disks'] != []:
            default_sr = prepareStorageRepository(answers['primary-disk'], answers['guest-disks'])
        else:
            xelogging.log("No storage repository created.")
            default_sr = None
        ui_package.displayProgressDialog(3, pd)
            
        # Put filesystems on Dom0 Disk
        createDom0DiskFilesystems(answers['primary-disk'])

        # Mount the system image:
        mounts = mountVolumes(answers['primary-disk'])
        ui_package.displayProgressDialog(5, pd)

        # Install packages:
        progress = 5
        packages = installmethod.getPackageList()
        for package in packages:
            installmethod.installPackage(package, mounts['root'])
            progress += 1
            ui_package.displayProgressDialog(progress, pd)

        # Install the bootloader:
        installGrub(mounts, answers['primary-disk'])
        ui_package.displayProgressDialog(14, pd)

        # Create modules.dep:
        doDepmod(mounts)
        ui_package.displayProgressDialog(15, pd)
        
        # perform dom0 file system customisations:
        writeResolvConf(mounts, answers['manual-hostname'], answers['manual-nameservers'])
        writeKeyboardConfiguration(mounts, answers['keymap'])
        ui_package.displayProgressDialog(16, pd)
        
        configureNetworking(mounts, answers['iface-configuration'], answers['manual-hostname'])
        ui_package.displayProgressDialog(17, pd)

        prepareSwapfile(mounts)
        writeFstab(mounts)
        writeSmtab(mounts, default_sr)
        enableSM(mounts)
        enableAgent(mounts)
        ui_package.displayProgressDialog(18, pd)

        writeModprobeConf(mounts)
        ui_package.displayProgressDialog(19, pd)

        mkinitrd(mounts)
        ui_package.displayProgressDialog(20, pd)
        
        writeInventory(mounts, default_sr)
        touchSshAuthorizedKeys(mounts)
        ui_package.displayProgressDialog(21, pd)
        
        # set the root password: (not if upgrade, because we're preserving the old
        # passwd file)
        if not isUpgradeInstall and answers.has_key('root-password'):
            xelogging.log("Setting root password.")
            ui_package.suspend_ui()
            setRootPassword(mounts, answers['root-password'])
            ui_package.resume_ui()
        else:
            xelogging.log("Not setting root password because we are doing an upgrade.")
        ui_package.displayProgressDialog(22, pd)
        
        # configure NTP:
        if answers['time-config-method'] == 'ntp':
            configureNTP(mounts, answers['time-config-method'], answers['ntp-servers'])
        ui_package.displayProgressDialog(23, pd)
        
        # complete the installation:
        makeSymlinks(mounts)
        ui_package.displayProgressDialog(24, pd)

        writeAnswersFile(mounts, answers)

        # set local time:
        setTimeZone(mounts, answers['timezone'])
        if not isUpgradeInstall:
            setTime(mounts, answers['time-config-method'], ui_package)

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

def removeBlockingVGs(disks):
    if diskutil.detectExistingInstallation():
        util.runCmd2(['vgreduce', '--removemissing', 'VG_XenSource'])
        util.runCmd2(['lvremove', 'VG_XenSource'])
        util.runCmd2(['vgremove', 'VG_XenSource'])

    for vg in diskutil.findProblematicVGs(disks):
        util.runCmd2(['lvremove', vg])
        util.runCmd2(['vgremove', vg])

def writeAnswersFile(mounts, answers):
    fd = open(os.path.join(mounts['boot'], ANSWERS_FILE), 'w')
    if answers.has_key('root-password'):
        del answers['root-password']
    pickle.dump(answers, fd)
    fd.close()

#def getSwapPartName(disk):
#    global swap_name, vgname
#    return "/dev/%s/%s" % (vgname, swap_name)

def getBootPartNumber(disk):
    return 1

def getBootPartName(disk):
    return determinePartitionName(disk, getBootPartNumber(disk))

# XXX boot and root are the same thing now - this mess should be
# cleaned up.
getRootPartName = getBootPartName
getRootPartNumber = getBootPartNumber

###
# Functions to write partition tables to disk

# TODO - take into account service partitions
def writeDom0DiskPartitions(disk):
    # we really don't want to screw this up...
    assert type(disk) == str
    assert disk[:5] == '/dev/'

    # partition the disk:
    diskutil.writePartitionTable(disk, [root_size, root_size, -1])
    diskutil.makeActivePartition(disk, 1)

def writeGuestDiskPartitions(disk):
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

def prepareStorageRepository(primary_disk, guest_disks):
    xelogging.log("Preparing default storage repository...")
    sr_uuid = util.getUUID()

    def sr_partition(disk):
        if disk == primary_disk:
            return determinePartitionName(disk, 3)
        else:
            return determinePartitionName(disk, 1)

    partitions = [sr_partition(disk) for disk in guest_disks]
    xelogging.log("Creating storage repository on partitions %s" % partitions)
    args = ['sm', 'create', '-f', '-vv', '-m', '/tmp', '-U', sr_uuid] + partitions
    assert util.runCmd2(args) == 0
    xelogging.log("Storage repository created with UUID %s" % sr_uuid)
    return sr_uuid

###
# Create dom0 disk file-systems:

def createDom0DiskFilesystems(disk):
    assert runCmd("mkfs.%s -L %s %s" % (rootfs_type, rootfs_label, getRootPartName(disk))) == 0

def mkinitrd(mounts):
    modules_list = ["--with=%s" % x for x in hardware.getModuleOrder()]

    modules_string = " ".join(modules_list)
    output_file = "/boot/initrd-%s.img" % version.KERNEL_VERSION
    
    cmd = "mkinitrd %s %s %s" % (modules_string, output_file, version.KERNEL_VERSION)
    
    util.runCmd("chroot %s %s" % (mounts['root'], cmd))
    util.runCmd("ln -sf %s %s/boot/initrd-2.6-xen.img" % (output_file, mounts['root']))

def installGrub(mounts, disk):
    # prepare extra mounts for installing GRUB:
    util.bindMount("/dev", "%s/dev" % mounts['root'])
    util.bindMount("/sys", "%s/sys" % mounts['root'])
    util.bindMount("/tmp", "%s/tmp" % mounts['root'])

    # this is a nasty hack but unavoidable (I think): grub-install
    # uses df to work out what the root device is, but df's output is
    # incorrect within the chroot.  Therefore, we fake out /etc/mtab
    # with the correct data, so GRUB will install correctly:
    mtab = "%s/proc/mounts" % mounts['root']
    if not os.path.islink("%s/etc/mtab" % mounts['root']):
        mtab = "%s/etc/mtab" % mounts['root']
    f = open(mtab, 'w')
    f.write("%s / %s rw 0 0\n" % (getRootPartName(disk), constants.rootfs_type))
    f.close()

    grubroot = getGrUBDevice(disk, mounts)

    rootdisk = "(%s,%s)" % (getGrUBDevice(disk, mounts), getRootPartNumber(disk) - 1)
    bootpart = getRootPartName(disk)

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

    # select an appropriate default (normal or serial) based on
    # how we are being installed:
    rc, tty = util.runCmdWithOutput("tty")
    if tty.startswith("/dev/ttyS") and rc == 0:
        grubconf += "default 1\n"
    else: # not tty.startswith("/dev/ttyS") or rc != 0
        grubconf += "default 0\n"
        
    grubconf += "terminal console\n"
    grubconf += "timeout 5\n\n"

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
    grubconf += "   kernel /boot/xen-%s.gz dom0_mem=524288 lowmem_emergency_pool=16M\n" % version.XEN_VERSION
    grubconf += "   module /boot/vmlinuz-%s ramdisk_size=75000 root=LABEL=%s ro console=tty0\n" % (version.KERNEL_VERSION, constants.rootfs_label)
    grubconf += "   module /boot/initrd-%s.img\n" % version.KERNEL_VERSION

    grubconf += "title %s (Serial)\n" % PRODUCT_BRAND
    grubconf += "   root %s\n" % rootdisk
    grubconf += "   kernel /boot/xen-%s.gz com1=115200,8n1 console=com1,tty dom0_mem=524288 lowmem_emergency_pool=16M\n" % version.XEN_VERSION
    grubconf += "   module /boot/vmlinuz-%s ramdisk_size=75000 root=LABEL=%s ro console=tty0 console=ttyS0,115200n8\n" % (version.KERNEL_VERSION, constants.rootfs_label)
    grubconf += "   module /boot/initrd-%s.img\n" % version.KERNEL_VERSION
    
    grubconf += "title %s in Safe Mode\n" % PRODUCT_BRAND
    grubconf += "   root %s\n" % rootdisk
    grubconf += "   kernel /boot/xen-%s.gz nosmp noreboot noirqbalance acpi=off noapic dom0_mem=524288 com1=115200,8n1 console=com1,tty\n" % version.XEN_VERSION
    grubconf += "   module /boot/vmlinuz-%s nousb ramdisk_size=75000 root=LABEL=%s ro console=tty0 console=ttyS0,115200n8\n" % (version.KERNEL_VERSION, constants.rootfs_label)
    grubconf += "   module /boot/initrd-%s.img\n" % version.KERNEL_VERSION

    # write the GRUB configuration:
    util.assertDir("%s/grub" % mounts['boot'])
    menulst_file = open("%s/grub/menu.lst" % mounts['boot'], "w")
    menulst_file.write(grubconf)
    menulst_file.close()

    # now perform our own installation, onto the MBR of hd0:
    assert runCmd("chroot %s grub-install --recheck '(%s)'" % (mounts['root'], grubroot)) == 0

    # done installing - undo our extra mounts:
    util.umount("%s/dev" % mounts['root'])
    # try to unlink /proc/mounts in case /etc/mtab is a symlink
    if os.path.exists("%s/proc/mounts" % mounts['root']):
        os.unlink("%s/proc/mounts" % mounts['root'])
    util.umount("%s/sys" % mounts['root'])
    util.umount("%s/tmp" % mounts['root'])

##########
# mounting and unmounting of various volumes

MOUNT_SOURCE_DEVICE = 1
MOUNT_SOURCE_BIND = 2
def mountVolumes(primary_disk):
    base = '/tmp/root'

    # mounts is a list of triples of (name, mount source, mountpoint)
    # where mountpoint is based off of base, defined above:
    mounts = [('root', (MOUNT_SOURCE_DEVICE, determinePartitionName(primary_disk, 1)), '/'),
              ('rws', None, '/rws'),
              ('boot', None, '/boot')]

    umount_order = ['root']

    for (name, src, dst) in mounts:
        dst = os.path.join(base, dst.lstrip('/'))

        util.assertDir(dst)
        if src:
            (mnt_type, mnt_source) = src

            if mnt_type == MOUNT_SOURCE_DEVICE:
                util.mount(mnt_source, dst)
            elif mnt_type == MOUNT_SOURCE_BIND:
                mnt_source = os.path.join(base, mnt_source.lstrip('/'))
                util.assertDir(mnt_source)
                util.bindMount(mnt_source, dst)

    # later I'll implement a class to do all this properly but
    # for now we're stuck with this rubbish (including umount-order):
    rv = {}
    for (n, s, d) in mounts:
        rv[n] = os.path.join(base, d.lstrip('/'))
    rv['umount-order'] = umount_order
    
    return rv
 
def umountVolumes(mounts, force = False):
    for name in mounts['umount-order']: # hack!
        util.umount(mounts[name], force)

def cleanup_umount():
    global mounts
    if mounts and mounts.has_key('umount-order'):
        umountVolumes(mounts, True)

##########
# second stage install helpers:
    
def doDepmod(mounts):
    runCmd("chroot %s depmod %s" % (mounts['root'], version.KERNEL_VERSION))

def writeKeyboardConfiguration(mounts, keymap):
    util.assertDir("%s/etc/sysconfig/" % mounts['root'])
    if not keymap:
        keymap = 'us'
        xelogging.log("No keymap specified, defaulting to 'us'")

    kbdfile = open("%s/etc/sysconfig/keyboard" % mounts['root'], 'w')
    kbdfile.write("KEYBOARDTYPE=pc\n")
    kbdfile.write("KEYTABLE=%s\n" % keymap)
    kbdfile.close()

def prepareSwapfile(mounts):
    util.assertDir("%s/var/swap" % mounts['root'])
    util.runCmd2(['dd', 'if=/dev/zero',
                  'of=%s' % os.path.join(mounts['root'], constants.swap_location.lstrip('/')),
                  'bs=1024', 'count=%d' % (constants.swap_size * 1024)])
    util.runCmd2(['chroot', mounts['root'], 'mkswap', '/var/swap/swap.001'])

def writeFstab(mounts):
    util.assertDir("%s/etc" % mounts['rws'])

    # write 
    fstab = open(os.path.join(mounts['root'], 'etc/fstab'), "w")
    fstab.write("LABEL=%s    /         %s     defaults   1  1\n" % (rootfs_label, rootfs_type))
    fstab.write("%s          swap      swap   defaults   0  0\n" % (constants.swap_location))
    fstab.write("none        /dev/pts  devpts defaults   0  0\n")
    fstab.write("none        /dev/shm  tmpfs  defaults   0  0\n")
    fstab.write("none        /proc     proc   defaults   0  0\n")
    fstab.write("none        /sys      sysfs  defaults   0  0\n")
    fstab.close()

# creates an empty file if default_sr is None:
def writeSmtab(mounts, default_sr):
    smtab = open(os.path.join(mounts['root'], 'etc/smtab'), 'w')
    if default_sr:
        smtab.write("%s none lvm default auto\n" % default_sr)
    smtab.close()

def enableSM(mounts):
    assert util.runCmd2(['chroot', mounts['root'], 'chkconfig',
                         '--add', 'smtab']) == 0

def enableAgent(mounts):
    util.runCmd2(['chroot', mounts['root'],
                  'chkconfig', 'xend', 'on'])
    util.runCmd2(['chroot', mounts['root'],
                  'chkconfig', 'xendomains', 'on'])
    util.runCmd2(['chroot', mounts['root'],
                  'chkconfig', 'xenagentd', 'on'])

def writeResolvConf(mounts, hn_conf, ns_conf):
    (manual_hostname, hostname) = hn_conf
    (manual_nameservers, nameservers) = ns_conf

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

def setTime(mounts, time_config_method, ui_package):
    global writeable_files

    # are we dealing with setting the time?
    if time_config_method == 'manual':
        # display the Set TIme dialog in the chosen UI:
        rc, time = util.runCmdWithOutput('chroot %s timeutil getLocalTime' % mounts['root'])
        answers = {}
        ui_package.set_time(answers, util.parseTime(time))

        newtime = answers['localtime']
        timestr = "%04d-%02d-%02d %02d:%02d:00" % \
                  (newtime.year, newtime.month, newtime.day,
                   newtime.hour, newtime.minute)

        # chroot into the dom0 and set the time:
        assert runCmd('chroot %s timeutil setLocalTime "%s"' % (mounts['root'], timestr)) == 0
        assert runCmd("hwclock --utc --systohc") == 0

def setTimeZone(mounts, tz):
    # write the time configuration to the /etc/sysconfig/clock
    # file in dom0:
    timeconfig = open("%s/etc/sysconfig/clock" % mounts['root'], 'w')
    timeconfig.write("ZONE=%s\n" % tz)
    timeconfig.write("UTC=true\n")
    timeconfig.write("ARC=false\n")
    timeconfig.close()

    writeable_files.append('/etc/sysconfig/clock')

    # make the localtime link:
    runCmd("ln -sf /usr/share/zoneinfo/%s %s/etc/localtime" %
           (tz, mounts['root']))
    
def configureNTP(mounts, time_config_method, ntp_servers):
    if time_config_method == 'ntp':
        # read in the old NTP configuration, remove the server
        # lines and write out a new one:
        ntpsconf = open("%s/etc/ntp.conf" % mounts['root'], 'r')
        lines = ntpsconf.readlines()
        ntpsconf.close()

        lines = filter(lambda x: not x.startswith('server '), lines)

        ntpsconf = open("%s/etc/ntp.conf" % mounts['root'], 'w')
        for line in lines:
            ntpsconf.write(line + "\n")
        for server in ntp_servers:
            ntpsconf.write("server %s\n" % server)
        ntpsconf.close()

        # now turn on the ntp service:
        util.runCmd('chroot %s chkconfig ntpd on' % mounts['root'])

def setRootPassword(mounts, root_password):
    # avoid using shell here to get around potential security issues.
    pipe = subprocess.Popen(["/usr/sbin/chroot", "%s" % mounts["root"],
                             "passwd", "--stdin", "root"],
                            stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    pipe.stdin.write(root_password)
    assert pipe.wait() == 0

# write /etc/sysconfig/network-scripts/* files
def configureNetworking(mounts, iface_config, hn_conf):
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
    (alldhcp, mancfg) = iface_config
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
    if hn_conf[0] == True:
        nfd.write("HOSTNAME=%s\n" % hn_conf[1])
    else:
        nfd.write("HOSTNAME=localhost.localdomain\n")
    nfd.close()

    # now symlink from dom0:
    writeable_files.append("/etc/sysconfig/network")

# use kudzu to write initial modprobe-conf:
def writeModprobeConf(mounts):
    util.bindMount("/proc", "%s/proc" % mounts['root'])
    util.bindMount("/sys", "%s/sys" % mounts['root'])
    assert runCmd("chroot %s kudzu -q -k %s" % (mounts['root'], version.KERNEL_VERSION)) == 0
    util.umount("%s/proc" % mounts['root'])
    util.umount("%s/sys" % mounts['root'])
   
# make appropriate symlinks according to writeable_files and writeable_dirs:
def makeSymlinks(mounts):
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
    # Note the behaviour here - we always create a symlink from
    # dom0 to RWS, but we only copy the contents of the dom0 file
    # in the case that a file does NOT already exists in RWS.
    #
    # Think carefully about the upgrade scenario before making
    # changes here.
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

def writeInventory(mounts, default_sr_uuid):
    inv = open("%s/etc/xensource-inventory" % mounts['root'], "w")
    inv.write("PRODUCT_BRAND='%s'\n" % PRODUCT_BRAND)
    inv.write("PRODUCT_NAME='%s'\n" % PRODUCT_NAME)
    inv.write("PRODUCT_VERSION='%s'\n" % PRODUCT_VERSION)
    inv.write("BUILD_NUMBER='%s'\n" % BUILD_NUMBER)
    inv.write("KERNEL_VERSION='%s'\n" % version.KERNEL_VERSION)
    inv.write("XEN_VERSION='%s'\n" % version.XEN_VERSION)
    inv.write("RHEL3X_KERNEL_VERSION='%s'\n" % version.RHEL3X_KERNEL_VERSION)
    inv.write("RHEL4X_KERNEL_VERSION='%s'\n" % version.RHEL4X_KERNEL_VERSION)
    inv.write("SLES9X_KERNEL_VERSION='%s'\n" % version.SLES9X_KERNEL_VERSION)
    inv.write("RHEL3X_KERNEL_RPM='%s'\n" % version.RHEL3X_RPM_NAME)
    inv.write("RHEL4X_KERNEL_RPM='%s'\n" % version.RHEL4X_RPM_NAME)
    inv.write("SLES9X_KERNEL_RPM='%s'\n" % version.SLES9X_RPM_NAME)
    inv.write("RHEL3X_RPM_NAME='%s'\n" % version.RHEL3X_RPM_NAME)
    inv.write("RHEL4X_RPM_NAME='%s'\n" % version.RHEL4X_RPM_NAME)
    inv.write("SLES9X_RPM_NAME='%s'\n" % version.SLES9X_RPM_NAME)
    inv.write("RHEL36_KERNEL_VERSION='%s'\n" % version.RHEL3X_KERNEL_VERSION)
    inv.write("RHEL41_KERNEL_VERSION='%s'\n" % version.RHEL4X_KERNEL_VERSION)
    inv.write("SLES_KERNEL_VERSION='%s'\n" % version.SLES9X_KERNEL_VERSION)
    inv.write("SLES9_KERNEL_VERSION='%s'\n" % version.SLES9X_KERNEL_VERSION)
    inv.write("SLES92_KERNEL_VERSION='%s'\n" % version.SLES9X_KERNEL_VERSION)
    inv.write("INSTALLATION_DATE='%s'\n" % str(datetime.datetime.now()))
    inv.write("DEFAULT_SR='%s'\n" % default_sr_uuid)
    inv.close()

def touchSshAuthorizedKeys(mounts):
    assert runCmd("mkdir -p %s/root/.ssh/" % mounts['root']) == 0
    assert runCmd("touch %s/root/.ssh/authorized_keys" % mounts['root']) == 0


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

def writeLog(primary_disk):
    try: 
        bootnode = getBootPartName(primary_disk)
        if not os.path.exists("/tmp/boot"):
           os.mkdir("/tmp/boot")
        util.mount(bootnode, "/tmp/boot")
        xelogging.writeLog("/tmp/boot/install-log")
        try:
            xelogging.collectLogs("/tmp/boot")
        except:
            pass
        util.umount("/tmp/boot")
    except:
        pass
