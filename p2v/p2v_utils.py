import sys
debug = False
import xelogging

def trace_message(message):
    if debug:
        sys.stderr.write(message)
    xelogging.log(message)
        
def is_debug():
    return debug

def show_debug_output():
    if not debug:
        return " &> /dev/null"
    else:
        return ""
