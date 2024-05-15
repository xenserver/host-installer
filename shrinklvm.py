import binascii
from collections import OrderedDict
import io
import json
import math
import os
import re
import six
import struct
import subprocess
import sys

from disktools import PartitionTool, partitionDevice
from xcp import logger

'''Infrastructure for shrinking an LVM volume'''

# LVM format high level overview:
# The label is contained in one of the first four sectors (usually 2nd)
# The label is followed by the PV header which points at a list of metadata
# areas and data areas.
# The metadata area has a header and points at the actual config.
# The config is a piece of vaguely JSON-like text.
# Although it is text and appears to be exclusively ASCII, there is no
# specification for the encoding and the reference LVM implementation is
# written in C so we use bytes to represent it.
# The data area is a sequence of extents.
# Each extent is a fixed number of sectors.


LABEL_SEARCH_SECTORS = 4
SECTOR_SIZE = 512
MDA_HEADER_SIZE = 512
PV_EXT_USED = 1


def int2bytes(n):
    if six.PY2:
        return bytes(n)
    return b'%d' % n


class _ConfigStore(object):
    '''Store and retrieve LVM config'''

    def __init__(self):
        # The config is stored as a list of (bytes, bytes) pairs
        # to avoid having to parse the values which may be a variety of types.
        # Use OrderedDict to maintain the config order.
        self.config = OrderedDict()

    def get_config(self, search_key):
        assert type(search_key) == bytes
        return self.config.get(search_key)

    def set_config(self, key, value):
        assert type(key) == bytes
        assert type(value) == bytes
        self.config[key] = value

    def __iter__(self):
        return iter(self.config)


class LVM(_ConfigStore):
    '''Represents an LVM device'''

    def __init__(self):
        super(LVM, self).__init__()

        self.file = None
        self.vgs = []
        self.pv_id = None
        self.dev_size = 0
        self.da = []
        self.mda = []
        self.ba = []
        self.pv_ext_version = 0
        self.pv_ext_flags = 0
        self.raw_locs = []
        self.text_config = None

    def close(self):
        if self.file:
            self.file.flush()
            os.fsync(self.file.fileno())
            self.file.close()
            self.file = None


class VG(_ConfigStore):
    '''Represents a volume group'''

    def __init__(self, name, lvm):
        super(VG, self).__init__()

        self.name = name
        self.lvm = lvm
        self.pvs = []
        self.lvs = []


class PV(_ConfigStore):
    '''Represents a physical volume'''

    def __init__(self, name, vg):
        super(PV, self).__init__()

        self.name = name
        self.vg = vg


class LV(_ConfigStore):
    '''Represents a logical volume'''

    def __init__(self, name, vg):
        super(LV, self).__init__()

        self.name = name
        self.vg = vg
        self.segs = []


class Segment(_ConfigStore):
    '''Represents a segment of a logical volume

    This maps logical extents to physical extents.
    '''

    def __init__(self, lv):
        super(Segment, self).__init__()

        self.lv = lv
        self.stripes = []

    @property
    def logical_start(self):
        '''Helper method to get the logical starting extent'''

        return int(self.get_config(b'start_extent'))

    @logical_start.setter
    def logical_start(self, new_value):
        '''Helper method to set the logical starting extent'''

        self.set_config(b'start_extent', int2bytes(new_value))

    @property
    def size(self):
        '''Helper method to get the size of the LV'''

        return int(self.get_config(b'extent_count'))

    @size.setter
    def size(self, new_value):
        '''Helper method to set the size of the LV'''

        self.set_config(b'extent_count', int2bytes(new_value))

    @property
    def start(self):
        '''Helper method to get the physical starting extent'''

        assert(self.stripes[0].startswith(b'"pv0",'))

        return int(self.stripes[0].split(b',')[1].strip())

    @start.setter
    def start(self, new_value):
        '''Helper method to set the physical starting extent'''

        assert(self.stripes[0].startswith(b'"pv0",'))

        self.stripes[0] = b'"pv0", %d' % (new_value,)

    @property
    def end(self):
        '''Helper method to set the physical starting extent'''

        return self.start + self.size - 1

    def __lt__(self, other):
        '''This segment is less than the other if the physical start is earlier
        or they are the same but this segment is shorter.
        '''

        if self.start < other.start:
            return True
        if self.start == other.start and self.size < other.size:
            return True

        return False

    def __eq__(self, other):
        '''This segment is equal to the other if the physical start and size
        are the same. It ignores whether or not they are pointing at the same
        LV.
        '''

        return self.start == other.start and self.size == other.size

    def __repr__(self):
        return "Segment({}, {}, {}, {})".format(self.start, self.end,
                                                self.logical_start, self.lv.name)

    def clone(self):
        '''Clone a segment

        The new segment has a separate copy of the config and stripes but
        points at the same LV.
        '''

        s = Segment(self.lv)
        s.config = self.config.copy()
        s.stripes = self.stripes[:]
        return s


