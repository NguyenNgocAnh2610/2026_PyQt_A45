"""Native STM32 register codec and the earlier experimental A45 frame codec."""
import math
import binascii
import hashlib
import json
import struct
import time
import uuid
from dataclasses import dataclass

from PySide6.QtSerialBus import QModbusDataUnit

from src.common.testing import Sample
from src.common.stm32 import (READ_COUNT, WRITE_COUNT, ReadRegister as RI, ReadRegister, WriteRegister,
                              DEFAULT_CPU_MAP)
from src.common.wire import MAGIC, VERSION, MAX_PAYLOAD, MAX_FRAME, MAX_SIGNALS, OPERATIONS, Opcode, QUALITY


def register_words(values):
    words = list(values)
    if any(type(v) is not int or not 0 <= v <= 0xFFFF for v in words):
        raise ValueError('Thanh ghi raw phải là số nguyên 0–65535.')
    return words


def encode_int16(value):
    if type(value) is not int or not -32768 <= value <= 32767:
        raise ValueError('Giá trị int16 phải từ -32768 đến 32767.')
    return value & 0xFFFF


def decode_int16(word):
    register_words([word])
    return word - 65536 if word & 0x8000 else word


def pack_data_t(data):
    """20 peripheral bytes, low byte first INSIDE each big-endian Modbus word."""
    data = bytes(data)
    if len(data) > 20:
        raise ValueError('DataT tối đa 20 byte.')
    return list(struct.unpack('<10H', data.ljust(20, b'\0')))


def unpack_data_r(words):
    words = register_words(words)
    if len(words) != 10:
        raise ValueError('DataR cần đúng 10 thanh ghi.')
    return struct.pack('<10H', *words)  # CDN does not define valid receive length.


def encode_encoder(period_ms, pulses, forward=True):
    if type(period_ms) is not int or not 4 <= period_ms <= 0x3FFF or period_ms % 4:
        raise ValueError('Chu kỳ encoder phải là bội số 4 ms, từ 4 đến 16380.')
    if type(pulses) is not int or not 1 <= pulses <= 65535:
        raise ValueError('Số xung encoder phải từ 1 đến 65535.')
    return [0x8000 | (0x4000 if forward else 0) | period_ms, pulses]


def stm32_write_words(address, values, limit=WRITE_COUNT):
    """``limit`` > WRITE_COUNT only for registers a profile declares as a
    proposed CPU firmware extension (``stm32_io.extra_write_registers``)."""
    words = register_words(values)
    if not isinstance(address, int) or isinstance(address, bool) or address < 1 or not words or address + len(words) > limit:
        raise ValueError(f'Vùng ghi STM32 chỉ có địa chỉ 1–{limit - 1}; địa chỉ 0 dành riêng.')
    return words


def decode_stm32(words, cpu_map=DEFAULT_CPU_MAP):
    """Decode a full DI bank (index 0 = Null). Index 1–19 are identical in
    every supported firmware; the UART receive buffers depend on ``cpu_map``."""
    words = register_words(words)
    if len(words) != cpu_map.read_count:
        raise ValueError(f'Mảng đọc {cpu_map.name} cần {cpu_map.read_count} phần tử, gồm Null tại 0.')
    resistance = words[RI.Ohm_val]
    metric = resistance >> 14
    amount = (resistance & 0x3FFF) / 100.0
    return {
        'adc_volts': [decode_int16(v) / 100.0 for v in words[RI.ADC0_val:RI.ADC4_val + 1]],
        'resistance_ohms': None if metric == 3 else amount * (1, 1000, 1000000)[metric],
        'resistance_quality': 'overrange' if metric == 3 else 'valid',
        'din_levels': [(words[RI.DIN] >> bit) & 1 for bit in range(10)],
        'encoder_count': decode_int16(words[RI.DataI1]),
        'encoder_a': words[RI.DataI2], 'encoder_b': words[RI.DataI3],
        'encoder_num_pulse': decode_int16(words[RI.DataI4]),
        'ssi_ident': words[RI.DataI5],
        # Low byte first inside each word; the valid length is unknown (CDN).
        'received': {name: struct.pack(f'<{count}H', *words[first:first + count])
                     for name, first, count in cpu_map.uart_buffers},
        'received_length': None,
    }


