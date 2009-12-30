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
import sys
import fcntl
import datetime
import traceback
import constants

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

def log_exception(e):
    """ Formats exception and logs it """
    ex = sys.exc_info()
    err = traceback.format_exception(*ex)
    errmsg = "\n".join([ str(x) for x in e.args ])

    # print the exception args nicely
    log(errmsg)

    # now print the traceback
    for exline in err:
        log(exline)

def writeLog(destination):
    """ Write the log as it stands to 'destination'. """
    global __log__
    
    dfd = open(destination, "w")
    dfd.write(__log__)
    dfd.close()

def collectLogs(dst, tarball_dir = None):
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

    if not tarball_dir:
        tarball_dir = dst

    # now, try to get the startup-log (it won't be in the same directory
    # most likely, but check in case):
    if not os.path.exists("%s/startup-log" % dst):
        # it didn't exist, so we need to try and fetch it -it ought to be in
        # /tmp:
        if os.path.exists("/tmp/startup-log"):
            os.system("cp /tmp/startup-log %s/" % dst)
    if dst != '/tmp':
        if os.path.exists(constants.SCRIPTS_DIR):
            os.system("cp -r "+constants.SCRIPTS_DIR+" %s/" % dst)
    logs = filter(lambda x: x.endswith('-log') or x == 'answerfile' or
                  x.startswith(os.path.basename(constants.SCRIPTS_DIR)), os.listdir(dst))
    logs = " ".join(logs)

    if os.path.exists(tarball_dir):
        # tar up contents
        os.system("tar -C %s -cjf %s/support.tar.bz2 %s" % (dst, tarball_dir, logs))

def openLog(lfile):
    if hasattr(lfile, 'name'):
        # file object
        continuous_logs.append(lfile)
    else:
        try:
            f = open(lfile, 'w', 1)
            continuous_logs.append(f)
            # set close-on-exec
            old = fcntl.fcntl(f.fileno(), fcntl.F_GETFD)
            fcntl.fcntl(f.fileno(), fcntl.F_SETFD, old | fcntl.FD_CLOEXEC)
        except:
            log("Error opening %s as a log output." % lfile)
            return False
    return True

def closeLogs():
    for fd in continuous_logs:
        if not fd.name.startswith('<'):
            fd.close()


def main():
    collectLogs("/tmp")
    
if __name__ == "__main__":
    main()
 
