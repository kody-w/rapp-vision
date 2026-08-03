#!/usr/bin/env python3
"""rapp-metrics/1.0 — GitHub Discussions as the ratings + signal backend
for the RAPP Vision network.

Ported from RAR's ``scripts/discussion_ratings.py``, which has been running
this pattern in production; generalized here for a subject type that is a
*video in a channel* rather than an agent in a registry.

The pattern, unchanged from RAR:

  * One Discussion per subject, whose title IS the subject's canonical id,
    in a maintainer-only category ("Announcements") so nobody can open a
    thread named after somebody else's video and mint their own counters.
    That is true about MINTING and it was never true about BLOCKING: every
    counted read filters to the category, so a same-titled discussion in an
    open category (General) is invisible to all of them — but the seeder's
    "does this already exist" preflight used to look at every category, and
    a squatted title there made it skip the subject forever. The preflight
    filters to the counted category too (``cmd_seed``); titles are not
    unique on GitHub, so the real thread is simply created beside it.
  * A machinery marker is a ROUTING LABEL, NOT A CREDENTIAL. The markers
    are HTML comments — invisible once rendered — so any user who can
    comment on a thread can paste one. A comment counts as machinery only
    when its body STARTS WITH the marker and the machinery actually wrote
    it (``viewerDidAuthor``, or an author login in ``MACHINERY_AUTHORS``).
    See the block above ``MACHINERY_AUTHORS`` for what an unchecked marker
    bought an attacker.
  * An upvote is a *positive* reaction on that Discussion's top post.
    Negative reactions (THUMBS_DOWN, CONFUSED) never contribute, so a
    thumbs-down cannot drag a score down or masquerade as a rating.
    Negative sentiment is not censored — it is routed to its own named
    channels on the signal comment, where it is reported and never summed.
  * One object per metric, never conflated: the top post is endorsement,
    the watch-tally comment is reach, the signal comment is experience.
  * GitHub enforces one reaction per user per subject per emoji, so every
    count published here is a count of *people*, not of clicks.
  * A build-time snapshot (``state/metrics.json``) is what any reader
    consumes. It carries no timestamps, so the file changes only when a
    number changes and git history becomes the time series.

THE ACTOR DETERMINES THE LANE — NEVER THE SUBJECT
-------------------------------------------------
Who PERFORMED an action decides which counter it feeds; not who authored
the thing being acted upon. Both halves of that rule are implemented here:

  1. An automated actor never contributes to a human counter. The machine
     review is written into its own ``editorial`` block, attributed to a
     reviewer id and rubric version, visibly machine-authored, and
     subtracted from the human comment count — or, when the thread is longer
     than the one page of comments this query reads and the subtraction
     therefore cannot be trusted, ``comments`` is published as ``null`` with
     ``comments_truncated: true`` rather than as a number that might have a
     machine's own comments inside it (see ``human_comment_count``). This
     script adds no reaction anywhere — it has no reaction mutation at all,
     so on the reaction path it *cannot* move a
     human number even by mistake.

  2. A human acting at the bot layer IS counted. A person reacting to the
     machine review is real human engagement, so it is collected under
     ``reviewer_feedback`` rather than discarded. Discarding it would be
     quarantining by SUBJECT ("a robot wrote the comment, so ignore
     everything about it"), which is the opposite error: it would make
     machine-authored content unmeasurable.

Those human reactions rate the REVIEWER, not the video, so they are a
different population answering a different question and are summed into no
video counter, no score and no ranking. ``rubric_health`` rolls them up:
sustained dispute is how a wrong rubric becomes visible instead of
accumulating authority nobody granted it.

WHAT IS A SUBJECT HERE
----------------------
Subjects are enumerated by walking ``channels.json`` -> each channel.json
-> ``videos[]``, resolving every channel URL **relative to the network
file**, exactly as the player's ``fetchChannel()`` does
(index.html:994-1017, ``absolutise(entry.url, location.href)``).

A video's ``id`` is only unique inside its own channel.json. The player
treats it as a global key (``byId = id => VIDEOS.find(v => v.id === id)``,
index.html:266) and ``template/channel.json`` ships ``"id":
"my-first-video"`` for every new publisher to copy — so id collisions
across channels are produced by the documented onboarding path, not merely
possible. Every subject id here is therefore CHANNEL-QUALIFIED:

    <channel id>/<video id>        e.g. rock-tumbler/rock-tumbler-showcase

The channel id is the one declared inside the channel FILE (``c.id``),
which is what the player keeps and routes on — never the registry entry id
from channels.json, which for user-added channels is a throwaway
``"custom-" + Date.now()`` (index.html:903).

Subcommands:
  seed       Create missing Discussions for enumerated subjects
             (idempotent, capped per run to stay under content-creation
             rate limits). New threads get their full signal surface at
             creation, so nothing needs back-filling for them.
  surfaces   Provision the marker comments on existing threads
             (idempotent, per-marker, capped; --only targets one subject).
  fetch      Snapshot counts into state/metrics.json.
  editorial  Write/refresh the machine review in the editorial lane —
             attributed, idempotent, and structurally unable to move any
             human counter.

Every subcommand is intentionally NON-FATAL: a missing token, a network
error, an unreadable channels.json, or a missing category produces a
warning and an unchanged snapshot — never a failed build. Exit code is 0.

Usage:
  GITHUB_TOKEN=... python3 scripts/rapp_metrics.py seed [--limit 60]
  GITHUB_TOKEN=... python3 scripts/rapp_metrics.py surfaces [--limit 60]
  GITHUB_TOKEN=... python3 scripts/rapp_metrics.py fetch
  GITHUB_TOKEN=... python3 scripts/rapp_metrics.py editorial [--limit 40]

Config (env, with defaults):
  GITHUB_TOKEN / GH_TOKEN     token with discussions read (fetch) / write
  RAPP_VISION_METRICS_REPO    owner/repo  (default: kody-w/rapp-vision)
  RAPP_VISION_METRICS_CATEGORY   Discussion category (default: Announcements)
  RAPP_VISION_PLAYER_URL      player base URL used in seeded bodies

KNOWN LIMITS, stated rather than discovered later:
  * Comments are read one page deep (``comments(first: 100)``) while
    ``totalCount`` describes the WHOLE thread. Past 100 comments the two
    stop describing the same set, so on such a thread:
      - ``comments`` is published as ``null`` with ``comments_truncated:
        true``. It is NOT published as ``totalCount`` minus the machinery
        found on page one: a machinery comment past position 100 is not in
        the subtrahend and would be counted as a human reply, which is a
        machine's own output landing in a human counter.
      - ``editorial`` becomes update-only. It refreshes the note if the id
        is on the page and otherwise skips with a warning, because a second
        appended note would be a fresh machine comment every night.
    Restoring a number needs nested pagination on the comments connection,
    which is a live-API change this file does not make.
  * Nothing in the player writes to any of this yet. This script provisions
    and reads the surface; wiring a viewer-initiated reaction into
    index.html is a separate change that does not exist in this repo. The
    watch tally counts a deliberate signed-in click, never an automatic
    beacon — the player's "nothing here phones home" copy stays true.
  * Remote (https://) channel URLs are skipped by the enumerator: it reads
    the filesystem so it can run offline in CI. Every channel in
    channels.json today is origin-relative, so this costs nothing now.
  * ``reviewer_feedback`` counts REACTIONS on the machine review. A threaded
    REPLY to that comment is not counted anywhere: GitHub returns replies on
    a separate ``replies`` connection that this query does not request. A
    human reply is human engagement and should count, so this is an
    understatement of the feedback loop, not an inflation of it — the
    direction of the error is the safe one, but it is an error.
  * Machinery ownership is decided by ``viewerDidAuthor`` first, so the
    identity that WROTE a surface is the identity that must READ it. If
    the workflow's token is ever swapped for one with a different actor,
    previously provisioned comments stop being recognised and `surfaces`
    provisions a second copy beside each of them (the counters then read
    the older, still-reacted one only if it is still ours — otherwise they
    read zero until people react on the new comment). The fix is to add the
    old identity to ``RAPP_VISION_METRICS_MACHINERY_AUTHORS`` before
    switching tokens, not after. As of this writing the repo's snapshot has
    ``videos: {}`` and ``editorial: {}`` — nothing is provisioned yet, so
    there is nothing to migrate today.
  * Ownership is checked, PROVENANCE IS NOT. Any actor in
    ``MACHINERY_AUTHORS`` — which on GitHub Actions is the same
    ``github-actions[bot]`` every workflow in the repo runs as — can write
    a comment this script will read as one of its own surfaces. The check
    stops arbitrary users, not a hostile workflow in the same repo; that
    would need a signature over the body, which does not exist here.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
NETWORK_FILE = REPO_ROOT / "channels.json"
SNAPSHOT_FILE = REPO_ROOT / "state" / "metrics.json"

REPO = os.environ.get("RAPP_VISION_METRICS_REPO", "kody-w/rapp-vision")
CATEGORY = os.environ.get("RAPP_VISION_METRICS_CATEGORY", "Announcements")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
PLAYER_URL = os.environ.get(
    "RAPP_VISION_PLAYER_URL", "https://kody-w.github.io/rapp-vision/"
)

SNAPSHOT_SCHEMA = "rapp-vision-metrics/1.0"
USER_AGENT = "rapp-vision-metrics"

# Discussion titles that count as subject threads. Belt: shape check.
# Suspenders: the title must also be a subject the enumerator found.
# Exactly one slash — the character class excludes it — so the shape is
# "<channel>/<video>" and nothing else.
SUBJECT_TITLE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$"
)

# GitHub reaction contents split into sentiment buckets. Only positive
# reactions on the TOP POST count toward the rating. The negative and
# neutral buckets exist so the split is written down once, and so a test
# can assert they never overlap.
POSITIVE_REACTIONS = frozenset(
    {"THUMBS_UP", "HEART", "HOORAY", "ROCKET", "LAUGH"}
)
NEGATIVE_REACTIONS = frozenset({"THUMBS_DOWN", "CONFUSED"})
NEUTRAL_REACTIONS = frozenset({"EYES"})

# Storefront-style ranking. This weighting is a CONVENTION, not a
# measurement: an endorsement is scarcer than a view, so it is worth more.
# Both components are published beside it, so anyone who disagrees with the
# weights can recompute from the parts.
RANK_UPVOTE_WEIGHT = 2

# ── The signal surface: a comment used as an eight-option poll ───────────
#
# GitHub Discussions has a real poll type, but `createDiscussion` accepts
# only repositoryId/title/body/categoryId — polls can ONLY be created by
# hand in the web UI. A signal surface that needs a human to click through
# the web UI once per video is not a pattern; it is a chore that will not
# survive the network growing.
#
# A comment IS creatable over the API, and every comment carries all eight
# reaction contents as independent, per-user-deduped counters. One comment
# therefore behaves as an eight-option poll and gets provisioned
# automatically for every video the moment it enters a channel.
WATCH_MARKER = "<!-- rapp-vision:watch-tally -->"
SIGNAL_MARKER = "<!-- rapp-vision:signal -->"
EDITORIAL_MARKER = "<!-- rapp-vision:editorial -->"

# Reaction content -> the snapshot key it feeds. LAUGH is deliberately
# unmapped: there is no honest question about a video that it answers, and
# an option that means nothing pollutes every other count.
#
# THUMBS_DOWN and CONFUSED are mapped to NAMED NEGATIVE channels. They are
# collected and published; they are never subtracted from anything. A
# viewer who bounced has told you something worth keeping, and burying it
# in a net score destroys the information.
SIGNAL_MAP = {
    "THUMBS_UP": "watched_it_all",
    "HOORAY": "learned_something",
    "HEART": "want_more_like_this",
    "ROCKET": "tried_it_myself",
    "EYES": "saved_for_later",
    "THUMBS_DOWN": "too_long",
    "CONFUSED": "confusing",
}

# Named negatives. Reported in their own right, never netted against a
# positive, never summed into `score`.
NEGATIVE_SIGNALS = frozenset({"too_long", "confusing"})

WATCH_BODY = (
    WATCH_MARKER
    + "\n### ▶️ Watch tally\n\n"
    "Viewers react :+1: **on this comment** to say *I watched this* — one "
    "reaction per GitHub account, so the number reads as **people**, not "
    "plays. It is a deliberate click by a signed-in viewer; the player "
    "never writes anything on its own and nothing about your watching "
    "leaves your browser unless you tap here.\n\n"
    "Rating the video? React on the **top post**, not on this comment."
)

SIGNAL_BODY = (
    SIGNAL_MARKER
    + "\n### How was this one?\n\n"
    "React **on this comment** — one tap, no form. Pick as many as apply.\n\n"
    "| React | Means |\n"
    "|---|---|\n"
    "| :+1: | I watched the whole thing |\n"
    "| :tada: | I learned something |\n"
    "| :heart: | I want more like this |\n"
    "| :rocket: | I went and tried it myself |\n"
    "| :eyes: | Saving this for later |\n"
    "| :-1: | Too long — it lost me |\n"
    "| :confused: | I found this confusing |\n\n"
    "The last two are real answers, not complaints: they are counted and "
    "published under their own names, and they never subtract from "
    "anything. One reaction per person per row, so every count is "
    "*people*, not clicks. Something specific to say? Reply in the thread "
    "— a sentence is worth more than any of these."
)

# Every marker a thread should carry, in provisioning order. Adding an
# entry here is all it takes for a new signal surface to be created on
# every video, old and new, by the same idempotent provisioner.
MARKERS = {
    "watch": (WATCH_MARKER, WATCH_BODY),
    "signal": (SIGNAL_MARKER, SIGNAL_BODY),
}

# Every comment this script or any bot writes. These are machinery, not
# conversation: their count is subtracted from the human comment count, and
# their reactions are never read into any human counter. EDITORIAL_MARKER
# is here but NOT in MARKERS — the editorial lane is written by the
# `editorial` command, not provisioned as a poll.
MACHINERY_MARKERS = (WATCH_MARKER, SIGNAL_MARKER, EDITORIAL_MARKER)

# ── A MARKER IS NOT A CREDENTIAL ────────────────────────────────────────
#
# The markers above are HTML comments, which means they render as nothing.
# Anyone who can comment on a public thread can paste one into an
# ordinary-looking sentence, and until the ownership check below existed
# that was enough to (a) donate their comment's reaction counts to
# `watched` / `signals` / `reviewer_feedback`, (b) get themselves
# subtracted from the human comment count, and (c) aim the editorial
# lane's `updateDiscussionComment` at their own comment. A marker is a
# ROUTING LABEL, never proof of who wrote the thing carrying it.
#
# So a comment is machinery only when BOTH hold:
#   1. its body STARTS WITH the marker — every body this script writes is
#      built marker-first (WATCH_BODY, SIGNAL_BODY, render_editorial), so
#      an anchored test costs nothing and removes "mentioned in passing";
#   2. the machinery actually wrote it — `viewerDidAuthor` (the token
#      running now is the author) or an author login on the allowlist.
#
# `viewerDidAuthor` is what makes this work without configuration: the
# workflow's GITHUB_TOKEN both writes and reads these comments, so it
# recognises its own work. The login allowlist is the escape hatch for a
# thread seeded under a different identity (a PAT, a migrated bot); it is
# env-overridable so a repo that needs it does not need a code change.
#
# Nothing that fails this test is deleted, hidden or penalised — it is
# simply treated as what it is: a human comment, counted in the human
# comment count, and read into no machinery counter.
MACHINERY_AUTHORS = frozenset(
    login.strip()
    for login in os.environ.get(
        "RAPP_VISION_METRICS_MACHINERY_AUTHORS", "github-actions[bot]"
    ).split(",")
    if login.strip()
)

# ── The editorial lane ──────────────────────────────────────────────────
#
# A machine-written review, kept in a lane of its own and attributed on
# every surface it appears on. It is reported next to the human counts and
# summed into none of them: robots must never become your engagement
# numbers.
EDITORIAL_BY = "rapp-vision-rubric/1.0"
EDITORIAL_NOTE = (
    "Machine-written from the channel record by a deterministic rubric. "
    "Never counted in any human total, ranking, or leaderboard."
)
VERDICT_READY = "ready"
VERDICT_ROUGH = "rough"

# How many editorial writes may fail back-to-back before the run gives up.
# One failing thread is skipped so it cannot stall the ones behind it; a
# whole batch failing is a bad API day and there is nothing to gain by
# walking the rest of it into the same wall.
EDITORIAL_CONSECUTIVE_FAILURES = 3

# ── the community rating the REVIEWER ───────────────────────────────────
#
# THE ACTOR DETERMINES THE LANE — NEVER THE SUBJECT.
#
# The rubric's own output is a machine ACTION, so it feeds no human counter
# (that is the whole point of the editorial lane). But a person reacting to
# that machine review is a HUMAN acting at the bot layer, and a human action
# always counts. Dropping these would be quarantining by SUBJECT — "the
# comment was written by a robot, so ignore everything about it" — which is
# the opposite error, and it throws away the most useful signal the lane
# produces.
#
# Because these are human counts they are real engagement; because they are
# ABOUT the reviewer and not about the video, they live in the editorial
# block and are summed into no video counter, no score and no ranking. Two
# populations answering two different questions are never added together.
#
# Sustained dispute is the feedback loop: if humans keep thumbs-downing the
# rubric's verdicts, the rubric is wrong. `rubric_health` in the snapshot
# exposes exactly that, so a bad rubric is visible rather than authoritative.
REVIEWER_FEEDBACK_MAP = {
    "THUMBS_UP": "agreed",
    "THUMBS_DOWN": "disputed",
    "CONFUSED": "unclear",
}

MIN_DESCRIPTION_CHARS = 60
CHAPTER_THRESHOLD_SECONDS = 180

# How many comments per thread DISCUSSIONS_QUERY asks for, as a number the
# code can reason about. GitHub returns min(totalCount, this) nodes, so a
# response holding exactly this many nodes while reporting a larger
# totalCount is the signature of a thread we have only partly read — which
# is what `comments_truncated()` keys on. A test pins this against the
# literal in the query below, because the two drifting apart would make a
# truncated thread look complete.
COMMENT_PAGE_SIZE = 100

DISCUSSIONS_QUERY = """
query ($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    discussions(first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        number
        title
        url
        category { name }
        comments(first: 100) {
          totalCount
          nodes {
            id
            body
            # WHO WROTE IT, not just what it says. A machinery marker is an
            # HTML comment any user can paste; these two fields are what
            # make "this is one of ours" checkable. viewerDidAuthor is the
            # primary test (the token reading this is the token that wrote
            # it); author.login backs it up for a comment seeded under a
            # different identity. See MACHINERY_AUTHORS.
            viewerDidAuthor
            author { login }
            reactionGroups { content reactors { totalCount } }
          }
        }
        reactionGroups { content reactors { totalCount } }
      }
    }
  }
}
"""

ADD_COMMENT_MUTATION = """
mutation ($discussionId: ID!, $body: String!) {
  addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
    comment { id }
  }
}
"""

UPDATE_COMMENT_MUTATION = """
mutation ($commentId: ID!, $body: String!) {
  updateDiscussionComment(input: {commentId: $commentId, body: $body}) {
    comment { id }
  }
}
"""

SEED_INFO_QUERY = """
query ($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    id
    discussionCategories(first: 25) { nodes { id name } }
  }
}
"""

CREATE_DISCUSSION_MUTATION = """
mutation ($repoId: ID!, $catId: ID!, $title: String!, $body: String!) {
  createDiscussion(input: {
    repositoryId: $repoId, categoryId: $catId, title: $title, body: $body
  }) {
    discussion { id number url }
  }
}
"""


def warn(msg: str) -> None:
    print(f"[rapp-metrics] {msg}", file=sys.stderr)


def graphql(query: str, variables: dict) -> dict:
    """POST a GraphQL query. Raises on transport or GraphQL errors.

    Every caller wraps this; nothing above it is allowed to fail a build.

    ONE EXCEPTION CONTRACT FOR CALLERS. Callers catch
    ``(OSError, RuntimeError, urllib.error.URLError)``, so anything this
    function can raise must land inside that set. Reading and PARSING the
    response therefore happens inside the same guard as the request: a 200
    carrying an HTML interstitial (a CDN maintenance page — GitHub's
    classic degraded-mode response) raises ``json.JSONDecodeError``, a
    truncated body raises ``http.client.IncompleteRead``, and a non-UTF-8
    body raises ``UnicodeDecodeError``. None of those are OSError or
    URLError, so before this guard existed each one escaped every caller
    and failed the build the module docstring promises can never fail.
    They are normalised to RuntimeError here rather than caught in five
    places, so the contract stays in one function.
    """
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except (ValueError, http.client.HTTPException) as exc:
        # ValueError covers JSONDecodeError and UnicodeDecodeError;
        # HTTPException covers IncompleteRead and friends.
        raise RuntimeError(
            f"GitHub returned an unusable response: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"GitHub returned a {type(payload).__name__}, not an object"
        )
    if payload.get("errors"):
        raise RuntimeError(
            "; ".join(e.get("message", "?") for e in payload["errors"])
        )
    data = payload.get("data")
    if not data:
        raise RuntimeError("GitHub GraphQL returned no data")
    return data


# Substrings GitHub uses when it is asking you to slow down. Matched
# case-insensitively against the exception text.
RATE_LIMIT_HINTS = (
    "rate limit",
    "secondary rate",
    "abuse detection",
    "too many requests",
    "was submitted too quickly",
    "retry your request",
)


def looks_rate_limited(exc: BaseException) -> bool:
    """Is this failure "the whole API is telling us to stop" or "this one
    thing did not work"?

    The distinction decides whether a write loop breaks or continues. A
    rate limit applies to every remaining item, so continuing burns the
    budget and achieves nothing — break. A per-item failure (a locked
    thread, a comment somebody deleted, a permission quirk on one object)
    says nothing about the next item — continue, or one bad thread stalls
    every thread behind it, forever, on every run.
    """
    code = getattr(exc, "code", None)
    if code in (403, 429):
        return True
    text = str(exc).lower()
    return any(hint in text for hint in RATE_LIMIT_HINTS)


# ── subject enumeration ─────────────────────────────────────────────────


def read_json(path: Path) -> dict | None:
    """Parse a JSON file. None on any problem — one unreadable channel
    must not blank the network (index.html:1030 uses Promise.allSettled
    for exactly this reason)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        warn(f"could not read {path}: {exc}")
        return None


