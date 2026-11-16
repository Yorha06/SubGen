import tempfile
import logging
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from subtitle_app.models.job import Job
from subtitle_app.models.subtitle_cue import SubtitleCue
from subtitle_app.pipeline.job_runner import JobRunner
from subtitle_app.pipeline.srt_io import parse_srt
from subtitle_app.pipeline.translate import ArgosTranslationService
from subtitle_app.services.job_store import JobStore
from subtitle_app.settings import Settings


class SrtTranslationTests(unittest.TestCase):
    def test_parser_preserves_cue_id_timestamps_and_multiline_text(self):
        cues = parse_srt(
            "\ufeff7\r\n00:00:01.250 --> 00:00:03.500\r\n"
            "First line\r\nSecond line\r\n"
        )

        self.assertEqual(
            cues,
            [SubtitleCue(7, 1.25, 3.5, "First line\nSecond line")],
        )

    def test_argos_translation_preserves_cue_timing(self):
        class FakeTranslation:
            @staticmethod
            def translate(text):
                return "ID: " + text

        cues = [SubtitleCue(4, 2.0, 3.5, "hello")]
        service = ArgosTranslationService()
        progress = []

        with patch.object(
            service, "_translation_for", return_value=FakeTranslation()
        ):
            result = service.translate_cues(
                cues,
                "en",
                progress_callback=lambda *args: progress.append(args),
            )

        self.assertEqual(result, [SubtitleCue(4, 2.0, 3.5, "ID: hello")])
        self.assertEqual(progress[-1][2:], (1, 1))

    def test_empty_translation_keeps_source_and_counts_duplicate_cues(self):
        class FakeTranslation:
            calls = []

            def translate(self, text):
                self.calls.append(text)
                return "" if text == "♪" else "ID: " + text

        cues = [
            SubtitleCue(1, 0, 1, "♪"),
            SubtitleCue(2, 1, 2, "♪"),
            SubtitleCue(3, 2, 3, "hello"),
        ]
        service = ArgosTranslationService()
        translation = FakeTranslation()

        with patch.object(service, "_translation_for", return_value=translation):
            result = service.translate_cues(cues, "en")

        self.assertEqual([cue.text for cue in result], ["♪", "♪", "ID: hello"])
        self.assertEqual(service.last_untranslated_count, 2)
        self.assertEqual(translation.calls, ["♪", "hello"])

    def test_translation_progress_is_reported_in_batches(self):
        class FakeTranslation:
            @staticmethod
            def translate(text):
                return "ID: " + text

        cues = [
            SubtitleCue(index, index, index + 1, f"line {index}")
            for index in range(201)
        ]
        service = ArgosTranslationService()
        progress = []

        with patch.object(service, "_translation_for", return_value=FakeTranslation()):
            service.translate_cues(
                cues,
                "en",
                progress_callback=lambda *args: progress.append(args),
            )

        self.assertEqual([item[2] for item in progress], [100, 200, 201])

    def test_auto_source_detection_handles_japanese_and_korean_scripts(self):
        service = ArgosTranslationService()
        japanese = [SubtitleCue(1, 0, 1, "こんにちは")]
        korean = [SubtitleCue(1, 0, 1, "안녕하세요")]

        self.assertEqual(service._resolve_source_language(japanese, "auto"), "ja")
        self.assertEqual(service._resolve_source_language(korean, "auto"), "ko")

    def test_argos_finds_pivot_routes_for_selected_target_language(self):
        packages = [
            SimpleNamespace(from_code="ja", to_code="en"),
            SimpleNamespace(from_code="en", to_code="id"),
            SimpleNamespace(from_code="en", to_code="ko"),
        ]

        self.assertEqual(
            ArgosTranslationService._find_route("ja", "id", packages),
            [("ja", "en"), ("en", "id")],
        )
        self.assertEqual(
            ArgosTranslationService._find_route("ja", "ko", packages),
            [("ja", "en"), ("en", "ko")],
        )

    def test_srt_job_translates_without_running_transcription(self):
        class UnusedService:
            def __getattr__(self, name):
                raise AssertionError(f"Unexpected transcription call: {name}")

        class FakeTranslator:
            def translate_cues(
                self,
                cues,
                source_lang,
                target_lang,
                cancel_event,
                progress_callback,
            ):
                translated = [
                    SubtitleCue(
                        cue.index,
                        cue.start_time,
                        cue.end_time,
                        target_lang.upper() + ": " + cue.text,
                    )
                    for cue in cues
                ]
                progress_callback("Menerjemahkan cue 1 / 1", 95, 1, 1)
                return translated

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.srt"
            output_path = root / "output.id.srt"
            input_path.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
                encoding="utf-8",
            )
            store = JobStore(root / "jobs")
            runner = JobRunner(
                UnusedService(),
                UnusedService(),
                store,
                Settings(),
                FakeTranslator(),
            )
            job = Job(
                id="translate1",
                input_path=str(input_path),
                output_path=str(output_path),
                language="en",
                operation="translate_srt",
                target_language="en",
            )

            try:
                runner._run_job(job)

                self.assertEqual(job.status, "completed")
                self.assertTrue(output_path.exists())
                self.assertIn("EN: Hello", output_path.read_text(encoding="utf-8"))
                self.assertEqual(job.completed_segments, 1)
            finally:
                logger = logging.getLogger("subtitle_app.job.translate1")
                for handler in list(logger.handlers):
                    handler.close()
                    logger.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
