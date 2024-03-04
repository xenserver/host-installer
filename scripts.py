# SPDX-License-Identifier: GPL-2.0-only

import constants
import os
import stat
import tempfile
import util
from xcp import logger

script_dict = {}

def add_script(stage, url):
    if stage not in script_dict:
        script_dict[stage] = []
    script_dict[stage].append(url)

def run_scripts(stage, *args):
    if stage not in script_dict:
        return

    for script in script_dict[stage]:
        run_script(script, stage, *args)

def run_script(script, stage, *args):
    logger.log("Running script for stage %s: %s %s" % (stage, script, ' '.join(args)))

    util.assertDir(constants.SCRIPTS_DIR)
    fd, local_name = tempfile.mkstemp(prefix=stage, dir=constants.SCRIPTS_DIR)
    try:
        os.close(fd)
        util.fetchFile(script, local_name)
    except:
        raise RuntimeError("Unable to fetch script %s" % script)

    cmd = [local_name]
    cmd.extend(args)
    os.chmod(local_name, stat.S_IRUSR | stat.S_IXUSR)
    os.environ['XS_STAGE'] = stage

    try:
        rc, out, err = util.runCmd2(cmd, with_stdout=True, with_stderr=True)
    except Exception:
        # match shell error code for exec failure
        return 127, "", ""

    logger.log("Script returned %d" % rc)
    # keep script, will be collected in support tarball

    return rc, out, err
