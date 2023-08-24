# SPDX-License-Identifier: GPL-2.0-only

import util
import netutil

def getText(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc.strip().encode()
def getTextOrNone(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc == "" and None or rc.strip().encode()

class NetInterface:
    """ Represents the configuration of a network interface. """

    Static = 1
    DHCP = 2
    Autoconf = 3

    def __init__(self, mode, nic, ipaddr=None, netmask=None, gateway=None,
                 dns=None, domain=None, vlan=None):
        assert mode is None or mode == self.Static or mode == self.DHCP
        if ipaddr == '':
            ipaddr = None
        if netmask == '':
            netmask = None
        if gateway == '':
            gateway = None
        if dns == '':
            dns = None
        elif isinstance(dns, str):
            dns = [ dns ]
        if mode == self.Static:
            assert ipaddr
            assert netmask

        self.mode = mode
        self.hwaddr = nic.hwaddr
        if mode == self.Static:
            self.ipaddr = ipaddr
            self.netmask = netmask
            self.gateway = gateway
            self.dns = dns
            self.domain = domain
        else:
            self.ipaddr = None
            self.netmask = None
            self.gateway = None
            self.dns = None
            self.domain = None
        self.vlan = vlan

        # Initialise IPv6 to None.
        self.modev6 = None
        self.ipv6addr = None
        self.ipv6_gateway = None

        self.bond_mode = nic.bond_mode
        if nic.bond_mode is not None:
            # Not `balance-slb` because it's openvswitch specific
            assert nic.bond_mode in ["lacp", "active-backup"]
            assert nic.bond_members is not None
            self.bond_members = nic.bond_members

    def __repr__(self):
        hw = "hwaddr = '%s' " % self.hwaddr

        if self.mode == self.Static:
            ipv4 = "Static;" + \
                "ipaddr='%s';netmask='%s';gateway='%s';dns='%s';domain='%s'>" % \
                (self.ipaddr, self.netmask, self.gateway, self.dns, self.domain)
        elif self.mode == self.DHCP:
            ipv4 = "DHCP"
        else:
            ipv4 = "None"

        if self.modev6 == self.Static:
            ipv6 = "Static;" + \
                "ipaddr='%s';gateway='%s'>" % \
                (self.ipv6addr, self.ipv6_gateway)
        elif self.modev6 == self.DHCP:
            ipv6 = "DHCP"
        elif self.modev6 == self.Autoconf:
            ipv6 = "autoconf"
        else:
            ipv6 = "None"
        bonding = ((" %s:%s" % (self.bond_mode, ",".join(self.bond_members)))
                   if self.bond_mode else "")
        vlan = (" vlan='%d' " % self.vlan) if self.vlan else ""

        return "<NetInterface: %s%s%s ipv4:%s ipv6:%s>" % (hw, bonding, vlan, ipv4, ipv6)

    def get(self, name, default=None):
        retval = default
        if hasattr(self, name):
            attr = getattr(self, name)
            if attr is not None:
                retval = attr
        return retval

    def getInterfaceName(self, iface):
        return ("%s.%d" % (iface, self.vlan)) if self.vlan else iface

    def addIPv6(self, modev6, ipv6addr=None, ipv6gw=None):
        assert modev6 is None or modev6 == self.Static or modev6 == self.DHCP or modev6 == self.Autoconf
        if ipv6addr == '':
            ipv6addr = None
        if ipv6gw == '':
            ipv6gw = None
        if modev6 == self.Static:
            assert ipv6addr

        self.modev6 = modev6
        if modev6 == self.Static:
            self.ipv6addr = ipv6addr
            self.ipv6_gateway = ipv6gw
        else:
            self.ipv6addr = None
            self.ipv6_gateway = None

    def valid(self):
        if (self.mode == self.Static) and ((self.ipaddr is None) or (self.netmask is None)):
            return False
        if (self.modev6 == self.Static) and (self.ipv6addr is None):
            return False
        return self.mode or self.modev6

    def isStatic(self):
        """ Returns true if a static interface configuration is represented. """
        return self.mode == self.Static

    def isVlan(self):
        return self.vlan is not None

    def getBroadcast(self):
        bcast = None
        rc, output = util.runCmd2(['/bin/ipcalc', '-b', self.ipaddr, self.netmask],
                                  with_stdout=True)
        if rc == 0:
            bcast = output[10:].strip()
        return bcast

    def writeRHStyleInterface(self, iface):
        """ Write a RedHat-style configuration entry for this interface to
        file object f using interface name iface. """

        def writeBondMember(index, member):
            """ Write a RedHat-style configuration entry for a bond member. """

            with open('/etc/sysconfig/network-scripts/ifcfg-%s' % member, 'w') as f:
                f.write("NAME=%s-slave%d\n" % (iface, index))
                f.write("DEVICE=%s\n" % member)
                f.write("ONBOOT=yes\n")
                f.write("MASTER=%s\n" % iface)
                f.write("SLAVE=yes\n")
                f.write("BOOTPROTO=none\n")
                f.write("Type=Ethernet\n")

        def writeBondMaster():
            """ Write a RedHat-style configuration entry for a bond master. """

            with open('/etc/sysconfig/network-scripts/ifcfg-%s' % iface, 'w') as f:
                f.write("NAME=%s\n" % iface)
                f.write("DEVICE=%s\n" % iface)
                f.write("ONBOOT=yes\n")
                f.write("Type=Bond\n")
                f.write("NOZEROCONF=yes\n")
                f.write("BONDING_MASTER=yes\n")
                if self.bond_mode == "lacp":
                    f.write("BONDING_OPTS=\"mode=4 miimon=100\"\n")
                elif self.bond_mode == "active-backup":
                    f.write("BONDING_OPTS=\"mode=1 miimon=100\"\n")

                if self.vlan:
                    f.write("BOOTPROTO=none\n")
                else:
                    writeIpConfig(f)

        def writeIface(iface_name):
            with open('/etc/sysconfig/network-scripts/ifcfg-%s' % iface_name, 'w') as f:
                f.write("NAME=%s\n" % iface_name)
                f.write("DEVICE=%s\n" % iface_name)
                f.write("ONBOOT=yes\n")
                writeIpConfig(f)
                if self.vlan:
                    f.write("VLAN=yes\n")

        def writeIpConfig(f):
            if self.mode == self.DHCP:
                f.write("BOOTPROTO=dhcp\n")
                f.write("PERSISTENT_DHCLIENT=1\n")
            else:
                # CA-11825: broadcast needs to be determined for non-standard networks
                bcast = self.getBroadcast()
                f.write("BOOTPROTO=none\n")
                f.write("IPADDR=%s\n" % self.ipaddr)
                if bcast is not None:
                    f.write("BROADCAST=%s\n" % bcast)
                f.write("NETMASK=%s\n" % self.netmask)
                if self.gateway:
                    f.write("GATEWAY=%s\n" % self.gateway)

        assert self.modev6 is None
        assert self.mode

        iface_vlan = self.getInterfaceName(iface)

        if self.bond_mode:
            # configuration of the bond interface
            for idx, member in enumerate(self.bond_members):
                writeBondMember(idx, member)
            writeBondMaster() # ... includes IP config if not using VLAN ...
            if self.vlan:
                writeIface(iface_vlan) # ... but here when using VLAN
        else:
            writeIface(iface_vlan)

    def waitUntilUp(self, iface):
        if not self.isStatic():
            return True
        if not self.gateway:
            return True

        rc = util.runCmd2(['/usr/sbin/arping', '-f', '-w', '120', '-I',
                           self.getInterfaceName(iface), self.gateway])
        return rc == 0

    @staticmethod
    def getModeStr(mode):
        if mode == NetInterface.Static:
            return 'static'
        if mode == NetInterface.DHCP:
            return 'dhcp'
        if mode == NetInterface.Autoconf:
            return 'autoconf'
        return 'none'
