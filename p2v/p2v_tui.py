#!/usr/bin/python
###
# XEN CLEAN INSTALLER
# Text user interface functions
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

from snack import *
#import generalui
import p2v_uicontroller
import findroot
import os
import sys

screen = None

# functions to start and end the GUI - these create and destroy a snack screen as
# appropriate.
def init_ui():
    global screen

    screen = SnackScreen()
    screen.drawRootText(0, 0, "Welcome to Xen Enterprise")

def end_ui():
    global screen

    if screen:
        screen.finish()

# welcome screen:
def welcome_screen(answers):
    global screen

    button = ButtonChoiceWindow(screen,
                       "Welcome to Xen Enterprise P2V",
                       """This will convert a locally installed OS install to a XenEnterprise machine to be used as a Xen guest on that machine.""",
                       ['Ok', 'Cancel'], width=50)

    # advance to next screen:
    if button == "cancel": return 0
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
                        ['Cancel'], width=50)

    if button == "cancel": return 1

    #ask for more info
    if entry == 0:
        answers['xen-target'] = 'xe'
        (button, xehost) = EntryWindow(screen,
                "XenEnterprise Host Information",
                "Please enter the XenEnterprise hostname: ",
                ['Hostname:'],
                buttons= ['Ok', 'Back'])
        answers['xehost'] = xehost[0]
    elif entry == 1:
        answers['xen-target'] = 'nfs'
        (button, (nfshost, nfspath)) = EntryWindow(screen,
                 "NFS Server Information",
                "Please enter the NFS server information: ",
                ['NFS Server:', 'Path'],
                buttons= ['Ok', 'Back'])
        answers['nfshost'] = nfshost
        answers['nfspath'] = nfspath
        

    #dump_answers(answers)
    #advance to next screen:
    return 1

def get_os_installs(answers):
    os_installs = findroot.findroot()
    
    return os_installs

#let the user chose the OS install
def os_install_screen(answers):
    global screen
    os_install_strings = []
    if screen: screen.suspend()

    os_installs = get_os_installs(answers)
    for os in os_installs: 
        os_install_strings.append(os[0] + " " + os[1] + "  (" + os[2] + ")")

    if screen: screen.resume()
    
    if len(os_install_strings) > 0:
        (button, entry) = ListboxChoiceWindow(screen,
                "OS Installs",
                "Which OS install do you want to P2V?",
                os_install_strings,
                ['Ok', 'Back'])
            
        if button == "ok" or button == None:
            ButtonChoiceWindow(screen, "debug", """OK pressed""",  ['Ok'], width=50)
            answers['osinstall'] = os_installs[entry]
            return 1
        else:
            return 0
    else: 
        ButtonChoiceWindow(screen, "debug", """NO oss found""",  ['Ok'], width=50)
        return -1
    
    if button == "back": 
        ButtonChoiceWindow(screen, "debug", """Back Pressed""",  ['Ok'], width=50)
        return 1

def dump_answers(answers):
    global screen

    for key in answers.keys():
        ButtonChoiceWindow(screen,
            "keys",
            """key = %s, value = %s""" % (key, answers[key]),
            ['Ok'], width=50)


