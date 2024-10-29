# SPDX-License-Identifier: GPL-2.0-only
import os
import ipaddress
import configparser

import util
import netutil
from xcp import logger

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


class CaseConfigParser(configparser.ConfigParser):
    """ ConfigParser support case sensitive key """
    def optionxform(self, optionstr):
        return optionstr


class NetInterface:
    """ Represents the configuration of a network interface. """

    Static = 1
    DHCP = 2
    Autoconf = 3

    def __init__(self, mode, hwaddr, ipaddr=None, netmask=None, gateway=None,
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
        self.hwaddr = hwaddr
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
        vlan = ("vlan = '%d' " % self.vlan) if self.vlan else ""

        return "<NetInterface: %s%s ipv4:%s ipv6:%s>" % (hw, vlan, ipv4, ipv6)

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

    @staticmethod
    def _subnet_mask_to_prefix_length(subnet_mask):
        # Create an IPv4Network object with the subnet mask
        network = ipaddress.IPv4Network(f"0.0.0.0/{subnet_mask}")
        # Return the prefix length
        return network.prefixlen

    def writeSystemdNetworkdConfig(self, iface):
        """Write a systemd-networkd configuration for this interface"""
        assert self.modev6 is None
        assert self.mode
        sysd_netd_path = "/etc/systemd/network"
        iface_vlan = self.getInterfaceName(iface)

        logger.debug(f"Configuring {iface} with systemd-networkd")

        network_conf = CaseConfigParser()
        # Match section, match by Name
        network_conf["Match"] = {}
        network_conf["Match"]["Name"] = iface_vlan
        # Network section
        # NOTE: Network section append last, to hold future VLANs
        # This order is preserved by configparser since 3.8
        network_conf["Network"] = {}
        if self.mode == self.DHCP:
            network_conf["Network"]["DHCP"] = "yes"
        else:
            prefixlen = NetInterface._subnet_mask_to_prefix_length(self.netmask)
            network_conf["Network"]["Address"] = f"{self.ipaddr}/{prefixlen}"
            network_conf["Network"]["Gateway"] = f"{self.gateway}"

        iface_network_path = os.path.join(sysd_netd_path, f"{iface_vlan}.network")
        # VLAN should be configured After hosting interface, getNetifList ensured that
        if os.path.exists(iface_network_path):
            logger.warning(f"Overiding existing configuration: {iface_network_path}")
        with open(iface_network_path, "w", encoding="utf-8") as f:
            network_conf.write(f)

        if self.vlan:
            # If this is a vlan, need extra configuration
            # - Setup .netdev configuration for the vlan interface
            # - Set VLAN in [Network] section of hosting interface

            netdev_conf = CaseConfigParser()
            # DetDev section
            netdev_conf["NetDev"] = {}
            netdev_conf["NetDev"]["Name"] = iface_vlan
            netdev_conf["NetDev"]["Kind"] = "vlan"
            # VLAN section
            netdev_conf["VLAN"] = {}
            netdev_conf["VLAN"]["Id"] = str(self.vlan)
            netdev_conf_path = os.path.join(sysd_netd_path, f"{iface_vlan}.netdev")
            with open(netdev_conf_path, "w", encoding="utf-8") as f:
                netdev_conf.write(f)

            hosting_iface_network_path = os.path.join(sysd_netd_path, f"{iface}.network")
            if os.path.exists(hosting_iface_network_path):
                # Just append VLAN to ending, which is in [Network] section
                with open(hosting_iface_network_path, 'a', encoding="utf-8") as f:
                    f.write(f"VLAN={iface_vlan}\n")
            else:
                # The hosting interface just used to host the vlan
                logger.debug("Found vlan {iface_vlan} with unconfigured hosting interface")
                hosting_conf = CaseConfigParser()
                hosting_conf["Match"] = {}
                hosting_conf["Match"]["Name"] = iface
                # NOTE: Network section append last, to hold future VLANs
                hosting_conf["Network"] = {}
                hosting_conf["Network"]["VLAN"] = iface_vlan
                with open(hosting_iface_network_path, "w", encoding="utf-8") as f:
                    hosting_conf.write(f)

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
