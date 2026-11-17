"""CPUv1.0 USART2 contract. Indices are zero-based Modbus PDU addresses.

Keep these two layouts independent, just like Modbus_DO and Modbus_DI in C.
Changing one bank must never shift or alias the other bank.
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
# on the real bench; 'unsupported' means CPUv1.0 cannot drive/measure it.
IO_STATUSES = ('verified', 'assumed', 'unsupported')
# Registers the test runner may own. DataO1/DataO2 (self-clearing encoder
# command), DataO3 (SSI re-muxes UART pins), CDT/DataT (repeating UART send)
# and Null are never written by the runner.
BENCH_WRITABLE = frozenset({
    WriteRegister.Mode, WriteRegister.Plan, WriteRegister.Block, WriteRegister.Cabinet,
    WriteRegister.Status, WriteRegister.DisplayOut, WriteRegister.DAC_val, WriteRegister.DOUT,
    WriteRegister.SW01, WriteRegister.SW02, WriteRegister.MUX, WriteRegister.Power,
    WriteRegister.DataO4, WriteRegister.DataO5,
})


@dataclass
class Stm32RegisterBanks:
    # Raw uint16 storage: signed conversion belongs to protocol.py.
    mod_buf_to_write: list = field(default_factory=lambda: [0] * WRITE_COUNT)
    mod_buf_to_read: list = field(default_factory=lambda: [0] * READ_COUNT)
    staged: set = field(default_factory=set)
    source: object = None  # (simulation, slave); never mix two devices' data.
    read_valid: bool = False
    received_at: float = 0.0
    last_ack: object = None  # Receipt of captured request, not output state.
    message: str = 'Chưa đọc STM32; mảng ghi chỉ là bản nháp.'

    def invalidate(self):
        self.read_valid = False
        self.received_at = 0.0
        self.last_ack = None

