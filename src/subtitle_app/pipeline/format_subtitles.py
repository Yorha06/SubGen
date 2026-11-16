"""Pemformatan dan validasi subtitle SRT."""

from __future__ import annotations

from typing import List

from subtitle_app.models.subtitle_cue import SubtitleCue
from subtitle_app.utils.timestamps import seconds_to_srt_timestamp


def format_srt(cues: List[SubtitleCue]) -> str:
    """Mengembalikan isi file SRT sebagai string dari daftar cue."""
    lines: List[str] = []
    for cue in cues:
        start = seconds_to_srt_timestamp(cue.start_time)
        end = seconds_to_srt_timestamp(cue.end_time)
        lines.append(str(cue.index))
        lines.append(f"{start} --> {end}")
        lines.append(cue.text)
        lines.append("")  # baris kosong memisahkan cue
    return "\n".join(lines)


def validate_cues(cues: List[SubtitleCue]) -> List[str]:
    """Memvalidasi daftar cue dan mengembalikan daftar pesan error."""
    errors: List[str] = []
    if not cues:
        errors.append("Daftar cue kosong")
    for cue in cues:
        if cue.end_time <= cue.start_time:
            errors.append(
                f"Cue {cue.index}: end_time ({cue.end_time}) <= start_time ({cue.start_time})"
            )
        if not cue.text.strip():
            errors.append(f"Cue {cue.index}: teks kosong")
    return errors