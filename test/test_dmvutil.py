# SPDX-License-Identifier: GPL-2.0-only

"""Driver-selection tests that never invoke driver-tool or modprobe."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


# Load the real module with isolated runtime dependencies. The installer's
# generated branding module and host-only xcp package are not needed here.
spec = importlib.util.spec_from_file_location(
    "dmvutil_under_test", Path(__file__).resolve().parents[1] / "dmvutil.py"
)
dmvutil = importlib.util.module_from_spec(spec)
with mock.patch.dict(
    sys.modules,
    {"util": mock.Mock(), "xcp": mock.Mock(), "diskutil": mock.Mock()},
):
    spec.loader.exec_module(dmvutil)


def driver_data(active="generic", selected="generic"):
    return json.dumps({"drivers": {"enic": {
        "type": "network",
        "friendly_name": "enic",
        "description": "Cisco enic driver",
        "info": "enic",
        "active": active,
        "selected": selected,
        "variants": {
            name: {
                "version": "4.11.0.97",
                "hardware_present": True,
                "priority": 100,
                "status": "production",
            }
            for name in ("generic", "oem")
        },
    }}})


class TestDriverSelection(unittest.TestCase):
    def setUp(self):
        self.provider = dmvutil.DriverMultiVersionData(driver_data(), {})
        self.active = "generic"
        self.selected = "generic"
        self.fail_command = None
        self.list_result = None
        patcher = mock.patch.object(
            dmvutil.util, "runCmd2", side_effect=self.run_command
        )
        self.run_cmd = patcher.start()
        self.addCleanup(patcher.stop)
        # No iBFT disks attached, so no driver is on the boot path
        self.nic_drivers = {}
        dmvutil.diskutil.ibft_reserved_nics = set()
        readlink = mock.patch.object(
            dmvutil.os, "readlink", side_effect=self.read_nic_driver_link
        )
        readlink.start()
        self.addCleanup(readlink.stop)

    def read_nic_driver_link(self, path):
        for nic, driver in self.nic_drivers.items():
            if path == "/sys/class/net/%s/device/driver" % nic:
                return "../../../../bus/pci/drivers/%s" % driver
        raise OSError(2, "No such file or directory", path)

    def reserve_ibft_nic(self, nic="eno5", driver="enic"):
        """Pretend the installer attached its target over `nic`."""
        dmvutil.diskutil.ibft_reserved_nics = {nic}
        if driver:
            self.nic_drivers[nic] = driver

    def run_command(self, command, with_stdout=False):
        self.assertTrue(with_stdout)
        if command == self.fail_command:
            return 1, "command failed"
        if command == ["driver-tool", "-l"]:
            return self.list_result or (0, driver_data(self.active, self.selected))
        if command[:5] == ["driver-tool", "-s", "-n", "enic", "-v"]:
            self.selected = command[5]
        elif command == ["modprobe", "-r", "enic"]:
            self.active = None
        elif command == ["modprobe", "enic"]:
            self.active = self.selected
        else:
            self.fail("Unexpected command: %r" % command)
        return 0, ""

    def commands(self):
        return [call.args[0] for call in self.run_cmd.call_args_list]

    def assert_only_selects(self, variant="generic"):
        self.assertEqual(self.commands(), [
            ["driver-tool", "-l"],
            ["driver-tool", "-s", "-n", "enic", "-v", variant],
        ])

    def assert_reloads(self, variant):
        self.assertEqual(self.commands(), [
            ["driver-tool", "-l"],
            ["driver-tool", "-s", "-n", "enic", "-v", variant],
            ["modprobe", "-r", "enic"],
            ["modprobe", "enic"],
        ])

    def assert_changes_nothing(self):
        self.assertEqual(self.commands(), [["driver-tool", "-l"]])

    def test_active_variant_is_not_unloaded(self):
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "generic"))
        self.assert_only_selects()

    def test_active_variant_is_still_selected_for_next_boot(self):
        self.selected = "oem"
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "generic"))
        self.assert_only_selects()
        self.assertEqual(self.selected, "generic")

    def test_selection_failure_is_reported_even_when_already_active(self):
        self.fail_command = ["driver-tool", "-s", "-n", "enic", "-v", "generic"]
        self.assertFalse(self.provider.selectSingleDriverVariant("enic", "generic"))
        self.assert_only_selects()

    def test_matching_selected_but_different_active_still_reloads(self):
        self.active = "oem"
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "generic"))
        self.assert_reloads("generic")

    def test_unloaded_or_non_dmv_driver_is_not_mistaken_for_active(self):
        self.active = None
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "generic"))
        self.assert_reloads("generic")

    def test_different_variant_still_reloads(self):
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "oem"))
        self.assert_reloads("oem")
        self.assertEqual(self.active, "oem")

    def test_live_state_overrides_cached_active_variant(self):
        self.provider = dmvutil.DriverMultiVersionData(driver_data(active="oem"), {})
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "generic"))
        self.assert_only_selects()

    def test_back_and_forward_selection_refreshes_live_state(self):
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "oem"))
        self.run_cmd.reset_mock()
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "generic"))
        self.assert_reloads("generic")
        self.run_cmd.reset_mock()
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "generic"))
        self.assert_only_selects()

    def test_failed_live_query_does_not_change_selection_or_unload(self):
        self.fail_command = ["driver-tool", "-l"]
        self.assertFalse(self.provider.selectSingleDriverVariant("enic", "generic"))
        self.assertEqual(self.commands(), [["driver-tool", "-l"]])

    def test_invalid_live_data_does_not_change_selection_or_unload(self):
        for output in ("", "not json", "null", "[]", "{}",
                       '{"drivers": {}}', '{"drivers": {"enic": {}}}'):
            with self.subTest(output=output):
                self.list_result = 0, output
                self.run_cmd.reset_mock()
                self.assertFalse(self.provider.selectSingleDriverVariant("enic", "generic"))
                self.assertEqual(self.commands(), [["driver-tool", "-l"]])

    def test_unload_failure_is_reported_without_attempting_load(self):
        self.fail_command = ["modprobe", "-r", "enic"]
        self.assertFalse(self.provider.selectSingleDriverVariant("enic", "oem"))
        self.assertEqual(self.commands(), [
            ["driver-tool", "-l"],
            ["driver-tool", "-s", "-n", "enic", "-v", "oem"],
            ["modprobe", "-r", "enic"],
        ])

    def test_load_failure_is_reported(self):
        self.fail_command = ["modprobe", "enic"]
        self.assertFalse(self.provider.selectSingleDriverVariant("enic", "oem"))
        self.assert_reloads("oem")

    def test_apply_driver_variants_reports_failure(self):
        self.fail_command = ["modprobe", "-r", "enic"]
        self.assertEqual(
            self.provider.applyDriverVariants([("enic", "oem")]), [("enic", "oem")]
        )

    def test_apply_active_variant_succeeds_without_reload(self):
        self.assertEqual(self.provider.applyDriverVariants([("enic", "generic")]), [])
        self.assert_only_selects()


class TestBootPathDriverIsLeftAlone(TestDriverSelection):
    """A driver carrying the iBFT session must survive a variant change."""

    def test_boot_path_driver_is_neither_selected_nor_reloaded(self):
        self.reserve_ibft_nic()
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "oem"))
        self.assert_changes_nothing()
        self.assertEqual(self.active, "generic")
        self.assertEqual(self.selected, "generic")

    def test_unapplied_variant_is_reported(self):
        self.reserve_ibft_nic()
        self.assertEqual(self.provider.applyDriverVariants([("enic", "oem")]), [])
        self.assertEqual(
            self.provider.getInUseDriverVariants(), [("enic", "oem")]
        )

    def test_already_active_variant_is_still_selected_and_not_reported(self):
        self.reserve_ibft_nic()
        self.selected = "oem"
        self.assertEqual(self.provider.applyDriverVariants([("enic", "generic")]), [])
        self.assert_only_selects()
        self.assertEqual(self.selected, "generic")
        self.assertEqual(self.provider.getInUseDriverVariants(), [])

    def test_reports_are_reset_when_the_selection_is_reapplied(self):
        self.reserve_ibft_nic()
        self.provider.applyDriverVariants([("enic", "oem")])
        self.provider.applyDriverVariants([("enic", "generic")])
        self.assertEqual(self.provider.getInUseDriverVariants(), [])

    def test_driver_of_an_unreserved_nic_still_reloads(self):
        self.nic_drivers["eno5"] = "enic"
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "oem"))
        self.assert_reloads("oem")

    def test_driver_of_a_different_reserved_nic_still_reloads(self):
        self.reserve_ibft_nic(nic="eth0", driver="bnx2")
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "oem"))
        self.assert_reloads("oem")

    def test_reserved_nic_without_a_driver_link_still_reloads(self):
        self.reserve_ibft_nic(driver=None)
        self.assertTrue(self.provider.selectSingleDriverVariant("enic", "oem"))
        self.assert_reloads("oem")

    def test_boot_path_drivers_are_read_from_the_reserved_nics(self):
        self.reserve_ibft_nic()
        self.assertEqual(dmvutil.getBootPathDrivers(), {"enic"})

    def test_no_boot_path_drivers_without_ibft_disks(self):
        self.nic_drivers["eno5"] = "enic"
        self.assertEqual(dmvutil.getBootPathDrivers(), set())

    def test_nic_driver_link_is_resolved_to_a_module_name(self):
        self.nic_drivers["eno5"] = "enic"
        self.assertEqual(dmvutil.getNicDriver("eno5"), "enic")
        self.assertIsNone(dmvutil.getNicDriver("eno6"))


if __name__ == "__main__":
    unittest.main()