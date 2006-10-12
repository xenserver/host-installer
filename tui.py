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

### TODO: Validation of IP addresses

from snack import *
import snackutil

import sys
import string
import datetime

import generalui
import uicontroller
import constants
import diskutil
import netutil
import packaging
import xelogging
from version import *
import hardware

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

# welcome screen:
def welcome_screen(answers):
    global screen

    warning = ""
    if not hardware.VTSupportEnabled ():
        warning = """

NOTE: Hardware virtualization assist support is not available on this system.  Either it is not present, or is disabled in the system's BIOS.  This capability is required to start Windows virtual machines."""

    button = ButtonChoiceWindow(screen,
                                "Welcome to %s Setup" % PRODUCT_BRAND,
                                """This setup tool will install %s on your server.

This install will overwrite data on any hard drives you select to use during the install process. Please make sure you have backed up any data on this system before proceeding with the product install. %s""" % (PRODUCT_BRAND, warning),
                                ['Ok', 'Cancel Installation'], width=60)

    # advance to next screen:
    if button == 'ok':
        return 1
    else:
        return uicontroller.EXIT


def no_disks():
    global screen

    ButtonChoiceWindow(screen,
                       "Fatal error",
                       """No disks have been found on your system.

Please refer to the user guide or %s technical support for more information on this problem.""" % COMPANY_NAME_SHORT,
                       ['Exit'], width=60)

    # advance to next screen:
    return 1

def no_netifs():
    global screen

    ButtonChoiceWindow(screen,
                       "Fatal error",
                       """No network interfaces have been found on your system.

Please refer to the user guide or %s technical support for more information on this problem.""" % COMPANY_NAME_SHORT,
                       ['Exit'], width=60)

    # advance to next screen:
    return 1

def not_enough_space_screen(answers):
    global screen

    ButtonChoiceWindow(screen,
                       "Insufficient disk space",
                       """Unfortunately, you do not have a disk with enough space to install %s.  You need at least one %sGB or greater disk in the system for the installation to proceed.""" % (PRODUCT_BRAND, str(constants.min_primary_disk_size)),
                       ['Exit'], width=60)

    # leave the installer:
    return 1

def eula_screen(answers):
    global screen

    if not os.path.exists(constants.EULA_PATH):
        return uicontroller.SKIP_SCREEN

    eula_file = open(constants.EULA_PATH, 'r')
    eula = string.join(eula_file.readlines())
    eula_file.close()

    button = snackutil.ButtonChoiceWindowEx(
        screen,
        "End User License Agreement",
        eula,
        ['Accept EULA', 'Back'], width=60, default=1)

    # advance to next screen:
    if button == 'back':
        return -1
    else:
        return 1


def get_keyboard_type(answers):
    global screen

    entries = generalui.getKeyboardTypes()

    (button, entry) = ListboxChoiceWindow(screen,
                                          "Select Keymap",
                                          "Please choose which type of keyboard you have.  (Note that you can tell by looking at the characters in the top-left corner of the keyboard - they should match one of the items listed below.)",
                                          entries,
                                          ['Ok', 'Back'])

    if button == "ok" or button == None:
        answers['keyboard-type'] = entries[entry]
        return 1
    
    if button == "back": return -1

def get_keymap(answers):
    global screen

    entries = generalui.getKeymaps(answers['keyboard-type'])

    (button, entry) = ListboxChoiceWindow(screen,
                                          "Select Keymap",
                                          "Please select the keymap you would like to use (note that, in this version of the installer, this will only take effect when you reboot into %s)." % PRODUCT_BRAND,
                                          entries,
                                          ['Ok', 'Back'], height = 8, scroll = 1)

    if button == "ok" or button == None:
        answers['keymap'] = entries[entry]
        return 1
    
    if button == "back": return -1

def confirm_wipe_existing(answers):
    global screen

    if not diskutil.detectExistingInstallation():
        return uicontroller.SKIP_SCREEN

    button = ButtonChoiceWindow(screen,
                       "Existing installations detected",
                       """There appear to be existing or incomplete installations of %s already present on your system.

If you continue with this installation, you will lose any data associated with old installations of %s""" % (PRODUCT_BRAND, PRODUCT_BRAND),
                       ['Continue', 'Cancel Installation'], width=60)

    if button == 'continue':
        return 1
    elif button == 'cancel installation':
        return uicontroller.EXIT

