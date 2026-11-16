"""Wrapper untuk menjalankan binary whisper.cpp dengan dukungan Vulkan/CPU."""

from __future__ import annotations

import subprocess
import json
import os
import queue
import re
import threading
from pathlib import Path
from threading import Event
from typing import Callable

from subtitle_app.utils.logging_setup import setup_app_logger
from subtitle_app.utils.process import (
    hidden_console_options,
    run_cancellable,
    terminate_process,
)
from subtitle_app.utils.timestamps import srt_timestamp_to_seconds


logger = setup_app_logger()


def _read_progress_updates(buffer: str) -> tuple[list[int], str]:
    updates = []
    while "%" in buffer:
        before, buffer = buffer.split("%", 1)
        match = re.search(r"(\d{1,3})\s*$", before)
        if match:
            percent = int(match.group(1))
            if percent <= 100:
                updates.append(percent)
    return updates, buffer[-128:]


class WhisperCppService:
    """Wrapper untuk whisper-cli dari whisper.cpp."""

    def __init__(
        self,
        whisper_cpp_path: str,
        models_dir: str,
        backend: str = "cpu",
        vad_model_path: str = "",
    ):
        self.whisper_cpp_path = whisper_cpp_path
        self.models_dir = models_dir
        self.backend = backend
        self.vad_model_path = vad_model_path

    def _model_path(self, model_name: str) -> str:
        return str(Path(self.models_dir) / model_name)

    def _run_with_progress(
        self,
        command: list[str],
        progress_callback: Callable[[int], None],
        cancel_event: Event | None = None,
    ) -> subprocess.CompletedProcess:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Dibatalkan pengguna")

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **hidden_console_options(),
        )
        events: queue.Queue[tuple[str, bytes | None]] = queue.Queue()

        def pump_stream(name: str, stream) -> None:
            try:
                while True:
                    chunk = stream.read1(4096)
                    if not chunk:
                        break
                    events.put((name, chunk))
            finally:
                events.put((name, None))

        readers = [
            threading.Thread(
                target=pump_stream,
                args=("stdout", process.stdout),
                daemon=True,
            ),
            threading.Thread(
                target=pump_stream,
                args=("stderr", process.stderr),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()

        stdout_chunks = []
        stderr_chunks = []
        progress_buffer = ""
        last_percent = None
        open_streams = len(readers)

        while open_streams:
            if cancel_event is not None and cancel_event.is_set():
                terminate_process(process, drain_output=False)
            try:
                name, chunk = events.get(timeout=0.1)
            except queue.Empty:
                continue
            if chunk is None:
                open_streams -= 1
                continue

            if name == "stdout":
                stdout_chunks.append(chunk)
                continue

            stderr_chunks.append(chunk)
            progress_buffer += chunk.decode("utf-8", errors="replace")
            updates, progress_buffer = _read_progress_updates(progress_buffer)
            for percent in updates:
                if percent != last_percent:
                    progress_callback(percent)
                    last_percent = percent

        for reader in readers:
            reader.join()
        returncode = process.wait()
        process.stdout.close()
        process.stderr.close()
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Dibatalkan pengguna")
        return subprocess.CompletedProcess(
            command,
            returncode,
            b"".join(stdout_chunks).decode("utf-8", errors="replace"),
            b"".join(stderr_chunks).decode("utf-8", errors="replace"),
        )

    def check_available(self) -> bool:
        """Periksa apakah binary whisper.cpp dapat dipanggil."""
        try:
            result = subprocess.run(
                [self.whisper_cpp_path, "--help"],
                capture_output=True, text=True, check=False, encoding="utf-8",
                **hidden_console_options(),
            )
            return result.returncode == 0
        except (FileNotFoundError, OSError):
            return False

    def list_available_models(self) -> list[str]:
        """Daftar file model yang tersedia di models_dir."""
        models_path = Path(self.models_dir)
        if not models_path.exists():
            return []
        models = []
        for f in models_path.iterdir():
            if f.suffix in (".bin", ".gguf"):
                models.append(f.name)
        return sorted(models)

    def transcribe_segment(
        self,
        audio_path: str,
        model_name: str,
        language: str = "auto",
        backend: str = "cpu",
        beam_size: int = 5,
        max_segment_length: int = 42,
        vad: bool = False,
        output_dir: str | None = None,
        progress_callback: Callable[[int], None] | None = None,
        cancel_event: Event | None = None,
    ) -> dict:
        """
        Menjalankan whisper.cpp pada satu file audio segmen.

        Returns dict dengan kunci:
          - text: teks transkripsi lengkap
          - segments: daftar segmen dengan start, end, text
          - language: bahasa yang terdeteksi
          - duration: durasi audio
        """
        if not os.path.exists(self.whisper_cpp_path):
            raise FileNotFoundError(f"whisper.cpp tidak ditemukan: {self.whisper_cpp_path}")

        model_path = self._model_path(model_name)
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model tidak ditemukan: {model_path}")

        output_dir_path = Path(output_dir) if output_dir else Path(audio_path).parent
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_base = output_dir_path / Path(audio_path).stem

        cmd = [
            self.whisper_cpp_path,
            "-m", model_path,
            "-f", audio_path,
            "-l", language if language != "auto" else "auto",
            "--beam-size", str(beam_size),
            "--max-len", str(max(1, max_segment_length)),
            "--split-on-word",
            "--output-json",
            "--output-file", str(output_base),
        ]

        if backend != "vulkan":
            cmd.append("--no-gpu")

        if vad:
            if not self.vad_model_path or not os.path.isfile(self.vad_model_path):
                raise FileNotFoundError(
                    "Model VAD tidak ditemukan. Atur vad_model_path atau nonaktifkan VAD."
                )
            cmd.extend(["--vad", "--vad-model", self.vad_model_path])

        if progress_callback:
            cmd.append("--print-progress")

        logger.info(f"Menjalankan whisper.cpp: {audio_path} (backend={backend}, model={model_name})")

        if progress_callback:
            result = self._run_with_progress(
                cmd, progress_callback, cancel_event=cancel_event
            )
        elif cancel_event is not None:
            result = run_cancellable(
                cmd,
                cancel_event,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                **hidden_console_options(),
            )
        else:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=False, encoding="utf-8",
                **hidden_console_options(),
            )

        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Dibatalkan pengguna")

        if result.returncode != 0:
            raise RuntimeError(
                f"whisper.cpp gagal (kode {result.returncode}): {result.stderr.strip()}"
            )

        json_path = Path(f"{output_base}.json")
        if not json_path.exists():
            detail = result.stderr.strip()
            raise RuntimeError(
                "whisper.cpp tidak menghasilkan file JSON transkrip."
                + (f" Detail: {detail[-1000:]}" if detail else "")
            )

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_segments = data.get("segments")
        if not isinstance(raw_segments, list):
            raw_segments = data.get("transcription", [])

        segments = []
        for item in raw_segments:
            text = str(item.get("text", "")).strip()
            if not text:
                continue

            if "start" in item and "end" in item:
                start = float(item["start"])
                end = float(item["end"])
            elif isinstance(item.get("offsets"), dict):
                start = float(item["offsets"]["from"]) / 1000
                end = float(item["offsets"]["to"]) / 1000
            elif isinstance(item.get("timestamps"), dict):
                start = srt_timestamp_to_seconds(item["timestamps"]["from"])
                end = srt_timestamp_to_seconds(item["timestamps"]["to"])
            else:
                continue

            segments.append({"start": start, "end": end, "text": text})

        if not segments:
            raise RuntimeError("whisper.cpp tidak menghasilkan segmen teks.")

        data["segments"] = segments
        data["text"] = data.get("text") or " ".join(
            segment["text"] for segment in segments
        )

        return data