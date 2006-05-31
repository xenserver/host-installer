#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Main script
#
# written by Andrew Peace & Mark Nijmeijer
# Copyright XenSource Inc. 2006

import p2v_tui
import p2v_uicontroller
import sys
import findroot
import p2v_backend
import xelogging
import os

from p2v_error import P2VError, P2VPasswordError
from snack import *


ui_package = p2v_tui

def main():
    os.environ['LVM_SYSTEM_DIR'] = '/tmp'
    ui_package.init_ui()
    fd = open('/dev/tty3', "w")
    xelogging.continuous_logs.append(fd)

    firstrun = True
    finished = False

    results = { 'ui-package': ui_package }

    
    while finished == False:
        if firstrun:
            seq = [ ui_package.welcome_screen,
                ui_package.os_install_screen,
                ui_package.target_screen,
                ui_package.get_root_password,
                ui_package.description_screen ]
        else:
            seq = [ ui_package.get_root_password ]
            
        try:
            rc = p2v_uicontroller.runUISequence(seq, results)
        
            if rc != -1:
                rc = p2v_backend.perform_P2V(results)
            else:
                ui_package.end_ui()
                sys.exit(1)
        
            if rc == 0: 
                seq = [ui_package.finish_screen ]
                rc = p2v_uicontroller.runUISequence(seq, results)
            else:
                seq = [ui_package.failed_screen ]
                rc = p2v_uicontroller.runUISequence(seq, results)
            ui_package.end_ui()
            p2v_backend.print_results(results)
            finished = True

        except P2VPasswordError, e:
            ButtonChoiceWindow(p2v_tui.screen, "P2V Failed", "Invalid password, please enter a valid password", ['Ok'], width = 60)
            finished = False
            firstrun = False

        except P2VError, e:
            global screen
            ButtonChoiceWindow(p2v_tui.screen, "P2V Failed", "P2V operation failed : \n%s" % e, ['Ok'], width = 60)
            ui_package.end_ui()
            print "P2V Failed: %s" % e
            xelogging.log(e)
            xelogging.writeLog("/tmp/install-log")
            sys.exit(2)
        except Exception, e:
            # clean up the screen
            ui_package.end_ui()
            print "P2V Failed: %s" % e
            xelogging.log(e)
            xelogging.writeLog("/tmp/install-log")
            sys.exit(1)

    #eject CD if success
    p2v_backend.ejectCD()

if __name__ == "__main__":
    main()
2
