# SPDX-License-Identifier: GPL-2.0-only

from snack import *
import tui

PLEASE_WAIT_STRING = "  Working: Please wait..."

def initProgressDialog(title, text, total):
    form = GridFormHelp(tui.screen, title, None, 1, 3)

    t = Textbox(60, 1, text)
    scale = Scale(60, total)
    form.add(t, 0, 0, padding=(0, 0, 0, 1))
    form.add(scale, 0, 1, padding=(0, 0, 0, 0))

    form.draw()
    tui.screen.pushHelpLine(PLEASE_WAIT_STRING)
    tui.screen.refresh()

    return (form, t, scale)

def showMessageDialog(title, text):
    form = GridFormHelp(tui.screen, title, None, 1, 1)

    t = TextboxReflowed(60, text)
    form.add(t, 0, 0, padding=(0, 0, 0, 0))

    form.draw()

    tui.screen.pushHelpLine(PLEASE_WAIT_STRING)
    tui.screen.refresh()

def displayProgressDialog(current, form_info, updated_text=None):
    (form, t, scale) = form_info
    scale.set(int(current))
    if updated_text:
        t.setText(updated_text)

    form.draw()
    tui.screen.refresh()

def clearModelessDialog():
    tui.screen.popHelpLine()
    tui.screen.popWindow()

def OKDialog(title, text, hasCancel=False):
    buttons = ['Ok']
    if hasCancel:
        buttons.append('Cancel')
    return ButtonChoiceWindow(tui.screen, title, text, buttons)