class Area(object):
    '''Represents an on-disk area containing data or metadata'''

    def __init__(self, offset, size, checksum=0, flags=0):
        self.offset = offset
        self.size = size
        self.checksum = checksum
        self.flags = flags


class ReservedRegion(object):
    '''Represents a region of physical extents to be reserved

    Any allocated extents in this area should be moved elsewhere.
    '''

    def __init__(self, start, size):
        self.start = start
        self.size = size
        self.end = start + size - 1

    def __repr__(self):
        return "ReservedRegion({}, {}, {})".format(self.start, self.end, self.size)


def calc_crc(data):
    '''Calculate CRC-32 according to the algorithm used by LVM2'''

    crctab = [
		0x00000000, 0x1db71064, 0x3b6e20c8, 0x26d930ac,
		0x76dc4190, 0x6b6b51f4, 0x4db26158, 0x5005713c,
		0xedb88320, 0xf00f9344, 0xd6d6a3e8, 0xcb61b38c,
		0x9b64c2b0, 0x86d3d2d4, 0xa00ae278, 0xbdbdf21c,
    ]
    crc = 0xf597a6cf
    assert(type(data) == bytes)
    for i in six.iterbytes(data):
        crc = crc ^ i
        crc = (crc >> 4) ^ crctab[crc & 0xf]
        crc = (crc >> 4) ^ crctab[crc & 0xf]

    return crc


def read_header(path):
    '''Read and parse the headers of an LVM device

    Returns an LVM object. The LVM object should be closed by the caller.
    '''

    lvm = LVM()

    lvm.file = open(path, 'rb+')

    # Find the LVM label which may be in one of the first 4 sectors
    found = False
    for i in range(LABEL_SEARCH_SECTORS):
        buf = lvm.file.read(SECTOR_SIZE)
        if buf.startswith(b'LABELONE'):
            assert(not found)
            found = True
            label_sector = i
            label_data = buf

    assert(found)
    lvm.label_sector = label_sector
    logger.log('Found LVM label at sector {}'.format(lvm.label_sector))

    # Read LVM label
    label_magic, sector_xl, crc_xl, offset_xl, lvm_type = struct.unpack_from('<8sQII8s', label_data)
    assert(label_magic == b'LABELONE')
    assert(sector_xl == label_sector)
    assert(offset_xl == 32)
    assert(lvm_type == b'LVM2 001')
    assert(calc_crc(label_data[20:]) == crc_xl) # CRC is calculated from offset_xl to the end of the sector

    # Read PV header
    parse_offset = offset_xl
    lvm.pv_id, lvm.dev_size = struct.unpack_from('<32sQ', label_data, offset=parse_offset)
    parse_offset += 40

    # Read data areas
    while True:
        offset, size = struct.unpack_from('<QQ', label_data, offset=parse_offset)
        parse_offset += 16
        if offset == 0:
            break

        lvm.da.append(Area(offset, size))
        logger.log('Found LVM data area: {}, {}'.format(offset, size))

    # Read metadata areas
    while True:
        offset, size = struct.unpack_from('<QQ', label_data, offset=parse_offset)
        parse_offset += 16
        if offset == 0:
            break
        lvm.mda.append(Area(offset, size))
        logger.log('Found LVM metadata area: {}, {}'.format(offset, size))

    # Read PV header extension
    lvm.pv_ext_version, lvm.pv_ext_flags = struct.unpack_from('<II', label_data, offset=parse_offset)
    parse_offset += 8

    # Read bootloader areas
    while True:
        offset, size = struct.unpack_from('<QQ', label_data, offset=parse_offset)
        parse_offset += 16
        if offset == 0:
            break
        lvm.ba.append(Area(offset, size))
        logger.log('Found LVM bootloader area: {}, {}'.format(offset, size))

    # Read metadata area header
    assert(len(lvm.mda) > 0)
    lvm.file.seek(lvm.mda[0].offset, os.SEEK_SET)
    buf = lvm.file.read(SECTOR_SIZE)

    checksum_xl, magic, version, start, size = struct.unpack_from('<I16sIQQ', buf)
    assert(calc_crc(buf[4:]) == checksum_xl)
    assert(magic == b' LVM2 x[5A%r0N*>')
    assert(version == 1)
    assert(start == lvm.mda[0].offset)
    assert(size == lvm.mda[0].size)

    # Read raw locations of metadata
    parse_offset = 40
    while True:
        offset, size, checksum, flags = struct.unpack_from('<QQII', buf, offset=parse_offset)
        parse_offset += 24
        if offset == 0:
            break
        lvm.raw_locs.append(Area(offset, size, checksum, flags))
        logger.log('Found LVM config: {}, {}'.format(offset, size))

    assert(len(lvm.raw_locs) > 0)

    # Now read the actual metadata
    # The metadata is stored in a circular buffer.
    wrap = max(0, lvm.raw_locs[0].offset + lvm.raw_locs[0].size - lvm.mda[0].size)

    lvm.file.seek(lvm.raw_locs[0].offset + start, os.SEEK_SET)
    buf = lvm.file.read(lvm.raw_locs[0].size - wrap)

    if wrap:
        lvm.file.seek(start + MDA_HEADER_SIZE, os.SEEK_SET)
        buf += lvm.file.read(wrap)

    assert(calc_crc(buf) == lvm.raw_locs[0].checksum)

    lvm.text_config = buf.rstrip(b'\x00') # ignore NUL terminator

    return lvm


