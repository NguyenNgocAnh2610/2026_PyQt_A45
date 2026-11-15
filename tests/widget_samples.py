"""Interactive dictionary samples. Only used by the UI preview tools."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QProgressBar, QPushButton, QRadioButton,
    QSlider, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)


# key, title, search aliases, usage; builders below share these stable keys.
SAMPLES = (
    ("buttons", "Nút bấm", "button QPushButton primary danger text",
     'button = QPushButton("Bắt đầu đo")\nbutton.setProperty("variant", "primary")'),
    ("inputs", "Ô nhập liệu", "input QLineEdit QTextEdit password readonly",
     'edit = QLineEdit()\nedit.setPlaceholderText("Tên chu trình đo")\n'
     '# Khi đổi trạng thái lúc chạy:\nset_state(edit, "error")'),
    ("choices", "Checkbox / Radio", "QCheckBox QRadioButton lựa chọn",
     'check = QCheckBox("Ghi dữ liệu")\ncheck.setChecked(True)'),
    ("values", "Combobox / Spinbox", "QComboBox QSpinBox QDoubleSpinBox số",
     'spin = QSpinBox()\nspin.setRange(0, 10000)\nspin.setSuffix(" ms")'),
    ("data", "Bảng / Danh sách / Cây", "QTableWidget QListWidget QTreeWidget table list tree",
     'table = QTableWidget(4, 3)\ntable.setAlternatingRowColors(True)'),
    ("tabs", "Tab", "QTabWidget điều hướng",
     'tabs = QTabWidget()\ntabs.addTab(QWidget(), "Thông số")'),
    ("progress", "Progress / Slider", "QProgressBar QSlider tiến độ",
     'slider.valueChanged.connect(progress.setValue)'),
    ("labels", "Nhãn trạng thái / Card", "QLabel QFrame success warning error title muted",
     'label = QLabel("Đạt")\nset_state(label, "success")\n'
     'card = QFrame()\ncard.setProperty("role", "card")'),
)


def create_sample(key: str) -> QWidget:
    page = QFrame()
    page.setProperty("role", "card")
    page.setMinimumWidth(420)
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    if key == "buttons":
        for text, variant in [("Mặc định", ""), ("Bắt đầu đo", "primary"),
                              ("Dừng", "danger"), ("Chi tiết", "text")]:
            row = QHBoxLayout()
            for enabled in (True, False):
                button = QPushButton(text if enabled else f"{text} — disabled")
                button.setProperty("variant", variant)
                button.setEnabled(enabled)
                row.addWidget(button)
            layout.addLayout(row)
        layout.addWidget(QLabel("Thử hover, nhấn giữ và dùng Tab để kiểm tra focus."))
    elif key == "inputs":
        for state in ("Trống", "Có dữ liệu", "Chỉ đọc", "Disabled", "Lỗi", "Mật khẩu"):
            layout.addWidget(QLabel(state))
            edit = QLineEdit()
            edit.setPlaceholderText("Nhập tên chu trình đo…")
            if state != "Trống":
                edit.setText("Dữ liệu mô phỏng")
            edit.setReadOnly(state == "Chỉ đọc")
            edit.setEnabled(state != "Disabled")
            if state == "Lỗi":
                edit.setProperty("state", "error")
            if state == "Mật khẩu":
                edit.setEchoMode(QLineEdit.Password)
            layout.addWidget(edit)
        layout.addWidget(QTextEdit("Vùng nhập nhiều dòng — dữ liệu mô phỏng."))
    elif key == "choices":
        for text, state in [("Chưa chọn", Qt.Unchecked), ("Đã chọn", Qt.Checked),
                            ("Trung gian", Qt.PartiallyChecked)]:
            check = QCheckBox(text)
            check.setCheckState(state)
            layout.addWidget(check)
        disabled = QCheckBox("Disabled")
        disabled.setChecked(True)
        disabled.setEnabled(False)
        layout.addWidget(disabled)
        for index, text in enumerate(("Chế độ mô phỏng", "Chế độ thủ công", "Disabled")):
            radio = QRadioButton(text)
            radio.setChecked(index == 0)
            radio.setEnabled(index != 2)
            layout.addWidget(radio)
    elif key == "values":
        for enabled in (True, False):
            combo = QComboBox()
            combo.addItems(["Chọn bo mạch (demo)", "Bo mạch A", "Bo mạch B"])
            combo.setEnabled(enabled)
            layout.addWidget(combo)
            spin = QSpinBox()
            spin.setRange(0, 10000)
            spin.setValue(250)
            spin.setSuffix(" ms")
            spin.setEnabled(enabled)
            layout.addWidget(spin)
        decimal = QDoubleSpinBox()
        decimal.setValue(24.0)
        decimal.setSuffix(" V (mô phỏng)")
        layout.addWidget(decimal)
    elif key == "data":
        table = QTableWidget(4, 3)
        table.setMinimumHeight(240)
        table.setHorizontalHeaderLabels(["Thông số", "Giá trị mô phỏng", "Đơn vị"])
        table.setAlternatingRowColors(True)
        for row, values in enumerate((("Điện áp", "24.0", "V"), ("Dòng điện", "1.25", "A"),
                                      ("Nhiệt độ", "32.5", "°C"), ("Tần số", "50.0", "Hz"))):
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.horizontalHeader().setStretchLastSection(True)
        table.selectRow(1)
        layout.addWidget(table)
        items = QListWidget()
        items.addItems(["Chu trình A (demo)", "Chu trình B (demo)"])
        layout.addWidget(items)
        tree = QTreeWidget()
        tree.setHeaderLabels(["Nhóm phép thử"])
        parent = QTreeWidgetItem(tree, ["Bo mạch mô phỏng"])
        QTreeWidgetItem(parent, ["Kiểm tra nguồn"])
        tree.expandAll()
        layout.addWidget(tree)
    elif key == "tabs":
        tabs = QTabWidget()
        tabs.addTab(QTextEdit("Thông số mô phỏng"), "Thông số")
        tabs.addTab(QTextEdit("Nhật ký mô phỏng"), "Nhật ký")
        tabs.addTab(QWidget(), "Disabled")
        tabs.setTabEnabled(2, False)
        layout.addWidget(tabs)
    elif key == "progress":
        progress = QProgressBar()
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.valueChanged.connect(progress.setValue)
        slider.setValue(68)
        layout.addWidget(QLabel("Kéo slider để thay đổi tiến độ mô phỏng."))
        layout.addWidget(progress)
        layout.addWidget(slider)
        disabled = QSlider(Qt.Horizontal)
        disabled.setValue(45)
        disabled.setEnabled(False)
        layout.addWidget(disabled)
    elif key == "labels":
        for role, text in (("title", "Tiêu đề trang"), ("muted", "Thông tin bổ sung")):
            label = QLabel(text)
            label.setProperty("role", role)
            layout.addWidget(label)
        for state, text in (("success", "Đạt"), ("warning", "Đang chờ"), ("error", "Lỗi kết nối")):
            label = QLabel(f"{text} — minh họa màu trạng thái")
            label.setProperty("state", state)
            layout.addWidget(label)
        card = QFrame()
        card.setProperty("role", "card")
        QVBoxLayout(card).addWidget(QLabel("Card chứa nội dung mô phỏng"))
        layout.addWidget(card)
    else:
        raise ValueError(f"Unknown sample: {key}")
    layout.addStretch()
    return page


def create_stylesheet_sample() -> QWidget:
    """Generic samples cannot reproduce page-specific object names/layouts."""
    tabs = QTabWidget()
    for key, title, _, _ in SAMPLES:
        tabs.addTab(create_sample(key), title)
    return tabs
