"""Inspect shared theme: python -m tests.preview_widgets [--capture directory]."""
import argparse
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSpinBox, QCheckBox, QRadioButton, QProgressBar,
    QSlider, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
)

from src.common.styles import apply_theme
from src.ui.main_window import MainWindow
from src.ui.widgets.login_page import LoginPage


def create_gallery() -> QWidget:
    page = QWidget()
    page.setWindowTitle("A45 — Shared Widgets theme")
    page.setObjectName("gallery")
    page.setStyleSheet("QWidget#gallery { background: #0b1220; }")
    page.resize(1000, 760)
    layout = QVBoxLayout(page)
    layout.setContentsMargins(32, 28, 32, 28)
    layout.setSpacing(16)
    title = QLabel("Bộ giao diện A45")
    title.setProperty("role", "title")
    layout.addWidget(title)
    layout.addWidget(QLabel("Điều khiển nhất quán · Navy / Cyan · Qt Widgets"))
    buttons = QHBoxLayout()
    for text, variant in [("Bắt đầu đo", "primary"), ("Lưu kết quả", ""), ("Dừng", "danger"), ("Chi tiết", "text"), ("Chưa sẵn sàng", "")]:
        button = QPushButton(text)
        button.setProperty("variant", variant)
        button.setEnabled(text != "Chưa sẵn sàng")
        buttons.addWidget(button)
    layout.addLayout(buttons)
    fields = QHBoxLayout()
    edit = QLineEdit()
    edit.setPlaceholderText("Tên chu trình đo...")
    fields.addWidget(edit)
    combo = QComboBox()
    combo.addItems(["Chọn thiết bị", "Thiết bị A45 (demo)"])
    fields.addWidget(combo)
    spin = QSpinBox()
    spin.setRange(0, 10000)
    spin.setValue(250)
    spin.setSuffix(" ms")
    fields.addWidget(spin)
    layout.addLayout(fields)
    choices = QHBoxLayout()
    check = QCheckBox("Ghi dữ liệu")
    check.setChecked(True)
    choices.addWidget(check)
    radio = QRadioButton("Chế độ mô phỏng")
    radio.setChecked(True)
    choices.addWidget(radio)
    for state, text in [("success", "Đạt"), ("warning", "Đang chờ"), ("error", "Lỗi kết nối")]:
        label = QLabel(text)
        label.setProperty("state", state)
        choices.addWidget(label)
    layout.addLayout(choices)
    tabs = QTabWidget()
    table = QTableWidget(4, 3)
    table.setHorizontalHeaderLabels(["Thông số", "Giá trị mô phỏng", "Đơn vị"])
    table.setAlternatingRowColors(True)
    for row, values in enumerate([("Điện áp", "24.0", "V"), ("Dòng điện", "1.25", "A"), ("Nhiệt độ", "32.5", "°C"), ("Tần số", "50.0", "Hz")]):
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(value))
    table.horizontalHeader().setStretchLastSection(True)
    table.setColumnWidth(0, 260)
    table.setColumnWidth(1, 260)
    tabs.addTab(table, "Dữ liệu mô phỏng")
    tabs.addTab(QTextEdit("Nhật ký preview — không kết nối phần cứng."), "Nhật ký")
    layout.addWidget(tabs)
    progress = QProgressBar()
    progress.setValue(68)
    layout.addWidget(progress)
    slider = QSlider(Qt.Horizontal)
    slider.setValue(45)
    layout.addWidget(slider)
    return page


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path)
    args = parser.parse_args()
    app = QApplication(sys.argv)
    apply_theme(app)
    gallery = create_gallery()
    if args.capture:
        args.capture.mkdir(parents=True, exist_ok=True)
        pages = {"widgets": gallery, "login": LoginPage(lambda *_: False), "main": MainWindow("admin")}
        for name, page in pages.items():
            page.show()
            app.processEvents()
            if not page.grab().save(str(args.capture / f"{name}.png")):
                raise RuntimeError(f"Could not capture {name}")
            if name == "login":
                page.resize(900, 560)
                app.processEvents()
                page.grab().save(str(args.capture / "login_minimum.png"))
            page.close()
        return 0
    gallery.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