def resolve_channel_ref(url: str | None, network_file: Path) -> Path | None:
    """Resolve a channels.json entry URL to a path on disk.

    Mirrors the player's ``absolutise(entry.url, location.href)``: the
    reference resolves against the NETWORK FILE, not the process's working
    directory, so ``../localFirstTools/rappvision/channel.json`` means the
    sibling repo checkout regardless of where this script is run from.

    Returns None (with a warning) for anything not resolvable on disk.
    """
    if not url:
        warn("channel entry has no url; skipped.")
        return None
    text = str(url).strip()
    if text.startswith("//"):
        warn(f"{text}: protocol-relative URL; enumeration reads the "
             "filesystem, so this channel is skipped.")
        return None
    parts = urlsplit(text)
    if parts.scheme:
        warn(f"{text}: '{parts.scheme}://' URL; enumeration reads the "
             "filesystem, so this channel is skipped.")
        return None
    path = parts.path
    if not path:
        warn(f"{text}: no path component; skipped.")
        return None
    if path.startswith("/"):
        # Root-relative resolves against the ORIGIN in a browser. There is
        # no origin on a filesystem, and guessing one would silently read
        # the wrong tree.
        warn(f"{text}: root-relative URL has no filesystem meaning; skipped.")
        return None
    return (Path(network_file).resolve().parent / path).resolve()


