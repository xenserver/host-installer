# Copyright (c) 2008 Citrix Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by Citrix Inc. All other rights reserved.

###
# XEN HOST INSTALLER
# Wrapper for network interfaces
#
# written by Simon Rowe

import os
import util

class NetInterface:
    Static = 1
    DHCP = 2

    def __init__(self, mode, hwaddr, ipaddr=None, netmask=None, gateway=None, dns=None):
        assert mode == self.Static or mode == self.DHCP
        if ipaddr == '':
            ipaddr = None
        if netmask == '':
            netmask = None
        if gateway == '':
            gateway = None
        if dns == '':
            dns = None
        if mode == self.Static:
            assert ipaddr
            assert netmask

        self.mode = mode
        self.hwaddr = hwaddr
        if mode == self.Static:
            self.ipaddr = ipaddr
            self.netmask = netmask
            self.gateway = gateway
            self.dns = dns

    def __str__(self):
        if self.mode == self.DHCP:
            return "{'mode': 'DHCP', 'hwaddr': '%s'}" % self.hwaddr
        else:
            return "{'mode': 'Static', 'hwaddr': '%s', " % self.hwaddr  + \
                "'ipaddr': '%s', 'netmask': '%s', 'gateway': '%s', 'dns': '%s'}" % \
                (self.ipaddr, self.netmask, self.gateway, self.dns)

    def isStatic(self):
        return self.mode == self.Static

    def writeDebStyleInterface(self, iface, f):
        if self.mode == self.DHCP:
            f.write("iface %s inet dhcp\n" % iface)
        else:
            # CA-11825: broadcast needs to be determined for non-standard networks
            bcast = None
            rc, output = util.runCmd2(['/bin/ipcalc', '-b', self.ipaddr, self.netmask],
                                      with_output=True)
            if rc == 0:
                bcast=output[10:]
            f.write("iface %s inet static\n" % iface)
            f.write("   address %s\n" % self.ipaddr)
            if bcast != None:
                f.write("   broadcast %s\n" % bcast)
            f.write("   netmask %s\n" % self.netmask)
            if self.gateway:
                f.write("   gateway %s\n" % self.gateway)
