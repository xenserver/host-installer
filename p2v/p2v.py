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
from version import *
from uicontroller import Step


def main(args):
    tui.init_ui()
    go(args, p2v_tui)
    tui.end_ui()

def go(args, use_ui):
    ui = None
    if use_ui != None:
        ui = p2v_tui

    answerfile = None
    for (opt, val) in args.items():
        if opt in ["--answerfile", "--rt_answerfile"]:
            answerfile = val
 
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
                return constants.EXIT_USER_CANCEL

        p2v_backend.rio_p2v(results, ui != None)

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

        return constants.EXIT_ERROR

    xelogging.log("P2V successfully completed.")
    xelogging.writeLog("/tmp/p2v-log")

    if ui:
        ui.finish_screen()

    #eject CD if success
    p2v_backend.ejectCD()
    return constants.EXIT_OK

if __name__ == "__main__":
    sys.exit(main(util.splitArgs(sys.argv[1:])))
