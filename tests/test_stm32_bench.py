"""Test runner over the two CPUv1.0 banks: mapping, validation, simulator, runner.

No serial port is opened; the register-level simulator stands in for the MCU.
The I/O map under test is the ASSUMED CPUv1.0 default in configs/a45.
"""
import tempfile
import time
import unittest
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.backend import Backend
from src.common.profiles import ProfileError, load_profile, validate_profile
from src.common.stm32 import ReadRegister as RI, WriteRegister as WO
from src.common.testing import Mode
from src.protocol import Stm32IoMap, UnsupportedSignal, decode_int16, encode_int16
from src.simulator import Stm32Simulator

POWER_ALL = [{'signal': s, 'value': 1} for s in ('ac_36v', 'dc_27v', 'dc_15v', 'dc_12v', 'dc_5v')]
RUNNABLE = {'P02', 'P03', 'P04', 'P05', 'P06', 'P07', 'P08', 'P09', 'P13', 'P14', 'P15', 'P18', 'P19'}


def io_map(profile=None):
    return Stm32IoMap((profile or load_profile()).hardware['stm32_io'])


class Stm32IoMapTests(unittest.TestCase):
    def test_apply_sets_relay_route_and_dac_without_clamping(self):
        io = io_map()
        image = io.apply(io.safe_image(), [{'signal': 'dc_27v', 'value': 1}, {'signal': 'set_40', 'value': 3}])
        self.assertEqual(image[WO.Mode], 1)
        self.assertEqual(image[WO.Power], 1 << 1)
        self.assertEqual(image[WO.SW02], 1 << 3)
        self.assertEqual(decode_int16(image[WO.DAC_val]), -600)  # Assumed −5 mV per code.
        self.assertEqual(io.inverse(image), {'dc_27v': 1, 'set_40': 3})
        bad = [[{'signal': 'set_4', 'value': 5}],       # Contact only supplies 27 V.
               [{'signal': 'set_40', 'value': 5}],      # Outside ±3.5 V: no silent clamp.
               [{'signal': 'set_40', 'value': 3}, {'signal': 'set_41', 'value': -3}],  # One DAC.
               [{'signal': 'missing', 'value': 1}]]
        for actions in bad:
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                io.apply(io.safe_image(), actions)
        shared_zero = io.apply(io.safe_image(), [{'signal': f'set_{p}', 'value': 0} for p in (40, 41, 42)])
        self.assertEqual(shared_zero[WO.SW02], 0b111000)
        with self.assertRaises(UnsupportedSignal):
            io.apply(io.safe_image(), [{'signal': 'set_43', 'value': 4.5}])

    def test_writes_are_contiguous_runs_and_never_touch_encoder_or_null(self):
        io = io_map()
        safe = io.safe_image()
        full = io.writes(None, safe)
        self.assertEqual(full, [(1, [1, 2]), (7, [0, 0, 0, 0, 0, 0])])
        powered = io.apply(safe, [{'signal': 'dc_27v', 'value': 1}])
        self.assertEqual(io.writes(safe, powered), [(WO.Power, [2])])
        self.assertEqual(io.writes(powered, powered), [])
        touched = {a + i for a, words in full for i in range(len(words))}
        self.assertFalse(touched & {WO.Null, WO.DataO1, WO.DataO2, WO.DataO3, WO.CDT})

    def test_decode_signed_scale_link_and_mux_groups(self):
        io = io_map()
        words = [0] * 30
        words[RI.ADC3_val] = encode_int16(-850)
        words[RI.ADC4_val] = 137
        self.assertEqual(io.decode(words, 'xp1_50'), -8.5)
        self.assertEqual(io.decode(words, 'dc_current'), 1.37)
        self.assertEqual(io.decode(words, 'ready'), 1)
        self.assertEqual(io.groups(['xp1_50', 'xp1_49', 'ready']),
                         [(14, ['xp1_50']), (13, ['xp1_49']), (None, ['ready'])])
        self.assertEqual(io.unsupported([{'signal': 'set_43', 'value': 4.5}], ['hz_A', 'xp1_50'])[0][:6], 'set_43')
        with self.assertRaises(UnsupportedSignal):
            io.decode(words, 'hz_A')


