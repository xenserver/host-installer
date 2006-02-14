###
# XEN CLEAN INSTALLER
# Functions to perform the XE installation
#
# written by Mark Nijmeijer
# Copyright XenSource Inc. 2006

import os
import os.path

import p2v_tui
import p2v_uicontroller
import findroot
import sys
import constants
import p2v_tui
import p2v_utils

ui_package = p2v_tui

from p2v_error import P2VError


def print_results( results ):
    if p2v_utils.is_debug():
        for key in results.keys():
            sys.stderr.write( "result.key = %s \t\t" % key )
            sys.stderr.write( "result.value = %s\n" % results[key] )
         
def mount_os_root( os_root_device, dev_attrs ):
    return findroot.mount_os_root( os_root_device, dev_attrs )
 
def umount_os_root( mnt ):
    return findroot.umount_dev( mnt )

def append_hostname(os_install): 
    os_install[constants.HOST_NAME] = os.uname()[1]
    
def setup_networking(os_install):
    findroot.run_command("ifup eth0");

def determine_size(os_install):
    os_root_device = os_install[constants.DEV_NAME]
    dev_attrs = os_install[constants.DEV_ATTRS]
    os_root_mount_point = mount_os_root( os_root_device, dev_attrs )

    (used_size, total_size) = findroot.determine_size(os_root_mount_point, os_root_device )
        
    os_install[constants.FS_USED_SIZE] = used_size
    os_install[constants.FS_TOTAL_SIZE] = total_size
    umount_os_root( os_root_mount_point )
    
def get_mem_info(os_install):
    total_mem = findroot.get_mem_info()
    os_install[constants.TOTAL_MEM] = total_mem
    
def get_cpu_count(os_install):
    cpu_count = findroot.get_cpu_count()
    os_install[constants.CPU_COUNT] = cpu_count

def perform_p2v( os_install, inbox_path ):
    os_root_device = os_install[constants.DEV_NAME]
    dev_attrs = os_install[constants.DEV_ATTRS]
    os_root_mount_point = mount_os_root( os_root_device, dev_attrs )
    pd = os_install['pd']
    rc, tardirname, tarfilename, md5sum = findroot.handle_root( os_root_mount_point, os_root_device, pd)
    os_install[constants.XEN_TAR_FILENAME] = tarfilename
    os_install[constants.XEN_TAR_DIRNAME] = tardirname
    os_install[constants.XEN_TAR_MD5SUM] = md5sum
    umount_os_root( os_root_mount_point )
    
def nfs_mount( nfs_mount_path ):
    local_mount_path = "/xenpending"
    rc, out = findroot.run_command('grep -q "%s nfs" /proc/mounts' % local_mount_path)
    if rc == 0:
        return #already mounted
    
    rc, out = findroot.run_command( "mkdir -p /xenpending" )
    if rc != 0: 
        raise P2VError("Failed to nfs mount - mkdir failed")
    rc, out = findroot.run_command( "mount %s %s %s" % ( nfs_mount_path, local_mount_path, p2v_utils.show_debug_output() ) )
    if rc != 0: 
        raise P2VError("Failed to nfs mount - mount failed")
    return local_mount_path

#TODO : validation of nfs_path?         
def nfs_p2v( nfs_host, nfs_path, os_install ):
    nfs_mount_path = nfs_host + ":" + nfs_path
    inbox_path = nfs_mount( nfs_mount_path )
    perform_p2v( os_install, inbox_path )
        
def mount_inbox( xe_host ):    
    inbox_path = "/inbox"
    fs_mount_path = nfs_mount( xe_host +":" + inbox_path )
    return fs_mount_path

def xe_p2v( xe_host, os_install ):
    inbox_path = mount_inbox( xe_host )
    perform_p2v( os_install, inbox_path )
         
