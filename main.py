"""Demo entry point; production authentication is not configured."""
import sys
import argparse
from pathlib import Path

from PySide6.QtCore import QObject, QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from src.common.config import APP_NAME, APP_VERSION, SETTINGS_ORGANIZATION
from src.common.styles import apply_theme
from src.common.profiles import load_profile, ProfileError
from src.common.testing import DEFAULT_PROFILE
from src.ui.main_window import MainWindow
from src.ui.widgets.login_page import LoginPage


def demo_authenticate(username: str, password: str) -> bool:
    """Preview only; replace with a backend API for production."""
    return username == "admin" and password == "123456"


class ApplicationFlow(QObject):
    """Own both windows for the lifetime of the login → workspace flow."""

    def __init__(self, app, profile, *, settings=None, storage_dir=None):
        super().__init__(app)
        self.profile = profile
        self.storage_dir = storage_dir
        self.main_window = None
        self.login = LoginPage(authenticate=demo_authenticate, settings=settings)
        self.login.setWindowTitle(f'{self.login.windowTitle()} - DEMO')
        self.login.login_success.connect(self.open_workspace)

    def open_workspace(self, username):
        if self.main_window is None:
            self.main_window = MainWindow(
                username, profile=self.profile, storage_dir=self.storage_dir,
            )
        elif self.main_window.backend.closed:
            return
        # Show the destination before closing the last visible login window.
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        self.login.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Giá thử cấu hình được — phiên bản mô phỏng")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args(argv)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    apply_theme(app)
    try:
        profile = load_profile(args.profile)
    except ProfileError as error:
        QMessageBox.critical(None, "Cấu hình không hợp lệ", str(error))
        return 2
    flow = ApplicationFlow(
        app, profile,
        settings=QSettings(SETTINGS_ORGANIZATION, APP_NAME),
    )
    flow.login.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
