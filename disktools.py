#!/usr/bin/env python
# Copyright (c) Citrix Systems 2009.  All rights reserved.
# Xen, the Xen logo, XenCenter, XenMotion are trademarks or registered
# trademarks of Citrix Systems, Inc., in the United States and other
# countries.

import re, subprocess, sys, types
from pprint import pprint
from copy import copy, deepcopy
import util, xelogging

class Segment:
    """Segments are areas, e.g. disk partitions or LVM segments, defined by start address and size"""
    def __init__(self, start, size):
        self.start = start
        self.size = size
        
    def end(self):
        return self.start + self.size
        
    def __repr__(self):
        repr = { 'end' : self.end() }
        repr.update(self.__dict__)
        return str(repr)

class MoveChunk:
    """MoveChunks represent a move.  They contain source and destination addresses"""
    def __init__(self, src, dest, size):
        self.src = src
        self.dest = dest
        self.size = size

    def __repr__(self):
        return str(self.__dict__)

class FreePool:
    """FreePool manages the allotment of segments a pool of free segments, and
    divides segments as necessary to fill the requested size exactly"""
    def __init__(self, freeSegments, usedThreshold = 0):
        self.freeSegments = freeSegments
        # Instead of altering the free segment list as free space is consumed by takeSegments,
        # this class maintains a usedThreshold address.  Addresses lower than the threshold
        # have already been used, and those at or above it are still available
        self.usedThreshold = usedThreshold
    
    def freeSpace(self):
        sizeLeft = 0
        for seg in self.freeSegments:
            freeSize = min(seg.size, seg.end() - self.usedThreshold)
            if freeSize > 0:
                sizeLeft += freeSize
        
        return sizeLeft
    
    def takeSegments(self, size):
        """Returns a LIST of segments that fill the requested size, and effectively removes
        those segments from the free pool by increasing usedThreshold"""
        initialFreeSpace= self.freeSpace()
        segsToTake = []
        sizeLeft = size
        for seg in self.freeSegments:
            availableStart = max(seg.start, self.usedThreshold)
            sizeToTake = min(seg.end() - availableStart, sizeLeft)
            if sizeToTake> 0:
                takenSegment = Segment(availableStart, sizeToTake)
                segsToTake.append(takenSegment)
                self.usedThreshold = takenSegment.end()
                sizeLeft -= takenSegment.size
            assert sizeLeft >= 0 # Underflow implies a logic error

        if sizeLeft > 0:
            raise Exception("Disk allocation failed - out of space")

        assert size == sum([seg.size for seg in segsToTake]) # Check we've allocated the size required
        assert size == initialFreeSpace - self.freeSpace() # Check that free space has shrunk by the right amount

        return segsToTake

    def __repr__(self):
        return str(self.__dict__)
        
