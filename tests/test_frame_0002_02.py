"""Contract tests for candidate frame 0002-02: keyboard invoice triage."""

from __future__ import annotations

import ast
import copy
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
    / "use-keyboard-invoice-triage"
)
PUBLICATION_ID = "use-keyboard-invoice-triage"
MANIFEST_PATH = CANDIDATE / "channel.production.json"
CHANNEL_PATH = CANDIDATE / "channel.json"
APP_PATH = CANDIDATE / "apps" / f"{PUBLICATION_ID}.html"
EVIDENCE_PATH = CANDIDATE / "evidence.json"
DELIVERY_PATH = CANDIDATE / "delivery.json"
RENDERER_PATH = CANDIDATE / "render.py"
VERIFY_DOM_PATH = CANDIDATE / "verify_dom.mjs"
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
COMPILER_PATH = ROOT / "scripts" / "compile_publications.py"
NODE = shutil.which("node")

EXPECTED_FOCUS_ORDER = (
    "invoice-syn-001",
    "invoice-syn-002",
    "invoice-syn-003",
    "amount-input",
    "code-select",
    "save-editor-btn",
    "cancel-editor-btn",
    "export-button",
    "restore-button",
    "confirm-restore-btn",
    "cancel-restore-btn",
)
EXPECTED_CONTROLS = set(EXPECTED_FOCUS_ORDER)

EXPECTED_MANIFEST_ACTIONS = [
    {"at": 0.5, "do": "key", "code": "Enter"},
    {"at": 1.1, "do": "key", "code": "ArrowDown"},
    {"at": 1.7, "do": "key", "code": "Enter"},
    {"at": 2.3, "do": "key", "code": "ArrowDown"},
    {"at": 2.9, "do": "key", "code": "Enter"},
    {"at": 3.5, "do": "key", "code": "ArrowDown"},
    {"at": 4.1, "do": "key", "code": "Enter"},
    {"at": 4.8, "do": "key", "code": "Tab"},
    {"at": 5.4, "do": "key", "code": "Enter"},
    {"at": 6.4, "do": "keydown", "code": "ShiftLeft"},
    {"at": 6.7, "do": "key", "code": "Tab"},
    {"at": 7.0, "do": "keyup", "code": "ShiftLeft"},
    {"at": 7.4, "do": "key", "code": "Enter"},
    {"at": 8.2, "do": "type", "text": "-1.00"},
    {"at": 9.2, "do": "key", "code": "Enter"},
    {"at": 10.0, "do": "key", "code": "Tab"},
    {"at": 10.5, "do": "key", "code": "Tab"},
    {"at": 11.0, "do": "key", "code": "Tab"},
    {"at": 11.5, "do": "key", "code": "Tab"},
    {"at": 12.3, "do": "key", "code": "Enter"},
    {"at": 14.3, "do": "key", "code": "Enter"},
]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_module("validate_frame_0002_02", VALIDATOR_PATH)
COMPILER = load_module("compile_frame_0002_02", COMPILER_PATH)
RENDERER = load_module("render_frame_0002_02", RENDERER_PATH)


def optional_media_tool(name: str) -> Path | None:
    try:
        return Path(RENDERER.discover_executable(name))
    except RuntimeError:
        return None


def browser_candidate(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value.strip().strip('"')).expanduser()
    if candidate.is_file() and re.search(
        r"(chrome|chromium|edge|brave)",
        candidate.name,
        flags=re.IGNORECASE,
    ):
        return candidate.resolve()
    resolved = shutil.which(value)
    if resolved and re.search(
        r"(chrome|chromium|edge|brave)",
        Path(resolved).name,
        flags=re.IGNORECASE,
    ):
        return Path(resolved).resolve()
    return None


