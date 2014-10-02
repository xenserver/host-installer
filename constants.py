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
INSTALL_TYPE_FRESH = "fresh"
INSTALL_TYPE_REINSTALL = "reinstall"
INSTALL_TYPE_RESTORE = "restore"

# sr types:
SR_TYPE_LVM = "lvm"
SR_TYPE_EXT = "ext"

# partition schemes:
PARTITION_DOS = "DOS"
PARTITION_GPT = "GPT"

# bootloader locations:
BOOT_LOCATION_MBR = "mbr"
BOOT_LOCATION_PARTITION = "partition"

# first partition preservation:
PRESERVE_IF_UTILITY = "if-utility"

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
timezone_data_file = '/opt/xensource/installer/timezones'
kbd_data_file = '/opt/xensource/installer/keymaps'
ANSWERFILE_PATH = '/tmp/answerfile'
ANSWERFILE_GENERATOR_PATH = '/tmp/answerfile_generator'
SCRIPTS_DIR = "/tmp/scripts"
EXTRA_SCRIPTS_DIR = "/tmp/extra-scripts"

# host filesystem - always absolute paths from root of install
# and never start with a '/', so they can be used safely with
# os.path.join.
ANSWERS_FILE = "upgrade_answers"
INVENTORY_FILE = "etc/xensource-inventory"
OLD_BLOB_DIRECTORY = "var/xapi/blobs"
BLOB_DIRECTORY = "var/lib/xcp/blobs"

MAIN_REPOSITORY_NAME = 'xcp:main'
MAIN_XS_REPOSITORY_NAME = 'xs:main'
INTERNAL_REPOS = [MAIN_XS_REPOSITORY_NAME, "xs:xenserver-transfer-vm", "xs:linux", "xcp:extras"]

FIRSTBOOT_DATA_DIR = "etc/firstboot.d/data"
INSTALLED_REPOS_DIR = "etc/xensource/installed-repos"
OLD_DBCACHE = "var/xapi/network.dbcache"
DBCACHE = "var/lib/xcp/network.dbcache"
OLD_NETWORK_DB = "var/xapi/networkd.db"
NETWORK_DB = "var/lib/xcp/networkd.db"
NETWORKD_DB = "usr/bin/networkd_db"
OLD_NETWORKD_DB = "opt/xensource/libexec/networkd_db"
NET_SCR_DIR = "etc/sysconfig/network-scripts"

POST_INSTALL_SCRIPTS_DIR = "etc/xensource/scripts/install"

SYSLINUX_CFG = "syslinux.cfg"
ROLLING_POOL_DIR = "boot/installer"

HYPERVISOR_CAPS_FILE = "/sys/hypervisor/properties/capabilities"

# timer to exit installer after fatal error
AUTO_EXIT_TIMER = 10 * 1000

# bootloader timeout
BOOT_MENU_TIMEOUT = 50

FIX_AD_REG_PATHS_SCRIPT = "fix_ad_reg_paths.py"
FIX_AD_WORK_DIR = "tmp/fix_ad"
# timeout used for multipath iscsi
MPATH_ISCSI_TIMEOUT = 15
