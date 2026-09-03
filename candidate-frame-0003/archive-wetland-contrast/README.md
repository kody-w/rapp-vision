# Archive Wetland Contrast

This candidate answers commission `explore-archive-map-contrast` with one
paired RAPP Vision publication: **Read the Wetland Twice**.

The fixture is a wholly synthetic wetland plot survey running west 1000 to
east 1600 and south 2000 to north 2400. The exact evidence label remains
`SYN E 1000–1600 / N 2000–2400`. It contains exactly 24 records and two
available archive sheets:

- `1990 field sheet`
- `2020 field sheet`

An independent categorical comparison yields exactly these seven changed
record IDs, in lexical order:

```text
WL-002, WL-005, WL-009, WL-012, WL-016, WL-020, WL-023
```

The canonical export is compact UTF-8 JSON plus one LF. Its SHA-256 is:

```text
fe05f5f52ddd174f2756d865e6e1baea3c0aa5497e8052ce430d1c4c8c1761e6
```

## Paired bundle

- `render.py` is a standard-library-only deterministic RGB24 renderer.
- `masters/explore-archive-map-contrast.mkv` is the 22-second, 960×540,
  12 fps, lossless FFV1 master.
- `media/explore-archive-map-contrast.mp4` is compiler-produced H.264.
- `media/explore-archive-map-contrast.webm` is compiler-produced VP9.
- `apps/explore-archive-map-contrast.html` is a standalone, offline,
  single-file live app with no map tiles or external runtime resources.
- `channel.production.json` retains the master and mandatory
  `rapp-vision-live/1.0` replay.
- `channel.json` is the exact deterministic compiler transformation.
- `evidence.json` binds the fixture, positive path, rejected query, exact
  reset, two viewport replays, rights, privacy, and expected state snapshots.
- `exports/changed-record-ids.json` contains the canonical export bytes.
- `delivery.json` binds every source and media artifact by size and SHA-256.

## Live proof

The replay uses only stable ID selectors and semantic `scroll`, `click`, and
focused `type` actions. It performs the following path:

1. Compare 1990 with 2020.
2. Filter to seven changed records.
3. Inspect `WL-016`, zoom once, and pan east once while the focused station
   remains inside the map window.
4. Export the exact sorted ID list.
5. Type the supplied impossible range `1880 → 1885`.
6. Distinctly reject the empty query with `queryResultCount: null`; the app
   never presents it as a successful zero-change result and preserves the
   accepted 1990/2020 state and canonical export.
7. Activate **Restore archive view**.
8. End on **YOUR TURN — choose any WL plot; arrows pan; −/+ zoom; Compare
   reruns; Export binds the result.**

Reset returns all 24 records, 1990/2020, seven changes, filter `all`, no
focused record, pan `0,0`, zoom `1.00`, and the expected export digest. After
the replay, every record button and each pan/zoom control remains available
for viewer takeover.

The live app has no minimum-width clipping: its assembled document fits a real
390 px player without horizontal expansion. Comparison controls precede the
map records in DOM and keyboard order. The 24 plot buttons use one roving tab
stop; arrow keys move it and Enter or Space selects. All visible text is at
least 12 px, mobile export IDs and digest are at least 13 px, and spatial
labels use west/east/south/north language while retaining the exact extent.
One sticky legend remains visible throughout:
**rust ring = changed 1990→2020; dark ring = unchanged**.

The film opens immediately with **7 of 24 changed**, carries the same legend
on every frame, holds all seven sorted IDs and the readable digest for four
seconds under **observed from 24 synthetic records**, renders the impossible
range as invalid rather than zero changes, restores exactly, and ends on the
same takeover instruction as live.

Non-integer query text is rejected as `rejected-invalid` without poisoning the
accepted state. The in-app SHA-256 implementation encodes all strings as
UTF-8, and the browser audit checks a non-ASCII digest vector in addition to
the canonical ASCII export.

`verify_dom.mjs` reserves an explicit DevTools port, waits up to 45 seconds
while detecting early browser exit, blocks HTTP(S) and WebSocket traffic via
DevTools, observes every page request, and replays the production manifest at
its authored timestamps in a real Chromium-family browser at 1120 px and
390 px. It requires every activation and checkpoint result to be on-screen,
asserts independent fixture arithmetic plus actual DOM/window state, captures
JavaScript and console errors, verifies unclipped width, readable font sizes,
actual tab order, roving keyboard focus/selection, one full-width map-adjacent
failure notice, persistent legend and final prompt, demonstrates takeover
through a measured map transform, closes the process, verifies browser exit,
and removes its profile.

## Reproduce

From this directory in PowerShell:

```powershell
$tools = python .\render.py --show-tools | ConvertFrom-Json
python .\render.py --ffmpeg $tools.ffmpeg
python ..\..\scripts\compile_publications.py check .\channel.production.json
python ..\..\scripts\compile_publications.py build .\channel.production.json --ffmpeg $tools.ffmpeg --ffprobe $tools.ffprobe
python .\render.py --delivery-only --ffprobe $tools.ffprobe
node .\verify_dom.mjs
python ..\..\tests\test_frame_0003_09.py -v
```

Tool discovery honors `RAPP_FFMPEG`, `RAPP_FFPROBE`, and `RAPP_BROWSER`,
their `RAPP_VISION_*` aliases, normal environment/PATH names, and common
portable Windows, macOS, and Linux locations. Explicit command arguments take
precedence.

The focused test always validates schema, source shape, complete delivery
hash coverage, stale-hash rejection, rights, privacy, exact fixture
arithmetic, raw canonical LF bytes, UTF-8 digest behavior, and CRLF-tolerant
source parsing.
When browser, FFmpeg, and FFprobe are discoverable, it also runs real-browser
replay, codec probes, compiler checks, a clean deterministic master rebuild,
paired recompilation, and byte-for-byte diff checks.

## Rights and privacy

All names, records, coordinates, observations, interface code, vector drawing,
renderer output, and film frames were created for this candidate. There are no
map tiles, network calls, copied imagery, real locations, personal data,
credentials, secrets, or fabricated credential-like tokens.
