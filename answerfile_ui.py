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
from xml.dom.minidom import parse

import xelogging

# module globals:
sub_ui_package = None
answerFile = None

# allow a sub-interface to specified - progress dialog calls and the
# init and de-init calls will be passed through.  Dialogs will be translated
# as no-ops.
def specifySubUI(subui):
    global sub_ui_package
    sub_ui_package = subui

def specifyAnswerFile(file):
    global answerFile
    assert type(file) == str

    util.fetchFile(file, "/tmp/answerfile")
    
    answerFile = "/tmp/answerfile"

def init_ui(results, is_subui):
    global answerFile

    # attempt to import the answers:
    try:
        answerdoc = parse(answerFile)
        # this function transforms 'results' that we pass in
        __parse_answerfile__(answerdoc, results)
    except Exception, e:
        xelogging.log("Error parsing answerfile.")
        raise
    
    # Now pass on initialisation to our sub-UI:
    if sub_ui_package is not None:
        sub_ui_package.init_ui(results, True)

# get data from a DOM object representing the answerfile:
def __parse_answerfile__(answerdoc, results):
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

def end_ui():
    if sub_ui_package is not None:
        sub_ui_package.end_ui()

# XXX THESE MUST GO!!!!
def suspend_ui():
    pass

def resume_ui():
    pass

# stubs:
def welcome_screen(answers):
    return 1
def hardware_warnings(answers, ram_warning, vt_warning):
    return 1
def eula_screen(answers):
    return 1
def get_installation_type(answers, insts):
    return 1
def backup_existing_installation(answers):
    return 1
def get_keyboard_type(answers):
    return 1
def get_keymap(answers):
    return 1
def confirm_installation_one_disk(answers):
    return 1
def confirm_installation_multiple_disks(answers):
    return 1
def confirm_erase_volume_groups(answers):
    return 1
def select_installation_source(answers):
    return 1
def get_http_source(answers):
    return 1
def get_nfs_source(answers):
    return 1
def verify_source(answers):
    return 1
def select_primary_disk(answers):
    return 1
def select_guest_disks(answers):
    return 1
def get_root_password(answers):
    if not answers.has_key('root-password') and sub_ui_package:
        return sub_ui_package.get_root_password(answers)
    else:
        return 1
def determine_basic_network_config(answers):
    return 1
def get_timezone_region(answers):
    return 1
def get_timezone_city(answers):
    return 1
def get_time_configuration_method(answers):
    return 1
def get_ntp_servers(answers):
    return 1
def set_time(answers, now):
    return 1
def get_name_service_configuration(answers):
    return 1
def installation_complete(answers):
    return 1
def confirm_installation_reinstall(answers):
    return 1

# 0 means don't retry
def request_media(medianame):
    return 0
def error_dialog(message):
    if sub_ui_package:
        sub_ui_package.error_dialog(message)
    else:
        print "ERROR:"
        print message

# progress dialogs:
def initProgressDialog(title, text, total):
    if sub_ui_package:
        return sub_ui_package.initProgressDialog(title, text, total)

def displayProgressDialog(current, pd, updated_text = None):
    if sub_ui_package:
        sub_ui_package.displayProgressDialog(current, pd)

def showMessageDialog(title, text):
    if sub_ui_package:
        sub_ui_package.showMessageDialog(title, text)

def clearModelessDialog():
    if sub_ui_package:
        sub_ui_package.clearModelessDialog()
