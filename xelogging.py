#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Logging functions
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import os
import util

continuous_logs = []
__log__ = ""

def log(txt):
    global __log__

    txt = "* %s\n" % txt
    __log__ += txt

    for fd in continuous_logs:
        fd.write(txt)
        fd.flush()

def logOutput(header, txt):
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
    global __log__
    
    dfd = open(destination, "w")
    dfd.write(__log__)
    dfd.close()

def collectLogs(dir):
    os.system("cat /proc/bus/pci/devices >%s/pci-log" % dir)
    os.system("lspci -i /usr/share/misc/pci.ids -vv >%s/lspci-log" % dir)
    os.system("cat /proc/modules >%s/modules-log" % dir)
    os.system("uname -a >%s/uname-log" % dir)
    os.system("ls /sys/block >%s/blockdevs-log" % dir)
    os.system("ls /dev >%s/devcontents-log" % dir)
    os.system("tty >%s/tty-log" % dir)
    os.system("cat /proc/cmdline >%s/cmdline-log" % dir)
    os.system("dmesg >%s/dmesg-log" % dir)
    os.system("ps axf >%s/processes-log" % dir)
    os.system("vgscan -P >%s/vgscan-log 2>&1" % dir)

    # now, try to get the startup-log (it won't be in the same directory
    # most likely, but check in case):
    if not os.path.exists("%s/startup-log" % dir):
        # it didn't exist, so we need to try and fetch it -it ought to be in
        # /tmp:
        if os.path.exists("/tmp/startup-log"):
            os.system("cp /tmp/startup-log %s/" % dir)

    logs = filter(lambda x: x.endswith('-log'), os.listdir(dir))
    logs = " ".join(logs)

    # tar up contents
    os.system("tar -C %s -cjf %s/support.tar.bz2 %s" % (dir, dir, logs))


def main():
    collectLogs("/tmp")
    
if __name__ == "__main__":
    main()
 
