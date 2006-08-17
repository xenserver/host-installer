#!/usr/bin/env python
# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Main script
#
# written by Mark Nijmeijer

from snack import *
import commands
import sys
import os
import p2v
from version import *

screen = None

def run_command(cmd):
    rc, out = commands.getstatusoutput(cmd)
    return (rc, out)

def main():
    global screen
    
    #disable all kernel printing
    run_command("echo 1 > /proc/sys/kernel/printk")
    
    try:
        
        while True:
            screen = SnackScreen()
            screen.drawRootText(0, 0, "Welcome to the %s Installer - Version %s (#%s)" % (PRODUCT_BRAND, PRODUCT_VERSION, BUILD_NUMBER))
            screen.drawRootText(0, 1, "Copyright (c) %s %s" % (COPYRIGHT_YEARS, COMPANY_NAME_LEGAL))
    
            entries = [ 
                    ' * Install %s Managed Host' % PRODUCT_BRAND,
                    ' * Upgrade %s Managed Host' % PRODUCT_BRAND,
                    ' * P2V (convert existing OS on this host into a VM template)'
                     ]
            (button, entry) = ListboxChoiceWindow(screen,
                            "Make a choice",
                            """Select the install you want to perform:""",
                            entries,
                            ['Ok', 'Exit and reboot'], width=70)
            if button == 'ok' or button == None:
                if entry == 0:
                     rc = os.system("/opt/xensource/installer/clean-installer --clog /dev/tty3")
                     if rc == 0: 
                         os.system("reboot")
                         sys.exit(0)
                     else:
                         sys.exit(rc)
                elif entry == 1:
                     rc = os.system("/opt/xensource/installer/clean-installer --upgrade --upgrade-answerdev /dev/sda1 --clog /dev/tty3")
                     if rc == 0: 
                         os.system("reboot")
                         sys.exit(0)
                     else:
                         sys.exit(rc)
                elif entry == 2:
                    rc = os.system("/opt/xensource/installer/p2v.py")
                    if (rc != 0):
                        os.system("reboot")
                        sys.exit(0)

            else:
                screen.finish()
                os.system("reboot")
                sys.exit(0)
    except Exception, e:
        screen.finish()
        raise
        
if __name__ == "__main__":
    main()
    
