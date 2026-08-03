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
"""


class V4L2CaptureModeTests(unittest.TestCase):
    def test_parses_rates_by_format_and_size(self):
        modes = publish.parse_v4l2_capture_modes(V4L2_SAMPLE)
        self.assertEqual(modes["MJPG"][(1280, 720)], [120.0])
        self.assertEqual(modes["MJPG"][(640, 360)], [210.0])
        self.assertEqual(modes["YUYV"][(640, 480)], [30.0])

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
