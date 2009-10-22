# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Installer TUI screens
#
# written by Andrew Peace

import string
import datetime

import generalui
import uicontroller
from uicontroller import SKIP_SCREEN, EXIT, LEFT_BACKWARDS, RIGHT_FORWARDS, REPEAT_STEP
import constants
import diskutil
from disktools import *
import xelogging
from version import *
import snackutil
import repository
import hardware
import util
import socket
import version
import product
import upgrade
import netutil
import urlparse

from snack import *

import tui
import tui.network
import tui.progress

def selectDefault(key, entries):
    """ Given a list of (text, key) and a key to select, returns the appropriate
    text,key pair, or None if not in entries. """

    for text, k in entries:
        if key == k:
            return text, k
    return None

# welcome screen:
def welcome_screen(answers):
    button = ButtonChoiceWindow(tui.screen,
                                "Welcome to %s Setup" % PRODUCT_BRAND,
                                """This setup tool will install %s on your server.  Installing %s will erase all data on the disks selected for use unless an upgrade option is chosen.

Please make sure you have backed up any data you wish to preserve before proceeding with the installation.""" % (PRODUCT_BRAND, PRODUCT_BRAND),
                                ['Ok', 'Cancel Installation'], width = 60)

    # advance to next screen:
    if button == 'cancel installation':
        return EXIT
    else:
        return RIGHT_FORWARDS

def add_iscsi_disks(answers):
    button = ButtonChoiceWindow(tui.screen,
                                "iSCSI",
                                "Locate additional iSCSI disks",
                                ['Skip', 'Ok', 'Back'], width = 60)
    if button in ['skip', None]:
        return RIGHT_FORWARDS
    if button == 'back':
        return LEFT_BACKWARDS
    
    # iSCSI needs networking...
    while True:
        rc = tui.network.requireNetworking(answers, msg="Please specify which network interface would you like to use to access the iSCSI target",
                                           blacklist=[], keys=['net-iscsi-interface','net-iscsi-configuration'])
        if rc == RIGHT_FORWARDS:
            break # networking succeeded
        if rc == LEFT_BACKWARDS:
            return rc
        
    # configure iSCSI initiator name before starting daemon
    rv, iname = util.runCmd2([ '/sbin/iscsi-iname' ], with_stdout=True)
    if rv: raise RuntimeError, "/sbin/iscsi-iname failed"
    open("/etc/iscsi/initiatorname.iscsi","w").write("InitiatorName=%s" % iname)

    try:
        # start iSCSI daemon
        rv = util.runCmd2([ '/sbin/modprobe', 'iscsi_tcp' ])
        if rv: raise RuntimeError, "/sbin/modprobe iscsi_tcp failed"
        rv = util.runCmd2([ '/sbin/iscsid' ])
        if rv: raise RuntimeError, "/sbin/iscsid failed"
       
        # ask for location of iSCSI server
        text = "Enter the IP address of the iSCSI target"
        if answers.has_key('iscsi-target-address'):
            default = answers['iscsi-target-address']
        else:
            default = ""
        (button, result) = EntryWindow(
            tui.screen,
            "iSCSI target IP",
            text,
            [("IP Address[:Port]:", default)], entryWidth = 50, width = 50,
            buttons = ['Ok', 'Back'])
            
        answers['iscsi-target-address'] = result[0]

        if button == 'back':
            return REPEAT_STEP

        # discover IQNs offered by iSCSI server
        rv, out = util.runCmd2([ '/sbin/iscsiadm', '-m', 'discovery', '-t', 'sendtargets', '-p', answers['iscsi-target-address']], with_stdout=True)
        if rv: raise RuntimeError, "/sbin/iscsiadm -m discovery failed"
        out = out.strip()
        iqns = map(lambda x : x.split()[-1], out.split('\n'))

        # ask user to select an IQN
        entries = [ (x,x) for x in iqns ]
        if answers.has_key('iscsi-iqn'):
            default = selectDefault(answers['iscsi-iqn'], entries)
        else:
            default = None
        
        (button, entry) = ListboxChoiceWindow(
            tui.screen,
            "IQN",
            "Select iSCSI IQN containing disks to be attached",
            entries,
            ['Ok', 'Back'], width=60, default = default)

        if button == 'back':
            return REPEAT_STEP

        answers['iscsi-iqn'] = entry

        # Just in case we've been here before... unattach all IQNs now
        util.runCmd2([ '/sbin/iscsiadm' ,'-m', 'node', '-u' ])

        # attach IQN's disks
        rv = util.runCmd2([ '/sbin/iscsiadm', '-m', 'node', '-T', answers['iscsi-iqn'], '-p', answers['iscsi-target-address'], '-l'])
        if rv: raise RuntimeError, "/sbin/iscsiadm -m node -l failed"

        # debug: print out what disks we have now available
        diskutil.log_available_disks()

    finally:
        # Kill this iscsid as we don't need it anymore running in the installer root filesystem
        util.runCmd2([ '/sbin/iscsiadm' ,'-k', '0' ])
        util.runCmd2([ '/sbin/udevsettle' ])

    # update the list of installed/upgradeable products as this may have
    # changed as a result of adding a disk
    tui.progress.showMessageDialog("Please wait", "Checking for existing products...")
    answers['installed-products'] = product.find_installed_products()
    answers['upgradeable-products'] = upgrade.filter_for_upgradeable_products(answers['installed-products'])
    tui.progress.clearModelessDialog()

    return RIGHT_FORWARDS

def hardware_warnings(answers, ram_warning, vt_warning):
    vt_not_found_text = "Hardware virtualization assist support is not available on this system.  Either it is not present, or is disabled in the system's BIOS.  This capability is required to start Windows virtual machines."
    not_enough_ram_text = "%s requires %dMB of system memory in order to function normally.  Your system appears to have less than this, which may cause problems during startup." % (PRODUCT_BRAND, constants.MIN_SYSTEM_RAM_MB_RAW)

    text = "The following problem(s) were found with your hardware:\n\n"
    if vt_warning:
        text += vt_not_found_text + "\n\n"
    if ram_warning:
        text += not_enough_ram_text + "\n\n"
    text += "You may continue with the installation, though %s might have limited functionality until you have addressed these problems." % PRODUCT_BRAND

    button = ButtonChoiceWindow(
        tui.screen,
        "System Hardware",
        text,
        ['Ok', 'Back'],
        width = 60
        )

    if button == 'back': return LEFT_BACKWARDS
    return RIGHT_FORWARDS

