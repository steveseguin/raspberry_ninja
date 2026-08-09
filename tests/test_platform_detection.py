import unittest
from types import SimpleNamespace
from unittest.mock import mock_open, patch

import publish


class RaspberryPiModelDetectionTests(unittest.TestCase):
    def detect(self, model_line):
        cpuinfo = f"processor\t: 0\nModel\t\t: {model_line}\n"
        with patch("builtins.open", mock_open(read_data=cpuinfo)):
            return publish.get_raspberry_pi_model()

    def test_zero_2_w_is_not_reported_as_pi_1(self):
        self.assertEqual(self.detect("Raspberry Pi Zero 2 W Rev 1.0"), 2)

    def test_pi_5_is_detected(self):
        self.assertEqual(self.detect("Raspberry Pi 5 Model B Rev 1.0"), 5)

    def test_non_pi_cpuinfo_returns_zero(self):
        with patch("builtins.open", mock_open(read_data="processor: Intel\n")):
            self.assertEqual(publish.get_raspberry_pi_model(), 0)

    def test_rpi_test_source_does_not_scan_physical_video_devices(self):
        args = SimpleNamespace(
            rpi=True,
            test=True,
            v4l2=None,
            hdmi=False,
            rpicam=False,
            z1=False,
        )

        self.assertFalse(publish.should_scan_rpi_video_devices(args))

    def test_rpi_auto_camera_source_still_scans_video_devices(self):
        args = SimpleNamespace(
            rpi=True,
            test=False,
            v4l2=None,
            hdmi=False,
            rpicam=False,
            z1=False,
        )

        self.assertTrue(publish.should_scan_rpi_video_devices(args))


if __name__ == "__main__":
    unittest.main()
