#!/usr/bin/env python3
"""Render and document the deterministic Island Herd Threshold publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parent
PUBLICATION_ID = "ecosystem-island-threshold"
CHANNEL_ID = "candidate-frame-0003-03"
TITLE = "Will the Island Herd Hold?"
MODEL_ID = "seeded-island-herd/1.0"
SEED = 31415
MINIMUM_SEED = 1
MAXIMUM_SEED = 0xFFFFFFFF
INITIAL_POPULATION_MILLI = 104_000
INITIAL_RESOURCES_MILLI = 146_000
RESOURCE_CEILING_MILLI = 180_000
STABLE_LOW_MILLI = 80_000
STABLE_HIGH_MILLI = 120_000
COLLAPSE_MILLI = 10_000
HORIZON = 600
RATE_STABLE_MILLI = 240
RATE_TRANSITION_MILLI = 450
RATE_COLLAPSE_MILLI = 600
FPS = 12
DURATION = 22
WIDTH = 960
HEIGHT = 540

MANIFEST_PATH = ROOT / "channel.production.json"
CHANNEL_PATH = ROOT / "channel.json"
APP_PATH = ROOT / "apps" / f"{PUBLICATION_ID}.html"
THUMB_PATH = ROOT / "thumbs" / f"{PUBLICATION_ID}.svg"
MASTER_PATH = ROOT / "masters" / f"{PUBLICATION_ID}.mkv"
MP4_PATH = ROOT / "media" / f"{PUBLICATION_ID}.mp4"
WEBM_PATH = ROOT / "media" / f"{PUBLICATION_ID}.webm"
FIXTURE_EXPORT_PATH = ROOT / "exports" / "fixture-series.json"
SNAPSHOT_PATH = ROOT / "snapshots" / "canonical-states.json"
EVIDENCE_PATH = ROOT / "evidence.json"
DELIVERY_PATH = ROOT / "delivery.json"


@dataclass(frozen=True)
class RenderSpec:
    publication_id: str = PUBLICATION_ID
    title: str = TITLE
    width: int = WIDTH
    height: int = HEIGHT
    fps: int = FPS
    duration: int = DURATION
    frame_count: int = FPS * DURATION
    master_relative: Path = Path("masters") / f"{PUBLICATION_ID}.mkv"
    thumbnail_relative: Path = Path("thumbs") / f"{PUBLICATION_ID}.svg"


@dataclass(frozen=True)
class ModelPoint:
    tick: int
    population_milli: int
    resources_milli: int
    support_milli: int
    weather_milli: int
    random_state: int

    def compact(self) -> list[int]:
        return [
            self.tick,
            self.population_milli,
            self.resources_milli,
            self.support_milli,
            self.weather_milli,
            self.random_state,
        ]

    def export(self) -> dict[str, int | float]:
        return {
            "tick": self.tick,
            "population": display_milli(self.population_milli),
            "populationMilli": self.population_milli,
            "resources": display_milli(self.resources_milli),
            "resourcesMilli": self.resources_milli,
            "support": display_milli(self.support_milli),
            "supportMilli": self.support_milli,
            "weatherMilli": self.weather_milli,
            "randomState": self.random_state,
        }


SPEC = RenderSpec()


def display_milli(value: int) -> int | float:
    rounded = round(value / 1000, 3)
    return int(rounded) if float(rounded).is_integer() else rounded


def xorshift32(value: int) -> int:
    value &= 0xFFFFFFFF
    value ^= (value << 13) & 0xFFFFFFFF
    value ^= value >> 17
    value ^= (value << 5) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def supported_population_milli(resources_milli: int) -> int:
    """Return the herd size supportable by the current grass resource."""
    if resources_milli <= 90_000:
        return 8_000
    if resources_milli >= 120_000:
        return 112_000
    distance = resources_milli - 90_000
    return 8_000 + (
        104_000 * distance * distance // (30_000 * 30_000)
    )


def normalize_seed(seed: int) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not MINIMUM_SEED <= seed <= MAXIMUM_SEED:
        raise ValueError(
            f"seed must be between {MINIMUM_SEED} and {MAXIMUM_SEED}"
        )
    return seed


def normalize_ticks(ticks: int) -> int:
    if isinstance(ticks, bool) or not isinstance(ticks, int):
        raise ValueError("ticks must be an integer")
    if not 0 <= ticks <= HORIZON:
        raise ValueError(f"ticks must be between 0 and {HORIZON}")
    return ticks


def normalize_rate_milli(
    grazing_rate: float | int,
    *,
    rate_is_milli: bool = False,
) -> int:
    if isinstance(grazing_rate, bool):
        raise ValueError("grazing rate must be numeric")
    if rate_is_milli:
        if not isinstance(grazing_rate, int):
            raise ValueError("milli grazing rate must be an integer")
        rate_milli = grazing_rate
    else:
        try:
            numeric_rate = float(grazing_rate)
        except (TypeError, ValueError) as exc:
            raise ValueError("grazing rate must be numeric") from exc
        if not math.isfinite(numeric_rate):
            raise ValueError("grazing rate must be finite")
        if not 0 <= numeric_rate <= 0.75:
            raise ValueError("grazing rate must be between 0.00 and 0.75")
        scaled_rate = numeric_rate * 1000
        rate_milli = round(scaled_rate)
        if abs(scaled_rate - rate_milli) > 1e-7:
            raise ValueError(
                "grazing rate must use increments of one thousandth"
            )
    if not 0 <= rate_milli <= 750:
        raise ValueError("grazing rate must be between 0.00 and 0.75")
    return rate_milli


def initial_point(seed: int = SEED) -> ModelPoint:
    seed = normalize_seed(seed)
    return ModelPoint(
        tick=0,
        population_milli=INITIAL_POPULATION_MILLI,
        resources_milli=INITIAL_RESOURCES_MILLI,
        support_milli=supported_population_milli(INITIAL_RESOURCES_MILLI),
        weather_milli=0,
        random_state=seed,
    )


def step_model(point: ModelPoint, grazing_rate_milli: int) -> ModelPoint:
    grazing_rate_milli = normalize_rate_milli(
        grazing_rate_milli,
        rate_is_milli=True,
    )
    random_state = xorshift32(point.random_state)
    weather_milli = ((random_state & 1023) - 512) * 550 // 1024
    regrowth_milli = (
        (RESOURCE_CEILING_MILLI - point.resources_milli) * 40 // 1000
    )
    grazing_loss_milli = grazing_rate_milli * 6400 // 1000
    resources_milli = max(
        0,
        min(
            RESOURCE_CEILING_MILLI,
            point.resources_milli
            + regrowth_milli
            - grazing_loss_milli
            + weather_milli,
        ),
    )
    support_milli = supported_population_milli(resources_milli)
    gap = support_milli - point.population_milli
    movement = abs(gap) * 35 // 1000
    if gap and movement == 0:
        movement = 1
    if gap < 0:
        movement = -movement
    population_milli = max(0, point.population_milli + movement)
    return ModelPoint(
        tick=point.tick + 1,
        population_milli=population_milli,
        resources_milli=resources_milli,
        support_milli=support_milli,
        weather_milli=weather_milli,
        random_state=random_state,
    )


def simulate(
    grazing_rate: float | int,
    ticks: int = HORIZON,
    *,
    rate_is_milli: bool = False,
    seed: int = SEED,
) -> list[ModelPoint]:
    rate_milli = normalize_rate_milli(
        grazing_rate,
        rate_is_milli=rate_is_milli,
    )
    ticks = normalize_ticks(ticks)
    seed = normalize_seed(seed)
    points = [initial_point(seed)]
    for _ in range(ticks):
        points.append(step_model(points[-1], rate_milli))
    return points


def collapse_crossing(points: Sequence[ModelPoint]) -> int | None:
    return next(
        (
            point.tick
            for point in points
            if point.tick > 0 and point.population_milli < COLLAPSE_MILLI
        ),
        None,
    )


def trace_digest(points: Sequence[ModelPoint]) -> str | None:
    if not points:
        return None
    return compact_trace_digest([point.compact() for point in points])


def compact_trace_digest(points: Sequence[Sequence[int]]) -> str | None:
    if not points:
        return None
    value = 0x811C9DC5
    for point in points:
        text = ":".join(str(item) for item in point) + ";"
        for character in text:
            value ^= ord(character)
            value = (value * 0x01000193) & 0xFFFFFFFF
    return f"{value:08x}"


def fixture_summary(rate_milli: int) -> dict[str, Any]:
    points = simulate(rate_milli, rate_is_milli=True)
    final = points[-1]
    populations = [point.population_milli for point in points]
    resources = [point.resources_milli for point in points]
    crossing = collapse_crossing(points)
    return {
        "grazingRate": display_milli(rate_milli),
        "horizon": HORIZON,
        "seed": SEED,
        "thresholds": {
            "stableBand": [
                display_milli(STABLE_LOW_MILLI),
                display_milli(STABLE_HIGH_MILLI),
            ],
            "collapseBelow": display_milli(COLLAPSE_MILLI),
            "collapseBeforeTick": 300,
        },
        "final": {
            "tick": final.tick,
            "population": display_milli(final.population_milli),
            "populationMilli": final.population_milli,
            "resources": display_milli(final.resources_milli),
            "resourcesMilli": final.resources_milli,
            "support": display_milli(final.support_milli),
            "supportMilli": final.support_milli,
        },
        "populationRange": {
            "minimum": display_milli(min(populations)),
            "maximum": display_milli(max(populations)),
        },
        "resourceRange": {
            "minimum": display_milli(min(resources)),
            "maximum": display_milli(max(resources)),
        },
        "collapseCrossingTick": crossing,
        "traceDigest": trace_digest(points),
        "series": [point.compact() for point in points],
    }


def prediction_history(rate_milli: int, choice: str) -> dict[str, Any]:
    return {"grazingRate": display_milli(rate_milli), "choice": choice}


def state_summary(
    *,
    rate_milli: int,
    speed: int,
    prediction: str | None,
    prediction_revision: int,
    history: list[dict[str, Any]],
    points: Sequence[ModelPoint],
    outcome: str | None,
    status: str,
    message: str,
    inspection_open: bool,
    export_prepared: bool = False,
    export_point_count: int = 0,
    export_trace_digest: str | None = None,
) -> dict[str, Any]:
    point = points[-1] if points else initial_point()
    return {
        "seed": SEED,
        "grazingRate": display_milli(rate_milli),
        "speed": speed,
        "initialPopulation": display_milli(INITIAL_POPULATION_MILLI),
        "initialResources": display_milli(INITIAL_RESOURCES_MILLI),
        "tick": point.tick if points else 0,
        "population": display_milli(point.population_milli),
        "resources": display_milli(point.resources_milli),
        "support": display_milli(point.support_milli),
        "prediction": prediction,
        "predictionRevision": prediction_revision,
        "predictionHistory": history,
        "traceLength": len(points),
        "traceDigest": trace_digest(points),
        "collapseCrossingTick": collapse_crossing(points),
        "outcome": outcome,
        "running": False,
        "status": status,
        "message": message,
        "inspectionOpen": inspection_open,
        "exportPrepared": export_prepared,
        "exportPointCount": export_point_count,
        "exportTraceDigest": export_trace_digest,
    }


def canonical_states_document() -> dict[str, Any]:
    stable_points = simulate(RATE_STABLE_MILLI, rate_is_milli=True)
    transition_points = simulate(RATE_TRANSITION_MILLI, rate_is_milli=True)
    collapse_points = simulate(RATE_COLLAPSE_MILLI, rate_is_milli=True)
    opening = state_summary(
        rate_milli=RATE_STABLE_MILLI,
        speed=1,
        prediction=None,
        prediction_revision=0,
        history=[],
        points=[],
        outcome=None,
        status="ready",
        message="Choose what happens before the trace is revealed.",
        inspection_open=False,
    )
    stable_history = [prediction_history(RATE_STABLE_MILLI, "band")]
    stable = state_summary(
        rate_milli=RATE_STABLE_MILLI,
        speed=1,
        prediction="band",
        prediction_revision=0,
        history=stable_history,
        points=stable_points,
        outcome="band",
        status="stable-inspected",
        message="Prediction: stable band. Observed outcome: inspected stable band through tick 600.",
        inspection_open=True,
    )
    transition_history = [
        prediction_history(RATE_TRANSITION_MILLI, "transition")
    ]
    transition = state_summary(
        rate_milli=RATE_TRANSITION_MILLI,
        speed=4,
        prediction="transition",
        prediction_revision=0,
        history=transition_history,
        points=transition_points,
        outcome="transition",
        status="transition",
        message="Prediction: transition. Observed outcome: transition outside the stable band, ending at 45.117.",
        inspection_open=False,
    )
    collapse_history = [
        prediction_history(RATE_STABLE_MILLI, "band"),
        prediction_history(RATE_COLLAPSE_MILLI, "collapse"),
    ]
    collapse = state_summary(
        rate_milli=RATE_COLLAPSE_MILLI,
        speed=2,
        prediction="collapse",
        prediction_revision=1,
        history=collapse_history,
        points=collapse_points,
        outcome="collapse",
        status="collapse",
        message="Prediction: collapse. Observed outcome: collapse below 10 at tick 134.",
        inspection_open=False,
    )
    export = state_summary(
        rate_milli=RATE_COLLAPSE_MILLI,
        speed=2,
        prediction="collapse",
        prediction_revision=1,
        history=collapse_history,
        points=collapse_points,
        outcome="collapse",
        status="exported",
        message="Export prepared from the observed collapse outcome: 601 points · digest 8bb46765.",
        inspection_open=False,
        export_prepared=True,
        export_point_count=HORIZON + 1,
        export_trace_digest=trace_digest(collapse_points),
    )
    return {
        "schema": "island-herd-canonical-states/1.0",
        "model": MODEL_ID,
        "opening": opening,
        "stable": stable,
        "transition": transition,
        "collapse": collapse,
        "export": export,
        "reset": opening,
    }


def model_contract() -> dict[str, Any]:
    return {
        "schema": MODEL_ID,
        "seed": SEED,
        "fixedPointScale": 1000,
        "initial": {
            "populationMilli": INITIAL_POPULATION_MILLI,
            "resourcesMilli": INITIAL_RESOURCES_MILLI,
            "randomState": SEED,
        },
        "limits": {
            "resourceCeilingMilli": RESOURCE_CEILING_MILLI,
            "stableLowMilli": STABLE_LOW_MILLI,
            "stableHighMilli": STABLE_HIGH_MILLI,
            "collapseMilli": COLLAPSE_MILLI,
            "horizon": HORIZON,
            "minimumRateMilli": 0,
            "maximumRateMilli": 750,
            "minimumSeed": MINIMUM_SEED,
            "maximumSeed": MAXIMUM_SEED,
        },
        "outcomes": {
            "band": "Population stays between 80 and 120 through tick 600.",
            "transition": "Population leaves the stable band without falling below 10.",
            "collapse": "Population falls below 10 before tick 600.",
        },
        "rules": [
            "Advance xorshift32 once per tick from the selected seed.",
            "Convert the low ten random bits into a weather pulse from -0.275 to +0.274 resource units.",
            "Regrow four percent of the gap to 180 resource units, then subtract 6.4 times the grazing rate and add the weather pulse.",
            "Support 8 herd units at 90 resources or less and 112 at 120 or more; between those points support rises with the square of the recovered share.",
            "Move the herd 3.5 percent of the integer gap toward the supported size each tick, with a one-thousandth minimum move while a gap remains.",
        ],
    }


def fixture_export_document() -> dict[str, Any]:
    fixtures = []
    for rate_milli, label in (
        (RATE_STABLE_MILLI, "stable-band"),
        (RATE_TRANSITION_MILLI, "transition"),
        (RATE_COLLAPSE_MILLI, "collapse"),
    ):
        points = simulate(rate_milli, rate_is_milli=True)
        fixtures.append(
            {
                "id": label,
                "grazingRate": display_milli(rate_milli),
                "seed": SEED,
                "horizon": HORIZON,
                "collapseCrossingTick": collapse_crossing(points),
                "traceDigest": trace_digest(points),
                "series": [point.export() for point in points],
            }
        )
    return {
        "schema": "island-herd-fixture-series/1.0",
        "model": model_contract(),
        "fixtures": fixtures,
    }


def deterministic_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_record(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    if not path.is_file():
        raise RuntimeError(f"required artifact does not exist: {path}")
    return {
        "path": relative,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


FONT: dict[str, tuple[str, ...]] = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    ":": ("00000", "00110", "00110", "00000", "00110", "00110", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "=": ("00000", "11111", "00000", "11111", "00000", "00000", "00000"),
    "<": ("00010", "00100", "01000", "10000", "01000", "00100", "00010"),
    ">": ("01000", "00100", "00010", "00001", "00010", "00100", "01000"),
    "%": ("11001", "11010", "00100", "01000", "10110", "00110", "00000"),
    "[": ("01110", "01000", "01000", "01000", "01000", "01000", "01110"),
    "]": ("01110", "00010", "00010", "00010", "00010", "00010", "01110"),
    "'": ("00100", "00100", "00000", "00000", "00000", "00000", "00000"),
    ",": ("00000", "00000", "00000", "00000", "00110", "00100", "01000"),
    " ": ("00000",) * 7,
}


class Canvas:
    def __init__(self, width: int, height: int, color: tuple[int, int, int]):
        self.width = width
        self.height = height
        self.pixels = bytearray(bytes(color) * (width * height))

    def rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: tuple[int, int, int],
    ) -> None:
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + width)
        y1 = min(self.height, y + height)
        if x0 >= x1 or y0 >= y1:
            return
        row = bytes(color) * (x1 - x0)
        for py in range(y0, y1):
            start = (py * self.width + x0) * 3
            self.pixels[start : start + len(row)] = row

    def border(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: tuple[int, int, int],
        thickness: int = 2,
    ) -> None:
        self.rect(x, y, width, thickness, color)
        self.rect(x, y + height - thickness, width, thickness, color)
        self.rect(x, y, thickness, height, color)
        self.rect(x + width - thickness, y, thickness, height, color)

    def circle(
        self,
        cx: int,
        cy: int,
        radius: int,
        color: tuple[int, int, int],
    ) -> None:
        radius_squared = radius * radius
        for offset_y in range(-radius, radius + 1):
            width = 0
            while (
                width + 1 <= radius
                and (width + 1) * (width + 1) + offset_y * offset_y
                <= radius_squared
            ):
                width += 1
            self.rect(cx - width, cy + offset_y, width * 2 + 1, 1, color)

    def line(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        color: tuple[int, int, int],
        thickness: int = 2,
    ) -> None:
        delta_x = abs(x1 - x0)
        step_x = 1 if x0 < x1 else -1
        delta_y = -abs(y1 - y0)
        step_y = 1 if y0 < y1 else -1
        error = delta_x + delta_y
        radius = max(0, thickness // 2)
        while True:
            self.rect(x0 - radius, y0 - radius, thickness, thickness, color)
            if x0 == x1 and y0 == y1:
                break
            twice_error = 2 * error
            if twice_error >= delta_y:
                error += delta_y
                x0 += step_x
            if twice_error <= delta_x:
                error += delta_x
                y0 += step_y

    def text(
        self,
        x: int,
        y: int,
        value: str,
        color: tuple[int, int, int],
        scale: int = 2,
        spacing: int = 1,
    ) -> int:
        cursor_x = x
        for character in value.upper():
            glyph = FONT.get(character, FONT["?"])
            for row_index, row in enumerate(glyph):
                for column_index, bit in enumerate(row):
                    if bit == "1":
                        self.rect(
                            cursor_x + column_index * scale,
                            y + row_index * scale,
                            scale,
                            scale,
                            color,
                        )
            cursor_x += (5 + spacing) * scale
        return cursor_x

    def bytes(self) -> bytes:
        return bytes(self.pixels)


INK = (12, 31, 43)
PAPER = (246, 241, 222)
SEA = (17, 56, 71)
SEA_LIGHT = (24, 79, 93)
GRASS = (82, 173, 125)
MINT = (153, 226, 177)
HERD = (255, 186, 84)
CORAL = (242, 95, 76)
WHITE = (255, 255, 252)
MUTED = (171, 191, 191)
GRID = (64, 101, 108)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def smooth(value: float) -> float:
    value = clamp(value)
    return value * value * (3 - 2 * value)


def draw_pill(
    canvas: Canvas,
    x: int,
    y: int,
    width: int,
    label: str,
    *,
    fill: tuple[int, int, int] = SEA_LIGHT,
    text_color: tuple[int, int, int] = WHITE,
) -> None:
    canvas.rect(x, y, width, 34, fill)
    canvas.border(x, y, width, 34, MUTED, 1)
    canvas.text(x + 10, y + 10, label, text_color, 2)


def draw_island(canvas: Canvas, population_milli: int, resources_milli: int) -> None:
    canvas.circle(176, 318, 116, (31, 91, 93))
    canvas.circle(176, 308, 101, (48, 121, 101))
    canvas.circle(138, 287, 72, GRASS)
    canvas.circle(222, 292, 70, GRASS)
    canvas.rect(102, 287, 148, 60, GRASS)
    resource_width = max(8, min(205, resources_milli * 205 // RESOURCE_CEILING_MILLI))
    canvas.rect(73, 414, 205, 12, INK)
    canvas.rect(73, 414, resource_width, 12, MINT if resources_milli >= 90_000 else CORAL)
    canvas.text(73, 436, f"GRASS {display_milli(resources_milli)}", PAPER, 2)
    count = max(1, min(32, round(population_milli / 4000)))
    for index in range(count):
        angle_x = ((index * 47 + 19) % 151) - 75
        angle_y = ((index * 71 + 11) % 91) - 45
        if angle_x * angle_x * 2 + angle_y * angle_y * 4 > 12_000:
            angle_x //= 2
            angle_y //= 2
        x = 176 + angle_x
        y = 304 + angle_y
        canvas.circle(x, y, 5, HERD)
        canvas.rect(x + 4, y - 3, 5, 3, HERD)


def chart_xy(tick: int, population_milli: int) -> tuple[int, int]:
    x = 420 + tick * 475 // HORIZON
    y = 414 - population_milli * 272 // 130_000
    return x, y


def draw_chart(
    canvas: Canvas,
    points: Sequence[ModelPoint],
    progress: float,
    color: tuple[int, int, int],
    *,
    crossing_tick: int | None = None,
    empty_label: str | None = None,
) -> None:
    x0, y0, width, height = 420, 142, 475, 272
    canvas.rect(x0, y0, width, height, (11, 42, 52))
    band_top = chart_xy(0, STABLE_HIGH_MILLI)[1]
    band_bottom = chart_xy(0, STABLE_LOW_MILLI)[1]
    canvas.rect(x0, band_top, width, band_bottom - band_top, (29, 78, 67))
    collapse_y = chart_xy(0, COLLAPSE_MILLI)[1]
    canvas.rect(x0, collapse_y, width, 2, CORAL)
    for tick in (0, 150, 300, 450, 600):
        x, _ = chart_xy(tick, 0)
        canvas.rect(x, y0, 1, height, GRID)
        canvas.text(x - 18, 426, str(tick), MUTED, 2)
    for population in (0, 40, 80, 120):
        _, y = chart_xy(0, population * 1000)
        canvas.rect(x0, y, width, 1, GRID)
        canvas.text(378, y - 6, str(population), MUTED, 2)
    canvas.border(x0, y0, width, height, MUTED, 2)
    canvas.text(420, 108, "POPULATION / TICK", PAPER, 3)
    if not points:
        canvas.text(520, 265, empty_label or "TRACE HIDDEN", MUTED, 3)
        return
    visible_tick = max(0, min(HORIZON, int(HORIZON * clamp(progress))))
    visible = [point for point in points if point.tick <= visible_tick]
    sampled = visible[::4]
    if visible and (not sampled or sampled[-1].tick != visible[-1].tick):
        sampled.append(visible[-1])
    for first, second in zip(sampled, sampled[1:]):
        canvas.line(*chart_xy(first.tick, first.population_milli), *chart_xy(second.tick, second.population_milli), color, 3)
    if visible:
        final_x, final_y = chart_xy(visible[-1].tick, visible[-1].population_milli)
        canvas.circle(final_x, final_y, 5, WHITE)
    if crossing_tick is not None and visible_tick >= crossing_tick:
        crossing_point = points[crossing_tick]
        crossing_x, crossing_y = chart_xy(
            crossing_point.tick, crossing_point.population_milli
        )
        canvas.rect(crossing_x - 1, y0, 2, height, CORAL)
        canvas.circle(crossing_x, crossing_y, 7, CORAL)
        canvas.text(crossing_x + 10, crossing_y - 23, f"CROSS {crossing_tick}", CORAL, 2)


def draw_header(canvas: Canvas, rate_label: str, phase_label: str) -> None:
    canvas.text(42, 28, "ISLAND HERD PREDICTION LAB", PAPER, 3)
    draw_pill(canvas, 574, 24, 126, f"SEED {SEED}")
    draw_pill(canvas, 710, 24, 206, f"GRAZING RATE {rate_label}")
    canvas.rect(42, 79, 874, 2, SEA_LIGHT)
    canvas.text(42, 94, phase_label, MINT, 2)


def frame_rgb(spec: RenderSpec, frame_index: int) -> bytes:
    if not 0 <= frame_index < spec.frame_count:
        raise ValueError("frame index outside render")
    seconds = frame_index / spec.fps
    canvas = Canvas(spec.width, spec.height, SEA)
    stable = simulate(RATE_STABLE_MILLI, rate_is_milli=True)
    collapse = simulate(RATE_COLLAPSE_MILLI, rate_is_milli=True)
    stable_final = stable[-1]
    collapse_final = collapse[-1]
    crossing = collapse_crossing(collapse)

    if seconds < 4:
        draw_header(canvas, ".24", "1 / PREDICT BEFORE THE TRACE")
        canvas.text(42, 132, "PREDICT THE OUTCOME", WHITE, 4)
        canvas.text(42, 170, "BY TICK 600", WHITE, 4)
        choices = (
            (42, "STABLE 80-120", (28, 83, 84), HERD),
            (332, "TRANSITION 10-80", (24, 76, 86), MUTED),
            (622, "COLLAPSE < 10", (74, 48, 55), MUTED),
        )
        for x, label, fill, border in choices:
            canvas.rect(x, 242, 270, 76, fill)
            canvas.border(
                x,
                242,
                270,
                76,
                border if label.startswith("STABLE") and seconds >= 1.6 else MUTED,
                4 if label.startswith("STABLE") and seconds >= 1.6 else 2,
            )
            canvas.text(x + 18, 270, label, PAPER, 2)
        canvas.text(42, 356, "GRAZING RATE 0.24 / SEED 31415", HERD, 3)
        canvas.text(42, 400, "PREDICTION IS A FORECAST.", MUTED, 2)
        canvas.text(42, 430, "THE OBSERVED OUTCOME COMES AFTER REVEAL.", PAPER, 2)
        canvas.rect(42, 478, 850, 12, INK)
        canvas.rect(42, 478, int(850 * clamp(seconds / 4)), 12, HERD)
    elif seconds < 8.5:
        progress = smooth((seconds - 4.3) / 2.5)
        draw_header(canvas, ".24", "2 / REVEAL THE STABLE RUN")
        point = stable[min(HORIZON, int(progress * HORIZON))]
        draw_island(canvas, point.population_milli, point.resources_milli)
        draw_chart(canvas, stable, progress, HERD)
        canvas.text(72, 142, "PREDICTION", MUTED, 2)
        canvas.text(72, 168, "STABLE BAND", HERD, 3)
        canvas.text(72, 210, "OBSERVED OUTCOME", MUTED, 2)
        canvas.text(
            72,
            236,
            "STABLE BAND" if progress >= 0.99 else "OBSERVING",
            MINT if progress >= 0.99 else PAPER,
            3,
        )
        if progress >= 0.99:
            canvas.rect(414, 458, 481, 58, (30, 104, 78))
            canvas.text(
                436,
                477,
                (
                    f"TICK {stable_final.tick} / HERD "
                    f"{display_milli(stable_final.population_milli)} / BAND HELD"
                ),
                WHITE,
                2,
            )
        else:
            canvas.text(420, 458, f"RUNNING TICK {point.tick}", PAPER, 2)
    elif seconds < 11.5:
        reveal = smooth((seconds - 8.5) / 2.2)
        draw_header(canvas, ".60", "3 / CHANGE THE RATE. REVISE THE CALL.")
        canvas.text(42, 145, "GRAZING RATE", MUTED, 3)
        canvas.rect(42, 178, 650, 18, INK)
        canvas.rect(42, 178, int(650 * (0.24 + 0.36 * reveal) / 0.75), 18, CORAL)
        canvas.circle(42 + int(650 * (0.24 + 0.36 * reveal) / 0.75), 187, 12, WHITE)
        canvas.text(720, 174, f"{0.24 + 0.36 * reveal:.2f}", WHITE, 3)
        canvas.rect(42, 246, 850, 94, (32, 70, 77))
        canvas.border(42, 246, 850, 94, CORAL if reveal > 0.55 else MUTED, 4)
        canvas.text(68, 274, "PREDICTION", MUTED, 2)
        canvas.text(68, 302, "COLLAPSE", CORAL, 4)
        canvas.text(42, 382, "OBSERVED OUTCOME: NOT REVEALED YET", PAPER, 2)
        canvas.text(42, 424, "SAME SEED. ONLY THE GRAZING RATE CHANGED.", MUTED, 2)
    elif seconds < 16:
        progress = smooth((seconds - 11.8) / 2.5)
        point = collapse[min(HORIZON, int(progress * HORIZON))]
        draw_header(canvas, ".60", "4 / WATCH FOR THE CROSSING")
        draw_island(canvas, point.population_milli, point.resources_milli)
        draw_chart(
            canvas,
            collapse,
            progress,
            CORAL,
            crossing_tick=crossing,
        )
        canvas.text(72, 142, "PREDICTION", MUTED, 2)
        canvas.text(72, 168, "COLLAPSE", CORAL, 3)
        canvas.text(72, 210, "OBSERVED OUTCOME", MUTED, 2)
        canvas.text(
            72,
            236,
            "COLLAPSE" if crossing is not None and progress >= crossing / HORIZON else "OBSERVING",
            CORAL if crossing is not None and progress >= crossing / HORIZON else PAPER,
            3,
        )
        if crossing is not None and progress >= crossing / HORIZON:
            canvas.rect(414, 458, 481, 58, (124, 48, 45))
            canvas.text(
                436,
                477,
                (
                    f"BELOW 10 AT TICK {crossing} / FINAL "
                    f"{display_milli(collapse_final.population_milli)}"
                ),
                WHITE,
                2,
            )
        else:
            canvas.text(420, 458, f"RUNNING TICK {point.tick}", PAPER, 2)
    elif seconds < 18.5:
        draw_header(canvas, ".60", "5 / EXPORT THE OBSERVED COLLAPSE")
        canvas.text(42, 132, "FULL SERIES EXPORT READY", WHITE, 4)
        canvas.rect(42, 190, 850, 250, (11, 42, 52))
        canvas.border(42, 190, 850, 250, HERD, 3)
        canvas.text(72, 220, "OBSERVED OUTCOME", MUTED, 2)
        canvas.text(360, 220, "COLLAPSE", CORAL, 3)
        canvas.text(72, 264, "POINTS", MUTED, 2)
        canvas.text(360, 258, str(HORIZON + 1), HERD, 4)
        canvas.text(72, 310, "SERIES DIGEST", MUTED, 2)
        canvas.text(360, 304, trace_digest(collapse) or "", HERD, 4)
        canvas.text(72, 356, "GRAZING RATE", MUTED, 2)
        canvas.text(360, 350, "0.60", PAPER, 3)
        canvas.text(72, 398, "TICKS", MUTED, 2)
        canvas.text(360, 392, "0 THROUGH 600", PAPER, 3)
        canvas.text(42, 474, "EXPORT PROOF IS VISIBLE BEFORE RESET.", MINT, 2)
    elif seconds < 20:
        draw_header(canvas, ".24", "6 / EXACT RESET")
        canvas.text(42, 128, "BACK TO THE OPENING STATE", WHITE, 3)
        rows = (
            ("SEED", "31415"),
            ("GRAZING RATE", ".24"),
            ("SPEED", "1X"),
            ("POP / GRASS", "104 / 146"),
            ("TICK", "0"),
            ("PREDICTION", "NONE"),
            ("TRACE", "EMPTY"),
            ("EXPORT", "NONE"),
        )
        for index, (label, value) in enumerate(rows):
            y = 178 + index * 37
            canvas.text(72, y, label, MUTED, 2)
            canvas.text(330, y, value, MINT if index < 4 else HERD, 2)
            canvas.rect(600, y + 5, 240, 2, SEA_LIGHT)
        canvas.rect(600, 174, 240, 288, (11, 42, 52))
        canvas.border(600, 174, 240, 288, MUTED, 2)
        canvas.text(630, 292, "NO TRACE", MUTED, 3)
        canvas.text(630, 336, "NO EXPORT", MUTED, 3)
        canvas.text(630, 380, "READY", HERD, 3)
    else:
        draw_header(canvas, ".24", "7 / YOUR TURN")
        canvas.text(42, 130, "YOUR TURN", HERD, 6)
        canvas.text(42, 190, "1 / CHOOSE A GRAZING RATE", PAPER, 3)
        canvas.text(42, 230, "2 / PREDICT STABLE, TRANSITION, OR COLLAPSE", PAPER, 2)
        canvas.text(42, 270, "3 / REVEAL THE TRACE", PAPER, 3)
        canvas.text(42, 310, "4 / INSPECT THE OBSERVED OUTCOME", PAPER, 2)
        canvas.text(42, 350, "5 / EXPORT ALL 601 POINTS", PAPER, 3)
        canvas.rect(42, 402, 850, 70, (24, 76, 86))
        canvas.border(42, 402, 850, 70, HERD, 3)
        canvas.text(70, 426, "TRY 0.45: TRANSITION ENDS NEAR 45", MINT, 3)
    return canvas.bytes()


def frame_digest(frame_index: int) -> str:
    return hashlib.sha256(frame_rgb(SPEC, frame_index)).hexdigest()


def thumbnail_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" aria-labelledby="title description">
  <title id="title">Will the Island Herd Hold?</title>
  <desc id="description">A prediction-first island herd model offers stable, transition, and collapse outcomes before any trace is shown.</desc>
  <rect width="960" height="540" fill="#113847"/>
  <rect x="36" y="32" width="888" height="476" rx="28" fill="#0c1f2b" stroke="#52ad7d" stroke-width="3"/>
  <text x="72" y="92" fill="#99e2b1" font-family="Arial, sans-serif" font-size="24" font-weight="700" letter-spacing="2">ISLAND HERD PREDICTION LAB</text>
  <text x="72" y="174" fill="#fffdf6" font-family="Arial, sans-serif" font-size="58" font-weight="800">Will the herd hold?</text>
  <text x="72" y="220" fill="#abbfbf" font-family="Arial, sans-serif" font-size="24">Seed 31415 · grazing rate 0.24 · predict first</text>
  <rect x="72" y="270" width="240" height="104" rx="18" fill="#1d534f" stroke="#ffba54" stroke-width="6"/>
  <text x="92" y="333" fill="#fffdf6" font-family="Arial, sans-serif" font-size="22" font-weight="800">STABLE 80–120</text>
  <rect x="330" y="270" width="240" height="104" rx="18" fill="#174c56" stroke="#77d6e3" stroke-width="3"/>
  <text x="346" y="333" fill="#fffdf6" font-family="Arial, sans-serif" font-size="21" font-weight="800">TRANSITION 10–80</text>
  <rect x="588" y="270" width="240" height="104" rx="18" fill="#572f30" stroke="#f25f4c" stroke-width="3"/>
  <text x="614" y="333" fill="#fffdf6" font-family="Arial, sans-serif" font-size="22" font-weight="800">COLLAPSE &lt; 10</text>
  <rect x="72" y="418" width="778" height="14" rx="7" fill="#113847"/>
  <rect x="72" y="418" width="286" height="14" rx="7" fill="#ffba54"/>
  <text x="72" y="473" fill="#ffba54" font-family="Arial, sans-serif" font-size="24" font-weight="700">YOUR TURN: PREDICT, REVEAL, INSPECT, EXPORT.</text>
</svg>
"""


