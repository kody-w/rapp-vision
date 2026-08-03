#!/usr/bin/env python3
"""Offline unit tests for scripts/content_machine.py.

No network, no model, no GitHub API, no mocking of an API — every test drives
the shipped functions directly over in-memory documents and temp directories.

Run:
    python3 tests/test_content_machine.py
    python3 scripts/content_machine.py selftest      # same suite, in-process

Each test pins an invariant that would otherwise fail silently. If you add a
test, verify it by reintroducing the bug and confirming it goes red — a test
that re-implements the logic it checks cannot fail, and the doc that cites it
becomes false assurance.
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "content_machine", REPO_ROOT / "scripts" / "content_machine.py")
cm = importlib.util.module_from_spec(_spec)
sys.modules["content_machine"] = cm
_spec.loader.exec_module(cm)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def video(vid="v1", **kw):
    base = {
        "id": vid,
        "title": "A video",
        "description": "A description long enough to be a description and not a caption, "
                       "carrying a measured figure of 0.49% error so the proxy has something "
                       "concrete to find in it when it reads the text.",
        "published": "2026-08-01",
        "duration": 100.0,
        "tags": [],
        "thumb": "thumbs/v1.jpg",
        "sources": [{"src": "media/v1.mp4", "type": "video/mp4"},
                    {"src": "media/v1.webm", "type": "video/webm"}],
        "chapters": [],
    }
    base.update(kw)
    return base


def channel(cid="chan", videos=None, **kw):
    base = {"id": cid, "name": cid.title(), "tagline": "A tagline.",
            "videos": videos if videos is not None else [video()]}
    base.update(kw)
    return base


def network(channels, offline=None, registry_count=None):
    return {
        "channels": channels,
        "offline": offline or [],
        "registry_count": registry_count if registry_count is not None else len(channels),
    }


class ExplodingAdapter:
    id = "exploding/1.0.0"
    kind = "test"
    judgment = True
    needs_model = False

    def propose(self, gap, context):
        raise RuntimeError("boom")

    def review(self, v, rubric, context):
        raise RuntimeError("boom")


class FullAdapter:
    """A stand-in for a model adapter: scores every criterion."""
    id = "full-fake/1.0.0"
    kind = "model"
    judgment = True
    needs_model = True

    def __init__(self, value=4):
        self.value = value

    def propose(self, gap, context):
        return {"title": "t", "angle": "a", "format": "static", "outline": [], "why_now": ""}

    def review(self, v, rubric, context):
        return {"scores": {c["id"]: self.value for c in rubric["criteria"]},
                "notes": {c["id"]: "n" for c in rubric["criteria"]}}


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------


class TestIdentity(unittest.TestCase):
    def test_subject_id_is_channel_scoped(self):
        """A bare video id is only unique inside its own channel.json."""
        a = cm.subject_id("rock-tumbler", "my-first-video")
        b = cm.subject_id("field-notes", "my-first-video")
        self.assertEqual(a, "rock-tumbler/my-first-video")
        self.assertNotEqual(a, b)

    def test_template_collision_produces_distinct_subjects(self):
        """template/channel.json ships id 'my-first-video' and README says copy it."""
        net = network([channel("alpha", [video("my-first-video")]),
                       channel("beta", [video("my-first-video")])])
        subjects = [s for _, _, s in cm.flatten_videos(net)]
        self.assertEqual(len(subjects), 2)
        self.assertEqual(len(set(subjects)), 2)

    def test_norm_collapses_dashes_and_case(self):
        self.assertEqual(cm.norm("Rock-Tumbler Showcase"), "rock_tumbler_showcase")
        self.assertEqual(cm.norm("rock_tumbler_showcase"), "rock_tumbler_showcase")

    def test_stable_id_is_deterministic_and_distinct(self):
        one = cm.stable_id("channel_stale", "rock-tumbler", "2026-08-01")
        two = cm.stable_id("channel_stale", "rock-tumbler", "2026-08-01")
        three = cm.stable_id("channel_thin", "rock-tumbler", "2026-08-01")
        self.assertEqual(one, two)
        self.assertNotEqual(one, three)

    def test_content_hash_tracks_the_reviewed_fields(self):
        a = cm.content_hash(video())
        self.assertEqual(a, cm.content_hash(video()))
        self.assertNotEqual(a, cm.content_hash(video(description="different text")))
        self.assertNotEqual(a, cm.content_hash(video(title="different title")))
        # A field the rubric never reads must not churn the hash.
        self.assertEqual(a, cm.content_hash(video(width=1920)))


# --------------------------------------------------------------------------
# the publish guard
# --------------------------------------------------------------------------


class TestPublishGuard(unittest.TestCase):
    def test_write_json_refuses_to_write_outside_state(self):
        """The content machine proposes; it must not be able to publish."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            state.mkdir()
            with self.assertRaises(ValueError):
                cm.write_json(root / "channel.json", {"videos": []}, state)
            with self.assertRaises(ValueError):
                cm.write_json(root / "channels.json", {"channels": []}, state)
            self.assertFalse((root / "channel.json").exists())

    def test_write_json_writes_inside_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            self.assertTrue(cm.write_json(state / "x.json", {"a": 1}, state))
            self.assertEqual(json.loads((state / "x.json").read_text()), {"a": 1})

    def test_write_json_is_a_noop_when_bytes_are_identical(self):
        """No-op run must leave `git status --porcelain` empty, so no commit happens."""
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            payload = {"b": 2, "a": 1}
            self.assertTrue(cm.write_json(state / "x.json", payload, state))
            self.assertFalse(cm.write_json(state / "x.json", dict(payload), state))
            self.assertFalse(cm.write_json(state / "x.json", {"a": 1, "b": 2}, state))


class TestNoTimestamps(unittest.TestCase):
    def test_snapshots_carry_no_timestamp(self):
        """Git history is the time series. A timestamp forces a daily commit."""
        net = network([channel("chan")])
        adapter = cm.DryRunAdapter()
        props = cm.proposals_payload([], [], net, cm.DEFAULTS, adapter)
        reviews = cm.editorial_payload({}, cm.RUBRIC, net, adapter)
        for payload in (props, reviews):
            blob = cm.serialize(payload).lower()
            for banned in ("generated_at", "updated_at", "timestamp", "last_seen", "\"at\":"):
                self.assertNotIn(banned, blob, banned + " leaked into a snapshot")

    def test_stale_evidence_is_a_date_not_an_age(self):
        """`days_stale` would change every day and commit every day."""
        chan = channel("chan", [video(published="2026-01-01")])
        gaps = cm.detect_gaps(network([chan]), {}, cm.DEFAULTS, "2026-08-01")
        stale = [g for g in gaps if g["kind"] == "channel_stale"]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["evidence"]["newest_published"], "2026-01-01")
        self.assertNotIn("days_stale", stale[0]["evidence"])
        # Evidence must be identical whichever day the detector runs.
        later = cm.detect_gaps(network([chan]), {}, cm.DEFAULTS, "2026-12-25")
        self.assertEqual([g["evidence"] for g in later if g["kind"] == "channel_stale"],
                         [stale[0]["evidence"]])


