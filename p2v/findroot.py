#!/usr/bin/python
# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

import os
import os.path
import sys
import time
import commands
import p2v_constants
import popen2
import httpput
import urllib
import xelogging
import tempfile
import util
from p2v_error import P2VError

class MalformedRoot(Exception):
    pass

def parse_blkid(line):
    """Take a line of the form '/dev/foo: key="val" key="val" ...' and return
a dictionary created from the key/value pairs and the /dev entry as 'path'"""

    dev_attrs = {}
    i =  line.find(":")
    dev_attrs[p2v_constants.DEV_ATTRS_PATH] = line[0:i]
    attribs = line[i+1:].split(" ")
    for attr in attribs:
        if len(attr) == 0:
            continue
        name, val = attr.split("=")
        dev_attrs[name.lower()] = val.strip('"')
    return dev_attrs
    
def scan():
    devices = {}
    
    #activate LVM
    util.runCmd2(['vgscan'])
    util.runCmd2(['vgchange', '-a', 'y'])
    rc, out = util.runCmd("/sbin/blkid -c /dev/null", with_output = True)
    if rc == 0 and out:
        for line in out.split("\n"):
            attrs = parse_blkid(line)
            devices[attrs[p2v_constants.DEV_ATTRS_PATH]] = attrs
    else:
        raise P2VError("Failed to scan devices")
    return devices

# to be deprecated in favour of util.mount
def mount_dev(dev, dev_type, mntpnt, options):
    umount_dev(mntpnt) # just a precaution, don't care if it fails
    rc = util.runCmd2(["mount", "-o", options, "-t", dev_type, dev, mntpnt])
    return rc

# to be deprecated in favour of util.unmount
def umount_dev(mntpnt):
    rc = util.runCmd2(["umount", mntpnt])
    return rc

def load_fstab(fstab_file):
    fp = None
    try:
        fp = open(fstab_file, 'r')
        fstab = {}
        for line in fp:
            if '#' in line:
                line = line[0:line.index('#')]
            line = line.strip()
            if not line:
                continue
            pieces = line.split()
            if ',' in pieces[3]:
                pieces[3] = [ x.strip() for x in pieces[3].split(',') ]
            fstab[(pieces[1], pieces[0])] = pieces
        return fstab
    finally:
        if fp:
            fp.close()

def find_dev_for_label(devices, label):
    for value in devices.values():
        if value.has_key(p2v_constants.DEV_ATTRS_LABEL) and value[p2v_constants.DEV_ATTRS_LABEL] == label:
            return value[p2v_constants.DEV_ATTRS_PATH]
    return None

def find_extra_mounts(fstab, devices):
    import copy
    
    mounts = []
    for ((mntpnt, dev), info) in fstab.items():
        if info[2] not in ('ext2', 'ext3', 'reiserfs') or \
           mntpnt == '/' or \
           'noauto' in info[3]:
            continue

        mount_info = copy.deepcopy(info)

        # convert label to real device name
        if 'LABEL=' in info[0]:
            label = mount_info[0][6:]
            mount_info[0] = find_dev_for_label(devices, label)

        options = None
        if type(mount_info[3]) == type([]):
            mount_info[3] = ','.join(filter(lambda x: not (x == "rw" or \
                                                           x == "ro"),
                                            mount_info[3]))

        mounts.append(mount_info)
    return mounts

