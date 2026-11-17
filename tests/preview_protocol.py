"""Exercise A45 bytes without hardware: python -m tests.preview_protocol --transport uart|rtu."""
import argparse
import uuid

from src.common.profiles import load_profile
from src.common.wire import (REQUEST_MAILBOX, RESPONSE_MAILBOX, COMMIT_REGISTER,
                             MODBUS_READ_CHUNK, MODBUS_WRITE_CHUNK)
from src.protocol import WireCodec, FrameStream, encode_frame, frame_to_registers, registers_to_frame
from src.simulator import SimulatedController


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport', choices=('uart', 'rtu'), default='uart')
    args = parser.parse_args()
    profile = load_profile()
    clock = [100.0]
    controller = SimulatedController(profile, clock=lambda: clock[0])
    codec = WireCodec(profile)
    token = str(uuid.uuid4())
    operations = [('connect', {}), ('snapshot', {}), ('prepare', {'token': token}),
                  ('snapshot', {}), ('finish', {'token': str(uuid.uuid4())}), ('snapshot', {})]
    for sequence, (operation, payload) in enumerate(operations, 1):
        frame = codec.request(operation, payload, 0x11223344, sequence)
        request = encode_frame(frame)
        print(f'{operation} TX {request.hex(" ")}')
        if args.transport == 'uart':
            stream = FrameStream()
            packets = []
            for index in range(0, len(request), 7):
                packets.extend(stream.feed(request[index:index + 7]))
            response = controller.exchange(packets[0])
        else:
            words = frame_to_registers(request)
            for offset in range(0, len(words), MODBUS_WRITE_CHUNK):
                controller.write_registers(REQUEST_MAILBOX + offset, words[offset:offset + MODBUS_WRITE_CHUNK])
            controller.write_registers(COMMIT_REGISTER, [1])
            length = controller.read_registers(RESPONSE_MAILBOX, 1)[0]
            words = [length]
            total = 1 + (length + 1) // 2
            for offset in range(1, total, MODBUS_READ_CHUNK):
                words.extend(controller.read_registers(RESPONSE_MAILBOX + offset,
                             min(MODBUS_READ_CHUNK, total - offset)))
            response = registers_to_frame(words)
        print(f'{operation} RX {response.hex(" ")}')
        print(ascii(codec.decode_response(response, frame, now=clock[0])))
        clock[0] += .2


if __name__ == '__main__':
    main()
