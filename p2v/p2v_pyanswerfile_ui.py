#!/usr/bin/python
# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Text user interface functions
#
# written by Mark Nijmeijer and Andrew Peace

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

from p2v_error import P2VMountError

pyAnswerFile = None

# functions to start and end the GUI - these create and destroy a snack screen as
# appropriate.
def specifyAnswerFile(file):
    global pyAnswerFile
    assert type(file) == str

    util.fetchFile(file, "/tmp/pyanswerfile")
    pyAnswerFile = "/tmp/pyanswerfile"

def init_ui(results):
    if pyAnswerFile is not None:
        fd = open (pyAnswerFile, 'r')
        answers = pickle.load(fd)
        fd.clouse()

    for key in answers:
        results[key] = answers[key]
    
def redraw_screen():
    pass
    
def end_ui():
    pass

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

def displayProgressDialog(current, (form, scale, t2), t2_text = ""):
    pass

def clearProgressDialog():
    pass

def displayButtonChoiceWindow(screen, title, text, 
		       buttons = [ 'Ok', 'Cancel' ], 
		       width = 40, x = None, y = None, help = None):
    pass
 
