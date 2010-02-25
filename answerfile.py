# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Read XML answerfiles.
#
# written by Andrew Peace

import util
import constants
import product
import xelogging
import netutil
import diskutil
import disktools
from netinterface import *
import os
import stat
import xml.dom.minidom
import scripts

class AnswerfileError(Exception):
    pass

# get text from a node:
def getText(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc.encode()

def normalize_disk(disk):
    if not disk.startswith('/dev/'):
        disk = '/dev/' + disk
    return diskutil.partitionFromId(disk)


class Answerfile:

    def __init__(self, location = None, xmldoc = None):
        assert location != None or xmldoc != None
        if location:
            xelogging.log("Fetching answerfile from %s" % location)
            util.fetchFile(location, constants.ANSWERFILE_PATH)
            
            try:
                xmldoc = xml.dom.minidom.parse(constants.ANSWERFILE_PATH)
            except:
                raise AnswerfileError, "Answerfile is incorrectly formatted."

        self.nodelist = xmldoc.documentElement

    @staticmethod
    def generate(location):
        ret, out, err = scripts.run_script(location, 'answerfile')
        if ret != 0:
            raise AnswerfileError, "Generator script failed:\n\n%s" % err

        try:
            xmldoc = xml.dom.minidom.parseString(out)
        except:
            raise AnswerfileError, "Generator script returned incorrectly formatted output."

        return Answerfile(xmldoc = xmldoc)

    def processAnswerfile(self):
        """ Downloads an answerfile from 'location' -- this is in the URL format
        used by fetchFile in the util module (which also permits fetching over
        NFS).  Returns answers ready for the backend to process. """

        xelogging.log("Importing XML answerfile.")

        # fresh install or upgrade?
        install_type = self.nodelist.getAttribute("mode")
        if install_type in ['', 'fresh']:
            results = self.parseFreshInstall()
        elif install_type == "reinstall":
            results = self.parseReinstall()
        elif install_type == "upgrade":
            results = self.parseUpgrade()

        nb_nodes = self.nodelist.getElementsByTagName('network-backend')
        if len(nb_nodes) == 1:
            network_backend = getText(nb_nodes[0].childNodes)
            if network_backend == constants.NETWORK_BACKEND_BRIDGE:
                results['network-backend'] = constants.NETWORK_BACKEND_BRIDGE
            elif network_backend == constants.NETWORK_BACKEND_VSWITCH:
                results['network-backend'] = constants.NETWORK_BACKEND_VSWITCH
            else:
                raise AnswerfileError, "Specified Network backend type \"%s\" unknown." % network_backend
        else:
            results['network-backend'] = constants.NETWORK_BACKEND_DEFAULT
        
        return results

    def parseFreshInstall(self):
        results = {}

        results['install-type'] = constants.INSTALL_TYPE_FRESH
        results['preserve-settings'] = False

        # storage type (lvm or ext):
        srtype_node = self.nodelist.getAttribute("srtype")
        if srtype_node in ['', 'lvm']:
            srtype = constants.SR_TYPE_LVM
        elif srtype_node in ['ext']:
            srtype = constants.SR_TYPE_EXT
        else:
            raise AnswerfileError, "Specified SR Type unknown.  Should be 'lvm' or 'ext'."
        results['sr-type'] = srtype

        # initial-partitions:
        results['initial-partitions'] = []
        init_part_nodes = self.nodelist.getElementsByTagName('initial-partitions')
        if len(init_part_nodes) == 1:
            for part_node in init_part_nodes[0].getElementsByTagName('partition'):
                try:
                    part = {}
                    for k in ('number', 'size', 'id'):
                        part[k] = int(part_node.getAttribute(k), 0)
                    results['initial-partitions'].append(part)
                except:
                    pass

        # primary-disk:
        pd = self.nodelist.getElementsByTagName('primary-disk')
        disk = normalize_disk(getText(pd[0].childNodes))

        # If we're using multipath and the answerfile names a multipath
        # slave, then we want to install to the master!
        master = disktools.getMpathMaster(disk)
        if master:
            disk = master
        results['primary-disk'] = disk

        pd_has_guest_storage = pd[0].getAttribute("gueststorage").lower() in ["", "yes", "true"]
        results['sr-at-end'] = pd[0].getAttribute("sr-at-end").lower() in ["", "yes", "true"]

        # guest-disks:
        results['guest-disks'] = []
        if pd_has_guest_storage:
            results['guest-disks'].append(results['primary-disk'])
        for disk in self.nodelist.getElementsByTagName('guest-disk'):
            results['guest-disks'].append(normalize_disk(getText(disk.childNodes)))

        results.update(self.parseSource())
        results.update(self.parseDriverSource())
        results.update(self.parseInterfaces())
        results.update(self.parseRootPassword())
        results.update(self.parseNSConfig())
        results.update(self.parseTimeConfig())
        results.update(self.parseKeymap())
        results.update(self.parseBootloader())

        return results

    def parseReinstall(self):
        results = {}

        results['install-type'] = constants.INSTALL_TYPE_REINSTALL
        results.update(self.parseExistingInstallation())
        results['preserve-settings'] = False
        results['backup-existing-installation'] = True

        results.update(self.parseSource())
        results.update(self.parseDriverSource())
        results.update(self.parseInterfaces())
        results.update(self.parseRootPassword())
        results.update(self.parseNSConfig())
        results.update(self.parseTimeConfig())
        results.update(self.parseKeymap())
        results.update(self.parseBootloader())

        return results

    def parseUpgrade(self):
        results = {}

        results['install-type'] = constants.INSTALL_TYPE_REINSTALL
        results.update(self.parseExistingInstallation())
        results['preserve-settings'] = True
        results['backup-existing-installation'] = True

        target_nodes = self.nodelist.getElementsByTagName('primary-disk')
        if len(target_nodes) == 1:
            disk = normalize_disk(getText(target_nodes[0].childNodes))

            # If answerfile names a multipath replace with the master!
            master = disktools.getMpathMaster(disk)
            if master:
                disk = master
            results['primary-disk'] = disk

        results.update(self.parseSource())
        results.update(self.parseDriverSource())
        results.update(self.parseBootloader())

        return results


### -- code to parse individual parts of the answerfile past this point.

    def parseScripts(self):
        results = {}
        
        # new format
        script_nodes = self.nodelist.getElementsByTagName('script')
        for node in script_nodes:
            stage = node.getAttribute("stage").lower()
            script = getText(node.childNodes)
            scripts.add_script(stage, script)

        pis_nodes = self.nodelist.getElementsByTagName('post-install-script')
        if len(pis_nodes) == 1:
            script = getText(pis_nodes[0].childNodes)
            scripts.add_script('filesystem-populated', script)
        ifs_nodes = self.nodelist.getElementsByTagName('install-failed-script')
        if len(ifs_nodes) == 1:
            script = getText(ifs_nodes[0].childNodes)
            scripts.add_script('installation-complete', script)

        return results

    def parseKeymap(self):
        results = {}
        keymap_nodes = self.nodelist.getElementsByTagName('keymap')
        if len(keymap_nodes) == 1:
            results['keymap'] = getText(keymap_nodes[0].childNodes)
        else:
            xelogging.log("No keymap specified in answer file: defaulting to 'us'")
            results['keymap'] = "us"
        return results

    def parseBootloader(self):
        results = {}
        keymap_nodes = self.nodelist.getElementsByTagName('bootloader')
        if len(keymap_nodes) == 1:
            bootloader = getText(keymap_nodes[0].childNodes)
            if bootloader == "grub":
                results['bootloader'] = constants.BOOTLOADER_TYPE_GRUB
            elif bootloader == "extlinux":
                results['bootloader'] = constants.BOOTLOADER_TYPE_EXTLINUX
            else:
                xelogging.log("Unknown bootloader %s specified in answer file" % bootloader)

            location = keymap_nodes[0].getAttribute("location").lower()
            if location == 'partition':
                results['bootloader-location'] = 'partition'
            elif location in [ 'mbr', '' ]:
                results['bootloader-location'] = 'mbr'
            else:
                xelogging.log("Unknown bootloader location %s specified in answer file" % location)
        else:
            xelogging.log("No bootloader specified in answer file.")

        return results

    def parseTimeConfig(self):
        results = {}
        results['timezone'] = getText(self.nodelist.getElementsByTagName('timezone')[0].childNodes)

        # ntp-servers:
        results['ntp-servers'] = []
        for disk in self.nodelist.getElementsByTagName('ntp-servers'):
            results['ntp-servers'].append(getText(disk.childNodes))
        results['time-config-method'] = 'ntp'

        return results

    def parseNSConfig(self):
        results = {}
        mnss = self.nodelist.getElementsByTagName('nameserver')
        if len(mnss) == 0:
            # no manual nameservers:
            results['manual-nameservers'] = (False, [])
        else:
            nameservers = []
            for nameserver in mnss:
                nameservers.append(getText(nameserver.childNodes))
            results['manual-nameservers'] = (True, nameservers)

        # manual-hostname:
        mhn = self.nodelist.getElementsByTagName('hostname')
        if len(mhn) == 1:
            results['manual-hostname'] = (True, getText(mhn[0].childNodes))
        else:
            results['manual-hostname'] = (False, None)
        return results

    def parseRootPassword(self):
        results = {}
        rp = self.nodelist.getElementsByTagName('root-password')
        if len(rp) == 0:
            # set up at first boot
            results['root-password'] = ('pwdhash', '!!')
        else:
            pw_type = rp[0].getAttribute("type")
            if pw_type in ['', 'plaintext']:
                results['root-password'] = ('plaintext', getText(rp[0].childNodes))
            elif pw_type == 'hash':
                results['root-password'] = ('pwdhash', getText(rp[0].childNodes))
            else:
                raise AnswerfileError, "Invalid type for root-password specified."
        return results

    def parseExistingInstallation(self):
        results = {}
        if len(self.nodelist.getElementsByTagName('existing-installation')) == 0:
            raise AnswerfileError, "No existing installation specified."
        disk = "/dev/" + getText(self.nodelist.getElementsByTagName('existing-installation')[0].childNodes)

        # If answerfile names a multipath replace with the master!
        master = disktools.getMpathMaster(disk)
        if master:
            disk = master

        results['primary-disk'] = disk

        installations = product.findXenSourceProducts()
        installations = filter(lambda x: x.primary_disk == disk or diskutil.idFromPartition(x.primary_disk) == disk, installations)
        if len(installations) != 1:
            raise AnswerfileError, "Could not locate the installation specified to be reinstalled."
        results['installation-to-overwrite'] = installations[0]
        return results

    def parseInterfaces(self):
        """ Parse the admin-interface element.  This has either name="eth0" or
        hwaddr="x:y:z.." to identify the interface to use, then an IP configuration
        which is either proto="dhcp" or proto="static" ip="..." subnet-mask="..."
        gateway="..." dns="..."."""

        results = {}
        netifnode = self.nodelist.getElementsByTagName('admin-interface')[0]

        # allow interfaces to be specified by either hardware address or name - find
        # out the value to both variables:
        nethw = netutil.scanConfiguration()
        requested_hwaddr = None
        requested_name = None
        if netifnode.getAttribute('name'):
            requested_name = netifnode.getAttribute('name')
            if nethw.has_key(requested_name):
                requested_hwaddr = nethw[requested_name].hwaddr
            else:
                raise AnswerfileError, "Interface %s not found." % requested_name
        elif netifnode.getAttribute('hwaddr'):
            requested_hwaddr = netifnode.getAttribute('hwaddr').lower()
            # work out which device corresponds to the hwaddr we were given:
            matching_list = filter(lambda x: x.hwaddr == requested_hwaddr, nethw.values())
            if len(matching_list) == 1:
                requested_name = matching_list[0].name
            else:
                raise AnswerfileError, "%d interfaces matching the MAC specified for the management interface." % (len(matching_list))

        assert requested_name and requested_hwaddr
        results['net-admin-interface'] = requested_name

        proto = netifnode.getAttribute('proto')
        if proto == 'static':
            ip = getText(netifnode.getElementsByTagName('ip')[0].childNodes)
            subnetmask = getText(netifnode.getElementsByTagName('subnet-mask')[0].childNodes)
            gateway = getText(netifnode.getElementsByTagName('gateway')[0].childNodes)
            results['net-admin-configuration'] = NetInterface(NetInterface.Static, requested_hwaddr, ip, subnetmask, gateway, dns=None)
        elif proto == 'dhcp':
            results['net-admin-configuration'] = NetInterface(NetInterface.DHCP, requested_hwaddr)
        else:
            raise AnswerfileError, "<admin-interface> tag must have attribute proto='static' or proto='dhcp'."
        return results

    def parseSource(self):
        results = {}
        if len(self.nodelist.getElementsByTagName('source')) == 0:
            raise AnswerfileError, "No source media specified."
        source = self.nodelist.getElementsByTagName('source')[0]
        if source.getAttribute('type') == 'local':
            results['source-media'] = 'local'
            results['source-address'] = "Install disc"
        elif source.getAttribute('type') == 'url':
            results['source-media'] = 'url'
            results['source-address'] = getText(source.childNodes)
        elif source.getAttribute('type') == 'nfs':
            results['source-media'] = 'nfs'
            results['source-address'] = getText(source.childNodes)
        else:
            raise AnswerfileError, "No source media specified."
        return results

    def parseDriverSource(self):
        results = {}
        for source in self.nodelist.getElementsByTagName('driver-source'):
            if not results.has_key('extra-repos'):
                results['extra-repos'] = []

            if source.getAttribute('type') == 'local':
                address = "Install disc"
            elif source.getAttribute('type') in ['url', 'nfs']:
                address = getText(source.childNodes)
            else:
                raise AnswerfileError, "Invalid type for driver-source media specified."
            results['extra-repos'].append((source.getAttribute('type'), address, []))
        return results