# --------------------------------------------------------------------------
# gap detection
# --------------------------------------------------------------------------


class TestGapDetection(unittest.TestCase):
    def test_stale_fires_only_past_the_threshold(self):
        chan = channel("chan", [video(published="2026-07-01")])
        kinds = {g["kind"] for g in cm.detect_gaps(network([chan]), {}, cm.DEFAULTS, "2026-07-20")}
        self.assertNotIn("channel_stale", kinds)
        kinds = {g["kind"] for g in cm.detect_gaps(network([chan]), {}, cm.DEFAULTS, "2026-09-20")}
        self.assertIn("channel_stale", kinds)

    def test_thin_channel_fires_below_the_floor(self):
        chan = channel("chan", [video("a"), video("b")])
        gaps = [g for g in cm.detect_gaps(network([chan]), {}, cm.DEFAULTS, "2026-08-01")
                if g["kind"] == "channel_thin"]
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["evidence"]["entries"], 2)

    def test_unreachable_channel_produces_no_gaps(self):
        """Broken must never be indistinguishable from an honest empty state."""
        net = network([], offline=["chan: unreachable"], registry_count=1)
        self.assertEqual(cm.detect_gaps(net, {}, cm.DEFAULTS, "2026-08-01"), [])
        self.assertEqual(cm.detect_advisories(net, cm.DEFAULTS), [])

    def test_curriculum_module_without_an_episode(self):
        chan = channel("learn", [video("a", module="m1"), video("b", tags=["module:m2"])],
                       curriculum=[{"id": "m1", "title": "One"},
                                   {"id": "m2", "title": "Two"},
                                   {"id": "m3", "title": "Three", "goal": "Do the thing."}])
        gaps = [g for g in cm.detect_gaps(network([chan]), {}, cm.DEFAULTS, "2026-08-01")
                if g["kind"] == "curriculum_module_uncovered"]
        self.assertEqual([g["evidence"]["module_id"] for g in gaps], ["m3"])
        self.assertEqual(gaps[0]["evidence"]["module_goal"], "Do the thing.")

    def test_no_curriculum_declared_means_no_curriculum_gaps(self):
        chan = channel("chan", [video("a"), video("b"), video("c")])
        kinds = {g["kind"] for g in cm.detect_gaps(network([chan]), {}, cm.DEFAULTS, "2026-08-01")}
        self.assertNotIn("curriculum_module_uncovered", kinds)

    def test_signal_gaps_fire_at_the_threshold_and_not_below(self):
        """Uses the CANONICAL names rapp_metrics.py actually publishes.

        REGRESSION: this file once looked for "confused"/"want_more" while the
        metrics lane published "confusing"/"want_more_like_this". Every
        signal-driven gap was dead and it looked like a quiet week. Feeding the
        canonical names here is what makes that bug go red.
        """
        chan = channel("chan", [video("a"), video("b"), video("c")])
        net = network([chan])
        below = cm.index_signals({"videos": {"chan/a": {"signals": {"confusing": 1}}}})
        kinds = {g["kind"] for g in cm.detect_gaps(net, below, cm.DEFAULTS, "2026-08-01")}
        self.assertNotIn("viewers_confused", kinds)
        at = cm.index_signals({"videos": {"chan/a": {
            "signals": {"confusing": 2, "want_more_like_this": 3}}}})
        gaps = cm.detect_gaps(net, at, cm.DEFAULTS, "2026-08-01")
        kinds = {g["kind"] for g in gaps}
        self.assertIn("viewers_confused", kinds)
        self.assertIn("viewers_want_more", kinds)
        subj = [g["subject"] for g in gaps if g["kind"] == "viewers_confused"]
        self.assertEqual(subj, ["chan/a"])

    def test_a_real_metrics_snapshot_shape_drives_the_detector(self):
        """End to end on the exact shape scripts/rapp_metrics.py writes.

        build_snapshot() emits {"videos": {"<chan>/<vid>": {..., "signals": {...}}}}
        with every channel present and zeroed. This asserts the whole path —
        snapshot shape, vocabulary, threshold — not just one helper.
        """
        snapshot = {
            "schema": "rapp-vision-metrics/1.0",
            "signal_channels": {"CONFUSED": "confusing", "HEART": "want_more_like_this"},
            "videos": {
                "chan/a": {
                    "channel": "chan", "video": "a", "upvotes": 3, "watched": 9,
                    "score": 15, "comments": 1,
                    "signals": {"watched_it_all": 9, "learned_something": 2,
                                "want_more_like_this": 4, "tried_it_myself": 0,
                                "saved_for_later": 1, "too_long": 0, "confusing": 3},
                },
            },
        }
        idx = cm.index_signals(snapshot)
        gaps = cm.detect_gaps(network([channel("chan", [video("a")])]),
                              idx, cm.DEFAULTS, "2026-08-01")
        by_kind = {g["kind"]: g for g in gaps}
        self.assertIn("viewers_confused", by_kind)
        self.assertIn("viewers_want_more", by_kind)
        self.assertEqual(by_kind["viewers_confused"]["evidence"]["signal"], "confusing")
        self.assertEqual(by_kind["viewers_confused"]["evidence"]["count"], 3)
        self.assertEqual(by_kind["viewers_want_more"]["evidence"]["signal"],
                         "want_more_like_this")

    def test_an_all_zero_signal_block_fires_nothing(self):
        """A provisioned surface nobody answered is zeros, not silence."""
        zeros = {n: 0 for n in cm.CANONICAL_SIGNALS}
        idx = cm.index_signals({"videos": {"chan/a": {"signals": zeros}}})
        self.assertEqual(cm.signals_for(idx, "chan/a"), zeros)
        gaps = cm.detect_gaps(network([channel("chan", [video("a")])]),
                              idx, cm.DEFAULTS, "2026-08-01")
        self.assertEqual([g for g in gaps if g["kind"].startswith("viewers_")], [])

    def test_missing_signals_never_look_like_zero_signals(self):
        chan = channel("chan", [video("a"), video("b"), video("c")])
        gaps = cm.detect_gaps(network([chan]), {}, cm.DEFAULTS, "2026-08-01")
        self.assertEqual([g for g in gaps if g["kind"].startswith("viewers_")], [])


class TestAdvisories(unittest.TestCase):
    def test_missing_webm_is_flagged(self):
        chan = channel("chan", [video("a", sources=[{"src": "media/a.mp4", "type": "video/mp4"}])])
        kinds = {a["kind"] for a in cm.detect_advisories(network([chan]), cm.DEFAULTS)}
        self.assertIn("missing_webm", kinds)

    def test_webm_present_is_not_flagged(self):
        kinds = {a["kind"] for a in cm.detect_advisories(network([channel("chan")]), cm.DEFAULTS)}
        self.assertNotIn("missing_webm", kinds)

    def test_live_entry_without_chapters_is_not_flagged(self):
        live = video("a", sources=[], duration=400, chapters=[],
                     live={"scenes": [{"t": 0, "dur": 400, "app": "../x.html"}]})
        kinds = {a["kind"] for a in cm.detect_advisories(network([channel("chan", [live])]), cm.DEFAULTS)}
        self.assertNotIn("missing_chapters", kinds)
        self.assertNotIn("missing_webm", kinds)

    def test_long_static_entry_without_chapters_is_flagged(self):
        chan = channel("chan", [video("a", duration=400, chapters=[])])
        kinds = {a["kind"] for a in cm.detect_advisories(network([chan]), cm.DEFAULTS)}
        self.assertIn("missing_chapters", kinds)


