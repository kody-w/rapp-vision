#!/usr/bin/env python3
"""Validate RAPP Vision paired publications and the default registry."""

from __future__ import annotations

import argparse
import json
import math
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
    if not is_number(at) or at < 0 or at > duration:
        errors.append(f"{path}.at: must be between 0 and the scene duration")
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


def validate_live(live: Any, duration: float, path: str) -> list[str]:
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

    if abs(cursor - duration) > EPSILON:
        errors.append(f"{path}.scenes: must fill publication duration {duration:g}; ended at {cursor:g}")
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
        duration_for_live = 0.0
    else:
        duration_for_live = float(duration)

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
            base_type = source_type.split(";", 1)[0].strip().lower()
            if base_type not in {"video/mp4", "video/webm"}:
                errors.append(f"{source_path}.type: only video/mp4 and video/webm are allowed")
            else:
                media_types.add(base_type)
    for required_type in ("video/mp4", "video/webm"):
        if required_type not in media_types:
            errors.append(f"{path}.sources: missing required {required_type} source")

    errors.extend(validate_live(video.get("live"), duration_for_live, f"{path}.live"))
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
            allowed = set(record.get("publications", []))
            for index, video in enumerate(videos):
                video_id = video.get("id") if is_object(video) else None
                if video_id not in allowed:
                    errors.append(
                        f"channel.videos[{index}].id: {video_id!r} is not a frozen legacy publication"
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
        elif (
            not all(nonempty_string(item) for item in publications)
            or len(publications) != len(set(publications))
        ):
            errors.append(f"{path}.publications: ids must be non-empty and unique")
    return errors


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
    args = parser.parse_args(argv)

    policy = load_json(args.legacy_policy)
    ok = print_result(str(args.legacy_policy), validate_legacy_policy(policy))
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
