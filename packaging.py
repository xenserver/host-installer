###
# XEN CLEAN INSTALLER
# Packaging functions
#
# written by Andrew Peace
# Copyright XenSource Inc., 2006

import os.path
import urllib2
import popen2

import xelogging
import util

class NoSuchPackage(Exception):
    pass

class MediaNotFound(Exception):
    pass

class BadSourceAddress(Exception):
    pass

###
# INSTALL METHODS

class InstallMethod:
    def __init__(self, *args):
        pass

    def openPackage(self, package):
        pass

    def finished(self):
        pass

class HTTPInstallMethod(InstallMethod):
    def __init__(self, *args):
        self.baseURL = args[0].rstrip('/')

        if not self.baseURL.startswith('http://') or \
           not self.baseURL.startswith('https://') or \
           not self.baseURL.startswith('ftp://'):
            self.baseURL = "http://" + self.baseURL

    def openPackage(self, package):
        xelogging.log("Opening package %s" % package)
        assert self.baseURL != None and self.baseURL != ""
        package_url = "%s/%s.tar.bz2" % (self.baseURL, package)
        return urllib2.urlopen(package_url)

    def finished(self):
        pass

class NFSInstallMethod(InstallMethod):
    def __init__(self, *args):
        self.nfsPath = args[0]

        if ':' not in self.nfsPath:
            raise BadSourceAddress()

        # attempt a mount:
        if not os.path.isdir('/tmp/nfs-source'):
            os.mkdir('/tmp/nfs-source')
        try:
            util.mount(self.nfsPath, '/tmp/nfs-source', fstype = 'nfs')
        except util.MountFailureException:
            raise BadSourceAddress()

    def openPackage(self, package):
        assert os.path.ismount('/tmp/nfs-source')
        return open('/tmp/nfs-source/%s.tar.bz2' % package, 'r')

    def finished(self):
        assert os.path.ismount('/tmp/nfs-source')
        util.umount('/tmp/nfs-source')

class LocalInstallMethod(InstallMethod):
    def __init__(self, *args):
        if not os.path.exists("/tmp/cdmnt"):
            os.mkdir("/tmp/cdmnt")

        device = None ; self.device = None
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

        if not device:
            assert not os.path.ismount('/tmp/cdmnt')
            raise MediaNotFound()
        else:
            assert os.path.ismount('/tmp/cdmnt')
            self.device = device

    def openPackage(self, package):
        assert os.path.ismount('/tmp/cdmnt')
        return open('/tmp/cdmnt/packages/%s.tar.bz2' % package, 'r')

    def finished(self):
        if os.path.ismount('/tmp/cdmnt'):
            util.umount('/tmp/cdmnt')
            if os.path.exists('/usr/bin/eject') and self.device:
                util.runCmd('/usr/bin/eject %s' % self.device)


###
# PACKAGING

def installPackage(packagename, method, dest):
    package = method.openPackage(packagename)

    pipe = popen2.Popen3('tar -C %s -xjf -' % dest, bufsize = 1024 * 1024)
    
    data = ''
    while True:
        data = package.read()
        if data == '':
            break
        pipe.tochild.write(data)

    pipe.tochild.flush()
    
    pipe.tochild.close()
    pipe.fromchild.close()
    assert pipe.wait() == 0
    
    package.close()
