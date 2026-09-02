# Production compiler

`scripts/compile_publications.py` turns local production masters into the paired
media required by `rapp-vision-channel/2.0`. It uses only the Python standard
library; `ffmpeg` and `ffprobe` are external runtime tools.

## Source contract

Start from `template/channel.production.json`. The
`rapp-vision-production/1.0` contract mirrors a v2 channel except that every
publication:

- has `production.master`, a local path relative to the production JSON;
- has no `sources`; and
- still contains its required inline `rapp-vision-live/1.0` replay.

Channel, publication, and live-replay metadata is preserved. The compiler
removes the compiler-only `production` object and writes exactly these sources,
in this order:

```json
[
  {"src": "media/<id>.mp4", "type": "video/mp4"},
  {"src": "media/<id>.webm", "type": "video/webm"}
]
```

The static source shape is documented by `channel.production.schema.json`.
After transformation, `scripts/validate_publications.py` is the semantic
authority, so existing duration, chapter, source, and live-replay rules apply.

## Commands

The source argument may be a production JSON file or a directory containing
`channel.production.json`. Output defaults to the source file's directory.

```console
python scripts/compile_publications.py check path/to/channel.production.json
python scripts/compile_publications.py plan path/to/channel.production.json --output dist
python scripts/compile_publications.py build path/to/channel.production.json --output dist
```

Use custom executable names or paths when needed:

```console
python scripts/compile_publications.py build . --ffmpeg ffmpeg.exe --ffprobe ffprobe.exe
```

- `check` validates the source, every master path, and the transformed v2
  channel without writing.
- `plan` performs the same checks and prints sorted, deterministic JSON with
  the exact ffmpeg and ffprobe argument arrays that `build` will execute.
- `build` creates H.264/AAC MP4 and VP9/Opus WebM staging files, probes the
  video codecs, publishes complete media pairs, and atomically replaces
  `channel.json` last.

Generated JSON is UTF-8, sorted, indented with two spaces, and LF-terminated.
It contains no timestamps, tool versions, or generated identifiers.
Both encoders run single-threaded with bit-exact muxer and codec flags, and
VP9 row-level threading is disabled. Repeated builds are byte-stable with the
same FFmpeg build and inputs; codec bytes are not promised across FFmpeg
versions. Both outputs explicitly declare BT.709 primaries, transfer, matrix,
and limited range; at most the first optional audio stream is carried.

Before encoding, the build probes each master. Untagged RGB masters are treated
as display-referred RGB and converted through FFmpeg's BT.709 matrix and
limited-range transform. YUV masters must already declare BT.709 primaries,
transfer, and matrix (full or limited range); other or unknown YUV color
descriptions are rejected rather than relabelled. Output probes verify every
BT.709 field after encoding.

## Path and failure safety

Masters must be regular files inside the source directory. URL, absolute,
backslash-containing, control-character, encoded-separator (`%2F`/`%5C`), and
escaping paths are rejected. Resolving a symlink outside the source directory
is also rejected.

Generated paths are checked with conservative case-insensitive filesystem
semantics. Publication ids that collide by case, map to reserved Windows
device names, or would make an output replace the production source or any
master are rejected before encoding.

Encoding and probing happen under `.rapp-vision-production-stage`. Nothing is
published until both formats for every publication pass their codec probes.
On an encoding, probe, or publish failure, staging files are removed, newly
installed media is rolled back, and the previous `channel.json` remains
untouched. If a rollback itself fails, the staging directory and its recovery
copies are deliberately preserved and their path is printed. A successful
build atomically installs `channel.json` only after all media pairs are in
place. Every destination, including `channel.json`, is backed up and registered
as potentially replaced before the OS rename starts, so an interrupt delivered
immediately after a completed rename is still recoverable.