def discover_browser() -> Path | None:
    for variable in (
        "RAPP_VISION_BROWSER",
        "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH",
        "EDGE_BIN",
        "CHROME_BIN",
        "CHROMIUM_BIN",
        "BROWSER",
    ):
        found = browser_candidate(os.environ.get(variable))
        if found:
            return found
    for command in (
        "msedge",
        "microsoft-edge",
        "microsoft-edge-stable",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "brave-browser",
    ):
        found = browser_candidate(command)
        if found:
            return found

    candidates: list[Path] = []
    if sys.platform == "win32":
        for root in filter(
            None,
            (
                os.environ.get("ProgramFiles"),
                os.environ.get("ProgramFiles(x86)"),
                os.environ.get("LOCALAPPDATA"),
            ),
        ):
            base = Path(root)
            candidates.extend(
                (
                    base / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                    base / "Google" / "Chrome" / "Application" / "chrome.exe",
                    base / "Chromium" / "Application" / "chrome.exe",
                    base
                    / "BraveSoftware"
                    / "Brave-Browser"
                    / "Application"
                    / "brave.exe",
                )
            )
    elif sys.platform == "darwin":
        candidates.extend(
            (
                Path(
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                ),
                Path(
                    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
                ),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
                Path(
                    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
                ),
            )
        )
    else:
        candidates.extend(
            Path(path)
            for path in (
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/microsoft-edge",
                "/usr/bin/microsoft-edge-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/brave-browser",
                "/usr/local/bin/google-chrome",
                "/usr/local/bin/chromium",
                "/snap/bin/chromium",
            )
        )
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


FFMPEG = optional_media_tool("ffmpeg")
FFPROBE = optional_media_tool("ffprobe")
BROWSER = discover_browser()


