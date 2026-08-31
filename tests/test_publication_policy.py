"""Executable tests for the paired-publication constitution."""

import copy
import importlib.util
import json
import re
import unittest
from pathlib import Path
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "publications"
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
SPEC = importlib.util.spec_from_file_location("validate_publications", VALIDATOR_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestPublicationPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load(ROOT / "policy" / "legacy-publications.json")
        cls.valid = load(FIXTURES / "valid-paired.json")

    def validate(self, document, source="https://example.test/channel.json"):
        return VALIDATOR.validate_channel(document, source, self.policy)

    def test_positive_fixture_and_template_are_valid(self):
        self.assertEqual(self.validate(self.valid), [])
        self.assertEqual(self.valid["videos"][0]["duration"], 10)
        self.assertEqual(self.valid["videos"][0]["live"]["duration"], 12)
        self.assertEqual(
            self.validate(load(ROOT / "template" / "channel.json")),
            [],
        )

    def test_replay_duration_is_explicit_or_derived_never_the_film_duration(self):
        derived = copy.deepcopy(self.valid)
        del derived["videos"][0]["live"]["duration"]
        self.assertEqual(self.validate(derived), [])

        wrong_replay_duration = copy.deepcopy(self.valid)
        wrong_replay_duration["videos"][0]["live"]["duration"] = 10
        errors = self.validate(wrong_replay_duration)
        self.assertTrue(any("must fill replay duration 10; ended at 12" in error for error in errors))

    def test_film_and_replay_chapters_use_their_own_duration_bounds(self):
        film_bad = copy.deepcopy(self.valid)
        film_bad["videos"][0]["chapters"] = [{"t": 11, "label": "Outside film"}]
        self.assertTrue(any(
            ".chapters[0].t: must be within the mode duration" in error
            for error in self.validate(film_bad)
        ))

        replay_ok = copy.deepcopy(self.valid)
        replay_ok["videos"][0]["live"]["chapters"].append(
            {"t": 11, "label": "Still inside replay"}
        )
        self.assertEqual(self.validate(replay_ok), [])

    def test_negative_fixtures_are_rejected_for_the_named_reason(self):
        cases = {
            "invalid-missing-webm.json": "missing required video/webm",
            "invalid-missing-live.json": ".live: must be an object",
            "invalid-scene-gap.json": "scenes must be contiguous",
            "invalid-ready-action.json": "requires exactly one non-empty selector or text",
            "invalid-media-type.json": "only video/mp4 and video/webm are allowed",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertTrue(
                    any(expected in error for error in self.validate(load(FIXTURES / name))),
                    self.validate(load(FIXTURES / name)),
                )

    def test_duration_and_action_bounds_are_rejected(self):
        errors = self.validate(load(FIXTURES / "invalid-ready-action.json"))
        self.assertTrue(any("less than the scene duration" in error for error in errors))
        self.assertTrue(any("click requires exactly one" in error for error in errors))

    def test_action_at_exact_scene_boundary_is_rejected(self):
        channel = copy.deepcopy(self.valid)
        scene = channel["videos"][0]["live"]["scenes"][1]
        scene["actions"][0]["at"] = scene["dur"]
        errors = self.validate(channel)
        self.assertTrue(any("less than the scene duration" in error for error in errors))

    def test_mime_types_are_canonical_lowercase_in_schema_and_validators(self):
        channel = copy.deepcopy(self.valid)
        channel["videos"][0]["sources"][0]["type"] = "Video/MP4"
        errors = self.validate(channel)
        self.assertTrue(any("only video/mp4 and video/webm" in error for error in errors))
        schema = load(ROOT / "channel.schema.json")
        pattern = schema["$defs"]["source"]["properties"]["type"]["pattern"]
        self.assertIsNone(re.fullmatch(pattern, "Video/MP4"))
        self.assertIsNotNone(re.fullmatch(pattern, "video/mp4; codecs=\"avc1\""))

    def test_frozen_legacy_identity_source_and_content_are_all_required(self):
        legacy = load(ROOT / "frame-chains" / "channel.json")
        canonical = "https://kody-w.github.io/rapp-vision/frame-chains/channel.json"
        self.assertEqual(self.validate(legacy, canonical), [])
        replaced = copy.deepcopy(legacy)
        replaced["videos"][0]["title"] = "Arbitrary replacement"
        self.assertTrue(any("frozen legacy digest" in error for error in self.validate(
            replaced, canonical
        )))
        self.assertTrue(any("canonical source" in error for error in self.validate(
            legacy, "https://example.test/frame-chains/channel.json"
        )))

    def test_new_publication_cannot_hide_in_allowlisted_v1_channel(self):
        legacy = {
            "schema": "rapp-vision-channel/1.0",
            "id": "frame-chains",
            "name": "Frame Chains",
            "videos": [{"id": "new-single-format-publication"}],
        }
        errors = self.validate(
            legacy,
            "https://kody-w.github.io/rapp-vision/frame-chains/channel.json",
        )
        self.assertTrue(any("not a frozen legacy publication" in error for error in errors))

    def test_new_v1_registry_url_is_not_grandfathered_by_adding_it(self):
        bypass = {
            "id": "new-v1",
            "name": "New v1",
            "url": "new-v1/channel.json",
            "legacy": self.policy["id"],
        }
        canonical = urljoin(self.policy["registry_base"], bypass["url"])
        self.assertIsNone(VALIDATOR.legacy_record(self.policy, bypass["id"], canonical))

    def test_new_v2_channel_still_rejects_single_format_entries(self):
        for field in ("sources", "live"):
            with self.subTest(field=field):
                channel = copy.deepcopy(self.valid)
                if field == "sources":
                    channel["videos"][0]["sources"] = []
                else:
                    del channel["videos"][0]["live"]
                self.assertTrue(self.validate(channel))

    def test_default_registry_is_fully_and_explicitly_frozen(self):
        registry = load(ROOT / "channels.json")
        base = self.policy["registry_base"]
        for entry in registry["channels"]:
            with self.subTest(channel=entry["id"]):
                self.assertEqual(entry.get("legacy"), self.policy["id"])
                self.assertIsNotNone(
                    VALIDATOR.legacy_record(
                        self.policy,
                        entry["id"],
                        urljoin(base, entry["url"]),
                    )
                )
                record = VALIDATOR.legacy_record(
                    self.policy,
                    entry["id"],
                    urljoin(base, entry["url"]),
                )
                self.assertTrue(all(
                    isinstance(publication, dict)
                    and re.fullmatch(r"[0-9a-f]{64}", publication.get("sha256", ""))
                    for publication in record["publications"]
                ))

    def test_git_baseline_rejects_legacy_expansion_and_digest_self_authorization(self):
        video = {"id": "old-video", "title": "Original"}
        digest = VALIDATOR.publication_digest(video)
        baseline = {
            "schema": "rapp-vision-legacy-publications/1.0",
            "id": "legacy-publications-2026-08-31",
            "frozen_at": "2026-08-31T16:24:12Z",
            "registry_base": "https://example.test/channels.json",
            "channels": [{
                "id": "old",
                "source": "https://example.test/old/channel.json",
                "publications": ["old-video"],
            }],
        }
        current = copy.deepcopy(baseline)
        current["channels"][0]["publications"] = [{"id": "old-video", "sha256": digest}]
        documents = {
            ("old", "https://example.test/old/channel.json"): {
                "videos": [video],
            }
        }
        self.assertEqual(
            VALIDATOR.validate_frozen_policy(current, baseline, documents),
            [],
        )

        expanded = copy.deepcopy(current)
        expanded["channels"].append({
            "id": "new",
            "source": "https://example.test/new/channel.json",
            "publications": [{"id": "new-video", "sha256": "0" * 64}],
        })
        self.assertTrue(any(
            "identities differ from git baseline" in error
            for error in VALIDATOR.validate_frozen_policy(expanded, baseline, documents)
        ))

        self_authorized = copy.deepcopy(current)
        self_authorized["channels"][0]["publications"][0]["sha256"] = "0" * 64
        self.assertTrue(any(
            "does not match git baseline content" in error
            for error in VALIDATOR.validate_frozen_policy(
                self_authorized, baseline, documents
            )
        ))

    def test_ci_uses_full_git_history_and_checks_the_trusted_base(self):
        workflow = (
            ROOT / ".github" / "workflows" / "publication-policy.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("--check-legacy-baseline", workflow)
        self.assertIn('origin/${{ github.base_ref }}', workflow)

    def test_digest_baseline_is_immutable_after_bootstrap(self):
        baseline = copy.deepcopy(self.policy)
        changed = copy.deepcopy(self.policy)
        changed["channels"][0]["publications"][0]["sha256"] = "0" * 64
        self.assertTrue(any(
            "frozen digest baseline was modified" in error
            for error in VALIDATOR.validate_frozen_policy(changed, baseline, {})
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
