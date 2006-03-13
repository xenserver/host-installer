#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Main script
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import pickle
from constants import ANSWERS_FILE
from util import runCmd

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
    pyAnswerFile = file

def specifyAnswerFileDevice(file):
    global pyAnswerFileDevice
    assert type(file) == str
    pyAnswerFileDevice = file

def init_ui(results, is_subui):
    global pyAnswerFile
    global pyAnswerFileDevice
    
    if pyAnswerFileDevice != None:
        assert runCmd("mkdir -p /tmp/mnt/") == 0
        assert runCmd("mount %s /tmp/mnt/" % pyAnswerFileDevice) == 0
        pyAnswerFile = os.path.join("/tmp/mnt", ANSWERS_FILE)
    
    assert pyAnswerFile
    
    fd = open(pyAnswerFile, "r")
    answers = pickle.load(fd)
    fd.close()

    if pyAnswerFileDevice != None:
        runCmd("umount /tmp/mnt")

    for key in answers:
        results[key] = answers[key]

    # now pass on initialisation to our sub-UI:
    if sub_ui_package is not None:
        sub_ui_package.init_ui(results, True)
        

def end_ui():
    if sub_ui_package is not None:
        sub_ui_package.end_ui()

# XXX THESE MUST GO!!!!
def suspend_ui():
    pass

def resume_ui():
    pass

# stubs:
###
# - stage 1 install:
def welcome_screen(answers):
    return 1
def upgrade_screen(answers):
    return 1
def confirm_installation_one_disk(answers):
    return 1
def confirm_installation_multiple_disks(answers):
    return 1
def select_primary_disk(answers):
    return 1
def select_guest_disks(answers):
    return 1
def get_root_password(answers):
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

# progress dialogs:
def initProgressDialog(title, text, total):
    if sub_ui_package:
        sub_ui_package.initProgressDialog(title, text, total)

def displayProgressDialog(current, pd):
    if sub_ui_package:
        sub_ui_package.displayProgressDialog(current, pd)

def clearModelessDialog():
    if sub_ui_package:
        sub_ui_package.clearProgressDialog()
