# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this
# copyrighted material is governed by and subject to terms and conditions
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Constants for use only by boot script
#
# written by Andrew Peace

OPERATION_REBOOT = -1
(
    OPERATION_NONE,
    OPERATION_INSTALL,
    OPERATION_UPGRADE,
    OPERATION_LOAD_DRIVER,
    OPERATION_RESTORE,
    OPERATION_P2V,
    OPERATION_INSTALL_OEM_TO_FLASH,
    OPERATION_INSTALL_OEM_TO_FLASH_CUSTOM,
    OPERATION_INSTALL_OEM_TO_DISK,
    OPERATION_INSTALL_OEM_TO_DISK_CUSTOM,
    OPERATION_RESET_PASSWORD,
    OPERATION_RESET_STATE_PARTITION
) = range(12)

# THIS IS ONLY USED FOR OEM A.T.M. 
# TODO rationalise with retail 
HW_CONFIG_COMPLETED_STAMP = "/tmp/.hw-config-completed.stamp"

# Derived properties of constants
def operationIsOEMInstall(operation):
    return operation in [
        OPERATION_INSTALL_OEM_TO_FLASH,
        OPERATION_INSTALL_OEM_TO_FLASH_CUSTOM,
        OPERATION_INSTALL_OEM_TO_DISK,
        OPERATION_INSTALL_OEM_TO_DISK_CUSTOM
    ]

def operationIsOEMHDDInstall(operation):
    return operation in [
        OPERATION_INSTALL_OEM_TO_DISK,
        OPERATION_INSTALL_OEM_TO_DISK_CUSTOM
    ]
