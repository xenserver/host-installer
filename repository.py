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

import os
import md5
import tempfile
import urlparse
import urllib2
import ftplib
import popen2
import re

import xelogging
import diskutil
import hardware
import version
import util
import product

class NoRepository(Exception):
    pass

class UnknownPackageType(Exception):
    pass

class ErrorInstallingPackage(Exception):
    pass

class Repository:
    """ Represents a XenSource repository containing packages and associated
    meta data. """
    REPOSITORY_FILENAME = "XS-REPOSITORY"
    PKGDATA_FILENAME = "XS-PACKAGES"

    def __init__(self, accessor, base = ""):
        self._accessor = accessor
        self._base = base
        self._product_brand = None
        self._product_version = None

        accessor.start()

        try:
            repofile = accessor.openAddress(self.path(self.REPOSITORY_FILENAME))
        except Exception, e:
            raise NoRepository, e
        self._parse_repofile(repofile)
        repofile.close()

        try:
            pkgfile = accessor.openAddress(self.path(self.PKGDATA_FILENAME))
        except Exception, e:
            raise NoRepository, e
        self._parse_packages(pkgfile)
        repofile.close()

        accessor.finish()

    def isRepo(cls, accessor, base):
        """ Return whether there is a repository at base address 'base' accessible
        using accessor."""
        return False not in [ accessor.access(accessor.pathjoin(base, f)) for f in [cls.REPOSITORY_FILENAME, cls.PKGDATA_FILENAME] ]
    isRepo = classmethod(isRepo)

    def _parse_repofile(self, repofile):
        """ Parse repository data -- get repository identifier and name. """
        lines = [x.strip() for x in repofile.readlines()]
        self._identifier = lines[0]
        self._name = lines[1]
        if len(lines) >= 4:
            self._product_brand = lines[2]
            try:
                self._product_version = product.Version.from_string(lines[3])
            except:
                self._product_version = None
        else:
            self._product_brand = None
            self._product_version = None

    def compatible_with(self, brand, version):
        return self._product_brand in [brand, None] and \
               self._product_version in [version, None]

    def name(self):
        return self._name

    def identifier(self):
        return self._identifier

    def path(self, name):
        return self._accessor.pathjoin(self._base, name)

    def _parse_packages(self, pkgfile):
        pkgtype_mapping = {
            'tbz2' : BzippedPackage,
            'driver' : DriverPackage,
            'firmware' : FirmwarePackage,
            }
        
        lines = pkgfile.readlines()
        self._packages = []
        for line in lines:
            pkgdata_raw = line.strip().split(" ")
            (_name, _size, _md5sum, _type) = pkgdata_raw[:4]
            if pkgtype_mapping.has_key(_type):
                pkg = pkgtype_mapping[_type](self, _name, _size, _md5sum, *pkgdata_raw[4:])
                pkg.type = _type
            else:
                raise UnknownPackageType, _type

            self._packages.append(pkg)

    def check(self, progress = lambda x: ()):
        """ Return a list of problematic packages. """
        def pkg_progress(start, end):
            def progress_fn(x):
                progress(start + ((x * (end - start)) / 100))
            return progress_fn

        self._accessor.start()

        try:
            problems = []
            total_size = reduce(lambda x,y: x + y,
                                [ p.size for p in self._packages ])
            total_progress = 0
            for p in self._packages:
                start = (total_progress * 100) / total_size
                end = ((total_progress + p.size) * 100) / total_size
                if not p.check(False, pkg_progress(start, end)):
                    problems.append(p)
                total_progress += p.size
        finally:
            self._accessor.finish()
        return problems

    def copyTo(self, destination):
        util.assertDir(destination)

        # write the XS-REPOSITORY file:
        xsrep_fd = open(os.path.join(destination, 'XS-REPOSITORY'), 'w')
        xsrep_fd.write(self.identifier() + '\n')
        xsrep_fd.write(self.name() + '\n')
        xsrep_fd.close()

        # copy the packages and write an XS-PACAKGES file:
        xspkg_fd = open(os.path.join(destination, 'XS-PACKAGES'), 'w')
        for pkg in self:
            repo_dir = os.path.dirname(pkg.repository_filename)
            target_dir = os.path.join(destination, repo_dir)
            util.assertDir(target_dir)
            xspkg_fd.write(pkg.pkgLine() + '\n')

            # pkg.copy will use the full path for us, we just have to make sure
            # the appropriate directory exists before using it (c.f. the
            # the assertDir above).
            pkg.copy(destination)
        xspkg_fd.close()

    def accessor(self):
        return self._accessor

    def __iter__(self):
        return self._packages.__iter__()

