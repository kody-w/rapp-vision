# Candidate frame 0002-09 · Create Vector Icon System

`Six Shapes, One Grid` is a complete paired publication for the
`create-vector-icon-system` commission. The standalone live tool edits one
shared stroke token through an authored **2 → 1.5 → 2 px** path, regenerates
all six original SVG symbols after each change, exposes the exact generated
geometry and sprite hashes, rejects one off-grid Pulse anchor without mutating
the accepted export, and restores the immutable 2 px opening reference.

## Objective result

- exactly **6** named `<symbol>` elements;
- every symbol has `viewBox="0 0 24 24"`;
- accepted export: `exports/six-shapes.svg`;
- accepted SHA-256:
  `6c32a2cef1a3ee29d398ae4070ec3a92961bb1625b4c5aa98b92e1c9318474f2`;
- accepted generated-geometry SHA-256:
  `c3df9da99bac96f2876087271bfd278f4f8dde093ed8d0f72b8ef3bad90099ca`;
- immutable reference SHA-256:
  `61744b14a3c1e4f360d77207712e12f33e626259e1ff9eaca7cd46dd5ebd2d46`;
- reference method: independent frozen 2.0 px round-polyline coverage at
  4 × 4 fixed subpixel centers;
- accepted comparison: **0 / 3,456 pixels, 0.0000% (pass)**;
- off-grid comparison: **51 / 3,456 pixels, 1.4757% (fail)**.

The positive live replay starts at the truthful 2 px reference, sets the draft
token to 1.5 px, regenerates all six previews and the sprite, and proves the
generated-geometry hash changes to
`623ba0ea4f9357fc04e406edbf48d301aa26b4a943db98364e4ee9fc09d858bc`
while the sprite changes to
`0dd372e6f87d6e78d6386dcb4b19444e2221e9afef0a9034af4a97d2882edd61`.
It then deliberately returns the token to 2 px, regenerates the exact opening
geometry and sprite bytes, and only then exports the passing reference.

The centerline path-set hash stays stable because this operation edits the
shared stroke token rather than the grid-aligned anchors. The browser runner
independently hashes the rendered geometry, verifies that all six generated
icons change at 1.5 px, and verifies the exact geometry and sprite hashes return
at 2 px. A no-op authored edit therefore fails the replay.

The rejected edit then moves one Pulse anchor from `(12,18)` to `(13,17)`. The
changed pixels are highlighted, while the accepted paths, rules, six names,
sprite hash, and last export remain unchanged.

All supported inputs (`1`, `1.5`, `2`, `2.5`, and `3` px) have deterministic
sprite hashes and independently recomputed raster measurements. In particular,
the former 1.5 px reset differs from the immutable 2 px reference by
**841 / 3,456 pixels, 24.3345%**, so it cannot claim a zero-difference pass.

| Stroke | Generated geometry SHA-256 | Sprite SHA-256 | Difference vs. 2 px reference |
| ---: | --- | --- | ---: |
| 1 | `a02d1be226192fab3fd111837688ce55fe4aef7f26805bafb74738cdfd7932b7` | `c8ca7d61b74ac74269f5878c4edbb939153d3bc845e29aa6e087f6ffefc80e88` | 943 px · 27.2859% · fail |
| 1.5 | `623ba0ea4f9357fc04e406edbf48d301aa26b4a943db98364e4ee9fc09d858bc` | `0dd372e6f87d6e78d6386dcb4b19444e2221e9afef0a9034af4a97d2882edd61` | 841 px · 24.3345% · fail |
| 2 | `c3df9da99bac96f2876087271bfd278f4f8dde093ed8d0f72b8ef3bad90099ca` | `6c32a2cef1a3ee29d398ae4070ec3a92961bb1625b4c5aa98b92e1c9318474f2` | 0 px · 0.0000% · pass |
| 2.5 | `842f482325b9c296fff49c103bce66a3d5055669f186a62f0f1b0be30294ddd8` | `019cd1a5234d86972d7ee16f38074b15893532c56db07a31b66d75fb6d445e85` | 904 px · 26.1574% · fail |
| 3 | `f67480dfae7e089bb930b61c8ace0d9af39a7d1b92df98d634a7e9cb7ae86df7` | `be4e159c82e877643862a0bc53ee2590dc1305ec843b0c97679144f4e273b223` | 946 px · 27.3727% · fail |

`Restore icon fixture` now returns the exact 2 px immutable reference, selects
Bloom, sets zoom to 800%, clears all overlays, and restores the truthful
zero-difference comparison.

## Package

| Path | Purpose |
| --- | --- |
| `apps/create-vector-icon-system.html` | Standalone accessible creation tool and deterministic reducer |
| `exports/six-shapes.svg` | Inspectable six-symbol accepted export |
| `reference/reference-raster.json` | Immutable per-icon coverage bytes and digests for the 2 px reference |
| `snapshots/create-vector-icon-system.svg` | Deterministic visual state snapshot |
| `snapshots/state-snapshot.json` | Exact positive, rejected, and reset states |
| `evidence.json` | Commission claims, supported-stroke measurements, browser replay contract, rights statement, and frame samples |
| `render.py` | Standard-library RGB renderer and artifact/delivery generator |
| `masters/create-vector-icon-system.mkv` | 15 s FFV1 lossless master |
| `media/create-vector-icon-system.mp4` | H.264 / BT.709 delivery |
| `media/create-vector-icon-system.webm` | VP9 / BT.709 delivery |
| `channel.production.json` | Production authoring source |
| `channel.json` | Compiled paired channel |
| `delivery.json` | Byte counts, SHA-256 values, codecs, color tags, dimensions, duration, immutable reference, state snapshot, and docs |

All icon geometry, reference data, UI, thumbnail, snapshot, and film graphics
are original to this candidate. The HTML makes no network requests and uses no
copied logos, icons, web fonts, or external assets.

## Deterministic rebuild

Run from this directory in PowerShell:

```powershell
$ffmpeg = python -c "import render; print(render.resolve_binary('ffmpeg', 'ffmpeg'))"
$ffprobe = python -c "import render; print(render.resolve_binary('ffprobe', 'ffprobe'))"

python .\render.py render --ffmpeg $ffmpeg
python ..\..\scripts\compile_publications.py build .\channel.production.json `
  --ffmpeg $ffmpeg --ffprobe $ffprobe
python .\render.py delivery --ffprobe $ffprobe

$env:PATH = "$(Split-Path $ffprobe);$env:PATH"
python ..\..\scripts\validate_publications.py --ffprobe-local .\channel.json
Set-Location ..\..
python -m unittest discover -s tests -p "test_frame_0002_09.py" -v
```

The resolver checks an explicit argument, `FFMPEG` / `FFPROBE` environment
variables, `PATH`, and Windows WinGet FFmpeg installations without embedding a
username or package version.

The test suite keeps all pure digest checks active regardless of media-tool
availability. It also launches a real Chromium-family browser, drives the
authored live selectors, asserts the 2 → 1.5 → 2 stroke transition, independently
hashes the six browser-generated geometries and sprite source at each positive
checkpoint, exercises every nondefault supported stroke, fails on no-op edits
or browser exceptions, independently rasterizes SVG geometry against the
frozen reference, rebuilds the master and both deliveries in a candidate-local
scratch directory, and removes every scratch artifact.
