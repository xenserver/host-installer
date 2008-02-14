# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Network interface management utils
#
# written by Andrew Peace

import os
import util
import re

class NIC:
    def __init__(self, name, hwaddr, pci_string):
        self.name = name
        self.hwaddr = hwaddr
        self.pci_string = pci_string

    def __repr__(self):
        return "<NIC: %s (%s)>" % (self.name, self.hwaddr)

def scanConfiguration():
    """ Returns a dictionary of string -> NIC with a snapshot of the NIC
    configuration."""
    conf = {}
    for nif in getNetifList():
        conf[nif] = NIC(nif, getHWAddr(nif), getPCIInfo(nif))
    return conf

def getNetifList():
    all = os.listdir("/sys/class/net")
    relevant = filter(lambda x: x.startswith("eth"), all)
    relevant.sort()
    return relevant

def mk_iface_config_dhcp(hwaddr, enabled):
    """ Make an interface configuration dictionary for DHCP. """
    return {'use-dhcp': True, 'hwaddr': hwaddr, 'enabled': enabled}

def mk_iface_config_static(hwaddr, enabled, ip, subnet_mask, gateway, dns):
    """ Make an interface configuration dictionary for a static IP config."""
    return {
        'use-dhcp': False,
        'hwaddr': hwaddr,
        'enabled': enabled,
        'ip': ip,
        'dns': dns,
        'subnet-mask': subnet_mask,
        'gateway': gateway
        }

# writes an 'interfaces' style file given a network configuration dictionary
# in the 'results' style format
def writeDebStyleInterfaceFile(configuration, filename):
    outfile = open(filename, 'w')

    outfile.write("auto lo\n")
    outfile.write("iface lo inet loopback\n")

    for iface in configuration:
        settings = configuration[iface]
        if settings['enabled']:
            if settings['use-dhcp']:
                outfile.write("iface %s inet dhcp\n" % iface)
            else:
                # CA-11825: broadcast needs to be determined for non-standard networks
                bcast = None
                rc, output = util.runCmd('/bin/ipcalc -b %s %s' % (settings['ip'], settings['subnet-mask']),
                                         with_output=True)
                if rc == 0:
                    bcast=output[10:]
                outfile.write("iface %s inet static\n" % iface)
                outfile.write("   address %s\n" % settings['ip'])
                if bcast != None:
                    outfile.write("   broadcast %s\n" % bcast)
                outfile.write("   netmask %s\n" % settings['subnet-mask'])
                if settings.has_key("gateway") and settings['gateway'] != "":
                    outfile.write("   gateway %s\n" % settings['gateway'])

    outfile.close()

# writes DNS server entries to a resolver file given a network configuration dictionary
# in the 'results' style format
def writeResolverFile(configuration, filename):
    outfile = open(filename, 'a')

    for iface in configuration:
        settings = configuration[iface]
        if settings['enabled'] and not settings['use-dhcp'] and settings.has_key('dns'):
            for dns in settings['dns']:
                outfile.write("nameserver %s\n" % dns)

    outfile.close()

# simple wrapper for calling the local ifup script:
def ifup(interface):
    assert interface in getNetifList()
    return util.runCmd2(['ifup', interface])

def ifdown(interface):
    return util.runCmd2(['ifdown', interface])

# work out if an interface is up:
def interfaceUp(interface):
    rc, out = util.runCmd("ip addr show %s" % interface, with_output = True)
    if rc != 0:
        return False
    inets = filter(lambda x: x.startswith("    inet "), out.split("\n"))
    return len(inets) == 1

# make a string to help users identify a network interface:
def getPCIInfo(interface):
    devpath = os.path.realpath('/sys/class/net/%s/device' % interface)
    slot = devpath[len(devpath) - 7:]

    rc, output = util.runCmd('lspci -i /usr/share/misc/pci.ids -s %s' % slot, with_output=True)

    if rc == 0:
        return output
    else:
        return "<Information unknown.>"

def __readOneLineFile__(filename):
    f = open(filename)
    value = f.readline().strip('\n')
    f.close()
    return value

def getHWAddr(iface):
    return __readOneLineFile__('/sys/class/net/%s/address' % iface)

def valid_hostname(x, emptyValid = False, fqdn = False):
    if emptyValid and x == '':
        return True
    if fqdn:
        return re.match('^[a-zA-Z0-9]([-a-zA-Z0-9]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([-a-zA-Z0-9]{0,61}[a-zA-Z0-9])?)*$', x) != None
    else:
        return re.match('^[a-zA-Z0-9]([-a-zA-Z0-9]{0,61}[a-zA-Z0-9])?$', x) != None


def valid_ip_addr(addr):
    if not re.match('^\d+\.\d+\.\d+\.\d+$', addr):
        return False
    els = addr.split('.')
    if len(els) != 4:
        return False
    for el in els:
        if int(el) > 255:
            return False
    return True