def write_or_check(path: Path, content: str, check: bool) -> None:
    encoded = content.encode("utf-8")
    if check:
        if not path.is_file() or path.read_bytes() != encoded:
            raise RuntimeError(f"{path} is missing or stale")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def write_generated_artifacts(*, check: bool = False) -> None:
    write_or_check(THUMB_PATH, thumbnail_svg(), check)
    write_or_check(
        FIXTURE_EXPORT_PATH,
        deterministic_json(fixture_export_document()),
        check,
    )
    write_or_check(
        SNAPSHOT_PATH,
        deterministic_json(canonical_states_document()),
        check,
    )


def ffmpeg_command(ffmpeg: str, target: Path, spec: RenderSpec = SPEC) -> list[str]:
    return [
        ffmpeg,
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{spec.width}x{spec.height}",
        "-framerate",
        str(spec.fps),
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
        "-color_range",
        "pc",
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-f",
        "matroska",
        str(target),
    ]


def _resolve_executable(value: str) -> str | None:
    cleaned = value.strip()
    if (
        len(cleaned) >= 2
        and cleaned[0] == cleaned[-1]
        and cleaned[0] in {'"', "'"}
    ):
        cleaned = cleaned[1:-1]
    if not cleaned:
        return None
    expanded = Path(os.path.expandvars(cleaned)).expanduser()
    if expanded.is_absolute() or expanded.parent != Path("."):
        return str(expanded.resolve()) if expanded.is_file() else None
    return shutil.which(value)