def load_network_entries(network_file: Path) -> list[dict]:
    """Channel entries from channels.json, deduped by entry id.

    Same dedupe the player does at index.html:1027-1028. Empty list on any
    problem — a missing or broken network file is a warning, not a crash.
    """
    data = read_json(Path(network_file))
    if not isinstance(data, dict):
        return []
    entries: list[dict] = []
    seen: set[str] = set()
    for entry in data.get("channels") or []:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or "").strip()
        if entry_id and entry_id in seen:
            warn(f"duplicate channel entry id '{entry_id}'; keeping the first.")
            continue
        if entry_id:
            seen.add(entry_id)
        entries.append(entry)
    return entries


def subject_id(channel_id: str, video_id: str) -> str:
    """The canonical, channel-qualified subject id.

    One function, called by everything that needs a key, so a bare video id
    can never leak into a counter. RAR's worst metrics bug was a join key
    written two ways: it failed silently and looked exactly like an honest
    empty state.
    """
    return f"{str(channel_id).strip()}/{str(video_id).strip()}"


def enumerate_subjects(network_file: Path | str | None = None) -> dict[str, dict]:
    """Walk channels.json -> channel.json -> videos[] into subjects.

    Returns ``{subject_id: {channel, channel_name, video, title, record,
    channel_file}}`` in network order. Any channel that cannot be read is
    skipped with a warning and the rest still enumerate.
    """
    net = Path(network_file or NETWORK_FILE)
    subjects: dict[str, dict] = {}
    for entry in load_network_entries(net):
        path = resolve_channel_ref(entry.get("url"), net)
        if path is None:
            continue
        channel = read_json(path)
        if not isinstance(channel, dict):
            continue
        # The id inside the FILE wins — that is the one the player keeps on
        # the object and routes on (#/channel/<id>, state.subs). The entry
        # id is only a fallback, because a channel file with no id would
        # otherwise produce the subject "None/<video>".
        channel_id = str(channel.get("id") or entry.get("id") or "").strip()
        if not channel_id:
            warn(f"{path}: channel has no id and its entry has none; skipped.")
            continue
        videos = channel.get("videos")
        if not isinstance(videos, list):
            warn(f"{path}: no videos[] array; skipped.")
            continue
        for record in videos:
            if not isinstance(record, dict):
                continue
            video_id = str(record.get("id") or "").strip()
            if not video_id:
                warn(f"{channel_id}: a video has no id; skipped.")
                continue
            sid = subject_id(channel_id, video_id)
            if not is_subject_title(sid):
                warn(f"{sid}: not a well-shaped subject id; skipped.")
                continue
            if sid in subjects:
                # Deterministic: first occurrence wins, matching the
                # player's first-match byId(). A collision INSIDE one
                # channel is a publisher bug worth naming.
                warn(f"{sid}: duplicate subject id; keeping the first.")
                continue
            subjects[sid] = {
                "channel": channel_id,
                "channel_name": str(channel.get("name") or ""),
                "video": video_id,
                "title": str(record.get("title") or ""),
                "record": record,
                "channel_file": str(path),
            }
    return subjects


