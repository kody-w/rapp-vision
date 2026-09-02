# Why the Grid Overflows

Candidate frame 04 answers the `learn-grid-overflow` commission with one
original paired publication. The 18-second guided film and standalone live
lesson share the same measured sequence:

1. At a simulated 320 px viewport, the restored fixture reports
   `scrollWidth 612 > clientWidth 320`.
2. `minmax(0, 1fr)` removes the track's automatic minimum and `min-width: 0`
   lets the payload shrink.
3. The live readouts report `320 = 320` and `1280 = 1280`.
4. **Restore broken CSS** brings back the unbreakable token and horizontal
   scrolling.
5. The exact reset restores the source, selects 320 px, and scrolls to `x = 0`.

The HTML has no external resources or network capabilities. It exposes
`window.gridOverflowLesson.snapshot()` (also aliased as `window.tinySystem`)
and embeds the three exact contract snapshots used by `evidence.json`.

## Rebuild

Run from the repository root in PowerShell:

```powershell
$bin = "C:\Users\kowildfe\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-essentials_build\bin"
$root = "candidate-frame-0002\learn-grid-overflow"
python "$root\render.py" --ffmpeg "$bin\ffmpeg.exe"
python scripts\compile_publications.py build "$root\channel.production.json" --ffmpeg "$bin\ffmpeg.exe" --ffprobe "$bin\ffprobe.exe"
python "$root\build_delivery.py" --ffprobe "$bin\ffprobe.exe"
python scripts\validate_publications.py --ffprobe-local "$root\channel.json"
python -m unittest tests.test_frame_0002_04 -v
```

`render.py` uses only the Python standard library and streams fixed RGB24
frames into a single-threaded, bit-exact FFV1 Matroska master. The existing
publication compiler creates H.264 MP4 and VP9 WebM derivatives with explicit
BT.709 tags. `delivery.json` binds the source, thumbnail, master, compiled
channel, and both delivery encodes by SHA-256.
