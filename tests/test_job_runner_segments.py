import tempfile
import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from subtitle_app.models.job import Job
from subtitle_app.models.segment import Segment
from subtitle_app.pipeline.job_runner import JobRunner
from subtitle_app.services.job_store import JobStore
from subtitle_app.settings import Settings


class JobRunnerSegmentTests(unittest.TestCase):
    def test_whisper_receives_audio_files_cut_to_each_segment(self):
        class FakeFFmpeg:
            def __init__(self):
                self.segment_ranges = []

            def probe(self, input_path, cancel_event=None):
                return {
                    "format": {"duration": "20"},
                    "streams": [{"codec_type": "audio"}],
                }

            def extract_audio(self, input_path, output_wav, **kwargs):
                Path(output_wav).parent.mkdir(parents=True, exist_ok=True)
                Path(output_wav).write_bytes(b"audio")

            def extract_audio_segment(
                self, input_path, output_wav, start_time, duration, cancel_event=None
            ):
                self.segment_ranges.append((start_time, duration))
                Path(output_wav).write_bytes(b"segment")

        class FakeWhisper:
            def __init__(self):
                self.audio_paths = []
                self.models = []
                self.backends = []

            def transcribe_segment(
                self, audio_path, model_name, backend, progress_callback, **kwargs
            ):
                self.audio_paths.append(audio_path)
                self.models.append(model_name)
                self.backends.append(backend)
                if backend == "vulkan":
                    raise RuntimeError("Vulkan failed")
                progress_callback(100)
                return {
                    "text": "spoken words",
                    "segments": [{"start": 0.0, "end": 1.0, "text": "spoken words"}],
                }

        segments = [
            Segment(index=0, start_time=0, end_time=10),
            Segment(index=1, start_time=10, end_time=20),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = Settings()
            settings.set("temp_dir", str(root / "temp"))
            settings.set("default_model", "configured-model.bin")
            ffmpeg = FakeFFmpeg()
            whisper = FakeWhisper()
            runner = JobRunner(
                ffmpeg,
                whisper,
                JobStore(root / "jobs"),
                settings,
            )
            job = Job(
                id="segments1",
                input_path=str(root / "input.mp4"),
                output_path=str(root / "output.srt"),
                model="selected-model.bin",
                backend="vulkan",
                cpu_fallback=True,
            )

            try:
                with patch(
                    "subtitle_app.pipeline.segment_audio.segment_audio_file",
                    return_value=segments,
                ):
                    runner._run_job(job)

                self.assertEqual(job.status, "completed")
                self.assertEqual(ffmpeg.segment_ranges, [(0, 10), (10, 10)])
                self.assertEqual(len(set(whisper.audio_paths)), 2)
                self.assertTrue(
                    all("audio_segments" in audio_path for audio_path in whisper.audio_paths)
                )
                self.assertEqual(set(whisper.models), {"selected-model.bin"})
                self.assertEqual(whisper.backends, ["vulkan", "cpu", "cpu"])
                self.assertFalse((root / "temp" / job.id).exists())
                self.assertIsNotNone(runner.store.load_segment(job.id, 0))
            finally:
                logger = logging.getLogger("subtitle_app.job.segments1")
                for handler in list(logger.handlers):
                    handler.close()
                    logger.removeHandler(handler)

    def test_startup_cleans_temp_for_terminal_jobs_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = Settings()
            temp_root = root / "temp"
            settings.set("temp_dir", str(temp_root))
            store = JobStore(root / "jobs")
            store.save_job(
                Job(
                    id="completed1",
                    input_path="input.mp4",
                    output_path="output.srt",
                    status="completed",
                )
            )
            store.save_job(
                Job(
                    id="active001",
                    input_path="input.mp4",
                    output_path="output2.srt",
                    status="transcribing",
                )
            )
            completed_temp = temp_root / "completed1"
            active_temp = temp_root / "active001"
            completed_temp.mkdir(parents=True)
            active_temp.mkdir(parents=True)

            JobRunner(None, None, store, settings)

            self.assertFalse(completed_temp.exists())
            self.assertTrue(active_temp.exists())


if __name__ == "__main__":
    unittest.main()
