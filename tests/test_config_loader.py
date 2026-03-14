import argparse
import unittest

from config_loader import apply_config_overrides


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--streamid", default="cli-default")
    parser.add_argument("--bitrate", type=int, default=2500)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--hdmi", action="store_true")
    parser.add_argument("--camlink", action="store_true")
    parser.add_argument("--z1", action="store_true")
    parser.add_argument("--z1passthru", action="store_true")
    parser.add_argument("--apple", default=None)
    parser.add_argument("--v4l2", default=None)
    parser.add_argument("--libcamera", action="store_true")
    parser.add_argument("--rpicam", action="store_true")
    parser.add_argument("--nvidiacsi", action="store_true")
    parser.add_argument("--pipeline", default=None)
    parser.add_argument("--video-pipeline", dest="video_pipeline", default=None)
    parser.add_argument("--filesrc", default=None)
    parser.add_argument("--filesrc2", default=None)
    parser.add_argument("--pipein", default=None)
    parser.add_argument("--novideo", action="store_true")
    parser.add_argument("--noaudio", action="store_true")
    return parser


class TestConfigLoader(unittest.TestCase):
    def test_installer_config_maps_stream_id_and_test_source(self):
        parser = build_parser()
        args = parser.parse_args([])

        apply_config_overrides(
            args,
            parser,
            {
                "stream_id": "config-stream",
                "bitrate": 1800,
                "video_source": "test",
                "audio_enabled": True,
            },
        )

        self.assertEqual(args.streamid, "config-stream")
        self.assertEqual(args.bitrate, 1800)
        self.assertTrue(args.test)
        self.assertIsNone(args.v4l2)
        self.assertFalse(args.noaudio)

    def test_custom_video_source_uses_custom_pipeline(self):
        parser = build_parser()
        args = parser.parse_args([])

        apply_config_overrides(
            args,
            parser,
            {
                "video_source": "custom",
                "custom_video_pipeline": "videotestsrc pattern=ball",
            },
        )

        self.assertEqual(args.video_pipeline, "videotestsrc pattern=ball")

    def test_config_video_source_does_not_override_explicit_cli_source(self):
        parser = build_parser()
        args = parser.parse_args(["--hdmi"])

        apply_config_overrides(
            args,
            parser,
            {
                "video_source": "test",
            },
        )

        self.assertTrue(args.hdmi)
        self.assertFalse(args.test)

    def test_v4l2_source_uses_video_device_from_config(self):
        parser = build_parser()
        args = parser.parse_args([])

        apply_config_overrides(
            args,
            parser,
            {
                "video_source": "v4l2",
                "video_device": "/dev/video2",
            },
        )

        self.assertEqual(args.v4l2, "/dev/video2")

    def test_v4l2_source_defaults_to_video0_without_video_device(self):
        parser = build_parser()
        args = parser.parse_args([])

        apply_config_overrides(
            args,
            parser,
            {
                "video_source": "v4l2",
            },
        )

        self.assertEqual(args.v4l2, "/dev/video0")

    def test_audio_enabled_false_sets_noaudio_when_not_explicitly_set(self):
        parser = build_parser()
        args = parser.parse_args([])

        apply_config_overrides(
            args,
            parser,
            {
                "audio_enabled": False,
            },
        )

        self.assertTrue(args.noaudio)


if __name__ == "__main__":
    unittest.main()
