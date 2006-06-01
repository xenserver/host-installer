###
# XEN CLEAN INSTALLER
# Packaging functions
#
# written by Andrew Peace
# Copyright XenSource Inc., 2006

import os.path
import urllib2
import popen2
import threading
import md5

import xelogging
import util
import constants
import version

class NoSuchPackage(Exception):
    pass

class ErrorInstallingPackage(Exception):
    pass

class MediaNotFound(Exception):
    def __init__(self, medianame):
        Exception.__init__("Setup could not find the media labelled %s.  Please ensure it is loaded and that the drive is closed as appropriate.  If the media is installed and you still see this error, please refer to your user guide or XenSource technical support." % \
                           medianame)

class BadSourceAddress(Exception):
    pass

###
# INSTALL METHODS

class InstallMethod:
    def __init__(self, *args):
        pass

    def openPackage(self, package):
        pass

    def getRecordedMd5(self, package):
        pass

    def checkPackageExistance(self, package):
        pass

    def finished(self, eject = True):
        pass

class HTTPInstallMethod(InstallMethod):
    def __init__(self, *args):
        self.baseURL = args[0].rstrip('/')

        if not self.baseURL.startswith('http://') and \
           not self.baseURL.startswith('https://') and \
           not self.baseURL.startswith('ftp://'):
            self.baseURL = "http://" + self.baseURL

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
            util.mount(self.nfsPath, '/tmp/nfs-source', fstype = 'nfs')
        except util.MountFailureException:
            raise BadSourceAddress()

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

    def finished(self, eject = False):
        assert os.path.ismount('/tmp/nfs-source')
        util.umount('/tmp/nfs-source')

class LocalInstallMethod(InstallMethod):
    def __init__(self, *args):
        if not os.path.exists("/tmp/cdmnt"):
            os.mkdir("/tmp/cdmnt")

        device = None ; self.device = None
        for dev in ['hda', 'hdb', 'hdc', 'hdd', 'scd0', 'scd1',
                    'scd2', 'sr0', 'sr1', 'sr2', 'cciss/c0d0p0',
                    'cciss/c0d1p0', 'cciss/c0d0', 'cciss/c0d1',
                    'sda', 'sdb', 'sdc', 'sdd']:
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
            raise MediaNotFound("%s Install CD" % version.PRODUCT_BRAND)
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

    def finished(self, eject = True):
        if os.path.ismount('/tmp/cdmnt'):
            util.umount('/tmp/cdmnt')
            if os.path.exists('/usr/bin/eject') and self.device and \
                   eject:
                util.runCmd('/usr/bin/eject %s' % self.device)


###
# PACKAGING

def installPackage(packagename, method, dest):
    def logInput(infile, prefix):
        try:
            while 1:
                line = infile.readline().rstrip('\n')
                if line == "":
                    break
                else:
                    xelogging.log("%s: %s" % (prefix, line))
        except Exception:
            # this thread is only responsible for logging output,
            # and we did the best we could:
            pass

    package = method.openPackage(packagename)

    xelogging.log("Starting installation of package %s" % packagename)

    pipe = popen2.Popen3('tar -C %s -xjf - 2>&1' % dest, bufsize = 1024 * 1024)

    thread = threading.Thread(target = logInput, args = (pipe.fromchild, 'Tar output: '))
    thread.start()
    data = ''
    while True:
        data = package.read()
        if data == '':
            break
        else:
            pipe.tochild.write(data)

    pipe.tochild.flush()
    pipe.tochild.close()

    if pipe.wait() != 0:
        raise ErrorInstallingPackage, "The decompressor returned an error processing package %s" % packagename
    else:
        xelogging.log("Package %s successfully installed." % packagename)

    pipe.fromchild.close()
    thread.join()

    package.close()

def md5CheckPackage(packagename, method):
    try:
        package = method.openPackage(packagename)
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
        recordedsum = method.getRecordedMd5(packagename)
    except:
        return False
    
    xelogging.log("Computed md5 as: %s" % newsum)
    xelogging.log("Excpected md5:   %s" % recordedsum)

    return (recordedsum == newsum)

# Returns a list of problematic packages
def quickSourceVerification(source):
    problems = []
    for package in constants.packages:
        if not source.checkPackageExistance(package):
            problems.append(package)

    return problems

# Returns a list of problematic packages
def md5SourceVerification(source):
    problems = []
    for package in constants.packages:
        if not md5CheckPackage(package, source):
            problems.append(package)

    return problems
