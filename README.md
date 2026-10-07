# D3 Manual Focus Epic

Custom firmware patches for the **Nikon D3** (firmware 2.03), aimed at shooting manual-focus lenses.
The headline feature is **trap focus**: hold the shutter release and the camera fires only once the
viewfinder focus dot (●) lights.

> **Use at your own risk.** This is unofficial, reverse-engineered firmware. It is not affiliated with or
> endorsed by Nikon. Flashing any firmware can brick a camera. Read the whole README before you flash.

## Downloads

| File | Version shown on camera | Features | Status |
|---|---|---|---|
| [`release/A-2.05-trap-focus/AD3_0203.bin`](release/A-2.05-trap-focus/AD3_0203.bin) | **A 2.05** | Trap focus for manual focus | ✅ Tested on a D3 |
| [`release/B-2.03-experimental-shots-d2x/BD3_0203.bin`](release/B-2.03-experimental-shots-d2x/BD3_0203.bin) | B 2.03 | Shutter count on the Firmware version screen; D2X MODE 1/2/3 built in | ⚠️ **Experimental, not yet flashed on a camera** |
| [`D3Update/AD3_0203.bin`](D3Update/AD3_0203.bin) | A 2.03 | Original Nikon sub-CPU firmware | Stock, for reverting |
| [`D3Update/BD3_0203.bin`](D3Update/BD3_0203.bin) | B 2.03 | Original Nikon main CPU firmware | Stock, for reverting |

The D3 has two firmware chips. **A** is the sub-CPU (release, AF, metering and the top/rear LCDs).
**B** is the main CPU (menus, image processing, EXIF). Each one is flashed separately. You can run the
patched A with the stock B, which is the tested setup.

### SHA-256

```
fbc65b6d768a20edfcdbe0acfe13e31b6d2969d79946678aa439d8b1f04884d4  release/A-2.05-trap-focus/AD3_0203.bin
b5dbae80c9123a38a8c6c2baffe377b17941c94f83087c9ffc9ba82a545b207d  release/B-2.03-experimental-shots-d2x/BD3_0203.bin
afc28972c292e42652aa47e49b18e37631c9cbc2de20c1e242fad1cadb920e52  D3Update/AD3_0203.bin   (stock)
982bee9e27582fed9cdbf80234e9190a0b39b47b37cc623433266ed33c9c3575  D3Update/BD3_0203.bin   (stock)
```

Check your download with `shasum -a 256 <file>` before you copy it to the card.

## Features

### Trap focus (A 2.05)

When **all** of these are true, holding the shutter release does **not** fire until the focus dot
(●) lights in the viewfinder. Then it fires.

- The effective focus mode is Manual. That means a non-CPU lens (AI/AI-S/Series E…) with the
  selector on any position, or any lens with the focus selector on **M**.
- Custom setting **a2 (AF-S priority selection) = Focus**.
- Release mode is **S, CL or CH**.

Set **a2 = Release** to turn it off and get normal behaviour. a2 is the switch because the camera can't
read the focus-mode selector when a non-CPU lens is mounted.

To use it: pre-focus on the spot where the subject will be, hold the release fully down and wait. The
camera fires the moment the rangefinder says it's in focus.

### Shutter count (B, experimental)

Adds a `Shots <n>` line under the A/B version lines on **Setup → Firmware version**. The count comes
from the sub-CPU, which sends it after each shot. Right after power-on it shows `Shots --` until the
first frame.

### D2X MODE 1/2/3 built in (B, experimental)

Nikon's D2X MODE 1/2/3 Picture Controls are built into optional Picture Control slots 1-3, so you don't
need to load the `.NOP` files. Slot 4 stays a normal slot for your own `.NOP`/`.NCP` files. Installing
over slots 1-3, or deleting them, won't stick: the D2X modes come back after a power cycle.

## How to flash

1. Fully charge an EN-EL4a battery. The updater refuses to run on a low battery.
2. Format a CF card in the camera.
3. Copy **one** firmware file into the **root** of the card. It must keep its exact name,
   `AD3_0203.bin` or `BD3_0203.bin`. If both are on the card, A is flashed and B is ignored, so flash
   them one at a time.
4. Put the card in slot 1, then go to **Setup menu → Firmware version → Update** and follow the prompts.
   Don't turn the camera off or open the card door during the update.
5. When it finishes, switch off, switch on, and check **Firmware version**. For the trap-focus build it
   must say **A 2.05**. If it still says A 2.03, the update didn't take.

## How to revert to stock

Flash the original Nikon files from [`D3Update/`](D3Update/) the same way: `AD3_0203.bin` brings back
**A 2.03**, and `BD3_0203.bin` brings back the stock **B 2.03**. The updater has no version check, so
going back down from 2.05 works. This was done repeatedly during development.

## Building from source

The patches are Python scripts that start from Nikon's stock files and fix the CRC trailer:

```sh
# A: trap focus, reported as A 2.05
python3 tools/patch_a.py D3Update/AD3_0203.bin build/AD3_0203.bin --trap-focus --version 2.05

# B: shutter count + D2X MODE 1-3 (needs D2X/D3____M{1,2,3}.NOP)
python3 tools/patch_d3.py D3Update/BD3_0203.bin build/BD3_0203.bin --shutter-count --d2x D2X

python3 tools/d3crc.py build/AD3_0203.bin   # verify the CRC16 trailer
```

Both builds are reproducible: the output should match the SHA-256 values above.

## Repository layout

| Path | Contents |
|---|---|
| `release/` | Ready-to-flash patched firmware |
| `D3Update/` | Original Nikon D3 firmware 2.03 (A and B) |
| `D2X/` | Nikon's D2X MODE 1/2/3 optional Picture Control files |
| `tools/` | Patchers (`patch_a.py`, `patch_d3.py`), CRC tool, FR mini-assembler, disassembly helpers |
| `NOTES.md` | Full reverse-engineering notes: addresses, hooks, dead ends |
| `work/`, `workA/` | Analysis notes. Regenerate the disassembly with binutils `objdump -m fr30 -EB` (see NOTES.md §2) |

## Work in progress

- ISO range limit, for example 200-3200 only, with Lo/Hi and 6400 removed. See NOTES.md §10.
- Custom colour profiles. The Picture Control colour table isn't decoded yet.

## Credits and legal

The original firmware and the D2X MODE files are © Nikon Corporation. They are included unmodified
so people can revert, and they remain Nikon's property. The patch scripts and notes are the work of
this project.
