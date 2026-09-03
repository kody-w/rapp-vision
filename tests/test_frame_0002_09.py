"""Contract tests for candidate frame 0002-09, Create Vector Icon System."""

from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = (
    ROOT
    / "candidate-frame-0002"
    / "create-vector-icon-system"
)
APP_PATH = CANDIDATE / "apps" / "create-vector-icon-system.html"
MANIFEST_PATH = CANDIDATE / "channel.production.json"
CHANNEL_PATH = CANDIDATE / "channel.json"
EVIDENCE_PATH = CANDIDATE / "evidence.json"
DELIVERY_PATH = CANDIDATE / "delivery.json"
SPRITE_PATH = CANDIDATE / "exports" / "six-shapes.svg"
REFERENCE_PATH = CANDIDATE / "reference" / "reference-raster.json"
SNAPSHOT_PATH = CANDIDATE / "snapshots" / "create-vector-icon-system.svg"
STATE_SNAPSHOT_PATH = CANDIDATE / "snapshots" / "state-snapshot.json"
THUMB_PATH = CANDIDATE / "thumbs" / "create-vector-icon-system.svg"
RENDERER_PATH = CANDIDATE / "render.py"
BROWSER_RUNNER_PATH = ROOT / "tests" / "frame_0002_09_browser.mjs"
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
COMPILER_PATH = ROOT / "scripts" / "compile_publications.py"
EXPECTED_NAMES = ("bloom", "cairn", "hinge", "orbit", "pulse", "weave")
EXPECTED_SPRITE_HASH = (
    "6c32a2cef1a3ee29d398ae4070ec3a92961bb1625b4c5aa98b92e1c9318474f2"
)
EXPECTED_EDIT_SPRITE_HASH = (
    "0dd372e6f87d6e78d6386dcb4b19444e2221e9afef0a9034af4a97d2882edd61"
)
EXPECTED_GENERATED_GEOMETRY_HASH = (
    "c3df9da99bac96f2876087271bfd278f4f8dde093ed8d0f72b8ef3bad90099ca"
)
EXPECTED_EDIT_GENERATED_GEOMETRY_HASH = (
    "623ba0ea4f9357fc04e406edbf48d301aa26b4a943db98364e4ee9fc09d858bc"
)
EXPECTED_REFERENCE_HASH = (
    "61744b14a3c1e4f360d77207712e12f33e626259e1ff9eaca7cd46dd5ebd2d46"
)
EXPECTED_FRAME_SAMPLES = {
    0: "50706739cd9bbd4173256b44bb11cfc1f95e2fcd7f1db25c9bd30fb59b19748d",
    42: "886d0c810bcad4dfc678cf32f0ad79c601d4ae752a0246e69501ad38b4ecb6ab",
    84: "eb017ca7b7e8427e825363eb77ef760e2e2090d08feda98bbdfda0805f20015f",
    132: "dcaebb247c6e49652ef79d7e9a33d70cc6825de23a70348f584331ad29296858",
    179: "dd2d48c46eee43ceda36ad7b0eeb7e6c2e23ff5a5cfafe108b359a315ba8dfe9",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RENDERER = load_module("frame_0002_09_renderer", RENDERER_PATH)
VALIDATOR = load_module("frame_0002_09_validator", VALIDATOR_PATH)
COMPILER = load_module("frame_0002_09_compiler", COMPILER_PATH)


def resolve_optional_media_tool(name: str) -> str | None:
    try:
        return RENDERER.resolve_binary(name, name)
    except RuntimeError:
        return None


def resolve_browser() -> str | None:
    for environment_name in (
        "BROWSER",
        "CHROME_PATH",
        "CHROMIUM_PATH",
        "EDGE_PATH",
    ):
        value = os.environ.get(environment_name)
        if value and Path(value).is_file():
            return str(Path(value).resolve())
    for name in (
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "chrome",
        "msedge",
        "microsoft-edge",
    ):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    roots = [
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    relative_candidates = (
        Path("Google") / "Chrome" / "Application" / "chrome.exe",
        Path("Microsoft") / "Edge" / "Application" / "msedge.exe",
    )
    for root in filter(None, roots):
        for relative in relative_candidates:
            candidate = Path(root) / relative
            if candidate.is_file():
                return str(candidate.resolve())
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        cache = Path(local_app_data) / "ms-playwright"
        patterns = (
            "chromium-*/chrome-win*/chrome.exe",
            "chromium-*/chrome-linux*/chrome",
            "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
        )
        for pattern in patterns:
            matches = sorted(cache.glob(pattern))
            if matches:
                return str(matches[-1].resolve())
    return None


FFMPEG = resolve_optional_media_tool("ffmpeg")
FFPROBE = resolve_optional_media_tool("ffprobe")
NODE = shutil.which("node")
BROWSER = resolve_browser()


class ResourceIndex(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.resources: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        for name in ("src", "href", "poster", "action"):
            if attributes.get(name):
                self.resources.append((tag, name, attributes[name]))


def embedded_json(source: str, element_id: str):
    match = re.search(
        rf'<script\s+type="application/json"\s+id="{re.escape(element_id)}">\s*'
        r"(.*?)\s*</script>",
        source,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError(f"standalone app has no {element_id} JSON")
    return json.loads(match.group(1))


def embedded_states(source: str):
    return embedded_json(source, "contract-states")


def resolve(document, path: str):
    current = document
    for component in path.split("."):
        current = current[component]
    return current


def sprite_geometry() -> dict[str, tuple[tuple[tuple[float, float], ...], ...]]:
    root = ET.fromstring(SPRITE_PATH.read_text(encoding="utf-8"))
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    geometry = {}
    for symbol in root.findall(".//svg:symbol", namespace):
        name = symbol.attrib["id"].removeprefix("icon-")
        paths = []
        for path in symbol.findall("./svg:g/svg:path", namespace):
            values = [
                float(value)
                for value in re.findall(r"-?\d+(?:\.\d+)?", path.attrib["d"])
            ]
            paths.append(
                tuple(
                    (values[index], values[index + 1])
                    for index in range(0, len(values), 2)
                )
            )
        geometry[name] = tuple(paths)
    return geometry


def independent_segment_distance_squared(point, start, end) -> float:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    delta_x = x2 - x1
    delta_y = y2 - y1
    length_squared = delta_x * delta_x + delta_y * delta_y
    if length_squared == 0:
        return (px - x1) ** 2 + (py - y1) ** 2
    projection = (
        (px - x1) * delta_x + (py - y1) * delta_y
    ) / length_squared
    projection = max(0.0, min(1.0, projection))
    near_x = x1 + projection * delta_x
    near_y = y1 + projection * delta_y
    return (px - near_x) ** 2 + (py - near_y) ** 2


def independent_rasterize(paths, stroke: float) -> bytes:
    segments = [
        (path[index], path[index + 1])
        for path in paths
        for index in range(len(path) - 1)
    ]
    radius_squared = (stroke / 2) ** 2
    coverage = bytearray()
    for y in range(24):
        for x in range(24):
            inside = 0
            for sub_y in range(4):
                sample_y = y + (sub_y + 0.5) / 4
                for sub_x in range(4):
                    sample_x = x + (sub_x + 0.5) / 4
                    if any(
                        independent_segment_distance_squared(
                            (sample_x, sample_y),
                            start,
                            end,
                        )
                        <= radius_squared
                        for start, end in segments
                    ):
                        inside += 1
            coverage.append(round(inside * 255 / 16))
    return bytes(coverage)


def independent_system(stroke: float, *, invalid: bool = False) -> dict[str, bytes]:
    geometry = sprite_geometry()
    if invalid:
        pulse = [list(path) for path in geometry["pulse"]]
        pulse[0][3] = (13.0, 17.0)
        geometry["pulse"] = tuple(tuple(path) for path in pulse)
    return {
        name: independent_rasterize(geometry[name], stroke)
        for name in EXPECTED_NAMES
    }


def immutable_coverages() -> dict[str, bytes]:
    document = load_json(REFERENCE_PATH)
    return {
        icon["name"]: base64.b64decode(
            icon["coverageBase64"],
            validate=True,
        )
        for icon in document["icons"]
    }


def independent_comparison(stroke: float, *, invalid: bool = False):
    baseline = immutable_coverages()
    candidate = independent_system(stroke, invalid=invalid)
    differing = sum(
        before != after
        for name in EXPECTED_NAMES
        for before, after in zip(baseline[name], candidate[name])
    )
    total = len(EXPECTED_NAMES) * 24 * 24
    return {
        "differingPixels": differing,
        "differingPercent": round(differing / total * 100, 4),
        "status": "pass" if differing / total * 100 < 0.5 else "fail",
        "totalPixels": total,
    }


def run_browser_replay(actions):
    if not NODE:
        raise AssertionError("Node.js is required for the browser live replay")
    if not BROWSER:
        raise AssertionError(
            "Chrome, Chromium, Edge, or a Playwright Chromium is required "
            "for the browser live replay"
        )
    profile = CANDIDATE / ".frame-0002-09-browser"
    shutil.rmtree(profile, ignore_errors=True)
    encoded_actions = base64.b64encode(
        json.dumps(actions, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    try:
        completed = subprocess.run(
            [
                NODE,
                str(BROWSER_RUNNER_PATH),
                BROWSER,
                APP_PATH.resolve().as_uri(),
                encoded_actions,
                str(profile),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        if completed.returncode:
            raise AssertionError(
                completed.stderr.strip()
                or completed.stdout.strip()
                or f"browser replay exited {completed.returncode}"
            )
        return json.loads(completed.stdout)
    finally:
        shutil.rmtree(profile, ignore_errors=True)


class TestFrame000209CommissionAndManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(MANIFEST_PATH)
        cls.channel = load_json(CHANNEL_PATH)

    def test_exact_commission_is_bound_to_the_candidate(self):
        commissions = load_json(ROOT / "commissions.json")["commissions"]
        commission = next(
            item for item in commissions
            if item["id"] == "create-vector-icon-system"
        )
        self.assertEqual(commission["title"], "Create a six-icon vector system")
        self.assertEqual(
            commission["gates"]["objective_evidence"]["criterion"],
            (
                "The export contains exactly six named 24 by 24 SVG symbols and "
                "the reference raster comparison remains below 0.50 percent "
                "differing pixels."
            ),
        )
        self.assertEqual(
            commission["gates"]["exact_reset"]["steps"],
            [
                "Activate Restore icon fixture.",
                "Set zoom to 800 percent.",
                "Select the first symbol and clear comparison overlays.",
            ],
        )
        evidence = load_json(EVIDENCE_PATH)
        self.assertEqual(evidence["commission"]["id"], commission["id"])
        self.assertEqual(
            evidence["commission"]["criterion"],
            commission["gates"]["objective_evidence"]["criterion"],
        )

    def test_production_manifest_is_paired_and_under_twenty_seconds(self):
        self.assertEqual(
            self.manifest["schema"],
            "rapp-vision-production/1.0",
        )
        self.assertEqual(
            self.manifest["id"],
            "candidate-frame-0002-create-vector-icon-system",
        )
        self.assertEqual(len(self.manifest["videos"]), 1)
        video = self.manifest["videos"][0]
        self.assertEqual(video["id"], "create-vector-icon-system")
        self.assertEqual(video["duration"], 15)
        self.assertLessEqual(video["duration"], 20)
        self.assertEqual((video["width"], video["height"]), (960, 540))
        self.assertNotIn("sources", video)
        self.assertEqual(
            video["production"],
            {"master": "masters/create-vector-icon-system.mkv"},
        )
        self.assertEqual(
            video["thumb"],
            "thumbs/create-vector-icon-system.svg",
        )
        self.assertEqual(video["live"]["kind"], "rapp-vision-live/1.0")
        self.assertEqual(video["live"]["duration"], 15)
        selectors = [
            action["selector"]
            for scene in video["live"]["scenes"]
            for action in scene["actions"]
            if action["do"] == "click"
        ]
        self.assertEqual(
            selectors,
            [
                "#stroke-15-btn",
                "#regenerate-btn",
                "#stroke-2-btn",
                "#regenerate-btn",
                "#export-btn",
                "#off-grid-btn",
                "#restore-btn",
            ],
        )
        self.assertEqual(
            [
                action["selector"]
                for scene in video["live"]["scenes"]
                for action in scene["actions"]
                if action["do"] == "scroll"
            ],
            [
                "#stroke-15-btn",
                "#regenerate-btn",
                "#stroke-2-btn",
                "#regenerate-btn",
                "#export-btn",
                "#status-panel",
                "#off-grid-btn",
                "#status-panel",
                "#restore-btn",
                "#status-panel",
            ],
        )
        for scene in video["live"]["scenes"]:
            for action in scene["actions"]:
                if action["do"] == "scroll":
                    self.assertEqual(action["block"], "start")
                    self.assertEqual(action["behavior"], "auto")
                    self.assertNotIn("to", action)

    def test_compiled_channel_is_exact_compiler_output_and_validator_clean(self):
        compilation = COMPILER.prepare_compilation(MANIFEST_PATH)
        self.assertEqual(
            CHANNEL_PATH.read_text(encoding="utf-8"),
            COMPILER.deterministic_json(compilation.channel),
        )
        self.assertEqual(self.channel["schema"], "rapp-vision-channel/2.0")
        video = self.channel["videos"][0]
        self.assertNotIn("production", video)
        self.assertEqual(
            video["sources"],
            [
                {
                    "src": "media/create-vector-icon-system.mp4",
                    "type": "video/mp4",
                },
                {
                    "src": "media/create-vector-icon-system.webm",
                    "type": "video/webm",
                },
            ],
        )
        policy = load_json(ROOT / "policy" / "legacy-publications.json")
        errors = VALIDATOR.validate_channel(
            self.channel,
            CHANNEL_PATH.resolve().as_uri(),
            policy,
        )
        self.assertEqual(errors, [])


class TestFrame000209SpriteAndEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sprite_source = SPRITE_PATH.read_text(encoding="utf-8")
        cls.sprite = ET.fromstring(cls.sprite_source)
        cls.evidence = load_json(EVIDENCE_PATH)
        cls.reference = load_json(REFERENCE_PATH)

    def test_sprite_has_exact_six_named_grid_aligned_symbols(self):
        namespace = {"svg": "http://www.w3.org/2000/svg"}
        symbols = self.sprite.findall(".//svg:symbol", namespace)
        self.assertEqual(len(symbols), 6)
        self.assertEqual(
            tuple(symbol.attrib["id"].removeprefix("icon-") for symbol in symbols),
            EXPECTED_NAMES,
        )
        self.assertEqual(
            tuple(symbol.attrib["data-name"].lower() for symbol in symbols),
            EXPECTED_NAMES,
        )
        self.assertTrue(
            all(symbol.attrib["viewBox"] == "0 0 24 24" for symbol in symbols)
        )
        for symbol in symbols:
            titles = symbol.findall("./svg:title", namespace)
            self.assertEqual(len(titles), 1)
            groups = symbol.findall("./svg:g", namespace)
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].attrib["stroke-width"], "2")
            self.assertEqual(groups[0].attrib["stroke-linecap"], "round")
            self.assertEqual(groups[0].attrib["stroke-linejoin"], "round")
            paths = groups[0].findall("./svg:path", namespace)
            self.assertGreaterEqual(len(paths), 2)
            for path in paths:
                coordinates = [
                    float(value)
                    for value in re.findall(r"-?\d+(?:\.\d+)?", path.attrib["d"])
                ]
                self.assertTrue(coordinates)
                self.assertTrue(
                    all(value % 2 == 0 for value in coordinates),
                    (symbol.attrib["id"], path.attrib["d"]),
                )

    def test_sprite_bytes_hash_and_renderer_are_identical(self):
        objective = self.evidence["objective"]["sprite"]
        self.assertEqual(self.sprite_source, RENDERER.sprite_svg())
        self.assertEqual(sha256(SPRITE_PATH), EXPECTED_SPRITE_HASH)
        self.assertEqual(objective["sha256"], EXPECTED_SPRITE_HASH)
        self.assertEqual(objective["bytes"], SPRITE_PATH.stat().st_size)
        self.assertEqual(objective["symbolCount"], 6)
        self.assertEqual(tuple(objective["names"]), EXPECTED_NAMES)
        self.assertEqual(objective["viewBox"], "0 0 24 24")
        self.assertEqual(objective["pathSetSha256"], RENDERER.geometry_sha256())
        self.assertEqual(
            objective["generatedGeometrySha256"],
            EXPECTED_GENERATED_GEOMETRY_HASH,
        )

    def test_objective_raster_uses_an_independent_immutable_reference(self):
        self.assertEqual(sha256(REFERENCE_PATH), EXPECTED_REFERENCE_HASH)
        self.assertEqual(
            self.reference["schema"],
            "six-shapes-immutable-reference-raster/2.0",
        )
        self.assertTrue(self.reference["frozen"])
        self.assertEqual(self.reference["stroke"], 2.0)
        self.assertEqual(
            self.reference["geometrySha256"],
            RENDERER.geometry_sha256(),
        )
        reference = immutable_coverages()
        independently_rasterized = independent_system(2.0)
        for name in EXPECTED_NAMES:
            with self.subTest(icon=name):
                self.assertEqual(independently_rasterized[name], reference[name])
                self.assertEqual(
                    hashlib.sha256(reference[name]).hexdigest(),
                    next(
                        icon["coverageSha256"]
                        for icon in self.reference["icons"]
                        if icon["name"] == name
                    ),
                )

        accepted = independent_comparison(2.0)
        invalid = independent_comparison(2.0, invalid=True)
        former_reset = independent_comparison(1.5)
        comparison = RENDERER.reference_document()["comparison"]
        self.assertEqual(comparison["totalPixels"], 6 * 24 * 24)
        self.assertEqual(accepted["differingPixels"], 0)
        self.assertEqual(accepted["differingPercent"], 0)
        self.assertEqual(accepted["status"], "pass")
        self.assertEqual(comparison["acceptedDifferingPixels"], 0)
        self.assertEqual(comparison["acceptedDifferingPercent"], 0)
        self.assertEqual(comparison["acceptedStatus"], "pass")
        self.assertEqual(invalid["differingPixels"], 51)
        self.assertEqual(invalid["differingPercent"], 1.4757)
        self.assertEqual(invalid["status"], "fail")
        self.assertEqual(
            comparison["invalidDifferingPixels"],
            invalid["differingPixels"],
        )
        self.assertEqual(
            comparison["invalidDifferingPercent"],
            invalid["differingPercent"],
        )
        self.assertEqual(comparison["invalidStatus"], invalid["status"])
        self.assertEqual(former_reset["differingPixels"], 841)
        self.assertEqual(former_reset["differingPercent"], 24.3345)
        self.assertEqual(former_reset["status"], "fail")
        self.assertEqual(
            len(comparison["changedPixelHighlights"]),
            comparison["invalidDifferingPixels"],
        )
        self.assertTrue(
            all(
                pixel["icon"] == "pulse"
                for pixel in comparison["changedPixelHighlights"]
            )
        )
        invalid = comparison["invalidEdit"]
        self.assertEqual(invalid["from"], [12, 18])
        self.assertEqual(invalid["to"], [13, 17])
        self.assertTrue(any(value % 2 for value in invalid["to"]))

    def test_every_supported_stroke_has_a_hash_and_truthful_measurement(self):
        source = APP_PATH.read_text(encoding="utf-8")
        browser_records = embedded_json(source, "stroke-records")
        renderer_records = RENDERER.stroke_records()
        self.assertEqual(browser_records, renderer_records)
        self.assertEqual(
            set(browser_records),
            {"1", "1.5", "2", "2.5", "3"},
        )
        for key, record in browser_records.items():
            stroke = float(key)
            comparison = independent_comparison(stroke)
            sprite = RENDERER.sprite_svg(stroke).encode("utf-8")
            with self.subTest(stroke=stroke):
                self.assertEqual(record["bytes"], len(sprite))
                self.assertEqual(
                    record["sha256"],
                    hashlib.sha256(sprite).hexdigest(),
                )
                self.assertEqual(record["comparison"], comparison)
                self.assertEqual(len(record["sha256"]), 64)
                self.assertEqual(
                    record["geometrySha256"],
                    RENDERER.generated_geometry_sha256(stroke),
                )
                self.assertEqual(len(record["geometrySha256"]), 64)

    def test_evidence_claims_are_exact_and_self_checking(self):
        self.assertEqual(
            self.evidence["schema"],
            "candidate-frame-0002-create-vector-icon-system-evidence/2.0",
        )
        claims = {
            claim["id"]: claim
            for claim in self.evidence["claims"]
        }
        self.assertEqual(set(claims), {"positive", "rejected", "reset"})
        positive_selectors = [
            action["selector"]
            for action in claims["positive"]["actions"]
        ]
        self.assertEqual(
            positive_selectors,
            [
                "#stroke-15-btn",
                "#regenerate-btn",
                "#stroke-2-btn",
                "#regenerate-btn",
                "#export-btn",
            ],
        )
        self.assertEqual(
            self.evidence["browserReplay"]["selectors"],
            positive_selectors + ["#off-grid-btn", "#restore-btn"],
        )
        self.assertEqual(self.evidence["browserReplay"]["actionCount"], 17)
        self.assertTrue(self.evidence["browserReplay"]["coordinateFree"])
        self.assertEqual(
            self.evidence["browserReplay"]["scrollSelectors"],
            [
                "#stroke-15-btn",
                "#regenerate-btn",
                "#stroke-2-btn",
                "#regenerate-btn",
                "#export-btn",
                "#status-panel",
                "#off-grid-btn",
                "#status-panel",
                "#restore-btn",
                "#status-panel",
            ],
        )
        self.assertEqual(
            self.evidence["browserReplay"]["checkpoints"],
            [
                {
                    "afterAction": 10,
                    "claim": "positive",
                    "selector": "#status-panel",
                },
                {
                    "afterAction": 13,
                    "claim": "rejected",
                    "selector": "#status-panel",
                },
                {
                    "afterAction": 16,
                    "claim": "reset",
                    "selector": "#status-panel",
                },
            ],
        )
        positive_path = self.evidence["browserReplay"]["positivePath"]
        self.assertEqual(
            (
                positive_path["initialStroke"],
                positive_path["editedStroke"],
                positive_path["returnedStroke"],
                positive_path["generatedSymbolCount"],
            ),
            (2, 1.5, 2, 6),
        )
        self.assertEqual(
            positive_path["editedGeometrySha256"],
            EXPECTED_EDIT_GENERATED_GEOMETRY_HASH,
        )
        self.assertEqual(
            positive_path["returnedGeometrySha256"],
            EXPECTED_GENERATED_GEOMETRY_HASH,
        )
        self.assertEqual(
            positive_path["editedSpriteSha256"],
            EXPECTED_EDIT_SPRITE_HASH,
        )
        self.assertEqual(
            positive_path["returnedSpriteSha256"],
            EXPECTED_SPRITE_HASH,
        )
        app_states = embedded_states(APP_PATH.read_text(encoding="utf-8"))
        self.assertEqual(load_json(STATE_SNAPSHOT_PATH), app_states)
        for claim_id, claim in claims.items():
            self.assertEqual(claim["expectedState"], app_states[claim_id])
            self.assertTrue(claim["claim"])
            self.assertTrue(claim["actions"])
            self.assertTrue(claim["assertions"])
            for assertion in claim["assertions"]:
                self.assertEqual(
                    resolve(claim["expectedState"], assertion["path"]),
                    assertion["equals"],
                )

        positive = claims["positive"]["expectedState"]
        positive_edit = app_states["positiveEdit"]
        positive_return = app_states["positiveReturn"]
        rejected = claims["rejected"]["expectedState"]
        reset = claims["reset"]["expectedState"]
        checkpoints = {
            checkpoint["id"]: checkpoint
            for checkpoint in claims["positive"]["checkpoints"]
        }
        self.assertEqual(set(checkpoints), {"edited", "returned"})
        self.assertEqual(checkpoints["edited"]["expectedState"], positive_edit)
        self.assertEqual(
            checkpoints["returned"]["expectedState"],
            positive_return,
        )
        for checkpoint in checkpoints.values():
            for assertion in checkpoint["assertions"]:
                self.assertEqual(
                    resolve(checkpoint["expectedState"], assertion["path"]),
                    assertion["equals"],
                )
        self.assertEqual(positive_edit["accepted"]["rules"]["stroke"], 1.5)
        self.assertEqual(
            positive_edit["accepted"]["generatedGeometrySha256"],
            EXPECTED_EDIT_GENERATED_GEOMETRY_HASH,
        )
        self.assertEqual(
            positive_edit["accepted"]["spriteSha256"],
            EXPECTED_EDIT_SPRITE_HASH,
        )
        self.assertNotEqual(
            positive_edit["accepted"]["generatedGeometrySha256"],
            reset["accepted"]["generatedGeometrySha256"],
        )
        self.assertNotEqual(
            positive_edit["accepted"]["spriteSha256"],
            reset["accepted"]["spriteSha256"],
        )
        self.assertEqual(
            positive_edit["accepted"]["pathSetSha256"],
            reset["accepted"]["pathSetSha256"],
        )
        self.assertEqual(positive_return["accepted"], reset["accepted"])
        self.assertIsNone(positive_return["lastExport"])
        self.assertEqual(positive_return["status"], "accepted")
        self.assertEqual(rejected["accepted"], positive["accepted"])
        self.assertEqual(rejected["lastExport"], positive["lastExport"])
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(len(rejected["comparison"]["overlay"]), 51)
        self.assertEqual(
            reset["accepted"]["fixture"],
            "reference-stroke-2",
        )
        self.assertEqual(reset["accepted"]["rules"]["stroke"], 2)
        self.assertEqual(tuple(reset["accepted"]["symbols"]), EXPECTED_NAMES)
        self.assertEqual(reset["selection"], EXPECTED_NAMES[0])
        self.assertEqual(reset["zoom"], 800)
        self.assertEqual(reset["comparison"]["overlay"], [])
        self.assertEqual(reset["comparison"]["status"], "pass")
        self.assertEqual(
            self.evidence["objective"]["rasterComparison"]["referenceSha256"],
            EXPECTED_REFERENCE_HASH,
        )
        self.assertTrue(
            self.evidence["objective"]["rasterComparison"]["immutable"]
        )

    def test_rights_attestation_covers_original_offline_assets(self):
        rights = self.evidence["rightsPrivacy"]
        self.assertTrue(rights["rightsAttestation"])
        self.assertTrue(rights["privacyAttestation"])
        self.assertTrue(rights["noSecrets"])
        statement = rights["statement"].lower()
        for phrase in ("original", "no logos", "copied icons", "external fonts"):
            self.assertIn(phrase, statement)


class TestFrame000209StandaloneApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP_PATH.read_text(encoding="utf-8")
        cls.index = ResourceIndex()
        cls.index.feed(cls.source)

    def test_app_is_standalone_accessible_and_live_replay_selectors_exist(self):
        self.assertIn('<html lang="en">', self.source)
        self.assertIn("<main", self.source)
        self.assertIn('role="status"', self.source)
        self.assertIn('aria-live="polite"', self.source)
        self.assertIn('aria-atomic="true"', self.source)
        self.assertIn('data-reset="exact"', self.source)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.source)
        self.assertEqual(self.index.resources, [])
        required = {
            "stroke-rule",
            "stroke-15-btn",
            "stroke-2-btn",
            "regenerate-btn",
            "export-btn",
            "off-grid-btn",
            "restore-btn",
            "comparison-svg",
            "status-message",
            "sprite-output",
        }
        required.update(f"select-{name}" for name in EXPECTED_NAMES)
        self.assertTrue(required <= self.index.ids)

    def test_app_has_no_network_or_external_asset_capabilities(self):
        forbidden = (
            r"\bfetch\s*\(",
            r"\bXMLHttpRequest\b",
            r"\bWebSocket\b",
            r"\bEventSource\b",
            r"\bnavigator\.sendBeacon\b",
            r"@import\b",
            r"<iframe\b",
            r"<object\b",
            r"<embed\b",
            r"<script[^>]+\bsrc=",
            r"<link[^>]+\bhref=",
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertIsNone(
                    re.search(pattern, self.source, flags=re.IGNORECASE)
                )

    def test_reducer_exposes_success_failure_preservation_and_exact_reset(self):
        for marker in (
            "function initialState()",
            "function reduce(state, action)",
            'case "SET_STROKE":',
            'case "REGENERATE":',
            'case "EXPORT":',
            'case "OFF_GRID":',
            'case "RESTORE":',
            "return initialState();",
            "function strokeRecord(value)",
            "window.vectorIconSystem = Object.freeze",
        ):
            self.assertIn(marker, self.source)
        self.assertIn("const accepted = acceptedSystem(state.draftStroke)", self.source)
        self.assertIn("...clone(state)", self.source)
        self.assertIn("changed pixels are highlighted", self.source.lower())
        self.assertIn("accepted 6-symbol export is unchanged", self.source)
        self.assertIn('typeof spriteHash === "string"', self.source)
        self.assertNotIn(
            "state.accepted.spriteSha256.slice",
            self.source,
        )


class TestFrame000209BrowserLiveReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = load_json(MANIFEST_PATH)
        cls.actions = [
            action
            for scene in manifest["videos"][0]["live"]["scenes"]
            for action in scene["actions"]
        ]
        cls.result = run_browser_replay(cls.actions)
        cls.states = embedded_states(APP_PATH.read_text(encoding="utf-8"))
        cls.records = RENDERER.stroke_records()

    def test_authored_live_sequence_executes_in_a_real_browser(self):
        self.assertTrue(self.result["browser"])
        self.assertEqual(self.result["consoleErrors"], [])
        self.assertEqual(self.result["pageErrors"], [])
        self.assertEqual(self.result["initial"]["state"], self.states["reset"])
        self.assertEqual(
            [step["selector"] for step in self.result["steps"]],
            [
                action["selector"]
                for action in self.actions
                if action["do"] == "click"
            ],
        )
        self.assertEqual(self.result["actionCount"], len(self.actions))
        self.assertEqual(
            [step["selector"] for step in self.result["framing"]],
            [
                action["selector"]
                for action in self.actions
                if action["do"] == "scroll"
            ],
        )
        steps = self.result["steps"]
        edited = steps[1]
        returned = steps[3]
        exported = steps[4]
        off_grid = steps[5]
        restored = steps[6]
        self.assertEqual(
            edited["state"],
            self.states["positiveEdit"],
        )
        self.assertEqual(
            returned["state"],
            self.states["positiveReturn"],
        )
        self.assertEqual(
            exported["state"],
            self.states["positive"],
        )
        self.assertEqual(
            off_grid["state"],
            self.states["rejected"],
        )
        self.assertEqual(
            restored["state"],
            self.states["reset"],
        )
        self.assertEqual(
            restored["diffText"],
            "0.0000%",
        )
        self.assertEqual(
            restored["hashText"],
            f"{EXPECTED_SPRITE_HASH[:12]}…",
        )
        positive_path = self.result["positivePath"]
        self.assertEqual(
            (
                positive_path["initialStroke"],
                positive_path["editedStroke"],
                positive_path["returnedStroke"],
            ),
            (2, 1.5, 2),
        )
        self.assertEqual(positive_path["changedIconCount"], 6)
        self.assertEqual(
            positive_path["initialGeometrySha256"],
            EXPECTED_GENERATED_GEOMETRY_HASH,
        )
        self.assertEqual(
            positive_path["editedGeometrySha256"],
            EXPECTED_EDIT_GENERATED_GEOMETRY_HASH,
        )
        self.assertEqual(
            positive_path["returnedGeometrySha256"],
            EXPECTED_GENERATED_GEOMETRY_HASH,
        )
        self.assertEqual(
            positive_path["initialSpriteSha256"],
            EXPECTED_SPRITE_HASH,
        )
        self.assertEqual(
            positive_path["editedSpriteSha256"],
            EXPECTED_EDIT_SPRITE_HASH,
        )
        self.assertEqual(
            positive_path["returnedSpriteSha256"],
            EXPECTED_SPRITE_HASH,
        )

    def test_nondefault_supported_inputs_render_hashes_without_exceptions(self):
        results = {
            str(item["stroke"]): item
            for item in self.result["nondefault"]
        }
        self.assertEqual(set(results), {"1", "1.5", "2.5", "3"})
        for key, result in results.items():
            record = self.records[key]
            with self.subTest(stroke=key):
                self.assertEqual(
                    result["state"]["accepted"]["spriteSha256"],
                    record["sha256"],
                )
                self.assertEqual(
                    result["state"]["accepted"]["generatedGeometrySha256"],
                    record["geometrySha256"],
                )
                self.assertEqual(
                    result["generatedGeometrySha256"],
                    record["geometrySha256"],
                )
                self.assertEqual(
                    result["spriteTextSha256"],
                    record["sha256"],
                )
                self.assertEqual(result["generatedIconCount"], 6)
                self.assertTrue(
                    all(
                        width == key
                        for width in result["generatedStrokeWidths"]
                    )
                )
                self.assertEqual(
                    result["state"]["comparison"]["differingPixels"],
                    record["comparison"]["differingPixels"],
                )
                self.assertEqual(
                    result["state"]["comparison"]["differingPercent"],
                    record["comparison"]["differingPercent"],
                )
                self.assertEqual(result["state"]["comparison"]["status"], "fail")
                self.assertEqual(result["state"]["status"], "rejected")
                self.assertEqual(
                    result["hashText"],
                    f"{record['sha256'][:12]}…",
                )
                self.assertNotEqual(result["hashText"], "unavailable")
                self.assertTrue(result["exportDisabled"])


class TestFrame000209RendererAndSnapshots(unittest.TestCase):
    def test_renderer_uses_standard_library_and_has_fixed_render_contract(self):
        tree = ast.parse(RENDERER_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        self.assertTrue(
            imported <= {
                "__future__",
                "argparse",
                "base64",
                "dataclasses",
                "functools",
                "hashlib",
                "json",
                "math",
                "os",
                "pathlib",
                "re",
                "shutil",
                "subprocess",
                "sys",
                "typing",
                "xml",
            },
            imported,
        )
        self.assertEqual((RENDERER.WIDTH, RENDERER.HEIGHT), (960, 540))
        self.assertEqual(RENDERER.FPS, 12)
        self.assertEqual(RENDERER.FRAME_COUNT, 180)
        self.assertEqual(RENDERER.DURATION, 15)
        command = RENDERER.ffmpeg_command("ffmpeg-contract", Path("master.mkv"))
        for token in ("rawvideo", "rgb24", "pipe:0", "ffv1", "bgr0", "matroska"):
            self.assertIn(token, command)
        self.assertIn("-an", command)
        self.assertEqual(
            RENDERER.IMMUTABLE_REFERENCE_SHA256,
            EXPECTED_REFERENCE_HASH,
        )
        self.assertEqual(RENDERER.BASE_STROKE, 2.0)
        self.assertEqual(RENDERER.EDIT_STROKE, 1.5)
        self.assertEqual(RENDERER.REFERENCE_STROKE, 2.0)

    def test_distinctive_frame_samples_are_stable(self):
        actual = {
            index: RENDERER.frame_digest(index)
            for index in EXPECTED_FRAME_SAMPLES
        }
        self.assertEqual(actual, EXPECTED_FRAME_SAMPLES)
        self.assertEqual(len(set(actual.values())), len(actual))
        for index in actual:
            self.assertEqual(
                len(RENDERER.frame_rgb(index)),
                RENDERER.WIDTH * RENDERER.HEIGHT * 3,
            )

    def test_generated_snapshot_thumbnail_and_text_assets_are_exact(self):
        self.assertEqual(
            THUMB_PATH.read_text(encoding="utf-8"),
            RENDERER.thumbnail_svg(),
        )
        self.assertEqual(
            SNAPSHOT_PATH.read_text(encoding="utf-8"),
            RENDERER.snapshot_svg(),
        )
        RENDERER.verify_text_assets(CANDIDATE)
        for path in (THUMB_PATH, SNAPSHOT_PATH):
            root = ET.fromstring(path.read_text(encoding="utf-8"))
            self.assertEqual(root.attrib["viewBox"], "0 0 960 540")
            self.assertEqual(root.attrib["role"], "img")
            for element in root.iter():
                tag = element.tag.rsplit("}", 1)[-1].lower()
                self.assertNotIn(
                    tag,
                    {"script", "image", "foreignobject", "iframe", "object"},
                )
                for name, value in element.attrib.items():
                    self.assertFalse(name.lower().startswith("on"))
                    self.assertNotIn("javascript:", value.lower())


class TestFrame000209DeliveryIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delivery = load_json(DELIVERY_PATH)

    def test_delivery_hashes_and_sizes_are_always_checked(self):
        artifacts = self.delivery["artifacts"]
        self.assertEqual(
            set(artifacts),
            {
                "app",
                "channel",
                "documentation",
                "evidence",
                "master",
                "mp4",
                "production",
                "reference",
                "renderer",
                "snapshot",
                "sprite",
                "stateSnapshot",
                "thumbnail",
                "webm",
            },
        )
        for name, artifact in artifacts.items():
            path = CANDIDATE / artifact["path"]
            with self.subTest(artifact=name):
                self.assertTrue(path.is_file(), path)
                self.assertEqual(path.stat().st_size, artifact["bytes"])
                self.assertEqual(sha256(path), artifact["sha256"])
        self.assertEqual(
            artifacts["reference"]["sha256"],
            EXPECTED_REFERENCE_HASH,
        )


@unittest.skipUnless(
    FFMPEG and FFPROBE,
    "ffmpeg and ffprobe were not found through PATH, environment, or WinGet",
)
class TestFrame000209MediaAndRebuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delivery = load_json(DELIVERY_PATH)

    def test_delivery_codecs_dimensions_color_and_duration_are_reprobed(self):
        artifacts = self.delivery["artifacts"]
        expected_codecs = {
            "master": "ffv1",
            "mp4": "h264",
            "webm": "vp9",
        }
        for name, expected_codec in expected_codecs.items():
            artifact = artifacts[name]
            actual = RENDERER.probe_media(
                FFPROBE,
                CANDIDATE / artifact["path"],
            )
            with self.subTest(artifact=name):
                self.assertEqual(actual["codec"], expected_codec)
                self.assertEqual(
                    (actual["width"], actual["height"]),
                    (960, 540),
                )
                self.assertEqual(actual["duration"], 15)
                for key, value in actual.items():
                    self.assertEqual(artifact[key], value)
        for name in ("mp4", "webm"):
            artifact = artifacts[name]
            self.assertEqual(artifact["pixel_format"], "yuv420p")
            self.assertEqual(artifact["color_space"], "bt709")
            self.assertEqual(artifact["color_transfer"], "bt709")
            self.assertEqual(artifact["color_primaries"], "bt709")
            self.assertEqual(artifact["color_range"], "tv")
        self.assertEqual(artifacts["master"]["pixel_format"], "bgr0")
        self.assertEqual(artifacts["master"]["color_space"], "gbr")
        self.assertEqual(artifacts["master"]["color_range"], "pc")

    def test_existing_validator_ffprobes_the_compiled_channel(self):
        environment = dict(os.environ)
        environment["PATH"] = (
            str(Path(FFPROBE).parent)
            + os.pathsep
            + environment.get("PATH", "")
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_PATH),
                "--ffprobe-local",
                str(CHANNEL_PATH),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(f"{CHANNEL_PATH}: valid", completed.stdout)

    def test_full_renderer_and_compiler_rebuild_is_byte_stable(self):
        scratches = [
            CANDIDATE / ".frame-0002-09-rebuild-a",
            CANDIDATE / ".frame-0002-09-rebuild-b",
        ]
        for scratch in scratches:
            shutil.rmtree(scratch, ignore_errors=True)
        try:
            rebuilt_deliveries = []
            for scratch in scratches:
                scratch.mkdir()
                (scratch / "apps").mkdir()
                shutil.copy2(
                    APP_PATH,
                    scratch / "apps" / APP_PATH.name,
                )
                shutil.copy2(CANDIDATE / "README.md", scratch / "README.md")
                shutil.copy2(RENDERER_PATH, scratch / "render.py")
                RENDERER.write_text_assets(scratch)
                RENDERER.render_master(FFMPEG, scratch)
                shutil.copy2(
                    MANIFEST_PATH,
                    scratch / "channel.production.json",
                )
                compilation = COMPILER.prepare_compilation(
                    scratch / "channel.production.json"
                )
                COMPILER.build_compilation(
                    compilation,
                    ffmpeg=FFMPEG,
                    ffprobe=FFPROBE,
                )
                rebuilt_deliveries.append(
                    RENDERER.delivery_document(scratch, FFPROBE)
                )

            for relative in (
                Path("channel.json"),
                Path("exports/six-shapes.svg"),
                Path("reference/reference-raster.json"),
                Path("snapshots/create-vector-icon-system.svg"),
                Path("snapshots/state-snapshot.json"),
                Path("thumbs/create-vector-icon-system.svg"),
                Path("evidence.json"),
                Path("apps/create-vector-icon-system.html"),
                Path("README.md"),
                Path("render.py"),
            ):
                with self.subTest(artifact=relative.as_posix()):
                    self.assertEqual(
                        sha256(scratches[0] / relative),
                        sha256(CANDIDATE / relative),
                    )
            for relative in (
                Path("masters/create-vector-icon-system.mkv"),
                Path("media/create-vector-icon-system.mp4"),
                Path("media/create-vector-icon-system.webm"),
            ):
                with self.subTest(rebuilt=relative.as_posix()):
                    self.assertEqual(
                        sha256(scratches[0] / relative),
                        sha256(scratches[1] / relative),
                    )
            self.assertEqual(rebuilt_deliveries[0], rebuilt_deliveries[1])
            for key in ("master", "mp4", "webm"):
                rebuilt = rebuilt_deliveries[0]["artifacts"][key]
                delivered = self.delivery["artifacts"][key]
                for field in (
                    "codec",
                    "pixel_format",
                    "width",
                    "height",
                    "duration",
                    "color_space",
                    "color_transfer",
                    "color_primaries",
                    "color_range",
                ):
                    self.assertEqual(rebuilt.get(field), delivered.get(field))
        finally:
            for scratch in scratches:
                shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
