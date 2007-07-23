# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Functions to perform the XE installation
#
# written by Mark Nijmeijer

import os
import os.path
import xml.sax.saxutils

import findroot
import sys
import time
import p2v_constants
import util
import xelogging
import xmlrpclib

import tui.progress

import urllib
import urllib2
import httplib
import httpput
import tempfile

from p2v_error import P2VError, P2VPasswordError, P2VMountError, P2VCliError
from version import *

# globals
dropbox_path = "/opt/xensource/packages/xgt/"
local_mount_path = "/tmp/xenpending"

class P2VServerError(Exception):
    pass

def append_hostname(os_install): 
    os_install[p2v_constants.HOST_NAME] = os.uname()[1]

def determine_size(os_install):
    os_root_device = os_install[p2v_constants.DEV_NAME]
    dev_attrs = os_install[p2v_constants.DEV_ATTRS]

    total_size_l = long(0)
    used_size_l = long(0)

    os_root_mount_point = tempfile.mkdtemp(dir = "/tmp", prefix="p2v-sizecheck-")
    try:
        util.mount(
            os_root_device, os_root_mount_point, fstype = dev_attrs['type'],
            options = ['ro']
            )

        # findroot.determine_size returns in bytes
        (used_size, total_size) = findroot.determine_size(os_root_mount_point, os_root_device )
    finally:
        while os.path.ismount(os_root_mount_point):
            util.umount(os_root_mount_point)
        os.rmdir(os_root_mount_point)
    
    # adjust total size to 150% of used size, with a minimum of 4Gb
    total_size_l = (long(used_size) * 3) / 2
    if total_size_l < (4 * (1024 ** 3)): # size in template.dat is in bytes
        total_size_l = (4 * (1024 ** 3))
        
    total_size = str(total_size_l)

    #now increase used_size by 100MB, because installing our RPMs during 
    #the p2v process will take up that extra room.
    used_size_l = long(used_size)
    used_size_l += 100 * (1024 ** 2)
    used_size = str(used_size_l)
    
    os_install[p2v_constants.FS_USED_SIZE] = used_size
    os_install[p2v_constants.FS_TOTAL_SIZE] = total_size
    
