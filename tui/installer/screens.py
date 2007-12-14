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
import constants
import diskutil
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
        return uicontroller.EXIT
    else:
        return 1

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

    if button == 'back':
        return -1
    else:
        return 1

def get_admin_interface(answers):
    direction, iface = tui.network.select_netif("Which network interface would you like to use for connecting to the management server on your host?", answers['network-hardware'])
    if direction == 1:
        answers['net-admin-interface'] = iface
    return direction

def get_admin_interface_configuration(answers):
    assert answers.has_key('net-admin-interface')
    nic = answers['network-hardware'][answers['net-admin-interface']]
    rc, conf = tui.network.get_iface_configuration(
        nic, txt = "Please specify how networking should be configured for the management interface on this host."
        )
    if rc == 1:
        answers['net-admin-configuration'] = conf
    return rc

def get_installation_type(answers, insts):
    entries = [ ("Perform clean installation", None) ]
    for x in insts:
        if x.version < product.THIS_PRODUCT_VERSION:
            entries.append(("Upgrade %s" % str(x), (x, x.settingsAvailable())))
        else:
            entries.append(("Freshen %s" % str(x), (x, x.settingsAvailable())))

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

    if button != 'back':
        if entry == None:
            answers['install-type'] = constants.INSTALL_TYPE_FRESH
            answers['preserve-settings'] = False

            if answers.has_key('installation-to-overwrite'):
                del answers['installation-to-overwrite']
        else:
            answers['install-type'] = constants.INSTALL_TYPE_REINSTALL
            answers['installation-to-overwrite'], preservable = entry
            if not preservable:
                answers['preserve-settings'] = False

            for k in ['guest-disks', 'primary-disk', 'default-sr-uuid']:
                if answers.has_key(k):
                    del answers[k]
        return 1
    else:
        return -1

def ask_preserve_settings(answers):
    default = 0
    if answers.has_key('preserve-settings'):
        default = {True: 0, False: 1}[answers['preserve-settings']]

    rv = snackutil.ButtonChoiceWindowEx(
        tui.screen,
        "Preserve Settings",
        """Would you like to install %s with the same configuration as %s?

WARNING: Only settings initially configured using the installer will be preserved.""" % (PRODUCT_BRAND, str(answers['installation-to-overwrite'])),
        ['Yes', 'No', 'Back'], default=default
        )

    if rv in ['yes', 'no', None]:
        answers['preserve-settings'] = rv != 'no'
        return 1
    else:
        return -1

def force_backup_screen(answers):
    button = ButtonChoiceWindow(
        tui.screen,
        "Back-up Existing Installation",
        """The installer needs to create a backup of your existing installation.

This will erase data currently on the backup partition (which includes previous backups performed by the installer, and backups installed onto the host using the CLI's 'host-restore' function).

Continue with installation?""",
        ['Continue', 'Back']
        )
    if button in ['continue', None]:
        answers['backup-existing-installation'] = True
        return 1
    else:
        return -1

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

The backup will be placed on the second partition of the destination disk (%s), overwriting any previous backups on that volume.""" % (PRODUCT_BRAND, diskutil.determinePartitionName(answers['installation-to-overwrite'].primary_disk, 2)),
        ['Yes', 'No', 'Back'], default = default
        )

    if button == 'no':
        answers['backup-existing-installation'] = False
        return 1
    elif button == 'back':
        return -1
    else:
        answers['backup-existing-installation'] = True
        return 1

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
            return 1
        elif button == 'back':
            return -1
        elif button == None:
            ButtonChoiceWindow(
                tui.screen,
                "End User License Agreement",
                "You must select 'Accept EULA' (by highlighting it with the cursor keys, then pressing either Space or Enter to press it) in order to install this product.",
                ['Ok'])

def confirm_erase_volume_groups(answers):
    problems = diskutil.findProblematicVGs(answers['guest-disks'])
    if len(problems) == 0:
        return uicontroller.SKIP_SCREEN

    if len(problems) == 1:
        affected = "The volume group affected is %s.  Are you sure you wish to continue?" % problems[0]
    elif len(problems) > 1:
        affected = "The volume groups affected are %s.  Are you sure you wish to continue?" % generalui.makeHumanList(problems)

    button = ButtonChoiceWindow(tui.screen,
                                "Conflicting LVM Volume Gruops",
                                """Some or all of the disks you selected to install %s onto contain parts of LVM volume groups.  Proceeding with the installation will cause these volume groups to be deleted.

