#!/usr/bin/env python3
"""RAPP Vision content machine — propose episodes, review published ones.

Two jobs, one script:

  A. PROPOSE  Walk the network (channels.json -> each channel.json), find gaps
              (stale channels, thin channels, curriculum modules with no
              episode, videos whose viewer signals say people were confused or
              wanted more) and write structured episode proposals to
              state/proposals.json.

              It NEVER writes a channel.json. A proposal is an entry in a queue
              that a human — or an explicit, separate promotion step — turns
              into an episode. See docs/CONTENT_MACHINE.md for why: an
              unattended bot that publishes into a channel Kody points
              customers at is a reputational risk, and the queue is the guard.
              write_json() below refuses any path outside state/, so the guard
              is enforced by code, not by discipline.

  B. REVIEW   Score published videos against an explicit, versioned rubric
              (RUBRIC, below — data, not prose, so it can be revised and
              diffed) and write the result through the EDITORIAL lane, never
              into human counters. Every review record carries its reviewer id
              and the rubric version it was scored under.

Design rules borrowed from the estate's metrics stack (see docs):

  * Non-fatal collection. Missing token, missing file, dead channel, adapter
    exception -> warn, leave the snapshot unchanged, exit 0. `--strict` flips
    that for callers where this script IS the whole job.

  * Never publish a number whose failure mode looks like an honest zero. A
    criterion the reviewer could not judge is `null`, never 0. A composite is
    emitted only when every criterion was scored; partial coverage gets
    `partial_composite` plus the explicit list of what was scored.

  * A source that failed to load produces NO gaps and closes NO proposals.
    "Unreachable" and "fine" must never look the same. There are two sources
    and the rule binds both: a channel that 404s closes nothing on that
    channel, and a metrics snapshot that is missing or unparseable closes no
    signal-driven proposal (SIGNAL_DRIVEN_KINDS) anywhere. The run publishes
    which of the two it could see — coverage.channels_unreachable and
    coverage.signals_available.

  * No timestamps anywhere in the snapshots. Git history is the time series.
    Every evidence field is a stable fact ("newest_published": "2026-08-01"),
    never a derived-from-now one ("days_stale": 47) — a field that changes
    daily forces a commit daily and destroys the signal in the log.

  * The generation/review call is a pluggable adapter with a DRY-RUN default
    that needs no model access, and model adapters refuse to run without an
    explicit --allow-model. The pipeline is testable offline and cannot
    silently burn credits.

Usage:
    python3 scripts/content_machine.py propose      # dry-run, writes state/proposals.json
    python3 scripts/content_machine.py review       # dry-run, writes editorial lane
    python3 scripts/content_machine.py run          # both
    python3 scripts/content_machine.py selftest     # offline unit tests
    python3 scripts/content_machine.py run --site-base https://kody-w.github.io/rapp-vision/
    python3 scripts/content_machine.py run --adapter mymod:make_adapter --allow-model
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import re
import sys
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------
# Paths and schemas
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = REPO_ROOT / "state"

SCHEMA_PROPOSALS = "rapp-vision-proposals/1.0"
SCHEMA_EDITORIAL = "rapp-vision-editorial-reviews/1.0"

PROPOSALS_NAME = "proposals.json"
EDITORIAL_NAME = "editorial_reviews.json"

# The player is served from this URL in production. Registry entries are
# origin-relative ("../localFirstTools/rappvision/channel.json") precisely so
# that one origin serves every repo, so a sibling channel resolves against the
# PAGE url — index.html:995 does `absolutise(entry.url, location.href)`. We do
# the same, with the page url supplied by --site-base.
DEFAULT_SITE_BASE = "https://kody-w.github.io/rapp-vision/"

USER_AGENT = "rapp-vision-content-machine/1.0 (+https://github.com/kody-w/rapp-vision)"
HTTP_TIMEOUT = 20

# --------------------------------------------------------------------------
# THE RUBRIC — data, not prose. Revise it here; bump `version` when you do.
#
# Scoring is 1..5, or null for "the reviewer could not judge this". null is
# NOT zero and never becomes zero: see score_video() and composite().
#
# `machine_checkable` marks the criteria the DRY-RUN adapter is allowed to put
# a number on. It scores those from the channel.json record alone and returns
# null for the rest, so a run with no model access publishes a structural lint
# and never an editorial judgement it did not make.
# --------------------------------------------------------------------------

RUBRIC = {
    "id": "rapp-vision-editorial",
    "version": "1.0.0",
    "scale": {"min": 1, "max": 5, "unknown": None},
    "note": (
        "Scores are 1-5. null means the reviewer could not judge that criterion "
        "and must render as an em-dash, never as 0. A composite is published "
        "only when every criterion carries a number."
    ),
    "criteria": [
        {
            "id": "clarity",
            "label": "Clarity",
            "weight": 1.0,
            "machine_checkable": False,
            "question": "Can a viewer who has never seen this project state what it does after watching?",
            "anchors": {
                "5": "One idea, named in the first 15 seconds, and every later beat serves it.",
                "3": "The idea arrives, but the viewer has to assemble it from pieces.",
                "1": "The viewer can describe what happened on screen but not what it was for.",
            },
        },
        {
            "id": "accuracy",
            "label": "Accuracy",
            "weight": 1.5,
            "machine_checkable": False,
            "question": "Is every claim in the narration and the description true of the artifact as shipped?",
            "anchors": {
                "5": "Every claim is demonstrated on screen or tied to a cited measurement.",
                "3": "Claims are true but some are asserted rather than shown.",
                "1": "At least one claim the artifact does not support.",
            },
        },
        {
            "id": "pacing",
            "label": "Pacing",
            "weight": 1.0,
            "machine_checkable": False,
            "question": "Does the runtime earn itself — no dead air, no rushed proof?",
            "anchors": {
                "5": "Every segment is as long as its evidence needs and no longer.",
                "3": "One or two stretches drag or skip.",
                "1": "The interesting part is 20 seconds inside four minutes.",
            },
        },
        {
            "id": "description_stands_alone",
            "label": "Description stands alone",
            "weight": 1.0,
            "machine_checkable": True,
            "question": (
                "Read the description with the video unplayed. Does it state what the "
                "thing is, what was found, and why it matters?"
            ),
            "anchors": {
                "5": "A reader who never plays the video gets the finding and its evidence.",
                "3": "States the subject but not the finding.",
                "1": "A title restated, or a teaser that withholds.",
            },
            "machine_proxy": (
                "Length, presence of a concrete finding (numbers/units), and whether it "
                "opens with something other than a restatement of the title. A proxy for "
                "the question, not an answer to it."
            ),
        },
        {
            "id": "honest_confidence",
            "label": "Honest confidence marking",
            "weight": 1.5,
            "machine_checkable": True,
            "question": (
                "Are claims marked at the confidence they were actually earned — measured, "
                "observed, or believed — with no unhedged superlatives?"
            ),
            "anchors": {
                "5": "Every strong claim carries its measurement or an explicit 'unverified'.",
                "3": "Mostly grounded, with one or two unhedged assertions.",
                "1": "Superlatives and absolutes with nothing behind them.",
            },
            "machine_proxy": (
                "Counts unhedged absolutes ('perfect', 'always', 'never fails', 'guaranteed', "
                "'flawless', '100%') against grounding markers (numbers with units, "
                "'measured', 'verified', 'unverified'). A proxy, not a judgement."
            ),
        },
    ],
    # A flag fires on a scored criterion even when coverage is partial, so a
    # structural run can still raise the two failures that matter most.
    "hard_flags": [
        {
            "id": "accuracy_risk",
            "criterion": "accuracy",
            "at_most": 2,
            "note": "A claim the artifact does not support. Do not promote until resolved.",
        },
        {
            "id": "overclaim_risk",
            "criterion": "honest_confidence",
            "at_most": 2,
            "note": "Confidence asserted above what was earned.",
        },
        {
            "id": "orphan_description",
            "criterion": "description_stands_alone",
            "at_most": 2,
            "note": "The description does not survive being read without the video.",
        },
    ],
}

# Words the structural proxy treats as unhedged absolutes, and the markers it
# treats as grounding. Kept beside the rubric so both are diffable.
#
# EVERY ONE OF THESE IS MATCHED ON WORD BOUNDARIES, NEVER AS A BARE SUBSTRING.
# Substring matching made this proxy wrong in both directions on the
# highest-weight criterion: "imperfect" contains "perfect", so a sentence
# disclaiming perfection was scored as an overclaim, and "problems", "forms",
# "items" and "claims" all contain "ms", so text with zero measurements in it
# scored as grounded. A criterion whose job is catching unearned confidence
# cannot be earned by the letters in an unrelated word.
ABSOLUTE_MARKERS = (
    "perfect", "perfectly", "flawless", "always works", "never fails",
    "guaranteed", "100%", "bug-free", "bulletproof", "the best", "unbeatable",
)

# Grounding splits in two, because the two kinds need different matching.
#
#   WORDS  are claims about evidence ("measured", "verified"). A word boundary
#          is enough. Note "unverified" cannot be matched by "verified": the
#          boundary before `verified` fails inside `unverified`, so the two
#          stay distinct markers, which is what the rubric's 5-anchor wants.
#   UNITS  are only grounding when a MAGNITUDE precedes them. "40 ms" is a
#          measurement; "problems" is not, and neither is a naked "%" or the
#          word "seconds" on its own. So a unit must be preceded by a digit.
GROUNDING_WORD_MARKERS = (
    "measured", "verified", "unverified", "benchmark", "test", "error",
)
GROUNDING_UNIT_MARKERS = (
    "%", "ms", "fps", "s", "sec", "secs", "second", "seconds",
)
# The union is kept under the old name so the marker vocabulary stays readable
# (and diffable) as one list, exactly as the rubric's `machine_proxy` prose
# describes it. Matching is done through the compiled patterns below.
GROUNDING_MARKERS = GROUNDING_WORD_MARKERS + GROUNDING_UNIT_MARKERS


def _boundary_pattern(marker: str) -> str:
    """A literal marker anchored on word boundaries — but only on the sides
    that HAVE a word character to anchor against.

    `\\b` is a transition between a word and a non-word character, so a
    trailing `\\b` on "100%" could never match (the `%` is already non-word and
    end-of-string is non-word too). Anchoring each side conditionally is what
    lets "100%" and "bug-free" live in the same list as "perfect".
    """
    text = str(marker)
    lead = r"\b" if text[:1].isalnum() or text[:1] == "_" else ""
    tail = r"\b" if text[-1:].isalnum() or text[-1:] == "_" else ""
    return lead + re.escape(text) + tail


ABSOLUTE_RE = re.compile("|".join(_boundary_pattern(m) for m in ABSOLUTE_MARKERS))
GROUNDING_WORD_RE = re.compile("|".join(_boundary_pattern(m) for m in GROUNDING_WORD_MARKERS))
# A number, optional decimal, optional space, then a unit. The `%` needs no
# trailing boundary (it is not a word character); the alphabetic units do, so
# "5s" grounds and "5start" does not.
GROUNDING_UNIT_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|(?:{})\b)".format(
        "|".join(re.escape(u) for u in sorted(
            (u for u in GROUNDING_UNIT_MARKERS if u != "%"), key=len, reverse=True))))


def absolute_markers_in(text: str) -> list:
    """Every unhedged absolute present, as it was actually written."""
    return sorted({m.group(0) for m in ABSOLUTE_RE.finditer(text or "")})


def grounding_markers_in(text: str) -> list:
    """Every grounding marker present, as it was actually written.

    Returns the matched TEXT ("0.49%", "measured"), not the pattern, so the
    note a reviewer reads quotes the evidence it actually found rather than a
    marker from a list that may not appear in that form anywhere in the input.
    """
    text = text or ""
    found = {m.group(0) for m in GROUNDING_WORD_RE.finditer(text)}
    found |= {m.group(0).strip() for m in GROUNDING_UNIT_RE.finditer(text)}
    return sorted(found)

# --------------------------------------------------------------------------
# Normalizers. One named function each, called by the SHIPPED code, so a test
# can never re-implement the thing it is checking.
# --------------------------------------------------------------------------


def norm(value) -> str:
    """Normalize a join key: lowercase, collapse dashes/spaces to underscore."""
    return re.sub(r"[-\s]+", "_", str(value or "").strip().lower())


def subject_id(channel_id, video_id) -> str:
    """The subject key for a video: `<channel id>/<video id>`.

    A video's `id` is only unique inside its own channel.json — template/
    channel.json ships `"id": "my-first-video"` and README.md tells every new
    publisher to copy it verbatim, so bare ids collide by construction. Every
    metric, review and proposal is keyed on the channel-scoped id. The channel
    half is the id declared INSIDE the channel file, which is what the player
    uses for routes and subscriptions — not the registry entry id, which for a
    user-added channel is a throwaway `custom-<timestamp>`.
    """
    return "{}/{}".format(str(channel_id or "").strip(), str(video_id or "").strip())


def stable_id(*parts) -> str:
    """Deterministic short id for a proposal, so re-runs update rather than duplicate."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def content_hash(video: dict) -> str:
    """Hash of the fields a review actually looks at.

    Re-review is skipped when this, the rubric version, and the reviewer id are
    all unchanged. That is what keeps a nondeterministic model adapter from
    rewriting identical work into a fresh commit every night — and from being
    billed for it.
    """
    payload = {
        "title": video.get("title") or "",
        "description": video.get("description") or "",
        "tags": list(video.get("tags") or []),
        "duration": video.get("duration"),
        "chapters": [c.get("label") for c in (video.get("chapters") or [])],
        "sources": [s.get("src") for s in (video.get("sources") or [])],
        "live_scenes": len(((video.get("live") or {}).get("scenes")) or []),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------
# I/O — every read is non-fatal, every write is guarded
# --------------------------------------------------------------------------


def warn(msg: str) -> None:
    print("content-machine: " + msg, file=sys.stderr)


def read_json_file(path: Path):
    """Read JSON from disk. Returns None on any failure; never raises."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        warn("could not read {}: {}".format(path, exc))
        return None


def fetch_json_url(url: str, opener=None):
    """GET a JSON document. Returns None on any failure; never raises."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        open_fn = opener or urllib.request.urlopen
        with open_fn(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        warn("could not fetch {}: {}".format(url, exc))
        return None


def serialize(payload: dict) -> str:
    """Stable bytes: sorted keys, fixed separators, trailing newline.

    Identical content must produce identical bytes so `git status --porcelain`
    finds nothing on a no-op run and the workflow makes no commit.
    """
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path: Path, payload: dict, state_dir: Path) -> bool:
    """Write a snapshot into state/ only. Returns True if bytes changed.

    THE PUBLISH GUARD. This is the only write path in the script and it refuses
    any destination outside `state_dir`. channel.json, channels.json and
    index.html are structurally unreachable from here: the content machine
    cannot publish an episode even if a future edit tries to.
    """
    path = Path(path).resolve()
    root = Path(state_dir).resolve()
    if root not in path.parents:
        raise ValueError(
            "refusing to write outside the state directory: {} (state dir is {}). "
            "The content machine proposes; a human promotes.".format(path, root)
        )
    body = serialize(payload)
    try:
        existing = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        existing = None
    if existing == body:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return True


# --------------------------------------------------------------------------
# Walking the network
# --------------------------------------------------------------------------


def resolve_channel_source(entry_url: str, repo_root: Path, site_base: str, offline: bool):
    """Decide where a registry entry's channel.json will be read from.

    Returns (kind, location) where kind is "file", "url" or "unreachable".

    Local first: when the sibling repos are cloned next to this one (the
    documented dev layout — README.md's `python3 -m http.server` from the PARENT
    directory), `../localFirstTools/rappvision/channel.json` is a real path. In
    CI the siblings are not checked out, so it falls through to the published
    site, resolved exactly the way the player resolves it: against the page URL.
    """
    url = (entry_url or "").strip()
    if not url:
        return ("unreachable", "")
    if url.startswith("http://") or url.startswith("https://"):
        return ("unreachable", url) if offline else ("url", url)
    local = (repo_root / url).resolve()
    if local.is_file():
        return ("file", str(local))
    if offline or not site_base:
        return ("unreachable", url)
    return ("url", urllib.parse.urljoin(site_base, url))


def load_channel(entry: dict, repo_root: Path, site_base: str, offline: bool, opener=None):
    """Load one channel.json. Returns (channel_dict | None, error_string | None).

    Shape tolerance mirrors the player's: it accepts what publishers actually
    write rather than what the spec says, because one typo in someone else's
    JSON must not blank the network.
    """
    kind, where = resolve_channel_source(entry.get("url"), repo_root, site_base, offline)
    if kind == "unreachable":
        return (None, "{}: unreachable ({})".format(entry.get("id"), where or "no url"))
    doc = read_json_file(Path(where)) if kind == "file" else fetch_json_url(where, opener=opener)
    if not isinstance(doc, dict):
        return (None, "{}: no usable document at {}".format(entry.get("id"), where))
    # The id inside the file wins; the registry entry id is only a hint.
    doc["id"] = doc.get("id") or entry.get("id")
    doc["name"] = doc.get("name") or entry.get("name") or doc.get("id")
    doc["_source"] = where
    doc["_registry_id"] = entry.get("id")
    doc["_repo"] = entry.get("repo") or doc.get("repo") or ""
    videos = doc.get("videos")
    doc["videos"] = [v for v in videos if isinstance(v, dict)] if isinstance(videos, list) else []
    return (doc, None)


def walk_network(repo_root: Path, site_base: str, offline: bool, opener=None) -> dict:
    """Load the registry and every channel it lists.

    Returns {"channels": [...], "offline": [...], "registry_count": n}.
    Channels load independently: one dead channel cannot blank the network,
    exactly as the player's Promise.allSettled does.
    """
    registry = read_json_file(repo_root / "channels.json") or {}
    entries = [e for e in (registry.get("channels") or []) if isinstance(e, dict)]
    seen, wanted = set(), []
    for e in entries:                       # dedupe by registry id, like the player
        if e.get("id") in seen:
            continue
        seen.add(e.get("id"))
        wanted.append(e)
    channels, failures = [], []
    for entry in wanted:
        chan, err = load_channel(entry, repo_root, site_base, offline, opener=opener)
        if chan is None:
            failures.append(err)
        else:
            channels.append(chan)
    return {"channels": channels, "offline": failures, "registry_count": len(wanted)}


def flatten_videos(network: dict):
    """[(channel, video, subject_id)] for every video in every loaded channel."""
    out = []
    for chan in network.get("channels") or []:
        for vid in chan.get("videos") or []:
            if not vid.get("id"):
                continue
            out.append((chan, vid, subject_id(chan.get("id"), vid.get("id"))))
    return out


# --------------------------------------------------------------------------
# Viewer signals, read from whatever the metrics lane publishes
# --------------------------------------------------------------------------
#
# THE SIGNAL VOCABULARY IS A CROSS-WRITER CONTRACT, NOT THIS SCRIPT'S CHOICE.
#
# scripts/rapp_metrics.py owns the signal surface and decides what each
# reaction counter is called. This script only READS what that one publishes.
# CANONICAL_SIGNALS below is a copy of rapp_metrics.SIGNAL_MAP's values, and
# tests/test_content_machine.py imports rapp_metrics and asserts the two still
# agree — so a rename on either side goes RED instead of going quiet.
#
# That test exists because this file shipped the bug it now prevents: it
# looked for "confused" and "want_more" while the metrics lane published
# "confusing" and "want_more_like_this". Every signal-driven gap was dead. No
# error, no exception, no zero — just an empty queue that looked exactly like
# a quiet week. A broken metric whose failure mode is indistinguishable from
# an honest empty state is the worst way for a metric to break, and only a
# test that confronts the OTHER writer's constants can catch it.
CANONICAL_SIGNALS = (
    "watched_it_all",
    "learned_something",
    "want_more_like_this",
    "tried_it_myself",
    "saved_for_later",
    "too_long",
    "confusing",
)

# Role -> the names that satisfy it, CANONICAL FIRST. The trailing aliases are
# read tolerance for an older snapshot or a third-party one; they are not a
# licence to rename. signal_of() returns the name it actually matched and that
# name is written into the evidence, so a proposal always says which counter
# fired rather than which role this script happens to call it.
#
# Note what the aliases do NOT protect against: if rapp_metrics renames a
# channel to something not listed here, the alias lookup finds nothing and
# returns 0 — the same silent failure as before. The contract test is the
# guard; the aliases are only politeness.
SIGNAL_ROLES = {
    "confusion": ("confusing", "confused"),
    "want_more": ("want_more_like_this", "want_more"),
    "too_long": ("too_long",),
    "watched": ("watched_it_all", "watched"),
    "learned": ("learned_something", "learned"),
    "tried": ("tried_it_myself", "tried"),
    "saved": ("saved_for_later", "saved"),
}

# Every name this script will read off a snapshot, canonical plus aliases.
SIGNAL_CHANNELS = tuple(sorted({n for names in SIGNAL_ROLES.values() for n in names}))

# The gap kinds that exist ONLY because the metrics snapshot said so, as
# (role, kind) pairs. One tuple, read by the detector AND by the merge, so a
# new signal-driven kind cannot be added to the first and forgotten in the
# second — which is exactly how a signal-blind run came to close them.
SIGNAL_GAP_KINDS = (
    ("confusion", "viewers_confused"),
    ("want_more", "viewers_want_more"),
)
SIGNAL_DRIVEN_KINDS = frozenset(kind for _role, kind in SIGNAL_GAP_KINDS)

# Containers a metrics snapshot might use for its per-video map. Checked in
# order; the first dict-of-dicts wins.
_METRIC_CONTAINERS = ("videos", "video_metrics", "subjects", "entries")


def declared_signal_names(metrics_doc) -> tuple:
    """The signal names the snapshot DECLARES about itself, if it says.

    state/metrics.json publishes a `signal_channels` map (reaction content ->
    counter name) precisely so a reader does not have to guess. Reading the
    vocabulary from the snapshot means a rename by the metrics owner is picked
    up on the very next run instead of silently zeroing this script's gap
    detection. When the snapshot declares nothing, the canonical list stands.
    """
    if isinstance(metrics_doc, dict):
        declared = metrics_doc.get("signal_channels")
        if isinstance(declared, dict):
            names = tuple(sorted({str(v).strip() for v in declared.values() if str(v).strip()}))
            if names:
                return names
    return CANONICAL_SIGNALS


def index_signals(metrics_doc) -> dict:
    """Normalize a metrics snapshot into {normalized subject key: {signal: int}}.

    Deliberately tolerant about SHAPE: scripts/rapp_metrics.py is owned by
    another writer and its exact container name is not something this script
    should hard-code. It is NOT tolerant about meaning — an unrecognised shape
    yields {}, which reads as "no signal", never as "zero signal", because
    every consumer below requires a count at or above a threshold before it
    fires.
    """
    if not isinstance(metrics_doc, dict):
        return {}
    table = None
    for key in _METRIC_CONTAINERS:
        candidate = metrics_doc.get(key)
        if isinstance(candidate, dict) and candidate:
            table = candidate
            break
    if table is None:
        return {}
    # Union: whatever the snapshot declares, plus everything we know how to
    # read. A name we recognise is never dropped because the snapshot forgot
    # to declare it.
    wanted = set(declared_signal_names(metrics_doc)) | set(SIGNAL_CHANNELS)
    out = {}
    for raw_key, record in table.items():
        if not isinstance(record, dict):
            continue
        signals = record.get("signals") if isinstance(record.get("signals"), dict) else record
        picked = {}
        for name in sorted(wanted):
            value = signals.get(name)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                picked[name] = int(value)
        if picked:
            out[norm(raw_key)] = picked
    return out


def signals_for(signal_index: dict, subject: str) -> dict:
    return signal_index.get(norm(subject), {})


def signal_of(signals: dict, role: str):
    """(name, count) for a role, or (None, 0) when nothing answered it.

    Returns the name that ACTUALLY matched, so evidence quotes the counter
    that fired instead of an internal role name nobody else uses. (None, 0)
    means "this snapshot carries no such counter" — distinct from a counter
    that exists and reads zero, which returns (name, 0).
    """
    for name in SIGNAL_ROLES.get(role, ()):
        value = (signals or {}).get(name)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return (name, int(value))
    return (None, 0)


# --------------------------------------------------------------------------
# Gap detection
# --------------------------------------------------------------------------

DEFAULTS = {
    "stale_days": 45,          # a channel silent longer than this is a gap
    "thin_min": 3,             # a channel with fewer entries than this is thin
    "min_signal": 2,           # a signal channel needs this many to fire
    "long_video_seconds": 180, # above this, chapters are expected
    "review_limit": 40,        # max videos reviewed per run (rate-limit drain)
}


def _newest_published(channel: dict) -> str:
    dates = [str(v.get("published") or "") for v in (channel.get("videos") or [])]
    dates = [d for d in dates if d]
    return max(dates) if dates else ""


def _days_between(iso_a: str, iso_b: str):
    """Whole days between two YYYY-MM-DD strings, or None if either is unusable."""
    import datetime

    try:
        a = datetime.date.fromisoformat(iso_a[:10])
        b = datetime.date.fromisoformat(iso_b[:10])
    except (ValueError, TypeError):
        return None
    return (b - a).days


def detect_gaps(network: dict, signal_index: dict, cfg: dict, today: str) -> list:
    """Find every gap in the loaded part of the network.

    `today` is passed in rather than read from the clock so the detector is
    deterministic and testable. It is used ONLY to decide whether a channel is
    stale; it is never written into a gap, because an evidence field that moves
    every day forces a commit every day.

    A channel that failed to load contributes nothing here — it is simply
    absent from network["channels"]. "Unreachable" must never be reported as
    "empty".
    """
    gaps = []
    for chan in network.get("channels") or []:
        cid = chan.get("id")
        videos = chan.get("videos") or []
        newest = _newest_published(chan)

        # 1. Stale channel.
        age = _days_between(newest, today) if newest else None
        if age is not None and age > cfg["stale_days"]:
            gaps.append({
                "kind": "channel_stale",
                "channel": cid,
                "subject": cid,
                "discriminator": newest,
                "evidence": {
                    "newest_published": newest,
                    "stale_after_days": cfg["stale_days"],
                    "entries": len(videos),
                },
            })

        # 2. Thin channel.
        if len(videos) < cfg["thin_min"]:
            gaps.append({
                "kind": "channel_thin",
                "channel": cid,
                "subject": cid,
                "discriminator": str(len(videos)),
                "evidence": {
                    "entries": len(videos),
                    "thin_below": cfg["thin_min"],
                    "titles": sorted(str(v.get("title") or v.get("id")) for v in videos),
                },
            })

        # 3. Curriculum modules with no episode.
        #
        # OPT-IN and currently unused: no channel in the default registry
        # declares `curriculum` today. A channel may add
        #   "curriculum": [{"id": "m1", "title": "..."}, ...]
        # and tag each video with "module": "m1" (or a tag "module:m1"). The
        # player ignores unknown fields, so declaring one changes nothing on
        # screen.
        modules = [m for m in (chan.get("curriculum") or []) if isinstance(m, dict)]
        if modules:
            covered = set()
            for vid in videos:
                if vid.get("module"):
                    covered.add(norm(vid.get("module")))
                for tag in (vid.get("tags") or []):
                    if str(tag).startswith("module:"):
                        covered.add(norm(str(tag).split(":", 1)[1]))
            for module in modules:
                mid = module.get("id")
                if not mid or norm(mid) in covered:
                    continue
                gaps.append({
                    "kind": "curriculum_module_uncovered",
                    "channel": cid,
                    "subject": cid,
                    "discriminator": str(mid),
                    "evidence": {
                        "module_id": mid,
                        "module_title": module.get("title") or mid,
                        "module_goal": module.get("goal") or "",
                        "modules_declared": len(modules),
                    },
                })

        # 4. Per-video viewer signals.
        for vid in videos:
            if not vid.get("id"):
                continue
            subj = subject_id(cid, vid.get("id"))
            sig = signals_for(signal_index, subj)
            if not sig:
                continue
            # Fire by ROLE, never by spelling. The evidence records the counter
            # name that actually matched, so a proposal can be traced back to a
            # column in the metrics snapshot by anyone reading it later.
            for role, kind in SIGNAL_GAP_KINDS:
                name, count = signal_of(sig, role)
                if name is None or count < cfg["min_signal"]:
                    continue
                gaps.append({
                    "kind": kind,
                    "channel": cid,
                    "subject": subj,
                    # The matched name, not the role: if the vocabulary ever
                    # changes the id changes with it, and the old proposal
                    # closes instead of quietly shadowing the new one.
                    "discriminator": name,
                    "evidence": {
                        "video_title": vid.get("title") or vid.get("id"),
                        "signal": name,
                        "count": count,
                        "signals": dict(sorted(sig.items())),
                        "fires_at": cfg["min_signal"],
                    },
                })
    for gap in gaps:
        gap["id"] = stable_id(gap["kind"], gap["subject"], gap["discriminator"])
    return gaps


def detect_advisories(network: dict, cfg: dict) -> list:
    """Structural findings that are NOT episode proposals.

    Kept in their own array so nobody mistakes a lint for a commission. These
    are things about an already-published entry that a human should fix.
    """
    out = []
    for chan in network.get("channels") or []:
        cid = chan.get("id")
        for vid in chan.get("videos") or []:
            if not vid.get("id"):
                continue
            subj = subject_id(cid, vid.get("id"))
            sources = vid.get("sources") or []
            is_live = bool(vid.get("live")) and not sources

            if sources and not any("webm" in str(s.get("src", "")).lower()
                                   or "webm" in str(s.get("type", "")).lower()
                                   for s in sources):
                out.append({
                    "kind": "missing_webm",
                    "subject": subj,
                    "detail": (
                        "Static entry ships no WebM. Headless Chromium has no H.264 "
                        "decoder, so a WebM source is what makes this entry verifiable "
                        "in CI (README.md, 'Always ship WebM alongside MP4')."
                    ),
                })
            if not str(vid.get("thumb") or vid.get("poster") or "").strip():
                out.append({
                    "kind": "missing_thumb",
                    "subject": subj,
                    "detail": "No thumb or poster; the card renders an empty frame.",
                })
            duration = vid.get("duration")
            if (isinstance(duration, (int, float))
                    and duration >= cfg["long_video_seconds"]
                    and not (vid.get("chapters") or [])
                    and not is_live):
                out.append({
                    "kind": "missing_chapters",
                    "subject": subj,
                    "detail": "Runs {}s with no chapters; the watch page renders no chapter list.".format(int(duration)),
                })
    out.sort(key=lambda a: (a["subject"], a["kind"]))
    return out


# --------------------------------------------------------------------------
# Adapters — the pluggable generation/review call
# --------------------------------------------------------------------------


class DryRunAdapter:
    """The default. No model, no network, no credits.

    PROPOSE: fills a deterministic template per gap kind from the gap's own
    evidence. Useful on its own — it names the gap, the channel and the hook —
    and it is explicitly marked `judgment: false` so nobody mistakes a template
    for an editorial decision.

    REVIEW: scores ONLY the criteria RUBRIC marks `machine_checkable`, from the
    channel.json record alone, and returns null for the rest. It never guesses
    a number for clarity, accuracy or pacing, because a fabricated 3 is worse
    than an honest blank.
    """

    id = "dryrun-structural/1.0.0"
    kind = "structural"
    judgment = False
    needs_model = False

    # -- propose -----------------------------------------------------------

    def propose(self, gap: dict, context: dict) -> dict:
        ev = gap.get("evidence") or {}
        chan_name = context.get("channel_name") or gap.get("channel")
        tagline = (context.get("channel_tagline") or "").strip()
        kind = gap["kind"]

        if kind == "channel_stale":
            return {
                "title": "[gap] {} has published nothing since {}".format(chan_name, ev.get("newest_published")),
                "angle": (tagline or "Pick up the thread this channel was already pulling on.")
                         + " The channel's own most recent entry is the obvious starting point.",
                "format": "unset",
                "outline": [
                    "Open on the thing that changed since the last entry.",
                    "Show it running, not described.",
                    "Close on the measurement that proves it.",
                ],
                "why_now": "Nothing published for more than {} days.".format(ev.get("stale_after_days")),
            }
        if kind == "channel_thin":
            return {
                "title": "[gap] {} has only {} entr{}".format(
                    chan_name, ev.get("entries"), "y" if ev.get("entries") == 1 else "ies"),
                "angle": (tagline or "A channel needs a second and third entry before it reads as a channel."),
                "format": "unset",
                "outline": [
                    "Choose a subject adjacent to: " + ", ".join(ev.get("titles") or []) + ".",
                    "Keep the same shape as the existing entries so the channel reads as one thing.",
                ],
                "why_now": "Below the {}-entry floor.".format(ev.get("thin_below")),
            }
        if kind == "curriculum_module_uncovered":
            return {
                "title": "[module] {}".format(ev.get("module_title")),
                "angle": ev.get("module_goal") or "Declared in this channel's curriculum with no episode against it.",
                "format": "unset",
                "outline": [
                    "State the module's goal in the first 15 seconds.",
                    "Demonstrate it end to end on the real artifact.",
                    "Close by naming what the viewer can now do.",
                ],
                "why_now": "Module '{}' is declared and uncovered.".format(ev.get("module_id")),
            }
        if kind == "viewers_confused":
            return {
                "title": "[follow-up] The part of '{}' people flagged as confusing".format(ev.get("video_title")),
                "angle": "Viewers marked this entry confusing. Re-cut or re-explain the step that lost them.",
                "format": "unset",
                "outline": [
                    "Name the step that was unclear, out loud, at the top.",
                    "Redo it slower against the real artifact.",
                    "Link back to the original entry rather than replacing it.",
                ],
                "why_now": "{} = {} (fires at {}).".format(
                    ev.get("signal"), ev.get("count"), ev.get("fires_at")),
            }
        if kind == "viewers_want_more":
            return {
                "title": "[follow-up] More on '{}'".format(ev.get("video_title")),
                "angle": "Viewers asked for more of this specific subject. Go one level deeper, not one level wider.",
                "format": "unset",
                "outline": [
                    "Assume the original entry was watched.",
                    "Take the single hardest thing it skipped.",
                    "Show the failure mode as well as the success.",
                ],
                "why_now": "{} = {} (fires at {}).".format(
                    ev.get("signal"), ev.get("count"), ev.get("fires_at")),
            }
        return {
            "title": "[gap] {}".format(kind),
            "angle": "Unclassified gap; a human should decide what this becomes.",
            "format": "unset",
            "outline": [],
            "why_now": "",
        }

    # -- review ------------------------------------------------------------

    def review(self, video: dict, rubric: dict, context: dict) -> dict:
        desc = str(video.get("description") or "")
        title = str(video.get("title") or "")
        scores, notes = {}, {}

        for crit in rubric["criteria"]:
            cid = crit["id"]
            if not crit.get("machine_checkable"):
                scores[cid] = None
                notes[cid] = "Not machine-checkable; no model reviewer ran."
                continue
            if cid == "description_stands_alone":
                scores[cid], notes[cid] = self._score_description(desc, title)
            elif cid == "honest_confidence":
                scores[cid], notes[cid] = self._score_confidence(desc)
            else:
                scores[cid] = None
                notes[cid] = "Marked machine_checkable but this adapter has no proxy for it."
        return {"scores": scores, "notes": notes}

    @staticmethod
    def _score_description(desc: str, title: str):
        """Length is only a floor. What separates 3 from 5 is whether a FINDING
        is present, proxied by a concrete figure — the rubric's anchors key on
        the finding, not on the word count, so word count must not dominate."""
        text = desc.strip()
        if not text:
            return 1, "Empty description."
        words = len(text.split())
        has_number = bool(re.search(r"\d", text))
        restates_title = norm(text[: max(len(title), 1)]) == norm(title) and words < 40
        if words < 15:
            return 1, "{} words; a caption, not a description.".format(words)
        if restates_title:
            return 2, "Opens by restating the title and adds little ({} words).".format(words)
        if words < 30:
            return (3, "{} words with a concrete figure; short but carries a finding.".format(words)) \
                if has_number else \
                (2, "{} words and no concrete finding; states the subject only.".format(words))
        if has_number:
            return (5, "{} words and carries at least one concrete figure.".format(words)) \
                if words >= 60 else \
                (4, "{} words with a concrete figure.".format(words))
        return 3, "{} words but no concrete finding (no figures).".format(words)

    @staticmethod
    def _score_confidence(desc: str):
        text = desc.lower()
        if not text.strip():
            return None, "No description to check; the video's narration is not readable from here."
        absolutes = absolute_markers_in(text)
        grounding = grounding_markers_in(text)
        if absolutes and not grounding:
            return 1, "Unhedged absolutes with no grounding: " + ", ".join(sorted(absolutes)) + "."
        if absolutes:
            return 3, "Absolutes present ({}) but grounding markers too ({}).".format(
                ", ".join(sorted(absolutes)), ", ".join(sorted(grounding)))
        if len(grounding) >= 2:
            return 5, "No unhedged absolutes; grounding markers present: " + ", ".join(sorted(grounding)) + "."
        if grounding:
            return 4, "No unhedged absolutes; one grounding marker: " + grounding[0] + "."
        return 3, "No unhedged absolutes, but nothing grounding a claim either."


def load_adapter(spec: str, allow_model: bool):
    """Resolve an adapter spec.

    "dryrun"                -> DryRunAdapter()
    "package.module:factory" -> importlib import, call factory(), use the result.

    A model-backed adapter must set `needs_model = True` on the object it
    returns; without --allow-model (or RAPP_CONTENT_ALLOW_MODEL=1) this refuses
    to use it and falls back to dry-run. That is the credit guard: a workflow
    misconfigured to point at a paid adapter spends nothing until someone
    explicitly says so.
    """
    spec = (spec or "dryrun").strip()
    if spec in ("dryrun", "dry-run", ""):
        return DryRunAdapter(), None
    if ":" not in spec:
        return DryRunAdapter(), "adapter spec '{}' must be module:callable; using dry-run".format(spec)
    mod_name, _, attr = spec.partition(":")
    try:
        module = importlib.import_module(mod_name)
        factory = getattr(module, attr)
        adapter = factory()
    except Exception as exc:                                  # noqa: BLE001 - never fatal
        return DryRunAdapter(), "adapter '{}' failed to load ({}); using dry-run".format(spec, exc)
    for required in ("id", "propose", "review"):
        if not hasattr(adapter, required):
            return DryRunAdapter(), "adapter '{}' lacks .{}; using dry-run".format(spec, required)
    if getattr(adapter, "needs_model", True) and not allow_model:
        return DryRunAdapter(), (
            "adapter '{}' needs model access and --allow-model was not passed; using dry-run".format(spec))
    return adapter, None


# --------------------------------------------------------------------------
# PROPOSE
# --------------------------------------------------------------------------

# Fields the machine owns and overwrites on every run. Everything else in an
# existing proposal record — status, human notes, an edited proposal body,
# fields nobody has invented yet — is preserved verbatim.
MACHINE_FIELDS = ("kind", "subject", "channel", "evidence", "gap_closed", "generated_by")


def build_proposals(network: dict, signal_index: dict, cfg: dict, adapter, today: str) -> list:
    gaps = detect_gaps(network, signal_index, cfg, today)
    by_id = {c.get("id"): c for c in (network.get("channels") or [])}
    out = []
    for gap in gaps:
        chan = by_id.get(gap["channel"]) or {}
        context = {
            "channel_id": chan.get("id"),
            "channel_name": chan.get("name"),
            "channel_tagline": chan.get("tagline"),
            "channel_repo": chan.get("_repo"),
        }
        try:
            body = adapter.propose(gap, context)
        except Exception as exc:                              # noqa: BLE001 - never fatal
            warn("adapter.propose failed for {} ({}); skipping this gap".format(gap["id"], exc))
            continue
        out.append({
            "id": gap["id"],
            "kind": gap["kind"],
            "subject": gap["subject"],
            "channel": gap["channel"],
            "evidence": gap["evidence"],
            "gap_closed": False,
            "status": "proposed",
            "proposal": body,
            "generated_by": {
                "adapter": getattr(adapter, "id", "unknown"),
                "kind": getattr(adapter, "kind", "unknown"),
                "judgment": bool(getattr(adapter, "judgment", False)),
            },
        })
    out.sort(key=lambda p: (p["channel"] or "", p["kind"], p["id"]))
    return out


def merge_proposals(existing: list, fresh: list, evaluated_channels: set,
                    signals_available: bool = True) -> list:
    """Fold a fresh detection into the existing queue.

    Rules, in order of importance:
      1. Nothing is ever deleted. A proposal a human triaged stays triaged.
      2. Human-owned fields (status, notes, an edited proposal body, anything
         else) survive untouched; only MACHINE_FIELDS are overwritten.
      3. A proposal is marked gap_closed ONLY if EVERY source its gap needs was
         actually readable this run. There are two such sources and both gate
         the close:
           * the channel — one 404 must not silently retire that channel's
             whole queue;
           * the metrics snapshot — a signal-driven gap (SIGNAL_DRIVEN_KINDS)
             cannot re-fire when index_signals() came back empty, so closing
             it would turn "seven people said this was confusing" into
             "resolved" on the strength of a JSON file that did not parse.
         Same rule as the channel guard, applied to the other source:
         "unreachable" and "fine" must never look the same.

    `signals_available` defaults to True only so that callers written before the
    signal source was gated keep their old behaviour on non-signal kinds; every
    shipped caller passes the real value, and cmd_propose derives it when it is
    not given. A test pins the plumbing (`TestSignalBlindRunClosesNothing`).
    """
    fresh_by_id = {p["id"]: p for p in fresh}
    merged = {}
    for record in existing or []:
        if not isinstance(record, dict) or not record.get("id"):
            continue
        kept = dict(record)
        rid = kept["id"]
        if rid in fresh_by_id:
            for field in MACHINE_FIELDS:
                kept[field] = fresh_by_id[rid][field]
            if "proposal" not in kept:
                kept["proposal"] = fresh_by_id[rid]["proposal"]
            kept.setdefault("status", "proposed")
        elif (kept.get("channel") in evaluated_channels
              and not (kept.get("kind") in SIGNAL_DRIVEN_KINDS and not signals_available)):
            kept["gap_closed"] = True
        merged[rid] = kept
    for rid, record in fresh_by_id.items():
        if rid not in merged:
            merged[rid] = record
    out = list(merged.values())
    out.sort(key=lambda p: (p.get("channel") or "", p.get("kind") or "", p.get("id") or ""))
    return out


def proposals_payload(proposals: list, advisories: list, network: dict, cfg: dict, adapter,
                      signals_available=None) -> dict:
    open_count = sum(1 for p in proposals
                     if not p.get("gap_closed") and p.get("status") in (None, "proposed"))
    return {
        "schema": SCHEMA_PROPOSALS,
        "note": (
            "A QUEUE, NOT A PUBLICATION. Nothing here is on the network. A human — or an "
            "explicit promotion step — turns a proposal into an episode by editing a "
            "channel.json. The content machine cannot write a channel.json: its only write "
            "path refuses any destination outside state/."
        ),
        "thresholds": {k: cfg[k] for k in ("stale_days", "thin_min", "min_signal", "long_video_seconds")},
        "generated_by": {
            "adapter": getattr(adapter, "id", "unknown"),
            "kind": getattr(adapter, "kind", "unknown"),
            "judgment": bool(getattr(adapter, "judgment", False)),
        },
        "coverage": {
            "channels_in_registry": network.get("registry_count", 0),
            "channels_loaded": len(network.get("channels") or []),
            "channels_unreachable": sorted(network.get("offline") or []),
            # Queue entries whose channel this run could not see. Their
            # gap_closed flag was deliberately NOT touched, so they are neither
            # closed nor re-evidenced. Published rather than left implicit: a
            # proposal nobody can re-check is a different thing from an open
            # one, and the difference should be visible without a diff.
            "queue_channels_not_loaded": sorted(
                {str(p.get("channel")) for p in proposals
                 if p.get("channel")
                 and p.get("channel") not in {c.get("id") for c in (network.get("channels") or [])}}
            ),
            # Did the metrics snapshot answer this run? False means every
            # signal-driven gap was invisible, so none of them could re-fire
            # and none of them were closed. Published rather than left to a
            # diff: a run that was signal-blind produces the same *shape* of
            # queue as a run where every viewer complaint got fixed, and the
            # difference is the whole meaning of the file. `null` means the
            # caller did not say — an unknown, never a claim (F7).
            "signals_available": signals_available,
        },
        "totals": {"proposals": len(proposals), "open": open_count, "advisories": len(advisories)},
        "proposals": proposals,
        "advisories": advisories,
    }


def cmd_propose(args, state_dir: Path, adapter, network: dict, signal_index: dict, cfg: dict,
                signals_available=None) -> int:
    path = state_dir / PROPOSALS_NAME
    # Derived here when the caller did not say, so the guard cannot be lost by
    # a caller that forgot to thread it through. An empty index means the
    # snapshot was missing, unparseable, or carried no counter this script
    # recognises — all three are "we could not see the signal this run".
    if signals_available is None:
        signals_available = bool(signal_index)
    loaded = network.get("channels") or []
    if network.get("registry_count", 0) and not loaded:
        warn("no channel loaded of {} in the registry; leaving {} unchanged".format(
            network.get("registry_count"), path.name))
        return 1 if args.strict else 0

    fresh = build_proposals(network, signal_index, cfg, adapter, args.today)
    advisories = detect_advisories(network, cfg)
    prior = read_json_file(path) or {}
    merged = merge_proposals(prior.get("proposals") or [], fresh,
                             {c.get("id") for c in loaded},
                             signals_available=signals_available)

    # Advisories only cover channels that loaded, so carry forward the ones for
    # channels we could not see this run rather than deleting them.
    seen_channels = {c.get("id") for c in loaded}
    carried = [a for a in (prior.get("advisories") or [])
               if isinstance(a, dict) and str(a.get("subject", "")).split("/")[0] not in seen_channels]
    advisories = sorted(advisories + carried, key=lambda a: (a.get("subject", ""), a.get("kind", "")))

    if not merged and (prior.get("proposals") or []):
        warn("refusing to replace a non-empty proposal queue with an empty one")
        return 1 if args.strict else 0

    payload = proposals_payload(merged, advisories, network, cfg, adapter,
                                signals_available=signals_available)
    changed = write_json(path, payload, state_dir)
    print("propose: {} proposals ({} open), {} advisories, {} channel(s) loaded, {} unreachable, "
          "signals {} -> {}".format(
              len(merged), payload["totals"]["open"], len(advisories),
              len(loaded), len(network.get("offline") or []),
              "available" if signals_available else "UNAVAILABLE (closed none)",
              "written" if changed else "unchanged"))
    return 0


# --------------------------------------------------------------------------
# REVIEW
# --------------------------------------------------------------------------


def composite(scores: dict, rubric: dict):
    """(composite, partial_composite, scored_ids).

    `composite` is a number ONLY when every criterion carries a score. Anything
    less is a partial, reported separately and alongside the list of what was
    actually scored — because a weighted average over 2 of 5 criteria printed
    as "the editorial score" is exactly the kind of number that ends up on a
    slide.
    """
    total = weight = 0.0
    scored = []
    for crit in rubric["criteria"]:
        value = scores.get(crit["id"])
        if value is None:
            continue
        scored.append(crit["id"])
        total += float(value) * float(crit["weight"])
        weight += float(crit["weight"])
    if not weight:
        return (None, None, [])
    avg = round(total / weight, 2)
    if len(scored) == len(rubric["criteria"]):
        return (avg, None, scored)
    return (None, avg, scored)


def evaluate_flags(scores: dict, rubric: dict) -> list:
    out = []
    for flag in rubric.get("hard_flags") or []:
        value = scores.get(flag["criterion"])
        if value is not None and value <= flag["at_most"]:
            out.append(flag["id"])
    return sorted(out)


def review_video(chan: dict, video: dict, adapter, rubric: dict) -> dict:
    context = {"channel_id": chan.get("id"), "channel_name": chan.get("name"),
               "channel_tagline": chan.get("tagline")}
    result = adapter.review(video, rubric, context)
    raw_scores = (result or {}).get("scores") or {}
    notes = (result or {}).get("notes") or {}
    scores = {}
    for crit in rubric["criteria"]:
        value = raw_scores.get(crit["id"], None)
        if isinstance(value, bool):
            value = None
        if isinstance(value, (int, float)):
            lo, hi = rubric["scale"]["min"], rubric["scale"]["max"]
            value = int(min(hi, max(lo, round(float(value)))))
        else:
            value = None
        scores[crit["id"]] = value
    comp, partial, scored = composite(scores, rubric)
    return {
        "subject": subject_id(chan.get("id"), video.get("id")),
        "channel": chan.get("id"),
        "video": video.get("id"),
        "title": video.get("title") or video.get("id"),
        "rubric": {"id": rubric["id"], "version": rubric["version"]},
        "reviewer": {
            "id": getattr(adapter, "id", "unknown"),
            "kind": getattr(adapter, "kind", "unknown"),
            "judgment": bool(getattr(adapter, "judgment", False)),
        },
        "content_hash": content_hash(video),
        "scores": scores,
        "notes": {k: str(v) for k, v in notes.items() if k in scores},
        "composite": comp,
        "partial_composite": partial,
        "criteria_scored": scored,
        "coverage": "{}/{}".format(len(scored), len(rubric["criteria"])),
        "flags": evaluate_flags(scores, rubric),
    }


def needs_review(existing: dict, video: dict, adapter, rubric: dict) -> bool:
    """True unless an identical review already exists.

    Identical means: same content hash, same rubric version, same reviewer id.
    Skipping here is what stops a nondeterministic model from rewriting the same
    judgement into a fresh commit (and a fresh bill) every night.
    """
    if not isinstance(existing, dict):
        return True
    if existing.get("content_hash") != content_hash(video):
        return True
    if (existing.get("rubric") or {}).get("version") != rubric["version"]:
        return True
    if (existing.get("reviewer") or {}).get("id") != getattr(adapter, "id", "unknown"):
        return True
    return False


def editorial_payload(reviews: dict, rubric: dict, network: dict, adapter,
                      lane: "EditorialLane | None" = None) -> dict:
    judged = [r for r in reviews.values() if (r.get("reviewer") or {}).get("judgment")]
    lane = lane or editorial_lane(STATE_DIR)
    return {
        "schema": SCHEMA_EDITORIAL,
        "lane": LANE_NAME,
        "lane_binding": lane.as_dict(),
        "note": (
            "MACHINE-WRITTEN EDITORIAL SCORES. These are the engine's own opinion of its "
            "own channel. They are NOT viewer signal and must never be summed into, "
            "averaged with, or displayed as human counters — report them in their own "
            "block, labelled. A null score means the reviewer could not judge that "
            "criterion; render it as an em-dash, never as 0."
        ),
        "never_sum_into": ["human_counters", "viewer_signals", "ratings"],
        "rubric": {"id": rubric["id"], "version": rubric["version"],
                   "criteria": [c["id"] for c in rubric["criteria"]]},
        "reviewer": {
            "id": getattr(adapter, "id", "unknown"),
            "kind": getattr(adapter, "kind", "unknown"),
            "judgment": bool(getattr(adapter, "judgment", False)),
        },
        "totals": {
            "reviews": len(reviews),
            "judgment_reviews": len(judged),
            "structural_reviews": len(reviews) - len(judged),
            "flagged": sorted(r["subject"] for r in reviews.values() if r.get("flags")),
        },
        "coverage": {
            "channels_loaded": len(network.get("channels") or []),
            "channels_unreachable": sorted(network.get("offline") or []),
        },
        "reviews": dict(sorted(reviews.items())),
    }


# The lane marker, as a last resort. It is a COPY of
# rapp_metrics.EDITORIAL_MARKER, used only when rapp_metrics cannot be
# imported at all. Every code path that can import it prefers the import, and
# EditorialLane.verified records which happened — a copied constant that is
# never checked against its original is how two files drift apart in silence.
FALLBACK_EDITORIAL_MARKER = "<!-- rapp-vision:editorial -->"

FALLBACK_LANE_NOTE = (
    "Machine-written. Never counted in any human total, ranking, or leaderboard."
)

LANE_NAME = "editorial"


class EditorialLane:
    """The editorial lane, bound to scripts/rapp_metrics.py where possible.

    THE LANE IS NOT A FILE. It is a promise with a mechanism behind it: a
    machine review is attributed to a reviewer id and rubric version, is
    visibly machine-authored wherever it appears, and is summed into no human
    counter, ever.

    rapp_metrics.py implements the mechanism for the GitHub half. Every bot
    comment carries a marker; MACHINERY_MARKERS lists them; and
    human_comment_count() subtracts the comments carrying one from the thread
    total. That subtraction is the ONLY thing standing between a machine
    review and inflating a conversation count simply by existing.

    So this class does not copy the marker and hope. It IMPORTS it, and it
    VERIFIES the marker is still a member of MACHINERY_MARKERS. If that
    membership is ever broken, the review is still written — losing a day of
    reviews is not worth a hard failure — but `verified` goes False, the
    reason is printed, and the snapshot says so in `lane_binding`. A binding
    nobody checks is not a binding.

    The whole import is wrapped: rapp_metrics.py is owned by another writer,
    and an error over there must never take this script down.
    """

    def __init__(self, marker: str, note: str, binding: str,
                 verified: bool, writer=None, problems=None):
        self.marker = marker
        self.note = note
        self.binding = binding
        self.verified = verified
        self.writer = writer
        self.problems = list(problems or [])

    def as_dict(self) -> dict:
        return {
            "lane": LANE_NAME,
            "marker": self.marker,
            "binding": self.binding,
            # False means: this script could not confirm, against
            # rapp_metrics.py itself, that a comment carrying this marker is
            # excluded from the human comment count. Treat any human-facing
            # number derived from this run as unverified until it is fixed.
            "machinery_exclusion_verified": self.verified,
            "problems": sorted(self.problems),
        }


def editorial_lane(state_dir: Path) -> EditorialLane:
    """Resolve and verify the editorial lane. Never raises.

    `state_dir` is accepted so a caller can bind a lane for a repo other than
    this one; the lane itself is code-level, not path-level.
    """
    _ = state_dir
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        rapp_metrics = importlib.import_module("rapp_metrics")
    except Exception as exc:                                  # noqa: BLE001 - never fatal
        return EditorialLane(
            marker=FALLBACK_EDITORIAL_MARKER,
            note=FALLBACK_LANE_NOTE,
            binding="fallback constants (rapp_metrics not importable: {})".format(exc),
            verified=False,
            problems=["rapp_metrics could not be imported; the lane marker is an "
                      "unchecked copy and machinery exclusion is unconfirmed"],
        )

    problems = []
    marker = getattr(rapp_metrics, "EDITORIAL_MARKER", None)
    if not isinstance(marker, str) or not marker.strip():
        problems.append("rapp_metrics defines no EDITORIAL_MARKER; using a copied constant")
        marker = FALLBACK_EDITORIAL_MARKER

    machinery = getattr(rapp_metrics, "MACHINERY_MARKERS", None)
    verified = bool(machinery) and marker in tuple(machinery)
    if not verified:
        problems.append(
            "the editorial marker is not in rapp_metrics.MACHINERY_MARKERS, so a "
            "machine review posted to a thread would be counted as human conversation")

    note = getattr(rapp_metrics, "EDITORIAL_NOTE", None)
    if not isinstance(note, str) or not note.strip():
        note = FALLBACK_LANE_NOTE

    # A writer function is optional and does not exist today. Probing for one
    # costs nothing and means the day rapp_metrics grows a canonical writer,
    # this script uses it without an edit.
    writer, binding = None, "rapp_metrics constants + direct snapshot write"
    for name in ("write_editorial_reviews", "write_editorial",
                 "record_editorial_reviews", "editorial_write"):
        fn = getattr(rapp_metrics, name, None)
        if callable(fn):
            writer, binding = fn, "rapp_metrics.{}()".format(name)
            break

    return EditorialLane(marker=marker, note=note, binding=binding,
                         verified=verified, writer=writer, problems=problems)


def render_lane_comment(subject: str, review: dict, lane: EditorialLane) -> str:
    """The review as a thread comment, in the editorial lane by construction.

    The body STARTS with the lane marker, which is what makes
    rapp_metrics.machinery_comment_count() subtract it from the human comment
    count. Nothing here posts anything — posting is rapp_metrics' `editorial`
    command's job. This exists so the review has one rendering that is safe to
    post, and so a test can prove the marker is present without a network.

    A null score renders as an em-dash. "The reviewer could not judge this"
    and "the reviewer scored this zero" are different claims, and printing 0
    for the first asserts the second.
    """
    scores = review.get("scores") or {}
    lines = [
        lane.marker,
        "### Editorial review — machine-written",
        "",
        "Subject `{}`, rubric `{}` v{}, reviewer `{}`.".format(
            subject,
            (review.get("rubric") or {}).get("id", "?"),
            (review.get("rubric") or {}).get("version", "?"),
            (review.get("reviewer") or {}).get("id", "?"),
        ),
        "",
        "| Criterion | Score |",
        "|---|---|",
    ]
    for crit in RUBRIC["criteria"]:
        value = scores.get(crit["id"])
        lines.append("| {} | {} |".format(
            crit["label"], "—" if value is None else "{}/5".format(value)))
    composite_value = review.get("composite")
    lines += [
        "",
        "**Composite:** {}".format(
            "{}/5".format(composite_value) if composite_value is not None
            else "— (not published: only {} of {} criteria were scored)".format(
                len(review.get("criteria_scored") or []), len(RUBRIC["criteria"]))),
    ]
    if review.get("flags"):
        lines += ["", "**Flags:** " + ", ".join(review["flags"])]
    lines += [
        "",
        "— *{}*. {} Reactions on this comment are counted nowhere; rate the "
        "video on the top post.".format(
            (review.get("reviewer") or {}).get("id", "?"), lane.note),
    ]
    return "\n".join(lines)


def cmd_review(args, state_dir: Path, adapter, network: dict, cfg: dict) -> int:
    path = state_dir / EDITORIAL_NAME
    loaded = network.get("channels") or []
    if network.get("registry_count", 0) and not loaded:
        warn("no channel loaded; leaving {} unchanged".format(path.name))
        return 1 if args.strict else 0

    prior = read_json_file(path) or {}
    reviews = {k: v for k, v in (prior.get("reviews") or {}).items() if isinstance(v, dict)}

    seen_channels = {c.get("id") for c in loaded}
    entries = flatten_videos(network)
    # Deterministic drain order: never-reviewed first, then by subject. A capped
    # run therefore makes progress through a backlog instead of re-chewing the
    # same head of the queue.
    entries.sort(key=lambda t: (t[2] in reviews, t[2]))

    done = failed = skipped = 0
    for chan, video, subj in entries:
        if done >= cfg["review_limit"]:
            break
        if not needs_review(reviews.get(subj), video, adapter, RUBRIC):
            skipped += 1
            continue
        try:
            reviews[subj] = review_video(chan, video, adapter, RUBRIC)
            done += 1
        except Exception as exc:                              # noqa: BLE001 - never fatal
            warn("adapter.review failed on {} ({}); stopping this run".format(subj, exc))
            failed += 1
            break

    # A subject whose channel did not load keeps its existing review untouched.
    # (Nothing above deletes; this comment records the intent for the next reader.)
    _ = seen_channels

    if not reviews and (prior.get("reviews") or {}):
        warn("refusing to replace a non-empty review snapshot with an empty one")
        return 1 if args.strict else 0

    lane = editorial_lane(state_dir)
    for problem in lane.problems:
        warn("editorial lane: " + problem)
    payload = editorial_payload(reviews, RUBRIC, network, adapter, lane)
    writer, how = lane.writer, lane.binding
    changed = False
    if writer is not None:
        try:
            changed = bool(writer(payload, path))
        except Exception as exc:                              # noqa: BLE001 - never fatal
            warn("editorial lane writer failed ({}); falling back to a direct write".format(exc))
            writer, how = None, "direct write (lane writer raised)"
    if writer is None:
        changed = write_json(path, payload, state_dir)

    remaining = max(0, len([e for e in entries if needs_review(reviews.get(e[2]), e[1], adapter, RUBRIC)]))
    print("review: {} scored, {} unchanged, {} still pending, via {} -> {}".format(
        done, skipped, remaining, how, "written" if changed else "unchanged"))
    if failed:
        print("review: stopped early after an adapter failure; the next run resumes here")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_config(args) -> dict:
    cfg = dict(DEFAULTS)
    for key in ("stale_days", "thin_min", "min_signal", "review_limit"):
        value = getattr(args, key, None)
        if value is not None:
            cfg[key] = value
    return cfg


def today_iso() -> str:
    import datetime

    return datetime.date.today().isoformat()


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="content_machine.py",
        description="RAPP Vision content machine: propose episodes, review published ones.")
    p.add_argument("command", choices=["propose", "review", "run", "selftest"])
    p.add_argument("--repo", default=str(REPO_ROOT), help="repository root (default: this file's parent's parent)")
    p.add_argument("--state-dir", default=None, help="override the state directory")
    p.add_argument("--metrics", default=None,
                   help="path to the metrics snapshot to read viewer signals from "
                        "(default: <state>/metrics.json, then <state>/ratings.json)")
    p.add_argument("--site-base", default=os.environ.get("RAPP_VISION_SITE_BASE", DEFAULT_SITE_BASE),
                   help="page URL that origin-relative channel URLs resolve against")
    p.add_argument("--offline", action="store_true", help="never touch the network; local files only")
    p.add_argument("--strict", action="store_true",
                   help="exit non-zero when collection could not complete "
                        "(for callers where this script is the whole job)")
    p.add_argument("--adapter", default=os.environ.get("RAPP_CONTENT_ADAPTER", "dryrun"),
                   help="'dryrun' (default) or 'module:factory'")
    p.add_argument("--allow-model", action="store_true",
                   default=os.environ.get("RAPP_CONTENT_ALLOW_MODEL") == "1",
                   help="permit an adapter that needs model access (costs credits)")
    p.add_argument("--stale-days", type=int, default=None)
    p.add_argument("--thin-min", type=int, default=None)
    p.add_argument("--min-signal", type=int, default=None)
    p.add_argument("--review-limit", type=int, default=None)
    p.add_argument("--today", default=None, help="YYYY-MM-DD used for staleness only (default: today)")
    return p.parse_args(argv)


