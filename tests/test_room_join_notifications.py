#!/usr/bin/env python3
"""
Unit tests for room join notification behavior.
"""

import asyncio
import os
import sys
import unittest
from unittest import mock
from unittest.mock import AsyncMock

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import publish


class TestRoomJoinNotifications(unittest.IsolatedAsyncioTestCase):
    async def test_build_room_join_payload_contains_expected_fields(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.room_name = "qa_room"

        payload = client._build_room_join_payload("stream123", "uuid456", "joinroom")

        self.assertEqual(payload["event"], "streamAdded")
        self.assertEqual(payload["roomEvent"], "room_join")
        self.assertEqual(payload["room"], "qa_room")
        self.assertEqual(payload["streamID"], "stream123")
        self.assertEqual(payload["uuid"], "uuid456")
        self.assertEqual(payload["source"], "joinroom")
        self.assertIsInstance(payload["timestamp"], int)

    async def test_send_room_join_postapi_wraps_update_payload(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.join_postapi_url = "https://example.invalid/postapi"
        client.join_notify_timeout = 1.0

        captured = {}

        def fake_post(url, payload):
            captured["url"] = url
            captured["payload"] = payload
            return 200

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        payload = {
            "streamID": "streamABC",
            "room": "roomX",
            "event": "streamAdded",
            "roomEvent": "room_join",
        }

        client._post_json_blocking = fake_post

        with mock.patch("publish.asyncio.to_thread", new=fake_to_thread):
            await client._send_room_join_postapi(payload)

        self.assertEqual(captured["url"], "https://example.invalid/postapi")
        self.assertIn("update", captured["payload"])
        self.assertEqual(captured["payload"]["update"]["action"], "streamAdded")
        self.assertEqual(captured["payload"]["update"]["streamID"], "streamABC")
        self.assertEqual(captured["payload"]["update"]["value"]["roomEvent"], "room_join")

    async def test_send_room_join_notify_topic_formats_query(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.join_notify_topic = "topic_123"
        client.join_notify_url = "https://notify.vdo.ninja/"
        client.join_notify_timeout = 1.0
        client.room_name = "test_room"

        captured = {}

        def fake_get(url):
            captured["url"] = url
            return 200

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        client._get_url_blocking = fake_get
        payload = {"streamID": "abc123"}

        with mock.patch("publish.asyncio.to_thread", new=fake_to_thread):
            await client._send_room_join_notify_topic(payload)

        self.assertIn("notify=topic_123", captured["url"])
        self.assertIn("message=Stream+abc123+joined+test_room", captured["url"])

    async def test_handle_new_room_stream_tracks_and_notifies_in_monitor_mode(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.stream_filter = None
        client.room_streams = {}
        client.room_streams_lock = asyncio.Lock()
        client.room_join_notifications_enabled = True
        client.room_recording = False
        client.room_ndi = False

        queued_labels = []

        def fake_queue(coro, label):
            queued_labels.append(label)
            coro.close()

        client._queue_background_task = fake_queue
        client.create_subprocess_recorder = AsyncMock()

        await client.handle_new_room_stream("stream_1", "uuid_1", source="joinroom")

        self.assertIn("uuid_1", client.room_streams)
        self.assertEqual(client.room_streams["uuid_1"]["streamID"], "stream_1")
        self.assertIn("room join notify stream_1", queued_labels)
        client.create_subprocess_recorder.assert_not_awaited()

    async def test_handle_new_room_stream_triggers_recorder_when_room_recording(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.stream_filter = None
        client.room_streams = {}
        client.room_streams_lock = asyncio.Lock()
        client.room_join_notifications_enabled = False
        client.room_recording = True
        client.room_ndi = False
        client.create_subprocess_recorder = AsyncMock()

        await client.handle_new_room_stream("stream_rec", "uuid_rec", source="someonejoined")

        client.create_subprocess_recorder.assert_awaited_once_with("stream_rec", "uuid_rec")

    async def test_handle_new_room_stream_ignores_duplicate_stream(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.stream_filter = None
        client.room_streams = {"existing_uuid": {"streamID": "dup_stream", "recording": False}}
        client.room_streams_lock = asyncio.Lock()
        client.room_join_notifications_enabled = True
        client.room_recording = True
        client.room_ndi = False

        client._queue_background_task = mock.Mock()
        client.create_subprocess_recorder = AsyncMock()

        await client.handle_new_room_stream("dup_stream", "new_uuid", source="videoaddedtoroom")

        client._queue_background_task.assert_not_called()
        client.create_subprocess_recorder.assert_not_awaited()
        self.assertNotIn("new_uuid", client.room_streams)

    async def test_handle_room_listing_monitor_mode_tracks_current_streams(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.room_recording = False
        client.room_ndi = False
        client.room_monitor = True
        client.stream_filter = None
        client.room_streams = {}
        client.room_streams_lock = asyncio.Lock()

        room_list = [
            {"UUID": "u1", "streamID": "s1"},
            {"UUID": "u2", "streamID": "s2"},
            {"UUID": "u3"},  # not publishing
        ]

        await client.handle_room_listing(room_list)

        self.assertEqual(len(client.room_streams), 2)
        self.assertEqual(client.room_streams["u1"]["streamID"], "s1")
        self.assertEqual(client.room_streams["u2"]["streamID"], "s2")


if __name__ == "__main__":
    unittest.main()