#returns in bytes
def determine_size(mntpnt, dev_name):
    fstab = load_fstab(os.path.join(mntpnt, 'etc', 'fstab'))
    
    devices = scan()

    active_mounts = []
    mounts = find_extra_mounts(fstab, devices)
    for mount_info in mounts:
        extra_mntpnt = os.path.join(mntpnt, mount_info[1][1:])

        rc = mount_dev(mount_info[0], mount_info[2],
                       extra_mntpnt, mount_info[3] + ",ro")
                       
        if rc != 0:
            raise P2VError("Failed to determine size - mount failed.")

        active_mounts.append(extra_mntpnt)

    #df reports in 1K blocks
    # get the used size
    rc, used_out = util.runCmd("df -kP | grep %s | awk '{print $3}'" % mntpnt, 
                               with_output = True)
    if rc != 0:
        raise P2VError("Failed to determine used size - df failed")

    #get the total size
    rc, total_out = util.runCmd("df -kP | grep %s | awk '{print $2}'" % mntpnt,
                                with_output = True)
    if rc != 0:
        raise P2VError("Failed to determine used size - df failed")
    
    xelogging.log("FS used Usage : %s, FS total usage : %s" % (used_out, total_out))
    used_size = long(0)
    total_size = long(0)

    split_used_size = used_out.split('\n')
    split_total_size = total_out.split('\n')
    for o in split_used_size:
        xelogging.log("FS used Usage : %s" % o)
        used_size += long(o)
    for o in split_total_size:
        xelogging.log("FS total Usage : %s" % o)
        total_size += long(o)
        
    xelogging.log("Final FS used Usage : %d" % used_size)
    xelogging.log("Final FS total Usage : %d" % total_size)

    for item in active_mounts:
        # assume the umount works
        umount_dev(item)

    return str(used_size * 1024), str(total_size * 1024)

def rio_handle_root(xapi_host, p2v_vm_uuid, mntpnt, dev_name, pd = None):
    """ Returns a boolean indicating whether we had to mount /boot separately or not. """
    fstab = load_fstab(os.path.join(mntpnt, 'etc', 'fstab'))

    devices = scan()
    
    active_mounts = []
    mounts = find_extra_mounts(fstab, devices)
    for mount_info in mounts:
        #p2v_utils.trace_message("  --", mount_info)
        extra_mntpnt = os.path.join(mntpnt, mount_info[1][1:])

        rc = mount_dev(mount_info[0], mount_info[2],
                       extra_mntpnt, mount_info[3] + ",ro")
        if rc != 0:
            raise P2VError("Failed to handle root - mount failed.")

        active_mounts.append(extra_mntpnt)

    hostname = findHostName(mntpnt)
    pipe = popen2.Popen3("tar -C '%s' -cjSf - . 2>/dev/null" % mntpnt)
    path = "http://" + p2v_vm_uuid + ":81/unpack-tar?" + urllib.urlencode({'volume': 'xvda1', 'compression': 'bzip2'})
    httpput.put(xapi_host, 443, path, pipe.fromchild, https = True)
    pipe.tochild.close()
    pipe.fromchild.close()
    rc = pipe.wait()

    for item in active_mounts:
        # assume the umount works
        umount_dev(item)

    return True in [x[1] == '/boot' for x in mounts]

def findHostName(mnt):
    hostname = "localhost"
    #generic
    hnFile = os.path.join(mnt,'etc', 'hostname')
    if os.path.exists(hnFile):
        hn = open(hnFile)
        for line in hn.readlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            hostname = line
            return hostname
   
    # suse before red hat, coz etc/sysconfig/network is a 
    # directory on suse
    hnFile = os.path.join(mnt,'etc', 'HOSTNAME')
    if os.path.exists(hnFile):
        hn = open(hnFile)
        for line in hn.readlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            hostname = line
            return hostname

    #red hat
    hnFile = os.path.join(mnt,'etc', 'sysconfig', 'network')
    if os.path.exists(hnFile):
        hn = open(hnFile)
        for line in hn.readlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            (name, value) = line.split('=')
            if (name) == 'HOSTNAME':
                hostname = value
                return hostname
 
    return hostname
    
