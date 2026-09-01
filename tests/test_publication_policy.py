"""Executable tests for the paired-publication constitution."""

import copy
import importlib.util
import json
import re
import subprocess
import sys
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
            "invalid-null-optionals.json": ".chapters: must be an array",
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
        self.assertIsNotNone(re.fullmatch(pattern, "video/mp4 ; codecs=\"avc1\""))
        whitespace = copy.deepcopy(self.valid)
        whitespace["videos"][0]["sources"][0]["type"] = "video/mp4 ; codecs=\"avc1\""
        self.assertEqual(self.validate(whitespace), [])

    def test_channel_and_publication_ids_use_one_collision_safe_grammar(self):
        schema = load(ROOT / "channel.schema.json")
        channel_pattern = schema["properties"]["id"]["pattern"]
        publication_pattern = schema["$defs"]["publication"]["properties"]["id"]["pattern"]
        self.assertEqual(channel_pattern, publication_pattern)

        for record in self.policy["channels"]:
            self.assertTrue(VALIDATOR.valid_id(record["id"]), record["id"])
            self.assertIsNotNone(re.fullmatch(channel_pattern, record["id"]))
            for publication in record["publications"]:
                self.assertTrue(VALIDATOR.valid_id(publication["id"]), publication["id"])
                self.assertIsNotNone(re.fullmatch(publication_pattern, publication["id"]))

        for invalid in ("a/b", "b/c", "percent%2Fid", "two words", "\ncontrol"):
            with self.subTest(invalid=invalid):
                self.assertFalse(VALIDATOR.valid_id(invalid))
                self.assertIsNone(re.fullmatch(channel_pattern, invalid))
                channel = copy.deepcopy(self.valid)
                channel["id"] = invalid
                self.assertTrue(any("channel.id: must start alphanumeric" in error for error in self.validate(channel)))
                channel = copy.deepcopy(self.valid)
                channel["videos"][0]["id"] = invalid
                self.assertTrue(any("videos[0].id: must start alphanumeric" in error for error in self.validate(channel)))

    def test_live_app_urls_allow_only_relative_or_absolute_https(self):
        schema = load(ROOT / "channel.schema.json")
        app_schema = schema["$defs"]["publication"]["properties"]["live"]["properties"][
            "scenes"
        ]["items"]["properties"]["app"]
        absolute_pattern = app_schema["oneOf"][0]["pattern"]
        relative_pattern = app_schema["oneOf"][1]["pattern"]
        schema_allows = lambda value: any(
            re.fullmatch(pattern, value)
            for pattern in (absolute_pattern, relative_pattern)
        )
        safe = [
            "../app/index.html",
            "/apps/demo.html?mode=live#start",
            "app.html",
            "https://example.test/app/",
        ]
        unsafe = [
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "blob:https://example.test/id",
            "file:///Users/me/app.html",
            "http://example.test/app.html",
            "//example.test/app.html",
            "\\\\example.test\\app.html",
            "?app=demo",
            "https://[",
            "../app.html;execute",
            "../app.html%3Bexecute",
            "../app%2Fchild.html",
            "../app%5Cchild.html",
            "https://example.test:999999/app.html",
        ]
        for app in safe:
            with self.subTest(app=app, allowed=True):
                self.assertTrue(VALIDATOR.safe_app_url(app))
                self.assertTrue(schema_allows(app))
        for app in unsafe:
            with self.subTest(app=app, allowed=False):
                self.assertFalse(VALIDATOR.safe_app_url(app))
                self.assertFalse(schema_allows(app))
                channel = copy.deepcopy(self.valid)
                channel["videos"][0]["live"]["scenes"][1]["app"] = app
                self.assertTrue(any(
                    ".app: must be a safe relative URL or absolute HTTPS URL" in error
                    for error in self.validate(channel)
                ))

    def test_media_sources_require_distinct_matching_extensions(self):
        positive = copy.deepcopy(self.valid)
        positive["videos"][0]["sources"][0]["src"] += "?download=1#video"
        positive["videos"][0]["sources"][1]["src"] += "?download=1#video"
        self.assertEqual(self.validate(positive), [])

        wrong_extension = copy.deepcopy(self.valid)
        wrong_extension["videos"][0]["sources"][0]["src"] = "paired.webm"
        self.assertTrue(any(
            "video/mp4 requires a .mp4 pathname" in error
            for error in self.validate(wrong_extension)
        ))

        duplicate = copy.deepcopy(self.valid)
        duplicate["videos"][0]["sources"] = [
            {"src": "same.mp4#one", "type": "video/mp4"},
            {"src": "same.mp4#two", "type": "video/mp4"},
            {"src": "other.webm", "type": "video/webm"},
        ]
        self.assertTrue(any(
            "media source URLs must be distinct" in error
            for error in self.validate(duplicate)
        ))

        schema = load(ROOT / "channel.schema.json")
        source_rules = schema["$defs"]["source"]["allOf"]
        self.assertEqual(
            source_rules[0]["then"]["properties"]["src"]["pattern"],
            "^(?![^?#]*(?:;|%3[bB]|%2[fF]|%5[cC]))[^?#]*\\.mp4(?:[?#].*)?$",
        )
        self.assertEqual(
            source_rules[1]["then"]["properties"]["src"]["pattern"],
            "^(?![^?#]*(?:;|%3[bB]|%2[fF]|%5[cC]))[^?#]*\\.webm(?:[?#].*)?$",
        )
        self.assertIsNotNone(re.search(
            source_rules[0]["then"]["properties"]["src"]["pattern"],
            "media/clip.mp4?download=1#video",
        ))
        self.assertIsNone(re.search(
            source_rules[0]["then"]["properties"]["src"]["pattern"],
            "media/clip.exe?download=clip.mp4",
        ))

    def test_parameterized_media_path_is_rejected_and_preserved_for_local_probe(self):
        for source in (
            "paired.mp4;served-as-html",
            "paired.mp4%3Bserved-as-html",
            "dir%2Fpaired.mp4",
            "dir%5Cpaired.mp4",
        ):
            with self.subTest(source=source):
                channel = copy.deepcopy(self.valid)
                channel["videos"][0]["sources"][0]["src"] = source
                errors = self.validate(channel)
                self.assertTrue(any(
                    "pathname parameters are not allowed" in error
                    or "encoded path separators or backslashes are not allowed" in error
                    for error in errors
                ))

        schema = load(ROOT / "channel.schema.json")
        pattern = schema["$defs"]["source"]["allOf"][0]["then"]["properties"]["src"][
            "pattern"
        ]
        self.assertIsNone(re.search(pattern, "paired.mp4;served-as-html"))
        self.assertIsNone(re.search(pattern, "paired.mp4%3Bserved-as-html"))

        represented = VALIDATOR.local_media_path(
            ROOT / "channel.json",
            "media/rock-tumbler-showcase.mp4;served-as-html",
        )
        self.assertEqual(
            represented.name,
            "rock-tumbler-showcase.mp4;served-as-html",
        )
        encoded_represented = VALIDATOR.local_media_path(
            ROOT / "channel.json",
            "media/rock-tumbler-showcase.mp4%3Bserved-as-html",
        )
        self.assertEqual(
            encoded_represented.name,
            "rock-tumbler-showcase.mp4;served-as-html",
        )
        self.assertIsNone(VALIDATOR.local_media_path(
            ROOT / "channel.json",
            "media%2Frock-tumbler-showcase.mp4",
        ))
        calls = []

        def runner(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout='{"streams":[]}', stderr="")

        probe_errors = VALIDATOR.ffprobe_local_media(
            {
                "videos": [{
                    "sources": [{
                        "src": "media/rock-tumbler-showcase.mp4;served-as-html",
                        "type": "video/mp4",
                    }],
                }],
            },
            ROOT / "channel.json",
            runner=runner,
        )
        self.assertEqual(calls, [])
        self.assertTrue(any(
            "rock-tumbler-showcase.mp4;served-as-html" in error
            for error in probe_errors
        ))

    def test_optional_ffprobe_path_checks_repository_owned_codecs(self):
        channel = {
            "videos": [{
                "sources": [
                    {
                        "src": "media/rock-tumbler-showcase.mp4",
                        "type": "video/mp4",
                    },
                    {
                        "src": "media/rock-tumbler-showcase.webm",
                        "type": "video/webm",
                    },
                ],
            }],
        }
        calls = []

        def runner(command, **_kwargs):
            calls.append(command)
            codec = "h264" if command[-1].endswith(".mp4") else "vp9"
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps({"streams": [{"codec_name": codec}]}),
                stderr="",
            )

        self.assertEqual(
            VALIDATOR.ffprobe_local_media(channel, ROOT / "channel.json", runner=runner),
            [],
        )
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(command[0] == "ffprobe" for command in calls))

        def wrong_runner(command, **_kwargs):
            return subprocess.CompletedProcess(
                command, 0, stdout='{"streams":[{"codec_name":"mpeg4"}]}', stderr=""
            )

        whitespace_type = copy.deepcopy(channel)
        whitespace_type["videos"][0]["sources"][0][
            "type"
        ] = "video/mp4 ; codecs=\"avc1\""
        calls = []

        def whitespace_runner(command, **_kwargs):
            calls.append(command)
            return wrong_runner(command)

        self.assertTrue(any(
            "expected ['h264'] video codec" in error
            for error in VALIDATOR.ffprobe_local_media(
                {"videos": [{"sources": [whitespace_type["videos"][0]["sources"][0]]}]},
                ROOT / "channel.json",
                runner=whitespace_runner,
            )
        ))
        self.assertEqual(len(calls), 1)

    def test_explicit_null_optionals_fail_cli_and_schema(self):
        fixture = FIXTURES / "invalid-null-optionals.json"
        errors = self.validate(load(fixture))
        self.assertTrue(any("videos[0].chapters: must be an array" in error for error in errors))
        self.assertTrue(any("live.duration: must be greater than zero" in error for error in errors))
        self.assertTrue(any("live.chapters: must be an array" in error for error in errors))
        self.assertTrue(any("scenes[0].actions: must be an array" in error for error in errors))

        completed = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), str(fixture)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("live.duration: must be greater than zero", completed.stderr)

        schema = load(ROOT / "channel.schema.json")
        publication = schema["$defs"]["publication"]["properties"]
        live = publication["live"]["properties"]
        scene = live["scenes"]["items"]["properties"]
        self.assertEqual(publication["chapters"]["type"], "array")
        self.assertEqual(live["chapters"]["type"], "array")
        self.assertEqual(live["duration"]["type"], "number")
        self.assertEqual(scene["actions"]["type"], "array")

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
            ROOT / ".github" / "workflows" / "legacy-freeze.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("pull_request_target:", workflow)
        self.assertIn("github.event.before", workflow)

    def test_registry_entry_and_resolved_channel_ids_must_be_equal_and_unique(self):
        resolved = {}
        self.assertEqual(
            VALIDATOR.validate_registry_channel_identity(
                {"id": "alpha"}, {"id": "alpha"}, resolved, "registry.channels[0]"
            ),
            [],
        )
        errors = VALIDATOR.validate_registry_channel_identity(
            {"id": "beta"}, {"id": "alpha"}, resolved, "registry.channels[1]"
        )
        self.assertTrue(any("must equal fetched channel id" in error for error in errors))
        self.assertTrue(any("duplicates registry.channels[0]" in error for error in errors))

    def test_scheduled_publishers_use_stable_branches_and_pull_requests(self):
        workflows = {
            "harvest-follows.yml": "automation/harvest-follows",
            "metrics.yml": "automation/metrics",
            "content-machine.yml": "automation/content-machine",
        }
        for filename, branch in workflows.items():
            with self.subTest(workflow=filename):
                source = (
                    ROOT / ".github" / "workflows" / filename
                ).read_text(encoding="utf-8")
                self.assertIn("contents: write", source)
                self.assertIn("pull-requests: write", source)
                self.assertIn(f"AUTOMATION_BRANCH: {branch}", source)
                self.assertIn("git fetch origin main", source)
                self.assertIn('git checkout -B "$AUTOMATION_BRANCH" origin/main', source)
                self.assertIn("--force-with-lease=", source)
                self.assertIn('origin "HEAD:$AUTOMATION_BRANCH"', source)
                self.assertIn("gh pr list", source)
                self.assertIn("--state open", source)
                self.assertIn("gh pr create", source)
                self.assertIn("--base main", source)
                self.assertIn("GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}", source)
                self.assertNotRegex(source, r"git push[^\n]*(?:HEAD:main|origin main)")
                self.assertNotIn("git pull --rebase origin main", source)

        operations = (ROOT / "docs" / "AUTOMATION-PRS.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("review-ready", operations)
        self.assertIn("Do not work around", operations)

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
