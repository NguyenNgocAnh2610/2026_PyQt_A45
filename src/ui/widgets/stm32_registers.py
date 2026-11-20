"""CPU register banks (DO/DI) of the profile's firmware map; state and requests belong to Backend."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
                               QSpinBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QHeaderView, QGroupBox, QWidget)

from src.protocol import decode_stm32, encode_int16

# Registers whose raw write has side effects beyond a plain output word.
WRITE_WARNINGS = {
    'Mode': '1 = PC điều khiển (AutoComputer); khác 1 = CPU chạy mã HMI và tự bật VDD1–3.',
    'Plan': '0 làm CPU cấu hình lại GPIO mỗi vòng; bộ chạy bài dùng 2.',
    'DataO1': 'Lệnh encoder TỰ XÓA: ghi là phát xung ngay.',
    'DataO2': 'Lệnh encoder TỰ XÓA: ghi là phát xung ngay.',
    'DataO3': 'SSI: dùng lại chân UART.',
    'CDT': 'bit8 = phát chuỗi UART lặp mỗi vòng; CPUv1.1 bit9 = đổi baud.',
    'MUX': 'Byte thấp = kênh MUX1, byte cao = MUX2; kênh ≥ 32 bị phần mềm chặn.',
    'Matrix0': 'Bo matrix ID 6, rơ-le RL1–RL16 (bit k → RL k+1).',
    'Matrix1': 'Bo matrix ID 6, rơ-le RL17–RL32.',
}


class Stm32RegistersPanel(QWidget):
    """Raw DO/DI view of one CPU; every send is explicit, never periodic writes."""

    def __init__(self, backend, parent=None, slave=None):
        super().__init__(parent)
        self.backend = backend
        self.cpu_map = backend.cpu_map
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.simulation = QCheckBox('Giả lập (COM ảo, không mở COM thật)')
        self.simulation.setChecked(True)
        self.slave = QSpinBox()
        self.slave.setRange(1, 247)
        self.slave.setValue(slave if slave is not None else backend.tool['slave'])
        if backend.device.io_map is not None:
            # PC talks only to the CPU; sub-boards are reached through its registers.
            cpu = backend.device.io_map.slave
            self.slave.setRange(cpu, cpu)
            self.slave.setReadOnly(True)
            self.slave.setButtonSymbols(QSpinBox.NoButtons)
            self.slave.setToolTip(f'CPU slave {cpu} (hardware.json → stm32_io.slave). Bo con nằm sau CPU.')
        last = self.cpu_map.read_count - 1
        self.read_button = QPushButton(f'Đọc DI 1–{last} · FC03')
        self.read_button.clicked.connect(lambda: self._request(False))
        self.poll = QCheckBox('Tự đọc mỗi')
        self.poll_ms = QSpinBox()
        self.poll_ms.setRange(200, 10000)
        self.poll_ms.setSingleStep(100)
        self.poll_ms.setValue(500)
        self.poll_ms.setSuffix(' ms')
        self._queued_write = False  # Write clicked during a background read.
        controls.addWidget(self.simulation)
        controls.addWidget(QLabel('CPU slave'))
        controls.addWidget(self.slave)
        controls.addWidget(QLabel(f'Bản đồ {self.cpu_map.name}'))
        controls.addStretch()
        controls.addWidget(self.poll)
        controls.addWidget(self.poll_ms)
        controls.addWidget(self.read_button)
        layout.addLayout(controls)
        hint = QLabel('DO: giá trị PC chuẩn bị gửi. DI: dữ liệu mạch trả về. Cùng địa chỉ nhưng khác vùng nhớ. '
                      'ACK chỉ xác nhận CPU đã nhận lệnh; không tự retry, không gửi định kỳ mảng ghi. '
                      'Rê chuột lên tên thanh ghi để xem lưu ý.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        tables = QHBoxLayout()
        self.tx = self._table(self.cpu_map.write_names, ['Địa chỉ', 'Modbus_DO', 'Giá trị gửi'], True)
        self.rx = self._table(self.cpu_map.read_names, ['Địa chỉ', 'Modbus_DI', 'Raw', 'Giải mã'], False)
        for title, table in ((f'PC → CPU · mod_buf_to_write[{self.cpu_map.write_count}]', self.tx),
                              (f'CPU → PC · mod_buf_to_read[{self.cpu_map.read_count}]', self.rx)):
            group = QGroupBox(title)
            box = QVBoxLayout(group)
            box.addWidget(table)
            tables.addWidget(group)
        layout.addLayout(tables, 1)
        self.tx.itemChanged.connect(self._stage)
        send = QHBoxLayout()
        self.address = QSpinBox()
        self.address.setRange(1, self.cpu_map.write_count - 1)
        self.count = QSpinBox()
        self.count.setRange(1, self.cpu_map.write_count - 1)
        self.address.valueChanged.connect(lambda value: self.count.setMaximum(self.cpu_map.write_count - value))
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
        self.frames_label = QLabel()
        self.frames_label.setWordWrap(True)
        self.frames_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.frames_label.setToolTip('Khung dựng lại từ PDU, CRC16 tính lại; dùng để đối chiếu với máy dò Modbus.')
        layout.addWidget(self.frames_label)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self.poll.toggled.connect(self._poll_changed)
        self.poll_ms.valueChanged.connect(self._poll_changed)
        self.simulation.toggled.connect(self._source_changed)
        self.slave.valueChanged.connect(self._source_changed)
        backend.stm32_changed.connect(self.refresh)
        backend.changed.connect(self.refresh)
        self._source_changed()

    def _table(self, names, headers, writable):
        table = QTableWidget(len(names), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        for index, name in enumerate(names):
            for column in range(len(headers)):
                text = (f'{index:02} / {index:04X}', name, '', '')[column]
                item = QTableWidgetItem(text)
                if not (writable and index and column == 2):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                elif column == 2:
                    item.setToolTip('Nhập thập phân hoặc 0xHEX; riêng DAC_val nhận cả số âm int16.')
                if writable and column == 1 and name in WRITE_WARNINGS:
                    item.setToolTip(WRITE_WARNINGS[name])
                table.setItem(index, column, item)
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
            if self.cpu_map.write_names[item.row()] == 'DAC_val' and value < 0:
                value = encode_int16(value)
            self.backend.stage_stm32(item.row(), [value])
        except ValueError as exc:
            # An invalid edit must not silently send the previous valid value.
            self.backend.unstage_stm32(item.row())
            self.status.setText(str(exc))

    def _request(self, writing):
        b = self.backend
        if b.stm32_background and not b.stm32_foreground_busy:
            if writing:
                self._queued_write = True  # Sent as soon as the auto-read returns.
                self.status.setText('Đang đọc nền; lệnh ghi sẽ gửi ngay sau.')
            return  # A plain read: the background read delivers anyway.
        try:
            self.backend.request_stm32(simulation=self.simulation.isChecked(), slave=self.slave.value(),
                                       address=self.address.value() if writing else None,
                                       count=self.count.value())
        except ValueError as exc:
            self.status.setText(str(exc))

    def _poll_changed(self, *_):
        if self.poll.isChecked():
            self._timer.start(self.poll_ms.value())
        else:
            self._timer.stop()

    def _poll(self):
        b = self.backend
        if not self.isVisible() or b.busy or b.serial_read_pending or b.tool_busy or b.closed:
            return  # Reads only; skipped while anything else is on the bus.
        try:
            b.request_stm32(simulation=self.simulation.isChecked(), slave=self.slave.value(), background=True)
        except ValueError as exc:
            self.poll.setChecked(False)
            self.status.setText(f'Dừng tự đọc: {exc}')

    def hideEvent(self, event):
        self.poll.setChecked(False)
        super().hideEvent(event)

    def refresh(self):
        state = self.backend.stm32
        busy = self.backend.stm32_foreground_busy  # Background auto-reads do not grey the panel.
        for control in (self.simulation, self.slave, self.read_button, self.write_button):
            if control.isEnabled() != (not busy):
                control.setEnabled(not busy)
        if self._queued_write and not self.backend.serial_read_pending and not busy:
            self._queued_write = False
            QTimer.singleShot(0, self, lambda: self._request(True))
        valid = state.read_valid and state.source == (self.simulation.isChecked(), self.slave.value())
        source = 'GIẢ LẬP' if self.simulation.isChecked() else 'THIẾT BỊ THẬT'
        validity = 'đã nhận phản hồi gần đây' if valid else 'chưa có dữ liệu / hết hạn'
        ack = state.last_ack
        receipt = '' if ack is None else f" ACK: địa chỉ {ack['address']}, giá trị {ack['values']}."
        self.status.setText(f'{source} · DI {validity}. {state.message}{receipt}')
        frames = state.frames.get(self.simulation.isChecked(), {})
        port = 'COM ảo' if self.simulation.isChecked() else 'COM thật'
        lines = [f"{d} {frames[d].hex(' ').upper()}" for d in ('TX', 'RX') if d in frames]
        self.frames_label.setText(f'Khung RTU gần nhất ({port}):\n' + '\n'.join(lines) if lines
                                  else f'Chưa có khung RTU ({port}).')
        self.tx.blockSignals(True)
        for row in range(self.tx.rowCount()):
            if row in state.staged:
                self.tx.item(row, 2).setText(str(state.mod_buf_to_write[row]))
        self.tx.blockSignals(False)
        decoded = decode_stm32(state.mod_buf_to_read, self.cpu_map) if valid else None
        for row in range(self.rx.rowCount()):
            self.rx.item(row, 2).setText(str(state.mod_buf_to_read[row]) if valid and row else '—')
            self.rx.item(row, 3).setText(decode_cell(row, state.mod_buf_to_read, decoded) if decoded else '')
        received = ' · '.join(f'{name}: {data.hex(" ").upper()}' for name, data in decoded['received'].items()) \
            if decoded else '—'
        self.bytes_label.setText('Bộ đệm UART nhận (low byte trước; chưa biết độ dài hợp lệ): ' + received)


def decode_cell(row, words, decoded):
    """Human meaning of DI index ``row`` (indices 1–19 are common to all maps)."""
    if 7 <= row <= 11:
        return f"{decoded['adc_volts'][row - 7]:.2f} V"
    if row == 12:
        value = decoded['resistance_ohms']
        return 'Quá thang / hở' if value is None else f'{value:g} Ω'
    if row == 13:
        return f'{words[row] & 1023:010b} (b9…b0)'
    if row in (14, 17):
        return str(decoded['encoder_count' if row == 14 else 'encoder_num_pulse'])
    if row == 1:
        return 'Firmware hiện giữ 0'
    return ''


class Stm32RegistersDialog(QDialog):
    """Stand-alone window around the panel (kept for the connection dialog)."""

    def __init__(self, backend, parent=None, slave=None):
        super().__init__(parent)
        self.setWindowTitle(f'STM32 USART2 · Hai mảng Modbus RTU · {backend.cpu_map.name}')
        self.resize(1060, 760)
        layout = QVBoxLayout(self)
        self.panel = Stm32RegistersPanel(backend, self, slave)
        layout.addWidget(self.panel)
        close = QPushButton('Đóng')
        close.clicked.connect(self.close)
        layout.addWidget(close)
        for name in ('simulation', 'slave', 'read_button', 'write_button', 'address', 'count', 'tx', 'rx',
                     'status', 'bytes_label', 'frames_label'):
            setattr(self, name, getattr(self.panel, name))

    def refresh(self):
        self.panel.refresh()
