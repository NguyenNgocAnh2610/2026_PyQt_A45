"""Virtual COM port: real Modbus RTU bytes between SerialConnection and the
simulated CPUv1.0 slave (FreeModbus behaviour, CPU main-loop latency).

No physical port is opened.
"""
from copy import deepcopy
import struct
import tempfile
import time
import unittest

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.backend import Backend
from src.common.profiles import ProfileError, load_profile, validate_profile
from src.common.stm32 import ReadRegister as RI, WriteRegister as WO
from src.common.testing import Mode
from src.protocol import Stm32IoMap, crc16_modbus, rtu_adu, rtu_request_pdu, split_rtu_adu
from src.simulator import Stm32RtuSlave, Stm32Simulator
from src.virtual_port import VirtualLine, create_virtual_connection

POWER_DC = [{'signal': s, 'value': 1} for s in ('dc_27v', 'dc_15v_pos', 'dc_15v_neg', 'dc_12v_pos', 'dc_12v_neg',
                                                 'dc_5v_pos', 'dc_5v_neg')]


def wait(predicate, timeout=4000):
    start = time.monotonic()
    while not predicate() and (time.monotonic() - start) * 1000 < timeout:
        QTest.qWait(5)
    return predicate()


class RtuFrameTests(unittest.TestCase):
    def test_crc_matches_the_modbus_reference_vector(self):
        # Standard Modbus example "01 03 00 00 00 01 84 0A". The CRC bytes shown
        # in docs/PHAN_TICH_GIAO_THUC_VA_LUONG_CODE.md (D5 6E, 84 5C) are not
        # valid CRC16 values; the real frames are below.
        self.assertEqual(rtu_adu(1, rtu_request_pdu(3, 0, count=1)).hex(' '), '01 03 00 00 00 01 84 0a')
        self.assertEqual(rtu_adu(9, bytes.fromhex('10 0001 001C')).hex(' '), '09 10 00 01 00 1c 91 48')
        self.assertEqual(rtu_adu(4, rtu_request_pdu(3, 0, count=5))[-2:], bytes.fromhex('859C'))
        raw = rtu_adu(9, rtu_request_pdu(3, 1, count=29))
        self.assertEqual(raw[:6].hex(' '), '09 03 00 01 00 1d')
        self.assertEqual(split_rtu_adu(raw), (9, raw[1:-2]))
        with self.assertRaises(ValueError):
            split_rtu_adu(raw[:-1] + bytes([raw[-1] ^ 1]))
        self.assertEqual(crc16_modbus(b''), 0xFFFF)


class Stm32RtuSlaveTests(unittest.TestCase):
    def setUp(self):
        self.sim = Stm32Simulator()
        self.slave = Stm32RtuSlave(self.sim)

    def ask(self, pdu, slave=9):
        return self.slave.handle(rtu_adu(slave, pdu))

    def test_fc03_returns_di_bank_with_byte_count(self):
        reply = self.ask(rtu_request_pdu(3, 1, count=29))
        server, pdu = split_rtu_adu(reply)
        self.assertEqual((server, pdu[0], pdu[1], len(reply)), (9, 3, 58, 63))
        words = struct.unpack('>29H', pdu[2:])
        self.assertEqual(words[RI.ADC0_val - 1], 1234)

    def test_fc06_and_fc16_write_do_bank_and_acknowledge(self):
        request = rtu_request_pdu(6, WO.Power, [0b10])
        self.assertEqual(split_rtu_adu(self.ask(request))[1], request)  # FC06 echo.
        reply = self.ask(rtu_request_pdu(16, WO.Mode, [1, 2]))
        self.assertEqual(split_rtu_adu(reply)[1], struct.pack('>BHH', 16, WO.Mode, 2))
        self.assertEqual(self.sim.mod_buf_to_write[WO.Mode:WO.Mode + 2], [1, 2])
        self.assertEqual(self.sim.mod_buf_to_write[WO.Power], 0b10)
        self.ask(rtu_request_pdu(6, 0, [7]))  # The firmware callback also takes index 0.
        self.assertEqual(self.sim.mod_buf_to_write[0], 7)

    def test_bad_crc_other_slave_and_broadcast_are_silent(self):
        raw = rtu_adu(9, rtu_request_pdu(3, 1, count=1))
        self.assertIsNone(self.slave.handle(raw[:-1] + bytes([raw[-1] ^ 0xFF])))
        self.assertIsNone(self.ask(rtu_request_pdu(3, 1, count=1), slave=3))
        self.assertIsNone(self.ask(rtu_request_pdu(6, WO.Power, [1]), slave=0))
        self.assertEqual(self.sim.mod_buf_to_write[WO.Power], 0)

    def test_exceptions_like_freemodbus(self):
        cases = [(rtu_request_pdu(3, 25, count=10), 0x83, 2),      # Past mod_buf_to_read[29].
                 (rtu_request_pdu(3, 1, count=0), 0x83, 3),
                 (rtu_request_pdu(6, 29, [1]), 0x86, 2),           # Past mod_buf_to_write[28].
                 (rtu_request_pdu(16, 1, [1, 2])[:-1], 0x90, 3),   # Byte count mismatch.
                 (bytes([5, 0, 1, 0xFF, 0]), 0x85, 1)]             # FC05 not implemented.
        for pdu, function, code in cases:
            with self.subTest(pdu=pdu.hex()):
                self.assertEqual(split_rtu_adu(self.ask(pdu))[1], bytes([function, code]))
        self.assertEqual(self.sim.mod_buf_to_write, [0] * 29)