def overwrite_warning(answers):
    button = ButtonChoiceWindow(
        tui.screen,
        "Warning",
        """Only product installations that cannot be upgraded have been detected.

Continuing will result in a clean installation, all existing configuration will be lost.

Alternatively, please contact a Technical Support Representative for the recommended upgrade path.""",
        ['Ok', 'Back'],
        width = 60
        )

    if button == 'back': return LEFT_BACKWARDS
    return RIGHT_FORWARDS

def get_iscsi_interface(answers):
    default = None
    try:
        if answers.has_key('net-iscsi-interface'):
            default = answers['net-iscsi-interface']
        else:
            # default is netdev used to access primary disk during installation
            _, _, default = diskutil.iscsi_address_port_netdev(answers['primary-disk'])
    except:
        pass

    net_hw = answers['network-hardware']
    direction, iface = tui.network.select_netif("Which network interface would you like to use for connecting to the iSCSI target from your host?", net_hw, default)
    if direction == RIGHT_FORWARDS:
        answers['net-iscsi-interface'] = iface
    return direction

def get_iscsi_interface_configuration(answers):
    assert answers.has_key('net-iscsi-interface')
    nic = answers['network-hardware'][answers['net-iscsi-interface']]

    defaults = None
    try:
        if answers.has_key('net-iscsi-configuration'):
            defaults = answers['net-iscsi-configuration']
        elif answers.has_key('runtime-iface-configuration'):
            all_dhcp, manual_config = answers['runtime-iface-configuration']
            if not all_dhcp:
                defaults = manual_config[answers['net-iscsi-interface']]
    except:
        pass

    rc, conf = tui.network.get_iface_configuration(
        nic, txt = "Please specify how networking should be configured for the management interface on this host.",
        defaults = defaults
        )
    if rc == RIGHT_FORWARDS:
        answers['net-iscsi-configuration'] = conf
    return rc

def get_admin_interface(answers):
    default = None
    try:
        if answers.has_key('net-admin-interface'):
            default = answers['net-admin-interface']
    except:
        pass

    net_hw = answers['network-hardware']
    
    # if the primary disk is iSCSI we need to filter out the interface
    # used to connect to that disk, as this cannot also be used as an
    # admin interface
    blacklist = []
    if diskutil.is_iscsi(answers['primary-disk']):
        blacklist.append(answers['net-iscsi-interface'])

    direction, iface = tui.network.select_netif("Which network interface would you like to use for connecting to the management server on your host?", net_hw, default, blacklist=blacklist)
    if direction == RIGHT_FORWARDS:
        answers['net-admin-interface'] = iface
    return direction

def get_admin_interface_configuration(answers):
    assert answers.has_key('net-admin-interface')
    nic = answers['network-hardware'][answers['net-admin-interface']]

    defaults = None
    try:
        if answers.has_key('net-admin-configuration'):
            defaults = answers['net-admin-configuration']
        elif answers.has_key('runtime-iface-configuration'):
            all_dhcp, manual_config = answers['runtime-iface-configuration']
            if not all_dhcp:
                defaults = manual_config[answers['net-admin-interface']]
    except:
        pass

    rc, conf = tui.network.get_iface_configuration(
        nic, txt = "Please specify how networking should be configured for the management interface on this host.",
        defaults = defaults
        )
    if rc == RIGHT_FORWARDS:
        answers['net-admin-configuration'] = conf
    return rc

def get_installation_type(answers):
    entries = []
    insts = answers['upgradeable-products']
    for x in insts:
        if x.version < product.THIS_PRODUCT_VERSION:
            entries.append(("Upgrade %s" % str(x), (x, x.settingsAvailable())))
        else:
            entries.append(("Freshen %s" % str(x), (x, x.settingsAvailable())))

    entries.append( ("Perform clean installation", None) )

    # default value?
    if answers.has_key('install-type') and answers['install-type'] == constants.INSTALL_TYPE_REINSTALL:
        default = selectDefault(answers['installation-to-overwrite'], entries)
    else:
        default = None

    (button, entry) = ListboxChoiceWindow(
        tui.screen,
        "Installation Type",
        "One or more existing product installations that can be refreshed using this setup tool have been detected.  What would you like to do?",
        entries,
        ['Ok', 'Back'], width=60, default = default)

    if button == 'back': 
        return LEFT_BACKWARDS

    if entry == None:
        answers['install-type'] = constants.INSTALL_TYPE_FRESH
        answers['preserve-settings'] = False

        if answers.has_key('installation-to-overwrite'):
            del answers['installation-to-overwrite']
    else:
        answers['install-type'] = constants.INSTALL_TYPE_REINSTALL
        answers['installation-to-overwrite'], preservable = entry
        answers['preserve-settings'] = preservable
        if 'primary-disk' not in answers:
            answers['primary-disk'] = answers['installation-to-overwrite'].primary_disk

        for k in ['guest-disks', 'default-sr-uuid']:
            if answers.has_key(k):
                del answers[k]
    return RIGHT_FORWARDS

def ha_master_upgrade(answers):
    button = ButtonChoiceWindow(
        tui.screen,
        "High Availability Enabled",
        """High Availability must be disabled before upgrade.

Please reboot this host, disable High Availability on the pool, check which server is the pool master and then restart the upgrade procedure.""",
        ['Cancel', 'Back'],
        width = 60
        )

    if button == 'back': return LEFT_BACKWARDS
    return EXIT

def upgrade_settings_warning(answers):
    button = ButtonChoiceWindow(
        tui.screen,
        "Preserve Settings",
        """The configuration of %s cannot be automatically retained. You must re-enter the configuration manually.

Warning: You must use the current values. Failure to do so may result in an incorrect installation of the product.""" % str(answers['installation-to-overwrite']),
        ['Ok', 'Back'],
        width = 60
        )

    if button == 'back': return LEFT_BACKWARDS
    return RIGHT_FORWARDS

