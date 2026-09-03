#!/usr/bin/env python3
"""Render the deterministic Archive Wetland Contrast master and delivery record."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "channel.production.json"
PUBLICATION_ID = "explore-archive-map-contrast"
EXPORT_DIGEST = "fe05f5f52ddd174f2756d865e6e1baea3c0aa5497e8052ce430d1c4c8c1761e6"
CHANGED_IDS = ("WL-002", "WL-005", "WL-009", "WL-012", "WL-016", "WL-020", "WL-023")
RECORDS = (
    ("WL-001", 1060, 2070),
    ("WL-002", 1160, 2055),
    ("WL-003", 1270, 2085),
    ("WL-004", 1390, 2060),
    ("WL-005", 1510, 2095),
    ("WL-006", 1580, 2050),
    ("WL-007", 1040, 2180),
    ("WL-008", 1150, 2160),
    ("WL-009", 1260, 2195),
    ("WL-010", 1380, 2170),
    ("WL-011", 1490, 2145),
    ("WL-012", 1590, 2190),
    ("WL-013", 1055, 2290),
    ("WL-014", 1175, 2260),
    ("WL-015", 1285, 2310),
    ("WL-016", 1400, 2280),
    ("WL-017", 1505, 2325),
    ("WL-018", 1585, 2270),
    ("WL-019", 1035, 2380),
    ("WL-020", 1160, 2360),
    ("WL-021", 1280, 2390),
    ("WL-022", 1390, 2350),
    ("WL-023", 1500, 2385),
    ("WL-024", 1595, 2340),
)
RGB = tuple[int, int, int]


@dataclass(frozen=True)
class RenderSpec:
    publication_id: str = PUBLICATION_ID
    title: str = "Read the Wetland Twice"
    width: int = 960
    height: int = 540
    fps: int = 12
    frame_count: int = 264

    @property
    def duration(self) -> float:
        return self.frame_count / self.fps

    @property
    def master_relative(self) -> Path:
        return Path("masters") / f"{self.publication_id}.mkv"

    @property
    def thumbnail_relative(self) -> Path:
        return Path("thumbs") / f"{self.publication_id}.svg"


SPEC = RenderSpec()


FONT = {
    " ": ("00000",) * 7,
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01110"),
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
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
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
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    ":": ("00000", "00110", "00110", "00000", "00110", "00110", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    ">": ("10000", "01000", "00100", "00010", "00100", "01000", "10000"),
    "<": ("00001", "00010", "00100", "01000", "00100", "00010", "00001"),
    "=": ("00000", "11111", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "#": ("01010", "11111", "01010", "01010", "11111", "01010", "00000"),
}


def _rgb(color: RGB) -> bytes:
    if len(color) != 3 or any(channel < 0 or channel > 255 for channel in color):
        raise ValueError(f"invalid RGB color: {color!r}")
    return bytes(color)


class Canvas:
    """Small deterministic RGB24 drawing surface."""

    def __init__(self, width: int, height: int, background: RGB):
        self.width = width
        self.height = height
        self.pixels = bytearray(_rgb(background) * (width * height))

    def rect(self, x: int, y: int, width: int, height: int, color: RGB) -> None:
        left = max(0, x)
        top = max(0, y)
        right = min(self.width, x + width)
        bottom = min(self.height, y + height)
        if left >= right or top >= bottom:
            return
        row = _rgb(color) * (right - left)
        stride = self.width * 3
        for row_index in range(top, bottom):
            start = row_index * stride + left * 3
            self.pixels[start : start + len(row)] = row

    def border(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: RGB,
        thickness: int = 2,
    ) -> None:
        self.rect(x, y, width, thickness, color)
        self.rect(x, y + height - thickness, width, thickness, color)
        self.rect(x, y, thickness, height, color)
        self.rect(x + width - thickness, y, thickness, height, color)

    def line(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        color: RGB,
        thickness: int = 1,
    ) -> None:
        x0, y0 = start
        x1, y1 = end
        delta_x = abs(x1 - x0)
        delta_y = -abs(y1 - y0)
        step_x = 1 if x0 < x1 else -1
        step_y = 1 if y0 < y1 else -1
        error = delta_x + delta_y
        radius = max(0, thickness // 2)
        while True:
            self.rect(x0 - radius, y0 - radius, max(1, thickness), max(1, thickness), color)
            if x0 == x1 and y0 == y1:
                break
            doubled = error * 2
            if doubled >= delta_y:
                error += delta_y
                x0 += step_x
            if doubled <= delta_x:
                error += delta_x
                y0 += step_y

    def circle(self, center_x: int, center_y: int, radius: int, color: RGB) -> None:
        radius_squared = radius * radius
        for offset_y in range(-radius, radius + 1):
            width = int((radius_squared - offset_y * offset_y) ** 0.5)
            self.rect(center_x - width, center_y + offset_y, width * 2 + 1, 1, color)

    def ring(
        self,
        center_x: int,
        center_y: int,
        radius: int,
        color: RGB,
        thickness: int = 2,
    ) -> None:
        self.circle(center_x, center_y, radius, color)
        inner = max(0, radius - thickness)
        self.circle(center_x, center_y, inner, PAPER)

    def text(self, x: int, y: int, value: str, color: RGB, scale: int = 1) -> None:
        cursor = x
        for character in value.upper():
            glyph = FONT.get(character, FONT[" "])
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
            cursor += 6 * scale

    def centered_text(
        self,
        center_x: int,
        y: int,
        value: str,
        color: RGB,
        scale: int = 1,
    ) -> None:
        width = max(0, len(value) * 6 * scale - scale)
        self.text(center_x - width // 2, y, value, color, scale)

    def bytes(self) -> bytes:
        return bytes(self.pixels)


PAPER = (243, 236, 216)
PAPER_DEEP = (226, 215, 184)
INK = (23, 60, 56)
INK_DARK = (15, 36, 34)
WATER = (143, 188, 192)
WATER_DARK = (45, 110, 114)
REED = (182, 170, 98)
MOSS = (99, 122, 83)
RUST = (166, 76, 50)
AMBER = (224, 170, 69)
CREAM = (255, 250, 240)
MUTED = (93, 99, 83)
FAIL_BG = (238, 207, 190)


def _paper(canvas: Canvas) -> None:
    for x in range(0, canvas.width, 24):
        canvas.rect(x, 0, 1, canvas.height, (226, 218, 195))
    for y in range(0, canvas.height, 24):
        canvas.rect(0, y, canvas.width, 1, (226, 218, 195))
    for y in range(11, canvas.height, 29):
        for x in range((y * 7) % 31, canvas.width, 43):
            canvas.rect(x, y, 2, 1, (210, 199, 169))


def _panel(canvas: Canvas, x: int, y: int, width: int, height: int) -> None:
    canvas.rect(x + 6, y + 7, width, height, (114, 107, 88))
    canvas.rect(x, y, width, height, PAPER)
    canvas.border(x, y, width, height, INK, 2)


def _header(canvas: Canvas, eyebrow: str, title: str, stamp: str) -> None:
    canvas.rect(0, 0, 960, 83, PAPER)
    canvas.rect(0, 0, 960, 5, RUST)
    canvas.text(32, 18, eyebrow, RUST, 1)
    canvas.text(32, 41, title, INK_DARK, 3)
    canvas.rect(724, 17, 204, 48, PAPER_DEEP)
    canvas.border(724, 17, 204, 48, RUST, 2)
    canvas.centered_text(826, 25, stamp, RUST, 2)


def _map_point(x: int, y: int, *, zoom: float = 1.0, pan_x: int = 0) -> tuple[int, int]:
    map_left, map_top = 48, 118
    map_width, map_height = 554, 336
    base_x = map_left + round((x - 1000) / 600 * map_width)
    base_y = map_top + map_height - round((y - 2000) / 400 * map_height)
    center_x = map_left + map_width // 2
    center_y = map_top + map_height // 2
    return (
        center_x + round((base_x - center_x) * zoom) + pan_x,
        center_y + round((base_y - center_y) * zoom),
    )


def _wetland_map(
    canvas: Canvas,
    *,
    changed: bool,
    filtered: bool = False,
    focus: str | None = None,
    zoom: float = 1.0,
    pan_x: int = 0,
) -> None:
    _panel(canvas, 30, 96, 604, 392)
    canvas.rect(46, 114, 560, 344, (239, 230, 206))
    canvas.border(46, 114, 560, 344, INK, 2)
    for x in range(90, 606, 52):
        canvas.rect(x, 114, 1, 344, (205, 197, 171))
    for y in range(154, 458, 52):
        canvas.rect(46, y, 560, 1, (205, 197, 171))

    upper = [
        (34, 180), (110, 144), (180, 192), (246, 164), (330, 127),
        (410, 159), (492, 210), (570, 170), (634, 143),
    ]
    for offset in range(-16, 17, 4):
        for first, second in zip(upper, upper[1:]):
            canvas.line(
                (first[0], first[1] + offset),
                (second[0], second[1] + offset),
                WATER if abs(offset) > 2 else WATER_DARK,
                3 if abs(offset) > 2 else 2,
            )
    lower = [(65, 402), (150, 346), (234, 386), (322, 339), (414, 352), (560, 408)]
    for offset in range(-8, 9, 4):
        for first, second in zip(lower, lower[1:]):
            canvas.line(
                (first[0], first[1] + offset),
                (second[0], second[1] + offset),
                WATER if offset else WATER_DARK,
                3 if offset else 2,
            )
    canvas.circle(170, 284, 52, REED)
    canvas.circle(170, 284, 38, PAPER_DEEP)
    canvas.circle(430, 294, 59, REED)
    canvas.circle(430, 294, 44, PAPER_DEEP)
    for index in range(12):
        x = 116 + index * 34
        canvas.line((x, 245 + index % 3 * 7), (x + 18, 223 + index % 2 * 8), MOSS, 2)

    visible = set(CHANGED_IDS) if filtered else {record[0] for record in RECORDS}
    for record_id, x, y in RECORDS:
        if record_id not in visible:
            continue
        point_x, point_y = _map_point(x, y, zoom=zoom, pan_x=pan_x)
        is_changed = record_id in CHANGED_IDS
        color = RUST if changed and is_changed else INK
        radius = 9 if record_id == focus else 6
        if record_id == focus:
            canvas.circle(point_x, point_y, 13, AMBER)
            canvas.circle(point_x, point_y, 10, CREAM)
        canvas.circle(point_x, point_y, radius, color)
        if filtered or record_id == focus:
            canvas.text(point_x + 8, point_y - 5, record_id[-3:], color, 1)

    canvas.text(53, 464, "SYN E 1000-1600 / N 2000-2400", MUTED, 1)
    canvas.text(562, 424, "N", INK, 2)
    canvas.line((568, 416), (568, 388), INK, 2)
    canvas.line((568, 388), (562, 398), INK, 2)
    canvas.line((568, 388), (574, 398), INK, 2)


def _side_metric(
    canvas: Canvas,
    y: int,
    label: str,
    value: str,
    color: RGB = INK_DARK,
) -> None:
    canvas.text(676, y, label, MUTED, 1)
    canvas.text(676, y + 18, value, color, 2)


def _render_opening(canvas: Canvas, seconds: float) -> None:
    _header(canvas, "SYNTHETIC FIELD ARCHIVE", "READ THE WETLAND TWICE", "24 PLOTS / 2 SHEETS")
    _wetland_map(canvas, changed=False)
    _panel(canvas, 654, 96, 276, 392)
    _side_metric(canvas, 120, "SNAPSHOTS", "1990 > 2020", WATER_DARK)
    _side_metric(canvas, 177, "TOTAL RECORDS", "24", INK_DARK)
    _side_metric(canvas, 234, "SYNTHETIC EXTENT", "600 X 400", MOSS)
    canvas.rect(674, 294, 236, 76, PAPER_DEEP)
    canvas.border(674, 294, 236, 76, INK, 2)
    canvas.text(688, 308, "EVERY STATION IS", MUTED, 1)
    canvas.text(688, 332, "ORIGINAL + SYNTHETIC", INK, 2)
    if seconds >= 2.0:
        canvas.rect(674, 392, 236, 58, INK)
        canvas.centered_text(792, 410, "COMPARE THE SHEETS", CREAM, 2)


def _render_compare(canvas: Canvas, seconds: float) -> None:
    _header(canvas, "1990 FIELD SHEET / 2020 FIELD SHEET", "SEVEN PLOTS CHANGED", "7 / 24")
    _wetland_map(canvas, changed=True)
    _panel(canvas, 654, 96, 276, 392)
    _side_metric(canvas, 120, "COMPARISON", "SUCCESS", MOSS)
    _side_metric(canvas, 177, "CHANGED", "7", RUST)
    canvas.text(676, 234, "SORTED IDS", MUTED, 1)
    reveal = min(len(CHANGED_IDS), max(1, int((seconds - 3.5) * 2.3) + 1))
    for index, record_id in enumerate(CHANGED_IDS[:reveal]):
        row_y = 256 + index * 25
        canvas.circle(684, row_y + 5, 5, RUST)
        canvas.text(697, row_y, record_id, INK_DARK, 1)
    canvas.rect(674, 446, 236, 24, RUST)
    canvas.centered_text(792, 452, "EXACTLY SEVEN", CREAM, 1)


def _render_inspect(canvas: Canvas) -> None:
    _header(canvas, "FILTER CHANGED / INSPECT WL-012", "MARSH LANTERN", "PAN 40 / ZOOM 1.25")
    _wetland_map(
        canvas,
        changed=True,
        filtered=True,
        focus="WL-012",
        zoom=1.12,
        pan_x=18,
    )
    _panel(canvas, 654, 96, 276, 392)
    _side_metric(canvas, 120, "VISIBLE / FILTER", "7 / CHANGED", RUST)
    _side_metric(canvas, 177, "FOCUS", "WL-012", WATER_DARK)
    canvas.rect(674, 235, 236, 112, (217, 231, 226))
    canvas.border(674, 235, 236, 112, WATER_DARK, 2)
    canvas.text(688, 250, "MARSH LANTERN", INK_DARK, 2)
    canvas.text(688, 280, "SEDGE-MEADOW", MUTED, 1)
    canvas.text(688, 301, "> REED-BED", RUST, 2)
    canvas.text(688, 329, "E 1590 / N 2190", WATER_DARK, 1)
    _side_metric(canvas, 374, "VIEW", "PAN 40 / ZOOM 1.25", MOSS)


def _render_export(canvas: Canvas) -> None:
    _header(canvas, "CANONICAL SORTED LIST", "EXPORT BOUND TO BYTES", "SHA-256")
    _panel(canvas, 52, 112, 856, 344)
    canvas.text(78, 140, "7 CHANGED IDS / UTF-8 / LF", MUTED, 2)
    for index, record_id in enumerate(CHANGED_IDS):
        x = 82 + (index % 4) * 198
        y = 188 + (index // 4) * 58
        canvas.rect(x, y, 168, 40, CREAM)
        canvas.border(x, y, 168, 40, RUST, 2)
        canvas.centered_text(x + 84, y + 12, record_id, RUST, 2)
    canvas.rect(78, 321, 804, 92, INK_DARK)
    canvas.text(96, 339, "FE05F5F52DDD174F2756D865E6E1BAEA", AMBER, 1)
    canvas.text(96, 367, "3C0AA5497E8052CE430D1C4C8C1761E6", AMBER, 1)
    canvas.text(96, 394, "SORTED EXPORT COMPLETE", CREAM, 1)
    canvas.text(52, 474, "THE FILE, APP, EVIDENCE, AND FILM NAME THE SAME SEVEN IDS", MUTED, 1)


def _render_failure(canvas: Canvas, seconds: float) -> None:
    _header(canvas, "SUPPLIED IMPOSSIBLE RANGE", "1880 > 1885", "QUERY REJECTED")
    _panel(canvas, 52, 112, 856, 344)
    canvas.rect(78, 145, 330, 90, PAPER_DEEP)
    canvas.border(78, 145, 330, 90, RUST, 3)
    canvas.text(100, 163, "FROM", MUTED, 1)
    canvas.text(100, 190, "1880", RUST, 4)
    canvas.rect(552, 145, 330, 90, PAPER_DEEP)
    canvas.border(552, 145, 330, 90, RUST, 3)
    canvas.text(574, 163, "TO", MUTED, 1)
    canvas.text(574, 190, "1885", RUST, 4)
    canvas.rect(78, 264, 804, 84, FAIL_BG)
    canvas.border(78, 264, 804, 84, RUST, 3)
    canvas.centered_text(480, 282, "EMPTY QUERY REJECTED", RUST, 3)
    canvas.centered_text(480, 319, "NOT A SUCCESSFUL ZERO", INK_DARK, 2)
    if seconds >= 16.0:
        canvas.rect(78, 371, 804, 52, INK)
        canvas.centered_text(480, 386, "CANONICAL 7-ID EXPORT PRESERVED", CREAM, 2)
    canvas.text(52, 474, "RESULT COUNT: NULL / FAILURE IS DISTINCT AND VISIBLE", RUST, 1)


def _render_reset(canvas: Canvas, seconds: float) -> None:
    _header(canvas, "RESTORE ARCHIVE VIEW", "EXACT RETURN", "CANONICAL")
    _wetland_map(canvas, changed=True)
    _panel(canvas, 654, 96, 276, 392)
    steps = (
        ("1990 > 2020", 18.0),
        ("ALL 24 VISIBLE", 18.7),
        ("7 CHANGES", 19.4),
        ("FOCUS NONE", 20.1),
        ("PAN 0 / ZOOM 1", 20.8),
    )
    for index, (label, threshold) in enumerate(steps):
        y = 122 + index * 61
        complete = seconds >= threshold
        canvas.circle(684, y + 8, 10, MOSS if complete else PAPER_DEEP)
        if complete:
            canvas.text(680, y + 3, "+", CREAM, 1)
        canvas.text(707, y, label, INK_DARK if complete else MUTED, 1)
    canvas.rect(674, 430, 236, 38, INK_DARK)
    canvas.centered_text(
        792,
        442,
        "DIGEST RESTORED" if seconds >= 21.0 else "RESTORING...",
        AMBER,
        1,
    )


def frame_rgb(frame_index: int, spec: RenderSpec = SPEC) -> bytes:
    if frame_index < 0 or frame_index >= spec.frame_count:
        raise ValueError(
            f"frame index {frame_index} outside 0..{spec.frame_count - 1}"
        )
    seconds = frame_index / spec.fps
    canvas = Canvas(spec.width, spec.height, PAPER)
    _paper(canvas)
    if seconds < 3.5:
        _render_opening(canvas, seconds)
    elif seconds < 7.0:
        _render_compare(canvas, seconds)
    elif seconds < 10.5:
        _render_inspect(canvas)
    elif seconds < 14.0:
        _render_export(canvas)
    elif seconds < 18.0:
        _render_failure(canvas, seconds)
    else:
        _render_reset(canvas, seconds)
    frame = canvas.bytes()
    expected_size = spec.width * spec.height * 3
    if len(frame) != expected_size:
        raise RuntimeError(f"frame has {len(frame)} bytes; expected {expected_size}")
    return frame


def frame_digest(frame_index: int, spec: RenderSpec = SPEC) -> str:
    return hashlib.sha256(frame_rgb(frame_index, spec)).hexdigest()


def iter_frames(spec: RenderSpec = SPEC) -> Iterator[bytes]:
    for frame_index in range(spec.frame_count):
        yield frame_rgb(frame_index, spec)


def thumbnail_svg(spec: RenderSpec = SPEC) -> str:
    title = escape(spec.title)
    markers = []
    for record_id, x, y in RECORDS:
        marker_x = 62 + round((x - 1000) / 600 * 548)
        marker_y = 132 + 320 - round((y - 2000) / 400 * 320)
        changed = record_id in CHANGED_IDS
        markers.append(
            f'    <circle cx="{marker_x}" cy="{marker_y}" r="{7 if changed else 5}" '
            f'fill="{"#a64c32" if changed else "#173c38"}"/>'
        )
    marker_source = "\n".join(markers)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" aria-labelledby="title desc">
  <title id="title">{title}</title>
  <desc id="desc">An original synthetic wetland field map with 24 stations and seven rust-colored changed plots.</desc>
  <rect width="960" height="540" fill="#f3ecd8"/>
  <path d="M0 24H960M0 48H960M0 72H960M0 96H960M0 120H960M0 144H960M0 168H960M0 192H960M0 216H960M0 240H960M0 264H960M0 288H960M0 312H960M0 336H960M0 360H960M0 384H960M0 408H960M0 432H960M0 456H960M0 480H960M0 504H960" stroke="#e2dac3"/>
  <rect width="960" height="84" fill="#f3ecd8"/>
  <rect width="960" height="5" fill="#a64c32"/>
  <text x="32" y="31" fill="#a64c32" font-family="monospace" font-size="13" font-weight="800">SYNTHETIC FIELD ARCHIVE · 1990 / 2020</text>
  <text x="32" y="68" fill="#0f2422" font-family="Georgia,serif" font-size="36" font-weight="800">READ THE WETLAND TWICE</text>
  <rect x="724" y="17" width="204" height="48" fill="#e2d7b8" stroke="#a64c32" stroke-width="2"/>
  <text x="826" y="47" text-anchor="middle" fill="#a64c32" font-family="monospace" font-size="18" font-weight="800">24 PLOTS / 7 CHANGED</text>
  <rect x="36" y="101" width="600" height="386" fill="#726b58"/>
  <rect x="30" y="94" width="600" height="386" fill="#f3ecd8" stroke="#173c38" stroke-width="2"/>
  <rect x="52" y="118" width="568" height="338" fill="#efe6ce" stroke="#173c38" stroke-width="2"/>
  <path d="M30 187 C120 130 177 214 259 176 S392 105 472 165 S568 228 640 176" fill="none" stroke="#8fbcc0" stroke-width="44" opacity=".82"/>
  <path d="M30 187 C120 130 177 214 259 176 S392 105 472 165 S568 228 640 176" fill="none" stroke="#2d6e72" stroke-width="3"/>
  <path d="M70 418 C154 350 219 428 306 376 S468 342 600 410" fill="none" stroke="#8fbcc0" stroke-width="25" opacity=".7"/>
  <ellipse cx="184" cy="292" rx="65" ry="46" fill="#b6aa62" opacity=".62" stroke="#637a53" stroke-width="2"/>
  <ellipse cx="432" cy="302" rx="72" ry="51" fill="#b6aa62" opacity=".58" stroke="#637a53" stroke-width="2"/>
  <g>
{marker_source}
  </g>
  <rect x="662" y="94" width="268" height="386" fill="#726b58"/>
  <rect x="656" y="87" width="268" height="386" fill="#f3ecd8" stroke="#173c38" stroke-width="2"/>
  <text x="678" y="122" fill="#5d6353" font-family="monospace" font-size="13">COMPARISON</text>
  <text x="678" y="154" fill="#637a53" font-family="monospace" font-size="25" font-weight="800">SUCCESS</text>
  <text x="678" y="198" fill="#5d6353" font-family="monospace" font-size="13">CHANGED IDS</text>
  <text x="678" y="231" fill="#a64c32" font-family="monospace" font-size="18" font-weight="800">WL-002 · WL-005</text>
  <text x="678" y="259" fill="#a64c32" font-family="monospace" font-size="18" font-weight="800">WL-009 · WL-012</text>
  <text x="678" y="287" fill="#a64c32" font-family="monospace" font-size="18" font-weight="800">WL-016 · WL-020</text>
  <text x="678" y="315" fill="#a64c32" font-family="monospace" font-size="18" font-weight="800">WL-023</text>
  <rect x="676" y="350" width="228" height="78" fill="#173c38"/>
  <text x="692" y="377" fill="#f3ecd8" font-family="monospace" font-size="13">SORTED EXPORT</text>
  <text x="692" y="405" fill="#e0aa45" font-family="monospace" font-size="17" font-weight="800">SHA-256 BOUND</text>
  <text x="678" y="451" fill="#2d6e72" font-family="monospace" font-size="12">SYN E 1000–1600 / N 2000–2400</text>
  <text x="480" y="519" text-anchor="middle" fill="#173c38" font-family="monospace" font-size="15" font-weight="800">FILTER · INSPECT · EXPORT · REJECT EMPTY · EXACT RESTORE</text>
</svg>
"""


