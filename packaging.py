# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Packaging functions
#
# written by Andrew Peace

import os.path
import urllib2
import popen2
import md5

import xelogging
import util
import constants
import version
import diskutil
from version import *

# the devices the we check if we can find the appropriate media
# in any devices with 'removable' set in /sys:
__static_devices__ = [
    'hda', 'hdb', 'hdc', 'hdd', 'hde', 'hdf',
    'sda', 'sdb', 'sdc', 'sdd', 'sde', 'sdf',
    'scd0', 'scd1', 'scd2', 'scd3', 'scd4',
    'sr0', 'sr1', 'sr2', 'sr3', 'sr4', 'sr5', 'sr6', 'sr7',
    'cciss/c0d0', 'cciss/c0d1'
    ]

class NoSuchPackage(Exception):
    pass

class ErrorInstallingPackage(Exception):
    pass

class MediaNotFound(Exception):
    MEDIA_CDROM = 1
    MEDIA_REMOTE = 2

    TEXT_MEDIA_CDROM = "Setup could not find the media labelled '%s'.  If the media is present and you still see this error, please refer to your user guide or " + COMPANY_NAME_SHORT + " technical support."
    TEXT_MEDIA_REMOTE = "Setup could not access the remote repository '%s'; please check that the address is correct and points to a valid " + PRODUCT_BRAND + " repository.  If the address is correct and you still see this error, please refer to your user guide or " + COMPANY_NAME_SHORT + " technical support."
    def __init__(self, medianame, mediatype):
        self.media_name = medianame
        if mediatype == self.MEDIA_CDROM:
            Exception.__init__(self, self.TEXT_MEDIA_CDROM % medianame)
        elif mediatype == self.MEDIA_REMOTE:
            Exception.__init__(self, self.TEXT_MEDIA_REMOTE % medianame)

class BadSourceAddress(Exception):
    pass

###
# INSTALL METHODS

__package_filename__ = "PACKAGES"

class InstallMethod:
    def __init__(self, *args):
        pass

    def openPackage(self, package):
        assert False

    def getRecordedMd5(self, package):
        assert False

    def checkPackageExistance(self, package):
        assert False

    def getPackageList(self):
        assert False

    def getPackageListFromFile(self, plfile):
        pl = plfile.readlines()
        pl = [x.strip() for x in pl]
        pl = filter(lambda x: x != "", pl)
        return pl

    def installPackage(self, packagename, dest):
        package = self.openPackage(packagename)

        xelogging.log("Starting installation of package %s" % packagename)
        
        pipe = popen2.Popen3('tar -C %s -xjf - &>/dev/null' % dest, bufsize = 1024 * 1024)
    
        data = ''
        while True:
            # read in 10mb chunks so as not to use so much RAM, and to
            # allow decompression to occur in parallel (in the bzip2
            # process).
            data = package.read(10485760)
            if data == '':
                break
            else:
                pipe.tochild.write(data)

        pipe.tochild.flush()
    
        pipe.tochild.close()
        pipe.fromchild.close()

        if pipe.wait() != 0:
            raise ErrorInstallingPackage, "The decompressor returned an error processing package %s" % packagename
    
        package.close()

    def md5CheckPackage(self, packagename):
        try:
            package = self.openPackage(packagename)
        except:
            return False   

        xelogging.log("Starting md5 check of package %s" % packagename)

        m = md5.new()

        date = ''
        while True:
            data = package.read()
            if data == '':
                break
            else:
                m.update(data)

        package.close()

        newsum = m.hexdigest()
        try:
            recordedsum = self.getRecordedMd5(packagename)
        except:
            xelogging.log("Unable to retrieve a recorded MD5 value for %s" % packagename)
            return False
    
        xelogging.log("Computed md5 as: %s" % newsum)
        xelogging.log("Expected md5:   %s" % recordedsum)

        return (recordedsum == newsum)

    def quickSourceVerification(self):
        """Return a list of problematic packages on the source media."""

        problems = []
        packages = self.getPackageList()
        for package in packages:
            if not self.checkPackageExistance(package):
                problems.append(package)

        return problems

    def md5SourceVerification(self):
        """Return a list of problematic packages on the source media."""

        problems = []
        packages = self.getPackageList()
        for package in packages:
            if not self.md5CheckPackage(package):
                problems.append(package)

        return problems

    def finished(self, eject = True):
        pass

class HTTPInstallMethod(InstallMethod):
    def __init__(self, *args):
        self.baseURL = args[0].rstrip('/')

        if not self.baseURL.startswith('http://') and \
           not self.baseURL.startswith('https://') and \
           not self.baseURL.startswith('ftp://'):
            self.baseURL = "http://" + self.baseURL

        # now check that we can access this repo:
        try:
            self.getPackageList()
        except urllib2.URLError, e:
            raise MediaNotFound, ("%s" % self.baseURL, MediaNotFound.MEDIA_REMOTE)

    def openPackage(self, package):
        xelogging.log("Opening package %s" % package)
        assert self.baseURL != None and self.baseURL != ""
        package_url = "%s/%s.tar.bz2" % (self.baseURL, package)
        return urllib2.urlopen(package_url)

    def getRecordedMd5(self, package):
        assert self.baseURL != None and self.baseURL != ""
        md5_url = "%s/%s.md5" % (self.baseURL, package)
        f = urllib2.urlopen(md5_url)
        csum = f.readline().strip()
        f.close()
        return csum

    def checkPackageExistance(self, package):
        assert self.baseURL != None and self.baseURL != ""
        try:
            package_url = "%s/%s.tar.bz2" % (self.baseURL, package)
            p = urllib2.urlopen(package_url)
            p.close()
        except:
            return False
        else:
            return True

    def getPackageList(self):
        assert self.baseURL != None and self.baseURL != ""
        plurl = "%s/%s" % (self.baseURL, __package_filename__)
        plfile = urllib2.urlopen(plurl)
        pl = self.getPackageListFromFile(plfile)
        plfile.close()

        return pl

    def finished(self, eject = False):
        pass

