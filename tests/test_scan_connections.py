"""Connection counts belong to listening ports, not every socket of a process."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plcore.scan import _public_inbound_count  # noqa: E402


class PublicInboundCountTests(unittest.TestCase):
    def test_outbound_https_does_not_create_visitors_at_every_listener(self):
        # One process listens on 7800 and 34999 while also calling a public API.
        connections = [
            {"lport": 34986, "rport": 443, "scope": "public"},
            {"lport": 7800, "rport": 50123, "scope": "public"},
            {"lport": 34999, "rport": 50124, "scope": "loopback"},
        ]

        self.assertEqual(_public_inbound_count(connections, 7800), 1)
        self.assertEqual(_public_inbound_count(connections, 34999), 0)


if __name__ == "__main__":
    unittest.main()
