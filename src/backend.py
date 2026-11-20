"""Single source of truth and asynchronous, profile-driven test runner."""
from collections import deque
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import time
import uuid
import math

from PySide6.QtCore import QObject, QTimer, Signal, QStandardPaths, QCoreApplication
from pathlib import Path

from src.common.models import SignalModel
from src.common.monitor import DEFAULT_MONITOR_CHANNELS, demo_monitor_samples
from src.common.profiles import (load_profile, specification_issues, stm32_unsupported, stm32_unverified,
                                 validate_profile)
from src.common.testing import (Mode, Sample, POLL_MS, OPERATION_TIMEOUT_MS, SCENARIOS, STM32_SCENARIOS,
                                READY_SIMULATION, READY_REAL, READY_STATES)
from src.common.serial import SerialSettings
from src.common.stm32 import Stm32RegisterBanks, DEFAULT_SLAVE, READ_STALE_MS
from src.protocol import stm32_write_words, decode_stm32, register_words
from src.device import Device
from src.storage import SessionStore


def evaluate(check, sample, now, stale_ms):
    """Pure verdict calculation, independent of protocol and Widgets.

    ``quality == "default"``: the operator left a manual entry empty and the
    nominal value was recorded instead; it is judged like a value but the
    caller labels it "mặc định, chưa đo". ``absolute`` compares |value|.
    """
    if sample is None or sample.quality not in ("valid", "default") or (now - sample.timestamp) * 1000 > stale_ms:
        return "ERROR", "Mẫu thiếu, lỗi hoặc hết hạn"
    nominal, tolerance = check.get("nominal"), check.get("tolerance")
    if nominal is None or tolerance is None:
        return "Chưa đánh giá", "Tiêu chuẩn chưa đủ giá trị/dung sai"
    value = abs(sample.value) if check.get("absolute") else sample.value
    lower, upper = nominal - tolerance, nominal + tolerance
    inside = lower <= value <= upper or math.isclose(value, lower, rel_tol=0, abs_tol=1e-10) or math.isclose(value, upper, rel_tol=0, abs_tol=1e-10)
    return ("PASS", "Trong giới hạn") if inside else ("FAIL", "Ngoài giới hạn")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Backend(QObject):
    changed = Signal()
    samples_changed = Signal()
    monitor_changed = Signal()
    shutdown_ready = Signal()
    stm32_changed = Signal()
    # Emitted when manual_request appears or disappears (operator entry).
    manual_input_changed = Signal()
    # Test Modbus tool state (queue, known DO image, message, log).
    tool_changed = Signal()

    def __init__(self, profile=None, username="demo", storage_dir=None, parent=None):
        super().__init__(parent)
        self.profile = profile or load_profile()
        validate_profile(self.profile)
        self.username = username
        self.device = Device(self.profile, self)
        self.device.communication.completed.connect(self._received)
        folder = storage_dir or Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) / "sessions" / "simulation"
        # Store outlives a gallery widget until pending checkpoints finish.
        self.store = SessionStore(folder, QCoreApplication.instance())
        self.store.changed.connect(self._save_changed)
        self.store.idle.connect(self._store_idle)
        self.store.recovered.connect(self._recovery_finished)
        self.signal_model = SignalModel(self.profile.signals, self, self.profile.system.get('status_signals', {}).values())
        self.definitions = {s["id"]: s for s in self.profile.signals}
        self.samples = {}
        # Last evaluated value per measured signal, kept for display after the
        # test ends (any mode/adapter). Cleared only by a new measurement of
        # that signal or a new session; never used for verdicts.
        self.measurement_history = {}
        self.signal_model.history = self.measurement_history
        self.pause_requested = False
        self.connection = "Chưa kết nối"
        self.connection_adapter = 'mock'
        self.serial_state = 'disconnected'
        self.serial_settings = None
        self.serial_result = None
        self.controller_info = None
        self.controller_result = None
        self.serial_read_pending = False
        self.cpu_map = self.device.cpu_map
        self.stm32 = Stm32RegisterBanks(self.cpu_map)
        # Rolling RTU frame log for the Test Modbus page (both ports).
        self.frame_log = deque(maxlen=500)
        profile_slave = self.device.io_map.slave if self.device.io_map else DEFAULT_SLAVE
        self.tool = {'image': None, 'queue': [], 'inflight': False, 'simulation': True, 'slave': profile_slave,
                     'message': 'Chưa lấy quyền điều khiển.', 'log': deque(maxlen=200)}
        self.stm32_pending = False
        # A periodic read issued by an auto-read box: the UI keeps its controls
        # enabled and tool commands wait for it instead of being refused.
        self.stm32_background = False
        self.device.stm32_completed.connect(self._stm32_completed)
        # 'stm32': runner writes/reads the two CPUv1.0 banks; 'mock': legacy A45 v1.
        self.adapter = self.profile.hardware["adapter"]
        self.bench_token = None
        # Last CPU loop-period self-test (D02) on the CURRENT real connection;
        # tests on real hardware need it to fit the runner's DI wait.
        self.loop_check = None
        # Pending operator entry (e.g. frequency read on an oscilloscope).
        self.manual_request = None
        self._manual_frozen = (0.0, {})  # (capture time, bench samples) of the waiting step.
        self.device.bench_completed.connect(self._bench_completed)
        self.device.stm32_snapshot.connect(self._stm32_snapshot)
        self.serial_detail = ''
        self.uart_received_bytes = 0
        self.uart_last_hex = ''
        self.device.serial_connection.status_changed.connect(self._serial_status)
        self.device.serial_connection.read_finished.connect(self._serial_read_finished)
        self.device.serial_connection.received.connect(self._uart_received)
        self.device.virtual_connection.status_changed.connect(self._virtual_status)
        for link, simulation in ((self.device.serial_connection, False), (self.device.virtual_connection, True)):
            link.frame_logged.connect(lambda direction, raw, sim=simulation: self._frame_logged(sim, direction, raw))
        self.device.controller_completed.connect(self._controller_received)
        self.mode = Mode.AUTO
        self.selected_id = self.profile.tests[0]["id"]
        self.serial_number = ""
        self.time_scale = 1.0
        self.epoch = 0
        self.session = None
        self.queue = []
        self.attempt = None
        self.test = None
        self.step_index = 0
        self.phase = "idle"
        self.token = None
        self.confirmed = None
        self.deadline = 0.0
        self.wait_until = 0.0
        self.capture_after = 0.0
        self.message = "MÔ PHỎNG · Chưa có kết nối phần cứng thật"
        self.stopping = False
        self.shutdown_requested = False
        self.closed = False
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self._poll_device)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(50)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()
        self.recovered = []
        self.store.scan()
        self.monitor_channels = deepcopy(self.profile.system.get('monitor_channels', DEFAULT_MONITOR_CHANNELS))
        self.monitor_samples = {}
        self._monitor_origin = time.monotonic()
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(100)
        self._monitor_timer.timeout.connect(self._sample_monitor)
        self.set_monitor_simulation(True)

    @property
    def monitor_enabled(self):
        return self._monitor_timer.isActive()

    def set_monitor_simulation(self, enabled):
        if enabled and not self.closed and not self.shutdown_requested and self.monitor_channels:
            self._monitor_timer.start()
            self._sample_monitor()
        else:
            self._monitor_timer.stop()
            self.monitor_samples = {sid: replace(sample, quality='stale')
                                    for sid, sample in self.monitor_samples.items()}
            self.monitor_changed.emit()

    def _sample_monitor(self):
        now = time.monotonic()
        self.monitor_samples = demo_monitor_samples(self.monitor_channels, now - self._monitor_origin, now)
        self.monitor_changed.emit()

    def _recovery_finished(self, ids):
        self.recovered = ids
        self.changed.emit()

    @property
    def busy(self):
        return self.phase != "idle"

    @property
    def tests(self):
        return self.profile.diagnostics if self.mode == Mode.SELF else self.profile.tests

    @property
    def paused(self):
        return self.phase == "paused"

    @property
    def can_pause(self):
        return (self.busy and not self.paused and not self.stopping and not self.pause_requested
                and not self.closed and not self.shutdown_requested)

    @property
    def scenarios(self):
        return STM32_SCENARIOS if self.adapter == "stm32" else SCENARIOS

    @property
    def real_hardware(self):
        """The runner talks to the real CPU (verified real COM connection)."""
        return self.connection == READY_REAL or (self.session is not None and not self.session.get("simulation", True)
                                                 and self.busy)

    @property
    def run_simulation(self):
        return self.connection_adapter == 'mock'

    @property
    def effective_time_scale(self):
        # Waits are never shortened on real hardware (AGENTS.md).
        return self.time_scale if self.run_simulation else 1.0

    def real_run_blockers(self, tests=None):
        """Why the selected tests may not run on the real bench (empty = allowed).

        Self-tests only write the safe state and are always allowed. Other
        tests need every mapping they use 'verified' on the bench, and a CPU
        loop period (self-test D02, this connection) within the DI wait.
        """
        if self.mode == Mode.SELF:
            return []
        tests = tests if tests is not None else self._selected_tests()
        blockers = []
        io = self.device.io_map
        limit = io.di_update_ms / 2 if io else 0
        check = self.loop_check
        if not check or check.get("status") != "PASS":
            blockers.append("Chưa chạy tự kiểm tra D02 (chu kỳ vòng lặp CPU) đạt trên kết nối thật này.")
        elif check["value"] > limit:
            blockers.append(f"Chu kỳ CPU đo được {check['value']:g} ms > di_update_ms/2 = {limit:g} ms.")
        for test in tests:
            pending = stm32_unverified(self.profile, test)
            if pending:
                blockers.append(f"{test['id']}: ánh xạ chưa đo kiểm ({', '.join(pending[:6])}"
                                + (f" … +{len(pending) - 6}" if len(pending) > 6 else "") + ")")
        return blockers

    def _selected_tests(self):
        return [t for t in self.tests if self.mode != Mode.MANUAL or t["id"] == self.selected_id]

    @property
    def can_start(self):
        if (self.busy or self.closed or self.shutdown_requested or self.connection not in READY_STATES
                or self.tool_busy):
            return False
        if self.adapter == "stm32":
            # Readiness = the slave answered FC03 on connect; each test starts
            # with a fresh FC03. CPUv1.0 exposes no ready/fault flag.
            return self.bench_token is None
        now = time.monotonic()
        for role, sid in self.profile.system.get("status_signals", {}).items():
            if role not in ("ready", "fault"):
                continue
            sample = self.samples.get(sid, Sample())
            if sample.quality != "valid" or (now - sample.timestamp) * 1000 > self.definitions[sid]["stale_ms"]:
                return False
            if sample.value != (1 if role == "ready" else 0):
                return False
        return True

    @property
    def progress(self):
        if not self.session or not self.session["planned"]:
            return 0
        return round(100 * self.session["processed"] / len(self.session["planned"]))

    def _save_changed(self, _):
        self.changed.emit()

    def _store_idle(self):
        if self.shutdown_requested and not self.busy:
            self._close()

    def configure(self, mode=None, serial_number=None, time_scale=None, scenario=None):
        if self.busy:
            return False
        if mode is not None:
            mode = Mode(mode)
            if mode != self.mode and self.session:
                self.message = "Tạo phiên mới trước khi đổi chế độ."
                self.changed.emit()
                return False
            self.mode = mode
        if serial_number is not None:
            if self.session and serial_number != self.serial_number:
                return False
            self.serial_number = serial_number.strip()
        if time_scale is not None:
            if time_scale not in (1.0, 10.0, 60.0):
                raise ValueError("Hệ số thời gian mô phỏng không hợp lệ")
            if self.session and time_scale != self.time_scale:
                return False
            self.time_scale = time_scale
        if scenario is not None:
            if scenario not in self.scenarios:
                raise ValueError("Kịch bản không hỗ trợ")
            self.device.communication.transport.scenario = scenario
        self.changed.emit()
        return True

    def connect_device(self):
        if self.busy or self.closed or self.shutdown_requested:
            return
        self.disconnect_device()
        self.connection_adapter = 'mock'
        self.epoch += 1
        self.connection = "Đang xác minh mô phỏng"
        if self.adapter == "stm32":
            if self.stm32_pending:
                self.connection = "Chưa kết nối"
                self.message = "Chờ giao dịch STM32 chẩn đoán kết thúc rồi kết nối lại."
            else:
                # Same Modbus RTU path as a real COM port, on the virtual port.
                self.bench_token = str(uuid.uuid4())
                self.message = "Mở COM ảo, gửi FC03 tới STM32 giả lập…"
                self.device.bench_connect(self.bench_token)
        else:
            self.device.connect_device(self.epoch)
        self.changed.emit()

    def connect_serial(self, settings):
        if self.busy or self.closed or self.shutdown_requested:
            return False
        if not isinstance(settings, SerialSettings):
            raise ValueError('Cấu hình serial không hợp lệ.')
        self.disconnect_device()
        self.connection_adapter = settings.adapter
        self.serial_settings = settings
        self.uart_received_bytes = 0
        self.uart_last_hex = ''
        self.device.open_serial(settings)
        return True

    def _serial_status(self, state, detail):
        self.serial_state = state
        self.serial_detail = detail
        self.serial_result = None
        self.serial_read_pending = False
        self.stm32_background = False
        if state != 'open':
            self._tool_drop_deferred('COM đã đóng')
            if self.stm32.source and not self.stm32.source[0]:
                self.stm32.invalidate()
                self.stm32.message = detail or 'COM đã đóng; dữ liệu STM32 không còn hiệu lực.'
                self.stm32_changed.emit()
            self.controller_info = None
            self.controller_result = None
            self.uart_received_bytes = 0
            self.uart_last_hex = ''
        if self.connection_adapter == 'mock':
            return
        if state != 'open':
            self.loop_check = None
        if state == 'open':
            self.connection = f'Đã mở {self.serial_settings.port}'
            self.serial_detail = (f'{self.serial_settings.baudrate} baud · {self.serial_settings.framing}. '
                                  'Cổng đã mở; chưa xác minh phản hồi thiết bị.')
            if (self.adapter == "stm32" and self.connection_adapter == 'rtu' and not self.stm32_pending
                    and self.bench_token is None and not self.busy):
                # FC03 only (writes nothing): proves the CPU slave answers.
                self.connection = "Đang xác minh STM32 thật"
                self.serial_detail += f" Đang đọc FC03 tới slave {self.device.io_map.slave}…"
                self.bench_token = str(uuid.uuid4())
                try:
                    self.device.bench_connect(self.bench_token, simulation=False)
                except ValueError as error:
                    self.bench_token = None
                    self.connection = f'Đã mở {self.serial_settings.port}'
                    self.serial_detail = str(error)
        elif state == 'connecting':
            self.connection = 'Đang mở COM…'
        elif state == 'error':
            if not self.connection.startswith('Không có phản hồi STM32'):
                self.connection = 'Lỗi kết nối COM'  # Keep the more specific verify failure.
            self._invalidate()
        else:
            self.connection = 'Chưa kết nối'
            self._invalidate()
        self.message = self.serial_detail or self.connection
        self.changed.emit()

    def _virtual_status(self, state, detail):
        """The virtual COM port closed by itself (timeout / unplug), like a real port."""
        if state not in ('error', 'disconnected'):
            return
        if self.stm32.source and self.stm32.source[0]:
            self.stm32.invalidate()
            self.stm32.message = detail or 'COM ảo đã đóng; dữ liệu STM32 không còn hiệu lực.'
            self.stm32_changed.emit()
        if (state == 'error' and self.connection_adapter == 'mock' and self.adapter == 'stm32'
                and self.connection in ("Sẵn sàng · MÔ PHỎNG", "Đang xác minh mô phỏng")):
            self.connection = "Mất kết nối COM ảo · cần kết nối lại"
            self.message = detail
            self._invalidate()
            self.changed.emit()

    def _frame_logged(self, simulation, direction, raw):
        self.frame_log.append((datetime.now().strftime('%H:%M:%S.%f')[:-3], bool(simulation), direction,
                               bytes(raw).hex(' ').upper()))
        frames = self.stm32.frames.setdefault(simulation, {})
        if direction == 'TX':
            frames.clear()
        frames[direction] = bytes(raw)

    def stage_stm32(self, address, values):
        words = stm32_write_words(address, values, self.cpu_map.write_count)
        self.stm32.mod_buf_to_write[address:address + len(words)] = words
        self.stm32.staged.update(range(address, address + len(words)))
        self.stm32_changed.emit()

    def unstage_stm32(self, address):
        self.stm32.staged.discard(address)
        self.stm32_changed.emit()

    def check_cpu_slave(self, slave):
        """Only the CPU is on the PC's bus: every stm32 request goes to its slave ID.

        Sub-boards (RLPW, RLMatrix, RLMUX…) sit on the CPU's own USART1 bus and
        are driven by writing the CPU's registers; the PC never addresses them.
        """
        io = self.device.io_map
        if io is not None and slave != io.slave:
            boards = ', '.join(f'{board} ID {sid}' for _, board, sid, _ in self.cpu_map.forwards)
            raise ValueError(f'PC chỉ giao tiếp với CPU slave {io.slave} (hardware.json → stm32_io.slave); không gửi tới '
                             f'slave {slave}. Bo con ({boards}) nằm trên bus riêng của CPU: điều khiển bằng thanh ghi '
                             f'của CPU.')

    @property
    def stm32_foreground_busy(self):
        """Busy for operator actions; a background auto-read does not count."""
        return (self.busy or self.closed or self.tool_busy
                or (self.serial_read_pending and not self.stm32_background))

    def select_stm32_source(self, simulation, slave):
        source = (bool(simulation), slave)
        if self.stm32_pending and source != self.stm32.source:
            raise ValueError('Chờ giao dịch STM32 kết thúc trước khi đổi nguồn.')
        if source != self.stm32.source:
            self.stm32.source = source
            self.stm32.invalidate()
            self.stm32.message = 'Đã đổi nguồn/Slave ID; cần đọc lại.'
            self.stm32_changed.emit()

    def request_stm32(self, *, simulation=True, slave=None, address=None, count=1, background=False):
        """``slave`` defaults to the profile's CPU slave ID.

        ``background`` marks a periodic auto-read: it leaves the status text
        alone (no "waiting" flicker) and lets tool commands queue behind it.
        """
        slave = self.tool['slave'] if slave is None else slave
        self.check_cpu_slave(slave)
        if self.busy or self.closed or self.shutdown_requested or self.serial_read_pending or self.tool_busy:
            raise ValueError('Ứng dụng đang bận hoặc đóng.')
        if self.bench_token is not None:
            raise ValueError('Bộ chạy bài đang dùng STM32 (đang xác minh kết nối).')
        if not simulation and (self.serial_state != 'open' or self.connection_adapter != 'rtu'):
            raise ValueError('Mở COM ở chế độ Modbus RTU trước khi giao tiếp STM32 thật.')
        values = None
        if address is not None:
            if type(count) is not int or count < 1:
                raise ValueError('Số thanh ghi ghi phải lớn hơn 0.')
            limit = self.cpu_map.write_count
            stm32_write_words(address, [0], limit)  # Validate address before slicing.
            values = stm32_write_words(address, self.stm32.mod_buf_to_write[address:address + count], limit)
            if len(values) != count or not set(range(address, address + count)) <= self.stm32.staged:
                raise ValueError('Nhập rõ giá trị cho từng thanh ghi trong vùng gửi; không tự gửi các số 0 mặc định.')
            self.check_safe_write(address, values)
        self.select_stm32_source(simulation, slave)
        self.stm32_pending = self.serial_read_pending = True
        self.stm32_background = bool(background) and values is None
        self.stm32.last_ack = None if values is not None else self.stm32.last_ack
        if not self.stm32_background:
            self.stm32.message = 'Đang chờ phản hồi STM32…'
        try:
            if values is None:
                self.device.read_stm32(slave, simulation)
            else:
                self.device.write_stm32(address, values, slave, simulation)
        except ValueError as error:
            self._stm32_completed('read' if values is None else 'write', None, str(error))
            raise
        self.stm32_changed.emit()
        self.changed.emit()

    def check_safe_write(self, address, values):
        """Refuse writes that the firmware would execute dangerously.

        The RLMUX board indexes Mux_Decoder[32] without a bounds check, so a
        MUX channel outside the configured range would close random relays.
        """
        io = self.device.io_map
        if io is None or not address <= io.mux < address + len(values):
            return
        word = values[io.mux - address]
        bad = [c for c in io.mux_channels(word) if c >= io.mux_channel_count]
        if bad:
            raise ValueError(f'MUX = {word} (0x{word:04X}) chọn kênh {bad[0]} ≥ {io.mux_channel_count}: firmware bo MUX '
                             'không kiểm giới hạn và sẽ đóng rơ-le ngẫu nhiên. Không gửi.')

    # ---- "Test Modbus" tool: operator-driven control of the boards ----------
    # Semantic operations go through the SAME Stm32IoMap as the runner
    # (interlocks, HMI-forced bits, matrix one-source-per-pin, MUX bound,
    # break-before-make). Writes are queued one transaction at a time, never
    # retried; any error makes the DO image unknown until "Về an toàn".

    @property
    def tool_busy(self):
        return bool(self.tool['queue']) or self.tool['inflight']

    def tool_take_control(self, simulation, slave):
        """Mode=1/Plan=2 plus the full safe state (everything off)."""
        self._tool_start(simulation, slave, [('image', None, self._tool_safe_image())],
                         'Lấy quyền điều khiển: Mode=1, mọi đầu ra về an toàn.')

    def tool_safe_state(self):
        """Rewrite the whole safe state (works even when the image is unknown)."""
        self._tool_start(self.tool['simulation'], self.tool['slave'], [('image', None, self._tool_safe_image())],
                         'Về an toàn: ghi lại toàn bộ trạng thái an toàn.')

    def tool_release_to_hmi(self):
        """Mode=0: the CPU follows its HMI code again (it turns VDD1–3 on)."""
        self._tool_start(self.tool['simulation'], self.tool['slave'],
                         [('write', self.cpu_map.write_index('Mode'), [0])],
                         'Trả về HMI (Mode=0): CPU tự điều khiển, tự bật VDD1–3; PC không còn giữ trạng thái.')
        self.tool['image'] = None

    def tool_set(self, actions):
        """Signal-level actions ({signal, value}) through the runner's map."""
        io = self._tool_io()
        new = io.apply(self.tool['image'], actions)
        self._tool_start(self.tool['simulation'], self.tool['slave'], [('image', self.tool['image'], new)],
                         'Đặt ' + ', '.join(f"{a['signal']}={a['value']}" for a in actions))

    def tool_set_word(self, name, word):
        """One register by name (MUX channels, DAC_val, DOUT, raw relay word)."""
        io = self._tool_io()
        address = io.address(name)
        if address not in io.safe_image():
            raise ValueError(f'{name} không thuộc vùng công cụ được ghi (safe_state).')
        register_words([word])
        new = dict(self.tool['image'])
        new[address] = word
        self.check_safe_write(address, [word])
        self._tool_check_interlocks(io, new)
        self._tool_start(self.tool['simulation'], self.tool['slave'], [('image', self.tool['image'], new)],
                         f'Ghi {name} = {word} (0x{word:04X})')

    def _tool_io(self):
        io = self.device.io_map
        if io is None:
            raise ValueError('Profile không dùng adapter stm32.')
        if not self.tool_image_known():
            raise ValueError('Trạng thái đầu ra chưa biết: bấm "Lấy quyền điều khiển" hoặc "Về an toàn" trước.')
        return io

    @staticmethod
    def _tool_check_interlocks(io, image):
        io.apply(image, [])  # Re-runs interlock checks on a raw image.
        for sid, entry in io.outputs.items():
            if entry.get('kind') == 'pin' and io.inverse(image).get(sid, 0) is None:
                raise ValueError(f'{sid}: hai nguồn cùng nối vào một chân (chập). Không gửi.')

    def _tool_safe_image(self):
        io = self.device.io_map
        if io is None:
            raise ValueError('Profile không dùng adapter stm32.')
        return io.safe_image()

    def _tool_start(self, simulation, slave, ops, label):
        self.check_cpu_slave(slave)
        if self.busy or self.closed or self.shutdown_requested:
            raise ValueError('Bộ chạy bài đang chạy hoặc ứng dụng đang đóng.')
        if self.tool_busy or (self.serial_read_pending and not self.stm32_background):
            raise ValueError('Đang chờ giao dịch trước kết thúc.')
        if not simulation and (self.serial_state != 'open' or self.connection_adapter != 'rtu'):
            raise ValueError('Mở COM ở chế độ Modbus RTU trước khi điều khiển mạch thật.')
        io = self.device.io_map
        queue = []
        for op in ops:
            if op[0] != 'image':
                queue.append(op)
                continue
            old, new = op[1], op[2]
            for index, image in enumerate(io.phases(old, new)):
                if index:
                    queue.append(('wait', io.break_ms))  # Break-before-make.
                queue += [('write', address, words) for address, words in io.writes(old, image)]
                old = image
        self.select_stm32_source(simulation, slave)
        if any(op[0] == 'image' and op[1] is None for op in ops):
            self.tool['image'] = {}  # Full rewrite: rebuilt from ACKs only.
        elif (simulation, slave) != (self.tool['simulation'], self.tool['slave']):
            raise ValueError('Đổi nguồn/Slave ID: bấm "Lấy quyền điều khiển" lại.')
        self.tool.update(simulation=bool(simulation), slave=slave, queue=queue, message=label)
        self.tool['log'].append(f"{datetime.now():%H:%M:%S} {'COM ảo' if simulation else 'COM THẬT'} · {label}")
        if self.serial_read_pending:
            self.tool_changed.emit()  # Starts when the background read completes.
            return
        self._tool_next()

    def _tool_drop_deferred(self, reason):
        """Forget commands queued behind a background read (nothing was sent)."""
        if self.tool['queue'] and not self.tool['inflight']:
            self.tool['queue'] = []
            self.tool['message'] = f'Hủy lệnh chưa gửi ({reason}); trạng thái đầu ra không đổi.'
            self.tool['log'].append(f"{datetime.now():%H:%M:%S} {self.tool['message']}")
            self.tool_changed.emit()

    def _tool_next(self):
        tool = self.tool
        if tool['inflight'] or self.closed:
            return
        if not tool['queue']:
            tool['message'] += ' · Xong (ACK: CPU đã nhận; đầu ra phải kiểm bằng đo).'
            self.tool_changed.emit()
            return
        op = tool['queue'].pop(0)
        if op[0] == 'wait':
            tool['inflight'] = True
            QTimer.singleShot(int(op[1]), self, self._tool_wait_done)
            self.tool_changed.emit()
            return
        address, words = op[1], op[2]
        tool['inflight'] = True
        tool['pending'] = (address, words)
        self.stm32_pending = self.serial_read_pending = True
        try:
            self.device.write_stm32(address, words, tool['slave'], tool['simulation'])
        except ValueError as error:
            self._stm32_completed('write', None, str(error))
            return
        self.tool_changed.emit()
        self.changed.emit()

    def _tool_wait_done(self):
        self.tool['inflight'] = False
        self._tool_next()

    def _tool_completed(self, result, error):
        tool = self.tool
        tool['inflight'] = False
        address, words = tool.pop('pending')
        if error:
            tool['queue'].clear()
            tool['image'] = None  # Executed or not is unknown; never resent.
            tool['message'] = f'Lỗi: {error} · Trạng thái đầu ra chưa biết.'
            tool['log'].append(f"{datetime.now():%H:%M:%S} LỖI {error}")
            self.tool_changed.emit()
            return
        if tool['image'] is not None:
            # ACKed words only: the image is "known" once every owned
            # register has been written (see tool_image_known).
            for offset, word in enumerate(words):
                tool['image'][address + offset] = word
        self._tool_next()

    def tool_image_known(self):
        image = self.tool['image']
        return (image is not None and self.device.io_map is not None
                and set(self.device.io_map.safe_image()) <= set(image))

    def _stm32_completed(self, operation, result, error):
        tool_write = operation == 'write' and self.tool['inflight'] and 'pending' in self.tool
        self.stm32_pending = self.serial_read_pending = False
        self.stm32_background = False
        if not error and operation == 'read':
            try:
                words = register_words(result['values'])
                last = self.cpu_map.read_count - 1
                if result['address'] != 1 or len(words) != last:
                    raise ValueError(f'Phản hồi không đủ mảng Modbus_DI 1–{last}.')
                decode_stm32([0] + words, self.cpu_map)
                self.stm32.mod_buf_to_read[:] = [0] + words
                self.stm32.received_at = result['timestamp']
                self.stm32.read_valid = True
                self.stm32.message = f'Đã đọc DI 1–{last}; thời điểm lấy mẫu trong MCU chưa xác định.'
            except (ValueError, KeyError, TypeError) as exc:
                error = str(exc)
        elif not error:
            self.stm32.last_ack = deepcopy(result)
            self.stm32.message = 'STM32 đã nhận lệnh ghi (ACK); chưa xác nhận phần cứng thực thi.'
        if error:
            self.stm32.invalidate()
            self.stm32.message = error
        elif operation == 'write' and not tool_write and self.tool['image'] is not None:
            # A raw register write changes words the tool believed it knew.
            self.tool['image'] = None
            self.tool['message'] = 'Ghi thanh ghi trực tiếp: trạng thái công cụ chưa biết, cần "Về an toàn".'
            self.tool_changed.emit()
        if tool_write:
            self._tool_completed(result, error)
        elif self.tool['queue'] and not self.tool['inflight']:
            # Tool commands queued behind this read.
            if error:
                self._tool_drop_deferred(f'lỗi đọc: {error}')
            else:
                self._tool_next()
        self.stm32_changed.emit()
        self.changed.emit()

    def read_serial_registers(self, slave, function, address, count):
        if self.busy or self.closed or self.shutdown_requested:
            raise ValueError('Ứng dụng đang bận hoặc đóng.')
        if self.serial_read_pending:
            raise ValueError('Đang chờ phản hồi giao dịch trước.')
        self.serial_result = None
        self.controller_result = None
        self.serial_read_pending = True
        self.serial_detail = 'Đang chờ phản hồi Modbus…'
        try:
            self.device.read_registers(slave, function, address, count)
        except ValueError as error:
            self.serial_read_pending = False
            self.serial_detail = str(error)
            self.changed.emit()
            raise
        self.changed.emit()

    def request_controller(self, node=None):
        if self.busy or self.closed or self.shutdown_requested or self.serial_read_pending:
            raise ValueError('Ứng dụng đang bận hoặc đóng.')
        self.serial_read_pending = True
        self.serial_result = None
        self.controller_result = None
        self.serial_detail = 'Đang chờ khung A45…'
        self._invalidate()
        try:
            if node is None:
                self.device.snapshot_controller()
            else:
                self.controller_info = None
                self.device.identify_controller(node)
        except ValueError as error:
            self.serial_read_pending = False
            self.serial_detail = str(error)
            self.changed.emit()
            raise
        self.changed.emit()

    def _controller_received(self, operation, result, error):
        self.serial_read_pending = False
        if error:
            self.serial_detail = error
            self.controller_result = None
            self._invalidate()
        elif operation == 'connect':
            self.controller_info = result
            source = 'bộ giả lập' if result['simulation'] else 'firmware'
            self.serial_detail = f"Đã xác minh A45 v1 · {source} · boot {result['boot_id']} · đúng ánh xạ kênh."
        else:
            self.controller_result = result
            self.samples = self.device.decode(result)
            self.signal_model.refresh(self.samples)
            self.samples_changed.emit()
            self.serial_detail = f"Đã nhận snapshot A45 #{result['sample_seq']} ({len(result['values'])} kênh)."
        self.message = self.serial_detail
        self.changed.emit()

    def _serial_read_finished(self, result, error):
        if self.closed or self.connection_adapter != 'rtu':
            return
        self.serial_read_pending = False
        self.serial_result = result if not error else None
        self.serial_detail = error or f"Đã nhận {len(result['values'])} thanh ghi từ slave {result['slave']}."
        self.message = self.serial_detail
        self.changed.emit()

    def _uart_received(self, data):
        if self.closed or self.connection_adapter != 'uart':
            return
        self.uart_received_bytes += len(data)
        self.uart_last_hex = data[-128:].hex(' ').upper()
        self.serial_detail = f'UART: đã nhận {self.uart_received_bytes} byte. Chưa diễn giải giao thức.'
        self.changed.emit()

    def available_serial_ports(self):
        from src.communication import available_serial_ports
        return available_serial_ports()

    def disconnect_device(self):
        self.loop_check = None
        if self.tool['image'] is not None or self.tool['queue']:
            self.tool.update(image=None, queue=[], message='Đã ngắt kết nối: trạng thái đầu ra chưa biết.')
            self.tool_changed.emit()
        if self.paused:
            # Outputs were already returned to the safe state when pausing.
            self.session["events"].append({"at": utc_now(), "event": "disconnect_while_paused"})
            self._finish_session(aborted=True)
        elif self.busy:
            self._fatal("Ngắt kết nối khi đang chạy")
        self._poll.stop()
        self.epoch += 1
        self.device.cancel_bench()
        self.bench_token = None
        self.device.communication.disconnect()
        self.device.close_serial()
        self.device.close_virtual()
        self.stm32.invalidate()
        self.stm32.message = 'Đã ngắt; cần đọc lại STM32.'
        self.stm32_changed.emit()
        self.serial_result = None
        self.serial_read_pending = False
        self.stm32_background = False
        self.uart_received_bytes = 0
        self.uart_last_hex = ''
        self.connection = "Chưa kết nối"
        self._invalidate()
        self.changed.emit()

    def _poll_device(self):
        self.device.poll(self.epoch)

    def _invalidate(self):
        self.samples = {sid: replace(sample, quality="stale") for sid, sample in self.samples.items()}
        self.signal_model.refresh(self.samples)
        self.samples_changed.emit()

    def select_test(self, tid):
        self.selected_id = tid
        self.changed.emit()

    def new_session(self):
        if self.busy or self.store.busy or self.store.status.startswith("Lỗi lưu"):
            self.message = "Cần kết thúc và lưu phiên hiện tại trước."
            self.changed.emit()
            return False
        self.session = None
        self.attempt = None
        self.test = None
        self.measurement_history.clear()
        self.signal_model.refresh(self.samples)
        self.message = "Sẵn sàng tạo phiên mới · MÔ PHỎNG"
        self.changed.emit()
        return True

    def start(self, confirm_real=False):
        """``confirm_real``: the operator confirmed the real-hardware run."""
        if not self.can_start:
            return False
        if self.connection == READY_REAL:
            blockers = self.real_run_blockers()
            if blockers:
                self.message = "Chưa được chạy trên mạch thật: " + " · ".join(blockers)
                self.changed.emit()
                return False
            if not confirm_real:
                self.message = "Cần người vận hành xác nhận trước khi chạy trên mạch thật."
                self.changed.emit()
                return False
        if self.mode != Mode.SELF and not self.serial_number:
            self.message = "Nhập số serial của khối cần kiểm tra."
            self.changed.emit()
            return False
        if self.store.status.startswith("Lỗi lưu"):
            self.message = "Lưu lại phiên trước khi tiếp tục."
            self.changed.emit()
            return False
        if self.session and self.mode != Mode.MANUAL:
            self.message = "Tạo phiên mới để chạy lại quy trình."
            self.changed.emit()
            return False
        selected = [t for t in self.tests if self.mode != Mode.MANUAL or t["id"] == self.selected_id]
        if not selected:
            return False
        self.epoch += 1
        self.device.communication.discard_pending()
        self.stopping = False
        self.session = self.session or {
            "schema_version": 1, "id": str(uuid.uuid4()), "started_at": utc_now(),
            "operator": self.username, "serial": self.serial_number if self.mode != Mode.SELF else None,
            "mode": self.mode.value, "simulation": self.run_simulation, "time_scale": self.effective_time_scale,
            "adapter": self.adapter, "cpu_map": self.cpu_map.name,
            "connection": self.connection,
            "profile": deepcopy({"system": self.profile.system, "target": self.profile.target, "hardware": self.profile.hardware, "mock": self.profile.fixtures}),
            "attempts": [], "events": [], "planned": [], "processed": 0,
        }
        self.session.update(state="running", verdict="Đang chạy", ended_at=None)
        self.session["planned"].extend(t["id"] for t in selected)
        self.session["events"].append({"at": utc_now(), "event": "start", "real_hardware": not self.run_simulation,
                                       "operator_confirmed": bool(confirm_real) if not self.run_simulation else None,
                                       "scenario": self.device.communication.transport.scenario
                                       if self.run_simulation else None})
        self.device.set_simulation_time_scale(self.time_scale)
        if self.tool['image'] is not None:
            # The runner now owns the outputs; the tool must re-take control.
            self.tool.update(image=None, message='Bộ chạy bài đang điều khiển đầu ra.')
            self.tool_changed.emit()
        self.queue = list(selected)
        self.phase = "next"
        self._checkpoint()
        self._next_test()
        return True

    def _next_test(self):
        if not self.queue:
            self._finish_session()
            return
        self.test = self.queue.pop(0)
        self.step_index = 0
        self.attempt = {"id": str(uuid.uuid4()), "test_id": self.test["id"], "name": self.test["name"],
                        "started_at": utc_now(), "status": "Đang chạy", "reason": "", "measurements": [], "cleanup_confirmed": False}
        self.session["attempts"].append(self.attempt)
        latest = {a["test_id"]: a["status"] for a in self.session["attempts"][:-1]}
        dependencies = self.test["dependencies"]
        if any(latest.get(dep) != "PASS" for dep in dependencies):
            self._skip("SKIPPED", "Bài phụ thuộc chưa PASS: " + ", ".join(dependencies))
            return
        issues = specification_issues(self.test)
        if issues:
            self._skip("BLOCKED", "; ".join(issues))
            return
        unsupported = stm32_unsupported(self.profile, self.test)
        if unsupported:
            # Never send part of a stimulus the CPUv1.0 map cannot complete.
            self._skip("BLOCKED", "Phần cứng CPUv1.0 chưa đáp ứng: " + "; ".join(unsupported))
            return
        if self.test["independence"] == "unknown" and any(a["status"] == "FAIL" for a in self.session["attempts"][:-1]):
            self._skip("BLOCKED", "Chưa xác minh tính độc lập sau bài FAIL")
            return
        self._issue("prepare")

    def _skip(self, status, reason):
        self.attempt.update(status=status, reason=reason, ended_at=utc_now())
        self._count_attempt()
        self.message = f"{self.test['id']} · {reason}"
        self._checkpoint()
        self.phase = "next"
        self.wait_until = time.monotonic() + .08
        self.changed.emit()

    def _count_attempt(self):
        if self.attempt and not self.attempt.get("completed", False):
            self.attempt["completed"] = True
            self.session["processed"] += 1

    def _clear_manual_request(self):
        if self.manual_request is not None:
            self.manual_request = None
            self.manual_input_changed.emit()

    def _manual_checks(self, step):
        """Checks the operator enters by hand (stm32 ``manual`` inputs)."""
        if self.adapter != "stm32":
            return []
        inputs = self.profile.hardware["stm32_io"]["inputs"]
        return [c for c in step["checks"] if inputs.get(c["signal"], {}).get("kind") == "manual"]

    def _request_manual(self, step, checks):
        inputs = self.profile.hardware["stm32_io"]["inputs"]
        self.phase = "awaiting_input"
        # The bench readings of this step were taken now. Freeze them: the
        # operator may take minutes, after which they would count as stale.
        # They are judged at their own capture time, never re-read or reused.
        self._manual_frozen = (time.monotonic(), {c["signal"]: self.samples.get(c["signal"])
                                                  for c in step["checks"] if c not in checks})
        self.manual_request = {
            "token": self.token, "test_id": self.test["id"], "step_id": step["id"], "title": step["title"],
            "fields": [{"signal": c["signal"], "label": self.definitions[c["signal"]]["label"], "unit": c["unit"],
                        "nominal": c["nominal"], "tolerance": c["tolerance"],
                        "prompt": inputs[c["signal"]].get("prompt", "")} for c in checks]}
        self.message = (f"{self.test['id']} / {step['id']} · Chờ người vận hành nhập "
                        + ", ".join(f["label"] for f in self.manual_request["fields"]))
        self.manual_input_changed.emit()

    def submit_manual(self, values):
        """Operator entry for the pending request: ``{signal: number | None}``.

        Empty (None/missing) records the nominal value with quality "default"
        so the report says it was not measured.
        """
        request = self.manual_request
        if self.phase != "awaiting_input" or request is None or request["token"] != self.token:
            return False
        now = time.monotonic()
        samples = {}
        for field in request["fields"]:
            value = values.get(field["signal"])
            if value is None:
                samples[field["signal"]] = Sample(field["nominal"], now, "default", "manual-default")
            elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                samples[field["signal"]] = Sample(float(value), now, "valid", "manual")
            else:
                raise ValueError(f"Giá trị nhập cho {field['label']} không hợp lệ.")
        self.samples.update(samples)
        self.signal_model.refresh(self.samples)
        self.samples_changed.emit()
        self._clear_manual_request()
        self.phase = "sampling"
        measured_at, frozen = self._manual_frozen
        self._evaluate_step(now, judged={sid: (sample, measured_at) for sid, sample in frozen.items()})
        self.changed.emit()
        return True

    def _issue(self, operation):
        self._clear_manual_request()
        self.token = str(uuid.uuid4())
        self.confirmed = None
        self.phase = operation + "_ack"
        self.deadline = time.monotonic() + OPERATION_TIMEOUT_MS / 1000
        if self.adapter == "stm32":
            self._issue_stm32(operation)
            return
        if operation == "prepare":
            self.message = f"{self.test['id']} · Chuẩn bị trạng thái mô phỏng"
            self.device.prepare(self.token, self.epoch)
        elif operation == "apply":
            step = self.test["steps"][self.step_index]
            self.message = f"{self.test['id']} / {step['id']} · {step['title']}"
            self._invalidate()
            self.device.apply(self.test, step, self.token, self.epoch)
        else:
            self.message = "Đang yêu cầu dừng / xác nhận kết thúc"
            self.device.finish(self.token, self.epoch)
        self.changed.emit()

    def _sequence(self, name):
        return self.profile.target["sequences"][name]["actions"]

    def _issue_stm32(self, operation):
        """Same phases as the mock runner, carried by the two STM32 banks."""
        self.bench_token = self.token
        try:
            if operation == "prepare":
                where = "MÔ PHỎNG" if self.run_simulation else "COM THẬT"
                self.message = f"{self.test['id']} · Đọc STM32, ghi trạng thái an toàn và chuẩn bị · {where}"
                count = self.device.bench_prepare(self.token, self._sequence(self.test["preparation"]),
                                                  self.run_simulation)
            elif operation == "apply":
                step = self.test["steps"][self.step_index]
                self.message = f"{self.test['id']} / {step['id']} · {step['title']}"
                self._invalidate()
                count = self.device.bench_apply(self.token, step["actions"], self.run_simulation)
            else:
                self.message = "Đang ghi trạng thái kết thúc / an toàn"
                count = self.device.bench_finish(self.token, self._sequence(self.test["cleanup"]),
                                                 self.run_simulation)
        except ValueError as error:
            self.bench_token = None
            self._fatal(str(error))
            return
        # One budget per planned transaction; no transaction is ever retried.
        self.deadline = time.monotonic() + OPERATION_TIMEOUT_MS / 1000 + .5 * count
        self.changed.emit()

    def _measure_stm32(self, now):
        step = self.test["steps"][self.step_index]
        manual = self._manual_checks(step)
        signals = [c["signal"] for c in step["checks"] if c not in manual]
        if not signals:
            return  # Hold step or operator entry only: nothing to read.
        self.bench_token = str(uuid.uuid4())
        try:
            count = self.device.bench_measure(self.bench_token, signals, self.run_simulation)
        except ValueError as error:
            self.bench_token = None
            self._fatal(str(error))
            return
        self.deadline = now + OPERATION_TIMEOUT_MS / 1000 + .5 * count

    def _bench_completed(self, operation, token, result, error):
        if self.closed or token != self.bench_token:
            return
        self.bench_token = None
        if operation == "connect":
            simulated = result["simulation"] if result else self.run_simulation
            slave = self.device.io_map.slave
            if error:
                self.connection = ("Lỗi kết nối mô phỏng STM32" if simulated
                                   else f"Không có phản hồi STM32 (slave {slave})")
                self.message = error if simulated else (
                    f"{error} · Kiểm tra: CPU đã cấp nguồn; slave ID = 8 + công tắc ID trên bo CPU "
                    f"(profile đang dùng {slave}, hardware.json → stm32_io.slave); dây RS485 A/B; baud 115200 8N1.")
            elif simulated:
                self.connection = READY_SIMULATION
                self._store_bench_samples(result)
                self.message = ("MÔ PHỎNG · STM32 giả lập đã trả lời FC03 qua COM ảo (khung Modbus RTU + CRC). "
                                f"Bản đồ {self.cpu_map.name}; ánh xạ phần cứng là giả định; MCU không có tín hiệu bảo vệ.")
            else:
                self.connection = READY_REAL
                self.loop_check = None
                self._store_bench_samples(result)
                self.message = (f"COM THẬT · CPU slave {slave} đã trả lời FC03 ({self.cpu_map.name}). "
                                "Chạy được tự kiểm tra; bài đo thật cần ánh xạ đã đo kiểm và D02 đạt.")
            self.changed.emit()
            return
        if error:
            self._fatal(error)
            return
        if operation == "measure":
            self._store_bench_samples(result)
        elif self.attempt is not None:
            step = self.test["steps"][self.step_index]["id"] if operation == "apply" else operation
            self.attempt.setdefault("transactions", []).append({
                "at": utc_now(), "operation": operation, "step_id": step, "writes": result["writes"],
                "note": "ACK: STM32 đã nhận lệnh ghi; chưa xác nhận đầu ra vật lý."})
            self.phase = operation + "_confirm"
            self.confirmed = token  # Receipt only; outputs are judged by measurements.
        self.changed.emit()

    def _store_bench_samples(self, result):
        source = "stm32-sim" if result["simulation"] else "stm32"
        for sid, value in result["values"].items():
            self.samples[sid] = Sample(value, result["timestamp"], "valid", source)
        self.signal_model.refresh(self.samples)
        self.samples_changed.emit()

    def _stm32_snapshot(self, result):
        """Show the runner's latest DI read in the two-bank dialog (view only)."""
        try:
            words = register_words(result["values"])
        except (ValueError, KeyError):
            return
        self.stm32.source = (bool(result["simulation"]), result["slave"])
        self.stm32.mod_buf_to_read[:] = [0] + words
        self.stm32.received_at = result["timestamp"]
        self.stm32.read_valid = True
        self.stm32.message = "DI do bộ chạy bài đọc (FC03); thời điểm lấy mẫu trong MCU chưa xác định."
        self.stm32_changed.emit()

    def _received(self, request, payload, error):
        if self.closed or request.epoch != self.epoch:
            return
        if error:
            self._fatal(error)
            return
        if request.operation == "connect":
            self.connection = "Đang xác minh mô phỏng"
            self.samples = {}
            self._poll.start()
            self._poll_device()
        elif request.operation == "snapshot":
            try:
                self.samples = self.device.decode(payload)
            except ValueError as exc:
                self._fatal(str(exc))
                return
            self.confirmed = payload.get("confirmed")
            self.connection = "Sẵn sàng · MÔ PHỎNG"
            fault_id = self.profile.system.get("status_signals", {}).get("fault")
            if self.busy and self.samples.get(fault_id, Sample()).value == 1:
                self._fatal("Lỗi bảo vệ; chuỗi đã gián đoạn")
                return
            self.signal_model.refresh(self.samples)
            self.samples_changed.emit()
        elif request.operation in ("prepare", "apply", "finish"):
            # Only the exact current token can acknowledge this operation.
            if request.payload.get("token") == self.token:
                self.phase = request.operation + "_confirm"
        self.changed.emit()

    def _tick(self):
        if self.closed:
            return
        now = time.monotonic()
        if self.stm32.read_valid and (now - self.stm32.received_at) * 1000 > READ_STALE_MS:
            self.stm32.read_valid = False
            self.stm32_changed.emit()
        expired = False
        for sid, sample in list(self.samples.items()):
            if sample.quality == "valid" and (now - sample.timestamp) * 1000 > self.definitions[sid]["stale_ms"]:
                self.samples[sid] = replace(sample, quality="stale")
                expired = True
        if expired:
            self.samples_changed.emit()
            self.changed.emit()
        self.signal_model.refresh(self.samples)
        if not self.busy:
            return
        if self.phase.endswith(("_ack", "_confirm")) and now > self.deadline:
            self._fatal("Hết thời hạn xác nhận thao tác; trạng thái đầu ra chưa xác định")
            return
        if self.phase == "next" and now >= self.wait_until:
            self._next_test()
        elif self.phase.endswith("_confirm") and self.confirmed == self.token:
            if self.phase == "prepare_confirm":
                if self.adapter == "stm32":
                    self._remember_requests(self._sequence(self.test["preparation"]), "chuẩn bị")
                self._issue("apply")
            elif self.phase == "apply_confirm":
                step = self.test["steps"][self.step_index]
                self._remember_requests(step["actions"], step["id"])
                self.phase = "settling"
                self.wait_until = now + self.test["steps"][self.step_index]["wait_ms"] / 1000 / self.effective_time_scale
            else:
                self.attempt["cleanup_confirmed"] = True
                self.attempt["ended_at"] = utc_now()
                if self.stopping:
                    self.attempt["status"] = "ABORTED"
                    self._count_attempt()
                elif self.attempt.get("paused"):
                    # Interrupted attempt is kept for traceability but not
                    # counted; the test reruns from its start on resume.
                    self.attempt["status"] = "PAUSED"
                    self.attempt.pop("provisional_status", None)
                    self.queue.insert(0, self.test)
                else:
                    self.attempt["status"] = self.attempt.pop("provisional_status", "PASS")
                    self._count_attempt()
                    if self.attempt["status"] == "FAIL" and self.test.get("stop_on_fail"):
                        # e.g. wrong supply current: likely a short; do not
                        # stimulate the unit further. Outputs are already safe.
                        self.queue.clear()
                        self.session["stopped_by"] = self.test["id"]
                        self.session["events"].append({"at": utc_now(), "event": "stop_on_fail",
                                                       "test_id": self.test["id"]})
                        self.attempt["reason"] = "FAIL ở bài nguồn: dừng cả lượt, đầu ra đã về an toàn"
                self._checkpoint()
                if self.stopping:
                    self._finish_session(aborted=True)
                elif self.pause_requested:
                    self._enter_pause()
                    return
                else:
                    self._next_test()
        elif self.phase == "settling":
            scale = self.effective_time_scale
            remaining = max(0, (self.wait_until - now) * scale)
            self.message = f"{self.test['id']} / {self.test['steps'][self.step_index]['id']} · Chờ ổn định {remaining:.1f} s tiêu chuẩn (×{scale:g})"
            if now >= self.wait_until:
                self.phase = "sampling"
                self.capture_after = now
                self.deadline = now + OPERATION_TIMEOUT_MS / 1000
                if self.adapter == "stm32":
                    self._measure_stm32(now)
        elif self.phase == "sampling":
            step = self.test["steps"][self.step_index]
            manual = self._manual_checks(step)
            if all(self.samples.get(c["signal"], Sample()).timestamp >= self.capture_after
                   for c in step["checks"] if c not in manual):
                if manual:
                    self._request_manual(step, manual)  # Outputs stay applied while the operator measures.
                else:
                    self._evaluate_step(now)
            elif now >= self.deadline:
                self._fatal("Không có mẫu mới hợp lệ sau thời gian ổn định")
        self.changed.emit()

    def _remember_requests(self, actions, step_id):
        """Keep the last requested value per command signal for display only.

        Status 'ACK' = the device acknowledged receipt; it does not confirm the
        physical output (outputs are judged only by measurements).
        """
        at = datetime.now().strftime("%H:%M:%S")
        for action in actions:
            if action["value"] is None:
                self.measurement_history.pop(action["signal"], None)  # Contact opened.
                continue
            self.measurement_history[action["signal"]] = {
                "value": action["value"], "status": "ACK", "test_id": self.test["id"], "step_id": step_id,
                "at": at, "source": "request"}

    def _evaluate_step(self, now, judged=None):
        """``judged``: {signal: (sample, time)} for readings frozen before an
        operator entry; each is judged at its own capture time."""
        step = self.test["steps"][self.step_index]
        judged = judged or {}
        for check in step["checks"]:
            sample, at = judged.get(check["signal"], (self.samples.get(check["signal"]), now))
            status, reason = evaluate(check, sample, at, self.definitions[check["signal"]]["stale_ms"])
            if sample is not None and sample.quality == "default" and status != "ERROR":
                reason += " · mặc định, chưa đo (không nhập)"
                self.attempt["defaults_used"] = True
            self.attempt["measurements"].append({**check, "step_id": step["id"], "step_title": step["title"],
                "value": sample.value if sample else None, "quality": sample.quality if sample else "unknown",
                "timestamp": utc_now(), "status": status, "reason": reason})
            if status != "ERROR":
                self.measurement_history[check["signal"]] = {
                    "value": sample.value, "status": status, "test_id": self.test["id"], "step_id": step["id"],
                    "at": datetime.now().strftime("%H:%M:%S"), "source": sample.source}
            if (self.adapter == "stm32" and self.device.io_map.inputs.get(check["signal"], {}).get("kind")
                    == "loop_probe"):
                # Remembered for this connection: gates real-hardware test runs.
                self.loop_check = {"value": sample.value if sample else None, "status": status,
                                   "simulation": self.run_simulation, "at": utc_now()}
            if status == "ERROR":
                self._fatal(reason)
                return
        self.step_index += 1
        if self.step_index < len(self.test["steps"]):
            self._issue("apply")
        else:
            statuses = [m["status"] for m in self.attempt["measurements"]]
            self.attempt["provisional_status"] = "FAIL" if "FAIL" in statuses else "BLOCKED" if "Chưa đánh giá" in statuses else "PASS"
            self._issue("finish")

    def pause(self):
        """Pause safely, not just visually.

        Between tests the pause is immediate (outputs are already in the
        cleanup/safe state). During a test the in-flight transaction finishes,
        then the cleanup/safe-state sequence runs; the attempt is kept as
        PAUSED and the same test reruns from its start on resume. A test that
        is already finishing completes normally before pausing.
        """
        if not self.can_pause:
            return False
        self.pause_requested = True
        self.session["events"].append({"at": utc_now(), "event": "pause_requested"})
        if self.phase == "next":
            self._enter_pause()
        elif not self.phase.startswith("finish"):
            self.attempt.update(paused=True, reason="Tạm dừng; bài sẽ chạy lại từ đầu khi tiếp tục")
            self._issue("finish")
            self.message = f"{self.test['id']} · Đang tạm dừng: đưa đầu ra về trạng thái an toàn…"
        self.changed.emit()
        return True

    def _enter_pause(self):
        self.phase = "paused"
        self.pause_requested = False
        self.session["state"] = "paused"
        self.session["events"].append({"at": utc_now(), "event": "paused"})
        rerun = f" · {self.queue[0]['id']} sẽ chạy lại từ đầu" if self.queue else ""
        self.message = "Đã tạm dừng · đầu ra đã về trạng thái an toàn" + rerun
        self._checkpoint()
        self.changed.emit()

    def resume(self):
        if not self.paused or self.closed or self.shutdown_requested:
            return False
        if self.connection not in READY_STATES:
            self.message = "Chưa thể tiếp tục: giá thử chưa sẵn sàng."
            self.changed.emit()
            return False
        self.session["state"] = "running"
        self.session["events"].append({"at": utc_now(), "event": "resumed"})
        self.phase = "next"
        self.wait_until = time.monotonic()
        self.message = "Tiếp tục kiểm tra"
        self._checkpoint()
        self.changed.emit()
        return True

    def stop(self):
        if not self.busy or self.stopping:
            return
        self.stopping = True
        self.queue.clear()
        self.session["state"] = "stopping"
        self.session["events"].append({"at": utc_now(), "event": "stop_requested"})
        if self.phase in ("next", "paused"):
            self._finish_session(aborted=True)
            return
        self.attempt.update(status="ABORTED", reason="Người vận hành yêu cầu dừng")
        self._issue("finish")

    def _fatal(self, reason):
        self.message = reason + " · Không tự khôi phục phiên"
        self.connection = "Lỗi / chưa xác nhận trạng thái"
        # No automatic safe-state write after an error: the link state is
        # unknown and hardware commands are never resent automatically.
        self.device.cancel_bench()
        self.bench_token = None
        self._clear_manual_request()
        self.pause_requested = False
        self.device.communication.disconnect()
        self._poll.stop()
        self._invalidate()
        if self.busy and self.session:
            if self.attempt:
                self.attempt.update(status="ERROR", reason=reason, ended_at=utc_now(), cleanup_confirmed=False)
                self._count_attempt()
            self.session["events"].append({"at": utc_now(), "event": "error", "detail": reason})
            self.session.update(state="interrupted", verdict="ERROR", ended_at=utc_now())
            self.queue.clear()
            self.phase = "idle"
            self._checkpoint()
        if self.shutdown_requested:
            self._close()
        self.changed.emit()

    def _finish_session(self, aborted=False):
        self.pause_requested = False
        statuses = [a["status"] for a in self.session["attempts"] if a["status"] != "PAUSED"]
        verdict = "ABORTED" if aborted else "ERROR" if "ERROR" in statuses else "FAIL" if "FAIL" in statuses else "Chưa đầy đủ" if any(s != "PASS" for s in statuses) else "PASS"
        defaults = any(a.get("defaults_used") for a in self.session["attempts"])
        self.session.update(state="finished", verdict=verdict, ended_at=utc_now(), defaults_used=defaults)
        self.phase = "idle"
        notes = ""
        if self.session.get("stopped_by"):
            notes += f" · Dừng cả lượt vì {self.session['stopped_by']} FAIL"
        if defaults:
            notes += " · Có giá trị mặc định chưa đo"
        where = "MÔ PHỎNG" if self.session.get("simulation", True) else "COM THẬT"
        self.message = f"Kết thúc · {verdict}{notes} · Kết quả {where}"
        self._checkpoint()
        if self.shutdown_requested:
            self._close()
        self.changed.emit()

    def _checkpoint(self):
        if self.session:
            self.store.save(deepcopy(self.session))

    def save_again(self):
        self._checkpoint()

    def shutdown(self):
        self.shutdown_requested = True
        self.set_monitor_simulation(False)
        if self.busy:
            self.stop()
        else:
            self._close()

    def _close(self):
        if self.closed:
            return
        self._poll.stop()
        self.device.cancel_bench()
        self.bench_token = None
        self.device.close_serial()
        self.device.close_virtual()
        self.stm32.invalidate()
        self.stm32_changed.emit()
        self.device.communication.disconnect()
        if self.store.busy:
            self.connection = "Đang lưu trước khi đóng"
            self.changed.emit()
            return
        if self.store.status.startswith("Lỗi lưu"):
            self.shutdown_requested = False
            self.connection = "Chưa kết nối"
            self.message = "Chưa đóng vì kết quả chưa lưu được. Dùng Lưu lại kết quả rồi đóng lại."
            self.changed.emit()
            return
        self.closed = True
        self._tick_timer.stop()
        self._poll.stop()
        self.device.communication.close()
        # All queued checkpoints have finished before allowing the window to close.
        self.store.changed.disconnect(self._save_changed)
        self.store.close()
        self.store.deleteLater()
        self.shutdown_ready.emit()
