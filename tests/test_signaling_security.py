import ssl
import unittest

import publish


class SignalingSecurityTests(unittest.TestCase):
    def test_secure_wss_uses_one_verified_attempt(self):
        attempts = publish.build_signaling_connection_attempts(
            "wss://wss.vdo.ninja:443"
        )

        self.assertEqual(len(attempts), 1)
        label, url, context = attempts[0]
        self.assertEqual(label, "verified TLS")
        self.assertEqual(url, "wss://wss.vdo.ninja:443")
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_insecure_fallback_requires_explicit_opt_in(self):
        attempts = publish.build_signaling_connection_attempts(
            "wss://legacy.example.test/socket",
            allow_insecure=True,
        )

        self.assertEqual([attempt[0] for attempt in attempts], [
            "verified TLS",
            "unverified TLS",
            "plaintext WebSocket fallback",
        ])
        self.assertEqual(attempts[1][2].verify_mode, ssl.CERT_NONE)
        self.assertFalse(attempts[1][2].check_hostname)
        self.assertEqual(attempts[2][1], "ws://legacy.example.test/socket")
        self.assertIsNone(attempts[2][2])

    def test_explicit_plaintext_url_is_not_silently_rewritten(self):
        attempts = publish.build_signaling_connection_attempts(
            "ws://127.0.0.1:8080"
        )

        self.assertEqual(
            attempts,
            [("plaintext WebSocket (explicit URL)", "ws://127.0.0.1:8080", None)],
        )

    def test_non_websocket_scheme_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "use wss:// or ws://"):
            publish.build_signaling_connection_attempts("https://example.test")


if __name__ == "__main__":
    unittest.main()
