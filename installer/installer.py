#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Main script
#
# written by Mark Nijmeijer
# Copyright XenSource Inc. 2006

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
            screen.drawRootText(0, 1, "Copyright XenSource, Inc. 2006")
    
            entries = [ 
                    ' * Install %s Managed Host' % PRODUCT_BRAND,
                    ' * P2V (convert existing OS on this host into a VM template)'
                     ]
            (button, entry) = ListboxChoiceWindow(screen,
                            "Make a choice",
                            """Select the install you want to perform:""",
                            entries,
                            ['Ok', 'Exit and reboot'], width=70)
            if button == 'ok' or button == None:
                if entry == 0:
                     rc = os.system("/opt/xensource/clean-installer/clean-installer --clog /dev/tty3")
                     if rc == 0: 
                         os.system("reboot")
                         sys.exit(0)
                     else:
                         sys.exit(rc)
                elif entry == 1:
                    rc = os.system("/opt/xensource/clean-installer/p2v.py")
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
    
