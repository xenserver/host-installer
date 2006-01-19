###
# XEN CLEAN INSTALLER
# User interface controller
#
# written by Andrew Peace
# Copyright XenSource Inc. 2006

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
        current += delta

    return delta
