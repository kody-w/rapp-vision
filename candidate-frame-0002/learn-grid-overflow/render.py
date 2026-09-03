#!/usr/bin/env python3
"""Render the deterministic Learn Grid Overflow FFV1 master and SVG thumb."""

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
PUBLICATION_ID = "learn-grid-overflow"
PRODUCTION_SCHEMA = "rapp-vision-production/1.0"
RGB = tuple[int, int, int]


@dataclass(frozen=True)
class RenderSpec:
    publication_id: str = PUBLICATION_ID
    title: str = "Why the Grid Overflows"
    width: int = 960
    height: int = 540
    fps: int = 12
    frame_count: int = 216

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
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "=": ("00000", "11111", "00000", "11111", "00000", "00000", "00000"),
    ">": ("10000", "01000", "00100", "00010", "00100", "01000", "10000"),
    "<": ("00001", "00010", "00100", "01000", "00100", "00010", "00001"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    ",": ("00000", "00000", "00000", "00000", "00110", "00100", "01000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
}


def _rgb(value: RGB) -> bytes:
    if len(value) != 3 or any(channel < 0 or channel > 255 for channel in value):
        raise ValueError(f"invalid RGB color: {value!r}")
    return bytes(value)


class Canvas:
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


INK = (12, 21, 34)
PAPER = (245, 247, 244)
PANEL = (255, 255, 255)
MUTED = (91, 107, 119)
GRID = (211, 220, 221)
RED = (211, 58, 61)
RED_DARK = (126, 30, 36)
GREEN = (27, 132, 91)
GREEN_DARK = (12, 83, 61)
BLUE = (45, 104, 196)
AMBER = (245, 184, 66)


def _panel(canvas: Canvas, x: int, y: int, width: int, height: int) -> None:
    canvas.rect(x + 8, y + 8, width, height, (196, 204, 204))
    canvas.rect(x, y, width, height, PANEL)
    canvas.rect(x, y, width, 3, INK)
    canvas.rect(x, y + height - 3, width, 3, INK)
    canvas.rect(x, y, 3, height, INK)
    canvas.rect(x + width - 3, y, 3, height, INK)


def _header(canvas: Canvas, step: str, title: str, color: RGB) -> None:
    canvas.rect(0, 0, 960, 86, INK)
    canvas.text(42, 24, step, color, 2)
    canvas.text(42, 49, title, PAPER, 3)
    canvas.rect(42, 78, 876, 3, color)


def _draw_broken_viewport(canvas: Canvas, scroll_x: int = 0) -> None:
    left = 92
    top = 150
    client = 430
    overflow = 236
    canvas.rect(left, top, client, 205, (238, 242, 242))
    canvas.rect(left + client, top, overflow, 205, (255, 226, 225))
    canvas.rect(left, top, client, 4, INK)
    canvas.rect(left, top + 201, client, 4, INK)
    canvas.rect(left, top, 4, 205, INK)
    canvas.rect(left + client - 4, top, 4, 205, INK)
    canvas.rect(left + client, top, overflow, 4, RED)
    canvas.rect(left + client, top + 201, overflow, 4, RED)
    canvas.rect(left + client + overflow - 4, top, 4, 205, RED)

    offset = round(scroll_x / 292 * 180) if scroll_x else 0
    grid_left = left + 18 - offset
    canvas.rect(grid_left, top + 32, 118, 118, BLUE)
    canvas.text(grid_left + 25, top + 79, "META", PAPER, 2)
    canvas.rect(grid_left + 130, top + 32, 480, 118, (252, 210, 103))
    canvas.text(grid_left + 150, top + 59, "UNBREAKABLE", INK, 2)
    canvas.text(grid_left + 150, top + 88, "BUILD HASH TOKEN", INK, 2)
    canvas.text(grid_left + 150, top + 117, "CONTENT RAIL 480", RED_DARK, 2)

    canvas.rect(left, top + 176, client, 18, (203, 211, 213))
    thumb_x = left + 4 + round(scroll_x / 292 * 217)
    canvas.rect(thumb_x, top + 178, 205, 14, RED)
    canvas.text(left, top + 216, f"PREVIEW X {scroll_x}", RED_DARK, 2)


def _render_measure(canvas: Canvas, time_seconds: float) -> None:
    _header(canvas, "STEP 1 / MEASURE", "THE AUTO MINIMUM ESCAPES", RED)
    _draw_broken_viewport(canvas)
    _panel(canvas, 592, 124, 292, 258)
    canvas.text(620, 151, "VIEWPORT", MUTED, 2)
    canvas.text(620, 181, "320 PX", INK, 5)
    canvas.text(620, 241, "SCROLLWIDTH", MUTED, 2)
    canvas.text(620, 269, "612", RED_DARK, 5)
    canvas.text(620, 329, "612 > 320", RED, 3)
    if time_seconds > 1.2:
        canvas.rect(92, 422, 792, 68, RED_DARK)
        canvas.text(122, 445, "AUTO MIN KEPT THE 480 PX CONTENT", PAPER, 3)


def _render_fix(canvas: Canvas, time_seconds: float) -> None:
    _header(canvas, "STEP 2 / FIX", "ZERO THE ITEM MINIMUM", GREEN)
    _panel(canvas, 68, 122, 824, 310)
    canvas.text(102, 153, "BROKEN", RED_DARK, 2)
    canvas.text(102, 187, "PAYLOAD  MIN-WIDTH AUTO", INK, 3)
    canvas.line((428, 213), (550, 213), RED, 5)
    canvas.text(102, 250, "FIXED", GREEN_DARK, 2)
    canvas.text(102, 284, "PAYLOAD  MIN-WIDTH 0", GREEN_DARK, 4)
    canvas.text(102, 341, "92PX  1FR  /  RAIL 480 UNCHANGED", BLUE, 3)
    canvas.rect(68, 455, 824, 56, GREEN)
    label = "SCROLLWIDTH 320 = CLIENTWIDTH 320"
    if time_seconds < 5.0:
        label = "CHANGE ONE DECLARATION"
    canvas.centered_text(480, 475, label, PAPER, 3)


def _check_card(
    canvas: Canvas,
    x: int,
    width_label: str,
    measurement: str,
    accent: RGB,
) -> None:
    _panel(canvas, x, 157, 360, 250)
    canvas.rect(x, 157, 360, 15, accent)
    canvas.text(x + 31, 198, width_label, MUTED, 3)
    canvas.centered_text(x + 180, 258, measurement, accent, 5)
    canvas.centered_text(x + 180, 334, "NO OVERFLOW", GREEN_DARK, 3)


def _render_verify(canvas: Canvas) -> None:
    _header(canvas, "STEP 3 / VERIFY", "BOTH TARGET WIDTHS FIT", GREEN)
    _check_card(canvas, 92, "VIEWPORT 320", "320 = 320", BLUE)
    _check_card(canvas, 508, "VIEWPORT 1280", "1280 = 1280", GREEN)
    canvas.rect(92, 446, 776, 54, INK)
    canvas.centered_text(480, 464, "SAME FIX / TWO EXACT MEASUREMENTS", PAPER, 3)


def _render_restore(canvas: Canvas, time_seconds: float) -> None:
    _header(canvas, "STEP 4 / UNDO", "RESTORE BROKEN CSS", RED)
    phase = min(1.0, max(0.0, (time_seconds - 11.0) / 2.5))
    scroll_x = round(292 * phase)
    _draw_broken_viewport(canvas, scroll_x)
    _panel(canvas, 592, 124, 292, 258)
    canvas.text(620, 151, "RESTORED", RED_DARK, 2)
    canvas.text(620, 186, "1FR", INK, 5)
    canvas.text(620, 244, "MIN WIDTH", MUTED, 2)
    canvas.text(620, 272, "AUTO", RED_DARK, 4)
    canvas.text(620, 329, "X", MUTED, 2)
    canvas.text(656, 319, str(scroll_x), RED, 4)
    canvas.rect(92, 438, 792, 62, RED_DARK)
    canvas.centered_text(488, 459, "FAILURE IS VISIBLE AND SCROLLABLE", PAPER, 3)


def _render_reset(canvas: Canvas, time_seconds: float) -> None:
    _header(canvas, "STEP 5 / RESET", "RETURN TO THE OPENING SNAPSHOT", AMBER)
    _panel(canvas, 108, 126, 744, 315)
    rows = (
        ("1", "RESTORE BROKEN CSS"),
        ("2", "SET VIEWPORT 320 PX"),
        ("3", "SCROLL PREVIEW TO X 0"),
    )
    completed = min(3, max(0, int((time_seconds - 14.1) / 1.0) + 1))
    for index, (number, label) in enumerate(rows):
        y = 161 + index * 83
        active = index < completed
        color = GREEN if active else (193, 199, 198)
        canvas.rect(142, y, 52, 52, color)
        canvas.centered_text(168, y + 15, number, PAPER if active else INK, 3)
        canvas.text(225, y + 14, label, INK, 3)
        if active:
            canvas.text(753, y + 16, "OK", GREEN_DARK, 2)
    if time_seconds >= 17.0:
        canvas.rect(108, 466, 744, 48, INK)
        canvas.centered_text(480, 481, "612 > 320 / X 0 / EXACT RESET", AMBER, 3)
    else:
        canvas.text(108, 477, "RESET IS THREE OBSERVABLE ACTIONS", MUTED, 3)


def frame_rgb(spec: RenderSpec, frame_index: int) -> bytes:
    if frame_index < 0 or frame_index >= spec.frame_count:
        raise ValueError(
            f"frame index {frame_index} outside 0..{spec.frame_count - 1}"
        )
    time_seconds = frame_index / spec.fps
    canvas = Canvas(spec.width, spec.height, PAPER)
    for x in range(0, spec.width, 48):
        canvas.rect(x, 0, 1, spec.height, GRID)
    for y in range(0, spec.height, 48):
        canvas.rect(0, y, spec.width, 1, GRID)

    if time_seconds < 4.0:
        _render_measure(canvas, time_seconds)
    elif time_seconds < 8.0:
        _render_fix(canvas, time_seconds)
    elif time_seconds < 11.0:
        _render_verify(canvas)
    elif time_seconds < 14.0:
        _render_restore(canvas, time_seconds)
    else:
        _render_reset(canvas, time_seconds)

    frame = canvas.bytes()
    expected = spec.width * spec.height * 3
    if len(frame) != expected:
        raise RuntimeError(f"frame has {len(frame)} bytes; expected {expected}")
    return frame


def frame_digest(frame_index: int) -> str:
    return hashlib.sha256(frame_rgb(SPEC, frame_index)).hexdigest()


def iter_frames(spec: RenderSpec = SPEC) -> Iterator[bytes]:
    for frame_index in range(spec.frame_count):
        yield frame_rgb(spec, frame_index)


def thumbnail_svg(spec: RenderSpec = SPEC) -> str:
    title = escape(spec.title)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '
        f'{spec.width} {spec.height}" role="img" aria-labelledby="title desc">\n'
        f'  <title id="title">{title}</title>\n'
        f'  <desc id="desc">A 480 pixel intrinsic rail sets a grid item automatic minimum; changing only min-width to zero restores equality.</desc>\n'
        '  <rect width="960" height="540" fill="#f5f7f4"/>\n'
        '  <path d="M0 48H960M0 96H960M0 144H960M0 192H960M0 240H960M0 288H960M0 336H960M0 384H960M0 432H960M0 480H960" stroke="#d3dcdd"/>\n'
        '  <rect width="960" height="88" fill="#0c1522"/>\n'
        '  <text x="42" y="35" fill="#f5b842" font-family="monospace" font-size="18" font-weight="700">CSS GRID / MEASURE, FIX, VERIFY</text>\n'
        '  <text x="42" y="70" fill="#f5f7f4" font-family="sans-serif" font-size="33" font-weight="900">WHY THE GRID OVERFLOWS</text>\n'
        '  <rect x="72" y="139" width="430" height="212" fill="#eef2f2" stroke="#0c1522" stroke-width="4"/>\n'
        '  <rect x="502" y="139" width="240" height="212" fill="#ffe2e1" stroke="#d33a3d" stroke-width="4"/>\n'
        '  <rect x="94" y="178" width="118" height="118" fill="#2d68c4"/>\n'
        '  <rect x="224" y="178" width="480" height="118" fill="#fcd267"/>\n'
        '  <text x="115" y="246" fill="#fff" font-family="monospace" font-size="22" font-weight="800">META</text>\n'
        '  <text x="250" y="224" fill="#0c1522" font-family="monospace" font-size="21" font-weight="800">480PX INTRINSIC RAIL</text>\n'
        '  <text x="250" y="264" fill="#7e1e24" font-family="monospace" font-size="19" font-weight="800">ITEM MIN-WIDTH: AUTO</text>\n'
        '  <rect x="72" y="389" width="816" height="92" fill="#fff" stroke="#0c1522" stroke-width="4"/>\n'
        '  <text x="104" y="430" fill="#d33a3d" font-family="monospace" font-size="28" font-weight="900">612 &gt; 320</text>\n'
        '  <text x="330" y="430" fill="#0c1522" font-family="monospace" font-size="22">→ MIN-WIDTH: 0 ONLY →</text>\n'
        '  <text x="704" y="430" fill="#1b845b" font-family="monospace" font-size="28" font-weight="900">320 = 320</text>\n'
        '  <text x="104" y="463" fill="#5b6b77" font-family="sans-serif" font-size="18">Exact scrollWidth and clientWidth stay visible.</text>\n'
        '</svg>\n'
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
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-f",
        "matroska",
        str(target),
    ]


