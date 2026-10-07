#!/usr/bin/env python3
"""Build a patched Nikon D3 B firmware (BD3_0203.bin, v2.03).

  python3 tools/patch_d3.py D3Update/BD3_0203.bin build/BD3_0203.bin --shutter-count

Image: file offset 0 = address 0x40000, Fujitsu FR, big-endian.
Trailer: CRC16-CCITT/XMODEM over everything before the last 2 bytes (tools/d3crc.py).
See NOTES.md for the analysis behind every address used here.
"""
import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from fr_asm import assemble          # noqa: E402
from d3crc import crc16              # noqa: E402

BASE = 0x40000
STOCK_SHA = '982bee9e27582fed9cdbf80234e9190a0b39b47b37cc623433266ed33c9c3575'

# Code cave: linker gap of 0xff between data ending 0x28edbc and the .data
# init image at 0x2966fc. Nothing references it.
CAVE = 0x28edc0
CAVE_END = 0x28fdd0

# Firmware version screen 0x23f9cc (draws "A 2.03" at 109,99 and "B 2.03" at 109,127,
# optional "S..." line at y=155). Hook its epilogue, after all lines are drawn.
VER_HOOK = 0x23fb86        # ldi:32 0x871b2a41,r0 ; borl 0x8,@r0   (8 bytes)
VER_HOOK_ORIG = bytes.fromhex('9f80871b2a419080')
VER_RET = 0x23fb8e

SPRINTF = 0x1c1bb4         # sprintf(r4 buf, r5 fmt, r6, r7, ...)
DRAW_TEXT = 0x165106       # draw_text(r4 scratch, r5 style, r6 x, r7 y, [sp]=str, [sp+4]=flag)
SHOTS = 0x871b057a         # shutter count, big-endian u32 (unaligned), sub-CPU comm item 0x1b + 0xa


def shutter_count_cave():
    """Version screen: add a 'Shots <n>' line under the A/B/S lines (x=109, y=183)."""
    return [
        "shots",
        # r6 = BE u32 at SHOTS (byte reads: the address is not word aligned)
        ("ldi32", SHOTS, 1),
        ("ldub", 1, 6),
        ("addi", 1, 1), ("ldub", 1, 0), ("lsl", 8, 6), ("or", 0, 6),
        ("addi", 1, 1), ("ldub", 1, 0), ("lsl", 8, 6), ("or", 0, 6),
        ("addi", 1, 1), ("ldub", 1, 0), ("lsl", 8, 6), ("or", 0, 6),
        # sprintf(r14-0x40, fmt, count): the A/B line buffers, already drawn
        ("ldi8", 0xc0, 4), ("extsb", 4), ("add", 14, 4),
        ("ldi32", "fmt_n", 5),
        ("cmpi", 0, 6),
        ("bne", "fmt_ok"),
        ("ldi32", "fmt_none", 5),      # 0 = no shot reported by the sub-CPU yet
        "fmt_ok",
        ("ldi32", SPRINTF, 12), ("call_r", 12),
        # draw_text(r14-12, 7, 109, 183, r14-0x40, 1), same style as the version digits
        ("mov", 14, 4), ("addi", -12, 4),
        ("ldi8", 7, 5), ("ldi8", 0x6d, 6), ("ldi8", 0xb7, 7),
        ("ldi8", 0xc0, 0), ("extsb", 0), ("add", 14, 0),
        ("raw", "1300"),               # st r0,@(r15,0)
        ("ldi8", 1, 0),
        ("raw", "1310"),               # st r0,@(r15,4)
        ("ldi32", DRAW_TEXT, 12), ("call_r", 12),
        # displaced instructions, then back
        ("ldi32", 0x871b2a41, 0),
        ("raw", "9080"),               # borl 0x8,@r0
        ("ldi32", VER_RET, 12), ("jmp_r", 12),
        ("align", 4),
        "fmt_n", ("bytes", b"Shots %d\0"),
        ("align", 2),
        "fmt_none", ("bytes", b"Shots --\0"),
        ("align", 2),
    ]


