"""Real-hardware path and the Test Modbus tool, without a real COM port.

The application's *physical* SerialConnection is built on a virtual RTU line
to a CPUv1.1 register simulator (slave 11, 50 ms main loop), so everything the
real connection does (verify on open, gates, self-test, runner, tool) runs
through the same code as on the bench.
"""
import tempfile
import time
import unittest
from copy import deepcopy
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.backend import Backend
from src.common.profiles import load_profile, stm32_io_map, stm32_unverified
from src.common.serial import SerialSettings
from src.common.stm32 import WriteRegister as WO
from src.common.testing import Mode, READY_REAL
from src.simulator import Stm32Simulator, Stm32RtuSlave
from src.virtual_port import VirtualLine, create_virtual_connection

MATRIX0 = 18


def verified(profile, outputs=(), inputs=()):
    io = profile.hardware['stm32_io']
    for sid in outputs:
        io['outputs'][sid]['status'] = 'verified'
    for sid in inputs:
        io['inputs'][sid]['status'] = 'verified'
    return profile


class RealBenchTests(unittest.TestCase):
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
        for b in self.backends:
            self.wait(lambda: b.closed and not b.store.busy)
            b.deleteLater()
        QTest.qWait(1)
        self.temp.cleanup()

    def wait(self, predicate, timeout=8000):
        start = time.monotonic()
        while not predicate() and (time.monotonic() - start) * 1000 < timeout:
            QTest.qWait(10)
        self.assertTrue(predicate(), 'Timed out waiting for asynchronous state')

    def backend(self, profile=None, slave=11):
        profile = profile or load_profile()
        self.bench = Stm32Simulator(slave=slave, io_map=stm32_io_map(profile),
                                    cases=profile.fixtures['stm32_cases'], loop_ms=50)
        line = VirtualLine(Stm32RtuSlave(self.bench))
        with patch('src.device.SerialConnection', side_effect=lambda parent: create_virtual_connection(parent, line)):
            b = Backend(profile, storage_dir=self.temp.name)
        self.backends.append(b)
        b.configure(serial_number='SAMPLE-001')
        return b

    def connect_real(self, b):
        b.connect_serial(SerialSettings('rtu', 'COM_BENCH', 115200))
        self.wait(lambda: b.connection not in ('Đang mở COM…', 'Đang xác minh STM32 thật')
                  and not b.connection.startswith('Đã mở'))

    def test_opening_the_port_verifies_the_cpu_without_writing(self):
        b = self.backend()
        self.connect_real(b)
        self.assertEqual(b.connection, READY_REAL)
        self.assertTrue(b.can_start)
        self.assertEqual(self.bench.mod_buf_to_write, [0] * len(self.bench.mod_buf_to_write))  # FC03 only.
        self.assertIn('slave 11', b.message)

    def test_wrong_slave_is_reported_not_ready(self):
        b = self.backend(slave=12)  # CPU board ID switch differs from the profile.
        self.connect_real(b)
        self.assertEqual(b.connection, 'Không có phản hồi STM32 (slave 11)')
        self.assertFalse(b.can_start)

    def test_self_test_runs_on_real_hardware_after_confirmation(self):
        b = self.backend()
        self.connect_real(b)
        b.configure(mode=Mode.SELF, serial_number='', time_scale=60.0)
        self.assertFalse(b.start())  # Real run needs the operator's confirmation.
        self.assertIn('xác nhận', b.message)
        self.assertTrue(b.start(confirm_real=True))
        self.wait(lambda: not b.busy, 15000)
        statuses = {a['test_id']: a['status'] for a in b.session['attempts']}
        self.assertEqual(statuses, {'D01': 'PASS', 'D02': 'PASS', 'D03': 'BLOCKED'})
        self.assertFalse(b.session['simulation'])
        self.assertEqual(b.session['time_scale'], 1.0)  # Never shortened on real hardware.
        self.assertEqual(b.session['cpu_map'], 'CPUv1.1')
        self.assertEqual(b.loop_check['status'], 'PASS')
        self.assertEqual(self.bench.mod_buf_to_write[WO.Mode], 1)
        self.assertEqual(self.bench.mod_buf_to_write[WO.MUX], 31 << 8 | 31)  # Safe state written.
        self.assertIn('COM THẬT', b.message)

    def test_tests_are_blocked_until_mapping_verified_and_loop_measured(self):
        b = self.backend()
        self.connect_real(b)
        b.configure(mode=Mode.MANUAL)
        b.select_test('P02')
        blockers = b.real_run_blockers()
        self.assertTrue(any('D02' in x for x in blockers))
        self.assertTrue(any(x.startswith('P02: ánh xạ chưa đo kiểm') for x in blockers))
        self.assertFalse(b.start(confirm_real=True))
        self.assertEqual(self.bench.mod_buf_to_write[WO.Mode], 0)  # Nothing was written.

    def test_verified_test_runs_on_real_hardware_with_unscaled_waits(self):
        profile = verified(deepcopy(load_profile()),
                           outputs=['dc_27v', 'dc_15v_pos', 'dc_15v_neg', 'dc_12v_pos', 'dc_12v_neg', 'dc_5v_pos',
                                    'dc_5v_neg'], inputs=['dc_current'])
        self.assertEqual(stm32_unverified(profile, profile.tests[1]), [])
        b = self.backend(profile)
        self.connect_real(b)
        b.configure(mode=Mode.SELF, serial_number='', time_scale=60.0)
        self.assertTrue(b.start(confirm_real=True))
        self.wait(lambda: not b.busy and not b.store.busy, 15000)
        self.assertTrue(b.new_session())
        b.configure(mode=Mode.MANUAL, serial_number='SAMPLE-001')
        b.select_test('P02')
        self.assertEqual(b.real_run_blockers(), [])
        started = time.monotonic()
        self.assertTrue(b.start(confirm_real=True))
        self.wait(lambda: not b.busy, 15000)
        self.assertGreaterEqual(time.monotonic() - started, 0.25)  # 250 ms wait, not ÷60.
        self.assertEqual((b.session['verdict'], b.attempt['measurements'][0]['value']), ('PASS', 1.37))
        self.assertEqual(self.bench.mod_buf_to_write[WO.Power], 0)  # Back to the safe state.
        self.assertIn(b.attempt['measurements'][0]['step_id'], ('S01',))
        self.assertEqual(b.samples['dc_current'].source, 'stm32')  # Real source label, not stm32-sim.

    def test_tool_drives_real_boards_through_the_runner_rules(self):
        b = self.backend()
        self.connect_real(b)
        b.tool_take_control(False, 11)
        self.wait(lambda: not b.tool_busy)
        self.assertTrue(b.tool_image_known())
        self.assertEqual(self.bench.mod_buf_to_write[WO.Mode], 1)
        b.tool_set([{'signal': 'set_40', 'value': 3}])
        self.wait(lambda: not b.tool_busy)
        self.assertEqual(self.bench.mod_buf_to_write[MATRIX0], 1)
        with self.assertRaises(ValueError):
            b.tool_set([{'signal': 'ac_36v', 'value': 1}, {'signal': 'ac_22v', 'value': 1}])  # Interlock.
        with self.assertRaises(ValueError):
            b.tool_set_word('MUX', 32)  # RLMUX would read past Mux_Decoder[32].
        b.tool_safe_state()
        self.wait(lambda: not b.tool_busy)
        self.assertEqual(self.bench.mod_buf_to_write[MATRIX0], 0)


