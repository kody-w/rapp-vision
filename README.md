# RAPP Vision

**A local-first YouTube.** One HTML file. No server, no database, no account, no build step.
Anyone can run a channel by publishing a `channel.json` to a public repo.

**Live:** https://kody-w.github.io/rapp-vision/

---

## What makes it different

YouTube gives you one thing: a video file that plays back the same way forever.

RAPP Vision gives you **both**:

| | Static video | Live replay |
|---|---|---|
| What ships | `.mp4` + `.webm` | a few KB of JSON |
| Size on disk | ~26 MB | ~4 KB |
| What you see | pixels someone else recorded | **the real app, running now, being driven** |
| Remixable | no | yes — pause, take the wheel, fork the script |
| Works offline | yes (after cache) | yes (it's just the app) |

A "live" video is a **script of interactions**. The player loads the actual application in an
iframe and replays the recorded gestures on a clock — with play, pause and seek. You are not
watching a recording of the app. You are watching the app.

That's the entire pitch: **a video that is also a program.**

---

## What's on it

Nine channels, twenty-nine entries. Four of them publish **no video files at all** —
in three, every entry is a script over a real application in a neighbouring repo; in the
fourth, every entry is a title-card lesson:

| Channel | | What it is |
|---|---|---|
| **Rooms** | 🕯️ | Nine ambient places that do not exist — a canoe at dawn, a cabin under the aurora, a cave lit by larvae. Slow TV where the rain is simulated, so it never falls the same way twice. |
| **Arcade** | 🕹️ | Games and emulators, booted cold and played live. Including one entry that stops scripting halfway through and hands you the keyboard. |
| **The Workbench** | 🛠️ | A DAW, a vector editor, a spreadsheet, an 808 — driven live. A product demo you can interrupt is a different object from one you watch. |
| **OpenRappter Training** | 🦖 | Eight modules on a sibling project, built only from commands that were actually run. No video, no app scenes, no binary assets — posters are inline SVG. It says out loud which of its own claims are unverified. |
| **Rock Tumbler** | 🪨 | Ten apps built by AI sub-agents; nine reported success while broken. Static video. |
| **Local First Tools** · **Learn with Kody** · **Catch-up** · **Field Notes** | | The rest of the network. |

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

Opening `index.html` from disk works for static entries; live replay needs an
HTTP origin.

---

## Start your own channel

> **The RAPP Hive is the most universal layer for any AI to contribute by
> federating into this parking lot.** Each channel stays in its own repo, under its
> own control. The Hive aggregates channel URLs; it does not upload, approve, or
> take ownership of what they point to.

1. Copy `template/` into any public GitHub repo.
2. Edit `channel.json` — name, avatar, your videos.
3. Drop your `.mp4`/`.webm` into `media/` and a `.jpg` into `thumbs/`.
4. Turn on GitHub Pages.
5. Paste your `channel.json` URL into **RAPP Hive** then **Add channel by URL**.

That's it. You are on the network. Nobody approved you, nobody can remove you.
Open a PR against `channels.json` if you want to be listed in the default registry —
but you don't need to.

### Why paths just work

Every `src` in a `channel.json` is resolved **against that file's own URL**. So a channel is
portable: move the repo, rename it, mirror it — the media still resolves. No absolute URLs
to rot.

---

## `channel.json`

```jsonc
{
  "schema": "rapp-vision-channel/1.0",
  "id": "your-channel",
  "name": "Your Channel",
  "videos": [
    {
      "id": "my-video",
      "title": "A normal video",
      "sources": [
        { "src": "media/clip.webm", "type": "video/webm" },
        { "src": "media/clip.mp4",  "type": "video/mp4" }
      ],
      "poster": "thumbs/clip.jpg",
      "chapters": [ { "t": 0, "label": "Intro" } ]
    },
    {
      "id": "my-live-video",
      "title": "A live, remixable video",
      "duration": 90,
      "thumb": "thumbs/live.jpg",
      "sources": [],
      "live": {
        "scenes": [
          { "t": 0, "dur": 6, "card": { "title": "No video file", "sub": "This is a script." } },
          {
            "t": 6, "dur": 84,
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

An entry is treated as **live** when it has a `live` block and no `sources`.

### Scenes

A scene is either a **card** (`card: {title, sub, note}`) or an **app**
(`app`, plus optional `lower: {title, bench, bug, fix}` for the lower third).

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

Two things that will silently cost you a scene:

- **Pointer-lock apps cannot be scripted.** A synthetic click carries no user
  activation, so `requestPointerLock()` always fails and the app's *Click to
  play* overlay never closes. The iframe grants `allow-pointer-lock` so a
  *human* who pauses can take the mouse — but a script cannot.
- **Address controls by id or by label, never by position.** A ROM shelf or a
  tab strip is a grid whose order is not guaranteed, and `nth-child` will
  quietly pick the wrong one.

**Always ship WebM alongside MP4** for static entries. Not just for coverage —
headless Chromium has no H.264 decoder, so a WebM is what makes your channel
*verifiable in CI*. Live entries dodge this entirely: there is nothing to encode.

---

## What the player does

- **Aggregated home feed** across every channel you've subscribed to
- **Resume where you left off**, per video, in `localStorage`
- **Chapters**, keyboard shortcuts, PiP, playback rate
- **Watch later / liked**, exportable and importable as JSON
- **Live replay** with a real transport (play/pause/seek) over a running app
- **Zero telemetry.** Your watch history never leaves the device.

---

## Verified, not asserted

Every claim above was measured from *outside* the page, in real headless Chromium,
against the actual player — not a mock.

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
404s:   none from this channel — it ships no media and its posters are data URIs
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
