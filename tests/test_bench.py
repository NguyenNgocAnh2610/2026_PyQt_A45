"""Behavior tests: reusable profiles, execution, failures and persistence."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickWidgets import QQuickWidget

from src.backend import Backend, evaluate
from src.common.profiles import load_profile, validate_profile, ProfileError, specification_issues
from src.common.testing import Mode, Sample
from src.communication import Communication, Request
from src.protocol import decode_snapshot
from src.storage import read_session
from src.ui.main_window import MainWindow


def alternative_profile():
    """Second system: no A45/1101K test or signal IDs used by the engine."""
    profile = deepcopy(load_profile())
    profile.system.update(id="thermal-fixture", name="Trạm nhiệt DEMO")
    profile.system["signals"] = [
        dict(id="temperature", label="Nhiệt độ", group="Cảm biến", unit="°C", kind="number", source="measured", decimals=1, stale_ms=1000, chart=True, states={}),
        dict(id="setpoint", label="Giá trị yêu cầu", group="Điều khiển", unit="°C", kind="number", source="derived", decimals=1, stale_ms=1000, chart=True, states={}),
        dict(id="trip", label="Bảo vệ nhiệt", group="Trạng thái", unit="", kind="boolean", source="confirmed", decimals=0, stale_ms=1000, chart=False, states={"0": {"label": "OK", "color": "#00ff00"}, "1": {"label": "TRIP", "color": "#ff0000"}}),
    ]
    profile.system["status_signals"] = {"fault": "trip"}
    profile.target.update(id="thermal", name="Cảm biến nhiệt")
    profile.target["tests"] = []
    profile.fixtures["cases"] = {}
    for tid, nominal, deps in [("T1", 20.0, []), ("T2", 30.0, ["T1"]), ("T3", -5.0, [])]:
        step = dict(id="sample", title="Đo nhiệt độ", capability="stimulate_measure", actions=[{"signal": "setpoint", "value": nominal}],
                    wait_ms=0, issues=[], checks=[dict(signal="temperature", nominal=nominal, tolerance=.5, unit="°C")])
        test = dict(id=tid, name=f"Bài {tid}", source="Fixture độc lập", group="Nhiệt", dependencies=deps,
                    independence="mock_only", preparation="mock_baseline", cleanup="mock_safe", issues=[], steps=[step])
        profile.target["tests"].append(test)
    # Explicit independent observations, not derived at evaluation time.
    profile.fixtures["cases"].update({"T1/sample": {"temperature": 20.25}, "T2/sample": {"temperature": 29.75}, "T3/sample": {"temperature": -5.25}})
    diag = deepcopy(profile.target["tests"][0])
    diag.update(id="health", name="Tự kiểm tra mô phỏng")
    profile.system["diagnostics"] = [diag]
    profile.fixtures["cases"]["health/sample"] = {"temperature": 20.25}
    profile.hardware['wire_signals'] = {'temperature': 1, 'setpoint': 2, 'trip': 3}
    # Second system keeps the legacy mock adapter: both runner paths stay covered.
    profile.hardware['adapter'] = 'mock'
    profile.hardware.pop('stm32_io')
    profile.target.pop('sequences')
    profile.fixtures.pop('stm32_cases')
    validate_profile(profile)
    return profile


class ProfileTests(unittest.TestCase):
    def test_source_has_24_parameters_five_groups_and_known_issues(self):
        p = load_profile()
        self.assertEqual([t['id'] for t in p.tests], [f"P{i:02}" for i in range(1, 25)])
        self.assertEqual(len({t['group'] for t in p.tests}), 5)
        self.assertEqual({t['id'] for t in p.tests if specification_issues(t)}, {'P01', 'P12', 'P16', 'P17', 'P20', 'P21', 'P22', 'P23', 'P24'})
        self.assertEqual(p.tests[0]['steps'][1]['wait_ms'], 120000)
        self.assertEqual(p.tests[15]['steps'][0]['checks'][0]['signal'], 'xp1_26')
        self.assertGreater(len(p.target['source_paragraphs']), 100)

    def test_invalid_reference_duplicate_cycle_unit_and_hardware_are_rejected(self):
        mutations = [
            lambda p: p.system['signals'].append(deepcopy(p.signals[0])),
            lambda p: p.tests[0]['steps'][0]['checks'][0].update(signal='missing'),
            lambda p: p.tests[0]['steps'][0]['checks'][0].update(unit='V'),
            lambda p: p.tests[0]['steps'][0].update(wait_ms=-1),
            lambda p: p.tests[0]['steps'][0]['checks'][0].update(tolerance=-1),
            lambda p: p.tests[0]['steps'][0].update(capability='missing'),
            lambda p: p.tests[0].update(dependencies=['T2']),
            lambda p: p.hardware.update(production_ready=True),
            lambda p: p.hardware.update(adapter='rtu'),
        ]
        for mutation in mutations:
            p = alternative_profile()
            mutation(p)
            with self.subTest(mutation=mutation), self.assertRaises(ProfileError):
                validate_profile(p)

    def test_second_profile_loads_from_json_without_code_changes(self):
        p = alternative_profile()
        with tempfile.TemporaryDirectory() as folder:
            p.system.update(target_file='target.json', hardware_file='hardware.json', fixtures_file='mock.json')
            for name, content in [('system.json', p.system), ('target.json', p.target), ('hardware.json', p.hardware), ('mock.json', p.fixtures)]:
                Path(folder, name).write_text(json.dumps(content), encoding='utf-8')
            loaded = load_profile(Path(folder, 'system.json'))
            self.assertEqual(loaded.system['id'], 'thermal-fixture')
            self.assertEqual(len(loaded.signals), 3)

    def test_boundaries_negative_values_and_missing_criteria(self):
        check = {'nominal': -9, 'tolerance': .2}
        for value, expected in [(-9.2, 'PASS'), (-8.8, 'PASS'), (-9.201, 'FAIL')]:
            self.assertEqual(evaluate(check, Sample(value, 10, 'valid'), 10.1, 1000)[0], expected)
        self.assertEqual(evaluate(check, Sample(-9, 1, 'valid'), 10, 1000)[0], 'ERROR')
        self.assertEqual(evaluate({'nominal': 9, 'tolerance': None}, Sample(9, 10, 'valid'), 10, 1000)[0], 'Chưa đánh giá')
        self.assertEqual(evaluate(check, None, 10, 1000)[0], 'ERROR')

    def test_malformed_adapter_response_rejected(self):
        for payload in [{}, {'values': {'a': float('nan')}, 'timestamp': 1}, {'values': {'unknown': 1}, 'timestamp': 1}]:
            with self.assertRaises(ValueError):
                decode_snapshot(payload, {'a'})


class BenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.backends = []
        self.windows = []

    def wait(self, predicate, timeout=6000):
        start = time.monotonic()
        while not predicate() and (time.monotonic() - start) * 1000 < timeout:
            QTest.qWait(20)
        self.assertTrue(predicate(), "Timed out waiting for asynchronous state")

    def backend(self, profile=None):
        backend = Backend(profile or alternative_profile(), storage_dir=self.temp.name)
        self.backends.append(backend)
        backend.configure(serial_number='SAMPLE-001', time_scale=60.0)
        backend.connect_device()
        self.wait(lambda: backend.connection == 'Sẵn sàng · MÔ PHỎNG')
        return backend

    def tearDown(self):
        for b in self.backends:
            if not b.closed:
                b.shutdown()
        for b in self.backends:
            self.wait(lambda: b.closed and not b.store.busy)
        for w in self.windows:
            w.close()
            w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.temp.cleanup()

    def run_done(self, b):
        self.assertTrue(b.start())
        self.wait(lambda: not b.busy, 10000)
        self.wait(lambda: not b.store.busy)

    def test_manual_prepares_confirms_measures_and_preserves_reruns(self):
        b = self.backend()
        b.configure(mode=Mode.MANUAL)
        self.run_done(b)
        self.assertEqual(b.session['verdict'], 'PASS')
        self.assertTrue(b.attempt['cleanup_confirmed'])
        self.assertEqual(b.attempt['measurements'][0]['value'], 20.25)
        old_id = b.attempt['id']
        self.run_done(b)
        self.assertEqual(len(b.session['attempts']), 2)
        self.assertNotEqual(old_id, b.attempt['id'])
        saved = read_session(Path(self.temp.name, b.session['id'] + '.json'))
        self.assertEqual(len(saved['attempts']), 2)
        self.assertTrue(saved['simulation'])

    def test_auto_fail_skips_dependents_but_runs_independent_test(self):
        b = self.backend()
        b.configure(scenario='fail')
        self.run_done(b)
        self.assertEqual([a['status'] for a in b.session['attempts']], ['FAIL', 'SKIPPED', 'PASS'])
        self.assertEqual(b.session['verdict'], 'FAIL')
        self.assertEqual(b.progress, 100)

    def test_all_pass_auto_and_selftest_without_serial(self):
        b = self.backend()
        self.run_done(b)
        self.assertEqual(b.session['verdict'], 'PASS')
        self.assertTrue(b.new_session())
        b.configure(mode=Mode.SELF, serial_number='')
        self.run_done(b)
        self.assertEqual(b.session['verdict'], 'PASS')
        self.assertIsNone(b.session['serial'])
        self.assertEqual(b.attempt['test_id'], 'health')

    def test_missing_spec_never_passes_or_sends_apply(self):
        b = self.backend(load_profile())
        b.configure(mode=Mode.MANUAL)
        b.select_test('P12')
        self.run_done(b)
        self.assertEqual(b.attempt['status'], 'BLOCKED')
        self.assertEqual(b.session['verdict'], 'Chưa đầy đủ')
        self.assertIsNone(b.device.communication.transport.last_case)
        # A45 uses the STM32 runner: a BLOCKED test writes nothing to the banks.
        self.assertEqual(b.device.stm32_simulator.mod_buf_to_write, [0] * 29)

    def test_busy_guards_and_view_selection_do_not_change_running_test(self):
        b = self.backend()
        b.configure(mode=Mode.MANUAL)
        self.assertTrue(b.start())
        self.assertFalse(b.start())
        self.assertFalse(b.configure(mode=Mode.SELF))
        b.select_test('T3')
        self.assertEqual(b.test['id'], 'T1')
        self.wait(lambda: not b.busy)

    def test_pause_and_resume_on_mock_adapter_rerun_the_test(self):
        profile = alternative_profile()
        profile.tests[0]['steps'][0]['wait_ms'] = 600000
        b = self.backend(profile)
        b.configure(mode=Mode.MANUAL)
        b.start()
        self.wait(lambda: b.phase == 'settling')
        self.assertTrue(b.pause())
        self.wait(lambda: b.paused)
        self.assertTrue(b.attempt['cleanup_confirmed'])
        b.test['steps'][0]['wait_ms'] = 0
        self.assertTrue(b.resume())
        self.wait(lambda: not b.busy)
        self.assertEqual([a['status'] for a in b.session['attempts']], ['PAUSED', 'PASS'])
        self.assertEqual(b.session['verdict'], 'PASS')

    def test_ack_does_not_mean_output_confirmed_and_stop_waits_for_confirmation(self):
        b = self.backend()
        b.configure(mode=Mode.MANUAL)
        b.start()
        self.wait(lambda: b.phase == 'apply_confirm')
        self.assertNotEqual(b.confirmed, b.token)
        b.stop()
        self.assertTrue(b.busy)
        self.assertEqual(b.session['state'], 'stopping')
        self.wait(lambda: not b.busy)
        self.assertEqual(b.session['verdict'], 'ABORTED')
        self.assertTrue(b.attempt['cleanup_confirmed'])

    def test_timeout_does_not_retry_write_or_resume_on_reconnect(self):
        b = self.backend()
        b.configure(mode=Mode.MANUAL, scenario='timeout')
        with patch.object(b.device, 'apply', wraps=b.device.apply) as apply:
            self.run_done(b)
            self.assertEqual(apply.call_count, 1)
        self.assertEqual(b.session['verdict'], 'ERROR')
        self.assertEqual(b.session['processed'], 1)
        b.configure(scenario='normal')
        b.connect_device()
        self.wait(lambda: b.connection == 'Sẵn sàng · MÔ PHỎNG')
        self.assertFalse(b.busy)
        self.assertEqual(b.session['verdict'], 'ERROR')

    def test_disconnect_stale_and_protection_stop_without_false_pass(self):
        for scenario in ('disconnect', 'stale', 'protection'):
            with self.subTest(scenario=scenario):
                b = self.backend()
                b.configure(mode=Mode.MANUAL, scenario=scenario)
                self.run_done(b)
                self.assertEqual(b.session['verdict'], 'ERROR')
                self.assertFalse(b.attempt['cleanup_confirmed'])
                self.assertTrue(all(s.quality != 'valid' for s in b.samples.values()))
                b.shutdown()

    def test_stop_timeout_and_shutdown_are_bounded(self):
        b = self.backend()
        b.configure(mode=Mode.MANUAL, scenario='stop_timeout')
        b.start()
        self.wait(lambda: b.phase == 'apply_confirm')
        b.shutdown()
        self.wait(lambda: b.closed, 4000)
        self.assertEqual(b.session['verdict'], 'ERROR')
        self.assertFalse(b.device.communication.queue)
        self.assertFalse(b._poll.isActive())
        self.assertFalse(b._tick_timer.isActive())

    def test_old_epoch_callback_cannot_update_new_session(self):
        b = self.backend()
        before = deepcopy(b.samples)
        b._received(Request(999, 'snapshot', {}, 2, b.epoch - 1), {'timestamp': time.monotonic(), 'values': {'temperature': 999}}, '')
        self.assertEqual(b.samples, before)

    def test_serial_required_and_incomplete_checkpoint_recovered_without_execution(self):
        b = self.backend()
        b.configure(serial_number='')
        self.assertFalse(b.start())
        path = Path(self.temp.name, 'interrupted.json')
        path.write_text(json.dumps({'id': 'old', 'state': 'running', 'verdict': 'Đang chạy'}), encoding='utf-8')
        self.assertEqual(read_session(path)['verdict'], 'ERROR')
        second = self.backend()
        self.wait(lambda: 'old' in second.recovered)
        self.assertIsNone(second.session)

    def test_storage_failure_retains_session_and_retry_succeeds(self):
        b = self.backend()
        b.configure(mode=Mode.MANUAL)
        bad = Path(self.temp.name, 'not-a-directory')
        bad.write_text('file', encoding='utf-8')
        b.store.folder = bad
        self.run_done(b)
        self.assertTrue(b.store.status.startswith('Lỗi lưu'))
        self.assertFalse(b.new_session())
        self.assertEqual(b.session['verdict'], 'PASS')
        b.shutdown()
        self.assertFalse(b.closed)
        self.assertIn('chưa lưu', b.message)
        b.store.folder = Path(self.temp.name)
        b.save_again()
        self.wait(lambda: not b.store.busy)
        self.assertEqual(b.store.status, 'Đã lưu')
        self.assertTrue(b.new_session())

    def test_unknown_or_stale_readiness_cannot_start(self):
        b = self.backend()
        b._poll.stop()
        b.samples['trip'] = Sample(0, time.monotonic() - 5, 'valid')
        self.assertFalse(b.start())
        b.samples['trip'] = Sample(1, time.monotonic(), 'valid')
        self.assertFalse(b.start())

    def test_standard_wait_is_scaled_only_in_mock_and_gui_remains_responsive(self):
        profile = alternative_profile()
        profile.tests[0]['steps'][0]['wait_ms'] = 120000
        b = self.backend(profile)
        b.configure(mode=Mode.MANUAL)
        b.start()
        self.wait(lambda: b.phase == 'settling')
        QTest.qWait(100)
        self.assertEqual(b.phase, 'settling')
        self.assertFalse(b.attempt['measurements'])
        b.select_test('T3')
        self.assertEqual(b.test['id'], 'T1')
        self.wait(lambda: not b.busy)
        self.assertEqual(b.session['verdict'], 'PASS')
        self.assertEqual(b.session['time_scale'], 60)

    def test_queue_coalesces_polling_and_prioritizes_finish(self):
        c = Communication(alternative_profile())
        spy = QSignalSpy(c.completed)
        c.submit('connect')
        self.wait(lambda: spy.count() == 1)
        c.submit('apply', {'token': '00000000-0000-0000-0000-000000000001', 'case': 'T1/sample'})
        self.wait(lambda: c.active is not None)
        for _ in range(100):
            c.submit('snapshot', priority=2)
        c.submit('finish', {'token': '00000000-0000-0000-0000-000000000002'}, priority=0)
        self.assertEqual(len(c.queue), 2)
        self.wait(lambda: spy.count() == 4)
        self.assertEqual([spy.at(i)[0].operation for i in range(4)], ['connect', 'apply', 'finish', 'snapshot'])
        self.assertEqual(c.max_inflight, 1)
        c.close()

    def test_second_system_renders_qml_and_filters_without_altering_data(self):
        b = self.backend()
        w = MainWindow('test', backend=b)
        self.windows.append(w)
        w.show()
        self.wait(lambda: w.qml.status() == QQuickWidget.Ready)
        self.assertEqual(b.signal_model.rowCount(), 3)
        self.assertEqual(len(w.tree_items), 3)
        w.group_combo.setCurrentText('Cảm biến')
        before = deepcopy(b.samples)
        w.related_combo.setCurrentIndex(2)
        self.assertEqual(b.samples, before)
        w.resize(1280, 720)
        QTest.qWait(50)
        self.assertLessEqual(w.start_button.mapTo(w, w.start_button.rect().bottomRight()).x(), w.width())
        b.configure(mode=Mode.MANUAL)
        b.start()
        w.close()
        self.wait(lambda: b.closed)
        self.assertFalse(b._poll.isActive())


if __name__ == '__main__':
    unittest.main()