def validate_manifest(path: Path = MANIFEST_PATH, spec: RenderSpec = SPEC) -> None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read production manifest {path}: {exc}") from exc
    if document.get("schema") != PRODUCTION_SCHEMA:
        raise RuntimeError(f"manifest schema must be {PRODUCTION_SCHEMA}")
    videos = document.get("videos")
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
        raise RuntimeError("manifest production.master does not match renderer output")
    if video.get("thumb") != spec.thumbnail_relative.as_posix():
        raise RuntimeError("manifest thumb does not match renderer output")
    if "sources" in video:
        raise RuntimeError("production manifest must not define delivery sources")


def _resolve_executable(value: str) -> str | None:
    expanded = Path(os.path.expandvars(value)).expanduser()
    if expanded.is_absolute() or expanded.parent != Path("."):
        return str(expanded.resolve()) if expanded.is_file() else None
    return shutil.which(value)


def _ffmpeg_common_paths() -> list[Path]:
    candidates = [
        Path("/usr/bin/ffmpeg"),
        Path("/usr/local/bin/ffmpeg"),
        Path("/opt/homebrew/bin/ffmpeg"),
        Path("/opt/local/bin/ffmpeg"),
    ]
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            candidates.extend(
                [
                    Path(root) / "ffmpeg" / "bin" / "ffmpeg.exe",
                    Path(root) / "FFmpeg" / "bin" / "ffmpeg.exe",
                ]
            )
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        packages = (
            Path(local_app_data)
            / "Microsoft"
            / "WinGet"
            / "Packages"
        )
        if packages.is_dir():
            for package in sorted(packages.glob("Gyan.FFmpeg.*")):
                candidates.extend(sorted(package.glob("ffmpeg-*/bin/ffmpeg.exe")))
    return candidates


