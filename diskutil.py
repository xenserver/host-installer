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

# Given a disk (eg. /dev/sda) and a partition number, get a partition name:
def partitionFromDisk(disk, pnum):
    midfix = ""
    if re.search("/cciss/", disk):
        midfix = "p"
    elif re.search("/disk/by-id/", disk):
        midfix = "-part"
    return disk + midfix + str(pnum)

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
    bytes = fd.read(82)
    fd.close()

    if bytes[83:87] == "FAT32":
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

################################################################################
# TOOLS FOR PARTITIONING DISKS

def clearDiskPartitions(disk):
    assert disk[:5] == '/dev/'
    assert util.runCmd2(["dd", "if=/dev/zero", "of=%s" % disk, "bs=512", "count=1"]) == 0

# partitions is a list of sizes in MB, currently we only make primary partitions.
# first_xensource_partition is the number of the first partition to create.  All
# existing partitions with lower numbers will be preserved.
#
# The last size may be -1, which is a special value indicating that the rest
# of the disk should be used.
def writePartitionTable(disk, partitions, first_xensource_partition):
    xelogging.log("About to write partition table %s to disk %s" % (partitions, disk))
    
    if first_xensource_partition == 1:
        # we create a new table
        pass
    else:
        # we preserve partitions with lower partnums: collect the numbers of partitions to delete
        part_names = partitionsOnDisk(disk)
        part_nums = map(partitionNumberFromPartition, part_names)
        part_nums_to_delete = filter(lambda n: n >= first_xensource_partition, part_nums)
        part_nums_to_delete.sort()
        part_nums_to_delete.reverse()   # reverse order so logical partitions are deleted first

    # start fdisk
    pipe = subprocess.Popen(['/sbin/fdisk', disk], stdin = subprocess.PIPE,
                            stdout = dev_null(), stderr = dev_null(), close_fds = True)

    # delete existing partitions
    if first_xensource_partition == 1:
        pipe.stdin.write('o\n') # create new table
    else:
        for i in part_nums_to_delete:
            pipe.stdin.write('d\n')  # delete partition
            pipe.stdin.write('%d\n' % i) # ith partition
            
    # create new partitions
    for i in range(0, len(partitions)):
        pipe.stdin.write('n\n') # new partition
        pipe.stdin.write('p\n') # primary
        pipe.stdin.write('%d\n' % (i + first_xensource_partition)) # ith partition
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

# This function is deliberately _very_ similar to the one above
# in order to result in the same partition table
def addRootPartition(disk, primary_partition_number, partition_size):
    xelogging.log("About to write a root partition #%d to disk %s" % (primary_partition_number, disk))
    
    pipe = subprocess.Popen(['/sbin/fdisk', disk], stdin = subprocess.PIPE,
                            stdout = dev_null(), stderr = dev_null(), close_fds = True)

    pipe.stdin.write('n\n') # new partition
    pipe.stdin.write('p\n') # primary
    pipe.stdin.write('%d\n' % primary_partition_number) # partition
    pipe.stdin.write('\n')  # default start cylinder
    pipe.stdin.write('+%dM\n' % partition_size) # size in MB

    # write the partition table to disk:
    pipe.stdin.write('w\n')

    # wait for fdisk to finish:
    assert pipe.wait() == 0

    # Wait for the udev events to be correctly processed:
    if os.path.exists('/sbin/udevsettle'):
        os.system('/sbin/udevsettle --timeout=5')

def removePrimaryPartition(disk, primary_partition_number):
    cmd = ["/sbin/sfdisk", "--force", disk, "-N", str(primary_partition_number)]
    pipe = subprocess.Popen(cmd, stdin = subprocess.PIPE,
                                 stdout = dev_null(), stderr = dev_null(), close_fds = True)
    pipe.stdin.write("0,0,0,-,\n")
    pipe.stdin.close()
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

def getActivePartition(disk):
    """ Returns the active partition, if any"""
    xelogging.log("Reading the active partition on disk %s" % disk)

    active = None
    pipe = subprocess.Popen(['/sbin/sfdisk', '-l', '-d', disk], bufsize = 1,
                            stdin = dev_null(), stdout = subprocess.PIPE,
                            stderr = dev_null(), close_fds = True)
    for line in pipe.stdout:
        theline = line.strip()
        if theline.endswith('bootable'):
            try:
                active = theline.split(':')[0].strip()
            except:
                xelogging.log("Failed to parse the active partition on disk %s" % disk)
                raise
    pipe.wait()
    return active

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
            if type in (0x05, 0x0F, 0x85):
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
    
class IscsiDeviceException(Exception):
    pass

