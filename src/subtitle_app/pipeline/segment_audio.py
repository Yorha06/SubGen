"""Segmentasi audio menjadi potongan yang dapat diproses."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from subtitle_app.models.segment import Segment
from subtitle_app.utils.process import hidden_console_options


def segment_audio_file(
    audio_path: str,
    segment_length_minutes: int = 20,
    overlap_seconds: int = 2,
) -> List[Segment]:
    """
    Membagi file audio menjadi segmen dengan overlap.

    Menggunakan ffmpeg untuk memotong audio tanpa re-encoding yang signifikan
    agar tetap cepat dan ringan.
    """
    audio_file = Path(audio_path)
    if not audio_file.exists():
        raise FileNotFoundError(f"File audio tidak ditemukan: {audio_path}")

    # Dapatkan durasi audio menggunakan ffprobe
    import json
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "json", str(audio_file)
        ],
        capture_output=True, text=True, check=False, encoding="utf-8",
        **hidden_console_options(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe gagal: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    total_duration = float(data["format"]["duration"])

    segment_length_sec = segment_length_minutes * 60
    overlap_sec = overlap_seconds

    segments: List[Segment] = []
    index = 0
    current_start = 0.0

    while current_start < total_duration:
        current_end = min(current_start + segment_length_sec, total_duration)

        # Tambahkan overlap di akhir (kecuali segmen terakhir)
        overlap_end = 0.0
        if current_end < total_duration:
            overlap_end = min(overlap_sec, total_duration - current_end)

        # Tambahkan overlap di awal (kecuali segmen pertama)
        overlap_start = 0.0
        if index > 0:
            overlap_start = min(overlap_sec, current_start)

        seg = Segment(
            index=index,
            start_time=current_start,
            end_time=current_end,
            overlap_start=overlap_start,
            overlap_end=overlap_end,
            status="pending",
        )
        segments.append(seg)

        index += 1
        current_start = current_end

    return segments