def check_lvm(lvm):
    '''Perform additional checks on the LVM device

    These checks constrain the number of edge cases and ensure that the LVM SR
    is in the state we expect it to be for shrinking.
    '''

    # Ensure there is only a single metadata area and data area
    assert(len(lvm.da) == 1)
    assert(len(lvm.mda) == 1)

    # Ensure the metadata area precedes the data area
    assert(lvm.mda[0].offset < lvm.da[0].offset)

    # Ensure the (single) data area's size is 0. This presumably means
    # that it continues until the end of the device/partition.
    assert(lvm.da[0].size == 0)

    # Enforce no bootloader areas
    assert(len(lvm.ba) == 0)

    # Ensure that the single metadata area has only a single config
    assert(len(lvm.raw_locs) == 1)

    # Check the PV extension version is one we understand
    assert(lvm.pv_ext_version <= 2)
    assert(lvm.pv_ext_version != 2 or lv.pv_ext_flags == PV_EXT_USED)

    # LVM has only a single volume group
    assert(len(lvm.vgs) == 1)

    # The volume group has only a single PV
    assert(len(lvm.vgs[0].pvs) == 1)

    # Each LV has at least one segment and each segment
    # has a single stripe.
    for lv in lvm.vgs[0].lvs:
        assert(len(lv.segs) >= 1)

        for seg in lv.segs:
            assert(seg.get_config(b'stripe_count') == b'1')


# A basic state machine for parsing the LVM text metadata format.

class Enum:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __eq__(self, other):
        return self.name == other.name and self.value == other.value


class ConfigState(Enum):
    INVALID = Enum('INVALID', 0)
    TOP = Enum('TOP', 1)
    IN_VG_I = Enum('IN_VG_I', 2)
    IN_PV = Enum('IN_PV', 3)
    IN_PV_I = Enum('IN_PV_I', 4)
    IN_LV = Enum('IN_LV', 5)
    IN_LV_I = Enum('IN_LV_I', 6)
    IN_SEG = Enum('IN_SEG', 7)
    IN_STRIPES = Enum('IN_STRIPES', 8)
    MAX = Enum('MAX', 9)


state_moves = {
    '{': [ConfigState.INVALID] * ConfigState.MAX.value,
    '[': [ConfigState.INVALID] * ConfigState.MAX.value,
    ']': [ConfigState.INVALID] * ConfigState.MAX.value,
    '}': [ConfigState.INVALID] * ConfigState.MAX.value,
}

state_moves['{'][ConfigState.TOP.value] = ConfigState.IN_VG_I
state_moves['{'][ConfigState.IN_PV.value] = ConfigState.IN_PV_I
state_moves['{'][ConfigState.IN_LV.value] = ConfigState.IN_LV_I
state_moves['{'][ConfigState.IN_LV_I.value] = ConfigState.IN_SEG

