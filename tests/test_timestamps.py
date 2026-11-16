"""Unit tests untuk utilitas timestamp."""

import unittest
from subtitle_app.utils.timestamps import (
    seconds_to_srt_timestamp,
    srt_timestamp_to_seconds,
    format_duration,
)


class TestTimestamps(unittest.TestCase):
    def test_seconds_to_srt_timestamp(self):
        self.assertEqual(seconds_to_srt_timestamp(0), "00:00:00,000")
        self.assertEqual(seconds_to_srt_timestamp(1.5), "00:00:01,500")
        self.assertEqual(seconds_to_srt_timestamp(65.123), "00:01:05,123")
        self.assertEqual(seconds_to_srt_timestamp(3661.001), "01:01:01,001")

    def test_srt_timestamp_to_seconds(self):
        self.assertAlmostEqual(srt_timestamp_to_seconds("00:00:01,500"), 1.5)
        self.assertAlmostEqual(srt_timestamp_to_seconds("01:01:01,001"), 3661.001)

    def test_round_trip(self):
        for val in [0, 1.5, 65.123, 3661.001, 7200.999]:
            ts = seconds_to_srt_timestamp(val)
            back = srt_timestamp_to_seconds(ts)
            self.assertAlmostEqual(val, back, places=2)

    def test_format_duration(self):
        self.assertEqual(format_duration(30), "30.0 detik")
        self.assertEqual(format_duration(90), "1 menit 30 detik")
        self.assertEqual(format_duration(3700), "1 jam 1 menit")


if __name__ == "__main__":
    unittest.main()