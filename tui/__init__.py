# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Text user interface functions
#
# written by Andrew Peace

import sys
import string
import datetime

import generalui
import uicontroller
import tui.network
import constants
import diskutil
import xelogging
from version import *
import hardware
import snackutil
import repository

from snack import *
import os.path

screen = None

# functions to start and end the GUI - these create and destroy a snack screen as
# appropriate.
def init_ui(results, is_subui):
    global screen
    
    screen = SnackScreen()
    screen.drawRootText(0, 0, "Welcome to the %s Installer - Version %s (#%s)" % (PRODUCT_BRAND, PRODUCT_VERSION, BUILD_NUMBER))
    screen.drawRootText(0, 1, "Copyright (c) %s %s" % (COPYRIGHT_YEARS, COMPANY_NAME_LEGAL))

def end_ui():
    global screen
    
    if screen:
        screen.finish()
        
def suspend_ui():
    global screen
    if screen:
        screen.suspend()
        
def resume_ui():
    global screen
    if screen:
        screen.resume()

def selectDefault(key, entries):
    """ Given a list of (text, key) and a key to select, returns the appropriate
    text,key pair, or None if not in entries. """

    for text, k in entries:
        if key == k:
            return text, k
    return None

# welcome screen:
def welcome_screen(answers):
    global screen

    button = ButtonChoiceWindow(screen,
                                "Welcome to %s Setup" % PRODUCT_BRAND,
                                """This setup tool will install %s on your server.

This install will overwrite data on any hard drives you select to use during the install process. Please make sure you have backed up any data on this system before proceeding with the product install.""" % PRODUCT_BRAND,
                                ['Ok', 'Cancel Installation'], width = 60)

    # advance to next screen:
    if button == 'cancel installation':
        return uicontroller.EXIT
    else:
        return 1

def hardware_warnings(answers, ram_warning, vt_warning):
    vt_not_found_text = "Hardware virtualization assist support is not available on this system.  Either it is not present, or is disabled in the system's BIOS.  This capability is required to start Windows virtual machines."
    not_enough_ram_text = "%s requires %dMB of system memory in order to function normally.  Your system appears to ahve less than this, which may cause problems during startup." % (PRODUCT_BRAND, constants.MIN_SYSTEM_RAM_MB_RAW)

    text = "The following problem(s) were found with your hardware:\n\n"
    if vt_warning:
        text += vt_not_found_text + "\n\n"
    if ram_warning:
        text += not_enough_ram_text + "\n\n"
    text += "You may continue with the installation, though %s might have limited functionality until you have addressed these problems." % PRODUCT_BRAND

    button = ButtonChoiceWindow(
        screen,
        "System Hardware",
        text,
        ['Ok', 'Back'],
        width = 60
        )

    if button == 'back':
        return -1
    else:
        return 1

def not_enough_space_screen(answers):
    global screen

    ButtonChoiceWindow(screen,
                       "Insufficient disk space",
                       """Unfortunately, you do not have a disk with enough space to install %s.  You need at least one %sGB or greater disk in the system for the installation to proceed.""" % (PRODUCT_BRAND, str(constants.min_primary_disk_size)),
                       ['Exit'], width=60)

    # leave the installer:
    return 1

def get_installation_type(answers, insts):
    if len(insts) == 0:
        answers['install-type'] = constants.INSTALL_TYPE_FRESH
        return uicontroller.SKIP_SCREEN

    entries = [ ("Perform clean installation", None) ]
    entries.extend([("Re-install over %s" % str(x), x) for x in insts])

    # default value?
    if answers.has_key('install-type') and answers['install-type'] == constants.INSTALL_TYPE_REINSTALL:
        default = selectDefault(answers['installation-to-overwrite'], entries)
    else:
        default = None

    (button, entry) = ListboxChoiceWindow(
        screen,
        "Installation Type",
        "One or more existing product installations that can be refreshed using this setup tool have been detected.  What would you like to do?",
        entries,
        ['Ok', 'Back'], width=60, default = default)

    if button != 'back':
        if entry == None:
            answers['install-type'] = constants.INSTALL_TYPE_FRESH

            if answers.has_key('installation-to-overwrite'):
                del answers['installation-to-overwrite']
        else:
            answers['install-type'] = constants.INSTALL_TYPE_REINSTALL
            answers['installation-to-overwrite'] = entry

            for k in ['guest-disks', 'primary-disk', 'default-sr-uuid']:
                if answers.has_key(k):
                    del answers[k]
        return 1
    else:
        return -1

