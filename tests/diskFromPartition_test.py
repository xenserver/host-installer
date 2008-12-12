#!/usr/bin/env python
###
# HOST INSTALLER
# Unit tests for the diskFromPartition function
#
# written by Andrew Peace
# Copyright Citrix, Inc. 2008

import sys
from framework import test, finish
from diskutil import diskFromPartition, partitionNumberFromPartition

# diskFromPartition
test('diskFromPartition("/dev/sda1") == "/dev/sda"', 
      diskFromPartition("/dev/sda1") == "/dev/sda")
test('diskFromPartition("/dev/cciss/c0d0p0") == "/dev/cciss/c0d0")', 
      diskFromPartition("/dev/cciss/c0d0p0") == "/dev/cciss/c0d0")
test('diskFromPartition("/dev/disk/by-id/scsi-1ATA_ST3160023AS_5MT17ZSY-part1") == "/dev/disk/by-id/scsi-1ATA_ST3160023AS_5MT17ZSY"', 
      diskFromPartition("/dev/disk/by-id/scsi-1ATA_ST3160023AS_5MT17ZSY-part1") == "/dev/disk/by-id/scsi-1ATA_ST3160023AS_5MT17ZSY")

# partitionNumberFromPartition
test('partitionNumberFromPartition("/dev/sda1") == 1', 
      partitionNumberFromPartition("/dev/sda1") == 1)
test('partitionNumberFromPartition("/dev/cciss/c0d0p1") == 1', 
      partitionNumberFromPartition("/dev/cciss/c0d0p1") == 1)
test('partitionNumberFromPartition("/dev/disk/by-id/scsi-1ATA_ST3160023AS_5MT17ZSY-part1") == 1',
      partitionNumberFromPartition("/dev/disk/by-id/scsi-1ATA_ST3160023AS_5MT17ZSY-part1") == 1)


result = finish()
if result:
    sys.exit(0)
else:
    sys.exit(1)
