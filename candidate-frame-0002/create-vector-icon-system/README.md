# Candidate frame 0002-09 · Create Vector Icon System

`Six Shapes, One Grid` is a complete paired publication for the
`create-vector-icon-system` commission. The standalone live tool edits one
shared stroke token, regenerates six original SVG symbols, exposes the exact
sprite source and SHA-256, rejects one off-grid Pulse anchor without mutating
the accepted export, and restores the complete opening fixture.

## Objective result

- exactly **6** named `<symbol>` elements;
- every symbol has `viewBox="0 0 24 24"`;
- accepted export: `exports/six-shapes.svg`;
- accepted SHA-256:
  `6c32a2cef1a3ee29d398ae4070ec3a92961bb1625b4c5aa98b92e1c9318474f2`;
- reference method: 4 × 4 fixed subpixel round-polyline coverage;
- accepted comparison: **0 / 3,456 pixels, 0.0000% (pass)**;
- off-grid comparison: **51 / 3,456 pixels, 1.4757% (fail)**.

The rejected edit moves one Pulse anchor from `(12,18)` to `(13,17)`. The
changed pixels are highlighted, while the accepted paths, rules, six names,
sprite hash, and last export remain unchanged.

`Restore icon fixture` returns the original path-set digest and 1.5 px shared
stroke, selects Bloom, sets zoom to 800%, clears all overlays, and restores the
passing comparison.

## Package

| Path | Purpose |
| --- | --- |
| `apps/create-vector-icon-system.html` | Standalone accessible creation tool and deterministic reducer |
| `exports/six-shapes.svg` | Inspectable six-symbol accepted export |
| `reference/reference-raster.json` | Coverage digests, method, threshold, measurements, and changed pixels |
| `snapshots/create-vector-icon-system.svg` | Deterministic visual state snapshot |
| `snapshots/state-snapshot.json` | Exact positive, rejected, and reset states |
| `evidence.json` | Commission claims, actions, assertions, rights statement, and frame samples |
| `render.py` | Standard-library RGB renderer and artifact/delivery generator |
| `masters/create-vector-icon-system.mkv` | 15 s FFV1 lossless master |
| `media/create-vector-icon-system.mp4` | H.264 / BT.709 delivery |
| `media/create-vector-icon-system.webm` | VP9 / BT.709 delivery |
| `channel.production.json` | Production authoring source |
| `channel.json` | Compiled paired channel |
| `delivery.json` | Byte counts, SHA-256 values, codecs, color tags, dimensions, and duration |

All icon geometry, reference data, UI, thumbnail, snapshot, and film graphics
are original to this candidate. The HTML makes no network requests and uses no
copied logos, icons, web fonts, or external assets.

## Deterministic rebuild

Run from this directory in PowerShell:

```powershell
$ff = "C:\Users\kowildfe\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-essentials_build\bin"

python .\render.py render --ffmpeg "$ff\ffmpeg.exe"
python ..\..\scripts\compile_publications.py build .\channel.production.json `
  --ffmpeg "$ff\ffmpeg.exe" --ffprobe "$ff\ffprobe.exe"
python .\render.py delivery --ffprobe "$ff\ffprobe.exe"

$env:PATH = "$ff;$env:PATH"
python ..\..\scripts\validate_publications.py --ffprobe-local .\channel.json
python -m unittest ..\..\tests\test_frame_0002_09.py -v
```

The test suite rebuilds the master and both encoded deliveries once inside a
candidate-local scratch directory, compares every resulting digest with the
committed artifacts, and removes the scratch directory.
