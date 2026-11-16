import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from subtitle_app.models.job import Job
from subtitle_app.services.job_store import JobStore


class JobStoreTests(unittest.TestCase):
    def test_retries_transient_replace_lock_and_cleans_temp_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(temp_dir)
            job = Job(id="save1", input_path="input.mp4")
            real_replace = os.replace
            calls = 0

            def replace_with_transient_lock(source, destination):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise PermissionError("temporary file lock")
                real_replace(source, destination)

            with patch(
                "subtitle_app.services.job_store.os.replace",
                side_effect=replace_with_transient_lock,
            ):
                store.save_job(job)

            manifest = Path(temp_dir) / "save1.json"
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["id"], "save1")
            self.assertFalse(list(Path(temp_dir).glob("*.tmp")))
            self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
