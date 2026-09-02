#!/usr/bin/env python3
"""Validate RAPP Vision claim/submission manifests and derived quality records."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_VALIDATOR = ROOT / "scripts" / "validate_publications.py"
SUBMISSION_SCHEMA = "rapp-vision-submission/1.0"
QUALITY_SCHEMA = "rapp-vision-quality/1.0"
REVIEW_ROLES = {"technical", "curation"}
RAPP_VISION_REPOSITORY = "https://github.com/kody-w/rapp-vision"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _load_publication_validator():
    spec = importlib.util.spec_from_file_location(
        "_rapp_submission_publication_validator",
        PUBLICATION_VALIDATOR,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"cannot load publication validator: {PUBLICATION_VALIDATOR}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_publication_validator()


class DuplicateKey(ValueError):
    pass


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ValueError(f"non-standard JSON number {value!r}")


def load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def canonical_digest(document: Any) -> str:
    body = json.dumps(
        document,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_codec(
    path: Path | None,
    expected: str,
    label: str,
    errors: list[str],
    *,
    ffprobe: str,
    runner,
) -> None:
    if path is None or not path.is_file():
        return
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        errors.append(f"{label}: ffprobe failed to start: {exc}")
        return
    if completed.returncode:
        detail = (completed.stderr or "").strip() or completed.returncode
        errors.append(f"{label}: ffprobe failed: {detail}")
        return
    try:
        streams = json.loads(completed.stdout or "").get("streams", [])
        codec = streams[0].get("codec_name") if len(streams) == 1 else None
    except (AttributeError, IndexError, json.JSONDecodeError):
        codec = None
    if codec != expected:
        errors.append(f"{label}: expected {expected!r} video codec, found {codec!r}")


def _control_character(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def resolve_artifact_path(
    root: Path,
    raw: Any,
    label: str,
    errors: list[str],
) -> Path | None:
    if not isinstance(raw, str) or not raw:
        errors.append(f"{label}: must be a non-empty repository-relative path")
        return None
    windows = PureWindowsPath(raw)
    posix = PurePosixPath(raw)
    if (
        "\\" in raw
        or _control_character(raw)
        or windows.drive
        or windows.is_absolute()
        or posix.is_absolute()
        or any(part in ("", ".", "..") for part in posix.parts)
        or urlsplit(raw).scheme
        or raw.startswith("//")
    ):
        errors.append(f"{label}: must be a safe repository-relative path")
        return None
    try:
        resolved = root.joinpath(*posix.parts).resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        errors.append(f"{label}: escapes the artifact checkout")
        return None
    return resolved


def resolve_channel_reference(
    root: Path,
    channel_path: Path,
    raw: Any,
    label: str,
    errors: list[str],
) -> tuple[Path | None, str | None]:
    if not isinstance(raw, str):
        errors.append(f"{label}: must be a repository-owned relative path")
        return None, None
    parsed = urlsplit(raw)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or raw.startswith("/")
        or "\\" in raw
        or _control_character(raw)
        or "%" in raw
    ):
        errors.append(
            f"{label}: immutable submissions require a repository-owned "
            "relative path"
        )
        return None, None
    try:
        relative_to_channel = channel_path.parent.joinpath(
            *PurePosixPath(parsed.path).parts
        ).resolve()
        relative_to_channel.relative_to(root)
    except (OSError, ValueError):
        errors.append(f"{label}: escapes the artifact checkout")
        return None, None
    try:
        repository_relative = relative_to_channel.relative_to(root).as_posix()
    except ValueError:
        errors.append(f"{label}: escapes the artifact checkout")
        return None, None
    return relative_to_channel, repository_relative


def normalize_repository_url(value: str) -> str:
    value = str(value or "").strip()
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value[len("git@github.com:") :]
    if value.startswith("ssh://git@github.com/"):
        value = "https://github.com/" + value[len("ssh://git@github.com/") :]
    return value.removesuffix(".git").rstrip("/")


def git_checkout_context(root: Path) -> tuple[str, str]:
    root = root.resolve()

    def run(*arguments: str) -> str:
        try:
            completed = subprocess.run(
                ["git", "-C", str(root), *arguments],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise ValueError(f"cannot inspect artifact checkout: {exc}") from exc
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            raise ValueError(
                f"cannot inspect artifact checkout with git {' '.join(arguments)}: "
                f"{detail or completed.returncode}"
            )
        return completed.stdout.strip()

    top = Path(run("rev-parse", "--show-toplevel")).resolve()
    if top != root:
        raise ValueError(
            f"artifact root must be the checkout root {top}, not {root}"
        )
    status = run("status", "--porcelain", "--untracked-files=all")
    if status:
        raise ValueError("artifact checkout must be clean and pinned to one commit")
    commit = run("rev-parse", "HEAD")
    repository = normalize_repository_url(run("config", "--get", "remote.origin.url"))
    if not repository:
        raise ValueError("artifact checkout has no remote.origin.url")
    return commit, repository


def _walk_strings(value: Any, prefix: str = "submission") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).startswith("_"):
                continue
            yield from _walk_strings(child, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{prefix}[{index}]")
    elif isinstance(value, str):
        yield prefix, value


def _mapping(value: Any, label: str, errors: list[str]) -> dict:
    if not isinstance(value, dict):
        errors.append(f"{label}: must be an object")
        return {}
    return value


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and ID_RE.fullmatch(value) is not None


def _expected_hash(
    path: Path | None,
    expected: Any,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
        errors.append(f"{label}: must be a lowercase SHA-256")
        return
    if path is None:
        return
    if not path.is_file():
        errors.append(f"{label}: artifact file does not exist: {path}")
        return
    actual = file_digest(path)
    if actual != expected:
        errors.append(f"{label}: digest mismatch; expected {expected}, found {actual}")


def validate_submission(
    document: Any,
    artifact_root: Path,
    *,
    expected_pr_number: int | None = None,
    checkout_commit: str | None = None,
    checkout_repository: str | None = None,
    ffprobe: str = "ffprobe",
    probe_runner=None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["submission: must be an object"]
    if document.get("schema") != SUBMISSION_SCHEMA:
        errors.append(f"submission.schema: must equal {SUBMISSION_SCHEMA!r}")
    if document.get("$schema") != "submission.schema.json":
        errors.append("submission.$schema: must equal 'submission.schema.json'")
    for key in ("id", "commission_id"):
        if not _valid_id(document.get(key)):
            errors.append(f"submission.{key}: must be a collision-safe id")

    creator = _mapping(document.get("creator"), "submission.creator", errors)
    if not _valid_id(creator.get("id")):
        errors.append("submission.creator.id: must be a collision-safe id")
    if not isinstance(creator.get("display_name"), str) or not creator.get(
        "display_name", ""
    ).strip():
        errors.append("submission.creator.display_name: must be non-empty")
    creator_github_user_id = creator.get("github_user_id")
    if (
        isinstance(creator_github_user_id, bool)
        or not isinstance(creator_github_user_id, int)
        or creator_github_user_id < 1
    ):
        errors.append(
            "submission.creator.github_user_id: must be a positive GitHub user id"
        )
    pull_request = _mapping(
        document.get("pull_request"),
        "submission.pull_request",
        errors,
    )
    number = pull_request.get("number")
    if pull_request.get("repository") != RAPP_VISION_REPOSITORY:
        errors.append(
            f"submission.pull_request.repository: must equal {RAPP_VISION_REPOSITORY!r}"
        )
    if not isinstance(pull_request.get("head_ref"), str) or not pull_request.get(
        "head_ref", ""
    ).strip():
        errors.append("submission.pull_request.head_ref: must be non-empty")
    if number is not None and (
        isinstance(number, bool) or not isinstance(number, int) or number < 1
    ):
        errors.append("submission.pull_request.number: must be a positive integer")
    if (
        expected_pr_number is not None
        and number is not None
        and number != expected_pr_number
    ):
        errors.append(
            "submission.pull_request.number: does not match the enclosing "
            f"pull request {expected_pr_number}"
        )

    claim = _mapping(document.get("claim"), "submission.claim", errors)
    if claim.get("effect") != "coordination-only" or claim.get("curation") != "none":
        errors.append("submission.claim: claims coordinate only and confer no curation")

    phase = document.get("phase")
    if phase == "claim":
        forbidden = (
            "artifact",
            "deliverables",
            "evidence",
            "attestations",
            "review_request",
        )
        for key in forbidden:
            if key in document:
                errors.append(f"submission.{key}: is not allowed during claim phase")
        return errors
    if phase != "submitted":
        errors.append("submission.phase: must equal 'claim' or 'submitted'")
        return errors

    for location, value in _walk_strings(document):
        if "REPLACE" in value.upper():
            errors.append(f"{location}: unresolved template sentinel")

    artifact_root = artifact_root.resolve()
    if not artifact_root.is_dir():
        errors.append(f"artifact root does not exist: {artifact_root}")
        return errors

    artifact = _mapping(document.get("artifact"), "submission.artifact", errors)
    artifact_repository = artifact.get("repository")
    if not isinstance(artifact_repository, str) or not artifact_repository.startswith(
        "https://github.com/"
    ):
        errors.append(
            "submission.artifact.repository: must be an HTTPS GitHub repository"
        )
    if not _valid_id(artifact.get("publication_id")):
        errors.append("submission.artifact.publication_id: invalid id")
    if not isinstance(artifact.get("commit"), str) or not COMMIT_RE.fullmatch(
        artifact.get("commit", "")
    ):
        errors.append("submission.artifact.commit: must be a full commit id")
    if checkout_commit is None or checkout_repository is None:
        errors.append(
            "artifact checkout context is required to bind repository and commit"
        )
    else:
        if artifact.get("commit") != checkout_commit:
            errors.append(
                "submission.artifact.commit: does not match checkout HEAD "
                f"{checkout_commit}"
            )
        if normalize_repository_url(artifact_repository) != normalize_repository_url(
            checkout_repository
        ):
            errors.append(
                "submission.artifact.repository: does not match checkout remote "
                f"{checkout_repository}"
            )
    if artifact.get("digest_scope") != "raw-file-bytes":
        errors.append(
            "submission.artifact.digest_scope: must equal 'raw-file-bytes'"
        )
    channel_path = resolve_artifact_path(
        artifact_root,
        artifact.get("path"),
        "submission.artifact.path",
        errors,
    )
    _expected_hash(
        channel_path,
        artifact.get("sha256"),
        "submission.artifact.sha256",
        errors,
    )

    channel = None
    if channel_path is not None and channel_path.is_file():
        try:
            channel = load_json(channel_path)
        except ValueError as exc:
            errors.append(str(exc))
    if isinstance(channel, dict):
        try:
            errors.extend(
                VALIDATOR.validate_channel(
                    channel,
                    "https://artifact.invalid/channel.json",
                    {},
                )
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            errors.append(f"artifact channel is structurally invalid: {exc}")
    else:
        errors.append("submission.artifact.path: does not contain a channel object")

    publication = None
    if isinstance(channel, dict):
        matches = [
            video
            for video in channel.get("videos", [])
            if isinstance(video, dict)
            and video.get("id") == artifact.get("publication_id")
        ]
        if len(matches) != 1:
            errors.append(
                "submission.artifact.publication_id: must select exactly one "
                "publication in the channel"
            )
        else:
            publication = matches[0]

    deliverables = _mapping(
        document.get("deliverables"),
        "submission.deliverables",
        errors,
    )
    source_by_type: dict[str, list[tuple[Path | None, str | None]]] = {}
    if isinstance(publication, dict):
        for source in publication.get("sources", []):
            if not isinstance(source, dict):
                continue
            media_type = str(source.get("type", "")).split(";", 1)[0].strip()
            source_by_type.setdefault(media_type, []).append(
                resolve_channel_reference(
                    artifact_root,
                    channel_path,
                    source.get("src"),
                    f"artifact publication source {media_type}",
                    errors,
                )
            )

    for key, media_type, suffix in (
        ("mp4", "video/mp4", ".mp4"),
        ("webm", "video/webm", ".webm"),
    ):
        media = _mapping(
            deliverables.get(key),
            f"submission.deliverables.{key}",
            errors,
        )
        raw_path = media.get("path")
        if not isinstance(raw_path, str) or not raw_path.endswith(suffix):
            errors.append(
                f"submission.deliverables.{key}.path: must end with {suffix}"
            )
        candidates = source_by_type.get(media_type, [])
        if len(candidates) != 1:
            errors.append(
                f"artifact publication: expected exactly one {media_type} "
                f"source, found {len(candidates)}"
            )
        source_path, repository_relative = (
            candidates[0] if len(candidates) == 1 else (None, None)
        )
        if repository_relative != raw_path:
            errors.append(
                f"submission.deliverables.{key}.path: must exactly match the "
                f"selected publication's checkout-relative {media_type} source "
                f"{repository_relative!r}"
            )
        media_path = source_path
        _expected_hash(
            media_path,
            media.get("sha256"),
            f"submission.deliverables.{key}.sha256",
            errors,
        )
        probe_codec(
            media_path,
            "h264" if key == "mp4" else "vp9",
            f"submission.deliverables.{key}",
            errors,
            ffprobe=ffprobe,
            runner=probe_runner or subprocess.run,
        )

    live = _mapping(
        deliverables.get("live"),
        "submission.deliverables.live",
        errors,
    )
    if live.get("channel_path") != artifact.get("path"):
        errors.append(
            "submission.deliverables.live.channel_path: must match artifact.path"
        )
    if live.get("publication_id") != artifact.get("publication_id"):
        errors.append(
            "submission.deliverables.live.publication_id: must match "
            "artifact.publication_id"
        )
    expected_live_kind = (
        (publication.get("live") or {}).get("kind")
        if isinstance(publication, dict)
        else None
    )
    if live.get("kind") != expected_live_kind or expected_live_kind != (
        "rapp-vision-live/1.0"
    ):
        errors.append(
            "submission.deliverables.live.kind: must match the selected live replay"
        )
    if isinstance(publication, dict):
        for scene_index, scene in enumerate(
            (publication.get("live") or {}).get("scenes", [])
        ):
            if not isinstance(scene, dict) or "app" not in scene:
                continue
            app_path, _repository_relative = resolve_channel_reference(
                artifact_root,
                channel_path,
                scene.get("app"),
                (
                    "submission artifact live scene "
                    f"{scene_index} application"
                ),
                errors,
            )
            if app_path is not None and not app_path.is_file():
                errors.append(
                    f"submission artifact live scene {scene_index} application: "
                    f"file does not exist: {app_path}"
                )

    evidence = _mapping(document.get("evidence"), "submission.evidence", errors)
    objective = _mapping(
        evidence.get("objective_evidence"),
        "submission.evidence.objective_evidence",
        errors,
    )
    for key in ("criterion", "observed"):
        if not isinstance(objective.get(key), str) or not objective.get(
            key, ""
        ).strip():
            errors.append(
                f"submission.evidence.objective_evidence.{key}: must be non-empty"
            )
    evidence_path = resolve_artifact_path(
        artifact_root,
        objective.get("evidence_path"),
        "submission.evidence.objective_evidence.evidence_path",
        errors,
    )
    if evidence_path is not None and not evidence_path.is_file():
        errors.append(
            "submission.evidence.objective_evidence.evidence_path: "
            f"file does not exist: {evidence_path}"
        )
    for key in ("positive_path", "visible_failure"):
        path_evidence = _mapping(
            evidence.get(key),
            f"submission.evidence.{key}",
            errors,
        )
        if not isinstance(path_evidence.get("description"), str) or not (
            path_evidence.get("description", "").strip()
        ):
            errors.append(
                f"submission.evidence.{key}.description: must be non-empty"
            )
        scene_t = path_evidence.get("live_scene_t")
        if (
            isinstance(scene_t, bool)
            or not isinstance(scene_t, (int, float))
            or scene_t < 0
        ):
            errors.append(
                f"submission.evidence.{key}.live_scene_t: must be non-negative"
            )
    reset_evidence = _mapping(
        evidence.get("exact_reset"),
        "submission.evidence.exact_reset",
        errors,
    )
    steps = reset_evidence.get("steps")
    if (
        not isinstance(steps, list)
        or not steps
        or not all(isinstance(step, str) and step.strip() for step in steps)
    ):
        errors.append(
            "submission.evidence.exact_reset.steps: must contain non-empty steps"
        )
    if not isinstance(reset_evidence.get("restored_state"), str) or not (
        reset_evidence.get("restored_state", "").strip()
    ):
        errors.append(
            "submission.evidence.exact_reset.restored_state: must be non-empty"
        )
    reset_t = reset_evidence.get("live_scene_t")
    if (
        isinstance(reset_t, bool)
        or not isinstance(reset_t, (int, float))
        or reset_t < 0
    ):
        errors.append(
            "submission.evidence.exact_reset.live_scene_t: must be non-negative"
        )

    attestations = _mapping(
        document.get("attestations"),
        "submission.attestations",
        errors,
    )
    for key in ("rights", "privacy"):
        attestation = _mapping(
            attestations.get(key),
            f"submission.attestations.{key}",
            errors,
        )
        if attestation.get("attested") is not True:
            errors.append(f"submission.attestations.{key}.attested: must be true")
        if not isinstance(attestation.get("statement"), str) or not attestation.get(
            "statement", ""
        ).strip():
            errors.append(
                f"submission.attestations.{key}.statement: must be non-empty"
            )
    if attestations.get("no_secrets") is not True:
        errors.append("submission.attestations.no_secrets: must be true")

    review_request = _mapping(
        document.get("review_request"),
        "submission.review_request",
        errors,
    )
    roles = review_request.get("required_roles")
    if not isinstance(roles, list) or not REVIEW_ROLES <= set(roles):
        errors.append(
            "submission.review_request.required_roles: must include technical "
            "and curation"
        )
    if review_request.get("independent_reviewers") is not True:
        errors.append(
            "submission.review_request.independent_reviewers: must be true"
        )
    minimum_approvals = review_request.get("minimum_approvals")
    if (
        isinstance(minimum_approvals, bool)
        or not isinstance(minimum_approvals, int)
        or minimum_approvals < 2
    ):
        errors.append(
            "submission.review_request.minimum_approvals: must be at least 2"
        )
    requested_reviews = review_request.get("reviews")
    if not isinstance(requested_reviews, list):
        errors.append("submission.review_request.reviews: must be an array")
    else:
        requested_roles = {
            review.get("role")
            for review in requested_reviews
            if isinstance(review, dict)
        }
        if not REVIEW_ROLES <= requested_roles:
            errors.append(
                "submission.review_request.reviews: must request technical "
                "and curation roles"
            )
        assigned = [
            review.get("reviewer")
            for review in requested_reviews
            if isinstance(review, dict) and review.get("reviewer")
        ]
        if len(assigned) != len(set(assigned)):
            errors.append(
                "submission.review_request.reviews: assigned reviewers must be distinct"
            )
        if creator.get("id") in assigned:
            errors.append(
                "submission.review_request.reviews: creator cannot review their own work"
            )
    return errors


def validate_quality(
    submission: Any,
    quality: Any,
    *,
    authority_repository: str | None = None,
    authority_run_url: str | None = None,
    authority_pull_request_number: int | None = None,
    authority_pull_request_head_sha: str | None = None,
    authority_review_state_sha256: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(submission, dict):
        return ["submission: must be an object"]
    if not isinstance(quality, dict):
        return ["quality: must be an object"]
    if quality.get("schema") != QUALITY_SCHEMA:
        errors.append(f"quality.schema: must equal {QUALITY_SCHEMA!r}")
    if quality.get("submission_id") != submission.get("id"):
        errors.append("quality.submission_id: must match submission.id")

    authority = _mapping(quality.get("authority"), "quality.authority", errors)
    pull_request = submission.get("pull_request") or {}
    if authority.get("kind") != "protected-workflow":
        errors.append("quality.authority.kind: must equal 'protected-workflow'")
    if authority_repository is None or authority_run_url is None:
        errors.append(
            "trusted workflow repository and run URL context are required"
        )
    if authority.get("repository") != authority_repository:
        errors.append(
            "quality.authority.repository: does not match trusted workflow context"
        )
    if authority.get("repository") != pull_request.get("repository"):
        errors.append(
            "quality.authority.repository: must match the submission repository"
        )
    if authority.get("run_url") != authority_run_url:
        errors.append(
            "quality.authority.run_url: does not match trusted workflow context"
        )
    for field, expected in (
        ("pull_request_number", authority_pull_request_number),
        ("pull_request_head_sha", authority_pull_request_head_sha),
        ("review_state_sha256", authority_review_state_sha256),
    ):
        if expected is None:
            errors.append(f"trusted workflow {field} context is required")
        elif authority.get(field) != expected:
            errors.append(
                f"quality.authority.{field}: does not match trusted workflow context"
            )
    if (
        isinstance(authority_pull_request_number, bool)
        or not isinstance(authority_pull_request_number, int)
        or authority_pull_request_number < 1
    ):
        errors.append("trusted workflow pull request number must be positive")
    if not isinstance(
        authority_pull_request_head_sha, str
    ) or COMMIT_RE.fullmatch(authority_pull_request_head_sha or "") is None:
        errors.append("trusted workflow pull request head SHA is invalid")
    if not isinstance(
        authority_review_state_sha256, str
    ) or SHA256_RE.fullmatch(authority_review_state_sha256 or "") is None:
        errors.append("trusted workflow review-state SHA-256 is invalid")
    if authority.get("check_name") != "Creator Submission Review / review":
        errors.append(
            "quality.authority.check_name: must identify the stable review check"
        )
    expected_run_prefix = (
        normalize_repository_url(authority_repository or RAPP_VISION_REPOSITORY)
        + "/actions/runs/"
    )
    if not str(authority.get("run_url", "")).startswith(expected_run_prefix):
        errors.append(
            "quality.authority.run_url: must identify a workflow run in the "
            "authority repository"
        )

    artifact = submission.get("artifact") or {}
    submission_sha256 = canonical_digest(submission)
    binding = _mapping(quality.get("binding"), "quality.binding", errors)
    expected_binding = {
        "submission_sha256": submission_sha256,
        "artifact_repository": artifact.get("repository"),
        "artifact_path": artifact.get("path"),
        "publication_id": artifact.get("publication_id"),
        "artifact_commit": artifact.get("commit"),
        "artifact_sha256": artifact.get("sha256"),
    }
    for key, expected in expected_binding.items():
        if binding.get(key) != expected:
            errors.append(f"quality.binding.{key}: does not match submission")

    freshness = _mapping(quality.get("freshness"), "quality.freshness", errors)
    compared = {
        "compared_submission_sha256": submission_sha256,
        "compared_commit": artifact.get("commit"),
        "compared_sha256": artifact.get("sha256"),
    }
    for key, expected in compared.items():
        if freshness.get(key) != expected:
            errors.append(f"quality.freshness.{key}: does not match submission")
    stale_when = freshness.get("stale_when") or {}
    for key in (
        "submission_sha256_changes",
        "artifact_commit_changes",
        "artifact_sha256_changes",
    ):
        if stale_when.get(key) is not True:
            errors.append(f"quality.freshness.stale_when.{key}: must be true")

    technical = _mapping(quality.get("technical"), "quality.technical", errors)
    checks = technical.get("checks")
    reviews = technical.get("reviews")
    quorum = _mapping(technical.get("quorum"), "quality.technical.quorum", errors)
    checks_pass = (
        isinstance(checks, list)
        and bool(checks)
        and all(
            isinstance(check, dict) and check.get("status") == "pass"
            for check in checks
        )
    )
    if not checks_pass and technical.get("status") == "pass":
        errors.append("quality.technical.status: pass requires all checks to pass")

    valid_reviews = []
    if isinstance(reviews, list):
        for index, review in enumerate(reviews):
            if not isinstance(review, dict):
                errors.append(f"quality.technical.reviews[{index}]: must be an object")
                continue
            reviewer = review.get("reviewer")
            reviewer_github_user_id = review.get("reviewer_github_user_id")
            role = review.get("role")
            reviewer_valid = _valid_id(reviewer)
            reviewer_id_valid = (
                isinstance(reviewer_github_user_id, int)
                and not isinstance(reviewer_github_user_id, bool)
                and reviewer_github_user_id > 0
            )
            role_valid = role in REVIEW_ROLES
            if not reviewer_valid:
                errors.append(
                    f"quality.technical.reviews[{index}].reviewer: "
                    "must be an authenticated reviewer id"
                )
            if not reviewer_id_valid:
                errors.append(
                    f"quality.technical.reviews[{index}]."
                    "reviewer_github_user_id: must be a positive GitHub user id"
                )
            if not role_valid:
                errors.append(
                    f"quality.technical.reviews[{index}].role: "
                    "must be technical or curation"
                )
            binding_valid = True
            for key, expected in (
                ("submission_sha256", submission_sha256),
                ("artifact_commit", artifact.get("commit")),
                ("artifact_sha256", artifact.get("sha256")),
            ):
                if review.get(key) != expected:
                    binding_valid = False
                    errors.append(
                        f"quality.technical.reviews[{index}].{key}: "
                        "does not match the reviewed submission"
                    )
            if (
                review.get("decision") == "pass"
                and reviewer_valid
                and reviewer_id_valid
                and role_valid
                and binding_valid
            ):
                valid_reviews.append(review)
    else:
        errors.append("quality.technical.reviews: must be an array")

    reviewer_ids = [
        review.get("reviewer_github_user_id") for review in valid_reviews
    ]
    roles = {review.get("role") for review in valid_reviews}
    minimum = quorum.get("minimum_approvals")
    distinct = len(reviewer_ids) == len(set(reviewer_ids))
    non_creator = (
        submission.get("creator", {}).get("github_user_id")
        not in reviewer_ids
    )
    derived_quorum = (
        isinstance(minimum, int)
        and not isinstance(minimum, bool)
        and len(valid_reviews) >= minimum
        and REVIEW_ROLES <= roles
        and distinct
        and non_creator
        and checks_pass
    )
    if quorum.get("independent_reviewers") is not True:
        errors.append("quality.technical.quorum.independent_reviewers: must be true")
    if quorum.get("met") is not derived_quorum:
        errors.append(
            "quality.technical.quorum.met: must equal the derived review quorum"
        )
    if not distinct:
        errors.append("quality.technical.reviews: passing reviewers must be distinct")
    if not non_creator:
        errors.append("quality.technical.reviews: creator cannot approve their own work")
    if technical.get("status") == "pass" and not derived_quorum:
        errors.append(
            "quality.technical.status: pass requires a complete independent quorum"
        )
    return errors


def _print_errors(prefix: Path, errors: list[str]) -> int:
    if not errors:
        return 0
    for error in errors:
        print(f"{prefix}: {error}", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    submission = commands.add_parser("submission")
    submission.add_argument("manifest", type=Path)
    submission.add_argument("--artifact-root", type=Path, default=Path("."))
    submission.add_argument("--pr-number", type=int)
    quality = commands.add_parser("quality")
    quality.add_argument("submission", type=Path)
    quality.add_argument("quality", type=Path)
    quality.add_argument("--repository", required=True)
    quality.add_argument("--run-url", required=True)
    quality.add_argument("--pull-request-number", type=int, required=True)
    quality.add_argument("--pull-request-head-sha", required=True)
    quality.add_argument("--review-state-sha256", required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "submission":
            document = load_json(args.manifest)
            checkout_commit = checkout_repository = None
            if isinstance(document, dict) and document.get("phase") == "submitted":
                checkout_commit, checkout_repository = git_checkout_context(
                    args.artifact_root
                )
            errors = validate_submission(
                document,
                args.artifact_root,
                expected_pr_number=args.pr_number,
                checkout_commit=checkout_commit,
                checkout_repository=checkout_repository,
            )
            if _print_errors(args.manifest, errors):
                return 1
            print(f"{args.manifest}: valid")
            if document.get("phase") == "submitted":
                print(f"submission_sha256={canonical_digest(document)}")
            return 0

        submission = load_json(args.submission)
        quality = load_json(args.quality)
        errors = validate_quality(
            submission,
            quality,
            authority_repository=args.repository,
            authority_run_url=args.run_url,
            authority_pull_request_number=args.pull_request_number,
            authority_pull_request_head_sha=args.pull_request_head_sha,
            authority_review_state_sha256=args.review_state_sha256,
        )
        if _print_errors(args.quality, errors):
            return 1
        print(f"{args.quality}: valid")
        return 0
    except ValueError as exc:
        print(f"validate_creator_submission: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
