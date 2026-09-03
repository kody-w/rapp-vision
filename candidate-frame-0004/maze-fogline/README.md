# Candidate frame 0004-01 · Fogline Survey

**Fogline Survey** answers commission `play-seeded-maze-return` with one
paired 24-second publication: a deterministic 960×540 film and a standalone
single-file maze. The interpretation is top-down fog of war: only surveyed
ground and local openings are revealed, a compass preserves bearing, a mint
trail records accepted movement, and the violet exit beacon remains marked.

The primary interaction is direct Arrow/WASD play. The authored live replay
sends each move as an individual semantic key event. It contains no replay,
auto-solve, or route-injection action.

## Canonical fixture

- Seed: `RAPP-42`
- Grid: `6 × 6`
- Entrance: `(0,0)`, initially facing north
- Exit: `(5,3)`, marked even under fog
- Generator: recursive backtracker from `(0,0)`
- Candidate order: north, east, south, west
- Seed hash: FNV-1a 32-bit over UTF-8
- PRNG: unsigned-integer Mulberry32
- Topology serialization: seed, `6x6`, then row-major `x,y:NESW-openings`
  cells joined with semicolons
- SHA-256 topology digest:
  `126bf70440d3ef542c8dc97251726994e0f23422675e831f93309235ae085eda`
- BFS shortest route, exactly 18 accepted moves:
  `S E E S S W W S S E N E E S E N N E`
- Deterministically selected trap: latest off-route branch before the exit,
  with N/E/S/W tie-breaking; for RAPP-42 this is west from route step 14 into
  `(2,5)`
- Marked 20-move detour:
  `S E E S S W W S S E N E E S W E E N N E`

`render.py`, the browser app, the verifier, and the focused test each
implement or independently derive the generator, serialization, digest, BFS
route, and trap. The live document displays the seed, full digest, current
steps, best projected finish, and reference length. It never prints the route
in visible DOM before play; reference length 18 is intentionally visible.

## One earned bearing

A run earns one survey charge after four accepted moves. The charge does
nothing automatically. Activating **Request earned one-step hint** reveals
only the next BFS move from the current cell, records `assistance.used: true`,
increments the request count once, and is then spent. Any following accepted
move clears the displayed bearing.

The canonical detour demonstration reaches route step 14, explicitly requests
the one-step `E` bearing, then deliberately takes the valid marked `W` branch.
At entry, the best projected finish becomes 20 while the exit remains marked.
Returning and completing opens the exit in a final 20 accepted moves.

## Exact return and arbitrary seeds

**Restart same seed** reconstructs the opening state for the active fixture:
same seed and digest, entrance `(0,0)`, north, zero steps, closed marked exit,
empty trail, and no assistance.

The seed field accepts any text containing 1–64 UTF-8 bytes and no control
characters. A valid value recomputes maze, digest, BFS length, and trap. The
authored handoff loads `FOG-7`, whose digest and reference length differ from
RAPP-42. Invalid text remains editable while the last accepted fixture and
all game fields are preserved. This rejection is demonstrated before the
multi-seed **YOUR TURN** handoff.

## Editorial sequence

1. Establish RAPP-42, its complete digest, fogline, compass, marked exit, and
   reference length 18.
2. Complete the computed shortest route with 18 individual Arrow-key events,
   unassisted.
3. Restart exactly.
4. Walk to the surveyed branch, earn and explicitly request one bearing.
5. Take the real west trap and complete with projected and final length 20.
6. Restart to entrance, north, zero, closed exit, and empty trail.
7. Reject a 65-byte seed while preserving the accepted RAPP-42 state.
8. Generate `FOG-7` and hold a clear multi-seed **YOUR TURN** invitation.

The film uses the same phases and facts. Critical live content has generous
bottom scroll clearance, so the player lower third does not obstruct actions
or checkpoints. The assembled page has no minimum-width clipping and is
checked throughout at desktop and exactly 390 CSS pixels.

## Bundle

| Path | Purpose |
| --- | --- |
| `apps/maze-fogline.html` | Offline single-file maze, generator, reducer, responsive fog renderer, and `window.foglineSurvey.snapshot()` contract |
| `render.py` | Standard-library deterministic model, RGB24 renderer, FFV1 writer, thumbnail/evidence/delivery generator, and release checker |
| `masters/maze-fogline.mkv` | 24-second, 12 fps, lossless FFV1 `bgr0` master |
| `media/maze-fogline.mp4` | Compiler-produced H.264 `yuv420p` BT.709 delivery |
| `media/maze-fogline.webm` | Compiler-produced VP9 `yuv420p` BT.709 delivery |
| `channel.production.json` | Production source and `rapp-vision-live/1.0` semantic replay |
| `channel.json` | Exact compiler transformation with paired sources |
| `thumbs/maze-fogline.svg` | Original self-contained fogline thumbnail |
| `snapshots/canonical-states.json` | Opening, optimal, hint, trap, detour, reset, invalid-preserved, and handoff states |
| `evidence.json` | Commission, fixture, replay, browser, film, rights/privacy, and source SHA-256 evidence |
| `delivery.json` | Source/media SHA-256 bindings plus fresh codec, color, frame-rate, size, and duration probes |
| `verify_dom.mjs` | Dependency-free real-Chromium timed replay and responsive state/geometry verifier |

The app has no network code, external assets, external data, audio, analytics,
personal data, customer data, credentials, or secrets.

## Reproduce

Tool discovery honors `RAPP_FFMPEG`, `RAPP_FFPROBE`, and `RAPP_BROWSER`,
their RAPP Vision aliases, PATH, and common portable Windows/macOS/Linux
locations. Explicit arguments take precedence.

From this candidate directory:

```powershell
$tools = python .\render.py tools | ConvertFrom-Json
$env:PATH = "$([IO.Path]::GetDirectoryName($tools.ffprobe));$env:PATH"
python .\render.py artifacts
python .\render.py render --ffmpeg $tools.ffmpeg
python ..\..\scripts\compile_publications.py build .\channel.production.json `
  --ffmpeg $tools.ffmpeg --ffprobe $tools.ffprobe
python .\render.py artifacts
python .\render.py delivery --ffprobe $tools.ffprobe
python .\render.py check --ffprobe $tools.ffprobe
node .\verify_dom.mjs --browser $env:RAPP_BROWSER
```

From the repository root:

```powershell
python -m unittest discover -s tests -p "test_frame_0004_01.py" -v
python scripts\compile_publications.py check `
  candidate-frame-0004\maze-fogline\channel.production.json
python scripts\validate_publications.py --ffprobe-local `
  candidate-frame-0004\maze-fogline\channel.json
git diff --check
```

The focused test normalizes CRLF for source parsing but keeps generated raw
LF contracts strict. It independently regenerates topology and BFS results,
accepts either the exact open commission or its future exact fulfillment,
binds committed delivery hashes separately from two same-toolchain rebuilds,
decodes one committed frame from every declared film phase, compares the
lossy deliveries, runs compiler/validator/release checks, and executes both
desktop and 390 px real-browser replays when the declared tools are available.

## Rights and privacy

All maze code, prose, interface graphics, bitmap typography, SVG artwork, and
film frames were created for this candidate. The fixture is algorithmic and
contains no people, real places, copied imagery, private information, or
third-party runtime material. No approval is self-asserted; the commission's
independent technical and curation review quorum remains external.
