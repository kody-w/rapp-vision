#!/usr/bin/env python3
"""Review a creator PR from trusted base code and emit an artifact-bound quality record."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import validate_creator_submission as validator


MANIFEST_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
REVIEW_MARKER = re.compile(
    r"<!--\s*rapp-vision-review\s+"
    r"role=(technical|curation)\s+"
    r"submission_sha256=([0-9a-f]{64})\s*-->",
    re.IGNORECASE,
)


def extract_manifest(body: str) -> dict:
    match = MANIFEST_BLOCK.search(body or "")
    if not match:
        raise ValueError("pull request body has no fenced json submission manifest")
    try:
        document = json.loads(
            match.group(1),
            object_pairs_hook=validator._object_without_duplicates,
            parse_constant=validator._reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"pull request submission manifest is invalid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("pull request submission manifest must be an object")
    return document


def _run(command: list[str], *, cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise ValueError(f"could not run {command[0]}: {exc}") from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(
            f"{' '.join(command)} failed: {detail or completed.returncode}"
        )
    return completed.stdout.strip()


def checkout_artifact(document: dict, destination: Path) -> tuple[str, str]:
    artifact = document.get("artifact") or {}
    repository = str(artifact.get("repository") or "")
    parsed = urlsplit(repository)
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or len([part for part in parsed.path.split("/") if part]) != 2
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("artifact.repository must be a public https://github.com/owner/repo URL")
    commit = str(artifact.get("commit") or "")
    if validator.COMMIT_RE.fullmatch(commit) is None:
        raise ValueError("artifact.commit must be a full 40- or 64-hex commit id")

    destination.mkdir()
    _run(["git", "init", "--quiet"], cwd=destination)
    _run(["git", "remote", "add", "origin", repository], cwd=destination)
    _run(
        [
            "git",
            "fetch",
            "--quiet",
            "--depth=1",
            "--filter=blob:none",
            "origin",
            commit,
        ],
        cwd=destination,
    )
    _run(["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"], cwd=destination)
    return validator.git_checkout_context(destination)


def fetch_reviews(
    repository: str,
    pull_request_number: int,
    token: str,
    *,
    api_url: str = "https://api.github.com",
) -> list[dict]:
    if not token:
        raise ValueError("GITHUB_TOKEN is required to derive authenticated reviews")
    reviews = []
    for page in range(1, 101):
        url = (
            f"{api_url.rstrip('/')}/repos/{repository}/pulls/"
            f"{pull_request_number}/reviews?per_page=100&page={page}"
        )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "rapp-vision-creator-review/1.0",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"could not fetch authenticated pull request reviews: {exc}"
            ) from exc
        if not isinstance(payload, list):
            raise ValueError("GitHub review response was not an array")
        reviews.extend(payload)
        if len(payload) < 100:
            return reviews
    raise ValueError("pull request review pagination exceeded 100 pages")


def derive_reviews(
    raw_reviews: list[dict],
    submission_sha256: str,
    artifact: dict,
) -> list[dict]:
    latest_by_reviewer: dict[int, dict] = {}
    for review in raw_reviews:
        if not isinstance(review, dict):
            continue
        user = review.get("user") or {}
        login = str(user.get("login") or "")
        github_user_id = user.get("id")
        if (
            not validator._valid_id(login)
            or isinstance(github_user_id, bool)
            or not isinstance(github_user_id, int)
            or github_user_id < 1
        ):
            continue
        previous = latest_by_reviewer.get(github_user_id)
        ordering = (
            str(review.get("submitted_at") or ""),
            int(review.get("id") or 0),
        )
        previous_ordering = (
            str((previous or {}).get("submitted_at") or ""),
            int((previous or {}).get("id") or 0),
        )
        if previous is None or ordering >= previous_ordering:
            latest_by_reviewer[github_user_id] = review

    derived = []
    for github_user_id, review in sorted(latest_by_reviewer.items()):
        login = str((review.get("user") or {}).get("login") or "")
        if str(review.get("state") or "").upper() != "APPROVED":
            continue
        marker = REVIEW_MARKER.search(str(review.get("body") or ""))
        if not marker or marker.group(2).lower() != submission_sha256:
            continue
        derived.append(
            {
                "reviewer": login,
                "reviewer_github_user_id": github_user_id,
                "role": marker.group(1).lower(),
                "decision": "pass",
                "submission_sha256": submission_sha256,
                "artifact_commit": artifact.get("commit"),
                "artifact_sha256": artifact.get("sha256"),
                "note": f"Authenticated GitHub review {review.get('html_url') or review.get('id')}",
            }
        )
    return derived


def review_state_digest(raw_reviews: list[dict]) -> str:
    state = []
    for review in raw_reviews:
        if not isinstance(review, dict):
            continue
        user = review.get("user") or {}
        state.append(
            {
                "id": review.get("id"),
                "submitted_at": review.get("submitted_at"),
                "state": review.get("state"),
                "body": review.get("body"),
                "user_id": user.get("id"),
                "user_login": user.get("login"),
            }
        )
    state.sort(key=lambda item: (str(item.get("submitted_at") or ""), int(item.get("id") or 0)))
    return validator.canonical_digest(state)


def creator_identity_errors(submission: dict, pull_request: dict) -> list[str]:
    creator = submission.get("creator") or {}
    author = pull_request.get("user") or {}
    errors = []
    if str(creator.get("id") or "").casefold() != str(
        author.get("login") or ""
    ).casefold():
        errors.append(
            "submission.creator.id must match the authenticated pull request author"
        )
    if creator.get("github_user_id") != author.get("id"):
        errors.append(
            "submission.creator.github_user_id must match the authenticated "
            "pull request author"
        )
    return errors


def build_quality(
    submission: dict,
    submission_errors: list[str],
    reviews: list[dict],
    *,
    authority_repository: str,
    authority_run_url: str,
    pull_request_number: int,
    pull_request_head_sha: str,
    review_state_sha256: str,
    trusted_base_ref: str,
    trusted_base_sha: str,
) -> dict:
    artifact = submission.get("artifact") or {}
    digest = validator.canonical_digest(submission)
    review_request = submission.get("review_request") or {}
    minimum = review_request.get("minimum_approvals", 2)
    required_roles = review_request.get(
        "required_roles",
        ["technical", "curation"],
    )
    reviewer_ids = [
        review.get("reviewer_github_user_id") for review in reviews
    ]
    roles = {review.get("role") for review in reviews}
    quorum_met = (
        not submission_errors
        and isinstance(minimum, int)
        and not isinstance(minimum, bool)
        and len(reviews) >= minimum
        and validator.REVIEW_ROLES <= roles
        and len(reviewer_ids) == len(set(reviewer_ids))
        and submission.get("creator", {}).get("github_user_id") not in reviewer_ids
    )
    check_status = "pass" if not submission_errors else "fail"
    evidence = (
        "Semantic submission and immutable artifact checks passed."
        if not submission_errors
        else "; ".join(submission_errors)
    )
    return {
        "$schema": "quality.schema.json",
        "schema": validator.QUALITY_SCHEMA,
        "id": f"{submission.get('id', 'submission')}-quality",
        "submission_id": submission.get("id"),
        "authority": {
            "kind": "protected-workflow",
            "repository": authority_repository,
            "run_url": authority_run_url,
            "pull_request_number": pull_request_number,
            "pull_request_head_sha": pull_request_head_sha,
            "review_state_sha256": review_state_sha256,
            "trusted_base_ref": trusted_base_ref,
            "trusted_base_sha": trusted_base_sha,
            "check_name": "Creator Submission Review / review",
        },
        "binding": {
            "submission_sha256": digest,
            "artifact_repository": artifact.get("repository"),
            "artifact_path": artifact.get("path"),
            "publication_id": artifact.get("publication_id"),
            "artifact_commit": artifact.get("commit"),
            "artifact_sha256": artifact.get("sha256"),
        },
        "freshness": {
            "status": "current",
            "compared_submission_sha256": digest,
            "compared_commit": artifact.get("commit"),
            "compared_sha256": artifact.get("sha256"),
            "stale_when": {
                "submission_sha256_changes": True,
                "artifact_commit_changes": True,
                "artifact_sha256_changes": True,
            },
        },
        "technical": {
            "status": (
                "fail"
                if submission_errors
                else ("pass" if quorum_met else "pending")
            ),
            "checks": [
                {
                    "id": "submission-semantic",
                    "status": check_status,
                    "evidence": evidence,
                }
            ],
            "reviews": reviews,
            "quorum": {
                "minimum_approvals": minimum,
                "required_roles": required_roles,
                "independent_reviewers": True,
                "met": quorum_met,
            },
        },
        "default_registry": {
            "status": "not-requested",
            "registry": "channels.json",
            "authority": "registry-entry-only",
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--server-url", default="https://github.com")
    parser.add_argument("--api-url", default="https://api.github.com")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trusted-base-ref", required=True)
    parser.add_argument("--trusted-base-sha", required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        event = validator.load_json(args.event)
        pull_request = (event or {}).get("pull_request") or {}
        number = pull_request.get("number")
        if not isinstance(number, int) or isinstance(number, bool):
            raise ValueError("event pull request number is unavailable")
        pull_request_head_sha = str(
            (pull_request.get("head") or {}).get("sha") or ""
        )
        if validator.COMMIT_RE.fullmatch(pull_request_head_sha) is None:
            raise ValueError("event pull request head SHA is unavailable")
        if validator.COMMIT_RE.fullmatch(args.trusted_base_sha) is None:
            raise ValueError("trusted base SHA is invalid")
        if not args.trusted_base_ref.strip():
            raise ValueError("trusted base ref is unavailable")
        submission = extract_manifest(pull_request.get("body") or "")
        if submission.get("phase") == "claim":
            errors = validator.validate_submission(
                submission,
                Path("."),
                expected_pr_number=number,
            )
            errors.extend(creator_identity_errors(submission, pull_request))
            if errors:
                raise ValueError("; ".join(errors))
            print(
                "claim manifest is valid; review check remains incomplete "
                "until submission and quorum"
            )
            return 1
        if submission.get("phase") != "submitted":
            raise ValueError("submission phase must be claim or submitted")

        with tempfile.TemporaryDirectory(prefix="rapp-vision-artifact-") as temporary:
            artifact_root = Path(temporary) / "checkout"
            checkout_commit, checkout_repository = checkout_artifact(
                submission,
                artifact_root,
            )
            submission_errors = validator.validate_submission(
                submission,
                artifact_root,
                expected_pr_number=number,
                checkout_commit=checkout_commit,
                checkout_repository=checkout_repository,
            )
            submission_errors.extend(
                creator_identity_errors(submission, pull_request)
            )

        digest = validator.canonical_digest(submission)
        raw_reviews = fetch_reviews(
            args.repository,
            number,
            os.environ.get("GITHUB_TOKEN", ""),
            api_url=args.api_url,
        )
        review_digest = review_state_digest(raw_reviews)
        reviews = derive_reviews(raw_reviews, digest, submission.get("artifact") or {})
        authority_repository = (
            f"{args.server_url.rstrip('/')}/{args.repository}"
        )
        authority_run_url = (
            f"{authority_repository}/actions/runs/{args.run_id}"
        )
        quality = build_quality(
            submission,
            submission_errors,
            reviews,
            authority_repository=authority_repository,
            authority_run_url=authority_run_url,
            pull_request_number=number,
            pull_request_head_sha=pull_request_head_sha,
            review_state_sha256=review_digest,
            trusted_base_ref=args.trusted_base_ref,
            trusted_base_sha=args.trusted_base_sha,
        )
        quality_errors = validator.validate_quality(
            submission,
            quality,
            authority_repository=authority_repository,
            authority_run_url=authority_run_url,
            authority_pull_request_number=number,
            authority_pull_request_head_sha=pull_request_head_sha,
            authority_review_state_sha256=review_digest,
            authority_trusted_base_ref=args.trusted_base_ref,
            authority_trusted_base_sha=args.trusted_base_sha,
        )
        if quality_errors:
            raise ValueError(
                "generated quality record failed validation: "
                + "; ".join(quality_errors)
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(quality, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(
            f"quality artifact: {quality['technical']['status']} "
            f"({len(reviews)} authenticated review(s))"
        )
        return 0 if quality["technical"]["status"] == "pass" else 1
    except ValueError as exc:
        print(f"review_creator_submission: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
