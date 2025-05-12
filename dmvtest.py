#!/usr/bin/env python3

# SPDX-License-Identifier: GPL-2.0-only

import dmvdata

def colorTextOutput(color, text):
    COLORS = {
        'black': '\033[30m',
        'red': '\033[31m',
        'red_bold': '\033[1;31m',
        'green': '\033[32m',
        'green_bold': '\033[1;32m',
        'yellow': '\033[33m',
        'yellow_bold': '\033[1;33m',
        'blue': '\033[34m',
        'blue_bold': '\033[1;34m',
        'magenta': '\033[35m',
        'magenta_bold': '\033[1;35m',
        'cyan': '\033[36m',
        'cyan_bold': '\033[1;36m',
        'white': '\033[37m',
        'white_bold': '\033[1;37m',
        'reset': '\033[0m'
    }
    print(f"{'%s'}%s{COLORS['reset']}" % (COLORS[color], text))

if __name__ == '__main__':
    mockdata = dmvdata.getMockDMVData()
    colorTextOutput("red_bold", "===== dump mock dmv data =====")
    drivers = mockdata.getDriversData()
    for d in drivers:
        print(d.getHumanDriverLabel())
        print(d.getHumanDeviceLabel())
        for variant in d.variants:
            print(variant)
    print("")

    colorTextOutput("blue_bold", "===== hardware present =====")
    hw_present_drivers = mockdata.getHardwarePresentDrivers()
    for d in hw_present_drivers:
        print(d.getHumanDriverLabel())
        print(d.getHumanDeviceLabel())
        print(d.getVersion())
        for variant in d.variants:
            print(variant)
    print("")

    colorTextOutput("green_bold", "===== igb driver =====")
    d = mockdata.getHardwarePresentDriver("igb")
    print(d.getHumanDriverLabel())
    print(d.getHumanDeviceLabel())
    for variant in d.variants:
        print(variant)
        print(variant.drvname)
        print(variant.oemtype)
        itemtype, _ = mockdata.queryDriversOrVariant(variant)
        print("===> %s %s" % (itemtype, variant.getHumanVariantLabel()))
    print("")

    colorTextOutput("yellow_bold", "===== ice driver =====")
    d = mockdata.getHardwarePresentDriver("ice")
    got, drvname = mockdata.sameDriverMultiVariantsSelected(d.variants)
    if got:
        print("sameDriverMultiVariantsSelected")
        print(drvname)
    print("")

    colorTextOutput("magenta_bold", "===== default selection =====")
    variants = mockdata.chooseDefaultDriverVariants(hw_present_drivers)
    print(variants)
    for variant in variants:
        print(variant)
        itemtype, _ = mockdata.queryDriversOrVariant(variant)
        print("===> %s %s" % (itemtype, variant.getHumanVariantLabel()))
    d = mockdata.getHardwarePresentDriver("fnic")
    v = d.variants[0]
    if v in variants:
        print("got")
    print("")

    colorTextOutput("red_bold", "===== get a variant =====")
    variant = mockdata.getDriverVariantByName("igb", "dell")
    print(variant)
    print("")

    colorTextOutput("white_bold", "===== hardware list =====")
    hardware_list = dmvdata.getRealHardwareList()
    print(hardware_list)
    print("")

    realdata = dmvdata.getRealDMVData()
    colorTextOutput("cyan_bold", "===== dump real dmv data =====")
    drivers = realdata.getDriversData()
    for d in drivers:
        print(d.getHumanDriverLabel())
        print(d.getHumanDeviceLabel())
        for variant in d.variants:
            print(variant)
    print("")
