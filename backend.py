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
import pickle

import repository
import generalui
import xelogging
import util
import diskutil
import netutil
from util import runCmd
import shutil
import constants
import hardware
import upgrade

# Product version and constants:
import version
from version import *
from constants import *

class InvalidInstallerConfiguration(Exception):
    pass

################################################################################
# FIRST STAGE INSTALLATION:

class Task:
    """
    Represents an install step.
    'fn'   is the function to execute
    'args' is a list of value labels identifying arguments to the function,
    'retursn' is a list of the labels of the return values, or a function
           that, when given the 'args' labels list, returns the list of the
           labels of the return values.
    """

    def __init__(self, fn, args, returns, args_sensitive = False,
                 progress_scale = 1, pass_progress_callback = False):
        self.fn = fn
        self.args = args
        self.returns = returns
        self.args_sensitive = args_sensitive
        self.progress_scale = progress_scale
        self.pass_progress_callback = pass_progress_callback

    def execute(self, answers, progress_callback = lambda x: ()):
        args = self.args(answers)
        assert type(args) == list

        if not self.args_sensitive:
            xelogging.log("TASK: Evaluating %s%s" % (self.fn, args))
        else:
            xelogging.log("TASK: Evaluating %s (sensitive data in arguments: not logging)" % self.fn)

        if self.pass_progress_callback:
            args.insert(0, progress_callback)

        rv = apply(self.fn, args)
        if type(rv) is not tuple:
            rv = (rv,)
        myrv = {}

        if callable(self.returns):
            ret = apply(self.returns, args)
        else:
            ret = self.returns
            
        for r in range(len(ret)):
            myrv[ret[r]] = rv[r]
        return myrv

###
# INSTALL SEQUENCES:
# convenience functions
# A: For each label in params, gives an arg function that evaluates
#    the labels when the function is called (late-binding)
# As: As above but evaulated immediately (early-binding)
# Use A when you require state values as well as the initial input values
A = lambda ans, *params: ( lambda a: [a[param] for param in params] )
As = lambda ans, *params: ( lambda _: [ans[param] for param in params] )

def getPrepSequence(ans):
    seq = []
    if ans['install-type'] == INSTALL_TYPE_FRESH:
        seq += [
            Task(removeBlockingVGs, As(ans, 'guest-disks'), []),
            Task(writeDom0DiskPartitions, As(ans, 'primary-disk'), []),
            ]
        for gd in ans['guest-disks']:
            if gd != ans['primary-disk']:
                seq.append(Task(writeGuestDiskPartitions,
                                (lambda mygd: (lambda _: [mygd]))(gd), []))
        seq += [
            Task(prepareStorageRepository, As(ans, 'primary-disk', 'guest-disks'), ['default-sr-uuid']),
            ]
    elif ans['install-type'] == INSTALL_TYPE_REINSTALL:
        seq.append(Task(getUpgrader, A(ans, 'installation-to-overwrite'), ['upgrader']))
        if ans['backup-existing-installation']:
            seq.append(Task(backupExisting, As(ans, 'installation-to-overwrite'), []))
        seq.append(Task(prepareUpgrade, A(ans, 'upgrader'), lambda upgrader: upgrader.prepStateChanges))

    seq += [
        Task(createDom0DiskFilesystems, A(ans, 'primary-disk'), []),
        Task(mountVolumes, A(ans, 'primary-disk', 'cleanup'), ['mounts', 'cleanup']),
        ]

    return seq

def getRepoSequence(ans, repos):
    seq = []
    for repo in repos:
        seq.append(Task(repo.accessor().start, lambda x: [], []))
        for package in repo:
            seq += [
                # have to bind package at the current value, hence the myp nonsense:
                Task(installPackage, (lambda myp: lambda a: [a['mounts'], myp])(package), [],
                     progress_scale = (package.size / 100),
                     pass_progress_callback = True)
                ]
        seq.append(Task(repo.accessor().finish, lambda x: [], []))
    return seq

