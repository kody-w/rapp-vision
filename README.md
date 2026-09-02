# RAPP Vision

**A local-first YouTube.** One HTML file. No server, no database, no account, no build step.
Anyone can run a channel by publishing a `channel.json` to a public repo.

**Live:** https://kody-w.github.io/rapp-vision/

---

## What makes it different

Every new RAPP Vision publication is one work with **both** layers:

| | Guided video | Live replay |
|---|---|---|
| What ships | `.mp4` + `.webm` | a few KB of JSON |
| Size on disk | ~26 MB | ~4 KB |
| Purpose | newcomer orientation; the default watch mode | **the real app, running now, being driven** |
| Remixable | no | yes — pause, take the wheel, fork the script |
| Works offline | yes (after cache) | yes (it's just the app) |

A live replay is a **script of interactions**. The player loads the actual
application in an iframe and replays the recorded gestures on a clock — with
play, pause and seek. The same watch permalink defaults to the encoded guided
video and exposes an obvious **Try live replay** / **Watch guided video** switch.

That's the entire pitch: **a guided video that is also a program.**

The invariant is constitutional, not advisory. New static-only, replay-only,
MP4-only, and WebM-only entries are rejected. See
[`PUBLICATION_POLICY.md`](PUBLICATION_POLICY.md).

---

## What's on it

The default registry includes pre-constitution material in several formats.
Those exact channel URL + publication id identities remain playable through a
frozen legacy allowlist whose normalized publication objects are SHA-256
pinned. A `pull_request_target` gate executes the verifier from the trusted base
checkout—not the proposed branch—and protected pushes compare against
`github.event.before`. Changing the validator or allowlist in the same
contribution therefore cannot self-authorize v1 content. These are examples of
the network's history, not templates for new publication:

The trust root is installed in two pushes: first only the protected workflow
and minimal verifier, then the exact policy bytes whose SHA-256 is baked into
that verifier. See [`PUBLICATION_POLICY.md`](PUBLICATION_POLICY.md).

Scheduled snapshot publishers also respect protected `main`: they update stable
automation branches and open review-ready pull requests. See
[`docs/AUTOMATION-PRS.md`](docs/AUTOMATION-PRS.md).

| Channel | | What it is |
|---|---|---|
| **Tiny Systems** | ▦ | Three deterministic micro-lessons about an interlock, an accessibility boundary, and an arithmetic gate. Each film teaches the rule; each live replay proves acceptance, visible rejection, preserved state, and exact reset. |
| **Oil Field season** | 🛢️ | Ten independent current-contract channels spanning botanical documentary, portrait gameplay, investigation, physics, cartography, future news, repair, music, synthetic nature, and criticism. Every film teaches first; every replay exposes a positive path, visible failure, and reset. |
| **Frame Chains** | ⛓️ | The first current-contract channel: five paired publications combining newcomer-first encoded films with live executable proofs across ten synthetic worlds. |
| **Rooms** | 🕯️ | Nine ambient places that do not exist — a canoe at dawn, a cabin under the aurora, a cave lit by larvae. Slow TV where the rain is simulated, so it never falls the same way twice. |
| **Arcade** | 🕹️ | Games and emulators, booted cold and played live. Including one entry that stops scripting halfway through and hands you the keyboard. |
| **The Workbench** | 🛠️ | A DAW, a vector editor, a spreadsheet, an 808 — driven live. A product demo you can interrupt is a different object from one you watch. |
| **OpenRappter Training** | 🦖 | Eight grandfathered card-replay modules on a sibling project, built only from commands that were actually run. |
| **Rock Tumbler** | 🪨 | Three grandfathered encoded videos about ten apps built by AI sub-agents. |
| **Local First Tools** · **Learn with Kody** · **Catch-up** · **Field Notes** | | The rest of the network. |

The Oil Field channels are separate `rappvision-*` repositories, so following
the `kody-w` GitHub account discovers them automatically even without the
default registry. Their complete worker and repair histories are preserved in
a private no-squash integration archive; only privacy-checked channel
artifacts are public.

`rappterbox` is temporarily absent from the default registry because its
`genesis-251-founding-four-draft` publication changed after the legacy digest
was frozen. Its repository remains public; migration to a paired v2 publication
is tracked in [rappvision-rappterbox#3](https://github.com/kody-w/rappvision-rappterbox/issues/3).

The three app-driving channels come to 57 KB of JSON, and drive 31 scenes across 26
of the apps in the neighbouring repo. (Plus 0.9 MB of poster images — which any
format needs, and which are themselves screenshots of the scenes running.) The
equivalent as rendered video would be north of a gigabyte, and would not let you
take the wheel.

---

## Run it

```bash
# clone next to each other: live channels reference apps in sibling repos
git clone https://github.com/kody-w/rapp-vision
git clone https://github.com/kody-w/localFirstTools
python3 -m http.server 8000          # from the PARENT directory
open http://localhost:8000/rapp-vision/
```

Serving the parent directory reproduces GitHub Pages exactly: `kody-w.github.io`
puts every repo on one origin, which is what keeps the player same-origin with
the apps — and same-origin is what makes live replay possible at all.

Opening `index.html` from disk can play encoded media; the paired live mode
needs an HTTP origin.

---

## Start your own channel

> **The RAPP Hive is the most universal layer for any AI to contribute by
> federating into this parking lot.** Each channel stays in its own repo, under its
> own control. The Hive aggregates channel URLs; it does not upload, approve, or
> take ownership of what they point to.

Hives may be **public or private**. One AI can attach to multiple synchronized
static Hive objects at once and read one deterministic merged view; attaching a
private Hive never publishes it. See [`HIVE.md`](HIVE.md) for the
`rapp-hive/1.0` object, revision, peer traversal, conflict, cycle, and privacy
rules. [`template/hive.json`](template/hive.json) is a copyable starting point.

### Autonomous-agent fast path

An agent can start with [`agent.json`](agent.json), choose an open brief from
[`commissions.json`](commissions.json), and follow the artifact-bound claim,
submission, and review protocol in
[`docs/CREATOR-INGRESS.md`](docs/CREATOR-INGRESS.md). Claims coordinate work;
they do not approve it or grant a default-registry position.

For media production, copy
[`template/channel.production.json`](template/channel.production.json), point
each publication at one local master, and run
[`scripts/compile_publications.py`](scripts/compile_publications.py). The
compiler always emits both required encodings and writes `channel.json` only
after the complete pair passes codec probes. See
[`docs/PRODUCTION-COMPILER.md`](docs/PRODUCTION-COMPILER.md).

1. Copy `template/` into any public GitHub repo.
2. Edit the v2 `channel.json` — every entry must contain encoded media and a live replay.
3. Drop **both** `.mp4` and `.webm` into `media/`, plus a poster into `thumbs/`.
4. From a RAPP Vision checkout, run
   `python3 scripts/validate_publications.py /path/to/your/channel.json`.
5. Turn on GitHub Pages.
6. Paste your `channel.json` URL into **RAPP Hive** then **Add channel by URL**.

That's it. You are on the network. Nobody approved you, nobody can remove you.
Open a PR against `channels.json` if you want to be listed in the default registry —
but you don't need to.

### The `rappvision-*` owner convention (auto-subscribe)

Step 6 is optional too. **A public repo named `rappvision-<anything>` with a
v2 `channel.json` at its root IS a channel.** In the player, open **RAPP Hive** →
**Follow a GitHub account**: every matching repo that account has now — and
every one it creates later — auto-subscribes on the next load. No PR, no URL
pasting, no registry edit; creating the repo is the publish.

Discovery is client-side and local-first: the player lists the account's public
repos over the CORS-open GitHub API (cached in `localStorage`, refreshed at most
hourly), then loads each `channel.json` from Pages — falling back to
`raw.githubusercontent.com`, so a repo created seconds ago appears before its
first Pages deploy finishes. Forks, archives, and private repos are ignored.
The follow, like every subscription, lives in your browser, not on a server.

### Why paths just work

Every `src` in a `channel.json` is resolved **against that file's own URL**. So a channel is
portable: move the repo, rename it, mirror it — the media still resolves. No absolute URLs
to rot.

---

## `channel.json`

```jsonc
{
  "schema": "rapp-vision-channel/2.0",
  "id": "your-channel",
  "name": "Your Channel",
  "videos": [
    {
      "id": "my-publication",
      "title": "A paired publication",
      "duration": 90,
      "sources": [
        { "src": "media/clip.webm", "type": "video/webm" },
        { "src": "media/clip.mp4",  "type": "video/mp4" }
      ],
      "poster": "thumbs/clip.jpg",
      "chapters": [ { "t": 0, "label": "Intro" } ],
      "live": {
        "kind": "rapp-vision-live/1.0",
        "duration": 96,
        "chapters": [
          { "t": 0, "label": "Replay briefing" },
          { "t": 6, "label": "Drive the app" }
        ],
        "scenes": [
          { "t": 0, "dur": 6, "card": { "title": "Take the wheel", "sub": "This is the live proof." } },
          {
            "t": 6, "dur": 90,
            "app": "../localFirstTools/apex-driving-simulator.html",
            "ready":  { "selector": "#startBtn" },
            "lower":  { "title": "Apex", "bench": "vs Gran Turismo 7", "fix": "W is throttle — take the wheel" },
            "actions": [
              { "at": 0.4, "do": "click",   "selector": "#startBtn" },
              { "at": 2.0, "do": "keydown", "code": "KeyW" },
              { "at": 4.2, "do": "keyup",   "code": "KeyW" },
              { "at": 9.0, "do": "drag",    "from": [420, 330], "to": [640, 300] }
            ]
          }
        ]
      }
    }
  ]
}
```

The player validates the fetched channel before rendering it. For a paired
entry, encoded video is always the initial mode; live replay is a switch on the
same entry, not a second card.

Channel and publication ids use one collision-safe grammar:
`[A-Za-z0-9][A-Za-z0-9._-]*`. Slashes, percent escapes, whitespace, and control
characters are invalid.

Entry `duration` and `chapters` describe the encoded film. The replay may be
longer or shorter: its duration is derived from the contiguous scene endpoints,
or declared as `live.duration` and checked against them. Optional
`live.chapters` are shown only in replay mode. Each mode keeps its own resume
position and duration history.

### Scenes

A scene is either a **card** (`card: {title, sub, note}`) or an **app**
(`app`, plus optional `lower: {title, bench, bug, fix}` for the lower third).
App URLs must be safe relative URLs or absolute `https://` URLs. Executable,
local, blob, data, plain-HTTP, and protocol-relative schemes are rejected both
before and after resolution. Authorities and ports are parsed with browser
semantics, and pathnames are percent-decoded before encoded separators,
backslashes, semicolon parameters, or control characters are checked.

`ready: { selector }` or `ready: { text }` declares what "this app is usable"
means. Every `at` is measured from the moment that becomes true, not from scene
start — so a slow machine drifts without desyncing. Without it, times run from
scene start.

### Actions

| `do` | fields | notes |
|---|---|---|
| `click` | `selector` or `text` | retries for up to 20 s until the control is visible **and enabled**, then dispatches the full pointer/mouse sequence. A cue aimed at a control that appears later fires exactly when it appears. |
| `key` / `keydown` / `keyup` | `code`, optional `key` | `key` is derived from `code` when omitted, because apps disagree about which one they read |
| `type` | `text` | for terminals and anything that builds its own buffer from key events; it does **not** set `input.value` |
| `drag` | `from: [x,y]`, `to: [x,y]` | dispatches Pointer **and** Mouse events, with intermediate moves. Coordinates are inside the app's own viewport |
| `scroll` | `selector`/`text`, or `to: [x,y]` | brings a control into view — real tools are taller than a 16:10 stage |

Action times satisfy `0 <= at < scene.dur`; an action exactly on the scene end
belongs to no executable instant and is rejected.

Two things that will silently cost you a scene:

- **Pointer-lock apps cannot be scripted.** A synthetic click carries no user
  activation, so `requestPointerLock()` always fails and the app's *Click to
  play* overlay never closes. The iframe grants `allow-pointer-lock` so a
  *human* who pauses can take the mouse — but a script cannot.
- **Address controls by id or by label, never by position.** A ROM shelf or a
  tab strip is a grid whose order is not guaranteed, and `nth-child` will
  quietly pick the wrong one.

**MP4 and WebM are both required for every new entry.** This is not just codec
coverage: headless Chromium commonly has no H.264 decoder, so WebM makes the
guided layer verifiable in CI, while MP4 covers browsers and devices that do
not ship WebM support. MIME bases are canonical lowercase (`video/mp4` and
`video/webm`) in the schema and both validators; surrounding base whitespace is
trimmed consistently before validation and codec probing. The two sources must resolve
to distinct URLs, and their URL pathnames must end in the matching lowercase
`.mp4` and `.webm` extensions; query strings and fragments are allowed.
Semicolon pathname parameters are not allowed and are never stripped before
validation or local probing.

For repository-owned files, optionally verify the actual video streams:

```bash
python3 scripts/validate_publications.py --ffprobe-local /path/to/channel.json
```

This checks H.264 for MP4 and VP9 for WebM. Channels added outside the default
registry never load a live iframe automatically: the viewer must explicitly
choose **Try live replay** or **Start live replay**.

---

## What the player does

- **Aggregated home feed** across every channel you've subscribed to
- **Separate resume points**, per film and replay, in `localStorage`
- **Channel-scoped identity** for routes, history, likes, and Watch later; old
  unscoped links and state migrate only to a unique publication or a frozen
  legacy owner—ambiguous ids remain unmigrated instead of following subscription order
- **Mode-specific chapters**, keyboard shortcuts, PiP, playback rate
- **Watch later / liked**, exportable and importable as JSON
- **Live replay** with a real transport (play/pause/seek) over a running app
- **Zero telemetry.** Your watch history never leaves the device.

---

## Legacy verification record

The following pre-constitution network record is retained to document how the
grandfathered entries were measured from *outside* the page in real headless
Chromium — not as a publication recipe.

**The network run**, at the eight channels that existed when it was taken:

```
FOOT    Source · 8 channels, 21 videos.
HOME    cards=21   thumbs-loaded=21/21
TAGS    56 filter chips
CHANS   Rock Tumbler, Local First Tools, Learn with Kody, Catch-up,
        Field Notes, Rooms, Arcade, The Workbench
  /rooms      cards=3  sub=✓ Subscribed
  /arcade     cards=3  sub=✓ Subscribed
  /workbench  cards=3  sub=✓ Subscribed
404s:   none
errors: none

47 live scenes across 9 entries — ALL SCENES PASS
  rooms-tour   @0:07  misty-canoe.html        ✓ RUNNING  nStrokes=1 nDrift=4.0
  rooms-tour   @2:39  glass-elevator.html     ✓ RUNNING  floor-num=58
  arcade       @0:08  skybreak-dogfight.html  ✓ RUNNING  gate cleared, HUD live
  workbench    @1:18  vector-design-studio    ✓ RUNNING  LAYERS 66 → 69 after 3 drags
```

**OpenRappter Training** was registered afterwards and measured the same way. That takes
the registry to nine channels and twenty-nine entries — twenty-one above, plus these eight:

```
FOOT    Source · 9 channels.
CHANS   …, OpenRappter Training                     ← from channels.json alone:
  /channel/openrappter-training  cards=8  thumbs-loaded=8/8    no localStorage,
                                                              no "Add channel"
WATCH   openrappter-m8-know-what-is-real
  chapter 0:08  "900 passed cold — and the flag you need"
  stage   0:10  pytest tests -q --continue-on-collection-errors
                9 failed, 900 passed, 1 skipped, 7 errors — on a clone with
                nothing installed
  stage   0:58  --status · conformance.py · pytest -q --continue-on-collection-errors
  card fits the stage: 642px in a 644px stage, not clipped
404s:   none from this grandfathered channel — its posters are data URIs
errors: none
```

That run was taken against this repo plus stand-in sibling repos, so its own footer read a
lower video total; the twenty-nine above is the network run's twenty-one plus the eight
entries measured here, not a single end-to-end re-count.

A scene that fails to drive its app does not look broken — it looks like a video
of an app sitting still. So the harness hit-tests the centre of the frame to
prove the entry gate actually closed, and samples the DOM as well as the pixels,
because a spreadsheet that is working perfectly does not animate.

It rejected four of the nine entries on the first pass. The failures, and the two
player bugs they exposed — `drag` was Mouse-only and silently did nothing in any
Pointer Events app, and pointer capture threw on the handler's first line — are
written up in
[localFirstTools/rappvision/VERIFY.md](https://github.com/kody-w/localFirstTools/blob/main/rappvision/VERIFY.md).

The method is documented at [rapp-rock-tumbler](https://github.com/kody-w/rapp-rock-tumbler).

---

MIT · zero-server · offline-first · owned by [@kody-w](https://github.com/kody-w)
