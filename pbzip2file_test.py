#!/usr/bin/env python
# Copyright (c) Citrix Systems 2008.  All rights reserved.
# Xen, the Xen logo, XenCenter, XenMotion are trademarks or registered
# trademarks of Citrix Systems, Inc., in the United States and other
# countries.

import commands, md5, os, random, sys, unittest
from test import test_support

from pbzip2file import *

def pbzip2file_test_main():
    """These tests compare the operation of PBZ2File on a bzipped file with a normal
    python file object on the decompressed file
    """
    # Testing function
    if len(sys.argv) != 3:
        raise Exception('Usage: '+sys.argv[0]+' <bzip2 file> <decompressed file>')

    bz2filename = sys.argv[1]
    filename = sys.argv[2]
    hash = commands.getoutput("md5sum '" + filename+"'")[:32]
    class TestCase1(unittest.TestCase):
        def file_md5sum(self, f):
            m = md5.new()
            had_short = False
            while True:
                size = random.randint(1, 10000000) # 10MB to exercise pbzip2's 900kB boundaries
                d = f.read(size) 
                if len(d) == 0:
                    break
                if len(d) != size:
                    # We only expect one string (at the end of the file) to be shorter than we requested.
                    if had_short:
                        raise Exception('Short string returned twice')
                    had_short = True

                m.update(d)
            return m.hexdigest()

        def test_uncompressed_md5sum(self):
            self.failIf(hash != commands.getoutput("md5sum '" + filename+"'")[:32])

        def test_command_line_bunzip2(self):
            self.failIf(hash != commands.getoutput("bunzip2 -c '"+bz2filename+"' | md5sum")[:32])

        def test_uncompressed_file_object(self):
            f2 = file(filename, 'rb')
            self.failIf(hash != self.file_md5sum(f2))
            f2.close()
            
        def test_PBZ2File_file_object(self):
            f3 = PBZ2File(bz2filename, 'rb')
            self.failIf(hash != self.file_md5sum(f3))
            f3.close()

    class TestCase2(unittest.TestCase):
        def test_extent(self):
            f = PBZ2File(bz2filename, 'rb')
            f.seek(0, f.SEEK_END)
            extent = f.tell()
            f.close()
            size = os.path.getsize(filename)
            self.failIf(size != extent)
        
        def test_random_seek_set(self):
            size = os.path.getsize(filename)
            test_size = 64
            if size <= test_size*2:
                raise Exception('Test file too small for seek tests')
            f0 = file(filename, 'rb')
            f1 = PBZ2File(bz2filename, 'rb')
            for i in range(10):
                offset = random.randint(0, size - test_size*2)
                f0.seek(offset, PBZ2File.SEEK_SET)
                f1.seek(offset, PBZ2File.SEEK_SET)
                self.failIf(f0.read(test_size) != f1.read(test_size))
                self.failIf(f0.read(test_size) != f1.read(test_size))
                
        def test_random_seek_cur(self):
            size = os.path.getsize(filename)
            test_size = 64
            if size <= test_size*2:
                raise Exception('Test file too small for seek tests')
            f0 = file(filename, 'rb')
            f1 = PBZ2File(bz2filename, 'rb')
            for i in range(10):
                offset = random.randint(0, (size - test_size*2) / 2)
                from_cur = random.randint(0, (size - test_size*2) / 2)
                f0.seek(offset, PBZ2File.SEEK_SET)
                f1.seek(offset, PBZ2File.SEEK_SET)
                f0.seek(from_cur, PBZ2File.SEEK_CUR)
                f1.seek(from_cur, PBZ2File.SEEK_CUR)
                self.failIf(f0.read(test_size) != f1.read(test_size))
                self.failIf(f0.read(test_size) != f1.read(test_size))
                
        def test_random_seek_end(self):
            size = os.path.getsize(filename)
            test_size = 64
            if size <= test_size*2:
                raise Exception('Test file too small for seek tests')
            f0 = file(filename, 'rb')
            f1 = PBZ2File(bz2filename, 'rb')
            for i in range(10):
                offset = 2*test_size + random.randint(0, size - test_size*2)
                f0.seek(-offset, PBZ2File.SEEK_END)
                f1.seek(-offset, PBZ2File.SEEK_END)
                self.failIf(f0.read(test_size) != f1.read(test_size))
                self.failIf(f0.read(test_size) != f1.read(test_size))
                
        def test_eof(self):
            size = os.path.getsize(filename)
            if size <= 11:
                raise Exception('Test file too small for EOF tests')
            f0 = file(filename, 'rb')
            f1 = PBZ2File(bz2filename, 'rb')
            f0.seek(-10, PBZ2File.SEEK_END)
            f1.seek(-10, PBZ2File.SEEK_END)
            read0 = f0.read(20)
            read1 = f1.read(20)
            self.failIf(len(read0) != 10 or read0 != read1)
            read0 = f0.read(20)
            read1 = f1.read(20)
            self.failIf(len(read0) != 0 or read0 != read1)
            
    # Running TestCase1 tests individually shows timings for each
    test_support.run_unittest(TestCase1('test_uncompressed_md5sum'))    
    test_support.run_unittest(TestCase1('test_command_line_bunzip2'))    
    test_support.run_unittest(TestCase1('test_uncompressed_file_object'))    
    test_support.run_unittest(TestCase1('test_PBZ2File_file_object'))    
    test_support.run_unittest(TestCase2)
    
if __name__ == '__main__':
    pbzip2file_test_main()