def _resolve_ffmpeg(value: str | None) -> str:
    requested = [
        value,
        os.environ.get("FRAME_FFMPEG"),
        os.environ.get("FFMPEG"),
        "ffmpeg",
    ]
    for candidate in requested:
        if candidate:
            resolved = _resolve_executable(candidate)
            if resolved:
                return resolved
    for candidate in _ffmpeg_common_paths():
        if candidate.is_file():
            return str(candidate.resolve())
    raise RuntimeError(
        "ffmpeg executable not found via --ffmpeg, FRAME_FFMPEG, FFMPEG, "
        "PATH, or common install locations"
    )


def render_master(ffmpeg: str, target: Path, spec: RenderSpec = SPEC) -> None:
    if target.exists():
        raise RuntimeError(f"refusing to replace existing master: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f"{target.stem}.partial.mkv")
    if partial.exists():
        raise RuntimeError(f"partial output already exists: {partial}")
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
        return_code = process.wait()
        if return_code:
            raise RuntimeError(f"ffmpeg failed: {stderr or return_code}")
        if not partial.is_file() or partial.stat().st_size <= 0:
            raise RuntimeError("ffmpeg produced no FFV1 master")
        partial.replace(target)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if partial.exists():
            partial.unlink()


def write_thumbnail(path: Path, spec: RenderSpec = SPEC) -> None:
    content = thumbnail_svg(spec)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"existing thumbnail differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.partial")
    partial.write_text(content, encoding="utf-8", newline="\n")
    partial.replace(path)


def render(output_root: Path, ffmpeg: str, spec: RenderSpec = SPEC) -> None:
    render_master(ffmpeg, output_root / spec.master_relative, spec)
    write_thumbnail(output_root / spec.thumbnail_relative, spec)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg")
    parser.add_argument("--output-root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        validate_manifest()
        target = args.output_root / SPEC.master_relative
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "schema": "candidate-frame-render-plan/1.0",
                        "id": SPEC.publication_id,
                        "width": SPEC.width,
                        "height": SPEC.height,
                        "fps": SPEC.fps,
                        "frames": SPEC.frame_count,
                        "duration": SPEC.duration,
                        "master": str(target),
                        "thumbnail": str(args.output_root / SPEC.thumbnail_relative),
                        "command": ffmpeg_command(args.ffmpeg or "ffmpeg", target),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        render(args.output_root, _resolve_ffmpeg(args.ffmpeg))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
