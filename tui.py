#!/usr/bin/python
###
# XEN CLEAN INSTALLER
# Text user interface functions
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

### TODO: Validation of IP addresses

from snack import *
import generalui
import uicontroller
import sys
import constants
from version import *

import datetime

screen = None

# functions to start and end the GUI - these create and destroy a snack screen as
# appropriate.
def init_ui(results, is_subui):
    global screen
    
    screen = SnackScreen()
    screen.drawRootText(0, 0, "Welcome to %s Installer - Version %s" % (PRODUCT_BRAND, PRODUCT_VERSION))
    screen.drawRootText(0, 1, "Copyright XenSource, Inc. 2006")

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

    ButtonChoiceWindow(screen,
                       "Welcome to %s Setup" % PRODUCT_BRAND,
                       """This CD will install %s on your server.

This install will overwrite data on any hard drives you select to use during the install process. Please make sure you have backed up any data on this system before proceeding with the product install.""" % PRODUCT_BRAND,
                       ['Ok'], width=60)

    # advance to next screen:
    return 1

def upgrade_screen(answers):
    global screen

    button = ButtonChoiceWindow(screen,
                       "Welcome to %s Setup" % PRODUCT_BRAND,
                       """This CD will upgrade %s on your server to version %s.""" % 
                           (PRODUCT_BRAND, PRODUCT_VERSION),
                       ['Ok', 'Exit'], width=60)

    # advance to next screen:
    if button == "exit":
        sys.exit(0)
    else:
        return 1


# select drive to use as the Dom0 disk:
def select_primary_disk(answers):
    global screen
    entries = []
    
    diskEntries = generalui.getDiskList()
    for de in diskEntries:
        (vendor, model, size) = generalui.getExtendedDiskInfo(de)
        stringEntry = "%s - %s [%s %s]" % (de, generalui.getHumanDiskSize(size), vendor, model)
        e = (stringEntry, de)
        entries.append(e)

    (button, entry) = ListboxChoiceWindow(screen,
                        "Select Primary Disk",
                        """Please select the disk you would like to use as the primary %s disk.

Xen will be installed onto this disk, requiring 120MB, and the remaining space used for guest virtual machines.""" % PRODUCT_BRAND,
                        entries,
                        ['Ok', 'Back'])

    # entry contains the 'de' part of the tuple passed in
    answers['primary-disk'] = entry
    print ("setting primary disk to %s" % entry)

    if button == "ok" or button == None: return 1
    if button == "back": return -1

def select_guest_disks(answers):
    global screen
    
    entries = []

    diskEntries = generalui.getDiskList()
    diskEntries.remove(answers['primary-disk'])
    for de in diskEntries:
        (vendor, model, size) = generalui.getExtendedDiskInfo(de)
        entry = "%s - %s [%s %s]" % (de, generalui.getHumanDiskSize(size), vendor, model)
        entries.append(entry)
        
    text = TextboxReflowed(50, "Please select any additional disks you would like to use for guest storage")
    buttons = ButtonBar(screen, [('Ok', 'ok'), ('Back', 'back')])
    cbt = CheckboxTree(4, 1)
    for x in entries:
        cbt.append(x)
    
    gf = GridFormHelp(screen, 'Select Additional Disks', None, 1, 3)
    gf.add(text, 0, 0, padding = (0, 0, 0, 1))
    gf.add(cbt, 0, 1, padding = (0, 0, 0, 1))
    gf.add(buttons, 0, 2)
    
    result = gf.runOnce()
    
    answers['guest-disks'] = []
  
    for sel in cbt.getSelection():
        answers['guest-disks'].append(diskEntries[entries.index(sel)])

    if buttons.buttonPressed(result) == 'ok': return 1
    if buttons.buttonPressed(result) == 'back': return -1

# confirm they want to blow stuff away:
def confirm_installation_multiple_disks(answers):
    global screen

    disks = [ answers['primary-disk'] ] + answers['guest-disks']
    disks_used = generalui.makeHumanList(disks)

    button = ButtonChoiceWindow(screen,
                                "Confirm Installation",
                                """We have collected all the information required to install %s.

If you proceed, ALL DATA WILL BE DESTROYED on the disks selected for use by %s (you selected %s)""" % (PRODUCT_BRAND, PRODUCT_BRAND, disks_used),
                                ['Ok', 'Back'])

    if button == "ok": return 1
    if button == "back": return -1

def confirm_installation_one_disk(answers):
    global screen

    button = ButtonChoiceWindow(screen,
                                "Confirm Installation",
                                """Since your server only has a single disk, this will be used to install %s.

Please confirm you wish to proceed; all data on this disk will be destroyed (vendor service partitions will be left intact)""" % PRODUCT_BRAND,
                                ['Ok', 'Back'])

    if button == "ok": return 1
    if button == "back": return -1