def validate_manifest(path: Path = MANIFEST_PATH, spec: RenderSpec = SPEC) -> None:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read production manifest {path}: {exc}") from exc
    if manifest.get("schema") != "rapp-vision-production/1.0":
        raise RuntimeError("manifest schema must be rapp-vision-production/1.0")
    videos = manifest.get("videos")
    if not isinstance(videos, list) or len(videos) != 1:
        raise RuntimeError("manifest must contain exactly one publication")
    video = videos[0]
    expected = {
        "id": spec.publication_id,
        "title": spec.title,
        "duration": spec.duration,
        "width": spec.width,
        "height": spec.height,
    }
    for field, value in expected.items():
        if video.get(field) != value:
            raise RuntimeError(f"manifest {field} must equal {value!r}")
    if video.get("production") != {"master": spec.master_relative.as_posix()}:
        raise RuntimeError("manifest production master does not match renderer")
    if video.get("thumb") != spec.thumbnail_relative.as_posix():
        raise RuntimeError("manifest thumbnail does not match renderer")
    if "sources" in video:
        raise RuntimeError("production publication must not declare sources")
    live = video.get("live")
    if not isinstance(live, dict) or live.get("kind") != "rapp-vision-live/1.0":
        raise RuntimeError("manifest live replay is mandatory")