# --------------------------------------------------------------------------
# signal normalization
# --------------------------------------------------------------------------


class TestSignalIndex(unittest.TestCase):
    def test_accepts_nested_and_flat_shapes(self):
        nested = cm.index_signals({"videos": {"chan/a": {"signals": {"confusing": 3}}}})
        flat = cm.index_signals({"video_metrics": {"chan/a": {"confusing": 3}}})
        self.assertEqual(cm.signals_for(nested, "chan/a"), {"confusing": 3})
        self.assertEqual(cm.signals_for(flat, "chan/a"), {"confusing": 3})

    def test_key_normalization_bridges_dashes_and_underscores(self):
        idx = cm.index_signals(
            {"subjects": {"Rock-Tumbler/Rock Tumbler Short": {"want_more_like_this": 5}}})
        self.assertEqual(cm.signals_for(idx, "rock_tumbler/rock_tumbler_short"),
                         {"want_more_like_this": 5})

    def test_unrecognised_shape_yields_no_signal_not_zero_signal(self):
        self.assertEqual(cm.index_signals({"something_else": 1}), {})
        self.assertEqual(cm.index_signals(None), {})
        self.assertEqual(cm.index_signals([]), {})

    def test_booleans_and_strings_are_not_counts(self):
        idx = cm.index_signals(
            {"videos": {"chan/a": {"confusing": True, "want_more_like_this": "many"}}})
        self.assertEqual(cm.signals_for(idx, "chan/a"), {})

    def test_a_snapshot_declaring_its_own_vocabulary_is_believed(self):
        """metrics.json publishes `signal_channels`. Read it rather than guess.

        A name this script has never heard of is still indexed when the
        snapshot declares it, so a rename by the metrics owner degrades to
        "the role stops resolving" instead of "the whole record vanishes".
        """
        doc = {"signal_channels": {"CONFUSED": "baffling"},
               "videos": {"chan/a": {"signals": {"baffling": 7}}}}
        self.assertEqual(cm.declared_signal_names(doc), ("baffling",))
        self.assertEqual(cm.signals_for(cm.index_signals(doc), "chan/a"), {"baffling": 7})

    def test_signal_of_distinguishes_absent_from_zero(self):
        """(None, 0) means no such counter. (name, 0) means it exists and reads zero."""
        self.assertEqual(cm.signal_of({}, "confusion"), (None, 0))
        self.assertEqual(cm.signal_of({"confusing": 0}, "confusion"), ("confusing", 0))
        self.assertEqual(cm.signal_of({"confusing": 4}, "confusion"), ("confusing", 4))

    def test_signal_of_prefers_the_canonical_name_over_an_alias(self):
        both = {"confusing": 9, "confused": 1}
        self.assertEqual(cm.signal_of(both, "confusion"), ("confusing", 9))

    def test_legacy_alias_is_still_read(self):
        """Read tolerance for an older snapshot — politeness, not a rename."""
        self.assertEqual(cm.signal_of({"confused": 2}, "confusion"), ("confused", 2))


