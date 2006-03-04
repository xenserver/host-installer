###
# XEN CLEAN INSTALLER
# General functions related to UI
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import os
import uicontroller
import commands
import logging

timezone_data_file = '/opt/xensource/clean-installer/timezones'

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

def getDiskDeviceVendor(deviceName):
    rc, output = runOutputCmd('cat /sys/block/%s/device/vendor' % deviceName)
    if rc == 0:
        return output.strip()
    else:
        return None
        

def getDiskDeviceModel(deviceName):
    rc, output = runOutputCmd('cat /sys/block/%s/device/model' % deviceName)
    if rc == 0:
        return output.strip()
    else:
        return None

def getDiskDeviceSize(deviceName):
    rc, output = runOutputCmd('cat /sys/block/%s/size' % deviceName)
    if rc == 0:
        return output.strip()
    else:
        return None
    
def getHumanDiskSize(rawDiskSize):
    longSize = long(rawDiskSize)
    gbSize = (longSize * 512) / (1024 * 1024 * 1024)
    return "%d GB" % gbSize

def getExtendedDiskInfo(disk):
    deviceNameParts = disk.split('/')
    if len(deviceNameParts) == 2:
        deviceName = deviceNameParts[1]
    elif len(deviceNameParts) == 3:
        deviceName = deviceNameParts[2]
    else:
        #unsupported
        return None
    
    deviceVendor = getDiskDeviceVendor(deviceName)
    deviceModel = getDiskDeviceModel(deviceName)
    deviceSize = getDiskDeviceSize(deviceName)
    
    return (deviceVendor, deviceModel, deviceSize)

def getNetifList():
    pipe = os.popen("/sbin/ifconfig -a | grep '^[a-z].*' | awk '{ print $1 }' | grep '^eth.*'")
    interfaces = []
    for iface in pipe:
        interfaces.append(iface.strip("\n"))
    pipe.close()

    return interfaces

def getTimeZones():
    global timezone_data_file

    tzf = open(timezone_data_file)
    lines = tzf.readlines()
    tzf.close()

    # strip trailing newlines:
    return map(lambda x: x.strip('\n'), lines)

# TODO
def getHWAddr(iface):
    return None

def disk_selection(answers, args):
    ui_package = args['ui-package']
    disks = getDiskList()

    if len(disks) == 1:
        answers['primary-disk'] = disks[0]
        answers['guest-disks'] = []
        return 1
    else:
        sequence = [ ui_package.select_primary_disk,
                     ui_package.select_guest_disks ]
        return uicontroller.runUISequence(sequence, answers)

def confirm_installation(answers, args):
    ui_package = args['ui-package']
    disks = getDiskList()

    if len(disks) == 1:
        sequence = [ ui_package.confirm_installation_one_disk ]
    else:
        sequence = [ ui_package.confirm_installation_multiple_disks ]

    return uicontroller.runUISequence(sequence, answers)

def runCmd(command):
    (rv, output) = commands.getstatusoutput(command)
    logging.logOutput(command, output)
    return rv

def runOutputCmd(command):
    (rv, output) = commands.getstatusoutput(command)
    logging.logOutput(command, output)
    return (rv, output)
    

def makeHumanList(list):
    if len(list) == 0:
        return ""
    elif len(list) == 1:
        return list[0]
    else:
        start = ", ".join(list[:len(list) - 1])
        start += " and %s" % list[len(list) - 1]
        return start
                          
