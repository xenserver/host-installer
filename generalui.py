# SPDX-License-Identifier: GPL-2.0-only

import os
import time
import datetime
import constants

def getTimeZoneRegions():
    tzf = open(constants.timezone_data_file)
    lines = tzf.readlines()
    tzf.close()

    lines = [x.strip('\n').split('/') for x in lines]

    regions = []
    for zone in lines:
        if zone[0] not in regions:
            regions.append(zone[0])

    return regions

def getTimeZoneCities(desired_region):
    tzf = open(constants.timezone_data_file)
    lines = tzf.readlines()
    tzf.close()

    lines = [x.strip('\n').split('/') for x in lines]

    cities = []
    for zone in lines:
        city = "/".join(zone[1:])
        if zone[0] == desired_region:
            cities.append(city)

    return cities

def getKeymaps():
    kbdfile = open(constants.kbd_data_file, 'r')
    lines = kbdfile.readlines()
    kbdfile.close()

    lines = [x.strip('\n').split('/') for x in lines]

    keymaps = []
    for keymap in lines:
        keymaps.append( ("[%s] %s" % (keymap[0], keymap[1]), keymap[1]) )

    def cmp_us_uk_first(a, b):
        (a1, a2) = a
        (b1, b2) = b
        if a2 == 'us' and b2 == 'uk':
            return -1
        elif a2 == 'uk' and b2 == 'us':
            return 1
        elif a2 == 'us' or a2 == 'uk':
            return -1
        elif b2 == 'us' or b2 == 'uk':
            return 1
        else:
            return cmp("%s %s" % a, "%s %s" % b)
    keymaps.sort(cmp_us_uk_first)

    return keymaps

def makeHumanList(list):
    if len(list) == 0:
        return ""
    elif len(list) == 1:
        return list[0]
    elif len(list) == 2:
        return "%s and %s" % (list[0], list[1])
    else:
        start = ", ".join(list[:len(list) - 1])
        start += " and %s" % list[len(list) - 1]
        return start

# Hack to get the time in a different timezone
def translateDateTime(dt, tzname):
    return dt

    # TODO - tzset not compiled into Python for uclibc

    localtz = "utc"
    if 'TZ' in os.environ:
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
