#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Logging functions
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

import os

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
    os.system("cat /proc/modules >%s/modules-log" % dir)
    os.system("uname -a >%s/uname-log" % dir)
    os.system("ls /sys/block >%s/blockdevs-log" % dir)
    os.system("ls /dev >%s/devcontents-log" % dir)
    os.system("tty >%s/tty-log" % dir)
    os.system("cat /proc/cmdline >%s/cmdline-log" % dir)
    os.system("dmesg >%s/dmesg-log" % dir)
    os.system("ps axf >%s/processes-log" % dir)
    os.system("vgscan -P >%s/vgscan-log" % dir)

    # tar up contents
    os.system("tar -cjf %s/support.tar.bz2 %s/*-log" % (dir, dir))
