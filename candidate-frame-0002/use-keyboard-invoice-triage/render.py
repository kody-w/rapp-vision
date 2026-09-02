#!/usr/bin/env python3
"""Render the deterministic Keyboard Invoice Triage master and delivery record."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "channel.production.json"
PUBLICATION_ID = "use-keyboard-invoice-triage"
RGB = tuple[int, int, int]


@dataclass(frozen=True)
class RenderSpec:
    publication_id: str = PUBLICATION_ID
    title: str = "Triage Invoices Without a Pointer"
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
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "$": ("00100", "01111", "10100", "01110", "00101", "11110", "00100"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
}


def _rgb(color: RGB) -> bytes:
    if len(color) != 3 or any(channel < 0 or channel > 255 for channel in color):
        raise ValueError(f"invalid RGB color: {color!r}")
    return bytes(color)


class Canvas:
    """Minimal deterministic RGB24 drawing surface."""

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

    def text(
        self,
        x: int,
        y: int,
        value: str,
        color: RGB,
        scale: int = 1,
    ) -> None:
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


BG = (7, 19, 29)
PANEL = (9, 29, 41)
ROW = (14, 41, 55)
GRID = (40, 73, 88)
TEXT = (244, 247, 248)
MUTED = (152, 184, 197)
CYAN = (125, 249, 255)
YELLOW = (255, 209, 102)
GREEN = (77, 211, 151)
RED = (255, 107, 107)
ORANGE = (255, 189, 107)


def _stage(seconds: float) -> str:
    if seconds < 2.9:
        return "accept"
    if seconds < 5.3:
        return "correct"
    if seconds < 8.4:
        return "export"
    if seconds < 13.2:
        return "reject"
    if seconds < 15.2:
        return "confirm"
    return "reset"


def _draw_focus(
    canvas: Canvas,
    x: int,
    y: int,
    width: int,
    height: int,
    label_x: int,
    label_y: int,
) -> None:
    canvas.border(x - 5, y - 5, width + 10, height + 10, CYAN, 4)
    canvas.rect(label_x, label_y, 84, 21, CYAN)
    canvas.text(label_x + 8, label_y + 5, "FOCUS", BG, 2)


def _draw_invoice(
    canvas: Canvas,
    y: int,
    invoice_id: str,
    vendor: str,
    amount: str,
    category: str,
    accepted: bool,
    focused: bool,
) -> None:
    background = (13, 48, 41) if accepted else ROW
    border = GREEN if accepted else GRID
    canvas.rect(38, y, 650, 70, background)
    canvas.border(38, y, 650, 70, border, 2)
    canvas.text(54, y + 12, invoice_id, TEXT, 2)
    canvas.text(54, y + 39, vendor, MUTED, 1)
    canvas.text(350, y + 12, f"${amount}", YELLOW, 2)
    canvas.text(
        350,
        y + 40,
        category,
        ORANGE if category == "UNCODED" else TEXT,
        1,
    )
    canvas.text(
        556,
        y + 25,
        "ACCEPTED" if accepted else "PENDING",
        GREEN if accepted else MUTED,
        1,
    )
    if focused:
        _draw_focus(canvas, 38, y, 650, 70, 594, y - 15)


def frame_rgb(frame_index: int, spec: RenderSpec = SPEC) -> bytes:
    if frame_index < 0 or frame_index >= spec.frame_count:
        raise ValueError(
            f"frame index {frame_index} outside 0..{spec.frame_count - 1}"
        )
    seconds = frame_index / spec.fps
    stage = _stage(seconds)
    canvas = Canvas(spec.width, spec.height, BG)

    canvas.rect(0, 0, spec.width, 7, CYAN)
    canvas.text(38, 28, "INVOICE TRIAGE", TEXT, 4)
    canvas.text(40, 66, "KEYBOARD ONLY / SYNTHETIC DATA", MUTED, 1)
    canvas.rect(710, 22, 212, 65, PANEL)
    canvas.border(710, 22, 212, 65, GRID, 2)
    canvas.text(727, 34, "FIXTURE TOTAL", MUTED, 1)
    canvas.text(727, 54, "$196.25", YELLOW, 3)

    accepted = [False, False, False]
    focus_row = 0
    category = "UNCODED"
    if stage == "accept":
        accepted[0] = seconds >= 0.8
        accepted[1] = seconds >= 1.7
        focus_row = 0 if seconds < 1.0 else 1 if seconds < 2.0 else 2
    elif stage == "correct":
        accepted = [True, True, seconds >= 4.3]
        focus_row = 2
        category = "FACILITIES" if seconds >= 3.5 else "UNCODED"
    elif stage in {"export", "reject", "confirm"}:
        accepted = [True, True, True]
        focus_row = -1
        category = "FACILITIES"
    else:
        focus_row = 0

    _draw_invoice(
        canvas,
        112,
        "SYN-001",
        "PAPER KITE SUPPLIES",
        "64.75",
        "OFFICE",
        accepted[0],
        focus_row == 0,
    )
    _draw_invoice(
        canvas,
        194,
        "SYN-002",
        "METRO MOTH TRANSIT",
        "82.50",
        "TRANSIT",
        accepted[1],
        focus_row == 1,
    )
    _draw_invoice(
        canvas,
        276,
        "SYN-003",
        "COPPER COMET REPAIRS",
        "49.00",
        category,
        accepted[2],
        focus_row == 2,
    )

    canvas.rect(710, 112, 212, 292, PANEL)
    canvas.border(710, 112, 212, 292, GRID, 2)
    canvas.text(728, 130, "ACCEPTED QUEUE", MUTED, 1)
    count = sum(accepted)
    canvas.text(728, 155, f"{count} / 3", TEXT, 3)
    canvas.text(728, 194, "ACCEPTED TOTAL", MUTED, 1)
    totals = ("0.00", "64.75", "147.25", "196.25")
    canvas.text(728, 218, f"${totals[count]}", GREEN if count == 3 else YELLOW, 2)

    if stage == "accept":
        canvas.text(728, 265, "ENTER ACCEPTS", CYAN, 1)
        canvas.text(728, 284, "ARROWS MOVE", CYAN, 1)
        canvas.text(728, 318, "VISIBLE FOCUS", TEXT, 1)
    elif stage == "correct":
        canvas.rect(723, 262, 186, 76, (48, 36, 23))
        canvas.border(723, 262, 186, 76, ORANGE, 2)
        canvas.text(735, 276, "CATEGORY", MUTED, 1)
        canvas.text(735, 298, category, ORANGE, 2)
        _draw_focus(canvas, 723, 262, 186, 76, 823, 250)
    elif stage == "export":
        canvas.rect(723, 260, 186, 111, (13, 48, 41))
        canvas.border(723, 260, 186, 111, GREEN, 3)
        canvas.text(735, 275, "EXPORT COMPLETE", GREEN, 1)
        canvas.text(735, 302, "ACCEPTEDTOTAL", TEXT, 1)
        canvas.text(735, 326, "196.25", GREEN, 3)
        _draw_focus(canvas, 723, 260, 186, 111, 823, 248)
    elif stage == "reject":
        canvas.rect(723, 258, 186, 56, (53, 25, 30))
        canvas.border(723, 258, 186, 56, RED, 3)
        canvas.text(735, 270, "AMOUNT", MUTED, 1)
        canvas.text(735, 289, "-1.00", RED, 2)
        _draw_focus(canvas, 723, 258, 186, 56, 823, 246)
        canvas.text(728, 331, "NEGATIVE REJECTED", RED, 1)
        canvas.rect(727, 354, 178, 31, (53, 56, 59))
        canvas.text(743, 365, "EXPORT DISABLED", MUTED, 1)
    elif stage == "confirm":
        canvas.rect(723, 251, 186, 125, (48, 36, 23))
        canvas.border(723, 251, 186, 125, ORANGE, 3)
        canvas.text(735, 266, "RESTORE FIXTURE?", ORANGE, 1)
        canvas.text(735, 295, "REPLACE EDITS", TEXT, 1)
        canvas.text(735, 326, "ENTER CONFIRMS", CYAN, 1)
        _draw_focus(canvas, 723, 251, 186, 125, 823, 239)
    else:
        canvas.text(728, 267, "EXACT RESTORE", GREEN, 1)
        canvas.text(728, 292, "3 PENDING", TEXT, 2)
        canvas.text(728, 323, "NO ERROR", TEXT, 1)
        canvas.text(728, 346, "FOCUS SYN-001", CYAN, 1)

    canvas.rect(38, 429, 884, 70, (8, 26, 37))
    canvas.border(38, 429, 884, 70, GRID, 2)
    if stage == "accept":
        status = "TAB / ARROWS / ENTER FOLLOW THE VISIBLE FOCUS PATH"
        status_color = CYAN
    elif stage == "correct":
        status = "CORRECT SYN-003: UNCODED TO FACILITIES"
        status_color = ORANGE
    elif stage == "export":
        status = "EXPORTED ACCEPTEDTOTAL IS EXACTLY 196.25"
        status_color = GREEN
    elif stage == "reject":
        status = "AMOUNT MUST BE ZERO OR GREATER / EXPORT DISABLED"
        status_color = RED
    elif stage == "confirm":
        status = "CONFIRM REPLACEMENT OF LOCAL EDITS"
        status_color = ORANGE
    else:
        status = "RESTORED: 3 PENDING / TOTAL 196.25 / FOCUS FIRST ROW"
        status_color = GREEN
    canvas.centered_text(480, 452, status, status_color, 2)

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
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" aria-labelledby="title desc">
  <title id="title">{title}</title>
  <desc id="desc">Original synthetic invoice queue with visible keyboard focus, total 196.25, and export proof.</desc>
  <rect width="960" height="540" fill="#07131d"/>
  <rect width="960" height="7" fill="#7df9ff"/>
  <text x="38" y="65" fill="#f4f7f8" font-family="monospace" font-size="42" font-weight="800">INVOICE TRIAGE</text>
  <text x="40" y="91" fill="#98b8c5" font-family="monospace" font-size="15">KEYBOARD ONLY · SYNTHETIC DATA</text>
  <rect x="710" y="22" width="212" height="70" rx="10" fill="#091d29" stroke="#284958" stroke-width="2"/>
  <text x="727" y="46" fill="#98b8c5" font-family="monospace" font-size="13">FIXTURE TOTAL</text>
  <text x="727" y="76" fill="#ffd166" font-family="monospace" font-size="28" font-weight="800">$196.25</text>
  <g font-family="monospace">
    <rect x="38" y="128" width="650" height="72" rx="10" fill="#0d3029" stroke="#4dd397" stroke-width="2"/>
    <text x="55" y="157" fill="#f4f7f8" font-size="20" font-weight="800">SYN-001</text>
    <text x="55" y="181" fill="#98b8c5" font-size="13">PAPER KITE SUPPLIES</text>
    <text x="350" y="166" fill="#ffd166" font-size="23" font-weight="800">$64.75</text>
    <text x="565" y="166" fill="#4dd397" font-size="14" font-weight="800">ACCEPTED</text>
    <rect x="38" y="216" width="650" height="72" rx="10" fill="#0d3029" stroke="#4dd397" stroke-width="2"/>
    <text x="55" y="245" fill="#f4f7f8" font-size="20" font-weight="800">SYN-002</text>
    <text x="55" y="269" fill="#98b8c5" font-size="13">METRO MOTH TRANSIT</text>
    <text x="350" y="254" fill="#ffd166" font-size="23" font-weight="800">$82.50</text>
    <text x="565" y="254" fill="#4dd397" font-size="14" font-weight="800">ACCEPTED</text>
    <rect x="38" y="304" width="650" height="72" rx="10" fill="#0d3029" stroke="#4dd397" stroke-width="2"/>
    <rect x="32" y="298" width="662" height="84" rx="13" fill="none" stroke="#7df9ff" stroke-width="5"/>
    <text x="55" y="333" fill="#f4f7f8" font-size="20" font-weight="800">SYN-003</text>
    <text x="55" y="357" fill="#98b8c5" font-size="13">COPPER COMET REPAIRS</text>
    <text x="350" y="342" fill="#ffd166" font-size="23" font-weight="800">$49.00</text>
    <text x="565" y="342" fill="#4dd397" font-size="14" font-weight="800">ACCEPTED</text>
  </g>
  <rect x="710" y="128" width="212" height="248" rx="12" fill="#091d29" stroke="#284958" stroke-width="2"/>
  <text x="728" y="155" fill="#98b8c5" font-family="monospace" font-size="13">EXPORT COMPLETE</text>
  <text x="728" y="198" fill="#f4f7f8" font-family="monospace" font-size="15">acceptedTotal</text>
  <text x="728" y="240" fill="#4dd397" font-family="monospace" font-size="32" font-weight="800">196.25</text>
  <rect x="728" y="278" width="176" height="57" rx="8" fill="#35191e" stroke="#ff6b6b" stroke-width="3"/>
  <text x="743" y="302" fill="#98b8c5" font-family="monospace" font-size="12">NEGATIVE REJECTED</text>
  <text x="743" y="324" fill="#ff6b6b" font-family="monospace" font-size="18" font-weight="800">-1.00</text>
  <rect x="38" y="426" width="884" height="72" rx="10" fill="#081a25" stroke="#284958" stroke-width="2"/>
  <text x="480" y="469" text-anchor="middle" fill="#7df9ff" font-family="monospace" font-size="20" font-weight="800">VISIBLE FOCUS · SAFE REJECTION · EXACT RESET</text>
</svg>
"""


