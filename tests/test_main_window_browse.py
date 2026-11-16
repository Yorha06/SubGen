import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFileDialog

from subtitle_app.app_controller import AppController
from subtitle_app.gui.main_window import MainWindow
from subtitle_app.settings import Settings


class _Controller:
    def set_status_callback(self, callback):
        pass

    def check_environment(self):
        return {
            "ffmpeg_available": True,
            "whisper_available": True,
            "gpu_report": {"effective_backend": "cpu"},
            "models": [],
        }

    def get_available_output_path(self, path):
        return AppController.get_available_output_path(path)


class MainWindowBrowseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_input_browse_remembers_directory_between_windows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_dir = root / "first"
            first_dir.mkdir()
            preferences_path = root / "ui.ini"

            settings = Settings()
            settings.set("output_dir", str(root / "output"))
            first_window = MainWindow(_Controller(), settings)
            first_window._ui_settings = QSettings(
                str(preferences_path), QSettings.Format.IniFormat
            )
            selected_first = first_dir / "video.mp4"
            with patch.object(
                QFileDialog,
                "getOpenFileName",
                return_value=(str(selected_first), ""),
            ) as dialog:
                first_window._browse_input()

            self.assertEqual(dialog.call_args.args[2], str(Path.home()))
            self.assertEqual(
                first_window._last_browse_directory(), str(first_dir)
            )

            second_window = MainWindow(_Controller(), settings)
            second_window._ui_settings = QSettings(
                str(preferences_path), QSettings.Format.IniFormat
            )
            with patch.object(
                QFileDialog, "getOpenFileName", return_value=("", "")
            ) as dialog:
                second_window._browse_input()

            self.assertEqual(dialog.call_args.args[2], str(first_dir))
            first_window.close()
            second_window.close()


if __name__ == "__main__":
    unittest.main()
