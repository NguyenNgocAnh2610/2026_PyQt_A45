"""A45 v1 wire constants shared by codec, simulator and adapters."""
from enum import IntEnum

MAGIC = b'\xa5\x5a'
VERSION = 1
MAX_PAYLOAD = 1024
MAX_FRAME = 16 + MAX_PAYLOAD + 2
MAX_SIGNALS = 80
REQUEST_MAILBOX = 0x1000
RESPONSE_MAILBOX = 0x2000
COMMIT_REGISTER = 0x0FFF
MAILBOX_REGISTERS = 1 + (MAX_FRAME + 1) // 2
MODBUS_WRITE_CHUNK = 123
MODBUS_READ_CHUNK = 125


class Opcode(IntEnum):
    HELLO = 1
    SNAPSHOT = 2
    PREPARE = 16
    APPLY = 17
    FINISH = 18


class WireError(IntEnum):
    BAD_PAYLOAD = 1
    SESSION = 2
    CONFLICT = 3
    BUSY = 4
    UNSUPPORTED = 5


OPERATIONS = {'connect': Opcode.HELLO, 'snapshot': Opcode.SNAPSHOT,
              'prepare': Opcode.PREPARE, 'apply': Opcode.APPLY, 'finish': Opcode.FINISH}
QUALITY = {0: 'valid', 1: 'unknown', 2: 'stale', 3: 'error'}