def _common_media_paths(name: str) -> Iterable[Path]:
    executable = f"{name}.exe" if os.name == "nt" else name
    for raw in (
        "/usr/bin",
        "/usr/local/bin",
        "/opt/homebrew/bin",
        "/opt/local/bin",
    ):
        yield Path(raw) / executable
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            yield Path(root) / "ffmpeg" / "bin" / executable
            yield Path(root) / "FFmpeg" / "bin" / executable
    local = os.environ.get("LOCALAPPDATA")
    if local:
        packages = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if packages.is_dir():
            for package in sorted(packages.glob("Gyan.FFmpeg*")):
                yield from sorted(package.glob(f"ffmpeg-*/bin/{executable}"))


def resolve_binary(name: str, explicit: str | None = None) -> str:
    environment = {
        "ffmpeg": ("RAPP_FFMPEG", "FFMPEG", "FFMPEG_BIN"),
        "ffprobe": ("RAPP_FFPROBE", "FFPROBE", "FFPROBE_BIN"),
    }
    for value in (
        explicit,
        *(os.environ.get(variable) for variable in environment.get(name, ())),
        name,
    ):
        if value:
            resolved = _resolve_executable(value)
            if resolved:
                return resolved
    for candidate in _common_media_paths(name):
        if candidate.is_file():
            return str(candidate.resolve())
    variables = ", ".join(environment.get(name, ()))
    raise RuntimeError(
        f"{name} not found via explicit path, {variables}, PATH, or common locations"
    )