state_moves['}'][ConfigState.IN_VG_I.value] = ConfigState.TOP
state_moves['}'][ConfigState.IN_PV.value] = ConfigState.IN_VG_I
state_moves['}'][ConfigState.IN_PV_I.value] = ConfigState.IN_PV
state_moves['}'][ConfigState.IN_LV.value] = ConfigState.IN_VG_I
state_moves['}'][ConfigState.IN_LV_I.value] = ConfigState.IN_LV
state_moves['}'][ConfigState.IN_SEG.value] = ConfigState.IN_LV_I

state_moves['['][ConfigState.IN_SEG.value] = ConfigState.IN_STRIPES
state_moves[']'][ConfigState.IN_STRIPES.value] = ConfigState.IN_SEG


def next_state(state, char):
    return state_moves[char][state.value]


def action(lvm, state, l):
    if state == ConfigState.IN_STRIPES:
        lvm.vgs[-1].lvs[-1].segs[-1].stripes.append(l)
    else:
        items = l.split(b'=')
        assert(len(items) == 2)
        key, val = (i.strip() for i in items)

        if state == ConfigState.TOP:
            lvm.set_config(key, val)
        elif state == ConfigState.IN_VG_I:
            lvm.vgs[-1].set_config(key, val)
        elif state == ConfigState.IN_PV_I:
            lvm.vgs[-1].pvs[-1].set_config(key, val)
        elif state == ConfigState.IN_LV_I:
            lvm.vgs[-1].lvs[-1].set_config(key, val)
        elif state == ConfigState.IN_SEG:
            lvm.vgs[-1].lvs[-1].segs[-1].set_config(key, val)
        else:
            assert(False)


def parse_config(lvm):
    '''Parse an LVM config

    Given a text config, parse it into VGs, PVs, etc.
    '''

    state = ConfigState.TOP
    for l in lvm.text_config.split(b'\n'):
        l = l.strip()
        if not l:
            continue

        l = l.rsplit(b'#')[0].strip()
        if not l:
            continue

        if re.match(b'physical_volumes\s*{$', l):
            assert(state == ConfigState.IN_VG_I)
            state = ConfigState.IN_PV
        elif re.match(b'logical_volumes\s*{$', l):
            assert(state == ConfigState.IN_VG_I)
            state = ConfigState.IN_LV
        elif l.endswith(b'{'):
            # Extract the name from something like 'VG_XenStorage-4b279b04-dc82-a5e1-15ef-5cc508723fed {'
            match = re.match(b'(\S+)\s*{$', l)
            assert(match)
            val = match.group(1)

            state = next_state(state, '{')
            if state == ConfigState.IN_VG_I:
                lvm.vgs.append(VG(val, lvm))
            elif state == ConfigState.IN_PV_I:
                lvm.vgs[-1].pvs.append(PV(val, lvm.vgs[-1]))
            elif state == ConfigState.IN_LV_I:
                lvm.vgs[-1].lvs.append(LV(val, lvm.vgs[-1]))
            elif state == ConfigState.IN_SEG:
                lvm.vgs[-1].lvs[-1].segs.append(Segment(lvm.vgs[-1].lvs[-1]))
        elif l.endswith(b'['):
            state = next_state(state, '[')
        elif l == b']':
            state = next_state(state, ']')
        elif l == b'}':
            state = next_state(state, '}')
        else:
            action(lvm, state, l)

        assert(state != ConfigState.INVALID)

    assert(state == ConfigState.TOP)
    assert(len(lvm.vgs) > 0)


