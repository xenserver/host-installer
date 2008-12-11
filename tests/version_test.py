#!/usr/bin/env python
###
# HOST INSTALLER
# Unit tests for the Version class
#
# written by Andrew Peace
# Copyright Citrix, Inc. 2008

import sys
from framework import test, finish
from product import Version
ANY = Version.ANY


# Check equality: positive tests
test("4.0.0 = 4.0.0", Version(4, 0, 0) == Version(4, 0, 0))
test("4.0.0-1 = 4.0.0-1", Version(4, 0, 0, 1) == Version(4, 0, 0, 1))
test("4.0.0-1 = 4.0.0", Version(4, 0, 0, 1) == Version(4, 0, 0))

test("-ve 4.0.0 = 4.1.0", not (Version(4, 0, 0) == Version(4, 1, 0)))
test("-ve 4.0.0-1 = 4.0.0-2", not (Version(4, 0, 0, 1) == Version(4, 0, 0, 2)))

# Check inequality
test("3.2.0 < 4.0.0", Version(3, 2, 0) < Version(4, 0, 0))
test("3.2.0 < 3.3.0", Version(3, 2, 0) < Version(3, 3, 0))
test("3.2.0 < 3.2.1", Version(3, 2, 0) < Version(3, 2, 1))
test("3.2.0-100 < 4.0.0-100", Version(3, 2, 0, 100) < Version(4, 0, 0, 100))
test("3.2.0-100 < 4.0.0", Version(3, 2, 0, 100) < Version(4, 0, 0))

test("-ve: 3.2.0-100 < 3.2.0-100", not (Version(3, 2, 0, 100) < Version(3, 2, 0, 100)))
test("-ve: 3.2.0 < 3.1.0", not (Version(3, 2, 0) < Version(3, 1, 0)))
test("-ve: 4.2.0 < 3.1.0", not (Version(4, 2, 0) < Version(3, 1, 0)))
test("-ve: 4.0.0-100 < 3.2.0-100", not (Version(4, 0, 0, 100) < Version(3, 2, 0, 100)))
test("-ve: 4.0.0-100 < 3.2.0", not (Version(4, 0, 0, 100) < Version(3, 2, 0)))
test("-ve: 4.0.0-100 < 4.0.0", not (Version(4, 0, 0, 100) < Version(4, 0, 0)))

test("4.0.0 > 3.2.0", Version(4, 0, 0) > Version(3, 2, 0))
test("3.3.0 > 3.2.0", Version(3, 3, 0) > Version(3, 2, 0))
test("3.2.1 > 3.2.0", Version(3, 2, 1) > Version(3, 2, 0))
test("4.0.0-100 > 3.2.0-100", Version(4, 0, 0, 100) > Version(3, 2, 0, 100))
test("4.0.0 > 3.2.0-100", Version(4, 0, 0) > Version(3, 2, 0, 100))

test("-ve: 3.2.0-100 > 3.2.0-100", not (Version(3, 2, 0, 100) > Version(3, 2, 0, 100)))
test("-ve: 3.0.0 > 4.0.0", not (Version(3, 0, 0) > Version(4, 0, 0)))
test("-ve: 3.1.0 > 3.2.0", not (Version(3, 1, 0) > Version(3, 2, 0)))
test("-ve: 3.2.0-100 > 3.0.0-100", not (Version(3, 0, 0, 100) > Version(3, 2, 0, 100)))

###

result = finish()
if result:
    sys.exit(0)
else:
    sys.exit(1)
