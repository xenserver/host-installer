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