def getFinalisationSequence(ans):
    seq = [
        Task(installGrub, A(ans, 'mounts', 'primary-disk'), []),
        Task(doDepmod, A(ans, 'mounts'), []),
        Task(writeResolvConf, A(ans, 'mounts', 'manual-hostname', 'manual-nameservers'), []),
        Task(writeKeyboardConfiguration, A(ans, 'mounts', 'keymap'), []),
        Task(configureNetworking, A(ans, 'mounts', 'iface-configuration', 'manual-hostname'), []),
        Task(prepareSwapfile, A(ans, 'mounts'), []),
        Task(writeFstab, A(ans, 'mounts'), []),
        Task(writeSmtab, A(ans, 'mounts', 'default-sr-uuid'), []),
        Task(enableSM, A(ans, 'mounts'), []),
        Task(enableAgent, A(ans, 'mounts'), []),
        Task(writeModprobeConf, A(ans, 'mounts'), []),
        Task(mkinitrd, A(ans, 'mounts'), []),
        Task(writeInventory, A(ans, 'mounts', 'primary-disk', 'default-sr-uuid'), []),
        Task(touchSshAuthorizedKeys, A(ans, 'mounts'), []),
        Task(setRootPassword, A(ans, 'mounts', 'root-password'), []),
        Task(setTimeZone, A(ans, 'mounts', 'timezone'), []),
        ]
    if ans['time-config-method'] == 'ntp':
        seq.append( Task(configureNTP, A(ans, 'mounts', 'ntp-servers'), []) )
    elif ans['time-config-method'] == 'manual':
        seq.append( Task(configureTimeManually, A(ans, 'mounts', 'ui'), []) )
    if ans.has_key('post-install-script'):
        seq.append( Task(runScripts, lambda a: [a['mounts'], [a['post-install-script']]], []) )
    seq += [
        Task(umountVolumes, A(ans, 'mounts', 'cleanup'), ['cleanup']),

        Task(writeLog, A(ans, 'primary-disk'), [] ),
        ]

    return seq

def prettyLogAnswers(answers):
    for a in answers:
        if a == 'root-password':
            val = '< not printed >'
        else:
            val = answers[a]
        xelogging.log("%s := %s %s" % (a, val, type(val)))

def executeSequence(sequence, seq_name, answers_pristine, ui, cleanup):
    answers = answers_pristine.copy()
    answers['cleanup'] = []
    answers['ui'] = ui

    progress_total = reduce(lambda x,y: x + y,
                            [task.progress_scale for task in sequence])

    pd = None
    if ui:
        pd = ui.initProgressDialog(
            "Installing %s" % PRODUCT_BRAND,
            seq_name, progress_total
            )
    xelogging.log("DISPATCH: NEW PHASE: %s" % seq_name)

    def doCleanup(actions):
        for tag, f, a in actions:
            try:
                apply(f,a)
            except:
                xelogging.log("FAILED to perform cleanup action %s" % tag)

    def progressCallback(x):
        if ui:
            ui.displayProgressDialog(current + x, pd)
        
    try:
        current = 0
        for item in sequence:
            if pd:
                ui.displayProgressDialog(current, pd)
            updated_state = item.execute(answers, progressCallback)
            if len(updated_state) > 0:
                xelogging.log(
                    "DISPATCH: Updated state: %s" %
                    str.join("; ", ["%s -> %s" % (v, updated_state[v]) for v in updated_state.keys()])
                    )
                for state_item in updated_state:
                    answers[state_item] = updated_state[state_item]

            current = current + item.progress_scale
    except:
        doCleanup(answers['cleanup'])
        raise
    else:
        if ui and pd:
            ui.clearModelessDialog()

        if cleanup:
            doCleanup(answers['cleanup'])
            del answers['cleanup']

    return answers

