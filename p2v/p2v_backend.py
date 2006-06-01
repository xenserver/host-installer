###
# XEN CLEAN INSTALLER
# Functions to perform the XE installation
#
# written by Mark Nijmeijer
# Copyright XenSource Inc. 2006

import os
import os.path
import xml.sax.saxutils

import p2v_tui
import p2v_uicontroller
import findroot
import sys
import time
import p2v_constants
import p2v_tui
import p2v_utils
import util


ui_package = p2v_tui

from p2v_error import P2VError, P2VPasswordError, P2VMountError
from version import *

#globals
dropbox_path = "/opt/xensource/packages/xgt/"

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
    os_install[p2v_constants.HOST_NAME] = os.uname()[1]

def generate_ssh_key():
    rc = 0

    if not os.path.exists(p2v_constants.SSH_KEY_FILE):
        rc, out = findroot.run_command('echo "y" | /usr/bin/ssh-keygen -t rsa -P "" -f %s'% p2v_constants.SSH_KEY_FILE);
    return (rc, p2v_constants.SSH_KEY_FILE)
    
def prepare_agent(xe_host, os_install, ssh_key_file):
    rc = 0
    ssh_pub_key_file = ssh_key_file + ".pub"
    root_password = os_install['root-password']
    
    # send the public key to the agent
    rc, out = findroot.run_command("/opt/xensource/installer/xecli -h '%s' -c addkey -p '%s' '%s'" % (xe_host, root_password, ssh_pub_key_file))

    if rc != 0:
        p2v_utils.trace_message("Failed to add public key (%d, %s)" % (rc, out))
        if "Authentication failure" in out:
            raise P2VPasswordError("Failed to add public ssh key. Please verify your hostname and password.")
        else:
            raise P2VError("Failed to add public ssh key. Please verify your hostname and password.")

    total_size = long(0)
    used_size = long(0)

    os_install_name = os_install[p2v_constants.OS_NAME]
    os_install_version = os_install[p2v_constants.OS_VERSION]
    os_install_hostname =  os_install[p2v_constants.HOST_NAME]
    os_install_distribution = determine_distrib(os_install)
    # agent expects size in KB. We internally store in bytes
    total_size = long(os_install[p2v_constants.FS_TOTAL_SIZE]) / 1024
    used_size = long(os_install[p2v_constants.FS_USED_SIZE]) / 1024
    cpu_count = int(os_install[p2v_constants.CPU_COUNT])
    description = os_install[p2v_constants.DESCRIPTION]
    rc, out =  findroot.run_command("/opt/xensource/installer/xecli -h '%s' -c preparep2v -p '%s' '%s' '%s' '%s' '%s' '%s' '%d' '%d' '%d'" % (
                xe_host,
                root_password,
                os_install_name,
                description,
                os_install_version,
                os_install_hostname,
                os_install_distribution,
                total_size,
                used_size,
                cpu_count))

    if rc != 0:
        p2v_utils.trace_message("Failed to prepare_p2v (%s)" % out)
        raise P2VError("Failed to prepare the %s host for this P2V. There might not be enough free space(%s)" % PRODUCT_BRAND)

    for line in out.split('\n'):
        try:
            name, val = line.split('=')
            if name == 'p2v_path':
                os_install[name] = val
            if name == 'uuid':
                os_install[name] = val
        except ValueError:
            pass
    return rc
    
def finish_agent(os_install, xe_host):
    #tell the agent that we're done
    root_password = os_install['root-password']
    rc, out =  findroot.run_command("/opt/xensource/installer/xecli -h '%s' -c finishp2v -p '%s' '%s'"% (xe_host, root_password, os_install['uuid']))

    if rc != 0:
        p2v_utils.trace_message("Failed to finishp2v (%s)" % out)
        raise P2VError("Failed to finish this P2V to the %s host. Please contact XenSource support." % PRODUCT_BRAND)
    return rc
    