class TestSignalVocabularyContract(unittest.TestCase):
    """THE CROSS-WRITER CONTRACT.

    scripts/rapp_metrics.py owns the signal vocabulary; this script only reads
    it. These tests import that file and confront its real constants. They are
    the only tests here that can catch a rename, because every other test in
    this file is written against names this file chose — and a test written
    against your own constant agrees with you no matter how wrong you both are.

    If rapp_metrics.py is not present (someone vendored this script alone),
    they SKIP rather than fail: an absent contract is not a violated one. A
    skip is visible in the runner output; a silent pass would not be.
    """

    def setUp(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import rapp_metrics                                # noqa: PLC0415
        except Exception as exc:                               # noqa: BLE001
            self.skipTest("rapp_metrics not importable: {}".format(exc))
        self.rm = rapp_metrics

    def test_canonical_signals_match_the_metrics_lane_exactly(self):
        published = set(self.rm.SIGNAL_MAP.values())
        self.assertEqual(
            set(cm.CANONICAL_SIGNALS), published,
            "content_machine.CANONICAL_SIGNALS has drifted from "
            "rapp_metrics.SIGNAL_MAP. A name only one side knows reads as zero "
            "forever and looks exactly like nobody reacted.")

    def test_every_role_resolves_against_a_real_published_counter(self):
        published = set(self.rm.SIGNAL_MAP.values())
        for role, names in cm.SIGNAL_ROLES.items():
            self.assertIn(names[0], published,
                          "role '{}' resolves first to '{}', which the metrics "
                          "lane does not publish".format(role, names[0]))

    def test_the_two_gap_driving_roles_are_the_named_negatives_and_the_ask(self):
        """`confusing` is a named negative over there; it must stay readable."""
        self.assertIn(cm.SIGNAL_ROLES["confusion"][0], set(self.rm.NEGATIVE_SIGNALS))
        self.assertIn(cm.SIGNAL_ROLES["want_more"][0], set(self.rm.SIGNAL_MAP.values()))

    def test_an_empty_signal_block_from_the_real_lane_indexes_cleanly(self):
        """rapp_metrics.empty_signals() is the shape every unanswered video has."""
        idx = cm.index_signals({"videos": {"chan/a": {"signals": self.rm.empty_signals()}}})
        got = cm.signals_for(idx, "chan/a")
        self.assertEqual(set(got), set(self.rm.SIGNAL_MAP.values()))
        self.assertEqual(set(got.values()), {0})


# --------------------------------------------------------------------------
# proposal queue semantics
# --------------------------------------------------------------------------


class TestProposalMerge(unittest.TestCase):
    def setUp(self):
        self.chan = channel("chan", [video("a", published="2026-01-01")])
        self.net = network([self.chan])
        self.adapter = cm.DryRunAdapter()
        self.fresh = cm.build_proposals(self.net, {}, cm.DEFAULTS, self.adapter, "2026-08-01")

    def test_human_fields_survive_a_rerun(self):
        triaged = dict(self.fresh[0])
        triaged["status"] = "accepted"
        triaged["notes"] = "Kody: film this after the offsite."
        triaged["assignee"] = "kody"
        triaged["proposal"] = {"title": "A title I wrote myself"}
        merged = cm.merge_proposals([triaged], self.fresh, {"chan"})
        found = [m for m in merged if m["id"] == triaged["id"]][0]
        self.assertEqual(found["status"], "accepted")
        self.assertEqual(found["notes"], "Kody: film this after the offsite.")
        self.assertEqual(found["assignee"], "kody")
        self.assertEqual(found["proposal"], {"title": "A title I wrote myself"})

    def test_machine_fields_are_refreshed(self):
        stale_record = dict(self.fresh[0])
        stale_record["evidence"] = {"newest_published": "1999-01-01"}
        merged = cm.merge_proposals([stale_record], self.fresh, {"chan"})
        found = [m for m in merged if m["id"] == stale_record["id"]][0]
        self.assertEqual(found["evidence"], self.fresh[0]["evidence"])

    def test_nothing_is_ever_deleted(self):
        orphan = {"id": "deadbeef0001", "kind": "channel_stale", "channel": "chan",
                  "subject": "chan", "status": "rejected", "evidence": {}}
        merged = cm.merge_proposals([orphan], self.fresh, {"chan"})
        found = [m for m in merged if m["id"] == "deadbeef0001"][0]
        self.assertEqual(found["status"], "rejected")
        self.assertTrue(found["gap_closed"])

    def test_an_unreachable_channel_closes_nothing(self):
        """One 404 must not silently retire a channel's whole queue."""
        orphan = {"id": "deadbeef0002", "kind": "channel_stale", "channel": "offline-chan",
                  "subject": "offline-chan", "status": "proposed", "evidence": {},
                  "gap_closed": False}
        merged = cm.merge_proposals([orphan], self.fresh, {"chan"})
        found = [m for m in merged if m["id"] == "deadbeef0002"][0]
        self.assertFalse(found["gap_closed"])

    def test_rerun_is_idempotent(self):
        once = cm.merge_proposals([], self.fresh, {"chan"})
        twice = cm.merge_proposals(once, self.fresh, {"chan"})
        self.assertEqual(cm.serialize({"p": once}), cm.serialize({"p": twice}))

    def test_generated_proposals_are_marked_non_judgment(self):
        self.assertFalse(self.fresh[0]["generated_by"]["judgment"])
        self.assertEqual(self.fresh[0]["generated_by"]["adapter"], cm.DryRunAdapter.id)

    def test_a_failing_adapter_skips_the_gap_and_does_not_raise(self):
        out = cm.build_proposals(self.net, {}, cm.DEFAULTS, ExplodingAdapter(), "2026-08-01")
        self.assertEqual(out, [])


# --------------------------------------------------------------------------
# the rubric itself
# --------------------------------------------------------------------------


class TestRubric(unittest.TestCase):
    def test_rubric_is_data_and_versioned(self):
        self.assertIsInstance(cm.RUBRIC, dict)
        self.assertRegex(cm.RUBRIC["version"], r"^\d+\.\d+\.\d+$")
        self.assertTrue(cm.RUBRIC["criteria"])

    def test_the_five_named_criteria_are_present(self):
        ids = [c["id"] for c in cm.RUBRIC["criteria"]]
        for expected in ("clarity", "accuracy", "pacing",
                         "description_stands_alone", "honest_confidence"):
            self.assertIn(expected, ids)

    def test_criterion_ids_are_unique_and_fully_specified(self):
        ids = [c["id"] for c in cm.RUBRIC["criteria"]]
        self.assertEqual(len(ids), len(set(ids)))
        for crit in cm.RUBRIC["criteria"]:
            self.assertGreater(crit["weight"], 0)
            self.assertIn("question", crit)
            self.assertEqual(set(crit["anchors"]), {"1", "3", "5"})
            self.assertIsInstance(crit["machine_checkable"], bool)

    def test_hard_flags_reference_real_criteria(self):
        ids = {c["id"] for c in cm.RUBRIC["criteria"]}
        for flag in cm.RUBRIC["hard_flags"]:
            self.assertIn(flag["criterion"], ids)
            self.assertLessEqual(flag["at_most"], cm.RUBRIC["scale"]["max"])

    def test_unknown_is_null_not_zero(self):
        self.assertIsNone(cm.RUBRIC["scale"]["unknown"])
        self.assertEqual(cm.RUBRIC["scale"]["min"], 1)


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


class TestScoring(unittest.TestCase):
    def test_composite_requires_full_coverage(self):
        partial = {c["id"]: None for c in cm.RUBRIC["criteria"]}
        partial["description_stands_alone"] = 5
        comp, part, scored = cm.composite(partial, cm.RUBRIC)
        self.assertIsNone(comp)
        self.assertEqual(part, 5.0)
        self.assertEqual(scored, ["description_stands_alone"])

    def test_composite_is_published_when_everything_is_scored(self):
        full = {c["id"]: 4 for c in cm.RUBRIC["criteria"]}
        comp, part, scored = cm.composite(full, cm.RUBRIC)
        self.assertEqual(comp, 4.0)
        self.assertIsNone(part)
        self.assertEqual(len(scored), len(cm.RUBRIC["criteria"]))

    def test_weights_are_actually_applied(self):
        scores = {c["id"]: 5 for c in cm.RUBRIC["criteria"]}
        scores["accuracy"] = 1                      # weight 1.5
        weighted, _, _ = cm.composite(scores, cm.RUBRIC)
        flat = sum(5 for _ in cm.RUBRIC["criteria"])
        self.assertLess(weighted, (flat - 4) / len(cm.RUBRIC["criteria"]))

    def test_no_scores_at_all_yields_no_number(self):
        empty = {c["id"]: None for c in cm.RUBRIC["criteria"]}
        self.assertEqual(cm.composite(empty, cm.RUBRIC), (None, None, []))

    def test_flags_fire_on_partial_coverage(self):
        scores = {c["id"]: None for c in cm.RUBRIC["criteria"]}
        scores["description_stands_alone"] = 1
        self.assertEqual(cm.evaluate_flags(scores, cm.RUBRIC), ["orphan_description"])

    def test_null_never_trips_a_flag(self):
        scores = {c["id"]: None for c in cm.RUBRIC["criteria"]}
        self.assertEqual(cm.evaluate_flags(scores, cm.RUBRIC), [])


class TestDryRunReviewer(unittest.TestCase):
    def setUp(self):
        self.adapter = cm.DryRunAdapter()
        self.chan = channel("chan")

    def test_needs_no_model_and_is_not_a_judgment(self):
        self.assertFalse(self.adapter.needs_model)
        self.assertFalse(self.adapter.judgment)
        self.assertEqual(self.adapter.kind, "structural")

    def test_unjudgeable_criteria_come_back_null_not_zero(self):
        rec = cm.review_video(self.chan, video(), self.adapter, cm.RUBRIC)
        for cid in ("clarity", "accuracy", "pacing"):
            self.assertIsNone(rec["scores"][cid], cid + " must be null, never a guess")
        self.assertNotIn(0, [v for v in rec["scores"].values() if v is not None])

    def test_it_publishes_no_composite(self):
        rec = cm.review_video(self.chan, video(), self.adapter, cm.RUBRIC)
        self.assertIsNone(rec["composite"])
        self.assertIsNotNone(rec["partial_composite"])
        self.assertEqual(rec["coverage"], "2/5")

    def test_empty_description_scores_the_floor_and_flags(self):
        rec = cm.review_video(self.chan, video(description=""), self.adapter, cm.RUBRIC)
        self.assertEqual(rec["scores"]["description_stands_alone"], 1)
        self.assertIn("orphan_description", rec["flags"])
        self.assertIsNone(rec["scores"]["honest_confidence"])

    def test_unhedged_absolutes_without_grounding_are_flagged(self):
        v = video(description="This app is perfect and bug-free. It is the best there is, "
                              "and it always works on every machine you will ever own here.")
        rec = cm.review_video(self.chan, v, self.adapter, cm.RUBRIC)
        self.assertEqual(rec["scores"]["honest_confidence"], 1)
        self.assertIn("overclaim_risk", rec["flags"])

    def test_a_grounded_description_scores_well(self):
        rec = cm.review_video(self.chan, video(), self.adapter, cm.RUBRIC)
        self.assertGreaterEqual(rec["scores"]["honest_confidence"], 4)
        self.assertGreaterEqual(rec["scores"]["description_stands_alone"], 4)

    # -- the proxy against adversarial text --------------------------------
    #
    # honest_confidence is the heaviest criterion (weight 1.5), it drives the
    # overclaim_risk hard flag, and it is one of only two criteria the dry-run
    # adapter scores — so it is most of the published partial_composite. It
    # used to match its marker lists as BARE SUBSTRINGS, which made it wrong
    # in both directions on ordinary English. Each case below is a real
    # sentence that scored wrongly before the markers were anchored on word
    # boundaries; each one goes red again if the anchoring is removed.

    def _confidence(self, description):
        rec = cm.review_video(self.chan, video(description=description),
                              self.adapter, cm.RUBRIC)
        return rec["scores"]["honest_confidence"], rec["notes"]["honest_confidence"]

    def test_disclaiming_perfection_is_not_an_absolute(self):
        """'imperfect' contains 'perfect'. Scoring a sentence that DENIES
        perfection as an overclaim inverts the criterion completely."""
        score, note = self._confidence(
            "This capture is imperfect and the pacing drifts. I have not measured the drift.")
        self.assertGreaterEqual(score, 4)
        self.assertNotIn("perfect", note.split("markers")[0])
        self.assertNotIn("overclaim_risk", cm.evaluate_flags(
            {"honest_confidence": score}, cm.RUBRIC))

    def test_ordinary_words_containing_a_unit_do_not_ground_anything(self):
        """'problems', 'forms' and 'items' all contain 'ms'. A description
        with zero measurements in it must not read as grounded."""
        score, note = self._confidence(
            "The build has problems and the forms are janky; several items still "
            "crash when you resize the window mid-render and nothing recovers.")
        self.assertEqual(score, 3)
        self.assertIn("nothing grounding", note)

    def test_the_word_claims_does_not_count_as_grounding_a_claim(self):
        """'claims' contains 'ms'. Making a claim cannot be what grounds it."""
        score, note = self._confidence(
            "A short honest note about the workflow with no strong claims at all "
            "whatsoever here.")
        self.assertEqual(score, 3)
        self.assertIn("nothing grounding", note)

    def test_a_real_magnitude_with_a_unit_still_grounds(self):
        """The fix must not cost the proxy its actual job."""
        score, note = self._confidence(
            "Frame time held at 12 ms across the run and the drop count was zero; "
            "verified on two machines before this was published anywhere.")
        self.assertEqual(score, 5)
        self.assertIn("12 ms", note)
        self.assertIn("verified", note)

    def test_a_naked_unit_word_is_not_a_measurement(self):
        """'seconds' with no number in front of it measures nothing."""
        score, _ = self._confidence(
            "It takes seconds to set up and the whole flow feels quick once you "
            "have the window open and the panel docked on the right hand side.")
        self.assertEqual(score, 3)

    def test_markers_that_are_not_words_still_match(self):
        """'100%' ends in a non-word character, so a naive \\b on both sides
        would stop matching it. It is an absolute and must stay one."""
        self.assertEqual(cm.absolute_markers_in("this is 100% reliable"), ["100%"])
        self.assertEqual(cm.absolute_markers_in("a bug-free build"), ["bug-free"])

    def test_unverified_is_its_own_marker_and_not_a_verified_match(self):
        self.assertEqual(cm.grounding_markers_in("this number is unverified"),
                         ["unverified"])

    def test_the_record_carries_reviewer_and_rubric_version(self):
        rec = cm.review_video(self.chan, video(), self.adapter, cm.RUBRIC)
        self.assertEqual(rec["reviewer"]["id"], cm.DryRunAdapter.id)
        self.assertEqual(rec["rubric"]["version"], cm.RUBRIC["version"])
        self.assertEqual(rec["subject"], "chan/v1")

    def test_out_of_range_adapter_scores_are_clamped(self):
        class Wild(FullAdapter):
            def review(self, v, rubric, context):
                return {"scores": {c["id"]: 99 for c in rubric["criteria"]}, "notes": {}}
        rec = cm.review_video(self.chan, video(), Wild(), cm.RUBRIC)
        self.assertEqual(set(rec["scores"].values()), {5})

    def test_non_numeric_adapter_scores_become_null(self):
        class Wordy(FullAdapter):
            def review(self, v, rubric, context):
                return {"scores": {c["id"]: "good" for c in rubric["criteria"]}, "notes": {}}
        rec = cm.review_video(self.chan, video(), Wordy(), cm.RUBRIC)
        self.assertEqual(set(rec["scores"].values()), {None})
        self.assertIsNone(rec["composite"])


class TestReviewSkipping(unittest.TestCase):
    def test_identical_work_is_not_redone(self):
        adapter = cm.DryRunAdapter()
        rec = cm.review_video(channel("chan"), video(), adapter, cm.RUBRIC)
        self.assertFalse(cm.needs_review(rec, video(), adapter, cm.RUBRIC))

    def test_changed_content_is_rereviewed(self):
        adapter = cm.DryRunAdapter()
        rec = cm.review_video(channel("chan"), video(), adapter, cm.RUBRIC)
        self.assertTrue(cm.needs_review(rec, video(description="new words entirely"), adapter, cm.RUBRIC))

    def test_a_rubric_bump_rereviews_everything(self):
        adapter = cm.DryRunAdapter()
        rec = cm.review_video(channel("chan"), video(), adapter, cm.RUBRIC)
        bumped = json.loads(json.dumps(cm.RUBRIC))
        bumped["version"] = "1.1.0"
        self.assertTrue(cm.needs_review(rec, video(), adapter, bumped))

    def test_a_different_reviewer_rereviews(self):
        rec = cm.review_video(channel("chan"), video(), cm.DryRunAdapter(), cm.RUBRIC)
        self.assertTrue(cm.needs_review(rec, video(), FullAdapter(), cm.RUBRIC))

    def test_missing_prior_review_is_reviewed(self):
        self.assertTrue(cm.needs_review(None, video(), cm.DryRunAdapter(), cm.RUBRIC))


# --------------------------------------------------------------------------
# the editorial lane
# --------------------------------------------------------------------------


class TestEditorialLane(unittest.TestCase):
    def test_payload_marks_the_lane_and_forbids_summing(self):
        payload = cm.editorial_payload({}, cm.RUBRIC, network([]), cm.DryRunAdapter())
        self.assertEqual(payload["lane"], "editorial")
        self.assertIn("human_counters", payload["never_sum_into"])
        self.assertIn("never be summed", payload["note"])

    def test_structural_and_judgment_reviews_are_counted_separately(self):
        chan = channel("chan")
        structural = cm.review_video(chan, video("a"), cm.DryRunAdapter(), cm.RUBRIC)
        judged = cm.review_video(chan, video("b"), FullAdapter(), cm.RUBRIC)
        payload = cm.editorial_payload({"chan/a": structural, "chan/b": judged},
                                       cm.RUBRIC, network([chan]), cm.DryRunAdapter())
        self.assertEqual(payload["totals"]["judgment_reviews"], 1)
        self.assertEqual(payload["totals"]["structural_reviews"], 1)

    def test_the_lane_resolves_and_reports_how_it_bound(self):
        lane = cm.editorial_lane(REPO_ROOT / "state")
        self.assertTrue(lane.writer is None or callable(lane.writer))
        self.assertIsInstance(lane.binding, str)
        self.assertTrue(lane.marker.strip())
        self.assertIsInstance(lane.as_dict()["machinery_exclusion_verified"], bool)

    def test_the_payload_publishes_whether_the_binding_was_verified(self):
        """An unverified binding must be visible in the artifact, not just on stderr."""
        payload = cm.editorial_payload({}, cm.RUBRIC, network([]), cm.DryRunAdapter())
        self.assertIn("lane_binding", payload)
        self.assertIn("machinery_exclusion_verified", payload["lane_binding"])
        self.assertIn("marker", payload["lane_binding"])

    def test_a_broken_machinery_exclusion_is_reported_not_swallowed(self):
        """If the marker ever leaves MACHINERY_MARKERS, a posted review would be
        counted as human conversation. That must go loud, and must NOT raise."""
        class FakeMetrics:
            EDITORIAL_MARKER = "<!-- x -->"
            MACHINERY_MARKERS = ("<!-- something-else -->",)
            EDITORIAL_NOTE = "note"
        sys.modules["rapp_metrics"] = FakeMetrics
        try:
            lane = cm.editorial_lane(REPO_ROOT / "state")
            self.assertFalse(lane.verified)
            self.assertTrue(lane.problems)
            self.assertIn("MACHINERY_MARKERS", " ".join(lane.problems))
        finally:
            sys.modules.pop("rapp_metrics", None)

    def test_an_unimportable_metrics_module_degrades_instead_of_raising(self):
        class Exploding:
            def __getattr__(self, name):
                raise RuntimeError("boom")
        sys.modules["rapp_metrics"] = Exploding()
        try:
            lane = cm.editorial_lane(REPO_ROOT / "state")
            self.assertFalse(lane.verified)
            self.assertTrue(lane.marker.strip())
        finally:
            sys.modules.pop("rapp_metrics", None)

    def test_a_rendered_lane_comment_carries_the_marker_first(self):
        """The marker is what makes rapp_metrics subtract this from the human
        comment count. If it is not in the body, the review inflates a
        conversation count merely by existing."""
        lane = cm.editorial_lane(REPO_ROOT / "state")
        rec = cm.review_video(channel("chan"), video(), cm.DryRunAdapter(), cm.RUBRIC)
        body = cm.render_lane_comment("chan/v1", rec, lane)
        self.assertTrue(body.startswith(lane.marker))
        self.assertIn("machine-written", body.lower())
        self.assertIn(cm.DryRunAdapter.id, body)
        self.assertIn(cm.RUBRIC["version"], body)

    def test_a_null_score_renders_as_an_em_dash_never_as_zero(self):
        """'could not judge' and 'scored zero' are different claims."""
        lane = cm.editorial_lane(REPO_ROOT / "state")
        rec = cm.review_video(channel("chan"), video(), cm.DryRunAdapter(), cm.RUBRIC)
        self.assertIsNone(rec["scores"]["clarity"])
        body = cm.render_lane_comment("chan/v1", rec, lane)
        self.assertIn("| Clarity | — |", body)
        self.assertNotIn("| Clarity | 0/5 |", body)
        self.assertIn("not published", body)      # no composite on partial coverage

    def test_the_lane_comment_is_byte_stable_for_an_unchanged_review(self):
        lane = cm.editorial_lane(REPO_ROOT / "state")
        rec = cm.review_video(channel("chan"), video(), cm.DryRunAdapter(), cm.RUBRIC)
        self.assertEqual(cm.render_lane_comment("chan/v1", rec, lane),
                         cm.render_lane_comment("chan/v1", rec, lane))


class TestLaneSeparation(unittest.TestCase):
    """THE FOUNDING TENET: the ACTOR determines the lane, never the SUBJECT.

    An automated actor never contributes to a human counter. What it reviewed
    is irrelevant — agent-authored content is a first-class citizen that earns
    real human numbers, and only agent-authored ACTIONS are quarantined.
    """

    def test_no_review_field_is_named_like_a_human_counter(self):
        rec = cm.review_video(channel("chan"), video(), cm.DryRunAdapter(), cm.RUBRIC)
        banned = ("upvotes", "watched", "comments", "views", "reactions",
                  "endorsements", "score", "signals")
        for key in rec:
            self.assertNotIn(key, banned,
                             "'{}' reads as a human counter inside a machine "
                             "review record".format(key))

    def test_the_review_snapshot_shares_no_key_with_the_metrics_snapshot(self):
        """Two files that both carry `videos: {...}` invite a careless merge."""
        payload = cm.editorial_payload({}, cm.RUBRIC, network([]), cm.DryRunAdapter())
        for banned in ("videos", "totals_human", "upvotes", "watched"):
            self.assertNotIn(banned, payload)

    def test_reviewing_agent_authored_content_is_not_special_cased(self):
        """Quarantining by SUBJECT would make agent-generated content
        unmeasurable. The rubric must treat it identically."""
        human_made = video("h", description="A hand-cut episode about a rock tumbler "
                                            "measured at 0.49% error across 40 runs today.")
        agent_made = dict(human_made, id="a", generated_by="some-agent/1.0")
        h = cm.review_video(channel("chan"), human_made, cm.DryRunAdapter(), cm.RUBRIC)
        a = cm.review_video(channel("chan"), agent_made, cm.DryRunAdapter(), cm.RUBRIC)
        self.assertEqual(h["scores"], a["scores"])
        self.assertEqual(h["flags"], a["flags"])

    def test_every_review_carries_reviewer_id_and_rubric_version(self):
        """Attribution is not optional: it is what makes the lane auditable."""
        rec = cm.review_video(channel("chan"), video(), cm.DryRunAdapter(), cm.RUBRIC)
        self.assertTrue(rec["reviewer"]["id"])
        self.assertTrue(rec["rubric"]["version"])
        self.assertIn("judgment", rec["reviewer"])


# --------------------------------------------------------------------------
# adapter loading — the credit guard
# --------------------------------------------------------------------------


class TestAdapterLoading(unittest.TestCase):
    def test_default_is_dry_run(self):
        adapter, why = cm.load_adapter("dryrun", allow_model=False)
        self.assertIsInstance(adapter, cm.DryRunAdapter)
        self.assertIsNone(why)

    def test_a_model_adapter_is_refused_without_allow_model(self):
        sys.modules["_fake_adapter_mod"] = type(sys)("_fake_adapter_mod")
        sys.modules["_fake_adapter_mod"].make = lambda: FullAdapter()
        adapter, why = cm.load_adapter("_fake_adapter_mod:make", allow_model=False)
        self.assertIsInstance(adapter, cm.DryRunAdapter)
        self.assertIn("allow-model", why)

    def test_a_model_adapter_is_accepted_with_allow_model(self):
        sys.modules["_fake_adapter_mod2"] = type(sys)("_fake_adapter_mod2")
        sys.modules["_fake_adapter_mod2"].make = lambda: FullAdapter()
        adapter, why = cm.load_adapter("_fake_adapter_mod2:make", allow_model=True)
        self.assertIsInstance(adapter, FullAdapter)
        self.assertIsNone(why)

    def test_a_broken_spec_falls_back_instead_of_crashing(self):
        for spec in ("nope", "no.such.module:make", "sys:not_a_thing"):
            adapter, why = cm.load_adapter(spec, allow_model=True)
            self.assertIsInstance(adapter, cm.DryRunAdapter, spec)
            self.assertTrue(why)

    def test_an_adapter_missing_the_interface_is_refused(self):
        sys.modules["_fake_adapter_mod3"] = type(sys)("_fake_adapter_mod3")
        sys.modules["_fake_adapter_mod3"].make = lambda: object()
        adapter, why = cm.load_adapter("_fake_adapter_mod3:make", allow_model=True)
        self.assertIsInstance(adapter, cm.DryRunAdapter)
        self.assertIn("lacks", why)


# --------------------------------------------------------------------------
# channel resolution
# --------------------------------------------------------------------------


class TestChannelResolution(unittest.TestCase):
    def test_local_file_wins_when_the_sibling_is_cloned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "channel.json").write_text("{}")
            kind, where = cm.resolve_channel_source("channel.json", root, "https://x/", False)
            self.assertEqual(kind, "file")
            self.assertTrue(where.endswith("channel.json"))

    def test_missing_sibling_falls_through_to_the_published_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "rapp-vision"
            root.mkdir()
            kind, where = cm.resolve_channel_source(
                "../localFirstTools/rappvision/channel.json", root,
                "https://kody-w.github.io/rapp-vision/", False)
            self.assertEqual(kind, "url")
            self.assertEqual(where, "https://kody-w.github.io/localFirstTools/rappvision/channel.json")

    def test_offline_never_reaches_the_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(cm.resolve_channel_source("https://x/c.json", root, "", True)[0],
                             "unreachable")
            self.assertEqual(cm.resolve_channel_source("../gone/c.json", root, "https://x/", True)[0],
                             "unreachable")

    def test_the_id_inside_the_file_wins_over_the_registry_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "c.json").write_text(json.dumps({"id": "real-id", "videos": []}))
            chan, err = cm.load_channel({"id": "custom-12345", "url": "c.json"}, root, "", True)
            self.assertIsNone(err)
            self.assertEqual(chan["id"], "real-id")
            self.assertEqual(chan["_registry_id"], "custom-12345")

    def test_a_malformed_channel_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "c.json").write_text("{not json")
            chan, err = cm.load_channel({"id": "x", "url": "c.json"}, root, "", True)
            self.assertIsNone(chan)
            self.assertIn("x", err)

    def test_non_dict_videos_are_dropped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "c.json").write_text(json.dumps({"id": "x", "videos": ["oops", {"id": "ok"}]}))
            chan, err = cm.load_channel({"id": "x", "url": "c.json"}, root, "", True)
            self.assertIsNone(err)
            self.assertEqual([v["id"] for v in chan["videos"]], ["ok"])


