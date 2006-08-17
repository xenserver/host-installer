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

# this will transform dict according to user input and will return a value
# indication the mode of exit:
#  0 == OK
#  1 == Cancel selected
def runUISequence(seq, answers):
    assert type(seq) == list
    assert type(answers) == dict
    assert len(seq) > 0

    current = 0
    delta = 0

    while current < len(seq) and current >= 0:
        if type(seq[current]) == tuple:
            (fn, args) = seq[current]
        else:
            fn = seq[current]
            args = None

        if args == None:
            delta = fn(answers)
        else:
            delta = fn(answers, args)
        if (delta == -2):
            return -1
        current += delta

    return delta