def backup_existing_installation(answers):
    if answers['install-type'] != constants.INSTALL_TYPE_REINSTALL:
        return uicontroller.SKIP_SCREEN

    # default selection:
    if answers.has_key('backup-existing-installation'):
        if answers['backup-existing-installation']:
            default = 0
        else:
            default = 1
    else:
        default = 0

    button = snackutil.ButtonChoiceWindowEx(
        screen,
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
    global screen

    eula_file = open(constants.EULA_PATH, 'r')
    eula = string.join(eula_file.readlines())
    eula_file.close()

    while True:
        button = snackutil.ButtonChoiceWindowEx(
            screen,
            "End User License Agreement",
            eula,
            ['Accept EULA', 'Back'], width=60, default=1)

        if button == 'accept eula':
            return 1
        elif button == 'back':
            return -1
        elif button == None:
            ButtonChoiceWindow(
                screen,
                "End User License Agreement",
                "You must select 'Accept EULA' (by highlighting it with the cursor keys, then pressing either Space or Enter to press it) in order to install this product.",
                ['Ok'])

def confirm_erase_volume_groups(answers):
    global screen

    # if install type is re-install, skip this screen:
    if answers['install-type'] == constants.INSTALL_TYPE_REINSTALL:
        return uicontroller.SKIP_SCREEN

    problems = diskutil.findProblematicVGs(answers['guest-disks'])
    if len(problems) == 0:
        return uicontroller.SKIP_SCREEN

    if len(problems) == 1:
        affected = "The volume group affected is %s.  Are you sure you wish to continue?" % problems[0]
    elif len(problems) > 1:
        affected = "The volume groups affected are %s.  Are you sure you wish to continue?" % generalui.makeHumanList(problems)

    button = ButtonChoiceWindow(screen,
                                "Conflicting LVM Volume Gruops",
                                """Some or all of the disks you selected to install %s onto contain parts of LVM volume groups.  Proceeding with the installation will cause these volume groups to be deleted.

%s""" % (PRODUCT_BRAND, affected),
                                ['Continue', 'Cancel Installation'], width=60)

    if button in [None, 'continue']:
        return 1
    elif button == 'cancel installation':
        return uicontroller.EXIT

def select_installation_source(answers):
    global screen
    ENTRY_LOCAL = 'Local media (CD-ROM)', 'local'
    ENTRY_URL = 'HTTP or FTP', 'url'
    ENTRY_NFS = 'NFS', 'nfs'
    entries = [ ENTRY_LOCAL, ENTRY_URL, ENTRY_NFS ]

    # default selection?
    if answers.has_key('source-media'):
        _, default = selectDefault(answers['source-media'], entries)
    else:
        _, default = ENTRY_LOCAL
        
    # widgets:
    text = TextboxReflowed(50, "Please select the type of source you would like to use for this installation:")
    listbox = Listbox(len(entries))
    for e in entries:
        listbox.append(*e)
    listbox.setCurrent(default)
    cbMoreMedia = Checkbox("Use additional media", False)
    buttons = ButtonBar(screen, [('Ok', 'ok'), ('Back', 'back')])
    # callback
    def lbcallback():
        cbMoreMedia.setFlags(FLAG_DISABLED, listbox.current() == 'local')
    listbox.setCallback(lbcallback)
    lbcallback()
    gfhDialog = GridFormHelp(screen, "Installation Source", None, 1, 4)
    gfhDialog.add(text, 0, 0, padding = (0, 0, 0, 1))
    gfhDialog.add(listbox, 0, 1, padding = (0, 0, 0, 1))
    gfhDialog.add(cbMoreMedia, 0, 2, padding = (0, 0, 0, 1))
    gfhDialog.add(buttons, 0, 3)

    result = gfhDialog.runOnce()
    entry = listbox.current()
    button = buttons.buttonPressed(result)
        
    answers['source-media'] = entry
    if entry == 'local':
        answers['source-address'] = ""

    answers['more-media'] = cbMoreMedia.value()

    if answers['source-media'] == 'local':
        # we should check that we can see a CD now:
        l = len(repository.repositoriesFromDefinition('local', ''))
        if l == 0:
            OKDialog(
                "Media not found",
                "Your installation media could not be found.  Please ensure it is inserted into the drive, and try again.  If you continue to have problems, please consult your user guide or Technical Support Representative."
                )
            return 0
        
    if button == "ok" or button == None: return 1
    if button == "back": return -1

def setup_runtime_networking(answers):
    if answers['source-media'] not in ['url', 'nfs']:
        return uicontroller.SKIP_SCREEN

    return generalui.requireNetworking(answers, tui)

def get_source_location(answers):
    if answers['source-media'] not in ['url', 'nfs']:
        return uicontroller.SKIP_SCREEN

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
            screen,
            "Specify Repository",
            text,
            [(label, default)], entryWidth = 50,
            buttons = ['Ok', 'Back'])
            
        answers['source-address'] = result[0]

        if button in ['ok', None]:
            location = result[0]
            # santiy check the location given
            try:
                repos = repository.repositoriesFromDefinition(
                    answers['source-media'], location
                    )
            except:
                ButtonChoiceWindow(
                    screen,
                    "Problem with location",
                    "Setup was unable to access the location you specified - please check and try again.",
                    ['Ok']
                    )
            else:
                if len(repos) == 0:
                    ButtonChoiceWindow(
                       screen,
                       "Problem with location",
                       "No repository was found at that location - please check and try again.",
                       ['Ok']
                       )
                else:
                    done = True

        elif button == "back":
            done = True
            
    if button in [None, 'ok']: return 1
    if button == 'back': return -1