def determine_size(os_install):
    os_root_device = os_install[p2v_constants.DEV_NAME]
    dev_attrs = os_install[p2v_constants.DEV_ATTRS]
    os_root_mount_point = mount_os_root( os_root_device, dev_attrs )

    total_size_l = long(0)

    #findroot.determine_size returns in bytes
    (used_size, total_size) = findroot.determine_size(os_root_mount_point, os_root_device )
    
    # adjust total size to 150% of used size, with a minimum of 4Gb
    total_size_l = (long(used_size) * 3) / 2
    if total_size_l < (4 * (1024 ** 3)): # size in template.dat is in bytes
        total_size_l = (4 * (1024 ** 3))
        
    total_size = str(total_size_l)
    
    os_install[p2v_constants.FS_USED_SIZE] = used_size
    os_install[p2v_constants.FS_TOTAL_SIZE] = total_size
    umount_os_root( os_root_mount_point )
    
def get_mem_info(os_install):
    total_mem = findroot.get_mem_info()
    os_install[p2v_constants.TOTAL_MEM] = total_mem
    
def get_cpu_count(os_install):
    cpu_count = findroot.get_cpu_count()
    os_install[p2v_constants.CPU_COUNT] = cpu_count

def perform_p2v( os_install, inbox_path):
    os_root_device = os_install[p2v_constants.DEV_NAME]
    dev_attrs = os_install[p2v_constants.DEV_ATTRS]
    os.environ['LVM_SYSTEM_DIR'] = '/tmp'
    os_root_mount_point = mount_os_root( os_root_device, dev_attrs )
    pd = os_install['pd']
    rc, tardirname, tarfilename, md5sum = findroot.handle_root( os_root_mount_point, os_root_device, pd)
    os_install[p2v_constants.XEN_TAR_FILENAME] = tarfilename
    os_install[p2v_constants.XEN_TAR_DIRNAME] = tardirname
    os_install[p2v_constants.XEN_TAR_MD5SUM] = md5sum
    umount_os_root( os_root_mount_point )

def perform_p2v_ssh( os_install, hostname, keyfile):
    os_root_device = os_install[p2v_constants.DEV_NAME]
    dev_attrs = os_install[p2v_constants.DEV_ATTRS]
    os_root_mount_point = mount_os_root( os_root_device, dev_attrs )
    pd = os_install['pd']
    target_directory=os_install['p2v_path']

    rc = findroot.handle_root_ssh(os_root_mount_point, os_root_device, hostname, target_directory, keyfile, pd)

    if rc != 0:
        raise P2VError("Failed to complete P2V operation")

    return rc
        
def nfs_mount( nfs_mount_path ):
    local_mount_path = "/tmp/xenpending"
    rc, out = findroot.run_command('grep -q "%s nfs" /proc/mounts' % local_mount_path)
    if rc == 0:
        return local_mount_path #already mounted
    
    rc, out = findroot.run_command( "mkdir -p %s"  % local_mount_path)
    if rc != 0: 
        raise P2VError("Failed to nfs mount - mkdir failed")
    rc, out = findroot.run_command( "mount %s %s %s" % ( nfs_mount_path, local_mount_path, p2v_utils.show_debug_output() ) )
    if rc != 0: 
        raise P2VMountError("Failed to nfs mount - mount failed")
    return local_mount_path

def validate_nfs_path(nfs_host, nfs_path):
    nfs_mount_path = nfs_host + ":" + nfs_path
    inbox_path = nfs_mount( nfs_mount_path )

#TODO : validation of nfs_path?         
def nfs_p2v( nfs_host, nfs_path, os_install ):
    nfs_mount_path = nfs_host + ":" + nfs_path
    inbox_path = nfs_mount( nfs_mount_path )
    perform_p2v( os_install, inbox_path )
    return 0
        
