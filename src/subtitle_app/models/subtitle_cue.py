"""Model data cue subtitle untuk output SRT."""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class SubtitleCue:
    """Satu cue dalam file SRT."""

    index: int
    start_time: float  # detik, global
    end_time: float    # detik, global
    text: str

    def to_srt_block(self) -> str:
        from subtitle_app.utils.timestamps import seconds_to_srt_timestamp

        start = seconds_to_srt_timestamp(self.start_time)
        end = seconds_to_srt_timestamp(self.end_time)
        return f"{self.index}\n{start} --> {end}\n{self.text}\n"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SubtitleCue":
        return cls(**data)