def format_config(lvm):
    '''Format an LVM text config

    Given an LVM object with config, VGs, PVs, etc., return a text config
    as a string.
    '''

    sio = io.BytesIO()

    indent = 0

    # LVM 2.02.130 expects the config to start with the VG name
    for vg in lvm.vgs:
        sio.write(b'%s {\n' % (vg.name,))

        for e in vg:
            sio.write(b'\t%s = %s\n' % (e, vg.get_config(e)))

        sio.write(b'\tphysical_volumes {\n')
        for pv in vg.pvs:
            sio.write(b'\t\t%s {\n' % (pv.name,))
            for e in pv:
                sio.write(b'\t\t\t%s = %s\n' % (e, pv.get_config(e)))
            sio.write(b'\t\t}\n')
        sio.write(b'\t}\n')

        sio.write(b'\tlogical_volumes {\n')
        for lv in vg.lvs:
            sio.write(b'\t\t%s {\n' % (lv.name,))
            for e in lv:
                sio.write(b'\t\t\t%s = %s\n' % (e, lv.get_config(e)))

            for i, seg in enumerate(lv.segs):
                sio.write(b'\t\t\tsegment%d {\n' % (i + 1,))
                for e in seg:
                    sio.write(b'\t\t\t\t%s = %s\n' % (e, seg.get_config(e)))

                if seg.stripes:
                    sio.write(b'\t\t\t\tstripes = [\n')
                    for stripe in seg.stripes:
                        sio.write(b'\t\t\t\t\t%s\n' % (stripe,))
                    sio.write(b'\t\t\t\t]\n')
                sio.write(b'\t\t\t}\n')
            sio.write(b'\t\t}\n')
        sio.write(b'\t}\n')

        sio.write(b'}\n')

    for e in lvm:
        sio.write(b'%s = %s\n' % (e, lvm.get_config(e)))

    return sio.getvalue()


def extent_to_segment(alloc_table, extent):
    '''Given an extent, return the segment it belongs to, or None'''

    for seg in alloc_table:
        if extent >= seg.start and extent <= seg.end:
            return seg

    return None


def next_segment(alloc_table, extent):
    '''Given an extent, return the next segment in the allocation table
    or None if there is no subsequent segment'''

    for seg in alloc_table:
        if seg.start > extent:
            return seg.start

    return None


def combine_alloc_and_reserved(alloc_table, regions):
    '''Combine allocation table and a list of ReservedRegions

    The output is a sorted list of (start, size) pairs that
    represent extents that have either been allocated or reserved.
    '''

    # Combine allocations and reserved regions into a new table
    new_table = []
    for seg in alloc_table:
        new_table.append((seg.start, seg.size))
    for r in regions:
        new_table.append((r.start, r.size))

    # Sort the table
    new_table.sort()

    # Now combine overlapping regions
    i = 0
    while i < len(new_table) - 1:
        if new_table[i + 1][0] <= new_table[i][0] + new_table[i][1]:
            new_table[i] = (new_table[i][0], max(new_table[i][1],
                                                 new_table[i + 1][0] + new_table[i + 1][1] - new_table[i][0]))
            del new_table[i + 1]
            i -= 1

        i += 1

    return new_table


def first_free_area(alloc_table, regions, end_extent):
    '''Return the start and end extents of the first free area

    This finds the first area that is not allocated or covered
    by a reserved region. It returns the start and end extents of that area.
    If the first free area is after all allocations, the end extent will be
    None.
    '''

    table = combine_alloc_and_reserved(alloc_table, regions)

    ptr = 0
    for seg in table:
        if ptr == seg[0]:
            ptr = seg[0] + seg[1]
            continue

    start = ptr
    for seg in table:
        if seg[0] > start:
            end = seg[0] - 1

            return start, end

    # This assert fails if there are no free extents
    assert(start <= end_extent)

    return start, end_extent


def insert_segment(alloc_table, seg):
    '''Insert a new segment into the correct place in an allocation table
    sorted according to physical start extent'''

    for i, s in enumerate(alloc_table):
        if seg.start > s.start and len(alloc_table) > (i + 1) and seg.start < alloc_table[i + 1].start:
            alloc_table.insert(i + 1, seg)
            return

    alloc_table.append(seg)


def lvm_to_alloc_table(lvm):
    '''Create and return a sorted allocation table from an LVM object'''

    alloc_table = []

    for lv in lvm.vgs[0].lvs:
        for seg in lv.segs:
            alloc_table.append(seg)

    alloc_table.sort()
    return alloc_table


