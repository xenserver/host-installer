# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# User interface controller
#
# written by Andrew Peace

import xelogging

SKIP_SCREEN = -100
EXIT = -101
LEFT_BACKWARDS = -1

class Step:
    def __init__(self, fn, args = [], predicate = lambda x: True):
        self.fn = fn
        self.args = args
        self.predicate = predicate

    def execute(self, answers):
        assert callable(self.predicate)
        assert callable(self.fn)
        if self.predicate(answers):
            return self.fn(answers, *self.args)
        else:
            xelogging.log("Not displaying screen %s due to predicate return false." % self.fn)
            return SKIP_SCREEN

def runSequence(seq, answers, previous_delta = 1):
    assert type(seq) == list
    assert type(answers) == dict
    assert len(seq) > 0

    if previous_delta == 1:
        current = 0
    else:
        current = len(seq) -1
    delta = 1

    while current < len(seq) and current >= 0:
        previous_delta = delta
        delta = seq[current].execute(answers)

        if delta == SKIP_SCREEN:
            delta = previous_delta
        if delta == EXIT:
            break
        current += delta

    return delta

# Leave old version here for now.
def runUISequence(seq, answers, previous_delta = 1):
    assert type(seq) == list
    assert type(answers) == dict
    assert len(seq) > 0

    if previous_delta == 1:
        current = 0
    else:
        current = len(seq) -1
    delta = 1

    while current < len(seq) and current >= 0:
        if type(seq[current]) == tuple:
            (fn, args) = seq[current]
        else:
            fn = seq[current]
            args = ()

        previous_delta = delta
        delta = fn(answers, *args)

        if delta == SKIP_SCREEN:
            delta = previous_delta
        if delta == EXIT:
            break
        current += delta

    return delta