class CpuLoopLatencyTests(unittest.TestCase):
    def test_di_shows_a_new_mux_channel_only_after_the_main_loop_ran_it(self):
        p = load_profile()
        io = Stm32IoMap(p.hardware['stm32_io'])
        now = [10.0]
        sim = Stm32Simulator(io_map=io, cases=p.fixtures['stm32_cases'], clock=lambda: now[0], loop_ms=50)
        image = io.apply(io.safe_image(), POWER_DC)
        image[WO.MUX] = io.mux_word(io.inputs['dc_current'])
        for address, words in io.writes(None, image):
            sim.write(9, address, words)  # ACKed immediately, executed later.
        self.assertEqual(sim.read(9)[RI.ADC3_val - 1], 1200)  # Still the old DI copy.
        now[0] += 0.060
        self.assertEqual(sim.read(9)[RI.ADC3_val - 1], 1200)  # Loop running it has not finished.
        now[0] += 0.045
        self.assertEqual(sim.read(9)[RI.ADC3_val - 1], 137)  # ≤ 2 loops after the write.

    def test_adc_noise_changes_once_per_loop(self):
        now = [10.0]
        sim = Stm32Simulator(clock=lambda: now[0], loop_ms=50)
        seen = []
        for i in range(8):
            now[0] = 10.0125 + 0.025 * i  # Two reads per loop, away from loop boundaries.
            seen.append(sim.read(9)[RI.ADC2_val - 1])
        self.assertEqual([seen[i] == seen[i + 1] for i in range(0, 8, 2)], [True] * 4)
        self.assertEqual(len(set(seen)), 2)

    def test_profile_requires_runner_wait_to_be_valid(self):
        p = deepcopy(load_profile())
        p.hardware['stm32_io']['di_update_ms'] = -1
        with self.assertRaises(ProfileError):
            validate_profile(p)
        p = deepcopy(load_profile())
        p.fixtures['stm32_timing']['loop_ms'] = 'nhanh'
        with self.assertRaises(ProfileError):
            validate_profile(p)
        p = load_profile()
        self.assertGreaterEqual(p.hardware['stm32_io']['di_update_ms'], 2 * p.fixtures['stm32_timing']['loop_ms'])


