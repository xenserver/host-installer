#!/usr/bin/env python
# Copyright (c) Citrix Systems 2009.  All rights reserved.
# Xen, the Xen logo, XenCenter, XenMotion are trademarks or registered
# trademarks of Citrix Systems, Inc., in the United States and other
# countries.

import re, subprocess, sys, types
from pprint import pprint
from copy import copy
import util

class Chunk:
    """Chunks are the individual blocks that are moved or copied.  When a segment is moved
    the operation is divided into one or more chunks.  Source and destination chunks typically aren't 
    allowed to overlap (depending on whtether what actually does the moving can handle overlap)"""
    def __init__(self, src, dest, size):
        self.src = src
        self.dest = dest
        self.size = size

    def __repr__(self):
        return str(self.__dict__)
        
class ChunkList:
    """A list of chunks that can be saved/restored from disk"""
    def __init__(self):
        self.chunks = []
        
    def __iter__(self, *params): 
        return self.chunks.__iter__(*params)
        
    def append(self, toAppend):
        if isinstance(toAppend, ChunkList):
            self.chunks += toAppend.chunks
        elif isinstance(toAppend, Chunk):
            self.chunks.append(toAppend)
        else:
            raise Exception("ChunkList can only contain chunks")
    
    def top(self):
        if len(self.chunks) < 1:
            return None            
        return self.chunks[0]
    
    def pop(self):
        self.chunks.pop(0)

    def __repr__(self):
        return str(self.__dict__)

class Segment:
    """Segments are potentially large extents, e.g. disk partitions or LVM segments.  Source and
    destination segments can overlap."""
    def __init__(self, start, size):
        self.start = start
        self.size = size
        
    def __repr__(self):
        return str(self.__dict__)

class MoveUtils:
    @classmethod
    def segmentMoveChunks(cls, srcSeg, destSeg):
        chunkList = ChunkList()
        offset = destSeg.start - srcSeg.start
        if offset != 0: # offset = 0 requires no action, and would cause infinite loop below

            # Segments can move to an overlapping position on the same media.  The thing that
            # does the moving wants a guarantee that the chunks it gets don't overlap.  If the source
            # and destination segments overlap we must start at the right end of the segment (so we
            # don't overwrite source data before we've copied it) and move in chunks smaller in size
            # than the offset amount (so chunks don't overlap).
            if offset > 0:
                # Moving to higher address, currently unused space is at the end of the destination segment,
                # so begin at the ends of segments.  Assume a predecrement of chunk size before move - see (1)
                srcSegChunkStart = srcSeg.start+srcSeg.size
                destSegChunkStart = destSeg.start+destSeg.size
            else:
                # Moving to a lower address, currently unused space is at the start of the destination segment,
                # so begin at starts of segments.  Assume a postincrement of chunk size after move - see (2)
                srcSegChunkStart = srcSeg.start
                destSegChunkStart = destSeg.start
            
            remaining = min(srcSeg.size, destSeg.size)
            while remaining > 0:
                chunkSize = min(remaining, abs(offset))
                
                if offset > 0:
                    # (1) Predecrement
                    srcSegChunkStart -= chunkSize
                    destSegChunkStart -= chunkSize
                
                chunkList.append(Chunk(
                    src = srcSegChunkStart,
                    dest = destSegChunkStart,
                    size = chunkSize
                ))
                
                if offset < 0:
                    # (2) Postincrement
                    srcSegChunkStart += chunkSize
                    destSegChunkStart += chunkSize
                remaining -= chunkSize
        return chunkList

    @classmethod
    def compareDeviceNames(cls, device1, device2):
        # Maybe this needs to resolve symlinks
        return device1 == device2
        
