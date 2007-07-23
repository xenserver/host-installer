# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# P2V Answerfile Support
#
# written by Andrew Peace

import xml.dom.minidom

import findroot
import xelogging
import util

class P2VAnswerfileError(Exception):
    pass

# get text from a node:
def getText(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc.encode()

def processAnswerfile(location):
    """ Downloads an answerfile from 'location' -- this is in the URL format
    used by fetchFile in the util module (which also permits fetching over
    NFS).  Returns answers ready for the backend to process. """

    xelogging.log("Fetching answerfile from %s" % location)
    util.fetchFile(location, '/tmp/answerfile')

    xmldoc = xml.dom.minidom.parse('/tmp/answerfile')
    n = xmldoc.documentElement

    results = {}

    # source OS:
    source_dev = "/dev/" + getText(n.getElementsByTagName("root")[0].childNodes)
    oslist = findroot.findroot()
    chosen_os = None
    for os in oslist:
        if os['dev_attrs']['path'] == source_dev:
            chosen_os = os
    
    if not chosen_os:
        raise RuntimeError, "Selected operating system not found."
    results['osinstall'] = chosen_os

    # target:
    target_n = n.getElementsByTagName("target")[0]

    host = getText(target_n.getElementsByTagName("host")[0].childNodes)
    if True not in [ host.startswith(x) for x in ['http://', 'https://'] ]:
        host = "https://" + host
    name_nodes = target_n.getElementsByTagName("vm-name")
    if len(name_nodes) == 1:
        results['vm-name'] = getText(name_nodes[0].childNodes)
    results['target-host-name'] = host
    results['target-host-user'] = getText(target_n.getElementsByTagName("user")[0].childNodes)
    results['target-host-password'] = getText(target_n.getElementsByTagName("password")[0].childNodes)
    results['target-sr'] = getText(target_n.getElementsByTagName("sr")[0].childNodes)
    results['target-vm-disksize-mb'] = long(getText(target_n.getElementsByTagName("size")[0].childNodes))

    return results
