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
from snack import *
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

def doInteractiveLoadDriver(ui, answers):
    driver_repos = []
    incompat_drivers = []

    rc = ui.init.driver_disk_sequence(answers)
    if rc:
        media, address = rc
        repos = repository.repositoriesFromDefinition(media, address)

        # put firmware in place:
        for r in repos:
            repo_has_drivers = False
            for p in r:
                if p.type == 'firmware':
                    p.provision()
                    repo_has_drivers = True
            if repo_has_drivers:
                driver_repos.append(r)

        # now load the drivers:
        for r in repos:
            repo_has_drivers = False
            for p in r:
                if p.type.startswith('driver'):
                    repo_has_drivers = True
                    if not p.is_compatible():
                        incompat_drivers.append(p)
                    elif p.is_loadable():
                        if not answers.has_key('loaded-drivers'):
                            answers['loaded-drivers'] = []
                        if p.name not in answers['loaded-drivers']:
                            if p.load() == 0:
                                answers['loaded-drivers'].append(p.name)
                            else:
                                repo_has_drivers = False
                                ButtonChoiceWindow(
                                    ui.screen,
                                    "Problem Loading Driver",
                                    "Setup was unable to load the device driver %s you specified." % p.name,
                                    ['Ok']
                                    )
            if repo_has_drivers:
                driver_repos.append(r)

    # stash the repositories we used for pickup later:
    dr_copies = []
    text = "The following driver disks were successfully loaded:\n\n"
    for dr in driver_repos:
        loc = tempfile.mkdtemp(prefix="stashed-repo-", dir="/tmp")
        dr.accessor().start()
        dr.copyTo(loc)
        dr.accessor().finish()
        dr_copies.append(loc)
        text += " * %s\n" % dr.name()

    if len(incompat_drivers) > 0:
        text += "\nThe following drivers are not compatible with this release but will be installed anyway:\n\n"
        for p in incompat_drivers:
            text += " * %s\n" % p.name

    if len(driver_repos) > 0:
        ButtonChoiceWindow(
            ui.screen,
            "Drivers Loaded",
            text,
            ['Ok'])

    return dr_copies

def main(args):
    if len(doInteractiveLoadDriver(tui, {})) > 0:
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main(util.splitArgs(sys.argv[1:])))
