#!/usr/bin/env python3
"""Minimal legacy-policy verifier intended to run from a trusted git ref."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import posixpath
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


POLICY_PATH = "policy/legacy-publications.json"
REGISTRY_PATH = "channels.json"
POLICY_SCHEMA = "rapp-vision-legacy-publications/1.0"
POLICY_ID = "legacy-publications-2026-08-31"
FROZEN_AT = "2026-08-31T16:24:12Z"
REGISTRY_BASE = "https://kody-w.github.io/rapp-vision/channels.json"


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
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{ref}:{path}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def git_json(repo: Path, ref: str, path: str) -> Any:
    return json.loads(git_bytes(repo, ref, path))


def fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "rapp-vision-trusted-freeze/1.0"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return value


def publication_digest(publication: Any) -> str:
    canonical = json.dumps(
        normalize(publication),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def load_baseline_channel(
    repo: Path, ref: str, raw_url: str, canonical_url: str
) -> dict[str, Any]:
    parsed = urlparse(raw_url)
    repo_path = posixpath.normpath(parsed.path)
    if not parsed.scheme and not parsed.netloc and not repo_path.startswith("../"):
        return git_json(repo, ref, repo_path)
    return fetch_json(canonical_url)


def expected_bootstrap_policy(repo: Path, ref: str) -> dict[str, Any]:
    registry = git_json(repo, ref, REGISTRY_PATH)
    channels = []
    for entry in registry.get("channels", []):
        channel_id = entry.get("id")
        raw_url = entry.get("url", "")
        source = urljoin(REGISTRY_BASE, raw_url)
        channel = load_baseline_channel(repo, ref, raw_url, source)
        channels.append(
            {
                "id": channel_id,
                "source": source,
                "publications": [
                    {
                        "id": publication.get("id"),
                        "sha256": publication_digest(publication),
                    }
                    for publication in channel.get("videos", [])
                ],
            }
        )
    return {
        "schema": POLICY_SCHEMA,
        "id": POLICY_ID,
        "frozen_at": FROZEN_AT,
        "registry_base": REGISTRY_BASE,
        "channels": channels,
    }


def expected_transition_policy(
    repo: Path, ref: str, baseline: dict[str, Any]
) -> dict[str, Any]:
    registry = git_json(repo, ref, REGISTRY_PATH)
    entries = {entry.get("id"): entry for entry in registry.get("channels", [])}
    channels = []
    for record in baseline.get("channels", []):
        entry = entries.get(record.get("id"))
        if not entry:
            raise RuntimeError(f"baseline registry lacks {record.get('id')!r}")
        source = record.get("source")
        channel = load_baseline_channel(repo, ref, entry.get("url", ""), source)
        videos = {video.get("id"): video for video in channel.get("videos", [])}
        channels.append(
            {
                "id": record.get("id"),
                "source": source,
                "publications": [
                    {
                        "id": publication_id,
                        "sha256": publication_digest(videos[publication_id]),
                    }
                    for publication_id in record.get("publications", [])
                ],
            }
        )
    return {
        "schema": baseline.get("schema"),
        "id": baseline.get("id"),
        "frozen_at": baseline.get("frozen_at"),
        "registry_base": baseline.get("registry_base"),
        "channels": channels,
    }


def compare_frozen_bytes(candidate_bytes: bytes, baseline_bytes: bytes) -> list[str]:
    return [] if candidate_bytes == baseline_bytes else [
        "legacy policy bytes differ from the trusted baseline"
    ]


def verify(repo: Path, baseline_ref: str, candidate_ref: str) -> list[str]:
    try:
        candidate_bytes = git_bytes(repo, candidate_ref, POLICY_PATH)
        candidate = json.loads(candidate_bytes)
    except Exception as exc:
        return [f"candidate legacy policy is unreadable: {exc}"]

    if git_has_path(repo, baseline_ref, POLICY_PATH):
        try:
            baseline_bytes = git_bytes(repo, baseline_ref, POLICY_PATH)
            baseline = json.loads(baseline_bytes)
        except Exception as exc:
            return [f"trusted baseline legacy policy is unreadable: {exc}"]
        publications = [
            publication
            for record in baseline.get("channels", [])
            for publication in record.get("publications", [])
        ]
        if publications and all(isinstance(item, dict) for item in publications):
            return compare_frozen_bytes(candidate_bytes, baseline_bytes)
        try:
            expected = expected_transition_policy(repo, baseline_ref, baseline)
        except Exception as exc:
            return [f"cannot reconstruct trusted transition baseline: {exc}"]
    else:
        try:
            expected = expected_bootstrap_policy(repo, baseline_ref)
        except Exception as exc:
            return [f"cannot reconstruct trusted bootstrap baseline: {exc}"]

    return [] if normalize(candidate) == normalize(expected) else [
        "legacy policy does not exactly match the trusted baseline registry and publication digests"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--candidate-ref", required=True)
    args = parser.parse_args(argv)
    errors = verify(args.repo.resolve(), args.baseline_ref, args.candidate_ref)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(
        f"legacy freeze valid: {args.candidate_ref} matches trusted {args.baseline_ref}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
