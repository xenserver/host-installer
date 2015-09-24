#!/usr/bin/env python
# Copyright (c) 2011 Citrix Systems, Inc. All use and distribution of this
# copyrighted material is governed by and subject to terms and conditions
# as licensed by Citrix Systems, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or
# trademarks of Citrix Systems, Inc. in the United States and/or other 
# countries.

import logging
import os
import os.path
import re
import shutil
import socket
import sys
import tempfile
import urlparse
import StringIO

import xcp.accessor as accessor
import xcp.bootloader as bootloader
import xcp.cmd as cmd
import xcp.cpiofile as cpiofile
import xcp.pci as pci
import xcp.repository as repository
import xcp.version as version
import xcp.logger as logger
import XenAPI
import XenAPIPlugin

min_upgrade_lvm_part_size = 38 * 2**30 #38GB

boot_files = [ 'install.img', 'boot/vmlinuz', 'boot/xen.gz', 'boot/isolinux/isolinux.cfg' ]
xs_6_2 = version.Version([6, 2, 0])

def shell_value(line):
    return line.split('=', 1)[1].strip("'")

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

def get_repo_ver(accessor):
    repo_ver = None

    try:
        repos = repository.Repository.findRepositories(accessor)
        for r in repos:
            if r.identifier == repository.Repository.XS_MAIN_IDENT:
                logger.debug("Repository found: " + str(r))
                repo_ver = r.product_version
                break
    except:
        pass

    return repo_ver

def map_label_to_partition(label):
    partition = None
    (rc, out) = cmd.runCmd(['blkid', '-l', '-t', 'LABEL="%s"' % label, '-o', 'device'],
                           with_stdout = True)
    if rc == 0 and out.startswith('/dev/'):
        partition = out.strip()
        if os.path.isfile('/sbin/udevadm'):
            args = ['/sbin/udevadm', 'info']
        else:
            args = ['udevinfo']
        (rc, out) = cmd.runCmd(args + ['-q', 'symlink', '-n', partition[5:]],
                               with_stdout = True)
        if rc == 0:
            for link in out.split():
                if link.startswith('disk/by-id') and not link.startswith('disk/by-id/edd'):
                    partition = '/dev/'+link
                    break

    return partition

def get_fs_labels():
    root_label = None
    boot_label = None
    try:
        # determine root and boot labels
        with open('/etc/fstab') as f:
            for line in f:
                line = line.strip()
                if line.startswith('LABEL=root-'):
                    v, _ = line.split(None, 1)
                    root_label = v[6:]
                if line.startswith('LABEL=BOOT-'):
                    v, _ = line.split(None, 1)
                    boot_label = v[6:]
    except:
        logger.error("Failed to read fstab")

    return root_label, boot_label

def gen_answerfile(accessor, installer_dir, url):
    root_device = None
    root_partition = None
    boot_partition = None

    try:
        # determine root disk
        f = open('/etc/xensource-inventory')
        for l in f:
            line = l.strip()
            if line.startswith('PRIMARY_DISK='):
                root_device = shell_value(line)
                break
        f.close()
    except:
        logger.error("Failed to read inventory")
        return False
    if not root_device:
        logger.error("Failed to determine root disk")
        return False

    if not os.path.exists(root_device):
        logger.error("Root disk %s not found" % root_device)
        return False

    # Some G6/G7 controllers moved from the cciss subsystem to scsi
    repo_ver = get_repo_ver(accessor)
    if (repo_ver > xs_6_2):
        devices = pci.PCIDevices()
        raid_devs = devices.findByClass('01', '04')
        g6 = map(lambda x: x['vendor'] == '103c' and x['device'] == '323a' and
                 x['subvendor'] == '103c' and x['subdevice'].startswith('324'),
                 raid_devs)
        if True in g6:
            new_device = root_device.replace('cciss', 'scsi')
            logger.info("Replacing root disk "+root_device+ " with "+new_device)
            root_device = new_device

    root_label, boot_label = get_fs_labels()
    if not root_label:
        logger.error("Failed to determine root label")
        return False

    try:
        root_partition = map_label_to_partition(root_label)
        if boot_label:
            boot_partition = map_label_to_partition(boot_label)
    except:
        logger.error("Failed to map label to partition")
        return False
    if not root_partition:
        logger.error("Failed to determine root partition")
        return False
    if boot_label and not boot_partition:
        logger.error("Failed to determine boot partition")
        return False

    logger.debug("Root device: "+root_device)
    logger.debug("Root label: "+root_label)
    logger.debug("Root partition: "+root_partition)
    logger.debug("Boot label: %s" % boot_label)
    logger.debug("Boot partition: %s" % boot_partition)
    
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
    text += '\nimport os.path\n'
    text += 'import xcp.bootloader as bootloader\n'
    text += 'import xcp.mount as mount\n'
    text += '\nrootfs = mount.TempMount("%s", "root", fstype = "ext3")\n' % root_partition
    if boot_partition:
        text += 'mount.mount("%s", os.path.join(rootfs.mount_point, "boot/efi"), fstype = "vfat")\n' % boot_partition
    text += 'cfg = bootloader.Bootloader.loadExisting(rootfs.mount_point)\n'
    text += 'cfg.default = "%s"\n' % config.default
    text += 'cfg.remove("upgrade")\n'
    text += 'cfg.commit()\n'
    if boot_partition:
        text += 'mount.umount(os.path.join(rootfs.mount_point, "boot/efi"))\n'
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