def ffmpeg_command(executable: str, target: Path, spec: RenderSpec = SPEC) -> list[str]:
    return [
        executable,
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
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-f",
        "matroska",
        str(target),
    ]


def _executable_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def _configured_tool_values(name: str) -> Iterator[str]:
    upper = name.upper()
    for variable in (
        f"RAPP_{upper}",
        f"RAPP_VISION_{upper}",
        upper,
        f"{upper}_PATH",
        f"{upper}_BIN",
    ):
        value = os.environ.get(variable)
        if value:
            yield value
    bin_directory = os.environ.get("FFMPEG_BIN")
    if bin_directory and name in {"ffmpeg", "ffprobe"}:
        yield str(Path(bin_directory) / _executable_name(name))


def _common_tool_candidates(name: str) -> Iterator[Path]:
    executable = _executable_name(name)
    for path in (
        Path("/usr/bin") / name,
        Path("/usr/local/bin") / name,
        Path("/opt/homebrew/bin") / name,
        Path("/opt/local/bin") / name,
    ):
        yield path
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            yield Path(root) / "ffmpeg" / "bin" / executable
            yield Path(root) / "FFmpeg" / "bin" / executable
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if packages.is_dir():
            for package in sorted(packages.glob("Gyan.FFmpeg.*")):
                yield from sorted(package.glob(f"ffmpeg-*/bin/{executable}"))


