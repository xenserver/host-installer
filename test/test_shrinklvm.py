import gzip
import io
import six
if six.PY2:
    import mock
    from mock import Mock
else:
    from unittest import mock
    from unittest.mock import Mock
import random
import unittest

from xcp import logger

import shrinklvm
from shrinklvm import LVM
from shrinklvm import ReservedRegion
from shrinklvm import _ConfigStore
from shrinklvm import format_config
from shrinklvm import lvm_to_alloc_table
from shrinklvm import move_segment_allocations
from shrinklvm import parse_config
from shrinklvm import read_header
from shrinklvm import recreate_segment_metadata
from shrinklvm import update_metadata_offsets
from shrinklvm import write_headers_to_disk


if six.PY2:
    BUILTINS_OPEN = '__builtin__.open'
else:
    BUILTINS_OPEN = 'builtins.open'


class TestConfigStore(unittest.TestCase):
    def test_get_set_config(self):
        c = _ConfigStore()
        c.set_config(b'one', b'foo')
        c.set_config(b'two', b'bar')
        c.set_config(b'three', b'baz')

        self.assertEqual(c.get_config(b'one'), b'foo')
        self.assertEqual(c.get_config(b'two'), b'bar')
        self.assertEqual(c.get_config(b'three'), b'baz')

        self.assertEqual(c.get_config(b'four'), None)

        # Check order is maintained
        self.assertEqual(list(c.config.items()), [(b'one', b'foo'), (b'two', b'bar'), (b'three', b'baz')])

    def test_update_config(self):
        c = _ConfigStore()
        c.set_config(b'one', b'foo')
        c.set_config(b'two', b'bar')
        c.set_config(b'three', b'baz')

        c.set_config(b'two', b'updated')

        self.assertEqual(c.get_config(b'one'), b'foo')
        self.assertEqual(c.get_config(b'two'), b'updated')
        self.assertEqual(c.get_config(b'three'), b'baz')

        # Check order is maintained
        self.assertEqual(list(c.config.items()), [(b'one', b'foo'), (b'two', b'updated'), (b'three', b'baz')])


class MockSegment:
    def __init__(self, start, size, logical_start):
        self.start = start
        self.size = size
        self.logical_start = logical_start

    @property
    def end(self):
        return self.start + self.size - 1

    def clone(self):
        return MockSegment(self.start, self.size, self.logical_start)

    def __eq__(self, other):
        return self.start == other.start and self.size == other.size and self.logical_start == other.logical_start

    def __repr__(self):
        return 'MockSegment({}, {}, {})'.format(self.start, self.size, self.logical_start)


