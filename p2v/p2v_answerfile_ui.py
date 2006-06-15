#!/usr/bin/python
###
# XEN CLEAN INSTALLER
# Text user interface functions
#
# written by Mark Nijmeijer and Andrew Peace
# Copyright XenSource Inc. 2006

from snack import *
from version import *
import p2v_uicontroller
import findroot
import os
import sys
import p2v_constants
import p2v_utils
import p2v_backend
import time
import xelogging
import util

from p2v_error import P2VMountError

from xml.dom.minidom import parse

answerFile = None
sub_ui_package = None

# functions to start and end the GUI - these create and destroy a snack screen as
# appropriate.
def specifyAnswerFile(file):
    global answerFile
    assert type(file) == str

    util.fetchFile(file, "/tmp/pyanswerfile")
    answerFile = "/tmp/pyanswerfile"
    print "answerFile = %s" % answerFile

def specifySubUI(subui):
    global sub_ui_package
    sub_ui_package = subui


def init_ui(results):
    global answerFile

    # attempt to import the answers:
    try:
        print "answerFile = %s" % answerFile
        answerdoc = parse(answerFile)
        # this function transforms 'results' that we pass in
        __parse_answerfile__(answerdoc, results)
    except Exception, e:
        xelogging.log("Error parsing answerfile.")
        raise
    
    # Now pass on initialisation to our sub-UI:
    if sub_ui_package is not None:
        sub_ui_package.init_ui()

# get data from a DOM object representing the answerfile:
def __parse_answerfile__(answerdoc, results):
    # get text from a node:
    def getText(nodelist):
        rc = ""
        for node in nodelist:
            if node.nodeType == node.TEXT_NODE:
                rc = rc + node.data
        return rc

    def getValue(n, key):
        es = n.getElementsByTagName(key)
        if len(es) > 0:
            return getText(es[0].childNodes)
        else:
            return None

    n = answerdoc.documentElement

    keyList = [ p2v_constants.XEN_TARGET,
                p2v_constants.XE_HOST,
                p2v_constants.NFS_HOST,
                p2v_constants.NFS_PATH ]

    for key in keyList:
        r = getValue(n, key)
        if r is not None:
            results[key] = r
            print key + " = " + results[key]
        else:
            print key + " not found."

    keyList = [ p2v_constants.UUID,
                p2v_constants.DESCRIPTION,
                p2v_constants.HOST_NAME,
                p2v_constants.OS_NAME,
                p2v_constants.OS_VERSION,
                p2v_constants.ROOT_PASSWORD,
                p2v_constants.FS_USED_SIZE,
                p2v_constants.FS_TOTAL_SIZE,
                p2v_constants.CPU_COUNT,
                p2v_constants.TOTAL_MEM,
                p2v_constants.P2V_PATH,
                p2v_constants.DEV_NAME,
                p2v_constants.XEN_TAR_FILENAME,
                p2v_constants.XEN_TAR_DIRNAME,
                p2v_constants.XEN_TAR_MD5SUM ]

    os_install_node = n.getElementsByTagName(p2v_constants.OS_INSTALL)
    results[p2v_constants.OS_INSTALL] = {}
    for os_install in os_install_node:
        for key in keyList:
            r = getValue(n, key)
            if r is not None:
                results[p2v_constants.OS_INSTALL][key] = r
                print "  " + key + " = " + results[p2v_constants.OS_INSTALL][key]
            else:
                print key + " not found."

        keyList = [ p2v_constants.DEV_ATTRS_TYPE,
                    p2v_constants.DEV_ATTRS_PATH,
                    p2v_constants.DEV_ATTRS_LABEL ]

        dev_attr_node = os_install.getElementsByTagName(p2v_constants.DEV_ATTRS)
        print "dan = " + str(len(dev_attr_node))
        for dev_attr in dev_attr_node:
             for key in keyList:
                r = getValue(n, key)
                if r is not None:
                    results[p2v_constants.OS_INSTALL][p2v_constants.DEV_ATTRS] = {}
                    results[p2v_constants.OS_INSTALL][p2v_constants.DEV_ATTRS][key] = r
                    print "    " + key + " = " + results[p2v_constants.OS_INSTALL][p2v_constants.DEV_ATTRS][key]
                else:
                    print key + " not found."

       

  
def redraw_screen():
    pass
    
def end_ui():
    if sub_ui_package:
        sub_ui_package.end_ui()

def suspend_ui():
    pass
        
def resume_ui():
    pass

#   The screens
def welcome_screen(answers):
    return 1

def target_screen(answers):
    return 1

def os_install_screen(answers):
    return 1

def description_screen(answers):
    return 1

def size_screen(answers):
    return 1

def get_root_password(answers):
    return 1

def finish_screen(answers):
    return 1
    
def failed_screen(answers):
    return 1

# Progress dialog:
def initProgressDialog(title, text, total):
    pass

def displayProgressDialog(current, pd, t2_text = ""):
    pass

def clearProgressDialog():
    pass
