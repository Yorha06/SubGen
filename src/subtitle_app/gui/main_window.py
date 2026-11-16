"""Jendela utama aplikasi PySide6."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QComboBox, QCheckBox,
    QProgressBar, QTextEdit, QGroupBox, QMessageBox, QFrame,
    QSpinBox, QRadioButton, QDialog, QPlainTextEdit
)
from PySide6.QtCore import Qt, QTimer, Signal, QUrl, QSettings
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDesktopServices

from subtitle_app.app_controller import AppController
from subtitle_app.settings import Settings
from subtitle_app.models.job import Job


class MainWindow(QMainWindow):
    """Jendela utama aplikasi SubGen."""

    job_updated = Signal(object)

    def __init__(self, controller: AppController, settings: Settings):
        super().__init__()
        self.controller = controller
        self.settings = settings
        self._last_logged_state: tuple[str, str] | None = None
        self._job_started_at: datetime | None = None
        self._job_eta_seconds: float | None = None
        self._job_status = ""
        self._cancel_requested = False
        self._output_path_was_browsed = False
        self._ui_settings = QSettings("SubGen", "SubGen")
        self.setWindowTitle("SubGen - Video to SRT Subtitle Transcription")
        self.resize(900, 700)
        self.setAcceptDrops(True)
        self._setup_ui()
        self._connect_signals()
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._update_timing_label)
        self._refresh_environment()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # === Job type ===
        mode_group = QGroupBox("Jenis pekerjaan")
        self.mode_group = mode_group
        mode_layout = QHBoxLayout()
        self.transcribe_mode_rb = QRadioButton("Transkripsikan video/audio")
        self.transcribe_mode_rb.setChecked(True)
        self.translate_mode_rb = QRadioButton("Terjemahkan file SRT")
        mode_layout.addWidget(self.transcribe_mode_rb)
        mode_layout.addWidget(self.translate_mode_rb)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # === Input ===
        input_group = QGroupBox("Input Video")
        self.input_group = input_group
        input_layout = QHBoxLayout()
        self.input_edit = QLabel("Belum ada file yang dipilih")
        self.input_edit.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Sunken)
        self.input_edit.setMinimumHeight(30)
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_input)
        input_layout.addWidget(self.input_edit, stretch=1)
        input_layout.addWidget(btn_browse)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        self.meta_label = QLabel("Durasi: -   Audio: -   Ukuran: -")
        layout.addWidget(self.meta_label)

        # === Transcription Settings ===
        trans_group = QGroupBox("Transkripsi")
        self.trans_group = trans_group
        trans_layout = QHBoxLayout()

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Auto", "Jepang (ja)", "Inggris (en)", "Korea (ko)", "Indonesia (id)"])
        self.language_label = QLabel("Bahasa:")
        trans_layout.addWidget(self.language_label)
        trans_layout.addWidget(self.lang_combo)

        self.model_combo = QComboBox()
        self.model_combo.addItems(["Large-v3 Turbo Q5", "Medium", "Small", "Large-v3"])
        trans_layout.addWidget(QLabel("Model:"))
        trans_layout.addWidget(self.model_combo)

        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["Vulkan GPU", "CPU"])
        trans_layout.addWidget(QLabel("Backend:"))
        trans_layout.addWidget(self.backend_combo)

        self.cpu_fallback_cb = QCheckBox("CPU fallback")
        self.cpu_fallback_cb.setChecked(True)
        trans_layout.addWidget(self.cpu_fallback_cb)

        trans_group.setLayout(trans_layout)
        layout.addWidget(trans_group)

        source_group = QGroupBox("Terjemahan SRT")
        self.translation_language_group = source_group
        source_layout = QHBoxLayout()
        self.srt_language_combo = QComboBox()
        self.srt_language_combo.addItems(
            ["Auto", "Jepang (ja)", "Inggris (en)", "Korea (ko)", "Indonesia (id)"]
        )
        self.target_language_combo = QComboBox()
        self.target_language_combo.addItems(
            ["Indonesia (id)", "Inggris (en)", "Jepang (ja)", "Korea (ko)"]
        )
        self.target_language_combo.currentTextChanged.connect(
            self._update_translation_output
        )
        source_layout.addWidget(QLabel("Bahasa sumber:"))
        source_layout.addWidget(self.srt_language_combo)
        source_layout.addWidget(QLabel("Bahasa tujuan:"))
        source_layout.addWidget(self.target_language_combo)
        source_layout.addWidget(
            QLabel("Auto mengenali tulisan Jepang/Korea; teks Latin dianggap Inggris.")
        )
        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        # Segmen
        seg_group = QGroupBox("Segmentasi")
        self.seg_group = seg_group
        seg_layout = QHBoxLayout()
        self.seg_spin = QSpinBox()
        self.seg_spin.setRange(5, 60)
        self.seg_spin.setValue(20)
        self.seg_spin.setSuffix(" menit")
        seg_layout.addWidget(QLabel("Panjang segmen:"))
        seg_layout.addWidget(self.seg_spin)
        self.overlap_spin = QSpinBox()
        self.overlap_spin.setRange(0, 10)
        self.overlap_spin.setValue(2)
        self.overlap_spin.setSuffix(" detik overlap")
        seg_layout.addWidget(QLabel("Overlap:"))
        seg_layout.addWidget(self.overlap_spin)
        seg_group.setLayout(seg_layout)
        layout.addWidget(seg_group)

        # === Output ===
        out_group = QGroupBox("Output")
        self.out_group = out_group
        out_layout = QHBoxLayout()
        self.output_edit = QLabel("Pilih file output SRT")
        self.output_edit.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Sunken)
        btn_out_browse = QPushButton("Browse...")
        btn_out_browse.clicked.connect(self._browse_output)
        out_layout.addWidget(self.output_edit, stretch=1)
        out_layout.addWidget(btn_out_browse)
        out_group.setLayout(out_layout)
        layout.addWidget(out_group)

        # === Controls ===
        ctrl_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_start.setMinimumHeight(40)
        self.btn_start.clicked.connect(self._start_job)
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setEnabled(False)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_job)
        self.btn_resume = QPushButton("Resume")
        self.btn_resume.setEnabled(False)
        self.btn_resume.clicked.connect(self._start_job)
        ctrl_layout.addWidget(self.btn_start)
        ctrl_layout.addWidget(self.btn_pause)
        ctrl_layout.addWidget(self.btn_cancel)
        ctrl_layout.addWidget(self.btn_resume)
        layout.addLayout(ctrl_layout)

        # === Progress ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        self.stage_label = QLabel("Siap")
        layout.addWidget(self.stage_label)
        self.segment_label = QLabel("")
        layout.addWidget(self.segment_label)
        self.eta_label = QLabel("")
        layout.addWidget(self.eta_label)
        self.backend_label = QLabel("Backend: -")
        layout.addWidget(self.backend_label)

        # === Log ===
        log_group = QGroupBox("Log / Pesan")
        log_layout = QVBoxLayout()
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(150)
        log_layout.addWidget(self.log_edit)
        btn_log = QPushButton("Buka Folder Output")
        btn_log.clicked.connect(self._open_output_folder)
        btn_preview = QPushButton("Preview SRT")
        btn_preview.clicked.connect(self._preview_srt)
        log_btn_layout = QHBoxLayout()
        log_btn_layout.addWidget(btn_preview)
        log_btn_layout.addStretch()
        log_btn_layout.addWidget(btn_log)
        log_layout.addLayout(log_btn_layout)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        self.transcribe_mode_rb.toggled.connect(self._update_mode_ui)
        self._update_mode_ui()

    def _connect_signals(self) -> None:
        self.job_updated.connect(self._on_job_updated)
        self.controller.set_status_callback(
            lambda job: self.job_updated.emit(replace(job))
        )

    def _refresh_environment(self) -> None:
        report = self.controller.check_environment()
        gpu = report.get("gpu_report", {})
        backend_text = gpu.get("effective_backend", "cpu").upper()
        self.backend_label.setText(f"Backend: {backend_text}")
        self.backend_combo.setCurrentText(
            "Vulkan GPU" if backend_text == "VULKAN" else "CPU"
        )

        if not report.get("ffmpeg_available"):
            self.log("Peringatan: ffmpeg tidak ditemukan. Pasang di tools/ffmpeg/")
        if not report.get("whisper_available"):
            self.log("Peringatan: whisper.cpp tidak ditemukan. Pasang di tools/whisper.cpp/")

        models = report.get("models", [])
        if models:
            self.model_combo.clear()
            self.model_combo.addItems(models)
            default_model = self.settings.get("default_model", "")
            if default_model in models:
                self.model_combo.setCurrentText(default_model)

        amd_gpu = gpu.get("amd_gpu")
        if amd_gpu:
            self.log(f"GPU terdeteksi: {amd_gpu.get('name', 'Unknown')}")
        else:
            self.log("GPU AMD tidak terdeteksi via Vulkan, menggunakan CPU fallback")

    def _on_job_updated(self, job: Job) -> None:
        self.progress_bar.setValue(int(job.progress))
        stage_text = job.current_stage
        if job.status == "transcribing" and job.current_segment_progress is not None:
            stage_text += f" ({job.current_segment_progress:.0f}%)"
        self.stage_label.setText(stage_text)
        if job.total_segments > 0:
            item_label = "Cue" if job.operation == "translate_srt" else "Segmen"
            self.segment_label.setText(
                f"{item_label} selesai: {job.completed_segments} / {job.total_segments}"
            )
        else:
            self.segment_label.setText("")

        state = (job.status, job.current_stage)
        if state != self._last_logged_state:
            self.log(f"[{job.status}] {job.current_stage}")
            self._last_logged_state = state

        self._job_status = job.status
        self._job_eta_seconds = job.estimated_seconds_remaining
        if job.started_at:
            self._job_started_at = datetime.fromisoformat(job.started_at)
            if not self._elapsed_timer.isActive():
                self._elapsed_timer.start()

        if job.status == "completed":
            self._elapsed_timer.stop()
            self._job_started_at = None
            self.eta_label.setText("Proses selesai.")
        elif job.status == "failed":
            self._elapsed_timer.stop()
            self._job_started_at = None
            self.eta_label.setText("Proses gagal.")
        elif job.status == "cancelled":
            self._elapsed_timer.stop()
            self._job_started_at = None
            self.eta_label.setText("Proses dibatalkan.")
        else:
            self._update_timing_label()

        if job.status == "completed":
            self.btn_start.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.btn_pause.setEnabled(False)
            self.btn_resume.setEnabled(False)
            self._set_job_form_enabled(True)
            self._cancel_requested = False
            self.btn_cancel.setText("Cancel")
            self.log(f"Selesai! Output: {job.output_path}")
        elif job.status == "failed":
            self.btn_start.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.btn_pause.setEnabled(False)
            self.btn_resume.setEnabled(False)
            self._set_job_form_enabled(True)
            self._cancel_requested = False
            self.btn_cancel.setText("Cancel")
            self.log(f"Error: {job.error_message}")
        elif job.status == "cancelled":
            self.btn_start.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.btn_pause.setEnabled(False)
            self.btn_resume.setEnabled(False)
            self._set_job_form_enabled(True)
            self._cancel_requested = False
            self.btn_cancel.setText("Cancel")
        elif job.status in ("queued", "probing", "extracting", "segmenting", "transcribing", "merging", "translating", "exporting"):
            self.btn_start.setEnabled(False)
            self.btn_cancel.setEnabled(not self._cancel_requested)
            self.btn_pause.setEnabled(False)
            self.btn_resume.setEnabled(False)
            self._set_job_form_enabled(False)

    def _set_job_form_enabled(self, enabled: bool) -> None:
        for group in (
            self.mode_group,
            self.input_group,
            self.trans_group,
            self.translation_language_group,
            self.seg_group,
            self.out_group,
        ):
            group.setEnabled(enabled)

    def _update_mode_ui(self) -> None:
        translating = self.translate_mode_rb.isChecked()
        self.input_group.setTitle("Input SRT" if translating else "Input Video/Audio")
        self.trans_group.setVisible(not translating)
        self.translation_language_group.setVisible(translating)
        self.seg_group.setVisible(not translating)
        self.btn_start.setText("Terjemahkan SRT" if translating else "Start")
        self.language_label.setText(
            "Bahasa sumber:" if translating else "Bahasa:"
        )

    def log(self, message: str) -> None:
        self.log_edit.append(message)

    def _update_timing_label(self) -> None:
        if not self._job_started_at:
            return

        elapsed = max(0, int((datetime.now() - self._job_started_at).total_seconds()))
        elapsed_hours, remainder = divmod(elapsed, 3600)
        elapsed_minutes, elapsed_seconds = divmod(remainder, 60)
        elapsed_text = (
            f"{elapsed_hours:02d}:{elapsed_minutes:02d}:{elapsed_seconds:02d}"
        )

        if self._job_status == "translating":
            self.eta_label.setText(
                f"Waktu berjalan: {elapsed_text}; terjemahan lokal sedang berjalan."
            )
            return

        if self._job_status != "transcribing" or self._job_eta_seconds is None:
            self.eta_label.setText(
                f"Waktu berjalan: {elapsed_text}; estimasi muncul setelah transkripsi berjalan."
            )
            return

        remaining = max(0.0, self._job_eta_seconds)
        total_minutes = max(1, int((remaining + 59) // 60))
        hours, minutes = divmod(total_minutes, 60)
        duration_text = f"{hours} jam {minutes} menit" if hours else f"{minutes} menit"
        finish_time = (datetime.now() + timedelta(seconds=remaining)).strftime("%H:%M")
        self.eta_label.setText(
            f"Berjalan: {elapsed_text}; sisa sekitar {duration_text}, "
            f"selesai sekitar {finish_time}"
        )

    def _browse_input(self) -> None:
        translating = self.translate_mode_rb.isChecked()
        if translating:
            title = "Pilih file subtitle SRT"
            file_filter = "Subtitle SRT (*.srt)"
        else:
            title = "Pilih File Video/Audio"
            file_filter = (
                "Video/Audio (*.mp4 *.mkv *.mov *.avi *.webm *.wav *.mp3 "
                "*.aac *.flac *.ogg *.m4a);;Semua File (*)"
            )
        file_path, _ = QFileDialog.getOpenFileName(
            self, title, self._last_browse_directory(), file_filter
        )
        if file_path:
            self._remember_browse_directory(file_path)
            self.input_edit.setText(file_path)
            self._set_default_output(file_path)
            self.meta_label.setText(
                "File SRT siap diterjemahkan."
                if translating
                else "Memeriksa file..."
            )

    def _browse_output(self) -> None:
        current_path = self.output_edit.text()
        if not current_path.lower().endswith(".srt"):
            filename = "subtitle.srt"
        else:
            filename = Path(current_path).name
        current_path = str(Path(self._last_browse_directory()) / filename)
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Simpan file SRT", current_path, "Subtitle SRT (*.srt)"
        )
        if file_path:
            self._remember_browse_directory(file_path)
            if Path(file_path).suffix.lower() != ".srt":
                file_path += ".srt"
            file_path = self.controller.get_available_output_path(file_path)
            self.output_edit.setText(file_path)
            self._output_path_was_browsed = True

    def _set_default_output(self, input_path: str) -> None:
        if self.translate_mode_rb.isChecked():
            target_map = {
                "Indonesia (id)": "id",
                "Inggris (en)": "en",
                "Jepang (ja)": "ja",
                "Korea (ko)": "ko",
            }
            suffix = f".{target_map.get(self.target_language_combo.currentText(), 'id')}.srt"
        else:
            suffix = ".srt"
        output_path = Path(self.settings.get("output_dir", "output"))
        output_path /= f"{Path(input_path).stem}{suffix}"
        self.output_edit.setText(
            self.controller.get_available_output_path(str(output_path))
        )
        self._output_path_was_browsed = False

    def _update_translation_output(self) -> None:
        input_path = self.input_edit.text()
        if (
            self.translate_mode_rb.isChecked()
            and not self._output_path_was_browsed
            and Path(input_path).is_file()
        ):
            self._set_default_output(input_path)

    def _start_job(self) -> None:
        input_path = self.input_edit.text()
        if not input_path or input_path == "Belum ada file yang dipilih":
            kind = "file SRT" if self.translate_mode_rb.isChecked() else "video/audio"
            QMessageBox.warning(self, "Peringatan", f"Pilih {kind} terlebih dahulu.")
            return
        if not Path(input_path).is_file():
            QMessageBox.warning(self, "Peringatan", "File input tidak ditemukan.")
            return

        translating = self.translate_mode_rb.isChecked()
        if translating and Path(input_path).suffix.lower() != ".srt":
            QMessageBox.warning(
                self, "Peringatan", "Mode terjemahan hanya menerima file .srt."
            )
            return
        if not translating and Path(input_path).suffix.lower() == ".srt":
            QMessageBox.warning(
                self, "Peringatan", "File .srt harus diproses melalui mode terjemahan."
            )
            return

        output_path = self.output_edit.text()
        if not output_path or not output_path.lower().endswith(".srt"):
            QMessageBox.warning(
                self, "Peringatan", "Pilih file output dengan ekstensi .srt."
            )
            return
        if Path(input_path).resolve() == Path(output_path).resolve():
            QMessageBox.warning(
                self, "Peringatan", "File output tidak boleh sama dengan file input."
            )
            return
        available_output_path = self.controller.get_available_output_path(output_path)
        if available_output_path != output_path:
            output_path = available_output_path
            self.output_edit.setText(output_path)
            self.log(f"File output sudah ada; hasil baru disimpan ke {output_path}")
        self._cancel_requested = False

        lang_map = {
            "Auto": "auto",
            "Jepang (ja)": "ja",
            "Inggris (en)": "en",
            "Korea (ko)": "ko",
            "Indonesia (id)": "id",
        }
        operation = "translate_srt" if translating else "transcribe"
        language_combo = (
            self.srt_language_combo if operation == "translate_srt" else self.lang_combo
        )
        language = lang_map.get(language_combo.currentText(), "auto")
        target_map = {
            "Indonesia (id)": "id",
            "Inggris (en)": "en",
            "Jepang (ja)": "ja",
            "Korea (ko)": "ko",
        }
        target_language = target_map.get(self.target_language_combo.currentText(), "id")

        backend = "vulkan" if self.backend_combo.currentText() == "Vulkan GPU" else "cpu"

        job = self.controller.create_job(
            input_path=input_path,
            output_path=output_path,
            language=language,
            model=self.model_combo.currentText(),
            backend=backend,
            cpu_fallback=self.cpu_fallback_cb.isChecked(),
            segment_length_minutes=self.seg_spin.value(),
            overlap_seconds=self.overlap_spin.value(),
            operation=operation,
            target_language=target_language,
        )

        self.output_edit.setText(job.output_path)
        self.controller.start_current_job()
        self.log(f"Job dibuat: {job.id}")

    def _cancel_job(self) -> None:
        if self._cancel_requested:
            return
        self._cancel_requested = True
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Menghentikan...")
        self.controller.stop_current_job()
        self.log("Menghentikan proses aktif...")

    def _open_output_folder(self) -> None:
        output_path = Path(self.output_edit.text())
        if output_path.suffix.lower() == ".srt":
            output_dir = output_path.parent
        else:
            output_dir = Path(self.settings.get("output_dir", "output"))
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            opened = QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(output_dir.resolve()))
            )
        except OSError as exc:
            QMessageBox.critical(
                self, "Gagal membuka folder", f"Tidak dapat membuka folder output: {exc}"
            )
            return
        if not opened:
            QMessageBox.warning(
                self,
                "Gagal membuka folder",
                f"Windows tidak dapat membuka folder: {output_dir}",
            )

    def _preview_srt(self) -> None:
        output_path = Path(self.output_edit.text())
        if not output_path.is_file():
            selected_path, _ = QFileDialog.getOpenFileName(
                self,
                "Pilih file SRT untuk preview",
                self._last_browse_directory(),
                "Subtitle SRT (*.srt)",
            )
            if not selected_path:
                return
            self._remember_browse_directory(selected_path)
            output_path = Path(selected_path)

        try:
            content = output_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            QMessageBox.critical(
                self, "Gagal membaca SRT", f"Tidak dapat membuka {output_path}: {exc}"
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Preview SRT - {output_path.name}")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        preview = QPlainTextEdit(dialog)
        preview.setReadOnly(True)
        preview.setPlainText(content)
        layout.addWidget(preview)
        dialog.exec()

    def _last_browse_directory(self) -> str:
        saved_path = self._ui_settings.value("last_browse_directory", "")
        directory = Path(saved_path) if saved_path else Path.home()
        if not directory.is_dir():
            directory = Path.home()
        return str(directory)

    def _remember_browse_directory(self, selected_path: str) -> None:
        directory = Path(selected_path).parent
        if directory.is_dir():
            self._ui_settings.setValue("last_browse_directory", str(directory))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if self.translate_mode_rb.isChecked() and Path(path).suffix.lower() != ".srt":
                QMessageBox.warning(
                    self, "Peringatan", "Mode terjemahan hanya menerima file .srt."
                )
                return
            self.input_edit.setText(path)
            self._set_default_output(path)