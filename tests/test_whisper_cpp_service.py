import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from subtitle_app.services.whisper_cpp_service import WhisperCppService


class WhisperCppServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.executable = self.root / "whisper-cli.exe"
        self.model = self.root / "model.bin"
        self.audio = self.root / "audio.wav"
        self.executable.touch()
        self.model.touch()
        self.audio.touch()
        self.service = WhisperCppService(
            str(self.executable),
            str(self.root),
            backend="vulkan",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalizes_whisper_cpp_transcription_json(self):
        def run_command(command, **kwargs):
            output_path = Path(command[command.index("--output-file") + 1])
            output_path.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "transcription": [
                            {
                                "offsets": {"from": 1250, "to": 2400},
                                "text": " Hello there. ",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch(
            "subtitle_app.services.whisper_cpp_service.subprocess.run",
            side_effect=run_command,
        ) as run:
            result = self.service.transcribe_segment(
                str(self.audio),
                "model.bin",
                vad=False,
                output_dir=str(self.root / "transcripts"),
            )

        command = run.call_args.args[0]
        self.assertIn("--beam-size", command)
        self.assertEqual(command[command.index("--max-len") + 1], "42")
        self.assertIn("--split-on-word", command)
        self.assertNotIn("--output-timestamps", command)
        self.assertNotIn("-tg", command)
        self.assertEqual(result["text"], "Hello there.")
        self.assertEqual(
            result["segments"],
            [{"start": 1.25, "end": 2.4, "text": "Hello there."}],
        )

    def test_success_without_json_raises_instead_of_returning_empty_text(self):
        with patch(
            "subtitle_app.services.whisper_cpp_service.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ):
            with self.assertRaisesRegex(RuntimeError, "tidak menghasilkan file JSON"):
                self.service.transcribe_segment(
                    str(self.audio),
                    "model.bin",
                    vad=False,
                    output_dir=str(self.root / "transcripts"),
                )

    def test_streams_cli_progress_updates(self):
        command = [
            sys.executable,
            "-c",
            (
                "import sys, time; "
                "sys.stderr.write('progress 25%\\r'); sys.stderr.flush(); "
                "time.sleep(0.1); "
                "sys.stderr.write('progress 100%\\n'); sys.stderr.flush(); "
                "sys.stdout.write('done')"
            ),
        ]
        progress = []

        result = self.service._run_with_progress(command, progress.append)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "done")
        self.assertEqual(progress, [25, 100])

    def test_cancels_running_whisper_process(self):
        cancel_event = threading.Event()
        timer = threading.Timer(0.2, cancel_event.set)
        timer.start()
        started = time.monotonic()
        try:
            with self.assertRaises(InterruptedError):
                self.service._run_with_progress(
                    [
                        sys.executable,
                        "-c",
                        "import time; time.sleep(10)",
                    ],
                    lambda percent: None,
                    cancel_event=cancel_event,
                )
        finally:
            timer.cancel()

        self.assertLess(time.monotonic() - started, 5)


if __name__ == "__main__":
    unittest.main()
