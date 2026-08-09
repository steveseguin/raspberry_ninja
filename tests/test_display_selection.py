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

    def test_connected_drm_preferred_mode_is_used_for_direct_display(self):
        status_path = mock.MagicMock()
        status_path.read_text.return_value = "connected\n"
        modes_path = mock.MagicMock()
        modes_path.exists.return_value = True
        modes_path.read_text.return_value = "1920x1200\n1920x1080\n"
        status_path.parent.__truediv__.return_value = modes_path

        with mock.patch.object(publish.Path, "glob", return_value=[status_path]):
            self.assertEqual(publish.get_drm_display_resolution(), (1920, 1200))

    def test_disconnected_drm_mode_is_ignored(self):
        status_path = mock.MagicMock()
        status_path.read_text.return_value = "disconnected\n"

        with mock.patch.object(publish.Path, "glob", return_value=[status_path]):
            self.assertIsNone(publish.get_drm_display_resolution())

    def test_kms_conversion_preserves_aspect_ratio_by_default(self):
        chain = publish.build_kms_conversion_chain((1920, 1200), stretch=False)

        self.assertIn("videoscale add-borders=true", chain)
        self.assertIn("width=(int)1920,height=(int)1200", chain)

    def test_kms_conversion_can_stretch_to_display_mode(self):
        chain = publish.build_kms_conversion_chain((1920, 1200), stretch=True)

        self.assertIn("videoscale add-borders=false", chain)

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
            self.assertEqual(
                publish.select_display_sink(),
                "kmssink sync=false force-modesetting=true",
            )

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

    def test_viewer_retry_delays_must_be_finite(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                args = SimpleNamespace(
                    view="illinois-tv",
                    framebuffer=None,
                    viewer_retry_initial=value,
                    viewer_retry_short=45,
                    viewer_retry_long=180,
                )
                with self.assertRaisesRegex(ValueError, "finite, non-negative"):
                    publish.validate_receiver_output_args(args)

    def test_viewer_retry_delays_cannot_be_negative(self):
        args = SimpleNamespace(
            view="illinois-tv",
            framebuffer=None,
            viewer_retry_initial=15,
            viewer_retry_short=-1,
            viewer_retry_long=180,
        )

        with self.assertRaisesRegex(ValueError, "--viewer-retry-short"):
            publish.validate_receiver_output_args(args)


if __name__ == "__main__":
    unittest.main()