class TestSegmentAllocations(unittest.TestCase):

    def _test_config(self, config):
        alloc_table = [MockSegment(i[0], i[1], i[2]) for i in config[0]]
        regions = [ReservedRegion(i[0], i[1]) for i in config[1]]
        expected_move_ops = config[2]
        expected_alloc_table = [MockSegment(i[0], i[1], i[2]) for i in config[3]]

        move_ops = move_segment_allocations(alloc_table, regions, config[4])

        self.assertEqual(move_ops, expected_move_ops)
        self.assertEqual(alloc_table, expected_alloc_table)

    def _test_config_asserts(self, config):
        alloc_table = [MockSegment(i[0], i[1], i[2]) for i in config[0]]
        regions = [ReservedRegion(i[0], i[1]) for i in config[1]]

        with self.assertRaises(AssertionError):
            move_segment_allocations(alloc_table, regions, config[2])

    def test_basic(self):
        self._test_config([
                [(0, 10, 0), (10, 10, 0)],
                [(0, 30)],
                [(0, 30, 10), (10, 40, 10)],
                [(30, 10, 0), (40, 10, 0)],
                100
        ])

    def test_empty(self):
        '''No segments in region'''

        self._test_config([
                [],
                [(0, 30)],
                [],
                [],
                100
        ])

    def test_overlapping(self):
        '''Segment overlaps region on both sides'''

        self._test_config([
                [(0, 10, 0)],
                [(5, 3)],
                [(5, 10, 3)],
                [(0, 5, 0), (8, 2, 8), (10, 3, 5)],
                100
        ])

    def test_overlapping_end(self):
        '''Segment overlaps region at the end'''

        self._test_config([
                [(0, 10, 0)],
                [(5, 10)],
                [(5, 15, 5)],
                [(0, 5, 0), (15, 5, 5)],
                100
        ])

    def test_overlapping_start(self):
        '''Segment overlaps region at the start'''

        self._test_config([
                [(5, 10, 0)],
                [(0, 10)],
                [(5, 15, 5)],
                [(10, 5, 5), (15, 5, 0)],
                100
        ])

    def test_single_extent_empty(self):
        '''A single empty extent at start and end of region'''

        self._test_config([
                [(0, 10, 5), (11, 5, 0), (16, 5, 0)],
                [(10, 12)],
                [(11, 22, 5), (16, 27, 5)],
                [(0, 10, 5), (22, 5, 0), (27, 5, 0)],
                100
        ])

    def test_single_extent_allocated(self):
        '''A single allocated extent at start and end of region'''

        self._test_config([
                [(10, 1, 1), (19, 1, 0)],
                [(10, 10)],
                [(10, 0, 1), (19, 1, 1)],
                [(0, 1, 1), (1, 1, 0)],
                100
        ])

    def test_fragmented(self):
        '''Reserved area and free space is fragmented'''

        self._test_config([
                [(0, 10, 0), (10, 5, 40), (15, 1, 10), (20, 40, 0), (100, 10, 0), (111, 10, 0)],
                [(0, 100)],
                [(0, 110, 1), (1, 121, 9), (10, 130, 5), (15, 135, 1), (20, 136, 40)],
                [(100, 10, 0), (110, 1, 0), (111, 10, 0), (121, 9, 1), (130, 5, 40), (135, 1, 10), (136, 40, 0)],
                200
        ])

    def test_contained(self):
        '''Segment is fully contained within region, free space on either side'''

        self._test_config([
                [(10, 10, 0)],
                [(0, 30)],
                [(10, 30, 10)],
                [(30, 10, 0)],
                100
        ])

    def test_out_of_space(self):
        '''Disk does not have enough space for reserved regions'''

        self._test_config_asserts([
                [(0, 50, 0), (50, 30, 0)],
                [(0, 30)],
                100
        ])

        self._test_config_asserts([
                [(0, 50, 0), (50, 50, 0)],
                [(0, 30)],
                100
        ])

        self._test_config_asserts([
                [(0, 50, 0), (50, 30, 0)],
                [(70, 30)],
                100
        ])

    def test_region_larger_than_disk(self):
        '''Reserved region is larger than the disk'''

        self._test_config_asserts([
                [(0, 50, 0), (50, 30, 0)],
                [(0, 150)],
                100
        ])

    def test_multiple_regions(self):
        '''Multiple reserved regions'''

        # 2nd region overlaps segment
        self._test_config([
                [(0, 10, 0), (10, 30, 0), (80, 20, 0)],
                [(0, 30), (99, 1)],
                [(0, 40, 10), (10, 50, 20), (99, 70, 1)],
                [(30, 10, 20), (40, 10, 0), (50, 20, 0), (70, 1, 19), (80, 19, 0)],
                100
        ])

        # 2nd region has no segments
        self._test_config([
                [(0, 10, 0), (10, 30, 0)],
                [(0, 30), (99, 1)],
                [(0, 40, 10), (10, 50, 20)],
                [(30, 10, 20), (40, 10, 0), (50, 20, 0)],
                100
        ])


