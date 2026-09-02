"""Offline structural tests for the static RAPP Vision creator ingress."""

import json
import re
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = [
    "agent.schema.json",
    "commissions.schema.json",
    "submission.schema.json",
    "quality.schema.json",
]
SLATE_CATEGORIES = {"use", "learn", "prove", "play", "create", "explore"}
GATE_NAMES = {
    "paired_delivery",
    "objective_evidence",
    "positive_path",
    "visible_failure",
    "exact_reset",
    "rights_privacy",
    "review_quorum",
}


def load(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def object_schemas(value):
    if isinstance(value, dict):
        if value.get("type") == "object":
            yield value
        for child in value.values():
            yield from object_schemas(child)
    elif isinstance(value, list):
        for child in value:
            yield from object_schemas(child)


def nested_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from nested_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_keys(child)


def phase_branch(schema, phase):
    for branch in schema["allOf"]:
        expected = (
            branch.get("if", {})
            .get("properties", {})
            .get("phase", {})
            .get("const")
        )
        if expected == phase:
            return branch
    raise AssertionError(f"missing conditional branch for {phase}")


class TestCreatorIngress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = load("agent.json")
        cls.agent_schema = load("agent.schema.json")
        cls.commissions = load("commissions.json")
        cls.commissions_schema = load("commissions.schema.json")
        cls.submission_schema = load("submission.schema.json")
        cls.quality_schema = load("quality.schema.json")
        cls.template = load("template/submission.json")
        cls.channel_schema = load("channel.schema.json")

    def test_agent_is_stable_complete_and_portable(self):
        self.assertEqual(self.agent["name"], "RAPP Vision")
        self.assertEqual(self.agent["id"], "rapp-vision")
        current_contract = self.channel_schema["properties"]["schema"]["const"]
        self.assertEqual(current_contract, "rapp-vision-channel/2.0")
        self.assertEqual(self.agent["channel_contract"], current_contract)
        self.assertEqual(self.agent["publication_contract"], current_contract)
        self.assertEqual(self.agent["channel_schema"], "channel.schema.json")
        self.assertEqual(
            self.agent["publication_schema"],
            "channel.schema.json#/$defs/publication",
        )

        links = {
            "channel_schema": self.agent["channel_schema"],
            "publication_schema": self.agent["publication_schema"],
            "commissions": self.agent["commissions"],
            "commissions_schema": self.agent["commissions_schema"],
            "submission_protocol": self.agent["submission_protocol"],
            "submission_schema": self.agent["submission_schema"],
            "quality_schema": self.agent["quality_schema"],
            "submission_template": self.agent["submission_template"],
            "production_schema": self.agent["production"]["schema"],
            "production_template": self.agent["production"]["template"],
            "production_compiler": self.agent["production"]["compiler"],
            "submission_validator": self.agent["submission_validator"]["script"],
            "default_registry": self.agent["default_registry"],
        }
        for relation, link in links.items():
            with self.subTest(relation=relation):
                parsed = urlsplit(link)
                self.assertFalse(parsed.scheme)
                self.assertFalse(parsed.netloc)
                self.assertFalse(link.startswith(("/", "\\")))
                self.assertNotIn("\\", link)
                self.assertTrue((ROOT / parsed.path).is_file(), link)

        self.assertEqual(self.agent["submission_transport"], "pull-request")
        self.assertEqual(
            self.agent["submission_manifest_location"],
            "pull-request-body",
        )
        self.assertEqual(
            self.agent["validator"]["command"],
            "python3 scripts/validate_publications.py {channel_json}",
        )
        self.assertEqual(
            self.agent["repository"],
            "https://github.com/kody-w/rapp-vision",
        )
        self.assertEqual(
            self.agent["production"],
            {
                "contract": "rapp-vision-production/1.0",
                "schema": "channel.production.schema.json",
                "template": "template/channel.production.json",
                "compiler": "scripts/compile_publications.py",
                "check": (
                    "python3 scripts/compile_publications.py check "
                    "{production_json}"
                ),
                "build": (
                    "python3 scripts/compile_publications.py build "
                    "{production_json}"
                ),
            },
        )
        self.assertEqual(
            self.agent["submission_validator"],
            {
                "script": "scripts/validate_creator_submission.py",
                "submission_command": (
                    "python3 scripts/validate_creator_submission.py submission "
                    "{submission_json} --artifact-root {artifact_checkout} "
                    "--pr-number {pull_request_number}"
                ),
                "quality_command": (
                    "python3 scripts/validate_creator_submission.py quality "
                    "{submission_json} {quality_json} "
                    "--repository {repository_url} --run-url {workflow_run_url} "
                    "--pull-request-number {pull_request_number} "
                    "--pull-request-head-sha {pull_request_head_sha} "
                    "--review-state-sha256 {review_state_sha256}"
                ),
            },
        )

    def test_documents_expose_required_core_and_allow_extensions(self):
        documents = [
            (self.agent, self.agent_schema),
            (self.commissions, self.commissions_schema),
            (self.template, self.submission_schema),
        ]
        for document, schema in documents:
            with self.subTest(schema=schema["$id"]):
                self.assertTrue(set(schema["required"]) <= set(document))

        submitted_required = set(
            phase_branch(self.submission_schema, "submitted")["then"]["required"]
        )
        self.assertTrue(submitted_required <= set(self.template))

        for name in SCHEMA_NAMES:
            schema = load(name)
            with self.subTest(schema=name):
                self.assertFalse(urlsplit(schema["$id"]).scheme)
                self.assertTrue(list(object_schemas(schema)))
                for object_schema in object_schemas(schema):
                    self.assertIs(
                        object_schema.get("additionalProperties"),
                        True,
                        object_schema,
                    )

    def test_identifier_commit_and_digest_grammars_are_consistent(self):
        id_patterns = {
            load(name)["$defs"]["id"]["pattern"]
            for name in SCHEMA_NAMES
        }
        self.assertEqual(
            id_patterns,
            {"^[A-Za-z0-9][A-Za-z0-9._-]*$"},
        )
        id_pattern = next(iter(id_patterns))
        for value in (
            self.agent["id"],
            self.commissions["id"],
            self.template["id"],
            self.template["commission_id"],
            self.template["artifact"]["publication_id"],
        ):
            self.assertIsNotNone(re.fullmatch(id_pattern, value), value)
        for value in ("bad/id", "two words", "percent%2Fid", "-leading"):
            self.assertIsNone(re.fullmatch(id_pattern, value), value)

        sha_pattern = self.submission_schema["$defs"]["sha256"]["pattern"]
        commit_pattern = self.submission_schema["$defs"]["gitCommit"]["pattern"]
        self.assertEqual(sha_pattern, "^[0-9a-f]{64}$")
        self.assertIsNone(
            re.fullmatch(commit_pattern, self.template["artifact"]["commit"])
        )
        digests = [
            self.template["artifact"]["sha256"],
            self.template["deliverables"]["mp4"]["sha256"],
            self.template["deliverables"]["webm"]["sha256"],
        ]
        for digest in digests:
            self.assertIsNone(re.fullmatch(sha_pattern, digest))
        self.assertEqual(
            self.quality_schema["$defs"]["sha256"]["pattern"],
            sha_pattern,
        )
        self.assertEqual(
            self.quality_schema["$defs"]["gitCommit"]["pattern"],
            commit_pattern,
        )

    def test_launch_slate_covers_all_categories_and_every_gate(self):
        slate = self.commissions["commissions"]
        self.assertGreaterEqual(len(slate), 12)
        counts = Counter(item["category"] for item in slate)
        self.assertEqual(set(counts), SLATE_CATEGORIES)
        self.assertTrue(all(counts[category] >= 2 for category in SLATE_CATEGORIES))
        self.assertEqual(len({item["id"] for item in slate}), len(slate))

        id_pattern = self.commissions_schema["$defs"]["id"]["pattern"]
        for commission in slate:
            with self.subTest(commission=commission["id"]):
                self.assertEqual(commission["status"], "open")
                self.assertIsNotNone(re.fullmatch(id_pattern, commission["id"]))
                self.assertTrue(commission["brief"].strip())
                gates = commission["gates"]
                self.assertEqual(set(gates), GATE_NAMES)
                self.assertEqual(
                    gates["paired_delivery"],
                    {
                        "mp4": True,
                        "webm": True,
                        "live": True,
                        "same_publication": True,
                    },
                )
                objective = gates["objective_evidence"]
                self.assertIs(objective["required"], True)
                self.assertTrue(objective["criterion"].strip())
                self.assertTrue(objective["acceptance"].strip())
                for path_name in ("positive_path", "visible_failure"):
                    self.assertIs(gates[path_name]["required"], True)
                    self.assertTrue(gates[path_name]["demonstration"].strip())
                reset = gates["exact_reset"]
                self.assertIs(reset["required"], True)
                self.assertGreaterEqual(len(reset["steps"]), 1)
                self.assertTrue(reset["restored_state"].strip())
                rights = gates["rights_privacy"]
                self.assertIs(rights["rights_attestation"], True)
                self.assertIs(rights["privacy_attestation"], True)
                self.assertIs(rights["no_secrets"], True)
                quorum = gates["review_quorum"]
                self.assertGreaterEqual(quorum["minimum_approvals"], 2)
                self.assertTrue(
                    {"technical", "curation"} <= set(quorum["required_roles"])
                )
                self.assertIs(quorum["independent_reviewers"], True)

    def test_claim_and_submitted_phases_are_distinct(self):
        self.assertEqual(
            set(self.submission_schema["properties"]["phase"]["enum"]),
            {"claim", "submitted"},
        )
        claim = phase_branch(self.submission_schema, "claim")
        excluded = {
            tuple(rule["required"])[0]
            for rule in claim["then"]["not"]["anyOf"]
        }
        self.assertEqual(
            excluded,
            {
                "artifact",
                "deliverables",
                "evidence",
                "attestations",
                "review_request",
            },
        )
        submitted = phase_branch(self.submission_schema, "submitted")
        self.assertEqual(set(submitted["then"]["required"]), excluded)
        self.assertEqual(self.template["phase"], "submitted")
        self.assertEqual(
            self.template["claim"],
            {
                "effect": "coordination-only",
                "curation": "none",
                "note": self.template["claim"]["note"],
            },
        )

    def test_submitted_template_exposes_all_bindings_and_fails_closed(self):
        self.assertEqual(self.template["$schema"], "submission.schema.json")
        artifact = self.template["artifact"]
        self.assertEqual(artifact["digest_scope"], "raw-file-bytes")
        self.assertEqual(artifact["path"], "channel.json")
        self.assertEqual(
            self.template["pull_request"]["repository"],
            self.agent["repository"],
        )

        deliverables = self.template["deliverables"]
        self.assertEqual(set(deliverables), {"mp4", "webm", "live"})
        self.assertTrue(deliverables["mp4"]["path"].endswith(".mp4"))
        self.assertTrue(deliverables["webm"]["path"].endswith(".webm"))
        self.assertEqual(
            deliverables["live"]["publication_id"],
            artifact["publication_id"],
        )
        self.assertEqual(deliverables["live"]["channel_path"], artifact["path"])
        self.assertEqual(deliverables["live"]["kind"], "rapp-vision-live/1.0")

        evidence = self.template["evidence"]
        self.assertEqual(
            set(evidence),
            {
                "objective_evidence",
                "positive_path",
                "visible_failure",
                "exact_reset",
            },
        )
        self.assertTrue(evidence["objective_evidence"]["evidence_path"])
        self.assertTrue(evidence["positive_path"]["description"])
        self.assertTrue(evidence["visible_failure"]["description"])
        self.assertTrue(evidence["exact_reset"]["steps"])
        self.assertTrue(evidence["exact_reset"]["restored_state"])

        attestations = self.template["attestations"]
        self.assertIs(attestations["rights"]["attested"], False)
        self.assertIs(attestations["privacy"]["attested"], False)
        self.assertIs(attestations["no_secrets"], False)
        review = self.template["review_request"]
        self.assertGreaterEqual(review["minimum_approvals"], 2)
        self.assertIs(review["independent_reviewers"], True)
        self.assertEqual(
            {item["role"] for item in review["reviews"]},
            {"technical", "curation"},
        )
        self.assertTrue(
            all(
                "decision" not in item and "reviewer" not in item
                for item in review["reviews"]
            )
        )

    def test_quality_separates_pass_listing_and_staleness(self):
        properties = self.quality_schema["properties"]
        self.assertIn("technical", properties)
        self.assertIn("default_registry", properties)
        self.assertIn("freshness", properties)
        self.assertIn("authority", properties)
        self.assertNotEqual(properties["technical"], properties["default_registry"])

        technical_statuses = set(
            self.quality_schema["$defs"]["technical"]["properties"]["status"]["enum"]
        )
        listing = self.quality_schema["$defs"]["defaultRegistry"]
        listing_statuses = set(listing["properties"]["status"]["enum"])
        self.assertEqual(
            technical_statuses,
            {"pending", "pass", "fail", "stale"},
        )
        self.assertEqual(
            listing_statuses,
            {"not-requested", "requested", "not-listed", "listed", "stale"},
        )
        self.assertEqual(
            listing["properties"]["authority"]["const"],
            "registry-entry-only",
        )
        self.assertEqual(
            listing["properties"]["registry"]["const"],
            self.agent["default_registry"],
        )
        quorum = self.quality_schema["$defs"]["quorum"]
        self.assertIn("independent_reviewers", quorum["required"])
        self.assertIs(
            quorum["properties"]["independent_reviewers"]["const"],
            True,
        )

        stale_when = (
            self.quality_schema["$defs"]["freshness"]["properties"]["stale_when"]
        )
        self.assertIs(
            stale_when["properties"]["submission_sha256_changes"]["const"],
            True,
        )
        self.assertIs(
            stale_when["properties"]["artifact_commit_changes"]["const"],
            True,
        )
        self.assertIs(
            stale_when["properties"]["artifact_sha256_changes"]["const"],
            True,
        )
        stale = next(
            branch
            for branch in self.quality_schema["allOf"]
            if branch.get("if", {})
            .get("properties", {})
            .get("freshness", {})
            .get("properties", {})
            .get("status", {})
            .get("const")
            == "stale"
        )
        self.assertEqual(
            stale["then"]["properties"]["technical"]["properties"]["status"]["const"],
            "stale",
        )
        self.assertEqual(
            stale["then"]["properties"]["default_registry"]["properties"]["status"][
                "const"
            ],
            "stale",
        )

    def test_no_creator_field_can_self_authorize_listing(self):
        forbidden = {
            "approval",
            "approved",
            "accepted",
            "listing",
            "listed",
            "default_registry",
            "registry_entry",
            "quality_status",
        }
        self.assertFalse(forbidden & set(nested_keys(self.template)))
        self.assertFalse(forbidden & set(nested_keys(self.submission_schema)))
        self.assertNotIn("decision", set(nested_keys(self.submission_schema)))

        self.assertEqual(
            self.commissions["claim_policy"]["curation"],
            "none",
        )
        self.assertEqual(
            self.agent["authority"],
            {
                "claim": "coordination-only",
                "technical_pass": "not-listing",
                "default_registry": "registry-entry-only",
            },
        )

        listed = next(
            branch
            for branch in self.quality_schema["allOf"]
            if branch.get("if", {})
            .get("properties", {})
            .get("default_registry", {})
            .get("properties", {})
            .get("status", {})
            .get("const")
            == "listed"
        )
        listed_requirements = listed["then"]["properties"]["default_registry"][
            "required"
        ]
        self.assertIn("evidence", listed_requirements)
        self.assertEqual(
            set(self.quality_schema["$defs"]["registryEvidence"]["required"]),
            {"registry_commit", "registry_sha256", "channel_id"},
        )

    def test_documentation_states_the_authority_boundaries(self):
        guide = (ROOT / "docs" / "CREATOR-INGRESS.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "RAPP Vision is the public brand",
            "claim announces intent",
            "technical pass is not a listing",
            "artifact.commit",
            "artifact.sha256",
            "raw-byte SHA-256",
            "canonical submitted-manifest digest",
            "protected workflow",
            "default-registry bytes",
            "stale",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), guide.lower())


if __name__ == "__main__":
    unittest.main()
