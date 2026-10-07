# Nikon D3 firmware 2.03 — reverse engineering notes

## 1. Files
- `D3Update/AD3_0203.bin` (512 KiB): sub-CPU firmware ("D3_ Firmware A Copyright Nikon Corp."), FR code. SHA-256 `afc28972…0e52`.
- `D3Update/BD3_0203.bin` (7 MiB): main CPU firmware, Fujitsu FR (EXPEED), Softune REALOS/FR (µITRON). SHA-256 `982bee9e…3575`. Not encrypted.
- Both end in **CRC16-CCITT/XMODEM** (poly 0x1021, init 0) over the rest of the file, stored big-endian. `tools/d3crc.py [--fix] FILE`.
- B image: file offset 0 = address **0x40000** (694 string pointers agree), big-endian. Boot copies the .data init image `0x2966fc` (0x12f18 B) to RAM `0x871d3930` (`0x40402`). RAM is at `0x87xxxxxx`.
- Build signature `0x1d0a10`: "Q340FirmwareSignature" / "Ver.2.03a D3   2013/03/13 for mass production".

## 2. Tools
- `cd work && objdump` (binutils fr30, `-EB --adjust-vma=0x40000`) → `work/dis.txt`. Then `python3 ../tools/annot.py` (string refs → dis_ann.txt), `cg.py`, `cg2.py`. Use `lin.py START END` and `who.py ADDR`. These are copied from the DP2x project.
- `tools/fr_asm.py`: the mini-assembler (verified against objdump).
- `tools/patch_d3.py STOCK OUT [--shutter-count]`: builds the patched B file and fixes the CRC.

## 3. UI
- **Menu strings:** concatenated without NULs. Each language has 3 pointer tables, registered by `0x1a3788`; English: `0x3d0528`, `0x3d0b9c`, `0x3d0ef4`. Text-ID lookup is `0x165d0c`: bits 0xe000 pick the table and string k = ptr[k]..ptr[k+1]. "Firmware version" = ID 0x2075.
- **Firmware version screen `0x23f9cc`** (frame `enter 0x4c`):
  - A line: built by `0x181cd8` → `0x181ed2` from BCD bytes at `0x871b06bd` (sent by the sub-CPU).
  - B line: built by `0x181cc2`, which copies "2.03" out of the signature string.
  - Optional "S" lines, gated by bit 8 of `0x871b0274` / `0x871b069f`.
  - Positions: A at (109,99), B at (109,127), S at y=155. Line pitch 28; letter box 10×20.
- **Draw text:** `0x165106(r4 scratch, r5 style=7, r6 x, r7 y, [sp+0] char*, [sp+4] flag)`.
- **Clear rect:** `0x167208(&{x,y,w,h} u16, mode)`.
- **Draw text by ID:** `0x165496`.
- **sprintf:** `0x1c1bb4(buf, fmt, r6, r7, …)`.

## 4. Shutter count
- MakerNote template: 16-byte entries {tag, type, count, value, fill fn}, in the table at `0x1d2548`-`0x1d3258` (IFD list at `0x1d23e0`). Tag 0xA7's fill function is `0x15c45e`. It reads a BE u32 at record+0x13d; the record is the job message received by the EXIF task `0x15e1de` (via `0x123e96`).
- Source: `0x12d4a2` copies 0x66 bytes from the global `0x871b0570` into the payload. **Count = BE u32 at `0x871b057a`** (unaligned, read it byte-wise).
- `0x871b0570` is main↔sub-CPU comm item 0x1b in the table at `0x1c8c90` (receive, len 0x66). The sub-CPU pushes it; the main CPU never requests it. Expect 0 until the first shot after power-on (the patch shows "Shots --" then). The master count lives in the sub-CPU's EEPROM.
- Details: `work/shutter_count_notes.md`.

## 5. Picture Control (colour) data
- Built-in records: STANDARD `0x2056b4`, NEUTRAL `0x20535c`, VIVID `0x205004`, MONOCHROME `0x204fc4`.
- Pointer pairs at `0x204f8c`: (record, colour table) = STANDARD → `0x5166ba`, NEUTRAL → `0x51de4a`, VIVID → `0x50ef2a`, each 0x7790 B apart (layout not decoded yet).
- Custom Picture Controls load from `A:\NIKON\CUSTOMPC\PICCONnn.NCP`.

