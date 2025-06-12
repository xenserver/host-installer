#!/usr/bin/env python3

# SPDX-License-Identifier: GPL-2.0-only

import dmvutil

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

def getMockHardwareList():
    device_driver_map = {
        "igb": ["Intel I350 Gigabit Ethernet Controller",
                "Intel 82575 and 82576 Gigabit Ethernet controller"],
        "ice": ["Intel E810 Ethernet Controller"],
        "fnic": ["Cisco UCS VIC Fibre Channel over Ethernet HBA"]
    }
    return device_driver_map

def getMockDMVList():
    jsondata = '''
    {
        "protocol": {
            "version": 0.1
        },
        "operation": {
            "reboot": false
        },
        "drivers": {
            "igb": {
                "type": "network",
                "friendly_name": "Intel Gigabit Ethernet Controller",
                "description": "intel-igb",
                "info": "igb",
                "selected": null,
                "active": null,
                "variants": {
                    "generic": {
                        "version": "5.17.5",
                        "hardware_present": true,
                        "priority": 30,
                        "status": "production"
                    },
                    "dell": {
                        "version": "5.17.5",
                        "hardware_present": false,
                        "priority": 40,
                        "status": "production"
                    }
                }
            },
            "ice": {
                "type": "network",
                "friendly_name": "Intel E810 Series Devices Drivers",
                "description": "intel-ice",
                "info": "ice",
                "selected": "supermicro",
                "active": null,
                "variants": {
                    "generic": {
                        "version": "1.15.5",
                        "hardware_present": true,
                        "priority": 50,
                        "status": "production"
                    },
                    "supermicro": {
                        "version": "1.15.5",
                        "hardware_present": true,
                        "priority": 30,
                        "status": "production"
                    }
                }
            },
            "fnic": {
                "type": "storage",
                "friendly_name": "Cisco UCS VIC Fibre Channel",
                "description": "cisco-fnic",
                "info": "fnic",
                "selected": "generic",
                "active": null,
                "variants": {
                    "generic": {
                        "version": "3.18.2",
                        "hardware_present": true,
                        "priority": 50,
                        "status": "production"
                    } 
                }
            }
        }
    }
    '''
    return jsondata

def getMockDMVData():
    return dmvutil.DriverMultiVersionData(getMockDMVList(), getMockHardwareList())

if __name__ == '__main__':
    mockdata = getMockDMVData()
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
    hardware_list = dmvutil.getHardwareList()
    print(hardware_list)
    print("")

    realdata = dmvutil.getDMVData()
    colorTextOutput("cyan_bold", "===== dump real dmv data =====")
    drivers = realdata.getDriversData()
    for d in drivers:
        print(d.getHumanDriverLabel())
        print(d.getHumanDeviceLabel())
        for variant in d.variants:
            print(variant)
    print("")
