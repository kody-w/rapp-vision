#!/usr/bin/env python3
"""Create deterministic hashes and codec evidence for the candidate delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = ROOT / "delivery.json"
PUBLICATION_ID = "learn-grid-overflow"
FILES = (
    ".gitattributes",
    "README.md",
    "apps/learn-grid-overflow.html",
    "build_delivery.py",
    "channel.json",
    "channel.production.json",
    "evidence.json",
    "masters/learn-grid-overflow.mkv",
    "media/learn-grid-overflow.mp4",
    "media/learn-grid-overflow.webm",
    "render.py",
    "thumbs/learn-grid-overflow.svg",
    "verify_dom.mjs",
)
MEDIA_KINDS = {
    "masters/learn-grid-overflow.mkv": "master",
    "media/learn-grid-overflow.mp4": "mp4",
    "media/learn-grid-overflow.webm": "webm",
}


def file_record(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    if not path.is_file():
        raise RuntimeError(f"required delivery file does not exist: {path}")
    content = path.read_bytes()
    return {
        "bytes": len(content),
        "path": relative,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def probe_media(ffprobe: str, relative: str) -> dict[str, Any]:
    path = ROOT / relative
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        (
            "stream=codec_name,pix_fmt,width,height,color_space,color_transfer,"
            "color_primaries,color_range:format=duration"
        ),
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"ffprobe failed to start: {exc}") from exc
    if completed.returncode:
        raise RuntimeError(
            f"ffprobe failed for {relative}: "
            f"{completed.stderr.strip() or completed.returncode}"
        )
    try:
        payload = json.loads(completed.stdout)
        streams = payload["streams"]
        stream = streams[0] if len(streams) == 1 else None
        duration_value = float(payload["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"ffprobe returned malformed data for {relative}") from exc
    if not isinstance(stream, dict):
        raise RuntimeError(f"ffprobe did not return one video stream for {relative}")
    duration: int | float = round(duration_value, 6)
    if float(duration).is_integer():
        duration = int(duration)
    result = {
        "codec": stream.get("codec_name"),
        "duration": duration,
        "height": stream.get("height"),
        "pixelFormat": stream.get("pix_fmt"),
        "width": stream.get("width"),
    }
    if relative != "masters/learn-grid-overflow.mkv":
        result.update(
            {
                "colorPrimaries": stream.get("color_primaries"),
                "colorRange": stream.get("color_range"),
                "colorSpace": stream.get("color_space"),
                "colorTransfer": stream.get("color_transfer"),
            }
        )
    return result


def delivery_document(ffprobe: str) -> dict[str, Any]:
    artifacts = {}
    media = {}
    for relative in FILES:
        record = file_record(relative)
        artifacts[relative] = record
        if relative in MEDIA_KINDS:
            media[MEDIA_KINDS[relative]] = {
                **record,
                **probe_media(ffprobe, relative),
            }
    return {
        "artifacts": artifacts,
        "channel": "candidate-frame-0002-04",
        "media": media,
        "publication": PUBLICATION_ID,
        "schema": "candidate-frame-delivery/1.0",
    }


def deterministic_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        content = deterministic_json(delivery_document(args.ffprobe))
        if args.check:
            if not OUTPUT_PATH.is_file():
                raise RuntimeError(f"delivery file does not exist: {OUTPUT_PATH}")
            if OUTPUT_PATH.read_text(encoding="utf-8") != content:
                raise RuntimeError("delivery.json is stale")
            print(f"{OUTPUT_PATH}: valid")
        else:
            OUTPUT_PATH.write_text(content, encoding="utf-8", newline="\n")
            print(OUTPUT_PATH)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"build_delivery: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
