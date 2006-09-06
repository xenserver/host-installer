#!/usr/bin/python
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

from snack import *
from version import *
import p2v_uicontroller
import findroot
import os
import sys
import p2v_constants
import p2v_utils
import p2v_backend
import time
import xelogging
from p2v import closeClogs

from p2v_error import P2VMountError, P2VCliError

screen = None

def MyEntryWindow(screen, title, text, prompts, allowCancel = 1, width = 40,
		entryWidth = 20, buttons = [ 'Ok', 'Cancel' ], help = None):
    bb = ButtonBar(screen, buttons);
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
	    e = Entry(entryWidth, e)
	else:
	    e = Entry(entryWidth)

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

# functions to start and end the GUI - these create and destroy a snack screen as
# appropriate.
def init_ui(results):
    global screen

    screen = SnackScreen()
    screen.drawRootText(0, 0, "Welcome to %s" % PRODUCT_BRAND)
    
def redraw_screen():
    global screen
    screen.refresh()
    
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

    button = ButtonChoiceWindow(screen,
                       "Welcome to %s P2V" % PRODUCT_BRAND,
                       """This will copy a locally-installed OS filesystem and convert it into a %s running on a %s, or to a template on an NFS share that can be imported to a %s.""" % (BRAND_GUEST_SHORT, BRAND_SERVER, BRAND_SERVER),
                       ['Ok', 'Cancel'], width=50)

    # advance to next screen:
    if button == "cancel": return -2
    return 1

# NFS or XenEnterprise target
def target_screen(answers):
    global screen
    
    hn = ""

    entries = [ '%s' % BRAND_SERVER,
                'NFS Server' ]

    (button, entry) = ListboxChoiceWindow(screen,
                        "Target Choice",
                        """Please choose the target you want send the P2V image of your machine to.""",
                        entries,
                        ['Ok', 'Cancel'], width=50)

    if button == "cancel": return -2

    #ask for more info
    if entry == 0:
        # preset the hostname
        if answers.has_key(p2v_constants.XE_HOST):
            hn = answers[p2v_constants.XE_HOST]

        complete = False
        while not complete:
            answers[p2v_constants.XEN_TARGET] = p2v_constants.XEN_TARGET_SSH
            (button, xehost) = MyEntryWindow(screen,
                    "%s Information" % BRAND_SERVER,
                    "Please enter the %s information: " % BRAND_SERVER,
                    [('Hostname or IP:', hn)],
                    buttons= ['Ok', 'Back'])

            if button == 'back':
                return 0;

            if len(xehost[0]) > 0:
                answers[p2v_constants.XE_HOST] = xehost[0]
                complete = True
            else:
                ButtonChoiceWindow(screen,
                    "Invalid Entry",
                    "Invalid %s Information. Please review the information you entered." % (BRAND_SERVER),
                    buttons = ['Ok'])
                
    elif entry == 1:
        complete = False
        while not complete:
            hn = ""
            p = ""
            if answers.has_key(p2v_constants.NFS_HOST):
                hn = answers[p2v_constants.NFS_HOST]
            if answers.has_key(p2v_constants.NFS_PATH):
                p = answers[p2v_constants.NFS_PATH]
            answers[p2v_constants.XEN_TARGET] = p2v_constants.XEN_TARGET_NFS
            (button, (nfshost, nfspath)) = MyEntryWindow(screen,
                 "NFS Server Information",
                "Please enter the NFS server information: ",
                [('Hostname or IP:', hn), ('Path:', p)],
                buttons= ['Ok', 'Back'])
            answers[p2v_constants.NFS_HOST] = nfshost
            answers[p2v_constants.NFS_PATH] = nfspath

            if button == 'back':
                return 0;

            try:
                displayPleaseWaitDialog("Validating NFS information")
                p2v_backend.validate_nfs_path(nfshost, nfspath)
                removePleaseWaitDialog();
            except P2VMountError, e:
                ButtonChoiceWindow(screen,
                    "Cannot Connect",
                    "Failed to connect to %s:%s. Please re-enter the correct information." % (nfshost, nfspath),
                    buttons = ['Ok'])
            else:
                complete = True
  

    #dump_answers(answers)
    #advance to next screen:
    return 1

def get_os_installs(answers):
    os_installs = findroot.findroot()
    
    return os_installs

# TODO, CA-2747  pull this out of a supported OS list.
def isP2Vable(os):
    if os[p2v_constants.OS_NAME] == "Red Hat" and os[p2v_constants.OS_VERSION] == "4.1":
        return True;
    #if os[p2v_constants.OS_NAME] == "Red Hat" and os[p2v_constants.OS_VERSION] == "3.5":
        #return True;
    if os[p2v_constants.OS_NAME] == "Red Hat" and os[p2v_constants.OS_VERSION] == "3.6":
        return True;
    if os[p2v_constants.OS_NAME] == "SuSE" and os[p2v_constants.OS_VERSION] == "9sp2":
        return True;


    return False;

