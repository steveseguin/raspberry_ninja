import argparse
import tempfile
import unittest
from pathlib import Path

from tools import install_unattended


class InstallUnattendedTests(unittest.TestCase):
    def parse(self, *argv):
        parser = install_unattended.create_parser()
        args = parser.parse_args(["--password", "secret", "--dry-run", *argv])
        install_unattended.validate_args(parser, args)
        return args

    def test_receiver_config_keeps_credentials_out_of_unit(self):
        args = self.parse("receiver", "--stream-id", "illinois-tv")
        config = install_unattended.build_config(args)
        unit = install_unattended.render_service(
            service_name=args.service_name,
            description="Receiver",
            user="steve",
            repo_dir=Path("/home/steve/raspberry ninja"),
            config_path=Path("/etc/raspberry-ninja/viewer.json"),
            python_path=Path("/usr/bin/python3"),
        )

        self.assertEqual(config["view"], "illinois-tv")
        self.assertEqual(config["password"], "secret")
        self.assertFalse(config["stretch_display"])
        self.assertNotIn("secret", unit)
        self.assertIn("WorkingDirectory=/home/steve/raspberry\\x20ninja", unit)
        self.assertIn("Restart=always", unit)

    def test_native_h264_camera_sender_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            camera = Path(temporary) / "camera"
            camera.touch()
            args = self.parse(
                "sender",
                "--stream-id",
                "illinois-return",
                "--camera",
                str(camera),
                "--format",
                "H264",
                "--width",
                "1280",
                "--height",
                "720",
                "--audio-device",
                "hw:C920,0",
            )

        config = install_unattended.build_config(args)
        self.assertEqual(config["v4l2"], str(camera))
        self.assertEqual(config["format"], "H264")
        self.assertTrue(config["h264"])
        self.assertFalse(config["noaudio"])
        self.assertEqual(config["alsa"], "hw:C920,0")

    def test_test_source_sender_does_not_require_camera(self):
        args = self.parse(
            "sender", "--stream-id", "florida-test", "--test-source", "--codec", "vp8"
        )
        config = install_unattended.build_config(args)

        self.assertTrue(config["test"])
        self.assertTrue(config["vp8"])
        self.assertNotIn("v4l2", config)

    def test_explicit_stun_disable_is_written_to_config(self):
        parser = install_unattended.create_parser()
        args = parser.parse_args(
            [
                "--password",
                "secret",
                "--stun-server",
                "false",
                "--dry-run",
                "receiver",
                "--stream-id",
                "local-test",
            ]
        )
        config = install_unattended.build_config(args)

        self.assertEqual(config["stun_server"], "false")

    def test_systemd_quote_escapes_percent_backslash_and_quote(self):
        self.assertEqual(
            install_unattended.systemd_quote('a%\\b"c'),
            '"a%%\\\\b\\"c"',
        )

    def test_systemd_setting_path_escapes_spaces_and_percent(self):
        self.assertEqual(
            install_unattended.systemd_setting_path("/home/100%/raspberry ninja"),
            "/home/100%%/raspberry\\x20ninja",
        )


if __name__ == "__main__":
    unittest.main()