%s""" % (PRODUCT_BRAND, affected),
                                ['Continue', 'Back'], width=60)

    if button in [None, 'continue']:
        return 1
    elif button == 'back':
        return -1

(
    REPOCHK_NO_ACCESS,
    REPOCHK_NO_REPO,
    REPOCHK_NO_BASE_REPO,
    REPOCHK_PRODUCT_VERSION_MISMATCH,
    REPOCHK_NO_ERRORS
) = range(5)

def check_repo_def(definition, require_base_repo):
    """ Check that the repository source defintiion gives access to suitable
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

def interactive_check_repo_def(defintiion, require_base_repo):
    """ Check repo defintiion and display an appropriate dialog based
    on outcome.  Returns boolean indicating whether to continue with
    the definition given or not. """

    rc = check_repo_def(defintiion, require_base_repo)
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

    if button in ["ok", None]:
        # clear the source-address key?
        if answers.has_key('source-media') and answers['source-media'] != entry:
            answers['source-address'] = ""

        # store their answer:
        answers['source-media'] = entry

        # if local, check that the media is correct:
        if entry == 'local':
            answers['source-address'] = ""
            if not interactive_check_repo_def(('local', ''), True):
                return 0

        return 1

    elif button == "back":
        return -1

def use_extra_media(answers, vt_warning):
    if vt_warning:
        extra_text = "\n\nThis is strongly recommended as your system does not appear to support Windows guests.  If your system has hardware assist support, you may need to enable it in the BIOS to activate this capability."
    else:
        extra_text = ""

    if answers.has_key('more-media'):
        if answers['more-media']:
            default = 0
        else:
            default = 1
    else:
        default = 0

    rc = snackutil.ButtonChoiceWindowEx(
        tui.screen,
        "Linux Pack",
        "Would you like to install the Linux Pack from a second CD?" + extra_text,
        ['Yes', 'No', 'Back'],
        default = default
        )

    if rc in ['yes', None]:
        answers['more-media'] = True
        return 1
    elif rc == 'no':
        answers['more-media'] = False
        return 1
    else:
        return -1

def setup_runtime_networking(answers):
    return tui.network.requireNetworking(answers)

def get_source_location(answers):
    if answers['source-media'] == 'url':
        text = "Please enter the URL for your HTTP or FTP repository"
        label = "URL:"
    elif answers['source-media'] == 'nfs':
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

        if button in ['ok', None]:
            done = interactive_check_repo_def((answers['source-media'], answers['source-address']), True)
        elif button == "back":
            done = True
            
    if button in [None, 'ok']: return 1
    if button == 'back': return -1

# verify the installation source?
def verify_source(answers):
    done = False
    SKIP, VERIFY = range(2)
    entries = [ ("Skip verification", SKIP),
                ("Verify Installation Source", VERIFY), ]

    if answers['source-media'] == 'local':
        text = "Would you like to test your media?"
        default = selectDefault(VERIFY, entries)
    else:
        text = "Would you like to test your installation repository?  This may cause significant network traffic."
        default = selectDefault(SKIP, entries)

    while not done:
        (button, entry) = ListboxChoiceWindow(
            tui.screen, "Verify Installation Source", text,
            entries, ['Ok', 'Back'], default = default)
        if button != 'back' and entry == VERIFY:
            # we need to do the verification:
            done = interactive_source_verification(
                answers['source-media'], answers['source-address']
                )
        else:
            done = True

    if button == 'back':
        return -1
    else:
        return 1

