"""Offline tests for scripts/rapp_metrics.py.

Run with:
    python3 -m unittest discover -s tests -v

NOTHING HERE TOUCHES THE NETWORK AND NOTHING NEEDS A TOKEN. Every test
drives the pure transforms with hand-built GraphQL payloads, exactly the
shape GitHub returns. urllib.request.urlopen is replaced for the whole
module with a function that fails the test if anything calls it, so an
accidental live call is a red test rather than a slow one.

Nothing mocks the GitHub API itself: faking an API mostly tests the fake —
it passes while the real call 404s, and the first you hear about it is a
snapshot full of zeroes. What is tested here is the half that is ours: the
subject enumerator, the counting rules, the non-clobber guard, and the
isolation of the editorial lane from every human counter.
"""

import contextlib
import http.client
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "rapp_metrics.py"

_URLOPEN_PATCH = None


def _no_network(*args, **kwargs):
    raise AssertionError(
        "a test tried to open a network connection; these tests must run "
        "offline with no token"
    )


def setUpModule():
    global _URLOPEN_PATCH
    _URLOPEN_PATCH = mock.patch.object(
        urllib.request, "urlopen", side_effect=_no_network
    )
    _URLOPEN_PATCH.start()


def tearDownModule():
    if _URLOPEN_PATCH is not None:
        _URLOPEN_PATCH.stop()


