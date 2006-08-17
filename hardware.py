#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Hardware discovery tools
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import os
import version

# More of the hardware tools will be moved into here in future.

# module => module list
# if we discover x, actually load module_map[x]:
module_map = {
    # general:
    'mptscsih'     : ['mptspi', 'mptscsih'],
    'i810-tco'     : [],
    'usb-uhci'     : [],
    'ide-scsi'     : ['ide-generic'],
    'piix'         : ['ata-piix', 'piix'],

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
    }


###
# Module loading and order retrieval

__MODULE_ORDER_FILE__ = "/tmp/module-order"

class ModuleOrderUnknownException(Exception):
    pass

def getModuleOrder():
    def allKoFiles(directory):
        kofiles = []
        items = os.listdir(directory)
        for item in items:
            if item.endswith(".ko"):
                kofiles.append(item)
        itemabs = os.path.join(directory, item)
        if os.path.isdir(itemabs):
	    kofiles.extend(allKoFiles(itemabs))

        return kofiles

    try:
        all_modules = allKoFiles("/lib/modules/%s" % version.KERNEL_VERSION)
        all_modules = [x.replace(".ko", "") for x in all_modules]

        mo = open(__MODULE_ORDER_FILE__, 'r')
        lines = [x.strip() for x in mo]
        mo.close()

        modules = []
        for module in lines:
            if module in all_modules:
                modules.append(module)
            else:
                module = module.replace("-", "_")
                if module in all_modules:
                    modules.append(module)
        
        return modules
    except Exception, e:
        raise ModuleOrderUnknownException, e
