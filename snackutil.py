# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Text user interface helper functions
#
# written by Andrew Peace

from snack import *

def ButtonChoiceWindowEx(screen, title, text, 
               buttons = [ 'Ok', 'Cancel' ], 
               width = 40, x = None, y = None, help = None,
               default = 0):
    bb = ButtonBar(screen, buttons)
    t = TextboxReflowed(width, text, maxHeight = screen.height - 12)

    g = GridFormHelp(screen, title, help, 1, 2)
    g.add(t, 0, 0, padding = (0, 0, 0, 1))
    g.add(bb, 0, 1, growx = 1)

    g.draw()
    g.setCurrent(bb.list[default][0])
    
    return bb.buttonPressed(g.runOnce(x, y))

def PasswordEntryWindow(screen, title, text, prompts, allowCancel = 1, width = 40,
                        entryWidth = 20, buttons = [ 'Ok', 'Cancel' ], help = None):
    bb = ButtonBar(screen, buttons)
    t = TextboxReflowed(width, text)

    count = 0
    for n in prompts:
        count = count + 1

    sg = Grid(2, count)

    count = 0
    entryList = []
    for n in prompts:
        if (type(n) == types.TupleType):
            (n, e) = n
        else:
            e = Entry(entryWidth, password = 1)

        sg.setField(Label(n), 0, count, padding = (0, 0, 1, 0), anchorLeft = 1)
        sg.setField(e, 1, count, anchorLeft = 1)
        count = count + 1
        entryList.append(e)

    g = GridFormHelp(screen, title, help, 1, 3)

    g.add(t, 0, 0, padding = (0, 0, 0, 1)) 
    g.add(sg, 0, 1, padding = (0, 0, 0, 1))
    g.add(bb, 0, 2, growx = 1)

    result = g.runOnce()

    entryValues = []
    count = 0
    for n in prompts:
        entryValues.append(entryList[count].value())
        count = count + 1

    return (bb.buttonPressed(result), tuple(entryValues))

def OKDialog(screen, title, text):
    return ButtonChoiceWindow(screen, title, text, ['OK'])

PLEASE_WAIT_STRING = "  Working: Please wait..."

def initProgressDialog(screen, title, text, total):
    form = GridFormHelp(screen, title, None, 1, 3)
    
    t = Textbox(60, 1, text)
    scale = Scale(60, total)
    form.add(t, 0, 0, padding = (0,0,0,1))
    form.add(scale, 0, 1, padding = (0,0,0,0))

    return (form, t, scale)

def showMessageDialog(screen, title, text):
    form = GridFormHelp(screen, title, None, 1, 1)
    
    t = TextboxReflowed(60, text)
    form.add(t, 0, 0, padding = (0,0,0,0))

    form.draw()

    screen.pushHelpLine(PLEASE_WAIT_STRING)
    screen.refresh()

def displayProgressDialog(screen, current, (form, t, scale), updated_text = None):
    scale.set(current)
    if updated_text:
        t.setText(updated_text)

    form.draw()

    screen.pushHelpLine(PLEASE_WAIT_STRING)
    screen.refresh()

def clearModelessDialog(screen):
    screen.pushHelpLine(None)
    screen.popWindow()