def is_subject_title(title: str) -> bool:
    return bool(SUBJECT_TITLE_RE.match(str(title).strip()))


# ── counting ────────────────────────────────────────────────────────────


def positive_score(reaction_groups: list | None) -> int:
    """Sum reactors across positive reaction groups only.

    Negative and neutral groups are read and discarded here — they cannot
    subtract, because there is no subtraction anywhere in this function.
    """
    total = 0
    for group in reaction_groups or []:
        if group.get("content") in POSITIVE_REACTIONS:
            total += (group.get("reactors") or {}).get("totalCount", 0)
    return total


def machinery_authored(comment: dict) -> bool:
    """Did the machinery itself write this comment?

    ``viewerDidAuthor`` first: the token reading the thread is the token
    that wrote these comments, so it recognises its own work with no
    configuration at all. The login allowlist is the fallback for a thread
    provisioned under a different identity.

    Missing/unknown authorship is NOT machinery. A deleted account returns
    ``author: null``, and a comment nobody can attribute must fall to the
    human side: the cost of that is one machinery comment counted as
    conversation, while the cost of the other default is any stranger
    minting counters.
    """
    if comment.get("viewerDidAuthor"):
        return True
    login = (comment.get("author") or {}).get("login")
    return bool(login) and login in MACHINERY_AUTHORS


def is_machinery_comment(comment: dict) -> bool:
    """A machinery comment = OUR marker at the head AND our authorship.

    One predicate, used by every reader of these comments, so a marker can
    never mean one thing to the counter and another to the writer.
    """
    body = comment.get("body") or ""
    return (
        any(body.startswith(marker) for marker in MACHINERY_MARKERS)
        and machinery_authored(comment)
    )


def marker_comment_of(node: dict, marker: str) -> dict | None:
    """The MACHINERY comment carrying ``marker``, if it is provisioned.

    Anchored (``startswith``) and ownership-checked. A human comment that
    quotes or pastes the marker is not a surface: it is a human comment,
    and it is left in the human comment count where it belongs. Returning
    None for one makes `surfaces` provision the real comment beside it,
    which is the self-healing behaviour — the squatter is out-counted, not
    argued with.
    """
    for comment in ((node.get("comments") or {}).get("nodes") or []):
        if (comment.get("body") or "").startswith(marker) and \
                machinery_authored(comment):
            return comment
    return None


def watch_comment_of(node: dict) -> dict | None:
    return marker_comment_of(node, WATCH_MARKER)


def editorial_comment_of(node: dict) -> dict | None:
    return marker_comment_of(node, EDITORIAL_MARKER)


def empty_signals() -> dict[str, int]:
    """All channels at zero, in a fixed order so the snapshot is stable."""
    return {key: 0 for key in SIGNAL_MAP.values()}


def signal_counts(node: dict) -> dict[str, int]:
    """Per-reaction people-counts from the signal comment.

    Each of the eight reaction contents is an independent, one-per-user
    counter, so this reads as *how many distinct people said each thing* —
    not how many times it was clicked. An absent surface yields all zeros,
    so a thread nobody has provisioned is the same shape as one nobody has
    answered and callers need no special case.
    """
    counts = empty_signals()
    comment = marker_comment_of(node, SIGNAL_MARKER)
    if not comment:
        return counts
    for group in comment.get("reactionGroups") or []:
        key = SIGNAL_MAP.get(group.get("content"))
        if key:
            counts[key] = (group.get("reactors") or {}).get("totalCount", 0)
    return counts


def watch_count(node: dict) -> int:
    """THUMBS_UP reactors on the watch tally — one per unique viewer."""
    comment = watch_comment_of(node)
    if not comment:
        return 0
    for group in comment.get("reactionGroups") or []:
        if group.get("content") == "THUMBS_UP":
            return (group.get("reactors") or {}).get("totalCount", 0)
    return 0


def machinery_comment_count(node: dict) -> int:
    """How many bot-written comments are actually present on this node.

    Counts COMMENTS carrying a machinery marker, not markers found — so if
    a surface ever gets provisioned twice, both copies are excluded from
    the human total instead of one being counted as conversation.

    Computed from what is there, not a constant, so the human comment count
    stays honest as markers are added — and so the editorial lane can never
    inflate a conversation count by existing.

    Uses the SAME predicate as `marker_comment_of`, and that identity is
    the point: if a marker in a stranger's comment were enough to be
    subtracted here, anyone could delete themselves from the human comment
    count of any thread by pasting an invisible string.
    """
    return sum(
        1 for comment in ((node.get("comments") or {}).get("nodes") or [])
        if is_machinery_comment(comment)
    )


def comments_truncated(node: dict) -> bool:
    """Is this thread longer than the one page of comments we actually read?

    ``DISCUSSIONS_QUERY`` asks for ``comments(first: COMMENT_PAGE_SIZE)`` but
    the connection also reports ``totalCount`` for the WHOLE thread. GitHub
    returns ``min(totalCount, COMMENT_PAGE_SIZE)`` nodes, so "we read a FULL
    page and totalCount is bigger than it" is exactly "there are comments
    here we have not seen".

    Both halves matter. Without the full-page half, any fixture or response
    that reports more comments than it lists reads as truncated; without the
    totalCount half, a thread sitting at exactly one page reads as truncated
    forever. The unseen comments are the problem: they include machinery
    comments, which is what makes the subtraction in ``human_comment_count``
    unsafe and the append in ``editorial_targets`` non-idempotent.
    """
    comments = node.get("comments") or {}
    total = comments.get("totalCount", 0) or 0
    read = len(comments.get("nodes") or [])
    return read >= COMMENT_PAGE_SIZE and total > read


