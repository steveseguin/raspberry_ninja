import unittest
from unittest.mock import mock_open, patch

import publish


class RaspberryPiModelDetectionTests(unittest.TestCase):
    def detect(self, model_line):
        cpuinfo = f"processor\t: 0\nModel\t\t: {model_line}\n"
        with patch("builtins.open", mock_open(read_data=cpuinfo)):
            return publish.get_raspberry_pi_model()

    def test_zero_2_w_is_not_reported_as_pi_1(self):
        self.assertEqual(self.detect("Raspberry Pi Zero 2 W Rev 1.0"), 2)

    def test_pi_5_is_detected(self):
        self.assertEqual(self.detect("Raspberry Pi 5 Model B Rev 1.0"), 5)

    def test_non_pi_cpuinfo_returns_zero(self):
        with patch("builtins.open", mock_open(read_data="processor: Intel\n")):
            self.assertEqual(publish.get_raspberry_pi_model(), 0)


if __name__ == "__main__":
    unittest.main()