def get_root_password(answers):
    global screen
    done = False
        
    while not done:
        (button, result) = PasswordEntryWindow(screen,
                                     "Set Password",
                                     "Please specify the root password for this installation",
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

    def auto_nameserver_change((cb, entries)):
        for entry in entries:
            entry.setFlags(FLAG_DISABLED, not cb.value())

    def auto_hostname_change((cb, entry)):
        entry.setFlags(FLAG_DISABLED, not cb.value())

    ask_autohostname = not answers['iface-configuration'][0]

    gf = GridFormHelp(screen, 'Name Service Configuration', None, 1, 8)
        
    text = TextboxReflowed(50, "How should the name service be configured?")
    buttons = ButtonBar(screen, [("Ok", "ok"), ("Back", "back")])

    if ask_autohostname:
        auto_hostname = Checkbox("Set a hostname manually?", 1)
        hostname_text = Textbox(15, 1, "Hostname:")
        hostname = Entry(30)
        hostname.setFlags(FLAG_DISABLED, 0)
        hostname_grid = Grid(2, 1)
        hostname_grid.setField(hostname_text, 0, 0)
        hostname_grid.setField(hostname, 1, 0)
        auto_hostname.setCallback(auto_hostname_change, (auto_hostname, hostname))

    ns1_text = Textbox(15, 1, "Nameserver 1:")
    ns1_entry = Entry(30)
    ns1_grid = Grid(2, 1)
    ns1_grid.setField(ns1_text, 0, 0)
    ns1_grid.setField(ns1_entry, 1, 0)
    
    ns2_text = Textbox(15, 1, "Nameserver 2:")
    ns2_entry = Entry(30)
    ns2_grid = Grid(2, 1)
    ns2_grid.setField(ns2_text, 0, 0)
    ns2_grid.setField(ns2_entry, 1, 0)

    ns3_text = Textbox(15, 1, "Nameserver 3:")
    ns3_entry = Entry(30)
    ns3_grid = Grid(2, 1)
    ns3_grid.setField(ns3_text, 0, 0)
    ns3_grid.setField(ns3_entry, 1, 0)

    for entry in [ns1_entry, ns2_entry, ns3_entry]:
        entry.setFlags(FLAG_DISABLED, 0)

    auto_nameservers = Checkbox("Get DNS server list from DHCP?", 1)
    auto_nameservers.setCallback(auto_nameserver_change, (auto_nameservers, [ns1_entry, ns2_entry, ns3_entry]))

    gf.add(text, 0, 0, padding = (0,0,0,1))

    if ask_autohostname:
        gf.add(auto_hostname, 0, 1)
        gf.add(hostname_grid, 0, 2, padding = (0,0,0,1))
        
    gf.add(auto_nameservers, 0, 3)
    gf.add(ns1_grid, 0, 4)
    gf.add(ns2_grid, 0, 5)
    gf.add(ns3_grid, 0, 6, padding = (0,0,0,1))
    
    gf.add(buttons, 0, 7)

    result = gf.runOnce()

    if buttons.buttonPressed(result) == "ok":
        if ask_autohostname:
            # manual hostname?
            if auto_hostname.value():
                answers['manual-hostname'] = (False, None)
            else:
                answers['manual-hostname'] = (True, hostname.value())
        else:
            answers['manual-hostname'] = (False, None)

        # manual nameservers?
        if auto_nameservers.value():
            answers['manual-nameservers'] = (False, None)
        else:
            answers['manual-nameservers'] = (True, [ns1_entry.value(),
                                                    ns2_entry.value(),
                                                    ns3_entry.value()])

        return 1
    else:
        return -1

def get_autoconfig_ifaces(answers):
    global screen

    entries = generalui.getNetifList()

    text = TextboxReflowed(50, "Which network interfaces need to be configured manually?")
    buttons = ButtonBar(screen, [('Ok', 'ok'), ('Back', 'back')])
    cbt = CheckboxTree(4, 1)
    for x in entries:
        cbt.append(x)
    
    gf = GridFormHelp(screen, 'Network Configuration', None, 1, 3)
    gf.add(text, 0, 0, padding = (0, 0, 0, 1))
    gf.add(cbt, 0, 1, padding = (0, 0, 0, 1))
    gf.add(buttons, 0, 2)
    
    result = gf.runOnce()

    if buttons.buttonPressed(result) == 'back': return -1

    seq = []
    manually_configured = cbt.getSelection()

    for x in manually_configured:
        seq.append((get_iface_configuration, { 'iface': x }))

    if len(seq) == 0:
        answers['iface-configuration']  = (True, None)
        if buttons.buttonPressed(result) == 'back': return -1
        if buttons.buttonPressed(result) == 'ok': return 1

    subdict = {}

    rv = uicontroller.runUISequence(seq, subdict)

    for x in entries:
        if x not in manually_configured:
            subdict[x] = {"use-dhcp": True}

    answers['iface-configuration'] = (False, subdict)
    
    if rv == -1: return 0
    if rv == 1: return 1
    

def get_iface_configuration(answers, args):
    global screen

    iface = args['iface']

    (button, (ip, snm, gw)) = EntryWindow(screen,
                                          "Configuration for %s" % iface,
                                          "Please give configuration details for the interface %s" % iface,
                                          ['IP Address:', 'Subnet mask:', 'Gateway:'],
                                          buttons = ['Ok', 'Back'])

    answers[iface] = {'use-dhcp': False,
                      'ip': ip,
                      'subnet-mask': snm,
                      'gateway': gw }
    
    if button == 'ok': return 1
    if button == 'back': return -1

def get_timezone(answers):
    global screen

    entries = generalui.getTimeZones()

    (button, entry) = ListboxChoiceWindow(screen,
                                          "Select Time Zone",
                                          "Which time zone is the managed host in?",
                                          entries,
                                          ['Ok', 'Back'], height = 8, scroll = 1)

    if button == "ok" or button == None:
        answers['timezone'] = entries[entry]
        return 1
    
    if button == "back": return -1

def set_time(answers):
    global screen

    done = False

    # translate the current time to the selected timezone:
    now = generalui.translateDateTime(datetime.datetime.now(),
                                      answers['timezone'])

    # set these outside the loop so we don't overwrite them in the
    # case that the user enters a bad value.
    day = Entry(3, str(now.day))
    month = Entry(3, str(now.month))
    year = Entry(5, str(now.year))
    hour = Entry(3, str(now.hour))
    minute = Entry(3, str(now.minute))

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
                       """The %s installation has completed.  Please press enter to reboot the machine.
                       
Please manually eject the install media upon reboot.""" % PRODUCT_BRAND,
                       ['Ok'])

    return 1
                      
