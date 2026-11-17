"""Physical connection lifecycle with fake Qt endpoints; no hardware commands."""
import tempfile
import time
import unittest
import struct
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtSerialBus import QModbusDevice, QModbusDataUnit, QModbusPdu, QModbusResponse
from PySide6.QtSerialPort import QSerialPort

from src.common.serial import SerialSettings
from src.communication import SerialConnection
from src.protocol import make_read_unit


class FakeReply(QObject):
    finished = Signal()

    def __init__(self, parent, unit, slave):
        super().__init__(parent)
        self.unit = QModbusDataUnit(unit)
        self.slave = slave
        self.code = QModbusDevice.NoError
        self.done = False

    def finish(self, error=QModbusDevice.NoError):
        self.code = error
        self.done = True
        self.finished.emit()

    def error(self):
        return self.code

    def errorString(self):
        return 'fake reply error'

    def result(self):
        return self.unit

    def serverAddress(self):
        return self.slave

    def isFinished(self):
        return self.done

    def rawResult(self):
        return self

    def exceptionCode(self):
        return QModbusPdu.IllegalDataAddress


class FakeWriteReply(FakeReply):
    def result(self):
        return QModbusDataUnit()  # The real Qt API returns INVALID for writes.

    def rawResult(self):
        if self.code == QModbusDevice.ProtocolError:
            return QModbusResponse(QModbusPdu.FunctionCode(0x86), bytes([2]))
        single = self.unit.valueCount() == 1
        tail = self.unit.value(0) if single else self.unit.valueCount()
        return QModbusResponse(QModbusPdu.FunctionCode(6 if single else 16),
                               struct.pack('>HH', self.unit.startAddress(), tail))


class FakeRtu(QObject):
    stateChanged = Signal(object)
    errorOccurred = Signal(object)
    fail_open = False
    immediate = False
    reject_send = False

    def __init__(self, parent):
        super().__init__(parent)
        self.parameters = {}
        self.requests = []
        self.disconnected = False

    def setConnectionParameter(self, key, value):
        self.parameters[key] = value

    def setTimeout(self, value):
        self.timeout = value

    def setNumberOfRetries(self, value):
        self.retries = value

    def connectDevice(self):
        if self.fail_open:
            self.errorOccurred.emit(QModbusDevice.ConnectionError)
            return False
        self.stateChanged.emit(QModbusDevice.ConnectedState)
        return True

    def errorString(self):
        return 'Access denied / port busy'

    def disconnectDevice(self):
        self.disconnected = True
        self.stateChanged.emit(QModbusDevice.UnconnectedState)

    def sendReadRequest(self, unit, slave):
        if self.reject_send:
            return None
        reply = FakeReply(self, unit, slave)
        self.requests.append(reply)
        if self.immediate:
            reply.finish()
        return reply

    def sendWriteRequest(self, unit, slave):
        if self.reject_send:
            return None
        reply = FakeWriteReply(self, unit, slave)
        self.requests.append(reply)
        if self.immediate:
            reply.finish()
        return reply


class FakeUart(QObject):
    errorOccurred = Signal(object)
    readyRead = Signal()
    bytesWritten = Signal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.is_open = False
        self.data = b''

    def setPortName(self, value):
        self.port = value

    def setReadBufferSize(self, value):
        self.buffer_size = value

    def setBaudRate(self, value):
        self.baud = value
        return True

    def setDataBits(self, value):
        self.bits = value
        return True

    def setParity(self, value):
        self.parity = value
        return True

    def setStopBits(self, value):
        self.stops = value
        return True

    def setFlowControl(self, value):
        self.flow = value
        return True

    def open(self, mode):
        self.errorOccurred.emit(QSerialPort.NoError)
        self.is_open = True
        return True

    def close(self):
        self.is_open = False

    def errorString(self):
        return 'USB removed'

    def readAll(self):
        result, self.data = self.data, b''
        return result


class SerialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.link = SerialConnection(rtu_factory=FakeRtu, uart_factory=FakeUart)
        self.settings = SerialSettings('rtu', 'COM_TEST', 19200, parity='E', stop_bits=2)

    def tearDown(self):
        self.link.close()
        self.link.deleteLater()
        QTest.qWait(1)

    def test_open_only_does_not_probe_slave_or_send_anything(self):
        self.link.open(self.settings)
        client = self.link.client
        self.assertEqual(self.link.state, 'open')
        self.assertEqual(client.requests, [])
        self.assertEqual(client.retries, 0)
        self.assertEqual(client.parameters[QModbusDevice.SerialPortNameParameter], 'COM_TEST')
        self.assertEqual(client.parameters[QModbusDevice.SerialBaudRateParameter], 19200)
        self.assertEqual(client.parameters[QModbusDevice.SerialParityParameter], QSerialPort.EvenParity)
        self.assertEqual(client.parameters[QModbusDevice.SerialStopBitsParameter], QSerialPort.TwoStop)

    def test_open_error_is_not_reported_as_success(self):
        with patch.object(FakeRtu, 'fail_open', True):
            spy = QSignalSpy(self.link.status_changed)
            self.link.open(self.settings)
        self.assertEqual(self.link.state, 'error')
        self.assertIsNone(self.link.client)
        self.assertIn('Access denied', spy.at(spy.count() - 1)[1])
        self.assertNotIn('open', [spy.at(i)[0] for i in range(spy.count())])

    def test_read_success_validates_result_and_releases_transaction(self):
        self.link.open(self.settings)
        spy = QSignalSpy(self.link.read_finished)
        self.link.read_registers(7, 3, 12, 2)
        reply = self.link.reply
        reply.unit.setValue(0, 42)
        reply.unit.setValue(1, 65535)
        reply.finish()
        self.assertEqual(spy.at(0)[0]['values'], [42, 65535])
        self.assertEqual(spy.at(0)[1], '')
        self.assertIsNone(self.link.reply)
        self.assertFalse(self.link.deadline.isActive())

    def test_second_request_rejected_while_waiting_then_timeout_without_retry(self):
        self.link.open(self.settings)
        spy = QSignalSpy(self.link.read_finished)
        self.link.read_registers(7, 4, 0, 1)
        with self.assertRaises(ValueError):
            self.link.read_registers(7, 4, 1, 1)
        client = self.link.client
        self.link.reply.finish(QModbusDevice.TimeoutError)
        self.assertEqual(len(client.requests), 1)
        self.assertIsNone(spy.at(0)[0])
        self.assertIn('Timeout', spy.at(0)[1])
        self.assertEqual(self.link.state, 'error')
        self.assertTrue(client.disconnected)

    def test_wrong_slave_or_shape_is_rejected(self):
        self.link.open(self.settings)
        spy = QSignalSpy(self.link.read_finished)
        for change in ('slave', 'type', 'address', 'count'):
            self.link.read_registers(7, 3, 12, 2)
            reply = self.link.reply
            if change == 'slave':
                reply.slave = 8
            elif change == 'type':
                reply.unit.setRegisterType(QModbusDataUnit.InputRegisters)
            elif change == 'address':
                reply.unit.setStartAddress(13)
            else:
                reply.unit.setValueCount(1)
            reply.finish()
        self.assertEqual(spy.count(), 4)
        self.assertTrue(all(spy.at(i)[0] is None and spy.at(i)[1] for i in range(4)))

    def test_modbus_exception_and_invalid_response_clear_transaction(self):
        self.link.open(self.settings)
        spy = QSignalSpy(self.link.read_finished)
        for error in (QModbusDevice.ProtocolError, QModbusDevice.InvalidResponseError):
            self.link.read_registers(7, 3, 0, 1)
            self.link.reply.finish(error)
            self.assertIsNone(self.link.reply)
        self.assertEqual(spy.count(), 2)
        self.assertIn('exception 2', spy.at(0)[1])
        self.assertIsNone(spy.at(0)[0])
        self.assertIsNone(spy.at(1)[0])

    def test_close_cancels_reply_and_late_events_cannot_change_new_connection(self):
        self.link.open(self.settings)
        self.link.read_registers(7, 3, 0, 1)
        old_client, old_reply = self.link.client, self.link.reply
        spy = QSignalSpy(self.link.read_finished)
        self.link.open(self.settings)
        old_reply.finish()
        old_client.errorOccurred.emit(QModbusDevice.ConnectionError)
        self.assertEqual(spy.count(), 0)
        self.assertEqual(self.link.state, 'open')
        self.assertTrue(old_client.disconnected)

    def test_watchdog_closes_stalled_transaction_and_gui_keeps_processing(self):
        self.link.open(self.settings)
        self.link.read_registers(7, 3, 0, 1)
        spy = QSignalSpy(self.link.read_finished)
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(5)
        self.link.deadline.start(30)
        QTest.qWait(80)
        timer.stop()
        self.assertGreater(len(ticks), 2)
        self.assertEqual(self.link.state, 'error')
        self.assertIsNone(self.link.client)
        self.assertEqual(spy.count(), 1)

    def test_immediate_reply_and_send_rejection_complete_once(self):
        self.link.open(self.settings)
        spy = QSignalSpy(self.link.read_finished)
        with patch.object(FakeRtu, 'immediate', True):
            self.link.read_registers(7, 4, 0, 1)
        self.assertEqual(spy.count(), 1)
        self.assertIsNotNone(spy.at(0)[0])
        with patch.object(FakeRtu, 'reject_send', True):
            self.link.read_registers(7, 4, 0, 1)
        self.assertEqual(spy.count(), 2)
        self.assertIsNone(spy.at(1)[0])

    def test_uart_receive_disconnect_and_unplug(self):
        self.link.open(SerialSettings('uart', 'COM_TEST', 9600))
        client = self.link.client
        spy = QSignalSpy(self.link.received)
        self.assertTrue(client.is_open)
        client.data = b'\x01\x03'
        client.readyRead.emit()
        self.assertEqual(spy.at(0)[0], b'\x01\x03')
        client.errorOccurred.emit(QSerialPort.ResourceError)
        self.assertEqual(self.link.state, 'error')
        self.assertFalse(client.is_open)

    def test_validation_rejects_broadcast_bad_framing_and_overflow(self):
        for values in ((0, 3, 0, 1), (248, 3, 0, 1), (1, 6, 0, 1),
                       (1, 3, -1, 1), (1, 3, 65535, 2), (1, 3, 0, 126)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                make_read_unit(*values)
        for changes in ({'baudrate': 0}, {'parity': 'X'}, {'data_bits': 7},
                        {'stop_bits': 3}, {'port': ''}, {'timeout_ms': 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                SerialSettings(**(dict(adapter='rtu', port='COM_TEST', baudrate=9600) | changes))

    def test_real_qt_missing_port_reports_error(self):
        link = SerialConnection()
        try:
            link.open(SerialSettings('rtu', '__A45_NONEXISTENT_PORT__', 9600))
            self.assertEqual(link.state, 'error')
            self.assertIsNone(link.client)
        finally:
            link.close()
            link.deleteLater()


class SerialBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_mock_to_serial_read_timeout_and_shutdown(self):
        from src.backend import Backend
        from tests.test_bench import alternative_profile
        with tempfile.TemporaryDirectory() as folder:
            with patch('src.device.SerialConnection',
                       side_effect=lambda parent: SerialConnection(parent, rtu_factory=FakeRtu)):
                backend = Backend(alternative_profile(), storage_dir=folder)
            try:
                backend.connect_device()
                QTest.qWait(150)
                self.assertTrue(backend.samples)
                backend.connect_serial(SerialSettings('rtu', 'COM_TEST', 9600))
                self.assertEqual(backend.connection, 'Đã mở COM_TEST')
                self.assertFalse(backend.can_start)
                self.assertFalse(backend._poll.isActive())
                self.assertTrue(all(s.quality == 'stale' for s in backend.samples.values()))
                backend.read_serial_registers(1, 3, 0, 1)
                backend.device.serial_connection.reply.finish()
                self.assertIsNotNone(backend.serial_result)
                backend.read_serial_registers(1, 3, 0, 1)
                self.assertIsNone(backend.serial_result)
                backend.device.serial_connection.reply.finish(QModbusDevice.TimeoutError)
                self.assertIsNone(backend.serial_result)
                self.assertFalse(backend.serial_read_pending)
                self.assertEqual(backend.serial_state, 'error')
                backend.connect_serial(SerialSettings('rtu', 'COM_TEST', 9600))
                backend.read_serial_registers(1, 3, 0, 1)
                client = backend.device.serial_connection.client
                backend.shutdown()
                self.assertTrue(client.disconnected)
                self.assertFalse(backend.serial_read_pending)
                self.assertIsNone(backend.serial_result)
            finally:
                backend.shutdown()
                deadline = time.monotonic() + 3
                while not backend.closed and time.monotonic() < deadline:
                    QTest.qWait(20)
                self.assertTrue(backend.closed)
                backend.deleteLater()
                QTest.qWait(1)
