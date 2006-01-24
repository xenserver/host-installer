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

ui_package = p2v_tui

def main():
    ui_package.init_ui()

    results = { 'ui-package': ui_package }

    seq = [ ui_package.welcome_screen,
            ui_package.target_screen,
            ui_package.os_install_screen ]
    rc = p2v_uicontroller.runUISequence(seq, results)
    
    if rc != -1:
        rc = p2v_backend.perform_P2V(results)
    else:
        sys.exit(1)
        
    #ui_package.redraw_screen()

#    backend.performStage1Install(results)

    #seq = [ ui_package.get_root_password,
    #        ui_package.determine_basic_network_config,
    #        ui_package.need_manual_hostname,
    #        ui_package.installation_complete ]
    #seq = [ ui_package.installation_complete ]

    #uicontroller.runUISequence(seq, results)
    
    if rc == 0: 
        seq = [ui_package.finish_screen ]
        rc = p2v_uicontroller.runUISequence(seq, results)
    else:
        seq = [ui_package.failed_screen ]
        rc = p2v_uicontroller.runUISequence(seq, results)
    ui_package.end_ui()
    p2v_backend.print_results(results)

if __name__ == "__main__":
    main()
2
