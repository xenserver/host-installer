# SPDX-License-Identifier: GPL-2.0-only

"""Hardware bring-up for the installer.

Disk and network setup runs after the driver variants are chosen, because
applying a variant reloads the driver.  The screens can be walked backwards,
so the sequence steps here compare desired_hw_state(answers) with
answers['hw-applied'] and apply only the difference.
"""

import time

import constants
from constants import MultipathConfig
import diskutil
import disktools
import dmvutil
import netutil
import product
import upgrade
import util
from uicontroller import SKIP_SCREEN, LEFT_BACKWARDS, RIGHT_FORWARDS
from xcp import logger

import tui
import tui.progress
from snack import ButtonChoiceWindow

from netinterface import NetInterface


def parse_multipath_config(value):
    """Map a --device_mapper_multipath value onto a MultipathConfig."""

    value = value.lower()
    if value in ["disabled", "false", "0", "no"]:
        return MultipathConfig.DISABLED
    if value in ["enabled", "true", "1", "yes", "force"]:
        return MultipathConfig.ENABLED
    return MultipathConfig.IF_MULTIPLE


# Attempt to configure the network:
def configureNetworking(ui, device, config):
    if ui:
        ui.progress.showMessageDialog(
            "Preparing for installation",
            "Attempting to configure networking..."
            )

    if device == 'all':
        config = 'dhcp'
    mode, rest = config.split(":", 1) if config and ":" in config else (config, None)
    config_dict = {'gateway': None, 'dns': None, 'domain': None, 'vlan': None}
    if rest:
        for el in rest.split(';'):
            k, v = el.split('=', 1)
            config_dict[k] = v
    if mode == 'static':
        if config_dict['dns'] is not None:
            config_dict['dns'] = config_dict['dns'].split(',')
        assert 'ip' in config_dict and 'netmask' in config_dict
    if config_dict['vlan']:
        if not netutil.valid_vlan(config_dict['vlan']):
            raise RuntimeError("Invalid VLAN value for installer network")
        config_dict['vlan'] = int(config_dict['vlan'])

    nethw = netutil.scanConfiguration()
    netcfg = {}
    for i in nethw:
        if (device == i or device == nethw[i].hwaddr) and mode == 'static':
            netcfg[i] = NetInterface(NetInterface.Static, nethw[i].hwaddr,
                                     config_dict['ip'], config_dict['netmask'],
                                     config_dict['gateway'], config_dict['dns'],
                                     config_dict['domain'], config_dict['vlan'])
        else:
            netcfg[i] = NetInterface(NetInterface.DHCP, nethw[i].hwaddr,
                                     vlan=config_dict['vlan'])

    iface_to_start = []
    if device == 'all':
        iface_to_start.extend(list(netcfg.keys()))
    elif device in nethw:
        iface_to_start.append(device)
    else:
        # MAC address
        matching_list = [x for x in nethw.values() if x.hwaddr == device]
        if len(matching_list) == 1:
            devname = matching_list[0].name
            iface_to_start.append(devname)

    for i in iface_to_start:
        netcfg[i].writeSystemdNetworkdConfig(i)

    # Reload network to apply the configuration
    netutil.reloadNetwork()

    if ui:
        ui.progress.clearModelessDialog()


def desired_hw_state(answers):
    """The hardware state that the answers collected so far ask for."""

    return {
        'variants': frozenset(answers.get('selected-multiversion-drivers', [])),
        'ibft': bool(answers.get('attach-ibft', False)),
        'mpath': answers.get('multipath-config', MultipathConfig.IF_MULTIPLE),
        'netdev': answers.get('network-device'),
        }


def initial_hw_state():
    """The state of a host the installer has not touched yet."""

    return {
        'variants': frozenset(),
        'ibft': False,
        'mpath': MultipathConfig.DISABLED,
        'netdev': None,
        }


def teardown_storage(answers):
    """Detach whatever a previous pass attached.  Tolerates partial state.

    Multipath has to come down before the iSCSI logout, or mpath_enable()
    trips over leftover maps on the next pass.
    """

    applied = answers.get('hw-applied')
    if applied is None:
        return

    if applied['mpath'] != MultipathConfig.DISABLED:
        diskutil.mpath_disable()
        applied['mpath'] = MultipathConfig.DISABLED

    # Leaves iscsid running, ready for the next attach.
    diskutil.logout_ibft_disks()
    applied['ibft'] = False

    answers.pop('system-scanned', None)


def _find_after_rescan(previous, candidates, disk_of):
    """Return the entry in candidates on the same disk as previous, or None.

    Each scan builds new objects, which do not compare equal.
    """

    for candidate in candidates:
        if disk_of(candidate) == disk_of(previous):
            return candidate
    return None