example_config = b'''
# Generated by LVM2 version 2.03.17(2) (2022-11-10): Fri Nov 10 14:31:58 2023

contents = "Text Format Volume Group"
version = 1

description = "Created *after* executing 'lvremove testvg/testlv1'"

creation_host = "xenrt107157219"        # Linux xenrt107157219 5.14.0-284.11.1.el9_2.x86_64 #1 SMP PREEMPT_DYNAMIC Tue May 9 17:09:15 UTC 2023 x86_64
creation_time = 1699626718      # Fri Nov 10 14:31:58 2023

testvg {
        id = "RX2i78-sZFz-B21A-QeEa-Ac9C-IPZh-Ls6FKk"
        seqno = 5
        format = "lvm2"                 # informational
        status = ["RESIZEABLE", "READ", "WRITE"]
        flags = []
        extent_size = 8192              # 4 Megabytes
        max_lv = 0
        max_pv = 0
        metadata_copies = 0

        physical_volumes {

                pv0 {
                        id = "Fjpscc-pSRx-iUtV-60PY-zlYX-07Vb-Mul3yB"
                        device = "/dev/xvdb1"   # Hint only

                        status = ["ALLOCATABLE"]
                        flags = []
                        dev_size = 2095071      # 1022.98 Megabytes
                        pe_start = 2048
                        pe_count = 255  # 1020 Megabytes
                }
        }

        logical_volumes {

                testlv2 {
                        id = "HDbrMS-SQln-SJfu-cQR2-pZcj-ScO0-Li8JHQ"
                        status = ["READ", "WRITE", "VISIBLE"]
                        flags = []
                        creation_time = 1699626708      # 2023-11-10 14:31:48 +0000
                        creation_host = "xenrt107157219"
                        segment_count = 1

                        segment1 {
                                start_extent = 0
                                extent_count = 40       # 160 Megabytes

                                type = "striped"
                                stripe_count = 1        # linear

                                stripes = [
                                        "pv0", 50
                                ]
                        }
                }

                testlv3 {
                        id = "07i0W6-fJdo-otZ9-3cbS-8AQo-sfLR-xibOjB"
                        status = ["READ", "WRITE", "VISIBLE"]
                        flags = []
                        creation_time = 1699626712      # 2023-11-10 14:31:52 +0000
                        creation_host = "xenrt107157219"
                        segment_count = 2

                        segment1 {
                                start_extent = 0
                                extent_count = 30       # 120 Megabytes

                                type = "striped"
                                stripe_count = 1        # linear

                                stripes = [
                                        "pv0", 90
                                ]
                        }
                        segment2 {
                                start_extent = 30
                                extent_count = 5

                                type = "striped"
                                stripe_count = 1        # linear

                                stripes = [
                                        "pv0", 0
                                ]
                        }
                }
        }

}
'''


invalid_config = b'''
# Generated by LVM2 version 2.03.17(2) (2022-11-10): Fri Nov 10 14:31:58 2023

contents = "Text Format Volume Group"
version = 1

description = "Created *after* executing 'lvremove testvg/testlv1'"

testvg {
        physical_volumes {
                pv0 {
                    segment1 {
                    }
                }
        }
}
'''

example_config_out = b'''testvg {
	id = "RX2i78-sZFz-B21A-QeEa-Ac9C-IPZh-Ls6FKk"
	seqno = 5
	format = "lvm2"
	status = ["RESIZEABLE", "READ", "WRITE"]
	flags = []
	extent_size = 8192
	max_lv = 0
	max_pv = 0
	metadata_copies = 0
	physical_volumes {
		pv0 {
			id = "Fjpscc-pSRx-iUtV-60PY-zlYX-07Vb-Mul3yB"
			device = "/dev/xvdb1"
			status = ["ALLOCATABLE"]
			flags = []
			dev_size = 2095071
			pe_start = 2048
			pe_count = 255
		}
	}
	logical_volumes {
		testlv2 {
			id = "HDbrMS-SQln-SJfu-cQR2-pZcj-ScO0-Li8JHQ"
			status = ["READ", "WRITE", "VISIBLE"]
			flags = []
			creation_time = 1699626708
			creation_host = "xenrt107157219"
			segment_count = 1
			segment1 {
				start_extent = 0
				extent_count = 40
				type = "striped"
				stripe_count = 1
				stripes = [
					"pv0", 50
				]
			}
		}
		testlv3 {
			id = "07i0W6-fJdo-otZ9-3cbS-8AQo-sfLR-xibOjB"
			status = ["READ", "WRITE", "VISIBLE"]
			flags = []
			creation_time = 1699626712
			creation_host = "xenrt107157219"
			segment_count = 2
			segment1 {
				start_extent = 0
				extent_count = 30
				type = "striped"
				stripe_count = 1
				stripes = [
					"pv0", 90
				]
			}
			segment2 {
				start_extent = 30
				extent_count = 5
				type = "striped"
				stripe_count = 1
				stripes = [
					"pv0", 0
				]
			}
		}
	}
}
contents = "Text Format Volume Group"
version = 1
description = "Created *after* executing 'lvremove testvg/testlv1'"
creation_host = "xenrt107157219"
creation_time = 1699626718
'''

