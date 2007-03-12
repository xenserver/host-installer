# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Logging functions
#
# written by Andrew Peace

import os
import util
import datetime

continuous_logs = []
__log__ = ""

def log(txt):
    """ Write txt to the log. """

    global __log__

    prefix = '[%s]' % str(datetime.datetime.now().replace(microsecond=0))

    txt = "%s %s\n" % (prefix, txt)
    __log__ += txt

    for fd in continuous_logs:
        fd.write(txt)
        fd.flush()

def logOutput(header, txt):
    """ Add header,txt to the log, treating them as output from execution of a
    command, and so formatting them appropraitely. """

    global __log__

    if txt == "":
        txt = "* NO OUTPUT: %s.\n" % header
    else:
        txt = "* START OUTPUT: %s\n%s\n* END OUTPUT: %s\n\n" % (header, txt, header)
    __log__ += txt

    for fd in continuous_logs:
        fd.write(txt)
        fd.flush()

def writeLog(destination):
    """ Write the log as it stands to 'destination'. """

    global __log__
    
    dfd = open(destination, "w")
    dfd.write(__log__)
    dfd.close()

def collectLogs(dst):
    """ Make a support tarball including all logs (and some more) from 'dst'."""

    os.system("cat /proc/bus/pci/devices >%s/pci-log" % dst)
    os.system("lspci -i /usr/share/misc/pci.ids -vv >%s/lspci-log" % dst)
    os.system("lspci -n >%s/lspcin-log" % dst)
    os.system("cat /proc/modules >%s/modules-log" % dst)
    os.system("uname -a >%s/uname-log" % dst)
    os.system("ls /sys/block >%s/blockdevs-log" % dst)
    os.system("ls /dev >%s/devcontents-log" % dst)
    os.system("tty >%s/tty-log" % dst)
    os.system("cat /proc/cmdline >%s/cmdline-log" % dst)
    os.system("dmesg >%s/dmesg-log" % dst)
    os.system("ps axf >%s/processes-log" % dst)
    os.system("vgscan -P >%s/vgscan-log 2>&1" % dst)

    # now, try to get the startup-log (it won't be in the same dstectory
    # most likely, but check in case):
    if not os.path.exists("%s/startup-log" % dst):
        # it didn't exist, so we need to try and fetch it -it ought to be in
        # /tmp:
        if os.path.exists("/tmp/startup-log"):
            os.system("cp /tmp/startup-log %s/" % dst)

    logs = filter(lambda x: x.endswith('-log'), os.listdir(dst))
    logs = " ".join(logs)

    # tar up contents
    os.system("tar -C %s -cjf %s/support.tar.bz2 %s" % (dst, dst, logs))


def main():
    collectLogs("/tmp")
    
if __name__ == "__main__":
    main()
 
