# SPDX-License-Identifier: GPL-2.0-only

"""Bringing the host's hardware up, and keeping it in step with the answers.

Disk and network setup has to happen after the driver variants are chosen:
applying a variant reloads the driver and destroys every device it drives,
including the NIC carrying a live iSCSI boot session.

The screens can be walked backwards and uicontroller has no rollback, so the
two sequence steps here -- apply_drivers() and attach_storage_and_scan() --
are reconcilers: each diffs desired_hw_state(answers) against
answers['hw-applied'] and does only the difference.
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
    """Detach whatever a previous pass through the sequence attached.

    Multipath has to come down before the iSCSI logout, or the /dev/sdX under
    the maps vanish first: destroyMpathPartnodes() then abandons the rest on
    the first device it cannot remove, and the leftovers trip one of
    mpath_enable()'s asserts on the way back in.

    Every step tolerates its state not being there -- this also runs after a
    pass which died half way through, and after one which never started.
    """

    applied = answers.get('hw-applied')
    if applied is None:
        return

    if applied['mpath'] != MultipathConfig.DISABLED:
        diskutil.mpath_disable()
        applied['mpath'] = MultipathConfig.DISABLED

    # Deliberately leaves iscsid running, so the disks can be attached again.
    diskutil.logout_ibft_disks()
    applied['ibft'] = False

    answers.pop('system-scanned', None)


def _find_after_rescan(previous, candidates, disk_of):
    """Find `previous` in a freshly scanned list of installations or backups.

    Every scan builds new objects and they do not compare equal, so match on
    the disk the installation or backup lives on.  Returns None if it is gone.
    """

    for candidate in candidates:
        if disk_of(candidate) == disk_of(previous):
            return candidate
    return None


def prune_stale_answers(answers):
    """Drop answers which refer to hardware the latest scan no longer sees.

    A rescan can shrink the world: a teardown detaches the iSCSI LUNs, a
    variant change can lose a disk, answering No to the iBFT prompt on a second
    pass removes every iSCSI disk.  The screens which would let the user choose
    again are skipped when that happens, because their predicates read the very
    answers which are now wrong -- so the answers have to be corrected here.
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
    """Wait for the devices a driver reload destroyed to come back.

    udevadm settle only waits for the events already queued, and a freshly
    loaded driver probes asynchronously, so a rename can still be to come.
    Reserving a NIC under its pre-reload name leaves
    netutil.scanConfiguration()'s filter not matching it, silently offering
    the iSCSI NIC for management.  So wait for the interface list to settle.
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

    The ibft_present() check keeps iscsid out of the way on hosts with no iBFT:
    diskutil.probe_ibft() starts it, and a broken iscsid would otherwise turn a
    working local-disk install into a hard failure.
    """

    if not diskutil.ibft_present():
        logger.log("No iSCSI boot targets in the iBFT")
        return None

    try:
        return diskutil.probe_ibft()
    except Exception as e:
        # Do not take a local-disk install down with the iSCSI stack, but do
        # say so: a host with an iBFT was probably meant to boot from it.
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
    """Sequence step: put the selected driver variants into the running kernel.

    This is the first step which touches the hardware, and it deliberately runs
    before any disk or network setup: reloading a driver takes its devices away,
    so nothing may be built on them yet.
    """

    desired = desired_hw_state(answers)
    if 'hw-applied' not in answers:
        # First pass: nothing has been applied yet.
        answers['hw-applied'] = initial_hw_state()
    applied = answers['hw-applied']
    did_work = False

    if applied['variants'] != desired['variants']:
        # Whatever is running on these drivers' devices has to come down first.
        teardown_storage(answers)

        if not _apply_driver_variants(answers['selected-multiversion-drivers']):
            # Some variants may have loaded and some not, so the applied state
            # is unknown rather than unchanged.  None never compares equal, so
            # the next pass re-applies the whole selection -- including a
            # revert, which would otherwise be skipped over a half-changed host.
            applied['variants'] = None
            return LEFT_BACKWARDS

        applied['variants'] = desired['variants']
        # The reload took the netdevs away, so any --network_device
        # configuration has to go on again.
        applied['netdev'] = None
        answers.pop('system-scanned', None)
        # The NICs the iBFT names may have come back renamed, and a probe
        # which failed on the old driver deserves another go.
        answers.pop('ibft-targets', None)

        _settle_devices()
        # The reloaded netdevs came back down.  ibft_reserved_nics is still
        # empty here, so this reaches the iSCSI NIC too.
        netutil.setAllLinksUp()
        did_work = True

    # Not on every traversal: the prompt's predicate is evaluated in both
    # directions, and probing restarts iscsid.  Only when the key has been
    # dropped, which is how new hardware asks for a fresh answer.
    if 'ibft-targets' not in answers:
        answers['ibft-targets'] = try_probe_ibft(report_error=True)
        if not answers['ibft-targets']:
            # Nothing left to attach, so an earlier yes cannot stand.
            answers.pop('attach-ibft', None)
        did_work = True

    return RIGHT_FORWARDS if did_work else SKIP_SCREEN


def _scan_system(answers):
    """Work out what is on the disks and on the network.

    Runs after the storage is attached and the iSCSI NICs are reserved, so that
    the iSCSI LUNs are in the disk list and the reserved NICs are not in the
    interface list.
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
    """CA-41142: there is no point in going on without a disk and a usable NIC.

    Returns LEFT_BACKWARDS if the user has to go back and change something,
    otherwise None.
    """

    hint = """

If %s are present you may need to load a device driver, or select a different driver variant, on the previous screens for them to be detected."""

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
    """Sequence step: attach the storage, bring the network up, scan the result.

    Everything here needs the drivers that apply_drivers() loaded, and the scan
    has to follow the attach so that the iSCSI LUNs are in the disk list and the
    reserved NICs are out of the interface list.
    """

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
                # The only step here that depends on another host answering,
                # and it runs again on every traversal.  Going back puts the
                # user in front of the screens which can change the outcome --
                # decline the disks, or pick a different driver for the NIC.
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

    # --network_device, so the host is reachable while it installs.  Reads the
    # filtered interface list, so it must follow the reservation -- and go on
    # again whenever that has changed.
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

    Interactively this happens from the main sequence instead, after the driver
    variants are chosen.  No variant is applied live here, so that ordering does
    not arise; the iSCSI NICs must still be reserved before
    configureNetworking() looks at what is available.

    ui may be None -- that is the --rt_answerfile path.
    """

    # Nobody to ask here, so the firmware's own boot-selected bit decides.
    # Checking it first also keeps iscsid off a host with a merely stale table.
    if diskutil.ibft_boot_selected() and try_probe_ibft():
        diskutil.attach_ibft_disks()

    # ensure partitions/disks are not locked by LVM
    # this should be done before attempting to enable multipath
    lvm = disktools.LVMTool()
    lvm.deactivateAll()
    del lvm

    # Ensure multipath devices are created unless the installer is being
    # run with the "--device_mapper_multipath=disabled" option
    if mpath_config != MultipathConfig.DISABLED:
        diskutil.mpath_enable(mpath_config)

    if net_device:
        configureNetworking(ui, net_device, net_config)
