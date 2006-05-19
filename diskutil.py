###
# XEN CLEAN INSTALLER
# Disk discovery and utilities
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import re
import os.path
import subprocess
import util

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
    return __readOneLineFile__("/sys/block/%s/device/vendor" % dev).strip(' \n')

def getDiskDeviceModel(dev):
    return __readOneLineFile__("/sys/block/%s/device/model" % dev).strip('  \n')
    
def getDiskDeviceSize(dev):
    if os.path.exists("/sys/block/%s/device/block/size" % dev):
        return int(__readOneLineFile__("/sys/block/%s/device/block/size" % dev))
    elif os.path.exists("/sys/block/%s/size" % dev):
        return int(__readOneLineFile__("/sys/block/%s/size" % dev))
    
def blockSizeToGBSize(blocks):
    return (long(blocks) * 512) / (1024 * 1024 * 1024)
    
def getHumanDiskSize(blocks):
    return "%d GB" % blockSizeToGBSize(blocks)

def getExtendedDiskInfo(disk):
    devname = os.path.basename(disk)

    return (getDiskDeviceVendor(devname),
            getDiskDeviceModel(devname),
            getDiskDeviceSize(devname))


################################################################################
# TOOLS FOR PARTITIONING DISKS

def clearDiskPartitions(disk):
    assert disk[:5] == '/dev/'
    assert util.runCmd("dd if=/dev/zero of=%s count=512 bs=1" % disk) == 0

# partitions is a list of sizes in MB, currently we only make primary partitions.
# this is a completely destructive process.
#
# The last size may be -1, which is a special value indicating that the rest
# of the disk should be used.
def writePartitionTable(disk, partitions):
    clearDiskPartitions(disk)

    pipe = subprocess.Popen(['/sbin/fdisk', disk], stdin = subprocess.PIPE,
                            stdout = subprocess.PIPE, stderr = subprocess.PIPE)

    for i in range(0, len(partitions)):
        pipe.stdin.write('n\n') # new partition
        pipe.stdin.write('p\n') # primary
        pipe.stdin.write('%d\n' % (i + 1)) # ith partition
        pipe.stdin.write('\n')  # default start cylinder
        if partitions[i] == -1:
            pipe.stdin.write('\n') # use rest of disk
        else:
            pipe.stdin.write('+%dM\n' % partitions[i]) # size in MB

    # write the partition table to disk:
    pipe.stdin.write('w\n')

    # wait for fdisk to finish:
    assert pipe.wait() == 0

    # XXX - hack to make device nodes appear
    if os.path.exists('/sbin/udevstart'):
        os.system('/sbin/udevstart')
