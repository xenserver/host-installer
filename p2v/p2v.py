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

import tui
import p2v_tui
import uicontroller
import p2v_answerfile
import sys
import findroot
import p2v_backend
import xelogging
import os
import generalui
import constants
import traceback

from snack import *
from getopt import getopt, GetoptError
from version import *
from uicontroller import Step

def closeClogs(clog_fds):
    # close continuous logs:
    for logfd in clog_fds:
        try:
            xelogging.continuous_logs.remove(logfd)
        except:
            pass
        logfd.close()


def main():
    clog_fds = []

    try:
        (opts, _) = getopt(
            sys.argv[1:], "", [ "answerfile=", "clog=",
                "verbose-answerfile="]
            )
    except GetoptError:
        print "This program takes no arguments."
        return 2

    answerfile = None
    ui = p2v_tui
    for (opt, val) in opts:
        if opt == "--answerfile":
            answerfile = val
        if opt == "--verbose-answerfile":
            answerfile = val
            ui = None
            xelogging.continuous_logs.append(sys.stdout)
        if opt == "--clog":
            try:
                fd = open(val, "w")
                clog_fds.append(fd)
                xelogging.continuous_logs.append(fd)
            except:
                print "Error adding continuous log %s." % val
 
    os.environ['LVM_SYSTEM_DIR'] = '/tmp'
    if ui:
        tui.init_ui()

    try:
        if answerfile:
            results = p2v_answerfile.processAnswerfile(answerfile)
        else:
            seq = [
                Step(ui.welcome_screen),
                Step(ui.requireNetworking),
                Step(ui.get_target),
                Step(ui.select_sr),
                Step(ui.os_install_screen),
                Step(ui.size_screen),
                Step(ui.confirm_screen),
                ]
            
            results = {}
            rc = uicontroller.runSequence(seq, results)
        
            if rc == uicontroller.EXIT:
                tui.end_ui()
                closeClogs(clog_fds)
                return constants.EXIT_USER_CANCEL

        p2v_backend.rio_p2v(results, ui != None)
        
        xelogging.log("P2V successfully completed.")
        xelogging.writeLog("/tmp/p2v-log")

        if ui:
            ui.finish_screen()
            tui.end_ui()

    except Exception, e:
        ex = sys.exc_info()
        err = str.join("", traceback.format_exception(*ex))
        xelogging.log("P2V FAILED.")
        xelogging.log("A fatal exception occurred:")
        xelogging.log(err)

        # write logs where possible:
        xelogging.writeLog("/tmp/p2v-log")

        # display a dialog if UI is available:
        if ui:
            tui.exn_error_dialog("p2v-log", False)

        xelogging.collectLogs('/tmp')
        closeClogs(clog_fds)

        # clean up the screen
        if ui:
            tui.end_ui()
        return constants.EXIT_ERROR

    #eject CD if success
    p2v_backend.ejectCD()
    closeClogs(clog_fds)
    return 0

if __name__ == "__main__":
    sys.exit(main())
