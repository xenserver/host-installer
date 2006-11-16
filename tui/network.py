# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# TUI Network configuration screens
#
# written by Andrew Peace

import uicontroller
import netutil
import snackutil
import version

from snack import *

def get_network_config(screen,
                       show_reuse_existing = False,
                       runtime_config = False):
    """ Returns a pair (direction, config).

    config is a pair in answers iface config format, or None
    if the reuse option was specified. """

    REUSE_EXISTING = 1
    ALL_DHCP = 2
    OTHER = 3

    answers = {}

    entries = []
    if show_reuse_existing:
        entries += [ ('Use the current configuration', REUSE_EXISTING) ]
    entries += [ ('Configure all interfaces using DHCP', ALL_DHCP),
                 ('Specify a different network configuration', OTHER) ]

    if runtime_config:
        text = """%s needs to configure networking in order to proceed with this option.

How would you like networking to be configured at this time?""" % version.PRODUCT_BRAND
    else:
        text = "How would you like networking to be configured on your installed server?"

    (button, entry) = ListboxChoiceWindow(
        screen, "Network Configuration", text, entries,
        ['Ok', 'Back'], width=50)

    if button == "ok" or button == None:
        # proceed to get_autoconfig_ifaces if manual configuration was selected:
        if entry == OTHER:
            (rv, config) = get_autoconfig_ifaces(screen)
            if rv == 1:
                return 1, (False, config)
            else:
                return 0, (False, config)
        elif entry == ALL_DHCP:
            return 1, (True, None)
        elif entry == REUSE_EXISTING:
            return 1, None
    
    if button == "back": return -1, None

def get_autoconfig_ifaces(screen):
    seq = []
    for x in netutil.getNetifList():
        seq.append((get_iface_configuration, (x, screen)))

    # when this was written this branch would never be taken
    # since we require at least one NIC at setup time:
    if len(seq) == 0:
        return uicontroller.SKIP_SCREEN, {}

    subdict = {}
    rv = uicontroller.runUISequence(seq, subdict)
    return rv, subdict
    
def get_iface_configuration(answers, iface, screen):
    def identify_interface(iface):
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
        answers[iface] = {'use-dhcp': bool(dhcp_cb.value()),
                          'enabled': bool(enabled_cb.value()),
                          'ip': ip_field.value(),
                          'subnet-mask': subnet_field.value(),
                          'gateway': gateway_field.value() }
        return 1
    elif buttons.buttonPressed(result) == 'back':
        return -1
