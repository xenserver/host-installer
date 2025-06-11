#!/usr/bin/env python3

# SPDX-License-Identifier: GPL-2.0-only

import re
import os
import itertools
import json
from json.decoder import JSONDecodeError
import util
from xcp import logger

class PciDevice:
    def __init__(self, pci_id, devclass, vendor_id, device_id, driver):
        self.pci_id = pci_id
        self.devclass = devclass
        self.vendor_id = vendor_id
        self.device_id = device_id
        self.driver = driver

    def getLongDevLabel(self):
        return "%s | %s %s | %s" % (self.pci_id, self.vendor_id, self.device_id, self.driver)

    def getHumanDevLabel(self):
        return "%s %s" % (self.vendor_id, self.device_id)

    def __repr__(self):
        return self.getHumanDevLabel()

class DriverVariant:
    def __init__(self, drvname, vartype, varinfo):
        self.drvname = drvname
        self.oemtype = vartype
        self.version = varinfo["version"]
        self.hardware_present = varinfo["hardware_present"]
        self.priority = varinfo["priority"]
        self.status = varinfo["status"]

    def __repr__(self):
        return f"Driver: {self.drvname}-{self.oemtype} {self.version} {self.status}"

    def getHumanVariantLabel(self):
        template = "Driver: {name}-{oemtype} {version} {status}"
        return template.format(name=self.drvname, oemtype=self.oemtype,
                               version=self.version,
                               status=self.status)

    def getHardwarePresentText(self):
        return "Yes" if self.hardware_present else "No"

    def getPriorityText(self):
        return str(self.priority)

class Driver:
    def __init__(self, drvname, drvinfo=None):
        self.drvname = drvname
        self.type = ""
        self.friendly_name = ""
        self.description = ""
        self.info = ""
        self.selected = None
        self.active = None
        self.variants = []
        self.devices = []
        if drvinfo:
            self.type = drvinfo["type"]
            self.friendly_name = drvinfo["friendly_name"]
            self.description = drvinfo["description"]
            self.info = drvinfo["info"]
            self.selected = drvinfo["selected"]
            self.active = drvinfo["active"]
            for vartype, varinfo in drvinfo["variants"].items():
                self.variants.append(DriverVariant(drvname, vartype, varinfo))
            self.variants.sort(key=lambda v: v.oemtype)

    @classmethod
    def cloneDriver(self, driver):
        d = self(driver.drvname)
        d.type = driver.type
        d.friendly_name = driver.friendly_name
        d.description = driver.description
        d.info = driver.info
        d.selected = driver.selected
        d.active = driver.active
        return d

    def __repr__(self):
        return "<driver: %s (%s)>" % (self.friendly_name, self.description)

    def setDeviceList(self, devices):
        self.devices = devices

    def getHumanDriverLabel(self):
        return f"{self.friendly_name} {self.info}"

    def getHumanDeviceLabel(self):
        labels = []
        template = "{device}"
        for device in self.devices:
            labels.append(template.format(device=device))
        return labels

    def getVersion(self):
        if len(self.variants) == 0:
            return "unknown"
        return self.variants[0].version

    def getDriversVariants(self):
        variants = []
        template = "{description} variant: {vartype}"
        for variant in self.variants:
            label = template.format(description=self.description, vartype=variant.oemtype)
            variants.append((label, variant))
        return variants

    def selectDefaultVariant(self):
        variant = None
        l = [float(v.priority) for v in self.variants]
        if len(l) > 0:
            idx = l.index(max(l))
            variant = self.variants[idx]
        return variant

    def getSelectedText(self):
        if self.selected != None:
            return self.selected
        return "N/A"

    def getActiveText(self):
        if self.active != None:
            return self.active
        return "N/A"

def readPciDriver(pci_id):
    driver_path = f"/sys/bus/pci/devices/{pci_id}/driver"
    if os.path.exists(driver_path):
        driver_name = os.path.basename(os.path.realpath(driver_path))
        return driver_name
    # some devices like ACPI, PCI bridge
    return None

def filterDeviceRev(pci_device):
    filtered_text = re.sub(r'\(rev\s+\w+\)', '', pci_device).strip()
    return filtered_text

def getDeviceDriverMap(pci_dev_list):
    device_driver_map = {}
    for pci_dev in pci_dev_list:
        driver = pci_dev.driver
        if driver in device_driver_map:
            l = device_driver_map[driver]
            if pci_dev.getHumanDevLabel() not in l:
                l.append(pci_dev.getHumanDevLabel())
            device_driver_map[driver] = l
        else:
            device_driver_map[driver] = [pci_dev.getHumanDevLabel()]
    return device_driver_map

