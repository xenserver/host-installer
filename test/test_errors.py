#!/usr/bin/env python3

import sys
import os.path
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '..'))

import unittest
import constants

class TestErrorString(unittest.TestCase):
    def check(self, error, logname, with_hd, expected):
        got = constants.error_string(error, logname, with_hd)
        self.assertEqual(got, expected)

    def test_hello(self):
        self.check('hello', 'LOGFILE', True, '''An unrecoverable error has occurred.  The error was:

hello.

Please refer to your user guide or contact a Technical Support Representative for more details.''')

    def test_with_dot(self):
        self.check('hello.', 'LOGFILE', True, '''An unrecoverable error has occurred.  The error was:

hello.

Please refer to your user guide or contact a Technical Support Representative for more details.''')

    def test_empty(self):
        self.check('', 'LOGFILE', True, '''An unrecoverable error has occurred.  The details of the error can be found in the log file, which has been written to /tmp/LOGFILE (and /root/LOGFILE on your hard disk if possible).

Please refer to your user guide or contact a Technical Support Representative for more details.''')

    def test_empty_without_hd(self):
        self.check('', 'LOGFILE', False, '''An unrecoverable error has occurred.  The details of the error can be found in the log file, which has been written to /tmp/LOGFILE.

Please refer to your user guide or contact a Technical Support Representative for more details.''')

if __name__ == '__main__':
    unittest.main()
