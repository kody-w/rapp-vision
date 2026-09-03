"""Release contracts for frame 0003-09, Archive Wetland Contrast."""

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
CANDIDATE = ROOT / "candidate-frame-0003" / "archive-wetland-contrast"
PUBLICATION_ID = "explore-archive-map-contrast"
APP_PATH = CANDIDATE / "apps" / f"{PUBLICATION_ID}.html"
MANIFEST_PATH = CANDIDATE / "channel.production.json"
CHANNEL_PATH = CANDIDATE / "channel.json"
EVIDENCE_PATH = CANDIDATE / "evidence.json"
DELIVERY_PATH = CANDIDATE / "delivery.json"
EXPORT_PATH = CANDIDATE / "exports" / "changed-record-ids.json"
RENDERER_PATH = CANDIDATE / "render.py"
VERIFY_DOM_PATH = CANDIDATE / "verify_dom.mjs"
THUMB_PATH = CANDIDATE / "thumbs" / f"{PUBLICATION_ID}.svg"
MASTER_PATH = CANDIDATE / "masters" / f"{PUBLICATION_ID}.mkv"
MP4_PATH = CANDIDATE / "media" / f"{PUBLICATION_ID}.mp4"
WEBM_PATH = CANDIDATE / "media" / f"{PUBLICATION_ID}.webm"
COMPILER_PATH = ROOT / "scripts" / "compile_publications.py"
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
POLICY_PATH = ROOT / "policy" / "legacy-publications.json"
EXPECTED_CHANGED_IDS = (
    "WL-002",
    "WL-005",
    "WL-009",
    "WL-012",
    "WL-016",
    "WL-020",
    "WL-023",
)
EXPECTED_EXPORT = (
    b'["WL-002","WL-005","WL-009","WL-012","WL-016","WL-020","WL-023"]\n'
)
EXPECTED_EXPORT_DIGEST = (
    "fe05f5f52ddd174f2756d865e6e1baea3c0aa5497e8052ce430d1c4c8c1761e6"
)


def load_json(path: Path):
    return json.loads(normalized_text(path))


def normalized_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


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


RENDERER = load_module("frame_0003_09_renderer", RENDERER_PATH)
COMPILER = load_module("frame_0003_09_compiler", COMPILER_PATH)
VALIDATOR = load_module("frame_0003_09_validator", VALIDATOR_PATH)


def optional_media_tool(name: str) -> Path | None:
    try:
        return Path(RENDERER.discover_executable(name))
    except RuntimeError:
        return None


