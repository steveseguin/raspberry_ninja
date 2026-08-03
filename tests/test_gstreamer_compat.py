import unittest

import publish
import webrtc_subprocess_glib


class CurrentElement:
    def request_pad_simple(self, name):
        return ("current", name)


class LegacyElement:
    def get_request_pad(self, name):
        return ("legacy", name)


class GStreamerRequestPadCompatibilityTests(unittest.TestCase):
    def test_publish_uses_current_api_when_available(self):
        self.assertEqual(
            publish.request_pad_compat(CurrentElement(), "video"),
            ("current", "video"),
        )

    def test_publish_falls_back_to_legacy_api(self):
        self.assertEqual(
            publish.request_pad_compat(LegacyElement(), "audio_%u"),
            ("legacy", "audio_%u"),
        )

    def test_subprocess_falls_back_to_legacy_api(self):
        self.assertEqual(
            webrtc_subprocess_glib.request_pad_compat(LegacyElement(), "sink_%d"),
            ("legacy", "sink_%d"),
        )


if __name__ == "__main__":
    unittest.main()