def move_segment_allocations(alloc_table, regions, end_extent):
    '''Move segment allocations out of reserved regions and return a move list

    alloc_table is a list of segments
    regions is a list of reserved regions
    end_extent is the last extent in the data area

    Returns a list of move operations in the form of
    (from_extent, to_extent, num_extent) tuples.
    '''

    move_ops = []

    # The basic algorithm is: for each reserved region, find all the segments
    # that overlap the reserved region and move the overlapping parts into
    # unallocated extents, splitting if needed.
    for r in regions:
        ptr = r.start
        segment = None

        while ptr is not None and ptr <= r.end:
            # Either get the segment ptr points at or
            # the next allocated segment if it points at free space.
            segment = extent_to_segment(alloc_table, ptr)
            if not segment:
                ptr = next_segment(alloc_table, ptr)
                continue

            free_start, free_end = first_free_area(alloc_table, regions, end_extent)

            # The free area may not be big enough to contain all the blocks
            # that need to move. In that case, the segment will be split up
            # into multiple segments across > 1 free area.
            num_blocks = min(segment.end - ptr + 1, free_end - free_start + 1)
            num_blocks = min(num_blocks, r.end - ptr + 1)
            move_ops.append((ptr, free_start, num_blocks))

            # The original segment is removed from the allocation table and three are created:
            # 1) A segment for data before the moved data
            # 2) A segment for data after the moved data
            # 3) A segment for the new location of the moved data
            #
            # In some cases (1) and/or (2) may contain 0 extents and so
            # they are skipped.

            # Insert (3) into the allocation table
            moved_seg = segment.clone()
            moved_seg.start = free_start
            moved_seg.size = num_blocks
            moved_seg.logical_start = ptr - segment.start + segment.logical_start
            insert_segment(alloc_table, moved_seg)

            # Create (1)
            sega = segment.clone()
            sega.start = segment.start
            sega.size = ptr - segment.start
            sega.logical_start = segment.logical_start

            # Create (2)
            segb = segment.clone()
            segb.start = ptr + num_blocks
            segb.size = segment.end - (ptr + num_blocks) + 1
            segb.logical_start = moved_seg.logical_start + moved_seg.size

            # Remove original segment
            idx = alloc_table.index(segment)
            del alloc_table[idx]

            # Insert (1) if necessary
            if sega.size > 0:
                alloc_table.insert(idx, sega)
                idx += 1

            # Insert (2) if necessary
            if segb.size > 0:
                alloc_table.insert(idx, segb)

            ptr += num_blocks

    return move_ops


def move_extents(lvm, progress_callback, extent_from, extent_to, num_extents):
    '''Move num_extents from extent_from to extent_to'''

    pe_start = int(lvm.vgs[0].pvs[0].get_config(b'pe_start')) * SECTOR_SIZE
    extent_size = int(lvm.vgs[0].get_config(b'extent_size')) * SECTOR_SIZE
    num_bytes = num_extents * extent_size

    from_bytes = pe_start + extent_from * extent_size
    dest_bytes = pe_start + extent_to * extent_size

    block_size = min(128 * SECTOR_SIZE, extent_size)

    logger.log('Moving {} bytes from {} to {}'.format(num_bytes, from_bytes, dest_bytes))

    while num_bytes > 0:
        lvm.file.seek(from_bytes, os.SEEK_SET)
        nread = min(num_bytes, block_size)
        buf = lvm.file.read(nread)
        assert(len(buf) == nread)

        lvm.file.seek(dest_bytes, os.SEEK_SET)
        lvm.file.write(buf)

        from_bytes += nread
        dest_bytes += nread
        num_bytes -= nread

        progress_callback(nread)

    lvm.file.flush()
    os.fsync(lvm.file.fileno())


def recreate_segment_metadata(lvm, alloc_table):
    '''Recreate the segment metadata from the allocation table'''

    for lv in lvm.vgs[0].lvs:
        lv.segs = []

    for seg in alloc_table:
        seg.lv.segs.append(seg)

    for lv in lvm.vgs[0].lvs:
        lv.set_config(b'segment_count', int2bytes(len(lv.segs)))

        # LVM requires that segments are sorted by logical_start
        lv.segs.sort(key=lambda seg: seg.logical_start)


