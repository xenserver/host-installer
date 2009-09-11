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
from uicontroller import SKIP_SCREEN, LEFT_BACKWARDS, RIGHT_FORWARDS
import tui.network
import tui.progress
import tui.repo
import repository
import snackutil
import xelogging

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
        (' * Convert an existing OS on this machine to a %s (P2V)' % BRAND_GUEST_SHORT, init_constants.OPERATION_P2V)
        ]

    if display_restore:
        entries.append( (' * Restore from backup', init_constants.OPERATION_RESTORE) )

    (button, entry) = ListboxChoiceWindow(tui.screen,
                                          "Welcome to %s" % PRODUCT_BRAND,
                                          """Please select an operation:""",
                                          entries,
                                          ['Ok', 'Load driver', 'Exit and reboot'], width=70)

    if button == 'ok' or button == None:
        return entry
    elif button == 'load driver':
        return init_constants.OPERATION_LOAD_DRIVER
    else:
        return init_constants.OPERATION_REBOOT

def driver_disk_sequence(answers):
    uic = uicontroller
    seq = [
        uic.Step(tui.repo.select_repo_source, 
                 args = ["Select Driver Source", "Please select where you would like to load the Supplemental Pack containing the driver from:", 
                         False]),
        uic.Step(require_networking,
                 predicates = [lambda a: a['source-media'] != 'local' and 
                               not a.has_key('network-configured')]),
        uic.Step(tui.repo.get_source_location, 
                 predicates = [lambda a: a['source-media'] != 'local'],
                 args = [False]),
        uic.Step(confirm_load_drivers),
        uic.Step(tui.repo.verify_source, args=['driver']),
        uic.Step(eula_screen),
        ]
    rc = uicontroller.runSequence(seq, answers)

    if rc == LEFT_BACKWARDS:
        return None
    return (answers['source-media'], answers['source-address'])

def get_driver_source(answers):
    entries = [
        ('Removable media', 'local'),
        ('HTTP or FTP', 'url'),
        ('NFS', 'nfs')
        ]
    result, entry = ListboxChoiceWindow(
        tui.screen,
        "Load Driver",
        "Please select where you would like to load a driver from:",
        entries, ['Ok', 'Back'])

    if result == 'back': return LEFT_BACKWARDS

    answers['source-media'] = entry
    if entry == 'local':
        answers['source-address'] = ''
    return RIGHT_FORWARDS

def require_networking(answers):
    rc = tui.network.requireNetworking(answers)

    if rc == RIGHT_FORWARDS:
        # no further prompts
        answers['network-configured'] = True
    return rc

def confirm_load_drivers(answers):
    # find drivers:
    try:
        tui.progress.showMessageDialog("Please wait", "Searching for drivers...")
        repos = repository.repositoriesFromDefinition(
            answers['source-media'], answers['source-address'])
        tui.progress.clearModelessDialog()
    except:
        ButtonChoiceWindow(
            tui.screen, "Error",
            """Unable to access location specified.  Please check the address was valid and/or that the media was inserted correctly, and try again.""",
            ['Back'])
        return LEFT_BACKWARDS
        
    drivers = []

    for r in repos:
        has_drivers = False
        for p in r:
            if p.type.startswith("driver") and p.is_compatible():
                has_drivers = True
        if has_drivers:
           drivers.append(p)

    if len(drivers) == 0:
        ButtonChoiceWindow(
            tui.screen, "No Drivers Found",
            """No compatible drivers were found at the location specified.  Please check the address was valid and/or that the media was inserted correctly, and try again.

Note that this driver-loading mechanism is only compatible with media/locations containing %s repositories.  Check the installation guide for more information.""" % PRODUCT_BRAND,
            ['Back'])
        return LEFT_BACKWARDS
    else:
        this_repo = None
        driver_text = ""
        for d in drivers:
            if this_repo != d.repository:
                driver_text += "\n%s\n\n" % d.repository.name().center(30)
                this_repo = d.repository
            driver_text += " * %s\n" % d.name

        if len(drivers) == 1:
            text = "The following driver was found:\n"
        elif len(drivers) > 1:
            text = "The following drivers were found:\n"
        text += driver_text

        while True:
            rc = ButtonChoiceWindow(
                tui.screen, "Load Drivers", text, ['Load drivers', 'Info', 'Back'])

            if rc == 'back': return LEFT_BACKWARDS
            if rc in [None, 'load drivers']:
                answers['repos'] = repos
                return RIGHT_FORWARDS

            if rc == 'info':
                hashes = [" %s %s" % (r.md5sum(), r.name()) for r in repos]
                text2 = "The following MD5 hashes have been calculated. Please check them against those provided by the driver supplier:\n\n"
                text2 += "\n".join(hashes)
                ButtonChoiceWindow(
                    tui.screen, "Driver Repository Information", text2, ['Ok'])

def eula_screen(answers):
    eula = ''
    for r in answers['repos']:
        for p in r:
            if not p.is_compatible(): continue
            e = p.eula()
            if e:
                eula += e + '\n'
    if eula == '':
        return SKIP_SCREEN

    while True:
        button = snackutil.ButtonChoiceWindowEx(
            tui.screen,
            "Driver License Agreement",
            eula,
            ['Accept EULA', 'Back'], width=60, default=1)

        if button == 'accept eula':
            return RIGHT_FORWARDS
        elif button == 'back':
            return LEFT_BACKWARDS
        else:
            ButtonChoiceWindow(
                tui.screen,
                "Driver License Agreement",
                "You must select 'Accept EULA' (by highlighting it with the cursor keys, then pressing either Space or Enter) in order to install this driver.",
                ['Ok'])

# OBSOLETE?
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

    if button == 'back': return LEFT_BACKWARDS
    return RIGHT_FORWARDS

# OBSOLETE?
def ask_host_password_screen(answers):
    button, result = snackutil.PasswordEntryWindow(
        tui.screen,
        "Password",
        "Please enter the password for the host you are connecting to:",
        ["Password"], entryWidth = 30,
        buttons = ["Ok", "Back"])

    if button == 'back': return LEFT_BACKWARDS

    answers['password'] = result[0]

    return RIGHT_FORWARDS

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

