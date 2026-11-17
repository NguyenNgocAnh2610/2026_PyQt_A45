"""Wire contract, reference firmware and real adapter paths with fake I/O."""
from dataclasses import replace
import binascii
import struct
import unittest
import uuid
import tempfile
import time
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtSerialBus import QModbusDataUnit

from src.common.profiles import load_profile
from src.common.serial import SerialSettings
from src.common.wire import (MAX_FRAME, REQUEST_MAILBOX, RESPONSE_MAILBOX, COMMIT_REGISTER,
                             MODBUS_WRITE_CHUNK, MODBUS_READ_CHUNK)
from src.protocol import (WireCodec, FrameStream, encode_frame, decode_frame,
                          frame_to_registers, registers_to_frame, decode_snapshot)
from src.simulator import SimulatedController
from src.communication import SerialConnection, Communication
from tests.test_serial_connection import FakeUart, FakeRtu, FakeReply, FakeWriteReply


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.codec = WireCodec(self.profile)
        self.now = 100.0
        self.controller = SimulatedController(self.profile, clock=lambda: self.now)
        self.sequence = 0

    def exchange(self, operation, payload=None):
        self.sequence += 1
        request = self.codec.request(operation, payload or {}, 99, self.sequence)
        raw = self.controller.exchange(encode_frame(request))
        return self.codec.decode_response(raw, request, now=self.now)

    def test_frame_fields_crc_and_corruption(self):
        self.assertEqual(binascii.crc_hqx(b'123456789', 0xFFFF), 0x29B1)
        frame = self.codec.request('snapshot', {}, 0x11223344, 1)
        raw = encode_frame(frame)
        self.assertEqual(raw[:16].hex(), 'a55a0101020011223344000000010000')
        self.assertEqual(len(raw), 18)
        self.assertEqual(raw[-2:], bytes.fromhex('0595'))
        self.assertEqual(decode_frame(raw), frame)
        for index in range(len(raw)):
            broken = bytearray(raw)
            broken[index] ^= 1
            with self.subTest(index=index), self.assertRaises(ValueError):
                decode_frame(bytes(broken))

    def test_stream_fragment_concat_noise_and_bad_crc(self):
        first = encode_frame(self.codec.request('connect', {}, 99, 1))
        second = encode_frame(self.codec.request('snapshot', {}, 99, 2))
        stream = FrameStream()
        decoded = []
        for byte in b'noise' + first + second:
            decoded.extend(stream.feed(bytes([byte])))
        self.assertEqual(decoded, [first, second])
        bad = bytearray(first)
        bad[-1] ^= 1
        self.assertEqual(stream.feed(b'junk' + bad + second), [second])
        stream.feed(b'x' * 100000)
        self.assertLessEqual(len(stream.buffer), MAX_FRAME)

    def test_mailbox_roundtrip_odd_padding_and_incomplete_staging(self):
        request = self.codec.request('apply', dict(token=str(uuid.uuid4()), case='AB', actions=[]), 99, 2)
        raw = encode_frame(request)
        words = frame_to_registers(raw)
        self.assertEqual(registers_to_frame(words), raw)
        self.controller.write_registers(REQUEST_MAILBOX, words[:2])
        with self.assertRaises(ValueError):
            self.controller.write_registers(COMMIT_REGISTER, [1])
        self.assertEqual(self.controller.executions, 0)
        self.assertEqual(len(raw) % 2, 1)
        words[-1] |= 1
        with self.assertRaises(ValueError):
            registers_to_frame(words)

    def test_duplicate_same_sequence_does_not_execute_twice(self):
        self.exchange('connect')
        request = self.codec.request('prepare', dict(token=str(uuid.uuid4())), 99, 2)
        raw = encode_frame(request)
        first = self.controller.exchange(raw)
        self.assertEqual(self.controller.exchange(raw), first)
        self.assertEqual(self.controller.executions, 1)
        conflict = self.codec.request('finish', dict(token=str(uuid.uuid4())), 99, 2)
        with self.assertRaisesRegex(ValueError, 'mã lỗi 3'):
            self.codec.decode_response(self.controller.exchange(encode_frame(conflict)), conflict)
        self.assertEqual(self.controller.executions, 1)

    def test_ack_completion_and_snapshot_freshness_are_separate(self):
        self.exchange('connect')
        token = str(uuid.uuid4())
        self.assertEqual(self.exchange('prepare', dict(token=token)), {'accepted': True})
        self.assertIsNone(self.exchange('snapshot')['confirmed'])
        self.now += .2
        result = self.exchange('snapshot')
        self.assertEqual(result['confirmed'], token)
        self.controller.scenario = 'stale'
        self.now += 2
        stale = self.exchange('snapshot')
        self.assertEqual(result['sample_seq'], stale['sample_seq'])
        self.assertLessEqual(stale['timestamp'], result['timestamp'])
        self.assertEqual(decode_snapshot(stale, self.codec.mapping)['ready'].source, 'mock')

    def test_boot_change_schema_mismatch_and_old_session_rejected(self):
        self.exchange('connect')
        self.controller.boot_id += 1
        with self.assertRaisesRegex(ValueError, 'khởi động lại'):
            self.exchange('snapshot')
        wrong = self.codec.request('snapshot', {}, 100, 4)
        with self.assertRaisesRegex(ValueError, 'mã lỗi 2'):
            self.codec.decode_response(self.controller.exchange(encode_frame(wrong)), wrong)
        hello = self.codec.request('connect', {}, 101, 5)
        hello = replace(hello, payload=b'\0' * 16)
        with self.assertRaisesRegex(ValueError, 'mã lỗi 1'):
            self.codec.decode_response(self.controller.exchange(encode_frame(hello)), hello)

    def test_wrong_node_and_long_transaction_cannot_create_fresh_samples(self):
        request = self.codec.request('connect', {}, 99, 1, node=2)
        with self.assertRaises(ConnectionError):
            self.controller.exchange(encode_frame(request))
        self.exchange('connect')
        request = self.codec.request('snapshot', {}, 99, 2)
        raw = self.controller.exchange(encode_frame(request))
        payload = self.codec.decode_response(raw, request, now=105, sent_at=100)
        self.assertEqual(payload['timestamp'], 100)

    def test_reply_identity_and_trailing_payload_rejected_without_state_mutation(self):
        request = self.codec.request('connect', {}, 99, 1)
        frame = decode_frame(self.controller.exchange(encode_frame(request)))
        for change in (dict(node=2), dict(session=100), dict(sequence=2),
                       dict(opcode=2), dict(payload=frame.payload + b'\0')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.codec.decode_response(encode_frame(replace(frame, **change)), request)
            self.assertIsNone(self.codec.boot_id)

    def test_mapping_must_be_unique_and_finite_actions_use_output_channels(self):
        for actions in ([dict(signal='ready', value=1)], [dict(signal='set_4', value=float('nan'))],
                        [dict(signal='set_4', value=1), dict(signal='set_4', value=2)]):
            with self.assertRaises(ValueError):
                self.codec.request('apply', dict(token=str(uuid.uuid4()), actions=actions), 99, 2)
        self.profile.hardware['wire_signals']['ready'] = self.profile.hardware['wire_signals']['fault']
        with self.assertRaises(ValueError):
            WireCodec(self.profile)

    def test_mailbox_frozen_snapshot_and_chunk_limits(self):
        request = self.codec.request('connect', {}, 99, 1)
        words = frame_to_registers(encode_frame(request))
        for offset in range(0, len(words), MODBUS_WRITE_CHUNK):
            self.controller.write_registers(REQUEST_MAILBOX + offset, words[offset:offset + MODBUS_WRITE_CHUNK])
        self.controller.write_registers(COMMIT_REGISTER, [1])
        length = self.controller.read_registers(RESPONSE_MAILBOX, 1)[0]
        response = [length]
        self.now += 10
        for offset in range(1, 1 + (length + 1) // 2, MODBUS_READ_CHUNK):
            response.extend(self.controller.read_registers(RESPONSE_MAILBOX + offset,
                            min(MODBUS_READ_CHUNK, 1 + (length + 1) // 2 - offset)))
        self.assertTrue(self.codec.decode_response(registers_to_frame(response), request)['connected'])


class LoopbackUart(FakeUart):
    def __init__(self, parent):
        super().__init__(parent)
        self.controller = SimulatedController(load_profile())
        self.parser = FrameStream()
        self.write_calls = 0

    def write(self, raw):
        self.write_calls += 1
        accepted = min(7, len(raw))
        packets = self.parser.feed(bytes(raw[:accepted]))
        QTimer.singleShot(0, lambda: self.bytesWritten.emit(accepted))
        for packet in packets:
            response = self.controller.exchange(packet)
            QTimer.singleShot(0, lambda response=response: self._deliver(response))
        return accepted

    def _deliver(self, response):
        self.data = response[:9]
        self.readyRead.emit()
        self.data = response[9:]
        self.readyRead.emit()


class LoopbackRtu(FakeRtu):
    def __init__(self, parent):
        super().__init__(parent)
        self.controller = SimulatedController(load_profile())
        self.transfers = []

    def sendWriteRequest(self, unit, slave):
        self.transfers.append(('write', unit.startAddress(), unit.valueCount()))
        self.controller.write_registers(unit.startAddress(), list(unit.values()))
        reply = FakeWriteReply(self, unit, slave)
        QTimer.singleShot(0, reply.finish)
        return reply

    def sendReadRequest(self, unit, slave):
        self.transfers.append(('read', unit.startAddress(), unit.valueCount()))
        values = self.controller.read_registers(unit.startAddress(), unit.valueCount())
        reply = FakeReply(self, QModbusDataUnit(unit.registerType(), unit.startAddress(), values), slave)
        QTimer.singleShot(0, reply.finish)
        return reply


class AdapterWireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_uart_and_rtu_use_same_handshake_and_snapshot(self):
        for adapter in ('uart', 'rtu'):
            with self.subTest(adapter=adapter):
                link = SerialConnection(rtu_factory=LoopbackRtu, uart_factory=LoopbackUart)
                codec = WireCodec(load_profile())
                try:
                    link.open(SerialSettings(adapter, 'COM_TEST', 9600))
                    spy = QSignalSpy(link.wire_finished)
                    for seq, operation in enumerate(('connect', 'snapshot'), 1):
                        if operation == 'snapshot':
                            link.client.controller.values.update({sid: 1.0 for sid in codec.mapping})
                        frame = codec.request(operation, {}, 99, seq)
                        link.exchange_frame(encode_frame(frame))
                        with self.assertRaises(ValueError):
                            link.read_registers(1, 3, 0, 1)
                        for _ in range(100):
                            if spy.count() >= seq:
                                break
                            QTest.qWait(5)
                        self.assertEqual(spy.count(), seq)
                        raw, error = spy.at(seq - 1)
                        self.assertEqual(error, '')
                        payload = codec.decode_response(raw, frame)
                    self.assertEqual(payload['values']['ready'], 1)
                    self.assertIsNone(link.reply)
                    if adapter == 'uart':
                        self.assertGreater(link.client.write_calls, 2)
                    else:
                        self.assertTrue(all(size <= (123 if kind == 'write' else 125)
                                            for kind, _, size in link.client.transfers))
                        self.assertIn(('read', RESPONSE_MAILBOX + 1, 125), link.client.transfers)
                finally:
                    link.close()
                    link.deleteLater()
                    QTest.qWait(1)

    def test_command_queue_can_swap_to_serial_without_changing_device_operations(self):
        profile = load_profile()
        link = SerialConnection(rtu_factory=LoopbackRtu)
        queue = Communication(profile)
        try:
            link.open(SerialSettings('rtu', 'COM_TEST', 9600))
            queue.use_serial(link, 1)
            spy = QSignalSpy(queue.completed)
            queue.submit('connect')
            queue.submit('prepare', {'token': str(uuid.uuid4())})
            for _ in range(100):
                if spy.count() == 2:
                    break
                QTest.qWait(5)
            self.assertEqual(spy.count(), 2)
            self.assertEqual([spy.at(i)[2] for i in range(2)], ['', ''])
            self.assertEqual(link.client.controller.executions, 1)
        finally:
            queue.close()
            self.assertIsNone(link.client)
            queue.deleteLater()
            link.deleteLater()
            QTest.qWait(1)

    def test_uart_wire_timeout_cancels_without_retry(self):
        class SilentUart(FakeUart):
            writes = 0

            def write(self, raw):
                self.writes += 1
                return len(raw)

        link = SerialConnection(uart_factory=SilentUart)
        try:
            link.open(SerialSettings('uart', 'COM_TEST', 9600))
            client = link.client
            spy = QSignalSpy(link.wire_finished)
            codec = WireCodec(load_profile())
            link.exchange_frame(encode_frame(codec.request('connect', {}, 99, 1)))
            link.deadline.start(15)
            QTest.qWait(50)
            self.assertEqual(spy.count(), 1)
            self.assertTrue(spy.at(0)[1])
            self.assertEqual(client.writes, 1)
            self.assertEqual(link.state, 'error')
        finally:
            link.close()
            link.deleteLater()
            QTest.qWait(1)

    def test_rtu_splits_staging_and_commits_only_after_all_chunks(self):
        link = SerialConnection(rtu_factory=LoopbackRtu)
        codec = WireCodec(load_profile())
        try:
            link.open(SerialSettings('rtu', 'COM_TEST', 9600))
            request = replace(codec.request('connect', {}, 99, 1), payload=b'x' * 1024)
            spy = QSignalSpy(link.wire_finished)
            link.exchange_frame(encode_frame(request))
            for _ in range(100):
                if spy.count():
                    break
                QTest.qWait(5)
            self.assertEqual(spy.count(), 1)
            self.assertEqual(spy.at(0)[1], '')
            self.assertEqual(decode_frame(spy.at(0)[0]).flags, 3)
            writes = [(address, size) for kind, address, size in link.client.transfers if kind == 'write']
            self.assertGreater(len(writes), 2)
            self.assertEqual(writes[-1], (COMMIT_REGISTER, 1))
            self.assertTrue(all(size <= 123 for _, size in writes))
        finally:
            link.close()
            link.deleteLater()
            QTest.qWait(1)

    def test_backend_identify_snapshot_and_reboot_invalidates_samples(self):
        from src.backend import Backend
        with tempfile.TemporaryDirectory() as folder:
            with patch('src.device.SerialConnection',
                       side_effect=lambda parent: SerialConnection(parent, uart_factory=LoopbackUart)):
                backend = Backend(storage_dir=folder)
            try:
                backend.connect_serial(SerialSettings('uart', 'COM_TEST', 9600))
                backend.request_controller(1)
                for _ in range(100):
                    if not backend.serial_read_pending:
                        break
                    QTest.qWait(5)
                self.assertTrue(backend.controller_info['connected'])
                backend.request_controller()
                for _ in range(100):
                    if not backend.serial_read_pending:
                        break
                    QTest.qWait(5)
                self.assertIsNotNone(backend.controller_result)
                self.assertEqual(backend.samples['ready'].value, 1)
                self.assertFalse(backend.can_start)
                backend.device.serial_connection.client.controller.boot_id += 1
                backend.request_controller()
                for _ in range(100):
                    if not backend.serial_read_pending:
                        break
                    QTest.qWait(5)
                self.assertIsNone(backend.controller_info)
                self.assertIsNone(backend.controller_result)
                self.assertTrue(all(sample.quality == 'stale' for sample in backend.samples.values()))
            finally:
                backend.shutdown()
                deadline = time.monotonic() + 3
                while not backend.closed and time.monotonic() < deadline:
                    QTest.qWait(10)
                self.assertTrue(backend.closed)
                backend.deleteLater()
                QTest.qWait(1)
