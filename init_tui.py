###
# XEN CLEAN INSTALLER
# 'Init' text user interface
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

from snack import *
from version import *

screen = None

def init_ui():
    global screen
    screen = SnackScreen()
    screen.drawRootText(0, 0, "Welcome to %s - Version %s (#%s)" % (PRODUCT_BRAND, PRODUCT_VERSION, BUILD_NUMBER))
    screen.drawRootText(0, 1, "Copyright XenSource, Inc. 2006")

def end_ui():
    if screen:
        screen.finish()

def refresh():
    if screen:
        screen.refresh()

def startup_screen():
    ButtonChoiceWindow(screen,
                       "Welcome to %s" % PRODUCT_BRAND,
                       """From here you may perform a clean host installation, or a P2V operation.

Please select 'Ok' to continue installation on this console.""",
                       ['Ok'], width = 60)

    return 1

def choose_operation():
    entries = [ 
        ' * Install %s Managed Host' % PRODUCT_BRAND,
        ' * Upgrade %s Managed Host' % PRODUCT_BRAND,
        ' * P2V (convert existing OS on this host into a VM template)'
        ]
    (button, entry) = ListboxChoiceWindow(screen,
                                          "Make a choice",
                                          """Select the install you want to perform:""",
                                          entries,
                                          ['Ok', 'Exit and reboot'], width=70)

    if button == 'ok' or button == None:
        return entry
    else:
        return -1

def already_activated():
    while True:
        form = GridFormHelp(screen, "Installation already started", None, 1, 1)
        tb = TextboxReflowed(50, """You have already activated the installation on a different console!
        
If this message is unexpected, please try restarting your machine, and enusre you only use one console (either serial, or tty).""")
        form.add(tb, 0, 0)
        form.run()

###
# Progress dialog:
def initProgressDialog(title, text, total):
    global screen
    
    form = GridFormHelp(screen, title, None, 1, 3)
    
    t = Textbox(60, 1, text)
    scale = Scale(60, total)
    form.add(t, 0, 0, padding = (0,0,0,1))
    form.add(scale, 0, 1, padding = (0,0,0,0))

    return (form, scale)

def showMessageDialog(title, text):
    global screen
    
    form = GridFormHelp(screen, title, None, 1, 1)
    
    t = TextboxReflowed(60, text)
    form.add(t, 0, 0, padding = (0,0,0,0))

    form.draw()
    screen.refresh()

def displayProgressDialog(current, (form, scale)):
    global screen
    
    scale.set(current)

    form.draw()
    screen.refresh()

def displayInfoDialog(title, text):
    global screen

    form = GridFormHelp(screen, title, None, 1, 2)
    
    t = TextboxReflowed(60, text)
    form.add(t, 0, 0)
    form.draw()
    screen.refresh()

def clearModelessDialog():
    global screen
    
    screen.popWindow()