class Package:
    def copy(self, destination):
        """ Writes the package to destination with the same
        name that it has in the repository.  Saves the user of the
        class having to know about the repository_filename attribute. """
        return self.write(os.path.join(destination, self.repository_filename))
       
    def write(self, destination):
        """ Write package to 'destination'. """
        xelogging.log("Writing %s to %s" % (str(self), destination))
        pkgpath = self.repository.path(self.repository_filename)
        package = self.repository.accessor().openAddress(pkgpath)

        xelogging.log("Writing file %s" % destination)
        dest_fd = open(destination, 'w')
            
        data = ""
        while True:
            data = package.read(10485760)
            if data == '':
                break
            else:
                dest_fd.write(data)

        dest_fd.close()
        package.close()

class DriverPackage(Package):
    def __init__(self, repository, name, size, md5sum, src, dest):
        (
            self.repository,
            self.name,
            self.size,
            self.md5sum,
            self.repository_filename,
            self.destination,
        ) = ( repository, name, long(size), md5sum, src, dest )

        self.destination = self.destination.lstrip('/')
        self.destination = self.destination.replace("${KERNEL_VERSION}", version.KERNEL_VERSION)

    def __repr__(self):
        return "<DriverPackage: %s>" % self.name

    def pkgLine(self):
        return "%s %d %s driver %s %s" % \
               (self.name, self.size, self.md5sum, self.repository_filename,
                self.destination)

    def install(self, base, progress = lambda x: ()):
        self.write(os.path.join(base, self.destination))

    def check(self, fast = False, progress = lambda x: ()):
        return self.repository.accessor().access(self.repository_filename)
    
    def load(self):
        # Coyp driver to a temporary location:
        util.assertDir('/tmp/drivers')
        temploc = os.path.join('/tmp/drivers', self.repository_filename)
        self.write(temploc)

        # insmod the driver:
        rc = hardware.modprobe_file(temploc)

        # Remove the driver from the temporary location:
        os.unlink(temploc)

        return rc

class FirmwarePackage(Package):
    def __init__(self, repository, name, size, md5sum, src):
        (
            self.repository,
            self.name,
            self.size,
            self.md5sum,
            self.repository_filename,
        ) = ( repository, name, long(size), md5sum, src, )
        self.destination = 'lib/firmware/%s' % os.path.basename(src)

    def __repr__(self):
        return "<FirmwarePackage: %s>" % self.name

    def pkgLine(self):
        return "%s %d %s firmware %s" % \
               (self.name, self.size, self.md5sum, self.repository_filename)

    def provision(self):
        # write to /lib/firmware for immediate access:
        self.write(os.path.join('/', self.destination))

    def install(self, base, progress = lambda x: ()):
        self.write(os.path.join(base, self.destination))

    def check(self, fast = False, progress = lambda x: ()):
        return self.repository.accessor().access(self.repository_filename)

class BzippedPackage(Package):
    def __init__(self, repository, name, size, md5sum, required, src, dest):
        (
            self.repository,
            self.name,
            self.size,
            self.md5sum,
            self.required,
            self.repository_filename,
            self.destination
        ) = ( repository, name, long(size), md5sum, required == 'required', src, dest )

        self.destination = self.destination.lstrip('/')

    def install(self, base, progress = lambda x: ()):
        """ Install package to base.  Progress function takes values from 0
        to 100. """
        pkgpath = self.repository.path(self.repository_filename)
        package = self.repository.accessor().openAddress(pkgpath)

        xelogging.log("Starting installation of package %s" % self.name)
        
        pipe = popen2.Popen3('tar -C %s -xjf - &>/dev/null' % os.path.join(base, self.destination), bufsize = 1024 * 1024)
    
        data = ''
        current_progress = 0
        while True:
            # read in 10mb chunks so as not to use so much RAM, and to
            # allow decompression to occur in parallel (in the bzip2
            # process).
            data = package.read(10485760)
            if data == '':
                break
            else:
                pipe.tochild.write(data)
            current_progress += len(data)
            progress(current_progress / 100)

        pipe.tochild.flush()
    
        pipe.tochild.close()
        pipe.fromchild.close()
        rc = pipe.wait()
        if rc != 0:
            desc = 'returned [%d]' % rc
            if os.WIFEXITED(rc):
                desc = 'exited with %d' % os.WEXITSTATUS(rc)
            elif os.WIFSIGNALED(rc):
                desc = 'died with signal %d' % os.WTERMSIG(rc)
            raise ErrorInstallingPackage, "The decompressor %s whilst processing package %s" % (desc, self.name)
    
        package.close()

    def check(self, fast = False, progress = lambda x: ()):
        """ Check a package against it's known checksum, or if fast is
        specified, just check that the package exists. """
        path = self.repository.path(self.repository_filename)
        if fast:
            return self.repository.accessor().access(path)
        else:
            try:
                pkgfd = self.repository.accessor().openAddress(path)

                xelogging.log("Validating package %s" % self.name)
                m = md5.new()
                data = ''
                total_read = 0
                while True:
                    data = pkgfd.read(10485760)
                    total_read += len(data)
                    if data == '':
                        break
                    else:
                        m.update(data)
                    progress(total_read / (self.size / 100))
                
                pkgfd.close()
                
                calculated = m.hexdigest()
                valid = (self.md5sum == calculated)
                xelogging.log("Result: %s " % str(valid))
                return valid
            except Exception, e:
                return False

    def pkgLine(self):
        return "%s %s %s tbz2 required %s %s" % (
            self.name, self.size, self.md5sum, self.repository_filename, self.destination)

    def __repr__(self):
        return "<BzippedPackage: %s>" % self.name

