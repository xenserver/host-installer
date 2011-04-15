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
INSTALL_TYPE_RESTORE = 3

# sr types:
SR_TYPE_LVM = 1
SR_TYPE_EXT = 2

# network backend types:
NETWORK_BACKEND_BRIDGE = "bridge"
NETWORK_BACKEND_VSWITCH = "openvswitch"
NETWORK_BACKEND_DEFAULT = NETWORK_BACKEND_VSWITCH

# Old name for openvswitch backend, for use in answerfile and on upgrade only
NETWORK_BACKEND_VSWITCH_ALT = "vswitch"

# error strings:
def error_string(error, logname, with_hd):
    (
        ERROR_STRING_UNKNOWN_ERROR_WITH_HD,
        ERROR_STRING_UNKNOWN_ERROR_WITHOUT_HD,
        ERROR_STRING_KNOWN_ERROR
    ) = range(3)

    ERROR_STRINGS = { 
        ERROR_STRING_UNKNOWN_ERROR_WITH_HD: "An unrecoverable error has occurred.  The details of the error can be found in the log file, which has been written to /tmp/%s (and /root/%s on your hard disk if possible).",
        ERROR_STRING_UNKNOWN_ERROR_WITHOUT_HD: "An unrecoverable error has occurred.  The details of the error can be found in the log file, which has been written to /tmp/%s.",
        ERROR_STRING_KNOWN_ERROR: "An unrecoverable error has occurred.  The error was:\n\n%s\n"
    }

    if version.PRODUCT_VERSION:
        ERROR_STRINGS = { 
            ERROR_STRING_UNKNOWN_ERROR_WITH_HD: "An unrecoverable error has occurred.  The details of the error can be found in the log file, which has been written to /tmp/%s (and /root/%s on your hard disk if possible).\n\nPlease refer to your user guide or contact a Technical Support Representative for more details.",
            ERROR_STRING_UNKNOWN_ERROR_WITHOUT_HD: "An unrecoverable error has occurred.  The details of the error can be found in the log file, which has been written to /tmp/%s.\n\nPlease refer to your user guide or contact a Technical Support Representative for more details.",
            ERROR_STRING_KNOWN_ERROR: "An unrecoverable error has occurred.  The error was:\n\n%s\n\nPlease refer to your user guide, or contact a Technical Support Representative, for further details."
            }

    if error == "":
        if with_hd:
            return ERROR_STRINGS[ERROR_STRING_UNKNOWN_ERROR_WITH_HD] % (logname, logname)
        else:
            return ERROR_STRINGS[ERROR_STRING_UNKNOWN_ERROR_WITHOUT_HD] % logname
    else:
        return ERROR_STRINGS[ERROR_STRING_KNOWN_ERROR] % error

# minimum hardware specs:
# memory checks should be done against MIN_SYSTEM_RAM_MB since libxc
# reports the total system ram after the Xen heap.  The UI should
# display the value given by MIN_SYSTEM_RAM_MB_RAW.
min_primary_disk_size = 12 #GB
max_primary_disk_size_dos = 2047 #GB
MIN_SYSTEM_RAM_MB_RAW = 1024 # MB
MIN_SYSTEM_RAM_MB = MIN_SYSTEM_RAM_MB_RAW - 100

# Change this to True to enable GPT partitioning instead of DOS partitioning
GPT_SUPPORT = True

DOM0_MEM=752

# filesystems and partitions (sizes in MB):
root_size = 4096
rootfs_type = 'ext3'
rootfs_label = "root-%s" % "".join([random.choice(string.ascii_lowercase)
                                    for x in range(8)])
swap_location = '/var/swap/swap.001'
swap_size = 512

MIN_PASSWD_LEN=6

# file locations - installer filesystem
EULA_PATH = "/opt/xensource/installer/EULA"
INSTALLER_DIR="/opt/xensource/installer"
XENINFO = "/usr/bin/xeninfo"
timezone_data_file = '/opt/xensource/installer/timezones'
kbd_data_file = '/opt/xensource/installer/keymaps'
ANSWERFILE_PATH = '/tmp/answerfile'
ANSWERFILE_GENERATOR_PATH = '/tmp/answerfile_generator'
SCRIPTS_DIR = "/tmp/scripts"

# host filesystem - always absolute paths from root of install
# and never start with a '/', so they can be used safely with
# os.path.join.
ANSWERS_FILE = "upgrade_answers"
INVENTORY_FILE = "etc/xensource-inventory"
BLOB_DIRECTORY = "var/xapi/blobs"

MAIN_REPOSITORY_NAME = 'xcp:main'
INTERNAL_REPOS = ["xs:xenserver-transfer-vm", "xs:main", "xs:linux"]

FIRSTBOOT_DATA_DIR = "etc/firstboot.d/data"
INSTALLED_REPOS_DIR = "etc/xensource/installed-repos"
DBCACHE = "var/xapi/network.dbcache"
NET_SCR_DIR = "etc/sysconfig/network-scripts"

POST_INSTALL_SCRIPTS_DIR = "etc/xensource/scripts/install"

SYSLINUX_CFG = "syslinux.cfg"
ROLLING_POOL_DIR = "boot/installer"

HYPERVISOR_CAPS_FILE = "/sys/hypervisor/properties/capabilities"
