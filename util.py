# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Utilty functions for the clean installer
#
# written by Andrew Peace

import os
import os.path
import xelogging
import commands
import subprocess
import urllib2
import shutil
import re
import datetime
import random
import string
import tempfile

random.seed()

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

###
# shell

def runCmd(command, with_output = False):
    (rv, output) = commands.getstatusoutput(command)
    l = "ran %s; rc %d" % (command, rv)
    if output:
        l += "; output follows:\n" + output
    xelogging.log(l)
    if with_output:
        return rv, output
    else:
        return rv

def runCmd2(command, with_stdout = False, with_stderr = False):
    cmd = subprocess.Popen(command,
                           stdout = subprocess.PIPE,
                           stderr = subprocess.PIPE)
    rv = cmd.wait()

    out = ""
    err = ""

    nextout = cmd.stdout.read()
    while nextout:
        out += nextout
        nextout = cmd.stdout.read()

    nexterr = cmd.stderr.read()
    while nexterr:
        err += nexterr
        nexterr = cmd.stderr.read()

    output = "STANDARD OUT:\n" + out + \
             "STANDARD ERR:\n" + err
    
    l = "ran %s; rc %d" % (str(command), rv)
    if out:
        l += "\nSTANDARD OUT:\n" + out
    if err:
        l += "\nSTANDARD ERROR:\n" + err
    xelogging.log(l)
    if (not with_stdout) and (not with_stderr):
        return rv
    elif with_stdout and with_stderr:
        return rv, out, err
    elif with_stdout:
        return rv, out
    else:
        return rv, err

###
# mounting/unmounting

class MountFailureException(Exception):
    pass

def mount(dev, mountpoint, options = None, fstype = None):
    xelogging.log("Mounting %s to %s, options = %s, fstype = %s" % (dev, mountpoint, options, fstype))

    cmd = ['/bin/mount']
    if options:
        assert type(options) == list

    if fstype:
        cmd.append('-t')
        cmd.append(fstype)

    if options:
        cmd.append("-o")
        cmd.append(",".join(options))

    cmd.append(dev)
    cmd.append(mountpoint)

    xelogging.log("Mount command is %s" % str(cmd))
    rc, out, err = runCmd2(cmd, with_stdout=True, with_stderr=True)
    if rc != 0:
        raise MountFailureException, "out: '%s' err: '%s'" % (out, err)

def bindMount(source, mountpoint):
    xelogging.log("Bind mounting %s to %s" % (source, mountpoint))
    
    cmd = [ '/bin/mount', '--bind', source, mountpoint]
    rc = subprocess.Popen(cmd, stdout = subprocess.PIPE,
                          stderr = subprocess.PIPE).wait()
    if rc != 0:
        raise MountFailureException()

def umount(mountpoint, force = False):
    xelogging.log("Unmounting %s (force = %s)" % (mountpoint, force))

    cmd = ['/bin/umount']
    if force:
        cmd.append('-f')
    cmd.append(mountpoint)

    rc = runCmd2(cmd)
    return rc

def parseTime(timestr):
    match = re.match('(\d+)-(\d+)-(\d+) (\d+):(\d+):(\d+)', timestr)
    (year, month, day, hour, minute, second) = map(lambda x: int(x), match.groups())
    time = datetime.datetime(year, month, day, hour, minute, second)

    return time

###
# fetching of remote files

class InvalidSource(Exception):
    pass

# source may be
#  http://blah
#  ftp://blah
#  file://blah
#  nfs://server:/path/blah
def fetchFile(source, dest):
    cleanup_dirs = []

    try:
        # if it's NFS, then mount the NFS server then treat like
        # file://:
        if source[:4] == 'nfs:':
            # work out the components:
            [_, server, path] = source.split(':')
            if server[:2] != '//':
                raise InvalidSource("Did not start {ftp,http,file,nfs}://")
            server = server[2:]
            dirpart = os.path.dirname(path)
            if dirpart[0] != '/':
                raise InvalidSource("Directory part of NFS path was not an absolute path.")
            filepart = os.path.basename(path)
            xelogging.log("Split nfs path into server: %s, directory: %s, file: %s." % (server, dirpart, filepart))

            # make a mountpoint:
            mntpoint = tempfile.mkdtemp(dir = '/tmp', prefix = 'fetchfile-nfs-')
            mount('%s:%s' % (server, dirpart), mntpoint, fstype = "nfs", options = ['ro'])
            cleanup_dirs.append(mntpoint)
            source = 'file://%s/%s' % (mntpoint, filepart)

        if source[:5] == 'http:' or \
               source[:5] == 'file:' or \
               source[:4] == 'ftp:':
            # This something that can be fetched using urllib2:
            fd = urllib2.urlopen(source)
            fd_dest = open(dest, 'w')
            shutil.copyfileobj(fd, fd_dest)
            fd_dest.close()
            fd.close()
        else:
            raise InvalidSource("Unknown source type.")

    finally:
        for d in cleanup_dirs:
            umount(d)
            os.rmdir(d)

def getUUID():
    rc, out = runCmd('uuidgen', with_output = True)
    assert rc == 0

    return out.strip()

def mkRandomHostname():
    """ Generate a random hostname of the form xenserver-AAAAAAAA """
    s = "".join([random.choice(string.ascii_lowercase) for x in range(8)])
    return "xenserver-%s" % s

def splitNetloc(netloc):
    hostname = netloc
    username = None
    password = None
        
    if "@" in netloc:
        userinfo = netloc.split("@", 1)[0]
        hostname = netloc.split("@", 1)[1]
        if ":" in userinfo:
            (username, password) = userinfo.split(":")
        else:
            username = userinfo
    if ":" in hostname:
        hostname = hostname.split(":", 1)[0]
        
    return (hostname, username, password)

def splitArgs(argsIn):
    """ Split argument array into dictionary

    [ '--alpha', '--beta=42' ]

    becomes

    { '--alpha': None, '--beta': '42' }"""
    argsOut = {}
    for arg in argsIn:
        eq = arg.find('=')
        if eq == -1:
            argsOut[arg] = None
        else:
            argsOut[arg[:eq]] = arg[eq+1:]
    return argsOut    

def readKeyValueFile(filename, allowed_keys = None, strip_quotes = True):
    """ Reads a KEY=Value style file (e.g. xensource-inventory). Returns a 
    dictionary of key/values in the file.  Not designed for use with large files
    as the file is read entirely into memory."""

    f = open(filename, "r")
    lines = [x.strip("\n") for x in f.readlines()]
    f.close()

    # remove lines that do not contain allowed keys
    if allowed_keys:
        lines = filter(lambda x: True in [x.startswith(y) for y in allowed_keys],
                       lines)
    
    defs = [ (l[:l.find("=")], l[(l.find("=") + 1):]) for l in lines ]

    if strip_quotes:
        def quotestrip(x):
            return x.strip("'")
        defs = [ (a, quotestrip(b)) for (a,b) in defs ]

    return dict(defs)