class TestConfig(unittest.TestCase):
    def test_read_config(self):
        lvm = LVM()
        lvm.text_config = example_config
        parse_config(lvm)

        self.assertEqual(lvm.get_config(b'version'), b'1')
        self.assertEqual(len(lvm.vgs), 1)
        self.assertEqual(len(lvm.vgs[0].pvs), 1)
        self.assertEqual(len(lvm.vgs[0].lvs), 2)

        self.assertEqual(lvm.vgs[0].name, b'testvg')
        self.assertEqual(lvm.vgs[0].get_config(b'extent_size'), b'8192')

        self.assertEqual(lvm.vgs[0].pvs[0].name, b'pv0')
        self.assertEqual(lvm.vgs[0].pvs[0].get_config(b'dev_size'), b'2095071')
        self.assertEqual(lvm.vgs[0].pvs[0].get_config(b'pe_start'), b'2048')
        self.assertEqual(lvm.vgs[0].pvs[0].get_config(b'pe_count'), b'255')

        self.assertEqual(lvm.vgs[0].lvs[0].name, b'testlv2')
        self.assertEqual(len(lvm.vgs[0].lvs[0].segs), 1)
        self.assertEqual(lvm.vgs[0].lvs[0].segs[0].start, 50)
        self.assertEqual(lvm.vgs[0].lvs[0].segs[0].end, 89)
        self.assertEqual(lvm.vgs[0].lvs[0].segs[0].logical_start, 0)

        self.assertEqual(lvm.vgs[0].lvs[1].name, b'testlv3')
        self.assertEqual(len(lvm.vgs[0].lvs[1].segs), 2)
        self.assertEqual(lvm.vgs[0].lvs[1].segs[0].start, 90)
        self.assertEqual(lvm.vgs[0].lvs[1].segs[0].end, 119)
        self.assertEqual(lvm.vgs[0].lvs[1].segs[0].logical_start, 0)
        self.assertEqual(lvm.vgs[0].lvs[1].segs[1].start, 0)
        self.assertEqual(lvm.vgs[0].lvs[1].segs[1].end, 4)
        self.assertEqual(lvm.vgs[0].lvs[1].segs[1].logical_start, 30)

    def test_truncated_config(self):
        '''Test parsing truncated configs'''

        for i in range(len(example_config) - 1):
            lvm = LVM()
            lvm.text_config = example_config[:i]

            with self.assertRaises(AssertionError):
                parse_config(lvm)

    def test_invalid_config(self):
        '''Test logically invalid config'''

        lvm = LVM()
        lvm.text_config = invalid_config
        with self.assertRaises(AssertionError):
            parse_config(lvm)

    def test_format_config(self):
        '''Test parsing and writing out a config'''

        lvm = LVM()
        lvm.text_config = example_config
        parse_config(lvm)

        out = format_config(lvm)
        # For compatibility with older versions of LVM, the config must start with
        # the VG.
        self.assertEqual(out, example_config_out)