def run_selftest() -> int:
    """Run tests/test_content_machine.py in-process. No network, no model."""
    test_path = REPO_ROOT / "tests" / "test_content_machine.py"
    if not test_path.is_file():
        print("selftest: {} is missing".format(test_path), file=sys.stderr)
        return 1
    spec = importlib.util.spec_from_file_location("test_content_machine", test_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_content_machine"] = module
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv=None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.command == "selftest":
        return run_selftest()

    args.today = args.today or today_iso()
    repo_root = Path(args.repo).resolve()
    state_dir = Path(args.state_dir).resolve() if args.state_dir else (repo_root / "state")
    cfg = build_config(args)

    adapter, why = load_adapter(args.adapter, args.allow_model)
    if why:
        warn(why)

    network = walk_network(repo_root, args.site_base, args.offline)
    for failure in network.get("offline") or []:
        warn("channel offline -> " + failure)

    metrics_path = Path(args.metrics) if args.metrics else None
    metrics_doc = None
    for candidate in ([metrics_path] if metrics_path else
                      [state_dir / "metrics.json", state_dir / "ratings.json"]):
        metrics_doc = read_json_file(candidate)
        if metrics_doc is not None:
            break
    signal_index = index_signals(metrics_doc)
    signals_available = bool(signal_index)
    if not signals_available:
        warn("no viewer signals available; signal-driven gaps cannot fire this run "
             "and no signal-driven proposal will be closed by it")

    rc = 0
    if args.command in ("propose", "run"):
        rc |= cmd_propose(args, state_dir, adapter, network, signal_index, cfg,
                          signals_available=signals_available)
    if args.command in ("review", "run"):
        rc |= cmd_review(args, state_dir, adapter, network, cfg)
    return rc


if __name__ == "__main__":
    sys.exit(main())
