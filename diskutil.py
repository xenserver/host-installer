# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Disk discovery and utilities
#
# written by Andrew Peace

import re, sys
import os.path
import subprocess
from pprint import pprint
import constants

import util
from util import dev_null
import xelogging
from disktools import *

# hd* -> (ide has majors 3, 22, 33, 34, 56, 57, 88, 89, 90, 91, each major has
# two disks, with minors 0... and 64...)
ide_majors = [ 3, 22, 33, 34, 56, 57, 88, 89, 90, 91 ]
disk_nodes  = [ (x, 0) for x in ide_majors ]
disk_nodes += [ (x, 64) for x in ide_majors ]

# sd* -> (sd-mod has majors 8, 65 ... 71: each device has eight minors, each 
# major has sixteen disks).
disk_nodes += [ (8, x * 16) for x in range(16) ]
disk_nodes += [ (65, x * 16) for x in range(16) ]
disk_nodes += [ (66, x * 16) for x in range(16) ]
disk_nodes += [ (67, x * 16) for x in range(16) ]
disk_nodes += [ (68, x * 16) for x in range(16) ]
disk_nodes += [ (69, x * 16) for x in range(16) ]
disk_nodes += [ (70, x * 16) for x in range(16) ]
disk_nodes += [ (71, x * 16) for x in range(16) ]

# xvd* -> (blkfront has major 202: each device has 15 minors)
disk_nodes += [ (202, x * 16) for x in range(16) ]

# /dev/cciss : c[0-7]d[0-15]: Compaq Next Generation Drive Array
# /dev/ida   : c[0-7]d[0-15]: Compaq Intelligent Drive Array
for major in range(72, 80) + range(104, 112):
    disk_nodes += [ (major, x * 16) for x in range(16) ]

# /dev/rd    : c[0-7]d[0-31]: Mylex DAC960 PCI RAID controller
for major in range(48, 56):
    disk_nodes += [ (major, x * 8) for x in range(32) ]

def getDiskList():
    # read the partition tables:
    parts = open("/proc/partitions")
    partlines = map(lambda x: re.sub(" +", " ", x).strip(),
                    parts.readlines())
    parts.close()

    # parse it:
    disks = []
    for l in partlines:
        try:
           (major, minor, size, name) = l.split(" ")
           (major, minor, size) = (int(major), int(minor), int(size))
           if (major, minor) in disk_nodes:
               disks.append(name.replace("!", "/"))
        except:
            # it wasn't an actual entry, maybe the headers or something:
            continue
    return disks

# this works on this principle that everything that isn't a
# disk (according to our disk_nodes) is a partition.
def getPartitionList():
    # read the partition tables:
    parts = open("/proc/partitions")
    partlines = map(lambda x: re.sub(" +", " ", x).strip(),
                    parts.readlines())
    parts.close()

    rv = []
    for l in partlines:
        try:
           (major, minor, size, name) = l.split(" ")
           (major, minor, size) = (int(major), int(minor), int(size))
           if (major, minor) not in disk_nodes:
               rv.append(name.replace("!", "/"))
        except:
            # it wasn't an actual entry, maybe the headers or something:
            continue

    return rv

def partitionsOnDisk(dev):
    if dev.startswith('/dev/'):
        dev = dev[5:]
    dev = dev.replace('/', '!')
    return filter(lambda x: x.startswith(dev),
                  os.listdir(os.path.join('/sys/block', dev)))

def getQualifiedDiskList():
    return map(lambda x: getQualifiedDeviceName(x), getDiskList())

def getQualifiedPartitionList():
    return [getQualifiedDeviceName(x) for x in getPartitionList()]

def getRemovableDeviceList():
    devs = os.listdir('/sys/block')
    removable_devs = []
    for d in devs:
        if isRemovable(d):
            removable_devs.append(d.replace("!", "/"))

    return removable_devs

def removable(device):
    if device.startswith('/dev/'):
        device = device[5:]

    # CA-25624 - udev maps sr* to scd*
    if device.startswith('scd'):
        device='sr'+device[3:]

    return device in getRemovableDeviceList()

def getQualifiedDeviceName(disk):
    return "/dev/%s" % disk