def remind_driver_repos(answers):
    driver_list = []
    settings = answers['installation-to-overwrite'].readSettings()
    for repo in settings['repo-list']:
        id, name, is_supp = repo
        if is_supp and name not in driver_list:
            driver_list.append(name)

    if len(driver_list) == 0:
        return SKIP_SCREEN

    text = ''
    for driver in driver_list:
        text += " * %s\n" % driver

    button = ButtonChoiceWindow(
        tui.screen,
        "Installed Supplemental Packs",
        """The following Supplemental Packs are present in the current installation:

%s
Please ensure that the functionality they provide is either included in the version of %s being installed or by a Supplemental Pack for this release.""" % (text, PRODUCT_BRAND),
        ['Ok', 'Back'],
        width = 60
        )

    if button == 'back': return LEFT_BACKWARDS
    return RIGHT_FORWARDS

def repartition_existing(answers):
    button = ButtonChoiceWindow(
        tui.screen,
        "Convert Existing Installation",
        """The installer needs to change the disk layout of your existing installation.

The conversion will replace all previous system image partitions to create the %s %s disk partition layout.

Continue with installation?""" % (COMPANY_NAME_SHORT, PRODUCT_BRAND),
        ['Continue', 'Back']
        )
    if button == 'back': return LEFT_BACKWARDS

    return RIGHT_FORWARDS

def force_backup_screen(answers):
    button = ButtonChoiceWindow(
        tui.screen,
        "Back-up Existing Installation",
        """The installer needs to create a backup of your existing installation.

This will erase data currently on the backup partition (which includes previous backups performed by the installer, and backups installed onto the host using the CLI's 'host-restore' function).

Continue with installation?""",
        ['Continue', 'Back']
        )
    if button == 'back': return LEFT_BACKWARDS

    answers['backup-existing-installation'] = True
    return RIGHT_FORWARDS

def backup_existing_installation(answers):
    # default selection:
    if answers.has_key('backup-existing-installation'):
        if answers['backup-existing-installation']:
            default = 0
        else:
            default = 1
    else:
        default = 0

    button = snackutil.ButtonChoiceWindowEx(
        tui.screen,
        "Back-up Existing Installation?",
        """Would you like to back-up your existing installation before re-installing %s?

The backup will be placed on the backup partition of the destination disk (%s), overwriting any previous backups on that volume.""" % (PRODUCT_BRAND, answers['installation-to-overwrite'].primary_disk),
        ['Yes', 'No', 'Back'], default = default
        )

    if button == 'back': return LEFT_BACKWARDS

    answers['backup-existing-installation'] = (button == 'yes')
    return RIGHT_FORWARDS

def eula_screen(answers):
    eula_file = open(constants.EULA_PATH, 'r')
    eula = string.join(eula_file.readlines())
    eula_file.close()

    while True:
        button = snackutil.ButtonChoiceWindowEx(
            tui.screen,
            "End User License Agreement",
            eula,
            ['Accept EULA', 'Back'], width=60, default=1)

        if button == 'accept eula':
            return RIGHT_FORWARDS
        elif button == 'back':
            return LEFT_BACKWARDS
        else:
            ButtonChoiceWindow(
                tui.screen,
                "End User License Agreement",
                "You must select 'Accept EULA' (by highlighting it with the cursor keys, then pressing either Space or Enter) in order to install this product.",
                ['Ok'])

def confirm_erase_volume_groups(answers):
    problems = diskutil.findProblematicVGs(answers['guest-disks'])
    if len(problems) == 0:
        return SKIP_SCREEN

    if len(problems) == 1:
        xelogging.log("Problematic VGs: %s" % problems)
        affected = "The volume group affected is %s.  Are you sure you wish to continue?" % problems[0]
    elif len(problems) > 1:
        affected = "The volume groups affected are %s.  Are you sure you wish to continue?" % generalui.makeHumanList(problems)

    button = ButtonChoiceWindow(tui.screen,
                                "Conflicting LVM Volume Groups",
                                """Some or all of the disks you selected to install %s onto contain parts of LVM volume groups.  Proceeding with the installation will cause these volume groups to be deleted.

%s""" % (PRODUCT_BRAND, affected),
                                ['Continue', 'Back'], width=60)

    if button == 'back': return LEFT_BACKWARDS
    return RIGHT_FORWARDS

(
    REPOCHK_NO_ACCESS,
    REPOCHK_NO_REPO,
    REPOCHK_NO_BASE_REPO,
    REPOCHK_PRODUCT_VERSION_MISMATCH,
    REPOCHK_NO_ERRORS
) = range(5)

def check_repo_def(definition, require_base_repo):
    """ Check that the repository source definition gives access to suitable
    repositories. """
    try:
        repos = repository.repositoriesFromDefinition(*definition)
    except:
        return REPOCHK_NO_ACCESS
    else:
        if len(repos) == 0:
            return REPOCHK_NO_REPO
        elif constants.MAIN_REPOSITORY_NAME not in [r.identifier() for r in repos] and require_base_repo:
            return REPOCHK_NO_BASE_REPO
        elif False in [ r.compatible_with(version.PRODUCT_BRAND, product.THIS_PRODUCT_VERSION) for r in repos ]:
            return REPOCHK_PRODUCT_VERSION_MISMATCH

    return REPOCHK_NO_ERRORS

def interactive_check_repo_def(definition, require_base_repo):
    """ Check repo definition and display an appropriate dialog based
    on outcome.  Returns boolean indicating whether to continue with
    the definition given or not. """

    rc = check_repo_def(definition, require_base_repo)
    if rc == REPOCHK_NO_ACCESS:
        ButtonChoiceWindow(
            tui.screen,
            "Problem with location",
            "Setup was unable to access the location you specified - please check and try again.",
            ['Ok']
            )
    elif rc in [REPOCHK_NO_REPO, REPOCHK_NO_BASE_REPO]:
        ButtonChoiceWindow(
           tui.screen,
           "Problem with location",
           "A base installation repository was not found at that location.  Please check and try again.",
           ['Ok']
           )
    elif rc == REPOCHK_PRODUCT_VERSION_MISMATCH:
        cont = ButtonChoiceWindow(
            tui.screen,
            "Version Mismatch",
            "The location you specified contains packages designed for a different version of %s.\n\nThis may result in failures during installation, or an incorrect installation of the product." % version.PRODUCT_BRAND,
            ['Continue Anyway', 'Back']
            )
        return cont in ['continue anyway', None]
    else:
        return True