# verify the installation source?
def verify_source(answers):
    done = False
    while not done:
        SKIP, VERIFY = range(2)
        entries = [ ("Skip verification", SKIP),
                    ("Verify Installation Source", VERIFY), ]

        (button, entry) = ListboxChoiceWindow(
            screen, "Verify Installation Source",
            "Would you like to verify the integrity of your installation repository/media?  (This may take a while to complete and could cause significant network traffic if performing a network installation.)",
            entries, ['Ok', 'Back'])
        if entry == SKIP:
            done = True
        elif button != 'back' and entry == VERIFY:
            # we need to do the verification:
            done = interactive_source_verification(
                answers['source-media'], answers['source-address']
                )
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
            screen,
            "Problem accessing media",
            "Setup was unable to access the installation source you specified.",
            ['Ok']
            )
        return False
    else:
        if len(repos) == 0:
            ButtonChoiceWindow(
                screen,
                "Problem accessing media",
                "No setup files were found at the location you specified.",
                ['Ok']
                )
            return False
        else:
            errors = []
            pd = initProgressDialog(
                "Verifying installation source", "Initialising...",
                len(repos) * 100
                )
            displayProgressDialog(0, pd)
            for i in range(len(repos)):
                r = repos[i]
                def progress(x):
                    #print i * 100 + x
                    displayProgressDialog(i*100 + x, pd, "Checking %s..." % r._name)
                errors.extend(r.check(progress))

            clearModelessDialog()

            if len(errors) != 0:
                ButtonChoiceWindow(
                    screen,
                    "Problems found",
                    "Some packages appeared damaged.  These were: %s" % errors,
                    ['Ok']
                    )
                return False
            else:
                return True