def render_master(
    ffmpeg: str,
    target: Path = MASTER_PATH,
    spec: RenderSpec = SPEC,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    temporary.unlink(missing_ok=True)
    process = subprocess.Popen(
        ffmpeg_command(ffmpeg, temporary, spec),
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if process.stdin is None or process.stderr is None:
        raise RuntimeError("ffmpeg pipes were not created")
    try:
        for frame_index in range(spec.frame_count):
            process.stdin.write(frame_rgb(spec, frame_index))
        process.stdin.close()
        error = process.stderr.read().decode("utf-8", errors="replace").strip()
        return_code = process.wait()
    except OSError as exc:
        if process.poll() is None:
            process.kill()
        process.wait()
        error = process.stderr.read().decode("utf-8", errors="replace").strip()
        if not process.stdin.closed:
            try:
                process.stdin.close()
            except OSError as close_exc:
                if not error:
                    error = str(close_exc)
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            f"ffmpeg failed while receiving frames: {error or exc}"
        ) from exc
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        temporary.unlink(missing_ok=True)
        raise
    finally:
        process.stderr.close()
    if return_code:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed: {error or return_code}")
    os.replace(temporary, target)


def evidence_document() -> dict[str, Any]:
    stable = fixture_summary(RATE_STABLE_MILLI)
    transition = fixture_summary(RATE_TRANSITION_MILLI)
    collapse = fixture_summary(RATE_COLLAPSE_MILLI)
    states = canonical_states_document()
    binding_paths = (
        "README.md",
        "apps/ecosystem-island-threshold.html",
        "channel.production.json",
        "channel.json",
        "exports/fixture-series.json",
        "masters/ecosystem-island-threshold.mkv",
        "media/ecosystem-island-threshold.mp4",
        "media/ecosystem-island-threshold.webm",
        "render.py",
        "snapshots/canonical-states.json",
        "thumbs/ecosystem-island-threshold.svg",
        "verify_dom.mjs",
    )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    actions = manifest["videos"][0]["live"]["scenes"][0]["actions"]
    return {
        "schema": "ecosystem-island-threshold-evidence/1.0",
        "channel": CHANNEL_ID,
        "publication": PUBLICATION_ID,
        "commission": {
            "id": "explore-ecosystem-threshold",
            "criterion": "Seed 31415 at grazing 0.24 ends inside 80–120 at tick 600; grazing 0.60 falls below 10 before tick 300.",
            "canonicalFlow": [
                "Predict that 0.24 stays in band before revealing a trace.",
                "Run to tick 600 and inspect the stable band result.",
                "Offer transition as a distinct prediction for intermediate rates such as 0.45.",
                "Choose 0.60, revise the prediction to collapse, and observe the marked crossing.",
                "Export all 601 collapse points and show digest 8bb46765.",
                "Reset seed, rate, speed, population, resources, tick, prediction, and trace exactly.",
                "Invite the viewer to choose a rate, predict, reveal, inspect, and export.",
            ],
        },
        "model": model_contract(),
        "fixtures": [
            {
                "id": "stable-band",
                "prediction": "band",
                **stable,
            },
            {
                "id": "transition",
                "prediction": "transition",
                **transition,
            },
            {
                "id": "collapse",
                "prediction": "collapse",
                **collapse,
            },
        ],
        "claims": [
            {
                "id": "stable",
                "claim": "The 0.24 run is hidden until a prediction is made, then reaches tick 600 at population 112 without leaving the 80–120 band.",
                "expectedState": states["stable"],
                "assertions": [
                    {"path": "grazingRate", "equals": 0.24},
                    {"path": "tick", "equals": 600},
                    {"path": "population", "equals": 112},
                    {"path": "outcome", "equals": "band"},
                    {"path": "inspectionOpen", "equals": True},
                ],
            },
            {
                "id": "transition",
                "claim": "The three-outcome model classifies grazing 0.45 as a transition: it leaves the stable band, never crosses below 10, and ends at 45.117.",
                "expectedState": states["transition"],
                "assertions": [
                    {"path": "grazingRate", "equals": 0.45},
                    {"path": "prediction", "equals": "transition"},
                    {"path": "collapseCrossingTick", "equals": None},
                    {"path": "population", "equals": 45.117},
                    {"path": "outcome", "equals": "transition"},
                ],
            },
            {
                "id": "collapse",
                "claim": "After the rate changes to 0.60 and the prediction is revised, the herd crosses below 10 at tick 134 and ends at population 8.",
                "expectedState": states["collapse"],
                "assertions": [
                    {"path": "grazingRate", "equals": 0.6},
                    {"path": "predictionRevision", "equals": 1},
                    {"path": "collapseCrossingTick", "equals": 134},
                    {"path": "population", "equals": 8},
                    {"path": "outcome", "equals": "collapse"},
                ],
            },
            {
                "id": "export",
                "claim": "After the collapse result, the canonical replay visibly prepares all 601 points and computed digest 8bb46765 before reset.",
                "expectedState": states["export"],
                "assertions": [
                    {"path": "status", "equals": "exported"},
                    {"path": "exportPrepared", "equals": True},
                    {"path": "exportPointCount", "equals": HORIZON + 1},
                    {"path": "exportTraceDigest", "equals": "8bb46765"},
                    {"path": "traceLength", "equals": HORIZON + 1},
                ],
            },
            {
                "id": "reset",
                "claim": "Reset returns the exact opening model snapshot while a separate visible banner confirms the activation.",
                "expectedState": states["reset"],
                "assertions": [
                    {"path": "seed", "equals": SEED},
                    {"path": "grazingRate", "equals": 0.24},
                    {"path": "speed", "equals": 1},
                    {"path": "tick", "equals": 0},
                    {"path": "prediction", "equals": None},
                    {"path": "traceLength", "equals": 0},
                    {"path": "exportPrepared", "equals": False},
                ],
            },
            {
                "id": "your-turn",
                "claim": "The live replay ends on a visible invitation to choose a grazing rate, predict, reveal, inspect, and export.",
                "expectedState": states["reset"],
                "assertions": [
                    {"path": "status", "equals": "ready"},
                    {"path": "prediction", "equals": None},
                    {"path": "traceLength", "equals": 0},
                ],
            },
        ],
        "manifestReplay": {
            "manifest": "channel.production.json",
            "scene": 0,
            "actionCount": len(actions),
            "allowedActions": ["click", "key", "scroll", "type"],
            "coordinateFree": True,
            "readySelector": "#predict-band-btn",
            "checkpoints": [
                {
                    "afterAction": 6,
                    "claim": "stable",
                    "selector": "#stable-result",
                },
                {
                    "afterAction": 15,
                    "claim": "collapse",
                    "selector": "#collapse-result",
                },
                {
                    "afterAction": 18,
                    "claim": "export",
                    "selector": "#series-export",
                },
                {
                    "afterAction": 21,
                    "claim": "reset",
                    "selector": "#reset-proof",
                },
                {
                    "afterAction": 22,
                    "claim": "your-turn",
                    "selector": "#your-turn",
                },
            ],
        },
        "seriesExport": {
            **artifact_record("exports/fixture-series.json"),
            "containsEveryTick": True,
            "fixtureCount": 3,
            "pointCountPerFixture": HORIZON + 1,
        },
        "canonicalSnapshots": artifact_record(
            "snapshots/canonical-states.json"
        ),
        "artifactBindings": {
            path: artifact_record(path) for path in binding_paths
        },
        "rightsPrivacy": {
            "rightsAttestation": True,
            "privacyAttestation": True,
            "noSecrets": True,
            "syntheticModelData": True,
            "originalRendererAndIllustration": True,
            "externalResources": [],
            "personalData": False,
        },
    }


def resolve_document_path(document: Any, path: str) -> Any:
    current = document
    for component in path.split("."):
        current = current[component]
    return current


def validate_evidence(document: dict[str, Any]) -> None:
    if document.get("schema") != "ecosystem-island-threshold-evidence/1.0":
        raise RuntimeError("evidence schema is incorrect")
    if document.get("model") != model_contract():
        raise RuntimeError("evidence model contract is stale")
    fixtures = {fixture["id"]: fixture for fixture in document["fixtures"]}
    if set(fixtures) != {"stable-band", "transition", "collapse"}:
        raise RuntimeError("evidence must contain all three outcome fixtures")
    stable = fixtures["stable-band"]
    transition = fixtures["transition"]
    collapse = fixtures["collapse"]
    for fixture, rate_milli in (
        (stable, RATE_STABLE_MILLI),
        (transition, RATE_TRANSITION_MILLI),
        (collapse, RATE_COLLAPSE_MILLI),
    ):
        series = fixture.get("series")
        if not isinstance(series, list) or len(series) != HORIZON + 1:
            raise RuntimeError("fixture series must contain every tick")
        for tick, point in enumerate(series):
            if (
                not isinstance(point, list)
                or len(point) != 6
                or any(isinstance(value, bool) or not isinstance(value, int) for value in point)
                or point[0] != tick
            ):
                raise RuntimeError(f"fixture series point {tick} is malformed")
        if series[0] != initial_point().compact():
            raise RuntimeError("fixture series opening point is incorrect")
        if fixture.get("seed") != SEED:
            raise RuntimeError("fixture seed is incorrect")
        if fixture.get("horizon") != HORIZON:
            raise RuntimeError("fixture horizon is incorrect")
        if fixture.get("grazingRate") != display_milli(rate_milli):
            raise RuntimeError("fixture grazing rate is incorrect")
        expected_crossing = next(
            (
                point[0]
                for point in series[1:]
                if point[1] < COLLAPSE_MILLI
            ),
            None,
        )
        if fixture.get("collapseCrossingTick") != expected_crossing:
            raise RuntimeError("fixture collapse crossing is stale")
        if fixture.get("traceDigest") != compact_trace_digest(series):
            raise RuntimeError("fixture trace digest is stale")
        final = fixture.get("final", {})
        final_point = series[-1]
        if (
            final.get("tick") != final_point[0]
            or final.get("populationMilli") != final_point[1]
            or final.get("resourcesMilli") != final_point[2]
            or final.get("supportMilli") != final_point[3]
        ):
            raise RuntimeError("fixture final measurements are stale")
    if any(
        not STABLE_LOW_MILLI <= point[1] <= STABLE_HIGH_MILLI
        for point in stable["series"]
    ):
        raise RuntimeError("stable fixture leaves the commission band")
    if stable["collapseCrossingTick"] is not None:
        raise RuntimeError("stable fixture unexpectedly crosses below ten")
    if transition["collapseCrossingTick"] is not None:
        raise RuntimeError("transition fixture unexpectedly crosses below ten")
    transition_populations = [point[1] for point in transition["series"]]
    if (
        all(
            STABLE_LOW_MILLI <= population <= STABLE_HIGH_MILLI
            for population in transition_populations
        )
        or transition["final"]["populationMilli"] < COLLAPSE_MILLI
    ):
        raise RuntimeError("transition fixture does not demonstrate an intermediate outcome")
    crossing = collapse["collapseCrossingTick"]
    if not isinstance(crossing, int) or crossing >= 300:
        raise RuntimeError("collapse fixture does not cross before tick 300")
    if collapse["series"][crossing][1] >= COLLAPSE_MILLI:
        raise RuntimeError("collapse crossing point is not below ten")
    if collapse["series"][crossing - 1][1] < COLLAPSE_MILLI:
        raise RuntimeError("collapse crossing is not the first point below ten")
    for claim in document["claims"]:
        for assertion in claim["assertions"]:
            if (
                resolve_document_path(claim["expectedState"], assertion["path"])
                != assertion["equals"]
            ):
                raise RuntimeError(
                    f"stale assertion {claim['id']}:{assertion['path']}"
                )


def probe_media(ffprobe: str, relative: str) -> dict[str, Any]:
    path = ROOT / relative
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        (
            "stream=codec_name,codec_type,pix_fmt,width,height,color_space,color_transfer,"
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
            f"ffprobe failed for {relative}: "
            f"{completed.stderr.strip() or completed.returncode}"
        )
    try:
        payload = json.loads(completed.stdout)
        streams = payload["streams"]
        video_streams = [
            stream for stream in streams if stream.get("codec_type") == "video"
        ]
        if len(video_streams) != 1:
            raise ValueError("expected exactly one video stream")
        stream = video_streams[0]
        duration_value = round(float(payload["format"]["duration"]), 6)
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"malformed ffprobe result for {relative}") from exc
    duration: int | float = duration_value
    if float(duration_value).is_integer():
        duration = int(duration_value)
    result = {
        "codec": stream.get("codec_name"),
        "duration": duration,
        "height": stream.get("height"),
        "pixelFormat": stream.get("pix_fmt"),
        "streamCount": len(streams),
        "audioStreamCount": sum(
            stream.get("codec_type") == "audio" for stream in streams
        ),
        "width": stream.get("width"),
        "colorPrimaries": stream.get("color_primaries"),
        "colorRange": stream.get("color_range"),
        "colorSpace": stream.get("color_space"),
        "colorTransfer": stream.get("color_transfer"),
    }
    return result