def select_installation_source(answers):
    ENTRY_LOCAL = 'Local media (CD-ROM)', 'local'
    ENTRY_URL = 'HTTP or FTP', 'url'
    ENTRY_NFS = 'NFS', 'nfs'
    entries = [ ENTRY_LOCAL, ENTRY_URL, ENTRY_NFS ]

    # default selection?
    if answers.has_key('source-media'):
        default = selectDefault(answers['source-media'], entries)
    else:
        default = ENTRY_LOCAL

    (button, entry) = ListboxChoiceWindow(
        tui.screen,
        "Select Installation Source",
        "Please select the type of source you would like to use for this installation",
        entries,
        ['Ok', 'Back'], default=default
        )

    if button == 'back': return LEFT_BACKWARDS

    # clear the source-address key?
    if answers.has_key('source-media') and answers['source-media'] != entry:
        answers['source-address'] = ""

    # store their answer:
    answers['source-media'] = entry

    # if local, check that the media is correct:
    if entry == 'local':
        answers['source-address'] = ""
        if not interactive_check_repo_def(('local', ''), True):
            return REPEAT_STEP

    return RIGHT_FORWARDS

def use_extra_media(answers, vt_warning):
    default = 0
    if answers.has_key('more-media') and not answers['more-media']:
        default = 1

    rc = snackutil.ButtonChoiceWindowEx(
        tui.screen,
        "Supplemental Packs",
        "Would you like to install any Supplemental Packs?",
        ['Yes', 'No', 'Back'],
        default = default
        )

    if rc == 'back': return LEFT_BACKWARDS

    answers['more-media'] = (rc != 'no')
    return RIGHT_FORWARDS

def setup_runtime_networking(answers):
    defaults = None
    try:
        if answers.has_key('net-admin-interface'):
            defaults = {'net-admin-interface': answers['net-admin-interface']}
            if answers.has_key('runtime-iface-configuration') and \
                    answers['runtime-iface-configuration'][1].has_key(answers['net-admin-interface']):
                defaults['net-admin-configuration'] = answers['runtime-iface-configuration'][1][answers['net-admin-interface']]
        elif answers.has_key('installation-to-overwrite'):
            defaults = answers['installation-to-overwrite'].readSettings()
    except:
        pass

    # Blacklist any interfaces currently used for accessing iSCSI disks
    blacklist = []
    try:
        if answers.has_key('primary-disk') and answers.has_key('net-iscsi-interface') and diskutil.is_iscsi(answers['primary-disk']):
            blacklist = [answers['net-iscsi-interface']]
    except:
        pass

    # Get the answers from the user
    return tui.network.requireNetworking(answers, defaults, blacklist=blacklist)

def get_url_location(answers):
    text = "Please enter the URL for your HTTP or FTP repository and, optionally, a username and password"
    url_field = Entry(50)
    user_field = Entry(16)
    passwd_field = Entry(16, password = 1)
    url_text = Textbox(11, 1, "URL:")
    user_text = Textbox(11, 1, "Username:")
    passwd_text = Textbox(11, 1, "Password:")

    if answers.has_key('source-address'):
        url = answers['source-address']
        (scheme, netloc, path, params, query) = urlparse.urlsplit(url)
        (hostname, username, password) = util.splitNetloc(netloc)
        if username != None:
            user_field.set(username)
            if password == None:
                url_field.set(url.replace('%s@' % username, '', 1))
            else:
                passwd_field.set(password)
                url_field.set(url.replace('%s:%s@' % (username, password), '', 1))
        else:
            url_field.set(url)

    done = False
    while not done:
        gf = GridFormHelp(tui.screen, "Specify Repository", None, 1, 3)
        bb = ButtonBar(tui.screen, [ 'Ok', 'Back' ])
        t = TextboxReflowed(50, text)

        entry_grid = Grid(2, 3)
        entry_grid.setField(url_text, 0, 0)
        entry_grid.setField(url_field, 1, 0)
        entry_grid.setField(user_text, 0, 1)
        entry_grid.setField(user_field, 1, 1, anchorLeft = 1)
        entry_grid.setField(passwd_text, 0, 2)
        entry_grid.setField(passwd_field, 1, 2, anchorLeft = 1)

        gf.add(t, 0, 0, padding = (0,0,0,1))
        gf.add(entry_grid, 0, 1, padding = (0,0,0,1))
        gf.add(bb, 0, 2, growx = 1)

        button = bb.buttonPressed(gf.runOnce())

        if button == 'back': return LEFT_BACKWARDS

        if user_field.value() != '':
            if passwd_field.value() != '':
                answers['source-address'] = url_field.value().replace('//', '//%s:%s@' % (user_field.value(), passwd_field.value()), 1)
            else:
                answers['source-address'] = url_field.value().replace('//', '//%s@' % user_field.value(), 1)
        else:
            answers['source-address'] = url_field.value()
        done = interactive_check_repo_def((answers['source-media'], answers['source-address']), True)
            
    return RIGHT_FORWARDS

def get_nfs_location(answers):
    text = "Please enter the server and path of your NFS share (e.g. myserver:/my/directory)"
    label = "NFS Path:"
        
    done = False
    while not done:
        if answers.has_key('source-address'):
            default = answers['source-address']
        else:
            default = ""
        (button, result) = EntryWindow(
            tui.screen,
            "Specify Repository",
            text,
            [(label, default)], entryWidth = 50, width = 50,
            buttons = ['Ok', 'Back'])
            
        answers['source-address'] = result[0]

        if button == 'back': return LEFT_BACKWARDS

        done = interactive_check_repo_def((answers['source-media'], answers['source-address']), True)
            
    return RIGHT_FORWARDS

def get_source_location(answers):
    if answers['source-media'] == 'url':
        return get_url_location(answers)
    else:
        return get_nfs_location(answers)

