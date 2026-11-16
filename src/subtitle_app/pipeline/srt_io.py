"""Membaca file subtitle SRT menjadi cue terstruktur."""

from __future__ import annotations

import re
from pathlib import Path

from subtitle_app.models.subtitle_cue import SubtitleCue
from subtitle_app.utils.timestamps import srt_timestamp_to_seconds


_TIMING_LINE = re.compile(
    r"^\s*(\d{2,}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(\d{2,}:\d{2}:\d{2}[,.]\d{3})(?:\s+.*)?$"
)


def parse_srt(content: str) -> list[SubtitleCue]:
    """Parse SRT cues, preserving indices, timestamps, and multiline text."""
    content = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n[ \t]*\n+", content.strip())
    if not content.strip():
        raise ValueError("File SRT kosong.")

    cues = []
    for block_number, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if len(lines) < 3 or not lines[0].strip().isdigit():
            raise ValueError(f"Format cue SRT tidak valid pada blok {block_number}.")

        timing = _TIMING_LINE.match(lines[1])
        if not timing:
            raise ValueError(f"Timestamp SRT tidak valid pada cue {lines[0].strip()}.")

        start = srt_timestamp_to_seconds(timing.group(1).replace(".", ","))
        end = srt_timestamp_to_seconds(timing.group(2).replace(".", ","))
        text = "\n".join(lines[2:]).strip()
        if end <= start:
            raise ValueError(f"Waktu akhir cue {lines[0].strip()} harus setelah waktu mulai.")
        if not text:
            raise ValueError(f"Teks cue {lines[0].strip()} kosong.")

        cues.append(
            SubtitleCue(
                index=int(lines[0].strip()),
                start_time=start,
                end_time=end,
                text=text,
            )
        )

    return cues


def read_srt(path: str | Path) -> list[SubtitleCue]:
    with open(path, "r", encoding="utf-8-sig") as subtitle_file:
        return parse_srt(subtitle_file.read())