def prune_stale_answers(answers):
    """Drop answers which refer to hardware the latest scan no longer sees.

    The screens which would let the user choose again are skipped while those
    answers are set, so they have to be corrected here.
    """

    disks = diskutil.getQualifiedDiskList()

    chosen = answers.get('installation-to-overwrite')
    if chosen is not None:
        match = _find_after_rescan(chosen, answers['upgradeable-products'],
                                   lambda p: p.primary_disk)
        if match is None:
            logger.log("Installation to overwrite has gone away, forgetting it")
            del answers['installation-to-overwrite']
        else:
            answers['installation-to-overwrite'] = match

    backup = answers.get('backup-to-restore')
    if backup is not None:
        match = _find_after_rescan(backup, answers['backups'],
                                   lambda b: b.root_disk)
        if match is None:
            logger.log("Backup to restore has gone away, forgetting it")
            del answers['backup-to-restore']
        else:
            answers['backup-to-restore'] = match

    # get_installation_type() is skipped once there is nothing to upgrade or
    # restore, so a stale install type would never be revisited.
    install_type = answers.get('install-type')
    if (install_type == constants.INSTALL_TYPE_REINSTALL and
            'installation-to-overwrite' not in answers) or \
       (install_type == constants.INSTALL_TYPE_RESTORE and
            'backup-to-restore' not in answers):
        logger.log("Falling back to a clean installation")
        answers['install-type'] = constants.INSTALL_TYPE_FRESH
        answers['preserve-settings'] = False

    if answers.get('primary-disk') is not None and answers['primary-disk'] not in disks:
        logger.log("Primary disk %s has gone away, forgetting it" % answers['primary-disk'])
        del answers['primary-disk']
        answers.pop('physical-disks', None)

    if answers.get('guest-disks') is not None:
        remaining = [d for d in answers['guest-disks'] if d in disks]
        if remaining != answers['guest-disks']:
            logger.log("Guest disks are now %s" % str(remaining))
            answers['guest-disks'] = remaining

    # get_admin_interface is skipped on a single-NIC host, but
    # get_admin_interface_configuration is not and would raise a KeyError.
    if answers.get('net-admin-interface') not in answers['network-hardware']:
        answers.pop('net-admin-interface', None)
        answers.pop('net-admin-configuration', None)


def _apply_driver_variants(choices):
    """Select and load the chosen driver variants. True if they all took."""

    for drvname, oemtype in choices:
        logger.log("select and enable variant %s for driver %s." % (oemtype, drvname))

    failures = dmvutil.getCachedDMVData().applyDriverVariants(choices)
    if len(failures) == 0:
        logger.log("succeed to select and enable all driver variants.")
        return True

    for driver_name, variant_name in failures:
        logger.log("fail to select or enable variant %s for driver %s." % (variant_name, driver_name))
    ButtonChoiceWindow(
            tui.screen,
            "Problem Loading Driver Variant",
            "Setup was unable to activate driver variant.",
            ['Ok']
            )
    return False


def _settle_devices(timeout=30):
    """Wait for the interfaces to settle after a driver reload.

    The driver probes asynchronously, so a rename can follow udevadm settle.
    Reserving a NIC under its old name would offer it for management.
    """

    util.runCmd2(util.udevsettleCmd())

    previous = None
    for _ in range(timeout):
        current = netutil.getNetifList()
        if current and current == previous:
            break
        previous = current
        time.sleep(1)
    else:
        logger.log("Network interfaces still settling after %ds: %s" % (timeout, previous))

    util.runCmd2(util.udevsettleCmd())


def try_probe_ibft(report_error=False):
    """diskutil.probe_ibft(), returning None instead of raising.

    Hosts with no iBFT are skipped, so they never start iscsid.
    """

    if not diskutil.ibft_present():
        logger.log("No iSCSI boot targets in the iBFT")
        return None

    try:
        return diskutil.probe_ibft()
    except Exception as e:
        # Do not fail a local-disk install over the iSCSI stack.
        logger.logException(e)
        if report_error:
            ButtonChoiceWindow(
                    tui.screen,
                    "Problem Reading iBFT",
                    "Setup was unable to look for the iSCSI disks described by "
                    "this host's iSCSI Boot Firmware Table.  Only local disks "
                    "will be available.",
                    ['Ok'], width=60
                    )
        return None


def apply_drivers(answers):
    """Sequence step: load the selected driver variants.

    Runs before any disk or network setup, because a reload removes the
    driver's devices.
    """

    desired = desired_hw_state(answers)
    if 'hw-applied' not in answers:
        answers['hw-applied'] = initial_hw_state()
    applied = answers['hw-applied']
    did_work = False

    if applied['variants'] != desired['variants']:
        teardown_storage(answers)

        if not _apply_driver_variants(answers['selected-multiversion-drivers']):
            # Some variants may have loaded, so record the state as unknown:
            # the next pass then re-applies the whole selection.
            applied['variants'] = None
            return LEFT_BACKWARDS

        applied['variants'] = desired['variants']
        # The reload removed the netdevs, so --network_device must go on again.
        applied['netdev'] = None
        answers.pop('system-scanned', None)
        # Probe again: the iBFT NICs may have been renamed.
        answers.pop('ibft-targets', None)

        _settle_devices()
        # Reloaded netdevs come back down, iSCSI NICs included.
        netutil.setAllLinksUp()
        did_work = True

    # Probe only when the key has been dropped: this runs on every traversal
    # and probing restarts iscsid.
    if 'ibft-targets' not in answers:
        answers['ibft-targets'] = try_probe_ibft(report_error=True)
        if not answers['ibft-targets']:
            # Nothing left to attach, so an earlier yes cannot stand.
            answers.pop('attach-ibft', None)
        did_work = True

    return RIGHT_FORWARDS if did_work else SKIP_SCREEN


