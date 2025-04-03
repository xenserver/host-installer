""" Unit test module for netutil"""
import unittest
import sys
import re  # Import re for the regular expression
import os.path

from import_helper import mocked_modules, create_mock_module

sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '..'))


# Following are stolen from python-xcp-lib to decouple the runtime deps

_SBDF = (r"(?:(?P<segment> [\da-dA-F]{4}):)?" # Segment (optional)
        r"     (?P<bus>     [\da-fA-F]{2}):"   # Bus
        r"     (?P<device>  [\da-fA-F]{2})\."  # Device
        r"     (?P<function>[\da-fA-F])"       # Function
        )

VALID_SBDFI = re.compile(
        r"^(?P<sbdf>%s)"
        r"  (?:[\[](?P<index>[\d]{1,2})[\]])?$"   # Index (optional)
        % _SBDF
        , re.X)

VALID_COLON_MAC = re.compile(r"^([\da-fA-F]{1,2}:){5}[\da-fA-F]{1,2}$")

mock_xcp_pci = create_mock_module("xcp.pci", { "VALID_SBDFI": VALID_SBDFI})
mock_xcp_net_mac = create_mock_module("xcp.net.mac", { "VALID_COLON_MAC": VALID_COLON_MAC})

sys.modules["xcp.pci"] = mock_xcp_pci
sys.modules["xcp.net.mac"] = mock_xcp_net_mac

with mocked_modules("xcp", "version", "diskutil", "xcp.net", "xcp.net.biosdevname", "xcp.logger"):
    # Import the module under test
    import netutil
    from netutil import Rule, parse_interface_slot, parse_rule, generate_interface_rules, save_inteface_rules


class TestInterfaceRules(unittest.TestCase):
    """Test class"""
    def test_slot(self):
        """
        slot number can be [eth]X for backword compatbility
        """
        rule1 = Rule(1, "mac", "00:11:22:33:44:55")
        rule2 = parse_rule("eth1:s:00:11:22:33:44:55")
        rule3 = parse_rule("1:s:00:11:22:33:44:55")
        self.assertEqual(rule1, rule2)
        self.assertEqual(rule1, rule3)

    def test_rule_without_colon_taken_as_label(self):
        """interface without colon take as label"""
        rule1 = parse_rule("1:ens2")
        self.assertEqual(rule1, Rule(1, "label", "ens2"))

    def test_rule_with_quote_take_as_label(self):
        """interface quoted should taken as label"""
        rule1 = parse_rule('1:"ens2"')
        self.assertEqual(rule1, Rule(1, "label", "ens2"))

    def test_rule_type(self):
        """
        rule type (dynamic|static) just ignored
        """
        rule1 = Rule(1, "mac", "00:11:22:33:44:55")
        rule2 = parse_rule("eth1:s:00:11:22:33:44:55")
        rule3 = parse_rule("1:d:00:11:22:33:44:55")
        rule4 = parse_rule("1:00:11:22:33:44:55")
        self.assertEqual(rule1, rule2)
        self.assertEqual(rule1, rule3)
        self.assertEqual(rule1, rule4)

    def test_invalid_interface_by_mac(self):
        """
        invalid mac should got no rule
        """
        rule = parse_rule("eth1:s:00:11:22:33:44:55:88")
        self.assertEqual(rule, None)

    def test_valid_interface_by_label(self):
        """
        Interface can be identified by label
        """
        label= "ens4"
        rule = parse_rule(f'1:"{label}"')
        self.assertEqual(rule, Rule(1, "label", "ens4"))

    def test_valid_interface_by_pci(self):
        """
        Interface can be identified by pci address
        """
        pci = "0000:00:1f.0"
        rule = parse_rule(f'1:{pci}')
        self.assertEqual(rule, Rule(1, "pci", "0000:00:1f.0"))

    def  test_ignore_duplicated_slot(self):
        """
        Later duplicated rule will just be ingored
        """
        generate_interface_rules(['1:"ens4"', '1:"ens5"'])
        self.assertListEqual(netutil.interface_rules, [Rule(1, "label", "ens4")])

    def test_rule_print_format(self):
        """
        Output rules should match format
        """
        rule = Rule(1, "mac", "00:11:22:33:44:55")
        self.assertEqual('1:mac="00:11:22:33:44:55"', str(rule))

    def test_generate_rules(self):
        """
        Generate multiple rules, sorted by slot
        """
        generate_interface_rules(['1:"ens4"', '3:"ens6"', '2:"ens5"'])
        self.assertListEqual(netutil.interface_rules,
                             [ Rule(1, "label", "ens4"),
                               Rule(2, "label", "ens5"),
                               Rule(3, "label", "ens6")]
                            )
