###
# XEN CLEAN INSTALLER
# 'Init' text user interface
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

from snack import *
from version import *

import netutil

screen = None

def init_ui():
    global screen
    screen = SnackScreen()
    screen.drawRootText(0, 0, "Welcome to %s - Version %s (#%s)" % (PRODUCT_BRAND, PRODUCT_VERSION, BUILD_NUMBER))
    screen.drawRootText(0, 1, "Copyright %s %s" % (COMPANY_NAME_LEGAL, COPYRIGHT_YEARS))

def end_ui():
    if screen:
        screen.finish()

def refresh():
    if screen:
        screen.refresh()

def choose_operation():
    entries = [ 
        ' * Install %s' % BRAND_SERVER,
        ' * Upgrade %s' % BRAND_SERVER,
        ' * Convert an existing OS on this machine to a %s (P2V)' % BRAND_GUEST_SHORT
        ]
    (button, entry) = ListboxChoiceWindow(screen,
                                          "Welcome to %s" % PRODUCT_BRAND,
                                          """Please select an operation:""",
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

def ask_load_module(m):
    global screen

    result = ButtonChoiceWindow(screen,
                                "Interactive Module Loading",
                                "Load module %s?" % m,
                                ['Yes', 'No'])

    return result != 'no'


###
# Network configuration:

CONFIGURE_NETWORK_CANCEL = 0
CONFIGURE_NETWORK_STATICALLY = 1
CONFIGURE_NETWORK_NONE = 2

def require_static_config(first_time):
    global screen

    if first_time:
        message = "Automatic netowrk configuration using DHCP did not succeed."
    else:
        message = "The network configuration you selected didn't result in any interfaces successfully being brought up."

    result = ButtonChoiceWindow(screen,
                                "Configure Network",
                                """%s

Networking needs to be configured in order for the P2V tool to function correctly.  Would you like to specify a static configuration?""" % message,
                                ['Yes', 'No (Cancel P2V)'])

    if result == 'no (cancel p2v)':
        return CONFIGURE_NETWORK_CANCEL
    else:
        return CONFIGURE_NETWORK_STATICALLY

def ask_static_config(first_time):
    global screen

    if first_time:
        message = "Automatic netowrk configuration using DHCP did not succeed."
    else:
        message = "The network configuration you selected didn't result in any interfaces successfully being brought up."

    result = ButtonChoiceWindow(screen,
                                "Configure Network",
                                """%s

Would you like to specify a manual configuration?  If you choose not to, you will only be able to perform installation from local media.""" % message,
                                ['Configure manually', 'Continue without networking', 'Cancel'], width=60)

    if result == 'cancel':
        return CONFIGURE_NETWORK_CANCEL
    elif result == 'configure manually':
        return CONFIGURE_NETWORK_STATICALLY
    else:
        return CONFIGURE_NETWORK_NONE

def get_iface_configuration(answers, iface, installmode = True):
    global screen

    def identify_interface(iface):
        global screen
        ButtonChoiceWindow(screen,
                           "Identify Interface",
                           """Name: %s

MAC Address; %s

PCI details; %s""" % (iface, netutil.getHWAddr(iface), netutil.getPCIInfo(iface)),
                           ['Ok'], width=60)
    def enabled_change():
        for x in [ ip_field, gateway_field, subnet_field ]:
            x.setFlags(FLAG_DISABLED,
                           (enabled_cb.value() and not dhcp_cb.value()))
        dhcp_cb.setFlags(FLAG_DISABLED, enabled_cb.value())
    def dhcp_change():
        for x in [ ip_field, gateway_field, subnet_field ]:
            x.setFlags(FLAG_DISABLED,
                           (enabled_cb.value() and not dhcp_cb.value()))

    if installmode:
        gf = GridFormHelp(screen, 'Network Configuration', None, 1, 6)
    else:
        gf = GridFormHelp(screen, 'Network Configuration', None, 1, 5)
    text = TextboxReflowed(45, "Configuration for %s (%s)" % (iface, netutil.getHWAddr(iface)))
    buttons = ButtonBar(screen, [("Ok", "ok"), ("Back", "back"), ("Identify", "identify")])

    # note spaces exist to line checkboxes up:
    enabled_cb = Checkbox("Enable interface", 1)
    dhcp_cb = Checkbox("Configure with DHCP", 1)
    enabled_cb.setCallback(enabled_change, ())
    dhcp_cb.setCallback(dhcp_change, ())

    ip_field = Entry(16)
    ip_field.setFlags(FLAG_DISABLED, False)
    subnet_field = Entry(16)
    subnet_field.setFlags(FLAG_DISABLED, False)
    gateway_field = Entry(16)
    gateway_field.setFlags(FLAG_DISABLED, False)

    ip_text = Textbox(15, 1, "IP Address:")
    subnet_text = Textbox(15, 1, "Subnet mask:")
    gateway_text = Textbox(15, 1, "Gateway:")

    entry_grid = Grid(2, 3)
    entry_grid.setField(ip_text, 0, 0)
    entry_grid.setField(ip_field, 1, 0)
    entry_grid.setField(subnet_text, 0, 1)
    entry_grid.setField(subnet_field, 1, 1)
    entry_grid.setField(gateway_text, 0, 2)
    entry_grid.setField(gateway_field, 1, 2)

    gf.add(text, 0, 0, padding = (0,0,0,1))
    gf.add(enabled_cb, 0, 1, anchorLeft = True)
    gf.add(dhcp_cb, 0, 2, anchorLeft = True)
    gf.add(entry_grid, 0, 3, padding = (0,0,0,1))
    if installmode:
        gf.add(TextboxReflowed(45, "(The options you select here only take effect during %s installation.)" % BRAND_SERVER), 0, 4, padding = (0,0,0,1))
        gf.add(buttons, 0, 5)
    else:
        gf.add(buttons, 0, 4)
        
    while True:
        result = gf.run()
        # do we display a popup then continue, or leave the loop?
        if not buttons.buttonPressed(result) == 'ok' and \
           not buttons.buttonPressed(result) == 'back':
            assert buttons.buttonPressed(result) == 'identify'
            identify_interface(iface)
        else:
            # leave the loop - 'ok' or 'back' was pressed:
            screen.popWindow()
            break

    if buttons.buttonPressed(result) == 'ok':
        answers[iface] = {'use-dhcp': dhcp_cb.value(),
                          'enabled': enabled_cb.value(),
                          'ip': ip_field.value(),
                          'subnet-mask': subnet_field.value(),
                          'gateway': gateway_field.value() }
        return 1
    elif buttons.buttonPressed(result) == 'back':
        return -1


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