real_config = b'''testvg {
id = "zk0Ftr-9oWM-28V1-H9tN-kfTR-CdaA-9D5gD0"
seqno = 27
format = "lvm2"
status = ["RESIZEABLE", "READ", "WRITE"]
flags = []
extent_size = 8192
max_lv = 0
max_pv = 0
metadata_copies = 0

physical_volumes {

pv0 {
id = "HS9GnK-dVQF-Uuce-DKrj-EyYL-vozb-J0qG6n"
device = "/dev/xvdb4"

status = ["ALLOCATABLE"]
flags = []
dev_size = 2097152
pe_start = 2048
pe_count = 255
}
}

logical_volumes {

testlv3 {
id = "9ZQ3La-f9I9-GRzc-pwN7-QY1Y-L32U-BogEF3"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_time = 1699887688
creation_host = "xenrt107157219"
segment_count = 1

segment1 {
start_extent = 0
extent_count = 40

type = "striped"
stripe_count = 1

stripes = [
"pv0", 50
]
}
}

testlv4 {
id = "SHbnAl-DTCu-O86u-475d-h6Dq-Aj7n-JoVh8D"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_time = 1699887718
creation_host = "xenrt107157219"
segment_count = 1

segment1 {
start_extent = 0
extent_count = 30

type = "striped"
stripe_count = 1

stripes = [
"pv0", 90
]
}
}

testlv9 {
id = "YekJpf-iSfH-PyOG-v09P-Ne9c-Gnh6-PLRfwf"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_time = 1699887910
creation_host = "xenrt107157219"
segment_count = 1

segment1 {
start_extent = 0
extent_count = 10

type = "striped"
stripe_count = 1

stripes = [
"pv0", 0
]
}
}

testlv5 {
id = "RdEQwU-p6sB-cb9l-GmTs-t2mp-WUba-ahfDuQ"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_time = 1699888007
creation_host = "xenrt107157219"
segment_count = 2

segment1 {
start_extent = 0
extent_count = 40

type = "striped"
stripe_count = 1

stripes = [
"pv0", 10
]
}
segment2 {
start_extent = 40
extent_count = 10

type = "striped"
stripe_count = 1

stripes = [
"pv0", 220
]
}
}
}

}
# Generated by LVM2 version 2.03.17(2) (2022-11-10): Mon Nov 13 15:07:11 2023

contents = "Text Format Volume Group"
version = 1

description = "Write from lvremove testvg/tmp3."

creation_host = "xenrt107157219"	# Linux xenrt107157219 5.14.0-284.11.1.el9_2.x86_64 #1 SMP PREEMPT_DYNAMIC Tue May 9 17:09:15 UTC 2023 x86_64
creation_time = 1699888031	# Mon Nov 13 15:07:11 2023

'''

wrapped_config = b'''testvg {
id = "zk0Ftr-9oWM-28V1-H9tN-kfTR-CdaA-9D5gD0"
seqno = 406
format = "lvm2"
status = ["RESIZEABLE", "READ", "WRITE"]
flags = []
extent_size = 8192
max_lv = 0
max_pv = 0
metadata_copies = 0

physical_volumes {

pv0 {
id = "HS9GnK-dVQF-Uuce-DKrj-EyYL-vozb-J0qG6n"
device = "/dev/xvdb4"

status = ["ALLOCATABLE"]
flags = []
dev_size = 2097152
pe_start = 2048
pe_count = 255
}
}

logical_volumes {

testlv3 {
id = "9ZQ3La-f9I9-GRzc-pwN7-QY1Y-L32U-BogEF3"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_time = 1699887688
creation_host = "xenrt107157219"
segment_count = 1

segment1 {
start_extent = 0
extent_count = 40

type = "striped"
stripe_count = 1

stripes = [
"pv0", 50
]
}
}

testlv4 {
id = "SHbnAl-DTCu-O86u-475d-h6Dq-Aj7n-JoVh8D"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_time = 1699887718
creation_host = "xenrt107157219"
segment_count = 1

segment1 {
start_extent = 0
extent_count = 30

type = "striped"
stripe_count = 1

stripes = [
"pv0", 90
]
}
}

testlv9 {
id = "YekJpf-iSfH-PyOG-v09P-Ne9c-Gnh6-PLRfwf"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_time = 1699887910
creation_host = "xenrt107157219"
segment_count = 1

segment1 {
start_extent = 0
extent_count = 10

type = "striped"
stripe_count = 1

stripes = [
"pv0", 0
]
}
}

testlv5 {
id = "RdEQwU-p6sB-cb9l-GmTs-t2mp-WUba-ahfDuQ"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_time = 1699888007
creation_host = "xenrt107157219"
segment_count = 2

segment1 {
start_extent = 0
extent_count = 40

type = "striped"
stripe_count = 1

stripes = [
"pv0", 10
]
}
segment2 {
start_extent = 40
extent_count = 10

type = "striped"
stripe_count = 1

stripes = [
"pv0", 220
]
}
}

testlvtmp {
id = "jK9e9N-AvsA-JOLV-cGLb-G0tY-H0EX-G8DVJu"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_time = 1700495098
creation_host = "xenrt107157219"
segment_count = 1

segment1 {
start_extent = 0
extent_count = 50

type = "striped"
stripe_count = 1

stripes = [
"pv0", 120
]
}
}
}

}
# Generated by LVM2 version 2.03.17(2) (2022-11-10): Mon Nov 20 15:44:58 2023

contents = "Text Format Volume Group"
version = 1

description = "Write from lvcreate -l 50 -n testlvtmp testvg."

creation_host = "xenrt107157219"	# Linux xenrt107157219 5.14.0-284.11.1.el9_2.x86_64 #1 SMP PREEMPT_DYNAMIC Tue May 9 17:09:15 UTC 2023 x86_64
creation_time = 1700495098	# Mon Nov 20 15:44:58 2023

'''


