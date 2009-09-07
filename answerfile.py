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
from netinterface import *
import os
import stat
import xml.dom.minidom

class AnswerfileError(Exception):
    pass

# get text from a node:
def getText(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc.encode()


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
        xelogging.log("Fetching answerfile generator from %s" % location)
        util.fetchFile(location, constants.ANSWERFILE_GENERATOR_PATH)
        os.chmod(constants.ANSWERFILE_GENERATOR_PATH, stat.S_IRUSR | stat.S_IXUSR)

        # check the interpreter
        f = open(constants.ANSWERFILE_GENERATOR_PATH)
        line = f.readline()
        f.close()

        if not line.startswith('#!'):
            raise AnswerfileError, "Missing interpreter in generator script."
        interp = line[2:].split()
        if interp[0] == '/usr/bin/env':
            if interp[1] not in ['python']:
                raise AnswerfileError, "Invalid interpreter %s in generator script." % interp[1]
        elif interp[0] not in ['/bin/sh', '/bin/bash', 'usr/bin/python']:
            raise AnswerfileError, "Invalid interpreter %s in generator script." % interp[0]

        ret, out, err = util.runCmd2(constants.ANSWERFILE_GENERATOR_PATH, with_stdout = True, with_stderr = True)
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
        elif install_type == "oemhdd":
            results = self.parseOemHdd()
        elif install_type == "oemflash":
            results = self.parseOemFlash()
            
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

        # primary-disk:
        results['primary-disk'] = "/dev/%s" % getText(self.nodelist.getElementsByTagName('primary-disk')[0].childNodes)
        pd_has_guest_storage = True and self.nodelist.getElementsByTagName('primary-disk')[0].getAttribute("gueststorage").lower() in ["", "yes", "true"]

        # guest-disks:
        results['guest-disks'] = []
        if pd_has_guest_storage:
            results['guest-disks'].append(results['primary-disk'])
        for disk in self.nodelist.getElementsByTagName('guest-disk'):
            results['guest-disks'].append("/dev/%s" % getText(disk.childNodes))

        results.update(self.parseSource())
        results.update(self.parseDriverSource())
        results.update(self.parseInterfaces())
        results.update(self.parseRootPassword())
        results.update(self.parseNSConfig())
        results.update(self.parseTimeConfig())
        results.update(self.parseKeymap())
        results.update(self.parseScripts())
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
        results.update(self.parseScripts())
        results.update(self.parseBootloader())

        return results

    def parseUpgrade(self):
        results = {}

        results['install-type'] = constants.INSTALL_TYPE_REINSTALL
        results.update(self.parseExistingInstallation())
        results['preserve-settings'] = True
        results['backup-existing-installation'] = True

        results.update(self.parseSource())
        results.update(self.parseDriverSource())
        results.update(self.parseScripts())
        results.update(self.parseBootloader())

        return results

    def parseOemHdd(self):
        results = {}

        results['install-type'] = constants.INSTALL_TYPE_FRESH

        # storage type (lvm or ext):
        srtype_node = self.nodelist.getAttribute("srtype")
        if srtype_node in ['', 'lvm']:
            srtype = constants.SR_TYPE_LVM
        elif srtype_node in ['ext']:
            srtype = constants.SR_TYPE_EXT
        else:
            raise AnswerfileError, "Specified SR Type unknown.  Should be 'lvm' or 'ext'."
        results['sr-type'] = srtype

        # primary-disk:
        results['primary-disk'] = "/dev/%s" % getText(self.nodelist.getElementsByTagName('primary-disk')[0].childNodes)
        pd_has_guest_storage = True and self.nodelist.getElementsByTagName('primary-disk')[0].getAttribute("gueststorage").lower() in ["", "yes", "true"]

        # guest-disks:
        results['guest-disks'] = []
        if pd_has_guest_storage:
            results['guest-disks'].append(results['primary-disk'])
        for disk in self.nodelist.getElementsByTagName('guest-disk'):
            results['guest-disks'].append("/dev/%s" % getText(disk.childNodes))

        results.update(self.parseSource())
        try:
            results.update(self.parseInterfaces())
        except IndexError:
            # Don't configure the admin interface if not specified in answerfile
            pass
        results.update(self.parseOemSource())
        results.update(self.parseScripts())

        rw = self.nodelist.getElementsByTagName('rootfs-writable')
        if len(rw) == 1:
            results['rootfs-writable'] = True

        return results

    def parseOemFlash(self):
        results = {}

        # primary-disk:
        results['primary-disk'] = "/dev/%s" % getText(self.nodelist.getElementsByTagName('primary-disk')[0].childNodes)
        results.update(self.parseOemSource())
        results.update(self.parseScripts())

        # guest-disks:
        results['guest-disks'] = []
        results['sr-type'] = constants.SR_TYPE_LVM
        return results


### -- code to parse individual parts of the answerfile past this point.

    def parseScripts(self):
        results = {}
        pis_nodes = self.nodelist.getElementsByTagName('post-install-script')
        if len(pis_nodes) == 1:
            results['post-install-script'] = getText(pis_nodes[0].childNodes)
        ifs_nodes = self.nodelist.getElementsByTagName('install-failed-script')
        if len(ifs_nodes) == 1:
            results['install-failed-script'] = getText(ifs_nodes[0].childNodes)
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
        results['root-password'] = getText(self.nodelist.getElementsByTagName('root-password')[0].childNodes)
        results['root-password-type'] = 'plaintext'
        return results

    def parseExistingInstallation(self):
        results = {}
        if len(self.nodelist.getElementsByTagName('existing-installation')) == 0:
            raise AnswerfileError, "No existing installation specified."
        disk = "/dev/" + getText(self.nodelist.getElementsByTagName('existing-installation')[0].childNodes)
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

    def parseOemSource(self):
        results = {}
        if len(self.nodelist.getElementsByTagName('source')) == 0:
            raise AnswerfileError, "No OEM image specified."
        source = self.nodelist.getElementsByTagName('source')[0]
        if source.getAttribute('type') == 'local':
            results['source-media'] = 'local'
            results['source-address'] = getText(source.childNodes)
        elif source.getAttribute('type') == 'url':
            results['source-media'] = 'url'
            results['source-address'] = getText(source.childNodes)
        elif source.getAttribute('type') == 'nfs':
            results['source-media'] = 'nfs'
            results['source-address'] = getText(source.childNodes)
        else:
            raise AnswerfileError, "No media for OEM image specified."

        if len(self.nodelist.getElementsByTagName('xenrt')) != 0:
            xenrt = self.nodelist.getElementsByTagName('xenrt')[0]
            if xenrt.getAttribute('scorch').lower() != 'false':
                results['xenrt-scorch'] = True
            serport = xenrt.getAttribute('serial')
            if serport:
                results['xenrt-serial'] = str(serport)
            results['xenrt'] = getText(xenrt.childNodes)

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
            results['extra-repos'].append((source.getAttribute('type'), address))
        return results
