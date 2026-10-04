import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import publish
import webrtc_subprocess_glib


class SingleStreamRecordingTests(unittest.TestCase):
    def test_recording_filename_matches_selected_container(self):
        self.assertEqual(
            webrtc_subprocess_glib.filename_for_container("capture.webm", "mp4"),
            "capture.mp4",
        )
        self.assertEqual(
            webrtc_subprocess_glib.filename_for_container("capture.WEBM", "webm"),
            "capture.WEBM",
        )

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

    def test_subprocess_sigint_is_a_clean_shutdown(self):
        handler = MagicMock()
        handler.run.side_effect = KeyboardInterrupt

        with (
            patch("webrtc_subprocess_glib.sys.stdin", StringIO("{}\n")),
            patch("webrtc_subprocess_glib.sys.stderr", new_callable=StringIO) as stderr,
            patch("webrtc_subprocess_glib.GLibWebRTCHandler", return_value=handler),
        ):
            webrtc_subprocess_glib.main()

        handler.shutdown.assert_called_once_with()
        self.assertEqual(stderr.getvalue(), "")


class RecordingFinalizationTests(unittest.TestCase):
    def make_handler(self, video=None, audio=None):
        return SimpleNamespace(
            pipe=MagicMock(),
            recording_video=video is not None,
            recording_audio=audio is not None,
            recording_video_queue=video,
            recording_audio_queue=audio,
            log=MagicMock(),
        )

    def test_eos_is_enqueued_after_buffered_media_in_each_recording_queue(self):
        video, audio = MagicMock(), MagicMock()
        handler = self.make_handler(video, audio)
        handler.pipe.get_bus.return_value.timed_pop_filtered.return_value = None

        webrtc_subprocess_glib.GLibWebRTCHandler.finalize_recordings(handler, 2)

        for queue in (video, audio):
            queue.get_static_pad.assert_called_once_with("sink")
            queue.get_static_pad.return_value.send_event.assert_called_once()
            event = queue.get_static_pad.return_value.send_event.call_args.args[0]
            self.assertEqual(event.type, webrtc_subprocess_glib.Gst.EventType.EOS)
            queue.get_static_pad.return_value.push_event.assert_not_called()
        handler.pipe.get_bus.return_value.timed_pop_filtered.assert_called_once_with(
            2 * webrtc_subprocess_glib.Gst.SECOND,
            webrtc_subprocess_glib.Gst.MessageType.EOS | webrtc_subprocess_glib.Gst.MessageType.ERROR,
        )

    def test_same_queue_is_finalized_once(self):
        queue = MagicMock()
        handler = self.make_handler(queue, queue)
        webrtc_subprocess_glib.GLibWebRTCHandler.finalize_recordings(handler)
        queue.get_static_pad.assert_called_once_with("sink")
        queue.get_static_pad.return_value.send_event.assert_called_once()

    def test_other_branch_is_finalized_when_one_rejects_eos(self):
        video, audio = MagicMock(), MagicMock()
        video.get_static_pad.return_value.send_event.return_value = False
        handler = self.make_handler(video, audio)
        webrtc_subprocess_glib.GLibWebRTCHandler.finalize_recordings(handler)
        audio.get_static_pad.return_value.send_event.assert_called_once()
        handler.pipe.get_bus.assert_called_once()

    def test_other_branch_is_finalized_when_one_raises(self):
        video, audio = MagicMock(), MagicMock()
        video.get_static_pad.return_value.send_event.side_effect = RuntimeError("stopped")
        handler = self.make_handler(video, audio)
        webrtc_subprocess_glib.GLibWebRTCHandler.finalize_recordings(handler)
        audio.get_static_pad.return_value.send_event.assert_called_once()
        handler.pipe.get_bus.assert_called_once()

    def test_does_not_wait_when_no_branch_accepts_eos(self):
        for missing_pad in (False, True):
            with self.subTest(missing_pad=missing_pad):
                queue = MagicMock()
                if missing_pad:
                    queue.get_static_pad.return_value = None
                else:
                    queue.get_static_pad.return_value.send_event.return_value = False
                handler = self.make_handler(queue)
                webrtc_subprocess_glib.GLibWebRTCHandler.finalize_recordings(handler)
                handler.pipe.get_bus.assert_not_called()

    def test_does_not_finalize_when_recording_has_not_started(self):
        handler = self.make_handler()
        webrtc_subprocess_glib.GLibWebRTCHandler.finalize_recordings(handler)
        handler.pipe.get_bus.assert_not_called()


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
