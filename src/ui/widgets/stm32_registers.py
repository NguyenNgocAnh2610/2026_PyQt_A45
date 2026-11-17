"""Two CPUv1.0 register banks; all state and requests belong to Backend."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
                               QSpinBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QHeaderView, QGroupBox)

from src.common.stm32 import WriteRegister, ReadRegister, DEFAULT_SLAVE, WRITE_COUNT, READ_COUNT
from src.protocol import decode_stm32, encode_int16


class Stm32RegistersDialog(QDialog):
    def __init__(self, backend, parent=None, slave=DEFAULT_SLAVE):
        super().__init__(parent)
        self.backend = backend
        self.setWindowTitle('STM32 USART2 · Hai mảng Modbus RTU')
        self.resize(1060, 760)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.simulation = QCheckBox('Giả lập STM32 (không gửi COM)')
        self.simulation.setChecked(True)
        self.slave = QSpinBox()
        self.slave.setRange(1, 247)
        self.slave.setValue(slave)
        self.read_button = QPushButton(f'Đọc DI 1–{READ_COUNT - 1} · FC03')
        self.read_button.clicked.connect(lambda: self._request(False))
        controls.addWidget(self.simulation)
        controls.addWidget(QLabel('Slave ID'))
        controls.addWidget(self.slave)
        controls.addStretch()
        controls.addWidget(self.read_button)
        layout.addLayout(controls)
        hint = QLabel('DO: giá trị PC chuẩn bị gửi. DI: dữ liệu mạch trả về. Cùng địa chỉ nhưng khác vùng nhớ.\n'
                      'Mode = 1 cho phép điều khiển PC. Plan = 0 là SelfTest, không phải giá trị mặc định vô hại. '
                      'ACK chỉ xác nhận nhận lệnh; không tự retry hoặc gửi định kỳ mảng ghi.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        tables = QHBoxLayout()
        self.tx = self._table(WriteRegister, ['Địa chỉ', 'Modbus_DO', 'Giá trị gửi'])
        self.rx = self._table(ReadRegister, ['Địa chỉ', 'Modbus_DI', 'Raw', 'Giải mã'])
        for title, table in ((f'PC → STM32 · mod_buf_to_write[{WRITE_COUNT}]', self.tx),
                              (f'STM32 → PC · mod_buf_to_read[{READ_COUNT}]', self.rx)):
            group = QGroupBox(title)
            box = QVBoxLayout(group)
            box.addWidget(table)
            tables.addWidget(group)
        layout.addLayout(tables, 1)
        self.tx.itemChanged.connect(self._stage)
        send = QHBoxLayout()
        self.address = QSpinBox()
        self.address.setRange(1, WRITE_COUNT - 1)
        self.count = QSpinBox()
        self.count.setRange(1, WRITE_COUNT - 1)
        self.address.valueChanged.connect(lambda value: self.count.setMaximum(WRITE_COUNT - value))
        self.write_button = QPushButton('Gửi vùng đã nhập · FC06/16')
        self.write_button.clicked.connect(lambda: self._request(True))
        send.addWidget(QLabel('Địa chỉ ghi'))
        send.addWidget(self.address)
        send.addWidget(QLabel('Số thanh ghi'))
        send.addWidget(self.count)
        send.addStretch()
        send.addWidget(self.write_button)
        layout.addLayout(send)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.bytes_label = QLabel()
        self.bytes_label.setWordWrap(True)
        self.bytes_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.bytes_label)
        close = QPushButton('Đóng')
        close.clicked.connect(self.close)
        layout.addWidget(close)
        self.simulation.toggled.connect(self._source_changed)
        self.slave.valueChanged.connect(self._source_changed)
        backend.stm32_changed.connect(self.refresh)
        backend.changed.connect(self.refresh)
        self._source_changed()

    def _table(self, registers, headers):
        table = QTableWidget(len(registers), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        for register in registers:
            for column in range(len(headers)):
                text = (f'{register.value:02} / {register.value:04X}', register.name, '', '')[column]
                item = QTableWidgetItem(text)
                if not (registers is WriteRegister and register.value and column == 2):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                elif column == 2:
                    item.setToolTip('Nhập thập phân hoặc 0xHEX; riêng DAC_val nhận cả số âm int16.')
                table.setItem(register.value, column, item)
        return table

    def _source_changed(self, *_):
        try:
            self.backend.select_stm32_source(self.simulation.isChecked(), self.slave.value())
        except ValueError as exc:
            self.status.setText(str(exc))
        self.refresh()

    def _stage(self, item):
        if item.column() != 2 or item.row() == 0:
            return
        try:
            text = item.text().strip()
            value = int(text, 16 if text.lower().startswith('0x') else 10)
            if item.row() == WriteRegister.DAC_val and value < 0:
                value = encode_int16(value)
            self.backend.stage_stm32(item.row(), [value])
        except ValueError as exc:
            # An invalid edit must not silently send the previous valid value.
            self.backend.unstage_stm32(item.row())
            self.status.setText(str(exc))

    def _request(self, writing):
        try:
            self.backend.request_stm32(simulation=self.simulation.isChecked(), slave=self.slave.value(),
                                       address=self.address.value() if writing else None,
                                       count=self.count.value())
        except ValueError as exc:
            self.status.setText(str(exc))

    def refresh(self):
        state = self.backend.stm32
        busy = self.backend.serial_read_pending or self.backend.busy or self.backend.closed
        for control in (self.simulation, self.slave, self.read_button, self.write_button):
            control.setEnabled(not busy)
        valid = state.read_valid and state.source == (self.simulation.isChecked(), self.slave.value())
        source = 'GIẢ LẬP' if self.simulation.isChecked() else 'THIẾT BỊ THẬT'
        validity = 'đã nhận phản hồi gần đây' if valid else 'chưa có dữ liệu / hết hạn'
        ack = state.last_ack
        receipt = '' if ack is None else f" ACK: địa chỉ {ack['address']}, giá trị {ack['values']}."
        self.status.setText(f'{source} · DI {validity}. {state.message}{receipt}')
        self.tx.blockSignals(True)
        for row in range(self.tx.rowCount()):
            if row in state.staged:
                self.tx.item(row, 2).setText(str(state.mod_buf_to_write[row]))
        self.tx.blockSignals(False)
        decoded = decode_stm32(state.mod_buf_to_read) if valid else None
        for row in range(self.rx.rowCount()):
            self.rx.item(row, 2).setText(str(state.mod_buf_to_read[row]) if valid and row else '—')
            meaning = ''
            if decoded:
                if 7 <= row <= 11:
                    meaning = f"{decoded['adc_volts'][row - 7]:.2f} V"
                elif row == 12:
                    value = decoded['resistance_ohms']
                    meaning = 'Quá thang / hở' if value is None else f'{value:g} Ω'
                elif row == 13:
                    meaning = f'{state.mod_buf_to_read[row] & 1023:010b} (b9…b0)'
                elif row in (14, 17):
                    meaning = str(decoded['encoder_count' if row == 14 else 'encoder_num_pulse'])
                elif row == 1:
                    meaning = 'Firmware hiện giữ 0'
            self.rx.item(row, 3).setText(meaning)
        self.bytes_label.setText('DataR (20 byte, chưa biết độ dài hợp lệ): '
                                 + (decoded['received_bytes'].hex(' ').upper() if decoded else '—'))