class LVMTool:
    # If moving a block would reclaim less than this number of extents, don't bother
    MOVE_THRESHOLD = 16
    # Separation character - mustn't appear in anything we expect back from pvs/vgs/lvs
    SEP='#'
    
    # Volume group prefixes
    VG_SWAP_PREFIX='VG_XenSwap'
    VG_CONFIG_PREFIX='VG_XenConfig'
    VG_SR_PREFIX='VG_XenStorage'
    
    PVMOVE=['pvmove']
    LVREMOVE=['lvremove']
    VGREMOVE=['vgremove']
    PVREMOVE=['pvremove']
    PVRESIZE=['pvresize']
    
    
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
        'integer_options' : ['pv_size']
    }
    def __init__(self):
        self.readAllInfo()
        self.pvsToDelete = []
        self.vgsToDelete = []
        self.lvsToDelete = []
        self.resizeList = []
 
    @classmethod
    def cmdWrap(cls, params):
        rv, out, err = util.runCmd2(params, True, True)
        if rv != 0:
            if isinstance(err, (types.ListType, types.TupleType)):
                raise Exception("\n".join(err))
            else:
                raise Exception(str(err))
        return out
        
    def readInfo(self, info):
        retVal = []
        allOptions = info['string_options'] + info['integer_options']
        cmd = info['command'] + info['arguments'] + ['--options', ','.join(allOptions)]
        out = self.cmdWrap(cmd)

        for line in out.strip().split('\n'):
            # Create a dict of the form 'option_name':value
            data = dict(zip(allOptions, line.lstrip().split(self.SEP)))
            for name in info['integer_options']:
                # Convert integer options to integer type
                data[name] = int(data[name])
            retVal.append(data)
            
        return retVal

    def readAllInfo(self):
        self.lvs = self.readInfo(self.LVS_INFO)
        self.lvSegs = self.readInfo(self.LVS_SEG_INFO)
        self.pvs = self.readInfo(self.PVS_INFO)

    @classmethod
    def trimDeviceName(cls, deviceName):
        matches = re.match(r'([^:(]*)', deviceName)
        return matches.group(1)

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
            if MoveUtils.compareDeviceNames(segRange['device'], device):
                segments.append(Segment(segRange['start'], segRange['size']))
        segments.sort(lambda x, y : cmp(x.start, y.start))
        return segments

    @classmethod
    def proposedSegmentList(cls, segList):
        currentStart = 0 # FIXME: Leave room for metadata?
        newSegList = []
        for seg in segList:
            newSeg = copy(seg) # Shallow copy but OK for ints
            if seg.start < currentStart + cls.MOVE_THRESHOLD:
                currentStart = seg.start # Avoid moves by tiny offset
            newSeg.start = currentStart
            newSegList.append(newSeg)
            currentStart += seg.size
        
        return newSegList
            
    @classmethod
    def segmentsChunkList(cls, srcSegList, destSegList):
        chunkList = []
        for srcSeg, destSeg in zip(srcSegList, destSegList):
            chunkList.append(MoveUtils.segmentMoveChunks(srcSeg, destSeg))
        return chunkList

    @classmethod
    def executeMoves(cls, device, segmentsChunkList):
        for chunkList in segmentsChunkList:
            for chunk in chunkList:
                srcRange = cls.encodeSegmentRange(device, chunk.src, chunk.size)
                destRange = cls.encodeSegmentRange(device, chunk.dest, chunk.size)
                
                out = cls.cmdWrap(cls.PVMOVE +
                    [
                    '--alloc',
                    'anywhere',
                    srcRange,
                    destRange
                ])
                 
                print out

    def deviceToPV(self, device):
        for pv in self.pvs:
            if pv['pv_name'] == device:
                return pv
        raise Exception("PV for device '"+device+"' not found")

    def resizeDevice(self, device, byteChange):
        """byteChange is a signed delta to apply to the size.  To shrink by 8GiB
        byteChange would be -8589934592."""
        if byteChange % 16384 != 0: # Use an estimated 'big enough' power of 2 for sector size
            raise Exception("PV resize value not a multiple of sector size")
        
        self.resizeList.append({'device' : device, 'bytechange' : byteChange})

    def defragmentDevice(self, device):
        segList = self.segmentList('/dev/sdb3')
        propSegList = self.proposedSegmentList(segList)
        segChunkList = self.segmentsChunkList(segList, propSegList)
        self.executeMoves(sevice, segChunkList) 

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
        return self.testPartition(devicePrefix, self.VG_CONFIG_PREFIX)
        
    def swapPartition(self, devicePrefix):
        return self.testPartition(devicePrefix, self.VG_SWAP_PREFIX)

    def srPartition(self, devicePrefix):
        return self.testPartition(devicePrefix, self.VG_SR_PREFIX)

    def deleteDevice(self, device):
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

    def commit(self):
        for lv in self.lvsToDelete:
            self.cmdWrap(self.LVREMOVE + [lv])
        self.lvsToDelete = []
        for vg in self.vgsToDelete:
            self.cmdWrap(self.VGREMOVE + [vg])
        self.vgsToDelete = []
        for pv in self.pvsToDelete:
            self.cmdWrap(self.PVREMOVE + ['--force', '--yes', pv])
        self.pvsToDelete = []
        for resize in self.resizeList:
            pv = self.deviceToPV(resize['device'])
            # pv_size is not necessarily the size of the underlying device - that would be dev_size
            newSize = pv['pv_size'] + resize['bytechange']
            self.cmdWrap(self.PVRESIZE + ['--setphysicalvolumesize', str(newSize/1024)+'k', resize['device']])
        self.resizeList = []
        self.readAllInfo() # FIXME: ?

    def dump(self):
        pprint(self.__dict__)


