# Why the Grid Overflows

Candidate frame 04 answers the `learn-grid-overflow` commission with one
original paired publication. The 18-second guided film and standalone live
lesson share the same measured sequence:

1. At a simulated 320 px viewport, the restored fixture reports
   `scrollWidth 612 > clientWidth 320`.
2. The payload contains a 480 px intrinsic rail. Its default
   `min-width: auto` contributes that min-content size to the plain `1fr`
   track's automatic minimum.
3. Changing **only** `#payload { min-width: auto; }` to
   `#payload { min-width: 0; }` shrinks the payload track from 480 px to
   174 px. The `1fr` track, `overflow: clip`, and 480 px rail do not change.
4. Real Edge/Chrome DOM readouts report `320 = 320` and `1280 = 1280`.
5. **Restore broken CSS** brings back the automatic minimum and horizontal
   scrolling.
6. The exact reset restores the source, selects 320 px, and sets the real DOM
   `scrollLeft` to `x = 0`.

The HTML has no external resources or network capabilities. It exposes
`window.gridOverflowLesson.snapshot()` (also aliased as `window.tinySystem`)
and embeds the three exact contract snapshots used by `evidence.json`.
Measurements in those snapshots come from `scrollWidth`, `clientWidth`,
`scrollLeft`, computed `min-width`, and element widths in the browser—not from
a hard-coded sizing model.

## Rebuild

Run from the repository root. Candidate scripts and tests discover tools from
`FRAME_FFMPEG`, `FFMPEG`, `FRAME_FFPROBE`, `FFPROBE`,
`FRAME_BROWSER`, `BROWSER`, PATH, and common Windows/macOS/Linux install
locations. The compiler accepts the resolved executables explicitly:

```powershell
$root = "candidate-frame-0002\learn-grid-overflow"
$ffmpeg = $env:FRAME_FFMPEG
$ffprobe = $env:FRAME_FFPROBE
if (-not $ffmpeg) { $ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source }
if (-not $ffprobe) { $ffprobe = (Get-Command ffprobe -ErrorAction Stop).Source }
python "$root\render.py" --ffmpeg "$ffmpeg"
python scripts\compile_publications.py build "$root\channel.production.json" --ffmpeg "$ffmpeg" --ffprobe "$ffprobe"
python "$root\build_delivery.py" --ffprobe "$ffprobe"
python scripts\validate_publications.py --ffprobe-local "$root\channel.json"
python -m unittest tests.test_frame_0002_04 -v
```

`render.py` uses only the Python standard library and streams fixed RGB24
frames into a single-threaded, bit-exact FFV1 Matroska master. The existing
publication compiler creates H.264 MP4 and VP9 WebM derivatives with explicit
BT.709 tags. `delivery.json` binds the source, thumbnail, master, compiled
channel, and both delivery encodes by SHA-256.

Schema, source-contract, and SHA-256 checks always run without external tools.
Browser actions, codec probes, and rebuild execution run whenever their tools
are found. In CI—or with `FRAME_0002_04_RELEASE=1`—missing Node,
Edge/Chrome, FFmpeg, or FFprobe is a hard failure rather than a skip.
