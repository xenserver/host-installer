###
# XEN CLEAN INSTALLER
# General functions related to UI
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import os
import uicontroller
import time
import datetime
import util
import diskutil
import constants

from util import runCmdWithOutput

def getNetifList():
    pipe = os.popen("/sbin/ifconfig -a | grep '^[a-z].*' | awk '{ print $1 }' | grep '^eth.*'")
    interfaces = []
    for iface in pipe:
        interfaces.append(iface.strip("\n"))
    pipe.close()

    return interfaces

def getTimeZones():
    tzf = open(constants.timezone_data_file)
    lines = tzf.readlines()
    tzf.close()

    # strip trailing newlines:
    return map(lambda x: x.strip('\n'), lines)

# TODO
def getHWAddr(iface):
    return None

def disk_selection(answers, args):
    ui_package = args['ui-package']
    disks = diskutil.getQualifiedDiskList()

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
    disks = diskutil.getQualifiedDiskList()

    if len(disks) == 1:
        sequence = [ ui_package.confirm_installation_one_disk ]
    else:
        sequence = [ ui_package.confirm_installation_multiple_disks ]

    return uicontroller.runUISequence(sequence, answers)

def makeHumanList(list):
    if len(list) == 0:
        return ""
    elif len(list) == 1:
        return list[0]
    else:
        start = ", ".join(list[:len(list) - 1])
        start += " and %s" % list[len(list) - 1]
        return start

# Hack to get the time in a different timezone
def translateDateTime(dt, tzname):
    return dt

    # TODO - tzset not compiled into Python for uclibc
    
    localtz = "utc"
    if os.environ.has_key('TZ'):
        localtz = os.environ['TZ']
    os.environ['TZ'] = tzname
    time.tzset()

    # work out the delta:
    nowlocal = datetime.datetime.now()
    nowutc = datetime.datetime.utcnow()
    delta = nowlocal - nowutc

    os.environ['TZ'] = localtz
    time.tzset()

    return dt + delta
