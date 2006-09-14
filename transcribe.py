import uicontroller
import init_tui
import util
import constants
import os

import vm_exporter

__BURBANK_VMSTATE_VOLNAME__ = "VMState"
__BURBANK_VOLGROUP_NAME__ = "VG_XenSource"
__VMSTATE_MOUNTPOINT__ = "/tmp/mnt-vmstate"

def run():
    answers = {}
    ui_sequence = [
        init_tui.ask_export_destination_screen,
        init_tui.ask_host_password_screen
        ]

    rc = uicontroller.runUISequence(ui_sequence, answers)

    # was there a problem/cancel so far?
    if rc == uicontroller.LEFT_BACKWARDS:
        return constants.EXIT_USER_CANCEL
    if rc == uicontroller.EXIT:
        return constants.EXIT_ERROR

    # start a progress dialog:
    pd = init_tui.initProgressDialog("Exporting VMs", "VM export is in progress, please wait...", 100)
    init_tui.displayProgressDialog(0, pd)

    def progress_callback(amount):
        init_tui.displayProgressDialog(amount, pd)

    error = False
    try:
        try:
            os.environ['LVM_SYSTEM_DIR'] = '/tmp/lvm'
            util.assertDir("/tmp/lvm")
            
            # activate volume groups and mount VMState
            util.assertDir(__VMSTATE_MOUNTPOINT__)
            
            if util.runCmd2(['vgchange', '-a', 'y']) != 0:
                raise Exception, "Internal error: Unable to active volume groups"
        
            util.mount("/dev/%s/%s" % (__BURBANK_VOLGROUP_NAME__, __BURBANK_VMSTATE_VOLNAME__),
                       __VMSTATE_MOUNTPOINT__)

            vm_exporter.run(__VMSTATE_MOUNTPOINT__,
                            answers['hostname'],
                            'root',
                            answers['password'],
                            progress_callback)

        except Exception, e:
            init_tui.OKDialog(
                "Error",
                """An error has occurred during export of VMs, and the export was aborted.  The error was:

%s

Please refer to your user guide, or XenSource Technical Support, for further assistance.""" % str(e))

            error = True
        else:
            init_tui.OKDialog(
                "Completed",
                "The VM export operation is complete.  Select OK to reboot this host."
                )
    finally:
        if os.path.exists(__VMSTATE_MOUNTPOINT__):
            try:
                util.umount(__VMSTATE_MOUNTPOINT__)
            except:
                pass
        util.runCmd2(['vgchange', '-a', 'n'])

    init_tui.clearModelessDialog()

    # simulate external program return code:
    if error:
        return 1
    else:
        return 0
