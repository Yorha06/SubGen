"""Penyimpanan manifest pekerjaan dan status segmen (JSON atau SQLite)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

from subtitle_app.models.job import Job
from subtitle_app.models.segment import Segment
from subtitle_app.utils.logging_setup import setup_app_logger


logger = setup_app_logger()


class JobStore:
    """Menyimpan dan memuat manifest pekerjaan serta status segmen."""

    def __init__(self, jobs_dir: str | Path, format: str = "json"):
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.format = format
        self._jobs: dict[str, Job] = {}

    def _job_path(self, job_id: str) -> Path:
        if self.format == "json":
            return self.jobs_dir / f"{job_id}.json"
        elif self.format == "sqlite":
            return self.jobs_dir / f"{job_id}.db"
        else:
            raise ValueError(f"Format job store tidak didukung: {self.format}")

    def save_job(self, job: Job) -> None:
        """Menyimpan manifest pekerjaan ke disk."""
        path = self._job_path(job.id)
        path.parent.mkdir(parents=True, exist_ok=True)

        if self.format == "json":
            self._write_job_atomically(path, job)
        else:
            # SQLite placeholder - implementasi sederhana dengan JSON untuk sekarang
            self._write_job_atomically(path, job)

        self._jobs[job.id] = job
        logger.debug(f"Job disimpan: {job.id} (status={job.status})")

    @staticmethod
    def _write_job_atomically(path: Path, job: Job) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.stem}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(job.to_dict(), file, indent=2, ensure_ascii=False)
            for attempt in range(6):
                try:
                    os.replace(temporary_path, path)
                    return
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(0.05 * (2**attempt))
        finally:
            temporary_path.unlink(missing_ok=True)

    def load_job(self, job_id: str) -> Optional[Job]:
        """Memuat manifest pekerjaan dari disk."""
        path = self._job_path(job_id)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            job = Job.from_dict(data)
            self._jobs[job_id] = job
            return job
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.error(f"Gagal memuat job {job_id}: {exc}")
            return None

    def list_jobs(self) -> list[Job]:
        """Membuat daftar semua pekerjaan yang tersimpan."""
        jobs = []
        for path in self.jobs_dir.iterdir():
            if path.suffix in (".json", ".db"):
                job_id = path.stem
                job = self.load_job(job_id)
                if job:
                    jobs.append(job)
        return jobs

    def delete_job(self, job_id: str) -> bool:
        """Menghapus manifest pekerjaan dari disk."""
        path = self._job_path(job_id)
        if path.exists():
            path.unlink()
            self._jobs.pop(job_id, None)
            return True
        return False

    def save_segment(self, job_id: str, segment: Segment) -> None:
        """Menyimpan status segmen individu sebagai file terpisah."""
        seg_dir = self.jobs_dir / job_id / "segments"
        seg_dir.mkdir(parents=True, exist_ok=True)
        seg_path = seg_dir / f"segment_{segment.index:04d}.json"

        tmp_path = seg_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(segment.to_dict(), f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, seg_path)

    def load_segment(self, job_id: str, segment_index: int) -> Optional[Segment]:
        """Memuat status segmen individu."""
        seg_path = (
            self.jobs_dir / job_id / "segments" / f"segment_{segment_index:04d}.json"
        )
        if not seg_path.exists():
            return None
        try:
            with open(seg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Segment.from_dict(data)
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.error(f"Gagal memuat segmen {segment_index} dari job {job_id}: {exc}")
            return None

    def list_segments(self, job_id: str) -> list[Segment]:
        """Membuat daftar semua segmen untuk pekerjaan."""
        seg_dir = self.jobs_dir / job_id / "segments"
        if not seg_dir.exists():
            return []
        segments = []
        for path in sorted(seg_dir.glob("segment_*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                segments.append(Segment.from_dict(data))
            except (json.JSONDecodeError, OSError, TypeError):
                continue
        return segments

    def cleanup_job(self, job_id: str, keep_temp: bool = False) -> None:
        """Membersihkan file sementara pekerjaan setelah selesai."""
        job_dir = self.jobs_dir / job_id
        if job_dir.exists() and not keep_temp:
            shutil.rmtree(job_dir, ignore_errors=True)