# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Text user interface functions
#
# written by Andrew Peace

from snack import *
from version import *
import snackutil
import pdb
import xelogging

screen = None

def init_ui():
    global screen
    screen = SnackScreen()
    screen.drawRootText(0, 0, "Welcome to %s - Version %s (#%s)" % (PRODUCT_BRAND, PRODUCT_VERSION, BUILD_NUMBER))
    screen.drawRootText(0, 1, "Copyright (c) %s %s" % (COPYRIGHT_YEARS, COMPANY_NAME_LEGAL))

def end_ui():
    global screen
    if screen:
        screen.finish()

def OKDialog(title, text, hasCancel = False):
    return snackutil.OKDialog(screen, title, text, hasCancel)

def error_dialog(exc, trace):
    if screen:
        exc_str = str(exc)

        # If the error has a string representation, make the text
        # more helpful by displaying it.
        if exc_str == "":
            text = "An error has occurred and the installation must be aborted.  The details of the error can be found in the installation log, which will be written to /tmp/install-log and /boot/install-log on your hard disk if possible.\n\nPlease refer to your user guide or, contact a Technical Support Representative, for more details."
        else:
            text = "An error has occurred and the installation must be aborted.  The error was:\n\n%s\n\nPlease refer to your user guide, or contact a Technical Support Representative, for further details." % exc_str

        bb = ButtonBar(screen, ['Reboot'])
        t = TextboxReflowed(50, text, maxHeight = screen.height - 13)
        screen.pushHelpLine("  Press <Enter> to reboot.")
        g = GridFormHelp(screen, "Error occurred", None, 1, 2)
        g.add(t, 0, 0, padding = (0, 0, 0, 1))
        g.add(bb, 0, 1, growx = 1)
        g.addHotKey("F2")
        result = g.runOnce()
        screen.popHelpLine()

        # did they press the secret F2 key that activates debugging
        # features?
        if result == "F2":
            traceback_dialog(trace)
    else:
        xelogging.log("A text UI error dialog was requested, but the UI has not been initialised yet.")

def traceback_dialog(trace):
    result = ButtonChoiceWindow(
        screen, "Traceback",
        "The traceback was as follows:\n\n" + trace,
        ['Ok', 'Start PDB'], width=60
        )
    if result == "start pdb":
        screen.suspend()
        pdb.set_trace()
        screen.resume()