def mount_dropbox( xe_host ):    
    global dropbox_path
    fs_mount_path = nfs_mount( xe_host +":" + dropbox_path )
    return fs_mount_path

def xe_p2v( xe_host, os_install ):
    dropbox_path = mount_dropbox( xe_host )
    perform_p2v( os_install, dropbox_path )

def ssh_p2v( xe_host, os_install, results, pd ):
    (rc, ssh_key_file) = generate_ssh_key()
    if rc != 0:
        return rc

    ui_package.displayProgressDialog(0, pd, " - Preparing %s host" % PRODUCT_BRAND)
    rc = prepare_agent(xe_host, os_install, ssh_key_file)
    if rc != 0:
        return rc

    rc = perform_p2v_ssh( os_install, xe_host, ssh_key_file)
    if rc != 0:
        return rc

    ui_package.displayProgressDialog(3, pd, " - Finalizing install on %s host" % PRODUCT_BRAND)
    rc = finish_agent(os_install, xe_host)
    if rc != 0:
        return rc
         
def perform_P2V( results ):
    os_install = results[p2v_constants.OS_INSTALL]
    if results[p2v_constants.XEN_TARGET] == p2v_constants.XEN_TARGET_SSH:
        num_steps = 5
    else:
        num_steps = 4

    pd =  ui_package.initProgressDialog('Xen Enterprise P2V',
                                       'Performing P2V operation...',
                                       num_steps)
    os_install['pd'] = pd

    #determine_size(os_install)

#    append_hostname(os_install)

    get_mem_info(os_install)

    get_cpu_count(os_install)

    if results[p2v_constants.XEN_TARGET] == p2v_constants.XEN_TARGET_XE:
        p2v_utils.trace_message( "we're doing a p2v to XE" )
        xe_host = results[p2v_constants.XE_HOST]
        xe_p2v( xe_host, os_install )
    elif results[p2v_constants.XEN_TARGET] == p2v_constants.XEN_TARGET_NFS:
        p2v_utils.trace_message( "we're doing a p2v to NFS" )
        nfs_host = results[p2v_constants.NFS_HOST]
        nfs_path = results[p2v_constants.NFS_PATH]
        rc = nfs_p2v( nfs_host, nfs_path, os_install )
    elif results[p2v_constants.XEN_TARGET] == p2v_constants.XEN_TARGET_SSH:
        p2v_utils.trace_message( "we're doing a p2v over SSH" )
        xe_host = results[p2v_constants.XE_HOST]
        rc = ssh_p2v( xe_host, os_install, results, pd )
        
    if results[p2v_constants.XEN_TARGET] != p2v_constants.XEN_TARGET_SSH:
        ui_package.displayProgressDialog(3, pd, " - Writing template")
        write_template(os_install)
        
        ui_package.displayProgressDialog(4, pd, " - Creating XGT")
        create_xgt(os_install)

    ui_package.displayProgressDialog(num_steps, pd, " - Finished")
    
    ui_package.clearProgressDialog()
    
    return 0

def escape(string):
    dict = {"'" : "\\'"}
    return xml.sax.saxutils.escape(string, dict)
    
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
    
def determine_distrib(os_install):
    os_name = os_install[p2v_constants.OS_NAME]
    if os_name == "Red Hat":
        return "rhel"
    elif os_name == "SuSE":
        return "sles"

def determine_distrib_version(os_install):
    os_version = os_install[p2v_constants.OS_VERSION]
    return os_version
     
def add_xgt_version():
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_XGT_VERSION, "4")
    template_string += close_tag(p2v_constants.TAG_XGT_VERSION)
    return template_string

def add_xgt_type():
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_XGT_TYPE, "p2v-archive")
    template_string += close_tag(p2v_constants.TAG_XGT_TYPE)
    return template_string

# pp2vp = post p2v processing :)
def add_pp2vp(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_XGT_PP2VP, "yes")
    template_string += close_tag(p2v_constants.TAG_XGT_PP2VP)
    return template_string

    
