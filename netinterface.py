# Copyright (c) 2008 Citrix Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by Citrix Inc. All other rights reserved.

###
# XEN HOST INSTALLER
# Wrapper for network interfaces
#
# written by Simon Rowe

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

    def __init__(self, mode, hwaddr, ipaddr=None, netmask=None, gateway=None, dns=None, domain=None):
        assert mode == None or mode == self.Static or mode == self.DHCP
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

        return "<NetInterface: %s ipv4:%s ipv6:%s>" % (hw, ipv4, ipv6)

    def get(self, name, default = None):
        retval = default
        if hasattr(self, name):
            attr = getattr(self, name)
            if attr is not None:
                retval = attr
        return retval
        
    def addIPv6(self, modev6, ipv6addr=None, ipv6gw=None):
        assert modev6 == None or modev6 == self.Static or modev6 == self.DHCP or modev6 == self.Autoconf
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

    def writeDebStyleInterface(self, iface, f):
        """ Write a Debian-style configuration entry for this interface to 
        file object f using interface name iface. """

        # Debian style interfaces are only used for the installer; dom0 only uses CentOS style
        # IPv6 is only enabled through answerfiles and so is not supported here.
        assert self.modev6 == None

        assert self.mode
        if self.mode == self.DHCP:
            f.write("iface %s inet dhcp\n" % iface)
        else:
            # CA-11825: broadcast needs to be determined for non-standard networks
            bcast = None
            rc, output = util.runCmd2(['/bin/ipcalc', '-b', self.ipaddr, self.netmask],
                                      with_stdout=True)
            if rc == 0:
                bcast = output[10:].strip()
            f.write("iface %s inet static\n" % iface)
            f.write("   address %s\n" % self.ipaddr)
            if bcast != None:
                f.write("   broadcast %s\n" % bcast)
            f.write("   netmask %s\n" % self.netmask)
            if self.gateway:
                f.write("   gateway %s\n" % self.gateway)

    def writePif(self, iface, f, pif_uid, network_uid, bonding = None):
        """ Write PIF XML element for this interface to 
        file object f using interface name iface. """

        f.write('\t<pif ref="OpaqueRef:%s">\n' % pif_uid)
        f.write('\t\t<network>OpaqueRef:%s</network>\n' % network_uid)
        f.write('\t\t<management>True</management>\n')
        f.write('\t\t<uuid>%sPif</uuid>\n' % iface)

        f.write('\t\t<bond_slave_of>OpaqueRef:%s</bond_slave_of>\n' % ((bonding and bonding[0] == 'slave-of') and bonding[1] or 'NULL'))
        if (bonding and bonding[0] == 'master-of'):
            f.write('\t\t<bond_master_of>\n\t\t\t<slave>OpaqueRef:%s</slave>\n\t\t</bond_master_of>\n' % bonding[1])
        else:
            f.write('\t\t<bond_master_of/>\n')

        f.write('\t\t<VLAN_slave_of/>\n\t\t<VLAN_master_of>OpaqueRef:NULL</VLAN_master_of>\n\t\t<VLAN>-1</VLAN>\n')
        f.write('\t\t<tunnel_access_PIF_of/>\n')
        f.write('\t\t<tunnel_transport_PIF_of/>\n')
        f.write('\t\t<device>%s</device>\n' % iface)
        f.write('\t\t<MAC>%s</MAC>\n' % self.hwaddr)
        if self.domain:
            f.write('\t\t<other_config><domain>%s</domain></other_config>\n' % self.domain)
        else:
            f.write('\t\t<other_config/>\n')

        if self.mode == self.Static:
            f.write('\t\t<ip_configuration_mode>Static</ip_configuration_mode>\n')
            f.write('\t\t<IP>%s</IP>\n' % self.ipaddr)
            f.write('\t\t<netmask>%s</netmask>\n' % self.netmask)
            f.write('\t\t<gateway>%s</gateway>\n' % (self.gateway and self.gateway or ''))
            f.write('\t\t<DNS>%s</DNS>\n' % (self.dns and ','.join(self.dns) or ''))
        elif self.mode == self.DHCP:
            f.write('\t\t<ip_configuration_mode>DHCP</ip_configuration_mode>\n')
            f.write('\t\t<IP></IP>\n\t\t<netmask></netmask>\n')
            f.write('\t\t<gateway></gateway>\n')
            f.write('\t\t<DNS></DNS>\n')
        else:
            f.write('\t\t<ip_configuration_mode>None</ip_configuration_mode>\n')
            f.write('\t\t<DNS></DNS>\n')

        if self.modev6 == self.Static:
            f.write('\t\t<ipv6_configuration_mode>Static</ipv6_configuration_mode>\n')
            f.write('\t\t<IPv6>%s</IPv6>\n' % ipv6addr)
            if gateway is not None:
                f.write('\t\t<IPv6_gateway>%s</IPv6_gateway>\n' % ipv6_gateway)
        elif self.modev6 == self.DHCP:
            f.write('\t\t<ipv6_configuration_mode>DHCP</ipv6_configuration_mode>\n')
            f.write('\t\t<IPv6></IPv6>\n')
            f.write('\t\t<IPv6_gateway></IPv6_gateway>\n')
        elif self.modev6 == self.Autoconf:
            f.write('\t\t<ipv6_configuration_mode>Autoconf</ipv6_configuration_mode>\n')
            f.write('\t\t<IPv6></IPv6>\n')
            f.write('\t\t<IPv6_gateway></IPv6_gateway>\n')
        else:
            f.write('\t\t<ipv6_configuration_mode>None</ipv6_configuration_mode>\n')

        f.write('\t</pif>\n')

    @staticmethod
    def getModeStr(mode):
        if mode == NetInterface.Static:
            return 'static'
        if mode == NetInterface.DHCP:
            return 'dhcp'
        if mode == NetInterface.Autoconf:
            return 'autoconf'
        return 'none'

    @staticmethod
    def loadFromIfcfg(filename):
        def valOrNone(d, k):
            return d.has_key(k) and d[k] or None

        conf = util.readKeyValueFile(filename)
        mode = None
        if conf.has_key('BOOTPROTO'):
            if conf['BOOTPROTO'] == 'static' or conf.has_key('IPADDR'):
                mode = NetInterface.Static
            elif conf['BOOTPROTO'] == 'dhcp':
                mode = NetInterface.DHCP

        hwaddr = valOrNone(conf, 'HWADDR')
        if not hwaddr:
            hwaddr = valOrNone(conf, 'MACADDR')
        if not hwaddr:
            try:
                hwaddr = netutil.getHWAddr(conf['DEVICE'])
            except:
                pass
        dns = None
        n = 1
        while conf.has_key('DNS%d' % n):
            if not dns: dns = []
            dns.append(conf['DNS%d' % n])
            n += 1

        modev6 = None
        if conf.has_key('DHCPV6C'):
            modev6 = NetInterface.DHCP
        elif conf.has_key('IPV6_AUTOCONF'):
            modev6 = NetInterface.Autoconf
        elif conf.has_key('IPV6INIT'):
            modev6 = NetInterface.Static

        ni = NetInterface(mode, hwaddr, valOrNone(conf, 'IPADDR'), valOrNone(conf, 'NETMASK'),
                            valOrNone(conf, 'GATEWAY'), dns, valOrNone(conf, 'DOMAIN'))
        ni.addIPv6(modev6, valOrNone(conf, 'IPV6ADDR'), valOrNone(conf, 'IPV6_DEFAULTGW'))
        return ni

    @staticmethod
    def loadFromPif(pif):
        mode_txt = getText(pif.getElementsByTagName('ip_configuration_mode')[0].childNodes)
        mode = None
        if mode_txt == 'Static':
            mode = NetInterface.Static
        elif mode_txt == 'DHCP':
            mode = NetInterface.DHCP

        hwaddr = getTextOrNone(pif.getElementsByTagName('MAC')[0].childNodes)
        ipaddr = None
        netmask = None
        gateway = None
        dns = None
        domain = None

        if mode == NetInterface.Static:
            ipaddr = getTextOrNone(pif.getElementsByTagName('IP')[0].childNodes)
            netmask = getTextOrNone(pif.getElementsByTagName('netmask')[0].childNodes)
            gateway = getTextOrNone(pif.getElementsByTagName('gateway')[0].childNodes)
            dns_txt = getText(pif.getElementsByTagName('DNS')[0].childNodes)
            if dns_txt != '':
                dns = dns_txt.split(',')
            domain_list = pif.getElementsByTagName('other_config')[0].getElementsByTagName('domain')
            if len(domain_list) == 1:
                domain = getText(domain_list[0].childNodes)

        mode_txt = getText(pif.getElementsByTagName('ipv6_configuration_mode')[0].childNodes)
        modev6 = None
        ipv6addr = None
        gatewayv6 = None
        if mode_txt == 'Static':
            modev6 = NetInterface.Static
        elif mode_txt == 'DHCP':
            modev6 = NetInterface.DHCP
        elif mode_txt == 'Autoconf':
            modev6 = NetInterface.Autconf
        if modev6 == NetInterface.Static:
            ipv6addr = getTextOrNone(pif.getElementsByTagName('IPv6')[0].childNodes)
            gatewayv6 = getTextOrNone(pif.getElementsByTagName('IPv6_gateway')[0].childNodes)
    
        ni = NetInterface(mode, hwaddr, ipaddr, netmask, gateway, dns, domain)
        ni.addIPv6(modev6, ipv6addr, gatewayv6)
        return ni