class Accessor:
    def pathjoin(base, name):
        return os.path.join(base, name)
    pathjoin = staticmethod(pathjoin)

    def access(self, name):
        """ Return boolean determining where 'name' is an accessible object
        in the target. """
        try:
            f = self.openAddress(name)
            f.close()
        except:
            return False
        else:
            return True

    def canEject(self):
        return False

    def start(self):
        pass

    def finish(self):
        pass
    
    def findRepositories(self):
        # Check known locations:
        repos = []
        self.start()
        for loc in ['', 'packages', 'packages.main', 'packages.linux',
                    'packages.site']:
            if Repository.isRepo(self, loc):
                repos.append(Repository(self, loc))
        self.finish()
        return repos

class FilesystemAccessor(Accessor):
    def __init__(self, location):
        self.location = location

    def start(self):
        pass

    def finish(self):
        pass

    def openAddress(self, addr):
        return open(os.path.join(self.location, addr), 'r')

class MountingAccessor(FilesystemAccessor):
    def __init__(self, mount_types, mount_source, mount_options = ['ro']):
        (
            self.mount_types,
            self.mount_source,
            self.mount_options
        ) = (mount_types, mount_source, mount_options)
        self.start_count = 0
        self.location = None

    def start(self):
        if self.start_count == 0:
            self.location = tempfile.mkdtemp(prefix="media-", dir="/tmp")
            # try each filesystem in turn:
            success = False
            for fs in self.mount_types:
                try:
                    util.mount(self.mount_source, self.location,
                               options = self.mount_options,
                               fstype = fs)
                except util.MountFailureException, e:
                    continue
                else:
                    success = True
                    break
            if not success:
                raise util.MountFailureException
        self.start_count += 1

    def finish(self):
        if self.start_count == 0:
            return
        self.start_count = self.start_count - 1
        if self.start_count == 0:
            util.umount(self.location)
            os.rmdir(self.location)
            self.location = None

    def __del__(self):
        while self.start_count > 0:
            self.finish()

class DeviceAccessor(MountingAccessor):
    def __init__(self, device, fs = ['iso9660', 'vfat']):
        """ Return a MountingAccessor for a device 'device', which should
        be a fully qualified path to a device node. """
        MountingAccessor.__init__(self, fs, device)
        self.device = device

    def __repr__(self):
        return "<DeviceAccessor: %s>" % self.device

    def canEject(self):
        if diskutil.removable(self.device):
            return True

    def eject(self):
        assert self.canEject()
        util.runCmd2(['/usr/bin/eject', self.device])

class NFSAccessor(MountingAccessor):
    def __init__(self, nfspath):
        MountingAccessor.__init__(self, ['nfs'], nfspath)

