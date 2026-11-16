"""Model data pekerjaan (Job) untuk pelacakan status transkripsi."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


JOBS_STATUS_ORDER = [
    "queued",
    "probing",
    "extracting",
    "segmenting",
    "transcribing",
    "merging",
    "translating",
    "exporting",
    "completed",
    "failed",
    "cancelled",
]


@dataclass
class Job:
    """Mewakili satu pekerjaan transkripsi video ke subtitle."""

    id: str
    input_path: str
    output_path: str = ""
    status: str = "queued"
    language: str = "auto"
    model: str = ""
    backend: str = "cpu"
    cpu_fallback: bool = True
    segment_length_minutes: int = 20
    overlap_seconds: int = 2
    translate_to_id: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    progress: float = 0.0
    current_segment_progress: Optional[float] = None
    estimated_seconds_remaining: Optional[float] = None
    current_stage: str = ""
    total_segments: int = 0
    completed_segments: int = 0
    video_duration: float = 0.0
    audio_track_index: int = 0
    operation: str = "transcribe"
    target_language: str = "id"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        return cls(**data)

    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    def can_resume(self) -> bool:
        return self.status in ("failed", "cancelled", "queued") and not self.is_terminal()