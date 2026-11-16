"""Dialog pengaturan aplikasi."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QSpinBox, QDialogButtonBox, QGroupBox, QFileDialog
)
from PySide6.QtCore import Qt

from subtitle_app.settings import Settings


class SettingsDialog(QDialog):
    """Dialog pengaturan lanjutan aplikasi."""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Pengaturan")
        self.resize(500, 400)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Path
        path_group = QGroupBox("Path Binary")
        path_layout = QVBoxLayout()

        self.ffmpeg_edit = QComboBox()
        self.ffmpeg_edit.setEditable(True)
        self.ffmpeg_edit.setEditText(self.settings.get("ffmpeg_path", ""))
        btn_ffmpeg = QPushButton("Browse")
        btn_ffmpeg.clicked.connect(lambda: self._browse_file(self.ffmpeg_edit))
        path_layout.addWidget(QLabel("FFmpeg:"))
        path_layout.addWidget(self.ffmpeg_edit)
        path_layout.addWidget(btn_ffmpeg)

        self.whisper_edit = QComboBox()
        self.whisper_edit.setEditable(True)
        self.whisper_edit.setEditText(self.settings.get("whisper_cpp_path", ""))
        btn_whisper = QPushButton("Browse")
        btn_whisper.clicked.connect(lambda: self._browse_file(self.whisper_edit))
        path_layout.addWidget(QLabel("whisper.cpp:"))
        path_layout.addWidget(self.whisper_edit)
        path_layout.addWidget(btn_whisper)

        self.models_edit = QComboBox()
        self.models_edit.setEditable(True)
        self.models_edit.setEditText(self.settings.get("models_dir", ""))
        btn_models = QPushButton("Browse")
        btn_models.clicked.connect(lambda: self._browse_dir(self.models_edit))
        path_layout.addWidget(QLabel("Folder Model:"))
        path_layout.addWidget(self.models_edit)
        path_layout.addWidget(btn_models)

        path_group.setLayout(path_layout)
        layout.addWidget(path_group)

        # Audio
        audio_group = QGroupBox("Pengaturan Audio")
        audio_layout = QVBoxLayout()
        self.sample_spin = QSpinBox()
        self.sample_spin.setRange(8000, 48000)
        self.sample_spin.setValue(self.settings.get("audio_sample_rate", 16000))
        self.sample_spin.setSuffix(" Hz")
        audio_layout.addWidget(QLabel("Sample Rate:"))
        audio_layout.addWidget(self.sample_spin)
        audio_group.setLayout(audio_layout)
        layout.addWidget(audio_group)

        # Segment
        seg_group = QGroupBox("Segmentasi")
        seg_layout = QVBoxLayout()
        self.seg_spin = QSpinBox()
        self.seg_spin.setRange(5, 60)
        self.seg_spin.setValue(self.settings.get("segment_length_minutes", 20))
        self.seg_spin.setSuffix(" menit")
        seg_layout.addWidget(QLabel("Panjang Segmen:"))
        seg_layout.addWidget(self.seg_spin)
        self.overlap_spin = QSpinBox()
        self.overlap_spin.setRange(0, 10)
        self.overlap_spin.setValue(self.settings.get("segment_overlap_seconds", 2))
        self.overlap_spin.setSuffix(" detik overlap")
        seg_layout.addWidget(QLabel("Overlap:"))
        seg_layout.addWidget(self.overlap_spin)
        seg_group.setLayout(seg_layout)
        layout.addWidget(seg_group)

        layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_file(self, combo) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Pilih File")
        if path:
            combo.setEditText(path)

    def _browse_dir(self, combo) -> None:
        path = QFileDialog.getExistingDirectory(self, "Pilih Folder")
        if path:
            combo.setEditText(path)

    def _save(self) -> None:
        self.settings.set("ffmpeg_path", self.ffmpeg_edit.currentText())
        self.settings.set("whisper_cpp_path", self.whisper_edit.currentText())
        self.settings.set("models_dir", self.models_edit.currentText())
        self.settings.set("audio_sample_rate", self.sample_spin.value())
        self.settings.set("segment_length_minutes", self.seg_spin.value())
        self.settings.set("segment_overlap_seconds", self.overlap_spin.value())
        self.accept()