import xelogging
import time

# mnt: path to where vmstate is mounted
# hn: hostname of destination host
# uname: username on destination host
# pw: password for uname
# prgress: callback function: int -> unit.
def run(mnt, hn, uname, pw, progress):
    xelogging.log("Starting export of VMs")
    xelogging.log("Input: %s" % str((mnt, hn, uname, pw, progress)))

    for i in range(0, 10):
        time.sleep(1)
        progress(i * 10)

    xelogging.log("Export complete.")
