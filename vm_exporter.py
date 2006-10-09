#!/usr/bin/env python
# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this
# copyrighted material is governed by and subject to terms and conditions
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or
# trademarks of XenSource Inc. in the United States and/or other countries.

# Utility functions to
# (i) list VMs on a burbank host
# (ii) extract VM metadata and convert it into zurich format
# (iii) control a VM transfer (b2 slave) process

import os
import sys
import commands
import glob
import signal
import tempfile

# add fallback path for non-native python path installs if needed
sys.path.append('/usr/lib/python')
sys.path.append('/usr/lib64/python')
from xen.xend import sxp

# Path where the VM state is found:
VM_PATH="/tmp/mnt-vmstate"
# Path to the 'b2' binary
B2_PATH="/usr/sbin/b2"

XGT_EXPORT_VERSION="4"
CHUNKSIZE=1000000000l

# Path of the domain's vm.dat
def vm_dat(uuid):
    global VM_PATH
    return VM_PATH + "/" + uuid + "/vm.dat"

# Looks in the kernel cache for vmlinuz.*
def vm_kernel_filename(uuid):
    global VM_PATH
    all = os.listdir(VM_PATH + "/" + uuid)
    for x in all:
        if x.startswith("vmlinuz"): return x

# Looks in the kernel cache for initrd.*
def vm_kernel_initrd(uuid):
    global VM_PATH
    all = os.listdir(VM_PATH + "/" + uuid)
    for x in all:
        if x.startswith("initrd"): return x

# Path of the xend domain config file
def vm_config(uuid):
    global VM_PATH
    return VM_PATH + "/" + uuid + "/config"

def compute_total_steps(vm):
    steps = 0
    for x in sxp.children(vm, "vbd"):
        total_size = long(sxp.child_value(x, "size")) * 1024l # bytes
        steps = steps + (total_size + CHUNKSIZE - 1l) / CHUNKSIZE
    return steps

# Notes:
# 1. The only reliable way of finding out what should be in the kernel commandline
#    is to look at the xend domain config files, which happen to be lying around
# 2. We cannot add symlinks xenkernel and xeninitrd here because the CD lacks kpartx
# 3. We transmit the name of the kernel and initrd to the XE server, where prepare-guest
#    can insert the symlinks
# 4. We set the distrib to "upgrade" and distrib_version to "3.0.0" to activate our
#    custom prepare-guest plugin

# Takes a B2-format vm.dat and returns a Z1-format exported template.dat
# merging in kernel commandline info from the domain config file
def make_exported_template(vm):
    def escape(x): return repr(str(x))

    def option(name, x):
        if x:
            return "(" + name + " " + (escape(x)) + ")"
        return ""

    def table(t):
        result = ""
        for kv in t:
            result = result + (option(kv[0], kv[1]))
        return result

    uuid = sxp.child_value(vm, "uuid")
    t = []
    t.append(["name", sxp.child_value(vm, "name")])
    t.append(["uuid", uuid])
    t.append(["description", sxp.child_value(vm, "description")])    
    # mark this as an 'upgrade' to activate our special prepare-guest
    # plugin which will create the kernel symlinks
    t.append(["distrib", "upgrade" ])
    t.append(["distrib_version", "3.0.0" ])
    t.append(["os", "unknown" ])
    t.append(["pp2vp", sxp.child_value(vm, "pp2vp")])
    t.append(["vcpus", sxp.child_value(vm, "vcpus")])
    # WTF is mem_max?
    #t.append(["mem_max", sxp.child_value(vm, "mem_max")])
    t.append(["mem_set", sxp.child_value(vm, "mem_set")])
    t.append(["auto_poweron", sxp.child_value(vm, "auto_poweron")])
    hvm = sxp.child_value(vm, "is_hvm")
    if hvm == None:
        hvm = "false"
    t.append(["is_hvm", hvm])
    template = table(t)

    def kernel():
        vmlinuz = vm_kernel_filename(uuid)
        initrd = vm_kernel_initrd(uuid)
        args = read_root_from_config(uuid)
	if args == None: raise RuntimeError, "no args"	

        t = []
        # no kernel-type installed_version ramdisk
        t.append(["kernel_path", vmlinuz])
        t.append(["initrd-path", initrd])
        t.append(["kernel_args", args])
        return table(t)

    def vif(x):
        t = []
        for key in [ "name", "mac" ]:
            t.append([key, sxp.child_value(x, key)])
        return table(t)

    # Convert an xs_vbd into an xs_filesystem
    def fs(x):
        t = []
        t.append(["type", "gzipped-chunks"])
        if not(sxp.child(x, "size")):
            raise "Disk has missing size"
        total_size = int(sxp.child_value(x, "size")) * 1024
        t.append(["total_size", total_size])
        if sxp.child(x, "min_size"):
            t.append(["used_size", int(sxp.child_value(x, "min_size")) * 1024])
        else:
            t.append(["used_size", total_size])
        t.append(["vbd", sxp.child_value(x, "name")])
        t.append(["function", sxp.child_value(x, "function")])
        return table(t)

    # Add the kernel
    if hvm <> "true":
    	template = template + "(kernel " + kernel() + ")"
    # Add each filesystem
    all = sxp.children(vm, "vbd")
    for x in all:
        template = template + "(filesystem " + fs(x) + ")"
    # Add each VIF
    all = sxp.children(vm, "vif")
    for x in all:
        template = template + "(vif " + vif(x) + ")"

    return "(" + template + ")"

