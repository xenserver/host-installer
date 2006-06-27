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
import diskutil
from constants import ANSWERS_FILE
from version import *
from util import runCmd
from snack import ButtonChoiceWindow

# module globals:
sub_ui_package = None
pyAnswerFile = None
pyAnswerFileDevice = None

class PreviousInstallationNotFound(Exception):
    def __init__(self):
        Exception.__init__(self, "No previous %s installations were detected." % PRODUCT_BRAND)

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

def __findAnswerFileDevice__():
    devices_to_check = diskutil.getQualifiedPartitionList()
    device = None
    check_file = ANSWERS_FILE

    if not os.path.exists('/tmp/mnt'):
        os.mkdir('/tmp/mnt')
    
    for device_path in devices_to_check:
        if os.path.exists(device_path):
            try:
                util.mount(device_path, '/tmp/mnt', ['ro'], 'ext2')
                if os.path.isfile('/tmp/mnt/%s' % check_file):
                    device = device_path
                    util.umount("/tmp/mnt")
                    break
            except util.MountFailureException:
                # clearly it wasn't that device...
                pass
            else:
                if os.path.ismount('/tmp/mnt'):
                    util.umount('/tmp/mnt')

    if not device:
        raise PreviousInstallationNotFound()
    else:
        specifyAnswerFileDevice(device)

def specifyAnswerFileDevice(file):
    global pyAnswerFileDevice
    assert type(file) == str
    pyAnswerFileDevice = file

def init_ui(results, is_subui):
    # now pass on initialisation to our sub-UI:
    if sub_ui_package is not None:
        sub_ui_package.init_ui(results, True)

def prepareForUpgrade(results):
    global pyAnswerFile
    global pyAnswerFileDevice

    __findAnswerFileDevice__()

    if pyAnswerFileDevice != None:
        if not os.path.isdir('/tmp/mnt'):
            os.mkdir('/tmp/mnt')
        try:
            util.mount(pyAnswerFileDevice, '/tmp/mnt')
        except:
            raise PreviousInstallationNotFound()

        pyAnswerFile = os.path.join("/tmp/mnt", ANSWERS_FILE)
        if not os.path.isfile(pyAnswerFile):
            util.umount('/tmp/mnt')
            raise PreviousInstallationNotFound()
        else:
            # lets ask the user if they want to use it
            # XXX - we shouldn't assume we have a sub_ui_package
            # here...
            button = ButtonChoiceWindow(sub_ui_package.screen, "Use existing settings",
            """%s Setup can use existing settings to upgrade your %s host. 

Do you want to use existing settings?""" % (PRODUCT_BRAND, PRODUCT_BRAND), 
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

    assert answers != None
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
def get_keyboard_type(answers):
    return 1
def get_keymap(answers):
    return 1
def confirm_erase_volume_groups(answers):
    return 1
def confirm_wipe_existing(answers):
    return 1
def confirm_installation_one_disk(answers):
    return 1
def confirm_installation_multiple_disks(answers):
    return 1
def select_installation_source(answers, other):
    if answers.has_key('upgrade') and answers['upgrade'] and sub_ui_package:
        return sub_ui_package.select_installation_source(answers, {'cd-available': True})
    else:
        return 1
def get_http_source(answers):
    if answers.has_key('upgrade') and answers['upgrade'] and sub_ui_package:
        return sub_ui_package.get_http_source(answers)
    else:
        return 1
def get_nfs_source(answers):
    if answers.has_key('upgrade') and answers['upgrade'] and sub_ui_package:
        return sub_ui_package.get_nfs_source(answers)
    else:
        return 1
def verify_source(answers):
    if answers.has_key('upgrade') and answers['upgrade'] and sub_ui_package:
        return sub_ui_package.verify_source(answers)
    else:
        return 1
def select_primary_disk(answers):
    return 1
def select_guest_disks(answers):
    return 1
def get_root_password(answers):
    return 1
def determine_basic_network_config(answers):
    return 1
def get_timezone_region(answers):
    return 1
def get_timezone_city(answers):
    return 1
def get_time_configuration_method(answers):
    return 1
def get_ntp_servers(answers):
    return 1
def set_time(answers, now):
    answers['set-time'] = False
    return 1
def get_name_service_configuration(answers):
    return 1
def installation_complete(answers):
    return 1
def upgrade_complete(answers):
    if sub_ui_package:
        return sub_ui_package.upgrade_complete(answers)
    else:
        return 1

# 0 means don't retry
def request_media(medianame):
    return 0
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
