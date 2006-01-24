#!/usr/bin/python
#
# Copyright (c) 2005 XenSource, Inc. All use and distribution of this
# copyrighted material is governed by and subject to terms and 
# conditions as licensed by XenSource, Inc. All other rights reserved. 
#

import os
import os.path
import sys
import commands
import constants
import p2v_utils

def run_command(cmd):
#    p2v_utils.trace_message("running: %s\n" % cmd)
    rc, out = commands.getstatusoutput(cmd)
 #   if rc != 0:
 #       p2v_utils.trace_message("Failed %d: %s\n" % (rc, out))
    return (rc, out)

def parse_blkid(line):
    """Take a line of the form '/dev/foo: key="val" key="val" ...' and return
a dictionary created from the key/value pairs and the /dev entry as 'path'"""

    dev_attrs = {}
    i =  line.find(":")
    dev_attrs[constants.DEV_ATTRS_PATH] = line[0:i]
    attribs = line[i+1:].split(" ")
    for attr in attribs:
        if len(attr) == 0:
            continue
        name, val = attr.split("=")
        dev_attrs[name.lower()] = val.strip('"')
    return dev_attrs
    
def scan():
    devices = {}
    rc, out = run_command("/sbin/blkid -c /dev/null")
    if rc == 0 and out:
        for line in out.split("\n"):
            attrs = parse_blkid(line)
            devices[attrs[constants.DEV_ATTRS_PATH]] = attrs
    return devices

def mount_dev(dev, dev_type, mntpnt, options):
    umount_dev(mntpnt) # just a precaution, don't care if it fails
    # be paranoid, try to fsck it first
#    rc, out = run_command("/sbin/fsck -n %s" % (dev,))
#    if rc != 0:
#        p2v_utils.trace_message("fsck failed, not mounting\n")
#        return rc
    rc, out = run_command("echo 5 > /proc/sys/kernel/printk")
    rc, out = run_command("mount -o %s -t %s %s %s %s" % (options, dev_type,
                                                       dev, mntpnt, p2v_utils.show_debug_output()))
    return rc

def umount_dev(mntpnt):
    rc, out = run_command("umount %s" % (mntpnt))
    return rc

def umount_all_dev(devices):
    fp = open("/proc/mounts")
    mounts = load_fstab(fp)
    for dev_name, dev_attrs in devices.items():
        candidates = [ x[0] for x in mounts.keys() if x[1] == dev_name ]
        if not len(candidates):
            continue
        assert(len(candidates) == 1)
        umount_dev(candidates[0])

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
        if value.has_key(constants.DEV_ATTRS_LABEL) and value[constants.DEV_ATTRS_LABEL] == label:
            return value[constants.DEV_ATTRS_PATH]
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

def determine_size(mntpnt, dev_name):
    fp = open(os.path.join(mntpnt, 'etc', 'fstab'))
    fstab = load_fstab(fp)
    fp.close()
    
    devices = scan()

    active_mounts = []
    p2v_utils.trace_message("* Need to mount:")
    mounts = find_extra_mounts(fstab, devices)
    for mount_info in mounts:
        p2v_utils.trace_message("  --", mount_info)
        extra_mntpnt = os.path.join(mntpnt, mount_info[1][1:])

        rc = mount_dev(mount_info[0], mount_info[2],
                       extra_mntpnt, mount_info[3] + ",ro")
        if rc != 0:
#            p2v_utils.trace_message("Failed to mount %s\n" % mount_info[0])
            return rc

        active_mounts.append(extra_mntpnt)

    command = "df -k | grep %s | awk '{print $3}'" % mntpnt
    p2v_utils.trace_message("going to run : %s" % command)
    rc, out = run_command(command);
    p2v_utils.trace_message("\n\nFS Usage : %s\n\n" % out)
    size = 0
    split_out = out.split('\n')
    for o in split_out:
        p2v_utils.trace_message("\n\nFS Usage : %s\n\n" % o)
        size += int(o)
    p2v_utils.trace_message("\n\nFinal FS Usage : %d\n\n" % size)
    
    for item in active_mounts:
        # assume the umount works
        umount_dev(item)

    return str(size)


