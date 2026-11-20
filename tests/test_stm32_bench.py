"""Test runner over the two CPUv1.0 banks: mapping, validation, simulator, runner.

No serial port is opened; the register-level simulator stands in for the MCU.
The I/O map under test is the ASSUMED wiring allocation in configs/a45 for
CPUv1.1 (slave 11): four RLMatrix boards (board 1 on Matrix[0..1] = DO 18–19,
boards 2–4 on proposed firmware registers 31–36), RLPW power board, RLMUX
channel numbers.
"""
import tempfile
import time
import unittest
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.backend import Backend, evaluate
from src.common.profiles import ProfileError, load_profile, validate_profile, stm32_io_map
from src.common.stm32 import ReadRegister as RI, WriteRegister as WO
from src.common.testing import Mode, Sample
from src.protocol import Stm32IoMap, UnsupportedSignal, decode_int16, encode_int16
from src.simulator import Stm32Simulator

DC = ('dc_27v', 'dc_15v_pos', 'dc_15v_neg', 'dc_12v_pos', 'dc_12v_neg', 'dc_5v_pos', 'dc_5v_neg')
POWER_ALL = [{'signal': s, 'value': 1} for s in ('ac_22v',) + DC]
DC_BITS = 1 << 2 | 1 << 3 | 1 << 4 | 1 << 5 | 1 << 6 | 1 << 10 | 1 << 11
MATRIX0, MATRIX1 = 18, 19   # CPUv1.1 Matrix[0..1] → RLMatrix ID 6.
MATRIX2 = 31                # Proposed firmware registers Matrix2_0/1 (board 2).
MUX_IDLE = 31 << 8 | 31
# Never written by the runner on CPUv1.1: Null, encoder DataO1/DataO2, SSI DataO3, CDT (20), DataT (21–30).
FORBIDDEN = {0, 13, 14, 15} | set(range(20, 31))


def io_map(profile=None):
    return stm32_io_map(profile or load_profile())


def without_board_2():
    profile = deepcopy(load_profile())
    board = profile.hardware['stm32_io']['matrix_boards'][1]
    board.update(status='unsupported', reason='Firmware CPU chưa gửi Matrix2_0/1 tới bo matrix 2.')
    validate_profile(profile)
    return profile