class LVMTool:
    # Separation character - mustn't appear in anything we expect back from pvs/vgs/lvs
    SEP='#'
    
    # Evacuate this many more extents than pvresize theoretically requires
    PVRESIZE_EXTENT_MARGIN=0
    
    # Volume group prefixes
    VG_SWAP_PREFIX='VG_XenSwap'
    VG_CONFIG_PREFIX='VG_XenConfig'
    VG_SR_PREFIX='VG_XenStorage'
    
    PVMOVE=['pvmove']
    LVCHANGE=['lvchange']
    LVREMOVE=['lvremove']
    VGCHANGE=['vgchange']
    VGREMOVE=['vgremove']
    PVREMOVE=['pvremove']
    PVRESIZE=['pvresize']
    
    VGS_INFO = { # For one-per-VG records
        'command' : ['/sbin/lvm', 'vgs'],
        'arguments' : ['--noheadings', '--nosuffix', '--units', 'b', '--separator', SEP],
        'string_options' : ['vg_name'],
        'integer_options' : []
    }

    LVS_SEG_INFO = { # For one-per-LV-segment records
        'command' : ['/sbin/lvm', 'lvs'],
        'arguments' : ['--noheadings', '--nosuffix', '--units', 'b', '--separator', SEP, '--segments'],
        'string_options' : ['seg_pe_ranges'],
        'integer_options' : []
    }
    LVS_INFO = { # For one-per-LV records
        'command' : ['/sbin/lvm', 'lvs'],
        'arguments' : ['--noheadings', '--nosuffix', '--units', 'b', '--separator', SEP],
        'string_options' : ['lv_name', 'vg_name'],
        'integer_options' : []
    }
    PVS_INFO = { # For one-per-PV records
        'command' : ['/sbin/lvm', 'pvs'],
        'arguments' : ['--noheadings', '--nosuffix', '--units', 'b', '--separator', SEP],
        'string_options' : ['pv_name', 'vg_name'],
        'integer_options' : ['pe_start', 'pv_size', 'pv_free', 'pv_pe_count', 'dev_size']
    }
    
    def __init__(self):
        self.readAllInfo()
        self.pvsToDelete = []
        self.vgsToDelete = []
        self.lvsToDelete = []
        # moveLists are per device, so self.moveLists might be{ '/dev/sda3': [MoveChunk, MoveChunk, ...], '/dev/sdb3' : ... }
        self.moveLists = {}
        self.resizeList = []
 
    @classmethod
    def cmdWrap(cls, params, exceptOnFail = True):
        rv, out, err = util.runCmd2(params, True, True)
        if exceptOnFail and rv != 0:
            if isinstance(err, (types.ListType, types.TupleType)):
                raise Exception("\n".join(err)+"\nError="+str(rv))
            else:
                raise Exception(str(err)+"\nError="+str(rv))
        return out
        
    def readInfo(self, info):
        retVal = []
        allOptions = info['string_options'] + info['integer_options']
        cmd = info['command'] + info['arguments'] + ['--options', ','.join(allOptions)]
        out = self.cmdWrap(cmd, False)

        for line in out.strip().split('\n'):
            try:
                # Create a dict of the form 'option_name':value
                data = dict(zip(allOptions, line.lstrip().split(self.SEP)))
                if len(data) != len(allOptions):
                    raise Exception("Wrong number of options in reply")
                for name in info['integer_options']:
                    # Convert integer options to integer type
                    data[name] = int(data[name])
                retVal.append(data)
            except Exception, e:
                xelogging.log("Discarding corrupt LVM output line '"+str(line)+"'")
                xelogging.log("  Command was '"+str(cmd)+"'")
                xelogging.log("  Error was '"+str(e)+"'")
            
        return retVal

    def readAllInfo(self):
        self.vgs = self.readInfo(self.VGS_INFO)
        self.lvs = self.readInfo(self.LVS_INFO)
        self.lvSegs = self.readInfo(self.LVS_SEG_INFO)
        self.pvs = self.readInfo(self.PVS_INFO)

    @classmethod
    def decodeSegmentRange(cls, segRange):
        # Handle only a single range, e.g. '/dev/sdb3:11001-16158'
        matches = re.match(r'([^:]+):([0-9]+)-([0-9]+)$', segRange)
        if not matches:
            raise Exception("Could not decode segment range from '"+segRange+"'")
        # End value is inclusive, so 0-0 is one segment long
        return {
            'device' : matches.group(1),
            'start' : int(matches.group(2)),
            'size' : int(matches.group(3)) - int(matches.group(2)) + 1 # +1 because end is inclusive
        }
        
    @classmethod
    def encodeSegmentRange(cls, device, start, size):
        endInclusive = start+size-1
        if start < 0 or endInclusive < start:
            raise Exception("Invalid segment to encode: "+str(device)+', start='+str(start)+', size='+str(size))
        retVal = device+':'+str(start)+'-'+str(endInclusive)
        return retVal

    def segmentList(self, device):
        # PV segments don't record whether the segment is free space or not, so iterate through
        # the LV segments for the device instead
        segments = []
        for lvSeg in self.lvSegs:
            segRange = self.decodeSegmentRange(lvSeg['seg_pe_ranges'])
            if segRange['device'] == device:
                segments.append(Segment(segRange['start'], segRange['size']))
        segments.sort(lambda x, y : cmp(x.start, y.start))
        return segments

    def freeSegmentList(self, device):
        pv = self.deviceToPV(device)
        usedSegs = self.segmentList(device)
        # Add a fake zero-sized end segment to the list, so the unallocated space at the end
        # of the volume is a gap between two segments and not a special case
        fakeEndSeg = Segment(pv['pv_pe_count'], 0)
        usedSegs.append(fakeEndSeg)
        freeSegs = []
        # Iterate over pairs of consecutive segments
        for seg, nextSeg in zip(usedSegs[:-1], usedSegs[1:]):
            # ... work out the gap between them ...
            gapSize = nextSeg.start - seg.end()
            if gapSize > 0:
                # ... and add that to the free segment list
                freeSegs.append(Segment(seg.end(), gapSize))
        
        return freeSegs

    def segmentsToMove(self, device, threshold):
        """Given a device, i.e. a partition containing an LVM volume, and a threshold in extents,
        returns the segments that would need to be moved so that all non-free segments are
        below that address.  Can add just part of a segment if the original straddles the threshold"""
        segsToMove = []
        for seg in self.segmentList(device):
            if seg.end() > threshold:
                start = max(seg.start, threshold)
                segsToMove.append(Segment(start, seg.end() - start))
        return segsToMove

    def makeSpaceAfterThreshold(self, device, thresholdExtent):
        """Queues up a set of MoveChunks that will free up space at the end of a PV so that
        a pvresize cammand can succeed, and these will lead to pvmove commands at
        commit time.  Doesn't queue up the pvresize command itself - resizeDevice will do that..
        Also safe to call if no pvmoves are necessary"""
        pv = self.deviceToPV(device)
        # Extents >= thresholdExtent must be freed.
        segsToMove = self.segmentsToMove(device, thresholdExtent)
        
        # Calculate the free pool if we haven't already.  If we have done it already, we've been
        # here before for this device, so use the existing FreePool object as it knows how much
        # free space is already used by reallocation
        if 'free-pool' not in pv:
            pv['free-pool'] =  FreePool(self.freeSegmentList(device))

        # Take a copy.  We'll only commit our modified copy back to pv['free-pool']  if our transaction succeeds
        freePool = deepcopy(pv['free-pool'])
        moveList = []
        
        for srcSeg in segsToMove:
            srcOffset = 0
            destSegs = freePool.takeSegments(srcSeg.size)
            # destSegs are a tailor-made set of segments to consume srcSeg exactly, and the loop
            # beow relies on that
            for destSeg in destSegs:
                # Divide up the source segments into the destination segments
                srcStart = srcSeg.start + srcOffset
                destStart = destSeg.start
                moveList.append(MoveChunk(srcStart, destStart, destSeg.size))
                srcOffset += destSeg.size
            assert srcOffset == srcSeg.size # Logic error if not
        
        # Add our moves to the current MoveChunk list for this device, creating the
        # dict element if necessary
        self.moveLists[device] = self.moveLists.get(device, []) + moveList
        pv['free-pool'] = freePool

    def deviceToPVOrNone(self, device):
        """ Returns the PV record for a given device (partition), or None if there is no PV
        for that device."""
        for pv in self.pvs:
            if pv['pv_name'] == device:
                return pv
        return None
        
    def deviceToPV(self, device):
        pv = self.deviceToPVOrNone(device)
        if pv is None:
            raise Exception("PV for device '"+device+"' not found")
        return pv

    def vGContainingLV(self, lvol):
        for lv in self.lvs:
            if lv['lv_name'] == lvol:
                return lv['vg_name']
        raise Exception("VG for LV '"+lvol+"' not found")

    def deviceSize(self, device):
        pv = self.deviceToPV(device)
        return pv['pv_size'] # in bytes

    def deviceFreeSpace(self, device):
        pv = self.deviceToPV(device)
        return pv['pv_free'] # in bytes

    def resizeDevice(self, device, byteSize):
        """ Resizes the PV on a device, moving extents around if necessary
        """
        pv = self.deviceToPV(device)
        if byteSize > pv['dev_size']:
            raise Exception("Size requested for "+str(device)+" ("+str(byteSize)+
                ") is greater than device size ("+str(pv['dev_size'])+")")

        extentBytes = pv['pv_size'] / pv['pv_pe_count'] # Typically 4MiB
        # Calculate the threshold in extents beyond which segments must be moved elsewhere.
        # Round down, so enough space is freed for pvresize to complete, and allow
        # PVRESIZE_EXTENT_MARGIN for extents consumed by LVM metadata
        metadataExtents = (pv['pe_start'] + extentBytes - 1) / extentBytes # Round up
        
        thresholdExtent = byteSize / extentBytes - metadataExtents - self.PVRESIZE_EXTENT_MARGIN
        self.makeSpaceAfterThreshold(device, thresholdExtent)
        self.resizeList.append({'device' : device, 'bytesize' : byteSize})

    def testPartition(self, devicePrefix, vgPrefix):
        """Returns the first partition where the device name starts with devicePrefix and
        the volume group that it's in starts with vgPrefix"""
        retVal = None
        for pv in self.pvs:
            if pv['pv_name'].startswith(devicePrefix) and pv['vg_name'].startswith(vgPrefix):
                retVal = pv['pv_name']
                break
        return retVal

    def configPartition(self, devicePrefix):
        """Returns the PV name for a config partition on the specified WHOLE DEVICE, e.g. '/dev/sda',
        or None if none present"""
        return self.testPartition(devicePrefix, self.VG_CONFIG_PREFIX)
        
    def swapPartition(self, devicePrefix):
        return self.testPartition(devicePrefix, self.VG_SWAP_PREFIX)

    def srPartition(self, devicePrefix):
        return self.testPartition(devicePrefix, self.VG_SR_PREFIX)

    def isPartitionConfig(self, device):
        """Returns True if there is a config partition on the specified PARTITION, e.g. '/dev/sda2',
        or False if none present"""
        pv = self.deviceToPVOrNone(device)
        return pv is not None and pv['vg_name'].startswith(self.VG_CONFIG_PREFIX)

    def isPartitionSwap(self, device):
        pv = self.deviceToPVOrNone(device)
        return pv is not None and pv['vg_name'].startswith(self.VG_SWAP_PREFIX)

    def isPartitionSR(self, device):
        pv = self.deviceToPVOrNone(device)
        return pv is not None and pv['vg_name'].startswith(self.VG_SR_PREFIX)

    def deleteDevice(self, device):
        """Deletes PVs, VGs and LVs associated with a device (partition)"""
        pvsToDelete = []
        vgsToDelete = []
        lvsToDelete = []
        
        for pv in self.pvs:
            if pv['pv_name'] == device:
                pvsToDelete.append(pv['pv_name'])
                vgsToDelete.append(pv['vg_name'])
    
        for lv in self.lvs:
            if lv['vg_name'] in vgsToDelete:
                # lvremove requires a 'path': <VG name>/<LV name>
                lvsToDelete.append(lv['vg_name']+'/'+lv['lv_name'])
        
        self.pvsToDelete += pvsToDelete
        self.vgsToDelete += vgsToDelete
        self.lvsToDelete += lvsToDelete

    def activateVG(self, vg):
        self.cmdWrap(self.VGCHANGE + ['-ay', vg])

    def deactivateVG(self, vg):
        self.cmdWrap(self.VGCHANGE + ['-an', vg])

    def deactivateAll(self):
        """Makes sure that LVM has unmounted everything so that, e.g. sfdisk can succeed"""
        for vg in self.vgs:
            # Passing VG names to LVchange is intentional
            self.cmdWrap(self.LVCHANGE + ['-an', vg['vg_name']])

    @classmethod
    def executeMoves(cls, progress_callback, device, moveList):
        # Call commit instead this method unless you have special requirements
        """Issues pvmove commands to move MoveChunks specified by the MoveList.  Doesn't
        handle overlapping source and destination segments in a single MoveChunk, but in
        a makeSpaceAtEnd scenario those aren't generated"""
        sizeStep = 16 # Moving 16 extents takes only slightly more time than moving 1
        totalExtents = sum(move.size for move in moveList)
        extentsSoFar = 0
        for move in moveList:
            offset = 0
            while offset < move.size:
                progress_callback((100 * extentsSoFar) / totalExtents)
                chunkSize = min(sizeStep, move.size - offset)
                srcRange = cls.encodeSegmentRange(device, move.src + offset, chunkSize)
                destRange = cls.encodeSegmentRange(device, move.dest + offset, chunkSize)
                out = cls.cmdWrap(cls.PVMOVE +
                    [
                    '--alloc',
                    'anywhere',
                    srcRange,
                    destRange
                ])
                offset += chunkSize
                extentsSoFar += chunkSize

    def commit(self, progress_callback = lambda _ : ()):
        """Commit the changes queued up by issuing LVM commands, delete our queues as they
        succeed, and then reread the new configuration from LVM"""
        progress_callback(0)
        # Abort pvmoves if any have been left partiially completed by e.g. a crash
        self.cmdWrap(self.PVMOVE + ['--abort'])
        self.deactivateAll()
        progress_callback(1)
        
        # Process delete lists
        for lv in self.lvsToDelete:
            self.cmdWrap(self.LVREMOVE + [lv])
        self.lvsToDelete = []
        progress_callback(2)
        for vg in self.vgsToDelete:
            self.cmdWrap(self.VGREMOVE + [vg])
        self.vgsToDelete = []
        progress_callback(3)
        for pv in self.pvsToDelete:
            self.cmdWrap(self.PVREMOVE + ['--force', '--yes', pv])
        self.pvsToDelete = []
        progress_callback(4)
        
        # Process move lists.  Most of the code here is for calculating smoothly 
        # increasing progress values
        totalExtents = 0
        for moveList in self.moveLists.values():
            totalExtents += sum([ move.size for move in moveList ])
        extentsSoFar = 0
        
        for device, moveList in sorted(self.moveLists.iteritems()):
            thisSize = sum([ move.size for move in moveList ])
            callback = lambda percent : (progress_callback( 5 + (98 - 5) * (extentsSoFar + thisSize * percent / 100) / totalExtents) )
            self.executeMoves(callback, device, moveList)
            extentsSoFar +=  thisSize
        self.moveLists = {}
        
        # Process resize list
        progress_callback(98)
        for resize in self.resizeList:
            self.cmdWrap(self.PVRESIZE + ['--setphysicalvolumesize', str(resize['bytesize']/1024)+'k', resize['device']])
        self.resizeList = []

        self.readAllInfo() # Reread the new LVM configuration
        progress_callback(99)
        self.deactivateAll() # Stop active LVs preventing changes to the partition structure
        progress_callback(100)
        
    def dump(self):
        pprint(self.__dict__)