def rio_p2v(answers, use_tui = True):
    if use_tui:
        tui.progress.showMessageDialog("Working", "Connecting to server...")

    xapi = xmlrpclib.Server(answers['target-host-name'])
    rc = xapi.session.login_with_password(answers['target-host-user'], 
                                          answers['target-host-password'])
    assert rc['Status'] == 'Success'
    session = rc['Value']

    template_name = "XenSource P2V Server"

    # find and instantiate the P2V server:
    if use_tui:
        tui.progress.clearModelessDialog()
        tui.progress.showMessageDialog("Working", "Provisioning the target virtual machine...")

    xelogging.log("Looking for P2V server template")
    rc = xapi.VM.get_by_name_label(session, template_name)
    if rc['Status'] != 'Success':
        raise RuntimeError, "Unable to get reference to template '%s'" % template_name
    template_refs = rc['Value']
    assert len(template_refs) == 1
    [ template_ref ] = template_refs

    if not answers.has_key('vm-name'):
        vm_name = "New P2Vd guest"
    else:
        vm_name = answers['vm-name']

    xelogging.log("Cloning a new P2V server")
    rc = xapi.VM.clone(session, template_ref, vm_name)
    if rc['Status'] != 'Success':
        raise RuntimeError, "Unable to clone template %s" % template_ref
    guest_ref = rc['Value']

    rc = xapi.VM.provision(session, guest_ref)
    if rc['Status'] != 'Success':
        raise RuntimeError, "Unable to provision VM."

    xelogging.log("Starting P2V server")
    rc = xapi.VM.start(session, guest_ref, False, False)
    if rc['Status'] != 'Success':
        raise RuntimeError, "Unable to start the guest."

    rc = xapi.VM.get_uuid(session, guest_ref)
    if rc['Status'] != 'Success':
        raise RuntimeError, "Unable to get UUID of our new P2V guest."
    p2v_server_uuid = rc['Value']

    rc = xapi.VM.get_resident_on(session, guest_ref)
    if rc['Status'] != 'Success':
        raise RuntimeError, "Unable to get a reference to the host the guest is running on."
    host_ref = rc['Value']

    rc = xapi.host.get_address(session, host_ref)
    if rc['Status'] != 'Success':
        raise RuntimeError, "Unable to get address of host %s" % host_ref
    host_address = rc['Value']

    # wait for it to get an IP address:
    xelogging.log("Waiting for P2V server to signal ready state")
    p2v_server_ready = False
    for i in range(5):
        rc = xapi.VM.get_other_config(session, guest_ref)
        if rc['Status'] != 'Success':
            raise RuntimeError, "Unable to get other config field for ref %s" % guest_ref
        value = rc['Value']
        if value.has_key('ip') or value.has_key('ready'):
            p2v_server_ready = True
            break
        else:
            time.sleep(10)

    if not p2v_server_ready:
        raise RuntimeError, "P2V server did not signify ready state"

    def p2v_server_call(cmd, args):
        """ This function makes HTTP GET calls to the server via the xapi proxy
        code, so we connect to xapi on which the server is resident, then do a
        GET with the full address of the client, so that calls go via the 
        'guest-installer' network. """
        conn = httplib.HTTPSConnection(host_address)

        query_string = urllib.urlencode(args)
        address = "http://" + p2v_server_uuid + ":81/" + cmd + "?" + query_string
        xelogging.log("About to call p2v server: %s" % address)
        conn.request("GET", address, headers = {'Connection': 'close'})
        response = conn.getresponse()

        xelogging.log("Response was %d %s" % (response.status, response.reason))
        body = response.read()
        if body:
            xelogging.log("Body was %s" % body)
        
        if response.status != 200:
            raise P2VServerError, response.status

        conn.close()

    # add a disk, partition it with a big partition, format the partition:
    p2v_server_call('make-disk', {'volume': 'xvda', 'size': str(answers['target-vm-disksize-mb'] * 1024 * 1024),
        'sr': answers['target-sr'], 'bootable': 'true'})
    p2v_server_call('partition-disk', {'volume': 'xvda', 'part1': '-1'})

    # if RHEL 3 we need to use a more limited set of ext3 options than the default set:
    if answers['osinstall']['osname'] == "Red Hat" and answers['osinstall']['osversion'].startswith("3."):
        p2v_server_call('mkfs', {'volume': 'xvda1', 'fs': 'ext3', 'fsopts': 'none,has_journal,filetype,sparse_super'})
    else:
        p2v_server_call('mkfs', {'volume': 'xvda1', 'fs': 'ext3'})

    p2v_server_call('set-fs-metadata', {'volume': 'xvda1', 'mntpoint': '/'})

    # transfer filesystem(s):
    if use_tui:
        tui.progress.clearModelessDialog()
        tui.progress.showMessageDialog("Working", "Transferring filesystems - this will take a long time...")

    os_root_device = answers['osinstall'][p2v_constants.DEV_NAME]
    dev_attrs = answers['osinstall'][p2v_constants.DEV_ATTRS]

    # make a temporary mountpoint:
    mntpoint = tempfile.mkdtemp(dir = "/tmp", prefix="p2v-root")
    try:
        util.mount(os_root_device, mntpoint, options = ['ro'])
        xelogging.log("Starting to transfer filesystems")
        boot_merged = findroot.rio_handle_root(host_address, p2v_server_uuid, mntpoint, os_root_device)
    finally:
        while os.path.ismount(mntpoint):
            util.umount(mntpoint)
        os.rmdir(mntpoint)

    if use_tui:
        tui.progress.clearModelessDialog()
        tui.progress.showMessageDialog("Working", "Completing transformation...")

    p2v_server_call('update-fstab', {'root-vol': 'xvda1'})
    p2v_server_call('paravirtualise', {'root-vol': 'xvda1', 'boot-merged': str(boot_merged).lower()})
    p2v_server_call('completed', {})

    xelogging.log("Destroying the guest's vifs")

    # wait for the guest to go down then unplug and destroy the guest's vifs:
    for i in range(20):
        rc = xapi.VM.get_power_state(session, guest_ref)
        if rc['Status'] == 'Success':
            if rc['Value'] == 'Halted':
                break
        time.sleep(5)

    rc = xapi.VM.get_VIFs(session, guest_ref)
    if rc['Status'] != 'Success':
        raise RuntimeError, "Unable to get a list of VIFs associated with the P2V target"
    vifs = rc['Value']
    for vif in vifs:
        xapi.VIF.unplug(session, vif)
        xapi.VIF.destroy(session, vif)

    xapi.session.logout(session)

    if use_tui:
        tui.progress.clearModelessDialog()

#stolen from packaging.py
def ejectCD():
    if not os.path.exists("/tmp/cdmnt"):
        os.mkdir("/tmp/cdmnt")

    device = None
    for dev in ['hda', 'hdb', 'hdc', 'scd1', 'scd2',
                'sr0', 'sr1', 'sr2', 'cciss/c0d0p0',
                'cciss/c0d1p0', 'sda', 'sdb']:
        device_path = "/dev/%s" % dev
        if os.path.exists(device_path):
            try:
                util.mount(device_path, '/tmp/cdmnt', ['ro'], 'iso9660')
                if os.path.isfile('/tmp/cdmnt/REVISION'):
                    device = device_path
                    # (leaving the mount there)
                    break
            except util.MountFailureException:
                # clearly it wasn't that device...
                pass
            else:
                if os.path.ismount('/tmp/cdmnt'):
                    util.umount('/tmp/cdmnt')

    if os.path.exists('/usr/bin/eject') and device != None:
        util.runCmd2(['/usr/bin/eject', device])