class NFSInstallMethod(InstallMethod):
    def __init__(self, *args):
        self.nfsPath = args[0]

        if ':' not in self.nfsPath:
            xelogging.log("NFS path was '%s', which did not contain a ':' character, which indicates a malformed path." % self.nfsPath)
            raise BadSourceAddress()

        # attempt a mount:
        if not os.path.isdir('/tmp/nfs-source'):
            os.mkdir('/tmp/nfs-source')
        try:
            util.mount(self.nfsPath, '/tmp/nfs-source', fstype = 'nfs', options=['ro'])
        except util.MountFailureException:
            raise MediaNotFound, (self.nfsPath, MediaNotFound.MEDIA_REMOTE)

    def openPackage(self, package):
        assert os.path.ismount('/tmp/nfs-source')
        path = '/tmp/nfs-source/%s.tar.bz2' % package
        xelogging.log("Opening package %s, which is located at %s in our filesystem." % (package, path))
        return open(path, 'r')

    def getRecordedMd5(self, package):
        assert os.path.ismount('/tmp/nfs-source')
        path = '/tmp/nfs-source/%s.md5' % package
        f = open(path, 'r')
        csum = f.readline().strip()
        f.close()
        return csum

    def checkPackageExistance(self, package):
        assert os.path.ismount('/tmp/nfs-source')
        try:
            path = '/tmp/nfs-source/%s.tar.bz2' % package
            p = open(path, 'r')
            p.close()
        except:
            return False
        else:
            return True

    def getPackageList(self):
        assert os.path.ismount("/tmp/nfs-source")
        plpath = "%s/%s" % ('/tmp/nfs-source', __package_filename__)
        plfile = open(plpath, 'r')
        pl = self.getPackageListFromFile(plfile)
        plfile.close()

        return pl
    
    def finished(self, eject = False):
        assert os.path.ismount('/tmp/nfs-source')
        util.umount('/tmp/nfs-source')

class LocalInstallMethod(InstallMethod):
    def __init__(self, *args):
        if not os.path.exists("/tmp/cdmnt"):
            os.mkdir("/tmp/cdmnt")

        device = None ; self.device = None

        devices_to_check = diskutil.getRemovableDeviceList()
        devices_to_check.extend(__static_devices__)
        if 'fd0' in devices_to_check:
            devices_to_check.remove('fd0')

        xelogging.log("Checking for media at the following device nodes in the order listed:")
        xelogging.log(str(devices_to_check))

        for dev in devices_to_check:
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
            xelogging.log("ERROR: Install media not found.")
            assert not os.path.ismount('/tmp/cdmnt')
            raise MediaNotFound, ("%s Install CD" % version.PRODUCT_BRAND, MediaNotFound.MEDIA_CDROM)
        else:
            xelogging.log("Install media found on %s" % device)
            assert os.path.ismount('/tmp/cdmnt')
            self.device = device

    def openPackage(self, package):
        assert os.path.ismount('/tmp/cdmnt')
        if not os.path.exists('/tmp/cdmnt/packages/%s.tar.bz2' % package):
            xelogging.log("Package %s not found on source media (local)" % package)
            raise NoSuchPackage, "Package %s not found on source media" % package
        return open('/tmp/cdmnt/packages/%s.tar.bz2' % package, 'r')

    def getRecordedMd5(self, package):
        assert os.path.ismount('/tmp/cdmnt')
        path = '/tmp/cdmnt/packages/%s.md5' % package
        f = open(path, 'r')
        csum = f.readline().strip()
        f.close()
        return csum

    def checkPackageExistance(self, package):
        assert os.path.ismount('/tmp/cdmnt')
        try:
            path = '/tmp/cdmnt/packages/%s.tar.bz2' % package
            p = open(path, 'r')
            p.close()
        except:
            return False
        else:
            return True

    def getPackageList(self):
        assert os.path.ismount("/tmp/cdmnt")
        plpath = "%s/%s" % ('/tmp/cdmnt/packages', __package_filename__)
        plfile = open(plpath, 'r')
        pl = self.getPackageListFromFile(plfile)
        plfile.close()

        return pl

    def finished(self, eject = True):
        if os.path.ismount('/tmp/cdmnt'):
            util.umount('/tmp/cdmnt')
            if os.path.exists('/usr/bin/eject') and self.device and \
                   eject:
                util.runCmd('/usr/bin/eject %s' % self.device)

InstallMethods = {
    'local' : LocalInstallMethod,
    'url'   : HTTPInstallMethod,
    'nfs'   : NFSInstallMethod,
    }
