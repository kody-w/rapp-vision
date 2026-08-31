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
    def test_frozen_policy_bytes_cannot_be_self_authorized(self):
        baseline = b'{"frozen":true}\n'
        self.assertEqual(FREEZE.compare_frozen_bytes(baseline, baseline), [])
        self.assertEqual(
            FREEZE.compare_frozen_bytes(
                b'{"frozen":true,"self_authorized":"new-v1"}\n',
                baseline,
            ),
            ["legacy policy bytes differ from the trusted baseline"],
        )

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

    def test_general_policy_workflow_has_no_security_claim_from_pr_code(self):
        workflow = (
            ROOT / ".github" / "workflows" / "publication-policy.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("--check-legacy-baseline", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
