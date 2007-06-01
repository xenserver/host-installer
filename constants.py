# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Functions to perform the XE installation
#
# written by Andrew Peace & Mark Nijmeijer

import version
import string
import random

# exit status
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USER_CANCEL = 2

# install types:
INSTALL_TYPE_FRESH = 1
INSTALL_TYPE_REINSTALL = 2

# sr types:
SR_TYPE_LVM = 1
SR_TYPE_EXT = 2

# minimum hardware specs:
# memory checks should be done against MIN_SYSTEM_RAM_MB since libxc
# reports the total system ram after the Xen heap.  The UI should
# display the value given by MIN_SYSTEM_RAM_MB_RAW.
min_primary_disk_size = 16 #GB
max_primary_disk_size = 2047 #GB
MIN_SYSTEM_RAM_MB_RAW = 1024 # MB
MIN_SYSTEM_RAM_MB = MIN_SYSTEM_RAM_MB_RAW - 100

DOM0_MEM=752

# filesystems and partitions (sizes in MB):
root_size = 4096
rootfs_type = 'ext3'
rootfs_label = "root-%s" % "".join([random.choice(string.ascii_lowercase)
                                    for x in range(8)])
default_sr_firstpartition = 3
swap_location = '/var/swap/swap.001'
swap_size = 512

MIN_PASSWD_LEN=6

# file locations - installer filesystem
EULA_PATH = "/opt/xensource/installer/EULA"
XENINFO = "/usr/bin/xeninfo"
timezone_data_file = '/opt/xensource/installer/timezones'
kbd_data_file = '/opt/xensource/installer/keymaps'

# host filesystem - always absolute paths from root of install
# and never start with a '/', so they can be used safely with
# os.path.join.
ANSWERS_FILE = "upgrade_answers"
INVENTORY_FILE = "etc/xensource-inventory"

MAIN_REPOSITORY_NAME = 'xs:main'