# Picture Control table: 7 x (record*, colour table*): STANDARD, NEUTRAL, VIVID, then the
# 4 optional slots in runtime flash 0x7c0000-0x7f0000 (filled from .NOP files by the menu).
# A slot is empty when its record's first u16 (the id) is 0xffff. Everything reads through
# this table (list build 0x1b2580/0x1b260e, id lookups 0x1b2854/0x1b28a6).
PC_TABLE = 0x204f8c
NOP_REC = 0x358            # record size (same layout as the built-in records)
NOP_TAB = 0x7790           # colour table size
NOP_LEN = 8 + NOP_REC + NOP_TAB + 2
# Embedded copies go in the 0xff tail of the image (0x579ad3-0x73fffe). Only firmware
# updates write there; all runtime flash writes are >= 0x740000.
D2X_BASE = [0x6a0000, 0x6a8000, 0x6b0000]


def load_nop(path):
    d = open(path, 'rb').read()
    if len(d) != NOP_LEN or d[:8] != b'NOP\0\0\x01\0\x01':
        sys.exit(f'{path}: not a D3 .NOP file')
    if crc16(d[:-2]) != int.from_bytes(d[-2:], 'big'):
        sys.exit(f'{path}: bad CRC')
    return d[8:8 + NOP_REC], d[8 + NOP_REC:-2]


def put(img, addr, data, expect=None):
    o = addr - BASE
    if expect is not None and bytes(img[o:o + len(expect)]) != expect:
        sys.exit(f'unexpected bytes at {addr:#x}: {img[o:o + len(expect)].hex()}')
    img[o:o + len(data)] = data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--shutter-count', action='store_true',
                    help='show the shutter count on the Firmware version screen')
    ap.add_argument('--d2x', metavar='DIR',
                    help='build D2X MODE 1-3 (DIR/D3____M{1,2,3}.NOP) into optional slots 1-3')
    a = ap.parse_args()

    img = bytearray(open(a.src, 'rb').read())
    if hashlib.sha256(img).hexdigest() != STOCK_SHA:
        sys.exit('source is not the stock BD3_0203.bin')

    src = []
    if a.shutter_count:
        src += shutter_count_cave()
    if src:
        code, labels = assemble(src, CAVE)
        assert CAVE + len(code) <= CAVE_END
        put(img, CAVE, code, expect=b'\xff' * len(code))
        print(f'cave {CAVE:#x}-{CAVE + len(code):#x} ({len(code)} B)')
    if a.shutter_count:
        hook, _ = assemble([("ldi32", labels["shots"], 12), ("jmp_r", 12)], VER_HOOK)
        put(img, VER_HOOK, hook, expect=VER_HOOK_ORIG)
    if a.d2x:
        for n, base in enumerate(D2X_BASE, 1):
            rec, tab = load_nop(os.path.join(a.d2x, f'D3____M{n}.NOP'))
            # same layout as a real slot: record, table at +0x358, 0xaa55 marker at +0x7ae8
            blob = rec + tab + b'\xaa\x55'
            put(img, base, blob, expect=b'\xff' * len(blob))
            slot = PC_TABLE + 8 * (2 + n)
            orig = (0x7c0000 + 0x10000 * (n - 1)).to_bytes(4, 'big')
            put(img, slot, base.to_bytes(4, 'big') + (base + NOP_REC).to_bytes(4, 'big'),
                expect=orig + (int.from_bytes(orig, 'big') + NOP_REC).to_bytes(4, 'big'))
            name = rec[2:22].split(b'\0')[0].decode()
            print(f'slot {n}: {name} (id {int.from_bytes(rec[:2], "big"):#06x}) at {base:#x}')

    img[-2:] = crc16(img[:-2]).to_bytes(2, 'big')
    os.makedirs(os.path.dirname(a.dst) or '.', exist_ok=True)
    open(a.dst, 'wb').write(img)
    print(f'{a.dst}: CRC {int.from_bytes(img[-2:], "big"):#06x}  '
          f'SHA-256 {hashlib.sha256(img).hexdigest()}')


if __name__ == '__main__':
    main()
