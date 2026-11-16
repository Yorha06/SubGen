"""Validasi file input dan ruang penyimpanan."""

from __future__ import annotations

import os
from pathlib import Path


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a"}


def validate_input_file(file_path: str | Path) -> tuple[bool, str | None]:
    """Validasi apakah file input adalah video atau audio yang didukung.

    Returns (is_valid, error_message).
    """
    path = Path(file_path)

    if not path.exists():
        return False, f"File tidak ditemukan: {path}"

    if not path.is_file():
        return False, f"Bukan file: {path}"

    ext = path.suffix.lower()
    if ext not in SUPPORTED_VIDEO_EXTENSIONS and ext not in SUPPORTED_AUDIO_EXTENSIONS:
        return False, (
            f"Format file tidak didukung: {ext}. "
            f"Format yang didukung: {', '.join(sorted(SUPPORTED_VIDEO_EXTENSIONS | SUPPORTED_AUDIO_EXTENSIONS))}"
        )

    try:
        size = path.stat().st_size
        if size == 0:
            return False, "File kosong (0 byte)"
    except OSError as exc:
        return False, f"Tidak dapat mengakses file: {exc}"

    return True, None


def check_disk_space(path: str | Path, required_mb: float = 1024.0) -> tuple[bool, str | None]:
    """Memeriksa apakah ruang disk cukup di path yang diberikan.

    Returns (has_space, error_message).
    """
    try:
        free_bytes = shutil_disk_free(path)
        free_mb = free_bytes / (1024 * 1024)
        if free_mb < required_mb:
            return False, (
                f"Ruang disk tidak cukup: {free_mb:.1f} MB tersedia, "
                f"{required_mb:.1f} MB diperlukan"
            )
        return True, None
    except OSError as exc:
        return False, f"Tidak dapat memeriksa ruang disk: {exc}"


def shutil_disk_free(path: str | Path) -> int:
    """Wrapper untuk os.statvfs (Unix) atau os.stat (Windows) untuk ruang disk bebas."""
    if os.name == "nt":
        import ctypes

        free_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(str(path)), None, None, ctypes.byref(free_bytes)
        )
        return free_bytes.value
    else:
        stat = os.statvfs(path)
        return stat.f_bavail * stat.f_frsize


def sanitize_output_name(name: str) -> str:
    """Membersihkan nama file output dari karakter yang tidak aman."""
    import re

    # Ganti karakter yang tidak aman dengan underscore
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    # Batasi panjang
    return safe[:200]