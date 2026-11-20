"""'Test Modbus' page: talk to the CPU, drive the boards behind it, read values.

All requests go through Backend (tool_* / request_stm32); this module owns no
I/O. Signal-level controls use the profile's Stm32IoMap, so the same rules as
the test runner apply (interlocks, HMI bits, one source per pin, MUX bound,
break-before-make).
"""
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
                               QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView)

from src.protocol import decode_stm32, encode_int16
from src.ui.widgets.stm32_registers import Stm32RegistersPanel


def cpu_slave_box(backend):
    """Read-only CPU slave ID (from the profile) for pages that talk Modbus."""
    box = QSpinBox()
    box.setRange(1, 247)
    box.setValue(backend.tool['slave'])
    if backend.device.io_map is not None:
        slave = backend.device.io_map.slave
        box.setRange(slave, slave)
        box.setReadOnly(True)
        box.setButtonSymbols(QSpinBox.NoButtons)
        box.setToolTip(f'Slave ID của bo CPU STM32 = 8 + công tắc ID = {slave} (hardware.json → stm32_io.slave). '
                       'CPU là thiết bị DUY NHẤT nói chuyện với PC; bo con có ID riêng trên bus của CPU, PC không gọi tới.')
    return box


class BoardControlPanel(QWidget):
    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.io = backend.device.io_map
        self.labels = {sid: d['label'] for sid, d in backend.definitions.items()}
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.source = QComboBox()
        self.source.addItem('COM ảo (giả lập)', True)
        self.source.addItem('COM thật (đang mở, Modbus RTU)', False)
        self.slave = cpu_slave_box(backend)
        self.take = QPushButton('Lấy quyền điều khiển (Mode=1)')
        self.take.clicked.connect(self._take)
        self.safe = QPushButton('Về an toàn')
        self.safe.setObjectName('dangerButton')
        self.safe.clicked.connect(lambda: self._call(backend.tool_safe_state))
        self.hmi = QPushButton('Trả về HMI (Mode=0)')
        self.hmi.clicked.connect(self._release)
        for widget in (QLabel('Cổng'), self.source, QLabel('CPU slave'), self.slave):
            top.addWidget(widget)
        top.addStretch()
        for widget in (self.take, self.safe, self.hmi):
            top.addWidget(widget)
        layout.addLayout(top)
        self.route = QLabel(self._route_text())
        self.route.setObjectName('routeHint')
        self.route.setWordWrap(True)
        layout.addWidget(self.route)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status.setMinimumHeight(self.status.fontMetrics().lineSpacing() * 2 + 4)  # No reflow jumps.
        layout.addWidget(self.status)
        body = QHBoxLayout()
        left = QVBoxLayout()
        right = QVBoxLayout()
        body.addLayout(left, 3)
        body.addLayout(right, 2)
        layout.addLayout(body, 1)
        self.controls = []
        if self.io is None:
            layout.addWidget(QLabel('Profile không dùng adapter stm32: chỉ có tab Thanh ghi CPU.'))
            self.refresh()
            return
        left.addWidget(self._power_group())
        left.addWidget(self._matrix_group(), 1)
        right.addWidget(self._mux_group())
        right.addWidget(self._dac_dout_group())
        right.addWidget(self._readings_group(), 1)
        backend.tool_changed.connect(self.refresh)
        backend.stm32_changed.connect(self.refresh)
        backend.changed.connect(self.refresh)
        self.refresh()

    # ---- building blocks ------------------------------------------------
    def _forward(self, register):
        """'→ RLPW (ID 3 …)' for a CPU register the CPU loop forwards, else ''."""
        for registers, board, slave, _ in self.backend.cpu_map.forwards:
            if register in registers:
                return f'→ {board} (ID {slave} trên bus CPU)'
        return ''

    def _route_text(self):
        cpu = self.backend.cpu_map
        if self.io is None:
            return ''
        used = set(self.backend.profile.hardware['stm32_io'].get('safe_state', {}))
        parts = []
        for registers, board, slave, _ in cpu.forwards:
            if registers:
                absent = '' if used & set(registers) else ' (profile không dùng: bo không lắp)'
                parts.append(f"{'/'.join(registers)} → {board} ID {slave}{absent}")
        sends = ' · '.join(parts)
        return (f'Đường đi lệnh: PC ⇄ CPU STM32 (slave {self.backend.tool["slave"]}, RS485 Modbus RTU) là kết nối '
                f'DUY NHẤT của PC. PC chỉ ghi/đọc thanh ghi của CPU; mỗi vòng lặp CPU tự gửi tiếp xuống bus riêng '
                f'của nó: {sends}. Bo con không trả lời PC và firmware chưa báo lỗi bo con lên PC (FW-04), nên đầu ra '
                f'phải kiểm bằng đồng hồ.')

    def _power_group(self):
        group = QGroupBox(f"Rơ-le nguồn · thanh ghi CPU Power (DO {self.io.address('Power')}) "
                          f"{self._forward('Power')}")
        grid = QGridLayout(group)
        self.power_buttons = {}
        owners = {e['bit']: sid for sid, e in self.io.outputs.items()
                  if e.get('kind') == 'bit' and e.get('register') == 'Power'}
        forced = set(self.backend.profile.hardware['stm32_io'].get('hmi_forced_bits', {}).get('Power', []))
        for bit in range(12):
            sid = owners.get(bit)
            short = (self.labels.get(sid, sid or '').replace('Lệnh nguồn ', '').replace(' / 1000 Hz', '')
                     .replace('3 pha ', ''))
            text = f'RL{bit + 1} · {short}' if sid else f'RL{bit + 1} · trống'
            if bit in forced:
                text = f'RL{bit + 1} · HMI ép bật'
            button = QPushButton(text)
            button.setCheckable(True)
            button.setEnabled(sid is not None)
            button.setToolTip(self.io.outputs[sid].get('note', '') if sid else 'Bit chưa gán tín hiệu.')
            button.clicked.connect(lambda checked, s=sid, b=button: self._power(s, b))
            grid.addWidget(button, bit // 3, bit % 3)
            self.power_buttons[bit] = (sid, button)
            if sid:
                self.controls.append(button)
        return group

    def _matrix_group(self):
        group = QGroupBox('Matrix tín hiệu 8×4 (qua CPU) · bấm ô: nối chân (hàng) với nguồn (cột); "Hở" để nhả')
        group.setToolTip('Một chân chỉ nối một nguồn; đổi nguồn = ngắt trước, chờ break_ms, rồi đóng. DAC lấy mức ở ô '
                         '"Mức DAC". Bo đánh dấu "cần sửa FW" chỉ chạy được trên COM ảo cho tới khi firmware CPU/bo con '
                         'được sửa. Rê chuột lên ô để xem thanh ghi/bit.')
        box = QVBoxLayout(group)
        tabs = QTabWidget()
        self.matrix_tables = []
        sources = self.backend.profile.hardware['stm32_io'].get('sources', {})
        for board in self.backend.profile.hardware['stm32_io'].get('matrix_boards', []):
            table = QTableWidget(board['size']['outputs'], board['size']['inputs'] + 1)
            heads = [f"IN{n}\n{sources[board['inputs'][str(n)]]['label'].split(' ')[0]}"
                     if str(n) in board['inputs'] else f'IN{n}\n—' for n in range(1, board['size']['inputs'] + 1)]
            table.setHorizontalHeaderLabels(heads + ['Hở'])
            rows = []
            for out in range(1, board['size']['outputs'] + 1):
                sid = board['outputs'].get(str(out))
                rows.append(sid)
                table.setVerticalHeaderItem(out - 1, QTableWidgetItem(
                    f'OUT{out} · {self.labels.get(sid, sid)}' if sid else f'OUT{out} · —'))
                for col in range(board['size']['inputs'] + 1):
                    item = QTableWidgetItem('')
                    item.setFlags(Qt.ItemIsEnabled if sid else Qt.NoItemFlags)
                    item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(out - 1, col, item)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setMinimumHeight(230)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.cellClicked.connect(lambda r, c, b=board, rs=rows: self._matrix_click(b, rs, r, c))
            fw = ' · cần sửa FW' if 'SỬA FIRMWARE' in board.get('note', '') else ''
            regs = '/'.join(board['registers'])
            prefix = os.path.commonprefix(board['registers'])  # Matrix0/1, Matrix2_0/Matrix2_1 → Matrix2
            short = (prefix.rstrip('_') if prefix.endswith('_')
                     else prefix + '/'.join(r[len(prefix):] for r in board['registers']))
            tabs.addTab(table, f"ID {board['id']} · {short}{fw}")
            tabs.setTabToolTip(tabs.count() - 1, f"PC ghi thanh ghi CPU {regs}; CPU gửi tiếp FC16 tới bo RLMatrix "
                                                 f"ID {board['id']} mỗi vòng lặp. {board.get('note', '')}")
            self.matrix_tables.append((board, rows, table))
            self.controls.append(table)
        box.addWidget(tabs)
        return group

    def _mux_group(self):
        group = QGroupBox(f"MUX · thanh ghi CPU MUX (DO {self.io.mux}) {self._forward('MUX')} · kênh 0–31, 31 = hở")
        grid = QGridLayout(group)
        names = {}
        for sid, entry in self.io.inputs.items():
            if entry.get('kind') == 'adc' and entry.get('mux') is not None:
                names[(entry.get('mux_bank', 0), entry['mux'])] = sid
        self.mux_boxes = []
        for bank in range(self.io.mux_banks):
            combo = QComboBox()
            for channel in range(self.io.mux_channel_count):
                sid = names.get((bank, channel))
                text = f'{channel:02} · Mux{bank + 1}.{channel + 1}'
                if sid:
                    text += f' · {self.labels.get(sid, sid)}'
                if channel == self.io.mux_idle:
                    text += ' · hở hết (an toàn)'
                combo.addItem(text, channel)
            combo.setCurrentIndex(self.io.mux_idle)
            grid.addWidget(QLabel(f'MUX{bank + 1}'), bank, 0)
            grid.addWidget(combo, bank, 1)
            self.mux_boxes.append(combo)
            self.controls.append(combo)
        self.mux_apply = QPushButton('Chọn kênh rồi đọc ADC')
        self.mux_apply.clicked.connect(self._mux)
        grid.addWidget(self.mux_apply, self.io.mux_banks, 0, 1, 2)
        self.mux_reading = QLabel('—')
        self.mux_reading.setWordWrap(True)
        self.mux_reading.setMinimumHeight(self.mux_reading.fontMetrics().lineSpacing() * 2 + 4)
        grid.addWidget(self.mux_reading, self.io.mux_banks + 1, 0, 1, 2)
        self.controls.append(self.mux_apply)
        return group

    def _dac_dout_group(self):
        group = QGroupBox('DAC (PA4) và DOUT · chân của chính bo CPU')
        grid = QGridLayout(group)
        dac = self.io.dac or {}
        self.dac = QDoubleSpinBox()
        self.dac.setDecimals(3)
        self.dac.setRange(dac.get('min', -1.5), dac.get('max', 1.5))
        self.dac.setSingleStep(0.01)
        self.dac.setSuffix(' V')
        self.dac_apply = QPushButton('Ghi DAC_val')
        self.dac_apply.clicked.connect(self._dac)
        self.dac_apply.setEnabled(bool(dac))
        self.dac.setToolTip('Mức tại chân XP1 theo hệ số DAC giả định trong hardware.json (cần hiệu chuẩn). '
                            'DAC chỉ ra chân khi ô DAC của bo matrix được nối.')
        grid.addWidget(QLabel('Mức DAC'), 0, 0)
        grid.addWidget(self.dac, 0, 1)
        grid.addWidget(self.dac_apply, 0, 2)
        self.dout = []
        row = QHBoxLayout()
        for bit in range(10):
            check = QCheckBox(str(bit))
            self.dout.append(check)
            row.addWidget(check)
        grid.addWidget(QLabel('DOUT bit'), 1, 0)
        grid.addLayout(row, 1, 1, 1, 2)
        self.dout_apply = QPushButton('Ghi DOUT')
        self.dout_apply.clicked.connect(self._dout)
        grid.addWidget(self.dout_apply, 2, 2)
        self.controls += [self.dac, self.dac_apply, self.dout_apply] + self.dout
        return group

    def _readings_group(self):
        group = QGroupBox('Giá trị CPU đọc được (FC03 tới CPU)')
        box = QVBoxLayout(group)
        row = QHBoxLayout()
        self.read_now = QPushButton('Đọc')
        self.read_now.clicked.connect(lambda: self._read())
        self.auto = QCheckBox('Tự đọc mỗi')
        self.auto_ms = QSpinBox()
        self.auto_ms.setRange(200, 5000)
        self.auto_ms.setSingleStep(100)
        self.auto_ms.setValue(500)
        self.auto_ms.setSuffix(' ms')
        tip = ('Đọc nền: không khóa nút; lệnh bấm trong lúc đọc được gửi ngay sau. CPU chỉ cập nhật số đo một lần mỗi '
               'vòng lặp (xem D02); đọc nhanh hơn vòng lặp chỉ lặp lại số cũ.')
        self.auto.setToolTip(tip)
        self.auto_ms.setToolTip(tip)
        self.auto.toggled.connect(self._auto_changed)
        self.auto_ms.valueChanged.connect(self._auto_changed)
        row.addWidget(self.read_now)
        row.addWidget(self.auto)
        row.addWidget(self.auto_ms)
        row.addStretch()
        box.addLayout(row)
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.values = {}
        names = [f'ADC{i}' for i in range(5)] + ['Điện trở', 'DIN b9…b0', 'Cập nhật']
        for index, name in enumerate(names):
            value = QLabel('—')
            value.setFont(mono)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value.setMinimumWidth(value.fontMetrics().horizontalAdvance('quá thang/hở') + 6)
            row_, col = divmod(index, 2)  # Two pairs per row: fits the short right column.
            grid.addWidget(QLabel(name), row_, col * 2)
            grid.addWidget(value, row_, col * 2 + 1)
            self.values[name] = value
        box.addLayout(grid)
        group.setMinimumHeight(group.sizeHint().height())
        self._auto = QTimer(self)
        self._auto.timeout.connect(lambda: self._read(quiet=True))
        self._seen_at = None  # (received_at, wall clock) of the reading shown.
        return group

    def _auto_changed(self, *_):
        if self.auto.isChecked():
            self._auto.start(self.auto_ms.value())
        else:
            self._auto.stop()

    # ---- actions --------------------------------------------------------
    @property
    def simulation(self):
        return bool(self.source.currentData())

    def _call(self, function, *args):
        try:
            function(*args)
        except ValueError as error:
            self.status.setText(f'Không gửi: {error}')
            return False
        return True

    def _confirm(self, title, text):
        if self.simulation:
            return True
        answer = QMessageBox.question(self, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return answer == QMessageBox.Yes

    def _take(self):
        if self._confirm('Điều khiển mạch thật',
                         f'Ghi Mode=1, Plan=2 và tắt MỌI đầu ra trên CPU slave {self.slave.value()} (COM thật)?'):
            self._call(self.backend.tool_take_control, self.simulation, self.slave.value())

    def _release(self):
        if self._confirm('Trả về HMI', 'Mode=0: CPU chạy mã HMI và TỰ BẬT VDD1–3 (Power bit 7–9). Tiếp tục?'):
            self._call(self.backend.tool_release_to_hmi)

    def _power(self, sid, button):
        entry = self.io.outputs[sid]
        on = button.isChecked()
        button.setChecked(not on)  # Shown state follows ACKed writes only.
        if on and not self._confirm('Cấp nguồn', f'Đóng rơ-le {self.labels.get(sid, sid)} trên mạch thật?'):
            return
        self._call(self.backend.tool_set, [{'signal': sid, 'value': entry['on_value'] if on else None}])

    def _matrix_click(self, board, rows, row, col):
        sid = rows[row]
        if sid is None:
            return
        if col == board['size']['inputs']:
            value = None
        else:
            name = board['inputs'].get(str(col + 1))
            if name is None:
                return
            source = self.backend.profile.hardware['stm32_io']['sources'][name]
            value = self.dac.value() if source.get('dac') else source['value']
        self._call(self.backend.tool_set, [{'signal': sid, 'value': value}])

    def _mux(self):
        word = 0
        for bank, combo in enumerate(self.mux_boxes):
            word |= combo.currentData() << (bank * self.io.mux_bank_bits)
        if self._call(self.backend.tool_set_word, self.backend.profile.hardware['stm32_io']['mux_register'], word):
            # DI shows the new channel only after the CPU loop ran it.
            self.mux_reading.setText('Chờ CPU chuyển kênh rồi đọc…')
            QTimer.singleShot(int(self.io.di_update_ms + self.io.mux_settle_ms) + 50, self,
                              lambda: self._read(quiet=True))

    def _dac(self):
        dac = self.io.dac
        count = round((self.dac.value() - dac['offset']) / dac['scale'])
        if not dac['count_min'] <= count <= dac['count_max']:
            self.status.setText(f'Mã DAC {count} ngoài giới hạn.')
            return
        self._call(self.backend.tool_set_word, 'DAC_val', encode_int16(count))

    def _dout(self):
        word = sum(1 << bit for bit, check in enumerate(self.dout) if check.isChecked())
        self._call(self.backend.tool_set_word, 'DOUT', word)

    def _read(self, quiet=False):
        b = self.backend
        if b.busy or b.serial_read_pending or b.tool_busy or b.closed:
            return  # A read already in flight delivers fresh values anyway.
        try:
            # Background: no control disabling and no status text churn.
            b.request_stm32(simulation=self.simulation, slave=self.slave.value(), background=quiet)
        except ValueError as error:
            self.auto.setChecked(False)
            if not quiet:
                self.status.setText(str(error))

    def hideEvent(self, event):
        if hasattr(self, 'auto'):
            self.auto.setChecked(False)  # Never poll a hidden page.
        super().hideEvent(event)

    # ---- view -------------------------------------------------------------
    def refresh(self):
        b = self.backend
        tool = b.tool
        known = b.tool_image_known()
        where = 'COM ảo' if tool['simulation'] else 'COM THẬT'
        state = 'đầu ra đã biết (theo ACK)' if known else 'đầu ra CHƯA BIẾT'
        self.status.setText(f'{where} · slave {tool["slave"]} · {state}. {tool["message"]}')
        # A background auto-read must not grey the page out every period.
        idle = not b.stm32_foreground_busy
        for widget in (self.take, self.safe, self.hmi, self.source, self.slave):
            if widget.isEnabled() != idle:
                widget.setEnabled(idle)
        for widget in self.controls:
            if widget.isEnabled() != (idle and known):
                widget.setEnabled(idle and known)
        if self.io is None:
            return
        image = tool['image'] if known else {}
        active = self.io.inverse(image) if known else {}
        for bit, (sid, button) in self.power_buttons.items():
            if sid and button.isChecked() != (sid in active):
                button.setChecked(sid in active)
        if known:
            channels = self.io.mux_channels(image.get(self.io.mux, self.io.mux_word()))
            for combo, channel in zip(self.mux_boxes, channels):
                if not combo.hasFocus() and combo.currentData() != channel:
                    combo.setCurrentIndex(channel)  # Show what the CPU acknowledged.
        for board, rows, table in self.matrix_tables:
            for r, sid in enumerate(rows):
                for c in range(table.columnCount()):
                    item = table.item(r, c)
                    closed = False
                    if sid and known:
                        if c == table.columnCount() - 1:
                            closed = sid not in active
                        else:
                            name = board['inputs'].get(str(c + 1))
                            entry = self.io.outputs[sid]
                            point = next((p for p in entry['levels'] + ([entry['dac']] if entry['dac'] else [])
                                          if p['input'] == c + 1), None)
                            closed = point is not None and bool(image.get(self.io.address(point['register']), 0)
                                                               >> point['bit'] & 1)
                            item.setToolTip(f"{point['register']}.bit{point['bit']}" if point else
                                            ('Đầu vào chưa nối nguồn' if name is None else ''))
                    mark = '●' if closed else ''
                    if item.text() != mark:
                        item.setText(mark)
        self._refresh_readings()

    def _set_values(self, texts):
        for name, label in self.values.items():
            text = texts.get(name, '—')
            if label.text() != text:  # Only changed digits repaint.
                label.setText(text)

    def _refresh_readings(self):
        b = self.backend
        state = b.stm32
        valid = state.read_valid and state.source == (self.simulation, self.slave.value())
        if not valid:
            self._seen_at = None
            self._set_values({'Cập nhật': 'chưa có'})
            return
        words = state.mod_buf_to_read
        d = decode_stm32(words, b.cpu_map)
        if self._seen_at is None or self._seen_at[0] != state.received_at:
            self._seen_at = (state.received_at, datetime.now())
        texts = {f'ADC{i}': f'{v:+.2f} V' for i, v in enumerate(d['adc_volts'])}
        texts['Điện trở'] = 'quá thang/hở' if d['resistance_ohms'] is None else f"{d['resistance_ohms']:g} Ω"
        texts['DIN b9…b0'] = ''.join(str(x) for x in reversed(d['din_levels']))
        texts['Cập nhật'] = f'{self._seen_at[1]:%H:%M:%S}.{self._seen_at[1].microsecond // 1000:03d}'
        self._set_values(texts)
        if self.io is not None and b.tool_image_known():
            channels = self.io.mux_channels(b.tool['image'].get(self.io.mux, self.io.mux_word()))
            shown = []
            for sid, entry in self.io.inputs.items():
                if (entry.get('kind') == 'adc' and entry.get('mux') is not None
                        and channels[entry.get('mux_bank', 0)] == entry['mux']):
                    shown.append(f"{self.labels.get(sid, sid)} = {self.io.decode(words, sid):g} "
                                 f"{b.definitions[sid]['unit']}")
            text = ' · '.join(shown) if shown else 'Kênh đang chọn không gán tín hiệu đo.'
            if self.mux_reading.text() != text:
                self.mux_reading.setText(text)


class FrameLogPanel(QWidget):
    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.export = QPushButton('Xuất nhật ký…')
        self.export.clicked.connect(self._export)
        self.clear = QPushButton('Xóa')
        self.clear.clicked.connect(self._clear)
        row.addStretch()
        row.addWidget(self.clear)
        row.addWidget(self.export)
        layout.addLayout(row)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setObjectName('frameLog')
        layout.addWidget(self.text, 1)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(500)
        self._shown = None

    def lines(self):
        actions = [f'# {line}' for line in self.backend.tool['log']]
        frames = [f"{at} {'ẢO ' if sim else 'THẬT'} {d} {hexes}" for at, sim, d, hexes in self.backend.frame_log]
        return actions + ['', '# Khung RTU (dựng lại từ PDU, CRC tính lại):'] + frames

    def refresh(self):
        if not self.isVisible():
            return
        key = (len(self.backend.frame_log), len(self.backend.tool['log']),
               self.backend.frame_log[-1] if self.backend.frame_log else None)
        if key != self._shown:
            self._shown = key
            self.text.setPlainText('\n'.join(self.lines()))
            self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

    def _clear(self):
        self.backend.frame_log.clear()
        self.backend.tool['log'].clear()
        self.refresh()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Xuất nhật ký Modbus', 'modbus_log.txt', 'Text (*.txt)')
        if path:
            Path(path).write_text('\n'.join(self.lines()) + '\n', encoding='utf-8')


class ModbusTestPage(QWidget):
    """Sidebar page 'Test Modbus'."""

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.setObjectName('modbusTestPage')
        layout = QVBoxLayout(self)
        note = QLabel(f'Bản đồ thanh ghi {backend.cpu_map.name}. PC chỉ nói chuyện với bo CPU; rơ-le nguồn, matrix, '
                      'MUX được điều khiển bằng cách ghi thanh ghi của CPU để CPU gửi tiếp. Thử trước trên COM ảo; '
                      'COM thật cần mở cổng ở chế độ Modbus RTU. ACK chỉ là CPU đã nhận lệnh. Bị khóa khi đang chạy bài.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = QTabWidget()
        self.boards = BoardControlPanel(backend)
        self.registers = Stm32RegistersPanel(backend)
        self.log = FrameLogPanel(backend)
        self.tabs.addTab(self.boards, 'Điều khiển qua CPU')
        self.tabs.addTab(self.registers, 'Thanh ghi CPU')
        self.tabs.addTab(self.log, 'Nhật ký')
        layout.addWidget(self.tabs, 1)
