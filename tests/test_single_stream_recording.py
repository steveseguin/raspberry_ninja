import unittest
from types import SimpleNamespace

import publish


class SingleStreamRecordingTests(unittest.TestCase):
    def test_requested_stream_id_is_preserved_for_subprocess_recording(self):
        args = SimpleNamespace(
            record="camera-stream",
            streamin=None,
            single_stream_recording=False,
            room_recording=True,
            auto_turn=False,
        )

        publish.configure_single_stream_recording(args)

        self.assertEqual(args.streamin, "camera-stream")
        self.assertTrue(args.single_stream_recording)
        self.assertFalse(args.room_recording)
        self.assertTrue(args.auto_turn)


if __name__ == "__main__":
    unittest.main()
