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
import p2v_utils
import p2v_tui
import popen2
import httpput
import urllib
from p2v_error import P2VError

ui_package = p2v_tui


def run_command(cmd):
    p2v_utils.trace_message("running: %s\n" % cmd)
    rc, out = commands.getstatusoutput(cmd)
    if rc != 0:
        p2v_utils.trace_message("Failed %d: %s\n" % (rc, out))
    return (rc, out)

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
    run_command("vgscan")
    run_command("vgchange -a y")
    rc, out = run_command("/sbin/blkid -c /dev/null")
    if rc == 0 and out:
        for line in out.split("\n"):
            attrs = parse_blkid(line)
            devices[attrs[p2v_constants.DEV_ATTRS_PATH]] = attrs
    else:
        raise P2VError("Failed to scan devices")
    return devices

def mount_dev(dev, dev_type, mntpnt, options):
    umount_dev(mntpnt) # just a precaution, don't care if it fails
    rc, out = run_command("echo 1 > /proc/sys/kernel/printk")
    rc, out = run_command("mount -o %s -t %s %s %s %s" % (options, dev_type,
                                                       dev, mntpnt, p2v_utils.show_debug_output()))
    return rc

def umount_dev(mntpnt):
    rc, out = run_command("umount %s" % (mntpnt))
    return rc

def load_fstab(fp):
    fstab = {}
    for line in fp.readlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        pieces = line.split()
        if ',' in pieces[3]:
            pieces[3] = [ x.strip() for x in pieces[3].split(',') ]
        fstab[(pieces[1], pieces[0])] = pieces
    return fstab

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
    fp = open(os.path.join(mntpnt, 'etc', 'fstab'))
    fstab = load_fstab(fp)
    fp.close()
    
    devices = scan()

    active_mounts = []
    p2v_utils.trace_message("* Need to mount:")
    mounts = find_extra_mounts(fstab, devices)
    for mount_info in mounts:
#        p2v_utils.trace_message("  --", mount_info)
        extra_mntpnt = os.path.join(mntpnt, mount_info[1][1:])

        rc = mount_dev(mount_info[0], mount_info[2],
                       extra_mntpnt, mount_info[3] + ",ro")
                       
        if rc != 0:
            raise P2VError("Failed to determine size - mount failed.")

        active_mounts.append(extra_mntpnt)

    #df reports in 1K blocks
    # get the used size
    command = "df -kP | grep %s | awk '{print $3}'" % mntpnt
    p2v_utils.trace_message("going to run : %s" % command)
    rc, used_out = run_command(command);
    if rc != 0:
        raise P2VError("Failed to determine used size - df failed")

    #get the total size
    command = "df -kP | grep %s | awk '{print $2}'" % mntpnt
    p2v_utils.trace_message("going to run : %s" % command)
    rc, total_out = run_command(command);
    if rc != 0:
        raise P2VError("Failed to determine used size - df failed")
    
    p2v_utils.trace_message("\n\nFS used Usage : %s, FS total usage : %s\n" % (used_out, total_out))
    used_size = long(0)
    total_size = long(0)

    split_used_size = used_out.split('\n')
    split_total_size = total_out.split('\n')
    for o in split_used_size:
        p2v_utils.trace_message("\n\nFS used Usage : %s\n\n" % o)
        used_size += long(o)
    for o in split_total_size:
        p2v_utils.trace_message("\n\nFS total Usage : %s\n\n" % o)
        total_size += long(o)
        
    p2v_utils.trace_message("\n\nFinal FS used Usage : %d\n\n" % used_size)
    p2v_utils.trace_message("\n\nFinal FS total Usage : %d\n\n" % total_size)

    for item in active_mounts:
        # assume the umount works
        umount_dev(item)

    return str(used_size * 1024), str(total_size * 1024)

def rio_handle_root(host, port, mntpnt, dev_name, pd = None):
    rc = 0
    fp = open(os.path.join(mntpnt, 'etc', 'fstab'))
    fstab = load_fstab(fp)
    fp.close()
    
    if pd != None:
        ui_package.displayProgressDialog(0, pd, " - Scanning and mounting devices")
                                       
    devices = scan()
    
    active_mounts = []
    p2v_utils.trace_message("* Need to mount:")
    mounts = find_extra_mounts(fstab, devices)
    for mount_info in mounts:
        #p2v_utils.trace_message("  --", mount_info)
        extra_mntpnt = os.path.join(mntpnt, mount_info[1][1:])

        rc = mount_dev(mount_info[0], mount_info[2],
                       extra_mntpnt, mount_info[3] + ",ro")
        if rc != 0:
            raise P2VError("Failed to handle root - mount failed.")

        active_mounts.append(extra_mntpnt)

    if pd != None:
        ui_package.displayProgressDialog(1, pd, " - Compressing root filesystem")

    hostname = findHostName(mntpnt)
    pipe = popen2.Popen3("tar -C '%s' -cjSf - . 2>/dev/null" % mntpnt)
    path = "/unpack-tar?" + urllib.urlencode({'volume': 'xvda1', 'compression': 'bzip2'})
    httpput.put(host, port, path, pipe.fromchild)
    pipe.tochild.close()
    pipe.fromchild.close()
    rc = pipe.wait()

    if pd != None:
        ui_package.displayProgressDialog(2, pd, " - Calculating md5sum")

    for item in active_mounts:
        # assume the umount works
        umount_dev(item)

