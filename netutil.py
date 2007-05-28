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

def getNetifList():
    all = os.listdir("/sys/class/net")
    relevant = filter(lambda x: x.startswith("eth"), all)
    relevant.sort()
    return relevant

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
                outfile.write("iface %s inet static\n" % iface)
                outfile.write("   address %s\n" % settings['ip'])
                outfile.write("   netmask %s\n" % settings['subnet-mask'])
                if settings.has_key("gateway") and settings['gateway'] != "":
                    outfile.write("   gateway %s\n" % settings['gateway'])

    outfile.close()

# simple wrapper for calling the local ifup script:
def ifup(interface):
    assert interface in getNetifList()
    return util.runCmd("ifup %s" % interface)

# work out if an interface is up:
IFF_UP = 1
def interfaceUp(interface):
    flags = int(__readOneLineFile__('/sys/class/net/%s/flags' % interface), 16)
    return flags & IFF_UP == IFF_UP

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
