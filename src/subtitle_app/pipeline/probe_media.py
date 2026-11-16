"""Modul pemeriksaan media (ffprobe) - dipisahkan untuk kemudahan pengujian."""

from __future__ import annotations

from subtitle_app.services.ffmpeg_service import FFmpegService


def probe_media(ffmpeg: FFmpegService, input_path: str) -> dict:
    """Menjalankan ffprobe dan mengembalikan metadata."""
    return ffmpeg.probe(input_path)


def get_audio_streams(ffmpeg: FFmpegService, input_path: str) -> list[dict]:
    """Mengembalikan daftar stream audio."""
    return ffmpeg.get_audio_streams(input_path)


def get_duration(ffmpeg: FFmpegService, input_path: str) -> float:
    """Mengembalikan durasi dalam detik."""
    return ffmpeg.get_duration(input_path)


def has_audio(ffmpeg: FFmpegService, input_path: str) -> bool:
    """Periksa apakah file memiliki audio."""
    return ffmpeg.has_audio(input_path)