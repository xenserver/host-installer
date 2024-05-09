#!/usr/bin/env python

# SPDX-License-Identifier: GPL-2.0-only

import os
import shutil
import sys
import fcntl
import datetime
import traceback
import constants


def collectLogs(dst, tarball_dir=None):
    """ Make a support tarball including all logs (and some more) from 'dst'."""
    os.system("cat /proc/bus/pci/devices >%s/pci-log 2>&1" % dst)
    os.system("lspci -i /usr/share/misc/pci.ids -vv >%s/lspci-log 2>&1" % dst)
    os.system("lspci -n >%s/lspcin-log 2>&1" % dst)
    os.system("cat /proc/modules >%s/modules-log 2>&1" % dst)
    os.system("cat /proc/interrupts >%s/interrupts-log 2>&1" % dst)
    os.system("uname -a >%s/uname-log 2>&1" % dst)
    os.system("ls /sys/block >%s/blockdevs-log 2>&1" % dst)
    os.system("ls -lR /dev >%s/devcontents-log 2>&1" % dst)
    os.system("tty >%s/tty-log 2>&1" % dst)
    os.system("cat /proc/cmdline >%s/cmdline-log 2>&1" % dst)
    os.system("dmesg >%s/dmesg-log 2>&1" % dst)
    os.system("xl dmesg >%s/xl-dmesg-log 2>&1" % dst)
    os.system("ps axf >%s/processes-log 2>&1" % dst)
    os.system("vgscan -P >%s/vgscan-log 2>&1" % dst)
    os.system("cat /var/log/multipathd >%s/multipathd-log 2>&1" % dst)
    os.system("rpm -qa >%s/rpm-qa-log 2>&1" % dst)

    if not tarball_dir:
        tarball_dir = dst

    if dst != '/tmp':
        if os.path.exists("/tmp/install-log"):
            shutil.copy("/tmp/install-log", dst)
        if os.path.exists(constants.SCRIPTS_DIR):
            os.system("cp -r "+constants.SCRIPTS_DIR+" %s/" % dst)
    logs = [x for x in os.listdir(dst) if x.endswith('-log') or x == 'answerfile' or
                  x.startswith(os.path.basename(constants.SCRIPTS_DIR))]
    logs = " ".join(logs)

    if os.path.exists(tarball_dir):
        # tar up contents
        os.system("tar -C %s -cjf %s/support.tar.bz2 %s" % (dst, tarball_dir, logs))

def main():
    collectLogs("/tmp")

if __name__ == "__main__":
    main()