def resolve_bonded_iface_and_check_carrier(pif, session):
    bonds = pif.get('bond_master_of', '')
    if not len(bonds):
        # Return the PIF that was passed in if it is not a bond
        d = pif.get('device', '').strip()
        m = pif.get('MAC', '').strip()
        if d == '' or m == '':
            return None, None
        return d, m

    # Otherwise, determine the real interfaces behind the bond
    bond = session.xenapi.Bond.get_record(bonds[0])
    for slave in bond.get('slaves', []):
        bond_pif = session.xenapi.PIF.get_record(slave)
        device = bond_pif.get('device', '').strip()
        carrier = 0
        # Check if there is a carrier on this device
        try:
            f = open('/sys/class/net/%s/carrier' % device, 'r')
            carrier = int(f.read().strip())
            f.close()
        except:
            pass
        if carrier == 1:
            m = pif.get('MAC', '').strip()
            if m == '':
                return None, None
            return device, m
    
    # At this point, no interface had a carrier
    return None, None

def get_iface_config(iface):
    pif = None
    mac = None

    session = XenAPI.xapi_local()
    session.xenapi.login_with_password('', '','', 'prepare_host_upgrade.py')

    this_host = session.xenapi.session.get_this_host(session._session)

    for net in session.xenapi.network.get_all_records().values():
        if net.get('bridge', '') == iface:
            for p in net.get('PIFs', []):
                pif = session.xenapi.PIF.get_record(p)
                if pif.get('host', '') == this_host:
                    iface, mac = resolve_bonded_iface_and_check_carrier(pif, session)
                    break
        
    session.xenapi.session.logout()
    return pif, iface, mac

def urlsplit(url):
    host = ''
    parts = accessor.compat_urlsplit(url)
    if parts.scheme == 'nfs':
        host = parts.path.split(':', 1)[0][2:]
    elif parts.scheme in ['http', 'ftp']:
        host = parts.hostname
    return (parts.scheme, host)

def set_boot_config(installer_dir, url):
    try:
        config = bootloader.Bootloader.loadExisting()
        new_config = bootloader.Bootloader.readExtLinux(os.path.join(installer_dir, 'isolinux.cfg'))

        default = config.menu[config.default]
        new_default = new_config.menu[new_config.default]
        if 'upgrade' in config.menu_order:
            config.remove('upgrade')
        else:
            if config.src_file.startswith('/boot/efi'):
                config.commit(os.path.join(installer_dir, 'efi-%s' % os.path.basename(config.src_file)))
            else:
                config.commit(os.path.join(installer_dir, os.path.basename(config.src_file)))

        xen_args = filter(lambda x: not x.startswith('com') and not x.startswith('console='), new_default.hypervisor_args.split())
        xen_args.extend(filter(lambda x: x.startswith('com') or x.startswith('console='), default.hypervisor_args.split()))
        kernel_args = filter(lambda x: x.startswith('console=') or x.startswith('xencons=') or x.startswith('device_mapper_multipath='), default.kernel_args.split())
        kernel_args.extend(['install', 'answerfile=file:///answerfile'])

        (scheme, host) = urlsplit(url)
        if scheme in ['http', 'nfs', 'ftp']:
            # determine interface host is accessible over
            logger.debug("Repo host: "+host)
            (rc, out) = cmd.runCmd(['ip', 'route', 'get', socket.gethostbyname(host)], 
                                   with_stdout = True)
            if rc != 0:
                logger.error("Unable to resolve IP address of " + host)
                return False
            m = re.search(r' dev (\w+) ', out)
            if not m:
                logger.error("Unable to determine route to " + host)
                return False
            iface = m.group(1)
            pif, real_iface, mac = get_iface_config(iface)
            if not pif or not real_iface or not mac:
                logger.error("Unable to determine configuration of " + iface)
                return False
            logger.info("%s accessible via %s (%s)" % (host, iface, real_iface))

            if pif['ip_configuration_mode'] == 'Static':
                for p in ('IP', 'gateway', 'netmask'):
                    if pif.get(p, '') == '':
                        logger.error(p.capitalize()+" parameter missing for static network configuration")
                        return False
                config_str = "static:ip=%s;netmask=%s;gateway=%s" % (pif['IP'], pif['netmask'], pif['gateway'])
                if not re.match(r'(\d+\.){3}\d+', host) and pif.get('DNS', '') == '':
                    logger.error("DNS parameter missing for static network configuration")
                    return False
                if  pif.get('DNS', '') != '':
                    config_str += ";dns=" + pif['DNS']
                kernel_args.extend(['network_device='+mac,
                                'network_config='+config_str])
            else:
                kernel_args.append('network_device=' + mac)
            kernel_args.append("map_netdev=%s:d:%s" % (real_iface, mac))

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

        try:
            # determine if boot from SAN
            f = open('/etc/firstboot.d/data/sr-multipathing.conf')
            for l in f:
                line = l.strip()
                if line.startswith('MULTIPATHING_ENABLED='):
                    bfs = shell_value(line)
                    if bfs == 'True':
                        kernel_args.append("device_mapper_multipath=true")
                        logger.debug("Multipathing enabled")
                    break
            f.close()
        except:
            logger.error("Failed to read SR multipathing config")

        root_label, _ = get_fs_labels()
        if not root_label:
            logger.error("Failed to determine root label")
            return False

        e = bootloader.MenuEntry(hypervisor = installer_dir+'/xen.gz', hypervisor_args = ' '.join(xen_args),
                                 kernel = installer_dir+'/vmlinuz', kernel_args = ' '.join(kernel_args),
                                 initrd = installer_dir+'/upgrade.img', title = 'Rolling pool upgrade')
        e.root = root_label
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
    repo_ver = None
    try:
        a = accessor.createAccessor(url, True)
        if not test_boot_files(a):
            return TEST_URL_INVALID
        logger.debug("Boot files ok, testing repository...")
        repo_ver = get_repo_ver(a)
    except Exception, e:
        logger.error(str(e))
        return TEST_URL_INVALID
    if not repo_ver:
        logger.error("Unable to determine repository version")
        return TEST_URL_INVALID

    # read current host version
    curr_ver = None
    try:
        i = open('/etc/xensource-inventory')
        for l in i:
            line = l.strip()
            if line.startswith('PRODUCT_VERSION='):
                curr_ver = version.Version.from_string(shell_value(line))
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
        done = gen_answerfile(a, installer_dir, url)
        
    if done:
        # create bootloader entry
        done = set_boot_config(installer_dir, url)
        
    if not done:
        try:
            shutil.rmtree(installer_dir)
        except:
            pass
    return done