# Read the xend domain config file - it's the only place the kernel's commandline
# in particular the root=xxx bit is stored. (Apart from xenstore, which we cannot
# easily read from the CD)
def read_root_from_config(uuid):
    filename = vm_config(uuid)
    config = load_sxp(filename)
    # Looking for: (image (linux (kernel ...) (ramdisk ...) (root ...))))
    img = sxp.children(config, "image")
    root = None
    if img <> []:
        linux = sxp.children(img[0], "linux")
        if linux <> []:
            root = sxp.children(linux[0], "root")
	    if root <> []: root = "root=" + root[0][1]
    if root == None:
        print "WARNING: failed to discover root from domain config"
    return root
        
    
def load_sxp(filename):
    parser = sxp.Parser()
    f = open(filename)
    try:
        while True:
            buf = f.read(1024)
            parser.input(buf)
            if len(buf) == 0:
                break
        template = parser.get_val()
        return template
    finally:
        if f: f.close()

def save_sxp(s, filename):
    f = open(filename, 'w')
    sxp.show(s, f)
    f.close()

def list_vm_uuids():
    global VM_PATH
    uuids = []
    for x in os.listdir(VM_PATH):
        if x <> "lost+found":
            uuids.append(x)
    return uuids

def get_vm_name(uuid):
    s = load_sxp(vm_dat(uuid))
    name = sxp.child_value(s, "name")
    if name:
        return name
    else:
        return "Unknown"

def do_vm_upload(vm, hostname, username, password, progress_function, log_function):
    global VM_PATH, B2_PATH
    # make the exported template
    t = make_exported_template(vm)
    # save it to a temporary file
    tf = tempfile.mkstemp()
    os.write(tf[0], t)
    os.close(tf[0])
    log_function("Written new metadata file: " + tf[1])
    
    template_filename = tf[1]
    # XXX: missing username
    cmd_line = B2_PATH + " " + template_filename + " " + hostname + " " + password
    # out becomes both stdout and stderr
    out = os.popen4(cmd_line, 'r')[1]
    # interesting lines of output have this prefix:
    debug_prefix = "DEBUG: "
    error_prefix = "ERROR: "
    def has_prefix(prefix, line):
        return len(line) >= len(prefix) and line[0:len(prefix)] == prefix

    result = 1
    while 1:
        line = out.readline()
        if not line: break
        line = line.strip()
        # Allow caller to see (and log) all the crap ("it's the only way to be sure")
        if log_function:
            log_function(line)

        if has_prefix(debug_prefix, line):
            if has_prefix(debug_prefix + "CHUNK COMPLETE", line):
                if progress_function:
                    progress_function()
        elif has_prefix(error_prefix, line):
            # Record the failure
            raise RuntimeError, line
            result = 0
    out.close()

    # presumably we don't really need to clear this up?
    #os.unlink(tf[1])
    return result


