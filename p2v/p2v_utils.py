import sys
import re
debug = False
import xelogging

def purge_xecli_password(message):
    return re.sub("-p \S+", "-p SECRET", message)

def trace_message(message):
    if debug:
        sys.stderr.write(message)
    xelogging.log(purge_xecli_password(message))
        
def is_debug():
    return debug

def show_debug_output():
    if not debug:
        return " &> /dev/null"
    else:
        return ""
