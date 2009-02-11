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
import init_constants

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
    'returns' is a list of the labels of the return values, or a function
           that, when given the 'args' labels list, returns the list of the
           labels of the return values.
    """

    def __init__(self, fn, args, returns, args_sensitive = False,
                 progress_scale = 1, pass_progress_callback = False,
                 progress_text = None):
        self.fn = fn
        self.args = args
        self.returns = returns
        self.args_sensitive = args_sensitive
        self.progress_scale = progress_scale
        self.pass_progress_callback = pass_progress_callback
        self.progress_text = progress_text

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
# As: As above but evaluated immediately (early-binding)
# Use A when you require state values as well as the initial input values
A = lambda ans, *params: ( lambda a: [a[param] for param in params] )
As = lambda ans, *params: ( lambda _: [ans[param] for param in params] )

def getPrepSequence(ans):
    seq = [ 
        Task(util.getUUID, As(ans), ['installation-uuid']),
        Task(util.getUUID, As(ans), ['control-domain-uuid']),
        ]
    if ans['install-type'] == INSTALL_TYPE_FRESH:
        seq += [
            Task(removeBlockingVGs, As(ans, 'guest-disks'), []),
            Task(writeDom0DiskPartitions, As(ans, 'primary-disk'), []),
            ]
        for gd in ans['guest-disks']:
            if gd != ans['primary-disk']:
                seq.append(Task(writeGuestDiskPartitions,
                                (lambda mygd: (lambda _: [mygd]))(gd), []))
    elif ans['install-type'] == INSTALL_TYPE_REINSTALL:
        seq.append(Task(getUpgrader, A(ans, 'installation-to-overwrite'), ['upgrader']))
        if ans['backup-existing-installation']:
            seq.append(Task(backupExisting, As(ans, 'installation-to-overwrite'), [],
                            progress_text = "Backing up existing installation..."))
        seq.append(Task(prepareUpgrade, lambda a: [ a['upgrader'] ] + [ a[x] for x in a['upgrader'].prepUpgradeArgs ], lambda upgrader, *a: upgrader.prepStateChanges))

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
                     pass_progress_callback = True,
                     progress_text = "Installing from %s..." % repo.name())
                ]
        seq.append(Task(repo.accessor().finish, lambda x: [], []))
    return seq

def getFinalisationSequence(ans):
    seq = [
        Task(installBootLoader, A(ans, 'mounts', 'primary-disk', 'bootloader', 'serial-console', 'boot-serial'), []),
        Task(doDepmod, A(ans, 'mounts'), []),
        Task(writeResolvConf, A(ans, 'mounts', 'manual-hostname', 'manual-nameservers'), []),
        Task(writeKeyboardConfiguration, A(ans, 'mounts', 'keymap'), []),
        Task(writeModprobeConf, A(ans, 'mounts'), []),
        Task(configureNetworking, A(ans, 'mounts', 'net-admin-interface', 'net-admin-bridge', 'net-admin-configuration', 'manual-hostname', 'manual-nameservers', 'network-hardware', 'preserve-settings', 'iscsi-iface'), []),
        Task(prepareSwapfile, A(ans, 'mounts'), []),
        Task(writeFstab, A(ans, 'mounts'), []),
        Task(enableAgent, A(ans, 'mounts'), []),
        Task(mkinitrd, A(ans, 'mounts', 'iscsi-iface'), []),
        Task(writeInventory, A(ans, 'installation-uuid', 'control-domain-uuid', 'mounts', 'primary-disk', 'guest-disks', 'net-admin-bridge'), []),
        Task(touchSshAuthorizedKeys, A(ans, 'mounts'), []),
        Task(setRootPassword, A(ans, 'mounts', 'root-password', 'root-password-type'), [], args_sensitive = True),
        Task(setTimeZone, A(ans, 'mounts', 'timezone'), []),
        ]

    if ans.has_key('install-xen64') and ans['install-xen64']:
        seq.append(Task(installXen64, A(ans, 'mounts'), []))

    # on fresh installs, prepare the storage repository as required:
    if ans['install-type'] == INSTALL_TYPE_FRESH:
        seq += [
            Task(prepareStorageRepositories, A(ans, 'operation', 'mounts', 'primary-disk', 'guest-disks', 'sr-type'), []),
            ]
    if ans['time-config-method'] == 'ntp':
        seq.append( Task(configureNTP, A(ans, 'mounts', 'ntp-servers'), []) )
    elif ans['time-config-method'] == 'manual':
        seq.append( Task(configureTimeManually, A(ans, 'mounts', 'ui'), []) )
    if ans.has_key('post-install-script'):
        seq.append( Task(runScripts, lambda a: [a['mounts'], [a['post-install-script']]], []) )
    # complete upgrade if appropriate:
    if ans['install-type'] == constants.INSTALL_TYPE_REINSTALL:
        seq.append( Task(completeUpgrade, lambda a: [ a['upgrader'] ] + [ a[x] for x in a['upgrader'].completeUpgradeArgs ], []) )

    seq += [
        Task(writei18n, A(ans, 'mounts'), []),
        Task(umountVolumes, A(ans, 'mounts', 'cleanup'), ['cleanup']),
        Task(writeLog, A(ans, 'primary-disk'), [])
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
        pd = ui.progress.initProgressDialog(
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
            ui.progress.displayProgressDialog(current + x, pd)
        
    try:
        current = 0
        for item in sequence:
            if pd:
                if item.progress_text:
                    text = item.progress_text
                else:
                    text = seq_name

                ui.progress.displayProgressDialog(current, pd, updated_text = text)
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
            ui.progress.clearModelessDialog()

        if cleanup:
            doCleanup(answers['cleanup'])
            del answers['cleanup']

    return answers

class UnkownInstallMediaType(Exception):
    pass

def performInstallation(answers, ui_package):
    xelogging.log("INPUT ANSWERS DICTIONARY:")
    prettyLogAnswers(answers)

    # update the settings:
    if answers['install-type'] == constants.INSTALL_TYPE_REINSTALL:
        if answers['preserve-settings'] == True:
            xelogging.log("Updating answers dictionary based on existing installation")
            answers.update(answers['installation-to-overwrite'].readSettings())
            xelogging.log("UPDATED ANSWERS DICTIONARY:")
            prettyLogAnswers(answers)
        else:
            # still need to have same keys present in the reinstall (non upgrade)
            # case, but we'll set them to None:
            answers['preserved-license-data'] = None

        # we require guest-disks to always be present, but it is not used other than
        # for status reporting when doing a re-install, so set it to empty rather than
        # trying to guess what the correct value should be.
        answers['guest-disks'] = []
    else:
        if not answers.has_key('sr-type'):
            answers['sr-type'] = constants.SR_TYPE_LVM

    if not answers.has_key('bootloader'):
        answers['bootloader'] = constants.BOOTLOADER_TYPE_EXTLINUX

    # work out whether primary disk is iscsi, and if so save the iface used to talk to it
    if answers.has_key('primary-disk'):
        primary_disk = answers['primary-disk'] # INSTALL CASE
    else:
        primary_disk = answers['installation-to-overwrite'].primary_disk # UPGRADE CASE
        
    if diskutil.is_iscsi(primary_disk):
        answers['iscsi-target-ip'], \
        answers['iscsi-target-port'], \
        answers['iscsi-iface'] = \
            diskutil.iscsi_address_port_netdev(primary_disk)
    else:
        answers['iscsi-target-ip'], \
        answers['iscsi-target-port'], \
        answers['iscsi-iface'] = \
            (None,None,None)

    # Slight hack: we need to write the bridge name to xensource-inventory 
    # further down; compute it here based on the admin interface name if we
    # haven't already recorded it as part of reading settings from an upgrade:
    if not answers.has_key('net-admin-bridge'):
        assert answers['net-admin-interface'].startswith("eth")
        answers['net-admin-bridge'] = "xenbr%s" % answers['net-admin-interface'][3:]
 
    # perform installation:
    prep_seq = getPrepSequence(answers)
    new_ans = executeSequence(prep_seq, "Preparing for installation...", answers, ui_package, False)

    # install from main repositories:
    def handleRepos(repos, ans):
        if len(repos) == 0:
            raise RuntimeError, "No repository found at the specified location."
        else:
            seq_name = "Reading package information..."
        repo_seq = getRepoSequence(ans, repos)
        new_ans = executeSequence(repo_seq, seq_name, ans, ui_package, False)
        return new_ans

    done = False
    installed_repo_ids = []
    while not done:
        all_repositories = repository.repositoriesFromDefinition(
            answers['source-media'], answers['source-address']
            )

        # only install repositories we've not already installed:
        repositories = filter(lambda r: r.identifier() not in installed_repo_ids,
                              all_repositories)
        if len(repositories) > 0:
            new_ans = handleRepos(repositories, new_ans)
            installed_repo_ids.extend([ r.identifier() for r in repositories] )

        # get more media?
        done = not (answers.has_key('more-media') and answers['more-media'] and answers['source-media'] == 'local')
        if not done:
            # find repositories that we installed from removable media:
            for r in repositories:
                if r.accessor().canEject():
                    r.accessor().eject()
            accept_media, ask_again = ui_package.installer.more_media_sequence(installed_repo_ids)
            done = not accept_media
            answers['more-media'] = ask_again

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
        for r in repositories:
            if r.accessor().canEject():
                r.accessor().eject()

def installPackage(progress_callback, mounts, package):
    package.install(mounts['root'], progress_callback)

# Time configuration:
def configureNTP(mounts, ntp_servers):
    # If NTP servers were specified, update the NTP config file:
    if len(ntp_servers) > 0:
        ntpsconf = open("%s/etc/ntp.conf" % mounts['root'], 'r')
        lines = ntpsconf.readlines()
        ntpsconf.close()

        lines = filter(lambda x: not x.startswith('server '), lines)

        ntpsconf = open("%s/etc/ntp.conf" % mounts['root'], 'w')
        for line in lines:
            ntpsconf.write(line)
        for server in ntp_servers:
            ntpsconf.write("server %s\n" % server)
        ntpsconf.close()

    # now turn on the ntp service:
    util.runCmd2(['chroot', mounts['root'], 'chkconfig', 'ntpd', 'on'])

def configureTimeManually(mounts, ui_package):
    # display the Set Time dialog in the chosen UI:
    rc, time = util.runCmd2(['chroot', mounts['root'], 'timeutil', 'getLocalTime'], with_stdout = True)
    answers = {}
    ui_package.installer.screens.set_time(answers, util.parseTime(time))
        
    newtime = answers['localtime']
    timestr = "%04d-%02d-%02d %02d:%02d:00" % \
              (newtime.year, newtime.month, newtime.day,
               newtime.hour, newtime.minute)
        
    # chroot into the dom0 and set the time:
    assert util.runCmd2(['chroot', mounts['root'], 'timeutil', 'setLocalTime', '%s' % timestr]) == 0
    assert util.runCmd2(['hwclock', '--utc', '--systohc']) == 0

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

def getRootPartNumber(disk):
    return RETAIL_ROOT_PARTITION_NUMBER

def getRootPartName(disk):
    return diskutil.determinePartitionName(disk, getRootPartNumber(disk))

def getBackupPartNumber(disk):
    return RETAIL_BACKUP_PARTITION_NUMBER

def getBackupPartName(disk):
    return diskutil.determinePartitionName(disk, getBackupPartNumber(disk))

###
# Functions to write partition tables to disk

# TODO - take into account service partitions
def writeDom0DiskPartitions(disk):
    # we really don't want to screw this up...
    assert type(disk) == str
    assert disk[:5] == '/dev/'

    if not os.path.exists(disk):
        raise RuntimeError, "The disk %s could not be found." % disk

    # partition the disk:
    diskutil.writePartitionTable(disk, [root_size, root_size, -1])
    diskutil.makeActivePartition(disk, constants.RETAIL_ROOT_PARTITION_NUMBER)

def writeGuestDiskPartitions(disk):
    # we really don't want to screw this up...
    assert type(disk) == str
    assert disk[:5] == '/dev/'

    diskutil.clearDiskPartitions(disk)

def getSRPhysDevs(primary_disk, guest_disks, is_oem = False):
    if is_oem:
        pd_sr_part = constants.OEMHDD_SR_PARTITION_NUMBER
    else:
        pd_sr_part = constants.RETAIL_SR_PARTITION_NUMBER

    def sr_partition(disk):
        if disk == primary_disk:
            return diskutil.determinePartitionName(disk, pd_sr_part)
        else:
            return disk

    return [sr_partition(disk) for disk in guest_disks]

def writeFirstbootFile(operation, mounts, filename, content):

    if init_constants.operationIsOEMInstall(operation):
        directory = os.path.join(mounts['state'], "installer", constants.FIRSTBOOT_DATA_DIR)
    else:
        directory = os.path.join(mounts['root'], constants.FIRSTBOOT_DATA_DIR)

    util.assertDir(directory) # Creates the directory if not present
    fd = open(os.path.join(directory, filename), 'w')
    for line in content:
        print >>fd, line
    fd.close()

def disableFirstbootScript(operation, mounts, filename):
    xelogging.log('Disabling firstboot script '+filename)

    if init_constants.operationIsOEMInstall(operation):
        directory = os.path.join(mounts['state'], "installer", constants.FIRSTBOOT_DATA_DIR)
    else:
        directory = os.path.join(mounts['root'], constants.FIRSTBOOT_DATA_DIR)
    log_directory = directory + '/../log'
    state_directory = directory + '/../state'
    
    util.assertDir(log_directory) # Creates the directory if not present
    fd = open(os.path.join(log_directory, filename), 'w')
    print >>fd, '# This firstboot script was disabled by the installer and did not run'
    fd.close()
    
    util.assertDir(state_directory) # Creates the directory if not present
    fd = open(os.path.join(state_directory, filename), 'w')
    print >>fd, 'success'
    print >>fd, '# This firstboot script was disabled by the installer and did not run'
    fd.close()

def prepareNetworking(operation, mounts, interface, config, nameservers, nethw):
    if config is None:
        admin_mac = ''
        network_content = [
            "ADMIN_INTERFACE=''",
            "INTERFACES='%s'" % ' '.join( [ x.hwaddr for x in nethw.values() ] )
        ]
    else:
        admin_mac = config.get('hwaddr', '')
        network_content = [
            "ADMIN_INTERFACE='%s'" % admin_mac,
            "INTERFACES='%s'" % ' '.join( [ x.hwaddr for x in nethw.values() ] )
        ]
    xelogging.log('Writing firstboot network.conf '+', '.join(network_content))
    writeFirstbootFile(operation, mounts, 'network.conf', network_content)
        
    for label, net_instance in nethw.iteritems():
        mac = net_instance.hwaddr
        content = [ '# Installer-generated configuration for '+label ]
        if mac.lower() != admin_mac.lower():
            # This is not the management interface so leave unconfigured
            content += [
                "LABEL='%s'" % label,
                "MODE='none'"
            ]
        else:
            # This is the management interface
            if config.isStatic():
                content += [
                    "LABEL='%s'" % label,
                    "MODE='static'",
                    "IP='%s'" % config.get('ipaddr', ''),
                    "NETMASK='%s'" % config.get('netmask', ''),
                    "GATEWAY='%s'" % config.get('gateway', '')
                ]
            else:
                content += [
                    "LABEL='%s'" % label,
                    "MODE='dhcp'"
                ]
            # Nameservers can be specified for both DHCP and static configurations
            for i, nameserver in enumerate(nameservers):
                content.append('DNS'+str(i+1)+"='"+nameserver.strip()+"'")
        writeFirstbootFile(operation, mounts, 'interface-'+mac.lower()+'.conf', content)
    disableFirstbootScript(operation, mounts, '27-detect-nics')

def prepareHostname(operation, mounts, hostname):
    content=[ "XSHOSTNAME='%s'" % hostname ]
    xelogging.log('Writing firstboot hostname configuration '+', '.join(content))
    writeFirstbootFile(operation, mounts, 'hostname.conf', content)

def prepareNTP(operation, mounts, method, ntp_servers):
    content=[
        "XSTIMEMETHOD='%s'" % method,
        "XSNTPSERVERS='%s'" % ' '.join(ntp_servers)
    ]
    xelogging.log('Writing firstboot NTP configuration '+', '.join(content))
    writeFirstbootFile(operation, mounts, 'ntp.conf', content)

def prepareTimezone(operation, mounts, timezone):
    content=[
        "XSTIMEZONE='%s'" % timezone
    ]
    xelogging.log('Writing firstboot timezone configuration '+', '.join(content))
    writeFirstbootFile(operation, mounts, 'timezone.conf', content)
    
def preparePassword(operation, mounts, password_hash):
    content=[
        "XSPASSWORD='%s'" % password_hash
    ]
    xelogging.log('Writing firstboot password configuration '+', '.join(content))
    writeFirstbootFile(operation, mounts, 'password.conf', content)
    
def prepareStorageRepositories(operation, mounts, primary_disk, guest_disks, sr_type):
    
    is_oem = init_constants.operationIsOEMInstall(operation)
    
    if len(guest_disks) == 0:
        xelogging.log("No storage repository requested.")
        return None

    xelogging.log("Arranging for storage repositories to be created at first boot...")

    partitions = getSRPhysDevs(primary_disk, guest_disks, is_oem)

    sr_type_strings = { constants.SR_TYPE_EXT: 'ext', 
                        constants.SR_TYPE_LVM: 'lvm' }
    sr_type_string = sr_type_strings[sr_type]

    # write a config file for the prepare-storage firstboot script:
    
    links = map(lambda x: diskutil.idFromPartition(x) or x, partitions)
    content = [
        "XSPARTITIONS='%s'" % str.join(" ", links),
        "XSTYPE='%s'" % sr_type_string,
        # Legacy names
        "PARTITIONS='%s'" % str.join(" ", links),
        "TYPE='%s'" % sr_type_string
    ]
    
    xelogging.log('Writing firstboot storage configuration '+', '.join(content))
    writeFirstbootFile(operation, mounts, 'default-storage.conf', content)
    
###
# Create dom0 disk file-systems:

def createDom0DiskFilesystems(disk):
    assert util.runCmd2(["mkfs.%s" % rootfs_type, "-L", rootfs_label, getRootPartName(disk)]) == 0

def __mkinitrd(mounts, iscsi_iface, kernel_version):
    try:
        util.bindMount('/sys', os.path.join(mounts['root'], 'sys'))
        util.bindMount('/dev', os.path.join(mounts['root'], 'dev'))
        util.bindMount('/proc', os.path.join(mounts['root'], 'proc'))

        if iscsi_iface:
            # primary disk is iscsi via iscsi_iface.
            # mkinitrd uses iscsiadm to talk to iscsid.  However, at this
            # point iscsid is not running in the dom0 chroot.

            # Make temporary copy of iscsi config in dom0 chroot
            util.mount('none', os.path.join(mounts['root'], 'etc/iscsi'), None, 'tmpfs')
            cmd = [ 'cp', '-a', '/etc/iscsi', os.path.join(mounts['root'], 'etc/')]
            if util.runCmd2(cmd) != 0:
                raise RuntimeError, "Failed to initialise temporary /etc/iscsi"
        
            # Start iscsid inside dom0 chroot
            util.runCmd2(['killall', '-9', 'iscsid']) # just in case one is running 
            cmd = [ 'chroot', mounts['root'], '/sbin/iscsid' ]
            if util.runCmd2(cmd) != 0:
                raise RuntimeError, "Failed to start iscsid in dom0 chroot"

        # Run mkinitrd inside dom0 chroot
        output_file = os.path.join("/boot", "initrd-%s.img" % kernel_version)
        cmd = ['chroot', mounts['root'], 'mkinitrd', '--theme=/usr/share/citrix-splash', '--with', 'ide-generic']
        if iscsi_iface:
            cmd.append('--net-dev=%s' % iscsi_iface)
        cmd.extend([output_file, kernel_version])
        if util.runCmd2(cmd) != 0:
            raise RuntimeError, "Failed to create initrd for %s.  This is often due to using an installer that is not the same version of %s as your installation source." % (kernel_version, version.PRODUCT_BRAND)
    finally:
        if iscsi_iface:
            # stop the iscsi daemon
            util.runCmd2(['killall', '-9', 'iscsid'])
            # Clear up temporary copy of iscsi config in dom0 chroot
            util.umount(os.path.join(mounts['root'], 'etc/iscsi'))

        util.umount(os.path.join(mounts['root'], 'sys'))
        util.umount(os.path.join(mounts['root'], 'dev'))
        util.umount(os.path.join(mounts['root'], 'proc'))

def mkinitrd(mounts, iscsi_iface):
    __mkinitrd(mounts, iscsi_iface, version.KERNEL_VERSION)
    __mkinitrd(mounts, iscsi_iface, version.KDUMP_VERSION)

    # make the initrd-2.6-xen.img symlink:
    initrd_name = "initrd-%s.img" % version.KERNEL_VERSION
    util.runCmd2(["ln", "-sf", initrd_name, "%s/boot/initrd-2.6-xen.img" % mounts['root']])

def writeMenuItems(f, fn, s):
    entries = [
        {
            'label':      "xe",
            'title':      PRODUCT_BRAND,
            'hypervisor': "/boot/xen.gz dom0_mem=%dM lowmem_emergency_pool=16M crashkernel=64M@32M console=/dev/null vga=mode-0x0311" % constants.DOM0_MEM,
            'kernel':     "/boot/vmlinuz-2.6-xen root=LABEL=%s ro quiet vga=785 splash" % (constants.rootfs_label),
            'initrd':     "/boot/initrd-2.6-xen.img",
        }
    ]
    if s:
        entries += [{
            'label':      "xe-serial",
            'title':      "%s (Serial)" % PRODUCT_BRAND,
            'hypervisor': "/boot/xen.gz %s=%s,%s%s%s console=%s,tty dom0_mem=%dM " \
                          % (s['port'][1], s['baud'], s['data'], s['parity'], s['stop'], s['port'][1], constants.DOM0_MEM) \
                          + "lowmem_emergency_pool=16M crashkernel=64M@32M",
            'kernel':     "/boot/vmlinuz-2.6-xen root=LABEL=%s ro console=tty0 console=%s,%s%s%s" \
                          % (constants.rootfs_label, s['port'][0], s['baud'], s['parity'], s['data']),
            'initrd':     "/boot/initrd-2.6-xen.img",
        }, {
            'label':      "safe",
            'title':      "%s in Safe Mode" % PRODUCT_BRAND,
            'hypervisor': "/boot/xen.gz nosmp noreboot noirqbalance acpi=off noapic " \
                          + "dom0_mem=%dM %s=%s,%s%s%s console=%s,tty" \
                          % (constants.DOM0_MEM, s['port'][1], s['baud'], s['data'], s['parity'], s['stop'], s['port'][1]),
            'kernel':     "/boot/vmlinuz-2.6-xen nousb root=LABEL=%s ro console=tty0 " \
                          % constants.rootfs_label \
                          + "console=%s,%s%s%s" % (s['port'][0], s['baud'], s['parity'], s['data']),
            'initrd':     "/boot/initrd-2.6-xen.img",
        }]
    entries += [{
            'label':      "fallback",
            'title':      "%s (Xen %s / Linux %s)" \
                          % (PRODUCT_BRAND,version.XEN_VERSION,version.KERNEL_VERSION),
            'hypervisor': "/boot/xen-%s.gz dom0_mem=%dM lowmem_emergency_pool=16M crashkernel=64M@32M" \
                          % (version.XEN_VERSION, constants.DOM0_MEM),
            'kernel':     "/boot/vmlinuz-%s root=LABEL=%s ro console=tty0" \
                          % (version.KERNEL_VERSION, constants.rootfs_label),
            'initrd':     "/boot/initrd-%s.img" % version.KERNEL_VERSION,
        }]
    if s:
        entries += [{
            'label':      "fallback-serial",
            'title':      "%s (Serial, Xen %s / Linux %s)" \
                          % (PRODUCT_BRAND,version.XEN_VERSION,version.KERNEL_VERSION),
            'hypervisor': "/boot/xen-%s.gz %s=%s,%s%s%s console=%s,tty dom0_mem=%dM " \
                          % (version.XEN_VERSION, s['port'][1], s['baud'], s['data'], s['parity'], s['stop'], s['port'][1], constants.DOM0_MEM) \
                          + "lowmem_emergency_pool=16M crashkernel=64M@32M",
            'kernel':     "/boot/vmlinuz-%s root=LABEL=%s ro console=tty0 console=%s,%s%s%s" \
                          % (version.KERNEL_VERSION, constants.rootfs_label, s['port'][0], s['baud'], s['parity'], s['data']),
            'initrd':     "/boot/initrd-%s.img" % version.KERNEL_VERSION,
        }]

    for entry in entries:
        fn(f, entry)

def installBootLoader(mounts, disk, bootloader, serial, boot_serial):
    # prepare extra mounts for installing bootloader:
    util.bindMount("/dev", "%s/dev" % mounts['root'])
    util.bindMount("/sys", "%s/sys" % mounts['root'])

    # This is a nasty hack but unavoidable (I think):
    #
    # The bootloader tries to work out what the root device is but
    # this is confused within the chroot.  Therefore, we fake out
    # /proc/mounts with the correct data. If /etc/mtab is not a
    # symlink (to /proc/mounts) then we fake that out too.
    f = open("%s/proc/mounts" % mounts['root'], 'w')
    f.write("%s / %s rw 0 0\n" % (getRootPartName(disk), constants.rootfs_type))
    f.close()
    if not os.path.islink("%s/etc/mtab" % mounts['root']):
        f = open("%s/etc/mtab" % mounts['root'], 'w')
        f.write("%s / %s rw 0 0\n" % (getRootPartName(disk), constants.rootfs_type))
        f.close()

    try:
        if bootloader == constants.BOOTLOADER_TYPE_GRUB:
            installGrub(mounts, disk, serial, boot_serial)
        elif bootloader == constants.BOOTLOADER_TYPE_EXTLINUX:
            installExtLinux(mounts, disk, serial, boot_serial)
        else:
            raise RuntimeError, "Unknown bootloader."

        if serial:
            # ensure a getty will run on the serial console
            init = open("%s/etc/inittab" % mounts['root'], 'r')
            lines = init.readlines()
            init.close()
            for line in lines:
                if line.find("getty %s " % serial['port'][0]) != -1:
                    break
            else:
                init = open("%s/etc/inittab" % mounts['root'], 'a')
                label = serial['port'][0][3:].lower()
                init.write("%s:2345:respawn:/sbin/agetty %s %s %s\n" % (label, serial['port'][0], serial['baud'], serial['term']))
                init.close()

            sec = open("%s/etc/securetty" % mounts['root'], 'r')
            lines = sec.readlines()
            sec.close()
            for line in lines:
                if line.strip('\n') == serial['port'][0]:
                    break
            else:
                sec = open("%s/etc/securetty" % mounts['root'], 'a')
                sec.write("%s\n" % serial['port'][0])
                sec.close()
    finally:
        # unlink /proc/mounts
        if os.path.exists("%s/proc/mounts" % mounts['root']):
            os.unlink("%s/proc/mounts" % mounts['root'])
        # done installing - undo our extra mounts:
        util.umount("%s/sys" % mounts['root'])
        util.umount("%s/dev" % mounts['root'])

def writeExtLinuxMenuItem(f, item):
    f.write("label %s\n  # %s\n" % (item['label'], item['title']))
    f.write("  kernel mboot.c32\n")
    f.write("  append %s --- %s --- %s\n" % (item['hypervisor'], item['kernel'], item['initrd']))
    f.write("\n")

def installExtLinux(mounts, disk, serial, boot_serial):
    f = open("%s/extlinux.conf" % mounts['boot'], "w")

    if serial:
        f.write("serial %s %s\n" % (serial['port'][0][4:], serial['baud']))
    if boot_serial:
        f.write("default xe-serial\n")
    else:
        f.write("default xe\n")
    
    f.write("prompt 1\n")
    f.write("timeout 50\n")
    f.write("\n")

    writeMenuItems(f, writeExtLinuxMenuItem, serial)
    
    f.close()

    assert util.runCmd2(["chroot", mounts['root'], "/sbin/extlinux", "--install", "/boot"]) == 0

    for m in ["mboot", "menu", "chain"]:
        assert util.runCmd2(["ln", "-f",
                             "%s/usr/lib/syslinux/%s.c32" % (mounts['root'], m),
                             "%s/%s.c32" % (mounts['boot'], m)]) == 0
    assert util.runCmd2(["dd", "if=%s/usr/lib/syslinux/mbr.bin" % mounts['root'], \
                         "of=%s" % disk, "bs=512", "count=1"]) == 0

def writeGrubMenuItem(f, item):
    f.write("title %s\n" % item['title'])
    f.write("   kernel %s\n" % item['hypervisor'])
    f.write("   module %s\n" % item['kernel'])
    f.write("   module %s\n\n" % item['initrd'])

def installGrub(mounts, disk, serial, boot_serial):
    grubroot = getGrUBDevice(disk, mounts)

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

    if serial:
        grubconf += "serial --unit=%s --speed=%s\n" % (serial['port'][0][4:], serial['baud'])
        grubconf += "terminal --timeout=10 console serial\n"
    else:
        grubconf += "terminal console\n"
    if boot_serial:
        grubconf += "default 1\n"
    else:
        grubconf += "default 0\n"

    grubconf += "timeout 5\n\n"

    # splash screen?
    # (Disabled for now since GRUB messes up on the serial line when
    # this is enabled.)
    if hasSplash and False:
        grubconf += "\n"
        grubconf += "foreground = 000000\n"
        grubconf += "background = cccccc\n"
        grubconf += "splashimage = /xs-splash.xpm.gz\n\n"


    # write the GRUB configuration:
    util.assertDir("%s/grub" % mounts['boot'])
    menulst_file = open("%s/grub/menu.lst" % mounts['boot'], "w")
    menulst_file.write(grubconf)
    writeMenuItems(menulst_file, writeGrubMenuItem, serial)
    menulst_file.close()

    # now perform our own installation, onto the MBR of the selected disk:
    xelogging.log("About to install GRUB.  Install to disk %s" % grubroot)
    assert util.runCmd2(["chroot", mounts['root'], "grub-install", "--no-floppy", "--recheck", grubroot]) == 0

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
    assert util.runCmd2(['chroot', mounts['root'], 'depmod', version.KERNEL_VERSION]) == 0

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

def enableAgent(mounts):
    util.runCmd2(['chroot', mounts['root'], 'chkconfig', '--del', 'xend'])
    for service in ['xenservices', 'xapi', 'xapi-domains', 'perfmon', 'snapwatchd']:
        util.runCmd2(['chroot', mounts['root'], 'chkconfig', '--add', service])
    util.assertDir(os.path.join(mounts['root'], constants.BLOB_DIRECTORY))

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
    assert util.runCmd2(['ln', '-sf', '/usr/share/zoneinfo/%s' % tz, 
                         '%s/etc/localtime' % mounts['root']]) == 0

def setRootPassword(mounts, root_password, pwdtype):
    # avoid using shell here to get around potential security issues.  Also
    # note that chpasswd needs -m to allow longer passwords to work correctly
    # but due to a bug in the RHEL5 version of this tool it segfaults when this
    # option is specified, so we have to use passwd instead if we need to 
    # encrypt the password.  Ugh.
    if pwdtype == 'pwdhash':
        cmd = ["/usr/sbin/chroot", mounts["root"], "chpasswd", "-e"]
        pipe = subprocess.Popen(cmd, stdin = subprocess.PIPE,
                                     stdout = subprocess.PIPE)
        pipe.communicate('root:%s\n' % root_password)
        assert pipe.wait() == 0
    else: 
        cmd = ["/usr/sbin/chroot", mounts['root'], "passwd", "--stdin", "root"]
        pipe = subprocess.Popen(cmd, stdin = subprocess.PIPE,
                                     stdout = subprocess.PIPE,
                                     stderr = subprocess.PIPE)
        pipe.communicate(root_password + "\n")
        assert pipe.wait() == 0

# write /etc/sysconfig/network-scripts/* files
def configureNetworking(mounts, admin_iface, admin_bridge, admin_config, hn_conf, ns_conf, nethw, preserve_settings, iscsi_iface):
    """ Writes configuration files that the firstboot scripts will consume to
    configure interfaces via the CLI.  Writes a loopback device configuration.
    to /etc/sysconfig/network-scripts, and removes any other configuration
    files from that directory."""

    if preserve_settings:
        return

    util.assertDir(os.path.join(mounts['root'], constants.FIRSTBOOT_DATA_DIR))

    network_scripts_dir = os.path.join(mounts['root'], 'etc', 'sysconfig', 'network-scripts')

    (manual_hostname, hostname) = hn_conf
    (manual_nameservers, nameservers) = ns_conf
    domain=None
    if manual_hostname:
        dot = hostname.find('.')
        if dot != -1:
            domain=hostname[dot+1:]

    # remove any files that may be present in the filesystem already, 
    # particularly those created by kudzu:
    network_scripts = os.listdir(network_scripts_dir)
    for s in filter(lambda x: x.startswith('ifcfg-'), network_scripts):
        os.unlink(os.path.join(network_scripts_dir, s))

    # write the configuration file for the loopback interface
    lo = open(os.path.join(network_scripts_dir, 'ifcfg-lo'), 'w')
    lo.write("DEVICE=lo\n")
    lo.write("IPADDR=127.0.0.1\n")
    lo.write("NETMASK=255.0.0.0\n")
    lo.write("NETWORK=127.0.0.0\n")
    lo.write("BROADCAST=127.255.255.255\n")
    lo.write("ONBOOT=yes\n")
    lo.write("NAME=loopback\n")
    lo.close()

    network_conf_file = os.path.join(mounts['root'], constants.FIRSTBOOT_DATA_DIR, 'network.conf')
    # write the master network configuration file; the firstboot script has the
    # ability to configure multiple interfaces but we only configure one.  When
    # upgrading the script should only modify the admin interface:
    nc = open(network_conf_file, 'w')
    print >>nc, "ADMIN_INTERFACE='%s'" % admin_config.hwaddr
    if not preserve_settings:
        # This tells /etc/firstboot.d/30-prepare-networking to pif-introduce all the network devices we've discovered
        # (although if we are using one for access to an iSCSI root disk then we omit that as it is reserved).
        print >>nc, "INTERFACES='%s'" % str.join(" ", [nethw[x].hwaddr for x in nethw.keys() if x != iscsi_iface ])
    else:
        print >>nc, "INTERFACES='%s'" % admin_config.hwaddr
    nc.close()

    # Write out the networking configuration.  Note that when doing a fresh
    # install the interface configuration will be made to look like the current
    # runtime configuration.  When doing an upgrade, the interface
    # configuration previously used needs to be preserved but we also don't
    # need to re-seed the configuration via firstboot, so we only write out a 
    # sysconfig file for the management interface to get networking going.
    ###
    if not preserve_settings:
        # Write a firstboot config file for every interface we know about
        # (unless we are using one for access to the iSCSI root device, in which case that must be ommited)
        for intf in [ x for x in nethw.keys() if x != iscsi_iface ]:
            hwaddr = nethw[intf].hwaddr
            conf_file = os.path.join(mounts['root'], constants.FIRSTBOOT_DATA_DIR, 'interface-%s.conf' % hwaddr)
            ac = open(conf_file, 'w')
            print >>ac, "LABEL='%s'" % intf
            if intf == admin_iface:
                if not admin_config.isStatic():
                    print >>ac, "MODE=dhcp"
                else:
                    print >>ac, "MODE=static"
                    print >>ac, "IP=%s" % admin_config.ipaddr
                    print >>ac, "NETMASK=%s" % admin_config.netmask
                    if admin_config.gateway:
                        print >>ac, "GATEWAY=%s" % admin_config.gateway
                    if manual_nameservers:
                        for i in range(len(nameservers)):
                            print >>ac, "DNS%d=%s" % (i+1, nameservers[i])
                    if domain:
                        print >>ac, "DOMAIN=%s" % domain
            else:
                print >>ac, "MODE=none"
            ac.close()

    save_dir = os.path.join(mounts['root'], constants.FIRSTBOOT_DATA_DIR, 'initial-ifcfg')
    util.assertDir(save_dir)

    # Write out initial network configuration file for management interface:
    sysconf_admin_iface_file = os.path.join(mounts['root'], 'etc', 'sysconfig', 'network-scripts', 'ifcfg-%s' % admin_iface)
    sysconf_admin_iface_fd = open(sysconf_admin_iface_file, 'w')
    print >>sysconf_admin_iface_fd, "# DO NOT EDIT: This file generated by the installer"
    print >>sysconf_admin_iface_fd, "XEMANAGED=yes"
    print >>sysconf_admin_iface_fd, "DEVICE=%s" % admin_iface
    print >>sysconf_admin_iface_fd, "ONBOOT=no"
    print >>sysconf_admin_iface_fd, "TYPE=Ethernet"
    print >>sysconf_admin_iface_fd, "HWADDR=%s" % admin_config.hwaddr
    print >>sysconf_admin_iface_fd, "BRIDGE=%s" % admin_bridge
    sysconf_admin_iface_fd.close()
    util.runCmd2(['cp', '-p', sysconf_admin_iface_file, save_dir])

    sysconf_bridge_file = os.path.join(mounts['root'], 'etc', 'sysconfig', 'network-scripts', 'ifcfg-%s' % admin_bridge)
    sysconf_bridge_fd = open(sysconf_bridge_file, "w")
    print >>sysconf_bridge_fd, "# DO NOT EDIT: This file generated by the installer"
    print >>sysconf_bridge_fd, "XEMANAGED=yes"
    print >>sysconf_bridge_fd, "DEVICE=%s" % admin_bridge
    print >>sysconf_bridge_fd, "ONBOOT=no"
    print >>sysconf_bridge_fd, "TYPE=Bridge"
    print >>sysconf_bridge_fd, "DELAY=0"
    print >>sysconf_bridge_fd, "STP=off"
    print >>sysconf_bridge_fd, "PIFDEV=%s" % admin_iface
    if not admin_config.isStatic():
        print >>sysconf_bridge_fd, "BOOTPROTO=dhcp"
    else:
        print >>sysconf_bridge_fd, "BOOTPROTO=none"
        print >>sysconf_bridge_fd, "NETMASK=%s" % admin_config.netmask
        print >>sysconf_bridge_fd, "IPADDR=%s" % admin_config.ipaddr
        if admin_config.gateway:
            print >>sysconf_bridge_fd, "GATEWAY=%s" % admin_config.gateway
        if manual_nameservers:
            print >>sysconf_bridge_fd, "PEERDNS=yes"
            for i in range(len(nameservers)):
                print >>sysconf_bridge_fd, "DNS%d=%s" % (i+1, nameservers[i])
        if domain:
            print >>sysconf_bridge_fd, "DOMAIN=%s" % domain
    sysconf_bridge_fd.close()
    util.runCmd2(['cp', '-p', sysconf_bridge_file, save_dir])

    # now we need to write /etc/sysconfig/network
    nfd = open("%s/etc/sysconfig/network" % mounts["root"], "w")
    nfd.write("NETWORKING=yes\n")
    if manual_hostname:
        nfd.write("HOSTNAME=%s\n" % hostname)
    else:
        nfd.write("HOSTNAME=localhost.localdomain\n")
    nfd.close()

# use kudzu to write initial modprobe-conf:
def writeModprobeConf(mounts):
    # CA-21996: kudzu can get confused and write ifcfg files for the
    # the wrong interface. If we move the network-scripts sideways
    # then it still performs its other tasks.
    os.rename("%s/etc/sysconfig/network-scripts" % mounts['root'], 
              "%s/etc/sysconfig/network-scripts.hold" % mounts['root'])

    util.bindMount("/proc", "%s/proc" % mounts['root'])
    util.bindMount("/sys", "%s/sys" % mounts['root'])
    assert util.runCmd2(['chroot', mounts['root'], 'kudzu', '-q', '-k', version.KERNEL_VERSION]) == 0
    util.umount("%s/proc" % mounts['root'])
    util.umount("%s/sys" % mounts['root'])

    # restore directory
    os.rename("%s/etc/sysconfig/network-scripts.hold" % mounts['root'], 
              "%s/etc/sysconfig/network-scripts" % mounts['root'])

def writeInventory(installID, controlID, mounts, primary_disk, guest_disks, admin_bridge):
    inv = open(os.path.join(mounts['root'], constants.INVENTORY_FILE), "w")
    default_sr_physdevs = getSRPhysDevs(primary_disk, guest_disks)
    inv.write("PRODUCT_BRAND='%s'\n" % PRODUCT_BRAND)
    inv.write("PRODUCT_NAME='%s'\n" % PRODUCT_NAME)
    inv.write("PRODUCT_VERSION='%s'\n" % PRODUCT_VERSION)
    inv.write("BUILD_NUMBER='%s'\n" % BUILD_NUMBER)
    inv.write("KERNEL_VERSION='%s'\n" % version.KERNEL_VERSION)
    inv.write("XEN_VERSION='%s'\n" % version.XEN_VERSION)
    inv.write("INSTALLATION_DATE='%s'\n" % str(datetime.datetime.now()))
    inv.write("PRIMARY_DISK='%s'\n" % (diskutil.idFromPartition(primary_disk) or primary_disk))
    inv.write("BACKUP_PARTITION='%s'\n" % (diskutil.idFromPartition(getBackupPartName(primary_disk)) or getBackupPartName(primary_disk)))
    inv.write("INSTALLATION_UUID='%s'\n" % installID)
    inv.write("CONTROL_DOMAIN_UUID='%s'\n" % controlID)
    inv.write("DEFAULT_SR_PHYSDEVS='%s'\n" % " ".join(default_sr_physdevs))
    inv.write("DOM0_MEM='%d'\n" % constants.DOM0_MEM)
    inv.write("MANAGEMENT_INTERFACE='%s'\n" % admin_bridge)
    inv.close()

def touchSshAuthorizedKeys(mounts):
    util.assertDir("%s/root/.ssh/" % mounts['root'])
    fh = open("%s/root/.ssh/authorized_keys" % mounts['root'], 'a')
    fh.close()

def backupExisting(existing):
    primary_partition = getRootPartName(existing.primary_disk)
    backup_partition = getBackupPartName(existing.primary_disk)
    xelogging.log("Backing up existing installation: source %s, target %s" % (primary_partition, backup_partition))

    # format the backup partition:
    util.runCmd2(['mkfs.ext3', backup_partition])

    # copy the files across:
    primary_mount = '/tmp/backup/primary'
    backup_mount  = '/tmp/backup/backup'
    for mnt in [primary_mount, backup_mount]:
        util.assertDir(mnt)
    try:
        util.mount(primary_partition, primary_mount, options = ['ro'])
        util.mount(backup_partition,  backup_mount)
        cmd = ['cp', '-a'] + \
              [ os.path.join(primary_mount, x) for x in os.listdir(primary_mount) ] + \
              ['%s/' % backup_mount]
        assert util.runCmd2(cmd) == 0
        util.runCmd2(['touch', os.path.join(backup_mount, '.xen-backup-partition')])
        
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
        util.assertDir("/tmp/mnt")
        util.mount(bootnode, "/tmp/mnt")
        log_location = "/tmp/mnt/var/log/installer"
        if os.path.islink(log_location):
            log_location = os.path.join("/tmp/mnt", os.readlink(log_location).lstrip("/"))
        util.assertDir(log_location)
        xelogging.writeLog(os.path.join(log_location, "install-log"))
        try:
            xelogging.collectLogs(log_location, "/tmp/mnt/root")
        except:
            pass
        try:
            util.umount("/tmp/mnt")
        except:
            pass
    except:
        pass

def writei18n(mounts):
    path = os.path.join(mounts['root'], 'etc', 'sysconfig', 'i18n')
    fd = open(path, 'w')
    fd.write('LANG="en_US.UTF-8"\n')
    fd.write('SYSFONT="drdos8x8"\n')
    fd.close()

def installXen64(mounts):
    rpmdir = os.path.join('opt', 'xensource', 'RPMS')
    if not os.path.exists(os.path.join(mounts['root'], rpmdir)):
        return

    # currently only contains xen64 RPM but cope with others
    rpmlist = ["/%s/%s" % (rpmdir, f) for f in os.listdir(os.path.join(mounts['root'], rpmdir)) if f.endswith('.rpm')]
    if len(rpmlist) > 0:
        util.bindMount("/proc", "%s/proc" % mounts['root'])
        util.bindMount("/sys", "%s/sys" % mounts['root'])
        # grubby needs to access disk device files
        util.bindMount("/dev", "%s/dev" % mounts['root'])
        util.runCmd2(['chroot', mounts['root'], 'new-kernel-pkg', '--package', 'kernel-xen', '--install', '--multiboot=/boot/xen.gz', version.KERNEL_VERSION])
        util.runCmd2(['chroot', mounts['root'], '/bin/rpm', '-ihv'] + rpmlist)
        util.umount("%s/proc" % mounts['root'])
        util.umount("%s/sys" % mounts['root'])
        util.umount("%s/dev" % mounts['root'])

def getUpgrader(source):
    """ Returns an appropriate upgrader for a given source. """
    return upgrade.getUpgrader(source)

def prepareUpgrade(upgrader, *args):
    """ Gets required state from existing installation. """
    return upgrader.prepareUpgrade(*args)

def completeUpgrade(upgrader, *args):
    """ Puts back state into new filesystem. """
    return upgrader.completeUpgrade(*args)