def is_iscsi(device):
    # Return True if this is an iscsi device
    buf = os.stat(device)
    major = os.major(buf.st_rdev)
    minor = os.minor(buf.st_rdev)

    # find /sys/block node
    sysblockdir = None
    sysblockdirs = [ "/sys/block/" + dev for dev in os.listdir("/sys/block")
                     if (not dev.startswith('loop')) and (not dev.startswith('ram')) ]
    for d in sysblockdirs:
        if os.path.isfile(d + "/dev") and os.path.isfile(d + "/range"):
            __major, __minor = map(int, open(d + "/dev").read().split(':'))
            __range  = int(open(d + "/range").read())
            if major == __major and __minor <= minor <= __minor + __range:
                sysblockdir = d
                break
    
    if not sysblockdir:
        raise IscsiDeviceException, "Cannot find " + device + " in /sys/block"
    
    devpath = os.path.realpath(sysblockdir + "/device")

    if not os.path.isdir("/sys/class/iscsi_session"):
        # iscsi modules not even loaded
        return False 

    # find list of iSCSI block devs
    for d in os.listdir("/sys/class/iscsi_session"):
        __devpath = os.path.realpath("/sys/class/iscsi_session/" + d + "/device")
        if devpath.startswith(__devpath):
            # we have a match!
            return True
    
    return False

def iscsi_address_port_netdev(device):
    # Return address, port, and netdev used to access this iscsi device
    buf = os.stat(device)
    major = os.major(buf.st_rdev)
    minor = os.minor(buf.st_rdev)
    
    # find /sys/block node
    sysblockdir = None
    sysblockdirs = [ "/sys/block/" + dev for dev in os.listdir("/sys/block") ]
    for d in sysblockdirs:
        if os.path.isfile(d + "/dev") and os.path.isfile(d + "/range"):
            __major, __minor = map(int, open(d + "/dev").read().split(':'))
            __range  = int(open(d + "/range").read())
            if major == __major and __minor <= minor <= __minor + __range:
                sysblockdir = d
                break
        
    if not sysblockdir:
        raise IscsiDeviceException, "Cannot find " + device + " in /sys/block"

    devpath = os.path.realpath(sysblockdir + "/device")

    # find matching session
    for s in os.listdir("/sys/class/iscsi_session"):
        __devpath = os.path.realpath("/sys/class/iscsi_session/" + s + "/device")
        if devpath.startswith(__devpath):
            # we have a match!
            connections = [ "/sys/class/iscsi_session/" + s + "/device/" + c 
                            for c in os.listdir("/sys/class/iscsi_session/" + s + "/device/")
                            if c.startswith("connection") ]
            if len(connections) == 0:
                raise IscsiDeviceException, "Cannot find connections in /sys/class/iscsi_session/" + s + "/device/"

            # just choose the first one and ignore the rest: they should all map to the same IP:port
            connection = connections[0]

            iscsi_connections = [ connection + "/" + i 
                                 for i in os.listdir(connection)
                                 if i.startswith("iscsi_connection") ]
            if len(iscsi_connections) == 0:
                raise IscsiDeviceException, "Cannot find iscsi_connections in " + connection
    
            # just choose the first one and ignore the rest: they should all map to the same IP:port
            iscsi_connection = iscsi_connections[0]
            
            ipaddr = open(iscsi_connection + "/persistent_address").read().strip()
            port = int(open(iscsi_connection + "/persistent_port").read())
            rv, out = util.runCmd2(['ip','route','get',ipaddr], with_stdout=True)
            try:
                tokens = out.split('\n')[0].split()
                idx = tokens.index('dev')
                netdev = tokens[idx + 1]
            except:
                raise IscsiDeviceException, "Cannot determine netdev used ofr iscsi device " + devpath

            return ipaddr, port, netdev


    raise IscsiDeviceException, "Cannot find matching session for " + devpath

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

# Get partitions numbers to use for root, backup, localSR.
#
# These will normally be 1,2,3, but may be 2, 3, 4 for disks on which we wish to
# the preserve contents of the 1st partition, e.g. for a revert-to-factory image.
__rootPartNumbers = {}

# Specify partition number used for root on this disk.  Installer must not touch earlier partitions
def preservePart1(disk):
    __rootPartNumbers[disk] = 2
    
def getRootPartNumber(disk):
    return __rootPartNumbers.get(disk, 1)

def getRootPartName(disk):
    return determinePartitionName(disk, getRootPartNumber(disk))

def getBackupPartNumber(disk):
    return getRootPartNumber(disk) + 1

def getBackupPartName(disk):
    return determinePartitionName(disk, getBackupPartNumber(disk))

def getSRPartNumber(disk):
    return getBackupPartNumber(disk) + 1

def getSRPartName(disk):
    return determinePartitionName(disk, getSRPartNumber(disk))

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
