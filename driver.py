#!/usr/bin/env python
# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Main script
#
# written by Andrew Peace

import os
import sys
import traceback
import platform

# user-interface stuff:
import tui.installer
import tui.installer.screens
import tui.progress
import util
import answerfile
import uicontroller
import constants

# hardware
import diskutil
import netutil
import hardware

# backend
import backend
import product
import upgrade
import repository

# general
import xelogging
import tempfile
import util

def doInteractiveLoadDriver(ui):
    rc = ui.init.driver_disk_sequence()
    if rc:
        media, address = rc
        repos = repository.repositoriesFromDefinition(media, address)
        drivers = []

        # put firmware in place:
        for r in repos:
            for p in r:
                if p.type == 'firmware':
                    p.provision()

        # now load the drivers:
        drivers = []
        driver_repos = []
        for r in repos:
            r.accessor().start()
            repo_has_drivers = False
            for p in r:
                if p.type == 'driver':
                    repo_has_drivers = True
                    _, driver_file = tempfile.mkstemp(prefix="driver-", dir="/tmp")
                    p.write(driver_file)
                    drivers.append( (p.name, driver_file) )
                elif p.type == 'firmware':
                    repo_has_drivers = True
            r.accessor().finish()

            if repo_has_drivers:
                driver_repos.append(r)

        total_rc = 0
        uname_r = platform.uname()[2]
        for name, driver in drivers:
            if hardware.module_file_uname(driver) == uname_r:
                rc = hardware.modprobe_file(driver, name = name)
                total_rc += rc
            else:
                xelogging.log("Skipping load of module %s due to non-matching kernel version" % name)
        if total_rc != 0:
            ui.OKDialog("Error", "One or more of your drivers failed to load.")

        # stash the repositories we used for pickup later:
        dr_copies = []
        for dr in driver_repos:
            loc = tempfile.mkdtemp(prefix="stashed-repo-", dir="/tmp")
            dr.accessor().start()
            dr.copyTo(loc)
            dr.accessor().finish()
            dr_copies.append(loc)
        return dr_copies
    else:
        return []

def main(args):
    if len(doInteractiveLoadDriver(tui)) > 0:
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main(util.splitArgs(sys.argv[1:])))