class Stm32ProfileValidationTests(unittest.TestCase):
    def test_a45_profile_uses_stm32_and_flags_cpu_gaps(self):
        p = load_profile()
        self.assertEqual(p.hardware['adapter'], 'stm32')
        self.assertFalse(p.hardware['production_ready'])
        statuses = {e['status'] for e in list(p.hardware['stm32_io']['outputs'].values())
                    + list(p.hardware['stm32_io']['inputs'].values())}
        self.assertNotIn('verified', statuses)  # Nothing is verified on the bench yet.
        self.assertEqual(p.tests[0]['steps'][0]['actions'], [{'signal': 'ac_36v', 'value': 1}])
        self.assertEqual(p.tests[2]['preparation'], 'power_all')
        self.assertEqual(p.tests[19]['preparation'], 'power_all_section_v')

    def test_invalid_maps_and_plans_are_rejected(self):
        def io(p):
            return p.hardware['stm32_io']
        mutations = [
            lambda p: io(p)['outputs']['set_4'].update(register='DataO1'),           # Encoder command.
            lambda p: io(p)['outputs']['set_12'].update(bit=0),                      # Same bit as set_4.
            lambda p: io(p)['outputs']['set_40']['route'][0].update(bit=3, register='CDT'),
            lambda p: io(p)['session'].update(Mode=0),
            lambda p: io(p)['inputs'].pop('xp1_50'),
            lambda p: io(p)['inputs']['xp1_49'].update(mux=14, register='ADC3_val'),  # Same slot as xp1_50.
            lambda p: p.tests[6]['steps'][0]['actions'].append({'signal': 'set_41', 'value': 1}),
            lambda p: p.tests[3]['steps'][0]['actions'][0].update(value=9),          # Out of DAC range.
            lambda p: p.tests[2].update(preparation='missing'),
            lambda p: p.target['sequences']['power_all']['actions'].append({'signal': 'set_4', 'value': 1}),
            lambda p: p.fixtures['stm32_cases'][0]['measure'].update(nope=1),
        ]
        for mutation in mutations:
            p = deepcopy(load_profile())
            mutation(p)
            with self.subTest(mutation=mutation), self.assertRaises(ProfileError):
                validate_profile(p)


class Stm32SimulatorTests(unittest.TestCase):
    def simulator(self, clock=time.monotonic):
        p = load_profile()
        io = io_map(p)
        return io, Stm32Simulator(io_map=io, cases=p.fixtures['stm32_cases'], clock=clock)

    def write_image(self, sim, image):
        for address, words in Stm32IoMap.writes(None, image):
            sim.write(9, address, words)

    def test_reading_follows_written_stimulus_route_and_mode(self):
        io, sim = self.simulator()
        image = io.apply(io.safe_image(), POWER_ALL + [{'signal': 'set_40', 'value': 3}])
        image[WO.MUX] = 14  # xp1_50
        self.write_image(sim, image)
        self.assertEqual(decode_int16(sim.read(9)[RI.ADC3_val - 1]), 850)
        wrong_route = dict(image)
        wrong_route[WO.SW02] = 1 << 4  # Stimulus lands on 41XP1 instead.
        self.write_image(sim, wrong_route)
        self.assertEqual(decode_int16(sim.read(9)[RI.ADC3_val - 1]), 0)
        no_mode = dict(image)
        no_mode[WO.Mode] = 0  # MCU follows the HMI, not the PC.
        self.write_image(sim, no_mode)
        self.assertEqual(sim.stimuli(), {})

    def test_after_ms_uses_scaled_simulated_time(self):
        now = [100.0]
        io, sim = self.simulator(clock=lambda: now[0])
        sim.time_scale = 60
        image = io.apply(io.safe_image(), [{'signal': 'ac_36v', 'value': 1}])
        image[WO.MUX] = 1  # ac_current
        self.write_image(sim, image)
        self.assertEqual(sim.read(9)[RI.ADC4_val - 1], 300)
        now[0] += 120 / 60  # 120 s of standard time at ×60.
        self.assertEqual(sim.read(9)[RI.ADC4_val - 1], 170)

    def test_bank_defaults_unchanged_without_mux_selection(self):
        io, sim = self.simulator()
        sim.write(9, 1, [1])
        self.assertEqual(sim.read(9)[RI.ADC0_val - 1], 1234)