# select drive to use as the Dom0 disk:
def select_primary_disk(answers):
    diskEntries = diskutil.getQualifiedDiskList()

    entries = []
    target_is_sr = {}
    
    for de in diskEntries:
        (vendor, model, size) = diskutil.getExtendedDiskInfo(de)
        if constants.min_primary_disk_size <= diskutil.blockSizeToGBSize(size) <= constants.max_primary_disk_size:
            # determine current usage
            usage = 'unknown'
            target_is_sr[de] = False
            (boot, state, storage) = diskutil.probeDisk(de)
            if boot[0]:
                usage = PRODUCT_BRAND
            elif storage[0]:
                usage = 'SR'
                target_is_sr[de] = True
            stringEntry = "%s - %s [%s]" % (de, diskutil.getHumanDiskSize(size), usage)
            e = (stringEntry, de)
            entries.append(e)

    # we should have at least one disk
    if len(entries) == 0:
        ButtonChoiceWindow(tui.screen,
                           "No Primary Disk",
                           "No disk with sufficient space to install %s on was found." % PRODUCT_BRAND,
                           ['Cancel'])
        return EXIT

    # if only one disk, set default and skip this screen:
    if len(entries) == 1:
        answers['primary-disk'] = entries[0][1]
        answers['target-is-sr'] = target_is_sr[entries[0][1]]
        return SKIP_SCREEN

    # default value:
    default = None
    if answers.has_key('primary-disk'):
        default = selectDefault(answers['primary-disk'], entries)

    (button, entry) = ListboxChoiceWindow(
        tui.screen,
        "Select Primary Disk",
        """Please select the disk you would like to install %s on (disks with insufficient space are not shown).

You may need to change your system settings to boot from this disk.""" % (PRODUCT_BRAND),
        entries,
        ['Ok', 'Back'], width = 55, height = 4, scroll = 1, default = default)

    # entry contains the 'de' part of the tuple passed in
    answers['primary-disk'] = entry
    answers['target-is-sr'] = target_is_sr[entry]

    if button == 'back': return LEFT_BACKWARDS

    return RIGHT_FORWARDS

def check_sr_space(answers):
    tool = LVMTool()
    sr = tool.srPartition(answers['primary-disk'])
    assert sr

    if tool.deviceFreeSpace(sr) >= 2 * constants.root_size * 2 ** 20:
        return SKIP_SCREEN
    
    button = ButtonChoiceWindow(tui.screen,
                                "Insufficient Space",
                                """The disk selected contains a storage repository which does not have enough space to also install %s on.

Either return to the previous screen and select a different disk or cancel the installation, restart the %s and use %s to free up %dMB of space in the local storage repository.""" % (PRODUCT_BRAND, BRAND_SERVER, BRAND_CONSOLE, 2 * constants.root_size),
                                ['Back', 'Cancel'], width = 60)
    if button == 'back': return LEFT_BACKWARDS

    return EXIT

def select_guest_disks(answers):
    # if only one disk, set default and skip this screen:
    diskEntries = diskutil.getQualifiedDiskList()

    # filter out non-primary iscsi disks as only the primary disk
    # may be an iscsi disk
    def test(disk):
        if disk != answers['primary-disk'] and diskutil.is_iscsi(disk):
            return False
        return True
    diskEntries = filter(test, diskEntries)

    if len(diskEntries) == 0:
        answers['guest-disks'] = []
        return SKIP_SCREEN

    if len(diskEntries) == 1:
        answers['guest-disks'] = diskEntries
        return SKIP_SCREEN

    # set up defaults:
    if answers.has_key('guest-disks'):
        currently_selected = answers['guest-disks']
    else:
        currently_selected = answers['primary-disk']

    # Make a list of entries: (text, item)
    entries = []
    for de in diskEntries:
        (vendor, model, size) = diskutil.getExtendedDiskInfo(de)
        entry = "%s - %s [%s %s]" % (de, diskutil.getHumanDiskSize(size), vendor, model)
        entries.append((entry, de))
        
    text = TextboxReflowed(54, "Which disks would you like to use for %s storage?  \n\nOne storage repository will be created that spans the selected disks.  You can choose not to prepare any storage if you wish to create an advanced configuration after installation." % BRAND_GUEST)
    buttons = ButtonBar(tui.screen, [('Ok', 'ok'), ('Back', 'back')])
    cbt = CheckboxTree(4, scroll = 1)
    for (c_text, c_item) in entries:
        cbt.append(c_text, c_item, c_item in currently_selected)
    
    gf = GridFormHelp(tui.screen, 'Guest Storage', None, 1, 3)
    gf.add(text, 0, 0, padding = (0, 0, 0, 1))
    gf.add(cbt, 0, 1, padding = (0, 0, 0, 1))
    gf.add(buttons, 0, 2, growx = 1)
    
    button = buttons.buttonPressed(gf.runOnce())
    
    if button == 'back': return LEFT_BACKWARDS

    answers['guest-disks'] = cbt.getSelection()

    # if the user select no disks for guest storage, check this is what
    # they wanted:
    if answers['guest-disks'] == []:
        button = ButtonChoiceWindow(
            tui.screen,
            "Warning",
            """You didn't select any disks for %s storage.  Are you sure this is what you want?

If you proceed, please refer to the user guide for details on provisioning storage after installation.""" % BRAND_GUEST,
            ['Continue', 'Back']
            )
        if button == 'back': return REPEAT_STEP

    return RIGHT_FORWARDS

def confirm_installation(answers):
    text1 = "We have collected all the information required to install %s. " % PRODUCT_BRAND
    if answers['install-type'] == constants.INSTALL_TYPE_FRESH:
        # need to work on a copy of this! (hence [:])
        disks = answers['guest-disks'][:]
        if answers['primary-disk'] not in disks:
            disks.append(answers['primary-disk'])
        disks.sort()
        if len(disks) == 1:
            term = 'disk'
        else:
            term = 'disks'
        disks_used = generalui.makeHumanList(disks)
        text2 = "Please confirm you wish to proceed: all data on %s %s will be destroyed!" % (term, disks_used)
    elif answers['install-type'] == constants.INSTALL_TYPE_REINSTALL:
        if answers['primary-disk'] == answers['installation-to-overwrite'].primary_disk:
            text2 = "The installation will be performed over %s" % str(answers['installation-to-overwrite'])
        else:
            text2 = "The installation will migrate the installation from %s to %s" % (str(answers['installation-to-overwrite']), answers['primary-disk'])
        text2 += ", preserving existing %s in your storage repository." % BRAND_GUESTS
    text = text1 + "\n\n" + text2
    ok = 'Install %s' % PRODUCT_BRAND
    button = snackutil.ButtonChoiceWindowEx(
        tui.screen, "Confirm Installation", text,
        [ok, 'Back'], default = 1
        )

    if button == 'back': return LEFT_BACKWARDS
    return RIGHT_FORWARDS

