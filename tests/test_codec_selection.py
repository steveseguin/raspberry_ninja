import unittest
from types import SimpleNamespace

import publish


def codec_args(**overrides):
    values = {
        "nvidia": False,
        "rpi": False,
        "x264": False,
        "openh264": False,
        "omx": False,
        "apple": None,
        "h264": False,
        "vp8": False,
        "vp9": False,
        "av1": False,
        "aom": False,
        "rav1e": False,
        "qsv": False,
        "h265": False,
        "hevc": False,
        "x265": False,
        "rtmp": None,
        "bitrate": 700,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CodecSelectionTests(unittest.TestCase):
    def test_vp9_overrides_raspberry_pi_h264_hint(self):
        args = codec_args(rpi=True, vp9=True)

        publish.normalize_video_codec_preferences(args)

        self.assertFalse(args.h264)

    def test_vp8_still_overrides_platform_h264_hint(self):
        args = codec_args(nvidia=True, vp8=True)

        publish.normalize_video_codec_preferences(args)

        self.assertFalse(args.h264)

    def test_rtmp_preserves_its_h264_requirement(self):
        args = codec_args(rpi=True, vp9=True, rtmp="rtmp://example.invalid/live")

        publish.normalize_video_codec_preferences(args)

        self.assertTrue(args.h264)

    def test_vp9_fragment_uses_vp9_payloader_and_bits_per_second(self):
        args = codec_args(rpi=True, vp9=True, bitrate=700)

        fragment = publish.build_vp9_encoder_fragment(args)

        self.assertIn("vp9enc", fragment)
        self.assertIn("target-bitrate=700000", fragment)
        self.assertIn("rtpvp9pay", fragment)
        self.assertIn("encoding-name=VP9", fragment)
        self.assertNotIn("vp8", fragment.lower())

    def test_nvidia_vp9_fragment_moves_frames_out_of_nvmm(self):
        args = codec_args(nvidia=True, vp9=True)

        fragment = publish.build_vp9_encoder_fragment(args)

        self.assertIn("nvvidconv ! video/x-raw,format=I420", fragment)

    def test_pi5_defaults_to_x264_without_an_explicit_alternative(self):
        self.assertTrue(publish.should_default_pi5_to_x264(codec_args(rpi=True)))

    def test_pi5_preserves_explicit_openh264(self):
        self.assertFalse(
            publish.should_default_pi5_to_x264(codec_args(rpi=True, openh264=True))
        )

    def test_pi5_preserves_explicit_non_h264_codec(self):
        self.assertFalse(publish.should_default_pi5_to_x264(codec_args(rpi=True, vp9=True)))

    def test_openh264_fragment_enables_bitrate_rate_control(self):
        fragment = publish.build_openh264_encoder_fragment(codec_args(bitrate=2500))

        self.assertIn("bitrate=2500000", fragment)
        self.assertIn("max-bitrate=2500000", fragment)
        self.assertIn("rate-control=bitrate", fragment)
        self.assertIn("enable-frame-skip=true", fragment)


if __name__ == "__main__":
    unittest.main()
