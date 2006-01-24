import sys
debug = False

def trace_message(message):
    if debug:
        sys.stderr.write(message)
        
def is_debug():
    return debug

def show_debug_output():
    if not debug:
        return " &> /dev/null"
    else:
        return ""