def confirm_erase_volume_groups(answers):
    global screen

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

    if button == 'continue':
        return 1
    elif button == 'cancel installation':
        return uicontroller.EXIT

def select_installation_source(answers):
    global screen

    done = False
    while not done:
        entries = [ ('Local media (CD-ROM)', 'local'),
                    ('HTTP or FTP', 'url'),
                    ('NFS', 'nfs') ]
        (button, entry) = ListboxChoiceWindow(screen,
                                              "Select Installation Source",
                                              "Please select the type of source you would like to use for this installation",
                                              entries,
                                              ['Ok', 'Back'])

        # if it's local media, verify that stuff exists:
        if entry == 'local' and button == 'ok':
            im = None
            try:
                im = packaging.LocalInstallMethod()
            except packaging.MediaNotFound, m:
                ButtonChoiceWindow(screen, "Problem with Media",
                                   str(m),  ['Back'])
            else:
                problems = im.quickSourceVerification()
                if problems == []:
                    done = True
                else:
                    ButtonChoiceWindow(screen, "Problem with Media",
                                       "The following required packages were not found on your media: \n\n%s" % \
                                       generalui.makeHumanList(problems),
                                       ['Back'])
                    
                im.finished(eject = False)
        else:
            # either they pressed 'back', or pressed 'ok' with
            # a non-local source:
            done = True

        answers['source-media'] = entry
        if entry == 'local':
            answers['source-address'] = "Installation disc"

    if button == "ok" or button == None: return 1
    if button == "back": return -1

def get_http_source(answers):
    if answers['source-media'] == 'url':
        done = False
        while not done:
            (button, result) = EntryWindow(screen,
                                           "Specify Repository",
                                           "Please enter URL for your HTTP or FTP repository",
                                           ['URL'], entryWidth = 50,
                                           buttons = ['Ok', 'Back'])
            
            answers['source-address'] = result[0]

            # 'not button' covers the user pressing F12
            if button == "ok" or not button:
                im = None
                try:
                    im = packaging.HTTPInstallMethod(result[0])
                except packaging.MediaNotFound, m:
                    ButtonChoiceWindow(screen, "Problem with repository",
                                       str(m),  ['Back'])
                else:
                    problems = im.quickSourceVerification()
                    if problems == []:
                        done = True
                    else:
                        ButtonChoiceWindow(screen, "Problem with repository",
                                           "The following required packages were not found in your repository: \n\n%s" % \
                                           generalui.makeHumanList(problems),
                                           ['Back'])
                if im:
                    im.finished()
            elif button == "back":
                done = True
            
        if button == 'ok': return 1
        if button == 'back': return -1
    else:
        # we don't need this screen
        return uicontroller.SKIP_SCREEN

def get_nfs_source(answers):
    if answers['source-media'] == 'nfs':
        done = False
        while not done:
            (button, result) = EntryWindow(screen,
                                           "Specify NFS Source",
                                           "Please enter the server and path of your NFS share (e.g. myserver:/my/directory)",
                                           ['NFS Path'], entryWidth = 50,
                                           buttons = ['Ok', 'Back'])
        
            answers['source-address'] = result[0]
            if button == 'ok' or not button:
                im = None
                try:
                    im = packaging.NFSInstallMethod(result[0])
                except packaging.MediaNotFound, m:
                    ButtonChoiceWindow(screen, "Problem with repository",
                                       str(m),  ['Back'])
                except packaging.BadSourceAddress:
                    ButtonChoiceWindow(screen, "Problem with repository",
                                       "The installer was unable to access the address you specified.  Please check that it is well-formed, and that you have read permission for the path you specified.",  ['Back'])
                else:
                    problems = im.quickSourceVerification()
                    if problems == []:
                        done = True
                    else:
                        ButtonChoiceWindow(screen, "Problem with repository",
                                           "The following required packages were not found in your repository: \n\n%s" % \
                                           generalui.makeHumanList(problems),
                                           ['Back'])
                
                    im.finished()
            elif button == 'back':
                done = True
                
        if button == 'ok': return 1
        if button == 'back': return -1
    else:
        # we don't need this screen
        return uicontroller.SKIP_SCREEN

