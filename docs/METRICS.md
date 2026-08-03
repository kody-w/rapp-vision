# Metrics for channel owners

You published a `channel.json`. Nobody approved you and nobody can remove you
([README](../README.md#start-your-own-channel)). This document explains the one
thing the network does on your behalf: it counts how people reacted to your
entries, and writes those counts into a static file the player reads.

There is no server, no account and no analytics. The counting happens on GitHub
Discussions, in public, where you can audit every number by clicking through to
the thread it came from.

> **Status — read before quoting a number.**
> The player half is shipped and readable in `index.html` (`loadMetrics`,
> `indexMetrics`, `parseRecord`, `communityHTML`), and every claim below about
> *rendering* is grounded there. The collector half is not: `scripts/`,
> `tests/` and `state/` are empty directories as of this writing, no workflow
> run has been observed, and no Discussion thread has been seeded. Everything
> about *collection* describes the contract
> [`.github/workflows/metrics.yml`](../.github/workflows/metrics.yml) schedules
> — not measured behaviour.

---

## What gets measured

| Signal | Where the reaction goes | Snapshot field |
|---|---|---|
| **Endorsement** | 👍 on the **top post** of the entry's thread | `upvotes` |
| **Experience** | one of 7 reactions on the **signal comment** | `signals{}` |
| **Conversation** | human replies in the thread | `comments` (`null` when the thread is longer than the one page the collector reads) |

Three distinct GitHub objects, three distinct ids, three distinct fields. They
are never added together. One number that means three things defends none of
them.

A fourth field, `score`, is whatever ranking you choose to publish. When the
snapshot omits it the player falls back to the endorsement count rather than
inventing one, and when the snapshot carries neither, the score pill does not
render at all — because *"never counted"* and *"counted, and it is zero"* are
different claims.

### The experience channels

The signal comment is an eight-option poll wearing a comment's clothes. GitHub
Discussions has a real poll type, but `createDiscussion` accepts only
`repositoryId` / `title` / `body` / `categoryId`, so a poll can only be created
by hand in the web UI — a chore that would not survive the network growing. A
*comment* is API-creatable and carries all eight reaction contents as
independent, per-user-deduped counters. So one comment behaves as an eight-option
poll and gets provisioned automatically for every entry the moment it enters a
registered channel.

| React | Channel key | The player labels it |
|---|---|---|
| 👍 | `worked` | worked for me |
| 👎 | `did_not_work` | didn't work |
| 😕 | `stuck` | got stuck |
| ❤️ | `regular_use` | watch it regularly |
| 🚀 | `shipped` | shipped with it |
| 🎉 | `saved_time` | saved me time |
| 👀 | `want_to_try` | want to try |
| 😄 | *(unmapped)* | — |

😄 is deliberately unmapped. There is no honest question it answers, and an
option that means nothing pollutes every other count.

Every channel must map to a **distinct** reaction. That uniqueness matters more
than it looks: two channels sharing one emoji are permanently indistinguishable,
and no amount of later work can separate the counts retroactively.

The vocabulary is not frozen. `SIGNAL_LABELS` in `index.html` knows one label the
table above does not map — `rewatched` — and anything else a snapshot carries is
labelled from its own key (`want_to_try` → "want to try") rather than dropped. So
a publisher can add a channel without shipping a new player.

> The table is the contract; the `SIGNAL_MAP` in the collector is the authority.
> If they ever disagree, the collector wins and this table is the bug.

---

## Counts are people, not clicks

GitHub enforces one reaction per user, per subject, per emoji. That is not a rule
this repository implements — it is a property of the platform, which means every
count here is a count of *people* by construction and there is nothing in the
client that can inflate it. There is no "+1" primitive to spam: the only way to
withdraw a 👍 is to remove your own.

Four consequences worth carrying with the number:

- **Negative reactions never subtract.** Only positive reactions feed the
  endorsement figure. 👎 and 😕 are not censored — they are *routed*, into
  `did_not_work` and `stuck`, where they are useful instead of destructive. A
  score that can be pushed down is a brigading target and stops being
  publishable.
- **Attribution is public.** Anyone can open a reaction and see who left it.
  This is a review surface, not telemetry. If you would not sign it, don't react.
- **Self-reactions count.** Nothing distinguishes a channel owner reacting to
  their own entry from a stranger doing it. Seeded numbers are real numbers.
- **Machinery is subtracted from the conversation count.** The signal comment is
  a comment. It is counted out of `comments`, computed from the markers actually
  present on the thread rather than from a hard-coded constant — so the count
  stays honest as surfaces are added, and a brand-new entry reads zero instead of
  inventing a conversation.
- **Past 100 comments, `comments` is `null` rather than wrong.** The collector
  reads one page of comments (`comments(first: 100)`) but GitHub's `totalCount`
  covers the whole thread. On a longer thread the subtraction above stops being
  valid — a machinery comment sitting past position 100 is not in the
  subtrahend, so it would be counted as a human reply, which is a machine's
  own output landing in a human counter. Such an entry publishes
  `"comments": null` alongside `"comments_truncated": true`, and the player
  renders nothing for it. Unknown is null; it is never a number that might be
  wrong. (The same condition makes the editorial writer update-only: it will
  refresh a note it can see and refuses to append a second one it cannot.)

### What is *not* measured

**There is no view count, and there cannot be one.** The player is a static HTML
file with no backend; your watch position lives in `localStorage` under
`rapp_vision_v1` and never leaves your device
([README](../README.md#what-the-player-does): *Zero telemetry*). Nothing in the
snapshot is a view, an impression, a watch-time or a completion rate. If a number
here gets reported as "views", the reporting is wrong — not the number.

### Does this break "nothing here phones home"?

No, and the distinction is worth stating precisely, because the player asserts it
in three places (the footer, the watch-page aside, the About page):

- **Reading** metrics is a `GET` of a static JSON file committed to this
  repository — the same class of request the page already makes for
  `channels.json`. It carries no identifier and says nothing about you.
- **Nothing is written back from the player.** Unlike the storefront this pattern
  came from, `index.html` has no write path at all: no token, no GraphQL call, no
  button that posts. Reacting means going to the thread on GitHub and reacting
  there, as yourself. The player renders a `Discuss on GitHub →` link and stops.
- **Watch history, likes and watch-later never move.** They stay in
  `localStorage`, and the only way off your device is the Export button you press
  yourself.

---

## Where the threads live

One Discussion per entry, in this repository, in a category ordinary users
**cannot post in** (Announcements is maintainer-only). That is the whole security
model: if anyone could open a thread, anyone could open one titled with your
entry's id and mint their own counters. A thread outside that category is ignored
by the collector even if the title matches perfectly.

The thread title is the entry's **subject id**:

```
<channel-id>/<video-id>          e.g.  rock-tumbler/rock-tumbler-showcase
```

### Why it is not just the video id

Because a bare video id is **not unique across the network** — by construction,
not by accident. `template/channel.json` ships `"id": "my-first-video"`, and the
README tells every new publisher to copy that template. The player is bare-id
internally (`byId = id => VIDEOS.find(v => v.id === id)`), which is a real latent
collision there — but the metrics key must not inherit it, so `vkey()` scopes it:

```js
const vkey = v => (v && v._ch ? v._ch.id : "") + "/" + (v ? v.id : "");
```

The channel half is the `id` declared **inside your `channel.json`**, not the id
in the network registry — channels added by hand in the UI get a throwaway
registry id (`custom-<timestamp>`), so the file's own `id` is the only stable one.

Three details that follow from how the player looks keys up:

- **Keys are compared normalised.** `normKey()` lowercases and collapses
  `-` and whitespace to `_`, so `Rock-Tumbler/My Video` and
  `rock_tumbler/my_video` are the same key. One normaliser, called by the shipped
  code, never re-derived at a call site.
- **An unscoped id works as an alias — until it doesn't.** A snapshot key with no
  `/` resolves as a bare video id *only while it still matches exactly one
  record*. The moment two channels collide on it, the alias is dropped rather
  than resolving to whichever happened to load first. Convenient, not reliable:
  publish scoped keys.
- **Renaming orphans everything.** Change a channel id or a video id and every
  count that entry ever collected is stranded under the old title, with nobody to
  notify. Pick both once.

---

## How to read the numbers

**In the player.** A `★` score pill sits on the thumbnail, and a **Community**
block sits at the bottom of the watch column. Both are additive: they are the
only two things a late-arriving snapshot touches, so nothing already on screen
moves and a playing `<video>` is never torn down.

What renders is deliberately sparse:

- No thread and no signal → **nothing at all.** Not a heading, not a row of
  zeros.
- A thread that exists but has not been used yet → **the link alone**, which is
  the one thing about it that is true.
- Only channels that actually registered are listed. A zero is filtered out,
  because a row of zeros is noise and is indistinguishable from a channel nobody
  has wired up.
- Score `null` or `0` → no pill. `0` is never printed as if it were a measurement.

If the snapshot is missing entirely — not published yet, 404, offline, malformed
JSON, or a shape nobody recognises — all of it lands in the same place: `METRICS`
stays `null`, every render site returns the empty string, and the player is
byte-for-byte the player it was before the file existed. One bad *record* drops
that record, not the file.

**In git.** `state/metrics.json` carries **no timestamp**. Keys are sorted and
serialisation is stable, so identical counts produce identical bytes, so a day
where nothing moved produces no commit at all. That makes the file's git history
a readable record of exactly when each number changed — the snapshot has no
history field because the repository *is* the history:

```bash
git log -p --follow state/metrics.json
```

This is load-bearing, not stylistic. The pattern this workflow is modelled on has
a counter-example in the same codebase: a sibling snapshot that stamps
`generated_at` on every build, whose "commit only if changed" guard therefore can
never fire, and which commits daily whether or not anything moved. Its history
tells you nothing.

**Caveats to carry with the number.** Reactions are people, so they are small: an
entry with six 👍 has six humans behind it, which is a different and better fact
than six hundred pageviews. And the surface only ever sees people signed in to
GitHub — a minority of any audience, and a biased one.

---

## Agent reviews are a separate lane

A live entry is a running application, not pixels someone recorded
([README](../README.md#what-makes-it-different)) — which means a model can
genuinely *watch* one: drive the app, sample the DOM, and write up what happened.

Those reviews are editorial, and they are quarantined:

- They live in their own field (`review`, or a top-level `reviews` map), never in
  `upvotes`, `comments`, `signals` or `score`.
- They render in their own block, tagged **MACHINE REVIEW**, carrying the
  reviewer's id and the disclaimer the player prints verbatim: *"Written by a
  model, not by a person. It is not counted in any number above."*
- Their `score` is displayed beside the reviewer, never merged into the community
  score.

Your robots must never become your engagement numbers. A machine review is a
second opinion printed next to the human one, the way a critic score sits beside
an audience score. If the two disagree, that gap is information. Summed, it is
noise you could never separate again.

**Two counts of different populations, measured by different methods, are never
added.** That rule has no exceptions here.

---

## Adopting `rapp-metrics/1.0`

**If you publish a channel on this network, you do not have to do anything.**
Your entries are counted by this repository's daily run, in this repository's
Discussions, and the numbers appear in the player automatically. There is nothing
to add to your `channel.json` — the snapshot belongs to the **player**, not to a
channel. `loadMetrics()` resolves `state/metrics.json` against the page the same
way `channels.json` is resolved, and never against a channel file's own URL. (A
channel's *media* paths resolve against its own file — that rule is unchanged and
unrelated.)

**If you run your own player instance** — your own fork, your own
`channels.json`, your own audience — then you publish your own snapshot next to
your own `index.html`, and `rapp-metrics/1.0` is the shape it has to be.

### The snapshot shape

```jsonc
{
  "schema": "rapp-metrics/1.0",

  "videos": {
    "your-channel/your-video": {
      "url": "https://github.com/you/your-repo/discussions/12",
      "upvotes": 6,
      "comments": 2,
      "score": 6,
      "signals": {
        "worked": 5, "stuck": 1, "regular_use": 2,
        "shipped": 1, "saved_time": 2, "want_to_try": 4
      },
      "review": {
        "reviewer_id": "some-model-id",
        "score": 72,
        "headline": "Drives the app cleanly; the third scene never gets past the gate.",
        "review": "..."
      }
    }
  },

  "reviews": {
    "your-channel/your-video": { "reviewer_id": "...", "headline": "...", "review": "..." }
  }
}
```

The parser is deliberately forgiving, because one typo in somebody else's JSON
must not blank the page:

| Slot | Accepted spellings |
|---|---|
| the map | `videos` · `agents` · `entries` · `items` · a bare map with no `schema` |
| endorsements | `upvotes` · `endorsements` · `up` |
| conversation | `comments` · `conversation` |
| thread link | `url` · `thread` · `discussion` |
| machine review | `review` · `editorial` · `machine_review` (or the top-level `reviews` map) |
| review body | `review` · `body` · `text`; headline as `headline` · `title` |
| reviewer | `reviewer_id` · `reviewer` · `critic_id` · `critic` · `model` · `by` |

Three rules the writer must follow, and why:

1. **No timestamp anywhere.** Not `generated_at`, not `as_of`, not a `history`
   array. A timestamp makes every rebuild a diff, every day a commit, and
   destroys the only time series you have.
2. **Sorted keys, stable serialisation** — `json.dumps(..., sort_keys=True,
   indent=2)` plus a trailing newline. Same reason.
3. **Omit what you did not measure.** Leave the field out rather than writing
   `0`. The player already filters zeroed signals, but an omitted field is the
   honest encoding of "not counted", and it keeps the file from churning.

**The snapshot is untrusted input** — anyone can open a PR against it. The player
treats it that way: every value goes through `esc()`, and `httpUrl()` refuses any
thread link that is not `http:` or `https:`, which is what keeps a `javascript:`
URL out of the `Discuss on GitHub` href. If you write your own renderer, keep
both.

### Running the collection

Copy [`.github/workflows/metrics.yml`](../.github/workflows/metrics.yml). One
line needs your attention — `METRICS_CLI` under `env:`, the path to the
collector. The workflow needs `contents: write` (to commit the snapshot) and
`discussions: write` (to seed threads), both satisfied by the default
`GITHUB_TOKEN`. No PAT, no secret to manage.

**Neither permission does anything until Discussions is switched on for the
repository.** `discussions: write` grants a capability; it does not enable the
feature. Turn it on first — **Settings → Features → Discussions** — and confirm
the category the collector writes to exists (`Announcements` by default,
`RAPP_VISION_METRICS_CATEGORY` to override). With the feature off, every step
below fails *silently and greenly*: `seed` gets an empty category list and
returns 0 (`scripts/rapp_metrics.py:1193-1194`), `surfaces` and `editorial` find
no threads and return 0, `fetch` counts nothing — and because every collection
step is `continue-on-error`, the run still passes. You get a green badge every
morning and zero human metrics, forever, with nothing anywhere reporting a
problem. The workflow's first step, `Discussions preflight`, exists to make that
loud: it is the only step in the daily job allowed to fail the run, and it fails
it when the feature is off or the category is missing. (A transport error is
treated as a bad API day, not a misconfigured repo, and only warns.)

It runs the Discussions preflight → `seed` → `surfaces` → `fetch` → `editorial`
→ two publication gates (nothing dropped, nothing deleted) → commit-if-changed,
once a day at 08:10 UTC. Four properties are worth preserving verbatim if you
adapt it:

- **Collection steps are non-fatal.** A bad API day leaves the previous snapshot
  byte-for-byte intact instead of erasing counts you cannot recompute. The
  collector must exit 0 on a missing token or a network error, and its `persist()`
  must refuse to write an empty result over a non-empty snapshot. One 404 must
  not cost you the other steps' signal.
- **The commit stages only files that exist**, so a snapshot that hasn't been
  produced yet doesn't fail `git add` for the ones that have.
- **It no-ops cleanly** — no change, no commit, no push, exit 0 — and rebases
  before pushing, because more than one process writes to this repository.
- **`[skip ci]`** in the commit message, so the snapshot commit does not retrigger
  CI on a quiet day.

Seeding is capped per run (`--limit 60`) to stay under GitHub's content-creation
rate limits; the daily cron drains any backlog. A brand-new entry therefore waits
up to 24 hours for its thread. If that matters for a launch, run the workflow by
hand: **Actions → Channel Metrics → Run workflow**.

### Verifying it before you trust it

Nothing in this document has been proven by a live run. When you first wire it up,
prove it by hand rather than by a green checkmark:

0. **Enable Discussions on the repo** (Settings → Features → Discussions) and
   confirm an `Announcements` category exists. Nothing below can work until this
   is true, and with it false everything below *looks* like it worked. Check it
   from the outside rather than from the run's colour:
   `gh api repos/<owner>/<repo> --jq .has_discussions` must print `true`.
1. Run the workflow manually and confirm a thread appears for each entry — in the
   maintainer-only category, titled `<channel-id>/<video-id>`.
2. React 👍 on one top post. Re-run. Confirm the count moved and a commit landed.
3. Re-run with nothing changed. Confirm **no commit** was produced. This is the
   check that proves the snapshot is timestamp-free and that its git history means
   what this document says it means.
4. Delete the token from the workflow and run once more. Confirm the run is green
   and the snapshot is **unchanged — not zeroed**.
5. Rename `state/metrics.json` to something else and load the player. Confirm no
   pills, no Community block, no error, no console noise.

Steps 4 and 5 are the ones people skip, and they are the ones that catch the
failures that actually cost you data.

---

## The offline test suite

`.github/workflows/metrics.yml` runs `pytest tests` on every push and pull
request, in a job with `contents: read` and **no `GITHUB_TOKEN` in its
environment** — so nothing in the suite can reach the GitHub API even by
accident. That is the point. Faking an API mostly tests the fake: it passes while
the real call 404s, and the first you hear of it is a snapshot full of zeroes.

So the suite covers the pure transforms — subject-id construction, the
reaction→channel map and its distinctness, the refuse-to-clobber guards,
byte-stable serialisation, one-bad-record-not-one-bad-file — and the live half is
driven by hand, by the five steps above. A red run there always means the code
broke, never that GitHub was having a bad day, which is exactly why it is allowed
to gate a merge.

One rule about adding to it: **a test that re-implements the logic it checks
cannot fail**, and is worse than no test, because the documentation citing it
becomes false assurance. Verify each new test by reintroducing the bug and
confirming it goes red.
