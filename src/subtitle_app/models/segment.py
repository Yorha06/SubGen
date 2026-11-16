"""Model data segmen audio untuk pemrosesan bertahap."""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class Segment:
    """Satu segmen audio yang akan ditranskripsikan."""

    index: int
    start_time: float  # detik, relatif ke audio sumber
    end_time: float    # detik, relatif ke audio sumber
    overlap_start: float = 0.0
    overlap_end: float = 0.0
    status: str = "pending"  # pending, running, completed, failed
    transcript_text: str = ""
    transcript_segments: list = None  # hasil whisper.cpp per segmen
    error_message: str = ""
    attempts: int = 0
    max_attempts: int = 3

    def __post_init__(self):
        if self.transcript_segments is None:
            self.transcript_segments = []

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Segment":
        return cls(**data)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time