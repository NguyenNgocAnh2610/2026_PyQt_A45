"""Load the shared Widgets theme once, with page overrides applied locally."""
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

from src.common.config import ASSETS_DIR


def apply_theme(app: QApplication, assets_dir: Path = ASSETS_DIR) -> None:
    app.setStyle("Fusion")
    stylesheet = (assets_dir / "styles" / "common.qss").read_text(encoding="utf-8")
    app.setStyleSheet(stylesheet.replace("@ASSETS@", assets_dir.resolve().as_posix()))


def apply_page_style(widget: QWidget, name: str, assets_dir: Path = ASSETS_DIR) -> None:
    widget.setStyleSheet((assets_dir / "styles" / f"{name}.qss").read_text(encoding="utf-8"))


def set_state(widget: QWidget, state: str) -> None:
    widget.setProperty("state", state)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