def parsePCIData(pcilist):
    pci_dev_list = []
    expression = r'''
        ^
        (?P<address>\S+)             # PCI address (0000:00:00.0)
        \s+
        "(?P<class>[^"]*)"           # Device class (Host bridge)
        \s+
        "(?P<vendor>[^"]*)"          # Vendor (Intel Corporation)
        \s+
        "(?P<device>[^"]*)"          # Device name (Device 1234)
        \s*
        (?:-(?P<revision>\S+))?      # Optional revision (-r06)
        \s*
        (?: "(?P<subvendor>[^"]*)")? # Optional subvendor (Dell)
        \s*
        (?: "(?P<subdevice>[^"]*)")? # Optional subdevice (Device abcd)
        $
    '''
    pattern = re.compile(expression, re.VERBOSE | re.MULTILINE)
    for device in pcilist.split("\n"):
        for match in pattern.finditer(device):
            pci_info = match.groupdict()
            pci_slot = pci_info["address"]
            devclass = pci_info["class"]
            vendor_id = pci_info["vendor"]
            device_id = filterDeviceRev(pci_info["device"])
            rev = pci_info["revision"]

            driver = readPciDriver(pci_slot)
            if driver:
                pci_dev = PciDevice(pci_slot, devclass, vendor_id, device_id, driver)
                pci_dev_list.append(pci_dev)
    return getDeviceDriverMap(pci_dev_list)

def parseDMVJsonData(dmvlist, device_driver_map):
    drivers = []
    for name, info in dmvlist.items():
        drivers.append(Driver(name, info))
    drivers.sort(key=lambda e: e.type)

    for drvname, devlist in device_driver_map.items():
        for driver in drivers:
            if driver.drvname == drvname:
                driver.setDeviceList(devlist)
    return drivers

def getHardwarePresentDrivers(drivers, name=None):
    hw_present_drivers = []
    for d in drivers:
        interest = True
        if name != None:
            if d.drvname != name:
                interest = False
        if interest:
            driver = Driver.cloneDriver(d)
            driver.variants = list(filter(lambda x:x.hardware_present, d.variants))
            driver.setDeviceList(d.devices)
            if len(driver.variants) > 0:
                hw_present_drivers.append(driver)
    return hw_present_drivers

def getHardwarePresentDriver(drivers, name):
    drivers = getHardwarePresentDrivers(drivers, name)
    if len(drivers) > 0:
        return drivers[0]
    return None

def chooseDefaultDriverVariants(drivers):
    variants = []
    for d in drivers:
        v = d.selectDefaultVariant()
        if v:
            variants.append(v)
    return variants

def queryMultipleVariants(context):
    return context

def querySingleVariant(context):
    return context

def queryDriversOrVariant(context):
    if isinstance(context, Driver):
        return ("drivers", context)
    elif isinstance(context, list):
        return ("variants", queryMultipleVariants(context))
    elif isinstance(context, DriverVariant):
        return ("variant", querySingleVariant(context))
    return ("unknown", None)

def sameDriverMultiVariantsSelected(variants):
    for drvname, group in itertools.groupby(variants, lambda x: x.drvname):
        if len(list(group)) > 1:
            return (True, drvname)
    return (False, "")

def getDriverVariantByName(drivers, drvname, oemtype):
    for d in drivers:
        if d.drvname == drvname:
            for v in d.variants:
                if v.oemtype == oemtype:
                    return v
    return None

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
        self.drivers = parseDMVJsonData(dmvlist, hardware_info)
        self.hw_present_drivers = getHardwarePresentDrivers(self.drivers)

    def getDriversData(self):
        return self.drivers

    def getHardwarePresentDrivers(self):
        return self.hw_present_drivers

    def getHardwarePresentDriver(self, drvname):
        return getHardwarePresentDriver(self.hw_present_drivers, drvname)

    def queryDriversOrVariant(self, context):
        return queryDriversOrVariant(context)

    def getDriverVariantByName(self, drvname, oemtype):
        return getDriverVariantByName(self.drivers, drvname, oemtype)

    def sameDriverMultiVariantsSelected(self, variants):
        return sameDriverMultiVariantsSelected(variants)

    def chooseDefaultDriverVariants(self, drivers = None):
        if not drivers:
            drivers = self.hw_present_drivers
        return chooseDefaultDriverVariants(drivers)

    def selectSingleDriverVariant(self, driver_name, variant_name):
        cmdparams = ['driver-tool', '-s', '-n', driver_name, '-v', variant_name]
        rc, out = util.runCmd2(cmdparams, with_stdout=True)
        if rc != 0:
            return False

        util.runCmd2(['modprobe', '-r', driver_name], with_stdout=True)

        rc, out = util.runCmd2(['modprobe', driver_name], with_stdout=True)
        if rc != 0:
            return False
        return True

    def selectMultiDriverVariants(self, choices):
        failures = []
        for driver_name, variant_name in choices:
            ret = self.selectSingleDriverVariant(driver_name, variant_name)
            if not ret:
                failures.append((driver_name, variant_name))
        return failures

def getDMVList():
    rc, out = util.runCmd2(['driver-tool', '-l'], with_stdout=True)
    if rc != 0:
        return None
    return out

def getHardwareList():
    rc, out = util.runCmd2(['lspci', '-mm', '-D'], with_stdout=True)
    if rc != 0:
        return None
    return parsePCIData(out)

def getDMVData():
    dmvlist = getDMVList()
    if not dmvlist:
        raise RuntimeError("Failed to execute 'driver-tool -l'")
    devlist = getHardwareList()
    if not devlist:
        raise RuntimeError("Failed to execute 'lspci'")
    logger.log(devlist)
    return DriverMultiVersionData(dmvlist, devlist)
