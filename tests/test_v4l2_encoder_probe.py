import unittest
from unittest.mock import patch

import publish


class V4L2EncoderProbeTests(unittest.TestCase):
    def setUp(self):
        publish.v4l2_h264_encoder_usable.cache_clear()

    def tearDown(self):
        publish.v4l2_h264_encoder_usable.cache_clear()

    @patch.object(publish, "gst_element_available", return_value=False)
    @patch.object(publish, "_run_v4l2_h264_encoder_probe")
    def test_missing_element_does_not_run_probe(self, run_probe, _available):
        with patch.object(publish, "RN_DISABLE_V4L2_ENCODER", False), patch.object(
            publish, "RN_FORCE_V4L2_ENCODER", False
        ):
            self.assertFalse(publish.v4l2_h264_encoder_usable())
        run_probe.assert_not_called()

    @patch.object(publish, "gst_element_available", return_value=True)
    @patch.object(publish, "_run_v4l2_h264_encoder_probe", return_value=(False, "driver error"))
    def test_failed_frame_probe_rejects_installed_element(self, run_probe, _available):
        with patch.object(publish, "RN_DISABLE_V4L2_ENCODER", False), patch.object(
            publish, "RN_FORCE_V4L2_ENCODER", False
        ), patch("builtins.print"):
            self.assertFalse(publish.v4l2_h264_encoder_usable())
        run_probe.assert_called_once_with()

    @patch.object(publish, "gst_element_available", return_value=True)
    @patch.object(publish, "_run_v4l2_h264_encoder_probe")
    def test_force_override_bypasses_frame_probe(self, run_probe, _available):
        with patch.object(publish, "RN_DISABLE_V4L2_ENCODER", False), patch.object(
            publish, "RN_FORCE_V4L2_ENCODER", True
        ), patch("builtins.print"):
            self.assertTrue(publish.v4l2_h264_encoder_usable())
        run_probe.assert_not_called()

    @patch.object(publish, "gst_element_available", return_value=True)
    @patch.object(publish, "_run_v4l2_h264_encoder_probe")
    def test_disable_override_wins(self, run_probe, _available):
        with patch.object(publish, "RN_DISABLE_V4L2_ENCODER", True), patch.object(
            publish, "RN_FORCE_V4L2_ENCODER", True
        ), patch("builtins.print"):
            self.assertFalse(publish.v4l2_h264_encoder_usable())
        run_probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
