"""Load the shared Widgets theme once, with page overrides applied locally."""
from pathlib import Path
import re

from PySide6.QtWidgets import QApplication, QWidget

from src.common.config import ASSETS_DIR


def apply_theme(app: QApplication, assets_dir: Path = ASSETS_DIR) -> None:
    app.setStyle("Fusion")
    stylesheet = (assets_dir / "styles" / "common.qss").read_text(encoding="utf-8")
    app.setStyleSheet(stylesheet.replace("@ASSETS@", assets_dir.resolve().as_posix()))


def apply_page_style(widget: QWidget, name: str, assets_dir: Path = ASSETS_DIR) -> None:
    stylesheet = (assets_dir / "styles" / f"{name}.qss").read_text(encoding="utf-8")
    widget.setStyleSheet(prepare_page_style(widget, stylesheet, assets_dir))


def prepare_page_style(widget: QWidget, stylesheet: str, assets_dir: Path = ASSETS_DIR) -> str:
    """Resolve assets and optional design-canvas px scaling for a page/preview."""
    scale = widget.property("styleScale") or 1.0
    if scale != 1.0:
        stylesheet = re.sub(
            r"(?<![\w./])(-?\d+(?:\.\d+)?)px\b",
            lambda match: f"{round(float(match.group(1)) * scale)}px",
            stylesheet,
        )
    return stylesheet.replace("@ASSETS@", assets_dir.resolve().as_posix())


def set_state(widget: QWidget, state: str) -> None:
    widget.setProperty("state", state)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
