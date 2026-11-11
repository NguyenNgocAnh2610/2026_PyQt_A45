"""Reusable login page for Hybrid Testbench (PySide6).

Standalone widget. Authentication is injected through `authenticate` callback.
Never put real production passwords directly into this UI module.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QLinearGradient
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from src.common.config import APP_NAME, APP_VERSION, ASSETS_DIR
from src.common.styles import apply_page_style, set_state


class BrandPanel(QWidget):
    """Paints a responsive visual panel; supports optional custom background image."""

    def __init__(self, background_path: Path | None = None, parent=None):
        super().__init__(parent)
        self.background_path = background_path
        self.setMinimumWidth(380)
        self.setObjectName("brandPanel")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 44, 44, 40)
        layout.setSpacing(10)

        mark = QLabel("◈  HYBRID TESTBENCH")
        mark.setObjectName("brandMark")
        layout.addWidget(mark)
        layout.addStretch(2)

        eyebrow = QLabel("HARDWARE TESTING PLATFORM")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)

        headline = QLabel("ĐO KIỂM THÔNG MINH\nVẬN HÀNH CHÍNH XÁC")
        headline.setObjectName("brandHeadline")
        headline.setWordWrap(True)
        layout.addWidget(headline)

        sub = QLabel("Quản lý thiết bị • Thu thập dữ liệu • Phân tích kết quả\nMột nền tảng cho toàn bộ quy trình thử nghiệm.")
        sub.setObjectName("brandDescription")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        layout.addSpacing(24)

        for text in ("●   REAL-TIME MONITORING", "●   TEST SEQUENCE CONTROL", "●   DATA LOGGING & REPORTING"):
            item = QLabel(text)
            item.setObjectName("brandFeature")
            layout.addWidget(item)

        layout.addStretch(3)
        foot = QLabel("ENGINEERING WORKSPACE   /   VERSION 1.0.0")
        foot.setObjectName("brandFooter")
        layout.addWidget(foot)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(rect), 20, 20)
        painter.setClipPath(clip)
        grad = QLinearGradient(0, 0, rect.width(), rect.height())
        grad.setColorAt(0, QColor("#101d3a"))
        grad.setColorAt(.52, QColor("#123b71"))
        grad.setColorAt(1, QColor("#0e6c8c"))
        painter.fillRect(rect, grad)

        if self.background_path and self.background_path.is_file():
            pix = QPixmap(str(self.background_path))
            if not pix.isNull():
                scaled = pix.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                painter.drawPixmap((rect.width()-scaled.width())//2,
                                   (rect.height()-scaled.height())//2, scaled)
                painter.fillRect(rect, QColor(4, 13, 35, 165))

        # Subtle circuit-board styling even without an image.
        painter.setPen(QPen(QColor(102, 205, 245, 32), 1.4))
        w, h = rect.width(), rect.height()
        for i in range(9):
            y = int(h * (.18 + i * .09))
            path = QPainterPath()
            path.moveTo(int(w*.53), y)
            path.lineTo(int(w*.73), y)
            path.lineTo(int(w*.82), y - 32)
            path.lineTo(w, y - 32)
            painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(42, 199, 236, 35))
        painter.drawEllipse(int(w*.54), int(h*.10), int(w*.66), int(w*.55))
        painter.end()


class LoginPage(QWidget):
    """Login form that emits `login_success(username)` after successful auth."""

    login_success = Signal(str)

    def __init__(
        self,
        authenticate: Callable[[str, str], bool],
        assets_dir: str | Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.authenticate = authenticate
        self.assets_dir = Path(assets_dir) if assets_dir else ASSETS_DIR
        self.setObjectName("loginRoot")
        self.setWindowTitle(f"{APP_NAME} | Đăng nhập")
        self.resize(1180, 720)
        self.setMinimumSize(900, 560)
        self._build_ui()
        self._load_styles()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(0)

        background = self.assets_dir / "images" / "login_background.jpg"
        self.brand = BrandPanel(background)
        self.brand.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer.addWidget(self.brand, 57)

        self.form_panel = QFrame()
        self.form_panel.setObjectName("formPanel")
        self.form_panel.setMinimumWidth(400)
        outer.addWidget(self.form_panel, 43)

        wrapper = QVBoxLayout(self.form_panel)
        wrapper.setContentsMargins(55, 35, 55, 35)
        wrapper.addStretch(1)

        logo = QLabel()
        logo.setObjectName("logoLabel")
        logo_file = self.assets_dir / "images" / "logo.png"
        if logo_file.is_file():
            pix = QPixmap(str(logo_file))
            if not pix.isNull():
                logo.setPixmap(pix.scaled(74, 74, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                logo.setText("◈")
        else:
            logo.setText("◈")
        wrapper.addWidget(logo)
        wrapper.addSpacing(14)

        title = QLabel("Chào mừng trở lại")
        title.setObjectName("loginTitle")
        wrapper.addWidget(title)

        description = QLabel("Đăng nhập để tiếp tục sử dụng hệ thống giá thử.")
        description.setObjectName("loginSubtitle")
        description.setWordWrap(True)
        wrapper.addWidget(description)
        wrapper.addSpacing(25)

        user_label = QLabel("TÊN ĐĂNG NHẬP")
        user_label.setObjectName("fieldLabel")
        wrapper.addWidget(user_label)
        self.username_edit = QLineEdit()
        self.username_edit.setObjectName("loginInput")
        self.username_edit.setPlaceholderText("Nhập tên đăng nhập")
        self.username_edit.setClearButtonEnabled(True)
        wrapper.addWidget(self.username_edit)
        wrapper.addSpacing(14)

        pass_label = QLabel("MẬT KHẨU")
        pass_label.setObjectName("fieldLabel")
        wrapper.addWidget(pass_label)
        self.password_edit = QLineEdit()
        self.password_edit.setObjectName("loginInput")
        self.password_edit.setPlaceholderText("Nhập mật khẩu")
        self.password_edit.setEchoMode(QLineEdit.Password)
        wrapper.addWidget(self.password_edit)

        options = QHBoxLayout()
        self.remember = QCheckBox("Ghi nhớ tên đăng nhập")
        self.remember.setObjectName("rememberCheck")
        options.addWidget(self.remember)
        options.addStretch()
        self.toggle_password = QPushButton("Hiện")
        self.toggle_password.setObjectName("textButton")
        self.toggle_password.setProperty("variant", "text")
        self.toggle_password.setCursor(Qt.PointingHandCursor)
        self.toggle_password.clicked.connect(self._toggle_password)
        options.addWidget(self.toggle_password)
        wrapper.addLayout(options)
        wrapper.addSpacing(12)

        self.login_button = QPushButton("ĐĂNG NHẬP   →")
        self.login_button.setObjectName("primaryButton")
        self.login_button.setProperty("variant", "primary")
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.clicked.connect(self._try_login)
        wrapper.addWidget(self.login_button)

        self.status_label = QLabel(" ")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        wrapper.addWidget(self.status_label)

        self.password_edit.returnPressed.connect(self._try_login)
        self.username_edit.returnPressed.connect(self.password_edit.setFocus)
        wrapper.addStretch(2)
        footer = QLabel(f"{APP_NAME.upper()}  •  SECURE ACCESS  •  v{APP_VERSION}")
        footer.setObjectName("formFooter")
        footer.setAlignment(Qt.AlignCenter)
        wrapper.addWidget(footer)

        self.username_edit.setFocus()

    def _toggle_password(self):
        is_hidden = self.password_edit.echoMode() == QLineEdit.Password
        self.password_edit.setEchoMode(QLineEdit.Normal if is_hidden else QLineEdit.Password)
        self.toggle_password.setText("Ẩn" if is_hidden else "Hiện")

    def _try_login(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or not password:
            self._show_error("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.")
            return
        try:
            allowed = bool(self.authenticate(username, password))
        except Exception:
            # Do not reveal internal auth/database details on the login screen.
            self._show_error("Không thể xác thực. Vui lòng kiểm tra dịch vụ đăng nhập.")
            return
        if not allowed:
            self.password_edit.clear()
            self._show_error("Tên đăng nhập hoặc mật khẩu không chính xác.")
            self.password_edit.setFocus()
            return
        set_state(self.status_label, "success")
        self.status_label.setText("Đăng nhập thành công.")
        self.login_success.emit(username)

    def _show_error(self, message):
        set_state(self.status_label, "error")
        self.status_label.setText(message)

    def _load_styles(self):
        apply_page_style(self, "login", self.assets_dir)
