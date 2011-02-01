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
import diskutil
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
    configuration.
    
    Filter out any NICs that have been reserved by the iBFT for use
    with boot time iSCSI targets.  (iBFT = iSCSI Boot Firmware Tables.)
    This is because we cannot use NICs that are used to access iSCSI
    LUNs for other purposes e.g. XenServer Management.
    """
    conf = {}

    for nif in getNetifList():
        if nif not in diskutil.ibft_reserved_nics:
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
            if settings.dns:
                for server in settings.dns:
                    outfile.write("nameserver %s\n" % server)
            if settings.domain:
                outfile.write("search %s\n" % settings.domain)

    outfile.close()

interface_up = {}

# simple wrapper for calling the local ifup script:
def ifup(interface):
    assert interface in getNetifList()
    interface_up[interface] = True
    return util.runCmd2(['ifup', interface])

def ifdown(interface):
    if interface in interface_up:
        del interface_up[interface]
    return util.runCmd2(['ifdown', interface])

def ipaddr(interface):
    rc, out = util.runCmd2(['ip', 'addr', 'show', interface], with_stdout = True)
    if rc != 0:
        return None
    inets = filter(lambda x: 'inet ' in x, out.split("\n"))
    if len(inets) == 1:
        m = re.search(r'inet (S+)/', inets[0])
        if m:
            return m.match(1)
    return None

# work out if an interface is up:
def interfaceUp(interface):
    rc, out = util.runCmd2(['ip', 'addr', 'show', interface], with_stdout = True)
    if rc != 0:
        return False
    inets = filter(lambda x: x.startswith("    inet "), out.split("\n"))
    return len(inets) == 1

def _linkUp(interface):
    linkUp = None
    duplexSet = None

    rc, out = util.runCmd2(['ethtool', interface], with_stdout = True)
    if rc != 0:
        return None, None
    for line in out.split('\n'):
        line = line.strip()
        if line.startswith('Link detected:'):
            linkUp = line.endswith('yes')
        elif line.startswith('Duplex:'):
            duplexSet = line.find('Unknown!') == -1
    return linkUp, duplexSet

# the following NICs always reflect link status in duplex
duplex_always = ['e1000', 'e1000e']

# work out if a link is up:
def linkUp(interface):
    up = False

    if getDriver(interface) in duplex_always:
        _, up = _linkUp(interface)
    else:
        # need interface to be up before we can probe
        if interface not in interface_up:
            util.runCmd2(['ifconfig', interface, 'up'])
            interface_up[interface] = True
        up, _ = _linkUp(interface)

    return up

def networkingUp():
    rc, out = util.runCmd2(['ip', 'route'], with_stdout = True)
    if rc == 0 and len(out.split('\n')) > 2:
        return True
    return False

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

def network(ipaddr, netmask):
    ip = map(int,ipaddr.split('.',3))
    nm = map(int,netmask.split('.',3))
    nw = map(lambda i: ip[i] & nm[i], range(4))
    return ".".join(map(str,nw))

class NetDevices:
    def __init__(self):
        self.netdev = []
        details = {}

        pipe = subprocess.Popen(['biosdevname', '-d'], bufsize = 1, stdout = subprocess.PIPE)
        for line in pipe.stdout:
            l = line.strip('\n')
            if len(l) == 0:
                self.netdev.append(details)
                details = {}
            else:
                (k, v) = l.split(':', 1)
                details[k.strip().lower().replace(' ', '-')] = v.strip()
        pipe.wait()

    def as_xml(self):
        output = '<net-devices>\n'

        for d in self.netdev:
            output += ' <net-device'
            for k, v in d.items():
                output += ' %s="%s"' % (k, v)
            output += '/>\n'

        output += '</net-devices>\n'
        return output
