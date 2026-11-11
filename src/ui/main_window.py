"""Main shell, ready for future device screens."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton

from src.common.config import APP_NAME


class MainWindow(QMainWindow):
    def __init__(self, username: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — A45")
        self.resize(1180, 760)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(40, 32, 40, 32)
        title = QLabel("Không gian làm việc A45")
        title.setProperty("role", "title")
        layout.addWidget(title)
        layout.addWidget(QLabel(f"Xin chào, {username}"))
        info = QLabel("Chưa tích hợp kết nối thiết bị.\nCác trang đo kiểm sẽ được bổ sung theo tính năng.")
        info.setProperty("role", "muted")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch()
        close = QPushButton("Đóng ứng dụng")
        close.clicked.connect(self.close)
        layout.addWidget(close, alignment=Qt.AlignRight)
        self.setCentralWidget(root)
