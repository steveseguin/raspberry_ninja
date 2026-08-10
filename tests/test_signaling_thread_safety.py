import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import publish


class SignalingThreadSafetyTests(unittest.TestCase):
    def test_sync_callback_marshals_send_to_the_owning_event_loop(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)
        client.event_loop = MagicMock()
        client.event_loop.is_closed.return_value = False
        client.sendMessageAsync = AsyncMock()
        scheduled_future = MagicMock()

        def schedule(coroutine, loop):
            self.assertIs(loop, client.event_loop)
            coroutine.close()
            return scheduled_future

        with patch("publish.asyncio.run_coroutine_threadsafe", side_effect=schedule) as mocked:
            result = client.sendMessage({"request": "play", "streamID": "camera"})

        self.assertIs(result, scheduled_future)
        mocked.assert_called_once()
        client.sendMessageAsync.assert_called_once_with(
            {"request": "play", "streamID": "camera"}
        )

    def test_sync_callback_rejects_non_dictionary_messages(self):
        client = publish.WebRTCClient.__new__(publish.WebRTCClient)

        with self.assertRaises(TypeError):
            client.sendMessage("not-json")


if __name__ == "__main__":
    unittest.main()
