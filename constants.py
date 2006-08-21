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

# exit status
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USER_CANCEL = 2

# other:
min_primary_disk_size = 16

vgname = "VG_XenSource"

root_size = 4096
rootfs_type = 'ext3'
rootfs_label = '/-main'

vmstate_size = 4000
vmstate_name = "VMState"
vmstate_vol = "/dev/%s/%s" % (vgname, vmstate_name)
vmstatefs_type = "ext3"

swap_size = 1000
swap_name = "Swap"

# file system creation constants
bootfs_type = 'ext2'
bootfs_label = "/boot"

MIN_PASSWD_LEN=6

EULA_PATH = "/opt/xensource/installer/EULA"

# location/destination of files on the dom0 FS
DOM0_FILES_LOCATION_ROOT = "%s/files/"
DOM0_VENDOR_KERNELS_LOCATION = DOM0_FILES_LOCATION_ROOT + "vendor-kernels/"
DOM0_XEN_KERNEL_LOCATION = DOM0_FILES_LOCATION_ROOT + "xen-kernel/"
DOM0_GUEST_INSTALLER_LOCATION = DOM0_FILES_LOCATION_ROOT + "guest-installer/"

DOM0_GLIB_RPMS_LOCATION = DOM0_FILES_LOCATION_ROOT + "glibc-rpms/"
DOM0_XGT_LOCATION = "%s/xgt"
DOM0_PKGS_DIR_LOCATION = "/opt/xensource/packages"

ANSWERS_FILE = "upgrade_answers"
INSTALLER_MODULE_LIST_FILE = "/tmp/module-order"

# location of the timezone data file in the installation environment
timezone_data_file = '/opt/xensource/installer/timezones'
kbd_data_file = '/opt/xensource/installer/keymaps'

# packages to be installed
packages = [ "dom0fs-%s-%s" % (version.PRODUCT_NAME, version.PRODUCT_VERSION),
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
writeable_files = [ '/etc/sysconfig/keyboard',
                    '/etc/yp.conf',
                    '/etc/ntp.conf',
                    '/etc/resolv.conf',
                    '/etc/dhclient-exit-hooks',
                    '/etc/hosts',
                    '/etc/hostname',
                    '/etc/syslog.conf',
                    '/etc/issue',
                    '/etc/adjtime',
                    '/etc/passwd',
                    '/etc/.pwd.lock',
                    '/etc/lvm/.cache',
                    '/etc/vendorkernel-inventory',
                    '/usr/sbin/system-info.sh']

# files that need to be readable before RWS comes online
pre_rws_dirs = [ '/etc' ]
pre_rws_files = [ '/etc/adjtime',
                 '/etc/passwd' ]

# directories to be created in the dom0 FS
asserted_dirs = [ '/etc',
                  '/etc/sysconfig',
                  '/etc/sysconfig/network-scripts',
                  '/etc/lvm',
                  '/usr/sbin' ]

# directories that should be writeable in the dom0 FS
writeable_dirs = [ '/etc/ntp',
                   '/etc/lvm/archive',
                   '/etc/lvm/backup',
                   '/etc/ssh',
                   '/root' ]