# Given a partition (e.g. /dev/sda1), get the id symlink:
def idFromPartition(partition):
    symlink = None
    v, out = util.runCmd2(['/usr/bin/udevinfo', '-q', 'symlink', '-n', partition], with_stdout = True)
    if v == 0:
        for link in out.split():
            if link.startswith('disk/by-id'):
                symlink = '/dev/'+link
                break
    return symlink

def __readOneLineFile__(filename):
    try:
        f = open(filename)
        value = f.readline()
        f.close()
        return value
    except Exception, e:
        raise e

def getDiskDeviceVendor(dev):
    if dev.startswith("/dev/"):
        dev = re.match("/dev/(.*)", dev).group(1)
    dev = dev.replace("/", "!")
    if os.path.exists("/sys/block/%s/device/vendor" % dev):
        return __readOneLineFile__("/sys/block/%s/device/vendor" % dev).strip(' \n')
    else:
        return ""

def getDiskDeviceModel(dev):
    if dev.startswith("/dev/"):
        dev = re.match("/dev/(.*)", dev).group(1)
    dev = dev.replace("/", "!")
    if os.path.exists("/sys/block/%s/device/model" % dev):
        return __readOneLineFile__("/sys/block/%s/device/model" % dev).strip('  \n')
    else:
        return ""
    
def getDiskDeviceSize(dev):
    if dev.startswith("/dev/"):
        dev = re.match("/dev/(.*)", dev).group(1)
    dev = dev.replace("/", "!")
    if os.path.exists("/sys/block/%s/device/block/size" % dev):
        return int(__readOneLineFile__("/sys/block/%s/device/block/size" % dev))
    elif os.path.exists("/sys/block/%s/size" % dev):
        return int(__readOneLineFile__("/sys/block/%s/size" % dev))

def isRemovable(dev):
    if dev.startswith("/dev/"):
        dev = re.match("/dev/(.*)", dev).group(1)
    dev = dev.replace("/", "!")
    if os.path.exists("/sys/block/%s/removable" % dev):
        return int(__readOneLineFile__("/sys/block/%s/removable" % dev)) == 1
    else:
        return False

def blockSizeToGBSize(blocks):
    return (long(blocks) * 512) / (1024 * 1024 * 1024)
    
def getHumanDiskSize(blocks):
    return "%d GB" % blockSizeToGBSize(blocks)

def getExtendedDiskInfo(disk, inMb = 0):
    devname = disk.replace("/dev/", "")

    return (getDiskDeviceVendor(devname),
            getDiskDeviceModel(devname),
            inMb and (getDiskDeviceSize(devname)/2048) or getDiskDeviceSize(devname))

def readFATPartitionLabel(partition):
    """Read the FAT partition label directly, including whitespace."""
    fd = open(partition)
    bytes = fd.read(90)
    fd.close()

    if bytes[82:87] == "FAT32":
        label = bytes[71:82]
    elif bytes[54:59] == "FAT16":
        label = bytes[43:54]
    elif bytes[54:59] == "FAT12":
        label = bytes[43:54]
    else:
        raise Exception("%s is not FAT partition" % partition)
    return label

def readExtPartitionLabel(partition):
    """Read the ext partition label."""
    rc, out = util.runCmd2(['/sbin/e2label', partition], with_stdout = True)
    if rc == 0:
        label = out.strip()
    else:
        raise Exception("%s is not ext partition" % partition)
    return label

def getHumanDiskName(disk):
    if disk.startswith('/dev/disk/by-id/'):
        return disk[16:]
    if disk.startswith('/dev/'):
        return disk[5:]
    return disk

# given a list of disks, work out which ones are part of volume
# groups that will cause a problem if we install XE to those disks:
def findProblematicVGs(disks):
    real_disks = map(lambda d: os.path.realpath(d), disks)

    # which disks are the volume groups on?
    vgdiskmap = {}
    tool = LVMTool()
    for pv in tool.pvs:
        if pv['vg_name'] not in vgdiskmap: vgdiskmap[pv['vg_name']] = []
        try:
            device = PartitionTool.diskDevice(pv['pv_name'])
        except:
            # CA-35020: whole disk
            device = pv['pv_name']
        vgdiskmap[pv['vg_name']].append(device)

    # for each VG, map the disk list to a boolean list saying whether that
    # disk is in the set we're installing to:
    vgusedmap = {}
    for vg in vgdiskmap:
        vgusedmap[vg] = [disk in real_disks for disk in vgdiskmap[vg]]

    # now, a VG is problematic if it its vgusedmap entry contains a mixture
    # of True and False.  If it's entirely True or entirely False, that's OK:
    problems = []
    for vg in vgusedmap:
        p = False
        for x in vgusedmap[vg]:
            if x != vgusedmap[vg][0]:
                p = True
        if p:
            problems.append(vg)

    return problems

