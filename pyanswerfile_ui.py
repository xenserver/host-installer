#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Main script
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import pickle
import os
import util
from constants import ANSWERS_FILE
from version import *
from util import runCmd
from snack import *

# module globals:
sub_ui_package = None
pyAnswerFile = None
pyAnswerFileDevice = None

# allow a sub-interface to specified - progress dialog calls and the
# init and de-init calls will be passed through.  Dialogs will be translated
# as no-ops.
def specifySubUI(subui):
    global sub_ui_package
    sub_ui_package = subui

def specifyAnswerFile(file):
    global pyAnswerFile
    assert type(file) == str

    util.fetchFile(file, "/tmp/pyanswerfile")
    
    pyAnswerFile = "/tmp/pyanswerfile"

def specifyAnswerFileDevice(file):
    global pyAnswerFileDevice
    assert type(file) == str
    pyAnswerFileDevice = file

def init_ui(results, is_subui):
    global pyAnswerFile
    global pyAnswerFileDevice
    
    # now pass on initialisation to our sub-UI:
    if sub_ui_package is not None:
        sub_ui_package.init_ui(results, True)

    if pyAnswerFileDevice != None:
        assert runCmd("mkdir -p /tmp/mnt/") == 0
        rc = runCmd("mount %s /tmp/mnt/" % pyAnswerFileDevice)
        if rc != 0:
            raise Exception("Failed to find a previous installation. Upgrade is not supported")
        pyAnswerFile = os.path.join("/tmp/mnt", ANSWERS_FILE)
        if not os.path.isfile(pyAnswerFile):
            runCmd("umount /tmp/mnt")
            raise Exception("Failed to find a previous installation. Upgrade is not supported")
        else:
            #lets ask the user if they want to use it
            button = ButtonChoiceWindow(sub_ui_package.screen, "Use existing settings",
            """%s Setup can use existing settings to upgrade your %s host. You will only be asked to enter a new root password.

Do you want to use existing settings?
            """ % (PRODUCT_BRAND, PRODUCT_BRAND), 
            ['Yes', 'No'], width=60)

            if button == "no":
                pyAnswerFile = None
                results['usesettings'] = False
                runCmd("umount /tmp/mnt")
                return
            else:
                fd = open(pyAnswerFile, "r")
                answers = pickle.load(fd)
                fd.close()
                runCmd("umount /tmp/mnt")
                results['usesettings'] = True

    elif pyAnswerFile is not None:
        fd = open(pyAnswerFile, 'r')
        answers = pickle.load(fd)
        fd.close()

    for key in answers:
        results[key] = answers[key]

def end_ui():
    if sub_ui_package is not None:
        sub_ui_package.end_ui()

# XXX THESE MUST GO!!!!
def suspend_ui():
    pass

def resume_ui():
    pass

# stubs:
def welcome_screen(answers):
    return 1
def upgrade_screen(answers):
    return 1
def no_disks():
    return 1
def no_netifs():
    return 1
def confirm_installation_one_disk(answers):
    return 1
def confirm_installation_multiple_disks(answers):
    return 1
def select_installation_source(answers, other):
    return 1
def get_http_source(answers):
    return 1
def get_nfs_source(answers):
    return 1
def select_primary_disk(answers):
    return 1
def select_guest_disks(answers):
    return 1
def get_root_password(answers):
    if not answers.has_key('root-password') and sub_ui_package:
        return sub_ui_package.get_root_password(answers)
    else:
        return 1
def determine_basic_network_config(answers):
    return 1
def get_timezone(answers):
    return 1
def set_time(answers):
    answers['set-time'] = False
    return 1
def get_name_service_configuration(answers):
    return 1
def installation_complete(answers):
    return 1
def upgrade_complete(answers):
    return 1

def error_dialog(message):
    if sub_ui_package:
        sub_ui_package.error_dialog(message)

# progress dialogs:
def initProgressDialog(title, text, total):
    if sub_ui_package:
        return sub_ui_package.initProgressDialog(title, text, total)

def displayProgressDialog(current, pd):
    if sub_ui_package:
        sub_ui_package.displayProgressDialog(current, pd)

def clearModelessDialog():
    if sub_ui_package:
        sub_ui_package.clearModelessDialog()