def handle_root(mntpnt, dev_name):
    fp = open(os.path.join(mntpnt, 'etc', 'fstab'))
    fstab = load_fstab(fp)
    fp.close()
    
    devices = scan()

    active_mounts = []
    p2v_utils.trace_message("* Need to mount:")
    mounts = find_extra_mounts(fstab, devices)
    for mount_info in mounts:
        p2v_utils.trace_message("  --", mount_info)
        extra_mntpnt = os.path.join(mntpnt, mount_info[1][1:])

        rc = mount_dev(mount_info[0], mount_info[2],
                       extra_mntpnt, mount_info[3] + ",ro")
        if rc != 0:
#            p2v_utils.trace_message("Failed to mount %s\n" % mount_info[0])
            return rc

        active_mounts.append(extra_mntpnt)

    hostname = os.uname()[1]
    os.chdir(mntpnt)
    tar_basefilename = "p2v%s.%s.tar.gz" % (hostname, os.path.basename(dev_name))
    tar_filename = "/xenpending/%s" %tar_basefilename
    rc, out = run_command("tar czvf %s . %s" % (tar_filename, p2v_utils.show_debug_output()))
    rc, md5_out = run_command("md5sum %s | awk '{print $1}'" % tar_filename)
    os.chdir("/")

    for item in active_mounts:
        # assume the umount works
        umount_dev(item)

    return (0, tar_basefilename, md5_out)

def mount_os_root(dev_name, dev_attrs):
    mntbase = "/var/mnt"
    mnt = mntbase + "/" + os.path.basename(dev_name)
    rc, out = run_command("mkdir -p %s" % (mnt))
    if rc != 0:
        p2v_utils.trace_message("mkdir failed\n")
        sys.exit(1)
    
    rc = mount_dev(dev_name, dev_attrs['type'], mnt, 'ro')
#    if rc != 0:
 #          p2v_utils.trace_message("Failed to mount mnt")
    return mnt

def inspect_root(dev_name, dev_attrs, results):
    mnt = mount_os_root(dev_name, dev_attrs)
    if os.path.exists(os.path.join(mnt, 'etc', 'fstab')):
       p2v_utils.trace_message("* Found root partition on %s" % dev_name)
       rc, out = run_command("/opt/xensource/clean-installer/p2v/read_osversion.sh " + mnt)
       if rc == 0:
           p2v_utils.trace_message("read_osversion succeeded : out = %s" % out)
           parts = out.split('\n')
           if len(parts) > 0:
               os_install = {}
               p2v_utils.trace_message("found os name: %s" % parts[0])
               p2v_utils.trace_message("found os version : %s" % parts[1])
               
               #results.append([parts[0], parts[1], dev_name, dev_attrs, out])
               os_install[constants.OS_NAME] = parts[0]
               os_install[constants.OS_VERSION] = parts[1]
               os_install[constants.DEV_NAME] = dev_name
               os_install[constants.DEV_ATTRS] = dev_attrs
               results.append(os_install)
       else:
           p2v_utils.trace_message("read_osversion failed : out = %s" % out)
    umount_dev(mnt)

def findroot():
    devices = scan()
    results = []

    for dev_name, dev_attrs in devices.items():
        if dev_attrs.has_key(constants.DEV_ATTRS_TYPE) and dev_attrs[constants.DEV_ATTRS_TYPE] in ('ext2', 'ext3', 'reiserfs'):
            inspect_root(dev_name, dev_attrs, results)
                   
    #run_command("sleep 2")
    return results
    

if __name__ == '__main__':
    mntbase = "/var/mnt"

    devices = scan()

    umount_all_dev(devices)

    for dev_name, dev_attrs in devices.items():
        if dev_attrs.has_key(constants.DEV_ATTRS_TYPE) and dev_attrs[constants.DEV_ATTRS_TYPE] in ('ext2', 'ext3', 'reiserfs'):
            mnt = mntbase + "/" + os.path.basename(dev_name)
            rc, out = run_command("mkdir -p %s" % (mnt))
            if rc != 0:
                p2v_utils.trace_message("mkdir failed\n")
                sys.exit(1)

            rc = mount_dev(dev_name, dev_attrs[constants.DEV_ATTRS_TYPE], mnt, 'ro')
            if rc != 0:
                p2v_utils.trace_message("Failed to mount mnt")
                continue
                #sys.exit(rc)

            if os.path.exists(os.path.join(mnt, 'etc', 'fstab')):
                p2v_utils.trace_message("* Found root partition on %s" % dev_name)
                rc, tar_filename, md5sum = handle_root(mnt, dev_name)
                if rc != 0:
                    p2v_utils.trace_message("%s failed\n" % dev_name)
                    sys.exit(rc)

            umount_dev(mnt)
