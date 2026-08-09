import os
import unittest
from types import SimpleNamespace
from unittest import mock

import publish


class DisplaySelectionTests(unittest.TestCase):
    def tearDown(self):
        publish.check_drm_displays.cache_clear()

    def test_drm_sysfs_connected_status_is_detected(self):
        status_path = mock.MagicMock()
        status_path.read_text.return_value = "connected\n"
        status_path.parent.name = "card0-HDMI-A-1"

        publish.check_drm_displays.cache_clear()
        with mock.patch.object(publish.Path, "glob", return_value=[status_path]):
            self.assertTrue(publish.check_drm_displays())

    def test_detects_standard_ssh_forwarded_x11_display(self):
        with mock.patch.dict(
            os.environ,
            {"DISPLAY": "localhost:10.0", "SSH_CONNECTION": "client server"},
            clear=True,
        ):
            self.assertTrue(publish.is_ssh_forwarded_display())

    @mock.patch("publish.gst_element_available", return_value=True)
    @mock.patch("publish.is_raspberry_pi_device", return_value=True)
    @mock.patch("publish.check_drm_displays", return_value=True)
    def test_pi_console_uses_kmssink_instead_of_forwarded_display(
        self, _display, _pi, _element
    ):
        with mock.patch.dict(
            os.environ,
            {"DISPLAY": "localhost:10.0", "SSH_CONNECTION": "client server"},
            clear=True,
        ):
            self.assertEqual(publish.select_display_sink(), "kmssink sync=false")

    @mock.patch("publish.is_raspberry_pi_device", return_value=True)
    @mock.patch("publish.check_drm_displays", return_value=False)
    def test_pi_without_connected_hdmi_does_not_open_forwarded_window(
        self, _display, _pi
    ):
        with mock.patch.dict(
            os.environ,
            {"DISPLAY": "localhost:10.0", "SSH_CONNECTION": "client server"},
            clear=True,
        ):
            self.assertEqual(publish.select_display_sink(), "fakesink sync=true")

    @mock.patch("publish.is_jetson_device", return_value=False)
    @mock.patch("publish.is_raspberry_pi_device", return_value=True)
    @mock.patch("publish.check_drm_displays", return_value=True)
    def test_pi_local_desktop_keeps_default_sink(self, _display, _pi, _jetson):
        with mock.patch.dict(
            os.environ,
            {"DISPLAY": ":0", "SSH_CONNECTION": "client server"},
            clear=True,
        ):
            self.assertEqual(publish.select_display_sink(), "autovideosink")

    def test_view_and_framebuffer_are_mutually_exclusive(self):
        args = SimpleNamespace(view="illinois-tv", framebuffer="/dev/fb0")

        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            publish.validate_receiver_output_args(args)

    def test_framebuffer_rejects_linux_device_path(self):
        args = SimpleNamespace(view=None, framebuffer="/dev/fb0")

        with self.assertRaisesRegex(ValueError, "expects a VDO.Ninja stream ID"):
            publish.validate_receiver_output_args(args)


if __name__ == "__main__":
    unittest.main()
