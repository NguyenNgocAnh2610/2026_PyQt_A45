"""Standalone login preview: python -m tests.preview_login."""
import sys
from PySide6.QtWidgets import QApplication
from src.common.styles import apply_theme
from src.ui.widgets.login_page import LoginPage


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    login = LoginPage(lambda user, password: user == "admin" and password == "123456")
    login.setWindowTitle("A45 — Login preview (DEMO: admin / 123456)")
    login.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