def embedded_json(source: str, element_id: str):
    match = re.search(
        rf'<script\s+type="application/json"\s+id="{re.escape(element_id)}">\s*'
        r"(.*?)\s*</script>",
        source,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError(f"missing embedded JSON #{element_id}")
    return json.loads(match.group(1))


def resolve_path(document, path: str):
    current = document
    for component in path.split("."):
        if isinstance(current, list):
            current = current[int(component)]
        else:
            current = current[component]
    return current


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AppIndex(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.focusable: dict[str, dict[str, str | None]] = {}
        self.resources: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.add(element_id)
        if tag in {"button", "input", "select", "textarea", "a"} and element_id:
            self.focusable[element_id] = attributes
        for name in ("src", "href", "poster", "action"):
            value = attributes.get(name)
            if value:
                self.resources.append((tag, name, value))


class TestCandidateManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(MANIFEST_PATH)
        cls.channel = load_json(CHANNEL_PATH)
        cls.video = cls.manifest["videos"][0]

    def test_exact_one_publication_production_contract(self):
        self.assertEqual(self.manifest["schema"], "rapp-vision-production/1.0")
        self.assertEqual(self.manifest["id"], PUBLICATION_ID)
        self.assertEqual(len(self.manifest["videos"]), 1)
        self.assertEqual(self.video["id"], PUBLICATION_ID)
        self.assertNotIn("sources", self.video)
        self.assertEqual(
            self.video["production"],
            {"master": f"masters/{PUBLICATION_ID}.mkv"},
        )
        self.assertEqual(
            self.video["thumb"],
            f"thumbs/{PUBLICATION_ID}.svg",
        )
        self.assertLessEqual(self.video["duration"], 20)
        self.assertEqual(self.video["duration"], 18)
        self.assertEqual((self.video["width"], self.video["height"]), (960, 540))

    def test_compiled_channel_is_the_same_paired_publication(self):
        self.assertEqual(self.channel["schema"], "rapp-vision-channel/2.0")
        self.assertEqual(self.channel["id"], self.manifest["id"])
        self.assertEqual(len(self.channel["videos"]), 1)
        publication = self.channel["videos"][0]
        self.assertEqual(publication["id"], PUBLICATION_ID)
        self.assertEqual(
            publication["sources"],
            [
                {
                    "src": f"media/{PUBLICATION_ID}.mp4",
                    "type": "video/mp4",
                },
                {
                    "src": f"media/{PUBLICATION_ID}.webm",
                    "type": "video/webm",
                },
            ],
        )
        self.assertEqual(publication["live"], self.video["live"])
        self.assertEqual(
            VALIDATOR.validate_channel(
                self.channel,
                "https://example.test/candidate/channel.json",
                {},
            ),
            [],
        )

    def test_live_replay_is_exactly_keyboard_only(self):
        live = self.video["live"]
        self.assertEqual(live["kind"], "rapp-vision-live/1.0")
        self.assertEqual(live["duration"], 18)
        self.assertEqual(len(live["scenes"]), 1)
        scene = live["scenes"][0]
        self.assertEqual(scene["t"], 0)
        self.assertEqual(scene["dur"], 18)
        self.assertEqual(scene["ready"], {"selector": "#invoice-syn-001"})
        self.assertEqual(scene["app"], f"apps/{PUBLICATION_ID}.html")

        self.assertEqual(scene["actions"], EXPECTED_MANIFEST_ACTIONS)
        action_types = {action["do"] for action in scene["actions"]}
        self.assertEqual(action_types, {"key", "keydown", "keyup", "type"})
        codes = [action["code"] for action in scene["actions"] if action["do"] == "key"]
        for required in ("Tab", "ArrowDown", "Enter"):
            self.assertIn(required, codes)
        self.assertEqual(
            [action["text"] for action in scene["actions"] if action["do"] == "type"],
            ["-1.00"],
        )
        times = [action["at"] for action in scene["actions"]]
        self.assertEqual(times, sorted(times))
        self.assertTrue(all(0 <= value < scene["dur"] for value in times))
        for action in scene["actions"]:
            with self.subTest(action=action):
                self.assertNotIn("selector", action)
                self.assertNotIn("from", action)
                self.assertNotIn("to", action)

        source = APP_PATH.read_text(encoding="utf-8")
        index = AppIndex()
        index.feed(source)
        selector = scene["ready"]["selector"]
        self.assertRegex(selector, r"^#[A-Za-z][A-Za-z0-9_-]*$")
        self.assertIn(selector[1:], index.ids)


class TestFixtureEvidenceAndApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP_PATH.read_text(encoding="utf-8")
        cls.fixture = embedded_json(cls.source, "invoice-fixture")
        cls.contracts = embedded_json(cls.source, "contract-states")
        cls.evidence = load_json(EVIDENCE_PATH)
        cls.claims = {claim["id"]: claim for claim in cls.evidence["claims"]}

    def test_synthetic_fixture_totals_exactly_196_25(self):
        invoices = self.fixture["invoices"]
        self.assertEqual(len(invoices), 3)
        self.assertEqual(
            sum(invoice["amountCents"] for invoice in invoices),
            19625,
        )
        self.assertEqual(self.fixture["expectedTotalCents"], 19625)
        self.assertEqual(self.evidence["fixture"]["expectedTotal"], "196.25")
        self.assertTrue(self.evidence["fixture"]["synthetic"])
        self.assertEqual(
            [invoice["id"] for invoice in invoices],
            ["SYN-001", "SYN-002", "SYN-003"],
        )

    def test_embedded_snapshot_contract_matches_evidence(self):
        self.assertEqual(set(self.claims), {"positive", "rejected", "reset"})
        self.assertEqual(
            self.contracts,
            {
                claim_id: self.claims[claim_id]["expectedState"]
                for claim_id in ("positive", "rejected", "reset")
            },
        )
        for claim in self.claims.values():
            self.assertTrue(claim["claim"].strip())
            self.assertTrue(claim["actions"])
            self.assertTrue(claim["assertions"])
            for assertion in claim["assertions"]:
                self.assertEqual(
                    resolve_path(claim["expectedState"], assertion["path"]),
                    assertion["equals"],
                )
        manifest_actions = load_json(MANIFEST_PATH)["videos"][0]["live"]["scenes"][0][
            "actions"
        ]
        normalized = [
            {key: value for key, value in action.items() if key != "at"}
            for action in manifest_actions
        ]
        self.assertEqual(self.claims["positive"]["actions"], normalized[:9])
        self.assertEqual(self.claims["rejected"]["actions"], normalized[:15])
        self.assertEqual(self.claims["reset"]["actions"], normalized[15:])
        replay = self.evidence["manifestReplay"]
        self.assertEqual(replay["actionCount"], len(manifest_actions))
        self.assertEqual(replay["declaredFocusOrder"], list(EXPECTED_FOCUS_ORDER))
        self.assertEqual(
            len(replay["focusAfterEachAction"]),
            len(manifest_actions),
        )
        self.assertEqual(
            replay["checkpoints"],
            [
                {"afterAction": 8, "claim": "positive"},
                {"afterAction": 14, "claim": "rejected"},
                {"afterAction": 20, "claim": "reset"},
            ],
        )

    def test_positive_failure_and_reset_are_exact(self):
        positive = self.claims["positive"]["expectedState"]
        rejected = self.claims["rejected"]["expectedState"]
        reset = self.claims["reset"]["expectedState"]

        self.assertEqual(positive["acceptedTotal"], "196.25")
        self.assertEqual(positive["exported"]["acceptedTotal"], "196.25")
        self.assertEqual(positive["invoices"][2]["code"], "Facilities")
        self.assertTrue(all(item["status"] == "accepted" for item in positive["invoices"]))

        self.assertFalse(rejected["canExport"])
        self.assertEqual(rejected["editor"]["amountText"], "-1.00")
        self.assertEqual(rejected["error"], "Amount must be zero or greater.")
        self.assertEqual(rejected["focus"], "amount-input")
        self.assertEqual(rejected["invoices"], positive["invoices"])
        self.assertEqual(rejected["exported"], positive["exported"])

        self.assertEqual(reset["fixtureTotal"], "196.25")
        self.assertTrue(all(item["status"] == "pending" for item in reset["invoices"]))
        self.assertEqual(reset["invoices"][2]["code"], "Uncoded")
        self.assertIsNone(reset["error"])
        self.assertIsNone(reset["exported"])
        self.assertEqual(reset["focus"], "invoice-syn-001")

    def test_standalone_keyboard_focus_and_reducer_contract(self):
        index = AppIndex()
        index.feed(self.source)
        self.assertEqual(index.resources, [])
        self.assertTrue(EXPECTED_CONTROLS <= index.ids)
        self.assertTrue(EXPECTED_CONTROLS <= set(index.focusable))
        self.assertEqual(list(index.focusable), list(EXPECTED_FOCUS_ORDER))
        for element_id in EXPECTED_CONTROLS:
            with self.subTest(control=element_id):
                self.assertNotEqual(index.focusable[element_id].get("tabindex"), "-1")

        required_fragments = (
            "function initialState()",
            "function reduce(state, action)",
            'case "RESET":',
            "return initialState();",
            'data-reset="exact"',
            "window.invoiceTriage = contract;",
            "window.tinySystem = contract;",
            "const FOCUS_ORDER = Object.freeze([",
            "currentFocusOrder: () => Object.freeze([...focusableOrder()])",
            'key === "Tab"',
            'key === "ArrowDown"',
            'key === "Enter"',
            "focus({ preventScroll: true })",
            ".has-focus",
            'id="focus-readout"',
            'aria-live="polite"',
            'role="alert"',
        )
        for fragment in required_fragments:
            self.assertIn(fragment, self.source)

    def test_app_has_no_external_runtime_capability(self):
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
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.source, flags=re.IGNORECASE))


