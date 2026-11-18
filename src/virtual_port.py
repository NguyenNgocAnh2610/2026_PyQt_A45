"""Virtual COM port to the simulated CPUv1.0 STM32 slave.

``VirtualRtuClient`` stands in for ``QModbusRtuSerialClient`` behind the same
``SerialConnection``: the request is turned into real Modbus RTU bytes (slave,
PDU, CRC16), carried with 115200-baud wire timing to ``Stm32RtuSlave`` and the
reply bytes are parsed back like the Qt client does (CRC, slave, function,
exception). Simulation and the real COM port therefore run the same runner,
device and connection code; only this client differs.

Faults are injected on the line (no reply, unplugged cable, slow reply), so the
application sees them exactly as it would on a real port.
"""
import math
import struct

from PySide6.QtCore import QObject, QTimer, Signal, QByteArray
from PySide6.QtSerialBus import (QModbusDevice, QModbusDataUnit, QModbusPdu, QModbusResponse,
                                 QModbusExceptionResponse)

from src.protocol import rtu_adu, split_rtu_adu, rtu_request_pdu

VIRTUAL_PORT = 'COM ảo · STM32 giả lập'
T35_MS = 1.75     # Modbus RTU silent interval above 19200 baud (end of frame).
SLAVE_POLL_MS = 1  # FreeModbus eMBPoll() runs from the 1 ms SysTick.
SLOW_EXTRA_MS = 320  # 'slow' scenario: late but inside the 1000 ms timeout.


class VirtualLine:
    """The far end of the virtual cable: the slave plus fault injection.

    ``stage`` is the runner phase currently on the line ('prepare', 'apply',
    'measure', 'finish' or None); it only decides *when* a scenario fault
    happens, the fault itself is a plain line event.
    """
    FAULTS = {('timeout', 'apply'): 'silent', ('stop_timeout', 'finish'): 'silent',
              ('disconnect', 'measure'): 'unplug'}

    def __init__(self, slave):
        self.slave = slave
        self.scenario = 'normal'
        self.stage = None
        self.frames = 0

    def fault(self):
        return self.FAULTS.get((self.scenario, self.stage))

    def extra_delay_ms(self):
        return SLOW_EXTRA_MS if self.scenario == 'slow' else 0


class VirtualReply(QObject):
    """Duck-typed QModbusReply: the members SerialConnection uses."""
    finished = Signal()

    def __init__(self, unit, server, parent=None):
        super().__init__(parent)
        self._unit = unit
        self._server = server
        self._done = False
        self._error = QModbusDevice.NoError
        self._error_string = ''
        self._result = QModbusDataUnit()
        self._raw = QModbusResponse()

    def isFinished(self):
        return self._done

    def error(self):
        return self._error

    def errorString(self):
        return self._error_string

    def result(self):
        return self._result

    def rawResult(self):
        return self._raw

    def serverAddress(self):
        return self._server

    def _finish(self, error=QModbusDevice.NoError, text='', result=None, raw=None):
        if self._done:
            return
        self._done = True
        self._error, self._error_string = error, text
        if result is not None:
            self._result = result
        if raw is not None:
            self._raw = raw
        self.finished.emit()


