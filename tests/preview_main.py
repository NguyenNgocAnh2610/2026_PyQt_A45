"""Standalone main window preview: python -m tests.preview_main."""
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.common.config import ASSETS_DIR
from src.common.styles import apply_theme
from src.ui.main_window import MainWindow


def create_preview(assets_dir: Path = ASSETS_DIR) -> MainWindow:
    """Match the gallery factory signature; use demo data only."""
    return MainWindow("admin (demo)")


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    window = create_preview()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
