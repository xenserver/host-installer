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
import errno
import md5
import tempfile
import urlparse
import urllib
import urllib2
import ftplib
import subprocess
import re

import xelogging
import diskutil
import hardware
import version
import util
from util import dev_null
from xcp.version import *
import cpiofile
from constants import *
import xml.dom.minidom

# get text from a node:
def getText(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc.encode().strip()

class NoRepository(Exception):
    pass

class RepoFormatError(Exception):
    pass

class UnknownPackageType(Exception):
    pass

class ErrorInstallingPackage(Exception):
    pass

class Repository:
    """ Represents a repository containing packages and associated meta data. """
    def __init__(self, accessor, base = ""):
        self._accessor = accessor
        self._base = base

    def accessor(self):
        return self._accessor

class LegacyRepository(Repository):
    """ Represents a XenSource repository containing packages and associated
    meta data. """
    REPOSITORY_FILENAME = "XS-REPOSITORY"
    PKGDATA_FILENAME = "XS-PACKAGES"
    REPOLIST_FILENAME = "XS-REPOSITORY-LIST"

    OPER_MAP = {'eq': ' = ', 'ne': ' != ', 'lt': ' < ', 'gt': ' > ', 'le': ' <= ', 'ge': ' >= '}

    def findRepositories(cls, accessor):
        # Check known locations:
        package_list = ['', 'packages', 'packages.main', 'packages.linux',
                        'packages.site']
        repos = []

        accessor.start()
        try:
            extra = accessor.openAddress(cls.REPOLIST_FILENAME)
            if extra:
                for line in extra:
                    package_list.append(line.strip())
                extra.close()
        except Exception, e:
            xelogging.log("Failed to open %s: %s" % (cls.REPOLIST_FILENAME, str(e)))

        for loc in package_list:
            if LegacyRepository.isRepo(accessor, loc):
                xelogging.log("Repository (legacy) found in /%s" % loc)
                repos.append(LegacyRepository(accessor, loc))
        accessor.finish()
        return repos
    findRepositories = classmethod(findRepositories)

    def __init__(self, accessor, base = ""):
        Repository.__init__(self, accessor, base)
        self._product_brand = None
        self._product_version = None
        self._md5 = md5.new()
        self.requires = []

        accessor.start()

        try:
            repofile = accessor.openAddress(self.path(self.REPOSITORY_FILENAME))
        except Exception, e:
            accessor.finish()
            raise NoRepository, e
        self._parse_repofile(repofile)
        repofile.close()

        try:
            pkgfile = accessor.openAddress(self.path(self.PKGDATA_FILENAME))
        except Exception, e:
            accessor.finish()
            raise NoRepository, e
        self._parse_packages(pkgfile)
        pkgfile.close()

        accessor.finish()

    def __repr__(self):
        return self._identifier

    def isRepo(cls, accessor, base):
        """ Return whether there is a repository at base address 'base' accessible
        using accessor."""
        return False not in [ accessor.access(accessor.pathjoin(base, f)) for f in [cls.REPOSITORY_FILENAME, cls.PKGDATA_FILENAME] ]
    isRepo = classmethod(isRepo)

    def _parse_repofile(self, repofile):
        """ Parse repository data -- get repository identifier and name. """
        
        self._repofile_contents = repofile.read()
        repofile.close()

        # update md5sum for repo
        self._md5.update(self._repofile_contents)

        # build xml doc object
        try:
            xmldoc = xml.dom.minidom.parseString(self._repofile_contents)
        except:
            raise RepoFormatError, "%s not in XML" % self.REPOSITORY_FILENAME

        try:
            repo_node = xmldoc.getElementsByTagName('repository')[0]
            desc_node = xmldoc.getElementsByTagName('description')[0]
            _originator = repo_node.getAttribute("originator").encode()
            _name = repo_node.getAttribute("name").encode()
            _product = repo_node.getAttribute("product").encode()
            _version = repo_node.getAttribute("version").encode()
            _build = repo_node.getAttribute("build").encode()
            if _build == '': _build = None
            _description = getText(desc_node.childNodes)
            _hidden = repo_node.getAttribute("hidden").encode()
            if _hidden == '': _hidden='false'

            for req_node in xmldoc.getElementsByTagName('requires'):
                req = {}
                for attr in ['originator', 'name', 'test', 'version', 'build']:
                    req[attr] = req_node.getAttribute(attr).encode()
                if req['build'] == '': del req['build']
                assert req['test'] in self.OPER_MAP
                self.requires.append(req)
        except:
            raise RepoFormatError, "%s format error" % self.REPOSITORY_FILENAME

        # map info gleaned from XML to data expected by other Repository methods
        self._identifier = "%s:%s" % (_originator,_name)
        self._name = _description
        self._product_brand = _product
        self._hidden = _hidden
        ver_str = _version
        if _build: ver_str += '-'+_build
        self._product_version = Version.from_string(ver_str)

    def compatible_with(self, platform, brand):
        return self._product_brand in [brand, platform, None]

    def __str__(self):
        return self._identifier + ' ' + str(self._product_version)

    def name(self):
        return self._name

    def identifier(self):
        return self._identifier

    def path(self, name):
        return self._accessor.pathjoin(self._base, name)

    def hidden(self):
        return self._hidden

    def _parse_packages(self, pkgfile):
        self._pkgfile_contents = pkgfile.read()
        pkgfile.close()
        
        # update md5sum for repo
        self._md5.update(self._pkgfile_contents)

        # build xml doc object
        try:
            xmldoc = xml.dom.minidom.parseString(self._pkgfile_contents)
        except:
            raise RepoFormatError, "%s not in XML" % self.PKGDATA_FILENAME

        self._packages = []
        for pkg_node in xmldoc.getElementsByTagName('package'):
            try:
                _label = pkg_node.getAttribute("label")
                _type = pkg_node.getAttribute("type")
                _size = pkg_node.getAttribute("size")
                _md5sum = pkg_node.getAttribute("md5")
                _root = pkg_node.getAttribute("root")
                _kernel = pkg_node.getAttribute("kernel")
                _options = pkg_node.getAttribute("options").split()
                if _options == []: _options = ['-U']
                _fname = getText(pkg_node.childNodes)
            except:
                raise RepoFormatError, "%s format error" % self.PKGDATA_FILENAME

            if (_type == 'tbz2'):
                pkg = BzippedPackage(self, _label, _size, _md5sum, 'required', _fname, _root)
            elif (_type == 'driver'):
                pkg = DriverPackage(self, _label, _size, _md5sum, _fname, _root)
            elif (_type == 'firmware'):
                pkg = FirmwarePackage(self, _label, _size, _md5sum, _fname)
            elif (_type == 'rpm'):
                pkg = RPMPackage(self, _label, _size, _md5sum, _fname, _options)
            elif (_type == 'driver-rpm'):
                pkg = DriverRPMPackage(self, _label, _size, _md5sum, _kernel, _fname, _options)
            else:
                raise UnknownPackageType, _type
            pkg.type = _type

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
            total_size = reduce(lambda x, y: x + y,
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

    def check_requires(self, installed_repos):
        """ Return a list the prerequisites that are not yet installed. """
        problems = []

        def fmt_dep(id, d):
            text = "%s requires %s:%s" % (id, d['originator'], d['name'])
            if d['test'] in self.OPER_MAP:
                text += self.OPER_MAP[d['test']]
            else:
                return text
            text += 'build' in d and "%s-%s" % (d['version'], d['build']) or d['version']
            
            return text

        for dep in self.requires:
            want_id = "%s:%s" % (dep['originator'], dep['name'])
            want_ver = Version.from_string('build' in dep and "%s-%s" % (dep['version'], dep['build']) or dep['version'])
            found = False
            for repo in installed_repos.values():
                if repo.identifier() == want_id and eval("repo._product_version.__%s__(want_ver)" % dep['test']):
                    xelogging.log("Dependency match: %s satisfies test %s" % (str(repo), fmt_dep(self._identifier, dep)))
                    found = True
                    break
            if not found:
                xelogging.log("Dependency failure: failed test %s" % fmt_dep(self._identifier, dep))
                problems.append(fmt_dep(self._identifier, dep))

        return problems

    def copyTo(self, destination):
        util.assertDir(destination)

        # write the XS-REPOSITORY file:
        xsrep_fd = open(os.path.join(destination, self.REPOSITORY_FILENAME), 'w')
        xsrep_fd.write(self._repofile_contents)
        xsrep_fd.close()

        # copy the packages and write an XS-PACKAGES file:
        xspkg_fd = open(os.path.join(destination, self.PKGDATA_FILENAME), 'w')
        xspkg_fd.write(self._pkgfile_contents)
        xspkg_fd.close()

    def __iter__(self):
        return self._packages.__iter__()

    def record_install(self, answers, installed_repos):
        self.copyTo(os.path.join(answers['root'], INSTALLED_REPOS_DIR, self._identifier))
        installed_repos[str(self)] = self
        return installed_repos

    def md5sum(self):
        return self._md5.hexdigest()

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

        xelogging.log("mkdir -p %s" % (os.path.dirname(destination)))
        try:
            os.makedirs(os.path.dirname(destination))
        except OSError, exc:
            # Needed for python < 2.5; considered a bug and fixed in later
            # versions: http://bugs.python.org/issue1675
            if exc.errno == errno.EEXIST:
                pass
            else: raise
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

    def is_compatible(self):
        return True

    def eula(self):
        return None

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
        self.destination = self.destination.replace("${LINUX_KABI_VERSION}", version.LINUX_KABI_VERSION)

    def __repr__(self):
        return "<DriverPackage: %s>" % self.name

    def install(self, base, progress = lambda x: ()):
        self.write(os.path.join(base, self.destination))

    def check(self, fast = False, progress = lambda x: ()):
        return self.repository.accessor().access(self.repository_filename)
    
    def is_loadable(self):
        return True

    def load(self):
        # Copy driver to a temporary location:
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
        ) = ( repository, name, long(size), md5sum, src )
        self.destination = 'lib/firmware/%s' % os.path.basename(src)

    def __repr__(self):
        return "<FirmwarePackage: %s>" % self.name

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

        tmpout = tempfile.TemporaryFile()
        tmperr = tempfile.TemporaryFile()
        
        cmd = ['tar', '-C', os.path.join(base, self.destination), '-xj']
        pipe = subprocess.Popen(cmd,
                                bufsize = 1024 * 1024, stdin = subprocess.PIPE, 
                                stdout = tmpout, stderr = tmperr)
    
        data = ''
        current_progress = 0
        while True:
            # read in 10mb chunks so as not to use so much RAM, and to
            # allow decompression to occur in parallel (in the bzip2
            # process).
            data = package.read(10485760)
            if data == '':
                break

            try:
                pipe.stdin.write(data)
            except IOError as e:
                xelogging.logException(e)
                break

            current_progress += len(data)
            progress(current_progress / 100)

        pipe.stdin.close()
        rc = pipe.wait()

        tmpout.seek(0)
        out = tmpout.read().strip()
        tmpout.close()
        if out:
            xelogging.log("'%s' stdout:\n%s" % (" ".join(cmd), out))

        tmperr.seek(0)
        err = tmperr.read().strip()
        tmperr.close()
        if err:
            xelogging.log("'%s' stderr:\n%s" % (" ".join(cmd), err))

        if current_progress != self.size:
            xelogging.log("Unexpected number of bytes read: Expected %d, but got %d" % (self.size, current_progress))

        if rc != 0:
            if rc > 0:
                desc = 'exited with %d' % rc
            else:
                desc = 'died with signal %d' % (-rc)
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

    def __repr__(self):
        return "<BzippedPackage: %s>" % self.name

class RPMPackage(Package):
    def __init__(self, repository, name, size, md5sum, src, options):
        (
            self.repository,
            self.name,
            self.size,
            self.md5sum,
            self.repository_filename,
            self.options,
        ) = ( repository, name, long(size), md5sum, src, options )
        self.destination = 'tmp/%s' % os.path.basename(src)

    def __repr__(self):
        return "<RPMPackage: %s>" % self.name

    def install(self, base, progress = lambda x: ()):
        self.write(os.path.join(base, self.destination))
        rc, name = util.runCmd2(['/usr/sbin/chroot', base, '/bin/rpm', '-q', '--qf', '%{NAME}', 
                                 '-p', self.destination], with_stdout = True)
        assert rc == 0

        rc, new_ver = util.runCmd2(['/usr/sbin/chroot', base, '/bin/rpm', '-q', '--qf', '%{VERSION}-%{RELEASE}', 
                                    '-p', self.destination], with_stdout = True)
        assert rc == 0
        rc, cur_ver = util.runCmd2(['/usr/sbin/chroot', base, '/bin/rpm', '-q', '--qf', '%{VERSION}-%{RELEASE}', 
                                        name], with_stdout = True)
        if rc == 0 and new_ver == cur_ver:
            # skip, this version is already installed
            xelogging.log("%s-%s already installed, skipping" % (name, new_ver))
            return

        rc, msg = util.runCmd2(['/usr/sbin/chroot', base, '/bin/rpm']+self.options+[self.destination], with_stderr = True)
        os.unlink(os.path.join(base, self.destination))
        if rc != 0:
            raise ErrorInstallingPackage, "Installation of %s failed.\n%s" % (self.destination, msg.rstrip())

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

    def eula(self):
        """ Extract the contents of any EULA files """

        self.repository.accessor().start()

        # Copy RPM to a temporary location:
        util.assertDir('/tmp/rpm')
        temploc = os.path.join('/tmp/rpm', self.repository_filename)
        self.write(temploc)

        tmpcpio = tempfile.mktemp(prefix="cpio-", dir="/tmp")
        util.runCmd2("rpm2cpio %s >%s" % (temploc, tmpcpio))

        data = ''

        payload = cpiofile.open(tmpcpio, 'r')

        for cpioinfo in payload:
            if cpioinfo.name.endswith('EULA'):
                data += payload.extractfile(cpioinfo).read()

        payload.close()

        self.repository.accessor().finish()
    
        # Remove the RPM from the temporary location:
        os.unlink(tmpcpio)
        os.unlink(temploc)

        return data

class DriverRPMPackage(RPMPackage):
    def __init__(self, repository, name, size, md5sum, kernel, src, options):
        (
            self.repository,
            self.name,
            self.size,
            self.md5sum,
            self.kernel_version,
            self.repository_filename,
            self.options,
        ) = ( repository, name, long(size), md5sum, kernel, src, options )
        self.destination = 'tmp/%s' % os.path.basename(src)

    def __repr__(self):
        return "<DriverRPMPackage: %s>" % self.name

    def load(self):
        def module_present(module):
            return hardware.module_present(os.path.splitext(os.path.basename(module))[0])

        # Skip drivers for kernels other than ours:
        if not self.is_loadable():
            xelogging.log("Skipping driver %s, version mismatch (%s != %s)" % 
                          (self.name, self.kernel_version, version.LINUX_KABI_VERSION))
            return 0

        self.repository.accessor().start()

        # Copy driver to a temporary location:
        util.assertDir('/tmp/drivers')
        temploc = os.path.join('/tmp/drivers', self.repository_filename)
        self.write(temploc)

        # Install the RPM into the ramdisk:
        rc = util.runCmd2(['/bin/rpm', '-i', temploc])

        if rc == 0:
            util.runCmd2(['/sbin/depmod'])
            modules = []
            rc, out = util.runCmd2(['/bin/rpm', '-qlp', temploc], with_stdout = True)
            if rc == 0:
                modules += filter(lambda x: x.endswith('.ko') and x not in modules and not module_present(x), out.split("\n"))

            # insmod the driver(s):
            for module in modules:
                rc = hardware.modprobe_file(module)
                if rc != 0:
                    xelogging.log("Failed to modprobe %s" %module)
        else:
            xelogging.log("Failed to install %s" % self.name)

        self.repository.accessor().finish()

        # Remove the driver from the temporary location:
        os.unlink(temploc)

        return rc

    def is_compatible(self):
        return self.kernel_version == 'any' or self.kernel_version == version.LINUX_KABI_VERSION
    
    def is_loadable(self):
        return self.kernel_version == 'any' or self.kernel_version == version.LINUX_KABI_VERSION

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
        repos = LegacyRepository.findRepositories(self)
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
                os.rmdir(self.location)
                raise util.MountFailureException
        self.start_count += 1

    def finish(self):
        if self.start_count == 0:
            return
        self.start_count -= 1
        if self.start_count == 0:
            util.umount(self.location)
            os.rmdir(self.location)
            self.location = None

    def __del__(self):
        while self.start_count > 0:
            self.finish()

class DeviceAccessor(MountingAccessor):
    def __init__(self, device, fs = ['iso9660', 'vfat', 'ext3']):
        """ Return a MountingAccessor for a device 'device', which should
        be a fully qualified path to a device node. """
        MountingAccessor.__init__(self, fs, device)
        self.device = device

    def __repr__(self):
        return "<DeviceAccessor: %s>" % self.device

    def canEject(self):
        return diskutil.removable(self.device)

    def eject(self):
        if self.canEject():
            self.finish()
            util.runCmd2(['eject', self.device])

class NFSAccessor(MountingAccessor):
    def __init__(self, nfspath):
        MountingAccessor.__init__(self, ['nfs'], nfspath, ['ro', 'tcp'])

class URLFileWrapper:
    "This wrapper emulate seek (forwards) for URL streams"
    SEEK_SET = 0 # SEEK_CUR and SEEK_END not supported

    def __init__(self, delegate):
        self.delegate = delegate
        self.pos = 0
        
    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def read(self, *params):
        ret_val = self.delegate.read(*params)
        self.pos += len(ret_val)
        return ret_val

    def seek(self, offset, whence = 0):
        consume = 0
        if whence == self.SEEK_SET:
            if offset >= self.pos:
                consume = offset - self.pos
            else:
                raise Exception('Backward seek not supported')
        else:
            raise Exception('Only SEEK_SET supported')
           
        if consume > 0:
            step = 100000
            while consume > step:
                if len(self.read(step)) != step: # Discard data
                    raise IOError('Seek beyond end of file')
                consume -= step
            if len(self.read(consume)) != consume: # Discard data
                raise IOError('Seek beyond end of file')

class URLAccessor(Accessor):
    url_prefixes = ['http://', 'https://', 'ftp://', 'file://']

    def __init__(self, baseAddress):
        if not True in [ baseAddress.startswith(prefix) for prefix in self.url_prefixes ] :
            xelogging.log("Base address: no known protocol specified, prefixing http://")
            baseAddress = "http://" + baseAddress
        if not baseAddress.endswith('/'):
            xelogging.log("Base address: did not end with '/' but should be a directory so adding it.")
            baseAddress += '/'

        if baseAddress.startswith('http://'):
            (scheme, netloc, path, params, query) = urlparse.urlsplit(baseAddress)
            if netloc.endswith(':'):
                baseAddress = baseAddress.replace(netloc, netloc[:-1])
                netloc = netloc[:-1]
            pos = baseAddress[7:].index('/')+7
            path2 = baseAddress[pos:]
            if '#' in path2:
                new_path = path2.replace('#', '%23')
                baseAddress = baseAddress.replace(path2, new_path)
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
        return url1 + urllib.quote(end)
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
        ret_val = urllib2.urlopen(self._url_concat(self.baseAddress, address))
        return URLFileWrapper(ret_val)

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
        'cciss/c0d0', 'cciss/c0d1',
        'xvda', 'xvdb','xvdc', 'xvdd', 
    ]

    removable_devices = diskutil.getRemovableDeviceList()
    removable_devices = filter(lambda x: not x.startswith('fd'),
                               removable_devices)

    parent_devices = []
    partitions = []
    for dev in removable_devices + static_devices:
        if os.path.exists("/dev/%s" % dev):
            if os.path.exists("/sys/block/%s" % dev):
                dev_partitions = diskutil.partitionsOnDisk(dev)
                if len(dev_partitions) > 0:
                    partitions.extend([x for x in dev_partitions if x not in partitions])
                else:
                    if dev not in parent_devices:
                        parent_devices.append(dev)
            else:
                if dev not in parent_devices:
                    parent_devices.append(dev)

    da = None
    repos = []
    try:
        for check in parent_devices + partitions:
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