def _scan_system(answers):
    """Scan the disks, installed products and NICs.

    Runs after the attach, so the iSCSI LUNs are listed and the reserved NICs
    are not.
    """

    logger.log("Waiting for partitions to appear...")
    util.runCmd2(util.udevsettleCmd())
    time.sleep(1)
    diskutil.mpath_part_scan()

    # ensure partitions/disks are not locked by LVM
    lvm = disktools.LVMTool()
    lvm.deactivateAll()
    del lvm

    tui.progress.showMessageDialog("Please wait", "Checking for existing products...")
    answers['installed-products'] = product.find_installed_products()
    answers['upgradeable-products'] = upgrade.filter_for_upgradeable_products(answers['installed-products'])
    answers['backups'] = product.findXenSourceBackups()
    tui.progress.clearModelessDialog()

    diskutil.log_available_disks()

    answers['network-hardware'] = netutil.scanConfiguration()

    prune_stale_answers(answers)


def _check_hardware_present(answers):
    """Return LEFT_BACKWARDS if there is no disk or no usable NIC."""

    hint = """

If %s are present you may need to load a device driver, or select a different driver variant, on the previous screens for them to be detected."""

    # CA-41142, ensure we have at least one network interface and one disk before proceeding
    if len(diskutil.getDiskList()) == 0:
        label = "No Disks"
        text = "This host does not appear to have any hard disks." + hint % "disks"
    elif len(netutil.getNetifList()) == 0:
        label = "No Network Interfaces"
        text = "This host does not appear to have any network interfaces." + hint % "interfaces"
    elif len(answers['network-hardware']) == 0:
        label = "No Usable Network Interfaces"
        text = """The only network interface(s) on this host are reserved for the iSCSI boot path and cannot be used for management.

To install to a local disk instead, go back and decline the iBFT disks."""
    else:
        return None

    ButtonChoiceWindow(tui.screen, label, text, ["Back"], width=48)
    return LEFT_BACKWARDS


def attach_storage_and_scan(answers):
    """Sequence step: attach storage, set up networking, scan the result."""

    desired = desired_hw_state(answers)
    applied = answers['hw-applied']
    did_work = False

    storage_changed = (applied['ibft'] != desired['ibft'] or
                       applied['mpath'] != desired['mpath'])
    if storage_changed:
        teardown_storage(answers)

        if desired['ibft']:
            try:
                diskutil.attach_ibft_disks()
            except Exception as e:
                # Going back lets the user decline the disks or change driver.
                logger.logException(e)
                teardown_storage(answers)
                ButtonChoiceWindow(
                        tui.screen,
                        "Problem Attaching iSCSI Disks",
                        "Setup was unable to attach the iSCSI disks described "
                        "by this host's iSCSI Boot Firmware Table.\n\n%s" % e,
                        ['Back'], width=60
                        )
                return LEFT_BACKWARDS
            applied['ibft'] = True

        # ensure partitions/disks are not locked by LVM
        # this should be done before attempting to enable multipath
        lvm = disktools.LVMTool()
        lvm.deactivateAll()
        del lvm

        if desired['mpath'] != MultipathConfig.DISABLED:
            diskutil.mpath_enable(desired['mpath'])
        applied['mpath'] = desired['mpath']

        answers.pop('system-scanned', None)
        did_work = True

    # --network_device reads the filtered interface list, so it has to go on
    # again whenever the reservation changes.
    if desired['netdev'] and (storage_changed or
                              applied['netdev'] != desired['netdev']):
        configureNetworking(tui, desired['netdev'],
                            answers.get('network-config', 'dhcp'))
        applied['netdev'] = desired['netdev']
        did_work = True

    if not answers.get('system-scanned'):
        _scan_system(answers)
        answers['system-scanned'] = True
        did_work = True

    direction = _check_hardware_present(answers)
    if direction is not None:
        return direction

    return RIGHT_FORWARDS if did_work else SKIP_SCREEN


def bring_up_hardware(ui, mpath_config, net_device, net_config):
    """Non-interactive bring-up, for the answerfile paths.

    ui may be None (--rt_answerfile).
    """

    # Nobody to ask, so attach only if the firmware booted from the iBFT.
    if diskutil.ibft_boot_selected() and try_probe_ibft():
        diskutil.attach_ibft_disks()

    # ensure partitions/disks are not locked by LVM
    # this should be done before attempting to enable multipath
    lvm = disktools.LVMTool()
    lvm.deactivateAll()
    del lvm

    # Ensure multipath devices are created unless installer is being
    # run with the "--device_mapper_multipath=disabled" option
    if mpath_config != MultipathConfig.DISABLED:
        diskutil.mpath_enable(mpath_config)

    if net_device:
        configureNetworking(ui, net_device, net_config)