class UnkownInstallMediaType(Exception):
    pass

def performInstallation(answers, ui_package):
    xelogging.log("INPUT ANSWERS DICTIONARY:")
    prettyLogAnswers(answers)

    # perform installation:
    prep_seq = getPrepSequence(answers)
    new_ans = executeSequence(prep_seq, "Preparing for Installation...", answers, ui_package, False)

    # install from main repositories:
    def handleRepos(repos, ans):
        if len(repos) == 0:
            raise RuntimeError, "No repository found at the specified location."
        elif len(repos) == 1:
            seq_name = "Installing from " + repositories[0].name() + "..."
        else:
            seq_name = "Installing %s..." % version.PRODUCT_BRAND
        repo_seq = getRepoSequence(ans, repos)
        new_ans = executeSequence(repo_seq, seq_name, ans, ui_package, False)
        return new_ans

    done = False
    installed_repo_ids = []
    while not done:
        all_repositories = repository.repositoriesFromDefinition(
            answers['source-media'], answers['source-address']
            )

        # only install repositorie s we've not already installed:
        repositories = filter(lambda r: r.identifier() not in installed_repo_ids,
                              all_repositories)
        new_ans = handleRepos(repositories, new_ans)
        installed_repo_ids.extend([ r.identifier() for r in repositories] )

        # get more media?
        done = not (answers.has_key('more-media') and answers['more-media'])
        if not done:
            util.runCmd2(['/usr/bin/eject'])
            done = not ui_package.more_media_sequence(installed_repo_ids)

    # install from driver repositories, if any:
    for driver_repo_def in answers['extra-repos']:
        xelogging.log("(Now installing from driver repositories that were previously stashed.)")
        rtype, rloc = driver_repo_def
        all_repos = repository.repositoriesFromDefinition(rtype, rloc)
        repos = filter(lambda r: r.identifier() not in installed_repo_ids,
                       all_repos)
        new_ans = handleRepos(repos, new_ans)
        installed_repo_ids.extend([ r.identifier() for r in repositories])

    # complete the installation:
    fin_seq = getFinalisationSequence(new_ans)
    new_ans = executeSequence(fin_seq, "Completing installation...", new_ans, ui_package, True)

    if answers['source-media'] == 'local':
        util.runCmd2(['/usr/bin/eject'])

def installPackage(progress_callback, mounts, package):
    package.install(mounts['root'], progress_callback)

# Time configuration:
def configureNTP(mounts, ntp_servers):
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

def configureTimeManually(mounts, ui_package):
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

def runScripts(mounts, scripts):
    for script in scripts:
        try:
            xelogging.log("Running script: %s" % script)
            util.fetchFile(script, "/tmp/script")
            util.runCmd2(["chmod", "a+x" ,"/tmp/script"])
            util.runCmd2(["/tmp/script", mounts['root']])
            os.unlink("/tmp/script")
        except Exception, e:
            xelogging.log("Failed to run script: %s" % script)
            xelogging.log(e)

def removeBlockingVGs(disks):
    for vg in diskutil.findProblematicVGs(disks):
        util.runCmd2(['vgreduce', '--removemissing', vg])
        util.runCmd2(['lvremove', vg])
        util.runCmd2(['vgremove', vg])

#def getSwapPartName(disk):
#    global swap_name, vgname
#    return "/dev/%s/%s" % (vgname, swap_name)

def getRootPartNumber(disk):
    return 1

def getRootPartName(disk):
    return diskutil.determinePartitionName(disk, getRootPartNumber(disk))

def getBackupPartNumber(disk):
    return 2

def getBackupPartName(disk):
    return diskutil.determinePartitionName(disk, getBackupPartNumber(disk))

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

def prepareStorageRepository(primary_disk, guest_disks):
    if len(guest_disks) == 0:
        xelogging.log("Not creating a default storage repository.")
        return None

    xelogging.log("Preparing default storage repository...")
    sr_uuid = util.getUUID()

    def sr_partition(disk):
        if disk == primary_disk:
            return diskutil.determinePartitionName(disk, 3)
        else:
            return diskutil.determinePartitionName(disk, 1)

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