# Only primary partitions are fully handled by PartitionTool
class PartitionTool:
    SFDISK='/sbin/sfdisk'
    DD='/bin/dd'
    def __init__(self, device):
        self.device = device
        self.readDiskDetails()
        # Call partitionTable twice to get independent copies
        self.partitions = self.partitionTable()
        self.origPartitions = self.partitionTable()
        self.moves = []
        
    def cmdWrap(self, params):
        rv, out, err = util.runCmd2(params, True, True)
        if rv != 0:
            raise Exception("\n".join(err))
        return out
        
    def readDiskDetails(self):
        # Read basic geometry
        out = self.cmdWrap([self.SFDISK, '-Lg', self.device])
        matches = re.match(r'^[^:]*:\s*(\d+)\s+cylinders,\s*(\d+)\s+heads,\s*(\d+)\s+sectors', out)
        if not matches:
            raise Exception("Couldn't decode sfdisk output: "+out)
        self.cylinders = int(matches.group(1))
        self.heads = int(matches.group(2))
        self.sectors = int(matches.group(3))
        
        # Read sector size
        out = self.cmdWrap([self.SFDISK, '-LluS', self.device])
        for line in out.split("\n"):
            matches = re.match(r'^\s*Units\s*=\s*sectors\s*of\s*(\d+)\s*bytes', line)
            if matches:
                self.sectorSize = int(matches.group(1))
                break
        if self.sectorSize is None:
            raise Exception("Couldn't determine sector size from sfdisk output: "+out)
        self.sectorExtent = self.cylinders * self.heads * self.sectors
        self.byteExtent = self.sectorExtent * self.sectorSize
    
    def partitionTable(self):
        out = self.cmdWrap([self.SFDISK, '-Ld', self.device])
        state = 0
        partitions = []
        for line in out.split("\n"):
            if line == '' or line[0] == '#':
                pass # Skip comments and blank lines
            elif state == 0:
                if line != 'unit: sectors':
                    raise Exception("Expecting 'unit: sectors' but got '"+line+"'")
                state += 1
            elif state == 1:
                matches = re.match(r'([^: ]+)\s*:\s*start=\s*(\d+),\s*size=\s*(\d+),\s*Id=\s*(\w+)\s*', line)
                if not matches:
                    raise Exception("Could not decode partition line: '"+line+"'")
                partitions.append({
                    'device': matches.group(1),
                    'start': int(matches.group(2)),
                    'size': int(matches.group(3)),
                    'id': matches.group(4)
                    })
        return partitions

    def writeThisPartitionTable(self, table):
        input = 'unit: sectors\n\n'
    
        for partition in table:
            line=partition['device']+' :'
            line += ' start='+str(partition['start'])+','
            line += ' size='+str(partition['size'])+','
            line += ' Id='+str(partition['id'])
            input += line+'\n'

        process = subprocess.Popen(
            [self.SFDISK, '-L', self.device],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            )
        output=process.communicate(input)
        if process.returncode != 0:
            raise Exception('Partition changes could not be applied: '+str(output))
        # Verify the table - raises exception on failure
        self.cmdWrap([self.SFDISK, '-LVq', self.device])
        
    def writePartitionTable(self):
        try:
            self.writeThisPartitionTable(self.partitions)
        except Exception, e:
            try:
                # Revert to the original partition table
                self.writeThisPartitionTable(self.origPartitions)
            except Exception, e2:
                raise Exception('The new partition table could not be written: '+str(e)+'\nReversion also failed: '+str(e2))
            raise Exception('The new partition table could not be written but was reverted successfully: '+str(e))
            
    def deletePartition(self, device):
        partToDelete = None
        for partition in self.partitions:
            if partition['device'] == device:
                partToDelete = partition
        if partToDelete is None:
            raise Exception("Cannot find partition to delete - '"+str(device)+"'")
        partToDelete['start'] = 0
        partToDelete['size'] = 0
        partToDelete['id'] = '0'

    def resizePartition(self, device, byteChange):
        if byteChange % self.sectorSize != 0:
            raise Exception("Partition resize amount "+str(byteChange)+" is not a multiple of the sector size "+str(self.sectorSize))
        sectorChange = byteChange / self.sectorSize
        if byteChange > 0:
            # Implementing this just needs the same overlap check as movePartition, but we don't need it yet
            raise Exception("Resizing to a larger size is not supported")
        partToResize = None
        for partition in self.partitions:
            if partition['device'] == device:
                partToResize = partition
        if partToResize is None:
            raise Exception("Cannot find partition to resize")
        if partToResize['size'] + sectorChange <= 0:
            raise Exception("Partition resize generates negative or zero partition size")
        partToResize['size'] += sectorChange

    def movePartition(self, device, byteOffset):
        if byteOffset % self.sectorSize != 0:
            raise Exception("Partition move offset "+str(byteOffset)+" is not a multiple of the sector size "+str(self.sectorSize))
        sectorOffset = byteOffset / self.sectorSize
        partToMove = None
        otherParts = []
        for partition in self.partitions:
            if partition['device'] == device:
                partToMove = partition
            else:
                otherParts.append(partition)
        if partToMove is None:
            raise Exception("Cannot find partition to move")
        newStart = partToMove['start'] + sectorOffset
        newEnd = newStart + partToMove['size']
        if newStart < 0 or newEnd > self.sectorExtent:
            raise Exception("Moved partition would extend outside disk")
            
        for otherPart in otherParts:
            otherStart = otherPart['start']
            otherSize = otherPart['size']
            otherEnd = otherStart+otherSize
            if otherSize != 0: # Not an empty partition
                if newStart < otherEnd and newEnd > otherStart:
                    raise Exception("Moved partition would collide with partition "+otherPart['device'])
        self.moves.append((
            Segment(partToMove['start'], partToMove['size']),
            Segment(partToMove['start']+sectorOffset, partToMove['size'])
        ))
        partToMove['start'] = newStart # This updates self.partitions, as partToMove is a reference into it

    def executeMoves(self):
        # In a move the source and destination blocks will usually overlap.
        # Move parameters are in sectors
        chunkList = ChunkList()
        for srcSeg, destSeg in self.moves:
            chunkList.append(MoveUtils.segmentMoveChunks(srcSeg, destSeg))

        for chunk in chunkList:
            out = self.cmdWrap([
                    self.DD,
                    'if='+self.device,
                    'of='+self.device,
                    'skip='+str(chunk.src),
                    'seek='+str(chunk.dest),
                    'bs='+str(self.sectorSize),
                    'count='+str(chunk.size)
                    ])
            
    def commit(self):
        self.writePartitionTable()
        self.executeMoves()

    def dump(self):
        print "Cylinders     : "+str(self.cylinders)
        print "Heads         : "+str(self.heads)
        print "Sectors       : "+str(self.sectors)
        print "Sector size   : "+str(self.sectorSize)
        print "Sector extent : "+str(self.sectorExtent)+" sectors"
        print "Byte extent   : "+str(self.byteExtent)+" bytes"
        print "Partition size and start addresses in sectors:"
        for partition in self.origPartitions:
            output = "Old partition:"
            for k, v in partition.iteritems():
                output += ' '+k+'='+str(v)
            print output
        for partition in self.partitions:
            output = "New partition:"
            for k, v in partition.iteritems():
                output += ' '+k+'='+str(v)
            print output
        for move in self.moves:
            src, dest = move
            output += 'Move from ' + str(src) + ' to ' + str(dest)
            print output

