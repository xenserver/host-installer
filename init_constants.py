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
    OPERATION_INSTALL_OEM_TO_DISK,
    OPERATION_RESET_PASSWORD
) = range(9)

# THIS IS ONLY USED FOR OEM A.T.M. 
# TODO rationalise with retail 
HW_CONFIG_COMPLETED_STAMP = "/tmp/.hw-config-completed.stamp"
