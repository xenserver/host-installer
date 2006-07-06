#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Main script
#
# written by Andrew Peace & Mark Nijmeijer
# Copyright XenSource Inc. 2006

import p2v_tui
import p2v_uicontroller
import p2v_answerfile_ui
import sys
import findroot
import p2v_backend
import xelogging
import os
import getopt

from p2v_error import P2VError, P2VPasswordError, P2VCliError
from snack import *
from getopt import getopt, GetoptError

ui_package = p2v_tui

def closeClogs(clog_fds):
    # close continuous logs:
    for logfd in clog_fds:
        try:
            xelogging.continuous_logs.remove(logfd)
        except:
            pass
        logfd.close()


def main():
    global ui_package
    clog_fds = []

    try:
        (opts, _) = getopt(sys.argv[1:],
                           "",
                           [ "answerfile=",
                            "clog="])
    except GetoptError:
        print "This program takes no arguments."
        sys.exit(1)

    for (opt, val) in opts:
        if opt == "--answerfile":
            #p2v_answerfile_ui.specifySubUI(ui_package)
            ui_package = p2v_answerfile_ui
            p2v_backend.specifyUI(ui_package)
            p2v_answerfile_ui.specifyAnswerFile(val)
        if opt == "--clog":
            try:
                fd = open(val, "w")
                clog_fds.append(fd)
                xelogging.continuous_logs.append(fd)
            except:
                print "Error adding continuous log %s." % val
 
    results = { 'ui-package': ui_package }

    os.environ['LVM_SYSTEM_DIR'] = '/tmp'
    ui_package.init_ui(results)

    firstrun = True
    finished = False
    
    while finished == False:
        if firstrun:
            seq = [ ui_package.welcome_screen,
                ui_package.os_install_screen,
                ui_package.description_screen,
                ui_package.size_screen,
                ui_package.target_screen,
                ui_package.get_root_password ]
        else:
            seq = [ 
                ui_package.target_screen,
                ui_package.get_root_password ]
            
        try:
            rc = p2v_uicontroller.runUISequence(seq, results)
        
            if rc != -1:
                rc = p2v_backend.perform_P2V(results)
            else:
                ui_package.end_ui()
                closeClogs(clog_fds)
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

        except (P2VPasswordError, P2VCliError), e:
            if ui_package == p2v_tui:
                ButtonChoiceWindow(p2v_tui.screen, "P2V Failed", "Invalid hostname and/or password. Please re-enter hostname and password information.", ['Ok'], width = 60)
            finished = False
            firstrun = False

        except P2VError, e:
            ui_package.end_ui()
            print "P2V Failed: %s" % e
            xelogging.log(e)
            xelogging.writeLog("/tmp/install-log")
            xelogging.collectLogs('/tmp')
            closeClogs(clog_fds)
            if ui_package == p2v_tui:
                ButtonChoiceWindow(p2v_tui.screen, "P2V Failed", "P2V operation failed : \n%s" % e, ['Ok'], width = 60)
            sys.exit(2)
        except Exception, e:
            # clean up the screen
            ui_package.end_ui()
            print "P2V Failed: %s" % e
            xelogging.log(e)
            xelogging.writeLog("/tmp/install-log")
            xelogging.collectLogs('/tmp')
            closeClogs(clog_fds)
            if ui_package == p2v_tui:
                ButtonChoiceWindow(p2v_tui.screen, "P2V Failed", "P2V operation failed : \n%s" % e, ['Ok'], width = 60)
            sys.exit(1)

    #eject CD if success
    p2v_backend.ejectCD()
    closeClogs(clog_fds)

if __name__ == "__main__":
    main()
