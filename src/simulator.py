"""Device doubles without Qt: CPUv1.0 STM32 slave (RTU bytes) and the legacy A45 v1 controller."""
from collections import OrderedDict
import math
import secrets
import struct
import time

from src.common.wire import (Opcode, WireError, REQUEST_MAILBOX, RESPONSE_MAILBOX,
                             COMMIT_REGISTER, MAILBOX_REGISTERS)
from src.protocol import WireCodec, decode_frame, frame_to_registers, registers_to_frame
from src.protocol import (encode_int16, pack_data_t, register_words,
                          rtu_adu, split_rtu_adu)
from src.common.stm32 import WRITE_COUNT, READ_COUNT, DEFAULT_SLAVE, ReadRegister, WriteRegister


class Stm32Simulator:
    """CPUv1.0 register-level double, not an electrical simulator.

    Without a bench model, read values are fixed and independent of outputs.
    With ``io_map``/``cases`` (fixtures ``stm32_cases``), the ADC selected by
    the written MUX code returns the unit's demo response to the stimuli
    decoded back from the written DO words, so a wrong bit/route/Mode gives a
    wrong reading. Responses are demo data, never derived from test limits.
    No fabricated command-completion flag or valid UART receive length.

    ``loop_ms`` models the CPUv1.0 main loop (ASSUMED period, fixtures
    ``stm32_timing``): a Modbus write only lands in ``mod_buf_to_write``; the
    loop copies it to ``Modbus_DO`` at its next start, drives SW/MUX/Power over
    USART1, samples the ADC and copies ``Modbus_DI`` to ``mod_buf_to_read`` at
    its end. A DI read therefore reflects the outputs in effect at the start of
    the last *completed* loop: up to two loops after the write ACK.
    ``loop_ms=0`` applies writes instantly (pure codec tests).
    """
    def __init__(self, slave=DEFAULT_SLAVE, io_map=None, cases=(), clock=time.monotonic, loop_ms=0):
        self.slave = slave
        # Registers a profile declares as a proposed firmware extension
        # (e.g. SW03/SW04 for a second matrix board) exist only with io_map.
        self.write_count = io_map.write_count if io_map is not None else WRITE_COUNT
        self.mod_buf_to_write = [0] * self.write_count
        self.mod_buf_to_read = [0] * READ_COUNT
        self.mod_buf_to_read[7:12] = [1234, encode_int16(-567), 2400, 1200, 330]
        self.mod_buf_to_read[12] = 0x4000 | 470  # 4.70 kOhm
        self.mod_buf_to_read[13] = 0x03FF
        self.mod_buf_to_read[14] = encode_int16(-123)
        self.mod_buf_to_read[20:30] = pack_data_t(b'STM32 SIM')
        self.encoder_triggers = 0
        self.io_map = io_map
        self.cases = list(cases)
        self.clock = clock
        self.loop_ms = loop_ms
        self.time_scale = 1.0  # Simulated unit time runs with the runner's ×N.
        self.scenario = 'normal'
        self.fail_signal = None
        self._t0 = clock()
        self._image = tuple(self.mod_buf_to_write)  # Modbus_DO the loop executes.
        self._pending = []  # (effective_at, mod_buf_to_write copy) not yet taken by the loop.
        self._active = {}  # stimulus -> (value, effective_at)

    def _check_slave(self, slave):
        if slave != self.slave:
            raise ValueError('Giả lập: không có phản hồi từ Slave ID này.')

    def read(self, slave):
        """mod_buf_to_read[1..29], as FC03 address 1, count 29 returns it."""
        self._check_slave(slave)
        return self.read_holding(1, READ_COUNT - 1)

    def read_holding(self, address, count):
        self._measure_selected()
        return self.mod_buf_to_read[address:address + count]

    def write(self, slave, address, values):
        """FC06/FC16 into mod_buf_to_write[0..28], as the firmware callback."""
        self._check_slave(slave)
        words = register_words(values)
        if type(address) is not int or address < 0 or not words or address + len(words) > self.write_count:
            raise ValueError(f'Vùng ghi ngoài mod_buf_to_write[0..{self.write_count - 1}].')
        self.mod_buf_to_write[address:address + len(words)] = words
        # Only the documented auto-clear behavior.
        if (self.mod_buf_to_write[1] == 1 and self.mod_buf_to_write[13] & 0x8000
                and self.mod_buf_to_write[14]):
            self.encoder_triggers += 1
            self.mod_buf_to_write[13:15] = [0, 0]
        self._pending.append((self._effective_at(self.clock()), tuple(self.mod_buf_to_write)))
        self._sync()

    def _effective_at(self, t):
        """Start of the first loop that copies a write made at ``t``."""
        if not self.loop_ms:
            return t
        loop = self.loop_ms / 1000
        return self._t0 + (math.floor((t - self._t0) / loop) + 1) * loop

    def _sample_at(self, now):
        """Start of the last completed loop, whose DI copy a read returns."""
        if not self.loop_ms:
            return now
        loop = self.loop_ms / 1000
        return self._t0 + (math.floor((now - self._t0) / loop) - 1) * loop

    def _sync(self):
        sample = self._sample_at(self.clock())
        while self._pending and self._pending[0][0] <= sample:
            at, image = self._pending.pop(0)
            previous = self._active
            self._active = {sid: previous[sid] if sid in previous and previous[sid][0] == value else (value, at)
                            for sid, value in self._stimuli(image).items()}
            self._image = image
        return sample

    def _stimuli(self, image):
        if self.io_map is None or image[WriteRegister.Mode] != 1:
            return {}
        return self.io_map.inverse({a: image[a] for a in range(1, len(image))})

    def stimuli(self):
        """Stimuli the MCU applies now: only in Mode=1 (AutoComputer)."""
        self._sync()
        return self._stimuli(self._image)

    def _measure_selected(self):
        sample = self._sync()
        if self.loop_ms:
            # One LSB of ADC2 noise that changes with every completed loop, so
            # the self-test can estimate the loop period from FC03 polling
            # (ADC2 carries no bench measurement in the A45 map).
            loop = round((sample - self._t0) / (self.loop_ms / 1000))
            self.mod_buf_to_read[ReadRegister.ADC2_val] = 2400 + loop % 2
        if self.io_map is None or self._image[WriteRegister.Mode] != 1:
            return
        mux = self._image[self.io_map.mux]
        for sid, entry in self.io_map.inputs.items():
            if (entry['status'] != 'unsupported' and entry.get('kind') == 'adc'
                    and self.io_map.mux_word(entry) == mux):
                self.mod_buf_to_read[ReadRegister[entry['register']]] = self.io_map.encode_input(
                    sid, self.response(sid, sample))

    def response(self, sid, now=None):
        """Most specific fixture case matching the active stimuli (0 if none).

        A DAC level matches its case within half a DAC step (quantization);
        a shorted pin (two sources, value ``None``) matches nothing.
        """
        now = self.clock() if now is None else now
        dac = self.io_map.dac if self.io_map is not None else None
        tolerance = abs(dac['scale']) / 2 + 1e-9 if dac else 1e-6
        best = None
        for case in self.cases:
            when = case['when']
            if sid not in case['measure'] or not all(
                    k in self._active and self._active[k][0] is not None
                    and math.isclose(self._active[k][0], v, abs_tol=tolerance) for k, v in when.items()):
                continue
            since = max((self._active[k][1] for k in when), default=now)
            if (now - since) * 1000 * self.time_scale < case.get('after_ms', 0):
                continue
            rank = (len(when), case.get('after_ms', 0))
            if best is None or rank > best[0]:
                best = (rank, case['measure'][sid])
        value = 0.0 if best is None else best[1]
        if self.scenario == 'fail':
            self.fail_signal = self.fail_signal or sid
            if sid == self.fail_signal:
                value += 1.0  # Demo deviation, far outside every ±0.2 limit.
        return value


