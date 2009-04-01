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
import repository
import xelogging

def main(args):
    ui = tui
    xelogging.log("Starting user interface")
    ui.init_ui()
    status = go(ui, args)
    xelogging.log("Shutting down user interface")
    ui.end_ui()
    return status

def handle_install_failure(answers):
    if answers.has_key('install-failed-script'):
        # XenRT - run failure script
        script = answers['install-failed-script']
        try:
            xelogging.log("Running script: %s" % script)
            util.fetchFile(script, "/tmp/script")
            os.chmod("/tmp/script", 0555)
            util.runCmd2(["/tmp/script"])
            os.unlink("/tmp/script")
        except Exception, e:
            print "Failed to run script: "+str(script) +': '+str(e)

def go(ui, args, answerfile_address):
    extra_repo_defs = []
    results = {
        'keymap': None, 
        'serial-console': None,
        'operation': init_constants.OPERATION_INSTALL,
        'boot-serial': False,
        'extra-repos': []
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
        elif opt == "--enable-iscsi":
            results['enable-iscsi'] = True
        

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
            a = answerfile.Answerfile(answerfile_address)
            results.update(a.parseScripts())
            results.update(a.processAnswerfile())
            if results.has_key('extra-repos'):
                # load drivers now
                for d in results['extra-repos']:
                    for r in repository.repositoriesFromDefinition(*d):
                        for p in r:
                            if p.type.startswith('driver'):
                                if p.load() != 0:
                                    raise RuntimeError, "Failed to load driver %s." % p.name

        results['extra-repos'] += extra_repo_defs
        xelogging.log("Driver repos: %s" % str(results['extra-repos']))

        # log the modules that we loaded:
        xelogging.log("All needed modules should now be loaded. We have loaded:")
        util.runCmd2(["/bin/lsmod"])

        status = constants.EXIT_OK

        nethw = netutil.scanConfiguration()        

        if len(nethw.keys()) == 0:
            raise RuntimeError, "No network interfaces found on this host."
        if len(nethw.keys()) == 1:
            if results.has_key('enable-iscsi') and results['enable-iscsi'] == True:
                raise RuntimeError, "--enable-iscsi not supported on hosts with only one network interface as an extra interface is required for iSCSI target access"

        # record the network configuration at startup so it remains consistent
        # in the face of kudzu:
        results['network-hardware'] = nethw
        
        # debug: print out what disks have been discovered
        diskutil.log_available_disks()

        # how much RAM do we have?
        ram_found_mb = hardware.getHostTotalMemoryKB() / 1024
        ram_warning = ram_found_mb < constants.MIN_SYSTEM_RAM_MB
        vt_warning = not hardware.VTSupportEnabled()

        # Generate the UI sequence and populate some default
        # values in backend input.  Note that not all these screens
        # will be displayed as they have conditional to skip them at
        # the start of each function.  In future these conditionals will
        # be moved into the sequence definition and evaluated by the
        # UI dispatcher.
        aborted = False
        if ui and not answerfile_address:
            uiexit = ui.installer.runMainSequence(
                results, ram_warning, vt_warning, suppress_extra_cd_dialog
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
        try:
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
    
            xelogging.log(results)
        except Exception, e:
            # Don't let logging exceptions prevent subsequent actions
            print 'Logging failed: '+str(e)
            
        handle_install_failure(results)

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
    sys.exit(main(util.splitArgs(sys.argv[1:], array_args = ('--extrarepo'))))
