import subprocess
import unittest

from tools import media_self_test


class MediaSelfTestTests(unittest.TestCase):
    def test_every_probe_has_a_complete_rtp_round_trip(self):
        for name, definition in media_self_test.PROBES.items():
            pipeline = " ".join(definition["pipeline"])
            self.assertIn("rtp", pipeline, name)
            self.assertIn("pay", pipeline, name)
            self.assertIn("depay", pipeline, name)
            self.assertIn("fakesink", pipeline, name)

    def test_missing_encoder_skips_probe(self):
        completed = subprocess.CompletedProcess([], 1)
        result = media_self_test.run_probe(
            "openh264",
            runner=lambda *_args, **_kwargs: completed,
        )
        self.assertEqual(result["status"], "skipped")
        self.assertIn("openh264enc", result["missing"])

    def test_available_codec_runs_pipeline(self):
        commands = []

        def runner(command, **_kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        result = media_self_test.run_probe("vp8", runner=runner)

        self.assertEqual(result["status"], "passed")
        self.assertTrue(any(command[0] == "gst-launch-1.0" for command in commands))


if __name__ == "__main__":
    unittest.main()
