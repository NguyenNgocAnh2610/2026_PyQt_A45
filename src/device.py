"""Semantic bench operations; no UI state or verdicts."""
from collections import deque
import math
import secrets
import time
from PySide6.QtCore import QObject, Signal, QTimer

from src.communication import Communication, SerialConnection
from src.protocol import decode_snapshot, WireCodec, encode_frame
from src.protocol import stm32_write_words, make_read_unit, register_words, Stm32IoMap
from src.common.serial import SerialSettings
from src.common.stm32 import DEFAULT_SLAVE, cpu_map_for
from src.common.testing import TRANSACTION_TIMEOUT_MS
from src.simulator import Stm32Simulator, Stm32RtuSlave
from src.virtual_port import VirtualLine, VIRTUAL_PORT, create_virtual_connection


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
        self.cpu_map = cpu_map_for(hardware)
        self.io_map = (Stm32IoMap(hardware['stm32_io'], self.cpu_map)
                       if hardware.get('adapter') == 'stm32' else None)
        # Highest DO index + 1 this profile may write (firmware map, plus the
        # registers it declares as a proposed firmware extension).
        self.write_limit = self.io_map.write_count if self.io_map else self.cpu_map.write_count
        timing = profile.fixtures.get('stm32_timing', {})
        # The virtual CPU answers at the profile's slave ID, like the real one.
        sim_slave = self.io_map.slave if self.io_map else (hardware.get('serial', {}).get('slave') or DEFAULT_SLAVE)
        self.stm32_simulator = Stm32Simulator(slave=sim_slave, io_map=self.io_map,
                                              cases=profile.fixtures.get('stm32_cases', ()),
                                              loop_ms=timing.get('loop_ms', 0), cpu_map=self.cpu_map)
        # Simulation = a virtual COM port: real RTU frames to the simulated
        # slave through the same SerialConnection as the physical port.
        self.virtual_line = VirtualLine(Stm32RtuSlave(self.stm32_simulator))
        self.virtual_connection = create_virtual_connection(self, self.virtual_line)
        serial = hardware.get('serial', {})
        self.virtual_settings = SerialSettings(
            'rtu', VIRTUAL_PORT, serial.get('baudrate') or 115200, parity=serial.get('parity') or 'N',
            stop_bits=serial.get('stop_bits') or 1, timeout_ms=TRANSACTION_TIMEOUT_MS)
        self._last_write_ack = None
        # DO words the MCU has ACKed for the runner. A missing address means
        # unknown (never written, or a write failed/was cancelled).
        self.bench_image = {}
        self._bench = None
        self._bench_timer = QTimer(self)
        self._bench_timer.setSingleShot(True)
        self._bench_timer.timeout.connect(self._bench_step)
        self._stm32_request = None
        for link, simulation in ((self.serial_connection, False), (self.virtual_connection, True)):
            link.read_finished.connect(
                lambda result, error, sim=simulation: self._stm32_received('read', result, error, sim))
            link.write_finished.connect(
                lambda result, error, sim=simulation: self._stm32_received('write', result, error, sim))
        self.virtual_connection.status_changed.connect(self._virtual_link_changed)
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
        if self._stm32_request is not None and not self._stm32_request['simulation']:
            self.cancel_stm32()
        self.serial_connection.close()

    def open_virtual(self):
        """Open the virtual COM port (synchronous); no frame is sent."""
        if self.virtual_connection.state != 'open':
            self.virtual_connection.open(self.virtual_settings)
        if self.virtual_connection.state != 'open':
            raise ValueError('Không mở được cổng COM ảo.')

    def close_virtual(self):
        if self._stm32_request is not None and self._stm32_request['simulation']:
            self.cancel_stm32()
        self.virtual_connection.close()

    def _virtual_link_changed(self, state, detail):
        if state != 'open' and self._stm32_request is not None and self._stm32_request['simulation']:
            self.cancel_stm32(detail or 'COM ảo đã đóng; kết quả lệnh đang chờ chưa biết, không tự gửi lại.')

    def cancel_stm32(self, reason='Giao dịch đã hủy; kết quả lệnh đang chờ chưa biết, không tự gửi lại.'):
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
        words = stm32_write_words(address, values, self.write_limit)
        self._request_stm32('write', slave, simulation, int(address), words)

    def _request_stm32(self, operation, slave, simulation, address=1, values=None, owner='diag'):
        """One Modbus transaction on the real or the virtual COM port; the
        code path after this point is identical for both."""
        count = self.cpu_map.read_count - 1
        make_read_unit(slave, 3, 1, count)
        if self._stm32_request is not None:
            raise ValueError('Đang chờ giao dịch STM32.')
        link = self.virtual_connection if simulation else self.serial_connection
        if simulation:
            self.open_virtual()
            self.virtual_line.scenario = self.communication.transport.scenario
            self.virtual_line.stage = self._bench['operation'] if owner == 'bench' and self._bench else None
        self._stm32_request = dict(operation=operation, slave=slave, simulation=simulation,
                                   address=address, values=values, owner=owner)
        try:
            if operation == 'read':
                link.read_registers(slave, 3, 1, count)
            else:
                link.write_registers(slave, address, values)
        except ValueError:
            self._stm32_request = None
            raise

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
        """FC03 per MUX group; ``loop_probe`` inputs poll FC03 for a while.
        ``manual`` inputs are entered by the operator, never read here."""
        io = self._require_io()
        ops = []
        probes = [s for s in signals if io.input_kind(s) == 'loop_probe']
        readable = [s for s in signals if s not in probes and io.input_kind(s) != 'manual']
        for mux, group in io.groups(readable):
            if mux is not None:
                ops.append(('mux', mux))
            # DI shows new outputs only after the MCU loop ran them (di_update_ms)
            # plus the analog settle, counted from the last write ACK.
            ops += [('after_ack', io.di_update_ms + io.mux_settle_ms), ('read', group)]
        ops += [('probe', sid) for sid in probes]
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
            self._stm32_request = None  # A late reply is ignored.

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
            if op[0] == 'after_ack':
                # Wait until op[1] ms have passed since the last write ACK.
                due = (self._last_write_ack or 0) + op[1] / 1000
                remaining = due - time.monotonic()
                if remaining > 0:
                    self._bench_timer.start(math.ceil(remaining * 1000))
                    return
                continue
            if op[0] == 'mux':
                target = dict(self.bench_image)
                target[io.mux] = op[1]
                op = ('image', target, False)
            if op[0] == 'image':
                # Break-before-make: open relays, wait until the MCU loop has
                # executed that write, then close the new ones.
                previous = None if op[2] else self.bench_image
                expanded = []
                for index, image in enumerate(io.phases(previous, op[1])):
                    if index:
                        expanded.append(('after_ack', io.break_ms))
                    expanded += [('write', address, words) for address, words in io.writes(previous, image)]
                    previous = image
                seq['ops'].extendleft(reversed(expanded))
                continue
            if op[0] == 'probe':
                if not self._probe_step(seq, op):
                    return
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

    def _probe_step(self, seq, op):
        """Self-test D02: poll FC03 for ``duration_ms``; the CPU loop period is
        the mean interval between reads in which ADC0–4 changed. Returns True
        when the estimate is done, False while a read is outstanding/failed."""
        sid = op[1]
        entry = self.io_map.inputs[sid]
        probe = seq.setdefault('probe', dict(end=time.monotonic() + entry['duration_ms'] / 1000,
                                             poll_ms=entry['poll_ms'], last=None, changes=[]))
        if time.monotonic() < probe['end']:
            seq['ops'].appendleft(op)
            seq['pending_probe'] = True
            try:
                self._request_stm32('read', self.io_map.slave, seq['simulation'], owner='bench')
            except ValueError as error:
                self._bench_fail(str(error))
            return False
        seq.pop('probe')
        changes = probe['changes']
        if len(changes) < 3:
            self._bench_fail('Tự kiểm tra chu kỳ CPU: ADC0–4 không đổi đủ số lần trong thời gian đo, '
                             'không ước lượng được chu kỳ vòng lặp.')
            return False
        seq['values'][sid] = round((changes[-1] - changes[0]) / (len(changes) - 1) * 1000, 1)
        seq['timestamp'] = time.monotonic()
        return True

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
            self._last_write_ack = time.monotonic()
            for offset, word in enumerate(pending['values']):
                self.bench_image[pending['address'] + offset] = word
            if seq is not None:
                seq['writes'].append(dict(address=pending['address'], values=list(pending['values'])))
        else:
            try:
                words = [0] + register_words(result['values'])
                if result['address'] != 1 or len(words) != self.cpu_map.read_count:
                    raise ValueError(f'Phản hồi không đủ mảng Modbus_DI 1–{self.cpu_map.read_count - 1}.')
                if seq is not None and seq.pop('pending_probe', False):
                    probe = seq['probe']
                    adc = tuple(words[7:12])  # ADC0_val … ADC4_val
                    if probe['last'] is not None and adc != probe['last']:
                        probe['changes'].append(result['timestamp'])
                    probe['last'] = adc
                    seq['reads'] += 1
                    self._bench_timer.start(probe['poll_ms'])
                    return
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
