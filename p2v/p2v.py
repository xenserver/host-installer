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
import os

from p2v_error import P2VError
from snack import *


ui_package = p2v_tui

def main():
    os.environ['LVM_SYSTEM_DIR'] = '/tmp'
    ui_package.init_ui()

    results = { 'ui-package': ui_package }

    seq = [ ui_package.welcome_screen,
            ui_package.os_install_screen,
            ui_package.target_screen,
            ui_package.get_root_password,
            ui_package.description_screen ]
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

    except P2VError, e:
        global screen
        ButtonChoiceWindow(p2v_tui.screen, "P2V Failed", "P2V operation failed : \n%s" % e, ['Ok'], width = 60)
        ui_package.end_ui()
        print "P2V Failed: %s" % e
        sys.exit(0)
    except Exception, e:
        # clean up the screen
        ui_package.end_ui()
        raise

if __name__ == "__main__":
    main()
2
