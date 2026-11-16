"""Orkestrator jalur pemrosesan pekerjaan (job runner)."""

from __future__ import annotations

import threading
import uuid
import time
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from subtitle_app.models.job import Job, JOBS_STATUS_ORDER
from subtitle_app.models.segment import Segment
from subtitle_app.models.subtitle_cue import SubtitleCue
from subtitle_app.services.ffmpeg_service import FFmpegService
from subtitle_app.services.whisper_cpp_service import WhisperCppService
from subtitle_app.services.job_store import JobStore
from subtitle_app.pipeline.export_srt import export_srt
from subtitle_app.pipeline.srt_io import read_srt
from subtitle_app.pipeline.translate import ArgosTranslationService, TranslationService
from subtitle_app.utils.logging_setup import setup_job_logger


def _estimate_remaining_seconds(elapsed: float, fraction: float) -> float | None:
    if elapsed < 30 or fraction < 0.01:
        return None
    return elapsed * (1.0 - fraction) / fraction


class JobRunner:
    """Menjalankan pipeline transkripsi di thread latar belakang."""

    def __init__(
        self,
        ffmpeg_service: FFmpegService,
        whisper_service: WhisperCppService,
        job_store: JobStore,
        settings,
        translation_service: TranslationService | None = None,
    ):
        self.ffmpeg = ffmpeg_service
        self.whisper = whisper_service
        self.store = job_store
        self.settings = settings
        self.translator = translation_service or ArgosTranslationService()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._callbacks: list[Callable[[Job], None]] = []
        self._cleanup_terminal_temp_dirs()

    def _cleanup_terminal_temp_dirs(self) -> None:
        temp_root = Path(self.settings.get("temp_dir", "temp"))
        if not temp_root.is_dir():
            return

        terminal_statuses = {"completed", "failed", "cancelled"}
        for job in self.store.list_jobs():
            if job.status in terminal_statuses:
                self._remove_temp_dir(temp_root / job.id, logging.getLogger(__name__))

    @staticmethod
    def _remove_temp_dir(temp_dir: Path, logger) -> None:
        if not temp_dir.exists():
            return
        try:
            shutil.rmtree(temp_dir)
        except OSError as exc:
            logger.warning(f"Gagal membersihkan direktori sementara {temp_dir}: {exc}")

    def add_callback(self, callback: Callable[[Job], None]) -> None:
        self._callbacks.append(callback)

    def _notify(self, job: Job) -> None:
        for cb in self._callbacks:
            try:
                cb(job)
            except Exception:
                pass

    def start_job(self, job: Job) -> None:
        """Memulai pekerjaan di thread latar belakang."""
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Pekerjaan lain sedang berjalan")

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_job, args=(job,), daemon=True)
        self._thread.start()

    def stop_job(self) -> None:
        """Meminta penghentian pekerjaan yang sedang berjalan."""
        self._stop_event.set()

    def is_running(self) -> bool:
        """Mengembalikan True jika ada pekerjaan yang sedang berjalan."""
        return self._thread is not None and self._thread.is_alive()

    def _run_job(self, job: Job) -> None:
        logger = setup_job_logger(job.id, self.store.jobs_dir)
        temp_dir = Path(self.settings.get("temp_dir", "temp")) / job.id

        try:
            if Path(job.output_path).exists():
                raise FileExistsError(
                    f"File output sudah ada; gunakan nama lain: {job.output_path}"
                )
            if job.operation == "translate_srt":
                self._run_srt_translation(job)
                return

            job.status = "probing"
            job.started_at = datetime.now().isoformat()
            job.progress = 0.0
            job.current_segment_progress = None
            job.estimated_seconds_remaining = None
            job.current_stage = "Memeriksa media..."
            self.store.save_job(job)
            self._notify(job)

            if self._stop_event.is_set():
                raise InterruptedError("Dibatalkan pengguna")

            metadata = self.ffmpeg.probe(
                job.input_path, cancel_event=self._stop_event
            )
            media_format = metadata.get("format", {})
            try:
                job.video_duration = float(media_format.get("duration", 0))
            except (TypeError, ValueError):
                job.video_duration = 0.0
            audio_streams = [
                stream
                for stream in metadata.get("streams", [])
                if stream.get("codec_type") == "audio"
            ]

            if not audio_streams:
                raise RuntimeError("File video tidak memiliki stream audio")

            job.status = "extracting"
            job.progress = 5.0
            job.current_stage = "Mengekstrak audio..."
            self.store.save_job(job)
            self._notify(job)

            temp_dir.mkdir(parents=True, exist_ok=True)
            extracted_wav = str(temp_dir / "audio_extracted.wav")

            self.ffmpeg.extract_audio(
                job.input_path,
                extracted_wav,
                audio_track_index=job.audio_track_index,
                sample_rate=self.settings.get("audio_sample_rate", 16000),
                channels=self.settings.get("audio_channels", 1),
                cancel_event=self._stop_event,
            )

            # Langkah 3: Segmentasi
            job.status = "segmenting"
            job.progress = 10.0
            job.current_stage = "Membuat segmen audio..."
            self.store.save_job(job)
            self._notify(job)

            from subtitle_app.pipeline.segment_audio import segment_audio_file

            segments = segment_audio_file(
                extracted_wav,
                segment_length_minutes=self.settings.get("segment_length_minutes", 20),
                overlap_seconds=self.settings.get("segment_overlap_seconds", 2),
            )
            job.total_segments = len(segments)

            for seg in segments:
                self.store.save_segment(job.id, seg)

            if self._stop_event.is_set():
                raise InterruptedError("Dibatalkan pengguna")

            # Langkah 4: Transkripsi per segmen
            job.status = "transcribing"
            job.progress = 10.0
            job.current_segment_progress = 0.0
            job.current_stage = f"Menyiapkan transkripsi {len(segments)} segmen..."
            self.store.save_job(job)
            self._notify(job)

            model_name = job.model or self.settings.get(
                "default_model", "ggml-large-v3-turbo-q5_0.bin"
            )
            language = job.language
            backend = job.backend
            beam_size = self.settings.get("beam_size", 5)
            max_subtitle_chars = self.settings.get("subtitle_max_chars", 42)
            vad_enabled = self.settings.get("vad_enabled", False)

            transcript_dir = temp_dir / "transcripts"
            transcript_dir.mkdir(parents=True, exist_ok=True)
            segment_audio_dir = temp_dir / "audio_segments"
            segment_audio_dir.mkdir(parents=True, exist_ok=True)
            total_audio_duration = sum(max(seg.duration, 0.0) for seg in segments) or 1.0
            completed_audio_duration = 0.0
            transcription_started_at = time.monotonic()

            for i, seg in enumerate(segments):
                if self._stop_event.is_set():
                    raise InterruptedError("Dibatalkan pengguna")

                existing = self.store.load_segment(job.id, seg.index)
                if (
                    existing
                    and existing.status == "completed"
                    and existing.transcript_text
                    and existing.transcript_segments
                ):
                    seg.transcript_text = existing.transcript_text
                    seg.transcript_segments = existing.transcript_segments or []
                    seg.status = "completed"
                    job.completed_segments += 1
                    completed_audio_duration += max(seg.duration, 0.0)
                    job.progress = 10.0 + (
                        completed_audio_duration / total_audio_duration
                    ) * 80.0
                    job.current_segment_progress = 100.0
                    job.current_stage = f"Segmen {i + 1} / {len(segments)} sudah tersedia"
                    self.store.save_segment(job.id, seg)
                    self.store.save_job(job)
                    self._notify(job)
                    continue

                job.current_stage = f"Mentranskripsi segmen {i + 1} / {len(segments)}..."
                job.current_segment_progress = 0.0
                job.estimated_seconds_remaining = None
                job.progress = 10.0 + (
                    completed_audio_duration / total_audio_duration
                ) * 80.0
                self.store.save_job(job)
                self._notify(job)

                progress_state = {
                    "fraction": completed_audio_duration / total_audio_duration
                }

                def report_progress(percent: int) -> None:
                    current_fraction = (
                        completed_audio_duration
                        + max(seg.duration, 0.0) * percent / 100.0
                    ) / total_audio_duration
                    progress_state["fraction"] = max(
                        progress_state["fraction"], current_fraction
                    )
                    fraction = min(1.0, progress_state["fraction"])
                    job.current_segment_progress = percent
                    job.progress = 10.0 + fraction * 80.0
                    elapsed = time.monotonic() - transcription_started_at
                    estimate = _estimate_remaining_seconds(elapsed, fraction)
                    if estimate is not None:
                        job.estimated_seconds_remaining = estimate
                    job.current_stage = (
                        f"Mentranskripsi segmen {i + 1} / {len(segments)}..."
                    )
                    self.store.save_job(job)
                    self._notify(job)

                for _ in range(seg.max_attempts):
                    if self._stop_event.is_set():
                        raise InterruptedError("Dibatalkan pengguna")

                    seg.status = "running"
                    seg.attempts += 1
                    self.store.save_segment(job.id, seg)

                    try:
                        segment_audio_path = segment_audio_dir / f"segment_{seg.index:04d}.wav"
                        self.ffmpeg.extract_audio_segment(
                            extracted_wav,
                            str(segment_audio_path),
                            start_time=seg.start_time,
                            duration=seg.duration,
                            cancel_event=self._stop_event,
                        )
                        try:
                            result = self.whisper.transcribe_segment(
                                audio_path=str(segment_audio_path),
                                model_name=model_name,
                                language=language,
                                backend=backend,
                                beam_size=beam_size,
                                max_segment_length=max_subtitle_chars,
                                vad=vad_enabled,
                                output_dir=str(transcript_dir),
                                progress_callback=report_progress,
                                cancel_event=self._stop_event,
                            )
                        except RuntimeError as exc:
                            if backend != "vulkan" or not job.cpu_fallback:
                                raise
                            logger.warning(
                                f"Transkripsi Vulkan gagal: {exc}; beralih ke CPU."
                            )
                            job.current_stage = (
                                "Vulkan gagal; melanjutkan transkripsi dengan CPU..."
                            )
                            self.store.save_job(job)
                            self._notify(job)
                            backend = "cpu"
                            job.backend = backend
                            result = self.whisper.transcribe_segment(
                                audio_path=str(segment_audio_path),
                                model_name=model_name,
                                language=language,
                                backend=backend,
                                beam_size=beam_size,
                                max_segment_length=max_subtitle_chars,
                                vad=vad_enabled,
                                output_dir=str(transcript_dir),
                                progress_callback=report_progress,
                                cancel_event=self._stop_event,
                            )
                        if not result.get("text", "").strip() or not result.get("segments"):
                            raise RuntimeError("Whisper tidak menghasilkan teks transkrip.")
                    except InterruptedError:
                        seg.status = "pending"
                        self.store.save_segment(job.id, seg)
                        raise
                    except Exception as exc:
                        logger.error(
                            f"Segmen {seg.index}, percobaan {seg.attempts} "
                            f"gagal: {exc}"
                        )
                        seg.error_message = str(exc)
                        seg.status = (
                            "pending" if seg.attempts < seg.max_attempts else "failed"
                        )
                        self.store.save_segment(job.id, seg)
                        if seg.status == "failed":
                            raise RuntimeError(
                                f"Segmen {seg.index} gagal setelah "
                                f"{seg.max_attempts} percobaan: {exc}"
                            ) from exc
                        continue

                    seg.transcript_text = result["text"]
                    seg.transcript_segments = result["segments"]
                    seg.status = "completed"
                    job.completed_segments += 1
                    completed_audio_duration += max(seg.duration, 0.0)
                    job.current_segment_progress = 100.0
                    job.progress = 10.0 + (
                        completed_audio_duration / total_audio_duration
                    ) * 80.0
                    break

                self.store.save_segment(job.id, seg)
                self.store.save_job(job)
                self._notify(job)

            # Langkah 5: Penggabungan segmen dan timestamp
            if self._stop_event.is_set():
                raise InterruptedError("Dibatalkan pengguna")
            job.status = "merging"
            job.progress = max(job.progress, 92.0)
            job.current_segment_progress = None
            job.estimated_seconds_remaining = None
            job.current_stage = "Menggabungkan segmen dan memperbaiki timestamp..."
            self.store.save_job(job)
            self._notify(job)

            from subtitle_app.pipeline.merge_segments import merge_segments

            cues = merge_segments(job, segments, self.settings)
            if not cues:
                raise RuntimeError(
                    "Tidak ada segmen transkrip. File SRT kosong tidak dibuat."
                )
            if self._stop_event.is_set():
                raise InterruptedError("Dibatalkan pengguna")

            # Langkah 6: Format dan ekspor SRT
            job.status = "exporting"
            job.progress = 97.0
            job.current_stage = "Mengekspor file SRT..."
            self.store.save_job(job)
            self._notify(job)

            from subtitle_app.pipeline.export_srt import export_srt

            export_srt(cues, job.output_path)
            if self._stop_event.is_set():
                raise InterruptedError("Dibatalkan pengguna")

            job.status = "completed"
            job.progress = 100.0
            job.current_segment_progress = None
            job.estimated_seconds_remaining = 0.0
            job.current_stage = "Selesai"
            self.store.save_job(job)
            self._notify(job)

        except InterruptedError:
            job.status = "cancelled"
            job.current_segment_progress = None
            job.estimated_seconds_remaining = None
            job.current_stage = "Dibatalkan"
            self.store.save_job(job)
            self._notify(job)
            logger.info("Pekerjaan dibatalkan pengguna")
        except Exception as exc:
            logger.error(f"Pekerjaan gagal: {exc}")
            job.status = "failed"
            job.current_segment_progress = None
            job.estimated_seconds_remaining = None
            job.error_message = str(exc)
            job.current_stage = "Gagal"
            self.store.save_job(job)
            self._notify(job)
        finally:
            self._remove_temp_dir(temp_dir, logger)
            self._stop_event.clear()

    def _run_srt_translation(self, job: Job) -> None:
        job.status = "translating"
        job.started_at = datetime.now().isoformat()
        job.progress = 0.0
        job.completed_segments = 0
        job.total_segments = 0
        job.current_stage = "Membaca file SRT..."
        self.store.save_job(job)
        self._notify(job)

        cues = read_srt(job.input_path)
        job.total_segments = len(cues)
        job.current_stage = f"Menyiapkan terjemahan {len(cues)} cue..."
        self.store.save_job(job)
        self._notify(job)

        def report_progress(
            stage: str, progress: float, completed: int, total: int
        ) -> None:
            if self._stop_event.is_set():
                raise InterruptedError("Dibatalkan pengguna")
            job.current_stage = stage
            job.progress = max(job.progress, min(95.0, progress))
            if total:
                job.completed_segments = completed
                job.total_segments = total
            self.store.save_job(job)
            self._notify(job)

        translated_cues = self.translator.translate_cues(
            cues,
            source_lang=job.language,
            target_lang=job.target_language,
            cancel_event=self._stop_event,
            progress_callback=report_progress,
        )
        if self._stop_event.is_set():
            raise InterruptedError("Dibatalkan pengguna")

        untranslated_count = getattr(self.translator, "last_untranslated_count", 0)
        job.completed_segments = job.total_segments
        job.progress = max(job.progress, 95.0)
        job.current_stage = "Menyimpan file SRT terjemahan..."
        job.progress = max(job.progress, 97.0)
        self.store.save_job(job)
        self._notify(job)
        export_srt(translated_cues, job.output_path)
        if self._stop_event.is_set():
            raise InterruptedError("Dibatalkan pengguna")

        job.status = "completed"
        job.progress = 100.0
        job.completed_segments = job.total_segments
        job.estimated_seconds_remaining = 0.0
        job.current_stage = "Terjemahan selesai"
        if untranslated_count:
            job.current_stage += (
                f"; {untranslated_count} cue dipertahankan dalam bahasa sumber"
            )
        self.store.save_job(job)
        self._notify(job)