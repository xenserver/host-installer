#!/usr/bin/env python3

import sys
import os.path
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '..'))

import unittest
import ppexpect
import re

class TestPPExpect(unittest.TestCase):
    @staticmethod
    def command(cmd):
        return ppexpect.Process(['sh', '-c', cmd])

    def test_base(self):
        p = self.command('sleep 0.9; echo hello')
        p.expect('hello')

    def test_timeout(self):
        p = self.command('sleep 0.9; echo hello')
        with self.assertRaises(ppexpect.TimeoutError):
            p.expect('hello', timeout=0.5)
        p.expect('hello')

    def test_regex(self):
        p = self.command('echo "pid is $$"')
        rex = re.compile(r'pid is (.*)')
        m = p.expect(rex)
        print("pid is %d" % int(m.group(1)))

    def test_close(self):
        p = self.command('exit 43')
        res = p.close()
        self.assertEqual(res, 43)
        p.close()

if __name__ == '__main__':
    unittest.main()
