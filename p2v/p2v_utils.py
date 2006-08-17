# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

import sys
import re
debug = False
import xelogging

def purge_xecli_password(message):
    return re.sub("-p \S+", "-p SECRET", message)

def trace_message(message):
    if debug:
        sys.stderr.write(message)
    xelogging.log(purge_xecli_password(message))
        
def is_debug():
    return debug

def show_debug_output():
    if not debug:
        return " &> /dev/null"
    else:
        return ""