DELIVERY_FILES = (
    ".gitattributes",
    "README.md",
    "apps/ecosystem-island-threshold.html",
    "channel.json",
    "channel.production.json",
    "evidence.json",
    "exports/fixture-series.json",
    "masters/ecosystem-island-threshold.mkv",
    "media/ecosystem-island-threshold.mp4",
    "media/ecosystem-island-threshold.webm",
    "render.py",
    "snapshots/canonical-states.json",
    "thumbs/ecosystem-island-threshold.svg",
    "verify_dom.mjs",
)


def delivery_document(ffprobe: str) -> dict[str, Any]:
    artifacts = {path: artifact_record(path) for path in DELIVERY_FILES}
    document = {
        "schema": "candidate-frame-delivery/1.0",
        "channel": CHANNEL_ID,
        "publication": PUBLICATION_ID,
        "artifacts": artifacts,
        "media": {
            "master": {
                **artifacts["masters/ecosystem-island-threshold.mkv"],
                **probe_media(
                    ffprobe, "masters/ecosystem-island-threshold.mkv"
                ),
            },
            "mp4": {
                **artifacts["media/ecosystem-island-threshold.mp4"],
                **probe_media(
                    ffprobe, "media/ecosystem-island-threshold.mp4"
                ),
            },
            "webm": {
                **artifacts["media/ecosystem-island-threshold.webm"],
                **probe_media(
                    ffprobe, "media/ecosystem-island-threshold.webm"
                ),
            },
        },
        "bindings": {
            "evidenceSha256": artifacts["evidence.json"]["sha256"],
            "productionSha256": artifacts["channel.production.json"]["sha256"],
            "compiledChannelSha256": artifacts["channel.json"]["sha256"],
            "fixtureSeriesSha256": artifacts["exports/fixture-series.json"][
                "sha256"
            ],
        },
    }
    validate_delivery(document)
    return document


