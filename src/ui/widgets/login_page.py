"""Image-backed login with real controls and injected, fast authentication.

Geometry uses the original artwork's 1672 x 941 design coordinates. The fixed
canvas, controls and page QSS share one scale; no hardware or remote I/O here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRect, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from src.common.config import APP_NAME, APP_VERSION, ASSETS_DIR, TESTBENCH_MODEL
from src.common.styles import apply_page_style, set_state


DESIGN_SIZE = QSize(1672, 941)
DEFAULT_WIDTH = 1280
USERNAME_SETTING = "login/username"


class LoginBrandText:
    """Text expected to change when this UI is reused for another testbench."""

    BRAND_TITLE = "HỆ THỐNG GIÁ THỬ"
    BRAND_ACTION = "KIỂM TRA"
    BRAND_SUBJECT = "KHỐI MẠCH"
    BRAND_DESCRIPTION = "Phần mềm giám sát, điều khiển và kiểm tra bo mạch điện tử"
    FEATURES = ("Giám sát trạng thái thiết bị", "Quản lý quy trình kiểm tra",
                "Lưu kết quả và truy xuất dữ liệu")
    LOGIN_DESCRIPTION = "Truy cập vào phần mềm giá thử kiểm tra khối mạch"


class InformationDialog(QDialog):
    """Small Login helper dialog; kept here because it is not an app-wide UI."""

    def __init__(self, title: str, message: str, note: str, icon_name: str,
                 assets_dir: Path, parent=None):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setObjectName("loginInformationDialog")
        self.setWindowTitle(title)
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setProperty("styleScale", 1.0)
        self.setFixedSize(500, 330)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        card = QFrame()
        card.setObjectName("informationCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 12, 30, 140))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        header = QHBoxLayout()
        icon = QLabel()
        icon.setObjectName("informationIcon")
        icon.setFixedSize(52, 52)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(QIcon(str(assets_dir / "images" / "icons" / icon_name)).pixmap(28, 28))
        header.addWidget(icon)
        heading = QVBoxLayout()
        heading.setSpacing(3)
        heading.addWidget(self._text("TRỢ GIÚP ĐĂNG NHẬP", "informationEyebrow"))
        heading.addWidget(self._text(title, "informationTitle"))
        header.addLayout(heading, 1)
        close_button = QPushButton("×")
        close_button.setObjectName("informationClose")
        close_button.setFixedSize(32, 32)
        close_button.setAccessibleName("Đóng")
        close_button.setToolTip("Đóng")
        close_button.clicked.connect(self.reject)
        header.addWidget(close_button, alignment=Qt.AlignTop)
        layout.addLayout(header)
        layout.addWidget(self._text(message, "informationDescription"))
        layout.addWidget(self._text(note, "informationNote"))
        layout.addStretch()

        footer = QHBoxLayout()
        footer.addWidget(self._text(f"Hệ thống giá thử {TESTBENCH_MODEL}  •  v{APP_VERSION}",
                                    "informationFooter"), 1)
        self.accept_button = QPushButton("Đã hiểu")
        self.accept_button.setObjectName("informationAccept")
        self.accept_button.setDefault(True)
        self.accept_button.clicked.connect(self.accept)
        footer.addWidget(self.accept_button)
        layout.addLayout(footer)
        for button in (close_button, self.accept_button):
            button.setCursor(Qt.PointingHandCursor)
        # Reuse login.qss while keeping dialog typography independent of canvas scaling.
        apply_page_style(self, "login", assets_dir)
        self.accept_button.setFocus()

    @staticmethod
    def _text(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        return label


def fitted_canvas_width(available: QSize) -> int:
    """Reserve room for the OS window frame, using Qt logical screen pixels."""
    return max(1, min(DEFAULT_WIDTH, available.width() - 40,
                      int((available.height() - 80) * DESIGN_SIZE.width() / DESIGN_SIZE.height())))


class LoginPage(QWidget):
    login_success = Signal(str)

    def __init__(
        self,
        authenticate: Callable[[str, str], bool],
        assets_dir: str | Path | None = None,
        parent=None,
        *,
        settings: QSettings | None = None,
        canvas_width: int | None = None,
    ):
        super().__init__(parent)
        self.authenticate = authenticate
        self.assets_dir = Path(assets_dir) if assets_dir else ASSETS_DIR
        # Persistence is opt-in: previews/tests never touch application settings.
        self.settings = settings
        self._information_dialog: InformationDialog | None = None
        self.setObjectName("loginRoot")
        self.setWindowTitle(f"{APP_NAME} | Đăng nhập")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
        width = canvas_width if canvas_width is not None else fitted_canvas_width(
            self.screen().availableGeometry().size()
        )
        if width <= 0:
            raise ValueError("canvas_width must be positive")
        self._scale = width / DESIGN_SIZE.width()
        self.setProperty("styleScale", self._scale)
        self.setFixedSize(width, round(DESIGN_SIZE.height() * self._scale))
        background_path = self.assets_dir / "images" / "login.png"
        self._background = QPixmap(str(background_path))
        if self._background.isNull():
            raise FileNotFoundError(f"Không thể đọc ảnh nền Login: {background_path}")
        self._build_ui()
        apply_page_style(self, "login", self.assets_dir)
        if self.settings is not None:
            username = str(self.settings.value(USERNAME_SETTING, ""))
            self.username_edit.setText(username)
            self.remember.setChecked(bool(username))
        self.remember.toggled.connect(self._remember_toggled)
        self.username_edit.setFocus()

    def _place(self, widget: QWidget, rect: tuple[int, int, int, int]) -> None:
        widget.setGeometry(QRect(*(round(value * self._scale) for value in rect)))

    def _label(self, text: str, name: str, rect, *, centered=False) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName(name)
        label.setTextFormat(Qt.PlainText)
        label.setAlignment((Qt.AlignHCenter if centered else Qt.AlignLeft) | Qt.AlignVCenter)
        label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._place(label, rect)
        return label

    def _button(self, text: str, name: str, rect) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName(name)
        button.setCursor(Qt.PointingHandCursor)
        self._place(button, rect)
        return button

    def _build_ui(self) -> None:
        self._label(LoginBrandText.BRAND_TITLE, "brandTitle", (340, 48, 660, 60))
        self._label(LoginBrandText.BRAND_ACTION, "brandTitle", (340, 108, 252, 60))
        self._label(LoginBrandText.BRAND_SUBJECT, "brandAccent", (600, 108, 405, 60))
        self._label(LoginBrandText.BRAND_DESCRIPTION,
                    "brandSubtitle", (340, 165, 670, 30))
        for text, y in zip(LoginBrandText.FEATURES, (242, 328, 414)):
            self._label(text, "brandFeature", (176, y, 296, 54))

        self._label("ĐĂNG NHẬP HỆ THỐNG", "loginTitle", (1067, 208, 538, 46), centered=True)
        self._label(LoginBrandText.LOGIN_DESCRIPTION,
                    "loginSubtitle", (1067, 251, 538, 28), centered=True)

        user_label = self._label("Tên đăng nhập", "fieldLabel", (1096, 318, 480, 32))
        self.username_edit = QLineEdit(self)
        self.username_edit.setObjectName("usernameInput")
        self.username_edit.setPlaceholderText("Nhập tên đăng nhập")
        self.username_edit.setAccessibleName("Tên đăng nhập")
        self.username_edit.setMaxLength(128)
        self._place(self.username_edit, (1095, 356, 482, 56))
        user_label.setBuddy(self.username_edit)

        pass_label = self._label("Mật khẩu", "fieldLabel", (1096, 412, 480, 31))
        self.password_edit = QLineEdit(self)
        self.password_edit.setObjectName("passwordInput")
        self.password_edit.setPlaceholderText("Nhập mật khẩu")
        self.password_edit.setAccessibleName("Mật khẩu")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self._place(self.password_edit, (1095, 444, 482, 56))
        pass_label.setBuddy(self.password_edit)

        self.toggle_password = self._button("", "passwordToggle", (1518, 452, 49, 40))
        self.toggle_password.setCheckable(True)
        self.toggle_password.setIconSize(QSize(round(28 * self._scale), round(28 * self._scale)))
        self.toggle_password.clicked.connect(self._toggle_password)
        self._update_password_button()

        self.remember = QCheckBox("Ghi nhớ đăng nhập", self)
        self.remember.setObjectName("rememberCheck")
        self.remember.setToolTip("Chỉ ghi nhớ tên đăng nhập, không lưu mật khẩu")
        self._place(self.remember, (1096, 533, 290, 32))
        self.forgot_button = self._button("Quên mật khẩu?", "forgotButton", (1400, 532, 178, 32))
        self.forgot_button.clicked.connect(self._forgot_password)
        self.status_label = self._label("", "statusLabel", (1096, 565, 480, 24), centered=True)
        self.status_label.setAccessibleName("Kết quả đăng nhập")

        self.login_button = self._button("ĐĂNG NHẬP", "loginButton", (1095, 590, 483, 68))
        self.login_button.clicked.connect(self._try_login)
        self.support_button = self._button("Hỗ trợ", "supportButton", (1206, 678, 258, 52))
        self.support_button.clicked.connect(self._show_support)

        self.username_edit.returnPressed.connect(self.password_edit.setFocus)
        self.password_edit.returnPressed.connect(self._try_login)
        self.username_edit.textEdited.connect(self._clear_status)
        self.password_edit.textEdited.connect(self._clear_status)
        order = (self.username_edit, self.password_edit, self.toggle_password,
                 self.remember, self.forgot_button, self.login_button, self.support_button)
        for first, second in zip(order, order[1:]):
            self.setTabOrder(first, second)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self._background)

    def _toggle_password(self) -> None:
        self.password_edit.setEchoMode(
            QLineEdit.Normal if self.toggle_password.isChecked() else QLineEdit.Password
        )
        self._update_password_button()

    def _update_password_button(self) -> None:
        visible = self.password_edit.echoMode() == QLineEdit.Normal
        action = "Ẩn mật khẩu" if visible else "Hiện mật khẩu"
        self.toggle_password.setToolTip(action)
        self.toggle_password.setAccessibleName(action)
        icon = "eye.svg" if visible else "eye-off.svg"
        self.toggle_password.setIcon(QIcon(str(self.assets_dir / "images" / "icons" / icon)))

    def _remember_toggled(self, checked: bool) -> None:
        if not checked and self.settings is not None:
            self.settings.remove(USERNAME_SETTING)
            self.settings.sync()

    def _try_login(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or not password:
            self._show_error("Vui lòng nhập tên đăng nhập và mật khẩu.")
            (self.username_edit if not username else self.password_edit).setFocus()
            return
        try:
            allowed = bool(self.authenticate(username, password))
        except Exception:
            self._show_error("Không thể xác thực. Vui lòng thử lại sau.")
            return
        if not allowed:
            self.password_edit.clear()
            self._show_error("Tên đăng nhập hoặc mật khẩu không chính xác.")
            self.password_edit.setFocus()
            return
        if self.settings is not None:
            if self.remember.isChecked():
                self.settings.setValue(USERNAME_SETTING, username)
            else:
                self.settings.remove(USERNAME_SETTING)
            self.settings.sync()
        self.password_edit.clear()
        self.toggle_password.setChecked(False)
        self._toggle_password()
        set_state(self.status_label, "success")
        self.status_label.setText("Đăng nhập thành công.")
        self.login_success.emit(username)

    def _clear_status(self) -> None:
        self.status_label.clear()

    def _show_error(self, message: str) -> None:
        set_state(self.status_label, "error")
        self.status_label.setText(message)

    def _show_information(self, title: str, message: str, note: str, icon_name: str) -> None:
        if self._information_dialog is not None:
            self._information_dialog.raise_()
            self._information_dialog.activateWindow()
            return
        dialog = InformationDialog(title, message, note, icon_name, self.assets_dir, self)
        self._information_dialog = dialog
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.finished.connect(self._information_closed)
        dialog.open()

    def _information_closed(self, _result: int) -> None:
        self._information_dialog = None

    def _forgot_password(self) -> None:
        self._show_information(
            "Quên mật khẩu",
            "Vui lòng liên hệ quản trị viên hệ thống và cung cấp tên đăng nhập, "
            "đơn vị sử dụng để được hỗ trợ cấp lại mật khẩu.",
            "Hiện chưa hỗ trợ đặt lại mật khẩu trực tuyến. Không chia sẻ mật khẩu của bạn.",
            "account-lock.svg",
        )

    def _show_support(self) -> None:
        self._show_information(
            "Hỗ trợ sử dụng",
            "Nhập tên đăng nhập và mật khẩu được cấp, sau đó chọn ĐĂNG NHẬP. "
            "Biểu tượng con mắt dùng để hiện hoặc ẩn mật khẩu; tùy chọn ghi nhớ chỉ lưu tên đăng nhập.",
            "Nếu vẫn không truy cập được, vui lòng liên hệ quản trị viên hệ thống.",
            "help.svg",
        )

    def closeEvent(self, event) -> None:
        if self._information_dialog is not None:
            self._information_dialog.close()
        super().closeEvent(event)
