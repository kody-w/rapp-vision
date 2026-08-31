"""Executable tests for the paired-publication constitution."""

import copy
import importlib.util
import json
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
        self.assertEqual(
            self.validate(load(ROOT / "template" / "channel.json")),
            [],
        )

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
        self.assertTrue(any("between 0 and the scene duration" in error for error in errors))
        self.assertTrue(any("click requires exactly one" in error for error in errors))

    def test_frozen_legacy_identity_and_source_are_both_required(self):
        legacy = {
            "schema": "rapp-vision-channel/1.0",
            "id": "frame-chains",
            "name": "Frame Chains",
            "videos": [{"id": "many-worlds-mission-control"}],
        }
        canonical = "https://kody-w.github.io/rapp-vision/frame-chains/channel.json"
        self.assertEqual(self.validate(legacy, canonical), [])
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
        registry = load(ROOT / "channels.json")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
