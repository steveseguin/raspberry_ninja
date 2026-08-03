import asyncio
import json
import ssl
import unittest

import publish
import websockets


class SignalingSecurityTests(unittest.TestCase):
    def test_explicit_ws_url_survives_cli_normalization(self):
        self.assertEqual(
            publish.normalize_signaling_server_url("ws://127.0.0.1:8080/socket"),
            "ws://127.0.0.1:8080/socket",
        )

    def test_bare_server_defaults_to_verified_wss(self):
        self.assertEqual(
            publish.normalize_signaling_server_url("relay.example.test:4443/socket"),
            "wss://relay.example.test:4443/socket",
        )

    def test_normalization_rejects_non_websocket_schemes(self):
        with self.assertRaisesRegex(ValueError, "must use ws:// or wss://"):
            publish.normalize_signaling_server_url("https://example.test")

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


class PlainWebSocketEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_connects_and_seeds_over_explicit_ws(self):
        received = asyncio.Queue()

        async def handler(websocket, path=None):
            received.put_nowait(await websocket.recv())
            await websocket.wait_closed()

        server = await websockets.serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.view = False
        client.server = publish.normalize_signaling_server_url(
            f"ws://127.0.0.1:{port}"
        )
        client.hostname = None
        client.insecure_signaling = False
        client.conn = None
        client.room_hashcode = None
        client.room_name = None
        client.streamin = None
        client.stream_id = "plain-ws-probe"
        client.hashcode = ""
        client.puuid = None
        client.clients = {}
        client.password = None
        client.salt = ""

        try:
            await client.connect()
            message = json.loads(await asyncio.wait_for(received.get(), timeout=2))
            self.assertEqual(
                message,
                {"request": "seed", "streamID": "plain-ws-probe"},
            )
        finally:
            if client.conn is not None:
                await client.conn.close()
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