def interactive_source_verification(media, address):
    try:
        repos = repository.repositoriesFromDefinition(
            media, address
            )
    except Exception, e:
        xelogging.log("Received exception %s whilst attempting to verify installation source." % str(e))
        ButtonChoiceWindow(
            tui.screen,
            "Problem accessing media",
            "Setup was unable to access the installation source you specified.",
            ['Ok']
            )
        return False
    else:
        if len(repos) == 0:
            ButtonChoiceWindow(
                tui.screen,
                "Problem accessing media",
                "No setup files were found at the location you specified.",
                ['Ok']
                )
            return False
        else:
            errors = []
            pd = tui.progress.initProgressDialog(
                "Verifying Installation Source", "Initialising...",
                len(repos) * 100
                )
            tui.progress.displayProgressDialog(0, pd)
            for i in range(len(repos)):
                r = repos[i]
                def progress(x):
                    #print i * 100 + x
                    tui.progress.displayProgressDialog(i*100 + x, pd, "Checking %s..." % r._name)
                errors.extend(r.check(progress))

            tui.progress.clearModelessDialog()

            if len(errors) != 0:
                errtxt = generalui.makeHumanList([x.name for x in errors])
                ButtonChoiceWindow(
                    tui.screen,
                    "Problems found",
                    "Some packages appeared damaged.  These were: %s" % errtxt,
                    ['Ok']
                    )
                return False
            else:
                repo_names = generalui.makeHumanList( ['"%s"' %x.name() for x in repos])
                ButtonChoiceWindow(
                    tui.screen,
                    "Verification Successful",
                    "Veification of your installation pack(s) %s completed successfully: no problems were found." % repo_names,
                    ['Ok']
                    )
                return True


# select drive to use as the Dom0 disk:
def select_primary_disk(answers):
    diskEntries = diskutil.getQualifiedDiskList()

    entries = []
    
    for de in diskEntries:
        (vendor, model, size) = diskutil.getExtendedDiskInfo(de)
        if constants.min_primary_disk_size <= diskutil.blockSizeToGBSize(size) <= constants.max_primary_disk_size:
            stringEntry = "%s - %s [%s %s]" % (de, diskutil.getHumanDiskSize(size), vendor, model)
            e = (stringEntry, de)
            entries.append(e)

    # we should have at least one disk (this should be checked before the UI is
    # started.
    assert len(entries) != 0

    # if only one disk, set default and skip this screen:
    if len(diskEntries) == 1:
        answers['primary-disk'] = diskEntries[0]
        return uicontroller.SKIP_SCREEN

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
        ['Ok', 'Back'], width = 55, default = default)

    # entry contains the 'de' part of the tuple passed in
    answers['primary-disk'] = entry

    if button == "ok" or button == None: return 1
    if button == "back": return -1

def select_guest_disks(answers):
    # if only one disk, set default and skip this screen:
    diskEntries = diskutil.getQualifiedDiskList()
    if len(diskEntries) == 1:
        answers['guest-disks'] = diskEntries
        return uicontroller.SKIP_SCREEN

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
        
    text = TextboxReflowed(50, "Which disks would you like to use for %s storage?  \n\nOne storage repository will be created that spans the selected disks.  You can choose not to prepare any storage if you wish to create an advanced configuration after installation." % BRAND_GUEST)
    buttons = ButtonBar(tui.screen, [('Ok', 'ok'), ('Back', 'back')])
    cbt = CheckboxTree(4, 1)
    for (c_text, c_item) in entries:
        cbt.append(c_text, c_item, c_item in currently_selected)
    
    gf = GridFormHelp(tui.screen, 'Guest Storage', None, 1, 3)
    gf.add(text, 0, 0, padding = (0, 0, 0, 1))
    gf.add(cbt, 0, 1, padding = (0, 0, 0, 1))
    gf.add(buttons, 0, 2)
    
    result = gf.runOnce()
    
    answers['guest-disks'] = cbt.getSelection()

    # if the user select no disks for guest storage, check this is what
    # they wanted:
    if buttons.buttonPressed(result) == 'ok' and answers['guest-disks'] == []:
        button = ButtonChoiceWindow(
            tui.screen,
            "Warning",
            """You didn't select any disks for %s storage.  Are you sure this is what you want?

If you proceed, please refer to the user guide for details on provisioning storage after installation.""" % BRAND_GUEST,
            ['Continue', 'Back']
            )
        if button == 'back':
            return 0

    if buttons.buttonPressed(result) in [None, 'ok']: return 1
    if buttons.buttonPressed(result) == 'back': return -1

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
        text2 = "The installation will be performed over %s, preserving existing %s in your storage repository." % (str(answers['installation-to-overwrite']), BRAND_GUESTS)

    text = text1 + "\n\n" + text2
    ok = 'Install %s' % PRODUCT_BRAND
    button = snackutil.ButtonChoiceWindowEx(
        tui.screen, "Confirm Installation", text,
        [ok, 'Back'], default = 1
        )

    if button in [None, string.lower(ok)]: return 1
    if button == "back": return -1

