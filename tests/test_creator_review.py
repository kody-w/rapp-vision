"""Tests for the trusted-base creator review workflow."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "review_creator_submission.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("review_creator_submission", SCRIPT)
REVIEW = importlib.util.module_from_spec(SPEC)
sys.modules["review_creator_submission"] = REVIEW
SPEC.loader.exec_module(REVIEW)


class TestCreatorReview(unittest.TestCase):
    def test_extracts_only_fenced_json_manifest(self):
        document = REVIEW.extract_manifest(
            "Before\n```json\n"
            + json.dumps({"schema": "rapp-vision-submission/1.0"})
            + "\n```\nAfter"
        )
        self.assertEqual(document["schema"], "rapp-vision-submission/1.0")
        with self.assertRaises(ValueError):
            REVIEW.extract_manifest('{"schema":"not-fenced"}')

    def test_derives_only_current_authenticated_approved_markers(self):
        digest = "a" * 64
        artifact = {"commit": "b" * 40, "sha256": "c" * 64}
        reviews = [
            {
                "id": 1,
                "state": "APPROVED",
                "body": (
                    "<!-- rapp-vision-review role=technical "
                    f"submission_sha256={digest} -->"
                ),
                "user": {"login": "reviewer-one", "id": 101},
                "html_url": "https://github.com/o/r/pull/1#pullrequestreview-1",
            },
            {
                "id": 2,
                "state": "APPROVED",
                "body": (
                    "<!-- rapp-vision-review role=curation "
                    f"submission_sha256={digest} -->"
                ),
                "user": {"login": "reviewer-two", "id": 102},
            },
            {
                "id": 3,
                "state": "CHANGES_REQUESTED",
                "body": (
                    "<!-- rapp-vision-review role=technical "
                    f"submission_sha256={digest} -->"
                ),
                "user": {"login": "reviewer-three", "id": 103},
            },
            {
                "id": 4,
                "state": "APPROVED",
                "body": (
                    "<!-- rapp-vision-review role=curation "
                    f"submission_sha256={'d' * 64} -->"
                ),
                "user": {"login": "stale-reviewer", "id": 104},
            },
        ]
        derived = REVIEW.derive_reviews(reviews, digest, artifact)
        self.assertEqual(
            {(review["reviewer"], review["role"]) for review in derived},
            {
                ("reviewer-one", "technical"),
                ("reviewer-two", "curation"),
            },
        )
        self.assertTrue(
            all(review["submission_sha256"] == digest for review in derived)
        )
        self.assertEqual(
            {review["reviewer_github_user_id"] for review in derived},
            {101, 102},
        )

    def test_creator_identity_comes_from_pull_request_actor(self):
        submission = {
            "creator": {"id": "author", "github_user_id": 77}
        }
        pull_request = {"user": {"login": "Author", "id": 77}}
        self.assertEqual(
            REVIEW.creator_identity_errors(submission, pull_request),
            [],
        )
        submission["creator"]["github_user_id"] = 88
        self.assertTrue(
            REVIEW.creator_identity_errors(submission, pull_request)
        )

    def test_review_state_digest_changes_when_approval_is_revoked(self):
        reviews = [
            {
                "id": 1,
                "submitted_at": "2026-09-02T12:00:00Z",
                "state": "APPROVED",
                "body": "approved",
                "user": {"login": "reviewer", "id": 101},
            }
        ]
        approved = REVIEW.review_state_digest(reviews)
        reviews[0]["state"] = "DISMISSED"
        dismissed = REVIEW.review_state_digest(reviews)
        self.assertNotEqual(approved, dismissed)

    def test_quality_status_revokes_when_quorum_disappears(self):
        submission = {
            "id": "submission",
            "creator": {"id": "author", "github_user_id": 77},
            "artifact": {
                "repository": "https://github.com/o/r",
                "path": "channel.json",
                "publication_id": "publication",
                "commit": "a" * 40,
                "sha256": "b" * 64,
            },
            "review_request": {
                "minimum_approvals": 2,
                "required_roles": ["technical", "curation"],
            },
        }
        binding = {
            "submission_sha256": REVIEW.validator.canonical_digest(submission),
            "artifact_commit": "a" * 40,
            "artifact_sha256": "b" * 64,
        }
        reviews = [
            {
                "reviewer": "reviewer-one",
                "reviewer_github_user_id": 101,
                "role": "technical",
                "decision": "pass",
                **binding,
            },
            {
                "reviewer": "reviewer-two",
                "reviewer_github_user_id": 102,
                "role": "curation",
                "decision": "pass",
                **binding,
            },
        ]
        context = {
            "authority_repository": "https://github.com/kody-w/rapp-vision",
            "authority_run_url": (
                "https://github.com/kody-w/rapp-vision/actions/runs/1"
            ),
            "pull_request_number": 1,
            "pull_request_head_sha": "c" * 40,
            "review_state_sha256": "d" * 64,
        }
        passed = REVIEW.build_quality(submission, [], reviews, **context)
        pending = REVIEW.build_quality(submission, [], reviews[:1], **context)
        self.assertEqual(passed["technical"]["status"], "pass")
        self.assertEqual(pending["technical"]["status"], "pending")
        self.assertIs(pending["technical"]["quorum"]["met"], False)

    def test_workflow_uses_trusted_base_and_read_only_permissions(self):
        workflow = (
            ROOT / ".github" / "workflows" / "creator-submission-review.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("pull_request_target:", workflow)
        self.assertIn("pull_request_review:", workflow)
        self.assertIn("types: [submitted, edited, dismissed]", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("pull-requests: read", workflow)
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("--event \"$GITHUB_EVENT_PATH\"", workflow)
        self.assertIn("--repository \"$GITHUB_REPOSITORY\"", workflow)
        self.assertIn("--run-id \"$GITHUB_RUN_ID\"", workflow)
        self.assertNotIn("github.event.pull_request.head", workflow)
        self.assertNotIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
