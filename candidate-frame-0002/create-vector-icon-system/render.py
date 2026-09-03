#!/usr/bin/env python3
"""Render the deterministic Create Vector Icon System candidate artifacts."""

from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
PUBLICATION_ID = "create-vector-icon-system"
TITLE = "Six Shapes, One Grid"
WIDTH = 960
HEIGHT = 540
FPS = 12
FRAME_COUNT = 180
DURATION = FRAME_COUNT / FPS
VIEW_BOX = "0 0 24 24"
GRID = 2
REFERENCE_STROKE = 2.0
BASE_STROKE = REFERENCE_STROKE
EDIT_STROKE = 1.5
EXPORT_STROKE = REFERENCE_STROKE
SUPPORTED_STROKES = (1.0, 1.5, 2.0, 2.5, 3.0)
RASTER_THRESHOLD_PERCENT = 0.5
SUPERSAMPLE = 4
REFERENCE_RELATIVE = Path("reference") / "reference-raster.json"
IMMUTABLE_REFERENCE_SHA256 = (
    "61744b14a3c1e4f360d77207712e12f33e626259e1ff9eaca7cd46dd5ebd2d46"
)
RGB = tuple[int, int, int]
Point = tuple[float, float]
Polyline = tuple[Point, ...]


@dataclass(frozen=True)
class Icon:
    name: str
    label: str
    paths: tuple[Polyline, ...]


ICONS = (
    Icon(
        "bloom",
        "Bloom",
        (
            ((12, 2), (18, 8), (12, 14), (6, 8), (12, 2)),
            ((12, 14), (12, 22)),
            ((8, 18), (16, 18)),
        ),
    ),
    Icon(
        "cairn",
        "Cairn",
        (
            ((4, 20), (8, 16), (16, 16), (20, 20)),
            ((6, 14), (10, 10), (14, 10), (18, 14)),
            ((10, 8), (12, 4), (14, 8)),
        ),
    ),
    Icon(
        "hinge",
        "Hinge",
        (
            ((4, 4), (4, 20), (20, 20)),
            ((8, 8), (16, 8), (16, 16), (8, 16), (8, 8)),
            ((4, 12), (8, 12)),
            ((12, 16), (12, 20)),
        ),
    ),
    Icon(
        "orbit",
        "Orbit",
        (
            (
                (12, 2),
                (18, 4),
                (22, 10),
                (20, 16),
                (14, 22),
                (8, 20),
                (2, 14),
                (4, 8),
                (12, 2),
            ),
            ((12, 8), (16, 12), (12, 16), (8, 12), (12, 8)),
        ),
    ),
    Icon(
        "pulse",
        "Pulse",
        (
            ((2, 12), (6, 12), (8, 6), (12, 18), (16, 6), (18, 12), (22, 12)),
            ((4, 4), (20, 4)),
        ),
    ),
    Icon(
        "weave",
        "Weave",
        (
            ((4, 6), (8, 6), (16, 18), (20, 18)),
            ((20, 6), (16, 6), (8, 18), (4, 18)),
            ((4, 12), (8, 12)),
            ((16, 12), (20, 12)),
        ),
    ),
)
ICON_BY_NAME = {icon.name: icon for icon in ICONS}
ICON_NAMES = tuple(icon.name for icon in ICONS)


