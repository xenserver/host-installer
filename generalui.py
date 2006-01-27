###
# XEN CLEAN INSTALLER
# General functions related to UI
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import os
import uicontroller

def getDiskList():
    pipe = os.popen("blockdev --report | grep -v '.*[0-9]$' | awk '{ print $7 }'")
    devices = []
    for dev in pipe:
        dev = dev.strip("\n")
        if dev != "Device":
            devices.append(dev)

    pipe.close()

    return devices

def getNetifList():
    pipe = os.popen("/sbin/ifconfig -a | grep '^[a-z].*' | awk '{ print $1 }'")
    interfaces = []
    for iface in pipe:
        interfaces.append(iface.strip("\n"))
    pipe.close()

    return interfaces

# TODO
def getHWAddr(iface):
    return None

def disk_selection(answers):
    ui_package = answers['ui-package']
    disks = getDiskList()

    if len(disks) == 1:
        answers['primary-disk'] = disks[0]
        answers['guest-disks'] = []
        sequence = [ ui_package.confirm_installation_one_disk ]
    else:
        sequence = [ ui_package.select_primary_disk,
                     ui_package.select_guest_disks,
                     ui_package.confirm_destroy_disks ]
    
    return uicontroller.runUISequence(sequence, answers)


###
# Logging

log_redirect = '>/dev/null 2>&1'
#log_redirect = ''

def setRedirectFile(filename):
    global log_redirect
    log_redirect = "&>%s" % filename

def runCmd(command):
    global log_redirect
    actualCmd = "%s %s" % (command, log_redirect)
    return os.system(actualCmd)
