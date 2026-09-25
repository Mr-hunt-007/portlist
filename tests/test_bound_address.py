"""A listener bound to one interface must be checked on that interface."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plcore import risk, scan  # noqa: E402


class BoundAddressTests(unittest.TestCase):
    def setUp(self):
        self.host = {"lan": [
            {"ip": "192.0.2.10", "iface": "ethernet"},
            {"ip": "100.64.0.42", "iface": "tailscale0"},
        ]}

    def test_specific_bind_is_probed_and_verified_at_its_own_address(self):
        addrs = {"100.64.0.42"}
        ips = [a["ip"] for a in self.host["lan"]]
        self.assertEqual(scan._probe_host(addrs, ips), "100.64.0.42")
        with patch.object(risk.collect, "reachable_from", return_value=True) as connect:
            verified = risk.verify_exposure("lan", 3110, self.host, addrs)
        connect.assert_called_once_with("100.64.0.42", 3110)
        self.assertTrue(verified["accepting"])
        self.assertEqual(verified["iface"], "tailscale0")

    def test_specific_bind_on_unknown_interface_is_not_called_unreachable(self):
        with patch.object(risk.collect, "reachable_from") as connect:
            verified = risk.verify_exposure("lan", 3110, self.host, {"198.51.100.10"})
        connect.assert_not_called()
        self.assertIsNone(verified)

    def test_multiple_specific_binds_accept_if_one_address_answers(self):
        addrs = {"192.0.2.10", "100.64.0.42"}
        with patch.object(risk.collect, "reachable_from", side_effect=[False, True]) as connect:
            verified = risk.verify_exposure("lan", 3110, self.host, addrs)
        self.assertEqual(connect.call_count, 2)
        self.assertEqual(verified["ip"], "100.64.0.42")
        self.assertTrue(verified["accepting"])
        self.assertEqual(scan._probe_host(addrs, [a["ip"] for a in self.host["lan"]],
                                          verified=verified["ip"]), "100.64.0.42")

    def test_shared_port_verification_is_separate_for_each_bind(self):
        scan._verify_cache.clear()
        try:
            with patch.object(risk, "verify_exposure", side_effect=[{"ip": "192.0.2.10"},
                                                             {"ip": "100.64.0.42"}]) as verify:
                first = scan._verify("lan", 3110, self.host, {"192.0.2.10"})
                second = scan._verify("lan", 3110, self.host, {"100.64.0.42"})
            self.assertEqual(verify.call_count, 2)
            self.assertNotEqual(first, second)
        finally:
            scan._verify_cache.clear()


if __name__ == "__main__":
    unittest.main()