## 6. Patches
### 6.1 `--shutter-count`
- Hook: `0x23fb86` (the version screen epilogue). The 8 bytes `ldi:32 0x871b2a41,r0; borl 0x8,@r0` become `ldi:32 0x28edc0,r12; jmp @r12`.
- Cave `0x28edc0`-`0x28ee40` (128 B) does the following:
  1. Reads the count.
  2. Writes "Shots %d" with sprintf into r14-0x40, the A/B line buffers, which are already drawn. If the count is 0 it writes "Shots --" instead.
  3. Draws the line at (109,183) with flag 1.
  4. Redoes the displaced instructions and jumps back to `0x23fb8e`.
- **Free cave space:** `0x28ee40`-`0x28fdd0`. This is the linker gap of 0xff between the data end `0x28edbc` and the .data init image; no instruction references it.
- **Avoid these 0xff regions:**
  - `0xf0000`-`0x120000` and the tail after `0x579ad3`, probably runtime flash.
  - `0x54e74`-`0xefbf0`.
- Build: `python3 tools/patch_d3.py D3Update/BD3_0203.bin build/BD3_0203.bin --shutter-count` → SHA-256 `1bac372f593e3af275464831aedcd2de14855c48a5edbbe3f88eb58ecab7768f`, CRC 0x64e7. **Not yet flashed.**
- Updater (`0x181ace` → `0x1829fc` → `0x182a18`/`0x182c4a`):
  1. Finds `BD3_????.BIN` on the card.
  2. Requires size 0x700000.
  3. Follows the pointer at file 0xafbf4 and compares the 32-byte "Q340FirmwareSignature" with its own copy.
  4. Follows the pointer at 0xafbf0 and copies the 9-byte version string "Ver.2.03a" for display.
  - No equal-version rejection was found statically, so reflashing 2.03 over 2.03 should be accepted.
- Unverified on the camera:
  - whether y=183 collides with anything else drawn on that screen;
  - when the sub-CPU first sends item 0x1b after power-on.

## 7. Optional Picture Controls (.NOP), e.g. D2X MODE 1/2/3
- Nikon files `D2X/D3____M{1,2,3}.NOP` (2007-10-15, 31474 B each). They are **data, not code**.
- File layout:
  - `"NOP\0"`
  - u16 1, u16 1
  - **0x358-byte Picture Control record**: the same layout as the built-in STANDARD/NEUTRAL/VIVID records. It holds a u16 id (0x0014/0x03d5/0x00d6), the name "D2XMODE1" at +2, the code "M1" at +0x16, parameters and menu icon bitmaps.
  - **0x7790-byte colour table**: the same size as the built-in tables.
  - CRC16-CCITT/XMODEM, BE, over everything before it. This is the same CRC as the firmware files.
