"""Pengelolaan konfigurasi aplikasi dari file YAML."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class Settings:
    """Wrapper untuk konfigurasi aplikasi dengan akses atribut."""

    def __init__(self, config_path: str | Path | None = None):
        self._config: dict[str, Any] = {}
        self._config_path = Path(config_path) if config_path else None
        self._load_defaults()
        if self._config_path and self._config_path.exists():
            self._load_file(self._config_path)

    def _load_defaults(self) -> None:
        self._config = {
            "ffmpeg_path": "tools/ffmpeg/ffmpeg.exe",
            "ffprobe_path": "tools/ffmpeg/ffprobe.exe",
            "whisper_cpp_path": "tools/whisper.cpp/whisper-cli.exe",
            "models_dir": "models",
            "jobs_dir": "jobs",
            "output_dir": "output",
            "temp_dir": "temp",
            "audio_sample_rate": 16000,
            "audio_channels": 1,
            "audio_format": "s16",
            "segment_length_minutes": 20,
            "segment_overlap_seconds": 2,
            "subtitle_max_chars": 42,
            "default_model": "ggml-large-v3-turbo-q5_0.bin",
            "default_language": "auto",
            "beam_size": 5,
            "vad_enabled": False,
            "vad_threshold": 0.5,
            "vad_model_path": "",
            "preferred_backend": "vulkan",
            "fallback_backend": "cpu",
            "max_concurrent_gpu_jobs": 1,
            "output_encoding": "utf-8",
            "output_mode": "original",
            "translate_to": "id",
            "job_store_format": "json",
        }

    def _load_file(self, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if isinstance(data, dict):
            self._config.update(data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._config[key] = value

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' has no attribute {name!r}")
        return self._config.get(name)

    def __repr__(self) -> str:
        return f"Settings({len(self._config)} keys)"