def human_comment_count(node: dict):
    """People who replied in the thread — or ``None`` when we cannot say.

    The count is ``totalCount`` (the whole thread) minus the machinery
    comments FOUND (one page). Those two numbers describe different
    populations the moment the thread is longer than a page: a machinery
    comment sitting at position 101 is not in the subtrahend, so it is counted
    as a human reply. That inflates a HUMAN counter with a machine's own
    output, which is the one thing this file is not allowed to do (§1.1 of the
    spec, and the header of this module).

    So a truncated thread publishes ``None``: unknown is null, never a wrong
    integer (spec F7). It is the honest answer and it degrades correctly — the
    player's ``numOr()`` renders null as nothing rather than as zero.

    The fix that would restore a number is nested pagination on the comments
    connection. That is a live-API change and is not made here; ``fetch``
    marks the entry ``comments_truncated`` so the gap is visible in the
    published document rather than only in this docstring.
    """
    if comments_truncated(node):
        return None
    total = (node.get("comments") or {}).get("totalCount", 0)
    return max(0, total - machinery_comment_count(node))


def build_snapshot(
    discussions: list[dict],
    subject_ids: set[str],
    category: str = CATEGORY,
) -> dict[str, dict]:
    """Filter discussions down to real subject threads and count them.

    Only discussions in ``category`` whose title is subject-shaped AND
    present in the enumerated subjects count. Belt and suspenders: the
    shape check alone would admit a well-formed name for a video that does
    not exist, and the membership check alone would admit any title a
    maintainer typo'd into the right category.

    If duplicate threads exist for one subject, the lowest discussion
    number (the earliest, i.e. the seeded one) wins, so the count cannot
    flip between two threads depending on API page order.
    """
    videos: dict[str, dict] = {}
    for node in discussions:
        if ((node.get("category") or {}).get("name")) != category:
            continue
        title = str(node.get("title", "")).strip()
        if not is_subject_title(title) or title not in subject_ids:
            continue
        upvotes = positive_score(node.get("reactionGroups"))
        watched = watch_count(node)
        channel, _, video = title.partition("/")
        entry = {
            "channel": channel,
            "video": video,
            "upvotes": upvotes,
            "watched": watched,
            # A ranking convention, not a measurement. Both components are
            # published above it; negatives are not in it and never will be.
            "score": RANK_UPVOTE_WEIGHT * upvotes + watched,
            "comments": human_comment_count(node),
            "signals": signal_counts(node),
            "url": node.get("url", ""),
            "number": node.get("number", 0),
        }
        # Present ONLY when it is true, so a normal thread's bytes are
        # unchanged (M23) and the flag is never a field a reader has to
        # interpret when it says nothing. It is the reason `comments` above
        # is null: the count is unknowable from one page, not zero.
        if comments_truncated(node):
            entry["comments_truncated"] = True
        existing = videos.get(title)
        if existing is None or entry["number"] < existing["number"]:
            videos[title] = entry
    return videos


# ── the editorial lane ──────────────────────────────────────────────────


def record_fingerprint(record: dict) -> str:
    """sha256 (first 8 hex) of the channel record, minus player-attached
    fields. An editorial verdict is always attributable to the exact
    record it was written against."""
    clean = {
        k: v for k, v in (record or {}).items() if not str(k).startswith("_")
    }
    blob = json.dumps(
        clean, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8]


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def editorial_checks(record: dict) -> list[dict]:
    """Deterministic, offline checks against the channel RECORD.

    This rubric reads the metadata a publisher declared. It does not open
    the media, so it can say a WebM source is declared and cannot say the
    file decodes. Every check is a property anyone can verify by reading
    channel.json, which is the only kind of claim a machine reviewer has
    any business making.

    States are pass / fail / n_a. An n_a is not a failure: a live-replay
    channel that ships no video file is doing that on purpose.
    """
    record = record or {}
    checks: list[dict] = []

    def add(name: str, state: str, detail: str) -> None:
        checks.append({"check": name, "state": state, "detail": detail})

    sources = record.get("sources") or []
    sources = [s for s in sources if isinstance(s, dict)]
    live = record.get("live") if isinstance(record.get("live"), dict) else None

    # 1. WebM fallback. README: headless Chromium has no H.264 decoder, so
    #    a WebM source is what makes an entry verifiable in CI.
    if not sources:
        add("webm_fallback", "n_a",
            "No video sources — nothing to encode (live-replay entry).")
    else:
        has_webm = any(
            "webm" in str(s.get("type", "")).lower()
            or str(s.get("src", "")).lower().endswith(".webm")
            for s in sources
        )
        add("webm_fallback", "pass" if has_webm else "fail",
            "WebM source declared." if has_webm else
            "No WebM source: headless Chromium cannot decode H.264, so this "
            "entry cannot be verified in CI.")

    # 2. Thumbnail. A card with no thumb is a hole in every grid.
    thumb = str(record.get("thumb") or record.get("poster") or "").strip()
    add("thumb_declared", "pass" if thumb else "fail",
        "Thumbnail declared." if thumb else
        "No thumb (or poster) — the card renders empty in every grid.")

    # 3. A description a reader can use.
    description = str(record.get("description") or "").strip()
    if len(description) >= MIN_DESCRIPTION_CHARS:
        add("description_present", "pass",
            f"Description is {len(description)} characters.")
    else:
        add("description_present", "fail",
            f"Description is {len(description)} characters; under "
            f"{MIN_DESCRIPTION_CHARS} it tells a viewer nothing.")

    # 4. Duration. The player formats it on every card.
    duration = _num(record.get("duration"))
    add("duration_declared", "pass" if duration > 0 else "fail",
        f"Duration {duration:g}s." if duration > 0 else
        "No positive duration declared.")

    # 5. Dimensions drive the card's aspect and the portrait/SHORT badge.
    width, height = _num(record.get("width")), _num(record.get("height"))
    ok_dims = width > 0 and height > 0
    add("dimensions_declared", "pass" if ok_dims else "fail",
        f"{width:g}x{height:g}." if ok_dims else
        "Width/height missing — the player cannot lay the card out.")

    # 6. Chapters, but only where they would earn their keep.
    chapters = record.get("chapters") or []
    if duration <= CHAPTER_THRESHOLD_SECONDS:
        add("chapters_for_long_entry", "n_a",
            f"Under {CHAPTER_THRESHOLD_SECONDS}s — chapters optional.")
    else:
        add("chapters_for_long_entry", "pass" if chapters else "fail",
            f"{len(chapters)} chapter(s)." if chapters else
            f"Over {CHAPTER_THRESHOLD_SECONDS}s with no chapters — nothing "
            "to navigate by.")

    # 7. Live scenes must declare readiness. README:145-148 — without
    #    `ready`, action times run from scene start and a slow app is driven
    #    before it exists. That failure does not look broken; it looks like
    #    a video of an app sitting still.
    if not live:
        add("live_scenes_declare_ready", "n_a", "Not a live-replay entry.")
    else:
        scenes = [s for s in (live.get("scenes") or []) if isinstance(s, dict)]
        app_scenes = [s for s in scenes if s.get("app")]
        if not app_scenes:
            add("live_scenes_declare_ready", "n_a",
                "No scene drives an app.")
        else:
            missing = [
                i for i, s in enumerate(app_scenes)
                if not isinstance(s.get("ready"), dict)
                or not (s["ready"].get("selector") or s["ready"].get("text"))
            ]
            add("live_scenes_declare_ready", "pass" if not missing else "fail",
                "Every app scene declares ready." if not missing else
                f"{len(missing)} of {len(app_scenes)} app scene(s) declare no "
                "ready{selector|text}; their action times run from scene "
                "start.")

    # 8. Tags are the only discovery surface the player has besides search.
    tags = [t for t in (record.get("tags") or []) if str(t).strip()]
    add("tags_declared", "pass" if tags else "fail",
        f"{len(tags)} tag(s)." if tags else "No tags — undiscoverable.")

    return checks


def editorial_review(record: dict) -> dict:
    """The machine review for one subject. Pure, deterministic, offline.

    The SAME function feeds both the snapshot and the comment written back
    to the thread, so the two can never disagree. Nobody types a field.
    """
    checks = editorial_checks(record)
    passed = [c for c in checks if c["state"] == "pass"]
    failed = [c for c in checks if c["state"] == "fail"]
    skipped = [c for c in checks if c["state"] == "n_a"]
    return {
        "by": EDITORIAL_BY,
        "note": EDITORIAL_NOTE,
        "verdict": VERDICT_READY if not failed else VERDICT_ROUGH,
        "checks_passed": len(passed),
        "checks_total": len(passed) + len(failed),
        "not_applicable": len(skipped),
        "notes": [c["detail"] for c in failed],
        "record_sha8": record_fingerprint(record),
    }