def __mkinitrd(mounts, kernel_version, link):
    modules_list = ["--with=%s" % x for x in hardware.getModuleOrder()]

    modules_string = " ".join(modules_list)
    output_file = "/boot/initrd-%s.img" % kernel_version
    
    cmd = "mkinitrd %s %s %s" % (modules_string, output_file, kernel_version)
    
    if util.runCmd("chroot %s %s" % (mounts['root'], cmd)) != 0:
        raise RuntimeError, "Failed to create initrd for %s.  This is often due to using an installer that is not the same version of %s as your installation source." % (kernel_version, version.PRODUCT_BRAND)
    if link:
        util.runCmd("ln -sf %s %s/boot/initrd-2.6-xen.img" % (output_file, mounts['root']))

def mkinitrd(mounts):
    __mkinitrd(mounts, version.KERNEL_VERSION, True)
    __mkinitrd(mounts, version.KDUMP_VERSION, False)

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
        grubconf += "serial --unit=0 --speed=115200\n"
        grubconf += "terminal --timeout=10 console serial\n"
        grubconf += "default 1\n"
    else: # not tty.startswith("/dev/ttyS") or rc != 0
        grubconf += "terminal console\n"
        grubconf += "default 0\n"
        
    grubconf += "timeout 5\n\n"

    # splash screen?
    # (Disabled for now since GRUB messes up on the serial line when
    # this is enabled.)
    if hasSplash and False:
        grubconf += "\n"
        grubconf += "foreground = 000000\n"
        grubconf += "background = cccccc\n"
        grubconf += "splashimage = %s/xs-splash.xpm.gz\n\n" % rootdisk

    # Generic boot entries first
    grubconf += "title %s\n" % PRODUCT_BRAND
    grubconf += "   root %s\n" % rootdisk
    grubconf += "   kernel /boot/xen.gz dom0_mem=524288 lowmem_emergency_pool=16M crashkernel=32M@32M\n"
    grubconf += "   module /boot/vmlinuz-2.6-xen root=LABEL=%s ro console=tty0\n" % (constants.rootfs_label)
    grubconf += "   module /boot/initrd-2.6-xen.img\n"

    grubconf += "title %s (Serial)\n" % PRODUCT_BRAND
    grubconf += "   root %s\n" % rootdisk
    grubconf += "   kernel /boot/xen.gz com1=115200,8n1 console=com1,tty dom0_mem=524288 lowmem_emergency_pool=16M crashkernel=32M@32M\n"
    grubconf += "   module /boot/vmlinuz-2.6-xen root=LABEL=%s ro console=tty0 console=ttyS0,115200n8\n" % (constants.rootfs_label)
    grubconf += "   module /boot/initrd-2.6-xen.img\n"
    
    grubconf += "title %s in Safe Mode\n" % PRODUCT_BRAND
    grubconf += "   root %s\n" % rootdisk
    grubconf += "   kernel /boot/xen.gz nosmp noreboot noirqbalance acpi=off noapic dom0_mem=524288 com1=115200,8n1 console=com1,tty\n"
    grubconf += "   module /boot/vmlinuz-2.6-xen nousb root=LABEL=%s ro console=tty0 console=ttyS0,115200n8\n" % (constants.rootfs_label)
    grubconf += "   module /boot/initrd-2.6-xen.img\n"

    # Entries with specific versions
    grubconf += "title %s (Xen %s / Linux %s)\n" % (PRODUCT_BRAND,version.XEN_VERSION,version.KERNEL_VERSION)
    grubconf += "   root %s\n" % rootdisk
    grubconf += "   kernel /boot/xen-%s.gz dom0_mem=524288 lowmem_emergency_pool=16M crashkernel=32M@32M\n" % version.XEN_VERSION
    grubconf += "   module /boot/vmlinuz-%s root=LABEL=%s ro console=tty0\n" % (version.KERNEL_VERSION, constants.rootfs_label)
    grubconf += "   module /boot/initrd-%s.img\n" % version.KERNEL_VERSION

    grubconf += "title %s (Serial, Xen %s / Linux %s)\n" % (PRODUCT_BRAND,version.XEN_VERSION,version.KERNEL_VERSION)
    grubconf += "   root %s\n" % rootdisk
    grubconf += "   kernel /boot/xen-%s.gz com1=115200,8n1 console=com1,tty dom0_mem=524288 lowmem_emergency_pool=16M crashkernel=32M@32M\n" % version.XEN_VERSION
    grubconf += "   module /boot/vmlinuz-%s root=LABEL=%s ro console=tty0 console=ttyS0,115200n8\n" % (version.KERNEL_VERSION, constants.rootfs_label)
    grubconf += "   module /boot/initrd-%s.img\n" % version.KERNEL_VERSION

    # write the GRUB configuration:
    util.assertDir("%s/grub" % mounts['boot'])
    menulst_file = open("%s/grub/menu.lst" % mounts['boot'], "w")
    menulst_file.write(grubconf)
    menulst_file.close()

    # now perform our own installation, onto the MBR of hd0:
    assert runCmd("chroot %s grub-install --no-floppy --recheck '(%s)'" % (mounts['root'], grubroot)) == 0

    # done installing - undo our extra mounts:
    util.umount("%s/dev" % mounts['root'])
    # try to unlink /proc/mounts in case /etc/mtab is a symlink
    if os.path.exists("%s/proc/mounts" % mounts['root']):
        os.unlink("%s/proc/mounts" % mounts['root'])
    util.umount("%s/sys" % mounts['root'])
    util.umount("%s/tmp" % mounts['root'])

