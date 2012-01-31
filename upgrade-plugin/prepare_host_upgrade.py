#!/usr/bin/env python
# Copyright (c) 2011 Citrix Systems, Inc. All use and distribution of this
# copyrighted material is governed by and subject to terms and conditions
# as licensed by Citrix Systems, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or
# trademarks of Citrix Systems, Inc. in the United States and/or other 
# countries.

import logging
import os
import shutil
import sys
import tempfile
import StringIO

import xcp.accessor as accessor
import xcp.bootloader as bootloader
import xcp.cpiofile as cpiofile
import xcp.repository as repository
import xcp.version as version
import xcp.logger as logger
import XenAPI
import XenAPIPlugin

boot_files = [ 'install.img', 'boot/vmlinuz', 'boot/xen.gz']

def test_boot_files(accessor):
    done = True
    accessor.start()
    for f in boot_files:
        try:
            logger.info("Testing "+f)
            done = accessor.access(f)
            if done:
                logger.info("    success")
            else:
                logger.error("    failed")
        except Exception, e:
            logger.error(str(e))
            done = False
        
    accessor.finish()
    return done

def get_boot_files(accessor, dest_dir):
    done = True
    accessor.start()
    for f in boot_files:
        try:
            logger.info("Fetching "+f)
            inf = accessor.openAddress(f)
            outf = open(os.path.join(dest_dir, os.path.basename(f)), 'w')
            outf.writelines(inf)
            outf.close()
            inf.close()
        except Exception, e:
            logger.error(str(e))
            done = False
            break
    accessor.finish()
    return done

def gen_answerfile(installer_dir, url):
    root_device = None
    root_label = None

    try:
        # determine root disk
        f = open('/etc/xensource-inventory')
        for l in f:
            line = l.strip()
            if line.startswith('PRIMARY_DISK='):
                root_device = line[13:].strip("'")
                break
        f.close()
    except:
        logger.error("Failed to read inventory")
        return False
    if not root_device:
        logger.error("Failed to determine root disk")
        return False

    if not os.path.exists(root_device):
        logger.error("Root disk %s not found" % root_disk)
        return False

    try:
        # determine root label
        f = open('/etc/fstab')
        line = f.readline().strip()
        f.close
        if line.startswith('LABEL='):
            v, _ = line.split(None, 1)
            root_label = v[6:]
    except:
        logger.error("Failed to read fstab")
        return False
    if not root_label:
        logger.error("Failed to determine root label")
        return False

    logger.debug("Root device: "+root_device)
    logger.debug("Root label: "+root_label)
    
    in_arc = cpiofile.CpioFile.open(installer_dir+'/install.img', 'r|*')
    out_arc = cpiofile.CpioFile.open(installer_dir+'/upgrade.img', 'w|gz')
    out_arc.hardlinks = False

    # copy initrd
    logger.info("Copying initrd...")
    for f in in_arc:
        data = None
        if f.size > 0:
            data = in_arc.extractfile(f)
        out_arc.addfile(f, data)
    in_arc.close()

    # create bootloader revert script
    config = bootloader.Bootloader.loadExisting()

    logger.info("Creating revert script")
    text = '#!/usr/bin/env python\n'
    text += '\nimport xcp.bootloader as bootloader\n'
    text += 'import xcp.mount as mount\n'
    text += '\nrootfs = mount.TempMount(None, "root", fstype = "ext3", label = "%s")\n' % root_label
    text += 'cfg = bootloader.Bootloader.loadExisting(rootfs.mount_point)\n'
    text += 'cfg.default = "%s"\n' % config.default
    text += 'cfg.remove("upgrade")\n'
    text += 'cfg.commit()\n'
    text += 'rootfs.unmount()\n'

    contents = StringIO.StringIO(text)

    f = cpiofile.CpioInfo('revert-bootloader.py')
    f.size = len(contents.getvalue())
    out_arc.addfile(f, contents)

    # create answerfile
    logger.info("Creating answerfile")
    text = '<?xml version="1.0"?>\n'
    text += ' <installation mode="upgrade">\n'
    text += '  <existing-installation>%s</existing-installation>\n' % root_device
    text += '  <source type="url">%s</source>\n' % url
    text += '  <script stage="installation-start" type="url">file:///revert-bootloader.py</script>\n'
    text += ' </installation>\n'
    
    contents = StringIO.StringIO(text)

    f = cpiofile.CpioInfo('answerfile')
    f.size = len(contents.getvalue())
    out_arc.addfile(f, contents)

    out_arc.close()

    return True

def get_mgmt_config():
    ret = None

    session = XenAPI.xapi_local()
    session.xenapi.login_with_password('', '')
    this_host = session.xenapi.session.get_this_host(session._session)
    host_record = session.xenapi.host.get_record(this_host)

    for pif in host_record['PIFs']:
        pif_record = session.xenapi.PIF.get_record(pif)
        if pif_record['management']:
            ret = pif_record
            break
        
    session.xenapi.session.logout()
    return ret

