###
# XEN CLEAN INSTALLER
# 'Init' output-only UI
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

def init_ui():
    pass
def end_ui():
    pass
def refresh():
    pass

def startup_screen():
    assert False
def choose_operation():
    assert False
def already_activated():
    pass

###
# Progress dialog:
def initProgressDialog(title, text, total):
    pass
def showMessageDialog(title, text):
    print "%s: %s" % (title, text)
def displayProgressDialog(current, (form, scale)):
    pass
def clearModelessDialog():
    pass