def _resolve_candidate(value: str) -> str | None:
    expanded = Path(os.path.expandvars(value)).expanduser()
    if expanded.is_absolute() or expanded.parent != Path("."):
        return str(expanded.resolve()) if expanded.is_file() else None
    resolved = shutil.which(value)
    return str(Path(resolved).resolve()) if resolved else None


def discover_executable(name: str, explicit: str | None = None) -> str:
    if explicit:
        resolved = _resolve_candidate(explicit)
        if not resolved:
            raise RuntimeError(f"{name} executable does not exist: {explicit}")
        return resolved
    for value in _configured_tool_values(name):
        resolved = _resolve_candidate(value)
        if resolved:
            return resolved
    resolved = shutil.which(name)
    if resolved:
        return str(Path(resolved).resolve())
    for candidate in _common_tool_candidates(name):
        if candidate.is_file():
            return str(candidate.resolve())
    raise RuntimeError(
        f"{name} executable not found via RAPP_{name.upper()}, environment, "
        "PATH, or common portable locations"
    )


def render(output_root: Path, ffmpeg: str, spec: RenderSpec = SPEC) -> tuple[Path, Path]:
    master = output_root / spec.master_relative
    thumbnail = output_root / spec.thumbnail_relative
    partial = master.with_name(f"{master.stem}.partial.mkv")
    expected_thumbnail = thumbnail_svg(spec)
    if master.exists() or partial.exists():
        raise RuntimeError(f"refusing to replace existing master or partial: {master}")
    if thumbnail.exists() and thumbnail.read_text(encoding="utf-8") != expected_thumbnail:
        raise RuntimeError(f"existing thumbnail differs from deterministic output: {thumbnail}")

    master.parent.mkdir(parents=True, exist_ok=True)
    thumbnail.parent.mkdir(parents=True, exist_ok=True)
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            ffmpeg_command(ffmpeg, partial, spec),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if process.stdin is None or process.stderr is None:
            raise RuntimeError("ffmpeg pipes were not created")
        try:
            for frame in iter_frames(spec):
                process.stdin.write(frame)
            process.stdin.close()
        except BrokenPipeError:
            process.stdin.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
        process.stderr.close()
        return_code = process.wait()
        if return_code:
            raise RuntimeError(f"ffmpeg failed: {stderr or return_code}")
        if not partial.is_file() or partial.stat().st_size <= 0:
            raise RuntimeError("ffmpeg produced no lossless master")
        partial.replace(master)
        if not thumbnail.exists():
            thumbnail.write_text(expected_thumbnail, encoding="utf-8", newline="\n")
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if partial.exists():
            partial.unlink()
    return master, thumbnail


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _probe(path: Path, ffprobe: str) -> dict[str, object]:
    completed = subprocess.run(
        [
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
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(
            f"ffprobe failed for {path}: {completed.stderr.strip() or completed.returncode}"
        )
    try:
        payload = json.loads(completed.stdout)
        stream = payload["streams"][0]
        duration = float(payload["format"]["duration"])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"ffprobe returned malformed metadata for {path}") from exc
    record: dict[str, object] = {
        "codec": stream.get("codec_name"),
        "pixelFormat": stream.get("pix_fmt"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "duration": round(duration, 6),
    }
    for source, target in (
        ("color_space", "colorSpace"),
        ("color_transfer", "colorTransfer"),
        ("color_primaries", "colorPrimaries"),
        ("color_range", "colorRange"),
    ):
        if stream.get(source) is not None:
            record[target] = stream[source]
    return record


def _artifact(
    path: Path,
    root: Path,
    probe: dict[str, object] | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }
    if probe:
        record.update(probe)
    return record


SOURCE_ARTIFACTS = (
    ".gitattributes",
    "README.md",
    "apps/explore-archive-map-contrast.html",
    "channel.production.json",
    "channel.json",
    "evidence.json",
    "exports/changed-record-ids.json",
    "render.py",
    "thumbs/explore-archive-map-contrast.svg",
    "verify_dom.mjs",
)


def delivery_document(
    output_root: Path,
    ffprobe: str,
    spec: RenderSpec = SPEC,
) -> dict[str, object]:
    master = output_root / spec.master_relative
    mp4 = output_root / "media" / f"{spec.publication_id}.mp4"
    webm = output_root / "media" / f"{spec.publication_id}.webm"
    required = [master, mp4, webm]
    required.extend(output_root / relative for relative in SOURCE_ARTIFACTS)
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"delivery artifact does not exist: {missing[0]}")
    sample_indexes = (0, 42, 90, 138, 186, spec.frame_count - 1)
    return {
        "schema": "archive-wetland-contrast-delivery/1.0",
        "channel": "candidate-frame-0003-09-archive-wetland-contrast",
        "publication": spec.publication_id,
        "artifacts": {
            "master": _artifact(master, output_root, _probe(master, ffprobe)),
            "mp4": _artifact(mp4, output_root, _probe(mp4, ffprobe)),
            "webm": _artifact(webm, output_root, _probe(webm, ffprobe)),
        },
        "sourceArtifacts": [
            _artifact(output_root / relative, output_root)
            for relative in SOURCE_ARTIFACTS
        ],
        "render": {
            "width": spec.width,
            "height": spec.height,
            "fps": spec.fps,
            "frames": spec.frame_count,
            "duration": spec.duration,
            "frameSamples": {
                str(index): frame_digest(index, spec)
                for index in sample_indexes
            },
            "masterCodec": "ffv1",
            "audio": False,
        },
        "objective": {
            "records": len(RECORDS),
            "changedIds": list(CHANGED_IDS),
            "exportSha256": EXPORT_DIGEST,
        },
    }


def write_delivery(output_root: Path, ffprobe: str) -> Path:
    target = output_root / "delivery.json"
    target.write_text(
        json.dumps(
            delivery_document(output_root, ffprobe),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    parser.add_argument("--output-root", type=Path, default=ROOT)
    parser.add_argument(
        "--show-tools",
        action="store_true",
        help="print portable ffmpeg and ffprobe discovery results",
    )
    parser.add_argument(
        "--delivery-only",
        action="store_true",
        help="write delivery.json from existing compiled artifacts",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print the deterministic render plan without writing",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.show_tools:
            print(
                json.dumps(
                    {
                        "ffmpeg": discover_executable("ffmpeg", args.ffmpeg),
                        "ffprobe": discover_executable("ffprobe", args.ffprobe),
                    },
                    sort_keys=True,
                )
            )
            return 0
        validate_manifest()
        output_root = args.output_root.resolve()
        if args.dry_run:
            ffmpeg = discover_executable("ffmpeg", args.ffmpeg)
            print(
                json.dumps(
                    {
                        "schema": "archive-wetland-render-plan/1.0",
                        "publication": SPEC.publication_id,
                        "width": SPEC.width,
                        "height": SPEC.height,
                        "fps": SPEC.fps,
                        "frames": SPEC.frame_count,
                        "duration": SPEC.duration,
                        "master": str(output_root / SPEC.master_relative),
                        "thumbnail": str(output_root / SPEC.thumbnail_relative),
                        "command": ffmpeg_command(
                            ffmpeg,
                            output_root / SPEC.master_relative,
                        ),
                    },
                    indent=2,
                )
            )
            return 0
        if args.delivery_only:
            ffprobe = discover_executable("ffprobe", args.ffprobe)
            print(write_delivery(output_root, ffprobe))
        else:
            ffmpeg = discover_executable("ffmpeg", args.ffmpeg)
            master, thumbnail = render(output_root, ffmpeg)
            print(master)
            print(thumbnail)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