def get_root_password(answers):
    done = False
        
    while not done:
        (button, result) = snackutil.PasswordEntryWindow(
            tui.screen, "Set Password",
            "Please specify the root password for this installation. \n\n(This is the password used when connecting to the %s from %s.)" % (BRAND_SERVER, BRAND_CONSOLE), 
            ['Password', 'Confirm'], buttons = ['Ok', 'Back'],
            )
        if button == 'back': return LEFT_BACKWARDS
        
        (pw, conf) = result
        if pw == conf:
            if pw == None or len(pw) < constants.MIN_PASSWD_LEN:
                ButtonChoiceWindow(tui.screen,
                               "Password Error",
                               "The password has to be %d characters or longer." % constants.MIN_PASSWD_LEN,
                               ['Ok'])
            else:
                done = True
        else:
            ButtonChoiceWindow(tui.screen,
                               "Password Error",
                               "The passwords you entered did not match.  Please try again.",
                               ['Ok'])

    # if they didn't select OK we should have returned already
    assert button in ['ok', None]
    answers['root-password'] = ('plaintext', pw)
    return RIGHT_FORWARDS

def get_name_service_configuration(answers):
    # horrible hack - need a tuple due to bug in snack that means
    # we don't get an arge passed if we try to just pass False
    def hn_callback((enabled, )):
        hostname.setFlags(FLAG_DISABLED, enabled)
    def ns_callback((enabled, )):
        for entry in [ns1_entry, ns2_entry, ns3_entry]:
            entry.setFlags(FLAG_DISABLED, enabled)

    hide_rb = answers['net-admin-configuration'].isStatic()

    # HOSTNAME:
    hn_title = Textbox(len("Hostname Configuration"), 1, "Hostname Configuration")
    
    # the hostname radio group:
    if not answers.has_key('manual-hostname'):
        # no current value set - if we currently have a useful hostname,
        # use that, else make up a random one:
        current_hn = socket.gethostname()
        if current_hn in [None, '', '(none)', 'localhost', 'localhost.localdomain']:
            answers['manual-hostname'] = True, util.mkRandomHostname()
        else:
            answers['manual-hostname'] = True, current_hn
    use_manual_hostname, manual_hostname = answers['manual-hostname']
    if manual_hostname == None:
        manual_hostname = ""
        
    hn_rbgroup = RadioGroup()
    hn_dhcp_rb = hn_rbgroup.add("Automatically set via DHCP", "hn_dhcp", not use_manual_hostname)
    hn_dhcp_rb.setCallback(hn_callback, data = (False,))
    hn_manual_rb = hn_rbgroup.add("Manually specify:", "hn_manual", use_manual_hostname)
    hn_manual_rb.setCallback(hn_callback, data = (True,))

    # the hostname text box:
    hostname = Entry(hide_rb and 30 or 42, text = manual_hostname)
    hostname.setFlags(FLAG_DISABLED, use_manual_hostname)
    hostname_grid = Grid(2, 1)
    if hide_rb:
        hostname_grid.setField(Textbox(15, 1, "Hostname:"), 0, 0)
    else:
        hostname_grid.setField(Textbox(4, 1, ""), 0, 0) # spacer
    hostname_grid.setField(hostname, 1, 0)

    # NAMESERVERS:
    def nsvalue(answers, id):
        if not answers.has_key('manual-nameservers'):
            if not answers.has_key('runtime-iface-configuration'):
                return ""
            # we have a runtime interface configuration; check to see if there is
            # configuration for the interface we're currently trying to configure.
            # If so, use it to get default values; we're being super careful to
            # check bounds, etc. here.  answers['runtime-iface-configuration'] is 
            # a pair, (all_dhcp, manual_config), where manual_config is a map
            # of interface name (string) -> network config.
            ric = answers['runtime-iface-configuration']
            if len(ric) != 2: # this should never really happen but best to be safe
                return ""
            else:
                ric_all_dhcp, ric_manual_config = ric
                if ric_manual_config == None or ric_all_dhcp:
                    return ""
                else:
                    if ric_manual_config.has_key(answers['net-admin-interface']):
                        ai = ric_manual_config[answers['net-admin-interface']]
                        if ai.isStatic() and id == 0 and ai.dns:
                            return ai.dns
                        else:
                            return ""
                    else:
                        return ""
        (mns, nss) = answers['manual-nameservers']
        if not mns or id >= len(nss):
            return ""
        else:
            return nss[id]

    ns_title = Textbox(len("DNS Configuration"), 1, "DNS Configuration")

    use_manual_dns = nsvalue(answers, 0) != ""
    if hide_rb:
        use_manual_dns = True

    # Name server radio group
    ns_rbgroup = RadioGroup()
    ns_dhcp_rb = ns_rbgroup.add("Automatically set via DHCP", "ns_dhcp",
                                not use_manual_dns)
    ns_dhcp_rb.setCallback(ns_callback, (False,))
    ns_manual_rb = ns_rbgroup.add("Manually specify:", "ns_dhcp",
                                  use_manual_dns)
    ns_manual_rb.setCallback(ns_callback, (True,))

    # Name server text boxes
    ns1_text = Textbox(15, 1, "DNS Server 1:")
    ns1_entry = Entry(30, nsvalue(answers, 0))
    ns1_grid = Grid(2, 1)
    ns1_grid.setField(ns1_text, 0, 0)
    ns1_grid.setField(ns1_entry, 1, 0)
    
    ns2_text = Textbox(15, 1, "DNS Server 2:")
    ns2_entry = Entry(30, nsvalue(answers, 1))
    ns2_grid = Grid(2, 1)
    ns2_grid.setField(ns2_text, 0, 0)
    ns2_grid.setField(ns2_entry, 1, 0)

    ns3_text = Textbox(15, 1, "DNS Server 3:")
    ns3_entry = Entry(30, nsvalue(answers, 2))
    ns3_grid = Grid(2, 1)
    ns3_grid.setField(ns3_text, 0, 0)
    ns3_grid.setField(ns3_entry, 1, 0)

    if nsvalue(answers, 0) == "":
        for entry in [ns1_entry, ns2_entry, ns3_entry]:
            entry.setFlags(FLAG_DISABLED, use_manual_dns)

    done = False
    while not done:
        buttons = ButtonBar(tui.screen, [('Ok', 'ok'), ('Back', 'back')])

        # The form itself:
        i = 1
        gf = GridFormHelp(tui.screen, 'Hostname and DNS Configuration', None, 1, 11)
        gf.add(hn_title, 0, 0, padding = (0,0,0,0))
        if not hide_rb:
            gf.add(hn_dhcp_rb, 0, 1, anchorLeft = True)
            gf.add(hn_manual_rb, 0, 2, anchorLeft = True)
            i += 2
        gf.add(hostname_grid, 0, i, padding = (0,0,0,1), anchorLeft = True)
    
        gf.add(ns_title, 0, i+1, padding = (0,0,0,0))
        if not hide_rb:
            gf.add(ns_dhcp_rb, 0, 5, anchorLeft = True)
            gf.add(ns_manual_rb, 0, 6, anchorLeft = True)
            i += 2
        gf.add(ns1_grid, 0, i+2)
        gf.add(ns2_grid, 0, i+3)
        gf.add(ns3_grid, 0, i+4, padding = (0,0,0,1))
    
        gf.add(buttons, 0, 10, growx = 1)

        button = buttons.buttonPressed(gf.runOnce())

        if button == 'back': return LEFT_BACKWARDS

        # manual hostname?
        if hn_manual_rb.selected():
            answers['manual-hostname'] = (True, hostname.value())
        else:
            answers['manual-hostname'] = (False, None)

        # manual nameservers?
        if ns_manual_rb.selected():
            answers['manual-nameservers'] = (True, [ns1_entry.value()])
            if ns2_entry.value() != '':
                answers['manual-nameservers'][1].append(ns2_entry.value())
                if ns3_entry.value() != '':
                    answers['manual-nameservers'][1].append(ns3_entry.value())
        else:
            answers['manual-nameservers'] = (False, None)
            
        # validate before allowing the user to continue:
        done = True

        if hn_manual_rb.selected():
            if not netutil.valid_hostname(hostname.value(), fqdn = True):
                done = False
                ButtonChoiceWindow(tui.screen,
                                       "Name Service Configuration",
                                       "The hostname you entered was not valid.",
                                       ["Back"])
                continue
        if ns_manual_rb.selected():
            if not netutil.valid_ip_addr(ns1_entry.value()) or \
                    (ns2_entry.value() != '' and not netutil.valid_ip_addr(ns2_entry.value())) or \
                    (ns3_entry.value() != '' and not netutil.valid_ip_addr(ns3_entry.value())):
                done = False
                ButtonChoiceWindow(tui.screen,
                                   "Name Service Configuration",
                                   "Please check that you have entered at least one nameserver, and that the nameservers you specified are valid.",
                                   ["Back"])

    return RIGHT_FORWARDS

