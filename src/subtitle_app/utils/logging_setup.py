"""Konfigurasi logging per pekerjaan dan aplikasi."""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path


def setup_job_logger(job_id: str, log_dir: str | Path) -> logging.Logger:
    """Membuat logger terpisah untuk setiap pekerjaan dengan file handler."""
    logger = logging.getLogger(f"subtitle_app.job.{job_id}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Hindari duplikasi handler jika logger sudah ada
    if logger.handlers:
        return logger

    log_path = Path(log_dir) / f"{job_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


def setup_app_logger(log_dir: str | Path | None = None) -> logging.Logger:
    """Membuat logger utama aplikasi."""
    logger = logging.getLogger("subtitle_app")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler jika log_dir disediakan
    if log_dir:
        log_path = Path(log_dir) / "app.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger