#!/usr/bin/env python
# Copyright (c) Citrix Systems 2010.  All rights reserved.
# Xen, the Xen logo, XenCenter, XenMotion are trademarks or registered
# trademarks of Citrix Systems, Inc., in the United States and other
# countries.

import os
import os.path
import sys

import xcp.accessor
import xcp.logger

import product
import util
import xelogging


def bugtool(inst, dest_url):
    try:
        inst.mount_root(ro = False)

        util.bindMount('/dev', os.path.join(inst.root_fs.mount_point, 'dev'))
        util.bindMount('/proc', os.path.join(inst.root_fs.mount_point, 'proc'))
        util.bindMount('/sys', os.path.join(inst.root_fs.mount_point, 'sys'))

        os.environ['XEN_RT'] = '1'
        os.environ['XENRT_BUGTOOL_BASENAME'] = 'offline-bugtool'
        util.runCmd2(['chroot', inst.root_fs.mount_point, '/usr/sbin/xen-bugtool', '-y', '--unlimited'])
        out_fname = os.path.join(inst.root_fs.mount_point, 'var/opt/xen/bug-report/offline-bugtool.tar.bz2')

        util.umount(os.path.join(inst.root_fs.mount_point, 'sys'))
        util.umount(os.path.join(inst.root_fs.mount_point, 'proc'))
        util.umount(os.path.join(inst.root_fs.mount_point, 'dev'))

        xcp.logger.log("Saving to " + dest_url)
        a = xcp.accessor.createAccessor(dest_url, False)
        a.start()
        inh = open(out_fname)
        a.writeFile(inh, 'offline-bugtool.tar.bz2')
        inh.close()
        a.finish()

        os.remove(out_fname)
    finally:
        inst.unmount_root()

def main(dest_url):
    xcp.logger.openLog(sys.stdout)
    xelogging.openLog(sys.stdout)

    # probe for XS installations
    insts = product.findXenSourceProducts()
    if len(insts) == 0:
        xcp.logger.log("No XenServer installations found.")
        return

    # Locate destination dir
    if not dest_url:
        f = open('/proc/cmdline')
        line = f.readline().strip()
        cmd_args = line.split()
        for arg in cmd_args:
            if arg.startswith('dest='):
                _, dest_url = arg.split('=', 1)
                break
        f.close()

    if not dest_url:
        xcp.logger.log("Destination directory not specified.")
        return

    for inst in insts:
        xcp.logger.log(str(inst))
        bugtool(inst, dest_url)

if __name__ == "__main__":
    main(None)
    
    # os.system('reboot')
