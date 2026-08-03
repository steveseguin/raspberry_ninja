import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import publish


class SingleStreamRecordingTests(unittest.TestCase):
    def test_requested_stream_id_is_preserved_for_subprocess_recording(self):
        args = SimpleNamespace(
            record="camera-stream",
            streamin=None,
            single_stream_recording=False,
            room_recording=True,
            auto_turn=False,
        )

        publish.configure_single_stream_recording(args)

        self.assertEqual(args.streamin, "camera-stream")
        self.assertTrue(args.single_stream_recording)
        self.assertFalse(args.room_recording)
        self.assertTrue(args.auto_turn)


class SingleStreamRecordingOfferTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_offer_starts_recorder_without_duplicate_play_request(self):
        client = SimpleNamespace(
            subprocess_managers={},
            uuid_to_stream_id={},
            stream_id_to_uuid={},
        )

        async def start_recorder(stream_id, uuid, request_play=True):
            self.assertFalse(request_play)
            client.subprocess_managers[stream_id] = object()

        client.create_subprocess_recorder = AsyncMock(side_effect=start_recorder)
        client.handle_subprocess_offer = AsyncMock()

        routed = await publish.WebRTCClient.route_single_stream_recording_offer(
            client,
            "camera-stream",
            "peer-uuid",
            "v=0\r\n",
            "session-id",
        )

        self.assertTrue(routed)
        self.assertEqual(client.uuid_to_stream_id, {"peer-uuid": "camera-stream"})
        self.assertEqual(client.stream_id_to_uuid, {"camera-stream": "peer-uuid"})
        client.create_subprocess_recorder.assert_awaited_once_with(
            "camera-stream",
            "peer-uuid",
            request_play=False,
        )
        client.handle_subprocess_offer.assert_awaited_once_with(
            "camera-stream",
            "v=0\r\n",
            "session-id",
        )


if __name__ == "__main__":
    unittest.main()