class TestRealBrowserReplay(unittest.TestCase):
    @unittest.skipUnless(
        NODE and BROWSER,
        "Node and a Chromium-family browser are required for real-browser replay",
    )
    def test_exact_manifest_actions_in_real_browser(self):
        profile = CANDIDATE / ".browser-profile-test"
        if profile.exists():
            shutil.rmtree(profile)
        self.addCleanup(lambda: shutil.rmtree(profile, ignore_errors=True))

        completed = subprocess.run(
            [
                str(NODE),
                str(VERIFY_DOM_PATH),
                "--browser",
                str(BROWSER),
                "--app",
                str(APP_PATH),
                "--evidence",
                str(EVIDENCE_PATH),
                "--manifest",
                str(MANIFEST_PATH),
                "--profile",
                str(profile),
            ],
            cwd=CANDIDATE,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if completed.returncode:
            self.fail(
                "real-browser manifest replay failed\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(
            payload,
            {
                "actionCount": 21,
                "fixtureTotal": "196.25",
                "acceptedTotal": "196.25",
                "negativeAmount": "-1.00",
                "errorFocus": "amount-input",
                "exportDisabledOnError": True,
                "resetFocus": "invoice-syn-001",
                "checkpoints": ["positive", "rejected", "reset"],
                "browserErrors": 0,
            },
        )


class TestRendererAndDelivery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delivery = load_json(DELIVERY_PATH)

    def test_renderer_is_pure_python_and_deterministic(self):
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
        self.assertEqual(RENDERER.SPEC.duration, 18)
        self.assertEqual(RENDERER.SPEC.frame_count, 216)
        self.assertEqual(
            len(RENDERER.frame_rgb(0)),
            RENDERER.SPEC.width * RENDERER.SPEC.height * 3,
        )
        samples = self.delivery["render"]["frameSamples"]
        for frame_index, expected in samples.items():
            with self.subTest(frame=frame_index):
                self.assertEqual(RENDERER.frame_digest(int(frame_index)), expected)
                self.assertEqual(RENDERER.frame_digest(int(frame_index)), expected)

    def test_svg_thumbnail_is_self_contained_and_matches_renderer(self):
        path = CANDIDATE / "thumbs" / f"{PUBLICATION_ID}.svg"
        source = path.read_text(encoding="utf-8")
        self.assertEqual(source, RENDERER.thumbnail_svg())
        root = ET.fromstring(source)
        self.assertTrue(root.tag.endswith("svg"))
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

    def test_delivery_hashes_bind_every_declared_artifact(self):
        self.assertEqual(
            self.delivery["schema"],
            "keyboard-invoice-triage-delivery/1.0",
        )
        self.assertEqual(self.delivery["publication"], PUBLICATION_ID)
        records = list(self.delivery["artifacts"].values())
        records.extend(self.delivery["sourceArtifacts"])
        paths = set()
        for record in records:
            path = CANDIDATE / record["path"]
            with self.subTest(artifact=record["path"]):
                self.assertNotIn(record["path"], paths)
                paths.add(record["path"])
                self.assertTrue(path.is_file(), path)
                self.assertEqual(path.stat().st_size, record["bytes"])
                self.assertEqual(sha256(path), record["sha256"])

    def test_lossless_master_and_paired_codecs(self):
        expected = {
            "master": ("ffv1", "bgr0"),
            "mp4": ("h264", "yuv420p"),
            "webm": ("vp9", "yuv420p"),
        }
        for kind, (codec, pixel_format) in expected.items():
            record = self.delivery["artifacts"][kind]
            with self.subTest(kind=kind):
                self.assertEqual(record["codec"], codec)
                self.assertEqual(record["pixelFormat"], pixel_format)
                self.assertEqual(record["width"], 960)
                self.assertEqual(record["height"], 540)
                self.assertEqual(record["duration"], 18)
        for kind in ("mp4", "webm"):
            record = self.delivery["artifacts"][kind]
            self.assertEqual(record["colorSpace"], "bt709")
            self.assertEqual(record["colorTransfer"], "bt709")
            self.assertEqual(record["colorPrimaries"], "bt709")
            self.assertEqual(record["colorRange"], "tv")

    @unittest.skipUnless(
        FFMPEG and FFPROBE,
        "ffmpeg and ffprobe were not found via environment, PATH, or common locations",
    )
    def test_repeated_compiler_build_is_byte_stable(self):
        scratch = CANDIDATE / ".test-rebuild"
        if scratch.exists():
            shutil.rmtree(scratch)
        self.addCleanup(lambda: shutil.rmtree(scratch, ignore_errors=True))

        source_root = scratch / "source"
        (source_root / "masters").mkdir(parents=True)
        manifest = copy.deepcopy(load_json(MANIFEST_PATH))
        (source_root / "channel.production.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        shutil.copy2(
            CANDIDATE / "masters" / f"{PUBLICATION_ID}.mkv",
            source_root / "masters" / f"{PUBLICATION_ID}.mkv",
        )

        outputs = []
        for name in ("first", "second"):
            output = scratch / name
            compilation = COMPILER.prepare_compilation(
                source_root / "channel.production.json",
                output,
            )
            COMPILER.build_compilation(
                compilation,
                ffmpeg=str(FFMPEG),
                ffprobe=str(FFPROBE),
            )
            outputs.append(output)

        self.assertEqual(
            (outputs[0] / "channel.json").read_bytes(),
            (outputs[1] / "channel.json").read_bytes(),
        )
        for extension in ("mp4", "webm"):
            relative = Path("media") / f"{PUBLICATION_ID}.{extension}"
            first = outputs[0] / relative
            second = outputs[1] / relative
            with self.subTest(extension=extension):
                self.assertEqual(sha256(first), sha256(second))
                expected = self.delivery["artifacts"][extension]["sha256"]
                self.assertEqual(sha256(first), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
