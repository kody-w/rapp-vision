"""Semantic tests for artifact-bound creator submissions and quality records."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TINY = ROOT / "tiny-systems"
SCRIPT = ROOT / "scripts" / "validate_creator_submission.py"
PR_NUMBER = 42
PR_HEAD_SHA = "d" * 40
REVIEW_STATE_SHA256 = "e" * 64
TRUSTED_BASE_REF = "main"
TRUSTED_BASE_SHA = "f" * 40
SPEC = importlib.util.spec_from_file_location("validate_creator_submission", SCRIPT)
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules["validate_creator_submission"] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def submission() -> dict:
    publication_id = "one-block-three-trains"
    return {
        "$schema": "submission.schema.json",
        "schema": "rapp-vision-submission/1.0",
        "id": "tiny-systems-review",
        "phase": "submitted",
        "commission_id": "learn-grid-overflow",
        "creator": {
            "id": "agent-author",
            "display_name": "Agent Author",
            "github_user_id": 1001,
            "profile": "https://github.com/agent-author",
        },
        "pull_request": {
            "repository": "https://github.com/kody-w/rapp-vision",
            "head_ref": "creator/tiny-systems-review",
        },
        "claim": {
            "effect": "coordination-only",
            "curation": "none",
        },
        "artifact": {
            "repository": "https://github.com/kody-w/rapp-vision",
            "path": "tiny-systems/channel.json",
            "publication_id": publication_id,
            "commit": "a" * 40,
            "sha256": sha256(TINY / "channel.json"),
            "digest_scope": "raw-file-bytes",
        },
        "deliverables": {
            "mp4": {
                "path": f"tiny-systems/media/{publication_id}.mp4",
                "sha256": sha256(TINY / "media" / f"{publication_id}.mp4"),
            },
            "webm": {
                "path": f"tiny-systems/media/{publication_id}.webm",
                "sha256": sha256(TINY / "media" / f"{publication_id}.webm"),
            },
            "live": {
                "channel_path": "tiny-systems/channel.json",
                "publication_id": publication_id,
                "kind": "rapp-vision-live/1.0",
            },
        },
        "evidence": {
            "objective_evidence": {
                "criterion": "The accepted state survives a rejected request.",
                "observed": "The browser replay preserved train A after rejecting B.",
                "evidence_path": "tiny-systems/evidence.json",
            },
            "positive_path": {
                "description": "Train A enters the clear block.",
                "live_scene_t": 0.8,
            },
            "visible_failure": {
                "description": "Train B is visibly rejected while A remains.",
                "live_scene_t": 2.8,
            },
            "exact_reset": {
                "steps": ["Activate Reset exactly."],
                "restored_state": "Three trains wait, the block is clear.",
                "live_scene_t": 8.7,
            },
        },
        "attestations": {
            "rights": {
                "attested": True,
                "statement": "All code and media are original.",
            },
            "privacy": {
                "attested": True,
                "statement": "The synthetic artifact contains no personal data.",
            },
            "no_secrets": True,
        },
        "review_request": {
            "minimum_approvals": 2,
            "required_roles": ["technical", "curation"],
            "independent_reviewers": True,
            "reviews": [
                {"role": "technical"},
                {"role": "curation"},
            ],
        },
    }


def quality_for(document: dict) -> dict:
    digest = VALIDATOR.canonical_digest(document)
    artifact = document["artifact"]
    review_binding = {
        "submission_sha256": digest,
        "artifact_commit": artifact["commit"],
        "artifact_sha256": artifact["sha256"],
    }
    return {
        "$schema": "quality.schema.json",
        "schema": "rapp-vision-quality/1.0",
        "id": "tiny-systems-quality",
        "submission_id": document["id"],
        "authority": {
            "kind": "protected-workflow",
            "repository": document["pull_request"]["repository"],
            "run_url": "https://github.com/kody-w/rapp-vision/actions/runs/1",
            "pull_request_number": PR_NUMBER,
            "pull_request_head_sha": PR_HEAD_SHA,
            "review_state_sha256": REVIEW_STATE_SHA256,
            "trusted_base_ref": TRUSTED_BASE_REF,
            "trusted_base_sha": TRUSTED_BASE_SHA,
            "check_name": "Creator Submission Review / review",
        },
        "binding": {
            "submission_sha256": digest,
            "artifact_repository": artifact["repository"],
            "artifact_path": artifact["path"],
            "publication_id": artifact["publication_id"],
            "artifact_commit": artifact["commit"],
            "artifact_sha256": artifact["sha256"],
        },
        "freshness": {
            "status": "current",
            "compared_submission_sha256": digest,
            "compared_commit": artifact["commit"],
            "compared_sha256": artifact["sha256"],
            "stale_when": {
                "submission_sha256_changes": True,
                "artifact_commit_changes": True,
                "artifact_sha256_changes": True,
            },
        },
        "technical": {
            "status": "pass",
            "checks": [
                {
                    "id": "publication-contract",
                    "status": "pass",
                    "evidence": "validator output",
                }
            ],
            "reviews": [
                {
                    "reviewer": "agent-technical",
                    "reviewer_github_user_id": 2001,
                    "role": "technical",
                    "decision": "pass",
                    **review_binding,
                },
                {
                    "reviewer": "agent-curation",
                    "reviewer_github_user_id": 2002,
                    "role": "curation",
                    "decision": "pass",
                    **review_binding,
                },
            ],
            "quorum": {
                "minimum_approvals": 2,
                "required_roles": ["technical", "curation"],
                "independent_reviewers": True,
                "met": True,
            },
        },
        "default_registry": {
            "status": "requested",
            "registry": "channels.json",
            "authority": "registry-entry-only",
        },
    }


def validate(
    document: dict,
    *,
    expected_pr_number: int | None = None,
    probe_runner=None,
    artifact_root: Path = ROOT,
) -> list[str]:
    if probe_runner is None:
        def probe_runner(command, **_kwargs):
            codec = "h264" if command[-1].endswith(".mp4") else "vp9"
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"codec_name": codec}]}),
                stderr="",
            )

    return VALIDATOR.validate_submission(
        document,
        artifact_root,
        expected_pr_number=expected_pr_number,
        checkout_commit=document.get("artifact", {}).get("commit"),
        checkout_repository=document.get("artifact", {}).get("repository"),
        probe_runner=probe_runner,
    )


class TestCreatorSubmission(unittest.TestCase):
    def test_symlink_components_cannot_alias_tracked_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            (real / "channel.json").write_text("{}", encoding="utf-8")
            alias = root / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            errors = []
            resolved = VALIDATOR.resolve_artifact_path(
                root,
                "alias/channel.json",
                "artifact",
                errors,
            )
            self.assertIsNone(resolved)
            self.assertTrue(any("symlink" in error for error in errors))

    def test_valid_submission_binds_selected_paired_publication(self):
        document = submission()
        self.assertEqual(validate(document), [])
        self.assertEqual(
            VALIDATOR.canonical_digest(document),
            VALIDATOR.canonical_digest(copy.deepcopy(document)),
        )

    def test_same_publication_and_raw_digests_are_enforced(self):
        document = submission()
        document["deliverables"]["live"]["publication_id"] = (
            "three-tokens-make-nine"
        )
        document["deliverables"]["mp4"]["path"] = (
            "tiny-systems/media/three-tokens-make-nine.mp4"
        )
        document["deliverables"]["mp4"]["sha256"] = sha256(
            TINY / "media" / "three-tokens-make-nine.mp4"
        )
        errors = validate(document)
        self.assertTrue(any("must match artifact.publication_id" in error for error in errors))
        self.assertTrue(any("must exactly match" in error for error in errors))

        document = submission()
        document["artifact"]["sha256"] = "0" * 64
        self.assertTrue(
            any(
                "digest mismatch" in error
                for error in validate(document)
            )
        )

    def test_media_codec_is_probed_not_inferred_from_extension(self):
        document = submission()

        def wrong_codec(command, **_kwargs):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"codec_name": "av1"}]}),
                stderr="",
            )

        errors = validate(document, probe_runner=wrong_codec)
        self.assertTrue(any("expected 'h264'" in error for error in errors))
        self.assertTrue(any("expected 'vp9'" in error for error in errors))

    def test_duplicate_codec_and_encoded_dot_sources_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary)
            copied = artifact_root / "tiny-systems"
            shutil.copytree(TINY, copied)
            channel_path = copied / "channel.json"
            channel = json.loads(channel_path.read_text(encoding="utf-8"))
            selected = channel["videos"][0]
            selected["sources"].append(
                {
                    "src": "media/duplicate.mp4",
                    "type": "video/mp4",
                }
            )
            shutil.copy2(
                copied / "media" / "one-block-three-trains.mp4",
                copied / "media" / "duplicate.mp4",
            )
            channel_path.write_text(json.dumps(channel), encoding="utf-8")
            document = submission()
            document["artifact"]["sha256"] = sha256(channel_path)
            errors = validate(document, artifact_root=artifact_root)
            self.assertTrue(
                any("exactly one video/mp4" in error for error in errors)
            )

            selected["sources"] = [
                {
                    "src": "nested/%2e%2e/media/one-block-three-trains.mp4",
                    "type": "video/mp4",
                },
                selected["sources"][1],
            ]
            channel_path.write_text(json.dumps(channel), encoding="utf-8")
            document["artifact"]["sha256"] = sha256(channel_path)
            errors = validate(document, artifact_root=artifact_root)
            self.assertTrue(
                any("repository-owned relative path" in error for error in errors)
            )

    def test_pr_number_is_transport_derived_not_required_at_creation(self):
        document = submission()
        self.assertEqual(validate(document), [])
        errors = validate(
            document,
            expected_pr_number=42,
        )
        self.assertEqual(errors, [])
        document["pull_request"]["number"] = 42
        self.assertEqual(validate(document, expected_pr_number=42), [])
        document["pull_request"]["number"] = 41
        self.assertTrue(
            any(
                "enclosing pull request 42" in error
                for error in validate(document, expected_pr_number=42)
            )
        )

    def test_checkout_repository_and_commit_are_not_self_asserted(self):
        document = submission()
        errors = VALIDATOR.validate_submission(
            document,
            ROOT,
            checkout_commit="b" * 40,
            checkout_repository="https://github.com/other/repository",
        )
        self.assertTrue(any("checkout HEAD" in error for error in errors))
        self.assertTrue(any("checkout remote" in error for error in errors))

    def test_required_submission_objects_are_semantically_checked(self):
        document = submission()
        del document["artifact"]["repository"]
        del document["evidence"]["positive_path"]
        errors = validate(document)
        self.assertTrue(any("artifact.repository" in error for error in errors))
        self.assertTrue(any("evidence.positive_path" in error for error in errors))

    def test_copyable_template_fails_closed(self):
        template = json.loads(
            (ROOT / "template" / "submission.json").read_text(encoding="utf-8")
        )
        errors = VALIDATOR.validate_submission(
            template,
            ROOT,
            checkout_commit="a" * 40,
            checkout_repository="https://github.com/kody-w/rapp-vision",
            probe_runner=lambda command, **_kwargs: subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"codec_name": "h264"}]}),
                stderr="",
            ),
        )
        self.assertTrue(any("unresolved template sentinel" in error for error in errors))
        self.assertTrue(any("must be true" in error for error in errors))


class TestCreatorQuality(unittest.TestCase):
    def validate(self, document, quality):
        return VALIDATOR.validate_quality(
            document,
            quality,
            authority_repository="https://github.com/kody-w/rapp-vision",
            authority_run_url=(
                "https://github.com/kody-w/rapp-vision/actions/runs/1"
            ),
            authority_pull_request_number=PR_NUMBER,
            authority_pull_request_head_sha=PR_HEAD_SHA,
            authority_review_state_sha256=REVIEW_STATE_SHA256,
            authority_trusted_base_ref=TRUSTED_BASE_REF,
            authority_trusted_base_sha=TRUSTED_BASE_SHA,
        )

    def test_valid_quality_is_bound_and_quorum_is_derived(self):
        document = submission()
        quality = quality_for(document)
        self.assertEqual(self.validate(document, quality), [])

    def test_any_submission_change_stales_the_quality_binding(self):
        document = submission()
        quality = quality_for(document)
        document["evidence"]["objective_evidence"]["observed"] += " Revised."
        errors = self.validate(document, quality)
        self.assertTrue(any("submission_sha256" in error for error in errors))

    def test_creator_or_duplicate_reviewer_cannot_make_quorum(self):
        document = submission()
        quality = quality_for(document)
        quality["technical"]["reviews"][1]["reviewer"] = "agent-technical"
        quality["technical"]["reviews"][1]["reviewer_github_user_id"] = 2001
        errors = self.validate(document, quality)
        self.assertTrue(any("must be distinct" in error for error in errors))
        self.assertTrue(any("complete independent quorum" in error for error in errors))

        quality = quality_for(document)
        quality["technical"]["reviews"][0]["reviewer"] = document["creator"]["id"]
        quality["technical"]["reviews"][0]["reviewer_github_user_id"] = (
            document["creator"]["github_user_id"]
        )
        errors = self.validate(document, quality)
        self.assertTrue(any("creator cannot approve" in error for error in errors))

        quality = quality_for(document)
        del quality["technical"]["reviews"][0]["reviewer"]
        del quality["technical"]["reviews"][0]["reviewer_github_user_id"]
        errors = self.validate(document, quality)
        self.assertTrue(any("authenticated reviewer id" in error for error in errors))
        self.assertTrue(any("complete independent quorum" in error for error in errors))

    def test_failed_check_cannot_coexist_with_technical_pass(self):
        document = submission()
        quality = quality_for(document)
        quality["technical"]["checks"][0]["status"] = "fail"
        errors = self.validate(document, quality)
        self.assertTrue(any("all checks to pass" in error for error in errors))
        self.assertTrue(any("complete independent quorum" in error for error in errors))

    def test_quality_cannot_lower_submission_quorum(self):
        document = submission()
        document["review_request"]["minimum_approvals"] = 3
        quality = quality_for(document)
        quality["technical"]["quorum"]["minimum_approvals"] = 2
        errors = self.validate(document, quality)
        self.assertTrue(
            any("minimum_approvals: must match submission" in error for error in errors)
        )
        self.assertTrue(any("complete independent quorum" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