class Stm32IoMapTests(unittest.TestCase):
    def test_matrix_pin_selects_one_source_and_never_clamps(self):
        io = io_map()
        safe = io.safe_image()
        image = io.apply(safe, [{'signal': 'dc_27v', 'value': 1}, {'signal': 'set_40', 'value': 3}])
        self.assertEqual(image[WO.Mode], 1)
        self.assertEqual(image[WO.Power], 1 << 2)
        self.assertEqual(image[MATRIX0], 1 << 0)  # Matrix 1: output 1 (40XP1) ← input 1 (+3 V) = RL1.
        self.assertEqual(io.inverse(image), {'dc_27v': 1, 'set_40': 3})
        flipped = io.apply(image, [{'signal': 'set_40', 'value': -3}])
        self.assertEqual(flipped[MATRIX0], 1 << 1)  # +3 V contact released, −3 V closed.
        released = io.apply(image, [{'signal': 'set_40', 'value': None}])
        self.assertEqual(released[MATRIX0], 0)  # Open circuit.
        small = io.apply(safe, [{'signal': 'set_40', 'value': 0.5}])
        self.assertEqual(small[MATRIX0], 1 << 2)  # DAC input.
        self.assertEqual(decode_int16(small[WO.DAC_val]), -323)  # −1.55 mV per code.
        self.assertAlmostEqual(io.inverse(small)['set_40'], 0.5, delta=0.00155 / 2)
        board_2 = io.apply(safe, [{'signal': 'set_43', 'value': 4.5}, {'signal': 'set_44', 'value': 4.5}])
        self.assertEqual(board_2[MATRIX2 + 1], 1 << 3 | 1 << 11)  # Matrix2_1: pulse input on outputs 3 and 4.
        logic = io.apply(safe, [{'signal': 'set_4', 'value': 27}, {'signal': 'set_13', 'value': 5}])
        self.assertEqual(logic[33], 1 << 0)   # Matrix3_0: 4XP1 ← 27 V (RL1 of board ID 8).
        self.assertEqual(logic[34], 1 << 2)   # Matrix3_1: 13XP1 ← 5 V.
        self.assertEqual(logic[WO.DOUT], 0)   # Level commands no longer need DOUT drivers.
        bad = [[{'signal': 'set_4', 'value': 12}],                      # 4XP1: only 27 V / GND / 5 V sources.
               [{'signal': 'set_40', 'value': 5}],                      # No source and outside the DAC range.
               [{'signal': 'set_32', 'value': 0.5}],                    # Matrix 2 has no DAC input.
               [{'signal': 'set_40', 'value': 0.5}, {'signal': 'set_41', 'value': -0.6}],  # One DAC.
               [{'signal': 'ac_36v', 'value': 1}, {'signal': 'ac_22v', 'value': 1}],       # Interlock.
               [{'signal': 'missing', 'value': 1}]]
        for actions in bad:
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                io.apply(safe, actions)
        grounded = io.apply(safe, [{'signal': f'set_{p}', 'value': 0} for p in (40, 41, 42)])
        self.assertEqual((grounded[MATRIX0], grounded[MATRIX1]), (1 << 3 | 1 << 11, 1 << 3))
        powered = io.apply(safe, [{'signal': 'ac_36v', 'value': 1}])
        self.assertEqual(io.apply(powered, [{'signal': 'ac_36v', 'value': 0}])[WO.Power], 0)  # off_value.
        unsupported = io_map(without_board_2())
        with self.assertRaises(UnsupportedSignal):
            unsupported.apply(unsupported.safe_image(), [{'signal': 'set_43', 'value': 4.5}])

    def test_hmi_forced_bits_and_switch_board_are_never_used(self):
        io = io_map()
        forced = {('Power', b) for b in (7, 8, 9)}
        used = {point for entry in io.outputs.values() for point in io.points(entry)}
        self.assertFalse(used & forced)
        self.assertFalse({r for r, _ in used} & {'SW01', 'SW02', 'DOUT'})  # No switch board, no DOUT driver.
        self.assertEqual(io.cpu_map.name, 'CPUv1.1')
        self.assertEqual(io.slave, 11)

    def test_break_before_make_phases(self):
        io = io_map()
        plus = io.apply(io.safe_image(), POWER_ALL + [{'signal': 'set_40', 'value': 3}])
        minus = io.apply(plus, [{'signal': 'set_40', 'value': -3}])
        opened, final = io.phases(plus, minus)
        self.assertEqual((opened[MATRIX0], final[MATRIX0]), (0, 1 << 1))
        self.assertEqual(opened[WO.Power], plus[WO.Power])  # Only the released contact opens.
        self.assertEqual(io.phases(io.safe_image(), plus), [plus])  # Only closing: one phase.
        self.assertEqual(io.phases(plus, io.safe_image()), [io.safe_image()])  # Only opening.
        ac = io.apply(io.safe_image(), [{'signal': 'ac_36v', 'value': 1}])
        switched = io.apply(ac, [{'signal': 'ac_36v', 'value': 0}, {'signal': 'ac_22v', 'value': 1}])
        self.assertEqual([p[WO.Power] for p in io.phases(ac, switched)], [0, 1 << 1])

    def test_writes_are_contiguous_runs_and_never_touch_encoder_or_null(self):
        io = io_map()
        safe = io.safe_image()
        full = io.writes(None, safe)
        self.assertEqual(full, [(1, [1, 2]), (7, [0, 0]), (11, [MUX_IDLE, 0]), (18, [0, 0]), (31, [0] * 6)])
        powered = io.apply(safe, [{'signal': 'dc_27v', 'value': 1}])
        self.assertEqual(io.writes(safe, powered), [(WO.Power, [4])])
        self.assertEqual(io.writes(powered, powered), [])
        touched = {a + i for a, words in full for i in range(len(words))}
        self.assertFalse(touched & FORBIDDEN)

    def test_decode_signed_scale_link_and_mux_channel_groups(self):
        io = io_map()
        words = [0] * 30
        words[RI.ADC3_val] = encode_int16(-850)
        self.assertEqual(io.decode(words, 'xp1_50'), -8.5)
        self.assertEqual(io.decode(words, 'ac_A'), -85)  # Assumed 0.1 V/V module.
        self.assertEqual(io.decode(words, 'ready'), 1)
        self.assertEqual(io.mux_word(), MUX_IDLE)
        self.assertEqual(io.groups(['xp1_50', 'xp1_49', 'ready']),
                         [(31 << 8 | 8, ['xp1_50']), (31 << 8 | 7, ['xp1_49']), (None, ['ready'])])
        with self.assertRaises(ValueError):
            io.groups(['hz_A'])  # Entered by the operator, never read over FC03.
        self.assertEqual(io.unsupported([], ['diag_adc', 'xp1_50'])[0][:8], 'diag_adc')
        with self.assertRaises(UnsupportedSignal):
            io.decode(words, 'diag_adc')