def empty_reviewer_feedback() -> dict[str, int]:
    return {key: 0 for key in REVIEWER_FEEDBACK_MAP.values()}


def reviewer_feedback(node: dict) -> dict[str, int]:
    """HUMAN reactions on the machine review — the community rating the rubric.

    These are people acting at the bot layer, so they count as human
    engagement (the actor decides the lane, not the subject). They answer a
    question about the REVIEWER, so they are reported here and summed into
    no video counter, no score, and no ranking.

    An absent or unreacted editorial comment reads as all zeros, so an
    unprovisioned lane has the same shape as one nobody has answered.
    """
    counts = empty_reviewer_feedback()
    comment = editorial_comment_of(node)
    if not comment:
        return counts
    for group in comment.get("reactionGroups") or []:
        key = REVIEWER_FEEDBACK_MAP.get(group.get("content"))
        if key:
            counts[key] = (group.get("reactors") or {}).get("totalCount", 0)
    return counts


def build_editorial(
    subjects: dict[str, dict],
    discussions: list[dict] | None = None,
    category: str = CATEGORY,
) -> dict[str, dict]:
    """The editorial block: the machine verdict plus the humans' verdict ON it.

    Pure and offline-testable. The review itself is derived from the channel
    record, so it covers every enumerated subject including ones with no
    thread yet. ``reviewer_feedback`` is folded in from the thread when there
    is one — the same earliest-wins tiebreak as ``build_snapshot``, so the
    two blocks can never disagree about which thread is authoritative.
    """
    by_subject: dict[str, dict] = {}
    for node in sorted(discussions or [], key=lambda n: n.get("number", 0)):
        if ((node.get("category") or {}).get("name")) != category:
            continue
        title = str(node.get("title", "")).strip()
        if not is_subject_title(title) or title not in subjects:
            continue
        by_subject.setdefault(title, node)   # earliest number wins
    editorial: dict[str, dict] = {}
    for sid, meta in subjects.items():
        review = editorial_review(meta.get("record") or {})
        node = by_subject.get(sid)
        review["reviewer_feedback"] = (
            reviewer_feedback(node) if node else empty_reviewer_feedback()
        )
        # Named so no reader can mistake whose engagement this is.
        review["reviewer_feedback"]["actor"] = "human"
        editorial[sid] = review
    return editorial


def rubric_health(editorial: dict[str, dict]) -> dict:
    """Portfolio view of what humans think of the machine reviewer.

    Sustained negative human signal on the rubric's verdicts means the
    rubric is wrong. Publishing that beside the verdicts is what keeps a
    machine reviewer accountable to the people it reviews for, instead of
    accumulating authority nobody granted it.
    """
    agreed = disputed = unclear = 0
    contested: list[str] = []
    for sid in sorted(editorial):
        feedback = (editorial[sid] or {}).get("reviewer_feedback") or {}
        a = int(feedback.get("agreed", 0) or 0)
        d = int(feedback.get("disputed", 0) or 0)
        u = int(feedback.get("unclear", 0) or 0)
        agreed += a
        disputed += d
        unclear += u
        if d > a:
            contested.append(sid)
    return {
        "actor": "human",
        "agreed": agreed,
        "disputed": disputed,
        "unclear": unclear,
        "subjects_where_dispute_leads": contested,
        "note": (
            "Human reactions on the machine review — people rating the "
            "REVIEWER, not the video. Real human engagement, counted as "
            "such, and summed into no video counter or ranking. Sustained "
            "dispute means the rubric is wrong."
        ),
    }


def render_editorial(sid: str, review: dict) -> str:
    """The editorial comment body. Byte-stable for an unchanged review, so
    a quiet day costs zero writes."""
    verdict = review.get("verdict", VERDICT_ROUGH)
    head = "✅ ready" if verdict == VERDICT_READY else "🛠 rough"
    lines = [
        EDITORIAL_MARKER,
        "### Editorial note — machine-written",
        "",
        f"**{head}** — {review.get('checks_passed', 0)} of "
        f"{review.get('checks_total', 0)} checks pass "
        f"({review.get('not_applicable', 0)} not applicable) on record "
        f"`{review.get('record_sha8', '')}` of `{sid}`.",
        "",
    ]
    notes = review.get("notes") or []
    if notes:
        lines.append("What a reader would trip over:")
        lines.append("")
        lines += [f"- {n}" for n in notes]
    else:
        lines.append("Nothing in the record to flag.")
    lines += [
        "",
        "**Was this review any good?** React here to rate *the reviewer*: "
        ":+1: it got this right, :-1: it got this wrong, :confused: the "
        "note is unclear. Those are counted as real human feedback on the "
        "rubric — if dispute keeps beating agreement, the rubric is wrong "
        "and that is the point of asking. They are never added to the "
        "video's own numbers; rate the **video** on the top post.",
        "",
        f"— *{review.get('by', EDITORIAL_BY)}*. {EDITORIAL_NOTE} It reads "
        "the channel record only; it has not watched the video.",
    ]
    return "\n".join(lines)


# ── persistence ─────────────────────────────────────────────────────────


def _prior_has_counts() -> bool:
    """Does the snapshot on disk hold counts worth protecting?

    A snapshot we cannot parse counts as YES (fail closed): the read may be
    transient, and the cost of guessing wrong is erasing numbers that exist
    only on a remote server we may not be able to re-read.
    """
    if not SNAPSHOT_FILE.exists():
        return False
    try:
        prior = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return True
    if not isinstance(prior, dict):
        return True
    return bool(prior.get("videos"))


def snapshot_body(
    videos: dict[str, dict], editorial: dict[str, dict] | None = None
) -> dict:
    """The exact object written to disk. No timestamps: the file changes
    only when a number changes, so `git status --porcelain` finds nothing
    on a no-op day and git history becomes the time series."""
    editorial = editorial or {}
    return {
        "schema": SNAPSHOT_SCHEMA,
        "repo": REPO,
        "category": CATEGORY,
        "counting": {
            "subject_id": (
                "<channel id>/<video id>. A video id is unique only inside "
                "its own channel.json, so every counter is keyed on the "
                "channel-qualified id."
            ),
            "upvotes": (
                "Positive reactions on the thread's top post "
                f"({', '.join(sorted(POSITIVE_REACTIONS))}). One reaction "
                "per GitHub account, so this is a count of people."
            ),
            "watched": (
                "Distinct accounts that reacted 👍 on the watch-tally "
                "comment. A deliberate click by a signed-in viewer — not a "
                "play count, not telemetry. Report it as 'viewers who said "
                "they watched', never as 'views'."
            ),
            "comments": (
                "Replies on the thread, minus the bot-written machinery "
                "comments actually present on it. null with "
                "'comments_truncated': true means the thread is longer than "
                "the one page of comments the collector reads, so the "
                "subtraction could leave a machine's own comment inside a "
                "human count — unknown is published as null, never as a "
                "number that might be wrong."
            ),
            "signals": (
                "Independent per-user reaction counters on the signal "
                "comment. Never summed with each other."
            ),
            "negative_signals": sorted(NEGATIVE_SIGNALS),
            "negative_signals_note": (
                "Collected, named and published. They subtract from nothing "
                "and appear in no score."
            ),
            "score": (
                f"{RANK_UPVOTE_WEIGHT} * upvotes + watched. A ranking "
                "convention, not a measurement; both components are "
                "published so it can be recomputed with other weights."
            ),
            "editorial": EDITORIAL_NOTE,
            "reviewer_feedback": (
                "Human reactions on the machine review. The ACTOR decides "
                "the lane, never the subject: a person reacting at the bot "
                "layer is real human engagement and is counted as such. It "
                "rates the REVIEWER, not the video, so it is summed into no "
                "video counter, no score and no ranking."
            ),
            "unwired": (
                "Nothing in the player writes to these surfaces yet. A "
                "subject with no thread has no entry here at all — absent "
                "is not zero."
            ),
        },
        "signal_channels": dict(SIGNAL_MAP),
        "reviewer_feedback_channels": dict(REVIEWER_FEEDBACK_MAP),
        "videos": {sid: videos[sid] for sid in sorted(videos)},
        "editorial": {sid: editorial[sid] for sid in sorted(editorial)},
        "rubric_health": rubric_health(editorial),
    }


