"""STM32 CPU USART2 contracts. Indices are zero-based Modbus PDU addresses.

Keep the two banks independent, just like Modbus_DO and Modbus_DI in C.
Changing one bank must never shift or alias the other bank.

Two firmware register maps exist (read from the firmware sources):
- CPUv1.0: DO 29 words (index 18 = CDT), DI 30 words.
- CPUv1.1 "For DK_QDT": index 18–19 = Matrix[0..1] (forwarded to the
  signal-relay matrix board, ID 6), CDT moved to index 20, four UART receive
  buffers DataR1..DataR4 in DI 20–42. Slave ID = 8 + board ID switch.
A profile selects its map with ``hardware.cpu_map``; CPUv1.0 is the default.
The IntEnums below describe CPUv1.0 and stay for code written against it.
"""
from dataclasses import dataclass, field
from enum import IntEnum


DEFAULT_SLAVE = 9
DEFAULT_BAUDRATE = 115200
READ_STALE_MS = 2000  # PC display policy, NOT the age of an MCU ADC conversion.


class WriteRegister(IntEnum):
    Null = 0
    Mode = 1
    Plan = 2
    Block = 3
    Cabinet = 4
    Status = 5
    DisplayOut = 6
    DAC_val = 7
    DOUT = 8
    SW01 = 9
    SW02 = 10
    MUX = 11
    Power = 12
    DataO1 = 13
    DataO2 = 14
    DataO3 = 15
    DataO4 = 16
    DataO5 = 17
    CDT = 18
    DataT0 = 19
    DataT1 = 20
    DataT2 = 21
    DataT3 = 22
    DataT4 = 23
    DataT5 = 24
    DataT6 = 25
    DataT7 = 26
    DataT8 = 27
    DataT9 = 28


class ReadRegister(IntEnum):
    Null = 0
    Mode = 1
    Plan = 2
    Block = 3
    Cabinet = 4
    Status = 5
    DisplayIN = 6
    ADC0_val = 7
    ADC1_val = 8
    ADC2_val = 9
    ADC3_val = 10
    ADC4_val = 11
    Ohm_val = 12
    DIN = 13
    DataI1 = 14
    DataI2 = 15
    DataI3 = 16
    DataI4 = 17
    DataI5 = 18
    CDN = 19
    DataR0 = 20
    DataR1 = 21
    DataR2 = 22
    DataR3 = 23
    DataR4 = 24
    DataR5 = 25
    DataR6 = 26
    DataR7 = 27
    DataR8 = 28
    DataR9 = 29


WRITE_COUNT = len(WriteRegister)
READ_COUNT = len(ReadRegister)

# Test-runner I/O map (hardware.stm32_io). A mapping is 'assumed' until checked
# on the real bench; 'unsupported' means the hardware cannot drive/measure it.
IO_STATUSES = ('verified', 'assumed', 'unsupported')
# Registers the test runner may own (CPUv1.0). DataO1/DataO2 (self-clearing
# encoder command), DataO3 (SSI re-muxes UART pins), CDT/DataT (repeating UART
# send) and Null are never written by the runner.
BENCH_WRITABLE = frozenset({
    WriteRegister.Mode, WriteRegister.Plan, WriteRegister.Block, WriteRegister.Cabinet,
    WriteRegister.Status, WriteRegister.DisplayOut, WriteRegister.DAC_val, WriteRegister.DOUT,
    WriteRegister.SW01, WriteRegister.SW02, WriteRegister.MUX, WriteRegister.Power,
    WriteRegister.DataO4, WriteRegister.DataO5,
})


@dataclass(frozen=True)
class CpuMap:
    """One firmware's register layout. ``write_names[i]`` names DO index i.

    ``array_words``: size of mod_buf_to_write/mod_buf_to_read in the firmware
    (room for registers a profile proposes as a firmware extension).
    ``uart_buffers``: DI receive buffers {name: (first index, words)}.
    ``forwards``: what the CPU main loop sends to its own sub-boards every
    pass, in order: ((CPU registers), board, sub-board slave ID, frames).
    The PC never talks to these boards; an absent one costs one master
    timeout (``t_timeout`` = 100 ms) per frame per loop.
    """
    name: str
    write_names: tuple
    read_names: tuple
    bench_writable: frozenset
    array_words: int
    uart_buffers: tuple  # ((name, first, words), ...)
    notes: str = ''
    forwards: tuple = ()
    _write_index: dict = field(default=None, compare=False, repr=False)
    _read_index: dict = field(default=None, compare=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, '_write_index', {n: i for i, n in enumerate(self.write_names)})
        object.__setattr__(self, '_read_index', {n: i for i, n in enumerate(self.read_names)})

    @property
    def write_count(self):
        return len(self.write_names)

    @property
    def read_count(self):
        return len(self.read_names)

    def write_index(self, name):
        """DO index of a register name; KeyError if this firmware lacks it."""
        return self._write_index[name]

    def read_index(self, name):
        return self._read_index[name]

    def has_write(self, name):
        return name in self._write_index

    def has_read(self, name):
        return name in self._read_index