class Stm32ProfileValidationTests(unittest.TestCase):
    def test_a45_profile_uses_stm32_and_flags_cpu_gaps(self):
        p = load_profile()
        self.assertEqual(p.hardware['adapter'], 'stm32')
        self.assertFalse(p.hardware['production_ready'])
        io = p.hardware['stm32_io']
        statuses = {e['status'] for e in list(io['outputs'].values()) + list(io['inputs'].values())
                    + io['matrix_boards'] + [io['dac']]}
        self.assertNotIn('verified', statuses)  # Nothing is verified on the bench yet.
        self.assertEqual(p.tests[0]['steps'][0]['actions'], [{'signal': 'ac_36v', 'value': 1}])
        self.assertEqual(p.tests[0]['steps'][1]['capability'], 'stimulate')
        self.assertTrue(p.tests[0]['stop_on_fail'] and p.tests[1]['stop_on_fail'])
        self.assertEqual(p.tests[2]['preparation'], 'power_all')
        self.assertEqual(p.tests[19]['preparation'], 'power_all_section_v')

    def test_invalid_maps_and_plans_are_rejected(self):
        def io(p):
            return p.hardware['stm32_io']
        mutations = [
            lambda p: p.hardware.update(cpu_map='CPUv9'),
            lambda p: io(p)['outputs']['dc_27v'].update(register='DataO1'),          # Encoder command.
            lambda p: io(p)['outputs']['dc_15v_pos'].update(bit=2),                  # Same bit as dc_27v.
            lambda p: io(p)['outputs']['ac_36v'].update(bit=7),                      # Forced on by the HMI code.
            lambda p: io(p)['safe_state'].update(CDT=0),                             # CDT is not runner-writable.
            lambda p: io(p)['matrix_boards'][0]['outputs'].update({'2': 'set_40'}),  # Pin twice on one board.
            lambda p: io(p)['matrix_boards'][1]['outputs'].update({'1': 'set_40'}),  # Pin on two boards.
            lambda p: io(p)['extra_write_registers'].update(Matrix2_0=20),           # Inside the CPUv1.1 map (CDT).
            lambda p: io(p)['extra_write_registers'].update(CDT=40),                 # Existing register name.
            lambda p: io(p)['extra_write_registers'].update(Matrix2_0=50),           # Beyond the 50-word array.
            lambda p: io(p)['inputs']['xp1_49'].update(mux=40),                      # RLMUX has 32 channels.
            lambda p: io(p)['session'].update(Mode=0),
            lambda p: io(p)['safe_state'].update(MUX=0),                             # Selects Mux1.1.
            lambda p: io(p)['inputs'].pop('xp1_50'),
            lambda p: io(p)['inputs']['xp1_49'].update(mux=8),                       # Same channel as xp1_50.
            lambda p: io(p)['inputs']['xp1_49'].update(mux=31),                      # Idle channel.
            lambda p: p.tests[6]['steps'][0]['actions'].append({'signal': 'set_41', 'value': 2}),
            lambda p: p.tests[3]['steps'][0]['actions'][0].update(value=9),          # No source, outside DAC.
            lambda p: p.tests[0]['steps'][2]['actions'].append({'signal': 'ac_36v', 'value': 1}),  # Interlock.
            lambda p: p.tests[2]['steps'][0].update(checks=[]),                      # Measuring step, no check.
            lambda p: p.tests[19]['steps'][0]['checks'][0].update(absolute='yes'),
            lambda p: p.tests[0].update(stop_on_fail=1),
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
    def simulator(self, clock=time.monotonic, cases=None):
        p = load_profile()
        io = io_map(p)
        return io, Stm32Simulator(io_map=io, cases=p.fixtures['stm32_cases'] if cases is None else cases, clock=clock)

    def write_image(self, io, sim, image):
        for address, words in io.writes(None, image):
            sim.write(9, address, words)

    def test_reading_follows_written_stimulus_source_and_mode(self):
        io, sim = self.simulator()
        image = io.apply(io.safe_image(), POWER_ALL + [{'signal': 'set_40', 'value': 3}])
        image[WO.MUX] = io.mux_word(io.inputs['xp1_50'])
        self.write_image(io, sim, image)
        self.assertEqual(decode_int16(sim.read(9)[RI.ADC3_val - 1]), 850)
        wrong = dict(image)
        wrong[MATRIX0] = 1 << 8  # Stimulus lands on 41XP1 instead.
        self.write_image(io, sim, wrong)
        self.assertEqual(decode_int16(sim.read(9)[RI.ADC3_val - 1]), 0)
        shorted = dict(image)
        shorted[MATRIX0] = 1 << 0 | 1 << 1  # +3 V and −3 V on one pin.
        self.write_image(io, sim, shorted)
        self.assertIsNone(sim.stimuli()['set_40'])
        self.assertEqual(decode_int16(sim.read(9)[RI.ADC3_val - 1]), 0)
        no_mode = dict(image)
        no_mode[WO.Mode] = 0  # MCU follows the HMI, not the PC.
        self.write_image(io, sim, no_mode)
        self.assertEqual(sim.stimuli(), {})

    def test_dac_level_matches_its_case_within_quantization(self):
        io, sim = self.simulator()
        image = io.apply(io.safe_image(), POWER_ALL + [{'signal': 'set_40', 'value': 0.02}])
        image[WO.MUX] = io.mux_word(io.inputs['xp1_37'])
        self.write_image(io, sim, image)
        self.assertEqual(sim.read(9)[RI.ADC3_val - 1], 19)

    def test_after_ms_uses_scaled_simulated_time(self):
        now = [100.0]
        cases = [{'when': {'ac_36v': 1}, 'measure': {'ac_current': 3}},
                 {'when': {'ac_36v': 1}, 'measure': {'ac_current': 1.7}, 'after_ms': 60000}]
        io, sim = self.simulator(clock=lambda: now[0], cases=cases)
        sim.time_scale = 60
        image = io.apply(io.safe_image(), [{'signal': 'ac_36v', 'value': 1}])
        image[WO.MUX] = io.mux_word(io.inputs['ac_current'])
        self.write_image(io, sim, image)
        self.assertEqual(sim.read(9)[RI.ADC3_val - 1], 300)
        now[0] += 120 / 60  # 120 s of standard time at ×60.
        self.assertEqual(sim.read(9)[RI.ADC3_val - 1], 170)

    def test_bank_defaults_unchanged_without_mux_selection(self):
        io, sim = self.simulator()
        sim.write(9, 1, [1])
        self.assertEqual(sim.read(9)[RI.ADC0_val - 1], 1234)

    def test_extension_registers_exist_only_with_the_profile_map(self):
        io, sim = self.simulator()
        sim.write(9, MATRIX2, [1, 2])
        self.assertEqual(sim.mod_buf_to_write[MATRIX2:MATRIX2 + 2], [1, 2])
        with self.assertRaises(ValueError):
            Stm32Simulator().write(9, MATRIX2, [1])  # CPUv1.0 without the profile's proposed registers.


class EvaluateTests(unittest.TestCase):
    def test_absolute_and_default_quality(self):
        check = {'nominal': 8.5, 'tolerance': 0.2, 'absolute': True}
        self.assertEqual(evaluate(check, Sample(-8.45, 10, 'valid'), 10, 1000)[0], 'PASS')
        self.assertEqual(evaluate(check, Sample(8.0, 10, 'valid'), 10, 1000)[0], 'FAIL')
        self.assertEqual(evaluate({'nominal': 8.5, 'tolerance': 0.2}, Sample(-8.5, 10, 'valid'), 10, 1000)[0], 'FAIL')
        self.assertEqual(evaluate({'nominal': 1000, 'tolerance': 50}, Sample(1000, 10, 'default'), 10, 1000)[0], 'PASS')
        self.assertEqual(evaluate({'nominal': 1000, 'tolerance': 50}, Sample(1000, 10, 'stale'), 10, 1000)[0], 'ERROR')


class Stm32RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.backends = []
        self.manual_values = {}
        self.auto_submit = True
        self.submit_delay_ms = 0

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
            self.writes.append((address, list(values), time.monotonic()))
            return original(slave, address, values)
        patcher = patch.object(b.device.stm32_simulator, 'write', side_effect=record)
        patcher.start()
        self.addCleanup(patcher.stop)

        def operator():  # Stands in for the dialog; deferred like a real click.
            if b.manual_request is not None and self.auto_submit:
                QTimer.singleShot(self.submit_delay_ms, lambda: b.submit_manual(self.manual_values))
        b.manual_input_changed.connect(operator)
        b.connect_device()
        self.wait(lambda: b.connection == 'Sẵn sàng · MÔ PHỎNG')
        self.assertEqual(self.writes, [])  # Connecting only reads (FC03).
        return b

    def sent(self):
        return [(address, values) for address, values, _ in self.writes]

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
        sent = self.sent()
        self.assertEqual(sent[0], (WO.Mode, [1, 2]))                       # Mode=1 before anything else.
        self.assertEqual(sent[1], (WO.DAC_val, [0, 0]))                    # Known all-off state…
        self.assertEqual(sent[2], (WO.MUX, [MUX_IDLE, 0]))
        self.assertEqual(sent[3], (MATRIX0, [0, 0]))                       # Matrix board ID 6.
        self.assertEqual(sent[4], (MATRIX2, [0] * 6))                      # Boards 7–9 (proposed FW registers).
        self.assertEqual(sent[5], (WO.Power, [DC_BITS]))                   # One relay per DC pole, no AC.
        self.assertEqual(sent[6], (WO.MUX, [31 << 8 | 14]))                # MUX1 channel 14: dc_current.
        self.assertEqual(sent[-1], (WO.MUX, [MUX_IDLE, 0]))                # MUX idle and Power off.
        touched = {a + i for a, words in sent for i in range(len(words))}
        self.assertFalse(touched & FORBIDDEN)
        self.assertTrue(b.attempt['cleanup_confirmed'])
        notes = {t['note'] for t in b.attempt['transactions']}
        self.assertEqual(len(notes), 1)
        self.assertIn('chưa xác nhận đầu ra', notes.pop())
        self.assertEqual(b.stm32.mod_buf_to_read[RI.ADC3_val], 137)   # Dialog sees the runner's DI.

    def test_auto_runs_all_24_tests(self):
        b = self.backend(mode=Mode.AUTO)
        self.run_done(b, 60000)
        statuses = {a['test_id']: a['status'] for a in b.session['attempts']}
        self.assertEqual(statuses, {f'P{i:02}': 'PASS' for i in range(1, 25)})
        self.assertEqual(b.session['verdict'], 'PASS')
        self.assertTrue(b.session['defaults_used'])  # Frequencies were left empty.
        self.assertIn('mặc định chưa đo', b.message)

    def test_unsupported_board_blocks_test_and_sends_nothing(self):
        b = self.backend(without_board_2(), test='P10')
        self.run_done(b)
        self.assertEqual(b.attempt['status'], 'BLOCKED')
        self.assertIn('Matrix2_0/1', b.attempt['reason'])
        self.assertEqual(self.writes, [])

    def test_fail_scenario_gives_fail_not_pass(self):
        b = self.backend(test='P07', scenario='fail')
        self.run_done(b)
        self.assertEqual(b.attempt['status'], 'FAIL')
        self.assertEqual(b.session['verdict'], 'FAIL')

    def test_power_test_fail_stops_the_whole_run(self):
        b = self.backend(mode=Mode.AUTO, scenario='fail')
        self.run_done(b)
        self.assertEqual([(a['test_id'], a['status']) for a in b.session['attempts']], [('P01', 'FAIL')])
        self.assertEqual(b.session['stopped_by'], 'P01')
        self.assertTrue(b.attempt['cleanup_confirmed'])
        self.assertEqual(b.device.stm32_simulator.mod_buf_to_write[WO.Power], 0)
        self.assertIn('Dừng cả lượt', b.message)

    def test_p01_switches_36_to_22_v_break_before_make_with_manual_frequency(self):
        self.manual_values = {'hz_A': 1001.0, 'hz_B': 1100.0}  # hz_C left empty.
        b = self.backend(test='P01')
        self.run_done(b)
        rows = {(m['step_id'], m['signal']): m for m in b.attempt['measurements']}
        self.assertEqual((rows['S01', 'ac_current']['value'], rows['S01', 'ac_current']['status']), (3, 'PASS'))
        self.assertEqual(rows['S03', 'ac_A']['value'], 22)
        self.assertEqual((rows['S03', 'hz_A']['quality'], rows['S03', 'hz_A']['status']), ('valid', 'PASS'))
        self.assertEqual(rows['S03', 'hz_B']['status'], 'FAIL')
        self.assertEqual((rows['S03', 'hz_C']['value'], rows['S03', 'hz_C']['quality']), (1000, 'default'))
        self.assertIn('mặc định, chưa đo', rows['S03', 'hz_C']['reason'])
        self.assertEqual(rows['S03', 'ac_current']['value'], 1.7)
        self.assertEqual(b.attempt['status'], 'FAIL')
        power = [(values[WO.Power - address], at) for address, values, at in self.writes
                 if address <= WO.Power < address + len(values)]
        self.assertEqual([v for v, _ in power], [0, 1, 0, 2, 0])  # safe, 36 V, open, 22 V, safe
        self.assertGreaterEqual(power[3][1] - power[2][1], 0.15)  # break_ms after opening 36 V.
        self.assertFalse(any(v & 1 and v & 2 for v, _ in power))  # Never both transformers.

    def test_slow_operator_does_not_make_bench_readings_stale(self):
        # Regression: an answer given after stale_ms (1 s) used to turn the
        # step's bench readings (phase voltages, current) into ERROR.
        for values in ({'hz_A': 1000.0, 'hz_B': 999.0, 'hz_C': 1001.0}, {}):
            with self.subTest(values=values):
                self.manual_values, self.submit_delay_ms = values, 2500
                b = self.backend(test='P01')
                self.run_done(b)
                self.assertEqual(b.session['verdict'], 'PASS')
                s03 = {m['signal']: m for m in b.attempt['measurements'] if m['step_id'] == 'S03'}
                self.assertEqual({s: m['status'] for s, m in s03.items()},
                                 {s: 'PASS' for s in ('ac_A', 'ac_B', 'ac_C', 'hz_A', 'hz_B', 'hz_C', 'ac_current')})
                self.assertEqual(s03['ac_A']['quality'], 'valid')
                b.shutdown()
                self.wait(lambda: b.closed and not b.store.busy)

    def test_pause_while_waiting_for_operator_goes_safe(self):
        self.auto_submit = False
        b = self.backend(test='P01')
        self.assertTrue(b.start())
        self.wait(lambda: b.phase == 'awaiting_input', 15000)
        self.assertEqual([f['signal'] for f in b.manual_request['fields']], ['hz_A', 'hz_B', 'hz_C'])
        self.assertEqual(b.device.stm32_simulator.mod_buf_to_write[WO.Power], 2)  # 22 V stays on while measuring.
        self.assertTrue(b.pause())
        self.assertIsNone(b.manual_request)
        self.assertFalse(b.submit_manual({}))  # A late dialog answer is ignored.
        self.wait(lambda: b.paused)
        self.assertEqual(b.device.stm32_simulator.mod_buf_to_write[WO.Power], 0)
        b.stop()
        self.wait(lambda: not b.busy)

    def test_timeout_in_apply_is_error_without_retry_or_more_writes(self):
        b = self.backend(test='P07', scenario='timeout')
        with patch.object(b.device, '_request_stm32', wraps=b.device._request_stm32) as sent:
            self.run_done(b)
            self.assertEqual(b.session['verdict'], 'ERROR')
            self.assertFalse(b.attempt['cleanup_confirmed'])
            stimulus = [c for c in sent.call_args_list
                        if c.args[0] == 'write' and c.args[3] == MATRIX0 and c.args[4][0] != 0]
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
        self.assertEqual(self.sent()[-1], (WO.Power, [0]))

    def test_self_test_checks_link_and_measures_cpu_loop(self):
        b = self.backend(mode=Mode.SELF)
        b.configure(serial_number='')
        self.run_done(b)
        statuses = {a['test_id']: a['status'] for a in b.session['attempts']}
        self.assertEqual(statuses, {'D01': 'PASS', 'D02': 'PASS', 'D03': 'BLOCKED'})
        loop = next(a for a in b.session['attempts'] if a['test_id'] == 'D02')['measurements'][0]['value']
        self.assertAlmostEqual(loop, b.profile.fixtures['stm32_timing']['loop_ms'], delta=10)

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
        self.assertEqual(self.sent()[-1], (WO.Power, [0]))  # Outputs back to safe state.
        self.assertEqual(b.device.stm32_simulator.mod_buf_to_write[WO.Power], 0)
        self.assertEqual(b.session['state'], 'paused')
        count = len(self.writes)
        QTest.qWait(300)
        self.assertEqual(len(self.writes), count)  # Nothing is sent while paused.
        b.test['steps'][0]['wait_ms'] = 250
        self.assertTrue(b.resume())
        self.wait(lambda: not b.busy, 10000)
        self.assertEqual(self.sent()[count], (WO.Mode, [1, 2]))  # Rerun starts with a fresh prepare.
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
