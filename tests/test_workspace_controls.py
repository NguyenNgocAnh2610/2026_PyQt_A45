"""Generic UI tests. No serial port is opened or test recipe executed."""
from types import SimpleNamespace
import tempfile
import time
import unittest

from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication

from src.ui.widgets.connection_bar import ConnectionBar
from src.ui.widgets.signal_monitor import SignalMonitor


class FakeConnectionBackend(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.profile = SimpleNamespace(hardware={'serial': {}})
        self.connection = 'Chưa kết nối'
        self.busy = False
        self.closed = False
        self.calls = []
        self.ports = [('COM7', 'USB demo'), ('COM9', 'USB demo 2')]
        self.serial_state = 'disconnected'
        self.serial_detail = ''
        self.serial_result = None
        self.controller_info = None
        self.controller_result = None
        self.serial_read_pending = False
        self.uart_last_hex = ''

    def available_serial_ports(self):
        return self.ports

    def connect_device(self):
        self.calls.append('connect_mock')
        self.connection = 'Sẵn sàng · MÔ PHỎNG'
        self.changed.emit()

    def disconnect_device(self):
        self.calls.append('disconnect_mock')
        self.serial_state = 'disconnected'
        self.connection = 'Chưa kết nối'
        self.changed.emit()

    def connect_serial(self, settings):
        self.calls.append(settings)
        self.serial_state = 'open'
        self.connection = f'Đã mở {settings.port}'
        self.changed.emit()

    def read_serial_registers(self, slave, function, address, count):
        self.calls.append((slave, function, address, count))
        self.serial_read_pending = True
        self.serial_detail = 'Đang chờ phản hồi Modbus…'
        self.changed.emit()


class WorkspaceControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.backend = FakeConnectionBackend()
        self.bar = ConnectionBar(self.backend)

    def tearDown(self):
        self.bar.close()
        self.bar.deleteLater()
        QTest.qWait(1)

    def test_discovery_does_not_select_baud_slave_or_open_port(self):
        self.assertIsNone(self.bar.port.currentData())
        self.assertIsNone(self.bar.baud.currentData())
        self.assertIsNone(self.bar.slave.currentData())
        self.assertEqual(self.bar.port.count(), 3)
        self.assertEqual(self.backend.calls, [])

    def test_mock_toggle_connects_and_disconnects(self):
        self.bar.toggle.click()
        self.assertEqual(self.bar.toggle.text(), 'Ngắt')
        self.bar.toggle.click()
        self.assertEqual(self.bar.toggle.text(), 'Kết nối')
        self.assertEqual(self.backend.calls, ['connect_mock', 'disconnect_mock'])

    def test_rtu_never_opens_mock_and_does_not_claim_connection(self):
        self.bar.toggle.click()
        self.bar.adapter.setCurrentIndex(1)
        self.assertEqual(self.backend.calls, ['connect_mock', 'disconnect_mock'])
        self.assertTrue(self.bar.port.isEnabled())
        self.assertTrue(self.bar.toggle.isEnabled())
        self.assertEqual('Chưa kết nối', self.bar.status.text())
        self.bar.toggle.click()
        self.assertEqual(len(self.backend.calls), 2)

    def test_uart_opens_selected_port_and_locks_settings_until_disconnect(self):
        self.bar.adapter.setCurrentIndex(self.bar.adapter.findData('uart'))
        self.assertFalse(self.bar.slave.isVisible())
        self.assertEqual(self.bar.adapter.maxVisibleItems(), 8)
        self.assertEqual(self.bar.port.maxVisibleItems(), 8)
        notices = QSignalSpy(self.bar.notice)
        self.bar.toggle.click()
        self.assertIn('Thiếu thông số', notices.at(0)[0])
        self.bar.port.setCurrentIndex(1)
        self.bar.baud.setCurrentIndex(1)
        self.bar.toggle.click()
        self.assertEqual(notices.count(), 1)
        self.assertEqual(self.backend.calls[0].adapter, 'uart')
        self.assertEqual(self.backend.calls[0].port, 'COM7')
        self.assertEqual(self.backend.calls[0].framing, '8N1')
        self.assertEqual(self.bar.status.text(), 'Đã mở COM7')
        self.assertFalse(self.bar.baud.isEnabled())
        self.assertFalse(self.bar.details.framing_group.isEnabled())
        self.bar.toggle.click()
        self.assertTrue(self.bar.baud.isEnabled())

    def test_rtu_opens_without_slave_and_passes_explicit_framing(self):
        self.bar.adapter.setCurrentIndex(1)
        self.bar.port.setCurrentIndex(1)
        self.bar.baud.setCurrentIndex(self.bar.baud.findData(9600))
        self.bar.details.parity.setCurrentIndex(self.bar.details.parity.findData('E'))
        self.bar.details.stops.setCurrentIndex(self.bar.details.stops.findData(2))
        self.assertIsNone(self.bar.slave.currentData())
        self.bar.toggle.click()
        settings = self.backend.calls[0]
        self.assertEqual((settings.adapter, settings.baudrate, settings.framing), ('rtu', 9600, '8E2'))
        self.assertEqual(self.bar.toggle.text(), 'Ngắt')
        self.bar.adapter.setCurrentIndex(0)
        self.assertEqual(self.backend.serial_state, 'disconnected')

    def test_read_dialog_requires_address_and_forwards_explicit_request(self):
        self.bar.adapter.setCurrentIndex(1)
        self.bar.port.setCurrentIndex(1)
        self.bar.baud.setCurrentIndex(1)
        self.bar.toggle.click()
        dialog = self.bar.details
        dialog.slave.setValue(17)
        dialog.function.setCurrentIndex(dialog.function.findData(4))
        dialog.read_button.click()
        self.assertIn('Hãy nhập', dialog.status.text())
        self.assertEqual(len(self.backend.calls), 1)
        dialog.address.setText('123')
        dialog.count.setValue(2)
        dialog.read_button.click()
        self.assertEqual(self.backend.calls[-1], (17, 4, 123, 2))
        self.assertEqual(self.bar.slave.currentData(), 17)
        self.assertFalse(dialog.read_button.isEnabled())
        self.assertTrue(self.bar.toggle.isEnabled())

    def test_connection_dropdown_shows_uart_without_clipping(self):
        self.bar.show()
        self.bar.adapter.showPopup()
        QTest.qWait(50)
        view = self.bar.adapter.view()
        rect = view.visualRect(view.model().index(2, 0))
        self.assertTrue(view.viewport().rect().contains(rect))
        self.bar.adapter.hidePopup()

    def test_pwm_preview_has_exact_edges_and_four_cycles(self):
        from src.common.monitor import demo_pwm_frame
        frame = demo_pwm_frame(1000, 25)
        self.assertEqual(frame.window_ms, 4)
        self.assertEqual(frame.points[:5], ((0, 0), (0, 5), (.25, 5), (.25, 0), (1, 0)))
        self.assertEqual(len(frame.points), 20)
        self.assertTrue(all(a[0] <= b[0] for a, b in zip(frame.points, frame.points[1:])))
        with self.assertRaises(ValueError):
            demo_pwm_frame(0, 50)

    def test_rescan_retains_selection_and_clears_removed_port(self):
        self.bar.port.setCurrentIndex(self.bar.port.findData('COM9'))
        self.bar.refresh_ports()
        self.assertEqual(self.bar.port.currentData(), 'COM9')
        self.backend.ports = [('COM7', 'Other')]
        self.bar.refresh_ports()
        self.assertIsNone(self.bar.port.currentData())

    def test_discovery_failure_stays_disconnected(self):
        def fail():
            raise OSError('Unavailable')
        self.backend.available_serial_ports = fail
        self.bar.refresh_ports()
        self.assertIsNone(self.bar.port.currentData())
        self.assertEqual(self.bar.port.currentText(), 'Lỗi tìm cổng')
        self.assertEqual(self.backend.calls, [])

    def test_controls_lock_while_busy(self):
        self.backend.busy = True
        self.backend.changed.emit()
        self.assertFalse(self.bar.adapter.isEnabled())
        self.assertFalse(self.bar.toggle.isEnabled())

    def test_monitor_is_independent_and_does_not_invent_channels(self):
        monitor = SignalMonitor()
        self.assertEqual([monitor.kind_combo.itemText(i) for i in range(2)], ['Analog', 'PWM'])
        self.assertEqual(monitor.channel_combo.count(), 1)
        self.assertIsNone(monitor.channel_combo.currentData())
        self.assertFalse(monitor.channel_combo.isEnabled())
        monitor.kind_combo.setCurrentText('PWM')
        self.assertIn('PWM', monitor.hint.text())
        monitor.deleteLater()

    def test_monitor_only_lists_curated_external_channels(self):
        monitor = SignalMonitor(channels=[
            {'id': 'external_a', 'label': 'Analog A', 'unit': 'V', 'kind': 'analog'},
            {'id': 'external_pwm', 'label': 'PWM A', 'unit': 'Hz', 'kind': 'pwm'},
        ])
        self.assertEqual(monitor.channel_combo.count(), 1)
        self.assertEqual(monitor.channel_combo.currentData(), 'external_a')
        monitor.kind_combo.setCurrentText('PWM')
        self.assertEqual(monitor.channel_combo.count(), 1)
        self.assertEqual(monitor.channel_combo.currentData(), 'external_pwm')
        monitor.deleteLater()

    def test_monitor_metadata_validation_uses_no_bench_signal_references(self):
        from copy import deepcopy
        from tests.test_bench import alternative_profile
        from src.common.profiles import validate_profile, ProfileError
        profile = alternative_profile()
        channel = {'id': 'external', 'label': 'Analog A', 'unit': 'V', 'kind': 'analog'}
        profile.system['monitor_channels'] = [channel]
        validate_profile(profile)
        for channels in ([channel, channel], [dict(channel, kind='digital')],
                         [dict(channel, id=str(i)) for i in range(7)], [None]):
            invalid = deepcopy(profile)
            invalid.system['monitor_channels'] = channels
            with self.assertRaises(ProfileError):
                validate_profile(invalid)

    def test_demo_monitor_does_not_connect_or_feed_test_measurements(self):
        from src.backend import Backend
        from tests.test_bench import alternative_profile
        with tempfile.TemporaryDirectory() as folder:
            backend = Backend(alternative_profile(), storage_dir=folder)
            monitor = SignalMonitor(backend=backend, channels=backend.monitor_channels)
            try:
                QTest.qWait(350)
                self.assertEqual(backend.connection, 'Chưa kết nối')
                self.assertEqual(backend.samples, {})
                self.assertIsNone(backend.session)
                self.assertEqual(len(backend.monitor_samples), 4)
                self.assertTrue(all(s.source == 'monitor_demo' for s in backend.monitor_samples.values()))
                self.assertGreater(monitor.series.count(), 1)
                monitor.toggle.click()
                self.assertFalse(backend.monitor_enabled)
                self.assertEqual(monitor.series.count(), 0)
                self.assertEqual(monitor.value_label.text(), '—')
                self.assertTrue(all(s.quality == 'stale' for s in backend.monitor_samples.values()))
                monitor.toggle.click()
                QTest.qWait(150)
                self.assertGreater(monitor.series.count(), 0)
                monitor.kind_combo.setCurrentText('PWM')
                self.assertEqual(monitor.channel_combo.count(), 2)
                self.assertEqual(monitor.channel_combo.currentText(), 'PWM 1')
                self.assertIn('Hz', monitor.value_label.text())
                self.assertIn('%', monitor.value_label.text())
                self.assertEqual(monitor.series.count(), 20)
                monitor.channel_combo.setCurrentIndex(1)
                self.assertEqual(monitor.channel_combo.currentText(), 'PWM 2')
                self.assertEqual(monitor.x_axis.labelFormat(), '%.1f ms')
            finally:
                backend.shutdown()
                deadline = time.monotonic() + 3
                while not backend.closed and time.monotonic() < deadline:
                    QTest.qWait(20)
                self.assertTrue(backend.closed)
                self.assertFalse(backend.monitor_enabled)
                monitor.deleteLater()
                backend.deleteLater()
                QTest.qWait(1)

    def test_main_serial_message_shared_run_button_and_mode_badge(self):
        from src.backend import Backend
        from src.common.testing import Mode
        from src.common.styles import apply_theme
        from src.ui.main_window import MainWindow
        from tests.test_bench import alternative_profile
        profile = alternative_profile()
        profile.tests[0]['steps'][0]['wait_ms'] = 5000
        with tempfile.TemporaryDirectory() as folder:
            backend = Backend(profile, storage_dir=folder)
            window = MainWindow('demo', backend=backend)
            apply_theme(self.app)
            try:
                backend.configure(mode=Mode.MANUAL)
                window.start_button.click()
                self.assertEqual(len(window._messages), 1)
                self.assertIn('serial', next(iter(window._messages.values())).text())
                self.assertIsNone(backend.session)
                stamp = backend.monitor_samples['analog_a'].timestamp
                QTest.qWait(150)
                self.assertGreater(backend.monitor_samples['analog_a'].timestamp, stamp)
                window._start()
                self.assertEqual(len(window._messages), 1)
                for box in list(window._messages.values()):
                    box.accept()
                window.serial_edit.setText('DEMO-001')
                backend.connect_device()
                deadline = time.monotonic() + 2
                while not backend.can_start and time.monotonic() < deadline:
                    QTest.qWait(20)
                window.start_button.click()
                self.assertTrue(backend.busy)
                self.assertEqual(window.start_button.property('state'), 'running')
                self.assertIn('Dừng', window.start_button.text())
                self.assertFalse(hasattr(window, 'stop_button'))
                window.start_button.click()
                deadline = time.monotonic() + 3
                while backend.busy and time.monotonic() < deadline:
                    QTest.qWait(20)
                self.assertFalse(backend.busy)
                self.assertEqual(window.start_button.property('state'), 'idle')
                window.connection_bar.adapter.setCurrentIndex(2)
                self.assertEqual(window.mode_badge.text(), 'UART')
                self.assertIn('UART', window.windowTitle())
                self.assertIn('MÔ PHỎNG', window.monitor.source_label.text())
            finally:
                for box in list(window._messages.values()):
                    box.accept()
                window.close()
                deadline = time.monotonic() + 3
                while not backend.closed and time.monotonic() < deadline:
                    QTest.qWait(20)
                self.assertTrue(backend.closed)
                window.deleteLater()
                backend.deleteLater()
                QTest.qWait(1)
