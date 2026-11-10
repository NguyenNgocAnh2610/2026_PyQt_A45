import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
from PySide6.QtCore import Qt
from src.ui.login import LoginWindow

from pathlib import Path

def main():
    app = QApplication(sys.argv)

    qss_path = Path(__file__).parent / "assets" / "dark.qss"

    with open(qss_path) as f:
        app.setStyleSheet(f.read())

    login_window = LoginWindow()

    login_window.login_successful.connect(lambda: print("Login successful!"))

    login_window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
