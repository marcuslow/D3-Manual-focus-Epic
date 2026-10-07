# D3 B fw 2.03 — shutter count source (static analysis)
- Global: 0x871b0570 = comm item 0x1b (27) from the sub-CPU, 0x66 bytes. Count = big-endian u32 at 0x871b057a..0x871b057d.
- Comm item table A @0x1c8c90 (16 B/entry: dest, len, dir flag 0=rx/1=tx, done-handler); entry 27 = {0x871b0570, 0x66, 0, 0x12df98 (ret)}.
  Table B @0x1daf04 (12 B/entry: dest, len, id) mirrors it.
- Rx copy: 0x12dc66 copies min(len, rxlen) from rx buffer 0x871b0a39 into entry->dest.
- Main CPU never requests id 0x1b via 0x12df42 → sub-CPU pushes it (presumably per release).
- Capture record: 0x126b32 -> 0x12d122(rec+0x5c) copies 0x871b0570[0..0x66) to payload+0xa7 (0x12d4a2). Payload moves 0x5c -> 0x80 (0x135074) -> 0x8c (0x130054).
  EXIF tag 0xA7 callback 0x15c45e reads rec+0x13d = payload+0xb1 = src+0xa. 
- 0x22671a compares payload bytes 0xb1..0xb4 of two payload buffers (0x871b709c / 0x871b4eb4) — same field.
- MakerNote parser (playback) tag table @0x1ced00: tag 0xa7 -> 0x14068a.