# --------------------------------------------------------------------------
# end to end, offline
# --------------------------------------------------------------------------


def build_fixture_repo(tmp: Path) -> Path:
    root = tmp / "repo"
    (root / "state").mkdir(parents=True)
    (root / "channels.json").write_text(json.dumps({
        "channels": [
            {"id": "chan", "url": "channel.json"},
            {"id": "gone", "url": "../missing/channel.json"},
        ]
    }))
    (root / "channel.json").write_text(json.dumps(channel("chan", [
        video("a", published="2026-01-01"),
        video("b", published="2026-01-02", description="short"),
    ])))
    return root


class TestEndToEnd(unittest.TestCase):
    def run_cm(self, root, *extra):
        return cm.main(["run", "--repo", str(root), "--offline",
                        "--today", "2026-08-01", *extra])

    def test_run_writes_both_snapshots_and_never_touches_a_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_fixture_repo(Path(tmp))
            before = (root / "channel.json").read_bytes()
            registry_before = (root / "channels.json").read_bytes()
            self.assertEqual(self.run_cm(root), 0)
            self.assertEqual((root / "channel.json").read_bytes(), before)
            self.assertEqual((root / "channels.json").read_bytes(), registry_before)
            props = json.loads((root / "state" / "proposals.json").read_text())
            reviews = json.loads((root / "state" / "editorial_reviews.json").read_text())
            self.assertEqual(props["schema"], cm.SCHEMA_PROPOSALS)
            self.assertEqual(reviews["schema"], cm.SCHEMA_EDITORIAL)
            self.assertTrue(props["proposals"])
            self.assertEqual(sorted(reviews["reviews"]), ["chan/a", "chan/b"])

    def test_a_second_run_changes_no_bytes(self):
        """A no-op run must produce no commit."""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_fixture_repo(Path(tmp))
            self.run_cm(root)
            first = {p.name: p.read_bytes() for p in (root / "state").iterdir()}
            self.run_cm(root)
            second = {p.name: p.read_bytes() for p in (root / "state").iterdir()}
            self.assertEqual(first, second)

    def test_the_unreachable_channel_is_reported_as_coverage_not_silence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_fixture_repo(Path(tmp))
            self.run_cm(root)
            props = json.loads((root / "state" / "proposals.json").read_text())
            self.assertEqual(props["coverage"]["channels_in_registry"], 2)
            self.assertEqual(props["coverage"]["channels_loaded"], 1)
            self.assertEqual(len(props["coverage"]["channels_unreachable"]), 1)
            self.assertNotIn("gone", [p["channel"] for p in props["proposals"]])

    def test_everything_offline_leaves_the_snapshots_untouched(self):
        """Zero channels loaded must not blank a good snapshot."""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_fixture_repo(Path(tmp))
            self.run_cm(root)
            good = (root / "state" / "proposals.json").read_bytes()
            (root / "channel.json").unlink()
            self.assertEqual(self.run_cm(root), 0)
            self.assertEqual((root / "state" / "proposals.json").read_bytes(), good)

    def test_strict_mode_reports_a_total_collection_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_fixture_repo(Path(tmp))
            (root / "channel.json").unlink()
            self.assertNotEqual(self.run_cm(root, "--strict"), 0)

    def test_review_limit_drains_a_backlog_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_fixture_repo(Path(tmp))
            self.run_cm(root, "--review-limit", "1")
            first = json.loads((root / "state" / "editorial_reviews.json").read_text())
            self.assertEqual(list(first["reviews"]), ["chan/a"])
            self.run_cm(root, "--review-limit", "1")
            second = json.loads((root / "state" / "editorial_reviews.json").read_text())
            self.assertEqual(sorted(second["reviews"]), ["chan/a", "chan/b"])

    def test_a_thin_description_is_scored_low_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_fixture_repo(Path(tmp))
            self.run_cm(root)
            reviews = json.loads((root / "state" / "editorial_reviews.json").read_text())
            self.assertEqual(reviews["reviews"]["chan/b"]["scores"]["description_stands_alone"], 1)
            self.assertIn("chan/b", reviews["totals"]["flagged"])

    def test_a_human_triaged_proposal_survives_a_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_fixture_repo(Path(tmp))
            self.run_cm(root)
            path = root / "state" / "proposals.json"
            doc = json.loads(path.read_text())
            doc["proposals"][0]["status"] = "accepted"
            doc["proposals"][0]["notes"] = "mine"
            path.write_text(json.dumps(doc, indent=2))
            self.run_cm(root)
            after = json.loads(path.read_text())["proposals"][0]
            self.assertEqual(after["status"], "accepted")
            self.assertEqual(after["notes"], "mine")


