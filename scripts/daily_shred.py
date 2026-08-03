#!/usr/bin/env python3
"""The daily shred — one script, a different outcome every day.

rapp-vision-daily/1.0 (kody-w/rapp-metrics/DAILY.md), v1: the hash gate.

Every live-replay scene on the network drives a real app. The scenes are
fixed; the apps are not — autonomous loops rewrite them continuously. This
job walks every live video, hashes the app each of its scenes drives, and
compares against yesterday. A changed hash means the software changed under
a fixed script — which is exactly one drop's worth of news:

    "arcade-take-over's app changed overnight — run it: <watch link>"

THE DISCIPLINE (from DAILY.md, non-negotiable):

  * Fire on difference, not on schedule. The job runs daily; it MESSAGES
    only when something actually changed. Silence is a valid, meaningful
    result: the loops did nothing worth showing.
  * A link, never an attachment. File sends die with error=25 on this
    machine; an attachment-based drop would silently never arrive.
  * One message per day, everything batched.
  * The runner is automated, so per the founding tenet of rapp-metrics/1.0
    its output is editorial-shaped news — it touches no human counter.

State lives in ~/.rappvision/daily-state.json (per-scene-app sha256 by
subject). No timestamps in the state beyond what dedup needs; a quiet day
writes nothing at all.

Usage:
  python3 scripts/daily_shred.py            # walk, diff, message if changed
  python3 scripts/daily_shred.py --dry      # show what it would send, send nothing
  python3 scripts/daily_shred.py --seed     # record baselines, never message
  python3 scripts/daily_shred.py install    # copy self + LaunchAgent, load it
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import urllib.request
from urllib.parse import urljoin

NETWORK = "https://kody-w.github.io/rapp-vision/channels.json"
WATCH = "https://kody-w.github.io/rapp-vision/#/watch/"
PHONE = "+14048628786"
HOME = os.path.expanduser("~/.rappvision")
STATE = os.path.join(HOME, "daily-state.json")
LABEL = "com.rapp.rappvision-daily-shred"
INSTALLED = os.path.join(HOME, "daily_shred.py")


def get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache",
                                               "User-Agent": "rapp-vision-daily/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def jget(url: str) -> dict:
    return json.loads(get(url).decode("utf-8"))


def load_state() -> dict:
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict) -> None:
    os.makedirs(HOME, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, STATE)


def live_subjects() -> list[dict]:
    """Every live video on the network with the app URLs its scenes drive.

    Each app URL is resolved against the channel file's own URL — the same
    rule the player uses — so a channel hosted in any repo resolves right.
    Any unreachable channel is skipped with a note; one publisher's outage
    must not kill the whole drop.
    """
    subjects = []
    net = jget(NETWORK)
    for entry in net.get("channels", []):
        curl = urljoin(NETWORK, entry.get("url", ""))
        try:
            ch = jget(curl)
        except Exception as exc:
            print(f"note: channel {entry.get('id', '?')} unreachable ({exc})")
            continue
        cid = entry.get("id") or ch.get("id") or "?"
        for v in ch.get("videos", []):
            live = v.get("live") or {}
            apps = sorted({urljoin(curl, s["app"]) for s in live.get("scenes", [])
                           if isinstance(s, dict) and s.get("app")})
            if apps:
                subjects.append({"key": f"{cid}/{v.get('id', '?')}",
                                 "id": v.get("id", "?"),
                                 "title": v.get("title", v.get("id", "?")),
                                 "apps": apps})
    return subjects


def sha12(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def send_imessage(text: str) -> bool:
    """Text, never attach — attachments fail on this machine (error=25)."""
    script = ('on run argv\n'
              '  tell application "Messages"\n'
              '    set b to first account whose service type = iMessage\n'
              '    send (item 2 of argv) to participant (item 1 of argv) of b\n'
              '  end tell\n'
              'end run')
    r = subprocess.run(["osascript", "-e", script, PHONE, text],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"send failed: {r.stderr.strip()}", file=sys.stderr)
    return r.returncode == 0


def run(dry: bool = False, seed: bool = False) -> int:
    state = load_state()
    hashes: dict[str, dict] = state.get("app_sha", {})
    changed: list[tuple[dict, list[str]]] = []
    checked = apps_total = unreachable = 0

    for s in live_subjects():
        checked += 1
        news = []
        mine = hashes.setdefault(s["key"], {})
        for app in s["apps"]:
            apps_total += 1
            try:
                now = sha12(get(app))
            except Exception:
                unreachable += 1
                continue                     # an outage is not a change
            before = mine.get(app)
            mine[app] = now
            if before and before != now:
                news.append(f"{os.path.basename(app)} {before}→{now}")
        if news and not seed:
            changed.append((s, news))

    if seed:
        save_state({"app_sha": hashes})
        print(f"seeded baselines: {checked} live videos, {apps_total} apps, "
              f"{unreachable} unreachable")
        return 0

    print(f"checked {checked} live videos / {apps_total} apps · "
          f"{unreachable} unreachable · {len(changed)} changed since last run")

    if not changed:
        # Fire on difference, not on schedule. Nothing changed -> no write,
        # no message. (State only advances when something moved, so a flapping
        # network read can't silently rebase the baseline.)
        print("nothing changed; staying quiet")
        return 0

    lines = ["🎬 The overnight loops changed the game — same script, new software:"]
    for s, news in changed[:8]:
        lines.append(f"• {s['title'][:60]}")
        lines.append(f"  {WATCH}{s['id']}")
    if len(changed) > 8:
        lines.append(f"…and {len(changed) - 8} more.")
    lines.append("Run one and see how today treats you.")
    msg = "\n".join(lines)

    if dry:
        print("--dry: would send ↓\n" + msg)
        return 0
    if send_imessage(msg):
        save_state({"app_sha": hashes})       # advance baseline only after the drop lands
        print("drop sent; baselines advanced")
    return 0


def install() -> int:
    os.makedirs(HOME, exist_ok=True)
    shutil.copy2(os.path.abspath(__file__), INSTALLED)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable or "/usr/bin/python3", INSTALLED],
        "StartCalendarInterval": {"Hour": 7, "Minute": 30},
        "StandardOutPath": os.path.join(HOME, "daily-shred.log"),
        "StandardErrorPath": os.path.join(HOME, "daily-shred.err"),
    }
    dest = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
    with open(dest, "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(["launchctl", "unload", dest], capture_output=True)
    r = subprocess.run(["launchctl", "load", dest], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"launchctl load failed: {r.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"installed: {dest} (daily 07:30 local); script at {INSTALLED}")
    return 0


if __name__ == "__main__":
    if "install" in sys.argv[1:]:
        sys.exit(install())
    sys.exit(run(dry="--dry" in sys.argv[1:], seed="--seed" in sys.argv[1:]))