def discover_browser() -> Path | None:
    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        return None
    completed = subprocess.run(
        [node, str(VERIFY_DOM_PATH), "--find-browser"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    if completed.returncode:
        return None
    candidate = Path(completed.stdout.strip().splitlines()[-1])
    return candidate.resolve() if candidate.is_file() else None


NODE = shutil.which("node") or shutil.which("nodejs")
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


class AppIndex(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.resources: list[tuple[str, str, str]] = []
        self.controls: dict[str, tuple[str, dict[str, str | None]]] = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.add(element_id)
        if element_id and tag in {"button", "input", "select", "textarea", "a"}:
            self.controls[element_id] = (tag, attributes)
        for name in ("src", "href", "poster", "action"):
            value = attributes.get(name)
            if value:
                self.resources.append((tag, name, value))


class TestCommissionAndPairedManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(MANIFEST_PATH)
        cls.channel = load_json(CHANNEL_PATH)
        cls.video = cls.manifest["videos"][0]
        cls.evidence = load_json(EVIDENCE_PATH)

    def test_exact_open_commission_and_gates_are_bound(self):
        commissions = load_json(ROOT / "commissions.json")["commissions"]
        commission = next(
            item for item in commissions
            if item["id"] == "explore-archive-map-contrast"
        )
        self.assertEqual(commission["status"], "open")
        self.assertEqual(
            commission["brief"],
            (
                "Build a spatial comparison over a synthetic 24-record archive "
                "where the viewer can isolate changed records, trigger an empty "
                "query, and return to the same view."
            ),
        )
        self.assertEqual(
            self.evidence["commission"]["criterion"],
            commission["gates"]["objective_evidence"]["criterion"],
        )
        self.assertEqual(
            self.evidence["commission"]["reset"],
            commission["gates"]["exact_reset"]["steps"],
        )

    def test_production_source_is_one_compact_lossless_publication(self):
        self.assertEqual(
            self.manifest["schema"], "rapp-vision-production/1.0"
        )
        self.assertEqual(
            self.manifest["id"],
            "candidate-frame-0003-09-archive-wetland-contrast",
        )
        self.assertEqual(len(self.manifest["videos"]), 1)
        self.assertEqual(self.video["id"], PUBLICATION_ID)
        self.assertEqual(self.video["title"], "Read the Wetland Twice")
        self.assertEqual(self.video["duration"], 22)
        self.assertGreaterEqual(self.video["duration"], 18)
        self.assertLessEqual(self.video["duration"], 24)
        self.assertEqual((self.video["width"], self.video["height"]), (960, 540))
        self.assertNotIn("sources", self.video)
        self.assertEqual(
            self.video["production"],
            {"master": f"masters/{PUBLICATION_ID}.mkv"},
        )
        self.assertEqual(
            self.video["thumb"],
            f"thumbs/{PUBLICATION_ID}.svg",
        )

    def test_compiled_channel_is_exact_and_semantically_valid(self):
        compilation = COMPILER.prepare_compilation(MANIFEST_PATH)
        self.assertEqual(
            normalized_text(CHANNEL_PATH),
            COMPILER.deterministic_json(compilation.channel),
        )
        self.assertEqual(self.channel["schema"], "rapp-vision-channel/2.0")
        publication = self.channel["videos"][0]
        self.assertNotIn("production", publication)
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
        policy = load_json(POLICY_PATH)
        self.assertEqual(
            VALIDATOR.validate_channel(
                self.channel,
                CHANNEL_PATH.resolve().as_uri(),
                policy,
            ),
            [],
        )

    def test_live_replay_is_coordinate_free_and_state_complete(self):
        live = self.video["live"]
        self.assertEqual(live["kind"], "rapp-vision-live/1.0")
        self.assertEqual(live["duration"], 22)
        self.assertEqual(len(live["scenes"]), 1)
        scene = live["scenes"][0]
        self.assertEqual(scene["t"], 0)
        self.assertEqual(scene["dur"], 22)
        self.assertEqual(
            scene["ready"],
            {"selector": "#compare-btn", "enabled": True},
        )
        self.assertEqual(scene["app"], f"apps/{PUBLICATION_ID}.html")
        actions = scene["actions"]
        self.assertEqual(len(actions), 24)
        self.assertEqual(
            {action["do"] for action in actions},
            {"scroll", "click", "type"},
        )
        self.assertEqual([action["at"] for action in actions], sorted(
            action["at"] for action in actions
        ))
        for action in actions:
            with self.subTest(action=action):
                self.assertNotIn("from", action)
                self.assertNotIn("to", action)
                self.assertGreaterEqual(action["at"], 0)
                self.assertLess(action["at"], scene["dur"])
                if action["do"] in {"click", "scroll"}:
                    self.assertRegex(
                        action["selector"],
                        r"^#[A-Za-z][A-Za-z0-9_-]*$",
                    )
                if action["do"] == "scroll":
                    self.assertEqual(action["behavior"], "auto")
                    self.assertIn(action["block"], {"start", "center"})
                if action["do"] == "type":
                    self.assertNotIn("selector", action)
        self.assertEqual(
            [action["text"] for action in actions if action["do"] == "type"],
            ["1880", "1885"],
        )


class TestFixtureEvidenceAndApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = normalized_text(APP_PATH)
        cls.fixture = embedded_json(cls.source, "wetland-fixture")
        cls.contract_states = embedded_json(cls.source, "contract-states")
        cls.evidence = load_json(EVIDENCE_PATH)
        cls.claims = {claim["id"]: claim for claim in cls.evidence["claims"]}

    def test_fixture_contains_exactly_24_unique_synthetic_records(self):
        records = self.fixture["records"]
        self.assertEqual(len(records), 24)
        self.assertEqual(records, self.evidence["fixture"]["records"])
        ids = [record["id"] for record in records]
        self.assertEqual(ids, [f"WL-{index:03d}" for index in range(1, 25)])
        self.assertEqual(len(ids), len(set(ids)))
        extent = self.fixture["extent"]
        for record in records:
            self.assertGreaterEqual(record["x"], extent["minX"])
            self.assertLessEqual(record["x"], extent["maxX"])
            self.assertGreaterEqual(record["y"], extent["minY"])
            self.assertLessEqual(record["y"], extent["maxY"])
            self.assertEqual(set(record["snapshots"]), {"1990", "2020"})
        self.assertEqual(self.fixture["availableYears"], [1990, 2020])
        self.assertEqual(self.fixture["impossibleRange"], [1880, 1885])
        self.assertTrue(self.evidence["fixture"]["synthetic"])

    def test_independent_comparison_yields_exactly_seven_sorted_ids(self):
        changed = tuple(
            sorted(
                record["id"]
                for record in self.fixture["records"]
                if record["snapshots"]["1990"] != record["snapshots"]["2020"]
            )
        )
        self.assertEqual(changed, EXPECTED_CHANGED_IDS)
        self.assertEqual(
            tuple(self.fixture["expectedChangedIds"]),
            EXPECTED_CHANGED_IDS,
        )
        self.assertEqual(
            tuple(self.evidence["objective"]["changedIds"]),
            EXPECTED_CHANGED_IDS,
        )
        self.assertEqual(self.evidence["objective"]["recordCount"], 24)
        self.assertEqual(self.evidence["objective"]["changedCount"], 7)

    def test_canonical_export_bytes_and_digest_are_exact(self):
        normalized_export = normalized_text(EXPORT_PATH).encode("utf-8")
        self.assertEqual(normalized_export, EXPECTED_EXPORT)
        self.assertEqual(
            hashlib.sha256(EXPECTED_EXPORT).hexdigest(),
            EXPECTED_EXPORT_DIGEST,
        )
        self.assertEqual(
            hashlib.sha256(normalized_export).hexdigest(),
            EXPECTED_EXPORT_DIGEST,
        )
        self.assertEqual(
            self.fixture["exportText"].encode("utf-8"),
            EXPECTED_EXPORT,
        )
        self.assertEqual(self.fixture["exportSha256"], EXPECTED_EXPORT_DIGEST)
        self.assertEqual(
            self.evidence["fixture"]["export"]["sha256"],
            EXPECTED_EXPORT_DIGEST,
        )
        self.assertEqual(
            self.evidence["fixture"]["export"]["text"].encode("utf-8"),
            EXPECTED_EXPORT,
        )

    def test_evidence_snapshots_bind_positive_failure_and_exact_reset(self):
        self.assertEqual(set(self.claims), {"positive", "failure", "reset"})
        self.assertEqual(
            self.contract_states,
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

        positive = self.claims["positive"]["expectedState"]
        failure = self.claims["failure"]["expectedState"]
        reset = self.claims["reset"]["expectedState"]
        self.assertEqual(positive["visibleRecordIds"], list(EXPECTED_CHANGED_IDS))
        self.assertEqual(positive["focus"], "WL-012")
        self.assertEqual(positive["filter"], "changed")
        self.assertEqual(positive["view"], {"panX": 40, "panY": 0, "zoom": 1.25})
        self.assertEqual(positive["export"]["status"], "exported")

        self.assertEqual(failure["years"], {"from": 1880, "to": 1885})
        self.assertEqual(failure["comparison"]["status"], "rejected-empty")
        self.assertIsNone(failure["comparison"]["queryResultCount"])
        self.assertNotEqual(failure["comparison"]["status"], "success")
        self.assertEqual(failure["changedCount"], 7)
        self.assertEqual(failure["export"]["ids"], positive["export"]["ids"])
        self.assertEqual(
            failure["export"]["digest"],
            positive["export"]["digest"],
        )
        self.assertEqual(failure["export"]["status"], "preserved")

        self.assertEqual(reset["totalRecords"], 24)
        self.assertEqual(reset["visibleCount"], 24)
        self.assertEqual(reset["years"], {"from": 1990, "to": 2020})
        self.assertEqual(reset["changedCount"], 7)
        self.assertEqual(reset["filter"], "all")
        self.assertIsNone(reset["focus"])
        self.assertEqual(reset["view"], {"panX": 0, "panY": 0, "zoom": 1})
        self.assertEqual(reset["export"]["digest"], EXPECTED_EXPORT_DIGEST)

    def test_manifest_replay_metadata_matches_manifest_actions(self):
        replay = self.evidence["manifestReplay"]
        actions = load_json(MANIFEST_PATH)["videos"][0]["live"]["scenes"][0][
            "actions"
        ]
        self.assertEqual(replay["actionCount"], len(actions))
        self.assertTrue(replay["coordinateFree"])
        self.assertEqual(replay["framingAction"], "scroll")
        self.assertEqual(
            replay["scrollSelectors"],
            [
                action["selector"]
                for action in actions
                if action["do"] == "scroll"
            ],
        )
        self.assertEqual(
            replay["checkpoints"],
            [
                {
                    "afterAction": 11,
                    "claim": "positive",
                    "selector": "#export-output",
                },
                {
                    "afterAction": 20,
                    "claim": "failure",
                    "selector": "#query-error",
                },
                {
                    "afterAction": 23,
                    "claim": "reset",
                    "selector": "#status-message",
                },
            ],
        )
        self.assertEqual(
            replay["viewports"],
            [
                {"name": "desktop", "width": 1120, "height": 900},
                {"name": "mobile-390", "width": 390, "height": 844},
            ],
        )

    def test_live_app_is_single_file_offline_and_explorable(self):
        index = AppIndex()
        index.feed(self.source)
        self.assertEqual(index.resources, [])
        required_ids = {
            "compare-btn",
            "filter-changed-btn",
            "filter-all-btn",
            "export-btn",
            "restore-btn",
            "from-year",
            "to-year",
            "query-error",
            "status-message",
            "export-output",
            "map-window",
            "view-readout",
            "contract-states",
            "wetland-fixture",
            "record-wl-012",
            "record-wl-024",
            "pan-west-btn",
            "pan-east-btn",
            "pan-north-btn",
            "pan-south-btn",
            "zoom-in-btn",
            "zoom-out-btn",
        }
        required_ids.update(f"record-wl-{index:03d}" for index in range(1, 25))
        self.assertTrue(required_ids <= index.ids)
        self.assertTrue(
            {
                "compare-btn",
                "filter-changed-btn",
                "filter-all-btn",
                "export-btn",
                "restore-btn",
                "from-year",
                "to-year",
                "record-wl-012",
                "record-wl-024",
                "pan-east-btn",
                "zoom-in-btn",
            }
            <= set(index.controls)
        )
        for fragment in (
            '<meta name="candidate-frame-reset" content="exact">',
            "function initialState()",
            "function reduce(state, action)",
            "function snapshot(value = state)",
            "function changedIds(fromYear, toYear)",
            "function sha256Ascii(text)",
            'case "COMPARE":',
            'case "RESET":',
            "return initialState();",
            "window.archiveWetlandMap = contract;",
            "window.tinySystem = contract;",
            "queryResultCount: null",
            "Canonical export preserved.",
            'data-reset="exact"',
            "@media (max-width: 520px)",
            "overflow-x: clip",
        ):
            self.assertIn(fragment, self.source)
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
            with self.subTest(pattern=pattern):
                self.assertIsNone(
                    re.search(pattern, self.source, flags=re.IGNORECASE),
                    pattern,
                )

    def test_rights_privacy_and_secret_attestations_are_explicit(self):
        attestations = self.evidence["attestations"]
        self.assertTrue(attestations["rights"])
        self.assertTrue(attestations["privacy"])
        self.assertTrue(attestations["noSecrets"])
        self.assertFalse(attestations["externalRuntimeResources"])
        self.assertFalse(attestations["networkRequests"])
        self.assertFalse(attestations["copiedImagery"])
        combined = (attestations["rights"] + " " + attestations["privacy"]).lower()
        for phrase in ("synthetic", "no people", "no map tiles"):
            if phrase == "no map tiles":
                self.assertIn("no map tiles", normalized_text(CANDIDATE / "README.md").lower())
            else:
                self.assertIn(phrase, combined)


class TestRendererMediaAndDelivery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delivery = load_json(DELIVERY_PATH)

    def test_renderer_is_standard_library_only_and_deterministic(self):
        tree = ast.parse(normalized_text(RENDERER_PATH))
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
        self.assertEqual(RENDERER.SPEC.duration, 22)
        self.assertEqual(RENDERER.SPEC.frame_count, 264)
        self.assertEqual(RENDERER.SPEC.fps, 12)
        self.assertEqual(
            len(RENDERER.frame_rgb(0)),
            RENDERER.SPEC.width * RENDERER.SPEC.height * 3,
        )
        for frame_index, expected in self.delivery["render"]["frameSamples"].items():
            with self.subTest(frame=frame_index):
                self.assertEqual(
                    RENDERER.frame_digest(int(frame_index)),
                    expected,
                )
                self.assertEqual(
                    RENDERER.frame_digest(int(frame_index)),
                    expected,
                )

    def test_thumbnail_is_renderer_exact_and_has_no_active_content(self):
        source = normalized_text(THUMB_PATH)
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

    def test_delivery_hashes_bind_all_source_and_media_artifacts(self):
        self.assertEqual(
            self.delivery["schema"],
            "archive-wetland-contrast-delivery/1.0",
        )
        self.assertEqual(
            self.delivery["channel"],
            "candidate-frame-0003-09-archive-wetland-contrast",
        )
        self.assertEqual(self.delivery["publication"], PUBLICATION_ID)
        records = list(self.delivery["artifacts"].values())
        records.extend(self.delivery["sourceArtifacts"])
        observed = set()
        for record in records:
            with self.subTest(artifact=record["path"]):
                self.assertNotIn(record["path"], observed)
                observed.add(record["path"])
                path = CANDIDATE / record["path"]
                self.assertTrue(path.is_file(), path)
                self.assertEqual(path.stat().st_size, record["bytes"])
                self.assertEqual(sha256(path), record["sha256"])
        self.assertEqual(
            observed,
            {
                "masters/explore-archive-map-contrast.mkv",
                "media/explore-archive-map-contrast.mp4",
                "media/explore-archive-map-contrast.webm",
                *RENDERER.SOURCE_ARTIFACTS,
            },
        )

    def test_recorded_codec_probes_are_release_grade(self):
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
                self.assertEqual(record["duration"], 22)
        for kind in ("mp4", "webm"):
            record = self.delivery["artifacts"][kind]
            self.assertEqual(record["colorSpace"], "bt709")
            self.assertEqual(record["colorTransfer"], "bt709")
            self.assertEqual(record["colorPrimaries"], "bt709")
            self.assertEqual(record["colorRange"], "tv")

    @unittest.skipUnless(FFPROBE, "ffprobe not found via RAPP_FFPROBE or portable locations")
    def test_actual_media_codec_probes_match_delivery(self):
        for kind, path in (
            ("master", MASTER_PATH),
            ("mp4", MP4_PATH),
            ("webm", WEBM_PATH),
        ):
            with self.subTest(kind=kind):
                self.assertEqual(
                    RENDERER._probe(path, str(FFPROBE)),
                    {
                        key: value
                        for key, value in self.delivery["artifacts"][kind].items()
                        if key
                        not in {
                            "path",
                            "sha256",
                            "bytes",
                        }
                    },
                )
        self.assertEqual(
            VALIDATOR.ffprobe_local_media(
                load_json(CHANNEL_PATH),
                CHANNEL_PATH,
                executable=str(FFPROBE),
            ),
            [],
        )

    @unittest.skipUnless(
        FFMPEG and FFPROBE,
        "ffmpeg/ffprobe not found via RAPP_FFMPEG, RAPP_FFPROBE, or portable locations",
    )
    def test_clean_rebuild_is_byte_identical_to_committed_bundle(self):
        scratch = CANDIDATE / ".frame-0003-09-rebuild"
        shutil.rmtree(scratch, ignore_errors=True)
        self.addCleanup(lambda: shutil.rmtree(scratch, ignore_errors=True))
        scratch.mkdir(parents=True)
        shutil.copy2(MANIFEST_PATH, scratch / "channel.production.json")

        rebuilt_master, rebuilt_thumb = RENDERER.render(
            scratch,
            str(FFMPEG),
        )
        compilation = COMPILER.prepare_compilation(
            scratch / "channel.production.json",
            scratch,
        )
        COMPILER.build_compilation(
            compilation,
            ffmpeg=str(FFMPEG),
            ffprobe=str(FFPROBE),
        )

        comparisons = (
            (MASTER_PATH, rebuilt_master),
            (THUMB_PATH, rebuilt_thumb),
            (CHANNEL_PATH, scratch / "channel.json"),
            (MP4_PATH, scratch / "media" / f"{PUBLICATION_ID}.mp4"),
            (WEBM_PATH, scratch / "media" / f"{PUBLICATION_ID}.webm"),
        )
        for committed, rebuilt in comparisons:
            with self.subTest(artifact=committed.name):
                self.assertEqual(committed.read_bytes(), rebuilt.read_bytes())
                self.assertEqual(sha256(committed), sha256(rebuilt))


class TestExecutableReleaseChecks(unittest.TestCase):
    def test_compiler_check_command_passes(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(COMPILER_PATH),
                "check",
                str(MANIFEST_PATH),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if completed.returncode:
            self.fail(
                "compiler check failed\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )

    @unittest.skipUnless(
        NODE and BROWSER,
        "Node/browser not found via RAPP_BROWSER or portable locations",
    )
    def test_real_browser_replays_desktop_mobile_and_takeover(self):
        profile = CANDIDATE / ".frame-0003-09-browser-test"
        shutil.rmtree(profile, ignore_errors=True)
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
            encoding="utf-8",
            timeout=120,
        )
        if completed.returncode:
            self.fail(
                "real-browser replay failed\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertRegex(payload.pop("browser"), r"(Chrome|Chromium|Edge|Edg)/")
        self.assertEqual(
            payload,
            {
                "actionCount": 24,
                "viewports": ["desktop", "mobile-390"],
                "recordCount": 24,
                "changedCount": 7,
                "changedIds": list(EXPECTED_CHANGED_IDS),
                "digest": EXPECTED_EXPORT_DIGEST,
                "failureStatus": "rejected-empty",
                "failureResultCount": None,
                "failureExportStatus": "preserved",
                "resetVisibleCount": 24,
                "resetFocus": None,
                "resetView": {"panX": 0, "panY": 0, "zoom": 1},
                "takeover": {
                    "focus": "WL-024",
                    "visibleCount": 24,
                    "view": {"panX": 0, "panY": -40, "zoom": 0.75},
                },
                "browserErrors": 0,
            },
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
