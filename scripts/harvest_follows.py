#!/usr/bin/env python3
"""Static Data Covenant harvester (RAR CONSTITUTION.md Article XXIV) for the
"follow a GitHub owner" convention (see index.html's conventionEntries /
ownerEntries).

The player lets a visitor follow a GitHub owner; every public repo of theirs
named ``rappvision-*`` (not a fork, not archived, not private) with a
``channel.json`` at its root becomes a channel. That used to mean the
visitor's own browser called ``api.github.com/users/<owner>/repos`` directly.

This script is the CI harvester instead: it reads the maintained owner seed
list at state/follow-seed.json, calls the same repos-listing endpoint for
each of them, and writes the matching entries to state/follow-index.json in
the exact ``{owner: {at, entries}}`` shape index.html's own
``state.followCache`` already uses — so the browser-side lookup logic is
unchanged, only the source of a first (un-cached) lookup is.

LIMITATION, on purpose and documented here rather than hidden: an owner who
is not yet in follow-seed.json will not resolve until they are added and
this harvester runs again. Before this migration, typing any GitHub
username into the "follow" box would resolve on the visitor's next reload,
via a live anonymous call. That instant, fully-open discovery is the part of
the feature this migration trades away to keep the visitor's browser off
api.github.com — add an owner to follow-seed.json (open a PR) to onboard
them.

Usage:
    python3 scripts/harvest_follows.py

Env:
    GITHUB_TOKEN   optional; if set, used for higher API rate limits.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_PATH = os.path.join(ROOT, "state", "follow-seed.json")
INDEX_PATH = os.path.join(ROOT, "state", "follow-index.json")


def fetch_owner_repos(owner, token=None):
    quoted = urllib.parse.quote(owner)
    url = f"https://api.github.com/users/{quoted}/repos?per_page=100&sort=updated"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  warn: {owner} -> HTTP {e.code}", file=sys.stderr)
        return None
    except Exception as e:  # noqa: BLE001
        print(f"  warn: {owner} -> {e}", file=sys.stderr)
        return None
    if not isinstance(data, list):
        return None
    return data


def convention_entries(owner, repos):
    entries = []
    for r in repos or []:
        name = r.get("name") or ""
        if not name.lower().startswith("rappvision-"):
            continue
        if r.get("fork") or r.get("archived") or r.get("private"):
            continue
        branch = r.get("default_branch") or "main"
        entries.append({
            "id": f"gh:{owner}/{name}".lower(),
            "url": f"https://{owner}.github.io/{name}/channel.json",
            "alt": f"https://raw.githubusercontent.com/{owner}/{name}/{branch}/channel.json",
            "repo": f"https://github.com/{owner}/{name}",
        })
    return entries


def main():
    with open(SEED_PATH) as f:
        seed = json.load(f)
    owners = seed.get("owners", [])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    token = os.environ.get("GITHUB_TOKEN")
    index = {}
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH) as f:
            index = json.load(f).get("owners", {})

    for owner in owners:
        print(f"harvesting follows for {owner} ...")
        repos = fetch_owner_repos(owner, token)
        if repos is None:
            continue  # keep whatever was previously harvested for this owner
        index[owner] = {"at": now, "entries": convention_entries(owner, repos)}

    with open(INDEX_PATH, "w") as f:
        json.dump({"generated_at": now, "owners": index}, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {INDEX_PATH} ({len(index)} owners)")


if __name__ == "__main__":
    main()