class Stm32RtuSlave:
    """CPUv1.0 Modbus RTU slave (FreeModbus) seen from the wire: RTU bytes in,
    RTU bytes out, or ``None`` for silence.

    - Wrong CRC, another slave ID or a broadcast: frame dropped, no reply.
    - FC03 reads ``mod_buf_to_read``; FC06/FC16 write ``mod_buf_to_write``;
      address = array index (the FreeModbus +1/-1 cancel out).
    - Exception 03 for a bad quantity/length, 02 outside the arrays (ASSUMED
      limits: 30 DI / 29 DO registers, plus any DO registers the profile
      declares as a proposed firmware extension), 01 for any other function code. The
      firmware also accepts FC17; the PC never sends it, so it is not simulated.
    """
    def __init__(self, simulator):
        self.simulator = simulator

    def handle(self, raw):
        try:
            slave, pdu = split_rtu_adu(raw)
        except ValueError:
            return None
        sim = self.simulator
        if slave != sim.slave or not pdu:
            return None
        function = pdu[0]

        def exception(code):
            return rtu_adu(slave, bytes([function | 0x80, code]))

        if function == 3:
            if len(pdu) != 5:
                return exception(3)
            address, count = struct.unpack('>HH', pdu[1:])
            if not 1 <= count <= 125:
                return exception(3)
            if address + count > READ_COUNT:
                return exception(2)
            words = sim.read_holding(address, count)
            return rtu_adu(slave, struct.pack('>BB', 3, 2 * count) + struct.pack(f'>{count}H', *words))
        if function == 6:
            if len(pdu) != 5:
                return exception(3)
            address, value = struct.unpack('>HH', pdu[1:])
            if address >= sim.write_count:
                return exception(2)
            sim.write(slave, address, [value])
            return rtu_adu(slave, pdu)  # FC06 echoes the request.
        if function == 16:
            if len(pdu) < 6:
                return exception(3)
            address, count, size = struct.unpack('>HHB', pdu[1:6])
            if not 1 <= count <= 120 or size != 2 * count or len(pdu) != 6 + size:
                return exception(3)
            if address + count > sim.write_count:
                return exception(2)
            sim.write(slave, address, list(struct.unpack(f'>{count}H', pdu[6:])))
            return rtu_adu(slave, struct.pack('>BHH', 16, address, count))
        return exception(1)


