"""Connection controls; discovery/connection requests go through the backend."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QComboBox, QPushButton, QListView, QSizePolicy,
    QDialog, QVBoxLayout, QFormLayout, QSpinBox, QLineEdit, QPlainTextEdit, QGroupBox,
    QScrollArea, QWidget,
)

from src.common.config import ASSETS_DIR, SERIAL_BAUDRATES
from src.common.serial import SerialSettings, SERIAL_PARITY



def _cpu_io(backend):
    """The stm32 io map (CPU slave) of the profile, or None (mock adapter / test doubles)."""
    return getattr(getattr(backend, 'device', None), 'io_map', None)

class ConnectionDetails(QDialog):
    """Serial framing and explicit read-only diagnostics; no guessed registers."""

    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar
        self.backend = bar.backend
        self.setObjectName('connectionDetails')
        self.setWindowTitle('Thông số serial và đọc thử Modbus')
        self.resize(620, 680)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName('connectionDetailsContent')
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        hint = QLabel('Mở COM xác nhận máy tính đã mở cổng. Chỉ một phản hồi giao thức hợp lệ '
                      'mới xác nhận giao dịch với slave. Đọc thử (chỉ đọc) dùng địa chỉ do bạn cung cấp, để tìm ID '
                      'của bo CPU khi không có phản hồi. Trên RS485 của PC chỉ có bo CPU; bo con nằm sau CPU nên đọc '
                      'ID bo con sẽ không có phản hồi.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.framing_group = QGroupBox('Thông số đường truyền — chỉnh trước khi kết nối')
        form = QFormLayout(self.framing_group)
        self.bits = QComboBox()
        for value in (5, 6, 7, 8):
            self.bits.addItem(str(value), value)
        self.parity = QComboBox()
        for label, value in SERIAL_PARITY:
            self.parity.addItem(label, value)
        self.stops = QComboBox()
        for value in (1, 2):
            self.stops.addItem(str(value), value)
        self.timeout = QSpinBox()
        self.timeout.setRange(100, 10000)
        self.timeout.setSuffix(' ms')
        serial = self.backend.profile.hardware.get('serial', {})
        for combo, key, default in ((self.bits, 'data_bits', 8), (self.parity, 'parity', 'N'),
                                    (self.stops, 'stop_bits', 1)):
            index = combo.findData(serial.get(key) or default)
            combo.setCurrentIndex(max(0, index))
        self.timeout.setValue(serial.get('timeout_ms') or 1000)
        form.addRow('Data bits (RTU: 8)', self.bits)
        form.addRow('Parity', self.parity)
        form.addRow('Stop bits', self.stops)
        form.addRow('Timeout đọc', self.timeout)
        layout.addWidget(self.framing_group)
        self.read_group = QGroupBox('Đọc thử Modbus RTU — không ghi thanh ghi')
        read_form = QFormLayout(self.read_group)
        self.slave = QSpinBox()
        self.slave.setRange(0, 247)
        self.slave.setSpecialValueText('Chọn ID')
        self.slave.valueChanged.connect(
            lambda value: bar.slave.setCurrentIndex(bar.slave.findData(value or None)))
        self.function = QComboBox()
        self.function.addItem('03 — Holding registers', 3)
        self.function.addItem('04 — Input registers', 4)
        self.address = QLineEdit()
        self.address.setPlaceholderText('Địa chỉ zero-based, 0–65535 (thập phân)')
        self.count = QSpinBox()
        self.count.setRange(1, 125)
        self.read_button = QPushButton('Đọc một lần')
        self.read_button.clicked.connect(self._read)
        controller_group = QGroupBox('STM32 USART2 — Modbus RTU Slave')
        controller_form = QFormLayout(controller_group)
        controller_form.addRow('ID trung tâm / Slave ID', self.slave)
        self.registers_button = QPushButton('Hai mảng STM32 · Giả lập / COM thật')
        self.registers_button.clicked.connect(self._show_stm32)
        self.registers_dialog = None
        controller_form.addRow(self.registers_button)
        layout.addWidget(controller_group)
        read_form.addRow('Function code', self.function)
        read_form.addRow('Địa chỉ bắt đầu', self.address)
        read_form.addRow('Số thanh ghi', self.count)
        read_form.addRow(self.read_button)
        layout.addWidget(self.read_group)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText('Kết quả đọc một lần; không phải dữ liệu đang được cập nhật liên tục.')
        self.output.setMinimumHeight(120)
        layout.addWidget(self.output)
        close = QPushButton('Đóng')
        close.clicked.connect(self.accept)
        outer.addWidget(close)
        self._shown_result = None
        self.backend.changed.connect(self.refresh)

    def options(self):
        return dict(data_bits=self.bits.currentData(), parity=self.parity.currentData(),
                    stop_bits=self.stops.currentData(), timeout_ms=self.timeout.value())

    def _read(self):
        try:
            address = int(self.address.text().strip(), 10)
        except ValueError:
            self.status.setText('Hãy nhập địa chỉ thanh ghi thập phân (zero-based).')
            return
        try:
            self.backend.read_serial_registers(self.slave.value(), self.function.currentData(),
                                               address, self.count.value())
        except ValueError as error:
            self.status.setText(str(error))

    def _show_stm32(self):
        from src.ui.widgets.stm32_registers import Stm32RegistersDialog
        from src.common.stm32 import DEFAULT_SLAVE
        if self.registers_dialog is None:
            self.registers_dialog = Stm32RegistersDialog(self.backend, self,
                                                        slave=self.slave.value() or DEFAULT_SLAVE)
        self.registers_dialog.refresh()
        self.registers_dialog.show()

    def refresh(self):
        backend = self.backend
        active = backend.serial_state in ('connecting', 'open')
        self.framing_group.setEnabled(not active and not backend.busy and not backend.closed)
        rtu = self.bar.adapter.currentData() == 'rtu'
        self.bits.setEnabled(not rtu)
        if rtu:
            self.bits.setCurrentIndex(self.bits.findData(8))
        self.read_group.setEnabled(rtu and backend.serial_state == 'open'
                                   and not backend.serial_read_pending and not backend.closed)
        self.registers_button.setEnabled(not backend.serial_read_pending and not backend.busy and not backend.closed)
        self.slave.setEnabled(not backend.serial_read_pending)
        self.status.setText(backend.serial_detail or backend.connection)
        result = backend.controller_result or backend.serial_result
        if result is not self._shown_result:
            self._shown_result = result
            self.output.clear()
            if result:
                from datetime import datetime
                if 'sample_seq' in result:
                    lines = [f"A45 snapshot #{result['sample_seq']} · boot {result['boot_id']} · {result['source']}",
                             'Ảnh chụp một lần; mẫu sẽ hết hạn nếu không đọc lại.']
                    lines.extend(f"{sid}: {value:g} [{result['qualities'][sid]}]"
                                 for sid, value in result['values'].items())
                else:
                    lines = [f"Phản hồi lúc {datetime.now():%H:%M:%S} · Slave {result['slave']} · FC{result['function']:02}",
                             'Ảnh chụp một lần; không xác nhận trạng thái hiện thời sau lần đọc này.']
                    lines.extend(f"{result['address'] + index}: {value} (0x{value:04X})"
                                 for index, value in enumerate(result['values']))
                self.output.setPlainText('\n'.join(lines))
        if self.bar.adapter.currentData() == 'uart' and result is None:
            self.output.setPlainText(backend.uart_last_hex)
        elif result is None:
            self.output.clear()


class ConnectionBar(QFrame):
    mode_changed = Signal()
    notice = Signal(str, str)

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.setObjectName('connectionBar')
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 9, 18, 9)
        row.setSpacing(8)
        title = QLabel('KẾT NỐI')
        title.setObjectName('connectionTitle')
        row.addWidget(title)
        self.adapter = QComboBox()
        self.adapter.addItem('Mô phỏng', 'mock')
        self.adapter.addItem('Modbus RTU', 'rtu')
        self.adapter.addItem('UART', 'uart')
        self.adapter.setAccessibleName('Loại kết nối')
        row.addWidget(self.adapter)
        row.addWidget(QLabel('COM'))
        self.port = QComboBox()
        self.port.setMinimumWidth(140)
        self.port.setAccessibleName('Cổng COM')
        row.addWidget(self.port)
        self.rescan = QPushButton()
        self.rescan.setIcon(QIcon(str(ASSETS_DIR / 'images' / 'icons' / 'refresh.svg')))
        self.rescan.setFixedWidth(34)
        self.rescan.setAccessibleName('Làm mới cổng COM')
        self.rescan.setToolTip('Làm mới danh sách cổng COM')
        self.rescan.clicked.connect(self.refresh_ports)
        row.addWidget(self.rescan)
        row.addWidget(QLabel('Baud'))
        self.baud = QComboBox()
        self.baud.setMinimumWidth(140)
        self.baud.addItem('Chọn baud', None)
        for value in SERIAL_BAUDRATES:
            self.baud.addItem(str(value), value)
        self.baud.setAccessibleName('Baudrate')
        row.addWidget(self.baud)
        self.slave_label = QLabel('ID CPU' if _cpu_io(backend) is not None else 'ID')
        row.addWidget(self.slave_label)
        self.slave = QComboBox()
        self.slave.addItem('—', None)
        for value in range(1, 248):
            self.slave.addItem(str(value), value)
        self.slave.setAccessibleName('Địa chỉ thiết bị Modbus')
        row.addWidget(self.slave)
        self.details = ConnectionDetails(self)
        self.details_button = QPushButton()
        self.details_button.setToolTip('Data bits, parity, stop bits, timeout và đọc thử thanh ghi')
        self.details_button.clicked.connect(self._show_details)
        for combo in (self.details.bits, self.details.parity, self.details.stops):
            combo.currentIndexChanged.connect(self._framing_changed)
        row.addWidget(self.details_button)
        self.toggle = QPushButton('Kết nối')
        self.toggle.setObjectName('connectDevice')
        self.toggle.clicked.connect(self._toggle)
        row.addWidget(self.toggle)
        row.addStretch()
        self.status = QLabel()
        self.status.setMinimumWidth(110)
        self.status.setMaximumWidth(150)
        self.status.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.status.setObjectName('connectionStatus')
        row.addWidget(self.status)
        for combo in (self.adapter, self.port, self.baud, self.slave):
            combo.setView(QListView())
            combo.setMaxVisibleItems(8)
            combo.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(4)
        self.slave.setMinimumContentsLength(2)
        # Include row padding in popup height so the final choice is not clipped.
        self.adapter.view().setMinimumHeight(3 * 36 + 8)
        self.baud.view().setMinimumHeight(8 * 36 + 8)
        self.slave.view().setMinimumHeight(6 * 36 + 8)
        self.adapter.setMinimumWidth(150)
        serial = backend.profile.hardware.get('serial', {})
        self.refresh_ports()
        for combo, key in ((self.baud, 'baudrate'), (self.slave, 'slave')):
            index = combo.findData(serial.get(key))
            combo.setCurrentIndex(max(0, index))
        self.adapter.currentIndexChanged.connect(self._change_mode)
        backend.changed.connect(self.refresh)
        self.refresh()

    @property
    def simulation_selected(self):
        return self.adapter.currentData() == 'mock'

    def refresh_ports(self):
        previous = self.port.currentData() or self.backend.profile.hardware.get('serial', {}).get('port')
        self.port.clear()
        try:
            ports = self.backend.available_serial_ports()
        except Exception as error:
            self.port.addItem('Lỗi tìm cổng', None)
            self.port.setToolTip(str(error))
            self.notice.emit('Không đọc được danh sách COM', str(error))
            return
        self.port.setToolTip('Chỉ liệt kê cổng; không tự mở hoặc gửi dữ liệu.')
        self.port.addItem('Chọn COM' if ports else 'Không có', None)
        if not ports:
            self.port.setToolTip('Không tìm thấy cổng COM. Kết nối thiết bị rồi làm mới danh sách.')
        for name, description in ports:
            self.port.addItem(name, name)
            self.port.setItemData(self.port.count() - 1, description, Qt.ToolTipRole)
        self.port.view().setMinimumHeight(min(self.port.count(), 6) * 36 + 8)
        self.port.setCurrentIndex(max(0, self.port.findData(previous)))

    def _change_mode(self):
        # Never label a live mock connection as an RTU connection.
        if self.backend.connection != 'Chưa kết nối':
            self.backend.disconnect_device()
        self.refresh()
        self.mode_changed.emit()

    def _framing_changed(self):
        options = self.details.options()
        self.details_button.setText(f"{options['data_bits']}{options['parity']}{options['stop_bits']} · Chi tiết")

    def _show_details(self):
        self.details.slave.setValue(self.slave.currentData() or 0)
        self.details.refresh()
        self.details.open()

    def _toggle(self):
        if self.backend.busy or self.backend.closed:
            return
        if self.backend.serial_state in ('connecting', 'open'):
            self.backend.disconnect_device()
            return
        if not self.simulation_selected:
            if self.port.currentData() is None or self.baud.currentData() is None:
                self.notice.emit('Thiếu thông số kết nối', 'Hãy chọn cổng COM và baudrate trước khi kết nối.')
            else:
                try:
                    settings = SerialSettings(self.adapter.currentData(), self.port.currentData(),
                                              self.baud.currentData(), **self.details.options())
                    self.backend.connect_serial(settings)
                except ValueError as error:
                    self.notice.emit('Thông số kết nối không hợp lệ', str(error))
            return
        if self.backend.connection == 'Chưa kết nối':
            self.backend.connect_device()
        else:
            self.backend.disconnect_device()

    def refresh(self):
        idle = not self.backend.busy and not self.backend.closed
        mock = self.simulation_selected
        active = self.backend.serial_state in ('connecting', 'open')
        self.adapter.setEnabled(idle)
        for widget in (self.port, self.baud, self.rescan):
            widget.setEnabled(idle and not active)
        rtu = self.adapter.currentData() == 'rtu'
        self.slave.setVisible(rtu)
        self.slave_label.setVisible(rtu)
        # stm32 profiles: the device is the CPU at the profile's slave ID, fixed.
        cpu = _cpu_io(self.backend)
        self.slave.setEnabled(idle and rtu and cpu is None)
        if cpu is not None and self.slave.currentData() != cpu.slave:
            self.slave.setCurrentIndex(self.slave.findData(cpu.slave))
        self.toggle.setEnabled(idle)
        self.toggle.setText('Ngắt' if active or (mock and self.backend.connection != 'Chưa kết nối') else 'Kết nối')
        status = {'Sẵn sàng · MÔ PHỎNG': 'Đã nối · Demo',
                  'Đang xác minh mô phỏng': 'Đang kết nối…'}.get(self.backend.connection, self.backend.connection)
        if self.backend.connection.startswith('Lỗi'):
            status = 'Lỗi kết nối'
        self.status.setText(status)
        reason = '' if mock else self.backend.serial_detail or 'Mở COM trước; đọc thử trong Chi tiết để xác minh slave.'
        self.toggle.setToolTip(reason)
        self.status.setToolTip(self.backend.connection if mock else reason)
        self.details_button.setEnabled(idle)
        self.details.refresh()
        self._framing_changed()
