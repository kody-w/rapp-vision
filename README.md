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

## Run it

```bash
git clone https://github.com/kody-w/rapp-vision
cd rapp-vision
python3 -m http.server 8000
open http://localhost:8000
```

Or just open `index.html` — though live replay needs an HTTP origin.

---

## Start your own channel

1. Copy `template/` into any public GitHub repo.
2. Edit `channel.json` — name, avatar, your videos.
3. Drop your `.mp4`/`.webm` into `media/` and a `.jpg` into `thumbs/`.
4. Turn on GitHub Pages.
5. Paste your `channel.json` URL into RAPP Vision then Channels then Add channel.

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
      "live": {
        "app": "../localFirstTools/apex-driving-simulator.html",
        "duration": 90,
        "scenes": [
          { "t": 0,  "caption": "Boot the sim" },
          { "t": 8,  "caption": "Start a chase", "act": { "click": "Chase" } },
          { "t": 30, "caption": "Photo mode",    "act": { "click": "Photo" } }
        ]
      }
    }
  ]
}
```

**Always ship WebM alongside MP4.** Not just for coverage — headless Chromium has no H.264
decoder, so a WebM is what makes your channel *verifiable in CI*.

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

Every claim above was measured from *outside* the page, in real headless Chromium:

```
HOME cards=6 (both channels aggregated)
CHANNELS listed=2
CHANNEL page cards=3  sub-btn=Subscribed
LIVE stage=true tag=true video=false openingCard=true
LIVE @0:11 iframe=true src=apex-driving-simulator.html
LIVE @0:20 HUD-present=true   => the sim is RUNNING and being driven
LIVE scrub -> 0:55        404s: none        errors: 0
```

The method is documented at [rapp-rock-tumbler](https://github.com/kody-w/rapp-rock-tumbler).

---

MIT · zero-server · offline-first · owned by [@kody-w](https://github.com/kody-w)
