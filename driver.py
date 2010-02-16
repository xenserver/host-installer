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

import sys

# user-interface stuff:
from snack import *
import tui.installer
import tui.installer.screens
import tui.progress
import util

# backend
import repository

# general
from version import *
import xelogging

def doInteractiveLoadDriver(ui, answers):
    media = None
    address = None
    required_repo_list = []
    loaded_drivers = []

    rc = ui.init.driver_disk_sequence(answers, answers['driver-repos'], answers['loaded-drivers'])
    if rc:
        media, address = rc
        repos = repository.repositoriesFromDefinition(media, address)
        compat_driver = False

        # now load the drivers:
        for r in repos:
            for p in r:
                if p.type.startswith('driver') and p.is_loadable():
                    if p.name not in answers['loaded-drivers']:
                        compat_driver = True
                        if p.load() == 0:
                            loaded_drivers.append(p.name)
                            if r not in required_repo_list:
                                required_repo_list.append(r)
                        else:
                            ButtonChoiceWindow(
                                ui.screen,
                                "Problem Loading Driver",
                                "Setup was unable to load the device driver %s." % p.name,
                                ['Ok']
                                )

        if not compat_driver:
            ButtonChoiceWindow(
                ui.screen,
                "No Compatible Drivers",
                "Setup was unable to find any drivers compatible with this version of %s." % PRODUCT_BRAND,
                ['Ok']
                )
        elif len(loaded_drivers) > 0:
            answers['loaded-drivers'] += loaded_drivers
            answers['driver-repos'] += map(lambda r: str(r), required_repo_list)
            text = "The following drivers were successfully loaded:\n\n"

            for dr in loaded_drivers:
                text += " * %s\n" % dr

                ButtonChoiceWindow(
                    ui.screen,
                    "Drivers Loaded",
                    text,
                    ['Ok'])

    return media, address, required_repo_list

def main(args):
    if len(doInteractiveLoadDriver(tui, {})) > 0:
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main(util.splitArgs(sys.argv[1:])))
