import unittest
from unittest import mock

import publish


class FakeSelector:
    def __init__(self, properties, rejected=()):
        self.properties = set(properties)
        self.rejected = set(rejected)
        self.values = {}

    def find_property(self, name):
        return object() if name in self.properties else None

    def set_property(self, name, value):
        if name in self.rejected:
            raise TypeError(f"unsupported value for {name}")
        self.values[name] = value


class FakePad:
    def __init__(self):
        self.values = {}

    def set_property(self, name, value):
        self.values[name] = value


class FakeEventLoop:
    def __init__(self):
        self.callback = None
        self.args = None

    def is_running(self):
        return True

    def call_soon_threadsafe(self, callback, *args):
        self.callback = callback
        self.args = args


class V4L2SinkSwitchingTests(unittest.TestCase):
    def test_common_sink_does_not_retime_across_source_switches(self):
        caps = "video/x-raw,format=YUY2,width=(int)1280,height=(int)720,framerate=(fraction)30/1"
        description = publish.build_v4l2sink_sink_description(
            "/dev/video17", 0, caps
        )

        self.assertNotIn("videorate", description)
        self.assertNotIn("videoscale", description)
        self.assertIn("videoconvert", description)
        self.assertIn(caps, description)
        self.assertIn("drop-allocation=true", description)
        self.assertIn('device="/dev/video17"', description)
        self.assertIn("io-mode=0", description)

    def test_h264_v4l2_output_prefers_resilient_viewer_decoder(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.disable_hw_decoder = False
        client._force_hw_decoder = False

        with mock.patch.object(publish, "is_jetson_device", return_value=False), mock.patch.object(
            publish, "gst_element_available", return_value=True
        ):
            decoder, using_hardware = client._get_v4l2sink_decoder_description(
                "H264", publish.H264_VIEWER_DECODER_FALLBACKS
            )

        self.assertEqual(decoder, "avdec_h264")
        self.assertFalse(using_hardware)

    def test_h264_v4l2_output_keeps_openh264_fallback(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.disable_hw_decoder = False
        client._force_hw_decoder = False

        with mock.patch.object(publish, "is_jetson_device", return_value=False), mock.patch.object(
            publish,
            "gst_element_available",
            side_effect=lambda name: name == "openh264dec",
        ):
            decoder, using_hardware = client._get_v4l2sink_decoder_description(
                "H264", publish.H264_VIEWER_DECODER_FALLBACKS
            )

        self.assertEqual(decoder, "openh264dec")
        self.assertFalse(using_hardware)

    def test_live_selector_uses_clock_synchronization(self):
        selector = FakeSelector(
            {"sync-streams", "sync-mode", "cache-buffers", "drop-backwards"}
        )

        applied = publish.configure_live_input_selector(selector)

        self.assertEqual(
            selector.values,
            {
                "sync-streams": True,
                "sync-mode": "clock",
                "cache-buffers": True,
                "drop-backwards": True,
            },
        )
        self.assertEqual(applied, selector.values)

    def test_live_selector_supports_legacy_gstreamer_properties(self):
        selector = FakeSelector({"sync-streams", "sync-mode", "cache-buffers"})

        applied = publish.configure_live_input_selector(selector)

        self.assertEqual(applied["sync-mode"], "clock")
        self.assertNotIn("drop-backwards", applied)

    def test_live_selector_keeps_configuring_after_vendor_property_error(self):
        selector = FakeSelector(
            {"sync-streams", "sync-mode", "cache-buffers", "drop-backwards"},
            rejected={"sync-mode"},
        )

        applied = publish.configure_live_input_selector(selector)

        self.assertNotIn("sync-mode", applied)
        self.assertTrue(applied["cache-buffers"])
        self.assertTrue(applied["drop-backwards"])

    def make_client(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.v4l2sink_selector = FakeSelector({"active-pad"})
        client.v4l2sink_selector_kind = "selector"
        client.v4l2sink_current_pad = FakePad()
        client.v4l2sink_state = "idle"
        client.v4l2sink_sources = {}
        return client

    def test_compositor_switches_visibility_without_replacing_output_stream(self):
        client = self.make_client()
        client.v4l2sink_selector_kind = "compositor"
        blank_pad = FakePad()
        remote_pad = FakePad()
        client.v4l2sink_sources = {
            "blank": {"selector_pad": blank_pad, "ready": True},
            "remote_src_0": {"selector_pad": remote_pad, "ready": True},
        }

        activated = client._activate_v4l2sink_source("remote_src_0")

        self.assertTrue(activated)
        self.assertEqual(blank_pad.values["alpha"], 0.0)
        self.assertEqual(remote_pad.values["alpha"], 1.0)
        self.assertIs(client.v4l2sink_current_pad, remote_pad)

    def test_compositor_idle_mode_blanks_remote_sources(self):
        client = self.make_client()
        client.v4l2sink_selector_kind = "compositor"
        remote_pad = FakePad()
        remote_pad.set_property("alpha", 1.0)
        client.v4l2sink_sources = {
            "remote_src_0": {"selector_pad": remote_pad, "ready": True},
        }

        client._set_v4l2sink_mode("idle")

        self.assertEqual(remote_pad.values["alpha"], 0.0)
        self.assertEqual(client.v4l2sink_state, "idle")
        self.assertIsNone(client.v4l2sink_current_pad)

    def test_v4l2_output_does_not_build_a_physical_display_chain(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.v4l2sink_device = "/dev/video17"

        self.assertIsNone(client._ensure_display_chain())

    def test_display_state_callbacks_are_routed_to_v4l2_output(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.v4l2sink_device = "/dev/video17"
        client._set_v4l2sink_mode = mock.Mock()

        client._set_display_mode("idle")

        client._set_v4l2sink_mode.assert_called_once_with(
            "idle", remote_label=None
        )

    def test_remote_source_waits_for_first_frame_before_switching(self):
        client = self.make_client()
        remote_pad = FakePad()
        source = {"selector_pad": remote_pad, "ready": False}
        client.v4l2sink_sources["remote_src_0"] = source

        client._set_v4l2sink_mode("remote", remote_label="remote_src_0")

        self.assertEqual(client.v4l2sink_state, "idle")
        self.assertTrue(source["activate_when_ready"])
        self.assertNotIn("active-pad", client.v4l2sink_selector.values)

        keep_idle_callback = client._mark_v4l2sink_source_ready(
            "remote_src_0", source
        )

        self.assertFalse(keep_idle_callback)
        self.assertEqual(client.v4l2sink_state, "remote")
        self.assertIs(client.v4l2sink_current_pad, remote_pad)
        self.assertIs(client.v4l2sink_selector.values["active-pad"], remote_pad)

    def test_stale_first_frame_callback_cannot_activate_replacement(self):
        client = self.make_client()
        old_source = {"selector_pad": FakePad(), "ready": False}
        replacement = {"selector_pad": FakePad(), "ready": False}
        client.v4l2sink_sources["remote_src_0"] = replacement

        client._mark_v4l2sink_source_ready("remote_src_0", old_source)

        self.assertEqual(client.v4l2sink_state, "idle")
        self.assertNotIn("active-pad", client.v4l2sink_selector.values)

    def test_first_frame_switch_is_scheduled_on_asyncio_loop(self):
        client = self.make_client()
        client.event_loop = FakeEventLoop()
        source = {
            "selector_pad": FakePad(),
            "ready": False,
            "activate_when_ready": True,
        }
        client.v4l2sink_sources["remote_src_0"] = source

        result = client._on_v4l2sink_source_buffer(
            source["selector_pad"], None, ("remote_src_0", source)
        )

        self.assertEqual(result, publish.Gst.PadProbeReturn.REMOVE)
        self.assertFalse(source["ready"])
        self.assertIsNotNone(client.event_loop.callback)

        client.event_loop.callback(*client.event_loop.args)

        self.assertTrue(source["ready"])
        self.assertEqual(client.v4l2sink_state, "remote")


if __name__ == "__main__":
    unittest.main()
