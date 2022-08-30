# SPDX-License-Identifier: GPL-2.0-only

# Constants for use only by boot script

OPERATION_REBOOT = -1
(
    OPERATION_NONE,
    OPERATION_INSTALL,
    OPERATION_UPGRADE,
    OPERATION_LOAD_DRIVER,
    OPERATION_RESTORE,
) = range(5)
