# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# General functions related to UI
#
# written by Andrew Peace

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

def getTimeZoneRegions():
    tzf = open(constants.timezone_data_file)
    lines = tzf.readlines()
    tzf.close()

    lines = map(lambda x: x.strip('\n').split('/'), lines)

    regions = []
    for zone in lines:
        if zone[0] not in regions:
            regions.append(zone[0])

    return regions

def getTimeZoneCities(desired_region):
    tzf = open(constants.timezone_data_file)
    lines = tzf.readlines()
    tzf.close()

    lines = map(lambda x: x.strip('\n').split('/'), lines)

    cities = []
    for zone in lines:
        city = "/".join(zone[1:])
        if zone[0] == desired_region:
            cities.append(city)

    return cities

def getKeyboardTypes():
    kbdfile = open(constants.kbd_data_file, 'r')
    lines = kbdfile.readlines()
    kbdfile.close()

    lines = map(lambda x: x.strip('\n').split('/'), lines)

    kbdtypes = []
    for kbdtype in lines:
        if kbdtype[0] not in kbdtypes:
            kbdtypes.append(kbdtype[0])

    return kbdtypes

def getKeymaps(kbdtype):
    kbdfile = open(constants.kbd_data_file, 'r')
    lines = kbdfile.readlines()
    kbdfile.close()

    lines = map(lambda x: x.strip('\n').split('/'), lines)

    keymaps = []
    for keymap in lines:
        if keymap[0] == kbdtype:
            keymapname = "/".join(keymap[1:])
            keymaps.append(keymapname)

    return keymaps

def makeHumanList(list):
    if len(list) == 0:
        return ""
    elif len(list) == 1:
        return list[0]
    else:
        start = ", ".join(list[:len(list) - 1])
        start += ", and %s" % list[len(list) - 1]
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