def testSafe2Upgrade(session, args):
    return safe2upgrade()

# plugin safe upgrade test
def safe2upgrade():

    fh = open('/etc/xensource-inventory')
    for l in fh:
        line = l.strip()
        k, v = line.split('=', 1)
        if k == 'PRIMARY_DISK':
            primary_disk = v.strip("'")
            break
    fh.close()

    session = XenAPI.xapi_local()
    session.xenapi.login_with_password('', '')

    this_host = session.xenapi.session.get_this_host(session._session)

    (rc, out) = cmd.runCmd(['grep', '-q', '/var/log', '/proc/mounts'], with_stdout = True)
    if rc == 0:
        return 'true'

    local_sr = None
    for pbd in session.xenapi.PBD.get_all_records().values():
        if pbd.get('host', '') != this_host:
            continue
        if not pbd.get('currently_attached', False):
            continue
        devconf = pbd.get('device_config', {})
        if not devconf.get('device', '').startswith(primary_disk):
            continue
        local_sr = pbd['SR']
        break

    if local_sr == None:
        logger.debug("No PBD found")
        return 'true'
    else:
        logger.debug("PBD: " + local_sr)

    local_sr_size = session.xenapi.SR.get_physical_size(local_sr)
    logger.debug("PBD size: %s" % local_sr_size)
    if int(local_sr_size) < min_upgrade_lvm_part_size:
        logger.debug("PBD size smaller than minimum required")
        return 'not_enough_space'

    vdi_num = 0
    for vdi in session.xenapi.VDI.get_all_records().values():
        if vdi.get('SR', '') != local_sr:
            continue
        vdi_num += 1
    logger.debug("Number of VDIs: %d" % vdi_num)

    return vdi_num == 0 and 'true' or 'false'

# plugin url test
def testUrl(session, args):
    if os.path.exists('/var/tmp/plugin_debug'):
        logger.logToSyslog(level = logging.DEBUG)
    else:
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
    if os.path.exists('/var/tmp/plugin_debug'):
        logger.logToSyslog(level = logging.DEBUG)
    else:
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

    if safe2upgrade() == 'true':
        fh = open('/var/preserve/safe2upgrade', 'w')
        fh.close()
    else:
        if os.path.isfile('/var/preserve/safe2upgrade'):
            os.remove('/var/preserve/safe2upgrade')

    logger.info("Preparation succeeded, ready for upgrade.")
    return "true"


if __name__ == '__main__':
    XenAPIPlugin.dispatch({"main": main,
                           "testUrl": testUrl,
                           "testSafe2Upgrade": testSafe2Upgrade})