- Firmware support:
  - The Picture Control table `0x204f8c` lists 3 built-ins (record, table), then **4 optional slots in flash**: `0x7c0000`/`0x7c0358`, `0x7d0000`, `0x7e0000`, `0x7f0000`. These are outside the 0x40000-0x73ffff image, so they survive firmware updates.
  - Card scan `0x1b2970` → `0x1b2cd8` → `0x1b2b4a` looks for 12-char names with the extension "NOP" in `A:\NIKON\` and checks them (`0x1b29e4`, `0x1b2a0e`, magic "NOP").
  - It runs once from the menu handler `0x256ee4` (flag `0x871d0938`). Which menu item that is hasn't been confirmed; probably Manage Picture Control.
- Implication: **new colour profiles can be shipped as our own .NOP files**. Copy a record and table, edit, rename, then fix the CRC. No firmware flash is needed. The D2X and built-in tables are 7 examples for decoding the table layout.

### 6.2 `--d2x DIR` (D2X MODE 1-3 built in)
- How optional slots are read: everything goes through `PC_TABLE` `0x204f8c`.
  - The list build `0x1b2580`/`0x1b260e` copies each entry into the RAM list `0x8768ec46` (64 B per entry). A slot is empty when its record id is 0xffff.
  - The id lookups `0x1b2854` (record) and `0x1b28a6` (colour table) also use it.
  - Only install (`0x1b43a8`) and delete (`0x1b4414`) use the flash base table `0x205bc4`.
- The patch embeds record+table+0xaa55 from `D2X/D3____M{1,2,3}.NOP` at `0x6a0000`/`0x6a8000`/`0x6b0000` and points PC_TABLE entries 3-5 at them. Entry 6 stays the real slot `0x7f0000`.
- Runtime flash writes only go to addresses >= 0x740000: settings 0x740000-0x770000, 0x780000/0x7a0000, the slots 0x7c0000-0x7f0000 and 0x800000. So the image tail (0x579ad3-0x73fffe) is static.
- Side effects:
  - Installing a .NOP into slot 1-3 from the menu writes the real flash slot, but the D2X mode comes back after a power cycle.
  - Deleting a D2X slot doesn't stick either.
  - Use slot 4 for other .NOP files.
- Build: `python3 tools/patch_d3.py D3Update/BD3_0203.bin build/BD3_0203.bin --shutter-count --d2x D2X` → SHA-256 `b5dbae80c9123a38a8c6c2baffe377b17941c94f83087c9ffc9ba82a545b207d`, CRC 0x4236. **Not yet flashed.**

## 8. Update-file detection
- The Firmware version menu (`0x23f692`) calls `0x181ace`:
  1. Gate `0x181bda`: card/state checks, including `0x871c5137 != 2`, probably the battery level.
  2. `A:\AD3_????.BIN` (`0x182f88` search, validated by `0x182a84`). **If found, A wins and B isn't checked.**
  3. `A:\BD3_????.BIN` (`0x1829fc`: size 0x700000, signature, 9-byte version string).
  4. `A:\S???????.BIN` (`0x182b90`). The WT-4 transmitter uses `0x181b76` and `_WT4????.BIN`.
- A return of 1 sets the menu item state to 2 (Update enabled); otherwise it is 1.
- To flash a B-only build, put just `BD3_0203.bin` in the card root, with no AD3 file.

## 9. Trap focus for manual lenses (investigation, 2026-10-07, not solved)
- Goal: with a non-CPU lens, the selector on S and a2 = Focus, hold the release and fire when the rangefinder confirms focus. The selector on M = normal.
- **Main CPU does not gate the release.**
  - Custom settings live in `0x871b9388` (0x68 B). The AF-C/AF-S priority bits are `0x871b938a` bit0 and `0x871b938c` bit2 (which is which is not pinned); setters are `0x245822` and `0x23e692`. The only consumers are UI code.
  - Focus mode M/S/C comes from the sub-CPU (item 27 `0x871b05cd` bits 7:6). The CPU-lens flag also comes from the sub-CPU (item 38 `0x871b0218` bit6).
  - There is no live in-focus signal on the main side.
  - The main CPU can only veto a release through item 11 `0x871b0625` (busy/inhibit bits, sent with `0x12df42(0xb)`).
- **Sub-CPU (A firmware) runs the release.**
  - Image: FR, base 0x80000, reset `0xfc000`, µITRON. Task table `0xfe014`; disassembly in `workA/`.
  - Comm table `0xe2218` (12-B entries, the same item order as the main table). Received items are unpacked by `0xa09d2`: item 5 → `0x3f873`, item 7 (custom settings) → `0x3f8a1`, item 11 → `0x3f8cb`, item 18 → `0x3f24c`.
  - Release task 11 (priority 1): entry `0xd9608`, command table `0xf2548`, release sequence `0xd97bc` → `0xda176`. The shutter count is u32 `0x40038`, incremented at `0xda20c`.
  - Release starts come from the button state machine (`0x951aa`, `0x3f710` states) and `0x9aa8c` (after `0x96012` returns 0).
  - Gates: `0x952c0` (0 ok, 1 inhibit, 2 not ready) and `0x96012`/`0x96794`.
  - The AF-S focus-priority check, the in-focus/rangefinder flag and the CPU-lens bypass are **not found yet**. Best lead: `0x96794` (`0x3f0ca` bit1 early-allow; tests `0x3f24d`/`0x3f24e` bit6, `0x3f8cc` bit4, `0x3f6f7`).
- A real patch would modify the A firmware: flash `AD3_0203.bin` with the CRC fixed.
- **Sub-CPU findings (continued, 2026-10-07):**
  - Focus mode = `0x3f6bd` bits1:0 (0 M, 1 AF-S, 2 AF-C; the decoding comes from main EXIF `0x15adc6`). It is copied to item 27 byte 0x5d by `0xa1466`.
  - CPU lens iff `(0x3f6d7 & 0xf) != 0` (built into item 38 byte0 bit6 by `0x9fb2c`).
  - **VF focus indicator state `0x3fa21`**, computed in `0xce882`: 1 = ● in focus, 2/4 = arrows, 0xe = can't focus (blinking). Shown by the segment builder `0x8e3ee` (VF segment RAM `0x3ff4e`+0xd..0xf, the blink phase `0x3ff21` bit6).
    - Rangefinder path when `[0x457e6]==0`: valid reading = `0x459a2` bit3, in focus = `0x459a1` bit5, direction via `0xc00b0([0x42720])`.
    - AF path: `0x3fa23` bit2 = AF achieved.
  - Display segment builders `0x8db98` → `0x8e0xx`-`0x8f2xx`; `0x3f8a1` bits1:0 = custom bank A-D, `0x3f873` bits1:0 = shooting bank.
  - Release call sites: `0x9b7b0` calls gate `0x96012` (latch `0x3f421` bit3, set by the self-timer path `0x95b4c`), then `sta_tsk(11,0)` at `0x9b812`. The `0x951b8` state machine (`0x3f710`) also does `sta_tsk(11,0)`. `0x96794` = card/buffer/mode checks, not focus.
  - The RTOS uses event flags (`int 0x40` codes 0xd0 set_flg, 0xd1 clr_flg, 0xd2 wai_flg?, 0xe9 sta_tsk) and has no dly_tsk.
- **Trap-focus patch (A firmware), `tools/patch_a.py --trap-focus`, built 2026-10-07. NOT flashed.**
  - The release decision `0x9aa8c` runs every tick while the button is held:
    - S2 level flag `0x3febd` bit0, from debounced port IO 0x0 in `0x9a52e`;
    - S2 halfword `0x3f10c`, S1 halfword `0x3f10e`;
    - the "don't release" exits write a reason code to `0x3feba`.
  - Nikon's focus-priority hold block `0x9b3d8`-`0x9b4e8`. The AF-S hold condition is: focus mode 1, `[0x3f112]==0` and `[0x3fa16]==0`. It exits at `0x9b4d6` (reason 0x3e: clears `0x3febe` bit0, sets `0x3fec0` bit1) and is asked again next tick.
  - a2 = `0x3f874` bit5 (0 Focus, 1 Release); a1 = bits 7:6. These come from main item 5 byte 1 (`0x871b0676`).
  - Why manual lenses never hold: the AF engine "OK to release" byte `0x3fa16` is set nonzero by `0xbe8d0` when engine mode `0x457e6==0` (MF/rangefinder).
  - Patch:
    - Hook at `0x9b3d8`: `9b3cf6ba 06c0` → `ldi:20 0xf2d10,r12; jmp @r12`.
    - Cave at `0xf2d10`-`0xf2d60`: if release mode `0x3f6ba` <= 2 && focus mode == AF-S && non-CPU lens && a2 == Focus && `0x3fa21` != 1, jump to the hold `0x9b4d6`. Otherwise redo `ldi/ldub` and jump to `0x9b3de`.
  - **Sub-CPU flash map:**
    - The A code/const sector is `0xf0000`-`0xf3fff`; the free gap `0xf2d04`-`0xf2ff7` ends at the **boot validity marker `0xf2ff8`** (8 B = version header). `0xf8060` compares it with `0xffbf8` at reset and enters recovery `0xf8456` on a mismatch or blank.
    - `0xf4000`-`0xf7fff` is a runtime data sector (copied to RAM 0x42000); `0xf8000`-`0xfbfff` is the boot/flash writer. Don't use either.
  - The A updater on the main side (`0x182aa0`) checks size 0x80002 and the 6-byte header. The AD3 file takes priority over BD3 on the card.
  - Build: `python3 tools/patch_a.py D3Update/AD3_0203.bin build/AD3_0203.bin --trap-focus` → SHA-256 `eb101ecae6622ae137bb6ea16f9d9e325b139e6a4b77aee653c919ab07d7c614`, CRC 0x241a, 87 bytes changed.
  - Assumptions to verify on the camera:
    - release modes 0-2 = S/CL/CH;
    - `0x3fa21` keeps updating while S2 is held in AF-S with a non-CPU lens;
    - the hold re-fires automatically.
  - Fork notes: `workA/notes_s2.md`, `workA/notes_afprio.md`.
- **Trap-focus v1 failed on the camera (2026-10-07): it fired immediately on S.**
  - Diagnosis was done from test NEFs, by decrypting ShotInfoD3b with `exiftool -v5`. In ShotInfo the shutter count is at 0x27f, item 27 at 0x275, item 38 at 0x3e3; ShotInfo offset = payload offset + 0x1ce.
  - With a non-CPU lens the effective focus mode (0x3f6bd&3, EXIF FocusMode) is 0 = Manual even with the selector on S. So v1's "AF-S" test never matched. (v1's "non-CPU lens" test `(0x3f6d7&0xf)==0` was also wrong on S.)
  - M vs S controlled pair (DSC_9916 = M, DSC_9917 = S):
    - item 38 byte0 changes 0x08 → 0x4c: bit6 = (0x3f6d7&0xf)!=0, bit2 = 0x3f6de bit0;
    - item 38 byte1 (= 0x3f6da) changes 0x80 → 0xe1;
    - the item 27 focus byte (0x5d) is unchanged; its bits 5:4 are not the selector.
- **Trap-focus v2:** condition = release mode <= 2 && effective focus mode == 0 && (0x3f6d7&0xf) != 0 (selector requests AF) && a2 == Focus && 0x3fa21 != 1 → hold.
  - S vs C is not distinguished, so C traps too.
  - Build SHA-256 `3d357213b36e63afa105fd24203aa2c684c78c97e2bce38f0a23061cb4e6e6ae`, CRC 0x2fb7. Copied to the card, not flashed yet.
- **v2 also failed (2026-10-07):** DSC_9921 (taken on S) has item 38 byte0 = 0x22 and byte1 = 0x3d, versus 0x4c/0xe1 on DSC_9917 (S). So `0x3f6d7`/`0x3f6da`/`0x3f6de` are live lens/AF-comm status and vary from shot to shot. They are not the selector.
  - Corrected item 38 map: byte k (1..8) is copied at `0x9fbaa+12*(k-1)` from 0x3f6da, 0x3f6db, 0x3f6dc, 0x3f6dd, 0x3f6df, 0x3f6e1, 0x3f6e2, 0x3f6f3 (byte 8 = lens ID, used by main LensType). Bytes 9..15 are copied at `0x9fc0a+12*(k-9)` from 0x3f6e5..0x3f6eb. The non-CPU stock values include byte10 = 0x21 and byte12 = 0xc0.
- **Debug build** `build/AD3_0203_debug.bin` (`--trap-focus --trap-debug`), SHA-256 `3e8dd8f8…`, CRC 0x5a08.
  - It re-points item 38 bytes 2-7 and 9-15 at candidate bytes: hook counter (0x40600), 0x3f6bd, the AF engine bytes 0x457e5/e6/e7/e9 and 0x45850..53, 0x3fa16, 0x3fa21, 0x3f874.
  - Decode with `tools/trap_debug.py`.
  - Plan: M shot + S shot, then find the byte that follows the selector, and check that the hook count is nonzero.
- **Debug shots DSC_9922-9926 show the stock item-38 lens bytes** (byte10 = 0x21, byte12 = 0xc0, hook counter 0). So **the patched A firmware is apparently not running**; this probably explains v1 and v2 too. The A file was gone from the card after the update.
  - Each NEF stores the running A version at decrypted ShotInfo 0x321 (6 B: header 0x80000-2 + `0x3f720`..; the main copies record+0x321 from item 2 `0x871b06bd`).
  - Sub item 2 is built at `0x9d2ae` from the A header bytes 0x80000-0x80002.
  - The main A-update path (state 2 at `0x1821d4`) reads the 0x80002-B file into 0x81000000, then `0x1823d8` drives the transfer through items 13/14 (`0x871b0621` bit6 / `0x871b061e` status) with a progress bar. The sub-CPU's flash writer decides what gets written. No version compare was found on the main side.
- Next: `--version 2.04` patches header byte 0x80001 (`build/AD3_0203_debug.bin`, SHA `f2f22a1a…`, CRC 0x229f, on the card). The version screen showing "A 2.04" after the update means the flash took.
- **A 2.04 debug build ran** (DSC_9927 M / DSC_9928 S record A version 02 04 at ShotInfo 0x321), but the snapshot was useless.
  - Every candidate (0x3f6bd, 0x457e5/6/7/9, 0x4585x, 0x3fa16) is identical on M and S. The AF-engine copies 0x45850-53 mirror the stock lens bytes (0x45851 = 0x21, 0x45853 = 0xc0).
  - The hook counter at 0x40600 was invalid: item 61 (main → sub, the per-shot image params from main 0x12867c/0x128a22) overwrites that buffer.
  - Bits that consistently differ M→S across both pairs: ShotInfo 0x114 = item 21 byte2 = sub `0x3fee4` (M 1, S 0; signed display/status value, purpose unclear); 0x383 (M 0, S 2); 0x6c5-0x6cb filled on S (AF data).
- **Probe build** `build/AD3_0203_probe.bin` (`--trap-probe --version 2.05`, SHA `10e4cf95…`, CRC 0x2539, on the card): holds every release the hook at 0x9b3d8 sees when release mode <= 2 and a2 = Focus. Never fires → the hook is on the path. Fires → MF single-frame releases take another path. a2 = Release is the escape.
- **Probe result (A 2.05):** with a2 = Focus the camera would not fire on M or S, even with the dot lit. **The hook at 0x9b3d8 is on every release path.**
- **Trap focus v3** = `python3 tools/patch_a.py D3Update/AD3_0203.bin build/AD3_0203.bin --trap-focus --version 2.06` (SHA `03b02ed2…`, CRC 0xdeab).
  - Condition: release mode <= 2 && effective focus mode == M && a2 == Focus && dot (0x3fa21) != 1 → hold.
  - a2 is the on/off switch, because the selector can't be read for a non-CPU lens.
  - Still unverified: whether 0x3fa21 updates while S2 is held.
- **2026-10-07: trap focus v3 CONFIRMED WORKING on the camera** (A 2.06, SHA `03b02ed2…`). With a2 = Focus and the Series E 50/1.8 (non-CPU), holding the release does not fire until the VF dot lights, then it fires. a2 = Release fires immediately. The camera currently runs this A firmware with the stock B 2.03.
- The focus point not moving (2026-10-07) was a hardware issue from the user's rear-panel LCD cleaning, since fixed. It was not caused by the patch; the stock A behaved the same.
- Current flashable trap-focus build: `python3 tools/patch_a.py D3Update/AD3_0203.bin build/AD3_0203.bin --trap-focus --version 2.05` → SHA `fbc65b6d…`, CRC 0x3d8e. It is identical to the confirmed 2.06 build apart from the version byte; the user asked for 2.05.
- **2026-10-07: the A 2.05 trap-focus build (SHA fbc65b6d…) is flashed and confirmed working. The camera runs it with the stock B 2.03.**

## 10. ISO range limit (investigation, 2026-10-07): DROPPED by the user, nothing built. Kept for reference only.
- Goal: remove Lo 1 / Lo 0.x, 6400 and Hi 0.3-Hi 2 so the manual ISO range is 200-3200 (or 200-5000).
- **Main (B) ISO setting = byte `0x871b064f`** (item 7 byte 3, main → sub). Units are 1/12 EV: Lo 1 = 60, 200 = 72, 3200 = 120, 6400 = 132, Hi 1 = 144, Hi 2 = 156. The ISO step (b1) is `0x871b067b` bits 7:6: 0 = 1/3, 1 = 1/2, 2 = 1 EV.
  - Value → list index: `0x1d7329[(v)/4]` (1/3), `0x1d72fe[v/6]` (1/2), `0x1d72e8[v/12]` (1 EV).
  - Index → value: `0x1d7152` (23 entries, 1/3), `0x1d7142` (16, 1/2), `0x1d7139` (9, 1 EV).
  - Menu list handlers (pointers at `0x29adb0`-`0x29add4`): enter `0x2501da`/`0x2502ac`/`0x25037e` clamp v to 60..156 and set the cursor; set `0x250244`/`0x250316`/`0x2503e8` write `0x871b064f` from the tables, then `0x24d59c(2)`.
  - PTP/Camera Control path: set `0x18764a` (tables `0x1dc56d`, RAM `0x871da435`, `0x1dc5f1`), enum `0x187888` (counts 23/16/9, label tables `0x1dc35a`/`0x1dc388`/`0x1dc3a8`).
  - Info-screen display `0x24fc06` clamps 60..156.
- **The ISO button + rear dial runs on the sub-CPU (A).** It reports via item 8 (`0x871b063a`, sub → main), and `0x12e574` copies all 0x12 bytes of item 8 into item 7, so main adopts the sub's ISO.
  - A: item 7 → `0x3f8a1`.. (ISO at `0x3f8a4`); item 8 is built from `0x3f8b3`.. at `0x9d8e8`. ISO byte `0x3f8b6` = `0x3fe4b` << 1, so **the sub keeps ISO in 1/6 EV at `0x3fe4b`** (200 = 36, 3200 = 60, Lo 1 = 30, Hi 2 = 78). It is only referenced directly once, so the dial handler reaches it via a base+offset (struct around `0x3fe40`). Next: find that writer and its min/max clamp.
- Plan: clamp in both firmwares (A dial and B menu/PTP), plus Auto ISO max sensitivity. Make min/max a script option.
