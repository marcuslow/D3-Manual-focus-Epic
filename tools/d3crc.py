#!/usr/bin/env python3
"""Check or fix the trailing CRC of a Nikon D3 firmware file (AD3_xxxx.bin / BD3_xxxx.bin).

The last 2 bytes are CRC16-CCITT/XMODEM (poly 0x1021, init 0, no reflection,
no xor-out) over everything before them, stored big-endian.

  d3crc.py FILE          check
  d3crc.py --fix FILE    rewrite the last 2 bytes in place
"""
import sys

TABLE = []
for i in range(256):
    c = i << 8
    for _ in range(8):
        c = ((c << 1) ^ 0x1021) if c & 0x8000 else (c << 1)
    TABLE.append(c & 0xFFFF)


def crc16(data):
    crc = 0
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ TABLE[((crc >> 8) ^ b) & 0xFF]
    return crc


def main():
    args = sys.argv[1:]
    fix = '--fix' in args
    args = [a for a in args if a != '--fix']
    if len(args) != 1:
        sys.exit(__doc__)
    path = args[0]
    d = bytearray(open(path, 'rb').read())
    want = crc16(d[:-2])
    have = int.from_bytes(d[-2:], 'big')
    if have == want:
        print(f'{path}: CRC OK 0x{have:04x}')
        return
    if not fix:
        print(f'{path}: CRC BAD stored 0x{have:04x}, computed 0x{want:04x}')
        sys.exit(1)
    d[-2:] = want.to_bytes(2, 'big')
    open(path, 'wb').write(d)
    print(f'{path}: CRC fixed 0x{have:04x} -> 0x{want:04x}')


if __name__ == '__main__':
    main()
