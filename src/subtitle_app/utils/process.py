"""Helpers for launching child processes without flashing consoles."""

from __future__ import annotations

import os
import subprocess
from threading import Event


def hidden_console_options() -> dict[str, int]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def run_cancellable(
    command: list[str],
    cancel_event: Event,
    **options,
) -> subprocess.CompletedProcess:
    if cancel_event.is_set():
        raise InterruptedError("Dibatalkan pengguna")

    process = subprocess.Popen(command, **options)
    while True:
        if cancel_event.is_set():
            terminate_process(process)
            raise InterruptedError("Dibatalkan pengguna")
        try:
            stdout, stderr = process.communicate(timeout=0.1)
            return subprocess.CompletedProcess(
                command, process.returncode, stdout, stderr
            )
        except subprocess.TimeoutExpired:
            continue


def terminate_process(
    process: subprocess.Popen,
    drain_output: bool = True,
) -> None:
    if process.poll() is None:
        try:
            process.terminate()
        except OSError:
            if process.poll() is None:
                raise
        if drain_output:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        else:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
