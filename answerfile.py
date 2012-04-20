#!/usr/bin/env python
# Copyright (c) 2011 Citrix Systems, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation; version 2.1 only. with the special
# exception on linking described in file LICENSE.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

"""answerfile - parse installation answerfiles"""

from constants import *
import disktools
import diskutil
from netinterface import *
import netutil
import product
import scripts
import util
import xelogging
import xml.dom.minidom

from xcp.xmlunwrap import *

def normalize_disk(disk):
    if disk.startswith('iscsi:'):
        # An rfc4173 spec identifying a LUN in the iBFT.  We
        # should be logged into this already.  Convert this spec into a
        # disk location.
        return diskutil.rfc4173_to_disk(disk)

    if not disk.startswith('/dev/'):
        disk = '/dev/' + disk
    return diskutil.partitionFromId(disk)

class AnswerfileException(Exception):
    pass

class Answerfile:

    def __init__(self, xmldoc):
        self.top_node = xmldoc.documentElement
        if self.top_node.nodeName in ['installation', 'upgrade']:
            self.operation = 'installation'
        elif self.top_node.nodeName == 'restore':
            self.operation = 'restore'
        else:
            raise AnswerfileException, "Unexpected top level element"
        
    @staticmethod
    def fetch(location):
        xelogging.log("Fetching answerfile from %s" % location)
        util.fetchFile(location, ANSWERFILE_PATH)
            
        try:
            xmldoc = xml.dom.minidom.parse(ANSWERFILE_PATH)
        except:
            raise AnswerfileException, "Answerfile is incorrectly formatted."

        return Answerfile(xmldoc)

    @staticmethod
    def generate(location):
        ret, out, err = scripts.run_script(location, 'answerfile')
        if ret != 0:
            raise AnswerfileException, "Generator script failed:\n\n%s" % err

        try:
            xmldoc = xml.dom.minidom.parseString(out)
        except:
            raise AnswerfileException, "Generator script returned incorrectly formatted output."

        return Answerfile(xmldoc)

    def processAnswerfile(self):
        xelogging.log("Processing XML answerfile for %s." % self.operation)
        if self.operation == 'installation':
            install_type = getStrAttribute(self.top_node, ['mode'], default = 'fresh')
            if install_type == "fresh":
                results = self.parseFreshInstall()
            elif install_type == "reinstall":
                results = self.parseReinstall()
            elif install_type == "upgrade":
                results = self.parseUpgrade()
            else:
                raise AnswerfileException, "Unknown mode, %s" % install_type

            results.update(self.parseCommon())
        elif self.operation == 'restore':
            # FIXME add restore support
            pass
        
        return results

    def parseScripts(self):

        def buildURL(stype, path):
            if stype == 'nfs':
                return 'nfs://'+path
            return path
        
        # new format
        script_nodes = getElementsByTagName(self.top_node, ['script'])
        for node in script_nodes:
            stage = getStrAttribute(node, ['stage'], mandatory = True).lower()
            stype = getStrAttribute(node, ['type'], mandatory = True).lower()
            script = buildURL(stype, getText(node))
            scripts.add_script(stage, script)

        # depreciated formats
        nodes = getElementsByTagName(self.top_node, ['post-install-script'])
        if len(nodes) == 1:
            scripts.add_script('filesystem-populated', getText(nodes[0]))
        nodes = getElementsByTagName(self.top_node, ['install-failed-script'])
        if len(nodes) == 1:
            scripts.add_script('installation-complete', getText(nodes[0]))
        return {}

    def parseFreshInstall(self):
        results = {}

        results['install-type'] = INSTALL_TYPE_FRESH
        results['preserve-settings'] = False
        results['backup-existing-installation'] = False

        # initial-partitions:
        nodes = getElementsByTagName(self.top_node, ['initial-partitions'])
        if len(nodes) > 0:
            results['initial-partitions'] = []
            for node in getElementsByTagName(nodes[0], ['partition']):
                try:
                    part = {}
                    for k in ('number', 'size', 'id'):
                        part[k] = getIntAttribute(node, [k], mandatory = True)
                    results['initial-partitions'].append(part)
                except:
                    pass

        results.update(self.parseDisks())
        results.update(self.parseInterface())
        results.update(self.parseRootPassword())
        results.update(self.parseNSConfig())
        results.update(self.parseTimeConfig())
        results.update(self.parseKeymap())

        return results

    def parseReinstall(self):
        # identical to fresh install except backup existing
        results = self.parseFreshInstall()
        results['backup-existing-installation'] = True
        return results

    def parseUpgrade(self):
        results = {}

        results['install-type'] = INSTALL_TYPE_REINSTALL
        results['preserve-settings'] = True
        results['backup-existing-installation'] = True
        results.update(self.parseExistingInstallation())

        # FIXME - obsolete?
        nodes = getElementsByTagName(self.top_node, ['primary-disk'])
        if len(nodes) == 1:
            disk = normalize_disk(getText(nodes[0]))

            # If answerfile names a multipath replace with the master!
            master = disktools.getMpathMaster(disk)
            if master:
                disk = master
            results['primary-disk'] = disk

        return results

    def parseCommon(self):
        results = {};

        results.update(self.parseSource())
        results.update(self.parseDriverSource())

        nodes = getElementsByTagName(self.top_node, ['network-backend'])
        if len(nodes) > 0:
            network_backend = getText(nodes[0])
            if network_backend == NETWORK_BACKEND_BRIDGE:
                results['network-backend'] = NETWORK_BACKEND_BRIDGE
            elif network_backend in [NETWORK_BACKEND_VSWITCH, NETWORK_BACKEND_VSWITCH_ALT]:
                results['network-backend'] = NETWORK_BACKEND_VSWITCH

        nodes = getElementsByTagName(self.top_node, ['bootloader'])
        if len(nodes) > 0:
            results['bootloader-location'] = getMapAttribute(nodes[0], ['location'],
                                                             [('mbr', BOOT_LOCATION_MBR),
                                                              ('partition', BOOT_LOCATION_PARTITION)],
                                                             default = 'mbr')
            if getText(nodes[0]) != 'extlinux':
                raise AnswerfileException, "Unsupported bootloader '%s'" % getText(nodes[0])
            
        return results

    def parseExistingInstallation(self):
        results = {}

        inst = getElementsByTagName(self.top_node, ['existing-installation'],
                                    mandatory = True)
        disk = normalize_disk(getText(inst[0]))

        # If answerfile names a multipath replace with the master!
        master = disktools.getMpathMaster(disk)
        if master:
            disk = master

        results['primary-disk'] = disk

        installations = product.findXenSourceProducts()
        installations = filter(lambda x: x.primary_disk == disk or diskutil.idFromPartition(x.primary_disk) == disk, installations)
        if len(installations) == 0:
            raise AnswerfileException, "Could not locate the installation specified to be reinstalled."
        elif len(installations) > 1:
            # FIXME non-multipath case?
            xelogging.log("Warning: multiple paths detected - recommend use of --device_mapper_multipath=yes")
            xelogging.log("Warning: selecting 1st path from %s" % str(map(lambda x: x.primary_disk, installations)))
        results['installation-to-overwrite'] = installations[0]
        return results
    
    def parseSource(self):
        results = {}
        source = getElementsByTagName(self.top_node, ['source'], mandatory = True)[0]
        rtype = getStrAttribute(source, ['type'], mandatory = True)

        if rtype == 'local':
            address = "Install disc"
        elif rtype in ['url', 'nfs']:
            address = getText(source)
        else:
            raise AnswerfileException, "Invalid type for <source> media specified."
        if rtype == 'url' and address.startswith('nfs://'):
            rtype = 'nfs'
            address = address[6:]

        results['source-media'] = rtype
        results['source-address'] = address

        return results

    def parseDriverSource(self):
        results = {}
        for source in getElementsByTagName(self.top_node, ['driver-source']):
            if not results.has_key('extra-repos'):
                results['extra-repos'] = []

            rtype = getStrAttribute(source, ['type'], mandatory = True)
            if rtype == 'local':
                address = "Install disc"
            elif rtype in ['url', 'nfs']:
                address = getText(source)
            else:
                raise AnswerfileException, "Invalid type for <driver-source> media specified."
            if rtype == 'url' and address.startswith('nfs://'):
                rtype = 'nfs'
                address = address[6:]
                
            results['extra-repos'].append((rtype, address, []))
        return results

    def parseDisks(self):
        results = {}

        # Primary disk (installation)
        node = getElementsByTagName(self.top_node, ['primary-disk'], mandatory = True)[0]
        results['preserve-first-partition'] = \
                                            getMapAttribute(node, ['preserve-first-partition'],
                                                            [('true', 'true'),
                                                             ('yes', 'true'),
                                                             ('false', 'false'),
                                                             ('no', 'false'),
                                                             ('if-utility', PRESERVE_IF_UTILITY)],
                                                            default = 'if-utility')
        if len(getElementsByTagName(self.top_node, ['zap-utility-partitions'])) > 0:
            results['preserve-first-partition'] = 'false'
        primary_disk = normalize_disk(getText(node))

        # If we're using multipath and the answerfile names a multipath
        # slave, then we want to install to the master!
        master = disktools.getMpathMaster(primary_disk)
        if master:
            primary_disk = master
        results['primary-disk'] = primary_disk

        inc_primary = getBoolAttribute(node, ['guest-storage', 'gueststorage'],
                                       default = True)
        results['sr-at-end'] = getBoolAttribute(node, ['sr-at-end'], default = True)

        # Guest disk(s) (Local SR)
        results['guest-disks'] = []
        if inc_primary:
            results['guest-disks'].append(primary_disk)
        for node in getElementsByTagName(self.top_node, ['guest-disk']):
            disk = normalize_disk(getText(node))
            # Replace references to multipath slaves with references to their multipath masters
            master = disktools.getMpathMaster(disk)
            if master:
                # CA-38329: disallow device mapper nodes (except primary disk) as these won't exist
                # at XenServer boot and therefore cannot be added as physical volumes to Local SR.
                # Also, since the DM nodes are multipathed SANs it doesn't make sense to include them
                # in the "Local" SR.
                if master != primary_disk:
                    raise AnswerfileException, "Answerfile specifies non-local disk %s to add to Local SR" % disk
                disk = master
            results['guest-disks'].append(disk)

        results['sr-type'] = getMapAttribute(self.top_node, ['sr-type', 'srtype'],
                                             [('lvm', SR_TYPE_LVM),
                                              ('ext', SR_TYPE_EXT)], default = 'lvm')
        return results

    def parseInterface(self):
        results = {}
        node = getElementsByTagName(self.top_node, ['admin-interface'], mandatory = True)[0]
        nethw = netutil.scanConfiguration()
        if_hwaddr = None

        if_name = getStrAttribute(node, ['name'])
        if if_name and if_name in nethw:
            if_hwaddr = nethw[if_name].hwaddr
        else:
            if_hwaddr = getStrAttribute(node, ['hwaddr'])
            if if_hwaddr:
                matching_list = filter(lambda x: x.hwaddr == if_hwaddr.lower(), nethw.values())
                if len(matching_list) == 1:
                    if_name = matching_list[0].name
        if not if_name and not if_hwaddr:
             raise AnswerfileException, "<admin-interface> tag must have one of 'name' or 'hwaddr'"

        results['net-admin-interface'] = if_name

        proto = getStrAttribute(node, ['proto'], mandatory = True)
        if proto == 'static':
            ip = getText(getElementsByTagName(node, ['ip', 'ipaddr'], mandatory = True)[0])
            subnet = getText(getElementsByTagName(node, ['subnet-mask', 'subnet'], mandatory = True)[0])
            gateway = getText(getElementsByTagName(node, ['gateway'], mandatory = True)[0])
            results['net-admin-configuration'] = NetInterface(NetInterface.Static, if_hwaddr, ip, subnet, gateway, dns=None)
        elif proto == 'dhcp':
            results['net-admin-configuration'] = NetInterface(NetInterface.DHCP, if_hwaddr)
        else:
            results['net-admin-configuration'] = NetInterface(None, if_hwaddr)

        protov6 = getStrAttribute(node, ['protov6'])
        if protov6 == 'static':
            ipv6 = getText(getElementsByTagName(node, ['ipv6'], mandatory = True)[0])
            gatewayv6 = getText(getElementsByTagName(node, ['gatewayv6'], mandatory = True)[0])
            results['net-admin-configuration'].addIPv6(NetInterface.Static, ipv6, gatewayv6)
        elif protov6 == 'dhcp':
            results['net-admin-configuration'].addIPv6(NetInterface.DHCP)
        elif protov6 == 'autoconf':
            results['net-admin-configuration'].addIPv6(NetInterface.Autoconf)

        if not results['net-admin-configuration'].valid():
            raise AnswerfileException, "<admin-interface> tag must have IPv4 or IPv6 defined."
        return results

    def parseRootPassword(self):
        results = {}
        nodes = getElementsByTagName(self.top_node, ['root-password'])
        if len(nodes) > 0:
            pw_type = getMapAttribute(nodes[0], ['type'], [('plaintext', 'plaintext'),
                                                           ('hash', 'pwdhash')],
                                      default = 'plaintext')
            results['root-password'] = (pw_type, getText(nodes[0]))
        return results

    def parseNSConfig(self):
        results = {}
        nodes = getElementsByTagName(self.top_node, ['name-server', 'nameserver'])
        results['manual-nameservers'] = (len(nodes) > 0, map(lambda x: getText(x), nodes))
        nodes = getElementsByTagName(self.top_node, ['hostname'])
        if len(nodes) > 0:
            results['manual-hostname'] = (True, getText(nodes[0]))
        else:
            results['manual-hostname'] = (False, None)
        return results

    def parseTimeConfig(self):
        results = {}

        nodes = getElementsByTagName(self.top_node, ['timezone'])
        if len(nodes) > 0:
            results['timezone'] = getText(nodes[0])

        nodes = getElementsByTagName(self.top_node, ['ntp-server', 'ntp-servers'])
        results['ntp-servers'] = map(lambda x: getText(x), nodes)
        results['time-config-method'] = 'ntp'

        return results

    def parseKeymap(self):
        results = {}
        nodes = getElementsByTagName(self.top_node, ['keymap'])
        if len(nodes) > 0:
            results['keymap'] = getText(nodes[0])
        return results
