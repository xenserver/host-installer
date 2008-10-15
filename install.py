#!/usr/bin/env python
# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN HOST INSTALLER
# Main script
#
# written by Andrew Peace

import os
import sys
import traceback
import re

# user-interface stuff:
import tui.installer
import tui.installer.screens
import tui.progress
import util
import answerfile
import uicontroller
import constants
import init_constants

# hardware
import diskutil
import netutil
import hardware

# backend
import backend
import product
import upgrade

# general
import xelogging

def main(args):
    ui = tui
    xelogging.log("Starting user interface")
    ui.init_ui()
    status = go(ui, args)
    xelogging.log("Shutting down user interface")
    ui.end_ui()
    return status

def go(ui, args, answerfile_address):
    extra_repo_defs = []
    results = {
        'keymap': None, 
        'serial-console': None,
        'operation': init_constants.OPERATION_INSTALL,
        'boot-serial': False
        }
    suppress_extra_cd_dialog = False
    serial_console = None
    boot_console = None
    boot_serial = False

    for (opt, val) in args.items():
        if opt == "--boot-console":
            # takes precedence over --console
            if val.startswith('ttyS'):
                boot_console = val
        elif opt == "--console":
            for console in val:
                if console.startswith('ttyS'):
                    serial_console = console
            if val[-1].startswith('ttyS'):
                boot_serial = True
        elif opt == "--keymap":
            results["keymap"] = val
            xelogging.log("Keymap specified on command-line: %s" % val)
        elif opt == "--extrarepo":
            for v in val:
                if not os.path.isdir(v):
                    raise RuntimeError, "Repository %s did not exist." % v
                else:
                    extra_repo_defs.append(('filesystem', v))
        elif opt == "--bootloader":
            xelogging.log("Bootloader specified on command-line: %s" % val)
            if val == "grub":
                results['bootloader'] = constants.BOOTLOADER_TYPE_GRUB
            elif val == "extlinux":
                results['bootloader'] = constants.BOOTLOADER_TYPE_EXTLINUX
        elif opt == "--install-xen64":
            xelogging.log("Installing xen64 package")
            results['install-xen64'] = True
        elif opt == "--onecd":
            suppress_extra_cd_dialog = True

    if boot_console and not serial_console:
        serial_console = boot_console
        boot_serial = True
    if serial_console:
        try:
            serial = {'baud': '9600', 'data': '8', 'parity': 'n', 'stop': '1', 'term': 'vt102'}
            param = serial_console.split(',')
            dev = param[0]
            if len(param) == 2:
                pdict = re.match(r'(?P<baud>\d+)(?P<parity>[noe])?(?P<data>\d)?r?', 
                                 param[1]).groupdict()
                for (k, v) in pdict.items():
                    if v != None:
                        serial[k] = v
            n = int(dev[4:])+1
            serial['port'] = (dev, "com%d" % n)
            if args.has_key('term'):
                serial['term'] = args['term']
            results['serial-console'] = serial
            results['boot-serial'] = boot_serial
            xelogging.log("Serial console specified on command-line: %s, default boot: %s" % 
                          (serial_console, boot_serial))
        except:
            pass

    try:
        # loading an answerfile?
        assert ui != None or answerfile_address != None

        if answerfile_address:
            results.update(answerfile.processAnswerfile(answerfile_address))

        results['extra-repos'] = extra_repo_defs

        # log the modules that we loaded:
        xelogging.log("All needed modules should now be loaded. We have loaded:")
        util.runCmd2(["/bin/lsmod"])

        status = constants.EXIT_OK

        disks = diskutil.getQualifiedDiskList()
        nethw = netutil.scanConfiguration()        

        # make sure we have discovered at least one disk and
        # at least one network interface:
        if len(disks) == 0:
            raise RuntimeError, "No disks found on this host."

        if len(nethw.keys()) == 0:
            raise RuntimeError, "No network interfaces found on this host."

        # record the network configuration at startup so it remains consistent
        # in the face of kudzu:
        results['network-hardware'] = nethw

        # make sure that we have enough disk space:
        xelogging.log("Found disks: %s" % str(disks))
        diskSizes = [diskutil.getDiskDeviceSize(x) for x in disks]
        diskSizesGB = [diskutil.blockSizeToGBSize(x) for x in diskSizes]
        xelogging.log("Disk sizes: %s" % str(diskSizesGB))

        dom0disks = filter(lambda x: constants.min_primary_disk_size <= x <= constants.max_primary_disk_size,
                           diskSizesGB)
        if len(dom0disks) == 0:
            raise RuntimeError, "Unable to find a suitable disk (with a size between %dGB and %dGB) to install to." % (constants.min_primary_disk_size, constants.max_primary_disk_size)

        # how much RAM do we have?
        ram_found_mb = hardware.getHostTotalMemoryKB() / 1024
        ram_warning = ram_found_mb < constants.MIN_SYSTEM_RAM_MB
        vt_warning = not hardware.VTSupportEnabled()

        # find existing installations:
        if ui:
            ui.progress.showMessageDialog("Please wait", "Checking for existing products...")
        try:
            all_installed_products = product.findXenSourceProducts()
        except Exception, e:
            xelogging.log("A problem occurred whilst scanning for existing installations:")
            ex = sys.exc_info()
            err = str.join("", traceback.format_exception(*ex))
            xelogging.log(err)
            xelogging.log("This is not fatal.  Continuing anyway.")
            all_installed_products = []
        installed_products = filter(lambda p: upgrade.upgradeAvailable(p),
                                    all_installed_products)
        if ui:
            ui.progress.clearModelessDialog()
        
        # Generate the UI sequence and populate some default
        # values in backend input.  Note that not all these screens
        # will be displayed as they have conditional to skip them at
        # the start of each function.  In future these conditionals will
        # be moved into the sequence definition and evaluated by the
        # UI dispatcher.
        aborted = False
        if ui and not answerfile_address:
            uiexit = ui.installer.runMainSequence(
                results, ram_warning, vt_warning, installed_products, all_installed_products, suppress_extra_cd_dialog
                )
            if uiexit == uicontroller.EXIT:
                aborted = True

        if not aborted:
            xelogging.log("Starting actual installation")       
            backend.performInstallation(results, ui)

            if ui and not answerfile_address:
                ui.installer.screens.installation_complete()
            
            xelogging.log("The installation completed successfully.")
        else:
            xelogging.log("The user aborted the installation from within the user interface.")
            status = constants.EXIT_USER_CANCEL
    except Exception, e:
        # first thing to do is to get the traceback and log it:
        ex = sys.exc_info()
        err = str.join("", traceback.format_exception(*ex))
        xelogging.log("INSTALL FAILED.")
        xelogging.log("A fatal exception occurred:")
        xelogging.log(err)

        # now write out logs where possible:
        xelogging.writeLog("/tmp/install-log")

        # collect logs where possible
        xelogging.collectLogs("/tmp")

        # now display a friendly error dialog:
        if ui:
            ui.exn_error_dialog("install-log", True)
        else:
            txt = constants.error_string(str(e), 'install-log', True)
            xelogging.log(txt)

        # and now on the disk if possible:
        if results.has_key('primary-disk'):
            backend.writeLog(results['primary-disk'])

        # exit with failure status:
        status = constants.EXIT_ERROR

    else:
        # put the log in /tmp:
        xelogging.writeLog("/tmp/install-log")
        xelogging.collectLogs('/tmp')

        # and now on the disk if possible:
        if results.has_key('primary-disk'):
            backend.writeLog(results['primary-disk'])

        assert (status == constants.EXIT_OK or status == constants.EXIT_USER_CANCEL)

    return status

if __name__ == "__main__":
    sys.exit(main(util.splitArgs(sys.argv[1:])))
