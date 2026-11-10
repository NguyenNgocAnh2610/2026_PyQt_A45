from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, Signal

from pathlib import Path

class LoginWindow(QWidget):
    login_successful = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LOGIN")
        self.resize(420, 350)

        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        """ Sets up the user interface for the login window."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(50, 50, 50, 50)

        # LOGO 
        self.logo_label = QLabel("LOGO")
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setObjectName("logo")

        # Ten gia thu
        self.title_label = QLabel("GIÁ THỬ A45 - ĐỀ TÀI 2026")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setObjectName("title")

        self.subtitle_label = QLabel("TRẦN QUỐC CHÍNH - 2026")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setObjectName("subtitle")

        # Nhập tài khoản và mật khẩu
        self.username_label = QLabel("USER NAME:")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username")
        self.username_input.setObjectName("username")

        self.password_label = QLabel("PASSWORD:")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setObjectName("password")

        self.login_button = QPushButton("LOGIN")
        self.login_button.setObjectName("login_button")

        layout.addWidget(self.logo_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        layout.addSpacing(15)
        layout.addWidget(self.username_label)
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)
        layout.addStretch()

    def connect_signals(self):
        """ Connects signals to their respective slots."""
        self.login_button.clicked.connect(self.handle_login)

    def handle_login(self):
        """ Handles the login button click event."""
        username = self.username_input.text()
        password = self.password_input.text()

        if self.validate_login(username, password):
            self.login_successful.emit()
            self.close()
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid username or password.")
    def validate_login(self, username, password):
        """ Validates the provided username and password."""
        # Replace this with your actual validation logic
        return username == "admin" and password == "admin"

if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    qss_path = Path(__file__).parent.parent.parent / "assets" / "dark.qss"

    with open(qss_path) as f:
        app.setStyleSheet(f.read())

    window = LoginWindow()
    window.show()

    sys.exit(app.exec())