def log_available_disks():
    disks = getQualifiedDiskList()

    # make sure we have discovered at least one disk and
    # at least one network interface:
    if len(disks) == 0:
        xelogging.log("No disks found on this host.")
    else:
        # make sure that we have enough disk space:
        xelogging.log("Found disks: %s" % str(disks))
        diskSizes = [getDiskDeviceSize(x) for x in disks]
        diskSizesGB = [blockSizeToGBSize(x) for x in diskSizes]
        xelogging.log("Disk sizes: %s" % str(diskSizesGB))

        dom0disks = filter(lambda x: constants.min_primary_disk_size <= x <= constants.max_primary_disk_size,
                           diskSizesGB)
        if len(dom0disks) == 0:
            xelogging.log("Unable to find a suitable disk (with a size between %dGB and %dGB) to install to." % (constants.min_primary_disk_size, constants.max_primary_disk_size))

INSTALL_RETAIL = 1
INSTALL_OEM = 2
STORAGE_LVM = 1
STORAGE_EXT3 = 2

def probeDisk(device, justInstall = False):
    """Examines device and reports the apparent presence of a XenServer installation and/or related usage
    Returns a tuple (boot, state, storage)
    
    Where:
    
    	boot is a tuple of None, INSTALL_RETAIL or INSTALL_OEM and the partition device
        state is a tuple of True or False and the partition device
        storage is a tuple of None, STORAGE_LVM or STORAGE_EXT3 and the partition device
    """

    boot = (None, None)
    state = (False, None)
    storage = (None, None)
    possible_srs = []
        
    tool = PartitionTool(device)
    for num, part in tool.iteritems():
        label = None
        part_device = tool._partitionDevice(num)

        if part['id'] == tool.ID_LINUX:
            try:
                label = readExtPartitionLabel(part_device)
            except:
                pass

        if part['active']:
            if part['id'] == tool.ID_LINUX:
                # probe for retail
                if label and label.startswith('root-'):
                    boot = (INSTALL_RETAIL, part_device)
                    state = (True, part_device)
                    if tool.partitions.has_key(num+2):
                        # George Retail and earlier didn't use the correct id for SRs
                        possible_srs = [num+2]
            elif part['id'] == tool.ID_FAT16:
                # probe for OEM
                try:
                    label = readFATPartitionLabel(part_device).strip()
                except:
                    pass
                if label == 'IHVCONFIG':
                    boot = (INSTALL_OEM, part_device)
        else:
            if part['id'] == tool.ID_LINUX_LVM:
                if num not in possible_srs:
                    possible_srs.append(num)
            elif part['id'] == tool.ID_LINUX:
                if num not in possible_srs:
                    # OEM Flash state partitions are named xe-state, and OEM HDD state partitions have generated
                    # names of the form xc+dddddddd-dddd where d is any hex digit
                    if label and (label == 'xe-state' or label.startswith('xc+')):
                        state = (True, part_device)

    if not justInstall:
        lv_tool = len(possible_srs) and LVMTool()
        for num in possible_srs:
            part_device = tool._partitionDevice(num)

            if lv_tool.isPartitionConfig(part_device):
                state = (True, part_device)
            elif lv_tool.isPartitionSR(part_device):
                storage = (STORAGE_LVM, part_device)
            else:
                pv = lv_tool.deviceToPVOrNone(part_device)
                if pv is not None and pv['vg_name'].startswith('XSLocalEXT'):
                    # odd 'ext3 in an LV' SR
                    storage = (STORAGE_EXT3, part_device)
    
    xelogging.log('Probe of '+device+' found boot='+str(boot)+' state='+str(state)+' storage='+str(storage))

    return (boot, state, storage)
