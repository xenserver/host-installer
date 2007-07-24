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

import xml.dom.minidom

class AnswerfileError(Exception):
    pass

def processAnswerfile(location):
    """ Downloads an answerfile from 'location' -- this is in the URL format
    used by fetchFile in the util module (which also permits fetching over
    NFS).  Returns answers ready for the backend to process. """

    xelogging.log("Fetching answerfile from %s" % location)
    util.fetchFile(location, '/tmp/answerfile')

    xmldoc = xml.dom.minidom.parse('/tmp/answerfile')
    n = xmldoc.documentElement

    xelogging.log("Importing XML answerfile.")

    # fresh install or upgrade?
    install_type = n.getAttribute("mode")
    if install_type in ['', 'fresh']:
        results = parseFreshInstall(n)
    elif install_type == "reinstall":
        results = parseReinstall(n)
    elif install_type == "upgrade":
        results = parseUpgrade(n)

    return results

# get text from a node:
def getText(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc.encode()

def parseFreshInstall(n):
    """ n is the top-level document node of the answerfile.  Parses the
    answerfile if it is for a fresh install. """
    results = {}

    results['install-type'] = constants.INSTALL_TYPE_FRESH
    results['preserve-settings'] = False

    # storage type (lvm or ext):
    srtype_node = n.getAttribute("srtype")
    if srtype_node in ['', 'lvm']:
        srtype = constants.SR_TYPE_LVM
    elif srtype_node in ['ext']:
        srtype = constants.SR_TYPE_EXT
    else:
        raise RuntimeError, "Specified SR Type unknown.  Should be 'lvm' or 'ext'"
    results['sr-type'] = srtype

    # primary-disk:
    results['primary-disk'] = "/dev/%s" % getText(n.getElementsByTagName('primary-disk')[0].childNodes)
    pd_has_guest_storage = True and n.getElementsByTagName('primary-disk')[0].getAttribute("gueststorage").lower() in ["", "yes", "true"]

    # guest-disks:
    results['guest-disks'] = []
    if pd_has_guest_storage:
        results['guest-disks'].append(results['primary-disk'])
    for disk in n.getElementsByTagName('guest-disk'):
        results['guest-disks'].append("/dev/%s" % getText(disk.childNodes))

    results.update(parseSource(n))
    results.update(parseInterfaces(n))
    results.update(parseRootPassword(n))
    results.update(parseNSConfig(n))
    results.update(parseTimeConfig(n))
    results.update(parseKeymap(n))
    results.update(parseScripts(n))

    return results

def parseReinstall(n):
    results = {}

    results['install-type'] = constants.INSTALL_TYPE_REINSTALL
    results.update(parseExistingInstallation(n))
    results['preserve-settings'] = False
    results['backup-existing-installation'] = True

    results.update(parseSource(n))
    results.update(parseInterfaces(n))
    results.update(parseRootPassword(n))
    results.update(parseNSConfig(n))
    results.update(parseTimeConfig(n))
    results.update(parseKeymap(n))
    results.update(parseScripts(n))

    return results

def parseUpgrade(n):
    results = {}

    results['install-type'] = constants.INSTALL_TYPE_REINSTALL
    results.update(parseExistingInstallation(n))
    results['preserve-settings'] = True
    results['backup-existing-installation'] = False

    results.update(parseSource(n))
    results.update(parseInterfaces(n))
    results.update(parseScripts(n))

    return results

### -- code to parse individual parts of the answerfile past this point.

def parseScripts(n):
    results = {}
    pis_nodes = n.getElementsByTagName('post-install-script')
    if len(pis_nodes) == 1:
        results['post-install-script'] = getText(n.getElementsByTagName('post-install-script')[0].childNodes)
    return results

def parseKeymap(n):
    results = {}
    keymap_nodes = n.getElementsByTagName('keymap')
    if len(keymap_nodes) == 1:
        results['keymap'] = getText(keymap_nodes[0].childNodes)
    else:
        xelogging.log("No keymap specified in answer file: defaulting to 'us'")
        results['keymap'] = "us"
    return results

def parseTimeConfig(n):
    results = {}
    results['timezone'] = getText(n.getElementsByTagName('timezone')[0].childNodes)

    # ntp-servers:
    results['ntp-servers'] = []
    for disk in n.getElementsByTagName('ntp-servers'):
        results['ntp-servers'].append(getText(disk.childNodes))
    results['time-config-method'] = 'ntp'

    return results

def parseNSConfig(n):
    results = {}
    mnss = n.getElementsByTagName('nameserver')
    if len(mnss) == 0:
        # no manual nameservers:
        results['manual-nameservers'] = (False, [])
    else:
        nameservers = []
        for nameserver in mnss:
            nameservers.append(getText(nameserver.childNodes))
        results['manual-nameservers'] = (True, nameservers)

    # manual-hostname:
    mhn = n.getElementsByTagName('hostname')
    if len(mhn) == 1:
        results['manual-hostname'] = (True, getText(mhn[0].childNodes))
    else:
        results['manual-hostname'] = (False, None)
    return results

def parseRootPassword(n):
    results = {}
    results['root-password'] = getText(n.getElementsByTagName('root-password')[0].childNodes)
    results['root-password-type'] = 'plaintext'
    return results

def parseExistingInstallation(n):
    results = {}
    disk = "/dev/" + getText(n.getElementsByTagName('existing-installation')[0].childNodes)
    installations = product.findXenSourceProducts()
    installations = filter(lambda x: x.primary_disk == disk, installations)
    if len(installations) != 1:
        raise AnswerfileError, "Could not locate the installation specified to be reinstalled."
    results['installation-to-overwrite'] = installations[0]
    return results

def parseInterfaces(n):
    results = {}
    netifnode = n.getElementsByTagName('admin-interface')[0]
    results['net-admin-interface'] = netifnode.getAttribute('name')
    proto = netifnode.getAttribute('proto')
    if proto == 'static':
        ip = getText(netifnode.getElementsByTagName('ip')[0].childNodes)
        subnetmask = getText(netifnode.getElementsByTagName('subnet-mask')[0].childNodes)
        gateway = getText(netifnode.getElementsByTagName('gateway')[0].childNodes)
        results['net-admin-configuration'] = { 'use-dhcp' : False ,
                    'enabled' : True,
                    'ip' : ip,
                    'subnet-mask' : subnetmask,
                    'gateway' : gateway }
    elif proto == 'dhcp':
        results['net-admin-configuration'] = { 'use-dhcp' : True, 'enabled' : True }
    return results

def parseSource(n):
    results = {}
    if len(n.getElementsByTagName('source')) == 0:
        raise AnswerfileError, "No source media sepcified."
    source = n.getElementsByTagName('source')[0]
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