def get_timezone_region(answers):
    entries = generalui.getTimeZoneRegions()

    # default value?
    default = None
    if answers.has_key('timezone-region'):
        default = answers['timezone-region']

    (button, entry) = ListboxChoiceWindow(
        tui.screen,
        "Select Time Zone",
        "Please select the geographical area that your %s is in:" % BRAND_SERVER,
        entries, ['Ok', 'Back'], height = 8, scroll = 1,
        default = default)

    if button == 'back': return LEFT_BACKWARDS

    answers['timezone-region'] = entries[entry]
    return RIGHT_FORWARDS

def get_timezone_city(answers):
    entries = generalui.getTimeZoneCities(answers['timezone-region'])

    # default value?
    default = None
    if answers.has_key('timezone-city') and answers['timezone-city'] in entries:
        default = answers['timezone-city'].replace('_', ' ')

    (button, entry) = ListboxChoiceWindow(
        tui.screen,
        "Select Time Zone",
        "Please select the city or area that the managed host is in (press a letter to jump to that place in the list):",
        map(lambda x: x.replace('_', ' '), entries),
        ['Ok', 'Back'], height = 8, scroll = 1, default = default)

    if button == 'back': return LEFT_BACKWARDS

    answers['timezone-city'] = entries[entry]
    answers['timezone'] = "%s/%s" % (answers['timezone-region'], answers['timezone-city'])
    return RIGHT_FORWARDS

def get_time_configuration_method(answers):
    ENTRY_NTP = "Using NTP", "ntp"
    ENTRY_MANUAL = "Manual time entry", "manual"
    entries = [ ENTRY_NTP, ENTRY_MANUAL ]

    # default value?
    default = None
    if answers.has_key("time-config-method"):
        default = selectDefault(answers['time-config-method'], entries)

    (button, entry) = ListboxChoiceWindow(
        tui.screen,
        "System Time",
        "How should the local time be determined?\n\n(Note that if you choose to enter it manually, you will need to respond to a prompt at the end of the installation.)",
        entries, ['Ok', 'Back'], default = default)

    if button == 'back': return LEFT_BACKWARDS

    if entry == 'ntp':
        answers['time-config-method'] = 'ntp'
    elif entry == 'manual':
        answers['time-config-method'] = 'manual'
    return RIGHT_FORWARDS