def persist(
    videos: dict[str, dict],
    editorial: dict[str, dict] | None = None,
    *,
    allow_empty: bool = False,
) -> bool:
    """Write the snapshot. Never clobber real counts with an empty result.

    A failed fetch and a network with no signal are indistinguishable in
    the result, so the guard keys on what is already on disk: if the
    existing snapshot holds counts and this run produced none, keep the
    old one. The counts live on GitHub and are not recomputable from here.

    The guard deliberately keys on the HUMAN counts alone. A run that
    collected none keeps the whole previous file, editorial block included:
    the editorial lane is recomputable from the channel records on any
    later run, and a fresh machine note is never worth erasing a count for.
    """
    if not videos and not allow_empty and _prior_has_counts():
        warn("no counts found; keeping the existing snapshot.")
        return False
    snapshot = snapshot_body(videos, editorial)
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_FILE.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"[rapp-metrics] wrote {len(videos)} counted subject(s) and "
        f"{len(snapshot['editorial'])} editorial note(s) to {SNAPSHOT_FILE}"
    )
    return True


# ── commands ────────────────────────────────────────────────────────────


def fetch_all_discussions(owner: str, name: str) -> list[dict]:
    nodes: list[dict] = []
    after = None
    while True:
        data = graphql(
            DISCUSSIONS_QUERY, {"owner": owner, "name": name, "after": after}
        )
        conn = (data.get("repository") or {}).get("discussions") or {}
        nodes.extend(conn.get("nodes") or [])
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return nodes
        after = page.get("endCursor")


def split_repo() -> tuple[str, str]:
    owner, _, name = REPO.partition("/")
    return owner, name


def cmd_fetch() -> int:
    if not TOKEN:
        warn("no GITHUB_TOKEN set; leaving the snapshot unchanged.")
        return 0
    owner, name = split_repo()
    if not owner or not name:
        warn(f"invalid RAPP_VISION_METRICS_REPO '{REPO}'; expected owner/repo.")
        return 0
    subjects = enumerate_subjects()
    if not subjects:
        warn("no subjects enumerated; leaving the snapshot unchanged.")
        return 0
    try:
        discussions = fetch_all_discussions(owner, name)
    except (OSError, RuntimeError, urllib.error.URLError) as exc:
        warn(f"fetch failed ({exc}); leaving the snapshot unchanged.")
        return 0
    videos = build_snapshot(discussions, set(subjects))
    # The editorial lane is derived locally and deterministically, so it
    # covers every enumerated subject — including ones with no thread yet.
    # It carries the machine verdict AND the humans' verdict on that
    # verdict, and is summed into no video counter.
    editorial = build_editorial(subjects, discussions)
    persist(videos, editorial)
    return 0


def seed_body(sid: str, meta: dict) -> str:
    """Discussion body for a seeded subject thread."""
    title = meta.get("title") or sid
    channel_name = meta.get("channel_name") or meta.get("channel", "")
    lines = [
        f"**{title}**",
        "",
        f"Rating thread for `{sid}` — *{channel_name}* on the "
        f"[RAPP Vision network]({PLAYER_URL}).",
        "",
        "- **Rate it**: react :+1: on this post "
        "(:heart: :tada: :rocket: :smile: count too). Negative reactions "
        "here do nothing — say what went wrong on the signal comment "
        "below, where it is counted under its own name.",
        "- **Say more**: reply in the thread. A sentence beats any reaction.",
    ]
    description = str((meta.get("record") or {}).get("description") or "").strip()
    if description:
        first = description.split("\n", 1)[0].strip()
        if first:
            lines += ["", f"> {first}"]
    # The player's route takes the BARE video id (index.html:273). It is
    # the real route, and it is the reason subject ids are qualified here:
    # if two channels ship the same video id, this link is ambiguous in a
    # way the counter above it is not.
    lines += [
        "",
        f"Watch: {PLAYER_URL}#/watch/{meta.get('video', '')}",
        f"Channel: {PLAYER_URL}#/channel/{meta.get('channel', '')}",
    ]
    return "\n".join(lines)


def cmd_seed(limit: int, delay: float) -> int:
    if not TOKEN:
        warn("no GITHUB_TOKEN set; cannot seed discussions.")
        return 0
    owner, name = split_repo()
    subjects = enumerate_subjects()
    if not subjects:
        warn("no subjects enumerated; nothing to seed.")
        return 0
    try:
        info = graphql(SEED_INFO_QUERY, {"owner": owner, "name": name})
        repository = info.get("repository") or {}
        repo_id = repository.get("id")
        category_id = next(
            (
                c["id"]
                for c in (repository.get("discussionCategories") or {}).get(
                    "nodes", []
                )
                if c.get("name") == CATEGORY
            ),
            None,
        )
        if not repo_id or not category_id:
            warn(f"category '{CATEGORY}' not found in {REPO}; cannot seed.")
            return 0
        # ONLY THE COUNTED CATEGORY COUNTS AS "already has a thread".
        #
        # build_snapshot, cmd_surfaces and editorial_targets all filter to
        # CATEGORY. An unfiltered preflight here disagreed with every one
        # of them: a discussion titled with a subject id in ANY category
        # made the seeder skip that subject, while the counter kept reading
        # only "Announcements". Since an open category (General) is
        # writable by any user on a public repo, that turned "nobody can
        # mint counters for somebody else's video" into "anybody can stop
        # them existing" — the cheaper attack, and a silent one: every
        # later run repeats the same conclusion.
        #
        # Discussion titles are not unique on GitHub, so seeding the real
        # thread alongside a same-titled one elsewhere is safe.
        existing = {
            str(node.get("title", "")).strip()
            for node in fetch_all_discussions(owner, name)
            if ((node.get("category") or {}).get("name")) == CATEGORY
        }
    except (OSError, RuntimeError, urllib.error.URLError) as exc:
        warn(f"seed preflight failed ({exc}); nothing created.")
        return 0

    missing = [sid for sid in sorted(subjects) if sid not in existing]
    if not missing:
        print("[rapp-metrics] every subject already has a thread.")
        return 0
    batch = missing[:limit]
    print(f"[rapp-metrics] seeding {len(batch)} of {len(missing)} missing "
          f"thread(s) (limit {limit})...")
    created = 0
    for sid in batch:
        try:
            made = graphql(
                CREATE_DISCUSSION_MUTATION,
                {
                    "repoId": repo_id,
                    "catId": category_id,
                    "title": sid,
                    "body": seed_body(sid, subjects[sid]),
                },
            )
            disc_id = (((made.get("createDiscussion") or {}).get("discussion"))
                       or {}).get("id")
            # A new subject gets its FULL signal surface at creation, not
            # eventually — so the day a video lands it can already record a
            # watch and a signal, and no later back-fill is needed for it.
            if disc_id:
                for _marker, body in MARKERS.values():
                    graphql(ADD_COMMENT_MUTATION,
                            {"discussionId": disc_id, "body": body})
            created += 1
        except (OSError, RuntimeError, urllib.error.URLError) as exc:
            # Likely a secondary rate limit. Stop, do not fail: the next
            # run picks up exactly where this one left off.
            warn(f"stopping after {created} create(s): {exc}")
            break
        time.sleep(delay)
    print(f"[rapp-metrics] created {created} thread(s); "
          f"{len(missing) - created} still missing.")
    return 0