def validate_delivery(document: dict[str, Any]) -> None:
    if document.get("schema") != "candidate-frame-delivery/1.0":
        raise RuntimeError("delivery schema is incorrect")
    expected = {
        "master": {
            "codec": "ffv1",
            "pixelFormat": "bgr0",
            "colorPrimaries": None,
            "colorRange": "pc",
            "colorSpace": "gbr",
            "colorTransfer": None,
        },
        "mp4": {
            "codec": "h264",
            "pixelFormat": "yuv420p",
            "colorPrimaries": "bt709",
            "colorRange": "tv",
            "colorSpace": "bt709",
            "colorTransfer": "bt709",
        },
        "webm": {
            "codec": "vp9",
            "pixelFormat": "yuv420p",
            "colorPrimaries": "bt709",
            "colorRange": "tv",
            "colorSpace": "bt709",
            "colorTransfer": "bt709",
        },
    }
    for kind, fields in expected.items():
        record = document.get("media", {}).get(kind, {})
        for field, value in fields.items():
            if record.get(field) != value:
                raise RuntimeError(
                    f"{kind} {field} must equal {value!r}"
                )
        if (
            record.get("width"),
            record.get("height"),
            record.get("duration"),
        ) != (WIDTH, HEIGHT, DURATION):
            raise RuntimeError(f"{kind} dimensions or duration are incorrect")
        if record.get("streamCount") != 1 or record.get("audioStreamCount") != 0:
            raise RuntimeError(f"{kind} must contain one silent video stream")


