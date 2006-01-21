#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Main script
#
# written by Andrew Peace & Mark Nijmeijer
# Copyright XenSource Inc. 2006

# user-interface stuff:
import p2v_tui
#import generalui
import p2v_uicontroller
import sys
import findroot

# backend
#import backend

ui_package = p2v_tui

def print_results(results):
   for key in results.keys():
         sys.stderr.write("result.key = %s \t\t" % key)
         sys.stderr.write("result.value = %s\n" % results[key])
         
def mount_os_root(os_root_device, dev_attrs):
    return findroot.mount_os_root(os_root_device, dev_attrs)
 
def umount_os_root(mnt):
    return findroot.umount_dev(mnt)

def perform_p2v(os_install, inbox_path):
    os_root_device = os_install[2]
    dev_attrs = os_install[3]
    os_root_mount_point = mount_os_root(os_root_device, dev_attrs)
    findroot.handle_root(os_root_mount_point, os_root_device)
    umount_os_root(os_root_mount_point)
    
def nfs_mount(nfs_mount_path):
    local_mount_path = "/xenpending"
    findroot.run_command("mkdir -p /xenpending")
    findroot.run_command("mount %s %s" % (nfs_mount_path, local_mount_path))
    return local_mount_path

#TODO : validation of nfs_path?         
def nfs_p2v(nfs_host, nfs_path, os_install):
    nfs_mount_path = nfs_host + ":" + nfs_path
    inbox_path = nfs_mount(nfs_mount_path)
    perform_p2v(os_install, inbox_path)
        
def mount_inbox(xe_host):    
    inbox_path = "/inbox"
    fs_mount_path = nfs_mount(xe_host +":" + inbox_path)
    return fs_mount_path

def xe_p2v(xe_host, os_install):
    inbox_path = mount_inbox(xe_host)
    perform_p2v(os_install, inbox_path)
         
def perform_P2V(results):
     os_install = results['osinstall']
     if results['xen-target'] == 'xe':
         sys.stderr.write("we're doing a p2v to XE")
         xe_host = results['xehost']
         xe_p2v(xe_host, os_install)
     elif results['xen-target'] == 'nfs':
         sys.stderr.write("we're doing a p2v to XE")
         nfs_host = results['nfshost']
         nfs_path = results['nfspath']
         nfs_p2v(nfs_host, nfs_path, os_install)

def main():
    ui_package.init_ui()

    results = { 'ui-package': ui_package }

    seq = [ ui_package.welcome_screen,
            ui_package.target_screen,
            ui_package.os_install_screen ]
    rc = p2v_uicontroller.runUISequence(seq, results)
    
    ui_package.end_ui()
    if rc != -1:
        perform_P2V(results)
    else:
        sys.exit(1)
            

#    backend.performStage1Install(results)

    #seq = [ ui_package.get_root_password,
    #        ui_package.determine_basic_network_config,
    #        ui_package.need_manual_hostname,
    #        ui_package.installation_complete ]
    #seq = [ ui_package.installation_complete ]

    #uicontroller.runUISequence(seq, results)
    

    print_results(results)

if __name__ == "__main__":
    main()
2
