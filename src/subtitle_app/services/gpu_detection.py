"""Deteksi GPU AMD dan backend Vulkan."""

from __future__ import annotations

import subprocess
from typing import Optional

from subtitle_app.utils.logging_setup import setup_app_logger
from subtitle_app.utils.process import hidden_console_options


logger = setup_app_logger()


def detect_vulkan_devices() -> list[dict]:
    """Mendeteksi perangkat Vulkan menggunakan vulkaninfo jika tersedia."""
    devices = []
    try:
        result = subprocess.run(
            ["vulkaninfo", "--summary"],
            capture_output=True, text=True, check=False, encoding="utf-8",
            **hidden_console_options(),
        )
        if result.returncode != 0:
            return devices

        # Parsing sederhana dari output vulkaninfo
        current_device = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if "GPU" in line or "deviceName" in line:
                if current_device:
                    devices.append(current_device)
                current_device = {"name": line}
            elif "VENDOR" in line and current_device:
                current_device["vendor"] = line
        if current_device:
            devices.append(current_device)
    except (FileNotFoundError, OSError):
        pass

    return devices


def detect_amd_gpu() -> Optional[dict]:
    """Mendeteksi apakah ada GPU AMD Radeon yang terdeteksi."""
    devices = detect_vulkan_devices()
    for device in devices:
        name = device.get("name", "").upper()
        vendor = device.get("vendor", "").upper()
        if "AMD" in name or "RADEON" in name or "AMD" in vendor:
            return device
    return None


def check_vulkan_runtime() -> bool:
    """Periksa apakah runtime Vulkan tersedia di sistem."""
    try:
        result = subprocess.run(
            ["vulkaninfo", "--summary"],
            capture_output=True, check=False,
            **hidden_console_options(),
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False


class GPUDetector:
    """Manajer deteksi GPU dan pilihan backend."""

    def __init__(self, preferred_backend: str = "vulkan", fallback_backend: str = "cpu"):
        self.preferred_backend = preferred_backend
        self.fallback_backend = fallback_backend
        self._vulkan_available = None
        self._amd_gpu = None

    @property
    def vulkan_available(self) -> bool:
        if self._vulkan_available is None:
            self._vulkan_available = check_vulkan_runtime()
        return self._vulkan_available

    @property
    def amd_gpu(self) -> Optional[dict]:
        if self._amd_gpu is None:
            self._amd_gpu = detect_amd_gpu()
        return self._amd_gpu

    def get_effective_backend(self) -> str:
        """Mengembalikan backend yang akan digunakan berdasarkan deteksi."""
        if self.preferred_backend == "vulkan" and self.vulkan_available:
            return "vulkan"
        return self.fallback_backend

    def report(self) -> dict:
        return {
            "preferred_backend": self.preferred_backend,
            "vulkan_available": self.vulkan_available,
            "amd_gpu": self.amd_gpu,
            "effective_backend": self.get_effective_backend(),
        }