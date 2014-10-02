#!/bin/env python

import os
import os.path
import subprocess
import sys


REG_FILE = "/var/lib/likewise/db/registry.db"
TABLE = "regvalues1"
IN_PATH = "/opt/likewise/lib/"
OUT_PATH = "/opt/likewise/lib64/"

DB_DUMP = "db.dump"
SQL_CMDS = "update.sql"
SQLITE = "/usr/bin/sqlite3"


"""
Unpack a string representation of little-endian UTF-16 to an ASCII string.
"""
def unpack(blob):
    s = ''
    for i in range(0, len(blob), 4):
        s += chr(int(blob[i:i+2], 16))
    return s

"""
Pack an ASCII string into a string representation of little-endian UTF-16.
"""
def pack(s):
    b = ''
    for c in list(s):
        b += "%02x00" % ord(c)
    return b


if __name__ == '__main__':
    # create all files relative to this script, caller will cleanup
    os.chdir(os.path.dirname(sys.argv[0]))

    # dump the value table from the registry
    p = subprocess.Popen("%s %s '.dump %s' >%s" % (SQLITE, REG_FILE, TABLE, DB_DUMP), shell = True)
    p.communicate()
    if p.returncode != 0:
        raise RuntimeError, "Failed to dump registry"

    # create a set of update statements
    dump_fh = open(DB_DUMP)
    sql_fh = open(SQL_CMDS, 'w')
    wrote_cmd = False
    for line in dump_fh:
        line = line.rstrip()

        # discard lines other than insert statements
        if not line.startswith('INSERT INTO'):
            continue
        f = line.split(None, 3)
        v = f[3][7:-2]
        values = v.split(', ')

        # discard records other than paths
        if values[2].lower() != "'path'":
            continue
        # strip X'...'
        blob = values[4][2:-1]
        val = unpack(blob)

        # discard paths other than libraries
        if not val.startswith(IN_PATH):
            continue
        newval = val.replace(IN_PATH, OUT_PATH)
        print >>sql_fh, "UPDATE %s SET Value = X'%s' where ParentId = %s AND ValueName = %s;" % (TABLE, pack(newval), values[1], values[2])
        wrote_cmd = True
    dump_fh.close()
    sql_fh.close()

    if wrote_cmd:
        # apply the updates to the registry
        p = subprocess.Popen("%s %s <%s" % (SQLITE, REG_FILE, SQL_CMDS), shell = True);
        p.communicate()
        if p.returncode != 0:
            raise RuntimeError, "Failed to update registry"