# --------------------------------------------------------------------------
# a signal-blind run closes nothing
#
# The channel source has always been gated: an unreachable channel closes no
# proposal on it. The metrics source was not, and it is the one that actually
# fails — a missing or unparseable state/metrics.json makes index_signals()
# return {}, every signal-driven gap goes quiet, and the merge read that
# silence as "the gap is gone". "Seven people said this was confusing" became
# "resolved" because a JSON file did not parse.
# --------------------------------------------------------------------------


def signal_proposal(**kw):
    """A queued proposal that exists only because the metrics snapshot said so."""
    base = {
        "id": "cafe12345678",
        "kind": "viewers_confused",
        "channel": "chan",
        "subject": "chan/a",
        "evidence": {"signal": "confusing", "count": 7, "fires_at": 2},
        "gap_closed": False,
        "status": "accepted",
        "notes": "Kody: reshoot the middle section.",
    }
    base.update(kw)
    return base


class TestSignalBlindRunClosesNothing(unittest.TestCase):
    def run_propose(self, root):
        # NOT named `run`: that is unittest.TestCase.run, and overriding it
        # makes every test in the class silently not execute while reporting
        # a pass.
        return cm.main(["propose", "--repo", str(root), "--offline",
                        "--today", "2026-08-01"])

    def test_the_signal_driven_kinds_are_exactly_what_the_detector_emits(self):
        """If a new signal-driven kind is added to the detector and not to
        SIGNAL_DRIVEN_KINDS, the guard silently stops covering it."""
        self.assertEqual(cm.SIGNAL_DRIVEN_KINDS,
                         frozenset(k for _role, k in cm.SIGNAL_GAP_KINDS))
        idx = cm.index_signals({"videos": {"chan/a": {"signals": {"confusing": 7,
                                                                 "want_more_like_this": 5}}}})
        chan = channel("chan", [video("a", published="2026-08-01"),
                                video("b"), video("c")])
        gaps = cm.detect_gaps(network([chan]), idx, cm.DEFAULTS, "2026-08-01")
        per_video = [g for g in gaps if "/" in g["subject"]]
        self.assertTrue(per_video, "the fixture should fire per-video signal gaps")
        for gap in per_video:
            self.assertIn(gap["kind"], cm.SIGNAL_DRIVEN_KINDS)

    def test_a_signal_driven_proposal_is_not_closed_when_signals_are_blind(self):
        kept = cm.merge_proposals([signal_proposal()], [], {"chan"},
                                  signals_available=False)[0]
        self.assertFalse(kept["gap_closed"],
                         "an unreadable metrics snapshot must not retire a triaged gap")
        self.assertEqual(kept["status"], "accepted")
        self.assertEqual(kept["notes"], "Kody: reshoot the middle section.")

    def test_the_same_proposal_does_close_when_signals_were_readable(self):
        """The guard must not be a blanket refusal: a gap that really stopped
        firing still closes, or the queue never drains."""
        kept = cm.merge_proposals([signal_proposal()], [], {"chan"},
                                  signals_available=True)[0]
        self.assertTrue(kept["gap_closed"])

    def test_a_channel_gap_still_closes_on_a_signal_blind_run(self):
        """Signal blindness gates the SIGNAL source only. A channel gap was
        re-checked against the channel, which loaded, so it closes."""
        stale = signal_proposal(id="deadbeef0003", kind="channel_stale",
                                subject="chan", status="proposed")
        kept = cm.merge_proposals([stale], [], {"chan"}, signals_available=False)[0]
        self.assertTrue(kept["gap_closed"])

    def test_coverage_publishes_whether_signals_answered(self):
        """Signal-blind and everything-got-fixed produce the same shaped queue.
        The difference has to be readable without diffing yesterday's file."""
        net = network([channel("chan")])
        adapter = cm.DryRunAdapter()
        blind = cm.proposals_payload([], [], net, cm.DEFAULTS, adapter,
                                     signals_available=False)
        seeing = cm.proposals_payload([], [], net, cm.DEFAULTS, adapter,
                                      signals_available=True)
        self.assertFalse(blind["coverage"]["signals_available"])
        self.assertTrue(seeing["coverage"]["signals_available"])
        # Unstated is null, never a claim either way.
        self.assertIsNone(
            cm.proposals_payload([], [], net, cm.DEFAULTS, adapter)["coverage"]
            ["signals_available"])

    def test_end_to_end_an_unparseable_metrics_file_retires_nothing(self):
        """The plumbing, not just the merge: main() -> cmd_propose -> merge.
        Reintroduce the bug by dropping `signals_available=` from either call
        site and this goes red."""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_fixture_repo(Path(tmp))
            metrics = root / "state" / "metrics.json"
            metrics.write_text(json.dumps({
                "videos": {"chan/a": {"signals": {"confusing": 7}}}
            }))
            self.assertEqual(self.run_propose(root), 0)

            path = root / "state" / "proposals.json"
            doc = json.loads(path.read_text())
            self.assertTrue(doc["coverage"]["signals_available"])
            confused = [p for p in doc["proposals"] if p["kind"] == "viewers_confused"]
            self.assertEqual(len(confused), 1, "the signal gap should have fired")
            confused[0]["status"] = "accepted"
            confused[0]["notes"] = "Kody: reshoot the middle section."
            path.write_text(json.dumps(doc, indent=2))

            # The snapshot the other writer owns stops parsing.
            metrics.write_text("{ this is not json")
            self.assertEqual(self.run_propose(root), 0)

            after = json.loads(path.read_text())
            self.assertFalse(after["coverage"]["signals_available"])
            kept = [p for p in after["proposals"] if p["kind"] == "viewers_confused"][0]
            self.assertFalse(kept["gap_closed"],
                             "a JSON parse error must not read as 'the viewers are happy now'")
            self.assertEqual(kept["status"], "accepted")
            self.assertEqual(kept["notes"], "Kody: reshoot the middle section.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
