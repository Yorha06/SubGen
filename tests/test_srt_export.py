"""Unit tests untuk format dan ekspor SRT."""

import unittest
import tempfile
import os
from subtitle_app.models.subtitle_cue import SubtitleCue
from subtitle_app.pipeline.format_subtitles import format_srt, validate_cues
from subtitle_app.pipeline.export_srt import export_srt


class TestSRTExport(unittest.TestCase):
    def test_format_srt(self):
        cues = [
            SubtitleCue(index=1, start_time=1.2, end_time=3.5, text="Halo dunia."),
            SubtitleCue(index=2, start_time=3.6, end_time=6.2, text="Ini adalah tes."),
        ]
        output = format_srt(cues)
        self.assertIn("1", output)
        self.assertIn("00:00:01,200 --> 00:00:03,500", output)
        self.assertIn("Halo dunia.", output)
        self.assertIn("2", output)
        self.assertIn("00:00:03,600 --> 00:00:06,200", output)

    def test_validate_cues_valid(self):
        cues = [SubtitleCue(index=1, start_time=0, end_time=5, text="Tes")]
        errors = validate_cues(cues)
        self.assertEqual(len(errors), 0)

    def test_validate_cues_invalid(self):
        cues = [
            SubtitleCue(index=1, start_time=5, end_time=3, text="Tes"),  # end < start
            SubtitleCue(index=2, start_time=0, end_time=5, text=""),     # empty text
        ]
        errors = validate_cues(cues)
        self.assertEqual(len(errors), 2)

    def test_export_srt_roundtrip(self):
        cues = [SubtitleCue(index=1, start_time=0, end_time=5, text="Halo")]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "test.srt")
            result = export_srt(cues, out_path)
            self.assertTrue(os.path.exists(result))
            with open(result, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Halo", content)

    def test_export_srt_rejects_empty_cues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "empty.srt")
            with self.assertRaisesRegex(ValueError, "Daftar cue kosong"):
                export_srt([], out_path)
            self.assertFalse(os.path.exists(out_path))


if __name__ == "__main__":
    unittest.main()