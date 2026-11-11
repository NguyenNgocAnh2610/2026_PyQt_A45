"""Demo entry point; production authentication is not configured."""
import sys

from PySide6.QtWidgets import QApplication

from src.common.config import APP_NAME, APP_VERSION
from src.common.styles import apply_theme
from src.ui.main_window import MainWindow
from src.ui.widgets.login_page import LoginPage


def demo_authenticate(username: str, password: str) -> bool:
    """Preview only; replace with a backend API for production."""
    return username == "admin" and password == "123456"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    apply_theme(app)
    login = LoginPage(authenticate=demo_authenticate)
    login.setWindowTitle(f"{APP_NAME} | Đăng nhập — DEMO")

    def open_workspace(username: str) -> None:
        app.main_window = MainWindow(username)
        app.main_window.show()
        login.close()

    login.login_success.connect(open_workspace)
    login.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