_COMMON_DO = tuple(r.name for r in WriteRegister)[:WriteRegister.CDT]  # Null … DataO5 (0–17)
_COMMON_DI = tuple(r.name for r in ReadRegister)[:ReadRegister.DataR0]  # Null … CDN (0–19)
_BENCH = frozenset(r.name for r in BENCH_WRITABLE)

CPU_V10 = CpuMap(
    name='CPUv1.0',
    write_names=tuple(r.name for r in WriteRegister),
    read_names=tuple(r.name for r in ReadRegister),
    bench_writable=_BENCH,
    array_words=32,
    uart_buffers=(('DataR', 20, 10),),
    notes='Giá thử cũ: SW01/SW02 → bo switch ID 1, MUX → ID 2, Power → ID 3.',
    forwards=(((), 'bo HMI (đèn LED)', 4, 1), (('SW01', 'SW02'), 'bo switch', 1, 2),
              (('MUX',), 'RLMUX', 2, 1), (('Power',), 'RLPW', 3, 1)),
)

CPU_V11 = CpuMap(
    name='CPUv1.1',
    write_names=_COMMON_DO + ('Matrix0', 'Matrix1', 'CDT') + tuple(f'DataT{i}' for i in range(10)),
    read_names=_COMMON_DI + tuple(f'DataR1_{i}' for i in range(5)) + tuple(f'DataR2_{i}' for i in range(5))
    + tuple(f'DataR3_{i}' for i in range(8)) + tuple(f'DataR4_{i}' for i in range(5)),
    bench_writable=_BENCH | {'Matrix0', 'Matrix1'},
    array_words=50,
    uart_buffers=(('DataR1', 20, 5), ('DataR2', 25, 5), ('DataR3', 30, 8), ('DataR4', 38, 5)),
    notes=('CPUv1.1 For DK_QDT: Matrix[0..1] (index 18–19) → bo matrix ID 6 (FC16 reg 0–1); CDT ở index 20; '
           'slave = 8 + công tắc ID trên bo.'),
    # main.c vòng while(1), Mode = 1: HMI → SW ×2 → Matrix → MUX → Power, mỗi khung chờ tối đa 100 ms + Delay 10 ms.
    forwards=(((), 'bo HMI (đèn LED)', 4, 1), (('SW01', 'SW02'), 'bo switch', 1, 2),
              (('Matrix0', 'Matrix1'), 'RLMatrix', 6, 1), (('MUX',), 'RLMUX', 2, 1), (('Power',), 'RLPW', 3, 1)),
)

CPU_MAPS = {m.name: m for m in (CPU_V10, CPU_V11)}
DEFAULT_CPU_MAP = CPU_V10


def cpu_map_for(hardware):
    """Register map a profile's hardware.json selects (default CPUv1.0)."""
    name = (hardware or {}).get('cpu_map', DEFAULT_CPU_MAP.name)
    if name not in CPU_MAPS:
        raise ValueError(f'cpu_map không hỗ trợ: {name} (có: {", ".join(CPU_MAPS)})')
    return CPU_MAPS[name]


@dataclass
class Stm32RegisterBanks:
    # Raw uint16 storage: signed conversion belongs to protocol.py.
    cpu_map: CpuMap = DEFAULT_CPU_MAP
    mod_buf_to_write: list = None
    mod_buf_to_read: list = None
    staged: set = field(default_factory=set)
    source: object = None  # (simulation, slave); never mix two devices' data.
    read_valid: bool = False
    received_at: float = 0.0
    last_ack: object = None  # Receipt of captured request, not output state.
    # Last RTU frames per source {simulation: {'TX': bytes, 'RX': bytes}},
    # rebuilt from the PDU with a recomputed CRC (Qt hides raw bytes).
    frames: dict = field(default_factory=dict)
    message: str = 'Chưa đọc STM32; mảng ghi chỉ là bản nháp.'

    def __post_init__(self):
        if self.mod_buf_to_write is None:
            self.mod_buf_to_write = [0] * self.cpu_map.write_count
        if self.mod_buf_to_read is None:
            self.mod_buf_to_read = [0] * self.cpu_map.read_count

    def invalidate(self):
        self.read_valid = False
        self.received_at = 0.0
        self.last_ack = None
