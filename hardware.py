#!/usr/bin/env python
# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Hardware discovery tools
#
# written by Andrew Peace

import os
import version
import constants
import xelogging
import util
import re

###
# Module loading

def module_present(module):
    mtmp = module.replace('-', '_')
    loaded_modules = []
    pm = open('/proc/modules', 'r')
    for line in pm:
        fields = line.split()
        loaded_modules.append(fields[0].replace('-', '_'))
    pm.close()

    return mtmp in loaded_modules

def modprobe(module, params = ""):
    xelogging.log("Loading module %s" % " ".join([module, params]))
    rc = util.runCmd2(['modprobe', module, params])
    if rc != 0:
        xelogging.log("(Failed.)")

    return rc

def module_file_uname(module):
    rc, out = util.runCmd2(['modinfo', module], with_stdout = True)
    if rc != 0:
        raise RuntimeError, "Error interrogating module"
    vermagics = filter(lambda x: x.startswith("vermagic:"), out.split("\n"))
    if len(vermagics) != 1:
        raise RuntimeError, "No version magic field for module %s" % module
    vermagic = vermagics[0]

    vermagic = vermagic[10:].strip()
    return vermagic.split(" ")[0]

def modprobe_file(module, params = "", name = None):
    INSMOD = '/sbin/insmod'

    # First use modinfo to find out what the dependants of the
    # module are and modprobe them:
    #
    # deps will initially look like 'depends:    x,y,z'
    rc, out = util.runCmd2(['modinfo', module], with_stdout = True)
    if rc != 0:
        raise RuntimeError, "Error interrogating module."
    [deps] = filter(lambda x: x.startswith("depends:"),
                    out.split("\n"))
    deps = deps[9:].strip()
    if deps != "":
        deps = deps.split(',')
        for dep in deps:
            if not module_present(dep):
                modprobe(dep)
    
    xelogging.log("Inserting module %s %s (%s)" %(module, params, name))
    rc = util.runCmd2([INSMOD, module, params])

    if rc != 0:
        xelogging.log("(Failed.)")

    return rc

################################################################################
# Functions to get characteristics of the host.  Can work in a VM too, to aid
# with developer testing.

def VTSupportEnabled():
    """ Checks if VT support is present.  Uses /sys/hypervisor to do so,
    expecting a single line in this file with a space separated list of 
    capabilities. """
    f = open(constants.HYPERVISOR_CAPS_FILE, 'r')
    caps = ""
    try:
        caps = f.readline()
    finally:
        f.close()

    return "hvm-3.0-x86_32" in caps.strip().split(" ")

def VM_getHostTotalMemoryKB():
    # Use /proc/meminfo to get this.  It has a MemFree entry with the value we
    # need.  The format is lines like this "XYZ:     123 kB".
    meminfo = {}

    f = open("/proc/meminfo", "r")
    try:
        for line in f:
            k, v = line.split(":")
            meminfo[k.strip()] = int(v.strip()[:-3])
    finally:
        f.close()

    return meminfo['MemTotal']

def PhysHost_getHostTotalMemoryKB():
    rc, mem = util.runCmd2([constants.XENINFO, 'host-total-mem'], with_stdout = True)
    assert rc == 0
    return int(mem.strip())

def VM_getSerialConfig():
    return ''

def PhysHost_getSerialConfig():
    rc, cmdline = util.runCmd2([constants.XENINFO, 'xen-commandline'], with_stdout = True)
    assert rc == 0
    m = re.match(r'.*(com\d=\S+)', cmdline)
    return m and m.group(1) or None

getHostTotalMemoryKB = PhysHost_getHostTotalMemoryKB
getSerialConfig = PhysHost_getSerialConfig
def useVMHardwareFunctions():
    global getHostTotalMemoryKB, getSerialConfig
    getHostTotalMemoryKB = VM_getHostTotalMemoryKB
    getSerialConfig = VM_getSerialConfig

def is_serialConsole(console):
    return console.startswith('hvc') or console.startswith('ttyS')

class SerialPort:
    def __init__(self, console):
        """Create instance from Xen console parameter (e.g. com1=115200,8n1)"""
        self.dev = 'hvc0'
        self.id = 0
        self.port = 'com1'
        self.baud = '9600'
        self.data = '8'
        self.parity = 'n'
        self.stop = '1'
        self.term = 'vt102'

        m = re.match(r'(com\d+)=(\d+)(?:/\d+)?(?:,(\d)(.)?(\d)?)?', console)
        if m:
            self.port = m.group(1)
            self.baud = m.group(2)
            if m.group(3): self.data = m.group(3)
            if m.group(4): self.parity = m.group(4)
            if m.group(5): self.stop = m.group(5)

    def __repr__(self):
        return "<SerialPort: %s>" % self.xenFmt()

    def kernelFmt(self):
        return self.dev

    def xenFmt(self):
        return "%s=%s,%s%s%s" % (self.port, self.baud, self.data, self.parity, self.stop)
