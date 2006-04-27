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

    # does the specified directory exist?
    if not os.path.isdir(dirname):
        os.makedirs(dirname)

def assertDirs(*dirnames):
    for d in dirnames:
        assertDir(d)
        
def copyFile(source, dest):
    assert os.path.isfile(source)
    assert os.path.isdir(dest)
    
    assert runCmd("cp -f %s %s/" % (source, dest)) == 0

def copyFilesFromDir(sourcedir, dest):
    assert os.path.isdir(sourcedir)
    assert os.path.isdir(dest)

    files = os.listdir(sourcedir)
    for f in files:
        assert runCmd("cp -a %s/%s %s/" % (sourcedir, f, dest)) == 0

def rmtree(path):
    assert os.path.exists(path)
    if not os.path.isdir(path):
        os.unlink(path)
    else:
        for f in os.listdir(path):
            rmtree(os.path.join(path, f))
        os.rmdir(path)

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

def bindMount(dir, mountpoint):
    cmd = [ '/bin/mount', '--bind', dir, mountpoint]
    rc = os.spwanv(os.P_WAIT, cmd[0], cmd)
    if rc != 0:
        raise MountFailureException()

def umount(mountpoint, force = False):
    if not force:
        assert os.path.ismount(mountpoint)
    elif not os.path.ismount(mountpoint):
        return
        
    os.spawnv(os.P_WAIT, '/bin/umount', ['/bin/umount', mountpoint])
