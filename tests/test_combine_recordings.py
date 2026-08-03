import tempfile
import unittest
from pathlib import Path

from tools import combine_recordings


class CombineRecordingDiscoveryTests(unittest.TestCase):
    def touch(self, directory, name):
        path = Path(directory, name)
        path.touch()
        return path

    def test_discovers_current_single_stream_ts_and_webm_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            video = self.touch(directory, "camera_main_1700000000.ts")
            audio = self.touch(directory, "camera_main_1700000001_audio.webm")

            pairs = combine_recordings.discover_recording_pairs(directory)

            self.assertEqual(pairs, [(video, audio)])

    def test_discovers_room_webm_pair_with_uuid_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            video = self.touch(
                directory, "studio_room_camera_one_1700000000_ab12cd34.webm"
            )
            audio = self.touch(
                directory,
                "studio_room_camera_one_1700000002_ab12cd34_audio.webm",
            )

            pairs = combine_recordings.discover_recording_pairs(directory)

            self.assertEqual(pairs, [(video, audio)])

    def test_discovers_current_files_created_three_seconds_apart(self):
        with tempfile.TemporaryDirectory() as directory:
            video = self.touch(
                directory,
                "rn-record-8021_rn-record-8021_1785729011.webm",
            )
            audio = self.touch(
                directory,
                "rn-record-8021_rn-record-8021_1785729014_audio.webm",
            )

            pairs = combine_recordings.discover_recording_pairs(directory)

            self.assertEqual(pairs, [(video, audio)])

    def test_supports_legacy_wav_audio_without_pairing_unrelated_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            video = self.touch(directory, "room_camera_1700000000.webm")
            audio = self.touch(directory, "room_camera_1700000000_audio.wav")
            self.touch(directory, "room_other_1700000000_audio.wav")

            pairs = combine_recordings.discover_recording_pairs(directory)

            self.assertEqual(pairs, [(video, audio)])

    def test_ignores_files_outside_timestamp_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            self.touch(directory, "camera_1700000000.ts")
            self.touch(directory, "camera_1700000006_audio.webm")

            self.assertEqual(
                combine_recordings.discover_recording_pairs(directory), []
            )


if __name__ == "__main__":
    unittest.main()