def update_metadata_offsets(lvm, pe_count, extent_size, start_shrunk_extents,
                            end_shrunk_extents, extra_metadata_sectors):
    '''Update metadata offsets in preparation for moving the start of the
    volume forward by shrunk_extents
    '''

    # The device shrinks by start_shrunk_extents from the beginning and
    # end_shrunk_extents from the end and increases in size by
    # extra_metadata_sectors
    lvm.dev_size = (lvm.dev_size - start_shrunk_extents * extent_size -
                       end_shrunk_extents * extent_size +
                       extra_metadata_sectors * SECTOR_SIZE)

    lvm.vgs[0].pvs[0].set_config(b'dev_size', int2bytes(lvm.dev_size // SECTOR_SIZE))
    lvm.vgs[0].pvs[0].set_config(b'pe_count', int2bytes(pe_count - start_shrunk_extents - end_shrunk_extents))
    lvm.vgs[0].pvs[0].set_config(b'pe_start', int2bytes(int(lvm.vgs[0].pvs[0].get_config(b'pe_start')) + extra_metadata_sectors))

    # Each segment's physical start decreases by the number of extents removed
    # from the start of the device.
    for lv in lvm.vgs[0].lvs:
        for seg in lv.segs:
            seg.start -= start_shrunk_extents

    # Increase the size of the metadata area to ensure the start of the
    # partition is aligned.
    lvm.mda[0].size += extra_metadata_sectors * SECTOR_SIZE
    lvm.da[0].offset += extra_metadata_sectors * SECTOR_SIZE


def write_headers_to_disk(lvm, offset):
    '''Write the headers and metadata/config to disk'''

    # Create label/PV header sector
    label_data = struct.pack('<I8s', 32, b'LVM2 001')
    pv_data = struct.pack('<32sQ', lvm.pv_id, lvm.dev_size)
    for i in lvm.da:
        pv_data += struct.pack('<QQ', i.offset, i.size)
    pv_data += b'\x00' * 16
    for i in lvm.mda:
        pv_data += struct.pack('<QQ', i.offset, i.size)
    pv_data += b'\x00' * 16
    pv_data += struct.pack('<II', lvm.pv_ext_version, lvm.pv_ext_flags)
    for i in lvm.ba:
        pv_data += struct.pack('<QQ', i.offset, i.size)
    pv_data += b'\x00' * 16
    pv_data += b'\x00' * (SECTOR_SIZE - 32 - len(pv_data))

    crc = calc_crc(label_data + pv_data)

    sector = struct.pack('<8sQI', b'LABELONE', lvm.label_sector, crc) + label_data + pv_data

    lvm.file.seek(offset, os.SEEK_SET)
    # Zero out the first few sectors then write the label/PV header sector
    for i in range(LABEL_SEARCH_SECTORS):
        lvm.file.write(b'\x00' * SECTOR_SIZE)
    lvm.file.seek(offset + lvm.label_sector * SECTOR_SIZE, os.SEEK_SET)
    lvm.file.write(sector)

    mda_data = format_config(lvm)
    logger.log('Updated LVM config: {}'.format(mda_data))
    mda_data =  mda_data + b'\x00'
    crc = calc_crc(mda_data)

    # Create metadata header sector
    mda_header = struct.pack('<16sIQQ', b' LVM2 x[5A%r0N*>', 1, lvm.mda[0].offset, lvm.mda[0].size)
    # Place config data at the beginning of the buffer to avoiding any wrapping issues.
    assert(len(mda_data) <= lvm.mda[0].size)
    mda_header += struct.pack('<QQII', SECTOR_SIZE, len(mda_data), crc, 0)
    mda_header += b'\x00' * (SECTOR_SIZE - 4 - len(mda_header))
    crc = calc_crc(mda_header)
    sector = struct.pack('<I', crc) + mda_header

    # Write metadata header sector and text config
    lvm.file.seek(offset + lvm.mda[0].offset, os.SEEK_SET)
    lvm.file.write(sector)
    lvm.file.write(mda_data)


def shrink_partition(drive, partno, start_shrunk_sectors, end_shrunk_sectors):
    '''Shrink the partition to match the new LVM size

    This returns a PartitionTool with the changes prepared in memory.
    The caller should call commit() to write the changes to disk.
    '''

    tool = PartitionTool(drive)
    old_partition = tool.partitions[partno]
    part_start = old_partition['start']
    part_size = old_partition['size']

    logger.log('Old partition: {} {}'.format(part_start, part_size))
    part_start += start_shrunk_sectors
    part_size -= start_shrunk_sectors
    part_size -= end_shrunk_sectors
    logger.log('New partition: {} {}'.format(part_start, part_size))

    tool.deletePartition(partno)
    tool.createPartition(old_partition['id'], sizeBytes=(part_size * tool.sectorSize),
                         number=partno, startBytes=(part_start * tool.sectorSize),
                         active=old_partition['active'])

    return tool


def shrink_lvm(drive, partno, start_space, end_space, progress_callback):
    '''Shrink an LVM partition

    This operation moves the start of the LVM volume forward by start_space
    bytes, moves the end backward by end_space bytes, and then resizes the
    partition to fit. The start is moved forward precisely to ensure that
    alignment is respected. This is done by increasing the size of the metadata
    area. The end_space is rounded up to the nearest extent.
    '''

    logger.log('Reading LVM header...')
    lvm = read_header(partitionDevice(drive, partno))
    logger.log('Original LVM config: {}'.format(lvm.text_config))

    logger.log('Parsing LVM config...')
    parse_config(lvm)

    logger.log('Checking LVM device...')
    check_lvm(lvm)

    # Create a sorted allocation table of the segments
    alloc_table = lvm_to_alloc_table(lvm)
    logger.log('Initial allocation table: {}'.format(alloc_table))

    extent_size = int(lvm.vgs[0].get_config(b'extent_size')) * SECTOR_SIZE
    pe_count = int(lvm.vgs[0].pvs[0].get_config(b'pe_count'))
    start_shrunk_extents = -(-start_space // extent_size)
    end_shrunk_extents = -(-end_space // extent_size)
    regions = []
    if start_shrunk_extents > 0:
        regions.append(ReservedRegion(0, start_shrunk_extents))
    if end_shrunk_extents > 0:
        regions.append(ReservedRegion(pe_count - end_shrunk_extents, end_shrunk_extents))

    if not regions:
        logger.log('LVM partition does not need to be shrunk')
        lvm.close()
        return

    # If we're shrinking the start by an amount that is not a multiple of the extent size
    # increase the size of the metadata area to compensate
    extra_metadata_sectors = (start_shrunk_extents * extent_size - start_space) // SECTOR_SIZE
    logger.log('Increasing metadata size by {} sectors'.format(extra_metadata_sectors))

    logger.log('Reserved regions: {}'.format(regions))

    move_ops = move_segment_allocations(alloc_table, regions, pe_count - 1)

    logger.log('Planned move operations: {}'.format(move_ops))
    logger.log('Planned final allocation table: {}'.format(alloc_table))

    # Prepare the new partition table in memory and do a dry-run commit to ensure it will work
    tool = shrink_partition(drive, partno,
                            (start_shrunk_extents * extent_size) // SECTOR_SIZE - extra_metadata_sectors,
                            (end_shrunk_extents * extent_size) // SECTOR_SIZE)
    tool.commit(dryrun=True, log=True)

    progress_callback(5)

    # Up to this point, the disk has not been modified.
    # Now that checks are complete and we have a plan,
    # begin the destructive part.

    # Emit progress accurately. Pre-move and post-move operations take 5% each
    # with moving data taking 90% of the progress.
    bytes_to_move = sum([i[2] * extent_size for i in move_ops])
    def get_move_ops_progress_cb():
        moved_bytes = [0]
        progress = [-1]

        def subprogress_callback(n):
            moved_bytes[0] += n
            new_progress = 5 + int(float(moved_bytes[0]) / bytes_to_move * 90)
            if new_progress != progress[0]:
                progress[0] = new_progress
                progress_callback(new_progress)

        return subprogress_callback

    move_ops_cb = get_move_ops_progress_cb()
    for op in move_ops:
        move_extents(lvm, move_ops_cb, *op)

    # A crash up to this point shouldn't affect anything because we've only
    # written into free unallocated extents. Now enter the critical region and
    # commit the changes.

    logger.log('Writing LVM headers and config to disk')

    recreate_segment_metadata(lvm, alloc_table)

    # Write updated LVM headers at the original location pointing at the new
    # segment locations. This is unnecessary but means a failure between
    # writing the real metadata and completing updating the partition table
    # should not result in data loss.
    write_headers_to_disk(lvm, 0)

    update_metadata_offsets(lvm, pe_count, extent_size, start_shrunk_extents, end_shrunk_extents, extra_metadata_sectors)

    # Now write the LVM headers at the final location.
    write_headers_to_disk(lvm, start_space)

    lvm.close()

    progress_callback(97)

    # At this point we're done with LVM. Now commit the partition changes to shrink the partition.
    logger.log('Shrinking partition...')
    tool.commit(log=True)

    # End of critical region. A crash at this point would see the shrunk
    # partition and the installer can be rerun without data loss.

    progress_callback(100)
