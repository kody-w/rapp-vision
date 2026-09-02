"""Exact offline contracts for candidate frame 0002-04."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate-frame-0002" / "learn-grid-overflow"
APP_PATH = CANDIDATE / "apps" / "learn-grid-overflow.html"
MANIFEST_PATH = CANDIDATE / "channel.production.json"
CHANNEL_PATH = CANDIDATE / "channel.json"
EVIDENCE_PATH = CANDIDATE / "evidence.json"
DELIVERY_PATH = CANDIDATE / "delivery.json"
RENDERER_PATH = CANDIDATE / "render.py"
DELIVERY_BUILDER_PATH = CANDIDATE / "build_delivery.py"
DOM_VERIFIER_PATH = CANDIDATE / "verify_dom.mjs"
THUMB_PATH = CANDIDATE / "thumbs" / "learn-grid-overflow.svg"
COMPILER_PATH = ROOT / "scripts" / "compile_publications.py"
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
POLICY_PATH = ROOT / "policy" / "legacy-publications.json"
FFMPEG_BIN = Path(
    r"C:\Users\kowildfe\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1.1-essentials_build\bin"
)
FFMPEG = FFMPEG_BIN / "ffmpeg.exe"
FFPROBE = FFMPEG_BIN / "ffprobe.exe"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

EXPECTED_ACTION_SELECTORS = [
    "#inspect-btn",
    "#apply-fix-btn",
    "#viewport-1280-btn",
    "#restore-broken-btn",
    "#viewport-320-btn",
    "#scroll-end-btn",
    "#restore-broken-btn",
    "#viewport-320-btn",
    "#scroll-zero-btn",
]
REQUIRED_IDS = {
    "preview-stage",
    "preview-viewport",
    "fixture-grid",
    "payload",
    "fixture-token",
    "viewport-value",
    "scroll-width",
    "client-width",
    "comparison",
    "css-source",
    "status-message",
    "inspect-btn",
    "apply-fix-btn",
    "viewport-1280-btn",
    "restore-broken-btn",
    "viewport-320-btn",
    "scroll-end-btn",
    "scroll-zero-btn",
    "contract-states",
}
FRAME_SAMPLES = {
    0: "d05fd88895ec1e1f02355cbe22e3f3f9442de4543249a766ffa5dd6e0c29ad29",
    48: "1979c54d216745f66249d6f0f9c34d8febd717195cf7f0da91fc5b5b08bb2f10",
    96: "6b9734d801c9dd2c97d438e0df9a2dc2130cd7c37b388904597dfc14deb2eb3f",
    132: "d6058e90c1b491f2a16ec14f11a06380b6896bf85458ca74b7fe93bbec6eae4d",
    168: "1126a00a761fa9e9822bef87adcf7912063f6b31f68bbc1a24775f17cb8c2429",
    215: "05ba5aadee478a7d07338708c3bfda358adaa58d428e655b58ea290e44136b0e",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RENDERER = load_module("frame_0002_04_renderer", RENDERER_PATH)
DELIVERY_BUILDER = load_module(
    "frame_0002_04_delivery_builder", DELIVERY_BUILDER_PATH
)
COMPILER = load_module("frame_0002_04_compiler", COMPILER_PATH)
VALIDATOR = load_module("frame_0002_04_validator", VALIDATOR_PATH)


class AppIndex(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.resources = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.add(element_id)
        for name in ("src", "href", "poster", "action"):
            if attributes.get(name):
                self.resources.append((tag, name, attributes[name]))


def embedded_contract_states(source: str):
    match = re.search(
        r'<script\s+type="application/json"\s+id="contract-states">\s*'
        r"(.*?)\s*</script>",
        source,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError("app has no embedded contract states")
    return json.loads(match.group(1))


def resolve_path(document, path: str):
    current = document
    for component in path.split("."):
        current = current[component]
    return current


def is_subsequence(needle, haystack):
    cursor = iter(haystack)
    return all(any(candidate == item for candidate in cursor) for item in needle)


class TestFrame000204SourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(MANIFEST_PATH)
        cls.video = cls.manifest["videos"][0]
        cls.evidence = load_json(EVIDENCE_PATH)
        cls.publication = cls.evidence["publications"][0]
        cls.claims = {
            claim["id"]: claim for claim in cls.publication["claims"]
        }
        cls.source = APP_PATH.read_text(encoding="utf-8")

    def test_production_manifest_is_one_readable_paired_lesson(self):
        self.assertEqual(
            self.manifest["schema"], "rapp-vision-production/1.0"
        )
        self.assertEqual(self.manifest["id"], "candidate-frame-0002-04")
        self.assertEqual(self.video["id"], "learn-grid-overflow")
        self.assertEqual(self.video["title"], "Why the Grid Overflows")
        self.assertEqual(self.video["duration"], 18)
        self.assertLessEqual(self.video["duration"], 20)
        self.assertEqual((self.video["width"], self.video["height"]), (960, 540))
        self.assertEqual(
            self.video["production"],
            {"master": "masters/learn-grid-overflow.mkv"},
        )
        self.assertNotIn("sources", self.video)
        self.assertEqual(self.video["live"]["kind"], "rapp-vision-live/1.0")
        self.assertEqual(self.video["live"]["duration"], 18)
        self.assertEqual(
            [action["selector"] for action in self.video["live"]["scenes"][0]["actions"]],
            EXPECTED_ACTION_SELECTORS,
        )
        self.assertTrue(
            all(
                action["at"] < self.video["live"]["scenes"][0]["dur"]
                for action in self.video["live"]["scenes"][0]["actions"]
            )
        )
        self.assertIn("scrollWidth 612 > clientWidth 320", self.video["description"])
        self.assertIn("minmax(0, 1fr)", self.video["description"])
        self.assertIn("min-width: 0", self.video["description"])

    def test_evidence_and_embedded_snapshots_are_exact(self):
        self.assertEqual(
            self.evidence["schema"], "candidate-frame-evidence/1.0"
        )
        self.assertEqual(self.evidence["commission"]["id"], "learn-grid-overflow")
        self.assertEqual(set(self.claims), {"positive", "failure", "reset"})
        embedded = embedded_contract_states(self.source)
        self.assertEqual(
            embedded,
            {
                claim_id: self.claims[claim_id]["expectedState"]
                for claim_id in ("positive", "failure", "reset")
            },
        )
        for claim in self.claims.values():
            self.assertTrue(claim["actions"])
            self.assertTrue(claim["assertions"])
            for assertion in claim["assertions"]:
                self.assertEqual(
                    resolve_path(claim["expectedState"], assertion["path"]),
                    assertion["equals"],
                )

        reset = self.claims["reset"]["expectedState"]
        failure = self.claims["failure"]["expectedState"]
        self.assertEqual(failure["cssText"], reset["cssText"])
        self.assertEqual(failure["token"], reset["token"])
        self.assertGreater(failure["x"], 0)
        self.assertEqual(reset["x"], 0)
        self.assertEqual(
            [action["selector"] for action in self.claims["reset"]["actions"]],
            [
                "#restore-broken-btn",
                "#viewport-320-btn",
                "#scroll-zero-btn",
            ],
        )

    def test_live_replay_covers_success_failure_and_exact_reset(self):
        live_actions = EXPECTED_ACTION_SELECTORS
        for claim_id in ("positive", "failure", "reset"):
            selectors = [
                action["selector"] for action in self.claims[claim_id]["actions"]
            ]
            self.assertTrue(
                is_subsequence(selectors, live_actions),
                (claim_id, selectors, live_actions),
            )
        scene = self.video["live"]["scenes"][0]
        self.assertEqual(scene["t"], 0)
        self.assertEqual(scene["dur"], self.video["live"]["duration"])
        self.assertEqual(scene["ready"], {"selector": "#inspect-btn"})

    def test_html_is_standalone_original_and_inspectable(self):
        index = AppIndex()
        index.feed(self.source)
        self.assertEqual(index.resources, [])
        self.assertTrue(REQUIRED_IDS <= index.ids)
        self.assertIn('<html lang="en">', self.source)
        self.assertIn("window.gridOverflowLesson = contract", self.source)
        self.assertIn("window.tinySystem = contract", self.source)
        self.assertIn("function initialState()", self.source)
        self.assertIn("function reduce(state, action)", self.source)
        self.assertIn("function snapshot(value = state)", self.source)
        self.assertIn('data-reset="exact"', self.source)
        self.assertIn("Restore broken CSS", self.source)
        self.assertIn("Scroll to x = 0", self.source)
        self.assertIn("grid-template-columns: 92px minmax(0, 1fr);", self.source)
        self.assertIn("min-width: 0;", self.source)
        self.assertIn("overflow-wrap: anywhere;", self.source)
        self.assertIn("scrollWidth", self.source)
        self.assertIn("clientWidth", self.source)

        forbidden = (
            r"\bfetch\s*\(",
            r"\bXMLHttpRequest\b",
            r"\bWebSocket\b",
            r"\bEventSource\b",
            r"\bnavigator\.sendBeacon\b",
            r"@import\b",
            r"url\s*\(",
            r"https?://",
            r"<iframe\b",
            r"<object\b",
            r"<embed\b",
            r"\bDate\.now\b",
            r"\bMath\.random\b",
        )
        for pattern in forbidden:
            self.assertIsNone(
                re.search(pattern, self.source, flags=re.IGNORECASE),
                pattern,
            )

    def test_source_math_proves_the_commission(self):
        measurements = self.publication["measurements"]
        opening = measurements["opening"]
        fixed = measurements["fixed"]
        restored = measurements["restoredFailure"]
        self.assertEqual(14 + 92 + 26 + 480, opening["scrollWidth"])
        self.assertEqual(opening["clientWidth"], opening["viewport"])
        self.assertGreater(opening["scrollWidth"], opening["clientWidth"])
        self.assertEqual(opening["scrollWidth"] - opening["clientWidth"], 292)
        self.assertEqual(fixed["320"], {"clientWidth": 320, "scrollWidth": 320})
        self.assertEqual(
            fixed["1280"],
            {"clientWidth": 1280, "scrollWidth": 1280},
        )
        self.assertEqual(restored["scrollWidth"], opening["scrollWidth"])
        self.assertEqual(restored["clientWidth"], opening["clientWidth"])
        self.assertEqual(restored["x"], 292)

    def test_rights_privacy_and_no_external_resources_are_attested(self):
        rights = self.evidence["rightsPrivacy"]
        self.assertTrue(rights["rightsAttestation"])
        self.assertTrue(rights["privacyAttestation"])
        self.assertTrue(rights["noSecrets"])
        self.assertTrue(rights["originalFixture"])
        self.assertEqual(rights["externalResources"], [])


@unittest.skipUnless(
    EDGE.is_file() and shutil.which("node"),
    "Edge and Node.js are required for exact DOM verification",
)
class TestFrame000204BrowserDOM(unittest.TestCase):
    def test_actual_dom_measurements_actions_and_reset(self):
        profile = CANDIDATE / "_test-browser-profile"
        shutil.rmtree(profile, ignore_errors=True)
        completed = subprocess.run(
            [
                shutil.which("node"),
                str(DOM_VERIFIER_PATH),
                str(EDGE),
                str(APP_PATH),
                str(EVIDENCE_PATH),
                str(profile),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["opening"], "612>320")
        self.assertEqual(result["fixed320"], "320=320")
        self.assertEqual(result["fixed1280"], "1280=1280")
        self.assertEqual(result["restoredX"], 292)
        self.assertEqual(result["resetX"], 0)
        self.assertEqual(result["browserErrors"], 0)
        shutil.rmtree(profile, ignore_errors=True)


class TestFrame000204Renderer(unittest.TestCase):
    def test_renderer_is_standard_library_and_has_fixed_contract(self):
        tree = ast.parse(RENDERER_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        self.assertTrue(
            imported
            <= {
                "__future__",
                "argparse",
                "dataclasses",
                "hashlib",
                "json",
                "pathlib",
                "shutil",
                "subprocess",
                "sys",
                "typing",
                "xml",
            },
            imported,
        )
        self.assertEqual(RENDERER.SPEC.publication_id, "learn-grid-overflow")
        self.assertEqual(
            (
                RENDERER.SPEC.width,
                RENDERER.SPEC.height,
                RENDERER.SPEC.fps,
                RENDERER.SPEC.frame_count,
                RENDERER.SPEC.duration,
            ),
            (960, 540, 12, 216, 18),
        )
        command = RENDERER.ffmpeg_command("fixed-ffmpeg", Path("master.mkv"))
        for value in (
            "rawvideo",
            "rgb24",
            "pipe:0",
            "ffv1",
            "bgr0",
            "+bitexact",
        ):
            self.assertIn(value, command)
        self.assertEqual(command[command.index("-threads") + 1], "1")
        self.assertEqual(command[-1], "master.mkv")

    def test_renderer_frame_samples_are_byte_stable(self):
        for frame_index, expected in FRAME_SAMPLES.items():
            with self.subTest(frame=frame_index):
                self.assertEqual(RENDERER.frame_digest(frame_index), expected)
                self.assertEqual(RENDERER.frame_digest(frame_index), expected)
        self.assertEqual(
            len(RENDERER.frame_rgb(RENDERER.SPEC, 0)),
            960 * 540 * 3,
        )

    def test_thumbnail_is_safe_and_exactly_renderer_owned(self):
        source = THUMB_PATH.read_text(encoding="utf-8")
        self.assertEqual(source, RENDERER.thumbnail_svg())
        root = ET.fromstring(source)
        self.assertEqual(root.attrib["viewBox"], "0 0 960 540")
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1].lower()
            self.assertNotIn(
                tag,
                {"script", "image", "foreignobject", "iframe", "object"},
            )
            for name, value in element.attrib.items():
                self.assertFalse(name.lower().startswith("on"))
                self.assertNotIn("javascript:", value.lower())
                self.assertNotIn("data:", value.lower())
                self.assertNotIn("url(", value.lower())


@unittest.skipUnless(
    FFMPEG.is_file() and FFPROBE.is_file(),
    "the commissioned fixed FFmpeg 8.1.1 build is required",
)
class TestFrame000204CompiledDelivery(unittest.TestCase):
    def test_compiled_channel_matches_existing_compiler_and_validator(self):
        compilation = COMPILER.prepare_compilation(MANIFEST_PATH)
        self.assertEqual(load_json(CHANNEL_PATH), compilation.channel)
        policy = load_json(POLICY_PATH)
        errors = VALIDATOR.validate_channel(
            compilation.channel,
            "https://example.test/candidate-frame-0002/learn-grid-overflow/channel.json",
            policy,
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            VALIDATOR.ffprobe_local_media(
                compilation.channel,
                CHANNEL_PATH,
                executable=str(FFPROBE),
            ),
            [],
        )

    def test_delivery_hashes_codecs_color_and_duration_are_exact(self):
        delivery = load_json(DELIVERY_PATH)
        self.assertEqual(delivery["schema"], "candidate-frame-delivery/1.0")
        self.assertEqual(delivery["channel"], "candidate-frame-0002-04")
        self.assertEqual(delivery["publication"], "learn-grid-overflow")
        self.assertEqual(
            delivery,
            DELIVERY_BUILDER.delivery_document(str(FFPROBE)),
        )
        for relative, record in delivery["artifacts"].items():
            path = CANDIDATE / relative
            self.assertTrue(path.is_file(), path)
            content = path.read_bytes()
            self.assertEqual(record["bytes"], len(content))
            self.assertEqual(
                record["sha256"], hashlib.sha256(content).hexdigest()
            )

        master = delivery["media"]["master"]
        self.assertEqual(master["codec"], "ffv1")
        self.assertEqual(master["pixelFormat"], "bgr0")
        for kind, codec in (("mp4", "h264"), ("webm", "vp9")):
            record = delivery["media"][kind]
            with self.subTest(kind=kind):
                self.assertEqual(record["codec"], codec)
                self.assertEqual(record["pixelFormat"], "yuv420p")
                self.assertEqual((record["width"], record["height"]), (960, 540))
                self.assertEqual(record["duration"], 18)
                self.assertEqual(record["colorSpace"], "bt709")
                self.assertEqual(record["colorTransfer"], "bt709")
                self.assertEqual(record["colorPrimaries"], "bt709")
                self.assertEqual(record["colorRange"], "tv")

    def test_existing_compiler_rebuild_is_byte_stable(self):
        outputs = [
            CANDIDATE / "_test-rebuild-a",
            CANDIDATE / "_test-rebuild-b",
        ]
        for output in outputs:
            shutil.rmtree(output, ignore_errors=True)
        try:
            for output in outputs:
                compilation = COMPILER.prepare_compilation(MANIFEST_PATH, output)
                COMPILER.build_compilation(
                    compilation,
                    ffmpeg=str(FFMPEG),
                    ffprobe=str(FFPROBE),
                )
            for relative in (
                Path("channel.json"),
                Path("media") / "learn-grid-overflow.mp4",
                Path("media") / "learn-grid-overflow.webm",
            ):
                first = (outputs[0] / relative).read_bytes()
                second = (outputs[1] / relative).read_bytes()
                self.assertEqual(
                    hashlib.sha256(first).hexdigest(),
                    hashlib.sha256(second).hexdigest(),
                    relative,
                )
                self.assertEqual(
                    hashlib.sha256(first).hexdigest(),
                    hashlib.sha256((CANDIDATE / relative).read_bytes()).hexdigest(),
                    relative,
                )
        finally:
            for output in outputs:
                shutil.rmtree(output, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
