import subprocess
import json
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import setup


class EasySetupTests(unittest.TestCase):
    def test_choice_reprompts_without_exposing_technical_options(self):
        answers = iter(["nope", "2"])
        with patch("builtins.print"):
            choice = setup.ask_choice("Role", ("Receiver", "Sender"), input_fn=lambda _p: next(answers))
        self.assertEqual(choice, 1)

    def test_stream_id_uses_simple_default(self):
        self.assertEqual(setup.ask_stream_id(input_fn=lambda _p: ""), "home-video")

    def test_view_link_contains_the_selected_password(self):
        self.assertEqual(
            setup.build_view_url("family-camera", "two words&more"),
            "https://vdo.ninja/?view=family-camera&password=two%20words%26more",
        )

    @patch("tools.setup.display_connected", return_value=True)
    @patch("tools.setup.discover_alsa_inputs", return_value=[])
    @patch("tools.setup.discover_cameras", return_value=[])
    def test_hidden_inventory_is_machine_readable(self, _cameras, _audio, _display):
        output = io.StringIO()
        with redirect_stdout(output):
            result = setup.main(["--inventory"])
        self.assertEqual(result, 0)
        self.assertTrue(json.loads(output.getvalue())["display"])

    def test_camera_format_prefers_native_h264(self):
        self.assertEqual(setup.choose_camera_format({"YUY2", "MJPG", "H264"}), "H264")

    def test_csi_discovery_requires_camera_and_working_gstreamer_source(self):
        responses = iter(
            [
                subprocess.CompletedProcess([], 0, stdout="Available cameras\n0 : imx219 [sensor]", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            ]
        )
        camera = setup.discover_csi_camera(runner=lambda *_a, **_k: next(responses))
        self.assertEqual(camera, ("csi:rpicam", "imx219"))

    def test_camera_probe_recognizes_common_driver_names(self):
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout="'H264' H.264\n'MJPG' Motion-JPEG\n'YUYV' YUYV 4:2:2",
            stderr="",
        )
        formats = setup.probe_camera_formats("/dev/video0", runner=lambda *_a, **_k: completed)
        self.assertEqual(formats, {"H264", "MJPG", "YUY2"})

    def test_alsa_discovery_builds_stable_card_name(self):
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout="card 2: C920 [HD Pro Webcam C920], device 0: USB Audio [USB Audio]",
            stderr="",
        )
        devices = setup.discover_alsa_inputs(runner=lambda *_a, **_k: completed)
        self.assertEqual(devices, [("hw:C920,0", "HD Pro Webcam C920")])

    def test_native_h264_sender_uses_safe_hd_defaults(self):
        arguments = setup.build_sender_arguments(
            Path("/opt/raspberry_ninja"),
            "family-camera",
            "secret",
            "/dev/v4l/by-id/camera",
            "H264",
            "hw:C920,0",
        )
        self.assertIn("/dev/v4l/by-id/camera", arguments)
        self.assertIn("H264", arguments)
        self.assertIn("1280", arguments)
        self.assertIn("hw:C920,0", arguments)

    def test_raw_camera_uses_gstreamer_yuy2_mode(self):
        arguments = setup.build_sender_arguments(
            Path("/opt/raspberry_ninja"),
            "raw-camera",
            "secret",
            "/dev/video0",
            "YUY2",
            None,
        )
        self.assertIn("--raw", arguments)
        self.assertIn("YUY2", arguments)

    def test_csi_camera_selects_detected_backend_without_device_path(self):
        arguments = setup.build_sender_arguments(
            Path("/opt/raspberry_ninja"),
            "csi-camera",
            "secret",
            "csi:libcamera",
            None,
            None,
        )
        self.assertIn("--libcamera", arguments)
        self.assertNotIn("--camera", arguments)

    @patch("tools.setup.display_connected", return_value=True)
    @patch("tools.setup.install_unattended.main", return_value=0)
    def test_receiver_flow_installs_with_three_simple_answers(self, install, _display):
        answers = iter(["1", "living-room"])
        with patch("builtins.print"):
            result = setup.main(
                input_fn=lambda _prompt: next(answers),
                password_fn=lambda _prompt: "secret",
            )
        self.assertEqual(result, 0)
        arguments = install.call_args.args[0]
        self.assertIn("receiver", arguments)
        self.assertIn("living-room", arguments)
        self.assertIn("secret", arguments)

    @patch("tools.setup.display_connected", return_value=True)
    @patch("tools.setup.install_unattended.main", side_effect=RuntimeError("service failed"))
    def test_setup_failure_is_reported_without_a_traceback(self, _install, _display):
        answers = iter(["1", "living-room"])
        with patch("builtins.print") as output:
            result = setup.main(
                input_fn=lambda _prompt: next(answers),
                password_fn=lambda _prompt: "secret",
            )
        self.assertEqual(result, 1)
        self.assertTrue(any("could not finish" in str(call).lower() for call in output.call_args_list))


if __name__ == "__main__":
    unittest.main()
