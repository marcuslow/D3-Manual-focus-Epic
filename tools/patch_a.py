#!/usr/bin/env python3
"""Build a patched Nikon D3 A (sub-CPU) firmware (AD3_0203.bin, v2.03).

  python3 tools/patch_a.py D3Update/AD3_0203.bin build/AD3_0203.bin --trap-focus

Image: file offset 0 = address 0x80000 (0x80000 bytes), Fujitsu FR, big-endian, then a
CRC16-CCITT/XMODEM trailer (tools/d3crc.py). The main CPU's updater wants exactly 0x80002 B.
See NOTES.md section 9 for the analysis behind every address used here.
"""
import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from fr_asm import assemble          # noqa: E402
from d3crc import crc16              # noqa: E402

BASE = 0x80000
STOCK_SHA = 'afc28972c292e42652aa47e49b18e37631c9cbc2de20c1e242fad1cadb920e52'

# Code cave: 0xff gap at the end of the code/constant sector 0xf0000-0xf3fff, before the
# boot validity marker at 0xf2ff8 (compared with 0xffbf8 by 0xf8060 at reset; never touch).
# Do NOT use 0xf4000-0xf7fff (runtime data sector, copied to RAM 0x42000 by 0x857f8) or
# 0xf8000-0xfbfff (boot / flash-writer sector).
CAVE = 0xf2d10
CAVE_END = 0xf2ff8

# Release decision 0x9aa8c runs every tick while the shutter button is held. Its
# focus-priority block starts at 0x9b3d8; the hold exit 0x9b4d6 (reason 0x3e) refuses
# the release this tick, and the next tick asks again (how AF lenses wait for focus).
HOLD_HOOK = 0x9b3d8        # ldi:20 0x3f6ba,r12 ; ldub @r12,r0   (6 bytes)
HOLD_HOOK_ORIG = bytes.fromhex('9b3cf6ba06c0')
HOLD_CONT = 0x9b3de        # cmp 0x3,r0 (r0 = release mode)
HOLD_EXIT = 0x9b4d6

RELEASE_MODE = 0x3f6ba     # 0..2 assumed S / CL / CH
FOCUS_MODE = 0x3f6bd       # bits 1:0: effective mode 0 M, 1 AF-S, 2 AF-C (a non-CPU lens
                           # reads 0 even with the selector on S: test shots DSC_9912-9917)
AF_REQUEST = 0x3f6d7       # low nibble 0 with the selector on M, non-zero on S (item 38
                           # byte0 bit6: 0x08 on M vs 0x4c on S, DSC_9916/9917)
AF_PRIO = 0x3f874          # bit 5 = a2 AF-S priority: 0 Focus, 1 Release
VF_FOCUS = 0x3fa21         # viewfinder focus indicator: 1 = in focus (green dot)


def trap_focus_cave():
    """Manual focus (effective mode M) + a2 = Focus + S/CL/CH: hold the release until the
    viewfinder focus dot is lit. a2 = Release turns it off (stock behaviour).
    The selector position can't be told apart for a non-CPU lens (effective mode reads M on
    S too, DSC_9912-9928), so a2 is the switch. Probe build A 2.05 proved the hook at
    0x9b3d8 sees every release (it blocked M and S)."""
    return [
        "trap",
        ("ldi20", RELEASE_MODE, 12), ("ldub", 12, 0),
        ("cmpi", 2, 0), ("bhi", "stock"),
        ("ldi20", FOCUS_MODE, 12), ("ldub", 12, 0), ("ldi8", 3, 1), ("and", 1, 0),
        ("cmpi", 0, 0), ("bne", "stock"),             # AF active: Nikon's own hold
        ("ldi20", AF_PRIO, 12), ("ldub", 12, 0), ("ldi8", 0x20, 1), ("and", 1, 0),
        ("cmpi", 0, 0), ("bne", "stock"),             # a2 = Release: fire as usual
        ("ldi20", VF_FOCUS, 12), ("ldub", 12, 0),
        ("cmpi", 1, 0), ("beq", "stock"),             # green dot lit: fire
        ("ldi20", HOLD_EXIT, 12), ("jmp_r", 12),      # not in focus: Nikon's hold
        "stock",                                      # displaced code, then back
        ("ldi20", RELEASE_MODE, 12), ("ldub", 12, 0),
        ("ldi20", HOLD_CONT, 12), ("jmp_r", 12),
    ]


# --trap-debug: item 38 (lens info, sub -> main, captured into every NEF's ShotInfo at 0x3e3)
# carries lens-data copies that are blank for a non-CPU lens. Bytes 2..7 and 9..15 are
# re-pointed at candidate state bytes (byte 1 and byte 8 = lens ID stay stock), and the hook
# counts its entries at DBG (item-61 receive buffer 0x405cc.., never read by the sub-CPU).
# Decode with: tools/trap_debug.py FILE.NEF
DBG = 0x40600
ITEM38_COPY = {k: (0x9fbb6 + 12 * (k - 2), src) for k, src in
               zip(range(2, 8), (0x3f6db, 0x3f6dc, 0x3f6dd, 0x3f6df, 0x3f6e1, 0x3f6e2))}