class VirtualPortTests(unittest.TestCase):
    """The application's SerialConnection, unchanged, over the virtual port."""
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.sim = Stm32Simulator()
        self.line = VirtualLine(Stm32RtuSlave(self.sim))
        self.link = create_virtual_connection(None, self.line)
        self.events, self.frames = [], []
        self.link.read_finished.connect(lambda r, e: self.events.append(('read', r, e)))
        self.link.write_finished.connect(lambda r, e: self.events.append(('write', r, e)))
        self.link.frame_logged.connect(lambda d, raw: self.frames.append((d, raw)))
        from src.common.serial import SerialSettings
        self.link.open(SerialSettings('rtu', 'COM ảo', 115200))
        self.assertEqual(self.link.state, 'open')

    def tearDown(self):
        self.link.close()

    def test_read_and_writes_go_through_rtu_bytes_with_wire_timing(self):
        start = time.monotonic()
        self.link.read_registers(9, 3, 1, 29)
        self.assertTrue(wait(lambda: self.events))
        elapsed = (time.monotonic() - start) * 1000
        kind, result, error = self.events.pop()
        self.assertEqual((kind, error), ('read', ''))
        self.assertEqual(result['values'], self.sim.read(9))
        self.assertGreaterEqual(elapsed, 8)  # 71 characters at 115200 baud + gaps.
        self.assertEqual(self.frames[0], ('TX', rtu_adu(9, rtu_request_pdu(3, 1, count=29))))
        self.assertEqual(self.frames[1][1][:3], bytes([9, 3, 58]))
        for address, values, function in ((int(WO.Power), [2], 6), (int(WO.Mode), [1, 2], 16)):
            self.link.write_registers(9, address, values)
            self.assertTrue(wait(lambda: self.events))
            kind, result, error = self.events.pop()
            self.assertEqual((kind, error, result['function']), ('write', '', function))
        self.assertEqual(self.sim.mod_buf_to_write[WO.Mode:WO.Mode + 2], [1, 2])
        self.assertEqual(self.link.state, 'open')

    def test_exception_reply_is_reported_and_port_stays_open(self):
        self.link.write_registers(9, 40, [1])
        self.assertTrue(wait(lambda: self.events))
        kind, result, error = self.events.pop()
        self.assertIsNone(result)
        self.assertIn('exception 2', error)
        self.assertEqual(self.frames[-1], ('RX', rtu_adu(9, bytes([0x86, 2]))))
        self.assertEqual(self.link.state, 'open')

    def test_silent_slave_times_out_and_closes_the_port_like_a_real_one(self):
        self.line.scenario, self.line.stage = 'timeout', 'apply'
        states = []
        self.link.status_changed.connect(lambda s, d: states.append((s, d)))
        self.link.write_registers(9, int(WO.Power), [2])
        self.assertTrue(wait(lambda: self.events, 3000))
        kind, result, error = self.events.pop()
        self.assertIsNone(result)
        self.assertEqual(self.link.state, 'error')
        self.assertIn('Chưa biết lệnh đã thực thi', states[-1][1])
        self.assertEqual(self.sim.mod_buf_to_write[WO.Power], 0)  # Never reached the slave.

    def test_unplugged_cable_reports_a_connection_error(self):
        self.line.scenario, self.line.stage = 'disconnect', 'measure'
        self.link.read_registers(9, 3, 1, 29)
        self.assertTrue(wait(lambda: self.events))
        self.assertIsNone(self.events[-1][1])
        self.assertEqual(self.link.state, 'error')
        self.assertIn('rút cáp', self.link_detail())

    def link_detail(self):
        return self.events[-1][2]


class RunnerOverVirtualPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.backends = []

    def tearDown(self):
        for b in self.backends:
            if not b.closed:
                b.shutdown()
            wait(lambda: b.closed and not b.store.busy, 8000)
            b.deleteLater()
        QTest.qWait(1)
        self.temp.cleanup()

    def run_p02(self, profile=None):
        b = Backend(profile or load_profile(), storage_dir=self.temp.name)
        self.backends.append(b)
        b.configure(serial_number='SAMPLE-001', time_scale=60.0, mode=Mode.MANUAL)
        b.select_test('P02')
        b.connect_device()
        self.assertTrue(wait(lambda: b.connection == 'Sẵn sàng · MÔ PHỎNG'))
        self.assertEqual(b.device.virtual_connection.state, 'open')
        self.assertTrue(b.start())
        self.assertTrue(wait(lambda: not b.busy, 15000))
        return b

    def test_p02_runs_over_the_virtual_com_port(self):
        b = self.run_p02()
        self.assertEqual(b.session['verdict'], 'PASS')
        self.assertGreater(b.device.virtual_line.frames, 5)
        frames = b.stm32.frames[True]
        self.assertEqual(frames['TX'][:4], bytes([9, 16, 0, WO.MUX]))  # Last write: MUX idle + Power off (FC16).
        self.assertEqual(split_rtu_adu(frames['RX'])[0], 9)

    def test_too_short_wait_after_mux_reads_the_old_channel_and_fails(self):
        profile = deepcopy(load_profile())
        profile.hardware['stm32_io'].update(di_update_ms=0, mux_settle_ms=0)
        b = self.run_p02(profile)
        self.assertEqual(b.attempt['status'], 'FAIL')  # The simulator exposes the timing error.

    def test_disconnect_closes_virtual_port(self):
        b = self.run_p02()
        b.disconnect_device()
        self.assertEqual(b.device.virtual_connection.state, 'disconnected')
        self.assertFalse(b.can_start)


if __name__ == '__main__':
    unittest.main()
