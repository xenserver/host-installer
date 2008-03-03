# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# 'Init' text user interface
#
# written by Andrew Peace

from snack import *
from version import *

import tui
import init_constants
import generalui
import uicontroller
import tui.network
import repository
import snackutil

def get_keymap():
    entries = generalui.getKeymaps()

    (button, entry) = ListboxChoiceWindow(
        tui.screen,
        "Select Keymap",
        "Please select the keymap you would like to use:",
        entries,
        ['Ok'], height = 8, scroll = 1)

    return entry

def choose_operation(display_restore):
    entries = [ 
        (' * Install or upgrade %s' % BRAND_SERVER, init_constants.OPERATION_INSTALL),
        (' * Load a driver', init_constants.OPERATION_LOAD_DRIVER),
        (' * Convert an existing OS on this machine to a %s (P2V)' % BRAND_GUEST_SHORT, init_constants.OPERATION_P2V)
        ]

    if display_restore:
        entries.append( (' * Restore from backup', init_constants.OPERATION_RESTORE) )

    (button, entry) = ListboxChoiceWindow(tui.screen,
                                          "Welcome to %s" % PRODUCT_BRAND,
                                          """Please select an operation:""",
                                          entries,
                                          ['Ok', 'Exit and reboot'], width=70)

    if button == 'ok' or button == None:
        return entry
    else:
        return -1

def already_activated():
    while True:
        form = GridFormHelp(tui.screen, "Installation already started", None, 1, 1)
        tb = TextboxReflowed(50, """You have already activated the installation on a different console!
        
If this message is unexpected, please try restarting your machine, and ensure you only use one console (either serial, or tty).""")
        form.add(tb, 0, 0)
        form.run()

def ask_load_module(m):
    result = ButtonChoiceWindow(tui.screen,
                                "Interactive Module Loading",
                                "Load module %s?" % m,
                                ['Yes', 'No'])

    return result != 'no'

def driver_disk_sequence():
    answers = {}
    uic = uicontroller
    seq = [
        uic.Step(get_driver_source),
        uic.Step(tui.network.requireNetworking,
                 predicates = [lambda a: a['source-media'] != 'local']),
        uic.Step(get_driver_source_location),
        uic.Step(confirm_load_drivers),
        ]
    rc = uicontroller.runSequence(seq, answers)

    if rc == -1:
        return None
    else:
        return (answers['source-media'], answers['source-address'])

def get_driver_source(answers):
    entries = [
        ('Removable media', 'local'),
        ('HTTP or FTP', 'url'),
        ('NFS', 'nfs')
        ]
    result, entry = ListboxChoiceWindow(
        tui.screen,
        "Load driver",
        "Please select where you would like to load a driver from:",
        entries, ['Ok', 'Back'])

    answers['source-media'] = entry
    if entry == 'local':
        answers['source-address'] = ''

    if result in ['ok', None]: return 1
    if result == 'back': return -1

def get_driver_source_location(answers):
    if answers['source-media'] not in ['url', 'nfs']:
        return uicontroller.SKIP_SCREEN

    if answers['source-media'] == 'url':
        text = "Please enter the URL for your HTTP or FTP repository"
        label = "URL:"
    elif answers['source-media'] == 'nfs':
        text = "Please enter the server and path of your NFS share (e.g. myserver:/my/directory)"
        label = "NFS Path:"
        
    if answers.has_key('source-address'):
        default = answers['source-address']
    else:
        default = ""
    (button, result) = EntryWindow(
        tui.screen,
        "Specify Repository",
        text,
        [(label, default)], entryWidth = 50,
        buttons = ['Ok', 'Back'])
    
    answers['source-address'] = result[0]
            
    if button in [None, 'ok']: return 1
    if button == 'back': return -1

def confirm_load_drivers(answers):
    # find drivers:
    repos = repository.repositoriesFromDefinition(
        answers['source-media'], answers['source-address'])
    drivers = []

    for r in repos:
        for p in r:
            if p.type == "driver":
                drivers.append(p)

    driver_names = [" * %s" % d.name for d in drivers]
    if len(drivers) == 0:
        ButtonChoiceWindow(
            tui.screen, "No drivers found",
            """No drivers were found at the location specified.  Please check the address was valid and/or that the media was inserted correctly, and try again.

Note that this driver-loading mechanism is only compatible with media/locations containing XenSource repositories.  Check the user guide for more information.""",
            ['Back'])
        return -1
    else:
        if len(drivers) == 1:
            text = "The following driver was found: \n\n"
        elif len(drivers) > 1:
            text = "The following drivers were found:\n\n"
        text += "\n".join(driver_names)
        rc = ButtonChoiceWindow(
            tui.screen, "Load drivers", text, ['Load Drivers', 'Back'])

        if rc in ['load drivers', None]: return 1
        if rc == 'back': return -1

def ask_export_destination_screen(answers):
    valid = False
    hn = ""
    while not valid:
        button, result = EntryWindow(
            tui.screen,
            "Export VMs",
            "Which host would you like to transfer the VMs to?",
            [("Hostname", Entry(50, hn))], entryWidth = 50,
            buttons = ["Ok", "Back"])
        
        if button == "back":
            valid = True
        elif button == "ok":
            hn = result[0].strip()
            if hn != "" and " " not in hn:
                valid = True
                answers['hostname'] = hn
            else:
                ButtonChoiceWindow(
                    tui.screen,
                    "Hostname required",
                    "You must enter a valid hostname",
                    ["Ok"])

    if button == "back":
        return -1
    else:
        return 1

def ask_host_password_screen(answers):
    button, result = snackutil.PasswordEntryWindow(
        tui.screen,
        "Password",
        "Please enter the password for the host you are connecting to:",
        ["Password"], entryWidth = 30,
        buttons = ["Ok", "Back"])

    answers['password'] = result[0]

    if button == "back":
        return -1
    else:
        return 1

def select_backup(backups):
    entries = []
    for b in backups:
        backup_partition, restore_disk = b
        entries.append(("%s, to be restored on %s" %
                           (backup_partition[5:], restore_disk[5:]), 
                        b))

    b, e = ListboxChoiceWindow(
        tui.screen,
        'Multiple Backups',
        'More than one backup has been found.  Which would you like to use?',
        entries,
        ['Select', 'Cancel']
        )

    if b in [ None, 'select' ]:
        return e
    else:
        return None

def confirm_restore(backup_partition, disk):
    b = snackutil.ButtonChoiceWindowEx(
        tui.screen,
        "Confirm Restore",
        "Are you sure you want to restore your installation on %s with the backup on %s?\n\nYour existing installation will be overwritten with the backup (though VMs will still be intact).\n\nTHIS OPERATION CANNOT BE UNDONE." % (disk[5:], backup_partition[5:]),
        ['Restore', 'Cancel'], default=1, width=50
        )

    return b in ['restore', None]

