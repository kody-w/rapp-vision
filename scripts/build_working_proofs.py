#!/usr/bin/env python3
"""Build the recurring Working Proofs channel from reviewed candidate outputs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "working-proofs"
CHANNEL_PATH = OUTPUT_ROOT / "channel.json"
EVIDENCE_INDEX_PATH = OUTPUT_ROOT / "evidence-index.json"

CHANNEL_SCHEMA = "rapp-vision-channel/2.0"
CHANNEL_ID = "working-proofs"
CHANNEL_NAME = "Working Proofs"
CHANNEL_TAGLINE = "Useful work, measurable results, controls included."

CANDIDATE_ONLY_KEYS = {
    "_candidate",
    "candidate",
    "candidate_frame",
    "candidate_id",
    "commission",
    "commission_id",
    "review",
    "review_id",
    "review_state",
}


@dataclass(frozen=True)
class Winner:
    candidate_frame: str
    source_directory: str
    commission_id: str
    publication_id: str
    title: str


WINNERS = (
    Winner(
        "candidate-frame-0002",
        "learn-grid-overflow",
        "learn-grid-overflow",
        "learn-grid-overflow",
        "Why the Grid Overflows",
    ),
    Winner(
        "candidate-frame-0002",
        "use-keyboard-invoice-triage",
        "use-keyboard-invoice-triage",
        "use-keyboard-invoice-triage",
        "Triage Invoices Without a Pointer",
    ),
    Winner(
        "candidate-frame-0002",
        "create-vector-icon-system",
        "create-vector-icon-system",
        "create-vector-icon-system",
        "Six Shapes, One Grid",
    ),
    Winner(
        "candidate-frame-0003",
        "ecosystem-island-threshold",
        "explore-ecosystem-threshold",
        "ecosystem-island-threshold",
        "Will the Island Herd Hold?",
    ),
    Winner(
        "candidate-frame-0003",
        "archive-wetland-contrast",
        "explore-archive-map-contrast",
        "explore-archive-map-contrast",
        "Read the Wetland Twice",
    ),
)


def load_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return document


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def strip_candidate_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_candidate_metadata(child)
            for key, child in value.items()
            if not key.startswith("_") and key not in CANDIDATE_ONLY_KEYS
        }
    if isinstance(value, list):
        return [strip_candidate_metadata(child) for child in value]
    return value


def candidate_prefix(winner: Winner) -> str:
    for label, component in (
        ("candidate frame", winner.candidate_frame),
        ("source directory", winner.source_directory),
    ):
        if (
            not component
            or component in {".", ".."}
            or "/" in component
            or "\\" in component
        ):
            raise ValueError(
                f"{winner.publication_id}: unsafe {label}: {component!r}"
            )
    return f"../{winner.candidate_frame}/{winner.source_directory}"


def rebase_relative_url(value: str, winner: Winner) -> str:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.path.startswith("/"):
        return value
    decoded_path = unquote(parsed.path)
    if (
        not parsed.path
        or "\\" in parsed.path
        or "\\" in decoded_path
        or decoded_path.startswith("/")
        or ".." in decoded_path.split("/")
    ):
        raise ValueError(
            f"{winner.source_directory}: expected a non-empty POSIX relative path, "
            f"got {value!r}"
        )

    source_prefix = candidate_prefix(winner)
    rebased_path = posixpath.normpath(
        posixpath.join(source_prefix, parsed.path)
    )
    expected_prefix = f"{source_prefix}/"
    if not rebased_path.startswith(expected_prefix):
        raise ValueError(
            f"{winner.source_directory}: path escapes its candidate directory: "
            f"{value!r}"
        )
    return urlunsplit(("", "", rebased_path, parsed.query, parsed.fragment))


def rewrite_publication_paths(
    publication: dict[str, Any],
    winner: Winner,
) -> None:
    for field in ("thumb", "poster"):
        if field in publication:
            publication[field] = rebase_relative_url(publication[field], winner)

    sources = publication.get("sources")
    if not isinstance(sources, list):
        raise ValueError(f"{winner.source_directory}: publication has no sources array")
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("src"), str):
            raise ValueError(f"{winner.source_directory}: invalid publication source")
        source["src"] = rebase_relative_url(source["src"], winner)

    live = publication.get("live")
    scenes = live.get("scenes") if isinstance(live, dict) else None
    if not isinstance(scenes, list):
        raise ValueError(f"{winner.source_directory}: publication has no live scenes")
    for scene in scenes:
        if isinstance(scene, dict) and "app" in scene:
            if not isinstance(scene["app"], str):
                raise ValueError(f"{winner.source_directory}: invalid live app path")
            scene["app"] = rebase_relative_url(scene["app"], winner)


def source_binding(source_root: Path, filename: str, winner: Winner) -> dict[str, str]:
    path = source_root / filename
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": f"{candidate_prefix(winner)}/{filename}",
        "sha256": sha256(path),
    }


def build_documents() -> tuple[dict[str, Any], dict[str, Any]]:
    publications: list[dict[str, Any]] = []
    evidence_entries: list[dict[str, Any]] = []

    for winner in WINNERS:
        source_root = ROOT / winner.candidate_frame / winner.source_directory
        source_channel = load_json(source_root / "channel.json")
        source_publications = source_channel.get("videos")
        if not isinstance(source_publications, list) or len(source_publications) != 1:
            raise ValueError(
                f"{winner.source_directory}: expected exactly one publication"
            )

        source_publication = source_publications[0]
        if not isinstance(source_publication, dict):
            raise ValueError(f"{winner.source_directory}: publication must be an object")
        if source_publication.get("id") != winner.publication_id:
            raise ValueError(
                f"{winner.source_directory}: expected publication "
                f"{winner.publication_id!r}"
            )
        if source_publication.get("title") != winner.title:
            raise ValueError(
                f"{winner.source_directory}: expected title {winner.title!r}"
            )

        publication = strip_candidate_metadata(copy.deepcopy(source_publication))
        rewrite_publication_paths(publication, winner)
        publications.append(publication)

        source_channel_binding = source_binding(
            source_root,
            "channel.json",
            winner,
        )
        source_channel_binding["id"] = str(source_channel.get("id", ""))
        evidence_entries.append(
            {
                "commission_id": winner.commission_id,
                "delivery": source_binding(source_root, "delivery.json", winner),
                "evidence": source_binding(source_root, "evidence.json", winner),
                "publication_id": winner.publication_id,
                "source_candidate": candidate_prefix(winner),
                "source_channel": source_channel_binding,
            }
        )

    channel = {
        "avatar": "✓",
        "cadence": "recurring",
        "creator": {
            "identity": "machine-produced, artifact-reviewed",
            "name": "RAPP Vision Working Proofs",
        },
        "id": CHANNEL_ID,
        "name": CHANNEL_NAME,
        "schema": CHANNEL_SCHEMA,
        "tagline": CHANNEL_TAGLINE,
        "videos": publications,
        "visibility": "public",
    }
    evidence_index = {
        "channel": CHANNEL_ID,
        "publications": evidence_entries,
        "schema": "working-proofs-evidence-index/1.0",
    }
    return channel, evidence_index


def json_bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if generated files do not match the reviewed candidate inputs",
    )
    args = parser.parse_args(argv)

    channel, evidence_index = build_documents()
    outputs = {
        CHANNEL_PATH: json_bytes(channel),
        EVIDENCE_INDEX_PATH: json_bytes(evidence_index),
    }
    if args.check:
        stale = [
            path
            for path, expected in outputs.items()
            if not path.is_file() or path.read_bytes() != expected
        ]
        if stale:
            for path in stale:
                print(f"stale: {path.relative_to(ROOT).as_posix()}")
            return 1
        print("working-proofs: current")
        return 0

    for path, content in outputs.items():
        write_bytes(path, content)
        print(f"wrote {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
