#!/usr/bin/python
###
# XEN CLEAN INSTALLER
# Text user interface functions
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

from snack import *
from version import *
#import generalui
import p2v_uicontroller
import findroot
import os
import sys
import constants
import p2v_utils
import time

screen = None

# functions to start and end the GUI - these create and destroy a snack screen as
# appropriate.
def init_ui():
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

# welcome screen:
def welcome_screen(answers):
    global screen

    button = ButtonChoiceWindow(screen,
                       "Welcome to %s P2V" % PRODUCT_BRAND,
                       """This will convert a locally installed OS install to a %s machine to be used as a Xen guest on that machine.""" % PRODUCT_BRAND,
                       ['Ok', 'Cancel'], width=50)

    # advance to next screen:
    if button == "cancel": return -2
    return 1

# NFS or XenEnterprise target
def target_screen(answers):
    global screen

    entries = [ 'XenEnterprise Machine',
                'NFS Server' ]

    (button, entry) = ListboxChoiceWindow(screen,
                        "Target Choice",
                        """Please choose the target you want send the P2V image of your machine to.""",
                        entries,
                        ['Ok', 'Cancel'], width=50)

    if button == "cancel": return -2

    #ask for more info
    if entry == 0:
        answers[constants.XEN_TARGET] = constants.XEN_TARGET_XE
        (button, xehost) = EntryWindow(screen,
                "%s Host Information" % PRODUCT_BRAND,
                "Please enter the %s host information: " % PRODUCT_BRAND,
                ['Hostname or IP:'],
                buttons= ['Ok', 'Back'])
        answers[constants.XE_HOST] = xehost[0]
    elif entry == 1:
        answers[constants.XEN_TARGET] = constants.XEN_TARGET_NFS
        (button, (nfshost, nfspath)) = EntryWindow(screen,
                 "NFS Server Information",
                "Please enter the NFS server information: ",
                ['Hostname or IP:', 'Path:'],
                buttons= ['Ok', 'Back'])
        answers[constants.NFS_HOST] = nfshost
        answers[constants.NFS_PATH] = nfspath
        

    #dump_answers(answers)
    #advance to next screen:
    return 1

def get_os_installs(answers):
    os_installs = findroot.findroot()
    
    return os_installs

def isP2Vable(os):
    if os[constants.OS_NAME] != "Red Hat" or os[constants.OS_VERSION] != "4.1":
            return False;
    else:
        return True;

#let the user chose the OS install
def os_install_screen(answers):
    global screen
    os_install_strings = []
    
    

    os_installs = get_os_installs(answers)
    for os in os_installs: 
        if isP2Vable(os):
            os_install_strings.append(os[constants.OS_NAME] + " " + os[constants.OS_VERSION] + "  (" + os[constants.DEV_NAME] + ")")
    
    if len(os_install_strings) > 0:
        (button, entry) = ListboxChoiceWindow(screen,
                "OS Installs",
                "Which OS install do you want to P2V?",
                os_install_strings,
                ['Ok', 'Back'])
            
        if button == "ok" or button == None:
            answers['osinstall'] = os_installs[entry]
            return 1
        else:
            return -1
    else: 
        ButtonChoiceWindow(screen, "debug", """NO oss found""",  ['Ok'], width=50)
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
        osinstall[constants.DESCRIPTION] = description[0]
        return 1
    else:
        return -1


def dump_answers(answers):
    global screen

    for key in answers.keys():
        ButtonChoiceWindow(screen,
            "keys",
            """key = %s, value = %s""" % (key, answers[key]),
            ['Ok'], width=50)


def finish_screen(answers):
    global screen
    ButtonChoiceWindow(screen, "Finish P2V", """P2V operation successfully completed""", ['Ok'], width = 50)
    return 1
    
def failed_screen(answers):
    global screen
    ButtonChoiceWindow(screen, "Finish P2V", """P2V operation failed""", ['Ok'], width = 50)
    return 1

def displayPleaseWaitDialog():
    global screen
    form = GridFormHelp(screen, "Please wait...", None, 1, 3)
    t = Textbox(60, 1, """Please wait while scanning for block devices.
This can take a long time...""")
    form.add(t, 0, 0, padding = (0,0,0,1))
    
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