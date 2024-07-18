# SPDX-License-Identifier: GPL-2.0-only

import version
import string
import random
import os.path

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
# See also SR_TYPE_LARGE_BLOCK at the bottom of this file

# partition schemes:
PARTITION_DOS = "DOS"
PARTITION_GPT = "GPT"

# bootloader locations:
BOOT_LOCATION_MBR = "mbr"
BOOT_LOCATION_PARTITION = "partition"

# The lowest LBA that a partition can start at if installing the bootloader
# to the MBR (applies to legacy mode with DOS partition type only).
LBA_PARTITION_MIN = 63

# target boot mode:
TARGET_BOOT_MODE_LEGACY = "legacy"
TARGET_BOOT_MODE_UEFI = "uefi"

# first partition preservation:
PRESERVE_IF_UTILITY = "if-utility"
UTILITY_PARTLABEL = "DELLUTILITY"

UEFI_INSTALLER = os.path.exists("/sys/firmware/efi")

# network backend types:
NETWORK_BACKEND_BRIDGE = "bridge"
NETWORK_BACKEND_VSWITCH = "openvswitch"
NETWORK_BACKEND_DEFAULT = NETWORK_BACKEND_VSWITCH

# Old name for openvswitch backend, for use in answerfile and on upgrade only
NETWORK_BACKEND_VSWITCH_ALT = "vswitch"

# error strings:
def error_string(error, logname, with_hd):
    error = error.rstrip()
    if error == "":
        err = "The details of the error can be found in the log file, which has been written to /tmp/%s" % logname
        if with_hd:
            err += " (and /root/%s on your hard disk if possible)" % logname
    else:
        err = "The error was:\n\n%s" % error

    if err[-1:] != '.':
        err += '.'

    return ('An unrecoverable error has occurred.  ' + err +
        '\n\nPlease refer to your user guide or contact a Technical Support Representative for more details.')

# minimum hardware specs:
# memory checks should be done against MIN_SYSTEM_RAM_MB since libxc
# reports the total system ram after the Xen heap.  The UI should
# display the value given by MIN_SYSTEM_RAM_MB_RAW.
min_primary_disk_size = 46 #GB
MIN_SYSTEM_RAM_MB_RAW = 1024 # MB
MIN_SYSTEM_RAM_MB = MIN_SYSTEM_RAM_MB_RAW - 100

# Change this to True to enable GPT partitioning instead of DOS partitioning
GPT_SUPPORT = True

# filesystems and partitions (sizes in MB):
boot_size = 512
root_size = 18432
backup_size = 18432
swap_file_size = 512
swap_size = 1024
logs_size = 4096
logs_free_space = 20

# filesystems and partitions types:
bootfs_type = 'vfat'
rootfs_type = 'ext3'
logsfs_type = 'ext3'

# filesystems and partitions labels:
bootfs_label = "BOOT-%s"
rootfs_label = "root-%s"
swap_file = '/var/swap/swap.001'
swap_label = 'swap-%s'
logsfs_label_prefix = 'logs-'
logsfs_label = logsfs_label_prefix + '%s'

rootpart_label = "root"
backuppart_label = "backup"
storagepart_label = "localsr"
bootpart_label = "ESP"
logspart_label = "logs"
swappart_label = "swap"

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
defaults_data_file = '/opt/xensource/installer/defaults.json'
SYSFS_IBFT_DIR = "/sys/firmware/ibft"

# host filesystem - always absolute paths from root of install
# and never start with a '/', so they can be used safely with
# os.path.join.
ANSWERS_FILE = "upgrade_answers"
INVENTORY_FILE = "etc/xensource-inventory"
XENCOMMONS_FILE = "etc/sysconfig/xencommons"
OLD_BLOB_DIRECTORY = "var/xapi/blobs"
BLOB_DIRECTORY = "var/lib/xcp/blobs"

MAIN_REPOSITORY_NAME = 'xcp:main'
MAIN_XS_REPOSITORY_NAME = 'xs:main'
INTERNAL_REPOS = [MAIN_XS_REPOSITORY_NAME, "xs:xenserver-transfer-vm", "xs:linux", "xcp:extras"]

FIRSTBOOT_DATA_DIR = "etc/firstboot.d/data"
INSTALLED_REPOS_DIR = "etc/xensource/installed-repos"
NETWORK_DB = "var/lib/xcp/networkd.db"
NETWORKD_DB = "usr/bin/networkd_db"
NET_SCR_DIR = "etc/sysconfig/network-scripts"
OLD_XAPI_DB = 'var/xapi/state.db'
XAPI_DB = 'var/lib/xcp/state.db'
CLUSTERD_CONF = 'var/opt/xapi-clusterd/db'

POST_INSTALL_SCRIPTS_DIR = "etc/xensource/scripts/install"

SYSLINUX_CFG = "syslinux.cfg"
ROLLING_POOL_DIR = "boot/installer"

HYPERVISOR_CAPS_FILE = "/sys/hypervisor/properties/capabilities"
SAFE_2_UPGRADE = "var/preserve/safe2upgrade"

# NTP server domains to treat as 'default' servers
DEFAULT_NTP_DOMAINS = [".centos.pool.ntp.org", ".xenserver.pool.ntp.org"]

# timer to exit installer after fatal error
AUTO_EXIT_TIMER = 10 * 1000

# bootloader timeout
BOOT_MENU_TIMEOUT = 50

# timeout used for multipath iscsi
MPATH_ISCSI_TIMEOUT = 15

ISCSI_NODES = 'var/lib/iscsi/nodes'

# prepare configuration for common criteria security
CC_PREPARATIONS = False
CC_FIREWALL_CONF = '/opt/xensource/installer/common_criteria_firewall_rules'

# list of dom0 services that will be disabled for common criteria preparation,
# and these can be overridden by answer file
SERVICES = ["sshd"]

# List of services which must have run before allowing an upgrade.
# These services need to have been run because they are only run after an
# install, not an upgrade so if they don't run before upgrading they will never
# be run.
INIT_SERVICE_FILES = [
    'var/lib/misc/ran-network-init',
    'var/lib/misc/ran-storage-init',
]

# optional features
FEATURES_DIR = "/etc/xensource/features"
HAS_SUPPLEMENTAL_PACKS = os.path.exists(os.path.join(FEATURES_DIR, "supplemental-packs"))
SR_TYPE_LARGE_BLOCK = None
try:
    with open(os.path.join(FEATURES_DIR, "large-block-capable-sr-type")) as f:
        value = f.read().strip()
        if value:
            SR_TYPE_LARGE_BLOCK = value
except IOError:
    pass

# Error partitioning disk as in use
PARTITIONING_ERROR = \
	'The disk appears to be in use and partition changes cannot be applied. Reboot and repeat the installation'