def cmd_surfaces(limit: int, delay: float, only: str | None = None) -> int:
    """Provision every marker comment in MARKERS on every subject thread.

    Idempotent and per-marker: a thread missing only the newer marker gets
    only that one. This is what makes a new signal surface a one-entry
    change in MARKERS rather than a migration — add the entry, and
    successive capped runs back-fill the whole network on their own.
    """
    if not TOKEN:
        warn("no GITHUB_TOKEN set; cannot add marker comments.")
        return 0
    owner, name = split_repo()
    subjects = set(enumerate_subjects())
    try:
        discussions = fetch_all_discussions(owner, name)
    except (OSError, RuntimeError, urllib.error.URLError) as exc:
        warn(f"surfaces preflight failed ({exc}); nothing added.")
        return 0
    targets: list[tuple[str, str, str, str]] = []  # (title, id, kind, body)
    for node in discussions:
        title = str(node.get("title", "")).strip()
        if ((node.get("category") or {}).get("name")) != CATEGORY:
            continue
        if not is_subject_title(title) or title not in subjects:
            continue
        if only and title != only:
            continue
        for kind, (marker, body) in MARKERS.items():
            if marker_comment_of(node, marker) is None:
                targets.append((title, node.get("id"), kind, body))
    if not targets:
        print("[rapp-metrics] every targeted thread has every surface.")
        return 0
    batch = targets[:limit]
    print(f"[rapp-metrics] adding {len(batch)} of {len(targets)} missing "
          f"surface comment(s) (limit {limit})...")
    added = 0
    by_kind: dict[str, int] = {}
    for _title, disc_id, kind, body in batch:
        try:
            graphql(ADD_COMMENT_MUTATION,
                    {"discussionId": disc_id, "body": body})
            added += 1
            by_kind[kind] = by_kind.get(kind, 0) + 1
        except (OSError, RuntimeError, urllib.error.URLError) as exc:
            warn(f"stopping after {added} surface comment(s): {exc}")
            break
        time.sleep(delay)
    detail = ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())) or "none"
    print(f"[rapp-metrics] added {added} surface comment(s) ({detail}); "
          f"{len(targets) - added} still missing.")
    return 0


def editorial_targets(
    discussions: list[dict], subjects: dict[str, dict],
    category: str = CATEGORY, only: str | None = None,
) -> list[dict]:
    """Threads whose editorial comment is missing or out of date.

    Pure, so it is testable without a network. An unchanged review yields
    no target at all: writing a note is the least important thing this
    script does, and a quiet day should cost zero writes.
    """
    targets: list[dict] = []
    seen: set[str] = set()
    for node in sorted(discussions, key=lambda n: n.get("number", 0)):
        title = str(node.get("title", "")).strip()
        if ((node.get("category") or {}).get("name")) != category:
            continue
        if not is_subject_title(title) or title not in subjects:
            continue
        if only and title != only:
            continue
        if title in seen:      # duplicate threads: earliest wins, as in fetch
            continue
        seen.add(title)
        body = render_editorial(
            title, editorial_review(subjects[title].get("record") or {})
        )
        existing = editorial_comment_of(node)
        # Belt and suspenders. `editorial_comment_of` already refuses to
        # return a comment the machinery does not own, so this can only be
        # one of ours — but `comment_id` is fed straight into
        # updateDiscussionComment with a `discussions: write` token, and an
        # update aimed at a stranger's comment OVERWRITES a human's words
        # and leaves the machine review bylined to them. That failure is
        # not recoverable by a later run, so it gets a second gate here
        # rather than trusting one function to stay correct forever. A
        # non-machinery comment leaves comment_id None, which creates a new
        # bot-authored comment instead.
        if existing is not None and not machinery_authored(existing):
            existing = None
        if existing is not None and (existing.get("body") or "") == body:
            continue
        # "I did not find one" is not "there is not one". The editorial
        # comment is created AFTER seeding, so on a busy thread it is the
        # first machinery comment to fall off the single page this query
        # reads — and then this function would ADD a second one every night,
        # each new one landing in `totalCount` where it inflates the human
        # conversation count. Update-only when the thread is truncated: if we
        # already hold the comment id we refresh it, otherwise we skip and say
        # so, because appending is the branch that cannot be undone.
        if existing is None and comments_truncated(node):
            warn(f"{title}: thread is longer than the one page of comments this "
                 "query reads and no editorial note was found on that page; "
                 "refusing to append a second one. Skipped.")
            continue
        targets.append({
            "subject": title,
            "discussion_id": node.get("id"),
            "comment_id": (existing or {}).get("id"),
            "body": body,
        })
    return targets


def cmd_editorial(limit: int, delay: float, only: str | None = None) -> int:
    """Write the machine review into the editorial lane.

    Never touches a human counter by construction: it only ever creates or
    updates ONE comment carrying EDITORIAL_MARKER, that comment is
    subtracted from the human comment count, its reactions are read by
    nothing, and this command adds no reaction anywhere.
    """
    if not TOKEN:
        warn("no GITHUB_TOKEN set; editorial lane unchanged.")
        return 0
    owner, name = split_repo()
    subjects = enumerate_subjects()
    if not subjects:
        warn("no subjects enumerated; editorial lane unchanged.")
        return 0
    try:
        discussions = fetch_all_discussions(owner, name)
    except (OSError, RuntimeError, urllib.error.URLError) as exc:
        warn(f"editorial preflight failed ({exc}); nothing written.")
        return 0
    targets = editorial_targets(discussions, subjects, CATEGORY, only)
    if not targets:
        print("[rapp-metrics] every editorial note is current.")
        return 0
    batch = targets[:limit]
    print(f"[rapp-metrics] writing {len(batch)} of {len(targets)} editorial "
          f"note(s) (limit {limit})...")
    written = 0
    skipped = 0
    consecutive = 0
    for target in batch:
        try:
            if target["comment_id"]:
                graphql(UPDATE_COMMENT_MUTATION, {
                    "commentId": target["comment_id"],
                    "body": target["body"],
                })
            else:
                graphql(ADD_COMMENT_MUTATION, {
                    "discussionId": target["discussion_id"],
                    "body": target["body"],
                })
            written += 1
            consecutive = 0
        except (OSError, RuntimeError, urllib.error.URLError) as exc:
            # ONE BAD THREAD MUST NOT BLOCK THE NETWORK. Targets are
            # ordered by discussion number ascending, so an unconditional
            # break means the lowest-numbered failing thread stalls every
            # thread behind it on this run AND on every future run — a
            # permanent, silent outage of the whole lane caused by one
            # object. So a per-thread failure is skipped and the batch
            # carries on.
            #
            # A rate limit is the opposite case: it applies to everything
            # left, so continuing burns budget for nothing. That still
            # breaks, and the next run resumes where this one stopped.
            skipped += 1
            consecutive += 1
            if looks_rate_limited(exc):
                warn(f"rate limited; stopping after {written} editorial "
                     f"note(s): {exc}")
                break
            warn(f"skipping '{target['subject']}' ({exc}); continuing.")
            # Guard against the other extreme: if everything is failing,
            # this is not one bad thread, it is a bad day. Stop rather
            # than walk the whole batch into the same wall.
            if consecutive >= EDITORIAL_CONSECUTIVE_FAILURES:
                warn(f"{consecutive} consecutive failures; stopping after "
                     f"{written} editorial note(s).")
                break
        time.sleep(delay)
    tail = f"; skipped {skipped}" if skipped else ""
    print(f"[rapp-metrics] wrote {written} editorial note(s); "
          f"{len(targets) - written} still stale{tail}.")
    return 0


def cmd_subjects() -> int:
    """List enumerated subjects. Needs no token and no network — the
    fastest way to see what this script thinks it is counting."""
    subjects = enumerate_subjects()
    for sid in sorted(subjects):
        meta = subjects[sid]
        print(f"{sid}\t{meta.get('title', '')}")
    print(f"[rapp-metrics] {len(subjects)} subject(s).", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="create missing subject Discussions")
    seed.add_argument("--limit", type=int, default=60)
    seed.add_argument("--delay", type=float, default=1.2)

    surfaces = sub.add_parser(
        "surfaces", help="provision watch/signal comments on existing threads"
    )
    surfaces.add_argument("--limit", type=int, default=60)
    surfaces.add_argument("--delay", type=float, default=1.2)
    surfaces.add_argument("--only", help="target a single subject id")

    editorial = sub.add_parser(
        "editorial", help="write the machine review into the editorial lane"
    )
    editorial.add_argument("--limit", type=int, default=40)
    editorial.add_argument("--delay", type=float, default=1.2)
    editorial.add_argument("--only", help="target a single subject id")

    sub.add_parser("fetch", help="snapshot counts to state/metrics.json")
    sub.add_parser("subjects", help="list enumerated subjects (no network)")

    args = parser.parse_args()
    if args.command == "seed":
        return cmd_seed(args.limit, args.delay)
    if args.command == "surfaces":
        return cmd_surfaces(args.limit, args.delay, args.only)
    if args.command == "editorial":
        return cmd_editorial(args.limit, args.delay, args.only)
    if args.command == "subjects":
        return cmd_subjects()
    return cmd_fetch()


if __name__ == "__main__":
    sys.exit(main())