class SimulatedController:
    def __init__(self, profile, clock=time.monotonic, node=1):
        self.profile = profile
        self.codec = WireCodec(profile)
        self.clock = clock
        self.node = node
        self.started = clock()
        self.boot_id = secrets.randbits(32) or 1
        self.session = None
        self.high_sequence = 0
        self.cache = OrderedDict()
        self.scenario = 'normal'
        self.roles = profile.system.get('status_signals', {})
        self.values = {sid: int(role == 'ready') for role, sid in self.roles.items()}
        self.connected = False
        self.confirmed = None
        self.pending = None
        self.failed_case = None
        self.last_case = None
        self.sample_seq = 0
        self.sample_time = self.started
        self.executions = 0
        self.staging = {}
        self.mailbox = []

    def exchange(self, raw):
        request = decode_frame(raw)
        if request.node != self.node:
            raise ConnectionError('Không có trung tâm ở địa chỉ node này (mô phỏng).')
        if request.flags != 0:
            raise ValueError('Trung tâm chỉ nhận khung yêu cầu.')
        key = (request.session, request.sequence)
        cached = self.cache.get(key)
        if cached:
            if cached[0] != raw:
                return self.codec.response(request, error=WireError.CONFLICT)
            return cached[1]
        try:
            operation, args = self.codec.decode_request(request)
        except ValueError:
            return self.codec.response(request, error=WireError.BAD_PAYLOAD)
        if operation != 'connect' and (not self.connected or request.session != self.session):
            return self.codec.response(request, error=WireError.SESSION)
        if request.session == self.session and request.sequence <= self.high_sequence:
            return self.codec.response(request, error=WireError.CONFLICT)
        if operation == 'connect':
            # HELLO does not change physical outputs or claim safe state.
            self.connected = True
            self.session = request.session
            self.high_sequence = 0
            self.cache.clear()
            result = dict(boot_id=self.boot_id, simulation=True)
        elif operation in ('prepare', 'apply', 'finish'):
            if self.pending and operation != 'finish':
                return self.codec.response(request, error=WireError.BUSY)
            if operation == 'apply' and args['case'] not in self.profile.fixtures['cases']:
                return self.codec.response(request, error=WireError.BAD_PAYLOAD)
            self.pending = (args['token'], self.clock() + (.12 if operation == 'apply' else .10),
                            args.get('actions', []), args.get('case'))
            self.executions += 1
            result = {'accepted': True}
        else:
            result = self._snapshot()
        self.high_sequence = request.sequence
        response = self.codec.response(request, result)
        self.cache[key] = (raw, response)
        if len(self.cache) > 64:
            self.cache.popitem(last=False)
        return response

    def _snapshot(self):
        now = self.clock()
        if self.pending and now >= self.pending[1]:
            self.confirmed, _, actions, self.last_case = self.pending
            self.pending = None
            self.values = {k: v for k, v in self.values.items()
                           if k in (self.roles.get('ready'), self.roles.get('fault'))}
            if 'output' in self.roles:
                self.values[self.roles['output']] = int(self.last_case is not None)
            for action in actions:
                self.values[action['signal']] = action['value']
        if self.scenario == 'disconnect' and self.last_case:
            self.connected = False
            raise ConnectionError('Mất liên lạc khi đang chạy (mô phỏng khung A45)')
        if self.scenario == 'protection' and self.last_case and 'fault' in self.roles:
            self.values[self.roles['fault']] = 1
        if self.last_case:
            self.values.update(self.profile.fixtures['cases'][self.last_case])
            if self.scenario == 'fail':
                self.failed_case = self.failed_case or self.last_case
                if self.failed_case == self.last_case:
                    sid = next(iter(self.profile.fixtures['cases'][self.last_case]))
                    self.values[sid] += 100
        if self.scenario != 'stale' or not self.sample_seq:
            self.sample_seq = (self.sample_seq + 1) & 0xFFFFFFFF or 1
            self.sample_time = now
        return dict(values=dict(self.values), confirmed=self.confirmed, boot_id=self.boot_id,
                    sample_seq=self.sample_seq, uptime_ms=int((now - self.started) * 1000) & 0xFFFFFFFF,
                    age_ms=min(0xFFFFFFFF, int((now - self.sample_time) * 1000)))

    def write_registers(self, address, values):
        """Reference mailbox semantics for a firmware FC16/FC06 handler."""
        if not values or any(type(v) is not int or not 0 <= v <= 65535 for v in values):
            raise ValueError('Thanh ghi không hợp lệ.')
        if address == COMMIT_REGISTER:
            if values != [1] or 0 not in self.staging:
                raise ValueError('Commit mailbox không hợp lệ.')
            count = 1 + (self.staging[0] + 1) // 2
            if not 1 <= count <= MAILBOX_REGISTERS or set(self.staging) != set(range(count)):
                raise ValueError('Mailbox chưa được ghi đầy đủ.')
            raw = registers_to_frame([self.staging[i] for i in range(count)])
            self.mailbox = frame_to_registers(self.exchange(raw))
            self.staging.clear()
        else:
            offset = address - REQUEST_MAILBOX
            if not 0 <= offset < MAILBOX_REGISTERS or offset + len(values) > MAILBOX_REGISTERS:
                raise ValueError('Ngoài vùng request mailbox.')
            if offset == 0:
                self.staging.clear()
                self.mailbox = []
            self.staging.update({offset + i: value for i, value in enumerate(values)})

    def read_registers(self, address, count):
        offset = address - RESPONSE_MAILBOX
        if offset < 0 or count < 1 or offset + count > len(self.mailbox):
            raise ValueError('Chưa có phản hồi hoặc đọc ngoài mailbox.')
        # Frozen until the next request starts: multiple reads share one snapshot.
        return self.mailbox[offset:offset + count]
