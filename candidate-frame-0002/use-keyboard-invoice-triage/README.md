# Keyboard Invoice Triage

Candidate frame 02 answers commission `use-keyboard-invoice-triage` with one
paired publication. Three wholly synthetic invoices total exactly **196.25**.

## What the pair proves

- The standalone app starts with focus on `SYN-001` and exposes a persistent,
  high-contrast focus ring plus a textual focus readout.
- `Enter`, `ArrowDown`, and `Tab` accept the first two invoices, correct
  `SYN-003` from `Uncoded` to `Facilities`, and export
  `{"acceptedTotal":"196.25","invoiceCount":3}`.
- Editing the accepted third invoice to `-1.00` shows an inline error, disables
  export, preserves the accepted/exported 196.25 result, and focuses the amount
  field.
- **Restore invoice fixture** requires confirmation, then returns all three
  invoices to pending, clears errors and exports, restores total 196.25, and
  focuses `SYN-001`.

`apps/use-keyboard-invoice-triage.html` is self-contained and exports the
deterministic reducer contract as both `window.invoiceTriage` and
`window.tinySystem`. `evidence.json` binds the positive, rejected, and exact
reset snapshots.

## Reproduce

From this directory in PowerShell:

```powershell
$bin = 'C:\Users\kowildfe\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-essentials_build\bin'
python .\render.py --ffmpeg "$bin\ffmpeg.exe"
python ..\..\scripts\compile_publications.py build .\channel.production.json --ffmpeg "$bin\ffmpeg.exe" --ffprobe "$bin\ffprobe.exe"
python .\render.py --delivery-only --ffprobe "$bin\ffprobe.exe"
node .\verify_dom.mjs 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' .\apps\use-keyboard-invoice-triage.html .\evidence.json .\.browser-profile
python ..\..\tests\test_frame_0002_02.py -v
```

The renderer uses only the Python standard library and streams deterministic
RGB24 frames to a single-threaded FFV1 Matroska master. The existing compiler
produces single-threaded H.264/yuv420p MP4 and VP9/yuv420p WebM derivatives
tagged limited-range BT.709. `delivery.json` records byte counts, SHA-256
digests, codec probes, and stable frame samples.

## Guided film timeline

The 18-second, 960×540 film states the expected fixture total, visualizes the
keyboard focus path, shows the correction and exported 196.25 field, displays
the negative-amount error beside a disabled export control, and finishes on
the exact restored fixture. It has no audio, external assets, or runtime
network dependency.
