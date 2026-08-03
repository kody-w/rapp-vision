# OpenRappter Training — content plan

**Status: this document is a PLAN. Nothing in it has been recorded.**

Everything in `channel.json` today is verified — the commands were run before they were
written down. Everything in *this* file is the opposite: it is the list of work that has
**not** been done, written down so the gap is visible instead of implied. Do not cite this
file as evidence that anything exists.

Current state of this directory:

```
openrappter-training/
├── channel.json      # 8 entries, all card-only, sources: [], posters inline as SVG data URIs
└── CONTENT_PLAN.md   # this file
```

Zero binary assets. Zero media files. That is deliberate and it is also why there is
something left to do.

---

## Why there is no video yet, and why there are no live app scenes either

Two different gaps. Only the first one is fixable by recording.

**1. Screen capture: simply not done.** No terminal capture has been recorded for any of
the eight modules. This is the gap this plan closes.

**2. Live app scenes: refused, permanently, and not part of this plan.** RAPP Vision's
strongest format is a `live` scene that drives a real app in a same-origin iframe
(`README.md`, "Scenes"). This channel cannot use it, for the reason recorded in
`channel.json`'s `_why_no_app_scenes` field: OpenRappter's two interactive web surfaces
both open a WebSocket to a gateway on the **viewer's** machine (`openrappter/index.html`
line 309 → `ws://<host>:18790`; `openrappter/dojo.html` line 76 → `ws://127.0.0.1:18790`),
which a hosted page cannot assume exists. The other web surfaces are static prose or
cross-origin fetchers. So: no `app` scene will ever be added here. Adding one would be a
demo that fails on every machine but the author's.

What that leaves is the honest option — **capture the terminal**, which is where all eight
modules actually happen.

---

## The shape of the target

Per the spec in `../README.md` and `../template/channel.json`:

- An entry is treated as **live** when it has a `live` block and **no** `sources`. Adding
  `sources` to an entry turns it into a normal video entry, so the card script and the
  recording are mutually exclusive **per entry** unless the recording is published as a
  separate entry.
- Every `src` and `thumb` resolves **relative to `channel.json`'s own URL**. Media for this
  channel goes in `openrappter-training/media/`, posters in `openrappter-training/thumbs/`.
- **Ship WebM alongside MP4.** Not for coverage — `README.md` is explicit that headless
  Chromium has no H.264 decoder, so the WebM is what makes the channel *verifiable in CI*.
  An MP4-only entry cannot be proven to play by the same headless check that proves the
  rest of the network.

Recommended approach, so nothing already-verified is lost: **keep the eight card entries
exactly as they are** and add recorded entries alongside them (`…-m1-…-screen`, etc.), or
add `sources` only to a module whose card script the recording fully replaces. The card
scripts are the lesson; a recording that says less than the card is a downgrade.

---

## What still needs recording, per module

Each module's card scenes already name the exact commands, in order, with the timings the
channel commits to. A capture is finished when it shows those commands being run and their
real output. Times below are the existing scene marks in `channel.json` — the recording
should land within a second or two of them so the published `chapters` stay honest.

### Module 1 — Install and prove it is running (60 s)
Record, from a **fresh clone with nothing pip-installed**:
1. `git clone …` and `cd openrappter/python` (t=8)
2. `python3 -m openrappter.cli --status` — must show `agents_loaded: 17` (t=16)
3. The `WARNING: Failed to load .../google_voice_agent.py: No module named 'agents'` line —
   **do not scroll past it or trim it**; it is the module's point (t=25)
4. `"copilot_available": false` visible in the same output (t=34)
5. Optional `pip install .` (t=43)

Capture requirement: a clean `$HOME`, or the `agents_loaded` count will not reproduce.

### Module 2 — A memory file you own (60 s)
1. `--exec ManageMemory "the deploy command is npm run deploy"` (t=8)
2. `--exec ContextMemory "deploy"` (t=17)
3. `--task "remember that Python works"` — the keyword router, no Copilot (t=26)
4. `cat ~/.openrappter/memory.json` — the file on disk is the whole argument (t=35)
5. The `OPENRAPPTER_HOME` doc bug: show it set, then show the memory still landing in
   `~/.openrappter` (t=44)

Capture requirement: start from an empty or freshly-moved-aside `~/.openrappter` so the
memory ids on screen match a first run. **Scrub the recording** — this writes to a real
home directory, and `memory.json` will contain whatever else is in it.

### Module 3 — Real work with zero AI (62 s)
1. `--exec Git "status"` → the `"No action specified"` error, shown **first** (t=8)
2. `--exec Shell "ls"` (t=18)
3. A Python REPL / script showing `CodeReviewAgent().execute(action="review", …)` (t=27)
4. `GitAgent().execute(action="status")` returning structured JSON (t=37)
5. Reading `metadata['parameters']['properties']['action']['enum']` in the REPL (t=45)

