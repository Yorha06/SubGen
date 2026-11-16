import tempfile
import unittest
from pathlib import Path

from subtitle_app.app_controller import AppController
from subtitle_app.settings import Settings


class AppControllerTests(unittest.TestCase):
    def test_create_job_chooses_new_output_path_instead_of_overwriting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = Settings()
            settings.set("jobs_dir", str(root / "jobs"))
            settings.set("output_dir", str(root / "output"))
            controller = AppController(settings)
            existing_output = root / "output" / "video.srt"
            existing_output.parent.mkdir(parents=True)
            existing_output.write_text("previous subtitles", encoding="utf-8")

            job = controller.create_job(
                input_path=str(root / "video.mp4"),
                output_path=str(existing_output),
                model="selected-model.bin",
                backend="cpu",
            )

            self.assertEqual(
                Path(job.output_path),
                existing_output.with_name("video (2).srt"),
            )
            self.assertEqual(
                existing_output.read_text(encoding="utf-8"),
                "previous subtitles",
            )
            self.assertEqual(job.model, "selected-model.bin")

    def test_available_output_path_skips_multiple_existing_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "video.srt"
            base.touch()
            base.with_name("video (2).srt").touch()

            result = AppController.get_available_output_path(str(base))

            self.assertEqual(Path(result), base.with_name("video (3).srt"))


if __name__ == "__main__":
    unittest.main()