def _load_module():
    spec = importlib.util.spec_from_file_location("rapp_metrics", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rapp_metrics"] = module
    spec.loader.exec_module(module)
    return module


rm = _load_module()


# ── fixture builders: the exact shapes GitHub's GraphQL returns ─────────


def reactions(**counts) -> list[dict]:
    """[{content, reactors:{totalCount}}] — GitHub's reactionGroups shape."""
    return [
        {"content": content, "reactors": {"totalCount": n}}
        for content, n in counts.items()
    ]


# The login the workflow's GITHUB_TOKEN acts as, and the default member of
# rm.MACHINERY_AUTHORS. Fixtures name it so that "who wrote this" is
# visible in the test rather than implied.
BOT_LOGIN = "github-actions[bot]"
HUMAN_LOGIN = "a-real-person"


def comment(
    body: str,
    cid: str = "C_1",
    *,
    author: str | None = HUMAN_LOGIN,
    viewer_did_author: bool = False,
    **counts,
) -> dict:
    """A discussion comment in GitHub's shape, INCLUDING its authorship.

    `author` defaults to a human because that is the safe default for a
    fixture: a test that forgets to say who wrote something gets a
    stranger, not the machinery. `author=None` models a deleted account
    (GitHub returns `author: null`).
    """
    return {
        "id": cid,
        "body": body,
        "viewerDidAuthor": viewer_did_author,
        "author": {"login": author} if author else None,
        "reactionGroups": reactions(**counts),
    }


def bot_comment(body: str, cid: str = "C_1", **counts) -> dict:
    """A comment the machinery actually wrote — marker AND authorship.

    Every machinery fixture goes through here, so a test that squats a
    marker on a human comment has to say so explicitly by calling
    `comment()` instead.
    """
    return comment(body, cid, author=BOT_LOGIN, viewer_did_author=True,
                   **counts)


def node(
    title: str,
    *,
    category: str = "Announcements",
    number: int = 1,
    top: dict | None = None,
    comments: list[dict] | None = None,
    total_comments: int | None = None,
    url: str = "https://example.test/d/1",
    node_id: str = "D_1",
) -> dict:
    comments = comments or []
    return {
        "id": node_id,
        "number": number,
        "title": title,
        "url": url,
        "category": {"name": category},
        "comments": {
            "totalCount": (
                len(comments) if total_comments is None else total_comments
            ),
            "nodes": comments,
        },
        "reactionGroups": reactions(**(top or {})),
    }


def watch_comment(n: int = 0, cid: str = "C_watch") -> dict:
    return bot_comment(rm.WATCH_BODY, cid, THUMBS_UP=n)


def signal_comment(cid: str = "C_signal", **counts) -> dict:
    return bot_comment(rm.SIGNAL_BODY, cid, **counts)


def editorial_comment(body: str, cid: str = "C_ed", **counts) -> dict:
    return bot_comment(body, cid, **counts)


class SilentWarnings(unittest.TestCase):
    """Base: capture warn() instead of spraying stderr through the run."""

    def setUp(self):
        self.warnings: list[str] = []
        patcher = mock.patch.object(rm, "warn", self.warnings.append)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assertWarned(self, needle: str):
        self.assertTrue(
            any(needle in w for w in self.warnings),
            f"expected a warning containing {needle!r}; got {self.warnings}",
        )


# ── the network is really off ───────────────────────────────────────────


class OfflineGuardTests(unittest.TestCase):
    def test_graphql_cannot_reach_the_network_in_tests(self):
        with self.assertRaises(AssertionError):
            rm.graphql("query { viewer { login } }", {})

    def test_no_token_is_needed_to_import_or_enumerate(self):
        self.assertEqual(
            rm.TOKEN,
            os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "",
        )


# ── subject enumeration ─────────────────────────────────────────────────


class SubjectEnumerationTests(SilentWarnings):
    """channels.json -> channel.json -> videos[], channel-qualified."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)

        self.site = root / "site"
        self.sibling = root / "sibling" / "rappvision"
        self.elsewhere = root / "elsewhere"
        for d in (self.site, self.sibling, self.elsewhere):
            d.mkdir(parents=True)

        # Two channels that BOTH ship a video called "intro" — the case
        # template/channel.json produces by construction, since every new
        # publisher copies the same file.
        (self.site / "channel.json").write_text(json.dumps({
            "id": "alpha",
            "name": "Alpha Channel",
            "videos": [
                {"id": "intro", "title": "Alpha intro"},
                {"id": "deep-dive", "title": "Alpha deep dive"},
                {"title": "no id at all"},
                {"id": "intro", "title": "Alpha intro, again"},
            ],
        }))
        (self.sibling / "channel.json").write_text(json.dumps({
            "id": "beta",
            "name": "Beta Channel",
            "videos": [{"id": "intro", "title": "Beta intro"}],
        }))
        self.network = self.site / "channels.json"
        self.network.write_text(json.dumps({
            "schema": "rapp-vision-network/1.0",
            "channels": [
                # entry id deliberately DISAGREES with the file's id
                {"id": "entry-alias", "url": "channel.json"},
                {"id": "beta", "url": "../sibling/rappvision/channel.json"},
                {"id": "remote", "url": "https://example.test/channel.json"},
                {"id": "gone", "url": "nope/channel.json"},
                {"id": "rooted", "url": "/absolute/channel.json"},
                {"id": "beta", "url": "duplicate-entry-id.json"},
            ],
        }))

    def enumerate_from_elsewhere(self) -> dict:
        """Enumerate with the process CWD somewhere unrelated, so a
        resolution anchored to the CWD instead of the network file would
        fail rather than accidentally pass."""
        cwd = os.getcwd()
        os.chdir(self.elsewhere)
        try:
            return rm.enumerate_subjects(self.network)
        finally:
            os.chdir(cwd)

    def test_subjects_are_channel_qualified_across_channels(self):
        subjects = self.enumerate_from_elsewhere()
        self.assertEqual(
            set(subjects),
            {"alpha/intro", "alpha/deep-dive", "beta/intro"},
        )

    def test_same_video_id_in_two_channels_stays_two_subjects(self):
        subjects = self.enumerate_from_elsewhere()
        self.assertIn("alpha/intro", subjects)
        self.assertIn("beta/intro", subjects)
        self.assertEqual(subjects["alpha/intro"]["title"], "Alpha intro")
        self.assertEqual(subjects["beta/intro"]["title"], "Beta intro")
        self.assertNotEqual(
            subjects["alpha/intro"]["channel"],
            subjects["beta/intro"]["channel"],
        )

    def test_channel_file_id_wins_over_registry_entry_id(self):
        subjects = self.enumerate_from_elsewhere()
        self.assertEqual(subjects["alpha/intro"]["channel"], "alpha")
        self.assertNotIn("entry-alias/intro", subjects)

    def test_relative_url_resolves_against_the_network_file_not_the_cwd(self):
        subjects = self.enumerate_from_elsewhere()
        self.assertEqual(
            Path(subjects["beta/intro"]["channel_file"]).resolve(),
            (self.sibling / "channel.json").resolve(),
        )

    def test_one_unreadable_channel_does_not_blank_the_network(self):
        subjects = self.enumerate_from_elsewhere()
        self.assertTrue(subjects)
        self.assertWarned("nope/channel.json")

    def test_remote_and_root_relative_urls_are_skipped_with_a_reason(self):
        self.enumerate_from_elsewhere()
        self.assertWarned("https://example.test/channel.json")
        self.assertWarned("/absolute/channel.json")

    def test_duplicate_entry_id_and_duplicate_video_id_keep_the_first(self):
        subjects = self.enumerate_from_elsewhere()
        self.assertEqual(subjects["alpha/intro"]["title"], "Alpha intro")
        self.assertWarned("duplicate channel entry id 'beta'")
        self.assertWarned("alpha/intro: duplicate subject id")

    def test_video_without_an_id_is_skipped(self):
        subjects = self.enumerate_from_elsewhere()
        self.assertEqual(len(subjects), 3)
        self.assertWarned("a video has no id")

    def test_missing_network_file_enumerates_nothing_and_does_not_raise(self):
        self.assertEqual(rm.enumerate_subjects(self.site / "absent.json"), {})

    def test_broken_network_json_enumerates_nothing_and_does_not_raise(self):
        broken = self.site / "broken.json"
        broken.write_text("{not json")
        self.assertEqual(rm.enumerate_subjects(broken), {})

    def test_subject_id_is_the_one_place_the_key_is_built(self):
        self.assertEqual(rm.subject_id("alpha", "intro"), "alpha/intro")
        self.assertEqual(rm.subject_id(" alpha ", " intro "), "alpha/intro")

    def test_the_repos_own_channels_json_enumerates(self):
        """Grounded on the real files in this repo, not a fixture."""
        subjects = rm.enumerate_subjects(REPO_ROOT / "channels.json")
        self.assertIn("rock-tumbler/rock-tumbler-showcase", subjects)
        self.assertIn("rock-tumbler/rock-tumbler-short", subjects)
        for sid in subjects:
            self.assertTrue(rm.is_subject_title(sid), sid)


class TitleShapeTests(unittest.TestCase):
    def test_subject_shaped_titles_accepted(self):
        self.assertTrue(rm.is_subject_title("rock-tumbler/rock-tumbler-short"))
        self.assertTrue(rm.is_subject_title("  alpha/intro  "))
        self.assertTrue(rm.is_subject_title("field-notes/note.01"))

    def test_non_subject_titles_rejected(self):
        for bad in [
            "",
            "Welcome to the network",
            "intro",                    # bare video id: the whole point
            "/intro",
            "alpha/",
            "alpha/beta/intro",         # more than one segment
            "alpha intro",
        ]:
            self.assertFalse(rm.is_subject_title(bad), bad)


# ── counting: positive only, negatives never subtract ───────────────────


class PositiveScoringTests(unittest.TestCase):
    def test_positive_reactions_counted(self):
        self.assertEqual(
            rm.positive_score(reactions(THUMBS_UP=3, HEART=2, ROCKET=1)), 6
        )

    def test_negative_and_neutral_ignored(self):
        self.assertEqual(
            rm.positive_score(
                reactions(THUMBS_UP=2, THUMBS_DOWN=50, CONFUSED=7, EYES=9)
            ),
            2,
        )

    def test_negatives_alone_can_never_go_below_zero(self):
        self.assertEqual(
            rm.positive_score(reactions(THUMBS_DOWN=99, CONFUSED=99)), 0
        )

    def test_missing_and_malformed_groups(self):
        self.assertEqual(rm.positive_score(None), 0)
        self.assertEqual(rm.positive_score([]), 0)
        self.assertEqual(rm.positive_score([{"content": "THUMBS_UP"}]), 0)

    def test_sentiment_buckets_do_not_overlap(self):
        self.assertFalse(rm.POSITIVE_REACTIONS & rm.NEGATIVE_REACTIONS)
        self.assertFalse(rm.POSITIVE_REACTIONS & rm.NEUTRAL_REACTIONS)
        self.assertFalse(rm.NEGATIVE_REACTIONS & rm.NEUTRAL_REACTIONS)


class SignalChannelTests(unittest.TestCase):
    def test_every_channel_maps_to_a_distinct_reaction(self):
        keys = list(rm.SIGNAL_MAP.values())
        self.assertEqual(len(keys), len(set(keys)))

    def test_laugh_is_deliberately_unmapped(self):
        self.assertNotIn("LAUGH", rm.SIGNAL_MAP)

    def test_named_negative_channels_exist_and_are_mapped(self):
        self.assertEqual(rm.SIGNAL_MAP["THUMBS_DOWN"], "too_long")
        self.assertEqual(rm.SIGNAL_MAP["CONFUSED"], "confusing")
        self.assertEqual(
            rm.NEGATIVE_SIGNALS, frozenset({"too_long", "confusing"})
        )
        for name in rm.NEGATIVE_SIGNALS:
            self.assertIn(name, rm.SIGNAL_MAP.values())

    def test_absent_signal_surface_reads_as_all_zeros(self):
        counts = rm.signal_counts(node("alpha/intro"))
        self.assertEqual(set(counts), set(rm.SIGNAL_MAP.values()))
        self.assertEqual(sum(counts.values()), 0)

    def test_signal_counts_read_per_reaction(self):
        n = node("alpha/intro", comments=[
            signal_comment(THUMBS_UP=5, HOORAY=3, THUMBS_DOWN=4, CONFUSED=2),
        ])
        counts = rm.signal_counts(n)
        self.assertEqual(counts["watched_it_all"], 5)
        self.assertEqual(counts["learned_something"], 3)
        self.assertEqual(counts["too_long"], 4)
        self.assertEqual(counts["confusing"], 2)
        self.assertEqual(counts["want_more_like_this"], 0)

    def test_negatives_are_published_and_subtract_from_nothing(self):
        loud = node("alpha/intro", number=1, top={"THUMBS_UP": 3},
                    comments=[
                        watch_comment(4),
                        signal_comment(THUMBS_UP=1, THUMBS_DOWN=99, CONFUSED=50),
                    ])
        quiet = node("alpha/intro", number=1, top={"THUMBS_UP": 3},
                     comments=[watch_comment(4), signal_comment(THUMBS_UP=1)])
        a = rm.build_snapshot([loud], {"alpha/intro"})["alpha/intro"]
        b = rm.build_snapshot([quiet], {"alpha/intro"})["alpha/intro"]
        self.assertEqual(a["upvotes"], b["upvotes"])
        self.assertEqual(a["watched"], b["watched"])
        self.assertEqual(a["score"], b["score"])
        self.assertEqual(a["signals"]["too_long"], 99)
        self.assertEqual(a["signals"]["confusing"], 50)
        self.assertEqual(b["signals"]["too_long"], 0)

    def test_thumbs_down_on_the_top_post_does_not_move_the_score(self):
        with_down = node("alpha/intro", top={"THUMBS_UP": 2, "THUMBS_DOWN": 40})
        without = node("alpha/intro", top={"THUMBS_UP": 2})
        self.assertEqual(
            rm.build_snapshot([with_down], {"alpha/intro"})["alpha/intro"]["score"],
            rm.build_snapshot([without], {"alpha/intro"})["alpha/intro"]["score"],
        )


class WatchTallyTests(unittest.TestCase):
    def test_watch_count_reads_thumbs_up_on_the_tally_comment(self):
        n = node("alpha/intro", comments=[watch_comment(7)])
        self.assertEqual(rm.watch_count(n), 7)

    def test_unprovisioned_thread_reads_zero(self):
        self.assertEqual(rm.watch_count(node("alpha/intro")), 0)

    def test_other_reactions_on_the_tally_are_not_watches(self):
        n = node("alpha/intro", comments=[
            bot_comment(rm.WATCH_BODY, "C_watch", HEART=9, THUMBS_DOWN=9)
        ])
        self.assertEqual(rm.watch_count(n), 0)


# ── machinery is not conversation ───────────────────────────────────────


class MachineryCommentTests(unittest.TestCase):
    def test_provisioned_markers_are_subtracted_from_comment_counts(self):
        n = node("alpha/intro",
                 comments=[watch_comment(0), signal_comment()],
                 total_comments=2)
        self.assertEqual(rm.human_comment_count(n), 0)

    def test_count_is_computed_from_markers_actually_present(self):
        only_watch = node("alpha/intro", comments=[watch_comment(0)],
                          total_comments=3)
        self.assertEqual(rm.human_comment_count(only_watch), 2)

    def test_editorial_comment_is_machinery_too(self):
        n = node("alpha/intro",
                 comments=[watch_comment(0), signal_comment(),
                           editorial_comment(rm.EDITORIAL_MARKER + "\nnote")],
                 total_comments=5)
        self.assertEqual(rm.machinery_comment_count(n), 3)
        self.assertEqual(rm.human_comment_count(n), 2)

    def test_comment_count_never_goes_negative(self):
        n = node("alpha/intro",
                 comments=[watch_comment(0), signal_comment()],
                 total_comments=0)
        self.assertEqual(rm.human_comment_count(n), 0)

    def test_every_provisioned_marker_is_registered_as_machinery(self):
        for marker, _body in rm.MARKERS.values():
            self.assertIn(marker, rm.MACHINERY_MARKERS)
        self.assertIn(rm.EDITORIAL_MARKER, rm.MACHINERY_MARKERS)

    def test_a_double_provisioned_surface_is_excluded_twice(self):
        """Both copies are machinery. Counting markers-found instead of
        comments would let the second one masquerade as a human reply."""
        n = node("alpha/intro",
                 comments=[watch_comment(0, "C_w1"), watch_comment(0, "C_w2"),
                           signal_comment(), comment("human", "C_h")],
                 total_comments=4)
        self.assertEqual(rm.machinery_comment_count(n), 3)
        self.assertEqual(rm.human_comment_count(n), 1)


# ── snapshot building ───────────────────────────────────────────────────


class BuildSnapshotTests(unittest.TestCase):
    def test_filters_by_category_and_enumerated_subjects(self):
        subjects = {"alpha/intro"}
        nodes = [
            node("alpha/intro", number=10, top={"THUMBS_UP": 4},
                 comments=[watch_comment(2), signal_comment()],
                 total_comments=5),
            # right title, wrong category: a category ordinary users can
            # post in is a category where anyone can mint counters
            node("alpha/intro", category="General", number=11,
                 top={"THUMBS_UP": 99}),
            # well-shaped but not a real subject
            node("evil/spoofed", number=12, top={"THUMBS_UP": 99}),
            # real-looking prose, not a subject id
            node("Welcome thread", number=13, top={"THUMBS_UP": 99}),
        ]
        snap = rm.build_snapshot(nodes, subjects)
        self.assertEqual(set(snap), {"alpha/intro"})
        entry = snap["alpha/intro"]
        self.assertEqual(entry["upvotes"], 4)
        self.assertEqual(entry["watched"], 2)
        self.assertEqual(entry["comments"], 3)
        self.assertEqual(entry["channel"], "alpha")
        self.assertEqual(entry["video"], "intro")

    def test_score_weights_endorsement_above_reach(self):
        n = node("alpha/intro", top={"THUMBS_UP": 3},
                 comments=[watch_comment(4)])
        entry = rm.build_snapshot([n], {"alpha/intro"})["alpha/intro"]
        self.assertEqual(
            entry["score"], rm.RANK_UPVOTE_WEIGHT * 3 + 4
        )

    def test_duplicate_threads_earliest_wins_in_either_page_order(self):
        """The tiebreak is the discussion NUMBER, never arrival order.

        Asserting one ordering is not enough, and the weaker version of this
        test is why: with the fixture listing #50 first, a last-one-wins
        implementation also returns #3 and the test stays green. The whole
        point of the invariant is that the count cannot flip depending on
        which page GitHub returned first, so both orders are asserted and
        the two results must be identical.
        """
        early = node("alpha/intro", number=3, top={"THUMBS_UP": 1},
                     node_id="D_early", url="https://example.test/d/3")
        late = node("alpha/intro", number=50, top={"THUMBS_UP": 99},
                    node_id="D_late", url="https://example.test/d/50")
        forward = rm.build_snapshot([early, late], {"alpha/intro"})
        reverse = rm.build_snapshot([late, early], {"alpha/intro"})
        for order, snap in (("early-first", forward), ("late-first", reverse)):
            with self.subTest(order=order):
                self.assertEqual(snap["alpha/intro"]["number"], 3)
                self.assertEqual(snap["alpha/intro"]["upvotes"], 1)
                self.assertEqual(
                    snap["alpha/intro"]["url"], "https://example.test/d/3"
                )
        self.assertEqual(
            forward, reverse,
            "page order changed the snapshot; the tiebreak is not "
            "order-independent",
        )

    def test_colliding_video_ids_are_counted_separately(self):
        nodes = [
            node("alpha/intro", number=1, top={"THUMBS_UP": 2}),
            node("beta/intro", number=2, top={"THUMBS_UP": 7}),
        ]
        snap = rm.build_snapshot(nodes, {"alpha/intro", "beta/intro"})
        self.assertEqual(snap["alpha/intro"]["upvotes"], 2)
        self.assertEqual(snap["beta/intro"]["upvotes"], 7)


# ── persistence: non-clobbering, no timestamps ──────────────────────────


class PersistTests(SilentWarnings):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.snapshot = Path(self.tmp.name) / "state" / "metrics.json"
        patcher = mock.patch.object(rm, "SNAPSHOT_FILE", self.snapshot)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_prior(self, body: dict):
        self.snapshot.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot.write_text(json.dumps(body))

    def test_empty_result_never_clobbers_real_counts(self):
        prior = rm.snapshot_body({"alpha/intro": {"upvotes": 9}}, {})
        self.write_prior(prior)
        self.assertFalse(rm.persist({}, {}))
        self.assertEqual(json.loads(self.snapshot.read_text()), prior)
        self.assertWarned("keeping the existing snapshot")

    def test_unparseable_prior_snapshot_is_protected_fail_closed(self):
        self.snapshot.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot.write_text("{ truncated")
        self.assertFalse(rm.persist({}, {}))
        self.assertEqual(self.snapshot.read_text(), "{ truncated")

    def test_empty_over_an_empty_seed_is_allowed(self):
        self.write_prior(rm.snapshot_body({}, {}))
        self.assertTrue(rm.persist({}, {}))

    def test_writes_sorted_and_carries_no_timestamp(self):
        videos = {
            "zeta/z": {"upvotes": 1, "watched": 0, "score": 2, "number": 2},
            "alpha/a": {"upvotes": 2, "watched": 1, "score": 5, "number": 1},
        }
        self.assertTrue(rm.persist(videos, {}))
        written = json.loads(self.snapshot.read_text())
        self.assertEqual(written["schema"], rm.SNAPSHOT_SCHEMA)
        self.assertEqual(list(written["videos"]), ["alpha/a", "zeta/z"])
        blob = self.snapshot.read_text()
        for forbidden in ("updated_at", "generated_at", "timestamp", "at\":"):
            self.assertNotIn(forbidden, blob)

    def test_same_counts_are_byte_stable(self):
        videos = {"alpha/a": {"upvotes": 2, "watched": 1, "score": 5}}
        editorial = {"alpha/a": rm.editorial_review({"id": "a"})}
        rm.persist(videos, editorial)
        first = self.snapshot.read_bytes()
        rm.persist(dict(videos), dict(editorial))
        self.assertEqual(self.snapshot.read_bytes(), first)

    def test_counting_rules_ship_beside_the_numbers(self):
        rm.persist({"alpha/a": {"upvotes": 1}}, {})
        written = json.loads(self.snapshot.read_text())
        self.assertIn("counting", written)
        self.assertEqual(
            written["counting"]["negative_signals"],
            sorted(rm.NEGATIVE_SIGNALS),
        )
        self.assertEqual(written["signal_channels"], dict(rm.SIGNAL_MAP))


class SeedSnapshotFileTests(unittest.TestCase):
    """The committed state/metrics.json must be shaped exactly as the code
    writes it. It started life as the empty seed, but the daily cron now
    commits real counts into it — the git history of this one file is the
    network's time series — so these tests pin the SHAPE the player parses
    and never the emptiness of a file whose whole job is to fill up."""

    def test_shipped_snapshot_matches_the_code_shape(self):
        """Byte-compare the committed file against snapshot_body() re-run on
        its own contents. Round-tripping proves the file was written by this
        code (key order, indent, escaping, trailing newline) without ever
        asserting what the counts are."""
        path = REPO_ROOT / "state" / "metrics.json"
        self.assertTrue(path.exists(), f"{path} is missing")
        text = path.read_text(encoding="utf-8")
        body = json.loads(text)
        expected = json.dumps(
            rm.snapshot_body(body.get("videos", {}), body.get("editorial", {})),
            indent=2, ensure_ascii=False,
        ) + "\n"
        self.assertEqual(text, expected)

    def test_shipped_snapshot_is_well_formed(self):
        body = json.loads(
            (REPO_ROOT / "state" / "metrics.json").read_text(encoding="utf-8")
        )
        self.assertEqual(body["schema"], rm.SNAPSHOT_SCHEMA)
        self.assertIsInstance(body["videos"], dict)
        self.assertIsInstance(body["editorial"], dict)
        # Every subject key must be channel-qualified — the invariant the
        # player's collision handling depends on.
        for key in body["videos"]:
            self.assertIn("/", key, f"unscoped subject id in snapshot: {key!r}")


# ── the editorial lane ──────────────────────────────────────────────────


class EditorialReviewTests(unittest.TestCase):
    GOOD = {
        "id": "showcase",
        "title": "A real entry",
        "description": "x" * 120,
        "duration": 219.5,
        "width": 1920,
        "height": 1080,
        "tags": ["demo"],
        "thumb": "thumbs/showcase.jpg",
        "sources": [
            {"src": "media/showcase.mp4", "type": "video/mp4"},
            {"src": "media/showcase.webm", "type": "video/webm"},
        ],
        "chapters": [{"t": 0, "label": "Intro"}],
    }

    def test_a_complete_record_reads_ready(self):
        review = rm.editorial_review(self.GOOD)
        self.assertEqual(review["verdict"], rm.VERDICT_READY)
        self.assertEqual(review["notes"], [])
        self.assertEqual(review["by"], rm.EDITORIAL_BY)

    def test_missing_webm_is_named_not_guessed(self):
        record = dict(self.GOOD, sources=[
            {"src": "media/showcase.mp4", "type": "video/mp4"}
        ])
        review = rm.editorial_review(record)
        self.assertEqual(review["verdict"], rm.VERDICT_ROUGH)
        self.assertTrue(any("WebM" in n for n in review["notes"]))

    def test_live_only_entry_is_not_penalised_for_shipping_no_video(self):
        record = {
            "id": "live", "title": "Live", "description": "y" * 90,
            "duration": 30, "width": 1280, "height": 800, "tags": ["live"],
            "thumb": "thumbs/live.jpg", "sources": [],
            "live": {"scenes": [
                {"t": 0, "app": "../app.html",
                 "ready": {"selector": "#start"}}
            ]},
        }
        review = rm.editorial_review(record)
        self.assertEqual(review["verdict"], rm.VERDICT_READY)
        self.assertGreaterEqual(review["not_applicable"], 1)

    def test_live_scene_without_ready_is_flagged(self):
        record = {
            "id": "live", "title": "Live", "description": "y" * 90,
            "duration": 30, "width": 1280, "height": 800, "tags": ["live"],
            "thumb": "thumbs/live.jpg", "sources": [],
            "live": {"scenes": [{"t": 0, "app": "../app.html"}]},
        }
        review = rm.editorial_review(record)
        self.assertEqual(review["verdict"], rm.VERDICT_ROUGH)
        self.assertTrue(any("ready" in n for n in review["notes"]))

    def test_empty_record_fails_loudly_rather_than_reading_ready(self):
        review = rm.editorial_review({})
        self.assertEqual(review["verdict"], rm.VERDICT_ROUGH)
        self.assertTrue(review["notes"])

    def test_review_is_deterministic(self):
        self.assertEqual(
            rm.editorial_review(self.GOOD), rm.editorial_review(dict(self.GOOD))
        )

    def test_review_is_pinned_to_the_record_it_read(self):
        changed = dict(self.GOOD, title="Renamed")
        self.assertNotEqual(
            rm.editorial_review(self.GOOD)["record_sha8"],
            rm.editorial_review(changed)["record_sha8"],
        )

    def test_player_attached_fields_do_not_change_the_fingerprint(self):
        annotated = dict(self.GOOD, _ch={"id": "alpha"}, _i=3)
        self.assertEqual(
            rm.record_fingerprint(self.GOOD),
            rm.record_fingerprint(annotated),
        )

    def test_fingerprint_normalizes_javascript_number_semantics(self):
        self.assertEqual(
            rm.record_fingerprint({"duration": 10}),
            rm.record_fingerprint({"duration": 10.0}),
        )
        self.assertEqual(
            rm.record_fingerprint({"value": 0}),
            rm.record_fingerprint({"value": -0.0}),
        )
        self.assertNotEqual(
            rm.record_fingerprint({"value": 1e-7}),
            rm.record_fingerprint({"value": 1e-8}),
        )
        self.assertEqual(
            rm.record_fingerprint({"value": "\ud800", "\udfff": "key"}),
            rm.record_fingerprint({"value": "\ufffd", "\ufffd": "key"}),
        )

    def test_rendered_note_is_marked_attributed_and_stable(self):
        review = rm.editorial_review(self.GOOD)
        body = rm.render_editorial("alpha/showcase", review)
        self.assertTrue(body.startswith(rm.EDITORIAL_MARKER))
        self.assertIn(rm.EDITORIAL_BY, body)
        self.assertIn("machine-written", body.lower())
        # It must say the two lanes are separate...
        self.assertIn("never added to the video", body.lower())
        # ...and must NOT tell a human their reaction is worthless, because
        # a human reacting at the bot layer is counted (rubric feedback).
        self.assertNotIn("counted nowhere", body)
        self.assertEqual(
            body, rm.render_editorial("alpha/showcase", review)
        )

    def test_rendered_note_is_stable_while_humans_react_to_it(self):
        """A reaction on the review must not rewrite the review.

        render_editorial reads the verdict only. If it ever rendered the
        feedback counts, every reaction would make the body differ from the
        one on the thread and the editorial command would rewrite it on
        every run — a daily write for a review that did not change.
        """
        review = rm.editorial_review(self.GOOD)
        quiet = rm.render_editorial("alpha/showcase", review)
        reacted = dict(review, reviewer_feedback={
            "agreed": 9, "disputed": 4, "unclear": 1, "actor": "human",
        })
        self.assertEqual(quiet, rm.render_editorial("alpha/showcase", reacted))


class EditorialIsolationTests(unittest.TestCase):
    """A bot write must be unable to move a human number."""

    SUBJECT = "alpha/intro"

    def human_only(self) -> dict:
        return node(self.SUBJECT, number=1, top={"THUMBS_UP": 3, "HEART": 1},
                    comments=[watch_comment(5),
                              signal_comment(THUMBS_UP=2, THUMBS_DOWN=1),
                              comment("A real human reply", "C_human")],
                    total_comments=3)

    def with_editorial(self) -> dict:
        n = self.human_only()
        # The editorial comment lands, and somebody even reacts to it.
        n["comments"]["nodes"].append(
            editorial_comment(rm.EDITORIAL_MARKER + "\n### Editorial note",
                              THUMBS_UP=40, HEART=25, THUMBS_DOWN=12)
        )
        n["comments"]["totalCount"] += 1
        return n

    def test_editorial_moves_no_human_counter(self):
        before = rm.build_snapshot([self.human_only()], {self.SUBJECT})
        after = rm.build_snapshot([self.with_editorial()], {self.SUBJECT})
        self.assertEqual(before, after)

    def test_human_reply_still_counts_as_one(self):
        entry = rm.build_snapshot(
            [self.with_editorial()], {self.SUBJECT}
        )[self.SUBJECT]
        self.assertEqual(entry["comments"], 1)

    def test_reactions_on_the_editorial_comment_reach_no_signal_channel(self):
        counts = rm.signal_counts(self.with_editorial())
        self.assertEqual(counts["watched_it_all"], 2)
        self.assertEqual(counts["want_more_like_this"], 0)
        self.assertEqual(counts["too_long"], 1)

    def test_this_script_cannot_add_a_reaction_at_all(self):
        """The strongest form of the guarantee: there is no reaction-adding
        mutation in the file, so no code path — bot, editorial or seed —
        can move a counter that is supposed to be a count of people."""
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("addReaction", source)
        self.assertNotIn("removeReaction", source)

    def test_editorial_block_is_separate_from_the_counted_block(self):
        videos = rm.build_snapshot([self.human_only()], {self.SUBJECT})
        editorial = {self.SUBJECT: rm.editorial_review({"id": "intro"})}
        body = rm.snapshot_body(videos, editorial)
        self.assertNotIn("editorial", body["videos"][self.SUBJECT])
        self.assertIn(self.SUBJECT, body["editorial"])
        self.assertIn("Never counted", body["counting"]["editorial"])


class ReviewerFeedbackTests(unittest.TestCase):
    """THE ACTOR DETERMINES THE LANE — NEVER THE SUBJECT.

    Half 1 (a bot action never feeds a human counter) is pinned by
    EditorialIsolationTests. This class pins half 2: a HUMAN acting at the
    bot layer is real engagement and must count. Quarantining these by
    SUBJECT — "a robot wrote the comment, so ignore everything about it" —
    is the opposite error, and it is what these tests exist to catch.
    """

    SUBJECT = "alpha/intro"
    SUBJECTS = {SUBJECT: {"record": {"id": "intro", "title": "Intro"}}}

    def reviewed(self, **counts) -> dict:
        """A thread with human counts AND a reacted-to machine review."""
        return node(
            self.SUBJECT, number=1, top={"THUMBS_UP": 3},
            comments=[
                watch_comment(5),
                signal_comment(THUMBS_UP=2, THUMBS_DOWN=1),
                comment("A real human reply", "C_human"),
                editorial_comment(rm.EDITORIAL_MARKER + "\n### Editorial note",
                                  **counts),
            ],
            total_comments=4,
        )

    def test_humans_reacting_to_a_machine_review_are_counted(self):
        counts = rm.reviewer_feedback(
            self.reviewed(THUMBS_UP=40, THUMBS_DOWN=12, CONFUSED=3)
        )
        self.assertEqual(counts["agreed"], 40)
        self.assertEqual(counts["disputed"], 12)
        self.assertEqual(counts["unclear"], 3)

    def test_feedback_is_labelled_as_human_engagement(self):
        editorial = rm.build_editorial(
            self.SUBJECTS, [self.reviewed(THUMBS_UP=4)]
        )
        self.assertEqual(
            editorial[self.SUBJECT]["reviewer_feedback"]["actor"], "human"
        )

    def test_feedback_moves_no_video_counter(self):
        """The whole point of the separation: real human numbers, but about
        the reviewer, so not one of them reaches the video's counters."""
        quiet = rm.build_snapshot([self.reviewed()], {self.SUBJECT})
        loud = rm.build_snapshot(
            [self.reviewed(THUMBS_UP=99, THUMBS_DOWN=40, CONFUSED=7)],
            {self.SUBJECT},
        )
        self.assertEqual(quiet, loud)
        entry = loud[self.SUBJECT]
        self.assertEqual(entry["upvotes"], 3)
        self.assertEqual(entry["watched"], 5)
        self.assertEqual(entry["score"], rm.RANK_UPVOTE_WEIGHT * 3 + 5)
        self.assertEqual(entry["comments"], 1)
        self.assertEqual(entry["signals"]["watched_it_all"], 2)

    def test_an_unreviewed_subject_reads_zero_not_missing(self):
        editorial = rm.build_editorial(self.SUBJECTS, [])
        self.assertEqual(
            editorial[self.SUBJECT]["reviewer_feedback"],
            {"agreed": 0, "disputed": 0, "unclear": 0, "actor": "human"},
        )

    def test_every_feedback_channel_maps_to_a_distinct_reaction(self):
        contents = list(rm.REVIEWER_FEEDBACK_MAP)
        names = list(rm.REVIEWER_FEEDBACK_MAP.values())
        self.assertEqual(len(set(contents)), len(contents))
        self.assertEqual(len(set(names)), len(names))

    def test_rubric_health_exposes_sustained_dispute(self):
        """Sustained negative human signal on the reviews means the rubric
        is wrong. It has to be visible, not buried in a net number."""
        editorial = {
            "a/one": {"reviewer_feedback": {"agreed": 1, "disputed": 9,
                                            "unclear": 0}},
            "a/two": {"reviewer_feedback": {"agreed": 7, "disputed": 2,
                                            "unclear": 1}},
        }
        health = rm.rubric_health(editorial)
        self.assertEqual(health["agreed"], 8)
        self.assertEqual(health["disputed"], 11)
        self.assertEqual(health["unclear"], 1)
        self.assertEqual(health["subjects_where_dispute_leads"], ["a/one"])
        self.assertEqual(health["actor"], "human")

    def test_rubric_health_never_nets_dispute_against_agreement(self):
        health = rm.rubric_health(
            {"a/one": {"reviewer_feedback": {"agreed": 5, "disputed": 5}}}
        )
        self.assertEqual(health["agreed"], 5)
        self.assertEqual(health["disputed"], 5)
        self.assertNotIn(0, (health["agreed"], health["disputed"]))

    def test_snapshot_publishes_the_lane_and_names_whose_it_is(self):
        videos = rm.build_snapshot([self.reviewed()], {self.SUBJECT})
        editorial = rm.build_editorial(
            self.SUBJECTS, [self.reviewed(THUMBS_UP=6, THUMBS_DOWN=1)]
        )
        body = rm.snapshot_body(videos, editorial)
        self.assertEqual(
            body["editorial"][self.SUBJECT]["reviewer_feedback"]["agreed"], 6
        )
        self.assertEqual(body["rubric_health"]["disputed"], 1)
        # ...and it is nowhere near the video block.
        self.assertNotIn("reviewer_feedback", body["videos"][self.SUBJECT])
        self.assertIn("ACTOR", body["counting"]["reviewer_feedback"])

    def test_feedback_uses_the_same_thread_as_the_counts(self):
        """Duplicate threads: the editorial lane and the counted block must
        agree on which thread is authoritative, or the snapshot reports a
        verdict from one thread and its feedback from another."""
        early = self.reviewed(THUMBS_UP=2)
        early["number"], early["id"] = 3, "D_early"
        late = self.reviewed(THUMBS_UP=90)
        late["number"], late["id"] = 50, "D_late"
        for order in ([early, late], [late, early]):
            with self.subTest(order=[n["id"] for n in order]):
                editorial = rm.build_editorial(self.SUBJECTS, order)
                self.assertEqual(
                    editorial[self.SUBJECT]["reviewer_feedback"]["agreed"], 2
                )
                self.assertEqual(
                    rm.build_snapshot(order, {self.SUBJECT})
                    [self.SUBJECT]["number"], 3
                )


class EditorialTargetTests(unittest.TestCase):
    SUBJECTS = {"alpha/intro": {"record": {"id": "intro", "title": "Intro"}}}

    def current_body(self) -> str:
        return rm.render_editorial(
            "alpha/intro",
            rm.editorial_review(self.SUBJECTS["alpha/intro"]["record"]),
        )

    def test_missing_note_is_a_create(self):
        targets = rm.editorial_targets([node("alpha/intro", node_id="D_7")],
                                       self.SUBJECTS)
        self.assertEqual(len(targets), 1)
        self.assertIsNone(targets[0]["comment_id"])
        self.assertEqual(targets[0]["discussion_id"], "D_7")

    def test_stale_note_is_an_update_not_a_second_comment(self):
        n = node("alpha/intro", comments=[
            editorial_comment(rm.EDITORIAL_MARKER + "\nold text", "C_old")
        ])
        targets = rm.editorial_targets([n], self.SUBJECTS)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["comment_id"], "C_old")

    def test_unchanged_note_costs_zero_writes(self):
        n = node("alpha/intro",
                 comments=[editorial_comment(self.current_body())])
        self.assertEqual(rm.editorial_targets([n], self.SUBJECTS), [])

    def test_threads_outside_the_category_or_registry_are_never_written(self):
        nodes = [
            node("alpha/intro", category="General"),
            node("evil/spoofed"),
            node("Welcome thread"),
        ]
        self.assertEqual(rm.editorial_targets(nodes, self.SUBJECTS), [])

    def test_only_targets_a_single_subject(self):
        subjects = dict(self.SUBJECTS, **{"beta/intro": {"record": {}}})
        nodes = [node("alpha/intro", number=1), node("beta/intro", number=2)]
        targets = rm.editorial_targets(nodes, subjects, only="beta/intro")
        self.assertEqual([t["subject"] for t in targets], ["beta/intro"])


