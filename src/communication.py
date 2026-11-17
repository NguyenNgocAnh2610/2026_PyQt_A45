"""Semantic mock queue and single-owner asynchronous UART/RTU connection.

Qt serial I/O uses its event loop; no blocking waits, polling loops or retries.
The physical connection never interprets or executes simulated bench recipes.
"""
from dataclasses import dataclass, field
import time
import secrets

from PySide6.QtCore import QObject, QTimer, Signal, QIODevice
from PySide6.QtSerialPort import QSerialPort
from PySide6.QtSerialBus import QModbusDevice, QModbusRtuSerialClient, QModbusDataUnit

from src.common.testing import TRANSACTION_TIMEOUT_MS
from src.common.serial import SerialSettings
from src.protocol import (make_read_unit, WireCodec, encode_frame, decode_frame, FrameStream,
                          frame_to_registers, registers_to_frame, register_words, validate_write_ack)
from src.simulator import SimulatedController
from src.common.wire import (MAX_FRAME, REQUEST_MAILBOX, RESPONSE_MAILBOX, COMMIT_REGISTER,
                             MODBUS_WRITE_CHUNK, MODBUS_READ_CHUNK)


class SerialConnection(QObject):
    status_changed = Signal(str, str)
    read_finished = Signal(object, str)
    write_finished = Signal(object, str)
    received = Signal(bytes)
    wire_finished = Signal(object, str)

    def __init__(self, parent=None, rtu_factory=QModbusRtuSerialClient,
                 uart_factory=QSerialPort):
        super().__init__(parent)
        self._rtu_factory = rtu_factory
        self._uart_factory = uart_factory
        self.client = None
        self.reply = None
        self.settings = None
        self.state = 'disconnected'
        self._request = None
        self._wire = None
        self._stream = FrameStream()
        self.wire_pump = QTimer(self)
        self.wire_pump.setSingleShot(True)
        self.wire_pump.timeout.connect(self._wire_step)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self._deadline_expired)

    def _status(self, state, detail=''):
        self.state = state
        self.status_changed.emit(state, detail)

    def open(self, settings):
        if not isinstance(settings, SerialSettings):
            raise ValueError('Cấu hình serial không hợp lệ.')
        self.close()
        self.settings = settings
        self._status('connecting')
        parity = {'N': QSerialPort.NoParity, 'E': QSerialPort.EvenParity,
                  'O': QSerialPort.OddParity}[settings.parity]
        bits = QSerialPort.DataBits(settings.data_bits)
        stops = QSerialPort.StopBits(settings.stop_bits)
        if settings.adapter == 'rtu':
            client = self._rtu_factory(self)
            self.client = client
            for key, value in (
                (QModbusDevice.SerialPortNameParameter, settings.port),
                (QModbusDevice.SerialBaudRateParameter, settings.baudrate),
                (QModbusDevice.SerialDataBitsParameter, bits),
                (QModbusDevice.SerialParityParameter, parity),
                (QModbusDevice.SerialStopBitsParameter, stops),
            ):
                client.setConnectionParameter(key, value)
            client.setTimeout(settings.timeout_ms)
            client.setNumberOfRetries(0)
            client.stateChanged.connect(lambda state: self._rtu_state(client, state))
            client.errorOccurred.connect(lambda error: self._rtu_error(client, error))
            self.deadline.start(settings.timeout_ms)
            if not client.connectDevice() and self.client is client:
                self._fail(client.errorString())
        else:
            client = self._uart_factory(self)
            self.client = client
            client.setPortName(settings.port)
            # Also bound raw receive memory when a source streams continuously.
            client.setReadBufferSize(4096)
            client.errorOccurred.connect(lambda error: self._uart_error(client, error))
            client.readyRead.connect(lambda: self._receive_uart(client))
            client.bytesWritten.connect(lambda _: self._flush_uart(client))
            configured = (client.setBaudRate(settings.baudrate)
                          and client.setDataBits(bits) and client.setParity(parity)
                          and client.setStopBits(stops)
                          and client.setFlowControl(QSerialPort.NoFlowControl))
            if configured and client.open(QIODevice.ReadWrite):
                if self.client is client:
                    self._status('open')
            elif self.client is client:
                self._fail(client.errorString())

    def _rtu_state(self, client, state):
        if self.client is not client:
            return
        if state == QModbusDevice.ConnectedState:
            self.deadline.stop()
            self._status('open')
        elif state == QModbusDevice.UnconnectedState:
            self._fail(client.errorString() or 'Cổng serial đã đóng.')

    def _rtu_error(self, client, error):
        if self.client is client and error in (
            QModbusDevice.ConnectionError, QModbusDevice.ConfigurationError,
        ):
            self._fail(client.errorString())

    def _uart_error(self, client, error):
        if self.client is client and error != QSerialPort.NoError:
            self._fail(client.errorString())

    def _receive_uart(self, client):
        if self.client is client:
            data = bytes(client.readAll())
            self.received.emit(data)
            if self._wire is not None:
                for raw in self._stream.feed(data):
                    if self._wire is None:
                        break
                    frame, expected = decode_frame(raw), self._wire['frame']
                    if ((frame.node, frame.opcode, frame.session, frame.sequence)
                            == (expected.node, expected.opcode, expected.session, expected.sequence)
                            and frame.flags in (1, 3)):
                        self._wire_finish(raw)

    def exchange_frame(self, raw):
        frame = decode_frame(raw)
        if frame.flags != 0 or self.state != 'open' or self.client is None:
            raise ValueError('Cần mở COM và gửi khung yêu cầu A45.')
        if self.reply is not None or self._wire is not None:
            raise ValueError('Đang có giao dịch trên cổng serial.')
        self._stream = FrameStream()
        self._wire = dict(frame=frame, raw=raw, offset=0, phase='stage',
                          words=frame_to_registers(raw), response=[])
        # Include serial wire time and all bounded mailbox stages, without retry.
        wire_ms = int((len(raw) + MAX_FRAME) * 12000 / self.settings.baudrate) + 1
        multiplier = 12 if self.settings.adapter == 'rtu' else 1
        self.deadline.start(self.settings.timeout_ms * multiplier + wire_ms)
        if self.settings.adapter == 'uart':
            self._flush_uart(self.client)
        else:
            self.wire_pump.start(0)

    def _flush_uart(self, client):
        pending = self._wire
        if self.client is not client or pending is None or self.settings.adapter != 'uart':
            return
        remaining = pending['raw'][pending['offset']:]
        if remaining:
            written = client.write(remaining)
            if self._wire is not pending:
                return
            if written < 0:
                self._fail(client.errorString())
            else:
                pending['offset'] += written

    def _wire_step(self):
        pending, client = self._wire, self.client
        if pending is None or client is None or self.reply is not None:
            return
        phase, offset = pending['phase'], pending['offset']
        if phase == 'stage':
            values = pending['words'][offset:offset + MODBUS_WRITE_CHUNK]
            unit = QModbusDataUnit(QModbusDataUnit.HoldingRegisters, REQUEST_MAILBOX + offset, values)
            write = True
        elif phase == 'commit':
            unit = QModbusDataUnit(QModbusDataUnit.HoldingRegisters, COMMIT_REGISTER, [1])
            write = True
        elif phase == 'length':
            unit = QModbusDataUnit(QModbusDataUnit.HoldingRegisters, RESPONSE_MAILBOX, 1)
            write = False
        else:
            count = min(MODBUS_READ_CHUNK, pending['total'] - offset)
            unit = QModbusDataUnit(QModbusDataUnit.HoldingRegisters, RESPONSE_MAILBOX + offset, count)
            write = False
        pending['unit'] = unit
        method = client.sendWriteRequest if write else client.sendReadRequest
        reply = method(unit, pending['frame'].node)
        if self.client is not client or self._wire is not pending:
            if reply is not None:
                reply.deleteLater()
            return
        if reply is None:
            self._fail(client.errorString() or 'Không gửi được mailbox A45.')
            return
        self.reply = reply
        reply.finished.connect(lambda: self._wire_reply_done(client, reply, pending))
        if reply.isFinished():
            self._wire_reply_done(client, reply, pending)

    def _wire_reply_done(self, client, reply, pending):
        if self.client is not client or self.reply is not reply or self._wire is not pending:
            return
        if reply.error() != QModbusDevice.NoError:
            self._fail(reply.errorString() or 'Lỗi giao dịch mailbox A45; không tự gửi lại.')
            return
        self.reply = None
        result, expected = reply.result(), pending['unit']
        reply.deleteLater()
        writing = pending['phase'] in ('stage', 'commit')
        valid = (validate_write_ack(reply.rawResult(), expected.startAddress(), expected.values())
                 if writing else (result.isValid() and result.registerType() == expected.registerType()
                                  and result.startAddress() == expected.startAddress()
                                  and result.valueCount() == expected.valueCount()))
        if reply.serverAddress() != pending['frame'].node or not valid:
            self._fail('Phản hồi mailbox không khớp yêu cầu.')
            return
        phase = pending['phase']
        if phase == 'stage':
            pending['offset'] += expected.valueCount()
            if pending['offset'] == len(pending['words']):
                pending['phase'] = 'commit'
        elif phase == 'commit':
            pending['phase'] = 'length'
        elif phase == 'length':
            length = result.value(0)
            if not 18 <= length <= MAX_FRAME:
                self._fail('Độ dài phản hồi mailbox A45 không hợp lệ.')
                return
            pending.update(phase='body', offset=1, total=1 + (length + 1) // 2, response=[length])
        else:
            pending['response'].extend(result.values())
            pending['offset'] += result.valueCount()
            if pending['offset'] == pending['total']:
                try:
                    raw = registers_to_frame(pending['response'])
                    frame = decode_frame(raw)
                    expected_frame = pending['frame']
                    if ((frame.node, frame.session, frame.sequence, frame.opcode)
                            != (expected_frame.node, expected_frame.session,
                                expected_frame.sequence, expected_frame.opcode) or frame.flags not in (1, 3)):
                        raise ValueError('Sai định danh phản hồi mailbox A45.')
                except ValueError as error:
                    self._fail(str(error))
                else:
                    self._wire_finish(raw)
                return
        self.wire_pump.start(0)

    def _wire_finish(self, raw):
        self._wire = None
        self.deadline.stop()
        self.wire_pump.stop()
        self.wire_finished.emit(raw, '')

    def read_registers(self, slave, function, address, count):
        unit = make_read_unit(slave, function, address, count)
        if self.state != 'open' or not self.client or self.settings.adapter != 'rtu':
            raise ValueError('Hãy mở kết nối Modbus RTU trước khi đọc.')
        if self.reply is not None or self._wire is not None:
            raise ValueError('Đang chờ phản hồi giao dịch trước.')
        client = self.client
        self._request = dict(slave=slave, function=function, address=address, count=count)
        reply = client.sendReadRequest(unit, slave)
        if reply is None:
            self._request = None
            self.read_finished.emit(None, client.errorString() or 'Không gửi được yêu cầu đọc.')
            return
        if self.client is not client:
            reply.deleteLater()
            return
        self.reply = reply
        reply.finished.connect(lambda: self._read_done(client, reply))
        # A bounded guard also covers a stalled/misbehaving client. Close on this
        # guard so a late RTU response cannot be consumed by a new transaction.
        self.deadline.start(self.settings.timeout_ms + 1000)
        if reply.isFinished():
            self._read_done(client, reply)

    def _read_done(self, client, reply):
        if self.client is not client or self.reply is not reply:
            return
        self.deadline.stop()
        request, self._request = self._request, None
        self.reply = None
        error = reply.error()
        result = None
        message = ''
        if error != QModbusDevice.NoError:
            message = reply.errorString() or 'Phản hồi Modbus không hợp lệ.'
            if error == QModbusDevice.TimeoutError:
                message = 'Timeout: không có phản hồi Modbus hợp lệ; không tự gửi lại.'
            elif error == QModbusDevice.ProtocolError:
                message = f'Lỗi Modbus exception {reply.rawResult().exceptionCode().value}: {message}'
        else:
            unit = reply.result()
            expected = make_read_unit(**request)
            if (reply.serverAddress() != request['slave'] or not unit.isValid()
                    or unit.registerType() != expected.registerType()
                    or unit.startAddress() != request['address']
                    or unit.valueCount() != request['count']):
                message = 'Phản hồi không khớp slave/loại/địa chỉ/số thanh ghi yêu cầu.'
            else:
                result = dict(request, values=list(unit.values()), timestamp=time.monotonic())
        reply.deleteLater()
        if error in (QModbusDevice.TimeoutError, QModbusDevice.InvalidResponseError):
            # RTU has no transaction ID. Require a fresh connection after an
            # ambiguous exchange instead of accepting a late frame for a new read.
            message += ' Đã đóng COM; kết nối lại trước khi đọc tiếp.'
            self._fail(message)
        self.read_finished.emit(result, message)

    def write_registers(self, slave, address, values):
        values = register_words(values)
        make_read_unit(slave, 3, address, len(values))
        if len(values) > 123:
            raise ValueError('FC16 cho phép tối đa 123 thanh ghi.')
        if self.state != 'open' or not self.client or self.settings.adapter != 'rtu':
            raise ValueError('Hãy mở kết nối Modbus RTU trước khi ghi.')
        if self.reply is not None or self._wire is not None:
            raise ValueError('Đang chờ phản hồi giao dịch trước.')
        client = self.client
        self._request = dict(slave=slave, function=6 if len(values) == 1 else 16,
                             address=address, values=values)
        unit = QModbusDataUnit(QModbusDataUnit.HoldingRegisters, address, values)
        reply = client.sendWriteRequest(unit, slave)
        if self.client is not client:
            if reply is not None:
                reply.deleteLater()
            return
        if reply is None:
            self._request = None
            self.write_finished.emit(None, client.errorString() or 'Không gửi được yêu cầu ghi.')
            return
        self.reply = reply
        reply.finished.connect(lambda: self._write_done(client, reply))
        self.deadline.start(self.settings.timeout_ms + 1000)
        if reply.isFinished():
            self._write_done(client, reply)

    def _write_done(self, client, reply):
        if self.client is not client or self.reply is not reply:
            return
        request = self._request
        error = reply.error()
        if error != QModbusDevice.NoError:
            message = reply.errorString() or 'Lỗi ghi Modbus.'
            if error == QModbusDevice.ProtocolError:
                message = f'Modbus exception {reply.rawResult().exceptionCode().value}: {message}'
            else:
                self._fail(message + ' Chưa biết lệnh đã thực thi hay chưa; không tự gửi lại.')
                return
        elif (reply.serverAddress() != request['slave']
              or not validate_write_ack(reply.rawResult(), request['address'], request['values'])):
            self._fail('ACK ghi không khớp yêu cầu. Chưa biết kết quả; không tự gửi lại.')
            return
        else:
            message = ''
        self.deadline.stop()
        self.reply = None
        self._request = None
        reply.deleteLater()
        self.write_finished.emit(None if message else dict(request, timestamp=time.monotonic()), message)

    def _deadline_expired(self):
        self._fail('Timeout mở cổng/giao dịch. Đã đóng COM; hãy kết nối lại.')

    def _fail(self, detail):
        wire_pending = self._wire is not None
        pending = self.reply is not None and not wire_pending
        writing = self._request is not None and 'values' in self._request
        self.close(notify=False)
        self._status('error', detail or 'Không mở được cổng serial.')
        if pending:
            (self.write_finished if writing else self.read_finished).emit(None, detail)
        if wire_pending:
            self.wire_finished.emit(None, detail)

    def close(self, notify=True):
        self.deadline.stop()
        self.wire_pump.stop()
        self._wire = None
        self._stream = FrameStream()
        client, self.client = self.client, None
        reply, self.reply = self.reply, None
        self._request = None
        if client is not None:
            if self.settings.adapter == 'rtu':
                client.disconnectDevice()
            else:
                client.close()
            client.deleteLater()
        if reply is not None:
            reply.deleteLater()
        self.state = 'disconnected'
        if notify:
            self._status('disconnected')


def available_serial_ports():
    """Discover names/descriptions without opening or probing any device."""
    from PySide6.QtSerialPort import QSerialPortInfo
    return sorted((port.portName(), port.description())
                  for port in QSerialPortInfo.availablePorts())


@dataclass
class Request:
    id: int
    operation: str
    payload: dict
    priority: int
    epoch: int
    queued_at: float = field(default_factory=time.monotonic)


class Communication(QObject):
    completed = Signal(object, object, str)

    def __init__(self, profile, parent=None, timeout_ms=TRANSACTION_TIMEOUT_MS):
        super().__init__(parent)
        self.transport = SimulatedController(profile)
        self.codec = WireCodec(profile)
        self.session_id = secrets.randbits(32) or 1
        self.wire_sequence = 0
        self.sent_at = 0.0
        self.wire_request = None
        self.last_tx = b''
        self.last_rx = b''
        self.serial_link = None
        self.node = 1
        self.timeout_ms = timeout_ms
        self.queue = []
        self.active = None
        self.serial = 0
        self.closed = False
        self.max_inflight = 0
        self.reply_timer = QTimer(self)
        self.reply_timer.setSingleShot(True)
        self.reply_timer.timeout.connect(self._respond)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(lambda: self._complete(None, "Timeout giao dịch; không tự gửi lại"))
        self.pump = QTimer(self)
        self.pump.setSingleShot(True)
        self.pump.timeout.connect(self._dispatch)

    def use_serial(self, connection, node):
        """Bind the same command queue/codec to an already-open physical port."""
        if self.active or self.queue or self.closed:
            raise ValueError('Chỉ đổi đường truyền khi hàng đợi rảnh.')
        if connection.state != 'open' or type(node) is not int or not 1 <= node <= 247:
            raise ValueError('Cần mở COM và chọn node 1–247.')
        self.use_simulation()
        self.serial_link, self.node = connection, node
        connection.wire_finished.connect(self._wire_received)
        connection.status_changed.connect(self._link_changed)

    def use_simulation(self):
        if self.active or self.queue:
            raise ValueError('Chỉ đổi đường truyền khi hàng đợi rảnh.')
        if self.serial_link is not None:
            self.serial_link.wire_finished.disconnect(self._wire_received)
            self.serial_link.status_changed.disconnect(self._link_changed)
            self.serial_link = None
        self.node = 1

    def _link_changed(self, state, detail):
        if state in ('error', 'disconnected') and self.active:
            self.queue.clear()
            self._complete(None, detail or 'Cổng đóng trong khi giao dịch A45.')

    def _wire_received(self, raw, error):
        if self.serial_link is None or self.active is None:
            return
        self.last_rx = raw or b''
        if error:
            self._complete(None, error)
            return
        try:
            response = self.codec.decode_response(raw, self.wire_request, sent_at=self.sent_at)
        except ValueError as exc:
            self._complete(None, str(exc))
        else:
            self._complete(response, '')

    def submit(self, operation, payload=None, priority=1, epoch=0):
        if self.closed:
            return None
        if operation == "snapshot":
            existing = ([self.active] if self.active else []) + self.queue
            if any(r.operation == "snapshot" and r.epoch == epoch for r in existing):
                return None
        if len(self.queue) >= 32:
            return None
        self.serial += 1
        request = Request(self.serial, operation, payload or {}, priority, epoch)
        self.queue.append(request)
        self.queue.sort(key=lambda r: (r.priority, r.id))
        if not self.active:
            self.pump.start(0)
        return request.id

    def discard_pending(self):
        self.queue.clear()

    def _dispatch(self):
        if self.closed or self.active or not self.queue:
            return
        self.active = self.queue.pop(0)
        if self.active.operation == 'connect':
            self.session_id = secrets.randbits(32) or 1
            self.wire_sequence = 0
        self.wire_sequence += 1
        self.sent_at = time.monotonic()
        try:
            self.wire_request = self.codec.request(self.active.operation, self.active.payload,
                                                   self.session_id, self.wire_sequence, self.node)
            self.last_tx = encode_frame(self.wire_request)
            self.last_rx = b''
        except (ValueError, KeyError) as error:
            self._complete(None, str(error))
            return
        self.max_inflight = max(self.max_inflight, 1)
        if self.serial_link is not None:
            # SerialConnection owns the full UART/mailbox deadline. No second
            # timer may end this transaction while its I/O is still active.
            try:
                self.serial_link.exchange_frame(self.last_tx)
            except ValueError as error:
                self._complete(None, str(error))
            return
        self.deadline.start(self.timeout_ms)
        scenario = self.transport.scenario
        op = self.active.operation
        if (scenario == "timeout" and op == "apply") or (scenario == "stop_timeout" and op == "finish"):
            return
        self.reply_timer.start(350 if scenario == "slow" else 35)

    def _respond(self):
        if not self.active:
            return
        try:
            self.last_rx = self.transport.exchange(self.last_tx)
            response = self.codec.decode_response(self.last_rx, self.wire_request, sent_at=self.sent_at)
        except (ValueError, ConnectionError) as error:
            self._complete(None, str(error))
        else:
            self._complete(response, "")

    def _complete(self, response, error):
        if not self.active:
            return
        request, self.active = self.active, None
        self.reply_timer.stop()
        self.deadline.stop()
        self.completed.emit(request, response, error)
        if not self.closed:
            self.pump.start(0)

    def disconnect(self):
        self.queue.clear()
        self.active = None
        self.wire_request = None
        self.reply_timer.stop()
        self.deadline.stop()
        self.pump.stop()
        if self.serial_link is not None:
            link = self.serial_link
            self.use_simulation()
            link.close()
        self.transport.connected = False
        self.transport.pending = None

    def close(self):
        self.disconnect()
        self.closed = True