##########
# mounting and unmounting of various volumes

def mountVolumes(primary_disk, cleanup):
    mounts = {'root': '/tmp/root',
              'boot': '/tmp/root/boot'}

    rootp = getRootPartName(primary_disk)
    util.assertDir('/tmp/root')
    util.mount(rootp, mounts['root'])

    new_cleanup = cleanup + [ ("umount-/tmp/root", util.umount, (mounts['root'], )) ]
    return mounts, new_cleanup
 
def umountVolumes(mounts, cleanup, force = False):
    util.umount(mounts['root'])
    cleanup = filter(lambda (tag, _, __): tag != "umount-%s" % mounts['root'],
                     cleanup)
    return cleanup

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
                  'chkconfig', '--add', 'xend'])
    util.runCmd2(['chroot', mounts['root'],
                  'chkconfig', '--add', 'xendomains'])
    util.runCmd2(['chroot', mounts['root'],
                  'chkconfig', '--add', 'xenagentd'])

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


def setTimeZone(mounts, tz):
    # write the time configuration to the /etc/sysconfig/clock
    # file in dom0:
    timeconfig = open("%s/etc/sysconfig/clock" % mounts['root'], 'w')
    timeconfig.write("ZONE=%s\n" % tz)
    timeconfig.write("UTC=true\n")
    timeconfig.write("ARC=false\n")
    timeconfig.close()

    # make the localtime link:
    runCmd("ln -sf /usr/share/zoneinfo/%s %s/etc/localtime" %
           (tz, mounts['root']))
    

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
        fd.write("TYPE=Ethernet\n")
        if hwaddr:
            fd.write("HWADDR=%s\n" % hwaddr)

    def writeDisabledConfigFile(fd, device, hwaddr = None):
        fd.write("DEVICE=%s\n" % device)
        fd.write("ONBOOT=no\n")
        fd.write("TYPE=Ethernet\n")
        if hwaddr:
            fd.write("HWADDR=%s\n" % hwaddr)

    def writeConfigFileBridgeDetails(fd, bridge):
        fd.write("BRIDGE=%s\n" % bridge)
        fd.write("LINKDELAY=5\n")

    def writeBridgeConfigFile(fd, bridge):
        fd.write("DEVICE=%s\n" % bridge)
        fd.write("ONBOOT=yes\n")
        fd.write("TYPE=Bridge\n")
        fd.write("DELAY=0\n")
        fd.write("STP=off\n")

    # are we all DHCP?
    (alldhcp, mancfg) = iface_config
    if alldhcp:
        ifaces = netutil.getNetifList()
        for i in ifaces:
            b = i.replace("eth", "xenbr")
            ifcfd = open("%s/etc/sysconfig/network-scripts/ifcfg-%s" % (mounts['root'], i), "w")
            writeDHCPConfigFile(ifcfd, i, netutil.getHWAddr(i))
            writeConfigFileBridgeDetails(ifcfd, b)
            if check_link_down_hack:
                ifcfd.write("check_link_down() { return 1 ; }\n")
            ifcfd.close()
            brcfd = open("%s/etc/sysconfig/network-scripts/ifcfg-%s" % (mounts['root'], b), "w")
            writeBridgeConfigFile(brcfd, b)
            if check_link_down_hack:
                brcfd.write("check_link_down() { return 1 ; }\n")
            brcfd.close()
    else:
        # no - go through each interface manually:
        for i in mancfg:
            b = i.replace("eth", "xenbr")
            iface = mancfg[i]
            ifcfd = open("%s/etc/sysconfig/network-scripts/ifcfg-%s" % (mounts['root'], i), "w")
            if not iface['enabled']:
                writeDisabledConfigFile(ifcfd, i, netutil.getHWAddr(i))
                writeConfigFileBridgeDetails(ifcfd, i.replace("eth", "xenbr"))
            else:
                if iface['use-dhcp']:
                    writeDHCPConfigFile(ifcfd, i, netutil.getHWAddr(i))
                    writeConfigFileBridgeDetails(ifcfd, b)
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
                    writeConfigFileBridgeDetails(ifcfd, b)

            if check_link_down_hack:
                ifcfd.write("check_link_down() { return 1 ; }\n")
            ifcfd.close()

            brcfd = open("%s/etc/sysconfig/network-scripts/ifcfg-%s" % (mounts['root'], b), "w")
            writeBridgeConfigFile(brcfd, b)
            if check_link_down_hack:
                brcfd.write("check_link_down() { return 1 ; }\n")
            brcfd.close()

    # write the configuration file for the loopback interface
    out = open("%s/etc/sysconfig/network-scripts/ifcfg-lo" % mounts['root'], "w")
    out.write("DEVICE=lo\n")
    out.write("IPADDR=127.0.0.1\n")
    out.write("NETMASK=255.0.0.0\n")
    out.write("NETWORK=127.0.0.0\n")
    out.write("BROADCAST=127.255.255.255\n")
    out.write("ONBOOT=yes\n")
    out.write("NAME=loopback\n")
    out.close()

    # now we need to write /etc/sysconfig/network
    nfd = open("%s/etc/sysconfig/network" % mounts["root"], "w")
    nfd.write("NETWORKING=yes\n")
    if hn_conf[0]:
        nfd.write("HOSTNAME=%s\n" % hn_conf[1])
    else:
        nfd.write("HOSTNAME=localhost.localdomain\n")
    nfd.write("PMAP_ARGS=-l\n")
    nfd.close()