class URLAccessor(Accessor):
    url_prefixes = ['http://', 'https://', 'ftp://']

    def __init__(self, baseAddress):
        if not True in [ baseAddress.startswith(prefix) for prefix in self.url_prefixes ] :
            xelogging.log("Base address: no known protocol specified, prefixing http://")
            baseAddress = "http://" + baseAddress
        if not baseAddress.endswith('/'):
            xelogging.log("Base address: did not end with '/' but should be a directory so adding it.")
            baseAddress += '/'

        if baseAddress.startswith('http://'):
            (scheme, netloc, path, params, query) = urlparse.urlsplit(baseAddress)
            (hostname, username, password) = util.splitNetloc(netloc)
            if username != None:
                xelogging.log("Using basic HTTP authentication: %s %s" % (username, password))
                self.passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
                self.passman.add_password(None, hostname, username, password)
                self.authhandler = urllib2.HTTPBasicAuthHandler(self.passman)
                self.opener = urllib2.build_opener(self.authhandler)
                urllib2.install_opener(self.opener)
                if password == None:
                    self.baseAddress = baseAddress.replace('%s@' % username, '', 1)
                else:
                    self.baseAddress = baseAddress.replace('%s:%s@' % (username, password), '', 1)
            else:
                self.baseAddress = baseAddress
        else:
            self.baseAddress = baseAddress

        xelogging.log("Initializing URLRepositoryAccessor with base address %s" % self.baseAddress)

    def _url_concat(url1, end):
        assert url1.endswith('/')
        end = end.lstrip('/')
        return url1 + end
    _url_concat = staticmethod(_url_concat)

    def _url_decode(url):
        start = 0
        i = 0
        while i != -1:
            i = url.find('%', start)
            if (i != -1):
                hex = url[i+1:i+3]
                if re.match('[0-9A-F]{2}', hex, re.I):
                    url = url.replace(url[i:i+3], chr(int(hex, 16)), 1)
                start = i+1
        return url
    _url_decode = staticmethod(_url_decode)

    def start(self):
        pass

    def finish(self):
        pass

    def access(self, path):
        if not self._url_concat(self.baseAddress, path).startswith('ftp://'):
            return Accessor.access(self, path)

        url = self._url_concat(self.baseAddress, path)

        # if FTP, override by actually checking the file exists because urllib2 seems
        # to be not so good at this.
        try:
            (scheme, netloc, path, params, query) = urlparse.urlsplit(url)
            (hostname, username, password) = util.splitNetloc(netloc)
            fname = os.path.basename(path)
            directory = self._url_decode(os.path.dirname(path[1:]))

            # now open a connection to the server and verify that fname is in 
            ftp = ftplib.FTP(hostname)
            ftp.login(username, password)
            ftp.cwd(directory)
            lst = ftp.nlst()
            return fname in lst
        except:
            # couldn't parse the server name out:
            return False

    def openAddress(self, address):
        return urllib2.urlopen(self._url_concat(self.baseAddress, address))

def repositoriesFromDefinition(media, address):
    if media == 'local':
        # this is a special case as we need to locate the media first
        return findRepositoriesOnMedia()
    else:
        accessors = { 'filesystem': FilesystemAccessor,
                      'url': URLAccessor,
                      'nfs': NFSAccessor }
        if accessors.has_key(media):
            accessor = accessors[media](address)
        else:
            raise RuntimeError, "Unknown repository media %s" % media

        accessor.start()
        rv = accessor.findRepositories()
        accessor.finish()
        return rv

def findRepositoriesOnMedia():
    """ Returns a list of repositories available on local media. """
    
    static_devices = [
        'hda', 'hdb', 'hdc', 'hdd', 'hde', 'hdf',
        'sda', 'sdb', 'sdc', 'sdd', 'sde', 'sdf',
        'scd0', 'scd1', 'scd2', 'scd3', 'scd4',
        'sr0', 'sr1', 'sr2', 'sr3', 'sr4', 'sr5', 'sr6', 'sr7',
        'cciss/c0d0', 'cciss/c0d1'
    ]

    removable_devices = diskutil.getRemovableDeviceList()
    removable_devices = filter(lambda x: not x.startswith('fd'),
                               removable_devices)

    # also scan the partitions of these removable devices:
    partitions = []
    for dev in removable_devices:
        partitions.extend(diskutil.partitionsOnDisk(dev))

    # remove devices we discovered from the static list so we don't
    # scan them twice:
    for x in removable_devices:
        if x in static_devices:
            static_devices.remove(x)

    da = None
    repos = []
    try:
        for check in removable_devices + partitions + static_devices:
            device_path = "/dev/%s" % check
            xelogging.log("Looking for repositories: %s" % device_path)
            if os.path.exists(device_path):
                da = DeviceAccessor(device_path)
                try:
                    da.start()
                except util.MountFailureException:
                    da = None
                    continue
                else:
                    repos.extend(da.findRepositories())
                    da.finish()
                    da = None
    finally:
        if da:
            da.finish()

    return repos
