#!/usr/bin/env python3
"""Two-stage trust-root verifier for the immutable legacy publication policy."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path


VERIFIER_PATH = "scripts/trusted_legacy_freeze.py"
WORKFLOW_PATH = ".github/workflows/legacy-freeze.yml"
POLICY_PATH = "policy/legacy-publications.json"
TRUST_ROOT_PATHS = (VERIFIER_PATH, WORKFLOW_PATH)
INSPECTED_PATHS = TRUST_ROOT_PATHS + (POLICY_PATH,)
ZERO_SHA = "0" * 40

# Stage two may introduce this exact reviewed policy and no other. Once present
# in the trusted baseline, byte identity replaces this one-time digest gate.
INITIAL_POLICY_SHA256 = {
    POLICY_PATH: "1ec1cf780bf6f31c593da19d7ff4008313b5ed39add09137ec1c539169cd8a50",
}


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def git_bytes(repo: Path, ref: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"],
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        raise RuntimeError(
            completed.stderr.decode("utf-8", "replace").strip()
            or f"cannot read {path} from {ref}"
        )
    return completed.stdout


def git_has_path(repo: Path, ref: str, path: str) -> bool:
    if not ref or ref == ZERO_SHA:
        return False
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{ref}:{path}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def ref_snapshot(repo: Path, ref: str | None) -> dict[str, bytes]:
    if not ref or ref == ZERO_SHA:
        return {}
    return {
        path: git_bytes(repo, ref, path)
        for path in INSPECTED_PATHS
        if git_has_path(repo, ref, path)
    }


def verify_snapshot(
    candidate: dict[str, bytes],
    baseline: dict[str, bytes],
    *,
    bootstrap: bool = False,
) -> list[str]:
    errors: list[str] = []
    for path in TRUST_ROOT_PATHS:
        if path not in candidate:
            errors.append(f"candidate deletes required trust-root file {path}")

    baseline_root = [path for path in TRUST_ROOT_PATHS if path in baseline]
    if bootstrap:
        if baseline_root:
            errors.append("bootstrap mode is forbidden after any trust-root file exists")
        if POLICY_PATH in baseline or POLICY_PATH in candidate:
            errors.append("bootstrap commit must install only the trust root before policy")
        return errors

    for path in TRUST_ROOT_PATHS:
        if path not in baseline:
            errors.append(f"trusted baseline lacks {path}; use the reviewed bootstrap commit")
        elif candidate.get(path) != baseline[path]:
            errors.append(f"candidate modifies protected trust-root file {path}")

    if POLICY_PATH in baseline:
        if candidate.get(POLICY_PATH) != baseline[POLICY_PATH]:
            errors.append("candidate modifies or deletes the frozen legacy policy")
    elif POLICY_PATH in candidate:
        expected = INITIAL_POLICY_SHA256[POLICY_PATH]
        actual = sha256(candidate[POLICY_PATH])
        if actual != expected:
            errors.append(
                f"initial {POLICY_PATH} digest {actual} does not match baked {expected}"
            )
    return errors


def verify(
    repo: Path,
    candidate_ref: str,
    *,
    baseline_ref: str | None = None,
    bootstrap: bool = False,
) -> list[str]:
    try:
        candidate = ref_snapshot(repo, candidate_ref)
        baseline = ref_snapshot(repo, baseline_ref)
    except Exception as exc:
        return [f"cannot inspect git objects: {exc}"]
    return verify_snapshot(candidate, baseline, bootstrap=bootstrap)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--baseline-ref")
    parser.add_argument("--candidate-ref", required=True)
    parser.add_argument(
        "--bootstrap-check",
        action="store_true",
        help="verify the reviewed first-stage commit contains the trust root but no policy",
    )
    args = parser.parse_args(argv)
    errors = verify(
        args.repo.resolve(),
        args.candidate_ref,
        baseline_ref=args.baseline_ref,
        bootstrap=args.bootstrap_check,
    )
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    mode = "bootstrap" if args.bootstrap_check else "freeze"
    print(f"legacy {mode} valid: {args.candidate_ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