def perform_P2V( results ):
    os_install = results[constants.OS_INSTALL]
    pd =  ui_package.initProgressDialog('Xen Enterprise P2V',
                                       'Performing P2V operation...',
                                       5)
    os_install['pd'] = pd
    setup_networking(os_install)
    determine_size(os_install)
    append_hostname(os_install)
    get_mem_info(os_install)
    get_cpu_count(os_install)
    if results[constants.XEN_TARGET] == constants.XEN_TARGET_XE:
        p2v_utils.trace_message( "we're doing a p2v to XE" )
        xe_host = results[constants.XE_HOST]
        xe_p2v( xe_host, os_install )
    elif results[constants.XEN_TARGET] == constants.XEN_TARGET_NFS:
        p2v_utils.trace_message( "we're doing a p2v to XE" )
        nfs_host = results[constants.NFS_HOST]
        nfs_path = results[constants.NFS_PATH]
        nfs_p2v( nfs_host, nfs_path, os_install )
        
    ui_package.displayProgressDialog(3, pd, " - Writing template")
    write_template(os_install)
    
    ui_package.displayProgressDialog(4, pd, " - Creating XGT")
    create_xgt(os_install)
    ui_package.displayProgressDialog(5, pd, " - Finished")
    
    ui_package.clearProgressDialog()
    
    return 0
    
def open_tag(tag, value = ""):
    template_string = ""
    template_string += "("
    template_string += tag
    template_string += " "
    template_string += value
    return template_string
    
def close_tag(tag):
    template_string = ""
    template_string += ") "
    return template_string
    #tag is unused
    
#TODO: add implementation
def determine_distrib(os_install):
    os_name = os_install[constants.OS_NAME]
    if os_name == "Red Hat":
        return "rhel"
    elif os_name == "SuSE":
        return "sles9"
    
def add_xgt_version():
    template_string = ""
    template_string += open_tag(constants.TAG_XGT_VERSION, "4")
    template_string += close_tag(constants.TAG_XGT_VERSION)
    return template_string

def add_xgt_type():
    template_string = ""
    template_string += open_tag(constants.TAG_XGT_TYPE, "p2v-archive")
    template_string += close_tag(constants.TAG_XGT_TYPE)
    return template_string

# pp2vp = post p2v processing :)
def add_pp2vp():
    template_string = ""
    template_string += open_tag(constants.TAG_XGT_PP2VP, "yes")
    template_string += close_tag(constants.TAG_XGT_PP2VP)
    return template_string

    
def add_name(os_install):
    template_string = ""
    host_name = os_install[constants.HOST_NAME]
    os_name = os_install[constants.OS_NAME]
    os_version = os_install[constants.OS_VERSION]
    template_string += open_tag(constants.TAG_NAME, "'P2V of os_install %s %s of host %s'" % (os_name, os_version, host_name))
    template_string += close_tag(constants.TAG_NAME)
    return template_string

def add_rootfs(os_install):
	template_string = ""
	fs = ""
	if os_install['dev_attrs'] != None:
		sec_type = os_install['dev_attrs']['sec_type']
    	fs_type = os_install['dev_attrs']['type']

	if sec_type != None:
		print "sectype = ", sec_type
		fs = sec_type
	else:
		if fs_type != None:
			print "fs_type = ", fs_type
			fs = fs_type
	template_string += open_tag("rootfs-type", fs)
	template_string += close_tag("rootfs-type")
	return template_string
    
def add_distrib(os_install):
    template_string = ""
    template_string += open_tag(constants.TAG_DISTRIB, determine_distrib(os_install))
    template_string += close_tag( constants.TAG_DISTRIB)
    return template_string

def add_mem_info(os_install):
    template_string = ""
    template_string += open_tag(constants.TAG_TOTAL_MEM, os_install[constants.TOTAL_MEM])
    template_string += close_tag( constants.TAG_TOTAL_MEM)
    return template_string

def add_cpu_count(os_install):
    template_string = ""
    template_string += open_tag(constants.TAG_CPU_COUNT, os_install[constants.CPU_COUNT])
    template_string += close_tag( constants.TAG_CPU_COUNT)
    return template_string

def add_description(os_install):
    template_string = ""
    template_string += open_tag(constants.TAG_DESCRIPTION, "'%s'" % os_install[constants.DESCRIPTION])
    template_string += close_tag( constants.TAG_DESCRIPTION)
    return template_string

def add_uri(os_install):
    template_string = ""
    template_string += open_tag(constants.TAG_FILESYSTEM_URI, os_install[constants.XEN_TAR_FILENAME])
    template_string += close_tag( constants.TAG_FILESYSTEM_URI)
    return template_string

