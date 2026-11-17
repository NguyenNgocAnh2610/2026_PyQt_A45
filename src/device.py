"""Semantic bench operations; no UI state or verdicts."""
from collections import deque
import secrets
import time
from PySide6.QtCore import QObject, Signal, QTimer

from src.communication import Communication, SerialConnection
from src.protocol import decode_snapshot, WireCodec, encode_frame
from src.protocol import stm32_write_words, make_read_unit, register_words, Stm32IoMap
from src.common.stm32 import DEFAULT_SLAVE, READ_COUNT
from src.simulator import Stm32Simulator


class Device(QObject):
    controller_completed = Signal(str, object, str)
    stm32_completed = Signal(str, object, str)
    # Test-runner sequences over the two STM32 banks: operation, token, result, error.
    bench_completed = Signal(str, str, object, str)
    stm32_snapshot = Signal(object)

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.communication = Communication(profile, self)
        self.serial_connection = SerialConnection(self)
        hardware = profile.hardware
        self.io_map = Stm32IoMap(hardware['stm32_io']) if hardware.get('adapter') == 'stm32' else None
        self.stm32_simulator = Stm32Simulator(io_map=self.io_map, cases=profile.fixtures.get('stm32_cases', ()))
        # DO words the MCU has ACKed for the runner. A missing address means
        # unknown (never written, or a write failed/was cancelled).
        self.bench_image = {}
        self._bench = None
        self._bench_timer = QTimer(self)
        self._bench_timer.setSingleShot(True)
        self._bench_timer.timeout.connect(self._bench_step)
        self._stm32_request = None
        self._stm32_timer = QTimer(self)
        self._stm32_timer.setSingleShot(True)
        self._stm32_timer.timeout.connect(self._stm32_simulate)
        self.serial_connection.read_finished.connect(lambda result, error: self._stm32_received('read', result, error))
        self.serial_connection.write_finished.connect(lambda result, error: self._stm32_received('write', result, error))
        self.physical_codec = WireCodec(profile)
        self._controller_request = None
        self._controller_sequence = 0
        self._controller_session = 0
        self._controller_node = None
        self.serial_connection.wire_finished.connect(self._controller_received)
        self.serial_connection.status_changed.connect(self._controller_link_changed)
        self.signals = {s["id"] for s in profile.signals}

    def connect_device(self, epoch):
        self.communication.use_simulation()
        return self.communication.submit("connect", epoch=epoch)

    def connect_controller(self, node, epoch):
        """Firmware integration hook; same prepare/apply/poll/finish API afterwards.

        The UI recipe runner remains simulation-only until electrical operation
        and safety interlocks have been verified on the actual bench.
        """
        self.communication.use_serial(self.serial_connection, node)
        return self.communication.submit('connect', epoch=epoch)

    def open_serial(self, settings):
        self.serial_connection.open(settings)

    def read_registers(self, slave, function, address, count):
        self.serial_connection.read_registers(slave, function, address, count)

    def close_serial(self):
        self.cancel_stm32()
        self.serial_connection.close()

    def cancel_stm32(self, reason='Giao dịch đã hủy; kết quả lệnh đang chờ chưa biết, không tự gửi lại.'):
        self._stm32_timer.stop()
        pending, self._stm32_request = self._stm32_request, None
        if pending is None:
            return
        if pending['owner'] == 'bench':
            self._forget_write(pending)
            self._bench_fail(reason)
        else:
            self.stm32_completed.emit(pending['operation'], None, reason)

    def read_stm32(self, slave=DEFAULT_SLAVE, simulation=True):
        if self._bench is not None:
            raise ValueError('Bộ chạy bài đang dùng STM32.')
        self._request_stm32('read', slave, simulation)

    def write_stm32(self, address, values, slave=DEFAULT_SLAVE, simulation=True):
        if self._bench is not None:
            raise ValueError('Bộ chạy bài đang dùng STM32.')
        words = stm32_write_words(address, values)
        self._request_stm32('write', slave, simulation, int(address), words)

    def _request_stm32(self, operation, slave, simulation, address=1, values=None, owner='diag'):
        make_read_unit(slave, 3, 1, READ_COUNT - 1)
        if self._stm32_request is not None:
            raise ValueError('Đang chờ giao dịch STM32.')
        self._stm32_request = dict(operation=operation, slave=slave, simulation=simulation,
                                   address=address, values=values, owner=owner)
        try:
            if simulation:
                delay = 30
                if owner == 'bench':
                    scenario = self.communication.transport.scenario
                    stage = self._bench['operation'] if self._bench else ''
                    if (scenario, stage) in (('timeout', 'apply'), ('stop_timeout', 'finish')):
                        return  # Simulated silence: the runner deadline decides, no retry.
                    delay = 350 if scenario == 'slow' else 30
                self._stm32_timer.start(delay)
            elif operation == 'read':
                self.serial_connection.read_registers(slave, 3, 1, READ_COUNT - 1)
            else:
                self.serial_connection.write_registers(slave, address, values)
        except ValueError:
            self._stm32_request = None
            raise

    def _stm32_simulate(self):
        pending = self._stm32_request
        if pending is None:
            return
        result, error = None, ''
        try:
            if (pending['owner'] == 'bench' and self.communication.transport.scenario == 'disconnect'
                    and self._bench and self._bench['operation'] == 'measure'):
                raise ValueError('Mất liên lạc với STM32 khi đang đo (mô phỏng).')
            if pending['operation'] == 'read':
                result = dict(slave=pending['slave'], address=1, function=3,
                              values=self.stm32_simulator.read(pending['slave']), timestamp=time.monotonic())
            else:
                self.stm32_simulator.write(pending['slave'], pending['address'], pending['values'])
                result = dict(pending, timestamp=time.monotonic())
        except ValueError as exc:
            error = str(exc)
        self._stm32_received(pending['operation'], result, error, simulation=True)

    def _stm32_received(self, operation, result, error, simulation=False):
        pending = self._stm32_request
        if pending is None or pending['operation'] != operation or pending['simulation'] != simulation:
            return
        self._stm32_request = None
        if pending['owner'] == 'bench':
            self._bench_result(pending, result, error)
        else:
            self.stm32_completed.emit(operation, result, error)

    # ---- Test-runner sequences (hardware.adapter == 'stm32') ----------------
    # Each sequence runs its transactions strictly one at a time, never
    # retries, and stops at the first error. Completion means the MCU ACKed the
    # writes / answered the reads; it does NOT confirm the physical outputs.

    def set_simulation_time_scale(self, scale):
        self.stm32_simulator.time_scale = scale

    def _require_io(self):
        if self.io_map is None:
            raise ValueError('Cấu hình phần cứng không dùng adapter stm32.')
        return self.io_map

    def bench_connect(self, token, simulation=True):
        """FC03 only: proves the slave answers; writes nothing."""
        self._require_io()
        return self._bench_begin('connect', token, [('read', [])], simulation)

    def bench_prepare(self, token, actions, simulation=True):
        io = self._require_io()
        safe = io.safe_image()
        target = io.apply(safe, actions)  # Validate before anything is sent.
        # Known all-off state first (Mode=1 written first), then preparation.
        return self._bench_begin('prepare', token, [('read', []), ('image', safe, True),
                                                    ('image', target, False)], simulation)

    def bench_apply(self, token, actions, simulation=True):
        io = self._require_io()
        if not set(io.safe_image()) <= set(self.bench_image):
            raise ValueError('Trạng thái DO trên STM32 chưa xác định; cần chuẩn bị lại.')
        target = io.apply(self.bench_image, actions)
        return self._bench_begin('apply', token, [('image', target, False)], simulation)

    def bench_measure(self, token, signals, simulation=True):
        io = self._require_io()
        ops = []
        for mux, group in io.groups(signals):
            if mux is not None:
                ops += [('mux', mux), ('wait', io.mux_settle_ms)]
            ops.append(('read', group))
        return self._bench_begin('measure', token, ops, simulation)

    def bench_finish(self, token, actions, simulation=True):
        """Cleanup actions, then safe_state. Replaces an unfinished sequence
        (operator stop); a transaction already on the wire completes first."""
        io = self._require_io()
        ops = [('image', io.apply(io.safe_image(), actions), False)] if actions else []
        ops.append(('image', io.safe_image(), False))
        return self._bench_begin('finish', token, ops, simulation, replace=True)

    def cancel_bench(self):
        """Abandon the runner sequence silently; DO state becomes unknown."""
        self._bench = None
        self._bench_timer.stop()
        self.bench_image = {}
        if self._stm32_request is not None and self._stm32_request['owner'] == 'bench':
            self._stm32_timer.stop()
            self._stm32_request = None  # A late real reply is ignored.

    def _bench_begin(self, operation, token, ops, simulation, replace=False):
        if self._bench is not None and not replace:
            raise ValueError('Đang chờ chuỗi giao dịch STM32 trước.')
        if self._stm32_request is not None and self._stm32_request['owner'] != 'bench':
            raise ValueError('Đang chờ giao dịch STM32 chẩn đoán.')
        self._bench_timer.stop()
        self._bench = dict(operation=operation, token=token, ops=deque(ops), simulation=simulation,
                           values={}, writes=[], reads=0, timestamp=None)
        self.stm32_simulator.scenario = self.communication.transport.scenario
        if self._stm32_request is None:
            self._bench_timer.start(0)  # Never complete inside the caller.
        return len(ops) + 1

    def _bench_step(self):
        seq = self._bench
        if seq is None or self._stm32_request is not None:
            return
        io = self.io_map
        while seq['ops']:
            op = seq['ops'].popleft()
            if op[0] == 'wait':
                self._bench_timer.start(int(op[1]))
                return
            if op[0] == 'mux':
                target = dict(self.bench_image)
                target[io.mux] = op[1]
                op = ('image', target, False)
            if op[0] == 'image':
                runs = Stm32IoMap.writes(None if op[2] else self.bench_image, op[1])
                seq['ops'].extendleft(reversed([('write', address, words) for address, words in runs]))
                continue
            try:
                if op[0] == 'write':
                    self._request_stm32('write', io.slave, seq['simulation'], op[1], op[2], owner='bench')
                else:
                    seq['pending_read'] = op[1]
                    self._request_stm32('read', io.slave, seq['simulation'], owner='bench')
            except ValueError as error:
                self._bench_fail(str(error))
            return
        self._bench = None
        self.bench_completed.emit(seq['operation'], seq['token'], dict(
            values=seq['values'], timestamp=seq['timestamp'], writes=seq['writes'], reads=seq['reads'],
            simulation=seq['simulation']), '')

    def _forget_write(self, pending):
        if pending['operation'] == 'write':
            for offset in range(len(pending['values'])):
                self.bench_image.pop(pending['address'] + offset, None)

    def _bench_fail(self, error):
        seq, self._bench = self._bench, None
        self._bench_timer.stop()
        if seq is not None:
            self.bench_completed.emit(seq['operation'], seq['token'], None, error)

    def _bench_result(self, pending, result, error):
        seq = self._bench
        if error:
            self._forget_write(pending)  # Executed or not is unknown.
            self._bench_fail(error)
            return
        if pending['operation'] == 'write':
            for offset, word in enumerate(pending['values']):
                self.bench_image[pending['address'] + offset] = word
            if seq is not None:
                seq['writes'].append(dict(address=pending['address'], values=list(pending['values'])))
        else:
            try:
                words = [0] + register_words(result['values'])
                if result['address'] != 1 or len(words) != READ_COUNT:
                    raise ValueError('Phản hồi không đủ mảng Modbus_DI 1–29.')
                if seq is not None:
                    for sid in seq.pop('pending_read', []):
                        seq['values'][sid] = self.io_map.decode(words, sid)
                    seq['timestamp'] = result['timestamp']
                    seq['reads'] += 1
            except (ValueError, KeyError, TypeError) as exc:
                self._bench_fail(str(exc))
                return
            self.stm32_snapshot.emit(dict(result, simulation=pending['simulation']))
        self._bench_step()

    def _controller_link_changed(self, state, detail):
        if state != 'open':
            if self._stm32_request is not None and not self._stm32_request['simulation']:
                self.cancel_stm32(detail or 'Mất kết nối COM; kết quả lệnh đang chờ chưa biết, không tự gửi lại.')
            self._controller_request = None
            self.physical_codec.boot_id = None

    def identify_controller(self, node):
        if type(node) is not int or not 1 <= node <= 247:
            raise ValueError('Chọn ID trung tâm 1–247 trong Chi tiết.')
        if self._controller_request is not None:
            raise ValueError('Đang chờ phản hồi trung tâm.')
        self._controller_session = secrets.randbits(32) or 1
        self._controller_sequence = 0
        self._controller_node = node
        self.physical_codec.boot_id = None
        self._send_controller('connect')

    def snapshot_controller(self):
        if self.physical_codec.boot_id is None:
            raise ValueError('Hãy xác minh A45 trước khi đọc trạng thái.')
        self._send_controller('snapshot')

    def _send_controller(self, operation):
        if self._controller_request is not None:
            raise ValueError('Đang chờ phản hồi trung tâm.')
        self._controller_sequence += 1
        frame = self.physical_codec.request(operation, {}, self._controller_session,
                                            self._controller_sequence, self._controller_node)
        self._controller_request = (operation, frame)
        self._controller_sent_at = time.monotonic()
        try:
            self.serial_connection.exchange_frame(encode_frame(frame))
        except ValueError:
            self._controller_request = None
            raise

    def _controller_received(self, raw, error):
        pending, self._controller_request = self._controller_request, None
        if pending is None:
            return
        operation, frame = pending
        result = None
        if not error:
            try:
                result = self.physical_codec.decode_response(raw, frame, sent_at=self._controller_sent_at)
            except ValueError as exc:
                error = str(exc)
                self.close_serial()
        self.controller_completed.emit(operation, result, error)

    def prepare(self, token, epoch):
        return self.communication.submit("prepare", {"token": token}, epoch=epoch)

    def apply(self, test, step, token, epoch):
        if step["capability"] not in self.profile.hardware["capabilities"]:
            raise ValueError("Thiết bị không hỗ trợ thao tác")
        return self.communication.submit("apply", {
            "token": token, "case": f"{test['id']}/{step['id']}", "actions": step["actions"],
        }, epoch=epoch)

    def poll(self, epoch):
        return self.communication.submit("snapshot", priority=2, epoch=epoch)

    def finish(self, token, epoch):
        self.communication.discard_pending()
        return self.communication.submit("finish", {"token": token}, priority=0, epoch=epoch)

    def decode(self, payload):
        return decode_snapshot(payload, self.signals)
