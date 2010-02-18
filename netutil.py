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
import subprocess

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
    relevant.sort(lambda l, r: int(l[3:]) - int(r[3:]))
    return relevant

# writes an 'interfaces' style file given a network configuration object list
def writeDebStyleInterfaceFile(configuration, filename):
    outfile = open(filename, 'w')

    outfile.write("auto lo\n")
    outfile.write("iface lo inet loopback\n")

    for iface in configuration:
        configuration[iface].writeDebStyleInterface(iface, outfile)

    outfile.close()

# writes DNS server entries to a resolver file given a network configuration object
# list
def writeResolverFile(configuration, filename):
    outfile = open(filename, 'a')

    for iface in configuration:
        settings = configuration[iface]
        if settings.isStatic() and settings.dns:
            for server in settings.dns:
                outfile.write("nameserver %s\n" % server)

    outfile.close()

# simple wrapper for calling the local ifup script:
def ifup(interface):
    assert interface in getNetifList()
    return util.runCmd2(['ifup', interface])

def ifdown(interface):
    return util.runCmd2(['ifdown', interface])

# work out if an interface is up:
def interfaceUp(interface):
    rc, out = util.runCmd2(['ip', 'addr', 'show', interface], with_stdout = True)
    if rc != 0:
        return False
    inets = filter(lambda x: x.startswith("    inet "), out.split("\n"))
    return len(inets) == 1

# work out if a link is up:
def linkUp(interface):
    up = False
    rc, out = util.runCmd2(['ethtool', interface], with_stdout = True)
    if rc != 0:
        return False
    for line in out.split('\n'):
        line = line.strip()
        # examine auto-neg line, the link line always reports 'no' if the interface is down
        if line.startswith('Duplex:'):
            up = line.find('Unknown!') == -1
            break
    return up

# make a string to help users identify a network interface:
def getPCIInfo(interface):
    info = "<Information unknown>"
    devpath = os.path.realpath('/sys/class/net/%s/device' % interface)
    slot = devpath[len(devpath) - 7:]

    rc, output = util.runCmd2(['lspci', '-i', '/usr/share/misc/pci.ids', '-s', slot], with_stdout=True)

    if rc == 0:
        info = output.strip('\n')

    cur_if = None
    pipe = subprocess.Popen(['biosdevname', '-d'], bufsize = 1, stdout = subprocess.PIPE)
    for line in pipe.stdout:
        l = line.strip('\n')
        if l.startswith('Kernel name'):
            cur_if = l[13:]
        elif l.startswith('PCI Slot') and cur_if == interface and l[16:] != 'embedded':
            info += "\nSlot "+l[16:]
    pipe.wait()

    return info

def getDriver(interface):
    return os.path.basename(os.path.realpath('/sys/class/net/%s/device/driver' % interface))

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
