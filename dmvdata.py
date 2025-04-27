#!/usr/bin/env python3

# SPDX-License-Identifier: GPL-2.0-only

import json
from json.decoder import JSONDecodeError
import util
import dmvutil
from xcp import logger

class DriverMultiVersionData:
    def __init__(self, dmv_jsondata, hardware_info):
        self.dmv_jsondata = dmv_jsondata
        self.device_driver_map = hardware_info

        dmvjson = None
        dmvlist = None
        try:
            dmvjson = json.loads(dmv_jsondata)
        except JSONDecodeError as e:
            raise e
        if not "drivers" in dmvjson:
            raise RuntimeError("Invalid output from driver-tool")
        dmvlist = dmvjson["drivers"]
        self.drivers = dmvutil.parseDMVJsonData(dmvlist, hardware_info)
        self.hw_present_drivers = dmvutil.getHardwarePresentDrivers(self.drivers)

    def getDriversData(self):
        return self.drivers

    def getHardwarePresentDrivers(self):
        return self.hw_present_drivers

    def getHardwarePresentDriver(self, drvname):
        return dmvutil.getHardwarePresentDriver(self.hw_present_drivers, drvname)

    def queryDriversOrVariant(self, context):
        return dmvutil.queryDriversOrVariant(context)

    def sameDriverMultiVariantsSelected(self, variants):
        return dmvutil.sameDriverMultiVariantsSelected(variants)

    def chooseDefaultDriverVariants(self, drivers = None):
        if not drivers:
            drivers = self.hw_present_drivers
        return dmvutil.chooseDefaultDriverVariants(drivers)

    def selectSingleDriverVariant(self, driver_name, variant_name):
        cmdstring = "driver-tool|-s|-n|%s|-v|%s" % (driver_name, variant_name)
        rc, out = util.runCmd2(cmdstring.split('|'), with_stdout=True)
        if rc != 0:
            logger.log(out)
            return False

        rc, out = util.runCmd2(['rmmod', driver_name], with_stdout=True)
        if rc != 0:
            # only log the output but ignore the error
            logger.log(out)

        rc, out = util.runCmd2(['modprobe', driver_name], with_stdout=True)
        if rc != 0:
            logger.log(out)
            return False
        return True

    def selectMultiDriverVariants(self, choices):
        failures = []
        for driver_name, variant_name in choices:
            ret = self.selectSingleDriverVariant(driver_name, variant_name)
            if not ret:
                failures.append((driver_name, variant_name))
        return failures

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
    return DriverMultiVersionData(getMockDMVList(), getMockHardwareList())

def getRealDMVList():
    rc, out = util.runCmd2(['driver-tool', '-l'], with_stdout=True)
    if rc != 0:
        logger.log(out)
        return None
    return out

def getRealHardwareList():
    rc, out = util.runCmd2(['lspci'], with_stdout=True)
    if rc != 0:
        logger.log(out)
        return None
    return dmvutil.parsePCIData(out)

def getRealDMVData():
    dmvlist = getRealDMVList()
    if not dmvlist:
        raise RuntimeError("Failed to execute 'driver-tool -l'")
    devlist = getRealHardwareList()
    if not devlist:
        raise RuntimeError("Failed to execute 'lspci'")
    logger.log(devlist)
    return DriverMultiVersionData(dmvlist, devlist)
