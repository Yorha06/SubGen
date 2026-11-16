"""Unit tests untuk penggabungan segmen."""

import unittest
from subtitle_app.models.segment import Segment
from subtitle_app.models.subtitle_cue import SubtitleCue
from subtitle_app.pipeline.merge_segments import merge_segments
from subtitle_app.settings import Settings


class TestMergeSegments(unittest.TestCase):
    def test_merge_segments_basic(self):
        settings = Settings()
        segments = [
            Segment(
                index=0,
                start_time=0.0,
                end_time=10.0,
                transcript_segments=[
                    {"start": 0.0, "end": 3.0, "text": "Halo dunia"},
                    {"start": 3.5, "end": 6.0, "text": "Ini tes"},
                ],
                status="completed",
            ),
            Segment(
                index=1,
                start_time=10.0,
                end_time=20.0,
                transcript_segments=[
                    {"start": 0.0, "end": 4.0, "text": "Selamat sore"},
                ],
                status="completed",
            ),
        ]

        class FakeJob:
            pass

        job = FakeJob()
        cues = merge_segments(job, segments, settings)

        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[0].start_time, 0.0)
        self.assertEqual(cues[0].end_time, 3.0)
        self.assertEqual(cues[0].text, "Halo dunia")
        self.assertEqual(cues[1].start_time, 3.5)
        self.assertEqual(cues[2].start_time, 10.0)  # offset dari segmen kedua
        self.assertEqual(cues[2].text, "Selamat sore")

    def test_merge_segments_with_offset(self):
        settings = Settings()
        segments = [
            Segment(
                index=0,
                start_time=100.0,
                end_time=110.0,
                transcript_segments=[
                    {"start": 1.0, "end": 3.0, "text": "Test offset"},
                ],
                status="completed",
            ),
        ]

        class FakeJob:
            pass

        job = FakeJob()
        cues = merge_segments(job, segments, settings)

        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].start_time, 101.0)  # 1 + 100 offset
        self.assertEqual(cues[0].end_time, 103.0)

    def test_splits_paragraph_transcripts_into_short_timed_cues(self):
        settings = Settings()
        settings.set("subtitle_max_chars", 22)
        text = (
            "This is a very long paragraph. It should become several "
            "short subtitle cues."
        )
        segment = Segment(
            index=0,
            start_time=0,
            end_time=10,
            transcript_segments=[{"start": 0, "end": 10, "text": text}],
            status="completed",
        )

        cues = merge_segments(object(), [segment], settings)

        self.assertGreater(len(cues), 1)
        self.assertTrue(all(len(cue.text) <= 22 for cue in cues))
        self.assertEqual(cues[0].start_time, 0)
        self.assertEqual(cues[-1].end_time, 10)
        self.assertTrue(
            all(left.end_time == right.start_time for left, right in zip(cues, cues[1:]))
        )


if __name__ == "__main__":
    unittest.main()