def add_function(os_install):
    template_string = ""
    template_string += open_tag(constants.TAG_FILESYSTEM_FUNCTION, 'root')
    template_string += close_tag( constants.TAG_FILESYSTEM_FUNCTION)
    return template_string

def add_type(os_install):
    template_string = ""
    template_string += open_tag(constants.TAG_FILESYSTEM_TYPE, 'tar')
    template_string += close_tag( constants.TAG_FILESYSTEM_TYPE)
    return template_string
    
def add_vbd(os_install):
    template_string = ""
    template_string += open_tag(constants.TAG_FILESYSTEM_VBD, os.path.basename(os_install[constants.DEV_NAME]))
    template_string += close_tag( constants.TAG_FILESYSTEM_VBD)
    return template_string

def add_md5sum(os_install):
    template_string = ""
    template_string += open_tag(constants.TAG_FILESYSTEM_MD5SUM,  os_install[constants.XEN_TAR_MD5SUM])
    template_string += close_tag( constants.TAG_FILESYSTEM_MD5SUM)
    return template_string

def add_total_size(os_install):
    template_string = ""
    template_string += open_tag(constants.TAG_FILESYSTEM_TOTAL_SIZE,  os_install[constants.FS_TOTAL_SIZE])
    template_string += close_tag( constants.TAG_FILESYSTEM_TOTAL_SIZE)
    return template_string

def add_used_size(os_install):
    template_string = ""
    template_string += open_tag(constants.TAG_FILESYSTEM_USED_SIZE,  os_install[constants.FS_USED_SIZE])
    template_string += close_tag( constants.TAG_FILESYSTEM_USED_SIZE)
    return template_string

def add_filesystem(os_install):
    template_string = ""
    os_root_device = os_install[constants.DEV_NAME]
    dev_attrs = os_install[constants.DEV_ATTRS]
    fs_used_size = os_install[constants.FS_USED_SIZE]
    template_string += open_tag(constants.TAG_FILESYSTEM)
    template_string += add_uri(os_install)
    template_string += add_function(os_install)
    template_string += add_type(os_install)
    template_string += add_vbd(os_install)
    template_string += add_md5sum(os_install)
    template_string += add_total_size(os_install)
    template_string += add_used_size(os_install)
    template_string += close_tag(constants.TAG_FILESYSTEM)
    return template_string
         
def write_template(os_install):
    template_string = ""
    
    template_string += open_tag(constants.TAG_XGT)
    template_string += add_xgt_version()
    template_string += add_xgt_type()
    template_string += add_pp2vp(os_install)
    template_string += add_name(os_install)
    template_string += add_rootfs(os_install)
    template_string += add_distrib(os_install)
    template_string += add_mem_info(os_install)
    template_string += add_cpu_count(os_install)
    template_string += add_description(os_install)
    template_string += add_filesystem(os_install)
    template_string += close_tag(constants.TAG_XGT)
    
    template_dir= os_install[constants.XEN_TAR_DIRNAME]
    template_filename = "template.dat"
    template_file = os.path.join(template_dir, template_filename)
    #store the template file name in the os_install, so we can use it when creating the xgt
    os_install[constants.XEN_TEMPLATE_FILENAME] = template_filename
    
    if os.path.exists(template_file):
        p2v_utils.trace_message("template file already exists. overwriting");
        os.unlink(template_file)
    
    f = open(template_file, "w")
    f.write(template_string + '\n')
    f.close()
    
    p2v_utils.trace_message("template  = %s\n" % template_string)
    return

def create_xgt(os_install):
    xgt_create_dir = os_install[constants.XEN_TAR_DIRNAME]
    template_filename =  os_install[constants.XEN_TEMPLATE_FILENAME]
    tar_filename = os_install[constants.XEN_TAR_FILENAME]
    
    xgt_filename = tar_filename.replace('.tar.bz2', '.xgt')
    
    assert (os.path.exists(os.path.join(xgt_create_dir, template_filename)))
    assert (os.path.exists(os.path.join(xgt_create_dir, tar_filename)))
    
    findroot.create_xgt(xgt_create_dir, xgt_filename, template_filename, tar_filename)
    
    #and delete the tar and template files
    os.unlink(os.path.join(xgt_create_dir, template_filename))
    os.unlink(os.path.join(xgt_create_dir, tar_filename))
    
    
    
