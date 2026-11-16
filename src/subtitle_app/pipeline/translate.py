"""Antarmuka layanan penerjemahan opsional (Tahap 8)."""

from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from threading import Event
from typing import Callable, List, Protocol

from subtitle_app.models.subtitle_cue import SubtitleCue


TranslationProgressCallback = Callable[[str, float, int, int], None]


class _ModelDownloadError(RuntimeError):
    pass


class TranslationService(Protocol):
    """Protokol untuk layanan penerjemahan teks subtitle."""

    def translate_cues(
        self,
        cues: List[SubtitleCue],
        source_lang: str,
        target_lang: str = "id",
        cancel_event: Event | None = None,
        progress_callback: TranslationProgressCallback | None = None,
    ) -> List[SubtitleCue]:
        """Terjemahkan teks cue sambil mempertahankan ID dan timestamp."""
        ...


class ArgosTranslationService:
    """Penerjemah lokal Argos Translate dengan pemasangan model saat dibutuhkan."""

    def __init__(self) -> None:
        self.last_untranslated_count = 0

    def translate_cues(
        self,
        cues: List[SubtitleCue],
        source_lang: str,
        target_lang: str = "id",
        cancel_event: Event | None = None,
        progress_callback: TranslationProgressCallback | None = None,
    ) -> List[SubtitleCue]:
        if not cues:
            raise ValueError("File SRT tidak berisi cue untuk diterjemahkan.")

        self.last_untranslated_count = 0
        source_lang = self._resolve_source_language(cues, source_lang)
        if source_lang == target_lang:
            return [
                SubtitleCue(cue.index, cue.start_time, cue.end_time, cue.text)
                for cue in cues
            ]

        translation = self._translation_for(
            source_lang,
            target_lang,
            cancel_event,
            progress_callback,
        )
        translated = []
        translated_text_cache = {}
        total = len(cues)
        for index, cue in enumerate(cues, start=1):
            self._raise_if_cancelled(cancel_event)
            if cue.text in translated_text_cache:
                text, used_source_text = translated_text_cache[cue.text]
            else:
                text = translation.translate(cue.text)
                used_source_text = not text.strip()
                if used_source_text:
                    text = cue.text
                translated_text_cache[cue.text] = (text, used_source_text)
            if used_source_text:
                self.last_untranslated_count += 1
            translated.append(
                SubtitleCue(cue.index, cue.start_time, cue.end_time, text.strip())
            )
            if progress_callback and (index % 100 == 0 or index == total):
                progress_callback(
                    f"Menerjemahkan cue {index} / {total}",
                    20.0 + 75.0 * index / total,
                    index,
                    total,
                )
        return translated

    def _translation_for(
        self,
        source_lang: str,
        target_lang: str,
        cancel_event: Event | None,
        progress_callback: TranslationProgressCallback | None,
    ):
        try:
            import argostranslate.package as argos_package
            import argostranslate.translate as argos_translate
        except ImportError as exc:
            raise RuntimeError(
                "Argos Translate belum terpasang. Jalankan pip install -r requirements.txt."
            ) from exc

        argos_translate.installed_translates.clear()
        argos_translate.get_installed_languages.cache_clear()
        if not self._has_route(argos_translate, source_lang, target_lang):
            packages = self._available_packages(
                argos_package,
                source_lang,
                target_lang,
                cancel_event,
                progress_callback,
            )
            pairs = self._find_route(source_lang, target_lang, packages)
            if pairs is None:
                raise RuntimeError(
                    f"Rute model Argos {source_lang} ke {target_lang} tidak tersedia."
                )
            for index, (from_code, to_code) in enumerate(pairs):
                self._raise_if_cancelled(cancel_event)
                if self._has_route(argos_translate, from_code, to_code):
                    continue
                available = next(
                    (
                        item
                        for item in packages
                        if item.from_code == from_code and item.to_code == to_code
                    ),
                    None,
                )
                if available is None:
                    raise RuntimeError(
                        f"Model Argos {from_code} ke {to_code} tidak tersedia."
                    )
                self._install_package(
                    available,
                    argos_package,
                    argos_translate,
                    cancel_event,
                    progress_callback,
                    index,
                    len(pairs),
                )

        self._raise_if_cancelled(cancel_event)
        if not self._has_route(argos_translate, source_lang, target_lang):
            raise RuntimeError(
                f"Rute model Argos {source_lang} ke {target_lang} belum tersedia."
            )
        return argos_translate.get_translation_from_codes(source_lang, target_lang)

    @classmethod
    def _available_packages(
        cls,
        argos_package,
        source_lang: str,
        target_lang: str,
        cancel_event: Event | None,
        progress_callback: TranslationProgressCallback | None,
    ):
        index_path = Path(argos_package.settings.local_package_index)
        if index_path.exists():
            packages = argos_package.get_available_packages()
        else:
            packages = []

        if cls._find_route(source_lang, target_lang, packages) is not None:
            return packages

        cls._raise_if_cancelled(cancel_event)
        if progress_callback:
            progress_callback("Mengunduh daftar model bahasa...", 5.0, 0, 0)
        request = urllib.request.Request(
            argos_package.settings.remote_package_index,
            headers={"User-Agent": "SubGen local translation"},
        )
        chunks = []
        with urllib.request.urlopen(request, timeout=5) as response:
            while True:
                cls._raise_if_cancelled(cancel_event)
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)

        index_data = json.loads(b"".join(chunks))
        index_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_index = index_path.with_suffix(index_path.suffix + ".tmp")
        try:
            temporary_index.write_text(
                json.dumps(index_data),
                encoding="utf-8",
            )
            os.replace(temporary_index, index_path)
        finally:
            temporary_index.unlink(missing_ok=True)
        packages = [
            argos_package.AvailablePackage(metadata)
            for metadata in index_data
        ]
        if cls._find_route(source_lang, target_lang, packages) is None:
            raise RuntimeError(
                f"Argos tidak menyediakan rute {source_lang} ke {target_lang}."
            )
        return packages

    @staticmethod
    def _find_route(source_lang: str, target_lang: str, packages) -> list[tuple[str, str]] | None:
        routes: dict[str, list[str]] = {}
        for item in packages:
            routes.setdefault(item.from_code, []).append(item.to_code)

        pending = [source_lang]
        previous: dict[str, str | None] = {source_lang: None}
        while pending:
            current = pending.pop(0)
            if current == target_lang:
                pairs = []
                while previous[current] is not None:
                    prior = previous[current]
                    pairs.append((prior, current))
                    current = prior
                return list(reversed(pairs))
            for next_language in routes.get(current, []):
                if next_language not in previous:
                    previous[next_language] = current
                    pending.append(next_language)
        return None

    @staticmethod
    def _has_route(argos_translate, source_lang: str, target_lang: str) -> bool:
        languages = {
            language.code: language
            for language in argos_translate.get_installed_languages()
        }
        source = languages.get(source_lang)
        target = languages.get(target_lang)
        return source is not None and target is not None and (
            source.get_translation(target) is not None
        )

    @classmethod
    def _install_package(
        cls,
        available,
        argos_package,
        argos_translate,
        cancel_event: Event | None,
        progress_callback: TranslationProgressCallback | None,
        package_index: int,
        package_count: int,
    ) -> None:
        package_name = f"{available.from_code} ke {available.to_code}"
        if progress_callback:
            progress_callback(f"Menyiapkan model {package_name}", 5.0, 0, 0)

        descriptor, temporary_name = tempfile.mkstemp(suffix=".argosmodel")
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            failures = []
            for link in available.links:
                if not link.startswith("https://"):
                    continue
                cls._raise_if_cancelled(cancel_event)
                try:
                    cls._download(
                        link,
                        temporary_path,
                        package_name,
                        cancel_event,
                        progress_callback,
                        package_index,
                        package_count,
                    )
                    argos_package.install_from_path(temporary_path)
                    argos_translate.installed_translates.clear()
                    argos_translate.get_installed_languages.cache_clear()
                    return
                except InterruptedError:
                    raise
                except _ModelDownloadError as exc:
                    failures.append(f"{link}: {exc}")
            raise RuntimeError(
                f"Gagal mengunduh model Argos {package_name}: "
                + ("; ".join(failures) if failures else "tidak ada URL HTTPS.")
            )
        finally:
            temporary_path.unlink(missing_ok=True)

    @classmethod
    def _download(
        cls,
        url: str,
        destination: Path,
        package_name: str,
        cancel_event: Event | None,
        progress_callback: TranslationProgressCallback | None,
        package_index: int,
        package_count: int,
    ) -> None:
        if progress_callback:
            progress_callback(
                f"Mengunduh model {package_name}...",
                5.0 + 15.0 * package_index / package_count,
                0,
                0,
            )
        request = urllib.request.Request(
            url, headers={"User-Agent": "SubGen local translation"}
        )
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except (OSError, urllib.error.URLError) as exc:
            raise _ModelDownloadError(str(exc)) from exc

        with response:
            content_length = response.headers.get("Content-Length")
            total_bytes = int(content_length) if content_length else 0
            downloaded = 0
            last_reported_bytes = 0
            last_reported_at = time.monotonic()
            with destination.open("wb") as model_file:
                while True:
                    cls._raise_if_cancelled(cancel_event)
                    try:
                        chunk = response.read(64 * 1024)
                    except (OSError, urllib.error.URLError) as exc:
                        raise _ModelDownloadError(str(exc)) from exc
                    if not chunk:
                        break
                    model_file.write(chunk)
                    downloaded += len(chunk)
                    now = time.monotonic()
                    if (
                        progress_callback
                        and total_bytes
                        and (
                            downloaded - last_reported_bytes >= 1024 * 1024
                            and now - last_reported_at >= 0.5
                        )
                    ):
                        fraction = min(1.0, downloaded / total_bytes)
                        progress = 5.0 + 15.0 * (
                            package_index + fraction
                        ) / package_count
                        progress_callback(
                            f"Mengunduh model {package_name} "
                            f"({downloaded // (1024 * 1024)} MB)",
                            progress,
                            0,
                            0,
                        )
                        last_reported_bytes = downloaded
                        last_reported_at = now
        cls._raise_if_cancelled(cancel_event)

    @staticmethod
    def _resolve_source_language(
        cues: List[SubtitleCue], source_lang: str
    ) -> str:
        if source_lang != "auto":
            if source_lang not in ("ja", "en", "ko", "id"):
                raise ValueError(f"Bahasa sumber {source_lang} tidak didukung.")
            return source_lang

        text = "\n".join(cue.text for cue in cues)
        if any("\uac00" <= char <= "\ud7af" for char in text):
            return "ko"
        if any(
            "\u3040" <= char <= "\u30ff" or "\u4e00" <= char <= "\u9fff"
            for char in text
        ):
            return "ja"
        return "en"

    @staticmethod
    def _raise_if_cancelled(cancel_event: Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Dibatalkan pengguna")