def validate_manifest(path: Path = MANIFEST_PATH, spec: RenderSpec = SPEC) -> None:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read production manifest {path}: {exc}") from exc
    if manifest.get("schema") != "rapp-vision-production/1.0":
        raise RuntimeError("manifest schema must be rapp-vision-production/1.0")
    if manifest.get("id") != PUBLICATION_ID:
        raise RuntimeError(f"manifest id must be {PUBLICATION_ID}")
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


def _resolve_executable(value: str, name: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute() or candidate.parent != Path("."):
        if not candidate.is_file():
            raise RuntimeError(f"{name} executable does not exist: {candidate}")
        return str(candidate.resolve())
    resolved = shutil.which(value)
    if not resolved:
        raise RuntimeError(f"{name} executable not found: {value}")
    return resolved


def render(output_root: Path, ffmpeg: str, spec: RenderSpec = SPEC) -> tuple[Path, Path]:
    master = output_root / spec.master_relative
    thumbnail = output_root / spec.thumbnail_relative
    partial = master.with_name(f"{master.stem}.partial.mkv")
    expected_svg = thumbnail_svg(spec)
    if master.exists() or partial.exists():
        raise RuntimeError(f"refusing to replace existing master or partial: {master}")
    if thumbnail.exists() and thumbnail.read_text(encoding="utf-8") != expected_svg:
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
        return_code = process.wait()
        if return_code:
            raise RuntimeError(f"ffmpeg failed: {stderr or return_code}")
        if not partial.is_file() or partial.stat().st_size <= 0:
            raise RuntimeError("ffmpeg produced no lossless master")
        partial.replace(master)
        if not thumbnail.exists():
            thumbnail.write_text(expected_svg, encoding="utf-8", newline="\n")
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if partial.exists():
            partial.unlink()
    return master, thumbnail


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _probe(path: Path, ffprobe: str) -> dict[str, object]:
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
    try:
        payload = json.loads(completed.stdout)
        stream = payload["streams"][0]
        duration = float(payload["format"]["duration"])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"ffprobe returned malformed metadata for {path}") from exc
    record = {
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


def _artifact(path: Path, root: Path, probe: dict[str, object] | None = None) -> dict[str, object]:
    record: dict[str, object] = {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }
    if probe:
        record.update(probe)
    return record


def delivery_document(
    output_root: Path,
    ffprobe: str,
    spec: RenderSpec = SPEC,
) -> dict[str, object]:
    master = output_root / spec.master_relative
    mp4 = output_root / "media" / f"{spec.publication_id}.mp4"
    webm = output_root / "media" / f"{spec.publication_id}.webm"
    thumbnail = output_root / spec.thumbnail_relative
    required = [master, mp4, webm, thumbnail]
    required.extend(
        output_root / name
        for name in (
            ".gitattributes",
            "README.md",
            "channel.production.json",
            "channel.json",
            "evidence.json",
            "render.py",
            "verify_dom.mjs",
            "apps/use-keyboard-invoice-triage.html",
        )
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"delivery artifact does not exist: {missing[0]}")

    source_records = [
        _artifact(output_root / name, output_root)
        for name in (
            ".gitattributes",
            "README.md",
            "apps/use-keyboard-invoice-triage.html",
            "channel.production.json",
            "channel.json",
            "evidence.json",
            "render.py",
            "thumbs/use-keyboard-invoice-triage.svg",
            "verify_dom.mjs",
        )
    ]
    return {
        "schema": "keyboard-invoice-triage-delivery/1.0",
        "publication": spec.publication_id,
        "artifacts": {
            "master": _artifact(master, output_root, _probe(master, ffprobe)),
            "mp4": _artifact(mp4, output_root, _probe(mp4, ffprobe)),
            "webm": _artifact(webm, output_root, _probe(webm, ffprobe)),
        },
        "sourceArtifacts": source_records,
        "render": {
            "width": spec.width,
            "height": spec.height,
            "fps": spec.fps,
            "frames": spec.frame_count,
            "duration": spec.duration,
            "frameSamples": {
                str(index): frame_digest(index, spec)
                for index in (0, spec.frame_count // 2, spec.frame_count - 1)
            },
            "masterCodec": "ffv1",
            "audio": False,
        },
    }


def write_delivery(output_root: Path, ffprobe: str) -> Path:
    document = delivery_document(output_root, ffprobe)
    target = output_root / "delivery.json"
    target.write_text(
        json.dumps(
            document,
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
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--output-root", type=Path, default=ROOT)
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
        validate_manifest()
        output_root = args.output_root.resolve()
        if args.dry_run:
            plan = {
                "schema": "keyboard-invoice-triage-render-plan/1.0",
                "publication": SPEC.publication_id,
                "width": SPEC.width,
                "height": SPEC.height,
                "fps": SPEC.fps,
                "frames": SPEC.frame_count,
                "duration": SPEC.duration,
                "master": str(output_root / SPEC.master_relative),
                "thumbnail": str(output_root / SPEC.thumbnail_relative),
                "command": ffmpeg_command(
                    args.ffmpeg,
                    output_root / SPEC.master_relative,
                ),
            }
            print(json.dumps(plan, indent=2))
            return 0
        if args.delivery_only:
            ffprobe = _resolve_executable(args.ffprobe, "ffprobe")
            print(write_delivery(output_root, ffprobe))
        else:
            ffmpeg = _resolve_executable(args.ffmpeg, "ffmpeg")
            master, thumbnail = render(output_root, ffmpeg)
            print(master)
            print(thumbnail)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