ITEM38_COPY.update({k: (0x9fc0a + 12 * (k - 9), 0x3f6e5 + k - 9) for k in range(9, 16)})
DEBUG_MAP = {2: DBG, 3: FOCUS_MODE, 4: 0x457e5, 5: 0x457e6, 6: 0x457e7, 7: 0x457e9,
             9: 0x45850, 10: 0x45851, 11: 0x45852, 12: 0x45853, 13: 0x3fa16, 14: VF_FOCUS,
             15: AF_PRIO}


def debug_prologue():
    """DBG = hook entry counter (wraps at 256)."""
    return [("ldi20", DBG, 1), ("ldub", 1, 0), ("addi", 1, 0), ("stb", 0, 1)]


def trap_probe_cave():
    """Experiment: hold EVERY release the hook sees (release mode <= 2, a2 = Focus).
    If the camera then never fires, the hook is on the release path. a2 = Release escapes."""
    return [
        "trap",
        ("ldi20", RELEASE_MODE, 12), ("ldub", 12, 0),
        ("cmpi", 2, 0), ("bhi", "stock"),
        ("ldi20", AF_PRIO, 12), ("ldub", 12, 0), ("ldi8", 0x20, 1), ("and", 1, 0),
        ("cmpi", 0, 0), ("bne", "stock"),
        ("ldi20", HOLD_EXIT, 12), ("jmp_r", 12),
        "stock",
        ("ldi20", RELEASE_MODE, 12), ("ldub", 12, 0),
        ("ldi20", HOLD_CONT, 12), ("jmp_r", 12),
    ]


def put(img, addr, data, expect=None):
    o = addr - BASE
    if expect is not None and bytes(img[o:o + len(expect)]) != expect:
        sys.exit(f'unexpected bytes at {addr:#x}: {img[o:o + len(expect)].hex()}')
    img[o:o + len(data)] = data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--trap-focus', action='store_true',
                    help='manual focus + a2 = Focus: hold the shutter until focus is confirmed, then fire')
    ap.add_argument('--trap-debug', action='store_true',
                    help='with --trap-focus: record the hook inputs into every NEF (item 38)')
    ap.add_argument('--trap-probe', action='store_true',
                    help='experiment: hold every release the hook sees (a2 = Release escapes)')
    ap.add_argument('--version', metavar='X.YY',
                    help='report this A version (header bytes 0x80000/1, BCD-ish as stock 02 03); '
                         'shows on the Firmware version screen and in every NEF (ShotInfo 0x321)')
    a = ap.parse_args()

    img = bytearray(open(a.src, 'rb').read())
    if hashlib.sha256(img).hexdigest() != STOCK_SHA:
        sys.exit('source is not the stock AD3_0203.bin')

    if a.trap_focus or a.trap_probe:
        src = trap_probe_cave() if a.trap_probe else trap_focus_cave()
        if a.trap_debug:
            src = src[:1] + debug_prologue() + src[1:]      # right after the "trap" label
        code, labels = assemble(src, CAVE)
        assert CAVE + len(code) <= CAVE_END
        put(img, CAVE, code, expect=b'\xff' * len(code))
        hook, _ = assemble([("ldi20", labels["trap"], 12), ("jmp_r", 12)], HOLD_HOOK)
        put(img, HOLD_HOOK, hook, expect=HOLD_HOOK_ORIG)
        print(f'cave {CAVE:#x}-{CAVE + len(code):#x} ({len(code)} B), hook {HOLD_HOOK:#x}')
        if a.trap_debug:
            for k, src in DEBUG_MAP.items():
                at, orig = ITEM38_COPY[k]
                new, _ = assemble([("ldi20", src, 12)], at)
                old, _ = assemble([("ldi20", orig, 12)], at)
                put(img, at, new, expect=old)
            print('debug: item 38 bytes', ', '.join(f'{k}<-{v:#x}' for k, v in DEBUG_MAP.items()))

    if a.version:
        major, minor = a.version.split('.')
        put(img, BASE, bytes([int(major), int(minor)]), expect=b'\x02\x03')
        print(f'A version reported as {a.version} (boot marker 0xf2ff8/0xffbf8 left stock)')

    img[-2:] = crc16(img[:-2]).to_bytes(2, 'big')
    os.makedirs(os.path.dirname(a.dst) or '.', exist_ok=True)
    open(a.dst, 'wb').write(img)
    print(f'{a.dst}: CRC {int.from_bytes(img[-2:], "big"):#06x}  '
          f'SHA-256 {hashlib.sha256(img).hexdigest()}')


if __name__ == '__main__':
    main()
