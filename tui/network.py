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
from netinterface import *
import version

from snack import *

def get_iface_configuration(nic, txt = None, show_identify = True, defaults = None, include_dns = False):
    def identify_interface(nic):
        ButtonChoiceWindow(tui.screen,
                           "Identify Interface",
                           """Name: %s

MAC Address: %s

PCI details: %s""" % (nic.name, nic.hwaddr, nic.pci_string),
                           ['Ok'], width=60)
    def dhcp_change():
        for x in [ ip_field, gateway_field, subnet_field, dns_field ]:
            x.setFlags(FLAG_DISABLED, not dhcp_rb.selected())

    gf = GridFormHelp(tui.screen, 'Networking', None, 1, 6)
    if txt == None:
        txt = "Configuration for %s (%s)" % (nic.name, nic.hwaddr)
    text = TextboxReflowed(45, txt)
    if show_identify:
        b = [("Ok", "ok"), ("Back", "back"), ("Identify", "identify")]
    else:
        b = [("Ok", "ok"), ("Back", "back")]
    buttons = ButtonBar(tui.screen, b)

    ip_field = Entry(16)
    subnet_field = Entry(16)
    gateway_field = Entry(16)
    dns_field = Entry(16)

    if defaults and defaults.isStatic():
        # static configuration defined previously
        dhcp_rb = SingleRadioButton("Automatic configuration (DHCP)", None, 0)
        dhcp_rb.setCallback(dhcp_change, ())
        static_rb = SingleRadioButton("Static configuration:", dhcp_rb, 1)
        static_rb.setCallback(dhcp_change, ())
        if defaults.ipaddr:
            ip_field.set(defaults.ipaddr)
        if defaults.netmask:
            subnet_field.set(defaults.netmask)
        if defaults.gateway:
            gateway_field.set(defaults.gateway)
        if defaults.dns:
            dns_field.set(defaults.dns)
    else:
        dhcp_rb = SingleRadioButton("Automatic configuration (DHCP)", None, 1)
        dhcp_rb.setCallback(dhcp_change, ())
        static_rb = SingleRadioButton("Static configuration:", dhcp_rb, 0)
        static_rb.setCallback(dhcp_change, ())
        ip_field.setFlags(FLAG_DISABLED, False)
        subnet_field.setFlags(FLAG_DISABLED, False)
        gateway_field.setFlags(FLAG_DISABLED, False)
        dns_field.setFlags(FLAG_DISABLED, False)

    ip_text = Textbox(15, 1, "IP Address:")
    subnet_text = Textbox(15, 1, "Subnet mask:")
    gateway_text = Textbox(15, 1, "Gateway:")
    dns_text = Textbox(15, 1, "Nameserver:")

    entry_grid = Grid(2, include_dns and 4 or 3)
    entry_grid.setField(ip_text, 0, 0)
    entry_grid.setField(ip_field, 1, 0)
    entry_grid.setField(subnet_text, 0, 1)
    entry_grid.setField(subnet_field, 1, 1)
    entry_grid.setField(gateway_text, 0, 2)
    entry_grid.setField(gateway_field, 1, 2)
    if include_dns:
        entry_grid.setField(dns_text, 0, 3)
        entry_grid.setField(dns_field, 1, 3)

    gf.add(text, 0, 0, padding = (0,0,0,1))
    gf.add(dhcp_rb, 0, 2, anchorLeft = True)
    gf.add(static_rb, 0, 3, anchorLeft = True)
    gf.add(entry_grid, 0, 4, padding = (0,0,0,1))
    gf.add(buttons, 0, 5)

    loop = True
    while loop:
        result = gf.run()
        # do we display a popup then continue, or leave the loop?
        if buttons.buttonPressed(result) == 'identify':
            identify_interface(nic)
        else:
            # leave the loop - 'ok', F12, or 'back' was pressed:
            if buttons.buttonPressed(result) in ['ok', None]:
                # validate input
                msg = ''
                if static_rb.selected():
                    if not netutil.valid_ip_addr(ip_field.value()):
                        msg = 'IP Address'
                    elif not netutil.valid_ip_addr(subnet_field.value()):
                        msg = 'Subnet mask'
                    elif gateway_field.value() != '' and not netutil.valid_ip_addr(gateway_field.value()):
                        msg = 'Gateway'
                    elif dns_field.value() != '' and not netutil.valid_ip_addr(dns_field.value()):
                        msg = 'Nameserver'
                if msg != '':
                    tui.progress.OKDialog("Networking", "Invalid %s, please check the field and try again." % msg)
                else:
                    loop = False
            else:
                loop = False
        if not loop:
            tui.screen.popWindow()

    if buttons.buttonPressed(result) in ['ok', None]:
        if bool(dhcp_rb.selected()):
            answers = NetInterface(NetInterface.DHCP, nic.hwaddr)
        else:
            answers = NetInterface(NetInterface.Static, nic.hwaddr, ip_field.value(),
                subnet_field.value(), gateway_field.value(), dns_field.value())
        return 1, answers
    elif buttons.buttonPressed(result) == 'back':
        return -1, None