PIXEL_FONT = {
    " ": ("000", "000", "000", "000", "000"),
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "J": ("001", "001", "001", "101", "010"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "P": ("110", "101", "110", "100", "100"),
    "Q": ("010", "101", "101", "111", "011"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("110", "001", "010", "100", "111"),
    "3": ("110", "001", "010", "001", "110"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "110", "001", "110"),
    "6": ("011", "100", "110", "101", "010"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("010", "101", "010", "101", "010"),
    "9": ("010", "101", "011", "001", "110"),
    ".": ("000", "000", "000", "000", "010"),
    ":": ("000", "010", "000", "010", "000"),
    "/": ("001", "001", "010", "100", "100"),
    "%": ("101", "001", "010", "100", "101"),
    "-": ("000", "000", "111", "000", "000"),
    "=": ("000", "111", "000", "111", "000"),
}


def _number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def path_data(path: Polyline) -> str:
    head, *tail = path
    commands = [f"M{_number(head[0])} {_number(head[1])}"]
    commands.extend(f"L{_number(x)} {_number(y)}" for x, y in tail)
    return "".join(commands)


def sprite_svg(stroke: float = EXPORT_STROKE) -> str:
    """Return the canonical deterministic six-symbol sprite."""
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true">',
        "  <title>Six Shapes shared geometric icon sprite</title>",
        "  <defs>",
    ]
    for icon in ICONS:
        lines.extend(
            [
                (
                    f'    <symbol id="icon-{icon.name}" data-name="{icon.label}" '
                    f'viewBox="{VIEW_BOX}">'
                ),
                f"      <title>{icon.label}</title>",
                (
                    '      <g fill="none" stroke="currentColor" '
                    f'stroke-width="{_number(stroke)}" stroke-linecap="round" '
                    'stroke-linejoin="round">'
                ),
            ]
        )
        lines.extend(f'        <path d="{path_data(path)}"/>' for path in icon.paths)
        lines.extend(["      </g>", "    </symbol>"])
    lines.extend(["  </defs>", "</svg>", ""])
    return "\n".join(lines)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _point_segment_distance(point: Point, start: Point, end: Point) -> float:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(px - x1, py - y1)
    projection = ((px - x1) * dx + (py - y1) * dy) / length_squared
    projection = min(1.0, max(0.0, projection))
    near_x = x1 + projection * dx
    near_y = y1 + projection * dy
    return math.hypot(px - near_x, py - near_y)


def invalid_paths(icon: Icon) -> tuple[Polyline, ...]:
    if icon.name != "pulse":
        return icon.paths
    altered = list(icon.paths[0])
    altered[3] = (13, 17)
    return (tuple(altered),) + icon.paths[1:]


def rasterize_icon(
    icon: Icon,
    *,
    stroke: float = EXPORT_STROKE,
    invalid: bool = False,
) -> bytes:
    """Rasterize round polylines to deterministic 4x supersampled coverage bytes."""
    paths = invalid_paths(icon) if invalid else icon.paths
    segments = [
        (path[index], path[index + 1])
        for path in paths
        for index in range(len(path) - 1)
    ]
    coverage = bytearray()
    radius = stroke / 2
    sample_count = SUPERSAMPLE * SUPERSAMPLE
    for y in range(24):
        for x in range(24):
            inside = 0
            for sub_y in range(SUPERSAMPLE):
                sample_y = y + (sub_y + 0.5) / SUPERSAMPLE
                for sub_x in range(SUPERSAMPLE):
                    sample_x = x + (sub_x + 0.5) / SUPERSAMPLE
                    if any(
                        _point_segment_distance(
                            (sample_x, sample_y),
                            segment_start,
                            segment_end,
                        )
                        <= radius
                        for segment_start, segment_end in segments
                    ):
                        inside += 1
            coverage.append(round(inside * 255 / sample_count))
    return bytes(coverage)


def rasterize_system(
    *,
    stroke: float = EXPORT_STROKE,
    invalid: bool = False,
) -> dict[str, bytes]:
    return {
        icon.name: rasterize_icon(icon, stroke=stroke, invalid=invalid)
        for icon in ICONS
    }


@functools.lru_cache(maxsize=4)
def immutable_reference(
    path: Path = ROOT / REFERENCE_RELATIVE,
) -> dict[str, object]:
    raw = path.read_bytes()
    actual_sha256 = sha256_bytes(raw)
    if actual_sha256 != IMMUTABLE_REFERENCE_SHA256:
        raise RuntimeError(
            "immutable raster reference digest mismatch: "
            f"{actual_sha256} != {IMMUTABLE_REFERENCE_SHA256}"
        )
    document = json.loads(raw.decode("utf-8"))
    if document.get("schema") != "six-shapes-immutable-reference-raster/2.0":
        raise RuntimeError("immutable raster reference has the wrong schema")
    expected = {
        "viewBox": VIEW_BOX,
        "width": 24,
        "height": 24,
        "grid": GRID,
        "stroke": REFERENCE_STROKE,
        "supersample": f"{SUPERSAMPLE}x{SUPERSAMPLE}",
        "geometrySha256": geometry_sha256(),
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise RuntimeError(
                f"immutable raster reference {key} mismatch: "
                f"{document.get(key)!r} != {value!r}"
            )
    icons = document.get("icons")
    if not isinstance(icons, list):
        raise RuntimeError("immutable raster reference icons are missing")
    if tuple(item.get("name") for item in icons) != ICON_NAMES:
        raise RuntimeError("immutable raster reference icon order differs")
    coverages: list[bytes] = []
    for item in icons:
        try:
            coverage = base64.b64decode(
                item["coverageBase64"],
                validate=True,
            )
        except (KeyError, ValueError) as exc:
            raise RuntimeError("immutable raster coverage is invalid") from exc
        if len(coverage) != 24 * 24:
            raise RuntimeError("immutable raster coverage has the wrong size")
        if sha256_bytes(coverage) != item.get("coverageSha256"):
            raise RuntimeError("immutable raster coverage digest mismatch")
        coverages.append(coverage)
    if sha256_bytes(b"".join(coverages)) != document.get(
        "systemCoverageSha256"
    ):
        raise RuntimeError("immutable system coverage digest mismatch")
    return document


def reference_coverages(
    path: Path = ROOT / REFERENCE_RELATIVE,
) -> dict[str, bytes]:
    document = immutable_reference(path)
    return {
        item["name"]: base64.b64decode(item["coverageBase64"], validate=True)
        for item in document["icons"]
    }


def compare_to_reference(
    candidate: dict[str, bytes],
    *,
    reference_path: Path = ROOT / REFERENCE_RELATIVE,
) -> dict[str, object]:
    reference = reference_coverages(reference_path)
    highlights: list[dict[str, object]] = []
    for icon in ICONS:
        baseline = reference[icon.name]
        rendered = candidate[icon.name]
        if len(rendered) != len(baseline):
            raise RuntimeError(f"candidate raster size differs for {icon.name}")
        for offset, (before, after) in enumerate(zip(baseline, rendered)):
            if before != after:
                highlights.append(
                    {
                        "icon": icon.name,
                        "x": offset % 24,
                        "y": offset // 24,
                        "reference": before,
                        "candidate": after,
                    }
                )
    total_pixels = len(ICONS) * 24 * 24
    differing_pixels = len(highlights)
    differing_percent = round(differing_pixels / total_pixels * 100, 4)
    return {
        "differingPixels": differing_pixels,
        "differingPercent": differing_percent,
        "status": (
            "pass"
            if differing_percent < RASTER_THRESHOLD_PERCENT
            else "fail"
        ),
        "totalPixels": total_pixels,
        "changedPixelHighlights": highlights,
    }


def stroke_comparison(
    stroke: float,
    *,
    invalid: bool = False,
    reference_path: Path = ROOT / REFERENCE_RELATIVE,
) -> dict[str, object]:
    if stroke not in SUPPORTED_STROKES:
        raise ValueError(f"unsupported stroke: {stroke}")
    return compare_to_reference(
        rasterize_system(stroke=stroke, invalid=invalid),
        reference_path=reference_path,
    )


@functools.lru_cache(maxsize=1)
def reference_document() -> dict[str, object]:
    reference = immutable_reference()
    accepted = stroke_comparison(REFERENCE_STROKE)
    invalid = stroke_comparison(REFERENCE_STROKE, invalid=True)
    return {
        "schema": "six-shapes-reference-comparison/2.0",
        "reference": {
            "path": REFERENCE_RELATIVE.as_posix(),
            "sha256": IMMUTABLE_REFERENCE_SHA256,
            "stroke": REFERENCE_STROKE,
            "method": reference["method"],
            "coverageEncoding": reference["coverageEncoding"],
            "systemCoverageSha256": reference["systemCoverageSha256"],
        },
        "comparison": {
            "method": reference["method"],
            "thresholdPercent": RASTER_THRESHOLD_PERCENT,
            "totalPixels": accepted["totalPixels"],
            "acceptedDifferingPixels": accepted["differingPixels"],
            "acceptedDifferingPercent": accepted["differingPercent"],
            "acceptedStatus": accepted["status"],
            "invalidEdit": {
                "icon": "pulse",
                "anchorIndex": 3,
                "from": [12, 18],
                "to": [13, 17],
                "reason": "Both coordinates must be divisible by the 2 px grid token.",
            },
            "invalidDifferingPixels": invalid["differingPixels"],
            "invalidDifferingPercent": invalid["differingPercent"],
            "invalidStatus": invalid["status"],
            "changedPixelHighlights": invalid["changedPixelHighlights"],
        },
    }


def stroke_records() -> dict[str, object]:
    records: dict[str, object] = {}
    for stroke in SUPPORTED_STROKES:
        comparison = stroke_comparison(stroke)
        sprite = sprite_svg(stroke)
        records[_number(stroke)] = {
            "bytes": len(sprite.encode("utf-8")),
            "geometrySha256": generated_geometry_sha256(stroke),
            "sha256": sha256_text(sprite),
            "comparison": {
                "differingPixels": comparison["differingPixels"],
                "differingPercent": comparison["differingPercent"],
                "status": comparison["status"],
                "totalPixels": comparison["totalPixels"],
            },
        }
    return records


def deterministic_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def geometry_document() -> list[dict[str, object]]:
    return [
        {
            "label": icon.label,
            "name": icon.name,
            "paths": icon.paths,
        }
        for icon in ICONS
    ]


def geometry_sha256() -> str:
    canonical = json.dumps(
        geometry_document(),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256_text(canonical)


def generated_geometry_signature(stroke: float) -> str:
    return "\n".join(
        "|".join(
            (
                icon.name,
                VIEW_BOX,
                _number(stroke),
                "round",
                "round",
                ";".join(path_data(path) for path in icon.paths),
            )
        )
        for icon in ICONS
    )


def generated_geometry_sha256(stroke: float) -> str:
    return sha256_text(generated_geometry_signature(stroke))


def contract_states(output_root: Path = ROOT) -> dict[str, object]:
    app = output_root / "apps" / f"{PUBLICATION_ID}.html"
    source = app.read_text(encoding="utf-8")
    match = re.search(
        r'<script\s+type="application/json"\s+id="contract-states">\s*'
        r"(.*?)\s*</script>",
        source,
        flags=re.DOTALL,
    )
    if not match:
        raise RuntimeError(f"contract states are missing from {app}")
    states = json.loads(match.group(1))
    expected = {
        "positiveEdit",
        "positiveReturn",
        "positive",
        "rejected",
        "reset",
    }
    if set(states) != expected:
        raise RuntimeError(
            "contract states must contain positiveEdit, positiveReturn, "
            "positive, rejected, and reset"
        )
    return states


def evidence_document(output_root: Path = ROOT) -> dict[str, object]:
    states = contract_states(output_root)
    reference = reference_document()
    comparison = reference["comparison"]
    supported = stroke_records()
    return {
        "schema": "candidate-frame-0002-create-vector-icon-system-evidence/2.0",
        "commission": {
            "id": "create-vector-icon-system",
            "criterion": (
                "The export contains exactly six named 24 by 24 SVG symbols and "
                "the reference raster comparison remains below 0.50 percent "
                "differing pixels."
            ),
        },
        "publication": PUBLICATION_ID,
        "objective": {
            "sprite": {
                "path": "exports/six-shapes.svg",
                "sha256": sha256_text(sprite_svg()),
                "bytes": len(sprite_svg().encode("utf-8")),
                "symbolCount": len(ICONS),
                "names": list(ICON_NAMES),
                "viewBox": VIEW_BOX,
                "sharedStroke": EXPORT_STROKE,
                "pathSetSha256": geometry_sha256(),
                "generatedGeometrySha256": generated_geometry_sha256(
                    EXPORT_STROKE
                ),
            },
            "rasterComparison": {
                "reference": "reference/reference-raster.json",
                "referenceSha256": IMMUTABLE_REFERENCE_SHA256,
                "referenceStroke": REFERENCE_STROKE,
                "immutable": True,
                "method": comparison["method"],
                "thresholdPercent": comparison["thresholdPercent"],
                "totalPixels": comparison["totalPixels"],
                "acceptedDifferingPixels": comparison["acceptedDifferingPixels"],
                "acceptedDifferingPercent": comparison["acceptedDifferingPercent"],
                "acceptedStatus": comparison["acceptedStatus"],
                "invalidDifferingPixels": comparison["invalidDifferingPixels"],
                "invalidDifferingPercent": comparison["invalidDifferingPercent"],
                "invalidStatus": comparison["invalidStatus"],
                "highlightCount": len(comparison["changedPixelHighlights"]),
                "supportedStrokes": [
                    {
                        "stroke": float(stroke),
                        "spriteSha256": record["sha256"],
                        "generatedGeometrySha256": record["geometrySha256"],
                        "spriteBytes": record["bytes"],
                        **record["comparison"],
                    }
                    for stroke, record in supported.items()
                ],
            },
        },
        "claims": [
            {
                "id": "positive",
                "claim": (
                    "The authored path changes the shared stroke from 2 px to "
                    "1.5 px and regenerates all six symbols with different "
                    "generated geometry and sprite hashes, then deliberately "
                    "returns to 2 px, regenerates, and exports the exact passing "
                    "reference sprite."
                ),
                "actions": [
                    {"type": "SET_STROKE", "selector": "#stroke-15-btn"},
                    {"type": "REGENERATE", "selector": "#regenerate-btn"},
                    {"type": "SET_STROKE", "selector": "#stroke-2-btn"},
                    {"type": "REGENERATE", "selector": "#regenerate-btn"},
                    {"type": "EXPORT", "selector": "#export-btn"},
                ],
                "checkpoints": [
                    {
                        "id": "edited",
                        "afterAction": 2,
                        "expectedState": states["positiveEdit"],
                        "assertions": [
                            {
                                "path": "accepted.rules.stroke",
                                "equals": EDIT_STROKE,
                            },
                            {
                                "path": "accepted.generatedGeometrySha256",
                                "equals": generated_geometry_sha256(EDIT_STROKE),
                            },
                            {
                                "path": "accepted.spriteSha256",
                                "equals": sha256_text(sprite_svg(EDIT_STROKE)),
                            },
                            {
                                "path": "accepted.symbols",
                                "equals": list(ICON_NAMES),
                            },
                        ],
                    },
                    {
                        "id": "returned",
                        "afterAction": 4,
                        "expectedState": states["positiveReturn"],
                        "assertions": [
                            {
                                "path": "accepted.rules.stroke",
                                "equals": EXPORT_STROKE,
                            },
                            {
                                "path": "accepted.generatedGeometrySha256",
                                "equals": generated_geometry_sha256(EXPORT_STROKE),
                            },
                            {
                                "path": "accepted.spriteSha256",
                                "equals": sha256_text(sprite_svg(EXPORT_STROKE)),
                            },
                            {
                                "path": "lastExport",
                                "equals": None,
                            },
                        ],
                    },
                ],
                "expectedState": states["positive"],
                "assertions": [
                    {"path": "accepted.rules.stroke", "equals": 2},
                    {"path": "accepted.symbols", "equals": list(ICON_NAMES)},
                    {
                        "path": "accepted.generatedGeometrySha256",
                        "equals": generated_geometry_sha256(EXPORT_STROKE),
                    },
                    {"path": "comparison.status", "equals": "pass"},
                    {"path": "comparison.differingPercent", "equals": 0},
                    {
                        "path": "lastExport.sha256",
                        "equals": sha256_text(sprite_svg()),
                    },
                ],
            },
            {
                "id": "rejected",
                "claim": (
                    "Moving the Pulse anchor from 12,18 to off-grid 13,17 fails "
                    "the comparison and highlights changed pixels without changing "
                    "the accepted icon system or export."
                ),
                "actions": [
                    {"type": "SET_STROKE", "selector": "#stroke-15-btn"},
                    {"type": "REGENERATE", "selector": "#regenerate-btn"},
                    {"type": "SET_STROKE", "selector": "#stroke-2-btn"},
                    {"type": "REGENERATE", "selector": "#regenerate-btn"},
                    {"type": "EXPORT", "selector": "#export-btn"},
                    {"type": "OFF_GRID", "selector": "#off-grid-btn"},
                ],
                "preserves": "positive",
                "expectedState": states["rejected"],
                "assertions": [
                    {"path": "accepted", "equals": states["positive"]["accepted"]},
                    {"path": "lastExport", "equals": states["positive"]["lastExport"]},
                    {"path": "comparison.status", "equals": "fail"},
                    {
                        "path": "comparison.differingPixels",
                        "equals": comparison["invalidDifferingPixels"],
                    },
                    {"path": "invalidEdit.to", "equals": [13, 17]},
                ],
            },
            {
                "id": "reset",
                "claim": (
                    "Restore icon fixture returns the immutable 2 px reference "
                    "geometry, selects Bloom, sets 800% zoom, and clears every "
                    "overlay."
                ),
                "actions": [
                    {"type": "RESTORE", "selector": "#restore-btn"},
                ],
                "expectedState": states["reset"],
                "assertions": [
                    {
                        "path": "accepted.fixture",
                        "equals": "reference-stroke-2",
                    },
                    {
                        "path": "accepted.rules.stroke",
                        "equals": REFERENCE_STROKE,
                    },
                    {"path": "accepted.symbols", "equals": list(ICON_NAMES)},
                    {"path": "selection", "equals": "bloom"},
                    {"path": "zoom", "equals": 800},
                    {"path": "comparison.overlay", "equals": []},
                    {"path": "comparison.status", "equals": "pass"},
                ],
            },
        ],
        "browserReplay": {
            "runner": "tests/frame_0002_09_browser.mjs",
            "source": (
                "channel.production.json#videos[0].live.scenes[0].actions"
            ),
            "selectors": [
                "#stroke-15-btn",
                "#regenerate-btn",
                "#stroke-2-btn",
                "#regenerate-btn",
                "#export-btn",
                "#off-grid-btn",
                "#restore-btn",
            ],
            "nondefaultSupportedStrokes": [1.0, 1.5, 2.5, 3.0],
            "assertion": (
                "The test suite launches a real Chromium-family browser, drives "
                "each selector, captures reducer state and generated SVG geometry "
                "after every click, independently hashes both the geometry and "
                "sprite source, and fails unless all six symbols change at 1.5 px "
                "before returning exactly to 2 px. Console and page exceptions "
                "also fail the replay."
            ),
            "positivePath": {
                "initialStroke": REFERENCE_STROKE,
                "editedStroke": EDIT_STROKE,
                "returnedStroke": EXPORT_STROKE,
                "editedGeometrySha256": generated_geometry_sha256(EDIT_STROKE),
                "returnedGeometrySha256": generated_geometry_sha256(
                    EXPORT_STROKE
                ),
                "editedSpriteSha256": sha256_text(sprite_svg(EDIT_STROKE)),
                "returnedSpriteSha256": sha256_text(sprite_svg(EXPORT_STROKE)),
                "generatedSymbolCount": len(ICONS),
            },
        },
        "renderer": {
            "path": "render.py",
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "frames": FRAME_COUNT,
            "duration": DURATION,
            "masterCodec": "ffv1",
            "frameSamples": {
                str(index): frame_digest(index)
                for index in (0, 42, 84, 132, FRAME_COUNT - 1)
            },
        },
        "rightsPrivacy": {
            "rightsAttestation": True,
            "privacyAttestation": True,
            "noSecrets": True,
            "statement": (
                "All icon geometry, interface code, immutable raster reference, "
                "thumbnail, snapshot, and renderer graphics are original to this "
                "candidate; no logos, copied icons, external fonts, or network "
                "assets are used."
            ),
        },
    }


def _svg_paths(icon: Icon, *, invalid: bool = False) -> str:
    paths = invalid_paths(icon) if invalid else icon.paths
    return "".join(f'<path d="{path_data(path)}"/>' for path in paths)


def thumbnail_svg() -> str:
    cells = []
    for index, icon in enumerate(ICONS):
        column = index % 3
        row = index // 3
        x = 48 + column * 202
        y = 160 + row * 154
        cells.append(
            f'<g transform="translate({x} {y})">'
            '<rect width="178" height="132" rx="18" fill="#111827" '
            'stroke="#334155"/>'
            f'<g transform="translate(41 12) scale(4)" fill="none" '
            'stroke="#d9f99d" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{_svg_paths(icon)}</g>'
            f'<text x="89" y="120" text-anchor="middle" fill="#a7b3c7" '
            f'font-family="monospace" font-size="14">{icon.label.upper()}</text>'
            "</g>"
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" '
        'role="img" aria-labelledby="title desc">\n'
        '  <title id="title">Six Shapes, One Grid</title>\n'
        '  <desc id="desc">Six original line icons share a two-pixel grid. '
        'An off-grid pulse anchor is rejected while the accepted sprite remains.</desc>\n'
        '  <rect width="960" height="540" fill="#080b12"/>\n'
        '  <path d="M0 112H960M0 512H960" stroke="#263246"/>\n'
        '  <text x="48" y="56" fill="#f8fafc" font-family="monospace" '
        'font-size="34" font-weight="700">SIX SHAPES / ONE GRID</text>\n'
        '  <text x="48" y="91" fill="#9fb0c8" font-family="monospace" '
        'font-size="18">24 × 24 · GRID 2 · SHARED STROKE 2</text>\n'
        f"  {''.join(cells)}\n"
        '  <g transform="translate(682 154)">\n'
        '    <rect width="230" height="285" rx="22" fill="#15111b" '
        'stroke="#fb7185" stroke-width="2"/>\n'
        '    <text x="22" y="38" fill="#fb7185" font-family="monospace" '
        'font-size="16" font-weight="700">OFF-GRID REJECTED</text>\n'
        '    <g transform="translate(61 58) scale(4.5)" fill="none" '
        'stroke="#fb7185" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{_svg_paths(ICON_BY_NAME["pulse"], invalid=True)}</g>\n'
        '    <circle cx="119.5" cy="134.5" r="7" fill="#fb7185"/>\n'
        '    <text x="22" y="203" fill="#f8fafc" font-family="monospace" '
        'font-size="15">ANCHOR 12,18 → 13,17</text>\n'
        '    <text x="22" y="232" fill="#f8fafc" font-family="monospace" '
        'font-size="15">EXPORT UNCHANGED</text>\n'
        '    <text x="22" y="260" fill="#86efac" font-family="monospace" '
        'font-size="15">6 SYMBOLS · PASS</text>\n'
        "  </g>\n"
        '  <rect x="48" y="466" width="864" height="34" rx="8" fill="#163326"/>\n'
        '  <text x="66" y="489" fill="#86efac" font-family="monospace" '
        'font-size="15">ACCEPTED SHA-256 IS BOUND IN EVIDENCE.JSON</text>\n'
        "</svg>\n"
    )


def snapshot_svg() -> str:
    reference = reference_document()["comparison"]
    invalid_percent = reference["invalidDifferingPercent"]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" '
        'role="img" aria-labelledby="title desc">\n'
        '  <title id="title">Vector icon system deterministic state snapshot</title>\n'
        '  <desc id="desc">The authored positive path regenerates all six icons '
        'at 1.5 pixels, returns to the passing 2 pixel reference, then demonstrates '
        'the rejected off-grid pulse and exact reset.</desc>\n'
        '  <rect width="960" height="540" fill="#0a0e17"/>\n'
        '  <rect x="34" y="32" width="892" height="476" rx="24" fill="#101827" '
        'stroke="#34445f"/>\n'
        '  <text x="66" y="82" fill="#f8fafc" font-family="monospace" '
        'font-size="30" font-weight="700">VECTOR TOKEN BENCH / SNAPSHOT</text>\n'
        '  <text x="66" y="116" fill="#9fb0c8" font-family="monospace" '
        'font-size="16">GRID 2 · VIEWBOX 0 0 24 24 · SIX NAMED SYMBOLS</text>\n'
        '  <rect x="66" y="150" width="522" height="230" rx="18" fill="#15130d" '
        'stroke="#fbbf24"/>\n'
        '  <text x="90" y="184" fill="#fbbf24" font-family="monospace" '
        'font-size="16" font-weight="700">LIVE EDIT / 2 → 1.5 / SIX REGENERATED</text>\n'
        + "".join(
            (
                f'<g transform="translate({86 + (index % 3) * 164} '
                f'{204 + (index // 3) * 88}) scale(2.8)" fill="none" '
                'stroke="#fde68a" stroke-width="1.5" stroke-linecap="round" '
                f'stroke-linejoin="round">{_svg_paths(icon)}</g>'
            )
            for index, icon in enumerate(ICONS)
        )
        + '\n  <text x="90" y="368" fill="#fde68a" font-family="monospace" '
        'font-size="11">GEOMETRY 623BA0EA · SPRITE 0DD372E6 · 24.3345% VS REF</text>\n'
        + '\n  <rect x="614" y="150" width="280" height="230" rx="18" '
        'fill="#1b1019" stroke="#fb7185"/>\n'
        '  <text x="638" y="184" fill="#fb7185" font-family="monospace" '
        'font-size="16" font-weight="700">REJECTED CANDIDATE</text>\n'
        '  <g transform="translate(696 205) scale(4.8)" fill="none" '
        'stroke="#fb7185" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{_svg_paths(ICON_BY_NAME["pulse"], invalid=True)}</g>\n'
        '  <text x="638" y="346" fill="#f8fafc" font-family="monospace" '
        f'font-size="15">{invalid_percent:.4f}% PIXELS DIFFER</text>\n'
        '  <rect x="66" y="410" width="828" height="66" rx="12" fill="#102b25"/>\n'
        '  <text x="90" y="438" fill="#86efac" font-family="monospace" '
        'font-size="16">RETURN: STROKE 2 · REGENERATE · EXPORT 6C32A2CE</text>\n'
        '  <text x="90" y="463" fill="#86efac" font-family="monospace" '
        'font-size="16">RESET: EXACT 2 PX · BLOOM · 800% · OVERLAYS CLEAR</text>\n'
        "</svg>\n"
    )


class Canvas:
    def __init__(self, width: int, height: int, background: RGB):
        self.width = width
        self.height = height
        self.pixels = bytearray(bytes(background) * (width * height))

    def rect(self, x: int, y: int, width: int, height: int, color: RGB) -> None:
        left = max(0, x)
        top = max(0, y)
        right = min(self.width, x + width)
        bottom = min(self.height, y + height)
        if left >= right or top >= bottom:
            return
        row = bytes(color) * (right - left)
        stride = self.width * 3
        for row_index in range(top, bottom):
            start = row_index * stride + left * 3
            self.pixels[start : start + len(row)] = row

    def circle(self, center_x: int, center_y: int, radius: int, color: RGB) -> None:
        if radius < 0:
            return
        radius_squared = radius * radius
        for offset_y in range(-radius, radius + 1):
            span = int(math.sqrt(max(0, radius_squared - offset_y * offset_y)))
            self.rect(
                center_x - span,
                center_y + offset_y,
                span * 2 + 1,
                1,
                color,
            )

    def line(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        color: RGB,
        thickness: int = 1,
    ) -> None:
        x0, y0 = start
        x1, y1 = end
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        step_x = 1 if x0 < x1 else -1
        step_y = 1 if y0 < y1 else -1
        error = dx + dy
        radius = max(0, thickness // 2)
        while True:
            self.circle(x0, y0, radius, color)
            if x0 == x1 and y0 == y1:
                return
            doubled = error * 2
            if doubled >= dy:
                error += dy
                x0 += step_x
            if doubled <= dx:
                error += dx
                y0 += step_y

    def text(self, x: int, y: int, value: str, color: RGB, scale: int = 2) -> None:
        cursor = x
        for character in value.upper():
            glyph = PIXEL_FONT.get(character, PIXEL_FONT[" "])
            for row_index, row in enumerate(glyph):
                for column_index, bit in enumerate(row):
                    if bit == "1":
                        self.rect(
                            cursor + column_index * scale,
                            y + row_index * scale,
                            scale,
                            scale,
                            color,
                        )
            cursor += 4 * scale

    def bytes(self) -> bytes:
        return bytes(self.pixels)


def _draw_icon(
    canvas: Canvas,
    icon: Icon,
    x: int,
    y: int,
    scale: int,
    color: RGB,
    stroke: float,
    *,
    invalid: bool = False,
) -> None:
    paths = invalid_paths(icon) if invalid else icon.paths
    thickness = max(1, round(stroke * scale))
    for path in paths:
        for start, end in zip(path, path[1:]):
            canvas.line(
                (x + round(start[0] * scale), y + round(start[1] * scale)),
                (x + round(end[0] * scale), y + round(end[1] * scale)),
                color,
                thickness,
            )


def _draw_grid(
    canvas: Canvas,
    x: int,
    y: int,
    size: int,
    step: int,
    color: RGB,
) -> None:
    for offset in range(0, size + 1, step):
        canvas.rect(x + offset, y, 1, size, color)
        canvas.rect(x, y + offset, size, 1, color)


def frame_rgb(frame_index: int) -> bytes:
    if frame_index < 0 or frame_index >= FRAME_COUNT:
        raise ValueError(f"frame index must be in 0..{FRAME_COUNT - 1}")
    second = frame_index / FPS
    if second < 0.8:
        phase = "initial"
        stroke = BASE_STROKE
        draft_stroke = BASE_STROKE
        accent = (96, 165, 250)
        status = "IMMUTABLE REFERENCE / GRID 2"
        detail = "STROKE 2 / ZERO DIFF"
    elif second < 2.2:
        phase = "draft-edit"
        stroke = BASE_STROKE
        draft_stroke = EDIT_STROKE
        accent = (251, 191, 36)
        status = "DRAFT TOKEN / 2 TO 1.5"
        detail = "ACCEPTED 2 / REGENERATE NEXT"
    elif second < 4.1:
        phase = "edited"
        stroke = EDIT_STROKE
        draft_stroke = EDIT_STROKE
        accent = (251, 191, 36)
        status = "6 SYMBOLS / 24.3345% DIFFER"
        detail = "GEOMETRY 623BA0EA / CHANGED"
    elif second < 5.5:
        phase = "draft-return"
        stroke = EDIT_STROKE
        draft_stroke = EXPORT_STROKE
        accent = (96, 165, 250)
        status = "RETURN TOKEN / DRAFT 2"
        detail = "ACCEPTED 1.5 / REGENERATE NEXT"
    elif second < 6.6:
        phase = "returned"
        stroke = EXPORT_STROKE
        draft_stroke = EXPORT_STROKE
        accent = (45, 212, 191)
        status = "6 SYMBOLS / 0.0000% PASS"
        detail = "RETURNED 2 / EXPORT NEXT"
    elif second < 8.6:
        phase = "accepted"
        stroke = EXPORT_STROKE
        draft_stroke = EXPORT_STROKE
        accent = (74, 222, 128)
        status = "6 SYMBOLS / 0.0000% PASS"
        detail = "RETURNED 2 / EXPORT 6C32A2CE"
    elif second < 11.8:
        phase = "rejected"
        stroke = EXPORT_STROKE
        draft_stroke = EXPORT_STROKE
        accent = (251, 113, 133)
        status = "OFF GRID 13,17 / REJECT"
        detail = "ACCEPTED EXPORT UNCHANGED"
    else:
        phase = "reset"
        stroke = BASE_STROKE
        draft_stroke = BASE_STROKE
        accent = (167, 139, 250)
        status = "RESTORE FIXTURE / EXACT"
        detail = "2PX / 800% / BLOOM / CLEAR"

    canvas = Canvas(WIDTH, HEIGHT, (8, 11, 18))
    for x in range(0, WIDTH, 48):
        canvas.rect(x, 0, 1, HEIGHT, (17, 24, 39))
    for y in range(0, HEIGHT, 48):
        canvas.rect(0, y, WIDTH, 1, (17, 24, 39))

    canvas.text(36, 28, "SIX SHAPES / ONE GRID", (241, 245, 249), 4)
    canvas.text(36, 60, "24 X 24 / GRID 2 / ROUND JOIN", (148, 163, 184), 2)
    canvas.rect(36, 92, 888, 2, (51, 65, 85))
    token_width = round(95 * draft_stroke)
    canvas.rect(36, 106, token_width, 8, accent)
    canvas.text(
        326,
        103,
        f"DRAFT {_number(draft_stroke)} / GENERATED {_number(stroke)}",
        accent,
        2,
    )

    card_width = 188
    card_height = 150
    positions: list[tuple[int, int]] = []
    for index, icon in enumerate(ICONS):
        column = index % 3
        row = index // 3
        card_x = 36 + column * 202
        card_y = 138 + row * 164
        positions.append((card_x, card_y))
        selected = phase == "reset" and index == 0
        border = (167, 139, 250) if selected else (48, 63, 84)
        canvas.rect(card_x, card_y, card_width, card_height, (15, 23, 38))
        canvas.rect(card_x, card_y, card_width, 2, border)
        canvas.rect(card_x, card_y + card_height - 2, card_width, 2, border)
        canvas.rect(card_x, card_y, 2, card_height, border)
        canvas.rect(card_x + card_width - 2, card_y, 2, card_height, border)
        icon_color = (217, 249, 157)
        _draw_grid(canvas, card_x + 52, card_y + 10, 84, 14, (26, 39, 57))
        _draw_icon(
            canvas,
            icon,
            card_x + 52,
            card_y + 10,
            3,
            icon_color,
            stroke,
        )
        canvas.text(card_x + 14, card_y + 128, icon.label, (159, 176, 200), 2)
        if selected:
            canvas.rect(card_x + 130, card_y + 126, 42, 12, (67, 48, 112))
            canvas.text(card_x + 136, card_y + 128, "1/6", (221, 214, 254), 1)

    panel_x = 648
    canvas.rect(panel_x, 138, 276, 314, (12, 18, 30))
    canvas.rect(panel_x, 138, 4, 314, accent)
    canvas.text(panel_x + 22, 160, "TOKEN INSPECTOR", (241, 245, 249), 2)
    canvas.text(panel_x + 22, 192, "SYMBOLS 6", (159, 176, 200), 2)
    canvas.text(panel_x + 22, 218, "VIEWBOX 24 X 24", (159, 176, 200), 2)
    canvas.text(panel_x + 22, 244, "GRID STEP 2", (159, 176, 200), 2)

    if phase == "rejected":
        pulse_x, pulse_y = positions[4]
        _draw_icon(
            canvas,
            ICON_BY_NAME["pulse"],
            pulse_x + 52,
            pulse_y + 10,
            3,
            (251, 113, 133),
            EXPORT_STROKE,
            invalid=True,
        )
        canvas.circle(pulse_x + 52 + 13 * 3, pulse_y + 10 + 17 * 3, 6, (251, 113, 133))
        changed = reference_document()["comparison"]["changedPixelHighlights"]
        for pixel in changed:
            if pixel["icon"] == "pulse":
                canvas.rect(
                    panel_x + 22 + int(pixel["x"]) * 3,
                    286 + int(pixel["y"]) * 3,
                    3,
                    3,
                    (251, 113, 133),
                )
        canvas.text(panel_x + 22, 270, "CHANGED PIXELS", (251, 113, 133), 2)
        canvas.text(panel_x + 112, 352, "FAIL GT 0.50%", (251, 113, 133), 2)
    elif phase == "accepted":
        canvas.rect(panel_x + 22, 282, 230, 96, (13, 45, 36))
        canvas.text(panel_x + 40, 302, "EXPORT SVG", (134, 239, 172), 2)
        canvas.text(panel_x + 40, 330, "SHA256", (134, 239, 172), 2)
        canvas.text(
            panel_x + 40,
            352,
            sha256_text(sprite_svg())[:16].upper(),
            (241, 245, 249),
            1,
        )
    elif phase == "returned":
        canvas.rect(panel_x + 22, 282, 230, 96, (10, 43, 42))
        canvas.text(panel_x + 40, 298, "REGENERATED 6", (153, 246, 228), 2)
        canvas.text(panel_x + 40, 324, "STROKE 2 / PASS", (153, 246, 228), 2)
        canvas.text(panel_x + 40, 352, "GEOM C3DF9DA9", (241, 245, 249), 1)
        canvas.text(panel_x + 40, 366, "EXPORT NEXT", (241, 245, 249), 1)
    elif phase == "edited":
        canvas.rect(panel_x + 22, 282, 230, 96, (52, 38, 10))
        canvas.text(panel_x + 40, 298, "REGENERATED 6", (253, 230, 138), 2)
        canvas.text(panel_x + 40, 324, "STROKE 1.5", (253, 230, 138), 2)
        canvas.text(panel_x + 40, 350, "GEOM 623BA0EA", (241, 245, 249), 1)
        canvas.text(panel_x + 40, 364, "SPRITE 0DD372E6", (241, 245, 249), 1)
    elif phase == "draft-edit":
        canvas.rect(panel_x + 22, 282, 230, 96, (52, 38, 10))
        canvas.text(panel_x + 40, 302, "EDIT TOKEN", (253, 230, 138), 2)
        canvas.text(panel_x + 40, 328, "2 TO 1.5", (253, 230, 138), 2)
        canvas.text(panel_x + 40, 354, "REGENERATE NEXT", (241, 245, 249), 1)
    elif phase == "draft-return":
        canvas.rect(panel_x + 22, 282, 230, 96, (16, 30, 51))
        canvas.text(panel_x + 40, 302, "RETURN TOKEN", (147, 197, 253), 2)
        canvas.text(panel_x + 40, 328, "1.5 TO 2", (147, 197, 253), 2)
        canvas.text(panel_x + 40, 354, "REGENERATE NEXT", (241, 245, 249), 1)
    elif phase == "reset":
        canvas.rect(panel_x + 22, 282, 230, 96, (34, 25, 62))
        canvas.text(panel_x + 40, 302, "ZOOM 800%", (221, 214, 254), 2)
        canvas.text(panel_x + 40, 328, "SELECT BLOOM", (221, 214, 254), 2)
        canvas.text(panel_x + 40, 354, "OVERLAY CLEAR", (221, 214, 254), 2)
    else:
        canvas.rect(panel_x + 22, 282, 230, 96, (16, 30, 51))
        canvas.text(panel_x + 40, 302, "REFERENCE", (147, 197, 253), 2)
        canvas.text(panel_x + 40, 328, "STROKE 2", (147, 197, 253), 2)
        canvas.text(panel_x + 40, 354, "READY", (147, 197, 253), 2)

    canvas.rect(36, 474, 888, 42, (17, 24, 39))
    canvas.rect(36, 474, 8, 42, accent)
    canvas.text(58, 486, status, accent, 2)
    canvas.text(570, 486, detail, (203, 213, 225), 2)
    playhead = min(887, round(frame_index / (FRAME_COUNT - 1) * 887))
    canvas.rect(36, 528, 888, 3, (31, 41, 57))
    canvas.rect(36, 528, playhead, 3, accent)
    return canvas.bytes()


def frame_digest(frame_index: int) -> str:
    return sha256_bytes(frame_rgb(frame_index))


def iter_frames() -> Iterator[bytes]:
    for frame_index in range(FRAME_COUNT):
        yield frame_rgb(frame_index)


def ffmpeg_command(ffmpeg: str, target: Path) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{WIDTH}x{HEIGHT}",
        "-framerate",
        str(FPS),
        "-i",
        "pipe:0",
        "-an",
        "-map_metadata",
        "-1",
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-coder",
        "1",
        "-context",
        "1",
        "-g",
        "1",
        "-slicecrc",
        "1",
        "-threads",
        "1",
        "-pix_fmt",
        "bgr0",
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-f",
        "matroska",
        str(target),
    ]


def resolve_binary(value: str, label: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute() or candidate.parent != Path("."):
        if not candidate.is_file():
            raise RuntimeError(f"{label} executable does not exist: {candidate}")
        return str(candidate.resolve())
    if value == label:
        for environment_name in (
            label.upper(),
            f"{label.upper()}_PATH",
        ):
            environment_value = os.environ.get(environment_name)
            if environment_value and Path(environment_value).is_file():
                return str(Path(environment_value).resolve())
    resolved = shutil.which(value)
    if resolved:
        return resolved
    if value == label:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            executable = f"{label}.exe" if os.name == "nt" else label
            pattern = (
                "Microsoft/WinGet/Packages/Gyan.FFmpeg*/"
                f"**/bin/{executable}"
            )
            matches = sorted(Path(local_app_data).glob(pattern))
            if matches:
                return str(matches[-1].resolve())
    raise RuntimeError(f"{label} executable not found: {value}")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(value, encoding="utf-8", newline="\n")
    partial.replace(path)


def _write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_bytes(value)
    partial.replace(path)


def generated_text_assets() -> dict[Path, str]:
    states = contract_states()
    return {
        Path("exports/six-shapes.svg"): sprite_svg(),
        Path("evidence.json"): deterministic_json(evidence_document()),
        Path("snapshots/create-vector-icon-system.svg"): snapshot_svg(),
        Path("snapshots/state-snapshot.json"): deterministic_json(states),
        Path("thumbs/create-vector-icon-system.svg"): thumbnail_svg(),
    }


def write_text_assets(output_root: Path) -> None:
    source_reference = ROOT / REFERENCE_RELATIVE
    target_reference = output_root / REFERENCE_RELATIVE
    if source_reference.resolve() != target_reference.resolve():
        _write_bytes(target_reference, source_reference.read_bytes())
    immutable_reference.cache_clear()
    immutable_reference(target_reference)
    for relative, content in generated_text_assets().items():
        _write_text(output_root / relative, content)


def render_master(ffmpeg: str, output_root: Path) -> Path:
    target = output_root / "masters" / f"{PUBLICATION_ID}.mkv"
    partial = target.with_name(f"{target.stem}.partial.mkv")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial.unlink(missing_ok=True)
    command = ffmpeg_command(ffmpeg, partial)
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if process.stdin is None or process.stderr is None:
            raise RuntimeError("FFmpeg pipes were not created")
        try:
            for frame in iter_frames():
                process.stdin.write(frame)
            process.stdin.close()
        except BrokenPipeError:
            process.stdin.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
        process.stderr.close()
        return_code = process.wait()
        if return_code:
            raise RuntimeError(f"FFmpeg failed: {stderr or return_code}")
        if not partial.is_file() or partial.stat().st_size <= 0:
            raise RuntimeError("FFmpeg did not create an FFV1 master")
        partial.replace(target)
        return target
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if process is not None and process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        if process is not None and process.stderr is not None and not process.stderr.closed:
            process.stderr.close()
        partial.unlink(missing_ok=True)


def probe_media(ffprobe: str, path: Path) -> dict[str, object]:
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
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(
            f"ffprobe failed for {path}: {completed.stderr.strip() or completed.returncode}"
        )
    payload = json.loads(completed.stdout)
    streams = payload.get("streams", [])
    if len(streams) != 1:
        raise RuntimeError(f"expected one video stream in {path}")
    stream = streams[0]
    duration = float(payload.get("format", {}).get("duration", 0))
    return {
        "codec": stream.get("codec_name"),
        "pixel_format": stream.get("pix_fmt"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "duration": round(duration, 6),
        "color_space": stream.get("color_space"),
        "color_transfer": stream.get("color_transfer"),
        "color_primaries": stream.get("color_primaries"),
        "color_range": stream.get("color_range"),
    }


def _artifact(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def delivery_document(output_root: Path, ffprobe: str) -> dict[str, object]:
    master = output_root / "masters" / f"{PUBLICATION_ID}.mkv"
    mp4 = output_root / "media" / f"{PUBLICATION_ID}.mp4"
    webm = output_root / "media" / f"{PUBLICATION_ID}.webm"
    sprite = output_root / "exports" / "six-shapes.svg"
    thumb = output_root / "thumbs" / f"{PUBLICATION_ID}.svg"
    snapshot = output_root / "snapshots" / f"{PUBLICATION_ID}.svg"
    channel = output_root / "channel.json"
    app = output_root / "apps" / f"{PUBLICATION_ID}.html"
    production = output_root / "channel.production.json"
    evidence = output_root / "evidence.json"
    reference = output_root / REFERENCE_RELATIVE
    state_snapshot = output_root / "snapshots" / "state-snapshot.json"
    readme = output_root / "README.md"
    renderer = output_root / "render.py"
    required = (
        master,
        mp4,
        webm,
        sprite,
        thumb,
        snapshot,
        channel,
        app,
        production,
        evidence,
        reference,
        state_snapshot,
        readme,
        renderer,
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"cannot write delivery; missing {missing[0]}")
    return {
        "schema": "candidate-frame-0002-delivery/1.0",
        "publication": PUBLICATION_ID,
        "artifacts": {
            "master": {**_artifact(master, output_root), **probe_media(ffprobe, master)},
            "mp4": {**_artifact(mp4, output_root), **probe_media(ffprobe, mp4)},
            "webm": {**_artifact(webm, output_root), **probe_media(ffprobe, webm)},
            "sprite": _artifact(sprite, output_root),
            "thumbnail": _artifact(thumb, output_root),
            "snapshot": _artifact(snapshot, output_root),
            "channel": _artifact(channel, output_root),
            "production": _artifact(production, output_root),
            "app": _artifact(app, output_root),
            "evidence": _artifact(evidence, output_root),
            "reference": _artifact(reference, output_root),
            "stateSnapshot": _artifact(state_snapshot, output_root),
            "documentation": _artifact(readme, output_root),
            "renderer": _artifact(renderer, output_root),
        },
    }


def verify_text_assets(output_root: Path) -> None:
    reference_path = output_root / REFERENCE_RELATIVE
    immutable_reference.cache_clear()
    immutable_reference(reference_path)
    for relative, expected in generated_text_assets().items():
        path = output_root / relative
        if not path.is_file():
            raise RuntimeError(f"missing deterministic asset: {path}")
        if path.read_text(encoding="utf-8") != expected:
            raise RuntimeError(f"deterministic asset differs: {path}")


def render_plan(output_root: Path, ffmpeg: str) -> dict[str, object]:
    return {
        "schema": "candidate-frame-0002-render-plan/1.0",
        "publication": PUBLICATION_ID,
        "width": WIDTH,
        "height": HEIGHT,
        "fps": FPS,
        "frames": FRAME_COUNT,
        "duration": DURATION,
        "master": str(output_root / "masters" / f"{PUBLICATION_ID}.mkv"),
        "immutableReference": {
            "path": str(output_root / REFERENCE_RELATIVE),
            "sha256": IMMUTABLE_REFERENCE_SHA256,
        },
        "textArtifacts": [
            relative.as_posix() for relative in generated_text_assets()
        ],
        "command": ffmpeg_command(
            ffmpeg,
            output_root / "masters" / f"{PUBLICATION_ID}.mkv",
        ),
        "frameSamples": {
            str(index): frame_digest(index)
            for index in (0, 42, 84, 132, FRAME_COUNT - 1)
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        choices=("render", "delivery", "verify"),
        default="render",
    )
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--output-root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = args.output_root.resolve()
    try:
        if args.command == "render":
            if args.dry_run:
                print(deterministic_json(render_plan(output_root, args.ffmpeg)), end="")
                return 0
            ffmpeg = resolve_binary(args.ffmpeg, "ffmpeg")
            write_text_assets(output_root)
            master = render_master(ffmpeg, output_root)
            print(master)
        elif args.command == "delivery":
            if args.dry_run:
                raise RuntimeError("delivery dry-run is not supported")
            ffprobe = resolve_binary(args.ffprobe, "ffprobe")
            document = delivery_document(output_root, ffprobe)
            path = output_root / "delivery.json"
            _write_text(path, deterministic_json(document))
            print(path)
        else:
            verify_text_assets(output_root)
            print(f"{output_root}: deterministic text assets verified")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