@mock.patch('shrinklvm.os.fsync')
class TestHeaders(unittest.TestCase):
    def _get_file(self, path):
        with gzip.open(path, 'rb') as f:
            disk_img = f.read()

        ret = io.BytesIO(disk_img)
        ret.fileno = Mock(return_value=0)

        return ret

    def test_read_headers(self, fsync_mock):
        '''Read LVM headers and config from disk and verify it'''

        inf = self._get_file('disk.img.gz')
        with mock.patch(BUILTINS_OPEN) as open_mock:
            open_mock.return_value = inf
            lvm = read_header('unused')
            lvm.close()

        self.assertEqual(lvm.dev_size, 1073741824)
        self.assertEqual(lvm.label_sector, 1)
        self.assertEqual(lvm.pv_id, b'HS9GnKdVQFUuceDKrjEyYLvozbJ0qG6n')
        self.assertEqual(lvm.da[0].size, 0)
        self.assertEqual(lvm.da[0].offset, 1048576)
        self.assertEqual(lvm.mda[0].offset, 4096)
        self.assertEqual(lvm.mda[0].size, 1044480)

        self.assertEqual(lvm.pv_ext_flags, 1)
        self.assertEqual(lvm.pv_ext_version, 2)

        self.assertEqual(len(lvm.ba), 0)

        self.assertEqual(lvm.text_config, real_config)

    def test_read_headers_wrap(self, fsync_mock):
        '''Read headers where the config wraps inside the circular buffer'''
        inf = self._get_file('disk-wrapped.img.gz')
        with mock.patch(BUILTINS_OPEN) as open_mock:
            open_mock.return_value = inf
            lvm = read_header('unused')
            lvm.close()

        self.assertEqual(lvm.dev_size, 1073741824)
        self.assertEqual(lvm.label_sector, 1)
        self.assertEqual(lvm.pv_id, b'HS9GnKdVQFUuceDKrjEyYLvozbJ0qG6n')
        self.assertEqual(lvm.da[0].size, 0)
        self.assertEqual(lvm.da[0].offset, 1048576)
        self.assertEqual(lvm.mda[0].offset, 4096)
        self.assertEqual(lvm.mda[0].size, 1044480)

        self.assertEqual(lvm.pv_ext_flags, 1)
        self.assertEqual(lvm.pv_ext_version, 2)

        self.assertEqual(len(lvm.ba), 0)

        self.assertEqual(lvm.text_config, wrapped_config)

    def test_write_headers(self, fsync_mock):
        '''Test writing out the LVM header'''

        # Read the header from an existing LVM disk
        inf = self._get_file('disk.img.gz')
        with mock.patch(BUILTINS_OPEN) as open_mock:
            open_mock.return_value = inf
            lvm = read_header('unused')
            parse_config(lvm)
            lvm.close()

        # Now write it out at an offset
        outf = io.BytesIO()
        # Mock disk has random data in it
        if six.PY2:
            outf.write(''.join(chr(random.randint(0, 255)) for i in range(1048576 + 4096)))
        else:
            outf.write(random.randbytes(1048576 + 4096))
        outf.fileno = Mock(return_value=0)
        lvm.file = outf

        write_headers_to_disk(lvm, 4096)

        outf.seek(4096)
        written_data = outf.read()

        lvm.close()

        # Read the header that we wrote at the offset and compare it with the original data
        # to check that it is unchanged.
        with mock.patch(BUILTINS_OPEN) as open_mock:
            inf = io.BytesIO(written_data)
            inf.fileno = Mock(return_value=0)
            open_mock.return_value = inf
            lvm2 = read_header('unused')
            lvm2.close()

        self.assertEqual(lvm.dev_size, lvm2.dev_size)
        self.assertEqual(lvm.label_sector, lvm2.label_sector)
        self.assertEqual(lvm.pv_id, lvm2.pv_id)
        self.assertEqual(lvm.da[0].size, lvm2.da[0].size)
        self.assertEqual(lvm.da[0].offset, lvm2.da[0].offset)
        self.assertEqual(lvm.mda[0].size, lvm2.mda[0].size)
        self.assertEqual(lvm.mda[0].offset, lvm2.mda[0].offset)

        self.assertEqual(lvm.pv_ext_flags, lvm2.pv_ext_flags)
        self.assertEqual(lvm.pv_ext_version, lvm2.pv_ext_version)

        self.assertEqual(len(lvm.ba), len(lvm2.ba))

        self.assertEqual(format_config(lvm), lvm2.text_config)

    def test_update_metadata(self, fsync_mock):
        '''Test metadata is updated correctly when shrunk'''

        inf = self._get_file('disk.img.gz')
        with mock.patch(BUILTINS_OPEN) as open_mock:
            open_mock.return_value = inf
            lvm = read_header('unused')
            parse_config(lvm)
            lvm.close()

        update_metadata_offsets(lvm, 255, 4 * 1024 ** 2, 5, 1, 56)

        self.assertEqual(lvm.dev_size, 1048604672)
        self.assertEqual(lvm.vgs[0].pvs[0].get_config(b'dev_size'), b'2048056')
        self.assertEqual(lvm.vgs[0].pvs[0].get_config(b'pe_count'), b'249')

        self.assertEqual(lvm.da[0].size, 0)
        self.assertEqual(lvm.da[0].offset, 1077248)
        self.assertEqual(lvm.mda[0].offset, 4096)
        self.assertEqual(lvm.mda[0].size, 1073152)

        seg_starts = []
        for lv in lvm.vgs[0].lvs:
            seg_starts.extend([seg.start for seg in lv.segs])
        self.assertEqual(seg_starts, [45, 85, -5, 5, 215])

    def test_recreate_segment_metadata(self, fsync_mock):
        '''Test that segment metadata is updated correctly'''

        inf = self._get_file('disk.img.gz')
        with mock.patch(BUILTINS_OPEN) as open_mock:
            open_mock.return_value = inf
            lvm = read_header('unused')
            parse_config(lvm)
            lvm.close()

        alloc_table = lvm_to_alloc_table(lvm)
        regions = [ReservedRegion(0, 100)]
        move_segment_allocations(alloc_table, regions, 256)

        recreate_segment_metadata(lvm, alloc_table)

        seg_starts = []
        for lv in lvm.vgs[0].lvs:
            seg_starts.extend([seg.start for seg in lv.segs])
        self.assertEqual(seg_starts, [170, 210, 100, 120, 130, 220])


if __name__ == '__main__':
    logger.openLog('/dev/null')
    unittest.main()
