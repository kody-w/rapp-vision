#!/usr/bin/env python3
"""Render deterministic Tiny Systems FFV1 masters and SVG thumbnails."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "tiny-systems"
MANIFEST_PATH = SOURCE_ROOT / "channel.production.json"
PRODUCTION_SCHEMA = "rapp-vision-production/1.0"
RGB = tuple[int, int, int]


@dataclass(frozen=True)
class RenderSpec:
    publication_id: str
    title: str
    width: int
    height: int
    fps: int
    frame_count: int
    style: str

    @property
    def duration(self) -> float:
        return self.frame_count / self.fps

    @property
    def master_relative(self) -> Path:
        return Path("masters") / f"{self.publication_id}.mkv"

    @property
    def thumbnail_relative(self) -> Path:
        return Path("thumbs") / f"{self.publication_id}.svg"


@dataclass(frozen=True)
class RenderJob:
    spec: RenderSpec
    master_path: Path
    thumbnail_path: Path


SPECS = (
    RenderSpec(
        publication_id="one-block-three-trains",
        title="One Block, Three Trains",
        width=960,
        height=540,
        fps=12,
        frame_count=120,
        style="signal-blueprint",
    ),
    RenderSpec(
        publication_id="four-and-a-half-to-one",
        title="Four-and-a-Half to One",
        width=720,
        height=720,
        fps=12,
        frame_count=108,
        style="contrast-grid",
    ),
    RenderSpec(
        publication_id="three-tokens-make-nine",
        title="Three Tokens Make Nine",
        width=540,
        height=960,
        fps=12,
        frame_count=144,
        style="token-poster",
    ),
)
SPEC_BY_ID = {spec.publication_id: spec for spec in SPECS}


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
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "=": ("00000", "11111", "00000", "11111", "00000", "00000", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    ",": ("00000", "00000", "00000", "00000", "00110", "00100", "01000"),
}


def _rgb(value: RGB) -> bytes:
    if len(value) != 3 or any(channel < 0 or channel > 255 for channel in value):
        raise ValueError(f"invalid RGB color: {value!r}")
    return bytes(value)


class Canvas:
    """Small RGB24 raster surface with deterministic integer drawing."""

    def __init__(self, width: int, height: int, background: RGB):
        if width <= 0 or height <= 0:
            raise ValueError("canvas dimensions must be positive")
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
            self.rect(x0 - radius, y0 - radius, max(1, thickness), max(1, thickness), color)
            if x0 == x1 and y0 == y1:
                break
            doubled = 2 * error
            if doubled >= dy:
                error += dy
                x0 += step_x
            if doubled <= dx:
                error += dx
                y0 += step_y

    def circle(self, center_x: int, center_y: int, radius: int, color: RGB) -> None:
        if radius <= 0:
            return
        squared = radius * radius
        for offset_y in range(-radius, radius + 1):
            span = int((squared - offset_y * offset_y) ** 0.5)
            self.rect(
                center_x - span,
                center_y + offset_y,
                span * 2 + 1,
                1,
                color,
            )

    def text(
        self,
        x: int,
        y: int,
        value: str,
        color: RGB,
        scale: int = 1,
    ) -> None:
        if scale <= 0:
            raise ValueError("text scale must be positive")
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


def _lerp(start: int, end: int, progress: float) -> int:
    bounded = min(1.0, max(0.0, progress))
    eased = bounded * bounded * (3.0 - 2.0 * bounded)
    return round(start + (end - start) * eased)


def _frame_progress(spec: RenderSpec, frame_index: int) -> float:
    if frame_index < 0 or frame_index >= spec.frame_count:
        raise ValueError(
            f"frame index {frame_index} outside 0..{spec.frame_count - 1} "
            f"for {spec.publication_id}"
        )
    return frame_index / max(1, spec.frame_count - 1)


def _draw_train(canvas: Canvas, x: int, y: int, label: str, color: RGB) -> None:
    canvas.rect(x, y, 118, 54, color)
    canvas.rect(x + 86, y - 18, 32, 18, color)
    canvas.rect(x + 8, y + 11, 45, 5, (7, 19, 31))
    canvas.circle(x + 25, y + 58, 11, (7, 19, 31))
    canvas.circle(x + 91, y + 58, 11, (7, 19, 31))
    canvas.centered_text(x + 59, y + 19, label, (7, 19, 31), 3)


def _render_trains(spec: RenderSpec, frame_index: int) -> bytes:
    progress = _frame_progress(spec, frame_index)
    canvas = Canvas(spec.width, spec.height, (7, 19, 31))
    grid = (16, 43, 62)
    for x in range(0, spec.width, 48):
        canvas.rect(x, 0, 1, spec.height, grid)
    for y in range(0, spec.height, 48):
        canvas.rect(0, y, spec.width, 1, grid)

    canvas.text(48, 42, "ONE BLOCK", (147, 201, 232), 4)
    canvas.text(48, 82, "THREE TRAINS", (244, 248, 251), 3)
    canvas.rect(48, 126, 864, 2, (49, 81, 106))

    rail_y = 309
    for x in range(0, spec.width, 38):
        canvas.rect(x, rail_y - 18, 9, 74, (58, 81, 96))
    canvas.rect(0, rail_y, spec.width, 6, (158, 177, 189))
    canvas.rect(0, rail_y + 34, spec.width, 6, (158, 177, 189))

    block_left = 330
    block_right = 690
    canvas.rect(block_left, 190, block_right - block_left, 4, (83, 199, 232))
    canvas.rect(block_left, 190, 4, 202, (83, 199, 232))
    canvas.rect(block_right - 4, 190, 4, 202, (83, 199, 232))
    canvas.rect(block_left, 388, block_right - block_left, 4, (83, 199, 232))
    canvas.centered_text(510, 207, "BLOCK 1", (157, 230, 251), 2)

    reset = progress >= 0.87
    rejected = 0.28 <= progress < 0.50
    continuation = 0.50 <= progress < 0.87
    if reset:
        positions = {"A": 150, "B": 14, "C": -122}
        signal = (85, 223, 160)
        status = "RESET / CLEAR"
        status_color = (85, 223, 160)
    elif progress < 0.28:
        train_progress = progress / 0.28
        positions = {
            "A": _lerp(150, 451, train_progress),
            "B": 14,
            "C": -122,
        }
        signal = (255, 107, 107) if train_progress > 0.55 else (85, 223, 160)
        status = "ACCEPT TRAIN A"
        status_color = (255, 209, 102)
    elif rejected:
        positions = {"A": 451, "B": 196, "C": 60}
        signal = (255, 107, 107)
        status = "REJECT B / A STAYS"
        status_color = (255, 107, 107)
    elif continuation:
        phase = (progress - 0.50) / 0.37
        positions = {
            "A": _lerp(451, 930, min(1.0, phase * 1.55)),
            "B": _lerp(196, 451, max(0.0, (phase - 0.28) / 0.72)),
            "C": 60,
        }
        signal = (255, 107, 107) if phase > 0.42 else (85, 223, 160)
        status = "CONTINUE SAFELY"
        status_color = (123, 223, 242)
    else:
        positions = {"A": 451, "B": 196, "C": 60}
        signal = (255, 107, 107)
        status = "BLOCK OCCUPIED"
        status_color = (255, 209, 102)

    canvas.circle(block_left - 28, 247, 19, (19, 40, 57))
    canvas.circle(block_left - 28, 247, 12, signal)
    _draw_train(canvas, positions["C"], 276, "C", (178, 247, 168))
    _draw_train(canvas, positions["B"], 276, "B", (123, 223, 242))
    _draw_train(canvas, positions["A"], 276, "A", (255, 209, 102))

    canvas.rect(48, 438, 864, 62, (11, 31, 46))
    canvas.text(72, 458, status, status_color, 3)
    return canvas.bytes()


def _render_contrast(spec: RenderSpec, frame_index: int) -> bytes:
    progress = _frame_progress(spec, frame_index)
    canvas = Canvas(spec.width, spec.height, (243, 239, 228))
    canvas.rect(0, 0, 12, spec.height, (22, 22, 22))
    canvas.text(48, 48, "FOUR-AND-A-HALF", (22, 22, 22), 3)
    canvas.text(48, 84, "TO ONE", (22, 22, 22), 5)

    if progress < 0.34:
        ratio = "#767676 / 4.54:1"
        label = "SOURCE PAIR / PASS"
        foreground = (118, 118, 118)
        decision = (31, 122, 77)
    elif progress < 0.78:
        ratio = "#777777 / 4.48:1"
        label = "SOURCE PAIR / REJECT"
        foreground = (119, 119, 119)
        decision = (156, 32, 39)
    else:
        ratio = "21.00:1"
        label = "RESET / OPENING PAIR"
        foreground = (0, 0, 0)
        decision = (29, 78, 137)

    canvas.rect(48, 150, 624, 292, (22, 22, 22))
    canvas.rect(54, 156, 612, 280, (255, 255, 255))
    canvas.text(84, 206, "NORMAL TEXT", foreground, 5)
    canvas.text(84, 266, "CROSSES THE", foreground, 4)
    canvas.text(84, 316, "4.50 THRESHOLD", foreground, 4)
    canvas.rect(84, 382, 430, 4, foreground)

    canvas.rect(48, 474, 624, 92, decision)
    canvas.text(74, 498, label, (255, 255, 255), 3)

    canvas.rect(48, 606, 624, 5, (22, 22, 22))
    marker = 360
    canvas.rect(48, 594, marker - 48, 29, (214, 64, 69))
    canvas.rect(marker, 594, 312, 29, (31, 122, 77))
    canvas.rect(marker - 3, 584, 6, 49, (22, 22, 22))
    canvas.text(48, 648, ratio, decision, 5)
    return canvas.bytes()


def _draw_token(
    canvas: Canvas,
    center_x: int,
    center_y: int,
    radius: int,
    value: int,
    color: RGB,
    selected: bool,
) -> None:
    canvas.circle(center_x, center_y + 7, radius, (39, 34, 27))
    canvas.circle(center_x, center_y, radius, color)
    if selected:
        canvas.circle(center_x, center_y, radius - 9, (255, 250, 240))
        canvas.circle(center_x, center_y, radius - 15, color)
    canvas.centered_text(center_x, center_y - 17, str(value), (39, 34, 27), 5)


def _render_tokens(spec: RenderSpec, frame_index: int) -> bytes:
    progress = _frame_progress(spec, frame_index)
    canvas = Canvas(spec.width, spec.height, (248, 237, 207))
    canvas.rect(0, 760, spec.width, 200, (242, 217, 153))
    canvas.centered_text(270, 50, "THREE TOKENS", (39, 34, 27), 4)
    canvas.centered_text(270, 100, "MAKE NINE", (39, 34, 27), 5)
    canvas.rect(55, 166, 430, 3, (109, 72, 34))

    if progress < 0.22:
        selected_count = min(3, int(progress / 0.22 * 4))
        draft = [2, 3, 4][:selected_count]
        accepted: list[int] = []
        status = "CHOOSE 2 + 3 + 4"
        status_color = (109, 72, 34)
    elif progress < 0.46:
        draft = [2, 3, 4]
        accepted = [2, 3, 4]
        status = "ACCEPT / TOTAL 9"
        status_color = (31, 122, 77)
    elif progress < 0.80:
        draft = [1, 3, 4]
        accepted = [2, 3, 4]
        status = "REJECT 8 / KEEP 9"
        status_color = (165, 40, 50)
    else:
        draft = []
        accepted = []
        status = "RESET / EMPTY TRAYS"
        status_color = (29, 78, 137)

    colors = {
        1: (255, 143, 112),
        2: (255, 209, 102),
        3: (123, 223, 242),
        4: (178, 247, 168),
    }
    for index, value in enumerate((1, 2, 3, 4)):
        _draw_token(
            canvas,
            90 + index * 120,
            252,
            48,
            value,
            colors[value],
            value in draft,
        )

    canvas.rect(55, 334, 430, 178, (255, 250, 240))
    canvas.rect(55, 334, 430, 4, (39, 34, 27))
    canvas.rect(55, 508, 430, 4, (39, 34, 27))
    canvas.text(80, 362, "CANDIDATE", (109, 72, 34), 2)
    draft_text = " + ".join(str(value) for value in draft) if draft else "EMPTY"
    total = sum(draft)
    canvas.centered_text(270, 420, f"{draft_text} = {total}", (39, 34, 27), 4)

    canvas.rect(55, 550, 430, 178, (255, 250, 240))
    canvas.rect(55, 550, 430, 4, (39, 34, 27))
    canvas.rect(55, 724, 430, 4, (39, 34, 27))
    canvas.text(80, 578, "ACCEPTED", (109, 72, 34), 2)
    accepted_text = " + ".join(str(value) for value in accepted) if accepted else "NONE"
    accepted_total = sum(accepted)
    canvas.centered_text(
        270,
        636,
        f"{accepted_text} = {accepted_total}",
        (39, 34, 27),
        4,
    )

    canvas.rect(55, 790, 430, 102, status_color)
    canvas.centered_text(270, 830, status, (255, 255, 255), 2)
    return canvas.bytes()


def frame_rgb(spec: RenderSpec, frame_index: int) -> bytes:
    """Return one deterministic RGB24 frame for a render spec."""
    if spec.style == "signal-blueprint":
        frame = _render_trains(spec, frame_index)
    elif spec.style == "contrast-grid":
        frame = _render_contrast(spec, frame_index)
    elif spec.style == "token-poster":
        frame = _render_tokens(spec, frame_index)
    else:
        raise ValueError(f"unknown render style: {spec.style}")
    expected_size = spec.width * spec.height * 3
    if len(frame) != expected_size:
        raise RuntimeError(
            f"{spec.publication_id} frame has {len(frame)} bytes; expected {expected_size}"
        )
    return frame


def frame_digest(publication_id: str, frame_index: int) -> str:
    """Return a stable SHA-256 sample for contract tests."""
    try:
        spec = SPEC_BY_ID[publication_id]
    except KeyError as exc:
        raise ValueError(f"unknown publication id: {publication_id}") from exc
    return hashlib.sha256(frame_rgb(spec, frame_index)).hexdigest()


def iter_frames(spec: RenderSpec) -> Iterator[bytes]:
    for frame_index in range(spec.frame_count):
        yield frame_rgb(spec, frame_index)


def thumbnail_svg(spec: RenderSpec) -> str:
    """Build a safe, self-contained SVG thumbnail for one publication."""
    title = escape(spec.title)
    if spec.style == "signal-blueprint":
        body = """
  <rect width="960" height="540" fill="#07131f"/>
  <g stroke="#102b3e" stroke-width="1"><path d="M0 48H960M0 96H960M0 144H960M0 192H960M0 240H960M0 288H960M0 336H960M0 384H960M0 432H960M0 480H960"/><path d="M48 0V540M96 0V540M144 0V540M192 0V540M240 0V540M288 0V540M336 0V540M384 0V540M432 0V540M480 0V540M528 0V540M576 0V540M624 0V540M672 0V540M720 0V540M768 0V540M816 0V540M864 0V540M912 0V540"/></g>
  <rect x="330" y="174" width="360" height="224" rx="18" fill="#0b2638" stroke="#53c7e8" stroke-width="4" stroke-dasharray="12 10"/>
  <path d="M0 309H960M0 345H960" stroke="#9eb1bd" stroke-width="7"/>
  <circle cx="300" cy="244" r="15" fill="#ff6b6b"/>
  <g fill="#ffd166" stroke="#07131f" stroke-width="5"><path d="M430 276h118v54H430z"/><path d="M516 258h32v18h-32z"/><circle cx="455" cy="338" r="12"/><circle cx="521" cy="338" r="12"/></g>
  <text x="58" y="74" fill="#93c9e8" font-family="monospace" font-size="30" font-weight="700" letter-spacing="4">ONE BLOCK</text>
  <text x="58" y="126" fill="#f4f8fb" font-family="monospace" font-size="42" font-weight="800">THREE TRAINS</text>
  <text x="489" y="312" text-anchor="middle" fill="#07131f" font-family="monospace" font-size="30" font-weight="900">A</text>
  <rect x="58" y="440" width="844" height="58" rx="8" fill="#0b1f2e"/>
  <text x="82" y="478" fill="#ff6b6b" font-family="monospace" font-size="25" font-weight="800">REJECT B / A STAYS</text>"""
    elif spec.style == "contrast-grid":
        body = """
  <rect width="720" height="720" fill="#f3efe4"/>
  <rect width="12" height="720" fill="#161616"/>
  <text x="48" y="72" fill="#161616" font-family="sans-serif" font-size="28" font-weight="800" letter-spacing="3">FOUR-AND-A-HALF</text>
  <text x="48" y="132" fill="#161616" font-family="sans-serif" font-size="58" font-weight="900">TO ONE</text>
  <rect x="48" y="168" width="624" height="294" fill="#161616"/>
  <rect x="55" y="175" width="610" height="280" fill="#fff"/>
  <text x="86" y="263" fill="#767676" font-family="sans-serif" font-size="38">NORMAL TEXT</text>
  <text x="86" y="326" fill="#767676" font-family="sans-serif" font-size="38">#767676 = 4.54:1</text>
  <rect x="48" y="492" width="624" height="94" fill="#1f7a4d"/>
  <text x="76" y="550" fill="#fff" font-family="sans-serif" font-size="29" font-weight="800">4.54 PASS / 4.48 REJECT</text>
  <path d="M48 633H672" stroke="#161616" stroke-width="5"/>
  <rect x="48" y="620" width="312" height="28" fill="#d64045"/>
  <rect x="360" y="620" width="312" height="28" fill="#1f7a4d"/>
  <path d="M360 607V661" stroke="#161616" stroke-width="6"/>"""
    elif spec.style == "token-poster":
        body = """
  <rect width="540" height="960" fill="#f8edcf"/>
  <path d="M0 760H540V960H0z" fill="#f2d999"/>
  <text x="270" y="75" text-anchor="middle" fill="#27221b" font-family="sans-serif" font-size="37" font-weight="800" letter-spacing="2">THREE TOKENS</text>
  <text x="270" y="132" text-anchor="middle" fill="#27221b" font-family="sans-serif" font-size="54" font-weight="900">MAKE NINE</text>
  <path d="M55 166H485" stroke="#6d4822" stroke-width="4"/>
  <g stroke="#27221b" stroke-width="5" font-family="sans-serif" font-size="43" font-weight="900" text-anchor="middle" fill="#27221b"><circle cx="90" cy="258" r="48" fill="#ff8f70"/><circle cx="210" cy="258" r="48" fill="#ffd166"/><circle cx="330" cy="258" r="48" fill="#7bdff2"/><circle cx="450" cy="258" r="48" fill="#b2f7a8"/><text x="90" y="273" stroke="none">1</text><text x="210" y="273" stroke="none">2</text><text x="330" y="273" stroke="none">3</text><text x="450" y="273" stroke="none">4</text></g>
  <rect x="55" y="354" width="430" height="176" rx="22" fill="#fffaf0" stroke="#27221b" stroke-width="5"/>
  <text x="270" y="433" text-anchor="middle" fill="#27221b" font-family="monospace" font-size="38" font-weight="900">2 + 3 + 4</text>
  <text x="270" y="489" text-anchor="middle" fill="#1f7a4d" font-family="sans-serif" font-size="31" font-weight="900">ACCEPT = 9</text>
  <rect x="55" y="585" width="430" height="112" rx="18" fill="#a52832"/>
  <text x="270" y="653" text-anchor="middle" fill="#fff" font-family="sans-serif" font-size="27" font-weight="800">REJECT 8 / KEEP 9</text>"""
    else:
        raise ValueError(f"unknown render style: {spec.style}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '
        f'{spec.width} {spec.height}" role="img" aria-labelledby="title desc">\n'
        f'  <title id="title">{title}</title>\n'
        f'  <desc id="desc">Deterministic synthetic thumbnail for {title}.</desc>'
        f"{body}\n</svg>\n"
    )


def build_render_plan(
    output_root: Path | str = SOURCE_ROOT,
    only: Iterable[str] | None = None,
) -> tuple[RenderJob, ...]:
    root = Path(output_root)
    if only is None:
        selected = [spec.publication_id for spec in SPECS]
    else:
        selected = list(only)
        if not selected:
            raise ValueError("at least one publication id is required")
        if len(selected) != len(set(selected)):
            raise ValueError("--only publication ids must not repeat")
        unknown = [publication_id for publication_id in selected if publication_id not in SPEC_BY_ID]
        if unknown:
            raise ValueError(f"unknown publication id: {unknown[0]}")
    selected_set = set(selected)
    return tuple(
        RenderJob(
            spec=spec,
            master_path=root / spec.master_relative,
            thumbnail_path=root / spec.thumbnail_relative,
        )
        for spec in SPECS
        if spec.publication_id in selected_set
    )


def ffmpeg_command(ffmpeg: str, spec: RenderSpec, target: Path) -> list[str]:
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
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-f",
        "matroska",
        str(target),
    ]


def validate_manifest(path: Path = MANIFEST_PATH) -> None:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read production manifest {path}: {exc}") from exc
    if manifest.get("schema") != PRODUCTION_SCHEMA:
        raise RuntimeError(f"manifest schema must be {PRODUCTION_SCHEMA}")
    if manifest.get("id") != "tiny-systems":
        raise RuntimeError("manifest id must be tiny-systems")
    videos = manifest.get("videos")
    if not isinstance(videos, list):
        raise RuntimeError("manifest videos must be an array")
    ids = [video.get("id") for video in videos if isinstance(video, dict)]
    expected_ids = [spec.publication_id for spec in SPECS]
    if ids != expected_ids:
        raise RuntimeError(f"manifest publication order must be {expected_ids!r}")
    for spec, video in zip(SPECS, videos):
        if "sources" in video:
            raise RuntimeError(f"{spec.publication_id} must not declare delivery sources")
        if video.get("production") != {"master": spec.master_relative.as_posix()}:
            raise RuntimeError(
                f"{spec.publication_id} production.master must be "
                f"{spec.master_relative.as_posix()}"
            )
        for field, expected in (
            ("title", spec.title),
            ("duration", spec.duration),
            ("width", spec.width),
            ("height", spec.height),
        ):
            if video.get(field) != expected:
                raise RuntimeError(
                    f"{spec.publication_id}.{field} must equal {expected!r}"
                )
        live = video.get("live")
        if not isinstance(live, dict) or live.get("kind") != "rapp-vision-live/1.0":
            raise RuntimeError(f"{spec.publication_id}.live is mandatory")
        if not isinstance(live.get("scenes"), list) or not live["scenes"]:
            raise RuntimeError(f"{spec.publication_id}.live.scenes must be non-empty")


def _resolve_ffmpeg(value: str) -> str:
    candidate = Path(value)
    has_parent = candidate.is_absolute() or candidate.parent != Path(".")
    if has_parent:
        if not candidate.is_file():
            raise RuntimeError(f"ffmpeg executable does not exist: {candidate}")
        return str(candidate.resolve())
    resolved = shutil.which(value)
    if not resolved:
        raise RuntimeError(f"ffmpeg executable not found: {value}")
    return resolved


def _preflight(jobs: Sequence[RenderJob]) -> None:
    for job in jobs:
        partial = job.master_path.with_name(f"{job.master_path.stem}.partial.mkv")
        if job.master_path.exists():
            raise RuntimeError(f"refusing to replace existing master: {job.master_path}")
        if partial.exists():
            raise RuntimeError(f"partial output already exists: {partial}")
        expected_svg = thumbnail_svg(job.spec)
        if job.thumbnail_path.exists():
            try:
                actual_svg = job.thumbnail_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise RuntimeError(f"cannot read thumbnail {job.thumbnail_path}: {exc}") from exc
            if actual_svg != expected_svg:
                raise RuntimeError(
                    f"existing thumbnail differs from deterministic output: {job.thumbnail_path}"
                )


def _render_master(ffmpeg: str, job: RenderJob) -> None:
    partial = job.master_path.with_name(f"{job.master_path.stem}.partial.mkv")
    command = ffmpeg_command(ffmpeg, job.spec, partial)
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if process.stdin is None or process.stderr is None:
            raise RuntimeError("ffmpeg pipes were not created")
        try:
            for frame in iter_frames(job.spec):
                process.stdin.write(frame)
            process.stdin.close()
        except BrokenPipeError:
            process.stdin.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
        return_code = process.wait()
        if return_code:
            raise RuntimeError(
                f"ffmpeg failed for {job.spec.publication_id}: "
                f"{stderr or f'exit code {return_code}'}"
            )
        if not partial.is_file() or partial.stat().st_size <= 0:
            raise RuntimeError(
                f"ffmpeg produced no master for {job.spec.publication_id}"
            )
        partial.replace(job.master_path)
    except OSError as exc:
        raise RuntimeError(
            f"could not render {job.spec.publication_id}: {exc}"
        ) from exc
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if partial.exists():
            partial.unlink()


def _write_thumbnail(job: RenderJob) -> None:
    content = thumbnail_svg(job.spec)
    if job.thumbnail_path.exists():
        return
    partial = job.thumbnail_path.with_name(f"{job.thumbnail_path.name}.partial")
    if partial.exists():
        raise RuntimeError(f"partial thumbnail already exists: {partial}")
    try:
        partial.write_text(content, encoding="utf-8", newline="\n")
        partial.replace(job.thumbnail_path)
    except OSError as exc:
        if partial.exists():
            partial.unlink()
        raise RuntimeError(f"could not write thumbnail {job.thumbnail_path}: {exc}") from exc


def render_jobs(ffmpeg: str, jobs: Sequence[RenderJob]) -> None:
    _preflight(jobs)
    for job in jobs:
        job.master_path.parent.mkdir(parents=True, exist_ok=True)
        job.thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        _render_master(ffmpeg, job)
        _write_thumbnail(job)


def _parse_only(values: Sequence[str] | None) -> list[str] | None:
    if values is None:
        return None
    selected: list[str] = []
    for value in values:
        parts = value.split(",")
        if any(not part.strip() for part in parts):
            raise ValueError("--only requires non-empty publication ids")
        selected.extend(part.strip() for part in parts)
    return selected


def _dry_run_document(ffmpeg: str, jobs: Sequence[RenderJob]) -> dict[str, object]:
    return {
        "schema": "tiny-systems-render-plan/1.0",
        "ffmpeg": ffmpeg,
        "jobs": [
            {
                "id": job.spec.publication_id,
                "style": job.spec.style,
                "width": job.spec.width,
                "height": job.spec.height,
                "fps": job.spec.fps,
                "frames": job.spec.frame_count,
                "duration": job.spec.duration,
                "master": str(job.master_path),
                "thumbnail": str(job.thumbnail_path),
                "command": ffmpeg_command(ffmpeg, job.spec, job.master_path),
            }
            for job in jobs
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="FFmpeg executable name or path (default: ffmpeg)",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="ID[,ID...]",
        help="render only named publication ids; may be repeated",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=SOURCE_ROOT,
        help="output root containing masters/ and thumbs/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print the deterministic plan without writing or invoking FFmpeg",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_manifest()
        selected = _parse_only(args.only)
        jobs = build_render_plan(args.output_root, selected)
        if args.dry_run:
            print(json.dumps(_dry_run_document(args.ffmpeg, jobs), indent=2))
            return 0
        ffmpeg = _resolve_ffmpeg(args.ffmpeg)
        render_jobs(ffmpeg, jobs)
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
