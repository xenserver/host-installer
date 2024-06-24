# SPDX-License-Identifier: GPL-2.0-only

# Poor Python Expect.
# Simplified expect to run a process

import errno
import fcntl
import os
import select
import subprocess
import sys
import time

__all__ = ['Process', 'TimeoutError']

def set_nonblocking(fd):
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

if sys.version_info[0] < 3:
    class TimeoutError(OSError):
        def __init__(self):
            super(TimeoutError, self).__init__(errno.ETIMEDOUT, None)
else:
    TimeoutError = TimeoutError

class Process:
    def __init__(self, cmd):
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            close_fds=True,
            universal_newlines=True,
            )
        set_nonblocking(process.stdout.fileno())

        self.process = process

    def __del__(self):
        self.close()

    def write(self, msg):
        stdin = self.process.stdin
        stdin.write(msg)
        stdin.flush()

    def expect(self, msg, timeout=1.0):
        data = b''
        deadline = time.time() + timeout
        while True:
            if type(msg) == str:
                found = msg in data.decode()
            else:
                found = msg.match(data.decode())
            if found:
                return found

            data += self.__readDeadline(deadline)

    def __readDeadline(self, deadline):
        fd = self.process.stdout.fileno()
        now = time.time()
        if now > deadline:
            raise TimeoutError()
        select.select([fd], [], [], deadline - now)
        return self.__readFd(fd)

    @staticmethod
    def __readFd(fd):
        try:
            return os.read(fd, 1024 * 16)
        except OSError as ex:
            if ex.errno != errno.EAGAIN:
                raise
        return b''

    def close(self):
        if not self.process:
            return None
        process = self.process
        self.process = None
        process.stdin.close()
        res = process.wait()
        process.stdout.close()
        return res
