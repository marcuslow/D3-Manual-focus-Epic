#!/usr/bin/env python3
"""Decode the --trap-debug item-38 snapshot from D3 NEFs (needs exiftool).

  python3 tools/trap_debug.py DSC_0001.NEF [...]

Item 38 = decrypted ShotInfoD3b offsets 0x3e3.. ; layout from tools/patch_a.py DEBUG_MAP.
"""
import re
import subprocess
import sys

NAMES = {2: 'hook_count', 3: '3f6bd', 4: '457e5', 5: '457e6', 6: '457e7', 7: '457e9',
         9: '45850', 10: '45851', 11: '45852', 12: '45853', 13: '3fa16', 14: '3fa21(dot)',
         15: '3f874(a2)'}


def shotinfo(path):
    out = subprocess.run(['exiftool', '-v5', '-U', path], capture_output=True, text=True).stdout
    b, on = bytearray(), False
    for line in out.splitlines():
        if 'Decrypted ShotInfoD3b' in line:
            on = True
            continue
        if on and 'ShotInfoVersion' in line:
            break
        m = re.search(r'\s([0-9a-f]{4}): ((?:[0-9a-f]{2} ){1,16})', line) if on else None
        if m:
            b += bytes.fromhex(m.group(2).replace(' ', ''))
    return bytes(b)


for p in sys.argv[1:]:
    it = shotinfo(p)[0x3e3:0x3e3 + 0x1d]
    fm = subprocess.run(['exiftool', '-s3', '-FocusMode', p], capture_output=True, text=True).stdout.strip()
    print(p.split('/')[-1], f'FocusMode={fm} item38[0:2]={it[:2].hex()}')
    print('   ' + '  '.join(f'{n}={it[k]:02x}' for k, n in NAMES.items()))