total_steps = 0
completed_steps = 0

# Called whenever one of the steps has been completed to calculate
# our progress so far.
def completed_step(log_fn, progress_fn):
    global total_steps, completed_steps
    completed_steps = completed_steps + 1
    percent = int(float(completed_steps) / float(total_steps) * 100.0)
    if log_fn <> None:
        log_fn("Completed steps = " + str(completed_steps) +
               "; Progress = " + str(percent))
    if progress_fn <> None:
        progress_fn(percent)

# Do actual uploading work, called both from the __main__ routine
# at the bottom and through AndyP's API
def upload_vms(log_fn, uuids, mnt, hn, uname, pw, progress):
    global VM_PATH, total_steps, completed_steps
    VM_PATH = mnt
 
    log_fn("Starting export of VMs")
    log_fn("Input: %s" % str((mnt, hn, uname, pw, progress)))

    total_steps = 0
    for x in uuids:
        vm = load_sxp(vm_dat(x))
        total_steps = total_steps + compute_total_steps(vm)
    completed_steps = 0

    def log(x):
        log_fn("Exporter> " + x)
    def prog():
        completed_step(log_fn, progress)

    for x in uuids:
        vm = load_sxp(vm_dat(x))
        if not(do_vm_upload(vm, hn, uname, pw, prog, log)):
            raise RuntimeError, "VM upload failed"

    log_fn("Export complete.")    

# AndyP's API function:
# mnt: path to where vmstate is mounted
# hn: hostname of destination host
# uname: username on destination host
# pw: password for uname
# prgress: callback function: int -> unit.
def run(mnt, hn, uname, pw, progress):
    import xelogging
    uuids = list_vm_uuids()
    return upload_vms(xelogging.log, uuids, mnt, hn, uname, pw, progress)

# Also runs as a standalone program for debugging
if __name__ == "__main__":
    from optparse import OptionParser
    opt = OptionParser("usage: vm_exporter")
    opt.add_option("-m", "--metadata_dir", help="path on which the metadata is mounted")
    opt.add_option("-t", "--target", help="target host to export VMs to")
    opt.add_option("-u", "--username", help="username on target host")
    opt.add_option("-p", "--password", help="password on target host")
    opt.add_option("-b", "--burbank_slave",
                   default=B2_PATH,
                   help="filename of the burbank VM export slave binary")
    opt.add_option("-i", "--uuid", default=None, help="UUID of single VM to upload")
    (options, args) = opt.parse_args()
    if options.burbank_slave:
        B2_PATH = options.burbank_slave
    if options.metadata_dir:
        VM_PATH = options.metadata_dir
    uuid = options.uuid
    hn = options.target
    uname = options.username
    pw = options.password
    
    if hn == None or uname == None or pw == None:
        raise "Need options: --target --username --password"

    print "VM export tool running in debug mode"
    print "Metadata dir: " + VM_PATH
    print "Burbank export slave path: " + B2_PATH
    if uuid == None:
        print "Intending to export all VMs"
    else:
        print "Intending to export only the VM with uuid: " + uuid
        
    print "All VMs found:"
    steps = 0
    uuids = list_vm_uuids()
    for x in uuids:
        print x, ": ", get_vm_name(x)
        print " " * len(x), vm_kernel_filename(x)
        print " " * len(x), vm_kernel_initrd(x)        
        steps = steps + compute_total_steps(load_sxp(vm_dat(x)))
    print "Total steps (disk chunks) involved in export of everything: ", steps

    def log(x):
        print "log: " + x
    def progress(amount):
        log("New progress: " + str(amount))
    if uuid == None:
        print "Starting upload of all VMs"
        upload_vms(log, uuids, VM_PATH, hn, uname, pw, progress)
    else:
        if uuid in uuids:
            print "Uploading VM with uuid: " + uuid
            upload_vms(log, [ uuid ], VM_PATH, hn, uname, pw, progress)            
        else:
            print "ERROR: couldn't find VM with uuid: " + uuid
