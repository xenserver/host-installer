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

import util
from util import dev_null
import xelogging

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
    return device in getRemovableDeviceList()

def getQualifiedDeviceName(disk):
    return "/dev/%s" % disk

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
    if True in [partition.startswith(x) for x in ['/dev/cciss', '/dev/ida', '/dev/rd']]:
        numlen += 1 # need to get rid of trailing 'p'

    # is it /dev/disk/by-id/XYZ-part<k>?
    if partition.startswith("/dev/disk/by-id"):
        return partition[:partition.rfind("-part")]

    return partition[:len(partition) - numlen]

def partitionNumberFromPartition(partition):
    match = re.search(r'([0-9]+)$',partition)
    if not match:
        raise Exception('Cannot extract partition number from '+partition)
    return int(match.group(1))

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

################################################################################
# TOOLS FOR PARTITIONING DISKS

def clearDiskPartitions(disk):
    assert disk[:5] == '/dev/'
    assert util.runCmd2(["dd", "if=/dev/zero", "of=%s" % disk, "bs=512", "count=1"]) == 0

# partitions is a list of sizes in MB, currently we only make primary partitions.
# this is a completely destructive process.
#
# The last size may be -1, which is a special value indicating that the rest
# of the disk should be used.
def writePartitionTable(disk, partitions):
    xelogging.log("About to write partition table %s to disk %s" % (partitions, disk))
    
    clearDiskPartitions(disk)

    pipe = subprocess.Popen(['/sbin/fdisk', disk], stdin = subprocess.PIPE,
                            stdout = dev_null(), stderr = dev_null(), close_fds = True)

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

    # Wait for the udev events to be correctly processed:
    if os.path.exists('/sbin/udevsettle'):
        os.system('/sbin/udevsettle --timeout=5')


def makeActivePartition(disk, partition_number):
    xelogging.log("About to make an active partition on disk %s" % disk)

    pipe = subprocess.Popen(['/sbin/fdisk', disk], stdin = subprocess.PIPE,
                            stdout = dev_null(), stderr = dev_null())

    pipe.stdin.write('a\n') # toggle bootable flag
    pipe.stdin.write('%d\n' % int(partition_number)) # ith partition

    # write the partition table to disk:
    pipe.stdin.write('w\n')

    # wait for fdisk to finish:
    assert pipe.wait() == 0

def getVolumeGroups():
    """ Returns a list of strings, each of which is the
    name of a volume group found by 'vgs'. """

    vgs = []
    pipe = subprocess.Popen(['vgs', '--noheadings'], bufsize = 1, stdout = subprocess.PIPE,
                            stderr = dev_null(), close_fds = True)
    for line in pipe.stdout:
        vgs.append(line.split()[0])
    pipe.wait()

    return vgs

# get a mapping of partitions to the volume group they are part of:
def getVGPVMap():
    rv = {}
    pipe = subprocess.Popen(['pvscan'], bufsize = 1, stdout = subprocess.PIPE,
                            stderr = dev_null(), close_fds = True)
    for line in pipe.stdout:
        a = line.split()
        if a[0] == 'PV' and a[2] == 'VG':
            if rv.has_key(a[3]):
                rv[a[3]].append(a[1])
            else:
                rv[a[3]] = [a[1]]
    pipe.wait()

    return rv

# given a list of disks, work out which ones are part of volume
# groups that will cause a problem if we install XE to those disks:
def findProblematicVGs(disks):
    # which partitions are the volue groups on?
    vgpvmap = getVGPVMap()

    # which disks are the volume groups on?
    vgdiskmap = {}
    for vg in vgpvmap:
        vgdiskmap[vg] = [diskFromPartition(x) for x in vgpvmap[vg]]

    # for each VG, map the disk list to a boolean list saying whether that
    # disk is in the set we're installing to:
    vgusedmap = {}
    for vg in vgdiskmap:
        vgusedmap[vg] = [disk in disks for disk in vgdiskmap[vg]]

    # now, a VG is problematic if it its vgusedmap entry contains a mixture
    # of Trua and False.  If it's entirely True or entirely False, that's OK:
    problems = []
    for vg in vgusedmap:
        p = False
        for x in vgusedmap[vg]:
            if x != vgusedmap[vg][0]:
                p = True
        if p:
            problems.append(vg)

    return problems

def determinePartitionName(guestdisk, partitionNumber):
    if guestdisk.find("cciss") != -1 or \
        guestdisk.find("ida") != -1 or \
        guestdisk.find("rd") != -1 or \
        guestdisk.find("sg") != -1 or \
        guestdisk.find("i2o") != -1 or \
        guestdisk.find("amiraid") != -1 or \
        guestdisk.find("iseries") != -1 or \
        guestdisk.find("emd") != -1 or \
        guestdisk.find("carmel") != -1:
        return guestdisk + "p%d" % partitionNumber
    elif "disk/by-id" in guestdisk:
        return guestdisk + "-part%d" % partitionNumber
    else:
        return guestdisk + "%d" % partitionNumber

class PartitionRecord:
    ELEMENTS = ['partition_number', 'bootable', 'type', 'lba_start', 'lba_size', 'start', 'size']
    def __init__(self, *args, **keywords):
        for k, v in keywords.items():
            assert k in self.ELEMENTS # Check this is a name that we expect
            setattr(self, k, v)
        assert len(keywords) == len(self.ELEMENTS)
        
    def __str__(self):
        return ', '.join( [ name+"='"+str(getattr(self, name))+"'" for name in self.ELEMENTS ] )    

def readPartitionInfoFromImageFD(file_desc, partition_number):
    # On entry, the current posisiton in the file should be at the start of the partition table
    
    # Assume a 512 byte sector size.  This will be true for our images but not for some hard disks
    SECTOR_SIZE = 512

    # Skip code area (440 bytes), optional disk signature (4) bytes, and NULLs (2 bytes)
    file_desc.read(446)
    record = None
    for i in range(4):
        boot_byte = ord(file_desc.read(1))
        if boot_byte == 0:
            bootable = False
        elif boot_byte == 0x80:
            bootable = True
        else:
            raise Exception('Corrupt partition table in image - status value '+str(boot_byte))
        hsc_start = [ ord(c) for c in file_desc.read(3) ] # Start sector as head/sector/cylinder
        type = ord(file_desc.read(1))

        hsc_end = [ ord(c) for c in file_desc.read(3) ] # End sector as head/sector/cylinder
        # Read LBA start and size as 4 byte little-endian values
        lba_start = reduce( lambda x, y: (x << 8) + y, reversed([ ord(c) for c in file_desc.read(4) ]) )
        lba_size = reduce( lambda x, y: (x << 8) + y, reversed([ ord(c) for c in file_desc.read(4) ]) )

        if i+1 == partition_number:
            if type == 15:
                raise Exception('Extended partitions are not supported')
            record  = PartitionRecord(partition_number=partition_number, bootable=bootable,
                type=type, lba_start=lba_start, lba_size=lba_size,
                start = lba_start*SECTOR_SIZE, size= lba_size * SECTOR_SIZE)

    if file_desc.read(2) != '\x55\xaa':
        raise Exception('Invalid boot record signature in partition table')
    
    if record is None:
        raise Exception('No record for partition number '+str(partition_number))
    
    return record
    
if __name__ == '__main__':
    fd = file(sys.argv[1],'r')
    for i in range(4):
        pprint(str(readPartitionInfoFromImageFD(fd, i+1)))
        fd.seek(0, 0) # Go back to file start
    fd.close()
    
