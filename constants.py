###
# XEN CLEAN INSTALLER
# Functions to perform the XE installation
#
# written by Andrew Peace & Mark Nijmeijer
# Copyright XenSource Inc. 2006

import version

min_primary_disk_size = 35

rws_size = 15000
rws_name = "RWS"
dropbox_size = 15000
dropbox_name = "Files"
dropbox_type = "ext3"

boot_size = 320
vgname = "VG_XenSource"
#xen_version = "3.0.1"

# file system creation constants
dom0tmpfs_name = "tmp-%s" % version.dom0_name
dom0tmpfs_size = 500
bootfs_type = 'ext2'
dom0tmpfs_type = 'ext3'
ramdiskfs_type = 'squashfs'
rwsfs_type = 'ext3'

MIN_PASSWD_LEN=6

# location of files on the CDROM
CD_DOM0FS_TGZ_LOCATION = "/opt/xensource/clean-installer/dom0fs-%s-%s.tgz" % (version.dom0_name, version.dom0_version)
CD_KERNEL_TGZ_LOCATION = "/opt/xensource/clean-installer/kernels-%s-%s.tgz" % (version.dom0_name, version.dom0_version)

CD_XGT_LOCATION = "/opt/xensource/xgt/"
CD_RHEL41_GUEST_INSTALLER_LOCATION = CD_XGT_LOCATION + "install/rhel41/"
CD_RHEL41_INSTALL_INITRD = CD_RHEL41_GUEST_INSTALLER_LOCATION + "rhel41-install-initrd.img"
CD_RPMS_LOCATION = "/opt/xensource/rpms/"
CD_VENDOR_KERNELS_LOCATION = "/opt/xensource/vendor-kernels"
CD_XEN_KERNEL_LOCATION = "/opt/xensource/xen-kernel"
CD_README_LOCATION = "/opt/xensource/docs/README"

# location/destination of files on the dom0 FS
DOM0_FILES_LOCATION_ROOT = "%s/files/"
DOM0_VENDOR_KERNELS_LOCATION = DOM0_FILES_LOCATION_ROOT + "vendor-kernels/"
DOM0_XEN_KERNEL_LOCATION = DOM0_FILES_LOCATION_ROOT + "xen-kernel/"
DOM0_GUEST_INSTALLER_LOCATION = DOM0_FILES_LOCATION_ROOT + "guest-installer/"

DOM0_GLIB_RPMS_LOCATION = DOM0_FILES_LOCATION_ROOT + "glibc-rpms/"
DOM0_XGT_LOCATION = "%s/xgt"
DOM0_PKGS_DIR_LOCATION = "/opt/xensource/packages"

ANSWERS_FILE = "upgrade_answers"

# files that should be writeable in the dom0 FS
writeable_files = [ '/etc/yp.conf',
                    '/etc/ntp.conf',
                    '/etc/resolv.conf',
                    '/etc/dhclient-exit-hooks',
                    '/etc/hosts',
                    '/etc/issue',
                    '/etc/adjtime' ,
                    '/etc/lvm/.cache']

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
