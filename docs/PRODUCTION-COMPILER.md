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

## Path and failure safety

Masters must be regular files inside the source directory. URL, absolute,
backslash-containing, control-character, encoded-separator (`%2F`/`%5C`), and
escaping paths are rejected. Resolving a symlink outside the source directory
is also rejected.

Encoding and probing happen under `.rapp-vision-production-stage`. Nothing is
published until both formats for every publication pass their codec probes.
On an encoding, probe, or publish failure, staging files are removed, newly
installed media is rolled back, and the previous `channel.json` remains
untouched. A successful build atomically installs `channel.json` only after all
media pairs are in place.
