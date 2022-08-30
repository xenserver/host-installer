# SPDX-License-Identifier: GPL-2.0-only

from xcp import logger

SKIP_SCREEN = -100
EXIT = -101
LEFT_BACKWARDS = -1
RIGHT_FORWARDS =  1
REPEAT_STEP =  0

class Step:
    def __init__(self, fn, args=[], predicates=[]):
        self.fn = fn
        self.args = args
        self.predicates = predicates

    def execute(self, answers):
        assert type(self.predicates) == list
        assert False not in [callable(x) for x in self.predicates]
        assert callable(self.fn)
        if False not in [x(answers) for x in self.predicates]:
            logger.log("Displaying screen %s" % self.fn)
            return self.fn(answers, *self.args)
        else:
            logger.log("Not displaying screen %s due to predicate return false." % self.fn)
            return SKIP_SCREEN

def runSequence(seq, answers, previous_delta=1):
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

