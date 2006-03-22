#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Disk discovery and utilities
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import re
import os.path

disk_nodes = [
    # sda -> sdh:
    (8, 0), (8,16), (8, 32), (8,48), (8,64), (8,80), (8,96),
    (8, 112),

    # hda -> hdh:
    (3,0), (3, 64), (22, 0), (22, 64), (33, 0), (33, 64),
    (34, 0), (34, 64)
    ]

# c{0,1,2}d0 -> c{0,1,2}d15
disk_nodes.append(map(lambda x: (104, x * 16), range(0, 15)))
disk_nodes.append(map(lambda x: (105, x * 16), range(0, 15)))
disk_nodes.append(map(lambda x: (106, x * 16), range(0, 15)))

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
               disks.append(name)
        except:
            # it wasn't an actual entry, maybe the headers or something:
            continue
        
    return disks

def getQualifiedDiskList():
    return map(lambda x: getQualifiedDeviceName(x), getDiskList())

def getQualifiedDeviceName(disk):
    if disk[:2] == "sd" or disk[:2] == "hd":
        return "/dev/%s" % disk
    elif disk[0] == "c" and disk[2] == "d":
        return "/dev/cciss/%s" % disk
    else:
        # TODO we should throw an exception here instead:
        return None

def __readOneLineFile__(filename):
    try:
        f = open(filename)
        value = f.readline()
        f.close()
        return value
    except Exception, e:
        raise e

def getDiskDeviceVendor(dev):
    return __readOneLineFile__("/sys/block/%s/device/vendor" % dev)

def getDiskDeviceModel(dev):
    return __readOneLineFile__("/sys/block/%s/device/model" % dev)

def getDiskDeviceSize(dev):
    return int(__readOneLineFile__("/sys/block/%s/device/block/size" % dev))

def blockSizeToGBSize(blocks):
    return (long(blocks) * 512) / (1024 * 1024 * 1024)

def getHumanDiskSize(blocks):
    return "%d GB" % blockSizeToGBSize(blocks)

def getExtendedDiskInfo(disk):
    devname = os.path.basename(disk)

    return (getDiskDeviceVendor(devname),
            getDiskDeviceModel(devname),
            getDiskDeviceSize(devname))