# verify the installation source?
def verify_source(answers):
    done = False
    while not done:
        (button, entry) = ListboxChoiceWindow(screen,
                                              "Verify Installation Source",
                                              "Would you like to verify the integrity of your installation repository/media?  (This may take a while to complete and could cause significant network traffic if performing a network installation.)",
                                              ['Skip verification', 'Verify installation source'],
                                              ['Ok', 'Back'])
        if entry == 0:
            done = True
        elif button != 'back' and entry == 1:
            # we need to do the verification:
            try:
                if answers['source-media'] == 'url':
                    installmethod = packaging.HTTPInstallMethod(answers['source-address'])
                elif answers['source-media'] == 'local':
                    installmethod = packaging.LocalInstallMethod()
                elif answers['source-media'] == 'nfs':
                    installmethod = packaging.NFSInstallMethod(answers['source-address'])
            except Exception, e:
                ButtonChoiceWindow(screen, "Problem with repository",
                                   str(e),  ['Back'])
            else:
                showMessageDialog("Verify Installation Source", "Package verification is in progress, please wait...")
                problems = installmethod.md5SourceVerification()
                if len(problems) == 0:
                    done = True
                else:
                    ButtonChoiceWindow(screen, "Problem with repository",
                                       "The following required packages did not pass verification: \n\n%s" % \
                                       generalui.makeHumanList(problems),
                                       ['Back'])
                clearModelessDialog()
                installmethod.finished(eject = False)

    if button == 'back':
        return -1
    else:
        return 1
            

# select drive to use as the Dom0 disk:
def select_primary_disk(answers):
    global screen
    entries = []
    
    diskEntries = diskutil.getQualifiedDiskList()
    for de in diskEntries:
        (vendor, model, size) = diskutil.getExtendedDiskInfo(de)
        if diskutil.blockSizeToGBSize(size) >= constants.min_primary_disk_size:
            stringEntry = "%s - %s [%s %s]" % (de, diskutil.getHumanDiskSize(size), vendor, model)
            e = (stringEntry, de)
            entries.append(e)

    (button, entry) = ListboxChoiceWindow(screen,
                        "Select Primary Disk",
                        """Please select the disk you would like to install %s on (disks with insufficient space are not shown).

You may need to change your system settings to boot from this disk.""" % (PRODUCT_BRAND),
                        entries,
                        ['Ok', 'Back'], width = 55)

    # entry contains the 'de' part of the tuple passed in
    answers['primary-disk'] = entry

    if button == "ok" or button == None: return 1
    if button == "back": return -1

def select_guest_disks(answers):
    global screen

    # set up defaults:
    if answers.has_key('guest-disks'):
        currently_selected = answers['guest-disks']
    else:
        currently_selected = answers['primary-disk']

    # Make a list of entries: (text, item)
    entries = []
    for de in diskutil.getQualifiedDiskList():
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

If you proceed, please refer to the user guide for details on provisioning storage after installation.""",
            ['Continue', 'Back']
            )
        if button == 'back':
            return 0

    if buttons.buttonPressed(result) == 'ok': return 1
    if buttons.buttonPressed(result) == 'back': return -1

# confirm they want to blow stuff away:
def confirm_installation_multiple_disks(answers):
    global screen

    disks = answers['guest-disks']
    if answers['primary-disk'] not in disks:
        disks.append(answers['primary-disk'])
    disks.sort()
    disks_used = generalui.makeHumanList(disks)

    ok = 'Install %s' % PRODUCT_BRAND
    button = snackutil.ButtonChoiceWindowEx(
        screen,
        "Confirm Installation",
        """We have collected all the information required to install %s.

