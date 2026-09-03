# Keyboard Invoice Triage

Candidate frame 02 answers commission `use-keyboard-invoice-triage` with one
paired publication. Three wholly synthetic invoices total exactly **196.25**.

## What the pair proves

- The standalone app starts with focus on `SYN-001` and exposes a persistent,
  high-contrast focus ring plus a textual focus readout.
- `Enter`, `ArrowDown`, and `Tab` accept the first two invoices, correct
  `SYN-003` from `Uncoded` to `Facilities`, and export
  `{"acceptedTotal":"196.25","invoiceCount":3}`.
- `Shift-Tab` returns from export to `SYN-003`; `Enter` opens the amount field,
  and typing `-1.00` shows an inline error, disables export, preserves the
  accepted/exported 196.25 result, and keeps focus on the invalid field.
- Four forward `Tab` presses reach **Restore invoice fixture**. Two `Enter`
  presses confirm replacement, return all three invoices to pending, clear
  errors and exports, restore total 196.25, and focus `SYN-001`.

`apps/use-keyboard-invoice-triage.html` is self-contained and exports the
deterministic reducer contract as both `window.invoiceTriage` and
`window.tinySystem`. `evidence.json` binds the positive, rejected, and exact
reset snapshots.

The live app compacts its queue and evidence panels in short or narrow player
iframes without shrinking focus targets below 44 px. Coordinate-free semantic
`scroll` actions frame the focused control and each exported, rejected, and
reset result; every state-changing activation remains keyboard-only.

## Reproduce

From this directory in PowerShell:

```powershell
$tools = python .\render.py --show-tools | ConvertFrom-Json
python .\render.py --ffmpeg $tools.ffmpeg
python ..\..\scripts\compile_publications.py build .\channel.production.json --ffmpeg $tools.ffmpeg --ffprobe $tools.ffprobe
python .\render.py --delivery-only --ffprobe $tools.ffprobe
node .\verify_dom.mjs
python ..\..\tests\test_frame_0002_02.py -v
```

Tool discovery checks explicit arguments, `RAPP_VISION_FFMPEG`,
`RAPP_VISION_FFPROBE`, `FFMPEG`, `FFPROBE`, `FFMPEG_BIN`, `PATH`, and common
cross-platform install locations. The DOM verifier similarly checks
`RAPP_VISION_BROWSER`, common Chromium environment variables, `PATH`, and
standard Edge, Chrome, Chromium, and Brave locations. Every path may still be
overridden explicitly.

The renderer uses only the Python standard library and streams deterministic
RGB24 frames to a single-threaded FFV1 Matroska master. The existing compiler
produces single-threaded H.264/yuv420p MP4 and VP9/yuv420p WebM derivatives
tagged limited-range BT.709. `delivery.json` records byte counts, SHA-256
digests, codec probes, and stable frame samples.

## Guided film timeline

The 18-second, 960×540 film states the expected fixture total, visualizes the
Tab, Shift-Tab, arrow, typing, and Enter focus path, shows the correction and
exported 196.25 field, displays the negative-amount error beside a disabled
export control, and finishes on the exact restored fixture. The executed
real-browser verifier replays the production manifest itself and checks
`document.activeElement` after every action. The pair has no audio, external
assets, pointer action, or runtime network dependency.