def mount_os_root(dev_name, dev_attrs):
    mntbase = "/tmp/mnt"
    mnt = mntbase + "/" + os.path.basename(dev_name)
    rc, out = run_command("mkdir -p %s" % (mnt))
    if rc != 0:
        p2v_utils.trace_message("mkdir failed\n")
        raise P2VError("Failed to mount os root - mkdir failed")
    
    rc = mount_dev(dev_name, dev_attrs['type'], mnt, 'ro')
#    if rc != 0:
#       raise P2VError("Failed to mount os root")
    return mnt

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
    mnt = mount_os_root(dev_name, dev_attrs)
    fstab_path = os.path.join(mnt, 'etc', 'fstab')
    if os.path.exists(fstab_path):
       p2v_utils.trace_message("* Found root partition on %s" % dev_name)

       #scan fstab for EVMS
       fp = open(fstab_path)
       fstab = load_fstab(fp)
       fp.close()
       for ((mntpnt, dev), info) in fstab.items():
           if dev.find("/evms/") != -1:
               p2v_utils.trace_message("Usage of EVMS detected. Skipping his root partition (%s)" % dev_name)
               return

       rc, out = run_command("/opt/xensource/installer/read_osversion.sh " + mnt)
       if rc == 0:
           p2v_utils.trace_message("read_osversion succeeded : out = %s" % out)
           parts = out.split('\n')
           if len(parts) > 0:
               os_install = {}
               p2v_utils.trace_message("found os name: %s" % parts[0])
               p2v_utils.trace_message("found os version : %s" % parts[1])
               p2v_utils.trace_message("os is : %s" % parts[2])
               
               os_install[p2v_constants.OS_NAME] = parts[0]
               os_install[p2v_constants.OS_VERSION] = parts[1]
               os_install[p2v_constants.BITS] = parts[2]
               os_install[p2v_constants.DEV_NAME] = dev_name
               os_install[p2v_constants.DEV_ATTRS] = dev_attrs
               os_install[p2v_constants.HOST_NAME] = findHostName(mnt)
               results.append(os_install)
       else:
           p2v_utils.trace_message("read_osversion failed : out = %s" % out)
           raise P2VError("Failed to inspect root - read_osversion failed.")
    umount_dev(mnt)

def findroot():
    devices = scan()
    results = []

    for dev_name, dev_attrs in devices.items():
        if dev_attrs.has_key(p2v_constants.DEV_ATTRS_TYPE) and dev_attrs[p2v_constants.DEV_ATTRS_TYPE] in ('ext2', 'ext3', 'reiserfs'):
            inspect_root(dev_name, dev_attrs, results)
                   
    #run_command("sleep 2")
    return results

def get_mem_info():
    command = "cat /proc/meminfo | grep MemTotal | awk '{print $2}'"
    rc, out = run_command(command)
    if rc != 0:
        raise P2VError("Failed to get mem size")
    return out

def get_cpu_count():
    command = "cat /proc/cpuinfo | grep processor | wc -l"
    rc, out = run_command(command)
    if rc != 0:
        raise P2VError("Failed to get cpu count")
    return out

if __name__ == '__main__':
    mntbase = "/tmp/mnt"

    devices = scan()

    for dev_name, dev_attrs in devices.items():
        if dev_attrs.has_key(p2v_constants.DEV_ATTRS_TYPE) and dev_attrs[p2v_constants.DEV_ATTRS_TYPE] in ('ext2', 'ext3', 'reiserfs'):
            mnt = mntbase + "/" + os.path.basename(dev_name)
            rc, out = run_command("mkdir -p %s" % (mnt))
            if rc != 0:
                p2v_utils.trace_message("mkdir failed\n")
                sys.exit(1)

            rc = mount_dev(dev_name, dev_attrs[p2v_constants.DEV_ATTRS_TYPE], mnt, 'ro')
            if rc != 0:
                p2v_utils.trace_message("Failed to mount mnt")
                continue
                #sys.exit(rc)

            if os.path.exists(os.path.join(mnt, 'etc', 'fstab')):
                p2v_utils.trace_message("* Found root partition on %s" % dev_name)
                rc, tar_dirname, tar_filename, md5sum = handle_root(mnt, dev_name)
                if rc != 0:
                    p2v_utils.trace_message("%s failed\n" % dev_name)
                    sys.exit(rc)

            umount_dev(mnt)
