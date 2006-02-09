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

    # CCISS disks:
    pipe = os.popen("blockdev --report | grep -v '/dev/hd' | grep -v '/dev/sd' | grep -v '.*p[0-9]$' | awk '{ print $7 }'")
    for dev in pipe:
        dev = dev.strip("\n")
        if dev != "Device":
            devices.append(dev)

    pipe.close()

    return devices

def getNetifList():
    pipe = os.popen("/sbin/ifconfig -a | grep '^[a-z].*' | awk '{ print $1 }' | grep '^eth.*'")
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
    else:
        sequence = [ ui_package.select_primary_disk,
                     ui_package.select_guest_disks ]
    
    return uicontroller.runUISequence(sequence, answers)

def confirm_installation(answers):
    ui_package = answers['ui-package']
    disks = getDiskList()

    if len(disks) == 1:
        sequence = [ ui_package.confirm_installation_one_disk ]
    else:
        sequence = [ ui_package.confirm_installation_multiple_disks ]

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

def makeHumanList(list):
    if len(list) == 0:
        return ""
    elif len(list) == 1:
        return list[0]
    else:
        start = ", ".join(list[:len(list) - 1])
        start += " and %s" % list[len(list) - 1]
        return start
                          