def add_name(os_install):
    template_string = ""
    host_name = os_install[p2v_constants.HOST_NAME]
    os_name = os_install[p2v_constants.OS_NAME]
    os_version = os_install[p2v_constants.OS_VERSION]
    template_string += open_tag(p2v_constants.TAG_NAME, "'P2V of %s %s on %s'" 
                                 % (os_name, os_version, host_name))
    template_string += close_tag(p2v_constants.TAG_NAME)
    return template_string

def add_rootfs(os_install):
    template_string = ""
    fs = ""
    sec_type = None
    fs_type = None
    if os_install['dev_attrs'] != None:
        if os_install['dev_attrs'].has_key('sec_type'):
            sec_type = os_install['dev_attrs']['sec_type']
        if os_install['dev_attrs'].has_key('fs_type'):
            fs_type = os_install['dev_attrs']['type']

    if sec_type != None:
        fs = sec_type
    else:
        if fs_type != None:
            fs = fs_type
    template_string += open_tag("rootfs-type", fs)
    template_string += close_tag("rootfs-type")
    return template_string
    
def add_distrib(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_DISTRIB, determine_distrib(os_install))
    template_string += close_tag( p2v_constants.TAG_DISTRIB)
    return template_string

def add_distrib_version(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_DISTRIB_VERSION, determine_distrib_version(os_install))
    template_string += close_tag( p2v_constants.TAG_DISTRIB_VERSION)
    return template_string

def add_mem_info(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_TOTAL_MEM, os_install[p2v_constants.TOTAL_MEM])
    template_string += close_tag( p2v_constants.TAG_TOTAL_MEM)
    return template_string

def add_cpu_count(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_CPU_COUNT, os_install[p2v_constants.CPU_COUNT])
    template_string += close_tag( p2v_constants.TAG_CPU_COUNT)
    return template_string

def add_description(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_DESCRIPTION, "'%s'" % escape(os_install[p2v_constants.DESCRIPTION]))
    template_string += close_tag( p2v_constants.TAG_DESCRIPTION)
    return template_string

def add_uri(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_FILESYSTEM_URI, os_install[p2v_constants.XEN_TAR_FILENAME])
    template_string += close_tag( p2v_constants.TAG_FILESYSTEM_URI)
    return template_string

def add_function(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_FILESYSTEM_FUNCTION, 'root')
    template_string += close_tag( p2v_constants.TAG_FILESYSTEM_FUNCTION)
    return template_string

def add_type(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_FILESYSTEM_TYPE, 'tar')
    template_string += close_tag( p2v_constants.TAG_FILESYSTEM_TYPE)
    return template_string
    
def add_vbd(os_install):
    template_string = ""
#    template_string += open_tag(p2v_constants.TAG_FILESYSTEM_VBD, os.path.basename(os_install[p2v_constants.DEV_NAME]))
    template_string += open_tag(p2v_constants.TAG_FILESYSTEM_VBD, 'sda1')
    template_string += close_tag( p2v_constants.TAG_FILESYSTEM_VBD)
    return template_string

def add_md5sum(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_FILESYSTEM_MD5SUM,  os_install[p2v_constants.XEN_TAR_MD5SUM])
    template_string += close_tag( p2v_constants.TAG_FILESYSTEM_MD5SUM)
    return template_string

def add_total_size(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_FILESYSTEM_TOTAL_SIZE,  os_install[p2v_constants.FS_TOTAL_SIZE])
    template_string += close_tag( p2v_constants.TAG_FILESYSTEM_TOTAL_SIZE)
    return template_string

def add_used_size(os_install):
    template_string = ""
    template_string += open_tag(p2v_constants.TAG_FILESYSTEM_USED_SIZE,  os_install[p2v_constants.FS_USED_SIZE])
    template_string += close_tag( p2v_constants.TAG_FILESYSTEM_USED_SIZE)
    return template_string

