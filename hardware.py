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

# More of the hardware tools will be moved into here in future.

# module => module list
# if we discover x, actually load module_map[x]:
module_map = {
    # general:
    'mptscsih'     : ['mptspi', 'mptscsih'],
    'i810-tco'     : [],
    'usb-uhci'     : [],
    'ide-scsi'     : ['ide-generic'],
    'piix'         : ['ata-piix', 'piix', 'ide-generic'],

    # blacklist firewire as we don't support it and it confuses our networking
    # code:
    "ohci1394"     : [],
    "eth1394"      : [],

    # blacklist framebuffer drivers (we don't need them):
    "arcfb"        : [],
    "aty128fb"     : [],
    "atyfb"        : [],
    "radeonfb"     : [],
    "cirrusfb"     : [],
    "cyber2000fb"  : [],
    "cyblafb"      : [],
    "gx1fb"        : [],
    "hgafb"        : [],
    "i810fb"       : [],
    "intelfb"      : [],
    "kyrofb"       : [],
    "i2c-matroxfb" : [],
    "neofb"        : [],
    "nvidiafb"     : [],
    "pm2fb"        : [],
    "rivafb"       : [],
    "s1d13xxxfb"   : [],
    "savagefb"     : [],
    "sisfb"        : [],
    "sstfb"        : [],
    "tdfxfb"       : [],
    "tridentfb"    : [],
    "vfb"          : [],
    "vga16fb"      : [],

    # blacklist agp modules (we don't need them and they can cause compatibility issues):
    "ali-agp"      : [],
    "amd64-agp"    : [],
    "via-agp"      : [],
    "intel-agp"    : [],
    "sworks-agp"   : [],
    "sis-agp"      : [],
    "nvidia-agp"   : [],
    "ati-agp"      : [],
    "amd-k7-agp"   : [],
    "efficeon-agp" : [],
    }


###
# Module loading

def module_present(module):
    mtmp = module.replace('-', '_')
    pm = open('/proc/modules', 'r')
    loaded_modules = pm.readlines()
    pm.close()

    return mtmp in [x.replace('-', '_') for x in loaded_modules]

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
# These functions assume we're running on Xen.

_vt_support = None

def VTSupportEnabled():
    global _vt_support

    # get the answer and cache it if necessary:
    if _vt_support == None:
        assert os.path.exists(constants.XENINFO)
        rc, caps = util.runCmd2([constants.XENINFO, 'xen-caps'], with_stdout = True)
        assert rc == 0
        caps = caps.strip().split(" ")
        _vt_support = "hvm-3.0-x86_32" in caps
    return _vt_support

def getHostTotalMemoryKB():
    assert os.path.exists(constants.XENINFO)
    rc, mem = util.runCmd2([constants.XENINFO, 'host-total-mem'], with_stdout = True)
    assert rc == 0
    return int(mem.strip())

def getSerialConfig():
    assert os.path.exists(constants.XENINFO)
    rc, cmdline = util.runCmd2([constants.XENINFO, 'xen-commandline'], with_stdout = True)
    assert rc == 0
    m = re.match(r'.*(com\d=\S+)', cmdline)
    return m and m.group(1) or None

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