class Stm32RunnerTests(unittest.TestCase):
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

    def backend(self, profile=None, mode=Mode.MANUAL, test=None, scenario='normal'):
        b = Backend(profile or load_profile(), storage_dir=self.temp.name)
        self.backends.append(b)
        b.configure(serial_number='SAMPLE-001', time_scale=60.0, mode=mode, scenario=scenario)
        if test:
            b.select_test(test)
        self.writes = []
        original = b.device.stm32_simulator.write

        def record(slave, address, values):
            self.writes.append((address, list(values)))
            return original(slave, address, values)
        patcher = patch.object(b.device.stm32_simulator, 'write', side_effect=record)
        patcher.start()
        self.addCleanup(patcher.stop)
        b.connect_device()
        self.wait(lambda: b.connection == 'Sẵn sàng · MÔ PHỎNG')
        self.assertEqual(self.writes, [])  # Connecting only reads (FC03).
        return b

    def run_done(self, b, timeout=20000):
        self.assertTrue(b.start())
        self.wait(lambda: not b.busy, timeout)
        self.wait(lambda: not b.store.busy)

    def test_p02_writes_power_then_reads_current_and_returns_safe(self):
        b = self.backend(test='P02')
        self.run_done(b)
        self.assertEqual(b.session['verdict'], 'PASS')
        self.assertEqual(b.session['adapter'], 'stm32')
        m = b.attempt['measurements'][0]
        self.assertEqual((m['signal'], m['value'], m['status']), ('dc_current', 1.37, 'PASS'))
        self.assertEqual(self.writes[0], (WO.Mode, [1, 2]))          # Mode=1 before anything else.
        self.assertEqual(self.writes[1], (WO.DAC_val, [0] * 6))       # Known all-off state.
        self.assertEqual(self.writes[2], (WO.Power, [0b11110]))       # DC rails, no AC.
        self.assertEqual(self.writes[3], (WO.MUX, [2]))               # Select dc_current.
        self.assertEqual(self.writes[-1], (WO.MUX, [0, 0]))           # MUX and Power off.
        touched = {a + i for a, words in self.writes for i in range(len(words))}
        self.assertFalse(touched & {WO.Null, WO.DataO1, WO.DataO2, WO.DataO3, WO.CDT})
        self.assertTrue(b.attempt['cleanup_confirmed'])
        notes = {t['note'] for t in b.attempt['transactions']}
        self.assertEqual(len(notes), 1)
        self.assertIn('chưa xác nhận đầu ra', notes.pop())
        self.assertEqual(b.stm32.mod_buf_to_read[RI.ADC4_val], 137)   # Dialog sees the runner's DI.

    def test_auto_runs_mapped_tests_and_blocks_cpu_gaps(self):
        b = self.backend(mode=Mode.AUTO)
        self.run_done(b, 40000)
        statuses = {a['test_id']: a['status'] for a in b.session['attempts']}
        self.assertEqual({t for t, s in statuses.items() if s == 'PASS'}, RUNNABLE)
        self.assertTrue(all(s == 'BLOCKED' for t, s in statuses.items() if t not in RUNNABLE))
        self.assertEqual(b.session['verdict'], 'Chưa đầy đủ')
        reason = next(a['reason'] for a in b.session['attempts'] if a['test_id'] == 'P10')
        self.assertIn('CPUv1.0', reason)

    def test_blocked_test_sends_nothing(self):
        b = self.backend(test='P10')
        self.run_done(b)
        self.assertEqual(b.attempt['status'], 'BLOCKED')
        self.assertEqual(self.writes, [])

    def test_fail_scenario_gives_fail_not_pass(self):
        b = self.backend(test='P07', scenario='fail')
        self.run_done(b)
        self.assertEqual(b.attempt['status'], 'FAIL')
        self.assertEqual(b.session['verdict'], 'FAIL')

    def test_timeout_in_apply_is_error_without_retry_or_more_writes(self):
        b = self.backend(test='P07', scenario='timeout')
        with patch.object(b.device, '_request_stm32', wraps=b.device._request_stm32) as sent:
            self.run_done(b)
            self.assertEqual(b.session['verdict'], 'ERROR')
            self.assertFalse(b.attempt['cleanup_confirmed'])
            stimulus = [c for c in sent.call_args_list
                        if c.args[0] == 'write' and c.args[3] == WO.DAC_val and c.args[4][0] != 0]
            self.assertEqual(len(stimulus), 1)  # The unanswered stimulus write, never resent.
            self.assertEqual(b.device.bench_image, {})  # Output state is now unknown.
            count = sent.call_count
            QTest.qWait(300)
            self.assertEqual(sent.call_count, count)  # No automatic safe-state write either.

    def test_disconnect_while_measuring_invalidates_samples(self):
        b = self.backend(test='P02', scenario='disconnect')
        self.run_done(b)
        self.assertEqual(b.session['verdict'], 'ERROR')
        self.assertTrue(all(s.quality != 'valid' for s in b.samples.values()))
        self.assertFalse(b.can_start)

    def test_stop_while_settling_writes_safe_state(self):
        profile = deepcopy(load_profile())
        profile.tests[1]['steps'][0]['wait_ms'] = 600000
        b = self.backend(profile, test='P02')
        self.assertTrue(b.start())
        self.wait(lambda: b.phase == 'settling')
        b.stop()
        self.wait(lambda: not b.busy)
        self.assertEqual(b.session['verdict'], 'ABORTED')
        self.assertTrue(b.attempt['cleanup_confirmed'])
        self.assertEqual(b.device.stm32_simulator.mod_buf_to_write[WO.Power], 0)
        self.assertEqual(self.writes[-1], (WO.Power, [0]))

    def test_inrush_then_steady_current_follows_standard_wait(self):
        profile = deepcopy(load_profile())
        p01 = profile.tests[0]
        p01['steps'][1]['checks'] = [c for c in p01['steps'][1]['checks'] if c['signal'] == 'ac_current']
        p01['steps'][1]['issues'] = []
        b = self.backend(profile, test='P01')
        self.run_done(b)
        values = [(m['step_id'], m['value'], m['status']) for m in b.attempt['measurements']]
        self.assertEqual(values, [('S01', 3, 'PASS'), ('S02', 1.7, 'PASS')])

    def long_p02(self):
        profile = deepcopy(load_profile())
        profile.tests[1]['steps'][0]['wait_ms'] = 600000
        return self.backend(profile, test='P02')

    def test_pause_goes_safe_then_resume_reruns_test_from_start(self):
        b = self.long_p02()
        self.assertFalse(b.can_pause)
        self.assertTrue(b.start())
        self.wait(lambda: b.phase == 'settling')
        self.assertTrue(b.pause())
        self.assertFalse(b.pause())  # Already pausing.
        self.wait(lambda: b.paused)
        paused = b.session['attempts'][-1]
        self.assertEqual((paused['status'], paused['cleanup_confirmed']), ('PAUSED', True))
        self.assertEqual(self.writes[-1], (WO.Power, [0]))  # Outputs back to safe state.
        self.assertEqual(b.device.stm32_simulator.mod_buf_to_write[WO.Power], 0)
        self.assertEqual(b.session['state'], 'paused')
        count = len(self.writes)
        QTest.qWait(300)
        self.assertEqual(len(self.writes), count)  # Nothing is sent while paused.
        b.test['steps'][0]['wait_ms'] = 250
        self.assertTrue(b.resume())
        self.wait(lambda: not b.busy, 10000)
        self.assertEqual(self.writes[count], (WO.Mode, [1, 2]))  # Rerun starts with a fresh prepare.
        self.assertEqual([a['status'] for a in b.session['attempts']], ['PAUSED', 'PASS'])
        self.assertEqual((b.session['verdict'], b.session['processed']), ('PASS', 1))
        self.assertEqual([e['event'] for e in b.session['events'] if 'pause' in e['event'] or e['event'] == 'resumed'],
                         ['pause_requested', 'paused', 'resumed'])

    def test_stop_or_disconnect_while_paused_aborts_without_writes(self):
        for action in ('stop', 'disconnect'):
            with self.subTest(action=action):
                b = self.long_p02()
                b.start()
                self.wait(lambda: b.phase == 'settling')
                b.pause()
                self.wait(lambda: b.paused)
                count = len(self.writes)
                b.stop() if action == 'stop' else b.disconnect_device()
                self.wait(lambda: not b.busy)
                self.assertEqual(b.session['verdict'], 'ABORTED')
                self.assertEqual(len(self.writes), count)
                # One application instance per storage folder, as in real use.
                b.shutdown()
                self.wait(lambda: b.closed and not b.store.busy)

    def test_measured_values_stay_visible_after_test_until_new_session(self):
        b = self.backend(test='P02')
        self.run_done(b)
        self.assertEqual(b.measurement_history['dc_current']['value'], 1.37)
        self.assertEqual(b.measurement_history['dc_current']['status'], 'PASS')
        # Commands are remembered as acknowledged requests, never as PASS.
        self.assertEqual((b.measurement_history['dc_27v']['value'], b.measurement_history['dc_27v']['status']),
                         (1, 'ACK'))
        model = b.signal_model
        row = next(i for i, s in enumerate(model.definitions) if s['id'] == 'dc_current')

        def role(name):
            return model.data(model.index(row), Qt.UserRole + model.fields.index(name) + 1)
        b.samples['dc_current'] = replace(b.samples['dc_current'], quality='stale')  # e.g. link lost
        self.assertEqual((role('display'), role('verdict'), role('live'), role('recorded')),
                         ('1.37', 'PASS', False, True))
        self.assertIn('P02/S01', role('subtitle'))
        self.assertEqual(role('quality'), 'Giá trị đã lưu')
        self.assertTrue(b.new_session())
        self.assertEqual(role('display'), '—')

    def test_diagnostic_read_rejected_while_runner_busy(self):
        b = self.backend(test='P02')
        self.assertTrue(b.start())
        with self.assertRaises(ValueError):
            b.request_stm32()
        self.wait(lambda: not b.busy)


if __name__ == '__main__':
    unittest.main()
