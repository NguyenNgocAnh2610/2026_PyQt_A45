"""Operator entry for values measured outside the bench (e.g. oscilloscope)."""
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout


def _number(text):
    text = text.strip().replace(',', '.')
    if not text:
        return None
    value = float(text)  # ValueError for non-numbers.
    if not math.isfinite(value):
        raise ValueError(text)
    return value


class ManualInputDialog(QDialog):
    """One field per requested signal. Empty = record the nominal value,
    labelled "mặc định, chưa đo" by the backend; closing the dialog does the
    same. The dialog never decides PASS/FAIL."""
    submitted = Signal(str, object)  # token, {signal: float | None}

    def __init__(self, request, parent=None):
        super().__init__(parent)
        self.setObjectName('manualInput')
        self.token = request['token']
        self.setWindowTitle(f"Nhập số đo · {request['test_id']} / {request['step_id']}")
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_DeleteOnClose)
        layout = QVBoxLayout(self)
        title = QLabel(request['title'])
        title.setWordWrap(True)
        layout.addWidget(title)
        hint = QLabel('Đo trên thiết bị ngoài (oxilo) rồi nhập. Để trống: ghi giá trị chuẩn, '
                      'kết quả ghi rõ "mặc định, chưa đo".')
        hint.setWordWrap(True)
        hint.setProperty('role', 'hint')
        layout.addWidget(hint)
        form = QFormLayout()
        self.fields = {}
        for field in request['fields']:
            edit = QLineEdit()
            limit = '' if field['tolerance'] is None else f" ± {field['tolerance']:g}"
            edit.setPlaceholderText(f"Chuẩn {field['nominal']:g}{limit} {field['unit']}".strip())
            edit.setToolTip(field.get('prompt') or field['label'])
            form.addRow(f"{field['label']} ({field['unit']})" if field['unit'] else field['label'], edit)
            self.fields[field['signal']] = edit
        layout.addLayout(form)
        self.error = QLabel('')
        self.error.setProperty('role', 'error')
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        skip = QPushButton('Bỏ qua (dùng giá trị chuẩn)')
        skip.clicked.connect(self._skip)
        ok = QPushButton('Ghi nhận')
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        buttons.addStretch(1)
        buttons.addWidget(skip)
        buttons.addWidget(ok)
        layout.addLayout(buttons)
        self._sent = False

    def _send(self, values):
        if not self._sent:
            self._sent = True
            self.submitted.emit(self.token, values)

    def _accept(self):
        values = {}
        for sid, edit in self.fields.items():
            try:
                values[sid] = _number(edit.text())
            except ValueError:
                self.error.setText(f'Giá trị "{edit.text()}" không phải số.')
                edit.setFocus()
                return
        self._send(values)
        self.accept()

    def _skip(self):
        self._send({})
        self.reject()

    def withdraw(self):
        """The backend no longer waits (stop/pause/error): close silently."""
        self._sent = True
        self.reject()

    def reject(self):
        self._send({})  # Closing the window = leave every field empty.
        super().reject()
