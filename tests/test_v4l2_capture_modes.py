import unittest
from unittest.mock import patch

import publish


V4L2_SAMPLE = """\
    [0]: 'MJPG' (Motion-JPEG, compressed)
        Size: Discrete 1280x720
            Interval: Discrete 0.008s (120.000 fps)
        Size: Discrete 640x360
            Interval: Discrete 0.005s (210.000 fps)
    [1]: 'YUYV' (YUYV 4:2:2)
        Size: Discrete 640x480
            Interval: Discrete 0.033s (30.000 fps)
    [2]: 'H264' (H.264, compressed)
        Size: Discrete 1920x1080
            Interval: Discrete 0.033s (30.000 fps)
"""


class V4L2CaptureModeTests(unittest.TestCase):
    def test_parses_rates_by_format_and_size(self):
        modes = publish.parse_v4l2_capture_modes(V4L2_SAMPLE)
        self.assertEqual(modes["MJPG"][(1280, 720)], [120.0])
        self.assertEqual(modes["MJPG"][(640, 360)], [210.0])
        self.assertEqual(modes["YUYV"][(640, 480)], [30.0])
        self.assertEqual(modes["H264"][(1920, 1080)], [30.0])

    def test_selects_nearest_size_and_marks_unsupported_rate(self):
        modes = publish.parse_v4l2_capture_modes(V4L2_SAMPLE)["MJPG"]
        width, height, rate_supported, rates = publish.select_v4l2_capture_mode(
            modes, 640, 400, 25
        )
        self.assertEqual((width, height), (640, 360))
        self.assertFalse(rate_supported)
        self.assertEqual(rates, [210.0])

    def test_accepts_explicitly_advertised_rate(self):
        modes = publish.parse_v4l2_capture_modes(V4L2_SAMPLE)["YUYV"]
        width, height, rate_supported, rates = publish.select_v4l2_capture_mode(
            modes, 640, 480, 30
        )
        self.assertEqual((width, height), (640, 480))
        self.assertTrue(rate_supported)
        self.assertEqual(rates, [30.0])

    def test_builds_native_h264_passthrough_without_encoder(self):
        pipeline = publish.build_v4l2_h264_passthrough_pipeline(
            "/dev/video0", 2, 1280, 720, 15
        )

        self.assertIn("video/x-h264", pipeline)
        self.assertIn("width=(int)1280,height=(int)720", pipeline)
        self.assertIn("framerate=(fraction)15/1", pipeline)
        self.assertIn("h264parse", pipeline)
        self.assertIn("rtph264pay", pipeline)
        self.assertNotIn("264enc", pipeline)

    def test_h264_passthrough_can_leave_rate_unconstrained(self):
        pipeline = publish.build_v4l2_h264_passthrough_pipeline(
            "/dev/video0", 2, 1280, 720, 25, constrain_rate=False
        )

        self.assertNotIn("framerate=", pipeline)


class V4L2JpegProbeTests(unittest.TestCase):
    def setUp(self):
        publish.v4l2_jpeg_decoder_usable.cache_clear()

    def tearDown(self):
        publish.v4l2_jpeg_decoder_usable.cache_clear()

    @patch.object(publish, "gst_element_available", return_value=False)
    @patch.object(publish, "_run_v4l2_jpeg_decoder_probe")
    def test_missing_decoder_does_not_probe(self, run_probe, _available):
        self.assertFalse(publish.v4l2_jpeg_decoder_usable())
        run_probe.assert_not_called()

    @patch.object(publish, "gst_element_available", return_value=True)
    @patch.object(publish, "_run_v4l2_jpeg_decoder_probe", return_value=(False, "timeout"))
    def test_failed_probe_uses_software_fallback(self, run_probe, _available):
        with patch("builtins.print"):
            self.assertFalse(publish.v4l2_jpeg_decoder_usable())
        run_probe.assert_called_once_with()

    @patch.object(publish, "gst_element_available", return_value=True)
    @patch.object(publish, "_run_v4l2_jpeg_decoder_probe", return_value=(True, "ok"))
    def test_successful_probe_accepts_decoder(self, run_probe, _available):
        self.assertTrue(publish.v4l2_jpeg_decoder_usable())
        run_probe.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
