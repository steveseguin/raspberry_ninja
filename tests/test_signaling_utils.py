import unittest

from signaling_utils import handshake_server_requires_puuid


class TestSignalingUtils(unittest.TestCase):
    def test_primary_server_does_not_require_puuid(self):
        self.assertFalse(handshake_server_requires_puuid("wss://wss.vdo.ninja:443"))

    def test_backup_server_does_not_require_puuid(self):
        self.assertFalse(handshake_server_requires_puuid("apibackup.vdo.ninja:443"))

    def test_custom_server_requires_puuid(self):
        self.assertTrue(handshake_server_requires_puuid("wss://signal.example.test:443"))


if __name__ == "__main__":
    unittest.main()
