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