If you proceed, ALL DATA WILL BE DESTROYED on the disks selected for use by %s (you selected %s)""" % (PRODUCT_BRAND, PRODUCT_BRAND, disks_used),
        [ok, 'Back'], default = 1)
        

    if button == string.lower(ok): return 1
    if button == "back": return -1

def confirm_installation_one_disk(answers):
    global screen

    ok = 'Install %s' % PRODUCT_BRAND
    button = snackutil.ButtonChoiceWindowEx(
        screen,
        "Confirm Installation",
        """Since your server only has a single disk, this will be used to install %s.

Please confirm you wish to proceed; ALL DATA ON THIS DISK WILL BE DESTROYED.""" % PRODUCT_BRAND,
        [ok, 'Back'], default = 1)

    if button == string.lower(ok): return 1
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
    assert button == 'ok'
    answers['root-password'] = pw
    return 1

def determine_basic_network_config(answers):
    global screen

    entries = [ 'Configure all interfaces using DHCP',
                'Specify a different network configuration' ]

    (button, entry) = ListboxChoiceWindow(screen,
                                          "Network Configuration",
                                          "How would you like networking to be configured on this host?",
                                          entries,
                                          ['Ok', 'Back'])

    if button == "ok" or button == None:
        # proceed to get_autoconfig_ifaces if manual configuration was selected:
        if entry == 1:
            seq = [ get_autoconfig_ifaces ]
            rv = uicontroller.runUISequence(seq, answers)
            if rv == -1: return 0
            if rv == 1: return 1
        else:
            answers['iface-configuration'] = (True, None)
            return 1
    
    if button == "back": return -1

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

    if buttons.buttonPressed(result) == "ok":
        return 1
    else:
        return -1

def get_autoconfig_ifaces(answers):
    global screen

    seq = []
    for x in netutil.getNetifList():
        seq.append((get_iface_configuration, (x,)))

    # when this was written this branch would never be taken
    # since we require at least one NIC at setup time:
    if len(seq) == 0:
        answers['iface-configuration']  = (True, None)
        return 1

    subdict = {}
    rv = uicontroller.runUISequence(seq, subdict)
    answers['iface-configuration'] = (False, subdict)
    
    if rv == -1: return 0
    if rv == 1: return 1
    
def get_iface_configuration(answers, iface):
    global screen

    def identify_interface(iface):
        global screen
        ButtonChoiceWindow(screen,
                           "Identify Interface",
                           """Name: %s

MAC Address; %s

