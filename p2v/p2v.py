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
# written by Andrew Peace & Mark Nijmeijer

import p2v_tui
import uicontroller
import p2v_answerfile_ui
import sys
import findroot
import p2v_backend
import xelogging
import os
import getopt
import generalui
import constants
import traceback

from p2v_error import P2VError, P2VPasswordError, P2VCliError
from snack import *
from getopt import getopt, GetoptError
from version import *

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
            seq = [
                ui_package.welcome_screen,
                (generalui.requireNetworking, (ui_package, )),
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
            rc = uicontroller.runUISequence(seq, results)

            if rc != -1 and rc != uicontroller.EXIT:
                rc = p2v_backend.perform_P2V(results)
            else:
                ui_package.end_ui()
                closeClogs(clog_fds)
                sys.exit(constants.EXIT_USER_CANCEL)
        
            if rc == 0:
                ui_package.finish_screen({})
            else:
                ui_package.failed_screen({})
            ui_package.end_ui()
            p2v_backend.print_results(results)
            finished = True

        except (P2VPasswordError, P2VCliError), e:
            ui_package.displayButtonChoiceWindow(p2v_tui.screen, "P2V Failed", str(e), ['Ok'], width = 60)
            finished = False
            firstrun = False

        except SystemExit: raise
        except Exception, e:
            xelogging.log(e)
            ex = sys.exc_info()
            err = str.join("", traceback.format_exception(*ex))
            xelogging.log(err)
            xelogging.writeLog("/tmp/install-log")
            xelogging.collectLogs('/tmp')
            closeClogs(clog_fds)
            # clean up the screen
            ui_package.displayButtonChoiceWindow(p2v_tui.screen, "P2V Failed", """P2V operation failed. Please contact a Technical Support Representative. Log files have been collected in /tmp.  

Diagnostic output from the P2V operation follows:
%s""" % (e), ['Ok'], width = 60)
            ui_package.end_ui()
            print "P2V Failed: %s" % e
            sys.exit(1)

    #eject CD if success
    p2v_backend.ejectCD()
    closeClogs(clog_fds)

if __name__ == "__main__":
    main()
