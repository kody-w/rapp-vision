"""Tests for the verifier and workflow that never execute PR-controlled code."""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "trusted_legacy_freeze.py"
SPEC = importlib.util.spec_from_file_location("trusted_legacy_freeze", SCRIPT)
FREEZE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FREEZE)


class TestTrustedLegacyFreeze(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_bytes()
        cls.workflow = (
            ROOT / ".github" / "workflows" / "legacy-freeze.yml"
        ).read_bytes()
        cls.policy = (ROOT / FREEZE.POLICY_PATH).read_bytes()
        cls.root = {
            FREEZE.VERIFIER_PATH: cls.script,
            FREEZE.WORKFLOW_PATH: cls.workflow,
        }

    def test_stage_one_bootstrap_installs_only_trust_root(self):
        self.assertEqual(
            FREEZE.verify_snapshot(self.root, {}, bootstrap=True),
            [],
        )
        with_policy = {**self.root, FREEZE.POLICY_PATH: self.policy}
        self.assertTrue(any(
            "before policy" in error
            for error in FREEZE.verify_snapshot(with_policy, {}, bootstrap=True)
        ))

    def test_stage_two_allows_only_baked_initial_policy_digest(self):
        self.assertEqual(
            FREEZE.sha256(self.policy),
            FREEZE.INITIAL_POLICY_SHA256[FREEZE.POLICY_PATH],
        )
        exact = {**self.root, FREEZE.POLICY_PATH: self.policy}
        self.assertEqual(FREEZE.verify_snapshot(exact, self.root), [])
        changed = {**self.root, FREEZE.POLICY_PATH: self.policy + b"\n"}
        self.assertTrue(any(
            "does not match baked" in error
            for error in FREEZE.verify_snapshot(changed, self.root)
        ))

    def test_trust_root_modification_or_deletion_is_rejected(self):
        for path in FREEZE.TRUST_ROOT_PATHS:
            with self.subTest(path=path, operation="modify"):
                changed = dict(self.root)
                changed[path] += b"# weakened\n"
                self.assertTrue(any(
                    path in error
                    for error in FREEZE.verify_snapshot(changed, self.root)
                ))
            with self.subTest(path=path, operation="delete"):
                changed = dict(self.root)
                del changed[path]
                self.assertTrue(any(
                    path in error
                    for error in FREEZE.verify_snapshot(changed, self.root)
                ))

    def test_future_policy_change_or_deletion_is_rejected(self):
        baseline = {**self.root, FREEZE.POLICY_PATH: self.policy}
        self.assertEqual(FREEZE.verify_snapshot(dict(baseline), baseline), [])
        for candidate in (
            {**self.root, FREEZE.POLICY_PATH: self.policy + b" "},
            dict(self.root),
        ):
            self.assertTrue(any(
                "frozen legacy policy" in error
                for error in FREEZE.verify_snapshot(candidate, baseline)
            ))

    def test_pull_request_workflow_runs_only_base_checked_out_verifier(self):
        workflow = (
            ROOT / ".github" / "workflows" / "legacy-freeze.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("pull_request_target:", workflow)
        self.assertIn("github.event.pull_request.base.sha", workflow)
        self.assertIn("Fetch candidate object without checking it out", workflow)
        self.assertIn("python3 scripts/trusted_legacy_freeze.py", workflow)
        self.assertNotIn("scripts/validate_publications.py", workflow)

    def test_push_sources_verifier_and_baseline_from_event_before(self):
        workflow = (
            ROOT / ".github" / "workflows" / "legacy-freeze.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("BASE_SHA: ${{ github.event.before }}", workflow)
        self.assertIn('git show "$BASE_SHA:scripts/trusted_legacy_freeze.py"', workflow)
        self.assertNotIn("--baseline-ref HEAD^", workflow)
        self.assertIn("0000000000000000000000000000000000000000", workflow)
        self.assertIn("--bootstrap-check", workflow)

    def test_general_policy_workflow_has_no_security_claim_from_pr_code(self):
        workflow = (
            ROOT / ".github" / "workflows" / "publication-policy.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("--check-legacy-baseline", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