PCI details; %s""" % (iface, netutil.getHWAddr(iface), netutil.getPCIInfo(iface)),
                           ['Ok'], width=60)
    def enabled_change():
        for x in [ ip_field, gateway_field, subnet_field ]:
            x.setFlags(FLAG_DISABLED,
                           (enabled_cb.value() and not dhcp_cb.value()))
        dhcp_cb.setFlags(FLAG_DISABLED, enabled_cb.value())
    def dhcp_change():
        for x in [ ip_field, gateway_field, subnet_field ]:
            x.setFlags(FLAG_DISABLED,
                           (enabled_cb.value() and not dhcp_cb.value()))

    gf = GridFormHelp(screen, 'Network Configuration', None, 1, 5)
    text = TextboxReflowed(45, "Configuration for %s (%s)" % (iface, netutil.getHWAddr(iface)))
    buttons = ButtonBar(screen, [("Ok", "ok"), ("Back", "back"), ("Identify", "identify")])

    # note spaces exist to line checkboxes up:
    enabled_cb = Checkbox("Enable interface", 1)
    dhcp_cb = Checkbox("Configure with DHCP", 1)
    enabled_cb.setCallback(enabled_change, ())
    dhcp_cb.setCallback(dhcp_change, ())

    ip_field = Entry(16)
    ip_field.setFlags(FLAG_DISABLED, False)
    subnet_field = Entry(16)
    subnet_field.setFlags(FLAG_DISABLED, False)
    gateway_field = Entry(16)
    gateway_field.setFlags(FLAG_DISABLED, False)

    ip_text = Textbox(15, 1, "IP Address:")
    subnet_text = Textbox(15, 1, "Subnet mask:")
    gateway_text = Textbox(15, 1, "Gateway:")

    entry_grid = Grid(2, 3)
    entry_grid.setField(ip_text, 0, 0)
    entry_grid.setField(ip_field, 1, 0)
    entry_grid.setField(subnet_text, 0, 1)
    entry_grid.setField(subnet_field, 1, 1)
    entry_grid.setField(gateway_text, 0, 2)
    entry_grid.setField(gateway_field, 1, 2)

    gf.add(text, 0, 0, padding = (0,0,0,1))
    gf.add(enabled_cb, 0, 1, anchorLeft = True)
    gf.add(dhcp_cb, 0, 2, anchorLeft = True)
    gf.add(entry_grid, 0, 3, padding = (0,0,0,1))
    gf.add(buttons, 0, 4)

    while True:
        result = gf.run()
        # do we display a popup then continue, or leave the loop?
        if not buttons.buttonPressed(result) == 'ok' and \
           not buttons.buttonPressed(result) == 'back':
            assert buttons.buttonPressed(result) == 'identify'
            identify_interface(iface)
        else:
            # leave the loop - 'ok' or 'back' was pressed:
            screen.popWindow()
            break

    if buttons.buttonPressed(result) == 'ok':
        answers[iface] = {'use-dhcp': dhcp_cb.value(),
                          'enabled': enabled_cb.value(),
                          'ip': ip_field.value(),
                          'subnet-mask': subnet_field.value(),
                          'gateway': gateway_field.value() }
        return 1
    elif buttons.buttonPressed(result) == 'back':
        return -1

def get_timezone_region(answers):
    global screen

    entries = generalui.getTimeZoneRegions()

    (button, entry) = ListboxChoiceWindow(screen,
                                          "Select Time Zone",
                                          "Please select the geographical area that the managed host is in.",
                                          entries,
                                          ['Ok', 'Back'], height = 8, scroll = 1)

    if button == "ok" or button == None:
        answers['timezone-region'] = entries[entry]
        return 1
    
    if button == "back": return -1

def get_timezone_city(answers):
    global screen

    entries = generalui.getTimeZoneCities(answers['timezone-region'])

    (button, entry) = ListboxChoiceWindow(screen,
                                          "Select Time Zone",
                                          "Please select the localised area that the managed host is in (press a letter to jump to that place in the list).",
                                          map(lambda x: x.replace('_', ' '), entries),
                                          ['Ok', 'Back'], height = 8, scroll = 1)

    if button == "ok" or button == None:
        answers['timezone-city'] = entries[entry]
        answers['timezone'] = "%s/%s" % (answers['timezone-region'], answers['timezone-city'])
        return 1
    
    if button == "back": return -1

def get_time_configuration_method(answers):
    global screen

    entries = [ "Using NTP",
                "Manual time entry" ]

    (button, entry) = ListboxChoiceWindow(screen,
                                          "System Time",
                                          "How should the local time be determined?\n\n(Note that if you choose to enter it manually, you will need to respond to a prompt at the end of the installation.)",
                                          entries,
                                          ['Ok', 'Back'])

    if button == "ok" or button == None:
        if entry == 0:
            answers['time-config-method'] = 'ntp'
        elif entry == 1:
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

    if buttons.buttonPressed(result) == 'ok':
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
def set_time(answers, now):
    global screen

    done = False

    # set these outside the loop so we don't overwrite them in the
    # case that the user enters a bad value.
    day = Entry(3, "%02d" % now.day)
    month = Entry(3, "%02d" % now.month)
    year = Entry(5, "%04d" % now.year)
    hour = Entry(3, "%02d" % now.hour)
    minute = Entry(3, "%02d" % now.minute)

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
        
        buttons = ButtonBar(screen, [("Ok", "ok"), ("Back", "back")])
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
                                "Please insert the media labelled '%s' into your drive.  If the media is already present, then the installer was unable to locate it - please refer to your user guide, or %s technical support, for more information" % (medianame, COMPANY_NAME_SHORT),
                                ['Retry', 'Cancel'], width=50)

    return button != "cancel"

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
