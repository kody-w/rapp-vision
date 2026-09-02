"""Contract tests for candidate frame 0002-09, Create Vector Icon System."""

from __future__ import annotations

import ast
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
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
COMPILER_PATH = ROOT / "scripts" / "compile_publications.py"
FFMPEG_DIR = Path(
    r"C:\Users\kowildfe\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1.1-essentials_build\bin"
)
FFMPEG = FFMPEG_DIR / "ffmpeg.exe"
FFPROBE = FFMPEG_DIR / "ffprobe.exe"
EXPECTED_NAMES = ("bloom", "cairn", "hinge", "orbit", "pulse", "weave")
EXPECTED_SPRITE_HASH = (
    "6c32a2cef1a3ee29d398ae4070ec3a92961bb1625b4c5aa98b92e1c9318474f2"
)
EXPECTED_FRAME_SAMPLES = {
    0: "bcb59b23114b600e6f4ac20d5afa24fb49cb9228033fb55985f417f4209b2fa1",
    42: "0dcc2fde27029b5d84aca5cdcda9be139280f187a04238bfd9acc9019a9e0ae8",
    84: "17cfb18dc5db6ddfa3bfa5cd2490ebcd9543b413bac27f88bc0d6bce9af75c3b",
    132: "ec28c82642a04eac5e8910619b3c1e6c51357efc4f2abafa29970eeb0ca44d21",
    179: "85201a48fbedbc440f8dd965cf6a419b701d40dd25604f949df423664abe8d80",
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


def embedded_states(source: str):
    match = re.search(
        r'<script\s+type="application/json"\s+id="contract-states">\s*'
        r"(.*?)\s*</script>",
        source,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError("standalone app has no contract-states JSON")
    return json.loads(match.group(1))


def resolve(document, path: str):
    current = document
    for component in path.split("."):
        current = current[component]
    return current


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
        ]
        self.assertEqual(
            selectors,
            [
                "#stroke-2-btn",
                "#regenerate-btn",
                "#export-btn",
                "#off-grid-btn",
                "#restore-btn",
            ],
        )

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

    def test_objective_raster_pass_and_visible_invalid_failure_are_recomputed(self):
        recomputed = RENDERER.reference_document()
        self.assertEqual(self.reference, recomputed)
        comparison = self.reference["comparison"]
        self.assertEqual(comparison["totalPixels"], 6 * 24 * 24)
        self.assertEqual(comparison["acceptedDifferingPixels"], 0)
        self.assertLess(
            comparison["acceptedDifferingPercent"],
            comparison["thresholdPercent"],
        )
        self.assertEqual(comparison["acceptedStatus"], "pass")
        self.assertEqual(comparison["invalidDifferingPixels"], 51)
        self.assertGreaterEqual(
            comparison["invalidDifferingPercent"],
            comparison["thresholdPercent"],
        )
        self.assertEqual(comparison["invalidStatus"], "fail")
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

    def test_evidence_claims_are_exact_and_self_checking(self):
        claims = {
            claim["id"]: claim
            for claim in self.evidence["claims"]
        }
        self.assertEqual(set(claims), {"positive", "rejected", "reset"})
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
        rejected = claims["rejected"]["expectedState"]
        reset = claims["reset"]["expectedState"]
        self.assertEqual(rejected["accepted"], positive["accepted"])
        self.assertEqual(rejected["lastExport"], positive["lastExport"])
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(len(rejected["comparison"]["overlay"]), 51)
        self.assertEqual(reset["accepted"]["fixture"], "original")
        self.assertEqual(reset["accepted"]["rules"]["stroke"], 1.5)
        self.assertEqual(tuple(reset["accepted"]["symbols"]), EXPECTED_NAMES)
        self.assertEqual(reset["selection"], EXPECTED_NAMES[0])
        self.assertEqual(reset["zoom"], 800)
        self.assertEqual(reset["comparison"]["overlay"], [])
        self.assertEqual(reset["comparison"]["status"], "pass")

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
            "window.vectorIconSystem = Object.freeze",
        ):
            self.assertIn(marker, self.source)
        self.assertIn("accepted: acceptedSystem(state.draftStroke)", self.source)
        self.assertIn("...clone(state)", self.source)
        self.assertIn("changed pixels are highlighted", self.source.lower())
        self.assertIn("accepted 6-symbol export is unchanged", self.source)


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
                "dataclasses",
                "functools",
                "hashlib",
                "json",
                "math",
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


@unittest.skipUnless(
    FFMPEG.is_file() and FFPROBE.is_file(),
    "the commissioned FFmpeg 8.1.1 binaries are required",
)
class TestFrame000209MediaAndRebuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delivery = load_json(DELIVERY_PATH)

    def test_delivery_hashes_codecs_dimensions_color_and_duration(self):
        artifacts = self.delivery["artifacts"]
        expected_codecs = {
            "master": "ffv1",
            "mp4": "h264",
            "webm": "vp9",
        }
        for name, artifact in artifacts.items():
            path = CANDIDATE / artifact["path"]
            with self.subTest(artifact=name):
                self.assertTrue(path.is_file(), path)
                self.assertEqual(path.stat().st_size, artifact["bytes"])
                self.assertEqual(sha256(path), artifact["sha256"])
                if name in expected_codecs:
                    self.assertEqual(artifact["codec"], expected_codecs[name])
                    self.assertEqual(
                        (artifact["width"], artifact["height"]),
                        (960, 540),
                    )
                    self.assertEqual(artifact["duration"], 15)
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
            str(FFMPEG_DIR)
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
        scratch = CANDIDATE / ".frame-0002-09-rebuild"
        shutil.rmtree(scratch, ignore_errors=True)
        try:
            scratch.mkdir()
            RENDERER.write_text_assets(scratch)
            rebuilt_master = RENDERER.render_master(str(FFMPEG), scratch)
            shutil.copy2(
                MANIFEST_PATH,
                scratch / "channel.production.json",
            )
            compilation = COMPILER.prepare_compilation(
                scratch / "channel.production.json"
            )
            COMPILER.build_compilation(
                compilation,
                ffmpeg=str(FFMPEG),
                ffprobe=str(FFPROBE),
            )

            for relative in (
                Path("masters/create-vector-icon-system.mkv"),
                Path("media/create-vector-icon-system.mp4"),
                Path("media/create-vector-icon-system.webm"),
                Path("channel.json"),
                Path("exports/six-shapes.svg"),
                Path("reference/reference-raster.json"),
                Path("snapshots/create-vector-icon-system.svg"),
                Path("snapshots/state-snapshot.json"),
                Path("thumbs/create-vector-icon-system.svg"),
                Path("evidence.json"),
            ):
                with self.subTest(artifact=relative.as_posix()):
                    self.assertEqual(
                        sha256(scratch / relative),
                        sha256(CANDIDATE / relative),
                    )
            self.assertEqual(
                sha256(rebuilt_master),
                self.delivery["artifacts"]["master"]["sha256"],
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
