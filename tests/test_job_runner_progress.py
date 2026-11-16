import unittest

from subtitle_app.pipeline.job_runner import _estimate_remaining_seconds


class JobRunnerProgressTests(unittest.TestCase):
    def test_waits_for_enough_elapsed_time_and_progress(self):
        self.assertIsNone(_estimate_remaining_seconds(29, 0.5))
        self.assertIsNone(_estimate_remaining_seconds(30, 0.009))

    def test_estimates_remaining_time_early_in_long_transcriptions(self):
        self.assertEqual(_estimate_remaining_seconds(30, 0.01), 2970)


if __name__ == "__main__":
    unittest.main()
