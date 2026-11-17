"""Single source of truth and asynchronous, profile-driven test runner."""
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
from src.common.profiles import load_profile, specification_issues, stm32_unsupported, validate_profile
from src.common.testing import Mode, Sample, POLL_MS, OPERATION_TIMEOUT_MS, SCENARIOS, STM32_SCENARIOS
from src.common.serial import SerialSettings
from src.common.stm32 import Stm32RegisterBanks, DEFAULT_SLAVE, READ_COUNT, READ_STALE_MS
from src.protocol import stm32_write_words, decode_stm32, register_words
from src.device import Device
from src.storage import SessionStore


def evaluate(check, sample, now, stale_ms):
    """Pure verdict calculation, independent of protocol and Widgets."""
    if sample is None or sample.quality != "valid" or (now - sample.timestamp) * 1000 > stale_ms:
        return "ERROR", "Mẫu thiếu, lỗi hoặc hết hạn"
    nominal, tolerance = check.get("nominal"), check.get("tolerance")
    if nominal is None or tolerance is None:
        return "Chưa đánh giá", "Tiêu chuẩn chưa đủ giá trị/dung sai"
    lower, upper = nominal - tolerance, nominal + tolerance
    inside = lower <= sample.value <= upper or math.isclose(sample.value, lower, rel_tol=0, abs_tol=1e-10) or math.isclose(sample.value, upper, rel_tol=0, abs_tol=1e-10)
    return ("PASS", "Trong giới hạn") if inside else ("FAIL", "Ngoài giới hạn")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Backend(QObject):
    changed = Signal()
    samples_changed = Signal()
    monitor_changed = Signal()
    shutdown_ready = Signal()
    stm32_changed = Signal()

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
        self.stm32 = Stm32RegisterBanks()
        self.stm32_pending = False
        self.device.stm32_completed.connect(self._stm32_completed)
        # 'stm32': runner writes/reads the two CPUv1.0 banks; 'mock': legacy A45 v1.
        self.adapter = self.profile.hardware["adapter"]
        self.bench_token = None
        self.device.bench_completed.connect(self._bench_completed)
        self.device.stm32_snapshot.connect(self._stm32_snapshot)
        self.serial_detail = ''
        self.uart_received_bytes = 0
        self.uart_last_hex = ''
        self.device.serial_connection.status_changed.connect(self._serial_status)
        self.device.serial_connection.read_finished.connect(self._serial_read_finished)
        self.device.serial_connection.received.connect(self._uart_received)
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
    def can_start(self):
        if self.busy or self.closed or self.shutdown_requested or self.connection != "Sẵn sàng · MÔ PHỎNG":
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
                self.bench_token = str(uuid.uuid4())
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
        if state != 'open':
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
        if state == 'open':
            self.connection = f'Đã mở {self.serial_settings.port}'
            self.serial_detail = (f'{self.serial_settings.baudrate} baud · {self.serial_settings.framing}. '
                                  'Cổng đã mở; chưa xác minh phản hồi thiết bị.')
        elif state == 'connecting':
            self.connection = 'Đang mở COM…'
        elif state == 'error':
            self.connection = 'Lỗi kết nối COM'
            self._invalidate()
        else:
            self.connection = 'Chưa kết nối'
            self._invalidate()
        self.message = self.serial_detail or self.connection
        self.changed.emit()

    def stage_stm32(self, address, values):
        words = stm32_write_words(address, values)
        self.stm32.mod_buf_to_write[address:address + len(words)] = words
        self.stm32.staged.update(range(address, address + len(words)))
        self.stm32_changed.emit()

    def unstage_stm32(self, address):
        self.stm32.staged.discard(address)
        self.stm32_changed.emit()

    def select_stm32_source(self, simulation, slave):
        if self.stm32_pending:
            raise ValueError('Chờ giao dịch STM32 kết thúc trước khi đổi nguồn.')
        source = (bool(simulation), slave)
        if source != self.stm32.source:
            self.stm32.source = source
            self.stm32.invalidate()
            self.stm32.message = 'Đã đổi nguồn/Slave ID; cần đọc lại.'
            self.stm32_changed.emit()

    def request_stm32(self, *, simulation=True, slave=DEFAULT_SLAVE, address=None, count=1):
        if self.busy or self.closed or self.shutdown_requested or self.serial_read_pending:
            raise ValueError('Ứng dụng đang bận hoặc đóng.')
        if not simulation and (self.serial_state != 'open' or self.connection_adapter != 'rtu'):
            raise ValueError('Mở COM ở chế độ Modbus RTU trước khi giao tiếp STM32 thật.')
        values = None
        if address is not None:
            if type(count) is not int or count < 1:
                raise ValueError('Số thanh ghi ghi phải lớn hơn 0.')
            stm32_write_words(address, [0])  # Validate address before slicing.
            values = stm32_write_words(address, self.stm32.mod_buf_to_write[address:address + count])
            if len(values) != count or not set(range(address, address + count)) <= self.stm32.staged:
                raise ValueError('Nhập rõ giá trị cho từng thanh ghi trong vùng gửi; không tự gửi các số 0 mặc định.')
        self.select_stm32_source(simulation, slave)
        self.stm32_pending = self.serial_read_pending = True
        self.stm32.last_ack = None if values is not None else self.stm32.last_ack
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

    def _stm32_completed(self, operation, result, error):
        self.stm32_pending = self.serial_read_pending = False
        if not error and operation == 'read':
            try:
                words = register_words(result['values'])
                if result['address'] != 1 or len(words) != READ_COUNT - 1:
                    raise ValueError('Phản hồi không đủ mảng Modbus_DI 1–29.')
                decode_stm32([0] + words)
                self.stm32.mod_buf_to_read[:] = [0] + words
                self.stm32.received_at = result['timestamp']
                self.stm32.read_valid = True
                self.stm32.message = 'Đã đọc DI 1–29; thời điểm lấy mẫu trong MCU chưa xác định.'
            except (ValueError, KeyError, TypeError) as exc:
                error = str(exc)
        elif not error:
            self.stm32.last_ack = deepcopy(result)
            self.stm32.message = 'STM32 đã nhận lệnh ghi (ACK); chưa xác nhận phần cứng thực thi.'
        if error:
            self.stm32.invalidate()
            self.stm32.message = error
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
        self.stm32.invalidate()
        self.stm32.message = 'Đã ngắt; cần đọc lại STM32.'
        self.stm32_changed.emit()
        self.serial_result = None
        self.serial_read_pending = False
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

    def start(self):
        if not self.can_start:
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
            "mode": self.mode.value, "simulation": True, "time_scale": self.time_scale, "adapter": self.adapter,
            "profile": deepcopy({"system": self.profile.system, "target": self.profile.target, "hardware": self.profile.hardware, "mock": self.profile.fixtures}),
            "attempts": [], "events": [], "planned": [], "processed": 0,
        }
        self.session.update(state="running", verdict="Đang chạy", ended_at=None)
        self.session["planned"].extend(t["id"] for t in selected)
        self.session["events"].append({"at": utc_now(), "event": "start", "scenario": self.device.communication.transport.scenario})
        self.device.set_simulation_time_scale(self.time_scale)
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

    def _issue(self, operation):
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
                self.message = f"{self.test['id']} · Đọc STM32, ghi trạng thái an toàn và chuẩn bị · MÔ PHỎNG"
                count = self.device.bench_prepare(self.token, self._sequence(self.test["preparation"]))
            elif operation == "apply":
                step = self.test["steps"][self.step_index]
                self.message = f"{self.test['id']} / {step['id']} · {step['title']}"
                self._invalidate()
                count = self.device.bench_apply(self.token, step["actions"])
            else:
                self.message = "Đang ghi trạng thái kết thúc / an toàn"
                count = self.device.bench_finish(self.token, self._sequence(self.test["cleanup"]))
        except ValueError as error:
            self.bench_token = None
            self._fatal(str(error))
            return
        # One budget per planned transaction; no transaction is ever retried.
        self.deadline = time.monotonic() + OPERATION_TIMEOUT_MS / 1000 + .5 * count
        self.changed.emit()

    def _measure_stm32(self, now):
        step = self.test["steps"][self.step_index]
        self.bench_token = str(uuid.uuid4())
        try:
            count = self.device.bench_measure(self.bench_token, [c["signal"] for c in step["checks"]])
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
            if error:
                self.connection = "Lỗi kết nối mô phỏng STM32"
                self.message = error
            else:
                self.connection = "Sẵn sàng · MÔ PHỎNG"
                self._store_bench_samples(result)
                self.message = ("MÔ PHỎNG · STM32 đã trả lời FC03. Ánh xạ thanh ghi là giả định theo CPUv1.0; "
                                "MCU không có tín hiệu bảo vệ.")
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
                self.wait_until = now + self.test["steps"][self.step_index]["wait_ms"] / 1000 / self.time_scale
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
                self._checkpoint()
                if self.stopping:
                    self._finish_session(aborted=True)
                elif self.pause_requested:
                    self._enter_pause()
                    return
                else:
                    self._next_test()
        elif self.phase == "settling":
            remaining = max(0, (self.wait_until - now) * self.time_scale)
            self.message = f"{self.test['id']} / {self.test['steps'][self.step_index]['id']} · Chờ ổn định {remaining:.1f} s tiêu chuẩn (×{self.time_scale:g})"
            if now >= self.wait_until:
                self.phase = "sampling"
                self.capture_after = now
                self.deadline = now + OPERATION_TIMEOUT_MS / 1000
                if self.adapter == "stm32":
                    self._measure_stm32(now)
        elif self.phase == "sampling":
            step = self.test["steps"][self.step_index]
            if all(self.samples.get(c["signal"], Sample()).timestamp >= self.capture_after for c in step["checks"]):
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
            self.measurement_history[action["signal"]] = {
                "value": action["value"], "status": "ACK", "test_id": self.test["id"], "step_id": step_id,
                "at": at, "source": "request"}

    def _evaluate_step(self, now):
        step = self.test["steps"][self.step_index]
        for check in step["checks"]:
            sample = self.samples.get(check["signal"])
            status, reason = evaluate(check, sample, now, self.definitions[check["signal"]]["stale_ms"])
            self.attempt["measurements"].append({**check, "step_id": step["id"], "step_title": step["title"],
                "value": sample.value if sample else None, "quality": sample.quality if sample else "unknown",
                "timestamp": utc_now(), "status": status, "reason": reason})
            if status != "ERROR":
                self.measurement_history[check["signal"]] = {
                    "value": sample.value, "status": status, "test_id": self.test["id"], "step_id": step["id"],
                    "at": datetime.now().strftime("%H:%M:%S"), "source": sample.source}
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
        if self.connection != "Sẵn sàng · MÔ PHỎNG":
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
        self.session.update(state="finished", verdict=verdict, ended_at=utc_now())
        self.phase = "idle"
        self.message = f"Kết thúc · {verdict} · Kết quả MÔ PHỎNG"
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
