# Sub-CPU AF-S focus priority / trap focus (2026-10-07)

## a1/a2 location
- Main item 5 buffer `0x871b0675` (0x17 B, send) byte 1 = `0x871b0676`:
  - bits 7:6 = a1 AF-C priority (menu set handler 0x18cb22, menu object 0x871d9b18, max 2);
  - bit 5 = a2 AF-S priority (set handler 0x18cc82/0x18cc72, object 0x871d9b0d, max 1). 0 = Focus (default), 1 = Release.
- Sub: item 5 work copy `0x3f873` → byte `0x3f874` (bits 7:6 = a1, bit 5 = a2).
- AF engine copy: `0xbe358` copies them into `0x45851` bits 7:6 / bit 5.

## AF-achieved flag `0x3fa16`
Written by the AF engine (`0xbe8d0`, `0xbef94`, `0xbf07a`, ...). Nonzero means OK to release.
In `0xbe8d0`, with `0x457e6` (AF engine mode: 0 MF/rangefinder, 1 AF-S, 2 AF-C):
- mode 0 → `0x3fa16 = [0x416e4] or 0x34`, i.e. **always nonzero**. This is the non-CPU / MF bypass. The same mode 0 selects the rangefinder path in `0xce882`.
- mode 1 with a2 = Release (0x45851 bit5) → nonzero.
- Otherwise 0 until focus is achieved.

## Release gate (polled every tick: 0x9a4f0 → 0x9aa72 → 0x9aa8c)
`0x9b404`-`0x9b4e8`, with r8 = 0x3febc, r9 = 0x3f706, r10 = 0x3f10c, r11 = 0x3feba:
- `0x9b41c`: if a2 = Release (0x3f874 bit5) and !(0x3f70f bit1), skip the AF-S hold.
- `0x9b42c`: if focus switch (0x3f6bd & 0xf) == 1 (AF-S) and [0x3f112] == 0 and **[0x3fa16] == 0**, then HOLD at `0x9b4d6`: clear 0x3febe bit0, set 0x3fec0 bit1, result code 0x3e → 0x3feba, return without firing.
- `0x9b48e`: AF-C equivalent (a1 bits nonzero) uses the same 0x3fa16 test at `0x9b4cc`.

## Candidate patch (AF-S only, non-CPU lens only)
- `0x9b442`: `9b3cfa16 06c0` (ldi:20 0x3fa16,r12; ldub @r12,r0) → `9bfc2d10 971c` (ldi:20 0xf2d10,r12; call @r12).
- Cave at `0xf2d10` (in the 0xff gap 0xf2d04-0xf2ff8 of sector 0xf0000-0xf3fff; unreferenced):

```
r0 = [0x3fa16]
if ([0x3f6d7] & 0xf) == 0:        ; non-CPU lens
    r0 = ([0x3fa21] == 1) ? 1 : 0 ; viewfinder in-focus dot
ret
```

- Hex: `9b3cfa16 06c0 9b3cf6d7 06c1 c0f2 8221 a801 e307 9b3cfa21 06c1 c000 a811 e301 c010 9720`.
- `rp` clobber is fine: 0x9aa8c saves rp and restores it at 0x9b81c, and other calls in it already use rp.
- Test image (scratchpad only): AD3_trap.bin, CRC 0xbde0.

## Avoid as cave space
0xf4000-0xf7fff (data sector copied to RAM 0x42000 at boot, 0x857f8) and 0xf8000-0xfbfff (boot / flash-writer sector, the reset path calls 0xf8050).
