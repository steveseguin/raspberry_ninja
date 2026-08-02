"""Tests for the production V4L2 device resolution helpers."""

import unittest
from unittest.mock import patch

import v4l2_devices


class TestV4l2DeviceRetry(unittest.TestCase):
    def test_device_exists_immediately(self):
        with (
            patch("v4l2_devices.os.path.exists", return_value=True),
            patch("v4l2_devices.os.access", return_value=True),
            patch("v4l2_devices.is_v4l2_capture_device", return_value=True),
        ):
            device, error = v4l2_devices.resolve_v4l2_input_device("/dev/video0")
        self.assertEqual(device, "/dev/video0")
        self.assertFalse(error)

    def test_device_appears_after_wait(self):
        exists_results = iter([False, False, True, True])
        with (
            patch("v4l2_devices.os.path.exists", side_effect=lambda _path: next(exists_results)),
            patch("v4l2_devices.os.access", return_value=True),
            patch("v4l2_devices.is_v4l2_capture_device", return_value=True),
            patch("v4l2_devices.time.sleep"),
        ):
            device, error = v4l2_devices.resolve_v4l2_input_device("/dev/video0")
        self.assertEqual(device, "/dev/video0")
        self.assertFalse(error)

    def test_fallback_skips_non_capture_nodes(self):
        with (
            patch("v4l2_devices.os.path.exists", side_effect=lambda path: path != "/dev/video0"),
            patch("v4l2_devices.os.access", return_value=True),
            patch("v4l2_devices.glob.glob", return_value=["/dev/video1", "/dev/video2"]),
            patch(
                "v4l2_devices.is_v4l2_capture_device",
                side_effect=lambda path: path == "/dev/video2",
            ),
            patch("v4l2_devices.open", side_effect=OSError),
            patch("v4l2_devices.time.sleep"),
        ):
            device, error = v4l2_devices.resolve_v4l2_input_device("/dev/video0")
        self.assertEqual(device, "/dev/video2")
        self.assertFalse(error)

    def test_no_capture_device_found_sets_error(self):
        with (
            patch("v4l2_devices.os.path.exists", return_value=False),
            patch("v4l2_devices.glob.glob", return_value=[]),
            patch("v4l2_devices.time.sleep"),
        ):
            device, error = v4l2_devices.resolve_v4l2_input_device("/dev/video0")
        self.assertEqual(device, "/dev/video0")
        self.assertTrue(error)

    def test_output_fallback_skips_capture_only_node(self):
        with (
            patch("v4l2_devices.os.path.exists", return_value=True),
            patch("v4l2_devices.os.access", return_value=True),
            patch("v4l2_devices.glob.glob", return_value=["/dev/video0", "/dev/video10"]),
            patch(
                "v4l2_devices.is_v4l2_output_device",
                side_effect=lambda path: path == "/dev/video10",
            ),
        ):
            device = v4l2_devices.resolve_v4l2_output_device("/dev/video0")
        self.assertEqual(device, "/dev/video10")

    def test_device_capability_flags_use_device_caps(self):
        buffer = bytearray(104)
        import struct

        struct.pack_into("I", buffer, 84, v4l2_devices.V4L2_CAP_DEVICE_CAPS)
        struct.pack_into("I", buffer, 88, v4l2_devices.V4L2_CAP_VIDEO_OUTPUT)
        with (
            patch("v4l2_devices.os.open", return_value=12),
            patch("v4l2_devices.os.close"),
            patch("v4l2_devices.fcntl.ioctl", side_effect=lambda _fd, _op, target, _mutate: target.__setitem__(slice(None), buffer)),
        ):
            capabilities = v4l2_devices.query_v4l2_capabilities("/dev/video10")
        self.assertEqual(capabilities, v4l2_devices.V4L2_CAP_VIDEO_OUTPUT)


if __name__ == "__main__":
    unittest.main()