def get_root_password(answers):
    done = False
        
    while not done:
        (button, result) = snackutil.PasswordEntryWindow(
            tui.screen, "Set Password",
            "Please specify the root password for this installation. \n\n(This is the password used when connecting to the %s from %s.)" % (BRAND_SERVER, BRAND_CONSOLE), 
            ['Password', 'Confirm'], buttons = ['Ok', 'Back'],
            )
        if button == 'back':
            return -1
        
        (pw, conf) = result
        if pw == conf:
            if pw == None or len(pw) < constants.MIN_PASSWD_LEN:
                ButtonChoiceWindow(tui.screen,
                               "Password Error",
                               "The password has to be 6 characters or longer.",
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
    answers['root-password'] = pw
    answers['root-password-type'] = 'plaintext'
    return 1

def get_name_service_configuration(answers):
    # horrible hack - need a tuple due to bug in snack that means
    # we don't get an arge passed if we try to just pass False
    def hn_callback((enabled, )):
        hostname.setFlags(FLAG_DISABLED, enabled)
    def ns_callback((enabled, )):
        for entry in [ns1_entry, ns2_entry, ns3_entry]:
            entry.setFlags(FLAG_DISABLED, enabled)

    done = False
    while not done:
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
        hostname = Entry(42, text = manual_hostname)
        hostname.setFlags(FLAG_DISABLED, use_manual_hostname)
        hostname_grid = Grid(2, 1)
        hostname_grid.setField(Textbox(4, 1, ""), 0, 0) # spacer
        hostname_grid.setField(hostname, 1, 0)

        # NAMESERVERS:
        ns_title = Textbox(len("DNS Configuration"), 1, "DNS Configuration")

        # Name server radio group
        ns_rbgroup = RadioGroup()
        ns_dhcp_rb = ns_rbgroup.add("Automatically set via DHCP", "ns_dhcp",
                                    not (answers.has_key('manual-nameservers') and answers['manual-nameservers'][0]))
        ns_dhcp_rb.setCallback(ns_callback, (False,))
        ns_manual_rb = ns_rbgroup.add("Manually specify:", "ns_dhcp",
                                    answers.has_key('manual-nameservers') and answers['manual-nameservers'][0])
        ns_manual_rb.setCallback(ns_callback, (True,))

        # Name server text boxes
        def nsvalue(answers, id):
            if not answers.has_key('manual-nameservers'):
                return ""
            (mns, nss) = answers['manual-nameservers']
            if not mns:
                return ""
            else:
                return nss[id]
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

        if not (answers.has_key('manual-nameservers') and \
                answers['manual-nameservers'][0]):
            for entry in [ns1_entry, ns2_entry, ns3_entry]:
                entry.setFlags(FLAG_DISABLED, 0)

        buttons = ButtonBar(tui.screen, [('Ok', 'ok'), ('Back', 'back')])

        # The form itself:
        gf = GridFormHelp(tui.screen, 'Hostname and DNS Configuration', None, 1, 11)
        gf.add(hn_title, 0, 0, padding = (0,0,0,0))
        gf.add(hn_dhcp_rb, 0, 1, anchorLeft = True)
        gf.add(hn_manual_rb, 0, 2, anchorLeft = True)
        gf.add(hostname_grid, 0, 3, padding = (0,0,0,1), anchorLeft = True)
        
        gf.add(ns_title, 0, 4, padding = (0,0,0,0))
        gf.add(ns_dhcp_rb, 0, 5, anchorLeft = True)
        gf.add(ns_manual_rb, 0, 6, anchorLeft = True)
        gf.add(ns1_grid, 0, 7)
        gf.add(ns2_grid, 0, 8)
        gf.add(ns3_grid, 0, 9, padding = (0,0,0,1))
    
        gf.add(buttons, 0, 10)

        result = gf.runOnce()

        if buttons.buttonPressed(result) == 'back':
            done = True
        else:
            # manual hostname?
            if hn_manual_rb.selected():
                answers['manual-hostname'] = (True, hostname.value())
            else:
                answers['manual-hostname'] = (False, None)

            # manual nameservers?
            if ns_manual_rb.selected():
                answers['manual-nameservers'] = (True, [ns1_entry.value(),
                                                        ns2_entry.value(),
                                                        ns3_entry.value()])
            else:
                answers['manual-nameservers'] = (False, None)
            
            # validate before allowing the user to continue:
            done = True

            if hn_manual_rb.selected():
                if not netutil.valid_hostname(hostname.value()):
                    done = False
                    ButtonChoiceWindow(tui.screen,
                                       "Name Service Configuration",
                                       "The hostname you entered was not valid.",
                                       ["Back"])
            if ns_manual_rb.selected():
                if not netutil.valid_ip_addr(ns1_entry.value()) or \
                   (ns2_entry.value() != '' and not netutil.valid_ip_addr(ns2_entry.value())) or \
                   (ns3_entry.value() != '' and not netutil.valid_ip_addr(ns3_entry.value())):
                    done = False
                    ButtonChoiceWindow(tui.screen,
                                       "Name Service Configuration",
                                       "Please check that you have entered at least one nameserver, and that the nameservers you specified are valid.",
                                       ["Back"])

    if buttons.buttonPressed(result) in [None, "ok"]:
        return 1
    else:
        return -1

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

    if button in ["ok", None]:
        answers['timezone-region'] = entries[entry]
        return 1
    
    if button == "back": return -1

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

    if button == "ok" or button == None:
        answers['timezone-city'] = entries[entry]
        answers['timezone'] = "%s/%s" % (answers['timezone-region'], answers['timezone-city'])
        return 1
    
    if button == "back": return -1

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

    if button == "ok" or button == None:
        if entry == 'ntp':
            answers['time-config-method'] = 'ntp'
        elif entry == 'manual':
            answers['time-config-method'] = 'manual'
        return 1
    if button == "back": return -1

def get_ntp_servers(answers):
    if answers['time-config-method'] != 'ntp':
        return uicontroller.SKIP_SCREEN

    def dhcp_change():
        for x in [ ntp1_field, ntp2_field, ntp3_field ]:
            x.setFlags(FLAG_DISABLED, not dhcp_cb.value())

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
    ntp1_field.setFlags(FLAG_DISABLED, False)
    ntp2_field = Entry(40, ntpvalue(answers, 1))
    ntp2_field.setFlags(FLAG_DISABLED, False)
    ntp3_field = Entry(40, ntpvalue(answers, 2))
    ntp3_field.setFlags(FLAG_DISABLED, False)

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

    gf.add(text, 0, 0, padding = (0,0,0,1))
    gf.add(dhcp_cb, 0, 1)
    gf.add(entry_grid, 0, 2, padding = (0,0,0,1))
    gf.add(buttons, 0, 3)

    result = gf.runOnce()

    if buttons.buttonPressed(result) in ['ok', None]:
        if not dhcp_cb.value():
            servers = filter(lambda x: x != "", [ntp1_field.value(), ntp2_field.value(), ntp3_field.value()])
            if len(servers) == 0:
                ButtonChoiceWindow(tui.screen,
                                   "NTP Configuration",
                                   "You didn't specify any NTP servers!",
                                   ["Ok"])
                return 0
            else:
                answers['ntp-servers'] = servers
        else:
            answers['ntp-servers'] = []
        return 1
    elif buttons.buttonPressed(result) == 'back':
        return -1

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
        gf.add(buttons, 0, 2)
        
        result = gf.runOnce()

        if buttons.buttonPressed(result) == "back":
            return -1

        # first, check they entered something valied:
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
    assert buttons.buttonPressed(result) == "ok"
    answers['set-time'] = True
    answers['set-time-dialog-dismissed'] = datetime.datetime.now()
    answers['localtime'] = datetime.datetime(int(year.value()),
                                             int(month.value()),
                                             int(day.value()),
                                             int(hour.value()),
                                             int(minute.value()))
    return 1

def installation_complete():
    ButtonChoiceWindow(tui.screen,
                       "Installation Complete",
                       """The %s installation has completed.

Please remove any local media from the drive, and press enter to reboot.""" % PRODUCT_BRAND,
                       ['Ok'])

    return 1

def request_media(medianame):
    button = ButtonChoiceWindow(tui.screen, "Media Not Found",
                                "Please insert the media labelled '%s' into your drive.  If the media is already present, then the installer was unable to locate it - please refer to your user guide, or a Technical Support Representative, for more information" % medianame,
                                ['Retry', 'Cancel'], width=50)

    return button != "cancel"

###
# Getting more media:


