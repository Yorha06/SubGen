"""Titik masuk utama aplikasi SubGen."""

from __future__ import annotations

import sys
import os

# Tambahkan direktori src ke Python path agar paket subtitle_app dapat diimpor
_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from PySide6.QtWidgets import QApplication

from subtitle_app.settings import Settings
from subtitle_app.app_controller import AppController
from subtitle_app.gui.main_window import MainWindow
from subtitle_app.utils.logging_setup import setup_app_logger


def main() -> int:
    logger = setup_app_logger(log_dir="logs")
    logger.info("Memulai SubGen...")

    app = QApplication(sys.argv)
    app.setApplicationName("SubGen")

    settings = Settings(config_path="config/default.yaml")

    controller = AppController(settings)
    window = MainWindow(controller, settings)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())