Capture requirement: run in a repo with a **boring, non-sensitive** `git status`.

### Module 4 — The brainstem (68 s)
Needs **two panes** (or a split capture): the server in one, curl in the other.
1. `PORT=7099 python3 -m openrappter.brainstem` starting (t=8)
2. `curl -s 127.0.0.1:7099/health` (t=17)
3. The 18-vs-17 agent count difference against the CLI (t=26)
4. `POST /agents/import -F "file=@hello_agent.py"` and the agent appearing live (t=36)
5. A `POST /chat` round trip (t=47)

Capture requirement: the entry's own last scene ("What is NOT proven here") stays true —
the **authenticated Copilot `/chat` loop is unverified**. Either record it working and
promote it out of the unverified list in Module 8, or record the unauthenticated response
and leave the caveat in place. Do not record a mock.

### Module 5 — Write your own agent (66 s)
Screen-record an editor, not a terminal, for the first half.
1. Typing the four-line guarded import (t=8)
2. Adding `__manifest__` (t=19)
3. Both load paths — drop-in file, and POST (t=29)
4. `self.get_signal('temporal.time_of_day')` returning a real value (t=38)
5. A `data_slush` return being read downstream (t=48)
6. The two broken tutorial commands failing on camera (t=57)

Capture requirement: the editor window must contain nothing but the agent file. Full-screen
editors leak file trees, branch names and other repos.

### Module 6 — The conformance gate (64 s)
1. `python3 conformance.py` → the real `4 passed, 4 failed, 1 skipped` (t=8)
2. Scrolling the R1/R6/R7/R8 passes (t=18)
3. Each failure read aloud/on screen: R2+R3 manifest, R4 under-declare, R5 over-declare
   (t=27, 37, 47)

Capture requirement: **record it red.** The scene note in `channel.json` says it out loud —
"Do not film a green screenshot you did not produce." Re-verify the 4/4/1 split at the
commit being filmed; if `main` has moved, re-measure and update the card before recording,
not after.

### Module 7 — Chaining with no LLM (66 s)
A Python REPL or a single script run three times.
1. Manual `upstream_slush` handoff (t=8)
2. `AgentChain().add_step(...)` (t=18)
3. `AgentChain([a, b])` raising `AttributeError` — the failure is the lesson (t=28)
4. A Pipeline spec validating (`valid: true, stepCount: 2`) and running to `completed`
   (t=38, 48)

### Module 8 — Read the map before you bet (68 s)
1. `python3 -m pytest tests -q --continue-on-collection-errors` on a clean clone, run to
   completion, with the summary line legible (t=8). **Record the bare
   `python3 -m pytest tests -q` aborting first** — `Interrupted: 7 errors during
   collection` — because the recovery is the teaching moment, and a viewer who runs the
   bare command will hit exactly that.
2. `ROADMAP.md` line 13 and its parity table, on screen (t=18)
3. The spine's "parity target" line, quoted in situ (t=28)
4. The four disagreeing agent counts, each in its own file (t=38)
5. `PROMPTS.md` scrolled far enough that the prose-not-code nature is self-evident (t=48)
6. The three-command trust check (t=58)

Capture requirement: **re-run the tests at the commit being filmed and update the counts in
the description, the t=8 card, the t=8 chapter label AND the base64 poster SVG together.**
Those four places have already drifted apart once. They are the highest-risk numbers in the
channel because they are its headline.

---

## How to record

Not yet chosen, and deliberately not asserted here. Three constraints that any choice has
to satisfy:

1. **Deterministic environment.** Fresh clone at a named commit, clean `$HOME` for
   Modules 1 and 2, nothing pip-installed unless the module says otherwise. Record the
   commit SHA in the entry description, as the current entries already do (`d314ba7`).
2. **WebM + MP4 output** (see above — the WebM is the CI-verifiable one).
3. **Nothing personal on screen.** These are terminal captures on a real machine:
   hostname, username in the prompt, shell history, editor file trees, `git status` output
   and `~/.openrappter/memory.json` contents all leak. Use a scratch user or a
   deliberately-blanked prompt, and review every frame before publishing.

OpenRappter ships a `DemoRecorder` agent, but it is listed in Module 8's explicit
NOT-VERIFIED set — it has not been exercised. Do not assume it does this job until someone
runs it.

---

## Definition of done, per module

- [ ] Recorded at a named commit, on a clean environment
- [ ] Reviewed frame by frame for leaked personal/host data
- [ ] WebM **and** MP4 in `openrappter-training/media/`, poster in `thumbs/`
- [ ] Entry's `sources` populated, `chapters` re-checked against the real timeline
- [ ] Every number spoken or shown re-measured at that commit — including, for Module 8,
      the poster SVG
- [ ] Channel loads in the player with the new entry's poster and media resolving

Until all six boxes are ticked for a module, that module stays card-only, which is a
complete lesson on its own. That is the trade this channel is making on purpose.
