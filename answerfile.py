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
import xml.dom.minidom
from xml.dom.minidom import parse

import xelogging

def processAnswerfile(location):
    """ Downloads an answerfile from 'location' -- this is in the URL format
    used by fetchFile in the util module (which also permits fetching over
    NFS).  Returns answers ready for the backend to process. """

    xelogging.log("Fetching answerfile from %s" % location)
    util.fetchFile(location, '/tmp/answerfile')

    xmldoc = xml.dom.minidom.parse('/tmp/answerfile')
    try:
        answers = __parse_answerfile__(xmldoc)
    except Exception, e:
        xelogging.log("Failed to parse answerfile, propogating error.")
        raise
    else:
        return answers

# get data from a DOM object representing the answerfile:
def __parse_answerfile__(answerdoc, results):
    results = {}
    
    xelogging.log("Importing XML answerfile.")

    # get text from a node:
    def getText(nodelist):
        rc = ""
        for node in nodelist:
            if node.nodeType == node.TEXT_NODE:
                rc = rc + node.data
        return rc.encode()

    n = answerdoc.documentElement

    # primary-disk:
    results['primary-disk'] = "/dev/%s" % getText(n.getElementsByTagName('primary-disk')[0].childNodes)
    pd_has_guest_storage = True and n.getElementsByTagName('primary-disk')[0].getAttribute("gueststorage").lower() in ["", "yes", "true"]
    
    # guest-disks:
    results['guest-disks'] = []
    if pd_has_guest_storage:
        results['guest-disks'].append(results['primary-disk'])
    for disk in n.getElementsByTagName('guest-disk'):
        results['guest-disks'].append("/dev/%s" % getText(disk.childNodes))

    # source-media, source-address:
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
        raise Exception, "No source media specified."

    # root-password:
    results['root-password'] = getText(n.getElementsByTagName('root-password')[0].childNodes)
    results['root-password-type'] = 'plaintext'

    # manual-nameservers:
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
        results['manual-hostname'] = (True, getText(mhn.childNodes))
    else:
        results['manual-hostname'] = (False, None)

    # timezone:
    results['timezone'] = getText(n.getElementsByTagName('timezone')[0].childNodes)

    # ntp-servers:
    results['ntp-servers'] = []
    for disk in n.getElementsByTagName('ntp-servers'):
        results['ntp-servers'].append(getText(disk.childNodes))
    results['time-config-method'] = 'ntp'

    # iface-configuration
    netifs = { }
    for netifnode in n.getElementsByTagName('interface'):
        name = netifnode.getAttribute('name')
        proto = netifnode.getAttribute('proto')
        enabled = netifnode.getAttribute('enabled')

        netif = { }
        if proto == 'static':
            ip = getText(netifnode.getElementsByTagName('ip')[0].childNodes)
            subnetmask = getText(netifnode.getElementsByTagName('subnet-mask')[0].childNodes)
            gateway = getText(netifnode.getElementsByTagName('gateway')[0].childNodes)

            netif = { 'use-dhcp' : False ,
                      'enabled' : (enabled == 'yes'),
                      'ip' : ip,
                      'subnet-mask' : subnetmask,
                      'gateway' : gateway }

        elif proto == 'dhcp':
            netif = { 'use-dhcp' : True,
                      'enabled' : (enabled == 'yes') }

        netifs[name] = netif

    # keymap:
    keymap_nodes = n.getElementsByTagName('post-install-script')
    if len(keymap_nodes) == 1:
        results['keymap'] = getText(n.getElementsByTagName('post-install-script')[0].childNodes)
    else:
        xelogging.log("No keymap specified in answer file: defaulting to 'us'")
        results['keymap'] = "us"

    # post-install-script
    pis_nodes = n.getElementsByTagName('post-install-script')
    if len(pis_nodes) == 1:
        results['post-install-script'] = getText(n.getElementsByTagName('post-install-script')[0].childNodes)
    
    results['iface-configuration'] = (False, netifs)

    # currently no supprt for re-installation:
    results['install-type'] = constants.INSTALL_TYPE_FRESH
    results['preserve-settings'] = False

    return results