# use kudzu to write initial modprobe-conf:
def writeModprobeConf(mounts):
    util.bindMount("/proc", "%s/proc" % mounts['root'])
    util.bindMount("/sys", "%s/sys" % mounts['root'])
    assert runCmd("chroot %s kudzu -q -k %s" % (mounts['root'], version.KERNEL_VERSION)) == 0
    util.umount("%s/proc" % mounts['root'])
    util.umount("%s/sys" % mounts['root'])

def writeInventory(mounts, primary_disk, default_sr_uuid):
    inv = open(os.path.join(mounts['root'], constants.INVENTORY_FILE), "w")
    installID = util.getUUID()
    inv.write("PRODUCT_BRAND='%s'\n" % PRODUCT_BRAND)
    inv.write("PRODUCT_NAME='%s'\n" % PRODUCT_NAME)
    inv.write("PRODUCT_VERSION='%s'\n" % PRODUCT_VERSION)
    inv.write("BUILD_NUMBER='%s'\n" % BUILD_NUMBER)
    inv.write("KERNEL_VERSION='%s'\n" % version.KERNEL_VERSION)
    inv.write("XEN_VERSION='%s'\n" % version.XEN_VERSION)
    inv.write("INSTALLATION_DATE='%s'\n" % str(datetime.datetime.now()))
    inv.write("DEFAULT_SR='%s'\n" % default_sr_uuid)
    inv.write("PRIMARY_DISK='%s'\n" % primary_disk)
    inv.write("BACKUP_PARTITION='%s'\n" % getBackupPartName(primary_disk))
    inv.write("INSTALLATION_UUID='%s'\n" % installID)
    inv.close()