class VirtualRtuClient(QObject):
    """Duck-typed QModbusRtuSerialClient over a ``VirtualLine``."""
    stateChanged = Signal(object)
    errorOccurred = Signal(object)

    def __init__(self, parent=None, line=None):
        super().__init__(parent)
        self.line = line
        self._state = QModbusDevice.UnconnectedState
        self._error_string = ''
        self._timeout = 1000
        self._baudrate = 115200
        self._pending = None

    def setConnectionParameter(self, key, value):
        if key == QModbusDevice.SerialBaudRateParameter:
            self._baudrate = int(value)

    def setTimeout(self, ms):
        self._timeout = int(ms)

    def timeout(self):
        return self._timeout

    def setNumberOfRetries(self, _count):
        pass  # The application never retries; neither does this port.

    def state(self):
        return self._state

    def errorString(self):
        return self._error_string

    def connectDevice(self):
        self._set_state(QModbusDevice.ConnectedState)
        return True

    def disconnectDevice(self):
        self._pending = None
        self._set_state(QModbusDevice.UnconnectedState)

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self.stateChanged.emit(state)

    def _char_ms(self):
        return 10_000 / self._baudrate  # 8N1: 10 bits per character.

    def sendReadRequest(self, unit, server):
        function = 3 if unit.registerType() == QModbusDataUnit.HoldingRegisters else 4
        pdu = rtu_request_pdu(function, unit.startAddress(), count=unit.valueCount())
        return self._send(unit, server, function, pdu)

    def sendWriteRequest(self, unit, server):
        values = list(unit.values())
        function = 6 if len(values) == 1 else 16  # As QModbusClient chooses.
        return self._send(unit, server, function, rtu_request_pdu(function, unit.startAddress(), values))

    def _send(self, unit, server, function, pdu):
        if self._state != QModbusDevice.ConnectedState:
            self._error_string = 'Cổng COM ảo chưa mở.'
            return None
        if self._pending is not None:
            self._error_string = 'Cổng COM ảo đang có giao dịch.'
            return None
        reply = VirtualReply(unit, server, self)
        request = rtu_adu(server, pdu)
        self._pending = dict(reply=reply, function=function, unit=unit, server=server)
        QTimer.singleShot(self._timeout, self, lambda: self._expire(reply))
        sent_ms = len(request) * self._char_ms() + T35_MS
        QTimer.singleShot(math.ceil(sent_ms), self, lambda: self._arrive(reply, request))
        return reply

    def _current(self, reply):
        return self._pending is not None and self._pending['reply'] is reply

    def _expire(self, reply):
        if self._current(reply):
            self._pending = None
            reply._finish(QModbusDevice.TimeoutError, 'Request timeout.')

    def _arrive(self, reply, request):
        """The request reached the slave: it answers, stays silent, or the cable is gone."""
        if not self._current(reply):
            return
        fault = self.line.fault()
        if fault == 'unplug':
            self._error_string = 'Mất cổng COM ảo (mô phỏng rút cáp RS485).'
            self.errorOccurred.emit(QModbusDevice.ConnectionError)
            return
        response = None if fault == 'silent' else self.line.slave.handle(request)
        self.line.frames += 1
        if response is None:
            return  # Silence: only the client timeout ends this transaction.
        back_ms = SLAVE_POLL_MS + len(response) * self._char_ms() + T35_MS + self.line.extra_delay_ms()
        QTimer.singleShot(math.ceil(back_ms), self, lambda: self._deliver(reply, response))

    def _deliver(self, reply, raw):
        """Parse reply bytes as the Qt RTU client does; invalid frames are ignored."""
        if not self._current(reply):
            return
        pending = self._pending
        try:
            server, pdu = split_rtu_adu(raw)
        except ValueError:
            return  # Bad CRC: discarded, the request times out.
        if server != pending['server'] or not pdu or pdu[0] & 0x7F != pending['function']:
            return
        self._pending = None
        function, unit = pending['function'], pending['unit']
        code = QModbusPdu.FunctionCode(function)
        if pdu[0] & 0x80:
            exception = QModbusPdu.ExceptionCode(pdu[1]) if len(pdu) > 1 else QModbusPdu.ExceptionCode(4)
            reply._finish(QModbusDevice.ProtocolError, f'Modbus exception 0x{pdu[1]:02X}.',
                          raw=QModbusExceptionResponse(code, exception))
            return
        raw_result = QModbusResponse(code, QByteArray(pdu[1:]))
        if function in (3, 4):
            count = pdu[1] // 2 if len(pdu) > 1 else 0
            if len(pdu) != 2 + 2 * count or count != unit.valueCount():
                reply._finish(QModbusDevice.InvalidResponseError, 'Phản hồi đọc sai độ dài.', raw=raw_result)
                return
            words = list(struct.unpack(f'>{count}H', pdu[2:]))
            result = QModbusDataUnit(unit.registerType(), unit.startAddress(), words)
        else:
            result = QModbusDataUnit(unit.registerType(), unit.startAddress(), list(unit.values()))
        reply._finish(result=result, raw=raw_result)


def create_virtual_connection(parent, line):
    """The application's own SerialConnection, with this client instead of Qt's."""
    from src.communication import SerialConnection
    return SerialConnection(parent, rtu_factory=lambda owner: VirtualRtuClient(owner, line))
