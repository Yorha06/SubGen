"""Penggabungan hasil segmen dengan koreksi timestamp global dan deduplikasi overlap."""

from __future__ import annotations

import re
from typing import List

from subtitle_app.models.job import Job
from subtitle_app.models.segment import Segment
from subtitle_app.models.subtitle_cue import SubtitleCue


def _split_long_text(text: str, max_chars: int) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    chunks = []
    while len(text) > max_chars:
        boundary = max(
            text.rfind(mark, 0, max_chars + 1)
            for mark in ".!?。！？"
        )
        if boundary >= max_chars // 3:
            cut = boundary + 1
        else:
            space = text.rfind(" ", 0, max_chars + 1)
            cut = space if space >= max_chars // 2 else max_chars

        chunk = text[:cut].strip()
        if not chunk:
            cut = max_chars
            chunk = text[:cut]
        chunks.append(chunk)
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


def merge_segments(
    job: Job,
    segments: List[Segment],
    settings,
) -> List[SubtitleCue]:
    """
    Menggabungkan hasil transkripsi semua segmen menjadi daftar SubtitleCue
    dengan timestamp global yang benar dan deduplikasi overlap.

    Algoritma:
      1. Untuk setiap segmen, tambahkan offset start_time ke semua timestamp lokal.
      2. Gabungkan semua cue.
      3. Deduplikasi teks pada area overlap (jika teks hampir sama, hapus duplikat).
      4. Urutkan berdasarkan waktu mulai.
      5. Pastikan end_time > start_time.
    """
    all_cues: List[SubtitleCue] = []
    cue_index = 1
    max_chars = max(1, int(settings.get("subtitle_max_chars", 42)))

    for seg in segments:
        if seg.status != "completed" or not seg.transcript_segments:
            continue

        offset = seg.start_time

        for seg_item in seg.transcript_segments:
            # whisper.cpp mengembalikan segmen dengan start/end dalam detik
            local_start = float(seg_item.get("start", 0))
            local_end = float(seg_item.get("end", 0))
            text = seg_item.get("text", "").strip()

            if not text:
                continue

            global_start = local_start + offset
            global_end = local_end + offset

            # Jangan melebihi durasi segmen (kecuali overlap)
            if global_end > seg.end_time + seg.overlap_end:
                global_end = seg.end_time + seg.overlap_end

            if global_end <= global_start:
                global_end = global_start + 0.5  # minimal durasi cue

            text_chunks = _split_long_text(text, max_chars)
            total_chars = sum(len(chunk) for chunk in text_chunks)
            elapsed_chars = 0
            duration = global_end - global_start
            for chunk_index, text_chunk in enumerate(text_chunks):
                chunk_start = (
                    global_start + duration * elapsed_chars / total_chars
                )
                elapsed_chars += len(text_chunk)
                chunk_end = (
                    global_end
                    if chunk_index == len(text_chunks) - 1
                    else global_start + duration * elapsed_chars / total_chars
                )
                all_cues.append(
                    SubtitleCue(
                        index=cue_index,
                        start_time=chunk_start,
                        end_time=chunk_end,
                        text=text_chunk,
                    )
                )
                cue_index += 1

    # Urutkan berdasarkan waktu mulai
    all_cues.sort(key=lambda c: c.start_time)

    # Deduplikasi overlap sederhana: jika dua cue berurutan memiliki teks
    # yang sama dan waktu yang sangat dekat, hapus yang kedua.
    deduped: List[SubtitleCue] = []
    for cue in all_cues:
        if deduped:
            last = deduped[-1]
            if (
                abs(cue.start_time - last.start_time) < 0.5
                and cue.text == last.text
            ):
                # Perbarui end_time dari yang terakhir jika diperlukan
                if cue.end_time > last.end_time:
                    last.end_time = cue.end_time
                continue
        deduped.append(cue)

    # Re-index
    for i, cue in enumerate(deduped):
        cue.index = i + 1

    return deduped