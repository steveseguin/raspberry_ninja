import json
import unittest

import publish


class FakeDataChannel:
    def __init__(self, fail=False):
        self.fail = fail
        self.emitted = []

    def emit(self, signal, payload):
        if self.fail:
            raise RuntimeError("channel closed")
        self.emitted.append((signal, payload))


class DataChannelHeartbeatTests(unittest.TestCase):
    def test_ping_is_answered_and_resets_liveness_counter(self):
        channel = FakeDataChannel()
        client = {"ping": 7}

        handled = publish.handle_data_channel_heartbeat(
            channel, {"ping": "123.5"}, client
        )

        self.assertTrue(handled)
        self.assertEqual(client["ping"], 0)
        self.assertEqual(channel.emitted[0][0], "send-string")
        self.assertEqual(json.loads(channel.emitted[0][1]), {"pong": "123.5"})

    def test_pong_resets_liveness_counter_without_response(self):
        channel = FakeDataChannel()
        client = {"ping": 4}

        handled = publish.handle_data_channel_heartbeat(
            channel, {"pong": "123.5"}, client
        )

        self.assertTrue(handled)
        self.assertEqual(client["ping"], 0)
        self.assertEqual(channel.emitted, [])

    def test_non_heartbeat_message_is_not_consumed(self):
        channel = FakeDataChannel()
        client = {"ping": 2}

        handled = publish.handle_data_channel_heartbeat(
            channel, {"candidate": "candidate:1"}, client
        )

        self.assertFalse(handled)
        self.assertEqual(client["ping"], 2)
        self.assertEqual(channel.emitted, [])

    def test_closed_channel_does_not_escape_callback(self):
        channel = FakeDataChannel(fail=True)
        client = {"ping": 9}

        handled = publish.handle_data_channel_heartbeat(
            channel, {"ping": 123}, client
        )

        self.assertTrue(handled)
        self.assertEqual(client["ping"], 0)


if __name__ == "__main__":
    unittest.main()
