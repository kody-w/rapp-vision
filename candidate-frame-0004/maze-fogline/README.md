# Candidate frame 0004-01 · Fogline Survey

**Fogline Survey** answers commission `play-seeded-maze-return` with one
paired 24-second publication: a deterministic 960×540 film and a standalone
single-file maze. The interpretation is top-down fog of war: only surveyed
ground and local openings are revealed, a compass preserves bearing, a mint
trail records accepted movement, and the violet exit beacon remains marked.

The primary interaction is direct Arrow/WASD play. The authored live replay
sends each move as an individual semantic key event. It contains no replay,
auto-solve, or route-injection action.

**Copy / export challenge** creates a portable offline fragment. Its decoded
JSON has exactly three keys: `seed`, `topologyDigest`, and `referenceLength`.
It contains no route, trail, position, or assistance history. Opening a valid
fragment regenerates and validates all three values, then starts at zero.
Malformed, extra-field, or mismatched fragments preserve the accepted game
and surface a visible error.

Rejected seed text sets `aria-invalid="true"` on the seed input. Rejected
challenge fragments set it on the fragment field. A valid edit, valid
fragment/load, or exact reset clears the associated invalid state without
silently changing the accepted game.

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
The verifier also searches the rendered markup and Chromium accessibility
tree. The app exposes no fixture, topology, route, or reducer API on `window`.

## One earned bearing

A run earns one survey charge after four accepted moves. The charge does
nothing automatically. Activating **Request earned one-step hint** reveals
only the next BFS move from the current cell, records `assistance.used: true`,
increments the request count once, and is then spent. Any following accepted
move clears the displayed bearing.

A rejected wall changes facing only. It does not increment accepted steps,
earn a charge, consume a displayed one-step bearing, or alter the trail.

Completion always locks the hint control and clears any displayed direction.
An 18-step result remains optimal whether assisted or not, but the assistance
readout and completion panel derive their label from the recorded
`assistanceUsed` state and never describe an assisted run as unassisted.

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
all game fields are preserved.

The independent browser audit additionally generates `FOG-7`, `MIST-Δ`, and
`A|B;C`, checks each recomputed digest and shortest length, completes each
shortest route, enters each computed trap, and finishes each real +2 detour
using CDP-delivered Arrow and WASD input.

## Editorial sequence

1. Establish and export the three-field RAPP-42 offline challenge.
2. Walk to the knot first, explicitly request one bearing, enter the marked
   west trap, and finish at the real `+2` total of 20 with the exit visible.
3. Reset exactly to entrance, north, zero, closed exit, and empty trail.
4. Complete the computed 18-step route unassisted.
5. Reset exactly again.
6. Generate untouched `FOG-7`, export it, show a strong **YOUR TURN**, and
   finish the authored replay with the board focused for movement.

The film follows the same trap-first hierarchy and is captured directly from
`apps/maze-fogline.html?film=1` in Chromium. It therefore uses the live
system/UI-monospace font stack, proof cards, fog board, readouts, notices,
buttons, focus treatment, and handoff component rather than a separate bitmap
approximation. The seed, reference, full 64-character digest, and film
callouts render at 22 source pixels or larger. The opening film frame visibly
shows the selected `#challenge=...` fragment and its copied/ready status.

`snapshots/film-live-continuity.json` binds every declared phase to the live
DOM structure, computed font families, screenshot PNG hash, decoded live RGB
hash, and exact lossless-master RGB hash. Live checkpoints remain partial
state gates inside 1.25-second windows, while actions retain scheduled timing
with a 0.8-second lateness ceiling.

The final FOG-7 handoff overlay cannot receive pointer or tab focus. Film
capture deliberately delays the final focus transition, then waits for both
the untouched handoff state and `#maze-board` focus. Every takeover frame
immediately reasserts board focus and state-gates `activeElement` before its
screenshot, including injected late-focus race frames.

Readiness polling tolerates transient `Runtime.evaluate` failures while
Chromium replaces a navigation context, but remains deadline-bounded and
reports the last failure. Runtime exception/console listeners still fail the
run after readiness, so persistent app faults are never converted to success.

At exactly 390 CSS pixels, the board, four state readouts, D-pad, hint, and
restart occupy a bounded 800-pixel play cluster instead of being distributed
through a 2473-pixel page. The complete document is bounded to 1800 pixels.

## Bundle

| Path | Purpose |
| --- | --- |
| `apps/maze-fogline.html` | Offline maze, private generator/reducer, three-field fragment export/import, responsive fog renderer, and keyboard-first controls |
| `render.py` | Standard-library deterministic model, browser-film orchestrator, thumbnail/evidence/delivery generator, and release checker |
| `render_live.mjs` | Chromium/CDP capture of the actual live app into the lossless FFV1 master |
| `masters/maze-fogline.mkv` | 24-second, 12 fps, lossless FFV1 `bgr0` master |
| `media/maze-fogline.mp4` | Compiler-produced H.264 `yuv420p` BT.709 delivery |
| `media/maze-fogline.webm` | Compiler-produced VP9 `yuv420p` BT.709 delivery |
| `channel.production.json` | Production source and `rapp-vision-live/1.0` semantic replay |
| `channel.json` | Exact compiler transformation with paired sources |
| `thumbs/maze-fogline.svg` | Original self-contained fogline thumbnail |
| `snapshots/canonical-states.json` | Opening, rejected-wall, optimal, hint, trap, detour, reset, invalid-preserved, and handoff states |
| `snapshots/film-live-continuity.json` | Per-phase live DOM/font structure and exact screenshot-to-master pixel bindings |
| `evidence.json` | Commission, fixture, replay, browser, film, rights/privacy, and source SHA-256 evidence |
| `delivery.json` | Source/media SHA-256 bindings plus fresh codec, color, frame-rate, size, and duration probes |
| `verify_dom.mjs` | Dependency-free real-Chromium CDP-input, accessibility, timed replay, alternate-seed, and responsive geometry verifier |

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
python .\render.py render --ffmpeg $tools.ffmpeg `
  --browser $tools.browser --node $tools.node
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

The focused test requires raw checkout bytes to match Git's canonical LF
bytes, normalizes CRLF only for source-text parsing, and hashes unmodified raw
bytes for every artifact binding. It independently regenerates topology and BFS results,
accepts either the exact open commission or its future exact fulfillment,
binds committed delivery hashes separately from two same-toolchain rebuilds,
decodes one committed frame from every declared film phase, proves each
lossless frame is pixel-identical to its live Chromium screenshot, compares
the lossy deliveries, verifies `RAPP_BROWSER` precedence, round-trips and
rejects challenge fragments, checks `aria-invalid`, state-gated replay timing,
and compact mobile geometry, runs compiler/validator/release checks, and
executes both desktop and 390 px direct play with actual CDP input.

## Rights and privacy

All maze code, prose, interface graphics, browser-rendered typography, SVG
artwork, and film frames were created for this candidate. The fixture is algorithmic and
contains no people, real places, copied imagery, private information, or
third-party runtime material. No approval is self-asserted; the commission's
independent technical and curation review quorum remains external.
