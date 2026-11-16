"""Layanan untuk memanggil FFmpeg dan ffprobe."""

from __future__ import annotations

import subprocess
import json
import os
from pathlib import Path
from threading import Event
from typing import Optional

from subtitle_app.utils.logging_setup import setup_app_logger
from subtitle_app.utils.process import hidden_console_options, run_cancellable


logger = setup_app_logger()


class FFmpegService:
    """Wrapper untuk menjalankan ffprobe dan FFmpeg."""

    def __init__(self, ffmpeg_path: str, ffprobe_path: str):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def probe(self, input_path: str, cancel_event: Event | None = None) -> dict:
        """Menjalankan ffprobe dan mengembalikan metadata media sebagai dict."""
        if not os.path.exists(self.ffprobe_path):
            raise FileNotFoundError(f"ffprobe tidak ditemukan: {self.ffprobe_path}")

        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-of", "json",
            input_path,
        ]

        result = self._run(cmd, cancel_event)

        if result.returncode != 0:
            raise RuntimeError(
                f"ffprobe gagal (kode {result.returncode}): {result.stderr.strip()}"
            )

        return json.loads(result.stdout)

    def get_audio_streams(self, input_path: str) -> list[dict]:
        """Mengembalikan daftar stream audio dari file input."""
        metadata = self.probe(input_path)
        streams = []
        for stream in metadata.get("streams", []):
            if stream.get("codec_type") == "audio":
                streams.append(stream)
        return streams

    def get_duration(self, input_path: str) -> float:
        """Mengembalikan durasi file dalam detik."""
        metadata = self.probe(input_path)
        format_info = metadata.get("format", {})
        duration_str = format_info.get("duration", "0")
        try:
            return float(duration_str)
        except (ValueError, TypeError):
            return 0.0

    def extract_audio(
        self,
        input_path: str,
        output_wav: str,
        audio_track_index: int = 0,
        sample_rate: int = 16000,
        channels: int = 1,
        cancel_event: Event | None = None,
    ) -> None:
        """Ekstrak audio dari video ke file WAV mono 16 kHz."""
        if not os.path.exists(self.ffmpeg_path):
            raise FileNotFoundError(f"ffmpeg tidak ditemukan: {self.ffmpeg_path}")

        output_path = Path(output_wav)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", input_path,
            "-map", f"0:a:{audio_track_index}",
            "-ac", str(channels),
            "-ar", str(sample_rate),
            "-sample_fmt", "s16",
            str(output_path),
        ]

        logger.info(f"Ekstraksi audio: {input_path} -> {output_wav}")

        try:
            result = self._run(cmd, cancel_event)
        except InterruptedError:
            output_path.unlink(missing_ok=True)
            raise

        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg gagal mengekstrak audio (kode {result.returncode}): "
                f"{result.stderr.strip()}"
            )

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("File output audio kosong atau tidak dibuat")

    def extract_audio_segment(
        self,
        input_path: str,
        output_wav: str,
        start_time: float,
        duration: float,
        cancel_event: Event | None = None,
    ) -> None:
        """Ekstrak satu rentang audio PCM tanpa mentranskripsikan file penuh."""
        if not os.path.exists(self.ffmpeg_path):
            raise FileNotFoundError(f"ffmpeg tidak ditemukan: {self.ffmpeg_path}")

        output_path = Path(output_wav)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-ss", f"{start_time:.3f}",
            "-i", input_path,
            "-t", f"{duration:.3f}",
            "-c:a", "pcm_s16le",
            str(output_path),
        ]

        try:
            result = self._run(cmd, cancel_event)
        except InterruptedError:
            output_path.unlink(missing_ok=True)
            raise

        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg gagal membuat segmen audio (kode {result.returncode}): "
                f"{result.stderr.strip()}"
            )
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("File segmen audio kosong atau tidak dibuat")

    @staticmethod
    def _run(command: list[str], cancel_event: Event | None) -> subprocess.CompletedProcess:
        options = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            **hidden_console_options(),
        }
        if cancel_event is not None:
            return run_cancellable(command, cancel_event, **options)
        return subprocess.run(command, check=False, **options)

    def has_audio(self, input_path: str) -> bool:
        """Periksa apakah file input memiliki stream audio."""
        try:
            streams = self.get_audio_streams(input_path)
            return len(streams) > 0
        except Exception:
            return False

    def check_available(self) -> bool:
        """Periksa apakah ffmpeg dan ffprobe dapat dipanggil."""
        try:
            subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True, check=False,
                **hidden_console_options(),
            )
            subprocess.run(
                [self.ffprobe_path, "-version"],
                capture_output=True, check=False,
                **hidden_console_options(),
            )
            return True
        except (FileNotFoundError, OSError):
            return False