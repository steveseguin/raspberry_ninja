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


class RecordingCodecLinkingTests(unittest.TestCase):
    def test_file_recording_uses_the_selected_codec_chain(self):
        for codec, expected in (
            ("VP8", ["queue", "rtpvp8depay", "webmmux", "filesink"]),
            ("VP9", ["queue", "rtpvp9depay", "webmmux", "filesink"]),
            ("AV1", ["queue", "rtpav1depay", "webmmux", "filesink"]),
            ("H264", ["queue", "rtph264depay", "h264parse", "mpegtsmux", "filesink"]),
        ):
            with self.subTest(codec=codec):
                elements = {}
                links = []

                def make(factory, _name):
                    element = MagicMock(name=factory)
                    element.factory = factory
                    element.link.side_effect = (
                        lambda target, source=factory:
                        links.append((source, target.factory)) or True
                    )
                    elements[factory] = element
                    return element

                handler = SimpleNamespace(
                    use_hls=False,
                    room_ndi=False,
                    stream_id="test-stream",
                    recording_video=False,
                    pipe=MagicMock(),
                    log=MagicMock(),
                    on_pad_probe=MagicMock(),
                    recording_output_file=MagicMock(
                        side_effect=lambda extension: "capture." + extension
                    ),
                )
                pad = MagicMock()
                structure = pad.get_current_caps.return_value.get_structure.return_value
                structure.get_string.return_value = codec
                structure.has_field.return_value = False
                pad.link.return_value = webrtc_subprocess_glib.Gst.PadLinkReturn.OK

                with patch("webrtc_subprocess_glib.Gst.ElementFactory.make", side_effect=make):
                    webrtc_subprocess_glib.GLibWebRTCHandler.handle_video_pad(handler, pad)

                self.assertEqual(links, list(zip(expected, expected[1:])))
                self.assertEqual(set(elements), set(expected))
                self.assertTrue(handler.recording_video)
                self.assertIs(handler.recording_video_queue, elements["queue"])
                extension = "ts" if codec == "H264" else "webm"
                self.assertEqual(handler.video_filename, "capture." + extension)
                elements["filesink"].set_property.assert_called_once_with(
                    "location", "capture." + extension
                )
                for element in elements.values():
                    handler.pipe.add.assert_any_call(element)
                    element.sync_state_with_parent.assert_called_once_with()
                pad.link.assert_called_once_with(elements["queue"].get_static_pad("sink"))


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