def inspect_root(dev_name, dev_attrs, results):
    mnt = tempfile.mkdtemp(dir = "/tmp", prefix = "p2v-inspect-")
    util.mount(dev_name, mnt, fstype = dev_attrs['type'])
    try:
        fstab_path = os.path.join(mnt, 'etc', 'fstab')
        if os.path.exists(fstab_path):
            xelogging.log("* Found root partition on %s" % dev_name)

            #scan fstab for EVMS
            fstab = load_fstab(fstab_path)
            for ((mntpnt, dev), info) in fstab.items():
                if dev.find("/evms/") != -1:
                    xelogging.log("Usage of EVMS detected. Skipping his root partition (%s)" % dev_name)
                    return

            rc, out = util.runCmd("/opt/xensource/installer/read_osversion.sh " + mnt, with_output = True)
            if rc == 0:
                xelogging.log("read_osversion succeeded : out = %s" % out)
                parts = out.split('\n')
                if len(parts) > 0:
                    os_install = {}
                    xelogging.log("found os name: %s" % parts[0])
                    xelogging.log("found os version : %s" % parts[1])

                    os_install[p2v_constants.OS_NAME] = parts[0]
                    os_install[p2v_constants.OS_VERSION] = parts[1]
                    if detect64bits(mnt):
                        os_install[p2v_constants.BITS] = 64
                    else:
                        os_install[p2v_constants.BITS] = 32
                    os_install[p2v_constants.DEV_NAME] = dev_name
                    os_install[p2v_constants.DEV_ATTRS] = dev_attrs
                    os_install[p2v_constants.HOST_NAME] = findHostName(mnt)
                    results.append(os_install)
            else:
                xelogging.log("read_osversion failed : out = %s" % out)
                raise P2VError, "Failed to inspect root - read_osversion failed."
    finally:
        while os.path.ismount(mnt):
            util.umount(mnt)
        os.rmdir(mnt)

def detect64bits(root_mnt):
    lib_dir = os.path.join(root_mnt, "lib")
    if not os.path.exists(lib_dir):
        raise MalformedRoot, "No /lib directory"
    lib_files = os.listdir(lib_dir)
    return True in [x.startswith("ld-linux-x86-64") for x in lib_files]

def findroot():
    devices = scan()
    results = []

    for dev_name, dev_attrs in devices.items():
        if dev_attrs.has_key(p2v_constants.DEV_ATTRS_TYPE) and dev_attrs[p2v_constants.DEV_ATTRS_TYPE] in ('ext2', 'ext3', 'reiserfs'):
            try:
                inspect_root(dev_name, dev_attrs, results)
            except MalformedRoot, e:
                xelogging.log("Encountered malformed root filesystem: skipping.  (%s)" % str(e))
                continue
                   
    return results

# TODO, CA-2747  pull this out of a supported OS list.
def isP2Vable(os):
    if os[p2v_constants.BITS] != 32:
        return False

    if os[p2v_constants.OS_NAME] == "Red Hat" and os[p2v_constants.OS_VERSION].startswith('4'):
        return True
    if os[p2v_constants.OS_NAME] == "Red Hat" and os[p2v_constants.OS_VERSION].startswith('3'):
        return True
    if os[p2v_constants.OS_NAME] == "SuSE" and os[p2v_constants.OS_VERSION].startswith('9'):
        return True

    return False

if __name__ == '__main__':
    mntbase = "/tmp/mnt"

    devices = scan()

    for dev_name, dev_attrs in devices.items():
        if dev_attrs.has_key(p2v_constants.DEV_ATTRS_TYPE) and dev_attrs[p2v_constants.DEV_ATTRS_TYPE] in ('ext2', 'ext3', 'reiserfs'):
            mnt = mntbase + "/" + os.path.basename(dev_name)
            if not os.path.exists(mnt):
                os.makedirs(mnt)

            rc = mount_dev(dev_name, dev_attrs[p2v_constants.DEV_ATTRS_TYPE], mnt, 'ro')
            if rc != 0:
                xelogging.log("Failed to mount mnt")
                continue

            if os.path.exists(os.path.join(mnt, 'etc', 'fstab')):
                xelogging.log("* Found root partition on %s" % dev_name)

            umount_dev(mnt)