#let the user chose the OS install
def os_install_screen(answers):
    global screen
    os_install_strings = []
    supported_os_installs = []

    displayPleaseWaitDialog("Scanning for installed operating systems")
    os_installs = get_os_installs(answers)
    removePleaseWaitDialog()

    for os in os_installs: 
        if isP2Vable(os):
            os_install_strings.append(os[p2v_constants.OS_NAME] + " " + os[p2v_constants.OS_VERSION] + "  (" + os[p2v_constants.DEV_NAME] + ")")
            supported_os_installs.append(os)
    
    if len(os_install_strings) > 0:
        (button, entry) = ListboxChoiceWindow(screen,
                "OS Installs",
                "Which OS install do you want to P2V?",
                os_install_strings,
                ['Ok', 'Back'])
            
        if button == "ok" or button == None:
            p2v_utils.trace_message("os_install = " + str(supported_os_installs[entry]))
            answers['osinstall'] = supported_os_installs[entry]
            return 1
        else:
            return -1
    else: 
        # TODO, CA-2747  pull this out of a supported OS list.
        ButtonChoiceWindow(screen, "Error", """No supported operating systems found. 
Supported operating systems are: RHEL 4.1, RHEL 3.6 and SLES 9sp2.""",  ['Ok'], width=50)
        return -2
    
    if button == "back": 
        ButtonChoiceWindow(screen, "debug", """Back Pressed""",  ['Ok'], width=50)
        return 1

def description_screen(answers):
    global screen
    (button, description) = EntryWindow(screen,
                "P2V Description",
                "Please enter a description (optional): ",
                ['Description:'],
                buttons= ['Ok', 'Back'])

    if button == "ok" or button == None:
        osinstall = answers['osinstall']
        osinstall[p2v_constants.DESCRIPTION] = description[0].replace ("'", "_")
        return 1
    else:
        return -1

def size_screen(answers):
    global screen
    
    displayPleaseWaitDialog("""Determining size of the selected operating system""")
    p2v_backend.determine_size(answers['osinstall'])
    removePleaseWaitDialog()

    total_size = str(long(answers['osinstall'][p2v_constants.FS_TOTAL_SIZE]) / 1024**2)
    used_size = str(long(answers['osinstall'][p2v_constants.FS_USED_SIZE]) / 1024**2)
    new_size = long(0)
    success = False
    while not success:
        (button, size) = MyEntryWindow(screen,
                "Enter Volume Size",
                """Please enter the size of the volume that will be created on the %s. 
                
Currently, %s MB is in use by the chosen operating system.  The default size of the volume is 150%% of the used size or 4096 MB, whichever is bigger.""" % (BRAND_SERVER, used_size),
                [('Size in MB:', total_size)],
                buttons = ['Ok', 'Back'])
        try:
            l = long(size[0])
        except ValueError:
            continue

        if long(size[0]) < long(used_size):
            ButtonChoiceWindow(screen,
                "Size too small",
                "Minimum size = %s MB." % used_size,
                buttons = ['Ok'])
        else:
            new_size = long(size[0]) * 1024**2
            success = True

    if button == "ok" or button == None:
        answers['osinstall'][p2v_constants.FS_TOTAL_SIZE] = str(new_size)
        return 1
    else:
        return -1



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


def get_root_password(answers):
    global screen
    done = False

    #oh, what a dirty way of skipping unwanted screens
    if answers[p2v_constants.XEN_TARGET] != p2v_constants.XEN_TARGET_SSH:
        return 1;
   
    (button, result) = PasswordEntryWindow(screen,
                                 "Enter Password",
                                "Please enter the root password for the %s" % BRAND_SERVER,
                                 ['Password'],
                                 buttons = ['Ok', 'Back'])
    if button == 'back' or button == None:
        return -1
        
    # if they didn't select OK we should have returned already
    assert button == 'ok'
    osinstall = answers['osinstall']
    osinstall['root-password'] = result[0]
    return 1


def dump_answers(answers):
    global screen

    for key in answers.keys():
        ButtonChoiceWindow(screen,
            "keys",
            """key = %s, value = %s""" % (key, answers[key]),
            ['Ok'], width=50)


def finish_screen(answers):
    global screen
    xelogging.writeLog("/tmp/install-log")
    xelogging.collectLogs('/tmp')
    ButtonChoiceWindow(screen, "Finish P2V", """P2V operation successfully completed. Please press enter to reboot the machine.""", ['Ok'], width = 50)
    return 1
    
def failed_screen(answers):
    global screen
    ButtonChoiceWindow(screen, "Finish P2V", """P2V operation failed""", ['Ok'], width = 50)
    return 1

def displayPleaseWaitDialog(wait_text):
    global screen
    form = GridFormHelp(screen, "Please wait...", None, 1, 3)
    t = Textbox(60, 3, """Please wait:
%s.
This can take a long time...""" % wait_text)
    form.add(t, 0, 0, padding = (0,0,0,1))
    form.draw()
    screen.refresh()
    
def removePleaseWaitDialog():
    global screen
    screen.popWindow()

###
# Progress dialog:
def initProgressDialog(title, text, total):
    global screen
    
    form = GridFormHelp(screen, title, None, 1, 3)
    
    t = Textbox(60, 1, text)
    t2 = Textbox(60, 1, "testtext")
    scale = Scale(60, total)
    form.add(t, 0, 0, padding = (0,0,0,1))
    form.add(t2, 0, 1, padding = (0,0,0,0))
    form.add(scale, 0, 2, padding = (0,0,0,0))

    return (form, scale, t2)

def displayProgressDialog(current, (form, scale, t2), t2_text = ""):
    global screen
    
    t2.setText(t2_text)
    scale.set(current)

    form.draw()
    screen.refresh()
    
    time.sleep(.5)

def clearProgressDialog():
    global screen
    
    screen.popWindow()

def displayButtonChoiceWindow(screen, title, text, 
		       buttons = [ 'Ok', 'Cancel' ], 
		       width = 40, x = None, y = None, help = None):
    ButtonChoiceWindow(screen, title, text,
            buttons, width, x, y, help)
 
