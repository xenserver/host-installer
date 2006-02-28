#!/usr/bin/env python
###
# XEN CLEAN INSTALLER
# Logging functions
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

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