def get_ntp_servers(answers):
    if answers['time-config-method'] != 'ntp':
        return SKIP_SCREEN

    def dhcp_change():
        for x in [ ntp1_field, ntp2_field, ntp3_field ]:
            x.setFlags(FLAG_DISABLED, not dhcp_cb.value())

    hide_cb = answers['net-admin-configuration'].isStatic()

    gf = GridFormHelp(tui.screen, 'NTP Configuration', None, 1, 4)
    text = TextboxReflowed(60, "Please specify details of the NTP servers you wish to use (e.g. pool.ntp.org)?")
    buttons = ButtonBar(tui.screen, [("Ok", "ok"), ("Back", "back")])

    dhcp_cb = Checkbox("NTP is configured by my DHCP server", 1)
    dhcp_cb.setCallback(dhcp_change, ())

    def ntpvalue(answers, sn):
        if not answers.has_key('ntp-servers'):
            return ""
        else:
            servers = answers['ntp-servers']
            if sn < len(servers):
                return servers[sn]
            else:
                return ""

    ntp1_field = Entry(40, ntpvalue(answers, 0))
    ntp1_field.setFlags(FLAG_DISABLED, hide_cb)
    ntp2_field = Entry(40, ntpvalue(answers, 1))
    ntp2_field.setFlags(FLAG_DISABLED, hide_cb)
    ntp3_field = Entry(40, ntpvalue(answers, 2))
    ntp3_field.setFlags(FLAG_DISABLED, hide_cb)

    ntp1_text = Textbox(15, 1, "NTP Server 1:")
    ntp2_text = Textbox(15, 1, "NTP Server 2:")
    ntp3_text = Textbox(15, 1, "NTP Server 3:")

    entry_grid = Grid(2, 3)
    entry_grid.setField(ntp1_text, 0, 0)
    entry_grid.setField(ntp1_field, 1, 0)
    entry_grid.setField(ntp2_text, 0, 1)
    entry_grid.setField(ntp2_field, 1, 1)
    entry_grid.setField(ntp3_text, 0, 2)
    entry_grid.setField(ntp3_field, 1, 2)

    i = 1

    gf.add(text, 0, 0, padding = (0,0,0,1))
    if not hide_cb:
        gf.add(dhcp_cb, 0, 1)
        i += 1
    gf.add(entry_grid, 0, i, padding = (0,0,0,1))
    gf.add(buttons, 0, i+1, growx = 1)

    button = buttons.buttonPressed(gf.runOnce())

    if button == 'back': return LEFT_BACKWARDS

    if hide_cb or not dhcp_cb.value():
        servers = filter(lambda x: x != "", [ntp1_field.value(), ntp2_field.value(), ntp3_field.value()])
        if len(servers) == 0:
            ButtonChoiceWindow(tui.screen,
                               "NTP Configuration",
                               "You did not specify any NTP servers",
                               ["Ok"])
            return REPEAT_STEP
        else:
            answers['ntp-servers'] = servers
    else:
        answers['ntp-servers'] = []
    return RIGHT_FORWARDS

# this is used directly by backend.py - 'now' is localtime
def set_time(answers, now, show_back_button = False):
    done = False

    # set these outside the loop so we don't overwrite them in the
    # case that the user enters a bad value.
    day = Entry(3, "%02d" % now.day, scroll = 0)
    month = Entry(3, "%02d" % now.month, scroll = 0)
    year = Entry(5, "%04d" % now.year, scroll = 0)
    hour = Entry(3, "%02d" % now.hour, scroll = 0)
    minute = Entry(3, "%02d" % now.minute, scroll = 0)

    # loop until the form validates or they click back:
    while not done:
        gf = GridFormHelp(tui.screen, "Set local time", "", 1, 4)
        
        gf.add(TextboxReflowed(50, "Please set the current (local) date and time"), 0, 0, padding = (0,0,1,1))
        
        dategrid = Grid(7, 4)
        # TODO: switch day and month around if in appropriate timezone
        dategrid.setField(Textbox(12, 1, "Year (YYYY)"), 1, 0)
        dategrid.setField(Textbox(12, 1, "Month (MM)"), 2, 0)
        dategrid.setField(Textbox(12, 1, "Day (DD)"), 3, 0)
        
        dategrid.setField(Textbox(12, 1, "Hour (HH)"), 1, 2)
        dategrid.setField(Textbox(12, 1, "Min (MM)"), 2, 2)
        dategrid.setField(Textbox(12, 1, ""), 3, 2)
        
        dategrid.setField(Textbox(12, 1, ""), 0, 0)
        dategrid.setField(Textbox(12, 1, "Date:"), 0, 1)
        dategrid.setField(Textbox(12, 1, "Time (24h):"), 0, 3)
        dategrid.setField(Textbox(12, 1, ""), 0, 2)
        
        dategrid.setField(year, 1, 1, padding=(0,0,0,1))
        dategrid.setField(month, 2, 1, padding=(0,0,0,1))
        dategrid.setField(day, 3, 1, padding=(0,0,0,1))
        
        dategrid.setField(hour, 1, 3)
        dategrid.setField(minute, 2, 3)
        
        gf.add(dategrid, 0, 1, padding=(0,0,1,1))

        if show_back_button:
            buttons = ButtonBar(tui.screen, [("Ok", "ok"), ("Back", "back")])
        else:
            buttons = ButtonBar(tui.screen, [("Ok", "ok")])
        gf.add(buttons, 0, 2, growx = 1)
        
        button = buttons.buttonPressed(gf.runOnce())

        if button == 'back': return LEFT_BACKWARDS

        # first, check they entered something valid:
        try:
            datetime.datetime(int(year.value()),
                              int(month.value()),
                              int(day.value()),
                              int(hour.value()),
                              int(minute.value()))
        except ValueError, _:
            # the date was invalid - tell them why:
            done = False
            ButtonChoiceWindow(tui.screen, "Date error",
                               "The date/time you entered was not valid.  Please try again.",
                               ['Ok'])
        else:
            done = True

    # we're done:
    assert button == 'ok'
    answers['set-time'] = True
    answers['set-time-dialog-dismissed'] = datetime.datetime.now()
    answers['localtime'] = datetime.datetime(int(year.value()),
                                             int(month.value()),
                                             int(day.value()),
                                             int(hour.value()),
                                             int(minute.value()))
    return RIGHT_FORWARDS

def installation_complete():
    ButtonChoiceWindow(tui.screen,
                       "Installation Complete",
                       """The %s installation has completed.

Please remove any local media from the drive, and press Enter to reboot.""" % PRODUCT_BRAND,
                       ['Ok'])

    return RIGHT_FORWARDS

def request_media(medianame):
    button = ButtonChoiceWindow(tui.screen, "Media Not Found",
                                "Please insert the media labelled '%s' into your drive.  If the media is already present, then the installer was unable to locate it - please refer to your user guide, or a Technical Support Representative, for more information" % medianame,
                                ['Retry', 'Cancel'], width=50)

    return button != 'cancel'

###
# Getting more media:


