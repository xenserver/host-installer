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
import tui
import tui.progress
import netutil
import version

from snack import *

def get_autoconfig_ifaces():
    def my_get_iface_configuration(answers, iface):
        rv, answers[iface] = get_iface_configuration(iface)
        return rv
   
    seq = []
    for x in netutil.getNetifList():
        seq.append((my_get_iface_configuration, (x,)))

    # when this was written this branch would never be taken
    # since we require at least one NIC at setup time:
    if len(seq) == 0:
        return uicontroller.SKIP_SCREEN, {}

    subdict = {}
    rv = uicontroller.runUISequence(seq, subdict)
    return rv, subdict

def get_iface_configuration(iface, txt = None, show_identify = True):
    def identify_interface(iface):
        ButtonChoiceWindow(tui.screen,
                           "Identify Interface",
                           """Name: %s

MAC Address: %s

PCI details: %s""" % (iface, netutil.getHWAddr(iface), netutil.getPCIInfo(iface)),
                           ['Ok'], width=60)
    def dhcp_change():
        for x in [ ip_field, gateway_field, subnet_field ]:
            x.setFlags(FLAG_DISABLED, not dhcp_rb.selected())

    gf = GridFormHelp(tui.screen, 'Networking', None, 1, 6)
    if txt == None:
        txt = "Configuration for %s (%s)" % (iface, netutil.getHWAddr(iface))
    text = TextboxReflowed(45, txt)
    if show_identify:
        b = [("Ok", "ok"), ("Back", "back"), ("Identify", "identify")]
    else:
        b = [("Ok", "ok"), ("Back", "back")]
    buttons = ButtonBar(tui.screen, b)

    dhcp_rb = SingleRadioButton("Automatic configuration (DHCP)", None, 1)
    dhcp_rb.setCallback(dhcp_change, ())
    static_rb = SingleRadioButton("Static configuration:", dhcp_rb, 0)
    static_rb.setCallback(dhcp_change, ())

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
    gf.add(dhcp_rb, 0, 2, anchorLeft = True)
    gf.add(static_rb, 0, 3, anchorLeft = True)
    gf.add(entry_grid, 0, 4, padding = (0,0,0,1))
    gf.add(buttons, 0, 5)

    while True:
        result = gf.run()
        # do we display a popup then continue, or leave the loop?
        if buttons.buttonPressed(result) == 'identify':
            identify_interface(iface)
        else:
            # leave the loop - 'ok', F12, or 'back' was pressed:
            tui.screen.popWindow()
            break

    if buttons.buttonPressed(result) in ['ok', None]:
        answers = {'use-dhcp': bool(dhcp_rb.selected()),
                   'enabled': True,
                   'ip': ip_field.value(),
                   'subnet-mask': subnet_field.value(),
                   'gateway': gateway_field.value() }
        return 1, answers
    elif buttons.buttonPressed(result) == 'back':
        return -1, None

def select_netif(text):
    netifs = [("%s (%s)" % (x, netutil.getHWAddr(x)), x) for x in netutil.getNetifList()]
    rc, entry = ListboxChoiceWindow(tui.screen, "Networking", text, netifs,
                                    ['Ok', 'Back'], width=45)
    if rc in ['ok', None]:
        return 1, entry
    elif rc == "back":
        return -1, None

def requireNetworking(answers):
    """ Display the correct sequence of screens to get networking
    configuration.  Bring up the network according to this configuration.
    If answers is a dictionary, set it's 'runtime-iface-configuration' key
    to the configuration in the style (all-dhcp, manual-config). """
    
    # Display a screen asking which interface to configure, then what the 
    # configuration for that interface should be:
    def select_interface(answers):
        direction, iface = select_netif("%s Setup needs network access to continue.\n\nWhich network interface would you like to configure to access your %s product repository?" % (version.PRODUCT_BRAND, version.PRODUCT_BRAND))
        if direction == 1:
            answers['interface'] = iface
        return direction
    def specify_configuration(answers, text):
        direction, conf = get_iface_configuration(answers['interface'], text)
        if direction == 1:
            answers['config'] = conf
        return direction

    netifs = netutil.getNetifList()
    conf_dict = {}
    if len(netifs) > 1:
        seq = [ uicontroller.Step(select_interface), 
                uicontroller.Step(specify_configuration, args=[None]) ]
    else:
        text = "%s Setup needs network access to continue.\n\nHow should networking be configured at this time?" % version.PRODUCT_BRAND
        conf_dict['interface'] = netifs[0]
        seq = [ uicontroller.Step(specify_configuration, args=[text]) ]
    direction = uicontroller.runSequence(seq, conf_dict)

    if direction == 1:
        netutil.writeDebStyleInterfaceFile(
            {conf_dict['interface']: conf_dict['config']},
            '/etc/network/interfaces'
            )
        tui.progress.showMessageDialog(
            "Networking",
            "Configuring network interface, please wait...",
            )
        netutil.ifup(conf_dict['interface'])

        # check that we have *some* network:
        if not netutil.interfaceUp(conf_dict['interface']):
            # no interfaces were up: error out, then go to start:
            tui.progress.OKDialog("Networking", "The network still does not appear to be active.  Please check your settings, and try again.")
            direction = 0
        else:
            if answers and type(answers) == dict:
                answers['runtime-iface-configuration'] = (False, {conf_dict['interface']: conf_dict['config']})
        tui.progress.clearModelessDialog()
        
    return direction