# ── non-fatal posture ───────────────────────────────────────────────────


class NonFatalTests(SilentWarnings):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.snapshot = root / "state" / "metrics.json"
        self.snapshot.parent.mkdir(parents=True)
        self.prior = rm.snapshot_body({"alpha/intro": {"upvotes": 9}}, {})
        self.snapshot.write_text(json.dumps(self.prior))

        (root / "channel.json").write_text(json.dumps({
            "id": "alpha",
            "videos": [{"id": "intro", "title": "Intro"}],
        }))
        self.network = root / "channels.json"
        self.network.write_text(json.dumps(
            {"channels": [{"id": "alpha", "url": "channel.json"}]}
        ))
        for name, value in (
            ("SNAPSHOT_FILE", self.snapshot),
            ("NETWORK_FILE", self.network),
        ):
            patcher = mock.patch.object(rm, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    @contextlib.contextmanager
    def token(self, value: str):
        patcher = mock.patch.object(rm, "TOKEN", value)
        patcher.start()
        try:
            yield
        finally:
            patcher.stop()

    def assertSnapshotUnchanged(self):
        self.assertEqual(json.loads(self.snapshot.read_text()), self.prior)

    def test_fetch_without_a_token_exits_zero_and_changes_nothing(self):
        with self.token(""):
            self.assertEqual(rm.cmd_fetch(), 0)
        self.assertSnapshotUnchanged()
        self.assertWarned("no GITHUB_TOKEN")

    def test_fetch_survives_a_network_error(self):
        with self.token("t"), mock.patch.object(
            rm, "fetch_all_discussions", side_effect=OSError("connection reset")
        ):
            self.assertEqual(rm.cmd_fetch(), 0)
        self.assertSnapshotUnchanged()
        self.assertWarned("connection reset")

    def test_fetch_survives_a_graphql_error(self):
        with self.token("t"), mock.patch.object(
            rm, "fetch_all_discussions",
            side_effect=RuntimeError("Resource not accessible"),
        ):
            self.assertEqual(rm.cmd_fetch(), 0)
        self.assertSnapshotUnchanged()

    def test_fetch_with_no_subjects_changes_nothing(self):
        self.network.write_text("{}")
        with self.token("t"):
            self.assertEqual(rm.cmd_fetch(), 0)
        self.assertSnapshotUnchanged()
        self.assertWarned("no subjects enumerated")

    def test_fetch_writes_both_blocks_from_one_enumeration(self):
        threads = [node("alpha/intro", number=4, top={"THUMBS_UP": 2},
                        comments=[watch_comment(3), signal_comment(HOORAY=1)],
                        total_comments=2)]
        with self.token("t"), mock.patch.object(
            rm, "fetch_all_discussions", return_value=threads
        ):
            self.assertEqual(rm.cmd_fetch(), 0)
        written = json.loads(self.snapshot.read_text())
        self.assertEqual(written["videos"]["alpha/intro"]["upvotes"], 2)
        self.assertEqual(written["videos"]["alpha/intro"]["watched"], 3)
        self.assertEqual(written["videos"]["alpha/intro"]["comments"], 0)
        self.assertEqual(
            written["videos"]["alpha/intro"]["signals"]["learned_something"], 1
        )
        # Editorial covers every enumerated subject, thread or not, and is
        # never merged into the counted block.
        self.assertIn("alpha/intro", written["editorial"])
        self.assertEqual(
            written["editorial"]["alpha/intro"]["by"], rm.EDITORIAL_BY
        )

    def test_write_commands_without_a_token_do_nothing(self):
        with self.token(""):
            self.assertEqual(rm.cmd_seed(10, 0), 0)
            self.assertEqual(rm.cmd_surfaces(10, 0), 0)
            self.assertEqual(rm.cmd_editorial(10, 0), 0)
        self.assertSnapshotUnchanged()

    def test_seed_survives_a_failed_preflight(self):
        with self.token("t"), mock.patch.object(
            rm, "graphql", side_effect=RuntimeError("bad credentials")
        ):
            self.assertEqual(rm.cmd_seed(10, 0), 0)
        self.assertWarned("seed preflight failed")

    def test_surfaces_survives_a_failed_preflight(self):
        with self.token("t"), mock.patch.object(
            rm, "fetch_all_discussions", side_effect=OSError("timeout")
        ):
            self.assertEqual(rm.cmd_surfaces(10, 0), 0)
        self.assertWarned("surfaces preflight failed")

    def test_editorial_survives_a_failed_preflight(self):
        with self.token("t"), mock.patch.object(
            rm, "fetch_all_discussions", side_effect=OSError("timeout")
        ):
            self.assertEqual(rm.cmd_editorial(10, 0), 0)
        self.assertWarned("editorial preflight failed")

    def test_editorial_stops_instead_of_failing_on_a_rate_limit(self):
        threads = [node("alpha/intro", number=1, node_id="D_1")]
        with self.token("t"), mock.patch.object(
            rm, "fetch_all_discussions", return_value=threads
        ), mock.patch.object(
            rm, "graphql", side_effect=RuntimeError("secondary rate limit")
        ):
            self.assertEqual(rm.cmd_editorial(10, 0), 0)
        self.assertWarned("stopping after 0 editorial note(s)")


class RateLimitCapTests(SilentWarnings):
    """--limit is what lets a backlog drain over successive cron runs."""

    def test_editorial_batch_is_capped(self):
        subjects = {f"alpha/v{i}": {"record": {"id": f"v{i}"}} for i in range(10)}
        nodes = [node(sid, number=i, node_id=f"D_{i}")
                 for i, sid in enumerate(sorted(subjects), start=1)]
        targets = rm.editorial_targets(nodes, subjects)
        self.assertEqual(len(targets), 10)
        calls: list[dict] = []
        with mock.patch.object(rm, "TOKEN", "t"), mock.patch.object(
            rm, "fetch_all_discussions", return_value=nodes
        ), mock.patch.object(
            rm, "enumerate_subjects", return_value=subjects
        ), mock.patch.object(
            rm, "graphql", side_effect=lambda q, v: calls.append(v) or {}
        ):
            self.assertEqual(rm.cmd_editorial(3, 0), 0)
        self.assertEqual(len(calls), 3)

# ── a marker is a routing label, never a credential ─────────────────────


class MarkerSquattingTests(unittest.TestCase):
    """The machinery markers are HTML comments, so they render as NOTHING.

    Anyone who can comment on a public thread can paste one into an
    ordinary-looking sentence. Until detection was ownership-checked that
    bought a stranger three things at once: their reaction counts were read
    as `watched` / `signals` / `reviewer_feedback`, their comment was
    subtracted from the human comment count, and the editorial lane aimed
    `updateDiscussionComment` at their comment.

    Nothing here hides or penalises the squatter. Their comment stays, and
    it stays counted as exactly what it is: one human comment.
    """

    SUBJECT = "alpha/intro"
    SUBJECTS = {SUBJECT: {"record": {"id": "intro", "title": "Intro"}}}

    def squatted(self, marker: str, cid: str, **counts) -> dict:
        """A HUMAN comment carrying a machinery marker, placed FIRST.

        Order is not a defence: `surfaces` back-fills markers onto threads
        that already exist, so a squatter's comment can predate the real
        surface. Every fixture here puts the squat ahead of the genuine
        comment for that reason.
        """
        return comment(f"{marker} great video, honestly", cid, **counts)

    def test_the_query_asks_who_wrote_each_comment(self):
        """Ownership cannot be checked on a field that was never fetched."""
        self.assertIn("viewerDidAuthor", rm.DISCUSSIONS_QUERY)
        self.assertIn("author { login }", rm.DISCUSSIONS_QUERY)

    def test_a_squatted_watch_marker_donates_no_watches(self):
        n = node(self.SUBJECT, comments=[
            self.squatted(rm.WATCH_MARKER, "C_squat", THUMBS_UP=9999),
            watch_comment(3),
        ], total_comments=2)
        self.assertEqual(rm.watch_count(n), 3)
        entry = rm.build_snapshot([n], {self.SUBJECT})[self.SUBJECT]
        self.assertEqual(entry["watched"], 3)
        self.assertEqual(entry["score"], 3)
        # ...and the squatter is still a human comment, counted as one.
        self.assertEqual(entry["comments"], 1)

    def test_a_squatted_signal_marker_donates_no_signals(self):
        n = node(self.SUBJECT, comments=[
            self.squatted(rm.SIGNAL_MARKER, "C_squat",
                          THUMBS_UP=500, HOORAY=500, HEART=500),
            signal_comment(THUMBS_UP=2),
        ], total_comments=2)
        counts = rm.signal_counts(n)
        self.assertEqual(counts["watched_it_all"], 2)
        self.assertEqual(counts["learned_something"], 0)
        self.assertEqual(counts["want_more_like_this"], 0)

    def test_a_squatted_editorial_marker_feeds_no_reviewer_feedback(self):
        n = node(self.SUBJECT, comments=[
            self.squatted(rm.EDITORIAL_MARKER, "C_squat",
                          THUMBS_UP=9, THUMBS_DOWN=1),
        ], total_comments=1)
        self.assertEqual(rm.reviewer_feedback(n), rm.empty_reviewer_feedback())
        self.assertEqual(
            rm.rubric_health(rm.build_editorial(self.SUBJECTS, [n]))["agreed"],
            0,
        )

    def test_a_squatter_is_never_subtracted_from_the_human_total(self):
        n = node(self.SUBJECT, comments=[
            self.squatted(rm.EDITORIAL_MARKER, "C_h1"),
            comment("second human comment", "C_h2"),
            comment("third human comment", "C_h3"),
        ], total_comments=3)
        self.assertEqual(rm.machinery_comment_count(n), 0)
        self.assertEqual(rm.human_comment_count(n), 3)

    def test_the_editorial_update_is_never_aimed_at_a_human_comment(self):
        """A `discussions: write` token pointed at a stranger's comment
        overwrites their words and bylines the machine review to them.
        That is not recoverable by a later run, so the target must be a
        CREATE, not an update."""
        n = node(self.SUBJECT, node_id="D_1", comments=[
            self.squatted(rm.EDITORIAL_MARKER, "C_human_first", THUMBS_UP=9),
        ], total_comments=1)
        targets = rm.editorial_targets([n], self.SUBJECTS)
        self.assertEqual(len(targets), 1)
        self.assertIsNone(targets[0]["comment_id"])
        self.assertEqual(targets[0]["discussion_id"], "D_1")

    def test_a_human_comment_containing_every_marker_changes_no_counter(self):
        clean = node(self.SUBJECT, top={"THUMBS_UP": 4}, comments=[
            watch_comment(3),
            signal_comment(THUMBS_UP=2, THUMBS_DOWN=1),
            editorial_comment(rm.EDITORIAL_MARKER + "\nnote", THUMBS_UP=7),
            comment("a real human reply", "C_human"),
        ])                            # 3 machinery + 1 human reply
        squatted = json.loads(json.dumps(clean))
        squatted["comments"]["nodes"].insert(0, comment(
            " ".join(rm.MACHINERY_MARKERS) + " every marker at once",
            "C_squat", THUMBS_UP=9999, HOORAY=9999, HEART=9999,
            ROCKET=9999, EYES=9999, THUMBS_DOWN=9999, CONFUSED=9999,
        ))
        squatted["comments"]["totalCount"] += 1

        before = rm.build_snapshot([clean], {self.SUBJECT})[self.SUBJECT]
        after = rm.build_snapshot([squatted], {self.SUBJECT})[self.SUBJECT]
        # The ONE thing that moves is the human comment count, by exactly
        # one, because a person did in fact write one comment.
        self.assertEqual(after["comments"], before["comments"] + 1)
        self.assertEqual(
            {k: v for k, v in after.items() if k != "comments"},
            {k: v for k, v in before.items() if k != "comments"},
        )
        self.assertEqual(rm.reviewer_feedback(squatted),
                         rm.reviewer_feedback(clean))

    def test_a_marker_mentioned_in_passing_is_not_a_surface(self):
        """Anchored, not substring: even OUR OWN comment quoting a marker
        mid-body is documentation, not a counter."""
        quoting = bot_comment(
            f"the tally comment starts with {rm.WATCH_MARKER}", "C_doc",
            THUMBS_UP=77,
        )
        self.assertEqual(rm.watch_count(node(self.SUBJECT,
                                             comments=[quoting])), 0)

    def test_an_unattributable_comment_is_treated_as_human(self):
        """GitHub returns `author: null` for a deleted account. The safe
        default is the human side: one machinery comment counted as
        conversation costs a number, the other default costs the rule."""
        ghost = comment(rm.WATCH_BODY, "C_ghost", author=None, THUMBS_UP=50)
        self.assertFalse(rm.machinery_authored(ghost))
        self.assertEqual(rm.watch_count(node(self.SUBJECT,
                                             comments=[ghost])), 0)

    def test_an_allowlisted_login_is_machinery_without_viewerdidauthor(self):
        """The escape hatch for a thread seeded under another identity: a
        token that did not write the comment still recognises it."""
        seeded = comment(rm.WATCH_BODY, "C_pat", author=BOT_LOGIN,
                         viewer_did_author=False, THUMBS_UP=6)
        self.assertIn(BOT_LOGIN, rm.MACHINERY_AUTHORS)
        self.assertTrue(rm.machinery_authored(seeded))
        self.assertEqual(rm.watch_count(node(self.SUBJECT,
                                             comments=[seeded])), 6)


# ── the seeder and the counter must agree on "already exists" ───────────


class SeedPreflightTests(SilentWarnings):
    """`build_snapshot`, `cmd_surfaces` and `editorial_targets` all filter
    to CATEGORY. An unfiltered preflight in `cmd_seed` disagreed with every
    one of them, which meant a discussion titled with a subject id in an
    OPEN category (General — writable by any user on a public repo) made
    the seeder skip that subject while the counter never looked there. The
    subject then became permanently and silently uncountable.
    """

    SUBJECTS = {
        "alpha/intro": {"channel": "alpha", "video": "intro",
                        "title": "Intro", "channel_name": "Alpha",
                        "record": {}},
        "alpha/short": {"channel": "alpha", "video": "short",
                        "title": "Short", "channel_name": "Alpha",
                        "record": {}},
    }

    def run_seed(self, discussions: list[dict]) -> list[str]:
        created: list[str] = []

        def fake_graphql(query, variables):
            if "discussionCategories" in query:
                return {"repository": {
                    "id": "R_1",
                    "discussionCategories": {
                        "nodes": [{"id": "C_ann", "name": rm.CATEGORY}]
                    },
                }}
            if "createDiscussion" in query:
                created.append(variables["title"])
                return {"createDiscussion": {"discussion": {"id": "D_new"}}}
            return {}

        with mock.patch.object(rm, "TOKEN", "t"), mock.patch.object(
            rm, "enumerate_subjects", return_value=self.SUBJECTS
        ), mock.patch.object(
            rm, "fetch_all_discussions", return_value=discussions
        ), mock.patch.object(rm, "graphql", side_effect=fake_graphql):
            self.assertEqual(rm.cmd_seed(60, 0), 0)
        return sorted(created)

    def test_a_squatted_title_in_an_open_category_does_not_block_seeding(self):
        squat = node("alpha/intro", category="General", node_id="D_squat")
        self.assertEqual(self.run_seed([squat]),
                         ["alpha/intro", "alpha/short"])

    def test_a_thread_in_the_counted_category_is_still_not_reseeded(self):
        """The filter must not turn idempotence off along the way."""
        real = node("alpha/intro", node_id="D_real")
        self.assertEqual(self.run_seed([real]), ["alpha/short"])


# ── one bad thread must not stall the network ──────────────────────────


class EditorialFailureIsolationTests(SilentWarnings):
    """Targets are ordered by discussion number ascending, so an
    unconditional `break` on any write failure means the lowest-numbered
    failing thread blocks every thread behind it — on this run and on every
    future run, silently and forever.
    """

    def build(self, count: int):
        subjects = {f"alpha/v{i}": {"record": {"id": f"v{i}"}}
                    for i in range(count)}
        nodes = [node(sid, number=i, node_id=f"D_{i}")
                 for i, sid in enumerate(sorted(subjects), start=1)]
        return subjects, nodes

    def run_editorial(self, subjects, nodes, side_effect):
        with mock.patch.object(rm, "TOKEN", "t"), mock.patch.object(
            rm, "enumerate_subjects", return_value=subjects
        ), mock.patch.object(
            rm, "fetch_all_discussions", return_value=nodes
        ), mock.patch.object(rm, "graphql", side_effect=side_effect):
            self.assertEqual(rm.cmd_editorial(40, 0), 0)

    def test_one_rejected_thread_does_not_block_the_rest(self):
        subjects, nodes = self.build(4)
        written: list[str] = []

        def fake(query, variables):
            if variables.get("discussionId") == "D_1":
                raise RuntimeError("Resource not accessible by integration")
            written.append(variables.get("discussionId"))
            return {}

        self.run_editorial(subjects, nodes, fake)
        self.assertEqual(written, ["D_2", "D_3", "D_4"])
        self.assertWarned("skipping 'alpha/v0'")

    def test_a_rate_limit_still_stops_the_whole_batch(self):
        """The opposite case: a rate limit applies to everything left, so
        continuing burns the budget for nothing."""
        subjects, nodes = self.build(4)
        seen: list[str] = []

        def fake(query, variables):
            seen.append(variables.get("discussionId"))
            raise RuntimeError("You have exceeded a secondary rate limit")

        self.run_editorial(subjects, nodes, fake)
        self.assertEqual(seen, ["D_1"])
        self.assertWarned("rate limited")

    def test_an_all_failing_batch_gives_up_after_n_in_a_row(self):
        subjects, nodes = self.build(10)
        seen: list[str] = []

        def fake(query, variables):
            seen.append(variables.get("discussionId"))
            raise RuntimeError("something specific went wrong")

        self.run_editorial(subjects, nodes, fake)
        self.assertEqual(len(seen), rm.EDITORIAL_CONSECUTIVE_FAILURES)
        self.assertWarned("consecutive failures")

    def http_error(self, code: int) -> urllib.error.HTTPError:
        exc = urllib.error.HTTPError("u", code, "boom", {}, None)
        self.addCleanup(exc.close)     # HTTPError owns a temp file
        return exc

    def test_a_403_is_read_as_a_rate_limit_and_a_500_is_not(self):
        self.assertTrue(rm.looks_rate_limited(self.http_error(403)))
        self.assertTrue(rm.looks_rate_limited(self.http_error(429)))
        self.assertFalse(rm.looks_rate_limited(self.http_error(500)))
        self.assertTrue(rm.looks_rate_limited(RuntimeError("Too Many Requests")))


# ── an unusable response is not a failed build ─────────────────────────


class _FakeResponse(io.BytesIO):
    """urlopen's context-manager shape over a fixed body."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class UnusableResponseTests(SilentWarnings):
    """A 200 carrying an HTML body is GitHub's classic degraded-mode
    response (a CDN interstitial). `json.JSONDecodeError` and
    `UnicodeDecodeError` are ValueError, and `http.client.IncompleteRead`
    is an HTTPException — none of them is OSError, RuntimeError or
    URLError, so before this was normalised inside `graphql` each one
    escaped every caller's except clause and failed the build the module
    docstring promises can never fail.

    The old suite missed it because it mocked `fetch_all_discussions` with
    `side_effect=OSError`, which exercises only the caller's except clause
    and never `graphql`'s parse. These tests patch `urlopen` instead, so
    the real parse path runs.
    """

    UNUSABLE = {
        "an HTML interstitial": b"<html>502 Bad Gateway</html>",
        "an empty body": b"",
        "a JSON array, not an object": b"[]",
        "non-UTF-8 bytes": b"\xff\xfe\x00",
    }

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.snapshot = root / "state" / "metrics.json"
        self.snapshot.parent.mkdir(parents=True)
        self.snapshot.write_text(json.dumps(
            rm.snapshot_body({"alpha/intro": {"upvotes": 9}}, {})
        ))
        self.prior_bytes = self.snapshot.read_bytes()

        (root / "channel.json").write_text(json.dumps({
            "id": "alpha", "videos": [{"id": "intro", "title": "Intro"}],
        }))
        self.network = root / "channels.json"
        self.network.write_text(json.dumps(
            {"channels": [{"id": "alpha", "url": "channel.json"}]}
        ))
        for name, value in (
            ("SNAPSHOT_FILE", self.snapshot),
            ("NETWORK_FILE", self.network),
            ("TOKEN", "t"),
        ):
            patcher = mock.patch.object(rm, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    @contextlib.contextmanager
    def responding(self, body: bytes):
        """Every urlopen call gets a FRESH response over the same bytes."""
        with mock.patch.object(
            urllib.request, "urlopen",
            lambda req, timeout=None: _FakeResponse(body),
        ):
            yield

    def test_graphql_normalises_an_unusable_body_to_runtimeerror(self):
        for label, body in self.UNUSABLE.items():
            with self.subTest(body=label), self.responding(body):
                with self.assertRaises(RuntimeError):
                    rm.graphql("query {}", {})

    def test_graphql_normalises_a_truncated_body(self):
        def truncated(req, timeout=None):
            raise http.client.IncompleteRead(b"partial")

        with mock.patch.object(urllib.request, "urlopen", truncated):
            with self.assertRaises(RuntimeError) as caught:
                rm.graphql("query {}", {})
        self.assertIn("unusable response", str(caught.exception))

    def test_an_http_error_still_reaches_the_caller_as_itself(self):
        """The normalisation must not swallow the errors that already
        worked: HTTPError is an OSError and callers catch it."""
        exc = urllib.error.HTTPError("u", 502, "bad gateway", {}, None)
        self.addCleanup(exc.close)     # HTTPError owns a temp file

        def failing(req, timeout=None):
            raise exc

        with mock.patch.object(urllib.request, "urlopen", failing):
            with self.assertRaises(urllib.error.HTTPError):
                rm.graphql("query {}", {})

    def test_every_subcommand_survives_an_html_interstitial(self):
        commands = {
            "fetch": lambda: rm.cmd_fetch(),
            "seed": lambda: rm.cmd_seed(10, 0),
            "surfaces": lambda: rm.cmd_surfaces(10, 0),
            "editorial": lambda: rm.cmd_editorial(10, 0),
        }
        for name, run in commands.items():
            with self.subTest(command=name):
                with self.responding(b"<html>502 Bad Gateway</html>"):
                    self.assertEqual(run(), 0)
                # Byte-for-byte: an unusable response must not rewrite the
                # snapshot even with identical content.
                self.assertEqual(self.snapshot.read_bytes(), self.prior_bytes)


# ── a thread longer than one page of comments ───────────────────────────
#
# DISCUSSIONS_QUERY reads comments(first: COMMENT_PAGE_SIZE) but subtracts
# the machinery it found from totalCount, which counts the WHOLE thread.
# Past one page those two describe different sets: a machinery comment at
# position 101 is not in the subtrahend, so it lands in `comments` — a
# MACHINE's own output inside a HUMAN counter, which is the one thing the
# founding tenet forbids. It compounds, because the editorial note is the
# first machinery comment to fall off the page and the writer then appends a
# new one every night.


def long_thread(*, humans: int, machinery: list[dict], extra_total: int = 0,
                title: str = "alpha/intro", node_id: str = "D_1") -> dict:
    """A thread whose comment connection is a FULL page with more behind it.

    Exactly what GitHub returns: min(totalCount, COMMENT_PAGE_SIZE) nodes,
    oldest first, and a totalCount for the whole thread.
    """
    page = list(machinery) + [
        comment(f"a human reply {i}", f"C_h{i}") for i in range(humans)
    ]
    page = page[:rm.COMMENT_PAGE_SIZE]
    node_doc = node(title, comments=page, node_id=node_id,
                    total_comments=rm.COMMENT_PAGE_SIZE + extra_total)
    return node_doc


class TruncatedThreadTests(unittest.TestCase):
    def test_the_page_size_constant_matches_the_query(self):
        """If the query asks for a different number than the code reasons
        about, a truncated thread reads as complete and the bug is back."""
        self.assertIn(f"comments(first: {rm.COMMENT_PAGE_SIZE})",
                      rm.DISCUSSIONS_QUERY)

    def test_a_short_thread_is_not_truncated(self):
        n = node("alpha/intro", comments=[watch_comment(0)], total_comments=3)
        self.assertFalse(rm.comments_truncated(n))
        self.assertEqual(rm.human_comment_count(n), 2)

    def test_a_full_page_with_more_behind_it_is_truncated(self):
        n = long_thread(humans=98, machinery=[watch_comment(0), signal_comment()],
                        extra_total=3)
        self.assertTrue(rm.comments_truncated(n))

    def test_machinery_past_the_page_is_not_counted_as_conversation(self):
        """The reviewer's proof case: 2 seed markers + 98 humans on the page,
        3 editorial notes appended behind it, totalCount 103. The old
        arithmetic published 101 humans where there were 98."""
        n = long_thread(humans=98, machinery=[watch_comment(0), signal_comment()],
                        extra_total=3)
        self.assertEqual(rm.machinery_comment_count(n), 2)
        self.assertIsNone(rm.human_comment_count(n),
                          "an unknowable human count must be null, never a guess")

    def test_the_snapshot_publishes_null_and_says_why(self):
        n = long_thread(humans=98, machinery=[watch_comment(4), signal_comment()],
                        extra_total=3)
        entry = rm.build_snapshot([n], {"alpha/intro"})["alpha/intro"]
        self.assertIsNone(entry["comments"])
        self.assertTrue(entry["comments_truncated"])
        # Everything read from an object we DID see is still published.
        self.assertEqual(entry["watched"], 4)

    def test_an_untruncated_entry_carries_no_truncation_key(self):
        """A flag that is always present is a field every reader must
        interpret, and it would rewrite every existing entry's bytes."""
        n = node("alpha/intro", comments=[watch_comment(1)], total_comments=2)
        entry = rm.build_snapshot([n], {"alpha/intro"})["alpha/intro"]
        self.assertNotIn("comments_truncated", entry)
        self.assertEqual(entry["comments"], 1)

    def test_the_published_count_is_null_not_zero(self):
        """null means 'not knowable from what we read'; 0 would mean 'read it,
        nobody replied' — on a 103-comment thread that is a lie."""
        n = long_thread(humans=98, machinery=[watch_comment(0), signal_comment()],
                        extra_total=3)
        entry = rm.build_snapshot([n], {"alpha/intro"})["alpha/intro"]
        self.assertIsNone(entry["comments"])
        self.assertNotEqual(entry["comments"], 0)


class TruncatedThreadEditorialTests(SilentWarnings):
    SUBJECTS = {"alpha/intro": {"record": {"id": "intro", "title": "Intro"}}}

    def test_a_missing_note_on_a_truncated_thread_is_not_appended(self):
        """The note may be sitting at position 101. Appending a second one
        writes a fresh machine comment into totalCount every night, and every
        one of them is counted as human conversation."""
        n = long_thread(humans=99, machinery=[watch_comment(0)], extra_total=5)
        self.assertIsNone(rm.editorial_comment_of(n))
        self.assertEqual(rm.editorial_targets([n], self.SUBJECTS), [])
        self.assertWarned("refusing to append")

    def test_a_stale_note_on_a_truncated_thread_is_still_updated(self):
        """Update-only, not do-nothing: an update is idempotent by id, so it
        is safe on a thread we have only partly read."""
        n = long_thread(
            humans=98,
            machinery=[editorial_comment(rm.EDITORIAL_MARKER + "\nold text", "C_old"),
                       watch_comment(0)],
            extra_total=5)
        targets = rm.editorial_targets([n], self.SUBJECTS)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["comment_id"], "C_old")

    def test_a_missing_note_on_a_short_thread_is_still_created(self):
        """The guard must not stop the lane working on ordinary threads."""
        targets = rm.editorial_targets([node("alpha/intro", node_id="D_7")],
                                       self.SUBJECTS)
        self.assertEqual(len(targets), 1)
        self.assertIsNone(targets[0]["comment_id"])


if __name__ == "__main__":
    unittest.main()
