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
import popen2

disk_nodes = [
    # sda -> sdh:
    (8, 0), (8,16), (8, 32), (8,48), (8,64), (8,80), (8,96),
    (8, 112),

    # hda -> hdh:
    (3,0), (3, 64), (22, 0), (22, 64), (33, 0), (33, 64),
    (34, 0), (34, 64)
    ]

# c{0,1,2}d0 -> c{0,1,2}d15
disk_nodes += map(lambda x: (104, x * 16), range(0, 15))
disk_nodes += map(lambda x: (105, x * 16), range(0, 15))
disk_nodes += map(lambda x: (106, x * 16), range(0, 15))

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

def getQualifiedDiskList():
    return map(lambda x: getQualifiedDeviceName(x), getDiskList())

def getQualifiedDeviceName(disk):
    if disk.startswith('sd') or \
       disk.startswith('hd') or \
       disk.startswith('cciss'):
        return "/dev/%s" % disk
    else:
        # TODO we should throw an exception here instead:
        return None

# Given a partition (e.g. /dev/sda1), get a disk name:
def diskFromPartition(partition):
    numlen = 1
    while 1:
        try:
            partnum = int(partition[len(partition) - numlen:])
        except:
            # move back one as this value failed.
            numlen -= 1 
            break
        else:
            numlen += 1

    # is it a cciss?
    if partition[:10] == '/dev/cciss':
        numlen += 1 # need to get rid of trailing 'p'
    return partition[:len(partition) - numlen]
        

def __readOneLineFile__(filename):
    try:
        f = open(filename)
        value = f.readline()
        f.close()
        return value
    except Exception, e:
        raise e

def getDiskDeviceVendor(dev):
    dev = dev.replace("/", "!")
    if os.path.exists("/sys/block/%s/device/vendor" % dev):
        return __readOneLineFile__("/sys/block/%s/device/vendor" % dev).strip(' \n')
    else:
        return ""

def getDiskDeviceModel(dev):
    dev = dev.replace("/", "!")
    if os.path.exists("/sys/block/%s/device/model" % dev):
        return __readOneLineFile__("/sys/block/%s/device/model" % dev).strip('  \n')
    else:
        return ""
    
def getDiskDeviceSize(dev):
    dev = dev.replace("/", "!")
    if os.path.exists("/sys/block/%s/device/block/size" % dev):
        return int(__readOneLineFile__("/sys/block/%s/device/block/size" % dev))
    elif os.path.exists("/sys/block/%s/size" % dev):
        return int(__readOneLineFile__("/sys/block/%s/size" % dev))
    
def blockSizeToGBSize(blocks):
    return (long(blocks) * 512) / (1024 * 1024 * 1024)
    
def getHumanDiskSize(blocks):
    return "%d GB" % blockSizeToGBSize(blocks)

def getExtendedDiskInfo(disk):
    devname = disk.replace("/dev/", "")

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
    
# get a mapping of partitions to the volume group they are part of:
def getVGPVMap():
    pipe = popen2.Popen3("pvscan 2>/dev/null | egrep '*[ \t]*PV' | awk '{print $2,$4;}'")
    volumes = pipe.fromchild.readlines()
    pipe.wait()

    volumes = map(lambda x: x.strip('\n').split(' '), volumes)
    rv = {}
    for [vg, pv] in volumes:
        if rv.has_key(pv):
            rv[pv].append(vg)
        else:
            rv[pv] = [vg]

    return rv

# given a list of disks, work out which ones are part of volume
# groups that will cause a problem if we install XE to those disks:
def findProblematicVGs(disks):
    vgmap = getVGPVMap()

    problems = []
    for vg in vgmap:
        # are we looking at wiping out only part of a volume
        # group here?
        _vgdisks = map(lambda x: diskFromPartition(x), vgmap[vg])
        vgdisks = []
        for disk in _vgdisks:
            if disk not in vgdisks:
                vgdisks.append(disk)

        # if the disks in the volume group is not a subset of the
        # disks we are installing to, but the the volume group
        # resides on at least one disk that we're installing to
        # then there is a problem associated with that VG:
        if not util.subset(vgdisks, disks) and \
           len(util.intersect(vgdisks, disks)) != 0:
            problems.append(vg)

    return problems

# does VG_XenSource already exist?
def detectExistingInstallation():
    # yuck
    return os.system("vgscan 2>/dev/null | grep -q 'VG_XenSource'") == 0
