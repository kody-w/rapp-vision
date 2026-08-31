#!/usr/bin/env python3
"""Validate RAPP Vision paired publications and the default registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CURRENT_SCHEMA = "rapp-vision-channel/2.0"
LEGACY_SCHEMA = "rapp-vision-channel/1.0"
LIVE_KIND = "rapp-vision-live/1.0"
MAX_DURATION = 86400
EPSILON = 1e-6
ACTION_KINDS = {"click", "key", "keydown", "keyup", "type", "drag", "scroll"}
LEGACY_POLICY_ID = "legacy-publications-2026-08-31"
LEGACY_FROZEN_AT = "2026-08-31T16:24:12Z"
TRUSTED_REGISTRY_BASE = "https://kody-w.github.io/rapp-vision/channels.json"


def is_object(value: Any) -> bool:
    return isinstance(value, dict)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def target_shape(value: Any) -> bool:
    if not is_object(value):
        return False
    selector = nonempty_string(value.get("selector"))
    text = nonempty_string(value.get("text"))
    return selector != text


def point_shape(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(is_number(item) for item in value)
    )


def validate_action(action: Any, duration: float, path: str) -> list[str]:
    errors: list[str] = []
    if not is_object(action):
        return [f"{path}: must be an object"]
    at = action.get("at")
    if not is_number(at) or at < 0 or at >= duration:
        errors.append(f"{path}.at: must be at least 0 and less than the scene duration")
    kind = action.get("do")
    if kind not in ACTION_KINDS:
        errors.append(f"{path}.do: unsupported action {kind!r}")
        return errors

    has_selector = nonempty_string(action.get("selector"))
    has_text = nonempty_string(action.get("text"))
    has_one_target = has_selector != has_text
    if kind == "click" and not has_one_target:
        errors.append(f"{path}: click requires exactly one non-empty selector or text")
    elif kind in {"key", "keydown", "keyup"} and not nonempty_string(action.get("code")):
        errors.append(f"{path}.code: {kind} requires a non-empty code")
    elif kind == "type" and not isinstance(action.get("text"), str):
        errors.append(f"{path}.text: type requires a string")
    elif kind == "drag":
        if not point_shape(action.get("from")) or not point_shape(action.get("to")):
            errors.append(f"{path}: drag requires numeric two-item from and to points")
    elif kind == "scroll":
        target_count = int(has_selector) + int(has_text) + int(point_shape(action.get("to")))
        if target_count != 1:
            errors.append(f"{path}: scroll requires exactly one selector, text, or numeric to point")
    return errors


def validate_chapters(chapters: Any, duration: float, path: str) -> list[str]:
    errors: list[str] = []
    if chapters is None:
        return errors
    if not isinstance(chapters, list):
        return [f"{path}: must be an array"]
    previous = -1.0
    for index, chapter in enumerate(chapters):
        chapter_path = f"{path}[{index}]"
        if not is_object(chapter):
            errors.append(f"{chapter_path}: must be an object")
            continue
        start = chapter.get("t")
        if not is_number(start) or start < 0 or start >= duration:
            errors.append(f"{chapter_path}.t: must be within the mode duration")
        elif start <= previous:
            errors.append(f"{chapter_path}.t: chapters must be strictly increasing")
        else:
            previous = float(start)
        if not nonempty_string(chapter.get("label")):
            errors.append(f"{chapter_path}.label: must be a non-empty string")
    return errors


def validate_live(live: Any, path: str) -> list[str]:
    errors: list[str] = []
    if not is_object(live):
        return [f"{path}: must be an object"]
    if live.get("kind") != LIVE_KIND:
        errors.append(f"{path}.kind: must equal {LIVE_KIND!r}")
    scenes = live.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return errors + [f"{path}.scenes: must be a non-empty array"]

    cursor = 0.0
    for index, scene in enumerate(scenes):
        scene_path = f"{path}.scenes[{index}]"
        if not is_object(scene):
            errors.append(f"{scene_path}: must be an object")
            continue
        start = scene.get("t")
        scene_duration = scene.get("dur")
        if not is_number(start) or start < 0:
            errors.append(f"{scene_path}.t: must be a non-negative number")
        elif abs(start - cursor) > EPSILON:
            errors.append(f"{scene_path}.t: scenes must be contiguous; expected {cursor:g}")
        if not is_number(scene_duration) or scene_duration <= 0:
            errors.append(f"{scene_path}.dur: must be greater than zero")
            continue

        has_card = is_object(scene.get("card"))
        has_app = nonempty_string(scene.get("app"))
        if has_card == has_app:
            errors.append(f"{scene_path}: must contain exactly one card object or non-empty app")
        if "ready" in scene:
            ready = scene["ready"]
            if not has_app:
                errors.append(f"{scene_path}.ready: is valid only on app scenes")
            if not target_shape(ready):
                errors.append(f"{scene_path}.ready: requires exactly one non-empty selector or text")
            elif "enabled" in ready and not isinstance(ready["enabled"], bool):
                errors.append(f"{scene_path}.ready.enabled: must be boolean")

        actions = scene.get("actions", [])
        if not isinstance(actions, list):
            errors.append(f"{scene_path}.actions: must be an array")
        else:
            if actions and not has_app:
                errors.append(f"{scene_path}.actions: card scenes cannot contain actions")
            for action_index, action in enumerate(actions):
                errors.extend(
                    validate_action(
                        action,
                        float(scene_duration),
                        f"{scene_path}.actions[{action_index}]",
                    )
                )
        if is_number(start):
            cursor = float(start) + float(scene_duration)

    explicit_duration = live.get("duration")
    if explicit_duration is not None and (
        not is_number(explicit_duration)
        or explicit_duration <= 0
        or explicit_duration > MAX_DURATION
    ):
        errors.append(
            f"{path}.duration: must be greater than zero and at most {MAX_DURATION}"
        )
        replay_duration = cursor
    else:
        replay_duration = float(explicit_duration) if explicit_duration is not None else cursor
    if replay_duration <= 0 or replay_duration > MAX_DURATION:
        errors.append(
            f"{path}.scenes: derived replay duration must be greater than zero and at most {MAX_DURATION}"
        )
    elif abs(cursor - replay_duration) > EPSILON:
        errors.append(
            f"{path}.scenes: must fill replay duration {replay_duration:g}; ended at {cursor:g}"
        )
    errors.extend(validate_chapters(live.get("chapters"), replay_duration, f"{path}.chapters"))
    return errors


def validate_publication(video: Any, path: str) -> list[str]:
    errors: list[str] = []
    if not is_object(video):
        return [f"{path}: must be an object"]
    for field in ("id", "title"):
        if not nonempty_string(video.get(field)):
            errors.append(f"{path}.{field}: must be a non-empty string")

    duration = video.get("duration")
    if not is_number(duration) or duration <= 0 or duration > MAX_DURATION:
        errors.append(f"{path}.duration: must be greater than zero and at most {MAX_DURATION}")
    else:
        errors.extend(validate_chapters(video.get("chapters"), float(duration), f"{path}.chapters"))

    sources = video.get("sources")
    media_types: set[str] = set()
    if not isinstance(sources, list) or not sources:
        errors.append(f"{path}.sources: must be a non-empty array")
    else:
        for index, source in enumerate(sources):
            source_path = f"{path}.sources[{index}]"
            if not is_object(source):
                errors.append(f"{source_path}: must be an object")
                continue
            if not nonempty_string(source.get("src")):
                errors.append(f"{source_path}.src: must be a non-empty string")
            source_type = source.get("type")
            if not nonempty_string(source_type):
                errors.append(f"{source_path}.type: must be a non-empty media type")
                continue
            match = re.fullmatch(r"video/(mp4|webm)(?:\s*;.*)?", source_type)
            if not match:
                errors.append(f"{source_path}.type: only video/mp4 and video/webm are allowed")
            else:
                media_types.add(f"video/{match.group(1)}")
    for required_type in ("video/mp4", "video/webm"):
        if required_type not in media_types:
            errors.append(f"{path}.sources: missing required {required_type} source")

    errors.extend(validate_live(video.get("live"), f"{path}.live"))
    return errors


def legacy_record(
    policy: dict[str, Any], channel_id: Any, source_url: str
) -> dict[str, Any] | None:
    for record in policy.get("channels", []):
        if (
            is_object(record)
            and record.get("id") == channel_id
            and record.get("source") == source_url
        ):
            return record
    return None


def normalize_json(value: Any) -> Any:
    if is_object(value):
        return {key: normalize_json(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [normalize_json(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def publication_digest(publication: Any) -> str:
    canonical = json.dumps(
        normalize_json(publication),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def legacy_publication_record(record: dict[str, Any], publication_id: Any) -> dict[str, Any] | None:
    for publication in record.get("publications", []):
        if is_object(publication) and publication.get("id") == publication_id:
            return publication
    return None


def validate_channel(
    channel: Any, source_url: str, legacy_policy: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    if not is_object(channel):
        return ["channel: must be an object"]
    if not nonempty_string(channel.get("id")):
        errors.append("channel.id: must be a non-empty string")
    if not nonempty_string(channel.get("name")):
        errors.append("channel.name: must be a non-empty string")
    videos = channel.get("videos")
    if not isinstance(videos, list) or not videos:
        errors.append("channel.videos: must be a non-empty array")
        videos = []

    ids = [video.get("id") for video in videos if is_object(video)]
    if len(ids) != len(set(ids)):
        errors.append("channel.videos: publication ids must be unique")

    schema = channel.get("schema")
    if schema == CURRENT_SCHEMA:
        for index, video in enumerate(videos):
            errors.extend(validate_publication(video, f"channel.videos[{index}]"))
    elif schema == LEGACY_SCHEMA:
        record = legacy_record(legacy_policy, channel.get("id"), source_url)
        if not record:
            errors.append(
                "channel.schema: v1 is frozen legacy only; channel id and canonical source are not allowlisted"
            )
        else:
            for index, video in enumerate(videos):
                video_id = video.get("id") if is_object(video) else None
                publication = legacy_publication_record(record, video_id)
                if not publication:
                    errors.append(
                        f"channel.videos[{index}].id: {video_id!r} is not a frozen legacy publication"
                    )
                elif publication_digest(video) != publication.get("sha256"):
                    errors.append(
                        f"channel.videos[{index}]: content does not match its frozen legacy digest"
                    )
    else:
        errors.append(f"channel.schema: must equal {CURRENT_SCHEMA!r}")
    return errors


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "rapp-vision-publication-validator/1.0"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def validate_legacy_policy(policy: Any) -> list[str]:
    errors: list[str] = []
    if not is_object(policy):
        return ["legacy policy: must be an object"]
    if policy.get("schema") != "rapp-vision-legacy-publications/1.0":
        errors.append("legacy policy.schema: unsupported schema")
    if not nonempty_string(policy.get("id")):
        errors.append("legacy policy.id: must be a non-empty string")
    if not nonempty_string(policy.get("registry_base")):
        errors.append("legacy policy.registry_base: must be a canonical URL")
    seen_channels: set[tuple[Any, Any]] = set()
    for index, record in enumerate(policy.get("channels", [])):
        path = f"legacy policy.channels[{index}]"
        if not is_object(record):
            errors.append(f"{path}: must be an object")
            continue
        key = (record.get("id"), record.get("source"))
        if key in seen_channels:
            errors.append(f"{path}: duplicate channel id and source")
        seen_channels.add(key)
        if not nonempty_string(record.get("id")) or not nonempty_string(record.get("source")):
            errors.append(f"{path}: id and source must be non-empty strings")
        publications = record.get("publications")
        if not isinstance(publications, list) or not publications:
            errors.append(f"{path}.publications: must be a non-empty array")
        else:
            publication_ids = []
            for publication_index, publication in enumerate(publications):
                publication_path = f"{path}.publications[{publication_index}]"
                if not is_object(publication):
                    errors.append(f"{publication_path}: must be an object with id and sha256")
                    continue
                publication_id = publication.get("id")
                digest = publication.get("sha256")
                if not nonempty_string(publication_id):
                    errors.append(f"{publication_path}.id: must be a non-empty string")
                else:
                    publication_ids.append(publication_id)
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    errors.append(f"{publication_path}.sha256: must be a lowercase SHA-256 digest")
            if len(publication_ids) != len(set(publication_ids)):
                errors.append(f"{path}.publications: ids must be unique")
    return errors


def git_json(ref: str, path: str) -> Any:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{ref}:{path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"cannot read {path} from {ref}")
    return json.loads(completed.stdout)


def git_has_path(ref: str, path: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{ref}:{path}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def policy_identity(policy: dict[str, Any]) -> list[tuple[Any, Any, tuple[Any, ...]]]:
    identity = []
    for record in policy.get("channels", []):
        publications = []
        for publication in record.get("publications", []):
            publications.append(
                publication.get("id") if is_object(publication) else publication
            )
        identity.append((record.get("id"), record.get("source"), tuple(publications)))
    return identity


def baseline_channel_documents(
    ref: str, policy: dict[str, Any], registry: dict[str, Any]
) -> tuple[dict[tuple[Any, Any], dict[str, Any]], list[str]]:
    documents: dict[tuple[Any, Any], dict[str, Any]] = {}
    errors: list[str] = []
    base = policy.get("registry_base", "")
    entries = registry.get("channels", []) if is_object(registry) else []
    for record in policy.get("channels", []):
        channel_id = record.get("id")
        source = record.get("source")
        entry = next(
            (
                item
                for item in entries
                if is_object(item)
                and item.get("id") == channel_id
                and urljoin(base, item.get("url", "")) == source
            ),
            None,
        )
        if not entry:
            errors.append(
                f"legacy baseline: {channel_id!r} at {source!r} is absent from baseline registry"
            )
            continue
        raw_url = entry.get("url", "")
        parsed = urlparse(raw_url)
        repo_path = posixpath.normpath(parsed.path)
        try:
            if not parsed.scheme and not parsed.netloc and not repo_path.startswith("../"):
                channel = git_json(ref, repo_path)
            else:
                channel = fetch_json(source)
        except Exception as exc:
            errors.append(f"legacy baseline: could not load {source}: {exc}")
            continue
        documents[(channel_id, source)] = channel
    return documents, errors


def validate_frozen_policy(
    current: dict[str, Any],
    baseline: dict[str, Any],
    baseline_channels: dict[tuple[Any, Any], dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for field in ("schema", "id", "frozen_at", "registry_base"):
        if current.get(field) != baseline.get(field):
            errors.append(f"legacy policy.{field}: frozen value differs from git baseline")
    if policy_identity(current) != policy_identity(baseline):
        errors.append("legacy policy: channel/source/publication identities differ from git baseline")
        return errors

    baseline_publications = [
        publication
        for record in baseline.get("channels", [])
        for publication in record.get("publications", [])
    ]
    if baseline_publications and all(is_object(item) for item in baseline_publications):
        if normalize_json(current) != normalize_json(baseline):
            errors.append("legacy policy: frozen digest baseline was modified")
        return errors

    # One-time transition from the original string allowlist to content digests.
    # Identities still come from git, and every digest must describe the
    # publication bytes reachable from that baseline registry.
    for record in current.get("channels", []):
        key = (record.get("id"), record.get("source"))
        channel = baseline_channels.get(key)
        if not channel:
            errors.append(f"legacy policy: no trusted baseline channel for {key[0]!r}")
            continue
        videos = {
            video.get("id"): video
            for video in channel.get("videos", [])
            if is_object(video) and nonempty_string(video.get("id"))
        }
        for publication in record.get("publications", []):
            publication_id = publication.get("id") if is_object(publication) else None
            video = videos.get(publication_id)
            if not video:
                errors.append(
                    f"legacy policy: baseline publication {key[0]}/{publication_id} is unavailable"
                )
            elif publication.get("sha256") != publication_digest(video):
                errors.append(
                    f"legacy policy: digest for {key[0]}/{publication_id} does not match git baseline content"
                )
    return errors


def validate_baseline_ref(current: dict[str, Any], ref: str) -> list[str]:
    try:
        registry = git_json(ref, "channels.json")
    except Exception as exc:
        return [f"legacy policy: could not read trusted git baseline {ref}: {exc}"]
    if not git_has_path(ref, "policy/legacy-publications.json"):
        # Bootstrap against the trusted pre-policy registry. The base commit,
        # not the PR, decides which channels and publications may become legacy.
        baseline = {
            "schema": "rapp-vision-legacy-publications/1.0",
            "id": LEGACY_POLICY_ID,
            "frozen_at": LEGACY_FROZEN_AT,
            "registry_base": TRUSTED_REGISTRY_BASE,
            "channels": [
                {
                    "id": entry.get("id"),
                    "source": urljoin(TRUSTED_REGISTRY_BASE, entry.get("url", "")),
                    "publications": [],
                }
                for entry in registry.get("channels", [])
                if is_object(entry)
            ],
        }
        channels, errors = baseline_channel_documents(ref, baseline, registry)
        for record in baseline["channels"]:
            channel = channels.get((record["id"], record["source"]))
            record["publications"] = [
                video.get("id")
                for video in (channel or {}).get("videos", [])
                if is_object(video) and nonempty_string(video.get("id"))
            ]
        return errors + validate_frozen_policy(current, baseline, channels)
    try:
        baseline = git_json(ref, "policy/legacy-publications.json")
    except Exception as exc:
        return [f"legacy policy: trusted git baseline is unreadable: {exc}"]
    baseline_publications = [
        publication
        for record in baseline.get("channels", [])
        for publication in record.get("publications", [])
    ]
    if baseline_publications and all(is_object(item) for item in baseline_publications):
        return validate_frozen_policy(current, baseline, {})
    channels, errors = baseline_channel_documents(ref, baseline, registry)
    return errors + validate_frozen_policy(current, baseline, channels)


def registry_local_path(registry_path: Path, raw_url: str) -> Path | None:
    parsed = urlparse(raw_url)
    if parsed.scheme or parsed.netloc:
        return None
    candidate = (registry_path.parent / parsed.path).resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def validate_registry_channel_identity(
    entry: dict[str, Any],
    channel: dict[str, Any],
    resolved_ids: dict[Any, str],
    path: str,
) -> list[str]:
    errors: list[str] = []
    entry_id = entry.get("id")
    channel_id = channel.get("id")
    if entry_id != channel_id:
        errors.append(
            f"{path}.id: registry id {entry_id!r} must equal fetched channel id {channel_id!r}"
        )
    if channel_id in resolved_ids:
        errors.append(
            f"{path}: fetched channel id {channel_id!r} duplicates {resolved_ids[channel_id]}"
        )
    else:
        resolved_ids[channel_id] = path
    return errors


def validate_registry(
    registry_path: Path,
    policy: dict[str, Any],
    *,
    offline: bool = False,
) -> list[str]:
    registry = load_json(registry_path)
    errors: list[str] = []
    entries = registry.get("channels") if is_object(registry) else None
    if not isinstance(entries, list):
        return ["registry.channels: must be an array"]
    ids = [entry.get("id") for entry in entries if is_object(entry)]
    if len(ids) != len(set(ids)):
        errors.append("registry.channels: ids must be unique")

    policy_id = policy.get("id")
    base = policy.get("registry_base", "")
    resolved_ids: dict[Any, str] = {}
    for index, entry in enumerate(entries):
        path = f"registry.channels[{index}]"
        if not is_object(entry):
            errors.append(f"{path}: must be an object")
            continue
        raw_url = entry.get("url")
        if not nonempty_string(raw_url):
            errors.append(f"{path}.url: must be a non-empty string")
            continue
        canonical = urljoin(base, raw_url)
        record = legacy_record(policy, entry.get("id"), canonical)
        if entry.get("legacy") is not None:
            if entry.get("legacy") != policy_id:
                errors.append(f"{path}.legacy: must equal the frozen policy id {policy_id!r}")
            if not record:
                errors.append(f"{path}: legacy marker does not match a frozen id and canonical source")
        else:
            if record:
                errors.append(f"{path}: frozen legacy entry must declare its legacy policy id")
            if entry.get("contract") != CURRENT_SCHEMA:
                errors.append(f"{path}.contract: new registry entries must declare {CURRENT_SCHEMA!r}")

        local_path = registry_local_path(registry_path, raw_url)
        if local_path:
            channel = load_json(local_path)
        elif offline:
            continue
        else:
            try:
                channel = fetch_json(canonical)
            except Exception as exc:  # deterministic message, no traceback
                errors.append(f"{path}: could not load {canonical}: {exc}")
                continue
        errors.extend(validate_registry_channel_identity(entry, channel, resolved_ids, path))
        channel_errors = validate_channel(channel, canonical, policy)
        errors.extend(f"{path} -> {error}" for error in channel_errors)
    return errors


def print_result(label: str, errors: list[str]) -> bool:
    if errors:
        for error in errors:
            print(f"{label}: {error}", file=sys.stderr)
        return False
    print(f"{label}: valid")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channels", nargs="*", type=Path, help="channel JSON files")
    parser.add_argument("--source-url", help="canonical source URL for one channel file")
    parser.add_argument("--registry", type=Path, help="validate a default registry")
    parser.add_argument(
        "--legacy-policy",
        type=Path,
        default=ROOT / "policy" / "legacy-publications.json",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip remote registry channels while still checking registry policy declarations",
    )
    parser.add_argument(
        "--check-legacy-baseline",
        metavar="GIT_REF",
        help="reject any legacy-policy change not authorized by the trusted git baseline",
    )
    args = parser.parse_args(argv)

    policy = load_json(args.legacy_policy)
    ok = print_result(str(args.legacy_policy), validate_legacy_policy(policy))
    if args.check_legacy_baseline:
        ok = print_result(
            f"{args.legacy_policy} vs {args.check_legacy_baseline}",
            validate_baseline_ref(policy, args.check_legacy_baseline),
        ) and ok
    if args.source_url and len(args.channels) != 1:
        parser.error("--source-url requires exactly one channel file")
    for channel_path in args.channels:
        source_url = args.source_url or channel_path.resolve().as_uri()
        ok = print_result(
            str(channel_path),
            validate_channel(load_json(channel_path), source_url, policy),
        ) and ok
    if args.registry:
        ok = print_result(
            str(args.registry),
            validate_registry(args.registry, policy, offline=args.offline),
        ) and ok
    if not args.channels and not args.registry:
        template = ROOT / "template" / "channel.json"
        ok = print_result(
            str(template),
            validate_channel(load_json(template), template.resolve().as_uri(), policy),
        ) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