def touchSshAuthorizedKeys(mounts):
    assert runCmd("mkdir -p %s/root/.ssh/" % mounts['root']) == 0
    assert runCmd("touch %s/root/.ssh/authorized_keys" % mounts['root']) == 0

def backupExisting(existing):
    primary_partition = getRootPartName(existing.primary_disk)
    backup_partition = getBackupPartName(existing.primary_disk)

    # format the backup partition:
    util.runCmd2(['mkfs.ext3', backup_partition])

    # copy the files across:
    primary_mount = '/tmp/backup/primary'
    backup_mount  = '/tmp/backup/backup'
    for mnt in [primary_mount, backup_mount]:
        util.assertDir(mnt)
    try:
        util.mount(primary_partition, primary_mount)
        util.mount(backup_partition,  backup_mount)
        cmd = ['cp', '-a'] + \
              [ os.path.join(primary_mount, x) for x in os.listdir(primary_mount) ] + \
              ['%s/' % backup_mount]
        util.runCmd2(cmd)
    finally:
        for mnt in [primary_mount, backup_mount]:
            util.umount(mnt)


################################################################################
# OTHER HELPERS

def getGrUBDevice(disk, mounts):
    devicemap_path = "/tmp/device.map"
    outerpath = "%s%s" % (mounts['root'], devicemap_path)
    
    # if the device map doesn't exist, make one up:
    if not os.path.isfile(devicemap_path):
        runCmd("echo '' | chroot %s grub --no-floppy --device-map %s --batch" %
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

# This function is not supposed to throw exceptions so that it can be used
# within the main exception handler.
def writeLog(primary_disk):
    try: 
        bootnode = getRootPartName(primary_disk)
        if not os.path.exists("/tmp/mnt"):
           os.mkdir("/tmp/mnt")
        util.mount(bootnode, "/tmp/mnt")
        log_location = "/tmp/mnt/root"
        if os.path.islink(log_location):
            log_location = os.path.join("/tmp/mnt", os.readlink(log_location).lstrip("/"))
        if not os.path.exists(log_location):
            os.mkdir(log_location)
        xelogging.writeLog(os.path.join(log_location, "install-log"))
        try:
            xelogging.collectLogs(log_location)
        except:
            pass
        try:
            util.umount("/tmp/mnt")
        except:
            pass
    except:
        pass

def getUpgrader(source):
    """ Returns an appropriate upgrader for a given source. """
    return upgrade.getUpgrader(source)

def prepareUpgrade(upgrader):
    """ Gets required state from existing installation. """
    return upgrader.prepareUpgrade()
