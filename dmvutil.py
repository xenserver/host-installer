#!/usr/bin/env python3

# SPDX-License-Identifier: GPL-2.0-only

import re
import os

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
        return "<%s variant: %s (%s)>" % (self.drvname, self.oemtype, self.version)

    def getHumanVariantLabel(self):
        template = "Driver: {name}-{oemtype} {version} {status}"
        return template.format(name=self.drvname, oemtype=self.oemtype,
                               version=self.version,
                               status=self.status)

    def getHardwarePresentText(self):
        if self.hardware_present:
            return "Yes"
        return "No"

    def getPriorityText(self):
        return str(self.priority)

class Drivers:
    def __init__(self, drvname, drvinfo=None):
        def sortKey(e):
            return e.oemtype

        self.drvname = drvname
        self.type = ""
        self.friendly_name = ""
        self.description = ""
        self.info = ""
        self.selected = None
        self.active = None
        self.variants = []
        self.devices = []
        if drvinfo != None:
            self.type = drvinfo["type"]
            self.friendly_name = drvinfo["friendly_name"]
            self.description = drvinfo["description"]
            self.info = drvinfo["info"]
            self.selected = drvinfo["selected"]
            self.active = drvinfo["active"]
            for vartype, varinfo in drvinfo["variants"].items():
                self.variants.append(DriverVariant(drvname, vartype, varinfo))
            self.variants.sort(key=sortKey)

    def __repr__(self):
        return "<drivers: %s (%s)>" % (self.friendly_name, self.description)

    def setDeviceList(self, devices):
        self.devices = devices

    def getHumanDriverLabel(self):
        template = "{friendly_name} ({info})"
        return template.format(friendly_name=self.friendly_name, info=self.info)

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

    def selectVariantByDefault(self):
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

def filterDeviceRcv(pci_device):
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
    for device in pcilist.split("\n"):
        pattern = re.compile(
            r'^(?P<slot>\S+)\s+(?P<class>.+?):\s+(?P<vendor>.+?)\s+(?P<device>.+?)(?: \((?P<rev>\w+)\))?$')
        for match in pattern.finditer(device):
            pci_info = match.groupdict()
            pci_slot = pci_info["slot"]
            devclass = pci_info["class"]
            vendor_id = pci_info["vendor"]
            device_id = filterDeviceRcv(pci_info["device"])
            rev = pci_info["rev"]

            pci_id = "0000:" + pci_slot
            driver = readPciDriver(pci_id)
            if driver:
                pci_dev = PciDevice(pci_id, devclass, vendor_id, device_id, driver)
                pci_dev_list.append(pci_dev)
    return getDeviceDriverMap(pci_dev_list)

def parseDMVJsonData(dmvlist, device_driver_map):
    def sortKey(e):
        return e.type

    drivers = []
    for name, info in dmvlist.items():
        drivers.append(Drivers(name, info))
    drivers.sort(key=sortKey)

    for drvname, devlist in device_driver_map.items():
        for driver in drivers:
            if driver.drvname == drvname:
                driver.setDeviceList(devlist)
    return drivers

def cloneDriverWithoutVariants(olddrv, newdrv):
    newdrv.type = olddrv.type
    newdrv.friendly_name = olddrv.friendly_name
    newdrv.description = olddrv.description
    newdrv.info = olddrv.info
    newdrv.selected = olddrv.selected
    newdrv.active = olddrv.active

def getHardwarePresentDrivers(drivers):
    hw_present_drivers = []
    for d in drivers:
        driver = Drivers(d.drvname)
        cloneDriverWithoutVariants(d, driver)
        driver.variants = list(filter(lambda x:x.hardware_present, d.variants))
        driver.setDeviceList(d.devices)
        if len(driver.variants) > 0:
            hw_present_drivers.append(driver)
    return hw_present_drivers

def getHardwarePresentDriver(drivers, name):
    hw_present_drivers = None
    for d in drivers:
        if d.drvname == name:
            driver = Drivers(d.drvname)
            cloneDriverWithoutVariants(d, driver)
            driver.variants = list(filter(lambda x:x.hardware_present, d.variants))
            driver.setDeviceList(d.devices)
            if len(driver.variants) > 0:
                hw_present_drivers = driver
    return hw_present_drivers

def chooseDefaultDriverVariants(drivers):
    variants = []
    for d in drivers:
        v = d.selectVariantByDefault()
        if v != None:
            variants.append(v)
    return variants

def queryMultipleVariants(context):
    return context

def querySingleVariant(context):
    return context

def queryDriversOrVariant(context):
    if isinstance(context, Drivers):
        return ("drivers", context)
    elif isinstance(context, list):
        return ("variants", queryMultipleVariants(context))
    elif isinstance(context, DriverVariant):
        return ("variant", querySingleVariant(context))
    return ("unknown", None)

def sameDriverMultiVariantsSelected(variants):
    for i in range(0, len(variants)):
        item1 = variants[i]
        a = variants[i+1:len(variants)]
        for item2 in a:
            if item1.drvname == item2.drvname:
                return (True, item1.drvname)
    return (False, "")