def set_boot_config(installer_dir, url):
    try:
        config = bootloader.Bootloader.loadExisting()

        default = config.menu[config.default]
        if 'upgrade' in config.menu_order:
            config.remove('upgrade')
        else:
            config.commit(os.path.join(installer_dir, os.path.basename(config.src_file)))

        xen_args = ['dom0_max_vcpus=2', 'dom0_mem=752M']
        xen_args.extend(filter(lambda x: x.startswith('com') or x.startswith('console='), default.hypervisor_args.split()))
        kernel_args = filter(lambda x: x.startswith('console=') or x.startswith('xencons=') or x.startswith('device_mapper_multipath='), default.kernel_args.split())
        kernel_args.extend(['install', 'answerfile=file:///answerfile'])

        scheme = url[:url.index('://')]
        if scheme in ['http', 'nfs', 'ftp']:
            pif = get_mgmt_config()

            if pif['ip_configuration_mode'] == 'Static':
                config_str = "static:ip=%s;netmask=%s" % (pif['IP'], pif['netmask'])
                if 'gateway' in pif:
                    config_str += ";gateway=" + pif['gateway']
                if 'DNS' in pif:
                    config_str += ";dns=" + pif['DNS']
                kernel_args.extend(['network_device='+pif['MAC'],
                                'network_config='+config_str])
            else:
                kernel_args.append('network_device=' + pif['MAC'])
        elif scheme == 'file':
            # locate major/minor of device url is on
            s = os.stat(url[7:])
            major = s[2] / 256
            minor = s[2] % 256

            # locate device name
            dev = None
            fh = open('/proc/partitions')
            fh.readline()
            fh.readline()
            for line in fh:
                v = line.split()
                if int(v[0]) == major and int(v[1]) == minor:
                    dev = v[3]
                    break
            fh.close()
            if not dev:
                logger.error("Unable to locate name for %d:%d" % (major, minor))
                return False
            dev = '/dev/' + dev

            # locate mount pount
            mnt = None
            fs = None
            fh = open('/proc/mounts')
            for line in fh:
                v = line.split()
                if v[0] == dev:
                    mnt = v[1]
                    fs = v[2]
                    break
            fh.close()
            if not mnt:
                logger.error("Unable to locate mount point for " + dev)
                return False

            kernel_args.append("mount=%s:%s:%s" % (dev, fs, mnt))

        e = bootloader.MenuEntry(installer_dir+'/xen.gz', ' '.join(xen_args),
                                 installer_dir+'/vmlinuz', ' '.join(kernel_args),
                                 installer_dir+'/upgrade.img', 'Rolling pool upgrade')
        config.append('upgrade', e)
        config.default = 'upgrade'
        logger.info("Writing updated bootloader config")
        config.commit()
    except:
        logger.error("Failed to set up bootloader")
        return False

    return True

TEST_REPO_GOOD = 0
TEST_URL_INVALID = 1
TEST_VER_INVALID = 2

def test_repo(url):
    logger.debug("Testing "+url)
    try:
        a = accessor.createAccessor(url, True)
        if not test_boot_files(a):
            return TEST_URL_INVALID
        repos = repository.Repository.findRepositories(a)
    except Exception, e:
        logger.error(str(e))
        return TEST_URL_INVALID
    if len(repos) == 0:
        return TEST_URL_INVALID

    repo_ver = None
    for r in repos:
        if r.identifier == repository.Repository.XS_MAIN_IDENT:
            logger.debug("Repository found: " + str(r))
            repo_ver = r.product_version
            break

    # read current host version
    curr_ver = None
    try:
        i = open('/etc/xensource-inventory')
        for line in i:
            if line.startswith('PRODUCT_VERSION'):
                curr_ver = version.Version.from_string(line.strip()[16:].strip("'"))
                break
        i.close()
    except:
        pass    
    
    # verify repo version
    if repo_ver and curr_ver and repo_ver >= curr_ver:
        logger.info("Repo version OK: " + str(repo_ver))
        return TEST_REPO_GOOD

    logger.error("Repo version ERR: " + str(repo_ver))
    return TEST_VER_INVALID

def prepare_host_upgrade(url):
    installer_dir = '/boot/installer'
    done = True

    # download the installer files
    try:
        shutil.rmtree(installer_dir)
    except:
        pass
    os.mkdir(installer_dir, 0700)

    a = accessor.createAccessor(url, True)
    done = get_boot_files(a, installer_dir)

    if done:
        done = gen_answerfile(installer_dir, url)
        
    if done:
        # create bootloader entry
        set_boot_config(installer_dir, url)
        
    if not done:
        try:
            shutil.rmtree(installer_dir)
        except:
            pass
    return done

# plugin url test
def testUrl(session, args):
    logger.logToSyslog(level = logging.INFO)

    try:
        url = args['url']
    except KeyError:
        raise Exception('MISSING_URL')

    ret = test_repo(url)
    if ret == TEST_URL_INVALID:
        raise Exception('INVALID_URL')
    elif ret == TEST_VER_INVALID:
        raise Exception('INVALID_VER')

    return "true"
    
# plugin entry point
def main(session, args):
    logger.logToSyslog(level = logging.INFO)

    try:
        url = args['url']
    except KeyError:
        logger.critical("Missing argument 'url'")
        raise Exception('MISSING_URL')

    logger.info("Verifying repo...")
    if test_repo(url) != TEST_REPO_GOOD:
        logger.error("%s is not a valid repo" % url)
        raise Exception('INVALID_URL')

    logger.info("Repo ok, preparing for upgrade")
    if not prepare_host_upgrade(url):
        logger.error("There was an error in preparing the host for upgrade.")
        raise Exception('ERROR_PREPARING_HOST')

    logger.info("Preparation succeeded, ready for upgrade.")
    return "true"


if __name__ == '__main__':
    XenAPIPlugin.dispatch({"main": main,
                           "testUrl": testUrl})