# select drive to use as the Dom0 disk:
def select_primary_disk(answers):
    global screen

    # if re-install, skip this screen:
    if answers['install-type'] == constants.INSTALL_TYPE_REINSTALL:
        return uicontroller.SKIP_SCREEN

    # if only one disk, set default and skip this screen:
    diskEntries = diskutil.getQualifiedDiskList()
    if len(diskEntries) == 1:
        answers['primary-disk'] = diskEntries[0]
        return uicontroller.SKIP_SCREEN

    entries = []
    
    for de in diskEntries:
        (vendor, model, size) = diskutil.getExtendedDiskInfo(de)
        if diskutil.blockSizeToGBSize(size) >= constants.min_primary_disk_size:
            stringEntry = "%s - %s [%s %s]" % (de, diskutil.getHumanDiskSize(size), vendor, model)
            e = (stringEntry, de)
            entries.append(e)

    # default value:
    default = None
    if answers.has_key('primary-disk'):
        default = selectDefault(answers['primary-disk'], entries)

    (button, entry) = ListboxChoiceWindow(
        screen,
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
    global screen

    # if re-install, skip this screen:
    if answers['install-type'] == constants.INSTALL_TYPE_REINSTALL:
        return uicontroller.SKIP_SCREEN

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
        
    text = TextboxReflowed(50, "Which disks would you like to use for %s storage?" % BRAND_GUEST)
    buttons = ButtonBar(screen, [('Ok', 'ok'), ('Back', 'back')])
    cbt = CheckboxTree(4, 1)
    for (c_text, c_item) in entries:
        cbt.append(c_text, c_item, c_item in currently_selected)
    
    gf = GridFormHelp(screen, 'Guest Storage', None, 1, 3)
    gf.add(text, 0, 0, padding = (0, 0, 0, 1))
    gf.add(cbt, 0, 1, padding = (0, 0, 0, 1))
    gf.add(buttons, 0, 2)
    
    result = gf.runOnce()
    
    answers['guest-disks'] = cbt.getSelection()

    # if the user select no disks for guest storage, check this is what
    # they wanted:
    if buttons.buttonPressed(result) == 'ok' and answers['guest-disks'] == []:
        button = ButtonChoiceWindow(
            screen,
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
    elif answers['install-type'] == consatnts.INSTALL_TYPE_REINSTALL:
        text2 = "The installation will be performed over " % (PRODUCT_BRAND, str(answers['installation-to-overwrite']), BRAND_GUESTS)

    text = text1 + "\n\n" + text2
    ok = 'Install %s' % PRODUCT_BRAND
    button = snackutil.ButtonChoiceWindowEx(
        screen, "Confirm Installation", text,
        [ok, 'Back'], default = 1
        )

    if button in [None, string.lower(ok)]: return 1
    if button == "back": return -1

def get_root_password(answers):
    global screen
    done = False
        
    while not done:
        (button, result) = snackutil.PasswordEntryWindow(screen,
                                               "Set Password",
                                               "Please specify the root password for this installation. \n\n(This is the password used when connecting to the %s from the %s.)" % (BRAND_SERVER, BRAND_CONSOLE),
                                               ['Password', 'Confirm'],
                                               buttons = ['Ok', 'Back'])
        if button == 'back':
            return -1
        
        (pw, conf) = result
        if pw == conf:
            if pw == None or len(pw) < constants.MIN_PASSWD_LEN:
                ButtonChoiceWindow(screen,
                               "Password Error",
                               "The password has to be 6 characters or longer.",
                               ['Ok'])
            else:
                done = True
        else:
            ButtonChoiceWindow(screen,
                               "Password Error",
                               "The passwords you entered did not match.  Please try again.",
                               ['Ok'])

    # if they didn't select OK we should have returned already
    assert button in ['ok', None]
    answers['root-password'] = pw
    return 1

def get_name_service_configuration(answers):
    global screen

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
        hn_rbgroup = RadioGroup()
        hn_dhcp_rb = hn_rbgroup.add("Automatically set via DHCP", "hn_dhcp", not (answers.has_key('manual-hostname') and answers['manual-hostname'][0]))
        hn_dhcp_rb.setCallback(hn_callback, data = (False,))
        hn_manual_rb = hn_rbgroup.add("Manually specify:", "hn_manual", answers.has_key('manual-hostname') and answers['manual-hostname'][0])
        hn_manual_rb.setCallback(hn_callback, data = (True,))

        # the hostname text box:
        hostname = Entry(42, text = answers.has_key('manual-hostname') and answers['manual-hostname'][1] or "")
        hostname.setFlags(FLAG_DISABLED, answers.has_key('manual-hostname') and answers['manual-hostname'][0])
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
        ns3_entry = Entry(30, nsvalue(answers, 1))
        ns3_grid = Grid(2, 1)
        ns3_grid.setField(ns3_text, 0, 0)
        ns3_grid.setField(ns3_entry, 1, 0)

        if not (answers.has_key('manual-nameservers') and \
                answers['manual-nameservers'][0]):
            for entry in [ns1_entry, ns2_entry, ns3_entry]:
                entry.setFlags(FLAG_DISABLED, 0)

        buttons = ButtonBar(screen, [('Ok', 'ok'), ('Back', 'back')])

        # The form itself:
        gf = GridFormHelp(screen, 'Hostname and DNS Configuration', None, 1, 11)
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

            def valid_hostname(x, emptyValid = False):
                return (x != "" or emptyValid) and \
                       " " not in x
            if hn_manual_rb.selected():
                if not valid_hostname(hostname.value()):
                    done = False
                    ButtonChoiceWindow(screen,
                                       "Name Service Configuration",
                                       "The hostname you entered was not valid.",
                                       ["Back"])
            if ns_manual_rb.selected():
                if not valid_hostname(ns1_entry.value(), False) or \
                   not valid_hostname(ns2_entry.value(), True) or \
                   not valid_hostname(ns3_entry.value(), True):
                    done = False
                    ButtonChoiceWindow(screen,
                                       "Name Service Configuration",
                                       "Please check that you have entered at least one nameserver, and that the nameservers you specified are valid.",
                                       ["Back"])

    if buttons.buttonPressed(result) in [None, "ok"]:
        return 1
    else:
        return -1

def determine_basic_network_config(answers):
    # XXX nasty way of telling if we already asked:
    reuse_available = answers.has_key('source-media') and answers['source-media'] in ['url', 'nfs']
    direction, config = tui.network.get_network_config(screen, reuse_available)
    if direction == 1:
        if config == None:
            (dhcp, manual) = answers['runtime-iface-configuration']
            answers['iface-configuration'] = (dhcp, manual.copy())
        else:
            answers['iface-configuration'] = config
    return direction

def get_timezone_region(answers):
    global screen

    entries = generalui.getTimeZoneRegions()

    # default value?
    default = None
    if answers.has_key('timezone-region'):
        default = answers['timezone-region']

    (button, entry) = ListboxChoiceWindow(
        screen,
        "Select Time Zone",
        "Please select the geographical area that the managed host is in.",
        entries, ['Ok', 'Back'], height = 8, scroll = 1,
        default = default)

    if button in ["ok", None]:
        answers['timezone-region'] = entries[entry]
        return 1
    
    if button == "back": return -1

def get_timezone_city(answers):
    global screen

    entries = generalui.getTimeZoneCities(answers['timezone-region'])

    # default value?
    default = None
    if answers.has_key('timezone-city'):
        default = answers['timezone-city'].replace(' ', '_')

    (button, entry) = ListboxChoiceWindow(
        screen,
        "Select Time Zone",
        "Please select the localised area that the managed host is in (press a letter to jump to that place in the list).",
        map(lambda x: x.replace('_', ' '), entries),
        ['Ok', 'Back'], height = 8, scroll = 1, default = default)

    if button == "ok" or button == None:
        answers['timezone-city'] = entries[entry]
        answers['timezone'] = "%s/%s" % (answers['timezone-region'], answers['timezone-city'])
        return 1
    
    if button == "back": return -1

def get_time_configuration_method(answers):
    global screen

    ENTRY_NTP = "Using NTP", "ntp"
    ENTRY_MANUAL = "Manual time entry", "manual"
    entries = [ ENTRY_NTP, ENTRY_MANUAL ]

    # default value?
    default = None
    if answers.has_key("time-config-method"):
        default = selectDefault(answers['time-config-method'], entries)

    (button, entry) = ListboxChoiceWindow(
        screen,
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
    global screen

    if answers['time-config-method'] != 'ntp':
        return uicontroller.SKIP_SCREEN

    def dhcp_change():
        for x in [ ntp1_field, ntp2_field, ntp3_field ]:
            x.setFlags(FLAG_DISABLED, not dhcp_cb.value())

    gf = GridFormHelp(screen, 'NTP Configuration', None, 1, 4)
    text = TextboxReflowed(60, "Please specify details of the NTP servers you wish to use (e.g. pool.ntp.org)?")
    buttons = ButtonBar(screen, [("Ok", "ok"), ("Back", "back")])

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
                ButtonChoiceWindow(screen,
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
    global screen

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
        gf = GridFormHelp(screen, "Set local time", "", 1, 4)
        
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
            buttons = ButtonBar(screen, [("Ok", "ok"), ("Back", "back")])
        else:
            buttons = ButtonBar(screen, [("Ok", "ok")])
        gf.add(buttons, 0, 2)
        
        result = gf.runOnce()

        if buttons.buttonPressed(result) == "back":
            return -1

        # first, check they entered something valied:
        try:
            dt = datetime.datetime(int(year.value()),
                                   int(month.value()),
                                   int(day.value()),
                                   int(hour.value()),
                                   int(minute.value()))
        except ValueError, e:
            # the date was invalid - tell them why:
            done = False
            ButtonChoiceWindow(screen, "Date error",
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

def installation_complete(answers):
    global screen

    ButtonChoiceWindow(screen,
                       "Installation Complete",
                       """The %s installation has completed.

Please remove any local media from the drive, and press enter to reboot.""" % PRODUCT_BRAND,
                       ['Ok'])

    return 1
                      
def error_dialog(message):
    global screen
    
    if screen:
        ButtonChoiceWindow(screen, "Error occurred",
                           message,
                           ['Reboot'], width=50)
    else:
        xelogging.log("Error dialog requested, but UI not initialised yet.")

def request_media(medianame):
    global screen
    
    button = ButtonChoiceWindow(screen, "Media Not Found",
                                "Please insert the media labelled '%s' into your drive.  If the media is already present, then the installer was unable to locate it - please refer to your user guide, or a Technical Support Representative, for more information" % (medianame, COMPANY_NAME_SHORT),
                                ['Retry', 'Cancel'], width=50)

    return button != "cancel"

def get_network_config(show_reuse_existing = False,
                       runtime_config = False):
    return tui.network.get_network_config(
        screen, show_reuse_existing, runtime_config)

###
# Getting more media:

def more_media_sequence(installed_repo_ids):
    """ Displays the sequence of screens required to load additional
    media to install from.  installed_repo_ids is a list of repository
    IDs of repositories we already installed from, to help avoid
    issues where multiple CD drives are present."""
    def get_more_media(_):
        done = False
        while not done:
            more = OKDialog("New Media", "Please insert your extra disc now", True)
            if more == "cancel":
                # they hit cancel:
                rv = -1;
                done = True
            else:
                # they hit OK - check there is a disc
                repos = repository.repositoriesFromDefinition('local', '')
                if len(repos) == 0:
                    ButtonChoiceWindow(
                        screen, "Error",
                        "No installation files were found - please check your disc and try again.",
                        ['Back'])
                else:
                    # found repositories - can leave this screen
                    rv = 1
                    done = True
        return rv

    def confirm_more_media(_):
        repos = repository.repositoriesFromDefinition('local', '')
        assert len(repos) > 0

        for r in repos:
            if r.identifier() in installed_repo_ids:
                media_contents.append(" * %s (alredy installed)" % r.name())
            else:
                media_contents.append(" * %s" % r.name())
        text = "The media you have inserted contains:\n\n" + "\n".join(media_contents)

        done = False
        while not done:
            ans = ButtonChoiceWindow(screen, "New Media", text, ['Use media', 'Verify media', 'Back'], width=50)
            
            if ans == 'verify media':
                if interactive_source_verification('local', ''):
                    OKDialog("Media Check", "No problems were found with your media.")
            elif ans == 'back':
                rc = -1
                done = True
            else:
                rc = 1
                done = True

        return rc

    seq = [ get_more_media, confirm_more_media ]
    direction = uicontroller.runUISequence(seq, {})
    return direction == 1

###
# Progress dialog:

def initProgressDialog(title, text, total):
    return snackutil.initProgressDialog(screen, title, text, total)

def displayProgressDialog(current, pd, updated_text = None):
    return snackutil.displayProgressDialog(screen, current, pd, updated_text)

def clearModelessDialog():
    return snackutil.clearModelessDialog(screen)

def showMessageDialog(title, text):
    return snackutil.showMessageDialog(screen, title, text)

###
# Simple 'OK' dialog for external use:

def OKDialog(title, text, hasCancel = False):
    return snackutil.OKDialog(screen, title, text, hasCancel)
