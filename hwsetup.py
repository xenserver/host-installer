# SPDX-License-Identifier: GPL-2.0-only

"""Bringing the host's hardware up: iBFT disks, multipath and networking."""

from constants import MultipathConfig
import diskutil
import disktools
import netutil

from netinterface import NetInterface


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


def bring_up_hardware(ui, interactive, mpath_config, attach_ibft,
                      net_device, net_config):
    """Attach the disks and bring the network up, as 'init' used to do inline.

    ui is None on the --rt_answerfile path, and net_device is None unless the
    command line asked for the network to be configured.
    """

    # Attaches iSCSI disks listed in iSCSI Boot Firmware Tables.  This may
    # reserve NICs and so should be called before netutil.scanConfiguration
    if attach_ibft:
        diskutil.process_ibft(ui, interactive)

    # ensure partitions/disks are not locked by LVM
    # this should be done before attempting to enable multipath
    lvm = disktools.LVMTool()
    lvm.deactivateAll()
    del lvm

    # Ensure multipath devices are created unless installer is being
    # run with the "--device_mapper_multipath=disabled" option
    if mpath_config != MultipathConfig.DISABLED:
        diskutil.mpath_enable(mpath_config)

    if ui:
        netutil.setAllLinksUp()
    if net_device:
        configureNetworking(ui, net_device, net_config)