class PartitionTool:
    SFDISK='/sbin/sfdisk'
    DD='/bin/dd'
    
    DISK_PREFIX = '/dev/'
    P_STYLE_DISKS = [ 'cciss', 'ida', 'rd', 'sg', 'i2o', 'amiraid', 'iseries', 'emd', 'carmel']
    PART_STYLE_DISKS = [ 'disk/by-id' ]
    
    DEFAULT_SECTOR_SIZE = 512 # Used if sfdisk won't print its (hardcoded) value
    
    ID_EXTENDED = 0x5
    ID_FAT16 = 0x6
    ID_W95_EXTENDED = 0x0f
    ID_LINUX_SWAP = 0x82
    ID_LINUX = 0x83
    ID_LINUX_EXTENDED = 0x85
    ID_LINUX_LVM = 0x8e
    ID_DELL_UTILITY = 0xde
    
    IDS_EXTENDED = [ID_EXTENDED, ID_W95_EXTENDED, ID_LINUX_EXTENDED]
    
    def __init__(self, device):
        self.device = device
        self.midfix = self.determineMidfix(device)
        self.readDiskDetails()
        self.partitions = self.partitionTable()
        self.origPartitions = deepcopy(self.partitions)

    @staticmethod                                                                                        
    def partitionDevice(device, deviceNum):                                                              
        return device + PartitionTool.determineMidfix(device) + str(deviceNum) 

    @staticmethod
    def diskDevice(partitionDevice):
        matches = re.match(r'(.+)(p|(-part))\d+$', partitionDevice)
        if matches:
            return matches.group(1)
        matches = re.match(r'(.+\D)\d+$', partitionDevice)
        if not matches:
            raise Exception("Could not determine disk device for device '"+partitionDevice+"'")
        return matches.group(1)
        
    def partitionNumber(self, partitionDevice):
        matches = re.match(self.device + self.midfix + r'(\d+)$', partitionDevice)
        if not matches:
            raise Exception("Could not determine partition number for device '"+partitionDevice+"'")
        return int(matches.group(1))

    # Private methods:
    def cmdWrap(self, params):
        rv, out, err = util.runCmd2(params, True, True)
        if rv != 0:
            raise Exception("\n".join(err))
        return out
    
    @staticmethod
    def determineMidfix(device):
        for key in PartitionTool.P_STYLE_DISKS:
            if device.startswith(PartitionTool.DISK_PREFIX + key):
                return 'p'
        for key in PartitionTool.PART_STYLE_DISKS:
            if device.startswith(PartitionTool.DISK_PREFIX + key):
                return '-part'
        return ''

    def _partitionDevice(self, deviceNum):
        return self.device + self.midfix + str(deviceNum)

    def _partitionNumber(self, partitionDevice):
        # sfdisk is inconsistent in naming partitions of by-id devices
        matches = re.match(self.device + r'\D*(\d+)$', partitionDevice)
        if not matches:
            raise Exception("Could not determine partition number for device '"+partitionDevice+"'")
        return int(matches.group(1))

    def readDiskDetails(self):
        # Read basic geometry
        out = self.cmdWrap([self.SFDISK, '-Lg', self.device])
        matches = re.match(r'^[^:]*:\s*(\d+)\s+cylinders,\s*(\d+)\s+heads,\s*(\d+)\s+sectors', out)
        if not matches:
            raise Exception("Couldn't decode sfdisk output: "+out)
        self.cylinders = int(matches.group(1))
        self.heads = int(matches.group(2))
        self.sectors = int(matches.group(3))
        self.sectorExtent = self.cylinders * self.heads * self.sectors
    
        # Read sector size.  This will fail if the disk has no partition table at all
        self.sectorSize = None
        
        out = self.cmdWrap([self.SFDISK, '-LluS', self.device])
        for line in out.split("\n"):
            matches = re.match(r'^\s*Units\s*=\s*sectors\s*of\s*(\d+)\s*bytes', line)
            if matches:
                self.sectorSize = int(matches.group(1))
                break
        
        if self.sectorSize is None:
            self.sectorSize = self.DEFAULT_SECTOR_SIZE
            xelogging.log("Couldn't determine sector size from sfdisk output - no partition table?\n"+
                "Using default value: "+str(self.sectorSize)+"\nsfdisk output:"+out)
                
        self.byteExtent = self.sectorExtent * self.sectorSize

    def partitionTable(self):
        out = self.cmdWrap([self.SFDISK, '-Ld', self.device])
        state = 0
        partitions = {}
        for line in out.split("\n"):
            if line == '' or line[0] == '#':
                pass # Skip comments and blank lines
            elif state == 0:
                if line != 'unit: sectors':
                    raise Exception("Expecting 'unit: sectors' but got '"+line+"'")
                state += 1
            elif state == 1:
                matches = re.match(r'([^: ]+)\s*:\s*start=\s*(\d+),\s*size=\s*(\d+),\s*Id=\s*(\w+)\s*(,\s*bootable)?', line)
                if not matches:
                    raise Exception("Could not decode partition line: '"+line+"'")
                
                size = int(matches.group(3))
                if size != 0: # Treat partitions of size 0 as not present
                    number = self._partitionNumber(matches.group(1))
    
                    partitions[number] = {
                        'start': int(matches.group(2)),
                        'size': size,
                        'id': int(matches.group(4), 16), # Base 16
                        'active': (matches.group(5) is not None)
                        }
        return partitions

    def writeThisPartitionTable(self, table, dryrun = False, log = False):
        input = 'unit: sectors\n\n'
    
        # sfdisk doesn't allow us to skip partitions, so invent lines for empty slot
        for number in range(1, 1+max(table.keys())):
            partition = table.get(number, {
                'start': 0,
                'size': 0,
                'id': 0,
                'active': False
            })
            line = self._partitionDevice(number)+' :'
            line += ' start='+str(partition['start'])+','
            line += ' size='+str(partition['size'])+','
            line += ' Id=%x' % partition['id']
            if partition['active']:
                line += ', bootable'
                
            input += line+'\n'
        if log:
            xelogging.log('Input to sfdisk:\n'+input)
        process = subprocess.Popen(
            [self.SFDISK, dryrun and '-LnuS' or '-LuS', self.device],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            )
        output=process.communicate(input)
        if log:
            xelogging.log('Output from sfdisk:\n'+output[0])
        if process.returncode != 0:
            raise Exception('Partition changes could not be applied: '+str(output[0]))
        # Verify the table - raises exception on failure
        self.cmdWrap([self.SFDISK, '-LVquS', self.device])
        
    def writePartitionTable(self, dryrun = False, log = False):
        try:
            self.writeThisPartitionTable(self.partitions, dryrun, log)
        except Exception, e:
            try:
                # Revert to the original partition table
                self.writeThisPartitionTable(self.origPartitions, dryrun)
            except Exception, e2:
                raise Exception('The new partition table could not be written: '+str(e)+'\nReversion also failed: '+str(e2))
            raise Exception('The new partition table could not be written but was reverted successfully: '+str(e))

    # Public methods from here onward:
    def getPartition(self, number, default = None):
        return deepcopy(self.partitions.get(number, default))
    
    def createPartition(self, id, sizeBytes = None, number = None, startBytes = None, active = False):
        if number is None:
            if len(self.partitions) == 0:
                newNumber = 1
            else:
                newNumber = 1+max(self.partitions.keys())
        else:
            newNumber = number
        if newNumber in self.partitions:
            raise Exception('Partition '+str(newNumber)+' already exists')

        if startBytes is None:
            # Get an array of previous partitions
            previousPartitions = [part for num, part in reversed(sorted(self.partitions.iteritems())) if num < newNumber]
            
            if len(previousPartitions) == 0:
                startSector = 1
            else:
                startSector =  previousPartitions[0]['start'] + previousPartitions[0]['size']
        else:
            if startBytes % self.sectorSize != 0:
                raise Exception("Partition start ("+str(startBytes)+") is not a multiple of the sector size "+str(self.sectorSize))
            startSector = startBytes / self.sectorSize

        if sizeBytes is None:
            # Get an array of subsequent partitions
            nextPartitions = [part for num, part in sorted(self.partitions.iteritems()) if num > newNumber]
            if len(nextPartitions) == 0:
                sizeSectors = self.sectorExtent - startSector
            else:
                sizeSectors =  nextPartitions[0]['start'] - startSector
        else:
            if sizeBytes % self.sectorSize != 0:
                raise Exception("Partition size ("+str(sizeBytes)+") is not a multiple of the sector size "+str(self.sectorSize))

            sizeSectors = sizeBytes / self.sectorSize

        self.partitions[newNumber] = {
            'start': startSector,
            'size': sizeSectors,
            'id': id,
            'active': active
        }

    def deletePartition(self, number):
       del self.partitions[number]            

    def deletePartitionIfPresent(self, number):
        if number in self.partitions:
            self.deletePartition(number)
        
    def deletePartitions(self, numbers):
        for number in numbers:
            self.deletePartition(number)
            
    def renamePartition(self, srcNumber, destNumber, overwrite = False):
        if srcNumber not in self.partitions:
            raise Exception('Source partition '+str(srcNumber)+' does not exist')
        if srcNumber != destNumber:
            if not overwrite and destNumber in self.partitions:
                raise Exception('Destination partition '+str(destNumber)+' already exists')
    
            self.partitions[destNumber] = self.partitions[srcNumber]
            self.deletePartition(srcNumber)
    
    def partitionSize(self, number):
        if number not in self.partitions:
            raise Exception('Partition '+str(number)+' does not exist')
        return self.getPartition(number)['size'] * self.sectorSize
    
    def partitionStart(self, number):
        if number not in self.partitions:
            raise Exception('Partition '+str(number)+' does not exist')
        return self.getPartition(number)['start'] * self.sectorSize
    
    def partitionEnd(self, number):
        return self.partitionStart(number) + self.partitionSize(number)
    
    def partitionID(self, number):
        if number not in self.partitions:
            raise Exception('Partition '+str(number)+' does not exist')
        return self.getPartition(number)['id']

    def resizePartition(self, number, sizeBytes):
        if number not in self.partitions:
            raise Exception('Partition for resize '+str(number)+' does not exists')
        if sizeBytes % self.sectorSize != 0:
            raise Exception("Partition size ("+str(sizeBytes)+") is not a multiple of the sector size "+str(self.sectorSize))
        
        self.partitions[number]['size'] = sizeBytes / self.sectorSize
    
    def setActiveFlag(self, activeFlag, number):
        assert isinstance(activeFlag, types.BooleanType) # Assert that params are the right way around
        if not number in self.partitions:
            raise Exception('Partition '+str(number)+' does not exist')
        self.partitions[number]['active'] = activeFlag

    def inactivateDisk(self):
        for number, partition in self.partitions.iteritems():
            if partition['active']:
                self.setActiveFlag(False, number)

    def iteritems(self):
        # sorted() creates a new list, so you can delete partitions whilst iterating
        for number, partition in sorted(self.partitions.iteritems()):
            yield number, partition

    def commit(self, dryrun = False, log = False):
        self.writePartitionTable(dryrun, log)
        if not dryrun:
            # Update the revert point so this tool can be used repeatedly
            self.origPartitions = deepcopy(self.partitions)

    def dump(self):
        output = "Cylinders     : "+str(self.cylinders) + "\n"
        output += "Heads         : "+str(self.heads) + "\n"
        output += "Sectors       : "+str(self.sectors) + "\n"
        output += "Sector size   : "+str(self.sectorSize) + "\n"
        output += "Sector extent : "+str(self.sectorExtent)+" sectors\n"
        output += "Byte extent   : "+str(self.byteExtent)+" bytes\n"
        output += "Partition size and start addresses in sectors:\n"
        for number, partition in sorted(self.origPartitions.iteritems()):
            output += "Old partition "+str(number)+":"
            for k, v in sorted(partition.iteritems()):
                output += ' '+k+'='+((k == 'id') and hex(v) or str(v))
            output += "\n"
        for number, partition in sorted(self.partitions.iteritems()):
            output += "New partition "+str(number)+":"
            for k, v in sorted(partition.iteritems()):
                output += ' '+k+'='+((k == 'id') and hex(v) or str(v))
            output += "\n"
        xelogging.log(output)

