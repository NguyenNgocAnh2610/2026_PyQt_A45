"""Standalone login preview: python -m tests.preview_login."""
import sys
import argparse
from pathlib import Path
from PySide6.QtWidgets import QApplication
from src.common.config import ASSETS_DIR
from src.common.styles import apply_theme
from src.ui.widgets.login_page import LoginPage


def create_preview(assets_dir: Path = ASSETS_DIR, *, canvas_width: int | None = None) -> LoginPage:
    """Build a fresh UI with demo auth; never create an app or open hardware."""
    login = LoginPage(
        lambda user, password: user == "admin" and password == "123456",
        assets_dir=assets_dir,
        canvas_width=canvas_width,
    )
    login.setWindowTitle(f"{login.windowTitle()} — Preview (DEMO: admin / 123456)")
    return login


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, help="Save a PNG and exit")
    parser.add_argument("--width", type=int, help="Explicit fixed canvas width for preview")
    args = parser.parse_args()
    if args.width is not None and args.width <= 0:
        parser.error("--width must be positive")
    app = QApplication(sys.argv)
    apply_theme(app)
    login = create_preview(canvas_width=args.width)
    login.show()
    if args.capture:
        args.capture.parent.mkdir(parents=True, exist_ok=True)
        app.processEvents()
        if not login.grab().save(str(args.capture)):
            raise RuntimeError("Could not capture Login")
        login.close()
        return 0
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
