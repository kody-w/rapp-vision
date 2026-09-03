"""Portable, exact contracts for candidate frame 0002-04."""

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
CANDIDATE = ROOT / "candidate-frame-0002" / "learn-grid-overflow"
APP_PATH = CANDIDATE / "apps" / "learn-grid-overflow.html"
README_PATH = CANDIDATE / "README.md"
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
EXPECTED_SCROLL_SELECTORS = [
    "#inspect-btn",
    "#apply-fix-btn",
    "#viewport-1280-btn",
    "#status-message",
    "#restore-broken-btn",
    "#viewport-320-btn",
    "#scroll-end-btn",
    "#status-message",
    "#restore-broken-btn",
    "#viewport-320-btn",
    "#scroll-zero-btn",
    "#status-message",
]
REQUIRED_IDS = {
    "preview-stage",
    "preview-viewport",
    "fixture-grid",
    "payload",
    "token-rail",
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
    0: "988f000b2d514c368300a0c24242f8fdd4b0ef8d82c9f09d319ec3a1f082d7a9",
    48: "3cf3a10ca0948549710916f51effac9b0028ae530362d8de7f00bc9172863652",
    96: "6b9734d801c9dd2c97d438e0df9a2dc2130cd7c37b388904597dfc14deb2eb3f",
    132: "504194fd91a1b5685540b046b868ad9c5059bc4a877ee106af6b339041c53da8",
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


def executable(value: str | None) -> str | None:
    if not value:
        return None
    expanded = Path(os.path.expandvars(value)).expanduser()
    if expanded.is_absolute() or expanded.parent != Path("."):
        return str(expanded.resolve()) if expanded.is_file() else None
    return shutil.which(value)


def discover(
    environment: tuple[str, ...],
    names: tuple[str, ...],
    common: tuple[Path, ...],
) -> str | None:
    for variable in environment:
        resolved = executable(os.environ.get(variable))
        if resolved:
            return resolved
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    for path in common:
        if path.is_file():
            return str(path.resolve())
    return None


def common_browser_paths() -> tuple[Path, ...]:
    paths = [
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/google-chrome-stable"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
        Path("/opt/google/chrome/chrome"),
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ]
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            paths.extend(
                [
                    Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                    Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe",
                ]
            )
    return tuple(paths)


def common_node_paths() -> tuple[Path, ...]:
    paths = [Path("/usr/bin/node"), Path("/usr/local/bin/node")]
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            paths.append(Path(root) / "nodejs" / "node.exe")
    return tuple(paths)


NODE = discover(("FRAME_NODE",), ("node", "nodejs"), common_node_paths())
BROWSER = discover(
    ("FRAME_BROWSER", "BROWSER", "EDGE_PATH", "CHROME_PATH"),
    (
        "msedge",
        "microsoft-edge",
        "microsoft-edge-stable",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ),
    common_browser_paths(),
)
try:
    FFMPEG = RENDERER._resolve_ffmpeg(None)
except RuntimeError:
    FFMPEG = None
try:
    FFPROBE = DELIVERY_BUILDER.resolve_ffprobe(None)
except RuntimeError:
    FFPROBE = None


def truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


RELEASE_MODE = truthy(os.environ.get("CI")) or truthy(
    os.environ.get("FRAME_0002_04_RELEASE")
)
REQUIRED_RELEASE_TOOLS = {
    "Node.js": NODE,
    "Edge/Chrome": BROWSER,
    "FFmpeg": FFMPEG,
    "FFprobe": FFPROBE,
}


def require_tools(test: unittest.TestCase, **tools: str | None) -> None:
    missing = [name for name, path in tools.items() if not path]
    if not missing:
        return
    message = "required tool(s) not found: " + ", ".join(missing)
    if RELEASE_MODE:
        test.fail(message)
    test.skipTest(message)


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


class TestFrame000204AlwaysOn(unittest.TestCase):
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
        scene = self.video["live"]["scenes"][0]
        self.assertEqual(
            [
                action["selector"]
                for action in scene["actions"]
                if action["do"] == "click"
            ],
            EXPECTED_ACTION_SELECTORS,
        )
        self.assertEqual(
            [
                action["selector"]
                for action in scene["actions"]
                if action["do"] == "scroll"
            ],
            EXPECTED_SCROLL_SELECTORS,
        )
        for action in scene["actions"]:
            if action["do"] == "scroll":
                self.assertEqual(action["block"], "start")
                self.assertEqual(action["behavior"], "auto")
                self.assertNotIn("to", action)
        self.assertTrue(all(action["at"] < scene["dur"] for action in scene["actions"]))
        self.assertIn("scrollWidth 612 > clientWidth 320", self.video["description"])
        self.assertIn("min-width: auto", self.video["description"])
        self.assertIn("changes only that declaration", self.video["description"])
        self.assertNotIn("minmax(0, 1fr)", self.video["description"])

    def test_evidence_and_embedded_snapshots_are_exact(self):
        self.assertEqual(
            self.evidence["schema"], "candidate-frame-evidence/1.0"
        )
        self.assertEqual(self.evidence["commission"]["id"], "learn-grid-overflow")
        self.assertEqual(set(self.claims), {"positive", "failure", "reset"})
        framing = self.publication["liveFraming"]
        self.assertEqual(framing["actionCount"], 21)
        self.assertTrue(framing["coordinateFree"])
        self.assertEqual(framing["scrollSelectors"], EXPECTED_SCROLL_SELECTORS)
        self.assertEqual(
            framing["checkpoints"],
            [
                {
                    "afterAction": 6,
                    "claim": "positive",
                    "selector": "#status-message",
                },
                {
                    "afterAction": 13,
                    "claim": "failure",
                    "selector": "#status-message",
                },
                {
                    "afterAction": 20,
                    "claim": "reset",
                    "selector": "#status-message",
                },
            ],
        )
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
        self.assertEqual(failure["cause"], reset["cause"])
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

    def test_the_advertised_fix_changes_exactly_one_declaration(self):
        before = self.claims["reset"]["expectedState"]["cssText"].splitlines()
        after = self.claims["positive"]["expectedState"]["cssText"].splitlines()
        self.assertEqual(len(before), len(after))
        changed = [
            (old, new)
            for old, new in zip(before, after)
            if old != new
        ]
        self.assertEqual(
            changed,
            [("  min-width: auto;", "  min-width: 0;")],
        )
        source_fix = self.publication["sourceFix"]
        self.assertEqual(source_fix["changedDeclarations"], 1)
        self.assertEqual(source_fix["before"], ["min-width: auto;"])
        self.assertEqual(source_fix["after"], ["min-width: 0;"])
        self.assertEqual(
            source_fix["unchanged"],
            [
                "grid-template-columns: 92px 1fr;",
                "overflow: clip;",
                "width: 480px;",
            ],
        )

    def test_live_replay_covers_success_failure_and_exact_reset(self):
        for claim_id in ("positive", "failure", "reset"):
            selectors = [
                action["selector"] for action in self.claims[claim_id]["actions"]
            ]
            self.assertTrue(
                is_subsequence(selectors, EXPECTED_ACTION_SELECTORS),
                (claim_id, selectors, EXPECTED_ACTION_SELECTORS),
            )
        scene = self.video["live"]["scenes"][0]
        self.assertEqual(scene["t"], 0)
        self.assertEqual(scene["dur"], self.video["live"]["duration"])
        self.assertEqual(scene["ready"], {"selector": "#inspect-btn"})

    def test_html_is_standalone_original_and_measures_the_real_dom(self):
        index = AppIndex()
        index.feed(self.source)
        self.assertEqual(index.resources, [])
        self.assertTrue(REQUIRED_IDS <= index.ids)
        for value in (
            '<html lang="en">',
            "window.gridOverflowLesson = contract",
            "window.tinySystem = contract",
            "function initialState()",
            "function reduce(state, action)",
            "function readDomMetrics(viewport)",
            "function snapshot(value = state)",
            'data-reset="exact"',
            "Restore broken CSS",
            "Scroll to x = 0",
            "grid-template-columns: 92px 1fr;",
            "min-width: auto;",
            "min-width: 0;",
            "overflow: clip;",
            "width: 480px;",
            "preview.scrollWidth",
            "preview.clientWidth",
            "preview.scrollLeft",
            "getComputedStyle(payload)",
        ):
            self.assertIn(value, self.source)
        self.assertNotIn("BROKEN_SCROLL_WIDTH", self.source)
        self.assertNotIn("expectedMetrics", self.source)
        self.assertNotIn("overflow-wrap: anywhere", self.source)
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

    def test_recorded_browser_geometry_proves_the_automatic_minimum(self):
        measurements = self.publication["measurements"]
        opening = measurements["opening"]
        fixed = measurements["fixed"]
        restored = measurements["restoredFailure"]
        self.assertEqual(14 + 92 + 26 + 480, opening["scrollWidth"])
        self.assertEqual(opening["clientWidth"], opening["viewport"])
        self.assertGreater(opening["scrollWidth"], opening["clientWidth"])
        self.assertEqual(opening["scrollWidth"] - opening["clientWidth"], 292)
        self.assertEqual(
            opening["cause"],
            {
                "itemMinWidth": "auto",
                "itemOverflow": "clip",
                "payloadWidth": 480,
                "railWidth": 480,
            },
        )
        self.assertEqual(fixed["320"]["scrollWidth"], 320)
        self.assertEqual(fixed["320"]["clientWidth"], 320)
        self.assertEqual(fixed["320"]["cause"]["payloadWidth"], 174)
        self.assertEqual(fixed["320"]["cause"]["railWidth"], 480)
        self.assertEqual(fixed["1280"]["scrollWidth"], 1280)
        self.assertEqual(fixed["1280"]["clientWidth"], 1280)
        self.assertEqual(fixed["1280"]["cause"]["payloadWidth"], 1134)
        self.assertEqual(restored["scrollWidth"], opening["scrollWidth"])
        self.assertEqual(restored["clientWidth"], opening["clientWidth"])
        self.assertEqual(restored["cause"], opening["cause"])
        self.assertEqual(restored["x"], 292)

    def test_compiled_channel_schema_and_registry_policy_always_validate(self):
        compilation = COMPILER.prepare_compilation(MANIFEST_PATH)
        self.assertEqual(load_json(CHANNEL_PATH), compilation.channel)
        policy = load_json(POLICY_PATH)
        errors = VALIDATOR.validate_channel(
            compilation.channel,
            "https://example.test/candidate-frame-0002/learn-grid-overflow/channel.json",
            policy,
        )
        self.assertEqual(errors, [])

    def test_delivery_schema_and_hashes_always_validate(self):
        delivery = load_json(DELIVERY_PATH)
        self.assertEqual(delivery["schema"], "candidate-frame-delivery/1.0")
        self.assertEqual(delivery["channel"], "candidate-frame-0002-04")
        self.assertEqual(delivery["publication"], "learn-grid-overflow")
        self.assertEqual(set(delivery["artifacts"]), set(DELIVERY_BUILDER.FILES))
        for relative, record in delivery["artifacts"].items():
            path = CANDIDATE / relative
            self.assertTrue(path.is_file(), path)
            content = path.read_bytes()
            self.assertEqual(record["path"], relative)
            self.assertEqual(record["bytes"], len(content))
            self.assertEqual(
                record["sha256"], hashlib.sha256(content).hexdigest()
            )
        self.assertEqual(delivery["media"]["master"]["codec"], "ffv1")
        self.assertEqual(delivery["media"]["mp4"]["codec"], "h264")
        self.assertEqual(delivery["media"]["webm"]["codec"], "vp9")

    def test_renderer_frames_and_thumbnail_are_byte_stable(self):
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
                "os",
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
        for value in ("rawvideo", "rgb24", "pipe:0", "ffv1", "bgr0", "+bitexact"):
            self.assertIn(value, command)
        self.assertEqual(command[command.index("-threads") + 1], "1")
        for frame_index, expected in FRAME_SAMPLES.items():
            with self.subTest(frame=frame_index):
                self.assertEqual(RENDERER.frame_digest(frame_index), expected)
                self.assertEqual(RENDERER.frame_digest(frame_index), expected)
        self.assertEqual(
            len(RENDERER.frame_rgb(RENDERER.SPEC, 0)),
            960 * 540 * 3,
        )
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

    def test_rights_privacy_and_portable_docs_are_attested(self):
        rights = self.evidence["rightsPrivacy"]
        self.assertTrue(rights["rightsAttestation"])
        self.assertTrue(rights["privacyAttestation"])
        self.assertTrue(rights["noSecrets"])
        self.assertTrue(rights["originalFixture"])
        self.assertEqual(rights["externalResources"], [])
        for path in (
            README_PATH,
            RENDERER_PATH,
            DELIVERY_BUILDER_PATH,
            DOM_VERIFIER_PATH,
        ):
            self.assertNotIn("kowildfe", path.read_text(encoding="utf-8").lower())
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("FRAME_BROWSER", readme)
        self.assertIn("FRAME_FFMPEG", readme)
        self.assertIn("FRAME_0002_04_RELEASE=1", readme)


class TestFrame000204ReleaseGate(unittest.TestCase):
    def test_release_requires_the_full_execution_toolchain(self):
        if not RELEASE_MODE:
            self.skipTest(
                "set FRAME_0002_04_RELEASE=1 (CI implies it) to require tools"
            )
        missing = [
            name for name, path in REQUIRED_RELEASE_TOOLS.items() if not path
        ]
        self.assertEqual(
            missing,
            [],
            "release validation cannot skip missing tools: " + ", ".join(missing),
        )


class TestFrame000204BrowserExecution(unittest.TestCase):
    def test_real_edge_or_chrome_measurements_actions_and_reset(self):
        require_tools(self, Node=NODE, Browser=BROWSER)
        profile = CANDIDATE / "_test-browser-profile"
        shutil.rmtree(profile, ignore_errors=True)
        try:
            completed = subprocess.run(
                [
                    NODE,
                    str(DOM_VERIFIER_PATH),
                    BROWSER,
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
            self.assertRegex(result["browser"], r"(Chrome|Chromium|Edge|Edg)/")
            self.assertEqual(result["opening"], "612>320")
            self.assertEqual(result["fixed320"], "320=320")
            self.assertEqual(result["fixed1280"], "1280=1280")
            self.assertEqual(result["sourceChanges"], 1)
            self.assertEqual(result["fixedPayload320"], 174)
            self.assertEqual(result["restoredX"], 292)
            self.assertEqual(result["resetX"], 0)
            self.assertEqual(result["browserErrors"], 0)
        finally:
            shutil.rmtree(profile, ignore_errors=True)


class TestFrame000204MediaExecution(unittest.TestCase):
    def test_lossless_master_decodes_to_the_renderer_frames(self):
        require_tools(self, FFmpeg=FFMPEG)
        frame_size = RENDERER.SPEC.width * RENDERER.SPEC.height * 3
        process = subprocess.Popen(
            [
                FFMPEG,
                "-v",
                "error",
                "-i",
                str(CANDIDATE / RENDERER.SPEC.master_relative),
                "-map",
                "0:v:0",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIsNotNone(process.stdout)
        self.assertIsNotNone(process.stderr)

        def read_exact(size):
            chunks = []
            remaining = size
            while remaining:
                chunk = process.stdout.read(remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)

        for frame_index in range(RENDERER.SPEC.frame_count):
            frame = read_exact(frame_size)
            self.assertEqual(len(frame), frame_size, frame_index)
            if frame_index in FRAME_SAMPLES:
                self.assertEqual(
                    hashlib.sha256(frame).hexdigest(),
                    FRAME_SAMPLES[frame_index],
                    frame_index,
                )
        self.assertEqual(process.stdout.read(1), b"")
        stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
        return_code = process.wait()
        process.stdout.close()
        process.stderr.close()
        self.assertEqual(return_code, 0, stderr)

    def test_real_ffprobe_matches_delivery_and_publication_contracts(self):
        require_tools(self, FFprobe=FFPROBE)
        compilation = COMPILER.prepare_compilation(MANIFEST_PATH)
        self.assertEqual(
            VALIDATOR.ffprobe_local_media(
                compilation.channel,
                CHANNEL_PATH,
                executable=FFPROBE,
            ),
            [],
        )
        delivery = load_json(DELIVERY_PATH)
        self.assertEqual(
            delivery,
            DELIVERY_BUILDER.delivery_document(FFPROBE),
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

    def test_compiler_rebuild_is_deterministic_with_discovered_tools(self):
        require_tools(self, FFmpeg=FFMPEG, FFprobe=FFPROBE)
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
                    ffmpeg=FFMPEG,
                    ffprobe=FFPROBE,
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
                (outputs[0] / "channel.json").read_bytes(),
                CHANNEL_PATH.read_bytes(),
            )
        finally:
            for output in outputs:
                shutil.rmtree(output, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
