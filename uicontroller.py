###
# XEN CLEAN INSTALLER
# User interface controller
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

def runUISequence(seq, answers, previous_delta = 1):
    assert type(seq) == list
    assert type(answers) == dict
    assert len(seq) > 0

    if previous_delta == 1:
        current = 0
    else:
        current = len(seq) -1
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
        current += delta

    return delta
