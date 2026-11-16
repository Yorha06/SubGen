"""Ekspor file SRT dari daftar SubtitleCue."""

from __future__ import annotations

from pathlib import Path

from subtitle_app.models.subtitle_cue import SubtitleCue
from subtitle_app.pipeline.format_subtitles import format_srt, validate_cues


def export_srt(cues: List[SubtitleCue], output_path: str) -> str:
    """
    Menulis file SRT ke disk.

    Returns path file yang ditulis.
    """
    errors = validate_cues(cues)
    if errors:
        raise ValueError(f"Validasi gagal: {'; '.join(errors)}")

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    content = format_srt(cues)

    # Tulis secara atomik
    tmp_path = out_path.with_suffix(".srt.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os_replace(tmp_path, out_path)

    return str(out_path)


def os_replace(src: Path, dst: Path) -> None:
    """Replace file secara atomic (mirip os.replace)."""
    import os
    os.replace(src, dst)