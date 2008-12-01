#!/usr/bin/env python
# Copyright (c) Citrix Systems 2008.  All rights reserved.
# Xen, the Xen logo, XenCenter, XenMotion are trademarks or registered
# trademarks of Citrix Systems, Inc., in the United States and other
# countries.

# This file replaces standard python BZ2File, which doesn't work with
# files compressed with pbzip2

# ***************************************
# After modifying please run the unit tests using:
# ./pbzip2file_test.py <pbzip2'd image file> <same file but decompressed>
# ***************************************

import bz2, os

class PBZ2File:
    SEEK_SET = 0
    SEEK_CUR = 1
    SEEK_END = 2
    
    def __init__(self, name_or_fd, mode = 'r', buffering = 0, compresslevel = 9):
        self.error = True # Leave the object unusable if initilaisation doesn't complete
        if mode not in ['r', 'rb']:
            raise ValueError("PBZ2File does not support modes other than 'r' and 'rb'")

        self.buffering = buffering
        if isinstance(name_or_fd, basestring):
            self.file = open(name_or_fd, 'rb') # Caller handles exceptions directly
        else:
            self.file = name_or_fd
        self.closed = False

        self.pos = 0 # Position in output file
        self.decompressor = bz2.BZ2Decompressor()
        self.unused_output = ''
        if self.buffering == 0:
            self.buffering = 128
        self.extent = None
        self.error = False
        
    def read(self, size = None):
        """Emulate file.read.  For large size values (>1MB) this is almost as fast as command line bunzip2.
        For small size values it is slower, e.g. 6 times slower for size=10kB, 1.5 times for size=100kB
        """
        if self.closed:
            raise IOError('Read operation on closed file')
        if self.error:
            raise IOError('Read operation on bad file')
        try:
            data = self.unused_output
            while size is None or len(data) < size:
                input = self.file.read(self.buffering)
                if len(input) == 0: # End of file
                    break
                try:
                    data += self.decompressor.decompress(input)
                except EOFError:
                    # This catches the event where the previous decompress() consumed exactly all
                    # of the input data, triggering BZ_STREAM_END on the last byte, but leaving no unused_data
                    # to trigger the case below.
                    self.decompressor = bz2.BZ2Decompressor()
                    data += self.decompressor.decompress(input)
                while len(self.decompressor.unused_data) > 0:
                    # Create a new compressor to handle pbzip2's multiple blocks
                    unused_data = self.decompressor.unused_data
                    self.decompressor = bz2.BZ2Decompressor()
                    data += self.decompressor.decompress(unused_data)
            
            # Return the requested output size, and store any extra output for later
            if size is None:
                output = data
                self.unused_output = ''
            else:
                output = data[:size]
                self.unused_output = data[size:]
            
            # Update the position counter
            self.pos += len(output)
            
        except:
            # Set error flag on any error to prevent subsequent reads returning bad data
            self.error = True
            raise
        return output
    
    def tell(self):
        return self.pos
    
    def rewind(self): # Used internally - not present in BZ2File
        self.file.seek(0, self.SEEK_SET)
        self.decompressor = bz2.BZ2Decompressor()
        self.unused_output = ''
        self.pos = 0
    
    def seek(self, offset, whence = SEEK_SET):
        """The seek operation is inefficient in that it must decompress the data for
        the file area that it traverses, and needs to restart at the beginning of the
        file to go backwards.
        """
        consume = 0
        if whence == self.SEEK_SET:
            if offset == 0:
                self.rewind()
            elif offset >= self.pos:
                consume = offset - self.pos
            else:
                self.rewind()
                consume = offset
        elif whence == self.SEEK_CUR:
            self.seek(self.pos + offset, self.SEEK_SET)
        elif whence == self.SEEK_END:
            if self.extent is None:
                self.measureExtent()
            self.seek(self.extent + offset, self.SEEK_SET)
        if consume > 0:
            step = 10000000
            while consume > step:
                if len(self.read(step)) != step: # Discard data
                    raise IOError('Seek beyond end of file')
                consume -= step
            if len(self.read(consume)) != consume: # Discard data
                raise IOError('Seek beyond end of file')
    
    def close(self):
        self.file.close()
        self.closed = True
    
    def measureExtent(self): # Internal use
        """ This method discards the current position in the file"""
        extent = 0
        step = 10000000
        self.rewind()
        while True:
            size = len(self.read(step)) # Discard data
            if size == 0:
                break
            extent += size
        self.extent = extent
 