def upgrade_complete(answers):
    global screen

    ButtonChoiceWindow(screen,
                       "Upgrade Complete",
                       """The %s upgrade has completed.  Please press enter to reboot the machine.
                       
Please manually eject the install media upon reboot.""" % PRODUCT_BRAND,
                       ['Ok'])

    return 1


###
# Helper functions
def PasswordEntryWindow(screen, title, text, prompts, allowCancel = 1, width = 40,
                        entryWidth = 20, buttons = [ 'Ok', 'Cancel' ], help = None):
    bb = ButtonBar(screen, buttons)
    t = TextboxReflowed(width, text)

    count = 0
    for n in prompts:
        count = count + 1

    sg = Grid(2, count)

    count = 0
    entryList = []
    for n in prompts:
        if (type(n) == types.TupleType):
            (n, e) = n
        else:
            e = Entry(entryWidth, password = 1)

        sg.setField(Label(n), 0, count, padding = (0, 0, 1, 0), anchorLeft = 1)
        sg.setField(e, 1, count, anchorLeft = 1)
        count = count + 1
        entryList.append(e)

    g = GridFormHelp(screen, title, help, 1, 3)

    g.add(t, 0, 0, padding = (0, 0, 0, 1)) 
    g.add(sg, 0, 1, padding = (0, 0, 0, 1))
    g.add(bb, 0, 2, growx = 1)

    result = g.runOnce()

    entryValues = []
    count = 0
    for n in prompts:
        entryValues.append(entryList[count].value())
        count = count + 1

    return (bb.buttonPressed(result), tuple(entryValues))

###
# Progress dialog:
def initProgressDialog(title, text, total):
    global screen
    
    form = GridFormHelp(screen, title, None, 1, 3)
    
    t = Textbox(60, 1, text)
    scale = Scale(60, total)
    form.add(t, 0, 0, padding = (0,0,0,1))
    form.add(scale, 0, 1, padding = (0,0,0,0))

    return (form, scale)

def displayProgressDialog(current, (form, scale)):
    global screen
    
    scale.set(current)

    form.draw()
    screen.refresh()

def displayInfoDialog(title, text):
    global screen

    form = GridFormHelp(screen, title, None, 1, 2)
    
    t = TextboxReflowed(60, text)
    form.add(t, 0, 0)
    form.draw()
    screen.refresh()

def clearModelessDialog():
    global screen
    
    screen.popWindow()
