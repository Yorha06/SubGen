"""Modul ekstraksi audio menggunakan FFmpeg."""

from __future__ import annotations

from pathlib import Path
from subtitle_app.services.ffmpeg_service import FFmpegService


def extract_audio(
    ffmpeg: FFmpegService,
    input_path: str,
    output_wav: str,
    audio_track_index: int = 0,
    sample_rate: int = 16000,
    channels: int = 1,
) -> str:
    """Ekstrak audio ke WAV mono 16 kHz. Mengembalikan path output."""
    output_path = Path(output_wav)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg.extract_audio(
        input_path,
        str(output_path),
        audio_track_index=audio_track_index,
        sample_rate=sample_rate,
        channels=channels,
    )
    return str(output_path)