class UnsupportedSignal(ValueError):
    """The configured hardware cannot drive or measure this signal."""


class Stm32IoMap:
    """Logical bench signals <-> CPU DO/DI words. Pure mapping, no I/O.

    An *image* is ``{DO address: uint16}`` for the registers the runner owns.
    Register names resolve through the firmware map (``hardware.cpu_map``);
    entries stay ``assumed`` until verified on the bench; this class never
    decides that an output is safe.

    Output kinds:
    - ``bit``: one relay/DOUT bit that switches a fixed source (``on_value``);
      ``off_value`` (optional) or ``None`` opens it.
    - ``pin``: one bench pin wired to a signal-relay matrix board. Each matrix
      input carries a ready-made source (fixed level, ground, DAC, pulse). The
      pin is connected to at most one input at a time; ``None`` leaves it open.
    """

    def __init__(self, io, cpu_map=DEFAULT_CPU_MAP):
        self.cpu_map = cpu_map
        self.slave = io['slave']
        self.extra = {name: int(address) for name, address in io.get('extra_write_registers', {}).items()}
        self.write_count = max([cpu_map.write_count] + [address + 1 for address in self.extra.values()])
        self.mux = self.address(io['mux_register'])
        layout = io.get('mux_layout', {})
        self.mux_banks = layout.get('banks', 1)
        self.mux_bank_bits = layout.get('bank_bits', 16)
        self.mux_idle = layout.get('idle_channel', 0)
        # Valid channels per bank (RLMUX: 32; its firmware does not bound-check).
        self.mux_channel_count = layout.get('channels', 1 << self.mux_bank_bits)
        self.mux_settle_ms = io['mux_settle_ms']
        self.di_update_ms = io.get('di_update_ms', 0)
        # Break-before-make: opened relays must be executed by the MCU loop
        # before new ones close (never two sources on one pin / AC 36+22 V).
        self.break_ms = io.get('break_ms', self.di_update_ms)
        self.dac = io.get('dac')
        self.interlocks = [list(group) for group in io.get('interlocks', [])]
        self.inputs = io['inputs']
        self.outputs = dict(io.get('outputs', {}))
        self.outputs.update(self._matrix_pins(io))
        self._boards = {board['id']: board for board in io.get('matrix_boards', [])}
        base = {**io['safe_state'], **io['session']}
        self._base = {self.address(name): value for name, value in base.items()}
        self.relay_registers = {self.address(register) for entry in self.outputs.values()
                                for register, _ in self.points(entry)}

    def address(self, name):
        """DO index of a CPUv1.0 register or of a declared firmware extension."""
        if name in self.extra:
            return self.extra[name]
        return self.cpu_map.write_index(name)

    @staticmethod
    def _matrix_pins(io):
        sources = io.get('sources', {})
        pins = {}
        for board in io.get('matrix_boards', []):
            inputs = board['size']['inputs']
            for output, sid in board['outputs'].items():
                entry = dict(kind='pin', levels=[], dac=None, status=board['status'],
                             board=board['id'], output=int(output))
                if board['status'] == 'unsupported':
                    entry['reason'] = board['reason']
                for number, name in board['inputs'].items():
                    index = (int(output) - 1) * inputs + int(number) - 1  # layout "out*N+in"
                    point = dict(register=board['registers'][index // 16], bit=index % 16, source=name,
                                 input=int(number))
                    if sources[name].get('dac'):
                        entry['dac'] = point
                    else:
                        entry['levels'].append(dict(point, value=sources[name]['value']))
                pins[sid] = entry
        return pins

    @staticmethod
    def points(entry):
        """(register, bit) contacts an output owns; none when unsupported."""
        if entry.get('status') == 'unsupported':
            return []
        if entry.get('kind') == 'bit':
            return [(entry['register'], entry['bit'])]
        if entry.get('kind') == 'pin':
            return [(p['register'], p['bit']) for p in entry['levels'] + ([entry['dac']] if entry['dac'] else [])]
        return []

    def safe_image(self):
        """Session registers (Mode=1 …) plus every owned output switched off."""
        return dict(self._base)

    def _output(self, sid):
        entry = self.outputs.get(sid)
        if entry is None:
            raise ValueError(f'Chưa ánh xạ tín hiệu yêu cầu {sid} vào thanh ghi STM32.')
        if entry['status'] == 'unsupported':
            raise UnsupportedSignal(f"{sid}: {entry['reason']}")
        return entry

    def _input(self, sid):
        entry = self.inputs.get(sid)
        if entry is None:
            raise ValueError(f'Chưa ánh xạ tín hiệu đo {sid} vào thanh ghi STM32.')
        if entry['status'] == 'unsupported':
            raise UnsupportedSignal(f"{sid}: {entry['reason']}")
        return entry

    def input_kind(self, sid):
        return self._input(sid).get('kind')

    def _is_set(self, image, point):
        return image.get(self.address(point['register']), 0) >> point['bit'] & 1

    def _set(self, image, register, bit, on):
        address = self.address(register)
        word = image.get(address, 0)
        image[address] = word | 1 << bit if on else word & ~(1 << bit) & 0xFFFF

    def _dac_count(self, sid, value):
        dac = self.dac
        if not dac['min'] - 1e-9 <= value <= dac['max'] + 1e-9:
            raise ValueError(f"{sid}: {value:g} V không có nguồn sẵn và ngoài dải DAC {dac['min']:g}…{dac['max']:g} V.")
        count = round((value - dac['offset']) / dac['scale'])
        if not dac['count_min'] <= count <= dac['count_max']:
            raise ValueError(f'{sid}: mã DAC {count} ngoài giới hạn phần cứng.')
        return count

    def apply(self, image, actions):
        """New image with actions added; raises instead of clamping/guessing."""
        image = dict(image)
        for action in actions:
            sid, value = action['signal'], action['value']
            entry = self._output(sid)
            if entry['kind'] == 'bit':
                if value is None or ('off_value' in entry and math.isclose(value, entry['off_value'], abs_tol=1e-9)):
                    self._set(image, entry['register'], entry['bit'], False)
                elif math.isclose(value, entry['on_value'], abs_tol=1e-9):
                    self._set(image, entry['register'], entry['bit'], True)
                else:
                    raise ValueError(f"{sid}: tiếp điểm chỉ cấp {entry['on_value']:g}, không đặt được {value:g}.")
                continue
            for register, bit in self.points(entry):  # One source per pin: release all first.
                self._set(image, register, bit, False)
            if value is None:
                continue  # Open circuit.
            level = next((p for p in entry['levels'] if math.isclose(p['value'], value, abs_tol=1e-9)), None)
            if level is not None:
                self._set(image, level['register'], level['bit'], True)
                continue
            if entry['dac'] is None or self.dac is None:
                raise ValueError(f'{sid}: không có nguồn {value:g} V nối tới chân này.')
            word = encode_int16(self._dac_count(sid, value))
            dac = self.address(self.dac['register'])
            for other_sid, other in self.outputs.items():
                if (other_sid != sid and other.get('kind') == 'pin' and other.get('dac')
                        and other['status'] != 'unsupported' and self._is_set(image, other['dac'])
                        and image.get(dac, 0) != word):
                    raise ValueError(f'{sid} và {other_sid} cần hai mức khác nhau trên cùng một DAC.')
            self._set(image, entry['dac']['register'], entry['dac']['bit'], True)
            image[dac] = word
        for group in self.interlocks:
            active = [sid for sid in group if sid in self.outputs
                      and any(self._is_set(image, dict(register=r, bit=b)) for r, b in self.points(self.outputs[sid]))]
            if len(active) > 1:
                raise ValueError('Liên động: không được bật đồng thời ' + ' và '.join(active) + '.')
        return image

    def writes(self, old, new):
        """Changed words of ``new`` as contiguous (address, words) runs.

        ``old=None`` means the MCU state is unknown: write every owned register.
        """
        runs = []
        for address in sorted(new):
            if old is not None and old.get(address) == new[address]:
                continue
            if runs and runs[-1][0] + len(runs[-1][1]) == address:
                runs[-1][1].append(new[address])
            else:
                runs.append((address, [new[address]]))
        return [(address, stm32_write_words(address, words, self.write_count)) for address, words in runs]

    def phases(self, old, new):
        """Break-before-make: ``[opened, new]`` when relays both open and close.

        The runner waits ``break_ms`` after the opening write before closing,
        so the MCU never drives an old and a new source together.
        """
        if old is None:
            return [new]
        opened = dict(old)
        for address in self.relay_registers & set(new):
            opened[address] = old.get(address, 0) & new[address]
        closes = any(new[a] & ~opened.get(a, 0) for a in self.relay_registers & set(new))
        if opened == old or not closes:
            return [new]
        return [opened, new]

    def unsupported(self, actions=(), signals=()):
        reasons = []
        for sid, table in [(a['signal'], self.outputs) for a in actions] + [(s, self.inputs) for s in signals]:
            entry = table.get(sid)
            if entry is not None and entry['status'] == 'unsupported':
                reason = f"{sid}: {entry['reason']}"
                if reason not in reasons:
                    reasons.append(reason)
        return reasons

    def verification(self, actions=(), signals=()):
        """Mapping entries a run relies on that are not yet 'verified'.

        Used to gate runs on real hardware (AGENTS.md: only mappings checked
        on the bench). Returns human-readable reasons; empty = all verified."""
        pending = []

        def note(label, status):
            if status != 'verified' and label not in pending:
                pending.append(label)
        for sid in dict.fromkeys(a['signal'] for a in actions):
            entry = self.outputs.get(sid)
            if entry is None:
                continue
            note(f'{sid} ({entry["status"]})', entry['status'])
            if entry.get('kind') == 'pin':
                board = self._boards.get(entry['board'], {})
                note(f'bo matrix {entry["board"]} ({board.get("status")})', board.get('status'))
                if entry.get('dac') is not None and self.dac is not None:
                    note(f'DAC ({self.dac.get("status")})', self.dac.get('status'))
        for sid in dict.fromkeys(signals):
            entry = self.inputs.get(sid)
            if entry is not None and entry.get('kind') != 'manual':
                note(f'{sid} ({entry["status"]})', entry['status'])
        return pending

    def mux_word(self, entry=None):
        """MUX word selecting ``entry``'s channel; other banks stay idle."""
        word = 0
        for bank in range(self.mux_banks):
            channel = entry['mux'] if entry is not None and entry.get('mux_bank', 0) == bank else self.mux_idle
            word |= channel << (bank * self.mux_bank_bits)
        return word

    def mux_channels(self, word):
        """Channel per bank encoded in a MUX word."""
        mask = (1 << self.mux_bank_bits) - 1
        return [(word >> (bank * self.mux_bank_bits)) & mask for bank in range(self.mux_banks)]

    def groups(self, signals):
        """[(MUX word | None, [signals])]; one FC03 per group."""
        groups = {}
        for sid in signals:
            entry = self._input(sid)
            if entry['kind'] not in ('adc', 'link'):
                raise ValueError(f'{sid}: kiểu đo {entry["kind"]} không đọc qua FC03 thường.')
            groups.setdefault(self.mux_word(entry) if entry['kind'] == 'adc' else None, []).append(sid)
        return list(groups.items())

    def decode(self, words, sid):
        """Physical value from a 30-word DI snapshot (index 0 = Null)."""
        entry = self._input(sid)
        if entry['kind'] == 'link':
            return 1  # Only the fact that a valid FC03 reply arrived.
        raw = words[self.cpu_map.read_index(entry['register'])]
        value = decode_int16(raw) if entry['signed'] else raw
        return round(value * entry['scale'] + entry.get('offset', 0), 9)

    def encode_input(self, sid, value):
        """Inverse of decode, saturating like an ADC. Simulator use only."""
        entry = self._input(sid)
        count = round((value - entry.get('offset', 0)) / entry['scale'])
        if entry['signed']:
            return encode_int16(max(-32768, min(32767, count)))
        return max(0, min(0xFFFF, count))

    def inverse(self, image):
        """Requested stimuli visible in a DO image. Simulator use only.

        A pin with two closed inputs (a short between sources) maps to ``None``.
        """
        active = {}
        for sid, entry in self.outputs.items():
            if entry['status'] == 'unsupported':
                continue
            if entry['kind'] == 'bit':
                if self._is_set(image, entry):
                    active[sid] = entry['on_value']
                continue
            closed = [p for p in entry['levels'] if self._is_set(image, p)]
            dac_on = entry['dac'] is not None and self._is_set(image, entry['dac'])
            if len(closed) + dac_on > 1:
                active[sid] = None
            elif closed:
                active[sid] = closed[0]['value']
            elif dac_on:
                count = decode_int16(image.get(self.address(self.dac['register']), 0))
                active[sid] = round(self.dac['offset'] + self.dac['scale'] * count, 9)
        return active


def validate_write_ack(response, address, values):
    """Qt result() is invalid for writes: validate the raw FC06/FC16 echo."""
    function = 6 if len(values) == 1 else 16
    tail = values[0] if function == 6 else len(values)
    return (response.isValid() and response.functionCode().value == function
            and bytes(response.data()) == struct.pack('>HH', address, tail))


@dataclass(frozen=True)
class Frame:
    node: int
    opcode: int
    flags: int
    session: int
    sequence: int
    payload: bytes = b''


HEADER = struct.Struct('>2sBBBBIIH')


def encode_frame(frame):
    for value, low, high in ((frame.node, 1, 247), (frame.opcode, 0, 255),
                             (frame.session, 1, 0xFFFFFFFF), (frame.sequence, 1, 0xFFFFFFFF)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Trường header A45 không hợp lệ.')
    if frame.flags not in (0, 1, 3) or len(frame.payload) > MAX_PAYLOAD:
        raise ValueError('Flags/độ dài khung A45 không hợp lệ.')
    raw = HEADER.pack(MAGIC, VERSION, frame.node, frame.opcode, frame.flags,
                      frame.session, frame.sequence, len(frame.payload)) + frame.payload
    return raw + struct.pack('>H', binascii.crc_hqx(raw, 0xFFFF))


def decode_frame(raw):
    if not 18 <= len(raw) <= MAX_FRAME:
        raise ValueError('Độ dài khung A45 không hợp lệ.')
    magic, version, node, opcode, flags, session, sequence, length = HEADER.unpack_from(raw)
    if magic != MAGIC or version != VERSION or len(raw) != HEADER.size + length + 2:
        raise ValueError('Sai magic/version/length A45.')
    if binascii.crc_hqx(raw[:-2], 0xFFFF) != struct.unpack('>H', raw[-2:])[0]:
        raise ValueError('CRC A45 không khớp.')
    frame = Frame(node, opcode, flags, session, sequence, bytes(raw[HEADER.size:-2]))
    encode_frame(frame)  # Same field bounds in both directions.
    return frame


class FrameStream:
    """Bounded UART stream parser: fragments, concatenated frames and noise."""
    def __init__(self):
        self.buffer = bytearray()
        self.errors = 0

    def feed(self, data):
        frames = []
        # Process bounded chunks even if a caller supplies a large noise buffer.
        for start in range(0, len(data), MAX_FRAME):
            self.buffer.extend(data[start:start + MAX_FRAME])
            while self.buffer:
                pos = self.buffer.find(MAGIC)
                if pos < 0:
                    self.buffer[:] = self.buffer[-1:] if self.buffer[-1:] == MAGIC[:1] else b''
                    break
                if pos:
                    del self.buffer[:pos]
                if len(self.buffer) < HEADER.size:
                    break
                length = HEADER.unpack_from(self.buffer)[-1]
                if length > MAX_PAYLOAD or self.buffer[2] != VERSION:
                    self.errors += 1
                    del self.buffer[0]
                    continue
                total = HEADER.size + length + 2
                if len(self.buffer) < total:
                    break
                raw = bytes(self.buffer[:total])
                try:
                    decode_frame(raw)
                except ValueError:
                    self.errors += 1
                    del self.buffer[0]
                else:
                    frames.append(raw)
                    del self.buffer[:total]
        return frames


def frame_to_registers(raw):
    decode_frame(raw)
    padded = raw + (b'\0' if len(raw) % 2 else b'')
    return [len(raw), *struct.unpack(f'>{len(padded) // 2}H', padded)]


def registers_to_frame(values):
    if not values or any(type(v) is not int or not 0 <= v <= 65535 for v in values):
        raise ValueError('Mailbox không hợp lệ.')
    length = values[0]
    if not 18 <= length <= MAX_FRAME or len(values) != 1 + (length + 1) // 2:
        raise ValueError('Độ dài mailbox không hợp lệ.')
    raw = struct.pack(f'>{len(values) - 1}H', *values[1:])
    if length % 2 and raw[-1] != 0:
        raise ValueError('Byte padding mailbox phải bằng 0.')
    raw = raw[:length]
    decode_frame(raw)
    return raw


class _Reader:
    def __init__(self, payload):
        self.payload = payload
        self.offset = 0

    def take(self, size):
        if self.offset + size > len(self.payload):
            raise ValueError('Payload A45 thiếu dữ liệu.')
        value = self.payload[self.offset:self.offset + size]
        self.offset += size
        return value

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def finish(self):
        if self.offset != len(self.payload):
            raise ValueError('Payload A45 thừa dữ liệu.')


class WireCodec:
    """Stable numeric channel IDs and one application schema for both links."""
    def __init__(self, profile):
        self.mapping = dict(profile.hardware.get('wire_signals', {}))
        definitions = {item['id']: item for item in profile.signals}
        if (set(self.mapping) != set(definitions) or not 1 <= len(self.mapping) <= MAX_SIGNALS
                or any(type(v) is not int or not 1 <= v <= 65535 for v in self.mapping.values())
                or len(set(self.mapping.values())) != len(self.mapping)):
            raise ValueError('wire_signals phải ánh xạ duy nhất toàn bộ tín hiệu (1–80 kênh).')
        self.reverse = {value: key for key, value in self.mapping.items()}
        self.outputs = {sid for sid, item in definitions.items() if item['source'] == 'derived'}
        manifest = [[sid, self.mapping[sid], definitions[sid]['unit'], definitions[sid]['kind'],
                     definitions[sid]['source']] for sid in sorted(definitions)]
        self.schema_hash = hashlib.sha256(json.dumps(manifest, ensure_ascii=True,
                                                     separators=(',', ':')).encode()).digest()[:16]
        self.boot_id = None
        self.simulation = True
        self.last_sample = None
        self.last_timestamp = None

    def request(self, operation, args, session, sequence, node=1):
        opcode = OPERATIONS[operation]
        payload = b''
        if opcode == Opcode.HELLO:
            payload = self.schema_hash
        elif opcode in (Opcode.PREPARE, Opcode.APPLY, Opcode.FINISH):
            payload = uuid.UUID(args['token']).bytes
            if not any(payload):
                raise ValueError('Command token toàn 0 được dành riêng cho chưa hoàn thành.')
            if opcode == Opcode.APPLY:
                case = args.get('case', '').encode('utf-8')
                actions = args.get('actions', [])
                if len(case) > 63 or len(actions) > MAX_SIGNALS:
                    raise ValueError('Quá dài case/actions A45.')
                payload += bytes([len(case)]) + case + struct.pack('>H', len(actions))
                seen = set()
                for action in actions:
                    sid, value = action['signal'], action['value']
                    if sid not in self.outputs or sid in seen or not math.isfinite(value):
                        raise ValueError('Action sai kênh/giá trị hoặc trùng kênh.')
                    seen.add(sid)
                    payload += struct.pack('>Hd', self.mapping[sid], value)
        frame = Frame(node, int(opcode), 0, session, sequence, payload)
        encode_frame(frame)
        return frame

    def decode_request(self, frame):
        if frame.flags != 0 or frame.opcode not in OPERATIONS.values():
            raise ValueError('Không phải yêu cầu A45 được hỗ trợ.')
        reader = _Reader(frame.payload)
        result = {}
        if frame.opcode == Opcode.HELLO:
            if reader.take(16) != self.schema_hash:
                raise ValueError('Sai schema hash; PC và firmware khác ánh xạ kênh.')
        elif frame.opcode in (Opcode.PREPARE, Opcode.APPLY, Opcode.FINISH):
            result['token'] = str(uuid.UUID(bytes=reader.take(16)))
            if uuid.UUID(result['token']).int == 0:
                raise ValueError('Command token không được toàn 0.')
            if frame.opcode == Opcode.APPLY:
                size = reader.take(1)[0]
                if size > 63:
                    raise ValueError('Case quá dài.')
                result['case'] = reader.take(size).decode('utf-8')
                count, = reader.unpack('>H')
                if count > MAX_SIGNALS:
                    raise ValueError('Quá nhiều action.')
                result['actions'] = []
                seen = set()
                for _ in range(count):
                    wire_id, value = reader.unpack('>Hd')
                    sid = self.reverse.get(wire_id)
                    if sid not in self.outputs or sid in seen or not math.isfinite(value):
                        raise ValueError('Action sai kênh/giá trị hoặc trùng kênh.')
                    seen.add(sid)
                    result['actions'].append(dict(signal=sid, value=value))
        reader.finish()
        return next(key for key, value in OPERATIONS.items() if value == frame.opcode), result

    def response(self, request, payload=None, error=None):
        payload = payload or {}
        if error is not None:
            data = struct.pack('>H', int(error))
        elif request.opcode == Opcode.HELLO:
            data = struct.pack('>4sI16sH', b'A45C', payload['boot_id'], self.schema_hash,
                               int(payload.get('simulation', False)))
        elif request.opcode == Opcode.SNAPSHOT:
            values = payload['values']
            if len(values) > MAX_SIGNALS:
                raise ValueError('Quá nhiều mẫu.')
            token = uuid.UUID(payload['confirmed']).bytes if payload.get('confirmed') else bytes(16)
            data = struct.pack('>IIII16sH', payload['boot_id'], payload['sample_seq'],
                               payload['uptime_ms'], payload['age_ms'], token, len(values))
            for sid, value in values.items():
                quality = payload.get('qualities', {}).get(sid, 0)
                if quality not in QUALITY or not math.isfinite(value):
                    raise ValueError('Chất lượng/giá trị mẫu không hợp lệ.')
                data += struct.pack('>HBd', self.mapping[sid], quality, value)
        else:
            data = request.payload[:16] + b'\x01'
        return encode_frame(Frame(request.node, request.opcode, 3 if error is not None else 1,
                                  request.session, request.sequence, data))

    def decode_response(self, raw, request, now=None, sent_at=None):
        now = time.monotonic() if now is None else now
        frame = decode_frame(raw)
        if ((frame.node, frame.opcode, frame.session, frame.sequence)
                != (request.node, request.opcode, request.session, request.sequence)
                or frame.flags not in (1, 3)):
            raise ValueError('Phản hồi sai node/lệnh/session/sequence A45.')
        reader = _Reader(frame.payload)
        if frame.flags == 3:
            code, = reader.unpack('>H')
            reader.finish()
            raise ValueError(f'Trung tâm từ chối lệnh A45, mã lỗi {code}.')
        if frame.opcode == Opcode.HELLO:
            product, boot, schema, capabilities = reader.unpack('>4sI16sH')
            if product != b'A45C' or schema != self.schema_hash or not boot or capabilities & ~1:
                raise ValueError('Nhận diện/schema/capabilities A45 không tương thích.')
            result = dict(connected=True, boot_id=boot, simulation=bool(capabilities & 1))
        elif frame.opcode == Opcode.SNAPSHOT:
            boot, sample, uptime, age, token, count = reader.unpack('>IIII16sH')
            if boot != self.boot_id or not sample or count > MAX_SIGNALS:
                raise ValueError('Thiết bị khởi động lại hoặc header mẫu không hợp lệ; kết nối lại.')
            values, qualities = {}, {}
            for _ in range(count):
                wire_id, quality, value = reader.unpack('>HBd')
                sid = self.reverse.get(wire_id)
                if sid is None or sid in values or quality not in QUALITY or not math.isfinite(value):
                    raise ValueError('Mẫu sai kênh/chất lượng/giá trị hoặc trùng kênh.')
                values[sid], qualities[sid] = value, QUALITY[quality]
            # Conservatively include the whole transaction time. MCU and PC
            # clocks are unrelated; receiving cached bytes never makes them new.
            timestamp = (min(now, sent_at) if sent_at is not None else now) - age / 1000
            if self.last_sample is not None:
                delta = (sample - self.last_sample) & 0xFFFFFFFF
                if delta >= 0x80000000:
                    raise ValueError('Số thứ tự mẫu đi lùi.')
                if delta == 0:
                    timestamp = min(timestamp, self.last_timestamp)
            result = dict(values=values, qualities=qualities, confirmed=str(uuid.UUID(bytes=token))
                          if any(token) else None, timestamp=timestamp, boot_id=boot,
                          sample_seq=sample, uptime_ms=uptime, source='mock' if self.simulation else 'device')
        else:
            token, accepted = reader.unpack('>16sB')
            if token != request.payload[:16] or accepted != 1:
                raise ValueError('ACK không khớp command token.')
            result = {'accepted': True}
        reader.finish()
        # Only validated packets may mutate the protocol session's state.
        if frame.opcode == Opcode.HELLO:
            self.boot_id, self.simulation = result['boot_id'], result['simulation']
            self.last_sample = self.last_timestamp = None
        elif frame.opcode == Opcode.SNAPSHOT:
            self.last_sample, self.last_timestamp = result['sample_seq'], result['timestamp']
        return result


def make_read_unit(slave, function, address, count):
    """Read-only diagnostics. Addresses are PDU offsets (zero-based)."""
    for value, lower, upper, label in (
        (slave, 1, 247, 'Slave ID'),
        (address, 0, 65535, 'Địa chỉ zero-based'),
        (count, 1, 125, 'Số thanh ghi'),
    ):
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f'{label} phải từ {lower} đến {upper}.')
    if type(function) is not int or function not in (3, 4):
        raise ValueError('Chỉ hỗ trợ đọc FC03/FC04.')
    if address + count > 65536:
        raise ValueError('Vùng đọc vượt quá địa chỉ 65535.')
    kind = QModbusDataUnit.HoldingRegisters if function == 3 else QModbusDataUnit.InputRegisters
    return QModbusDataUnit(kind, address, count)


def crc16_modbus(data):
    """Modbus RTU CRC16 (poly 0xA001, init 0xFFFF); sent low byte first."""
    crc = 0xFFFF
    for byte in bytes(data):
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def rtu_adu(slave, pdu):
    """Slave ID + PDU (function code + data, big-endian words) + CRC16 (Lo, Hi)."""
    body = bytes([slave]) + bytes(pdu)
    return body + struct.pack('<H', crc16_modbus(body))


def split_rtu_adu(raw):
    """(slave, pdu) of a complete RTU frame; ValueError on short frame or bad CRC."""
    raw = bytes(raw)
    if len(raw) < 4:
        raise ValueError('Khung RTU quá ngắn.')
    if struct.unpack('<H', raw[-2:])[0] != crc16_modbus(raw[:-2]):
        raise ValueError('Sai CRC16.')
    return raw[0], raw[1:-2]


def rtu_request_pdu(function, address, values=None, count=None):
    """PDU a Modbus master sends: FC03/FC04 read, FC06 single write, FC16 multiple write."""
    if function in (3, 4):
        return struct.pack('>BHH', function, address, count)
    if function == 6:
        return struct.pack('>BHH', 6, address, values[0])
    return struct.pack('>BHHB', 16, address, len(values), 2 * len(values)) + struct.pack(f'>{len(values)}H', *values)


def decode_snapshot(payload, known_signals):
    """Adapter boundary: reject malformed/non-finite data before UI/evaluation."""
    if not isinstance(payload, dict) or not isinstance(payload.get("values"), dict):
        raise ValueError("Phản hồi thiếu values")
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
        raise ValueError("Thời điểm mẫu không hợp lệ")
    result = {}
    for sid, value in payload["values"].items():
        if sid not in known_signals:
            raise ValueError(f"Tín hiệu lạ: {sid}")
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Giá trị không hợp lệ: {sid}")
        quality = payload.get('qualities', {}).get(sid, 'valid')
        if quality not in QUALITY.values():
            raise ValueError(f'Chất lượng không hợp lệ: {sid}')
        result[sid] = Sample(value, timestamp, quality, payload.get('source', 'mock'))
    return result


