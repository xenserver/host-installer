###
# XEN CLEAN INSTALLER
# Utilty functions for the clean installer
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import os
import os.path
import logging
import commands

###
# directory/tree management

def assertDir(dirname):
    # make sure there isn't already a file there:
    assert not (os.path.exists(dirname) and not os.path.isdir(dirname))

    # does the base directory exist?
    if not os.path.isdir(os.path.dirname(dirname)):
        assertDir(os.path.dirname(dirname))

    # does the specified directory exist?
    if not os.path.isdir(dirname):
        os.makedirs(dirname)

def assertDirs(*dirnames):
    for d in dirnames:
        assertDir(d)

def copyFilesFromDir(sourcedir, dest):
    assert os.path.isdir(sourcedir)
    assert os.path.isdir(dest)

    files = os.listdir(sourcedir)
    for f in files:
        assert runCmd("cp -a %s/%s %s/" % (sourcedir, f, dest)) == 0

###
# shell

def runCmd(command):
    (rv, output) = commands.getstatusoutput(command)
    logging.logOutput(command, output)
    return rv

def runCmdWithOutput(command):
    (rv, output) = commands.getstatusoutput(command)
    logging.logOutput(command, output)
    return (rv, output)

###
# mounting/unmounting

class MountFailureException(Exception):
    pass

def mount(dev, mountpoint, options = None, fstype = None):
    cmd = ['/bin/mount']

    if fstype:
        cmd.append('-t')
        cmd.append(fstype)

    if options:
        cmd.append("-o")
        cmd.append(",".join(options))

    cmd.append(dev)
    cmd.append(mountpoint)

    rc = os.spawnv(os.P_WAIT, cmd[0], cmd)
    if rc != 0:
        raise MountFailureException()

def umount(mountpoint):
    assert os.path.ismount(mountpoint)
    os.spawnv(os.P_WAIT, '/bin/umount', ['/bin/umount', mountpoint])