def select_netif(text, conf, default=None):
    """ Display a screen that displays a choice of network interfaces to the
    user, with 'text' as the informative text as the data, and conf being the
    netutil.scanConfiguration() output to be used. """

    netifs = conf.keys()
    netifs.sort()
    def_iface = None
    if default != None:
        def_iface = ("%s (%s)" % ((default, conf[default].hwaddr)), default)
    netif_list = [("%s (%s)" % ((x, conf[x].hwaddr)), x) for x in netifs]
    rc, entry = ListboxChoiceWindow(tui.screen, "Networking", text, netif_list,
                                    ['Ok', 'Back'], width=45, default=def_iface)
    if rc in ['ok', None]:
        return 1, entry
    elif rc == "back":
        return -1, None

def requireNetworking(answers, defaults=None):
    """ Display the correct sequence of screens to get networking
    configuration.  Bring up the network according to this configuration.
    If answers is a dictionary, set it's 'runtime-iface-configuration' key
    to the configuration in the style (all-dhcp, manual-config). """

    nethw = netutil.scanConfiguration()

    # Display a screen asking which interface to configure, then what the 
    # configuration for that interface should be:
    def select_interface(answers, default):
        """ Show the dialog for selecting an interface.  Sets
        answers['interface'] to the name of the interface selected (a
        string). """
        direction, iface = select_netif("%s Setup needs network access to continue.\n\nWhich network interface would you like to configure to access your %s product repository?" % (version.PRODUCT_BRAND, version.PRODUCT_BRAND), nethw, default)
        if direction == 1:
            answers['interface'] = iface
        return direction

    def specify_configuration(answers, txt, defaults):
        """ Show the dialog for setting nic config.  Sets answers['config']
        to the configuration used.  Assumes answers['interface'] is a string
        identifying by name the interface to configure. """
        direction, conf = get_iface_configuration(nethw[answers['interface']], txt, defaults=defaults, include_dns=True)
        if direction == 1:
            answers['config'] = conf
        return direction

    conf_dict = {}
    def_iface = None
    def_conf = None
    if type(defaults) == dict:
        if defaults.has_key('net-admin-interface'):
            def_iface = defaults['net-admin-interface']
        if defaults.has_key('net-admin-configuration'):
            def_conf = defaults['net-admin-configuration']
    if len(nethw.keys()) > 1:
        seq = [ uicontroller.Step(select_interface, args=[def_iface]), 
                uicontroller.Step(specify_configuration, args=[None, def_conf]) ]
    else:
        text = "%s Setup needs network access to continue.\n\nHow should networking be configured at this time?" % version.PRODUCT_BRAND
        conf_dict['interface'] = nethw.keys()[0]
        seq = [ uicontroller.Step(specify_configuration, args=[text, def_conf]) ]
    direction = uicontroller.runSequence(seq, conf_dict)

    if direction == 1:
        netutil.writeDebStyleInterfaceFile(
            {conf_dict['interface']: conf_dict['config']},
            '/etc/network/interfaces'
            )
        netutil.writeResolverFile(
            {conf_dict['interface']: conf_dict['config']},
            '/etc/resolv.conf'
            )
        tui.progress.showMessageDialog(
            "Networking",
            "Configuring network interface, please wait...",
            )
        netutil.ifdown(conf_dict['interface'])

        # check that we have *some* network:
        if netutil.ifup(conf_dict['interface']) != 0 or not netutil.interfaceUp(conf_dict['interface']):
            tui.progress.OKDialog("Networking", "The network still does not appear to be active.  Please check your settings, and try again.")
            direction = 0
        else:
            if answers and type(answers) == dict:
                answers['net-admin-interface'] = conf_dict['interface']
                answers['runtime-iface-configuration'] = (False, {conf_dict['interface']: conf_dict['config']})
        tui.progress.clearModelessDialog()
        
    return direction


