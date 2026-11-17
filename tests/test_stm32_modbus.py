"""CPUv1.0 contract, async native Modbus and UI; no real COM opened."""
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtSerialBus import QModbusDevice

from src.common.stm32 import Stm32RegisterBanks, WriteRegister as WO, ReadRegister as RI
from src.common.serial import SerialSettings
from src.protocol import (encode_int16, decode_int16, pack_data_t, unpack_data_r,
                          encode_encoder, decode_stm32, stm32_write_words)
from src.simulator import Stm32Simulator
from src.communication import SerialConnection
from tests.test_serial_connection import FakeRtu


class RegisterCodecTests(unittest.TestCase):
    def test_corrected_document_rtu_crc_examples(self):
        # Offline documentation check only. Production framing belongs to Qt.
        def crc16(data):
            crc = 0xFFFF
            for byte in data:
                crc ^= byte
                for _ in range(8):
                    crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
            return crc

        self.assertEqual(crc16(b'123456789'), 0x4B37)
        for frame in ('09 03 00 01 00 1D D5 4B', '09 06 00 01 00 01 18 82',
                      '09 10 00 01 00 1C 91 48'):
            data = bytes.fromhex(frame)
            self.assertEqual(crc16(data[:-2]).to_bytes(2, 'little'), data[-2:])
            self.assertEqual(crc16(data), 0)

    def test_two_independent_layouts_and_instances(self):
        first, second = Stm32RegisterBanks(), Stm32RegisterBanks()
        self.assertEqual((len(first.mod_buf_to_write), len(first.mod_buf_to_read)), (29, 30))
        first.mod_buf_to_write[WO.DAC_val] = 777
        self.assertEqual(first.mod_buf_to_read[RI.ADC0_val], 0)
        self.assertEqual(second.mod_buf_to_write[WO.DAC_val], 0)
        self.assertFalse(first.read_valid)

    def test_signed_boundaries_and_reject_bad_words(self):
        for value in (-32768, -1, 0, 32767):
            self.assertEqual(decode_int16(encode_int16(value)), value)
        for value in (-32769, 32768, True, 1.2):
            with self.assertRaises(ValueError):
                encode_int16(value)
        for address, values in ((0, [1]), (28, [1, 2]), (1, []), (1, [-1]), (1, [65536])):
            with self.assertRaises(ValueError):
                stm32_write_words(address, values)
        self.assertEqual(stm32_write_words(WO.DAC_val, [65535]), [65535])

    def test_peripheral_byte_order_length_and_zeros(self):
        words = pack_data_t(bytes.fromhex('11 22 00 44 55'))
        self.assertEqual(words[:3], [0x2211, 0x4400, 0x0055])
        self.assertEqual(unpack_data_r(words), bytes.fromhex('11 22 00 44 55') + b'\0' * 15)
        with self.assertRaises(ValueError):
            pack_data_t(b'x' * 21)

    def test_read_decode_scaling_and_overrange(self):
        words = Stm32Simulator().mod_buf_to_read
        values = decode_stm32(words)
        self.assertEqual(values['adc_volts'], [12.34, -5.67, 24.0, 12.0, 3.3])
        self.assertEqual(values['resistance_ohms'], 4700)
        self.assertEqual(values['encoder_count'], -123)
        self.assertEqual(values['din_levels'], [1] * 10)
        self.assertIsNone(values['received_length'])
        words[RI.Ohm_val] = 0xFFFF
        self.assertIsNone(decode_stm32(words)['resistance_ohms'])

    def test_simulator_does_not_echo_outputs_and_consumes_encoder_once(self):
        sim = Stm32Simulator()
        sim.write(9, 7, [333])
        self.assertEqual(sim.read(9)[6], 1234)
        sim.write(9, 1, [1])
        sim.write(9, 13, encode_encoder(8, 100))
        self.assertEqual(sim.mod_buf_to_write[13:15], [0, 0])
        for _ in range(5):
            sim.read(9)
        self.assertEqual(sim.encoder_triggers, 1)
        self.assertEqual(sim.read(9)[0], 0)  # Mode DI is not a DO readback.
        for period in (0, 2, 5, 16384):
            with self.assertRaises(ValueError):
                encode_encoder(period, 10)


class NativeSerialWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.link = SerialConnection(rtu_factory=FakeRtu)
        self.settings = SerialSettings('rtu', 'COM_TEST', 115200)
        self.link.open(self.settings)

    def tearDown(self):
        self.link.close()
        self.link.deleteLater()
        QTest.qWait(1)

    def test_fc06_fc16_ack_uses_raw_result_and_serializes_io(self):
        spy = QSignalSpy(self.link.write_finished)
        for values in ([1], [0xC008, 100]):
            self.link.write_registers(9, 13, values)
            self.assertFalse(self.link.reply.result().isValid())
            with self.assertRaises(ValueError):
                self.link.read_registers(9, 3, 1, 29)
            self.link.reply.finish()
        self.assertEqual(spy.count(), 2)
        self.assertEqual([spy.at(i)[1] for i in range(2)], ['', ''])
        self.assertEqual(spy.at(1)[0]['values'], [0xC008, 100])
        self.assertEqual(self.link.client.retries, 0)

    def test_bad_ack_closes_and_never_retries(self):
        for change in ('slave', 'address', 'value', 'count'):
            self.link.open(self.settings)
            client = self.link.client
            spy = QSignalSpy(self.link.write_finished)
            self.link.write_registers(9, 7, [100])
            reply = self.link.reply
            if change == 'slave':
                reply.slave = 8
            elif change == 'address':
                reply.unit.setStartAddress(8)
            elif change == 'count':
                reply.unit.setValueCount(2)
            else:
                reply.unit.setValue(0, 101)
            reply.finish()
            self.assertEqual(spy.count(), 1)
            self.assertTrue(spy.at(0)[1])
            self.assertEqual(self.link.state, 'error')
            self.assertEqual(len(client.requests), 1)

    def test_timeout_exception_rejection_and_late_reply(self):
        spy = QSignalSpy(self.link.write_finished)
        self.link.write_registers(9, 1, [1])
        self.link.reply.finish(QModbusDevice.ProtocolError)
        self.assertIn('exception', spy.at(0)[1])
        self.assertEqual(self.link.state, 'open')
        with patch.object(FakeRtu, 'reject_send', True):
            self.link.write_registers(9, 1, [1])
        self.assertEqual(spy.count(), 2)
        self.link.write_registers(9, 1, [1])
        old = self.link.reply
        self.link.deadline.start(10)
        QTest.qWait(30)
        self.assertEqual(spy.count(), 3)
        self.assertEqual(self.link.state, 'error')
        self.link.open(self.settings)
        # Separate explicit-close case: the old reply may be deleted after timeout.
        self.link.write_registers(9, 1, [1])
        old = self.link.reply
        self.link.open(self.settings)
        old.finish()
        self.assertEqual(spy.count(), 3)
        self.assertEqual(self.link.state, 'open')


class Stm32BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from src.backend import Backend
        self.folder = tempfile.TemporaryDirectory()
        with patch('src.device.SerialConnection', side_effect=lambda parent: SerialConnection(parent, rtu_factory=FakeRtu)):
            self.backend = Backend(storage_dir=self.folder.name)

    def tearDown(self):
        self.backend.shutdown()
        deadline = time.monotonic() + 3
        while not self.backend.closed and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(self.backend.closed)
        self.backend.deleteLater()
        QTest.qWait(1)
        self.folder.cleanup()

    def test_staging_capture_ack_and_read_bank_independence(self):
        b = self.backend
        with self.assertRaises(ValueError):
            b.request_stm32(address=1)
        b.stage_stm32(1, [1])
        b.request_stm32(address=1)
        b.stage_stm32(1, [2])
        QTest.qWait(60)
        self.assertEqual(b.stm32.last_ack['values'], [1])
        self.assertEqual(b.stm32.mod_buf_to_write[1], 2)
        self.assertFalse(b.stm32.read_valid)
        b.request_stm32()
        QTest.qWait(60)
        self.assertTrue(b.stm32.read_valid)
        self.assertEqual(b.stm32.mod_buf_to_read[1], 0)
        self.assertEqual(b.stm32.mod_buf_to_read[7], 1234)
        self.assertIsNone(b.device.serial_connection.client)

    def test_expiry_change_source_and_disconnect_invalidate(self):
        b = self.backend
        b.request_stm32()
        QTest.qWait(60)
        b.stm32.received_at -= 3
        b._tick()
        self.assertFalse(b.stm32.read_valid)
        b.request_stm32()
        QTest.qWait(60)
        b.select_stm32_source(False, 9)
        self.assertFalse(b.stm32.read_valid)
        b.request_stm32()
        b.disconnect_device()
        QTest.qWait(60)
        self.assertFalse(b.stm32.read_valid)
        self.assertFalse(b.stm32_pending)

    def test_real_path_full_read_and_write_ack_then_loss(self):
        b = self.backend
        b.connect_serial(SerialSettings('rtu', 'COM_TEST', 115200))
        b.request_stm32(simulation=False)
        reply = b.device.serial_connection.reply
        self.assertEqual((reply.slave, reply.unit.startAddress(), reply.unit.valueCount()), (9, 1, 29))
        reply.unit.setValue(6, 5432)
        reply.finish()
        self.assertEqual(b.stm32.mod_buf_to_read[7], 5432)
        b.stage_stm32(7, [100])
        b.request_stm32(simulation=False, address=7)
        b.device.serial_connection.reply.finish()
        self.assertEqual(b.stm32.mod_buf_to_read[7], 5432)
        self.assertEqual(b.stm32.last_ack['values'], [100])
        b.request_stm32(simulation=False, address=7)
        b.device.serial_connection.client.errorOccurred.emit(QModbusDevice.ConnectionError)
        self.assertFalse(b.stm32.read_valid)
        self.assertFalse(b.stm32_pending)
        self.assertFalse(b.serial_read_pending)

    def test_dialog_draft_edit_read_and_invalid_edit_cannot_send_previous(self):
        from src.ui.widgets.stm32_registers import Stm32RegistersDialog
        dialog = Stm32RegistersDialog(self.backend)
        try:
            dialog.tx.item(1, 2).setText('1')
            dialog.write_button.click()
            QTest.qWait(60)
            self.assertEqual(self.backend.stm32.last_ack['values'], [1])
            dialog.tx.item(1, 2).setText('invalid')
            dialog.write_button.click()
            self.assertIn('Nhập rõ', dialog.status.text())
            dialog.read_button.click()
            QTest.qWait(60)
            self.assertEqual(dialog.rx.item(7, 3).text(), '12.34 V')
        finally:
            dialog.close()
            dialog.deleteLater()
