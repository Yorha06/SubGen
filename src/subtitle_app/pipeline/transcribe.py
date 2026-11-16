"""Modul transkripsi per segmen menggunakan whisper.cpp."""

from __future__ import annotations

from typing import List

from subtitle_app.models.segment import Segment
from subtitle_app.services.whisper_cpp_service import WhisperCppService


def transcribe_segment(
    whisper: WhisperCppService,
    segment: Segment,
    audio_path: str,
    model_name: str,
    language: str = "auto",
    backend: str = "cpu",
    beam_size: int = 5,
    vad: bool = True,
    output_dir: str | None = None,
) -> Segment:
    """
    Mentranskripsi satu segmen audio dan memperbarui objek Segment.

    Returns Segment yang telah diperbarui.
    """
    result = whisper.transcribe_segment(
        audio_path=audio_path,
        model_name=model_name,
        language=language,
        backend=backend,
        beam_size=beam_size,
        vad=vad,
        output_dir=output_dir,
    )

    segment.transcript_text = result.get("text", "")
    segment.transcript_segments = result.get("segments", [])
    segment.status = "completed"
    return segment