class ToolTests(unittest.TestCase):
    """Test Modbus tool on the virtual port (simulation)."""
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.b = Backend(load_profile(), storage_dir=self.temp.name)
        self.sim = self.b.device.stm32_simulator

    def tearDown(self):
        self.b.shutdown()
        start = time.monotonic()
        while not (self.b.closed and not self.b.store.busy) and time.monotonic() - start < 5:
            QTest.qWait(10)
        self.b.deleteLater()
        QTest.qWait(1)
        self.temp.cleanup()

    def idle(self):
        start = time.monotonic()
        while (self.b.tool_busy or self.b.serial_read_pending) and time.monotonic() - start < 5:
            QTest.qWait(10)
        self.assertFalse(self.b.tool_busy)

    def test_control_requires_known_state_and_breaks_before_make(self):
        b = self.b
        with self.assertRaises(ValueError):
            b.tool_set([{'signal': 'set_40', 'value': 3}])  # Unknown outputs: take control first.
        b.tool_take_control(True, 11)
        self.assertFalse(b.can_start)  # Runner waits while the tool queue runs.
        self.idle()
        writes = []
        original = self.sim.write

        def record(slave, address, values):
            writes.append((address, list(values), time.monotonic()))
            return original(slave, address, values)
        with patch.object(self.sim, 'write', side_effect=record):
            b.tool_set([{'signal': 'set_40', 'value': 3}])
            self.idle()
            b.tool_set([{'signal': 'set_40', 'value': -3}])
            self.idle()
        self.assertEqual([(a, v) for a, v, _ in writes], [(MATRIX0, [1]), (MATRIX0, [0]), (MATRIX0, [2])])
        self.assertGreaterEqual(writes[2][2] - writes[1][2], 0.15)  # break_ms between open and close.

    def test_raw_register_write_makes_tool_state_unknown(self):
        b = self.b
        b.tool_take_control(True, 11)
        self.idle()
        b.stage_stm32(WO.DOUT, [1])
        b.request_stm32(simulation=True, slave=11, address=WO.DOUT)
        self.idle()
        self.assertFalse(b.tool_image_known())
        with self.assertRaises(ValueError):
            b.tool_set_word('DOUT', 2)

    def test_raw_mux_write_out_of_range_is_refused(self):
        b = self.b
        b.stage_stm32(WO.MUX, [40])
        with self.assertRaises(ValueError):
            b.request_stm32(simulation=True, slave=11, address=WO.MUX)
        self.assertEqual(self.sim.mod_buf_to_write[WO.MUX], 0)

    def test_background_read_keeps_controls_and_queues_commands(self):
        from src.ui.widgets.modbus_test import ModbusTestPage
        page = ModbusTestPage(self.b)
        try:
            page.show()
            boards = page.boards
            boards.take.click()
            self.idle()
            message = self.b.stm32.message
            boards._read(quiet=True)  # What the auto-read timer does.
            self.assertTrue(self.b.serial_read_pending and self.b.stm32_background)
            self.assertEqual(self.b.stm32.message, message)  # No "waiting…" text churn.
            self.assertTrue(boards.take.isEnabled())  # Page is not greyed out by a background read.
            self.assertTrue(boards.matrix_tables[0][2].isEnabled())
            self.assertTrue(page.registers.read_button.isEnabled())
            # A click during the read is queued, then sent once the read returns.
            boards._matrix_click(*boards.matrix_tables[0][:2], 0, 0)
            self.assertTrue(self.b.tool_busy)
            self.idle()
            self.assertEqual(self.sim.mod_buf_to_write[MATRIX0], 1)
            self.assertTrue(self.b.tool_image_known())
            self.assertNotEqual(boards.values['Cập nhật'].text(), 'chưa có')
            # A foreground (operator) read still locks the page while it runs.
            boards._read()
            self.assertFalse(boards.take.isEnabled())
            self.idle()
            self.assertTrue(boards.take.isEnabled())
        finally:
            page.close()
            page.deleteLater()

    def test_pc_never_addresses_a_sub_board(self):
        b = self.b
        sent = []
        original = self.sim.write
        with patch.object(self.sim, 'write', side_effect=lambda *a: sent.append(a) or original(*a)):
            for slave in (1, 2, 3, 4, 6, 7):  # Switch, RLMUX, RLPW, HMI, RLMatrix IDs on the CPU's own bus.
                with self.assertRaisesRegex(ValueError, 'chỉ giao tiếp với CPU slave 11'):
                    b.request_stm32(simulation=True, slave=slave)
                with self.assertRaisesRegex(ValueError, 'chỉ giao tiếp với CPU slave 11'):
                    b.tool_take_control(True, slave)
            self.assertFalse(b.serial_read_pending or b.tool_busy)
            b.tool_take_control(True, 11)
            self.idle()
        self.assertTrue(sent)
        self.assertEqual({call[0] for call in sent}, {11})  # Every frame went to the CPU.

    def test_slave_boxes_show_the_cpu_and_cannot_be_changed(self):
        from src.ui.widgets.modbus_test import ModbusTestPage
        page = ModbusTestPage(self.b)
        try:
            for box in (page.boards.slave, page.registers.slave):
                self.assertEqual(box.value(), 11)
                self.assertTrue(box.isReadOnly())
                box.setValue(6)
                self.assertEqual(box.value(), 11)
        finally:
            page.close()
            page.deleteLater()

    def test_route_labels_say_boards_are_reached_through_the_cpu(self):
        from src.ui.widgets.modbus_test import ModbusTestPage
        page = ModbusTestPage(self.b)
        try:
            text = page.boards.route.text()
            self.assertIn('slave 11', text)
            self.assertIn('Power → RLPW ID 3', text)
            self.assertIn('Matrix0/Matrix1 → RLMatrix ID 6', text)
            self.assertIn('MUX → RLMUX ID 2', text)
        finally:
            page.close()
            page.deleteLater()

    def test_test_modbus_page_controls(self):
        from src.ui.widgets.modbus_test import ModbusTestPage
        page = ModbusTestPage(self.b)
        try:
            page.show()
            boards = page.boards
            self.assertFalse(boards.matrix_tables[0][2].isEnabled())  # Locked until control is taken.
            boards.take.click()
            self.idle()
            board, rows, table = boards.matrix_tables[0]
            boards._matrix_click(board, rows, 0, 0)  # 40XP1 ← IN1 (+3 V).
            self.idle()
            self.assertEqual(self.sim.mod_buf_to_write[MATRIX0], 1)
            self.assertEqual(table.item(0, 0).text(), '●')
            sid, button = boards.power_buttons[2]
            self.assertEqual(sid, 'dc_27v')
            button.click()
            self.idle()
            self.assertEqual(self.sim.mod_buf_to_write[WO.Power], 1 << 2)
            boards.mux_boxes[0].setCurrentIndex(14)
            boards.mux_apply.click()
            self.idle()
            self.assertEqual(self.sim.mod_buf_to_write[WO.MUX], 31 << 8 | 14)
            boards.safe.click()
            self.idle()
            self.assertEqual(self.sim.mod_buf_to_write[WO.Power], 0)
            self.assertIn('Về an toàn', '\n'.join(page.log.lines()))
        finally:
            page.close()
            page.deleteLater()


if __name__ == '__main__':
    unittest.main()
