"""Utilitas konversi dan format timestamp untuk subtitle SRT."""

from __future__ import annotations

import re


def seconds_to_srt_timestamp(seconds: float) -> str:
    """Mengonversi detik (float) ke format SRT: HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0

    total_ms = int(round(seconds * 1000))
    hours = total_ms // 3_600_000
    total_ms %= 3_600_000
    minutes = total_ms // 60_000
    total_ms %= 60_000
    secs = total_ms // 1000
    millis = total_ms % 1000

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def srt_timestamp_to_seconds(timestamp: str) -> float:
    """Mengonversi format SRT HH:MM:SS,mmm ke detik (float)."""
    match = re.match(r"(\d{2,}):(\d{2}):(\d{2}),(\d{3})", timestamp.strip())
    if not match:
        raise ValueError(f"Format timestamp SRT tidak valid: {timestamp!r}")

    hours, minutes, seconds, millis = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def format_duration(seconds: float) -> str:
    """Format durasi dalam detik menjadi string yang dapat dibaca manusia."""
    if seconds < 60:
        return f"{seconds:.1f} detik"
    if seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes} menit {secs} detik"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours} jam {minutes} menit"