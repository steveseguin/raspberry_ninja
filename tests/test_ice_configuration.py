import unittest

import publish


class FakeWebRTC:
    def __init__(self):
        self.properties = {}

    def set_property(self, name, value):
        self.properties[name] = value


class IceConfigurationTests(unittest.TestCase):
    def test_false_disables_stun(self):
        for value in ("false", "0", "off", "none", "null"):
            with self.subTest(value=value):
                self.assertEqual(publish.normalize_stun_server_option(value), (None, True))

    def test_explicit_stun_url_is_preserved(self):
        value = "stun://stun.example.test:3478"
        self.assertEqual(publish.normalize_stun_server_option(value), (value, False))

    def test_disabled_stun_clears_webrtc_property(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.stun_server = None
        client.no_stun = True
        client.turn_server = None
        client.auto_turn = False
        client.ice_transport_policy = "all"
        webrtc = FakeWebRTC()

        client.setup_ice_servers(webrtc)

        self.assertIn("stun-server", webrtc.properties)
        self.assertIsNone(webrtc.properties["stun-server"])


if __name__ == "__main__":
    unittest.main()
