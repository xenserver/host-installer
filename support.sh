#!/bin/bash

# SPDX-License-Identifier: GPL-2.0-only

SUPPORT_FILE="/tmp/support.tar.bz2"
echo "Collecting logs for submission to Technical Support..."
/usr/bin/python3 /opt/xensource/installer/xelogging.py
echo
echo "Logfiles have been collected. You can find them in ${SUPPORT_FILE}:"
echo
ls -la ${SUPPORT_FILE}
echo
echo "The contents of ${SUPPORT_FILE}:"
echo
tar jtvf ${SUPPORT_FILE}

