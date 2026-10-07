# S2 -> release path (A firmware), trap-focus hook (fork notes 2026-10-07)

- Periodic tick 0x80480.. calls 0x9a4f0 every other tick -> 0x9a52e (switch debounce), 0x9a876, 0x9a90c->0x9a926, 0x9aa72->0x9aa8c (release decision chain).
- 0x9a52e: port PDR0 (IO 0x0) bits, active-low, 5-tick debounce (counters 0x3fe8a..), debounced in 0x3fe85.
  S1 sources -> 0x3fe7f bits0-2 -> halfword 0x3f10e (low 3 bits); S2 sources -> 0x3fe80 bits0-2, ANDed with S1 -> halfword 0x3f10c.
  0x3febd bit0 = S2 (sources 0/1) level each tick; bit5 = source 2.
- 0x9aa8c (r8=0x3febc r9=0x3f706 r10=0x3f10c r11=0x3feba): 0x9ab52 if byte 0x3febd != 0 -> chain at 0x9ac80 (clears 0x3febd; recomputed next tick) => level-triggered, re-run every tick while S2 held.
  Each 'no release' exit stores a reason code to 0x3feba then jmp 0x9b81c. Release: 0x9b7b0 gate 0x96012 -> sta_tsk(11,0) at 0x9b812.
- Focus-priority hold block 0x9b3d8..0x9b4e8, reason 0x3e (exit 0x9b4d6):
  AF-S: focus mode (0x3f6bd&0xf)==1, [0x3f112]==0, 0x3fa16==0 (or 0x3feeb bits3:1==3) -> hold. Skipped if 0x3f874 bit5 set (=a2 Release, inferred) unless 0x3f70f bit1.
  AF-C: 0x3f874 bits7:6 != 0 (a1), focus mode 2, [0x3f112]==0, 0x3fa16==0 -> hold.
  Skipped entirely when 0x3febe bit4 set (non-mode-3) or mode 3 w/o conditions.
- 0x3fa2a bit7 = release task busy (set 0xd961c task-11 entry, cleared 0xdbae0) -> reason 0x32. Not focus.
- Proposed hook: 0x9b3d8 (6 B: ldi:20 0x3f6ba,r12; ldub @r12,r0) -> ldi:20 0xf5a00,r12; jmp @r12. Cave 0xf5a00 (86 B, free 0xff 0xf59e8-0xf8000, no refs):
  if mode<=2 && AF-S && non-CPU lens && !(0x3f874 bit5): 0x3fa21==1 ? jmp 0x9b4ea (continue) : jmp 0x9b4d6 (hold 0x3e); else redo displaced + jmp 0x9b3de.