def validate_manifest() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("schema") != "rapp-vision-production/1.0":
        raise RuntimeError("production manifest schema is incorrect")
    videos = manifest.get("videos")
    if not isinstance(videos, list) or len(videos) != 1:
        raise RuntimeError("production manifest must have one publication")
    video = videos[0]
    expected = {
        "id": PUBLICATION_ID,
        "title": TITLE,
        "duration": DURATION,
        "width": WIDTH,
        "height": HEIGHT,
    }
    for field, value in expected.items():
        if video.get(field) != value:
            raise RuntimeError(f"manifest {field} must equal {value!r}")
    if video.get("production") != {
        "master": SPEC.master_relative.as_posix()
    }:
        raise RuntimeError("manifest master does not match renderer")
    if video.get("thumb") != SPEC.thumbnail_relative.as_posix():
        raise RuntimeError("manifest thumbnail does not match renderer")
    if "sources" in video:
        raise RuntimeError("production manifest must not contain sources")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        choices=("artifacts", "render", "evidence", "delivery", "check", "model"),
        default="render",
    )
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "model":
            print(
                deterministic_json(
                    {
                        "stable": fixture_summary(RATE_STABLE_MILLI),
                        "collapse": fixture_summary(RATE_COLLAPSE_MILLI),
                    }
                ),
                end="",
            )
            return 0
        validate_manifest()
        if args.command == "artifacts":
            write_generated_artifacts()
        elif args.command == "render":
            write_generated_artifacts()
            render_master(resolve_binary("ffmpeg", args.ffmpeg))
        elif args.command == "evidence":
            write_generated_artifacts(check=True)
            document = evidence_document()
            validate_evidence(document)
            write_or_check(EVIDENCE_PATH, deterministic_json(document), False)
        elif args.command == "delivery":
            ffprobe = resolve_binary("ffprobe", args.ffprobe)
            document = delivery_document(ffprobe)
            write_or_check(DELIVERY_PATH, deterministic_json(document), False)
        else:
            ffprobe = resolve_binary("ffprobe", args.ffprobe)
            write_generated_artifacts(check=True)
            evidence = evidence_document()
            validate_evidence(evidence)
            write_or_check(EVIDENCE_PATH, deterministic_json(evidence), True)
            write_or_check(
                DELIVERY_PATH,
                deterministic_json(delivery_document(ffprobe)),
                True,
            )
            print(f"{ROOT}: generated artifacts and documents are current")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