class DiskFixer:
    SR_RESIZE_BYTES = -8*2**30 # Shrink by 8GB
    SR_MOVE_BYTES = 8*2**30 # Move by 8GB
    
    def __init__(self, device):
        self.device = device
    
    def execResumeIfRequired(self):
        # Resume any dead operations
        self.cmdWrap(self.PVMOVE)
    
    def execFix(self):
        partTool = PartitionTool(self.device)
        lvmTool = LVMTool()
        partBase = 0
        oemPartNum = None
        # TODO: if we_have_an_oem_partition
        # TODO:    partBase = 1
        # TODO:    oemPartNum = 1
        
        # xxxPartNum methods return either a partition number, or None if none is present
        self.configPartition = lvmTool.configPartition(self.device)
        self.swapPartition = lvmTool.swapPartition(self.device)
        self.srPartition= lvmTool.srPartition(self.device)
        
        # Resize the current SR - defragments if necessary and raises exception if not possible
        try:
            lvmTool.resizePartition(self.srPartition, self.SR_RESIZE_BYTES)
            lvmTool.commit()
        except Exception, e:
            # Get a fresh lvmTool after failure
            lvmTool = LVMTool()
            # Resize failed - try defragmenting
            segList = lvmTool.segmentList(self.srPartition)
            propSegList = lvmTool.proposedSegmentList(segList)
            segChunkList = lvmTool.segmentsChunkList(segList, propSegList)
            
            lvmTool.executeMoves(self.srPartition, segChunkList)
            # Try resize again, but an exception this time propagates to the caller, i.e. we give up
            lvmTool.resizeDevice(self.srPartition, self.SR_RESIZE_BYTES)
            lvmTool.commit()
        
        
        # Resize and move the SR partition
        partTool.resizePartition(self.srPartition, self.SR_RESIZE_BYTES)
        partTool.movePartition(self.srPartition, self.SR_MOVE_BYTES)
        
        # Delete config and swap PVs and VGs
        if self.configPartition is not None:
            lvmTool.deleteDevice(self.configPartition)
        if self.swapPartition is not None:
            lvmTool.deleteDevice(self.swapPartition)
        lvmTool.commit()
        
        # Delete config and swap partitions
        if self.configPartition is not None:
            partTool.deletePartition(self.configPartition)
        if self.swapPartition is not None:
            partTool.deletePartition(self.swapPartition)
        partTool.commit()
        
        # TODO: Make SR partition oemBase+3


