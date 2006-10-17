# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# 'Init' output-only UI
#
# written by Andrew Peace

def init_ui():
    pass
def end_ui():
    pass
def refresh():
    pass

def startup_screen():
    assert False
def choose_operation(display_export_vms):
    assert False
def already_activated():
    pass

###
# Progress dialog:
def initProgressDialog(title, text, total):
    pass
def showMessageDialog(title, text):
    print "%s: %s" % (title, text)
def displayProgressDialog(current, pd):
    pass
def clearModelessDialog():
    pass
