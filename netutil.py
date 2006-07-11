###
# XEN CLEAN INSTALLER
# Network interface management utils
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import os
import util

def getNetifList():
    pipe = os.popen("/sbin/ifconfig -a | grep '^[a-z].*' | awk '{ print $1 }' | grep '^eth.*'")
    interfaces = []
    for iface in pipe:
        interfaces.append(iface.strip("\n"))
    pipe.close()

    return interfaces

# writes an 'interfaces' style file given a network configuration dictionary
# in the 'results' style format
def writeDebStyleInterfaceFile(configuration, filename):
    outfile = open(filename, 'w')

    outfile.write("auto lo\n")
    outfile.write("iface lo inet loopback\n")

    for iface in configuration:
        settings = configuration[iface]
        if settings['use-dhcp']:
            outfile.write("iface %s inet dhcp\n" % iface)
        else:
            # not coded this bit yet
            assert False

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

    rc, output = util.runCmdWithOutput('lspci -i /usr/share/misc/pci.ids -s %s' % slot)

    if rc == 0:
        return output
    else:
        return "<Information unknown.>"

def __readOneLineFile__(filename):
    try:
        f = open(filename)
        value = f.readline().strip('\n')
        f.close()
        return value
    except Exception, e:
        raise e

def getHWAddr(iface):
    return __readOneLineFile__('/sys/class/net/%s/address' % iface)
