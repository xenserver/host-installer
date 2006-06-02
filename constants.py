###
# XEN CLEAN INSTALLER
# Functions to perform the XE installation
#
# written by Andrew Peace & Mark Nijmeijer
# Copyright XenSource Inc. 2006

import version

min_primary_disk_size = 16

rws_size = 15000
rws_name = "RWS"

boot_size = 320
vgname = "VG_XenSource"

# file system creation constants
dom0tmpfs_name = "tmp-%s" % version.dom0_name
dom0tmpfs_size = 500
bootfs_type = 'ext2'
dom0tmpfs_type = 'ext3'
ramdiskfs_type = 'squashfs'
rwsfs_type = 'ext3'

MIN_PASSWD_LEN=6

# location/destination of files on the dom0 FS
DOM0_FILES_LOCATION_ROOT = "%s/files/"
DOM0_VENDOR_KERNELS_LOCATION = DOM0_FILES_LOCATION_ROOT + "vendor-kernels/"
DOM0_XEN_KERNEL_LOCATION = DOM0_FILES_LOCATION_ROOT + "xen-kernel/"
DOM0_GUEST_INSTALLER_LOCATION = DOM0_FILES_LOCATION_ROOT + "guest-installer/"

DOM0_GLIB_RPMS_LOCATION = DOM0_FILES_LOCATION_ROOT + "glibc-rpms/"
DOM0_XGT_LOCATION = "%s/xgt"
DOM0_PKGS_DIR_LOCATION = "/opt/xensource/packages"

ANSWERS_FILE = "upgrade_answers"

# location of the timezone data file in the installation environment
timezone_data_file = '/opt/xensource/installer/timezones'

# packages to be installed
packages = [ "dom0fs-%s-%s" % (version.dom0_name, version.dom0_version),
             "kernels",
             "xgts",
             "rhel41-guest-installer",
             "vendor-kernels",
             "xen-kernel",
             "documentation",
             "rpms",
             "firewall",
             'timeutil'
            ]

# files that should be writeable in the dom0 FS
writeable_files = [ '/etc/yp.conf',
                    '/etc/ntp.conf',
                    '/etc/resolv.conf',
                    '/etc/dhclient-exit-hooks',
                    '/etc/hosts',
                    '/etc/hostname',
                    '/etc/syslog.conf',
                    '/etc/issue',
                    '/etc/adjtime',
                    '/etc/passwd',
                    '/etc/lvm/.cache']

# files that need to be readable before RWS comes online
pre_rws_dirs = [ '/etc' ]
pre_rws_files = [ '/etc/adjtime',
                 '/etc/passwd' ]

# directories to be created in the dom0 FS
asserted_dirs = [ '/etc',
                  '/etc/sysconfig',
                  '/etc/sysconfig/network-scripts',
                  '/etc/lvm' ]

# directories that should be writeable in the dom0 FS
writeable_dirs = [ '/etc/ntp',
                   '/etc/lvm/archive',
                   '/etc/lvm/backup',
                   '/etc/ssh',
                   '/root' ]