def add_filesystem(os_install):
    template_string = ""
    os_root_device = os_install[p2v_constants.DEV_NAME]
    dev_attrs = os_install[p2v_constants.DEV_ATTRS]
    fs_used_size = os_install[p2v_constants.FS_USED_SIZE]
    template_string += open_tag(p2v_constants.TAG_FILESYSTEM)
    template_string += add_uri(os_install)
    template_string += add_function(os_install)
    template_string += add_type(os_install)
    template_string += add_vbd(os_install)
    template_string += add_md5sum(os_install)
    template_string += add_total_size(os_install)
    template_string += add_used_size(os_install)
    template_string += close_tag(p2v_constants.TAG_FILESYSTEM)
    return template_string
         
def write_template(os_install):
    template_string = ""
    
    template_string += open_tag(p2v_constants.TAG_XGT)
    template_string += add_xgt_version()
    template_string += add_xgt_type()
    template_string += add_pp2vp(os_install)
    template_string += add_name(os_install)
    template_string += add_rootfs(os_install)
    template_string += add_distrib(os_install)
    template_string += add_distrib_version(os_install)
    template_string += add_mem_info(os_install)
    template_string += add_cpu_count(os_install)
    template_string += add_description(os_install)
    template_string += add_filesystem(os_install)
    template_string += close_tag(p2v_constants.TAG_XGT)
    
    template_dir= os_install[p2v_constants.XEN_TAR_DIRNAME]
    template_filename = "template.dat"
    template_file = os.path.join(template_dir, template_filename)
    #store the template file name in the os_install, so we can use it when creating the xgt
    os_install[p2v_constants.XEN_TEMPLATE_FILENAME] = template_filename
    
    if os.path.exists(template_file):
        p2v_utils.trace_message("template file already exists. overwriting");
        os.unlink(template_file)
    
    f = open(template_file, "w")
    f.write(template_string + '\n')
    f.close()
    
    p2v_utils.trace_message("template  = %s\n" % template_string)
    return

def create_xgt(os_install):
    xgt_create_dir = os_install[p2v_constants.XEN_TAR_DIRNAME]
    template_filename =  os_install[p2v_constants.XEN_TEMPLATE_FILENAME]
    tar_filename = os_install[p2v_constants.XEN_TAR_FILENAME]
    
    xgt_filename = tar_filename.replace('.tar.bz2', '.xgt')
    
    assert (os.path.exists(os.path.join(xgt_create_dir, template_filename)))
    assert (os.path.exists(os.path.join(xgt_create_dir, tar_filename)))
    
    findroot.create_xgt(xgt_create_dir, xgt_filename, template_filename, tar_filename)
    
    #and delete the tar and template files
    os.unlink(os.path.join(xgt_create_dir, template_filename))
    os.unlink(os.path.join(xgt_create_dir, tar_filename))
    
    
    
#stolen from packaging.py
def ejectCD():
    if not os.path.exists("/tmp/cdmnt"):
        os.mkdir("/tmp/cdmnt")

    device = None
    for dev in ['hda', 'hdb', 'hdc', 'scd1', 'scd2',
                'sr0', 'sr1', 'sr2', 'cciss/c0d0p0',
                'cciss/c0d1p0', 'sda', 'sdb']:
        device_path = "/dev/%s" % dev
        if os.path.exists(device_path):
            try:
                util.mount(device_path, '/tmp/cdmnt', ['ro'], 'iso9660')
                if os.path.isfile('/tmp/cdmnt/REVISION'):
                    device = device_path
                    # (leaving the mount there)
                    break
            except util.MountFailureException:
                # clearly it wasn't that device...
                pass
            else:
                if os.path.ismount('/tmp/cdmnt'):
                    util.umount('/tmp/cdmnt')

    if os.path.exists('/usr/bin/eject') and device != None:
        findroot.run_command('/usr/bin/eject %s' % device)
