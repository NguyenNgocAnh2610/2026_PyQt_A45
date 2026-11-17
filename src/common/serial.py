"""Explicit serial connection settings, independent of any bench recipe."""
from dataclasses import dataclass


# Editable software defaults, not claims about the attached firmware.
SERIAL_PARITY = (('Không (N)', 'N'), ('Chẵn (E)', 'E'), ('Lẻ (O)', 'O'))


@dataclass(frozen=True)
class SerialSettings:
    adapter: str
    port: str
    baudrate: int
    data_bits: int = 8
    parity: str = 'N'
    stop_bits: int = 1
    timeout_ms: int = 1000

    def __post_init__(self):
        if self.adapter not in ('uart', 'rtu'):
            raise ValueError('Chọn UART hoặc Modbus RTU.')
        if not isinstance(self.port, str) or not self.port.strip():
            raise ValueError('Hãy chọn cổng COM.')
        for value, lower, upper, label in (
            (self.baudrate, 1, 4000000, 'Baudrate'),
            (self.data_bits, 5, 8, 'Data bits'),
            (self.stop_bits, 1, 2, 'Stop bits'),
            (self.timeout_ms, 100, 10000, 'Timeout (ms)'),
        ):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f'{label} phải từ {lower} đến {upper}.')
        if self.parity not in ('N', 'E', 'O'):
            raise ValueError('Parity phải là N, E hoặc O.')
        if self.adapter == 'rtu' and self.data_bits != 8:
            raise ValueError('Modbus RTU cần 8 data bits.')

    @property
    def framing(self):
        return f'{self.data_bits}{self.parity}{self.stop_bits}'
