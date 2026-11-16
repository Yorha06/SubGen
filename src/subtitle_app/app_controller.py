"""Pengontrol aplikasi yang menghubungkan GUI dengan pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Callable

from subtitle_app.models.job import Job
from subtitle_app.services.ffmpeg_service import FFmpegService
from subtitle_app.services.whisper_cpp_service import WhisperCppService
from subtitle_app.services.gpu_detection import GPUDetector
from subtitle_app.services.job_store import JobStore
from subtitle_app.pipeline.job_runner import JobRunner
from subtitle_app.pipeline.translate import ArgosTranslationService
from subtitle_app.settings import Settings


class AppController:
    """Kontroler utama aplikasi."""

    def __init__(self, settings: Settings):
        self.settings = settings

        # Inisialisasi layanan
        self.ffmpeg = FFmpegService(
            settings.get("ffmpeg_path", "tools/ffmpeg/ffmpeg.exe"),
            settings.get("ffprobe_path", "tools/ffmpeg/ffprobe.exe"),
        )
        self.whisper = WhisperCppService(
            settings.get("whisper_cpp_path", "tools/whisper.cpp/whisper-cli.exe"),
            settings.get("models_dir", "models"),
            backend=settings.get("preferred_backend", "vulkan"),
            vad_model_path=settings.get("vad_model_path", ""),
        )
        self.gpu_detector = GPUDetector(
            preferred_backend=settings.get("preferred_backend", "vulkan"),
            fallback_backend=settings.get("fallback_backend", "cpu"),
        )
        self.job_store = JobStore(
            settings.get("jobs_dir", "jobs"),
            format=settings.get("job_store_format", "json"),
        )
        self.job_runner = JobRunner(
            self.ffmpeg,
            self.whisper,
            self.job_store,
            settings,
            ArgosTranslationService(),
        )

        self._current_job: Optional[Job] = None
        self._status_callback: Optional[Callable[[Job], None]] = None
        self.job_runner.add_callback(self._on_job_update)

    def _on_job_update(self, job: Job) -> None:
        self._current_job = job
        if self._status_callback:
            self._status_callback(job)

    def set_status_callback(self, callback: Callable[[Job], None]) -> None:
        self._status_callback = callback

    def check_environment(self) -> dict:
        """Memeriksa ketersediaan dependensi dan mengembalikan laporan status."""
        report = {
            "ffmpeg_available": self.ffmpeg.check_available(),
            "whisper_available": self.whisper.check_available(),
            "gpu_report": self.gpu_detector.report(),
            "models": self.whisper.list_available_models(),
        }
        return report

    def create_job(
        self,
        input_path: str,
        output_path: str = "",
        language: str = "auto",
        model: str = "",
        backend: str = "vulkan",
        cpu_fallback: bool = True,
        segment_length_minutes: int = 20,
        overlap_seconds: int = 2,
        translate_to_id: bool = False,
        audio_track_index: int = 0,
        operation: str = "transcribe",
        target_language: str = "id",
    ) -> Job:
        """Membuat pekerjaan baru."""
        import uuid
        from datetime import datetime

        job_id = str(uuid.uuid4())[:8]
        if not output_path:
            input_name = Path(input_path).stem
            output_path = str(
                Path(self.settings.get("output_dir", "output")) / f"{input_name}.srt"
            )
        output_path = self.get_available_output_path(output_path)

        job = Job(
            id=job_id,
            input_path=input_path,
            output_path=output_path,
            language=language,
            model=model or self.settings.get("default_model", ""),
            backend=backend,
            cpu_fallback=cpu_fallback,
            segment_length_minutes=segment_length_minutes,
            overlap_seconds=overlap_seconds,
            translate_to_id=translate_to_id,
            audio_track_index=audio_track_index,
            operation=operation,
            target_language=target_language,
        )
        self.job_store.save_job(job)
        self._current_job = job
        return job

    @staticmethod
    def get_available_output_path(output_path: str) -> str:
        """Return a path that does not overwrite an existing output file."""
        path = Path(output_path)
        if not path.exists():
            return str(path)

        suffix = path.suffix
        stem = path.stem
        number = 2
        while True:
            candidate = path.with_name(f"{stem} ({number}){suffix}")
            if not candidate.exists():
                return str(candidate)
            number += 1

    def start_current_job(self) -> None:
        """Memulai pekerjaan yang saat ini aktif."""
        if self._current_job and not self.job_runner.is_running():
            self.job_runner.start_job(self._current_job)

    def stop_current_job(self) -> None:
        """Menghentikan pekerjaan yang sedang berjalan."""
        self.job_runner.stop_job()

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.job_store.load_job(job_id)

    def list_jobs(self) -> list[Job]:
        return self.job_store.list_jobs()