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
    return rc.encode()
def getTextOrNone(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc == "" and None or rc.encode()

class NetInterface:
    """ Represents the configuration of a network interface. """

    Static = 1
    DHCP = 2

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

    def __repr__(self):
        if self.mode == None:
            return "<NetInterface: None, hwaddr = '%s'>" % self.hwaddr
        elif self.mode == self.DHCP:
            return "<NetInterface: DHCP, hwaddr = '%s'>" % self.hwaddr
        else:
            return "<NetInterface: Static, hwaddr = '%s', " % self.hwaddr + \
                "ipaddr = '%s', netmask = '%s', gateway = '%s', dns = '%s' domain = '%s'>" % \
                (self.ipaddr, self.netmask, self.gateway, self.dns, self.domain)

    def get(self, name, default = None):
        retval = default
        if hasattr(self, name):
            attr = getattr(self, name)
            if attr is not None:
                retval = attr
        return retval
        

    def isStatic(self):
        """ Returns true if a static interface configuration is represented. """
        return self.mode == self.Static

    def writeDebStyleInterface(self, iface, f):
        """ Write a Debian-style configuration entry for this interface to 
        file object f using interface name iface. """

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
        f.write('\t</pif>\n')

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

        return NetInterface(mode, hwaddr, valOrNone(conf, 'IPADDR'), valOrNone(conf, 'NETMASK'),
                            valOrNone(conf, 'GATEWAY'), dns, valOrNone(conf, 'DOMAIN'))

    @staticmethod
    def loadFromPif(pif):
        mode_txt = getText(pif.getElementsByTagName('ip_configuration_mode')[0].childNodes)
        if mode_txt == 'None':
            mode = None
        elif mode_txt == 'Static':
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
    
        return NetInterface(mode, hwaddr, ipaddr, netmask, gateway, dns, domain)
