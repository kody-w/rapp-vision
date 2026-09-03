"""Focused contracts for candidate frame 0003-03, Island Herd Threshold."""

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
from pathlib import Path, PurePosixPath
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = (
    ROOT / "candidate-frame-0003" / "ecosystem-island-threshold"
)
PUBLICATION_ID = "ecosystem-island-threshold"
APP_PATH = CANDIDATE / "apps" / f"{PUBLICATION_ID}.html"
MANIFEST_PATH = CANDIDATE / "channel.production.json"
CHANNEL_PATH = CANDIDATE / "channel.json"
EVIDENCE_PATH = CANDIDATE / "evidence.json"
DELIVERY_PATH = CANDIDATE / "delivery.json"
FIXTURE_EXPORT_PATH = CANDIDATE / "exports" / "fixture-series.json"
SNAPSHOT_PATH = CANDIDATE / "snapshots" / "canonical-states.json"
THUMB_PATH = CANDIDATE / "thumbs" / f"{PUBLICATION_ID}.svg"
MASTER_PATH = CANDIDATE / "masters" / f"{PUBLICATION_ID}.mkv"
MP4_PATH = CANDIDATE / "media" / f"{PUBLICATION_ID}.mp4"
WEBM_PATH = CANDIDATE / "media" / f"{PUBLICATION_ID}.webm"
RENDERER_PATH = CANDIDATE / "render.py"
VERIFY_DOM_PATH = CANDIDATE / "verify_dom.mjs"
README_PATH = CANDIDATE / "README.md"
COMPILER_PATH = ROOT / "scripts" / "compile_publications.py"
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
COMMISSIONS_PATH = ROOT / "commissions.json"
PRODUCTION_SCHEMA_PATH = ROOT / "channel.production.schema.json"
CHANNEL_SCHEMA_PATH = ROOT / "channel.schema.json"
NODE = shutil.which("node")

EXPECTED_CLICK_SELECTORS = [
    "#predict-band-btn",
    "#run-btn",
    "#inspect-trace-btn",
    "#rate-60-btn",
    "#predict-collapse-btn",
    "#speed-2-btn",
    "#run-btn",
    "#reset-btn",
]
EXPECTED_SCROLL_SELECTORS = [
    "#predict-band-btn",
    "#run-btn",
    "#stable-result",
    "#stable-result",
    "#rate-60-btn",
    "#predict-collapse-btn",
    "#speed-2-btn",
    "#run-btn",
    "#collapse-result",
    "#reset-btn",
    "#reset-proof",
]
REQUIRED_IDS = {
    "app-ready",
    "prediction-panel",
    "grazing-input",
    "grazing-output",
    "rate-24-btn",
    "rate-45-btn",
    "rate-60-btn",
    "predict-band-btn",
    "predict-collapse-btn",
    "speed-1-btn",
    "speed-2-btn",
    "speed-4-btn",
    "run-btn",
    "reset-btn",
    "status-message",
    "reset-proof",
    "population-chart",
    "trace-path",
    "stable-result",
    "collapse-result",
    "inspect-trace-btn",
    "export-series-btn",
    "series-export",
    "model-contract",
    "fixture-expectations",
}
FRAME_SAMPLES = {
    0: "0122320a8deb0d7d2da75390675d57f4c855b0c4b7387d70944f773d16e0bd37",
    48: "d3fac41b7465aba0797ca4c2ef086702fc7989f509a6ed85b389f8e4044318b9",
    120: "afbd69d2376eec53e1f0390488f4fba5fc5df0ba883342443444ed31693e5aa1",
    156: "e6c94da9559b4520ed3c1a7c6bdd29e58c9d22919a304e6aae0ae15c1c4898e6",
    221: "fa190466336dbfe6a7d6e5669264d11d815172566e25577baf9ba91b19360c5c",
    263: "c41e6ce3bf01b5dd296e335e5b4e82ddb25ba916df38c75571d7636d109889d1",
}
EXPECTED_EVIDENCE_BINDINGS = {
    "README.md",
    "apps/ecosystem-island-threshold.html",
    "channel.production.json",
    "channel.json",
    "exports/fixture-series.json",
    "masters/ecosystem-island-threshold.mkv",
    "media/ecosystem-island-threshold.mp4",
    "media/ecosystem-island-threshold.webm",
    "render.py",
    "snapshots/canonical-states.json",
    "thumbs/ecosystem-island-threshold.svg",
    "verify_dom.mjs",
}


def independent_xorshift32(value: int) -> int:
    value &= 0xFFFFFFFF
    value ^= (value << 13) & 0xFFFFFFFF
    value ^= value >> 17
    value ^= (value << 5) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def independent_support(resources_milli: int) -> int:
    if resources_milli <= 90_000:
        return 8_000
    if resources_milli >= 120_000:
        return 112_000
    distance = resources_milli - 90_000
    return 8_000 + 104_000 * distance * distance // (30_000 * 30_000)


def independent_simulate(
    rate_milli: int,
    *,
    seed: int = 31415,
    ticks: int = 600,
) -> list[list[int]]:
    point = [
        0,
        104_000,
        146_000,
        independent_support(146_000),
        0,
        seed,
    ]
    points = [point.copy()]
    for tick in range(1, ticks + 1):
        random_state = independent_xorshift32(point[5])
        weather_milli = ((random_state & 1023) - 512) * 550 // 1024
        regrowth_milli = (180_000 - point[2]) * 40 // 1000
        grazing_loss_milli = rate_milli * 6400 // 1000
        resources_milli = max(
            0,
            min(
                180_000,
                point[2] + regrowth_milli - grazing_loss_milli + weather_milli,
            ),
        )
        support_milli = independent_support(resources_milli)
        gap = support_milli - point[1]
        movement = abs(gap) * 35 // 1000
        if gap and movement == 0:
            movement = 1
        if gap < 0:
            movement = -movement
        point = [
            tick,
            max(0, point[1] + movement),
            resources_milli,
            support_milli,
            weather_milli,
            random_state,
        ]
        points.append(point.copy())
    return points


def independent_digest(points: list[list[int]]) -> str:
    value = 0x811C9DC5
    for point in points:
        for character in (":".join(str(item) for item in point) + ";"):
            value ^= ord(character)
            value = (value * 0x01000193) & 0xFFFFFFFF
    return f"{value:08x}"


def independent_display(value: int) -> int | float:
    return value // 1000 if value % 1000 == 0 else value / 1000


def independent_export(points: list[list[int]]) -> list[dict[str, int | float]]:
    return [
        {
            "tick": point[0],
            "population": independent_display(point[1]),
            "populationMilli": point[1],
            "resources": independent_display(point[2]),
            "resourcesMilli": point[2],
            "support": independent_display(point[3]),
            "supportMilli": point[3],
            "weatherMilli": point[4],
            "randomState": point[5],
        }
        for point in points
    ]


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def normalized_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def load_json(path: Path):
    return json.loads(normalized_text(path))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RENDERER = load_module("frame_0003_03_renderer", RENDERER_PATH)
COMPILER = load_module("frame_0003_03_compiler", COMPILER_PATH)
VALIDATOR = load_module("frame_0003_03_validator", VALIDATOR_PATH)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_path(document, path: str):
    current = document
    for component in path.split("."):
        if isinstance(current, list):
            current = current[int(component)]
        else:
            current = current[component]
    return current


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


class AppIndex(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.resources: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        for name in ("src", "href", "poster", "action"):
            value = attributes.get(name)
            if value:
                self.resources.append((tag, name, value))


def executable(value: str | None) -> str | None:
    if not value:
        return None
    candidate = Path(os.path.expandvars(value.strip().strip('"'))).expanduser()
    if candidate.is_absolute() or candidate.parent != Path("."):
        return str(candidate.resolve()) if candidate.is_file() else None
    return shutil.which(value)


def discover_browser() -> str | None:
    for variable in (
        "RAPP_BROWSER",
        "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH",
        "EDGE_BIN",
        "CHROME_BIN",
        "CHROMIUM_BIN",
        "BROWSER",
    ):
        resolved = executable(os.environ.get(variable))
        if resolved and re.search(
            r"(chrome|chromium|edge|brave)", Path(resolved).name, re.IGNORECASE
        ):
            return resolved
    for name in (
        "msedge",
        "microsoft-edge",
        "microsoft-edge-stable",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "brave-browser",
    ):
        resolved = shutil.which(name)
        if resolved:
            return resolved
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
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
                Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
            )
        )
    else:
        candidates.extend(
            Path(value)
            for value in (
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/microsoft-edge",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/brave-browser",
                "/snap/bin/chromium",
            )
        )
    return next(
        (str(path.resolve()) for path in candidates if path.is_file()),
        None,
    )


def optional_media_tool(name: str) -> str | None:
    try:
        return RENDERER.resolve_binary(name)
    except RuntimeError:
        return None


BROWSER = discover_browser()
FFMPEG = optional_media_tool("ffmpeg")
FFPROBE = optional_media_tool("ffprobe")


def require_tools(test: unittest.TestCase, **tools: str | None) -> None:
    missing = [name for name, value in tools.items() if not value]
    if missing:
        test.skipTest("tool(s) not found: " + ", ".join(missing))


class TestFrame000303AlwaysOn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(MANIFEST_PATH)
        cls.channel = load_json(CHANNEL_PATH)
        cls.evidence = load_json(EVIDENCE_PATH)
        cls.delivery = load_json(DELIVERY_PATH)
        cls.export = load_json(FIXTURE_EXPORT_PATH)
        cls.snapshots = load_json(SNAPSHOT_PATH)
        cls.source = normalized_text(APP_PATH)
        cls.video = cls.manifest["videos"][0]
        cls.claims = {
            claim["id"]: claim for claim in cls.evidence["claims"]
        }
        cls.fixtures = {
            fixture["id"]: fixture for fixture in cls.evidence["fixtures"]
        }

    def test_commission_gates_and_schema_sources_are_bound(self):
        commissions = load_json(COMMISSIONS_PATH)
        commission = next(
            item
            for item in commissions["commissions"]
            if item["id"] == "explore-ecosystem-threshold"
        )
        gates = commission["gates"]
        self.assertTrue(gates["paired_delivery"]["mp4"])
        self.assertTrue(gates["paired_delivery"]["webm"])
        self.assertTrue(gates["paired_delivery"]["live"])
        self.assertTrue(gates["paired_delivery"]["same_publication"])
        self.assertIn("seed 31415", gates["objective_evidence"]["criterion"])
        self.assertIn("0.24", gates["objective_evidence"]["criterion"])
        self.assertIn("0.60", gates["objective_evidence"]["criterion"])
        self.assertTrue(gates["exact_reset"]["required"])

        production_schema = load_json(PRODUCTION_SCHEMA_PATH)
        channel_schema = load_json(CHANNEL_SCHEMA_PATH)
        self.assertEqual(
            production_schema["properties"]["schema"]["const"],
            "rapp-vision-production/1.0",
        )
        self.assertEqual(
            channel_schema["properties"]["schema"]["const"],
            "rapp-vision-channel/2.0",
        )
        self.assertEqual(
            channel_schema["$defs"]["publication"]["properties"]["live"][
                "properties"
            ]["kind"]["const"],
            "rapp-vision-live/1.0",
        )

    def test_production_and_compiled_channel_are_one_paired_publication(self):
        self.assertEqual(self.manifest["schema"], "rapp-vision-production/1.0")
        self.assertEqual(self.manifest["id"], "candidate-frame-0003-03")
        self.assertEqual(len(self.manifest["videos"]), 1)
        self.assertEqual(self.video["id"], PUBLICATION_ID)
        self.assertEqual(self.video["title"], "Will the Island Herd Hold?")
        self.assertEqual(self.video["duration"], 22)
        self.assertGreaterEqual(self.video["duration"], 18)
        self.assertLessEqual(self.video["duration"], 24)
        self.assertEqual((self.video["width"], self.video["height"]), (960, 540))
        self.assertEqual(
            self.video["production"],
            {"master": f"masters/{PUBLICATION_ID}.mkv"},
        )
        self.assertEqual(
            self.video["thumb"], f"thumbs/{PUBLICATION_ID}.svg"
        )
        self.assertNotIn("sources", self.video)
        self.assertEqual(self.video["live"]["kind"], "rapp-vision-live/1.0")

        compilation = COMPILER.prepare_compilation(MANIFEST_PATH)
        self.assertEqual(self.channel, compilation.channel)
        self.assertEqual(
            self.channel["videos"][0]["sources"],
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
        self.assertEqual(self.channel["videos"][0]["live"], self.video["live"])
        self.assertEqual(
            VALIDATOR.validate_channel(
                self.channel,
                "https://example.test/candidate-frame-0003/channel.json",
                {},
            ),
            [],
        )

    def test_prediction_first_manifest_replays_success_collapse_and_reset(self):
        scene = self.video["live"]["scenes"][0]
        self.assertEqual(scene["t"], 0)
        self.assertEqual(scene["dur"], 22)
        self.assertEqual(
            scene["ready"],
            {"enabled": True, "selector": "#predict-band-btn"},
        )
        actions = scene["actions"]
        self.assertEqual(
            [
                action["selector"]
                for action in actions
                if action["do"] == "click"
            ],
            EXPECTED_CLICK_SELECTORS,
        )
        self.assertEqual(
            [
                action["selector"]
                for action in actions
                if action["do"] == "scroll"
            ],
            EXPECTED_SCROLL_SELECTORS,
        )
        self.assertLess(
            EXPECTED_CLICK_SELECTORS.index("#predict-band-btn"),
            EXPECTED_CLICK_SELECTORS.index("#run-btn"),
        )
        self.assertEqual(
            {action["do"] for action in actions},
            {"click", "scroll"},
        )
        self.assertEqual(
            [action["at"] for action in actions],
            sorted(action["at"] for action in actions),
        )
        for action in actions:
            self.assertNotIn("from", action)
            self.assertNotIn("to", action)
            self.assertLess(action["at"], scene["dur"])
            self.assertRegex(action["selector"], r"^#[A-Za-z][A-Za-z0-9_-]*$")
            if action["do"] == "scroll":
                self.assertEqual(action["block"], "start")
                self.assertEqual(action["behavior"], "auto")
        self.assertEqual(
            self.evidence["manifestReplay"]["checkpoints"],
            [
                {
                    "afterAction": 6,
                    "claim": "stable",
                    "selector": "#stable-result",
                },
                {
                    "afterAction": 15,
                    "claim": "collapse",
                    "selector": "#collapse-result",
                },
                {
                    "afterAction": 18,
                    "claim": "reset",
                    "selector": "#reset-proof",
                },
            ],
        )

    def test_seeded_model_exactly_meets_both_fixture_thresholds(self):
        stable_points = RENDERER.simulate(0.24)
        collapse_points = RENDERER.simulate(0.60)
        stable_oracle = independent_simulate(240)
        collapse_oracle = independent_simulate(600)
        self.assertEqual(len(stable_points), 601)
        self.assertEqual(len(collapse_points), 601)
        self.assertEqual(
            [point.compact() for point in stable_points],
            stable_oracle,
        )
        self.assertEqual(
            [point.compact() for point in collapse_points],
            collapse_oracle,
        )
        self.assertEqual(stable_points[0], RENDERER.initial_point())
        self.assertEqual(
            RENDERER.xorshift32(31415), stable_points[1].random_state
        )
        self.assertNotEqual(
            stable_points[1].weather_milli,
            stable_points[2].weather_milli,
        )

        stable_final = stable_points[-1]
        self.assertEqual(stable_final.tick, 600)
        self.assertEqual(stable_final.population_milli, 112000)
        self.assertEqual(stable_final.resources_milli, 141688)
        self.assertTrue(
            all(
                80000 <= point.population_milli <= 120000
                for point in stable_points
            )
        )
        self.assertIsNone(RENDERER.collapse_crossing(stable_points))

        crossing = RENDERER.collapse_crossing(collapse_points)
        self.assertEqual(crossing, 134)
        self.assertLess(crossing, 300)
        self.assertGreaterEqual(
            collapse_points[crossing - 1].population_milli, 10000
        )
        self.assertLess(collapse_points[crossing].population_milli, 10000)
        self.assertEqual(collapse_points[-1].population_milli, 8000)
        self.assertEqual(collapse_points[-1].resources_milli, 84088)
        self.assertEqual(RENDERER.trace_digest(stable_points), "81d44b16")
        self.assertEqual(RENDERER.trace_digest(collapse_points), "8bb46765")
        self.assertEqual(independent_digest(stable_oracle), "81d44b16")
        self.assertEqual(independent_digest(collapse_oracle), "8bb46765")

    def test_arbitrary_rates_seeds_and_invalid_inputs_are_behavioral(self):
        rate_451 = RENDERER.simulate(0.451)
        seed_one = RENDERER.simulate(0.45, seed=1)
        seed_two = RENDERER.simulate(0.45, seed=2)
        self.assertEqual(
            [point.compact() for point in rate_451],
            independent_simulate(451),
        )
        self.assertEqual(
            [point.compact() for point in seed_one],
            independent_simulate(450, seed=1),
        )
        self.assertEqual(
            [point.compact() for point in seed_two],
            independent_simulate(450, seed=2),
        )
        self.assertNotEqual(
            RENDERER.trace_digest(rate_451),
            RENDERER.trace_digest(RENDERER.simulate(0.24)),
        )
        self.assertNotEqual(
            RENDERER.trace_digest(seed_one),
            RENDERER.trace_digest(seed_two),
        )
        self.assertEqual(RENDERER.simulate(0.75)[-1].resources_milli, 60_088)
        self.assertEqual(RENDERER.simulate(0.00)[-1].resources_milli, 180_000)

        invalid_calls = (
            lambda: RENDERER.simulate(-0.001),
            lambda: RENDERER.simulate(0.751),
            lambda: RENDERER.simulate(0.2405),
            lambda: RENDERER.simulate(float("nan")),
            lambda: RENDERER.simulate(float("inf")),
            lambda: RENDERER.simulate(True),
            lambda: RENDERER.simulate(0.24, -1),
            lambda: RENDERER.simulate(0.24, 600.5),
            lambda: RENDERER.simulate(0.24, 601),
            lambda: RENDERER.simulate(0.24, seed=0),
            lambda: RENDERER.simulate(0.24, seed=0x1_0000_0000),
            lambda: RENDERER.simulate(240.0, rate_is_milli=True),
        )
        for call in invalid_calls:
            with self.subTest(call=call):
                with self.assertRaises(ValueError):
                    call()

    def test_evidence_exports_every_tick_and_exact_final_measurements(self):
        self.assertEqual(
            self.evidence["schema"],
            "ecosystem-island-threshold-evidence/1.0",
        )
        self.assertEqual(
            self.evidence["commission"]["id"], "explore-ecosystem-threshold"
        )
        self.assertEqual(
            self.evidence["model"], RENDERER.model_contract()
        )
        self.assertEqual(set(self.fixtures), {"stable-band", "collapse"})
        for fixture_id, rate in (("stable-band", 0.24), ("collapse", 0.60)):
            points = RENDERER.simulate(rate)
            oracle = independent_simulate(round(rate * 1000))
            fixture = self.fixtures[fixture_id]
            exported = next(
                item for item in self.export["fixtures"] if item["id"] == fixture_id
            )
            self.assertEqual(fixture["series"], [point.compact() for point in points])
            self.assertEqual(fixture["series"], oracle)
            self.assertEqual(len(fixture["series"]), 601)
            self.assertEqual(
                exported["series"], [point.export() for point in points]
            )
            self.assertEqual(exported["series"], independent_export(oracle))
            self.assertEqual(exported["traceDigest"], fixture["traceDigest"])
            self.assertEqual(exported["traceDigest"], independent_digest(oracle))
            self.assertEqual(
                exported["collapseCrossingTick"],
                fixture["collapseCrossingTick"],
            )
        self.assertEqual(
            self.fixtures["stable-band"]["final"]["population"], 112
        )
        self.assertEqual(
            self.fixtures["collapse"]["collapseCrossingTick"], 134
        )
        self.assertEqual(self.fixtures["collapse"]["final"]["population"], 8)

    def test_canonical_window_states_and_exact_reset_are_self_checking(self):
        self.assertEqual(
            self.snapshots, RENDERER.canonical_states_document()
        )
        self.assertEqual(set(self.claims), {"stable", "collapse", "reset"})
        self.assertEqual(
            self.claims["reset"]["expectedState"],
            self.snapshots["opening"],
        )
        self.assertEqual(self.snapshots["reset"], self.snapshots["opening"])
        reset = self.snapshots["reset"]
        self.assertEqual(
            reset,
            {
                "seed": 31415,
                "grazingRate": 0.24,
                "speed": 1,
                "initialPopulation": 104,
                "initialResources": 146,
                "tick": 0,
                "population": 104,
                "resources": 146,
                "support": 112,
                "prediction": None,
                "predictionRevision": 0,
                "predictionHistory": [],
                "traceLength": 0,
                "traceDigest": None,
                "collapseCrossingTick": None,
                "outcome": None,
                "running": False,
                "status": "ready",
                "message": "Choose what happens before the trace is revealed.",
                "inspectionOpen": False,
            },
        )
        for claim in self.claims.values():
            for assertion in claim["assertions"]:
                self.assertEqual(
                    resolve_path(
                        claim["expectedState"], assertion["path"]
                    ),
                    assertion["equals"],
                )

    def test_live_app_is_standalone_responsive_and_exposes_the_same_model(self):
        index = AppIndex()
        index.feed(self.source)
        self.assertEqual(index.resources, [])
        self.assertTrue(REQUIRED_IDS <= index.ids)
        self.assertEqual(
            embedded_json(self.source, "model-contract"),
            {
                key: value
                for key, value in RENDERER.model_contract().items()
                if key != "rules"
            },
        )
        expectations = embedded_json(self.source, "fixture-expectations")
        self.assertEqual(expectations["stable"]["traceDigest"], "81d44b16")
        self.assertEqual(
            expectations["collapse"]["collapseCrossingTick"], 134
        )
        contract = embedded_json(self.source, "model-contract")
        self.assertEqual(contract["limits"]["minimumSeed"], 1)
        self.assertEqual(contract["limits"]["maximumSeed"], 0xFFFFFFFF)
        for fragment in (
            "Make a prediction before the deterministic trace appears.",
            'data-reset="exact"',
            "Reset ecosystem",
            "Prepare full JSON export",
            "@media (max-width: 430px)",
            "min-height: 44px",
        ):
            self.assertIn(fragment, self.source)
        forbidden = (
            r"\bfetch\s*\(",
            r"\bXMLHttpRequest\b",
            r"\bWebSocket\b",
            r"\bEventSource\b",
            r"\bnavigator\.sendBeacon\b",
            r"@import\b",
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

    def test_renderer_thumbnail_and_frame_samples_are_deterministic(self):
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
                "math",
                "os",
                "pathlib",
                "shutil",
                "subprocess",
                "sys",
                "typing",
            },
            imported,
        )
        self.assertEqual(
            (
                RENDERER.SPEC.width,
                RENDERER.SPEC.height,
                RENDERER.SPEC.fps,
                RENDERER.SPEC.duration,
                RENDERER.SPEC.frame_count,
            ),
            (960, 540, 12, 22, 264),
        )
        command = RENDERER.ffmpeg_command("fixed-ffmpeg", Path("master.mkv"))
        for value in (
            "rawvideo",
            "rgb24",
            "pipe:0",
            "ffv1",
            "bgr0",
            "pc",
            "+bitexact",
            "matroska",
        ):
            self.assertIn(value, command)
        self.assertEqual(command[command.index("-threads") + 1], "1")
        for frame_index, expected in FRAME_SAMPLES.items():
            with self.subTest(frame=frame_index):
                self.assertEqual(RENDERER.frame_digest(frame_index), expected)
        self.assertEqual(
            len(RENDERER.frame_rgb(RENDERER.SPEC, 0)),
            960 * 540 * 3,
        )

        thumbnail = normalized_text(THUMB_PATH)
        self.assertEqual(thumbnail, RENDERER.thumbnail_svg())
        root = ET.fromstring(thumbnail)
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

    def test_film_result_labels_are_derived_from_model_points(self):
        original_simulate = RENDERER.simulate
        labels: list[str] = []
        original_text = RENDERER.Canvas.text

        def altered_simulate(rate, *args, **kwargs):
            points = original_simulate(rate, *args, **kwargs)
            rate_milli = (
                int(rate)
                if kwargs.get("rate_is_milli")
                else round(float(rate) * 1000)
            )
            final = points[-1]
            if rate_milli == RENDERER.RATE_STABLE_MILLI:
                points[-1] = RENDERER.ModelPoint(
                    final.tick,
                    111_000,
                    final.resources_milli,
                    final.support_milli,
                    final.weather_milli,
                    final.random_state,
                )
            elif rate_milli == RENDERER.RATE_COLLAPSE_MILLI:
                points[-1] = RENDERER.ModelPoint(
                    final.tick,
                    9_000,
                    final.resources_milli,
                    final.support_milli,
                    final.weather_milli,
                    final.random_state,
                )
            return points

        def record_text(canvas, x, y, value, color, scale=2, spacing=1):
            labels.append(value)
            return original_text(canvas, x, y, value, color, scale, spacing)

        with mock.patch.object(RENDERER, "simulate", side_effect=altered_simulate):
            with mock.patch.object(RENDERER.Canvas, "text", new=record_text):
                RENDERER.frame_rgb(RENDERER.SPEC, 9 * RENDERER.SPEC.fps)
                RENDERER.frame_rgb(RENDERER.SPEC, 18 * RENDERER.SPEC.fps)
        self.assertIn("TICK 600 / HERD 111 / BAND HELD", labels)
        self.assertIn("BELOW 10 AT TICK 134 / FINAL 9", labels)

    def test_evidence_and_delivery_sha_bindings_are_complete(self):
        series_record = self.evidence["seriesExport"]
        self.assertEqual(series_record["path"], "exports/fixture-series.json")
        self.assertEqual(series_record["bytes"], FIXTURE_EXPORT_PATH.stat().st_size)
        self.assertEqual(series_record["sha256"], sha256(FIXTURE_EXPORT_PATH))
        self.assertTrue(series_record["containsEveryTick"])
        self.assertEqual(series_record["pointCountPerFixture"], 601)

        self.assertEqual(
            set(self.evidence["artifactBindings"]),
            EXPECTED_EVIDENCE_BINDINGS,
        )
        for relative, record in self.evidence["artifactBindings"].items():
            path = CANDIDATE / relative
            self.assertTrue(path.is_file(), path)
            self.assertEqual(record["path"], relative)
            self.assertEqual(record["bytes"], path.stat().st_size)
            self.assertEqual(record["sha256"], sha256(path))
        snapshots_record = self.evidence["canonicalSnapshots"]
        self.assertEqual(
            snapshots_record["path"],
            "snapshots/canonical-states.json",
        )
        self.assertEqual(snapshots_record["bytes"], SNAPSHOT_PATH.stat().st_size)
        self.assertEqual(snapshots_record["sha256"], sha256(SNAPSHOT_PATH))

        self.assertEqual(
            set(self.delivery["artifacts"]),
            set(RENDERER.DELIVERY_FILES),
        )
        for relative, record in self.delivery["artifacts"].items():
            path = CANDIDATE / relative
            self.assertTrue(path.is_file(), path)
            self.assertEqual(record["path"], relative)
            self.assertEqual(record["bytes"], path.stat().st_size)
            self.assertEqual(record["sha256"], sha256(path))
        self.assertEqual(
            self.delivery["bindings"]["evidenceSha256"],
            sha256(EVIDENCE_PATH),
        )
        self.assertEqual(
            self.delivery["bindings"]["productionSha256"],
            sha256(MANIFEST_PATH),
        )
        self.assertEqual(
            self.delivery["bindings"]["compiledChannelSha256"],
            sha256(CHANNEL_PATH),
        )
        self.assertEqual(
            self.delivery["bindings"]["fixtureSeriesSha256"],
            sha256(FIXTURE_EXPORT_PATH),
        )

    def test_rights_privacy_and_portable_documentation_are_explicit(self):
        rights = self.evidence["rightsPrivacy"]
        self.assertTrue(rights["rightsAttestation"])
        self.assertTrue(rights["privacyAttestation"])
        self.assertTrue(rights["noSecrets"])
        self.assertTrue(rights["syntheticModelData"])
        self.assertTrue(rights["originalRendererAndIllustration"])
        self.assertFalse(rights["personalData"])
        self.assertEqual(rights["externalResources"], [])
        combined = "\n".join(
            normalized_text(path)
            for path in CANDIDATE.rglob("*")
            if path.is_file()
            and path.suffix.lower() not in {".mkv", ".mp4", ".webm", ".pyc"}
        )
        self.assertNotIn(Path.home().name.lower(), combined.lower())
        for token in ("RAPP_BROWSER", "RAPP_FFMPEG", "RAPP_FFPROBE"):
            self.assertIn(token, normalized_text(README_PATH))
        secret_patterns = (
            rb"AKIA[0-9A-Z]{16}",
            rb"gh[pousr]_[A-Za-z0-9]{30,}",
            rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        )
        for path in CANDIDATE.rglob("*"):
            if not path.is_file() or path.suffix.lower() == ".pyc":
                continue
            payload = path.read_bytes()
            for pattern in secret_patterns:
                self.assertIsNone(
                    re.search(pattern, payload),
                    f"{path}: {pattern!r}",
                )

    def test_generated_text_documents_are_current(self):
        self.assertEqual(
            normalized_text(FIXTURE_EXPORT_PATH),
            RENDERER.deterministic_json(RENDERER.fixture_export_document()),
        )
        self.assertEqual(
            normalized_text(SNAPSHOT_PATH),
            RENDERER.deterministic_json(
                RENDERER.canonical_states_document()
            ),
        )
        generated_evidence = RENDERER.evidence_document()
        RENDERER.validate_evidence(generated_evidence)
        self.assertEqual(
            normalized_text(EVIDENCE_PATH),
            RENDERER.deterministic_json(generated_evidence),
        )

    def test_generated_text_is_lf_and_crlf_source_compiles_identically(self):
        for path in CANDIDATE.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() not in {".mkv", ".mp4", ".webm", ".pyc"}
            ):
                self.assertNotIn(b"\r", path.read_bytes(), path)

        scratch = CANDIDATE / "_test-crlf"
        remove_tree(scratch)
        try:
            scratch_master = scratch / "masters" / MASTER_PATH.name
            scratch_master.parent.mkdir(parents=True)
            shutil.copyfile(MASTER_PATH, scratch_master)
            scratch_manifest = scratch / MANIFEST_PATH.name
            scratch_manifest.write_bytes(
                MANIFEST_PATH.read_text(encoding="utf-8")
                .replace("\n", "\r\n")
                .encode("utf-8")
            )
            compilation = COMPILER.prepare_compilation(scratch_manifest)
            self.assertEqual(compilation.channel, self.channel)
        finally:
            remove_tree(scratch)

    def test_evidence_and_delivery_validators_reject_mutations(self):
        evidence = RENDERER.evidence_document()
        bad_band = copy.deepcopy(evidence)
        bad_band["fixtures"][0]["series"][250][1] = 79_999
        with self.assertRaisesRegex(RuntimeError, "band|digest"):
            RENDERER.validate_evidence(bad_band)

        bad_tick = copy.deepcopy(evidence)
        bad_tick["fixtures"][1]["series"][134][0] = 999
        with self.assertRaisesRegex(RuntimeError, "point"):
            RENDERER.validate_evidence(bad_tick)

        bad_crossing = copy.deepcopy(evidence)
        bad_crossing["fixtures"][1]["collapseCrossingTick"] = 135
        with self.assertRaisesRegex(RuntimeError, "crossing"):
            RENDERER.validate_evidence(bad_crossing)

        bad_delivery = copy.deepcopy(self.delivery)
        bad_delivery["media"]["webm"]["codec"] = "h264"
        with self.assertRaisesRegex(RuntimeError, "webm codec"):
            RENDERER.validate_delivery(bad_delivery)

    def test_portable_media_tool_resolution_accepts_quoted_paths(self):
        require_tools(self, FFmpeg=FFMPEG, FFprobe=FFPROBE)
        self.assertEqual(
            Path(RENDERER.resolve_binary("ffmpeg", f'"{FFMPEG}"')),
            Path(FFMPEG),
        )
        self.assertEqual(
            Path(RENDERER.resolve_binary("ffprobe", f"'{FFPROBE}'")),
            Path(FFPROBE),
        )
        candidates = {
            str(path).lower()
            for path in RENDERER._common_media_paths("ffmpeg")
        }
        self.assertTrue(any("usr" in path and "bin" in path for path in candidates))
        if sys.platform == "win32":
            self.assertTrue(
                any("winget" in path or "program files" in path for path in candidates)
            )
        with mock.patch.object(RENDERER.os, "name", "posix"):
            with mock.patch.object(RENDERER, "Path", PurePosixPath):
                with mock.patch.dict(RENDERER.os.environ, {}, clear=True):
                    posix_candidates = list(
                        RENDERER._common_media_paths("ffmpeg")
                    )
        self.assertIn(PurePosixPath("/usr/bin/ffmpeg"), posix_candidates)
        self.assertIn(
            PurePosixPath("/usr/local/bin/ffmpeg"),
            posix_candidates,
        )

    def test_verifiers_do_not_use_broad_silent_cleanup_catches(self):
        verifier = normalized_text(VERIFY_DOM_PATH)
        tests = normalized_text(Path(__file__))
        self.assertIsNone(re.search(r"catch\s*\{\s*\}", verifier))
        self.assertNotIn("ignore_errors" + "=True", tests)


class TestFrame000303BrowserExecution(unittest.TestCase):
    def test_exact_manifest_actions_and_responsive_results_in_real_browser(self):
        require_tools(self, Node=NODE, Browser=BROWSER)
        profile = CANDIDATE / "_test-browser-profile"
        remove_tree(profile)
        try:
            completed = subprocess.run(
                [
                    NODE,
                    str(VERIFY_DOM_PATH),
                    "--browser",
                    BROWSER,
                    "--profile",
                    str(profile),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=150,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertRegex(result["browser"], r"(Chrome|Chromium|Edge|Edg)/")
            self.assertEqual(result["actionCount"], 19)
            self.assertEqual(result["replayedWidths"], [1120, 390])
            self.assertEqual(
                result["activatedClicks"],
                {"desktop": 8, "responsive": 8},
            )
            self.assertEqual(
                result["checkpoints"], ["stable", "collapse", "reset"]
            )
            self.assertEqual(
                result["responsiveCheckpoints"],
                ["stable", "collapse", "reset"],
            )
            self.assertEqual(result["stableFinal"], 112)
            self.assertEqual(result["collapseCrossingTick"], 134)
            self.assertEqual(result["collapseFinal"], 8)
            self.assertEqual(result["resetTraceLength"], 0)
            self.assertEqual(result["responsiveWidth"], 390)
            self.assertEqual(result["browserErrors"], 0)
            self.assertEqual(result["externalRequests"], 0)
            self.assertEqual(
                result["arbitraryRateDigest"],
                independent_digest(independent_simulate(451)),
            )
            self.assertEqual(
                result["seedDigests"],
                [
                    independent_digest(independent_simulate(450, seed=1)),
                    independent_digest(independent_simulate(450, seed=2)),
                ],
            )
            self.assertNotEqual(
                result["seedDigests"][0],
                result["seedDigests"][1],
            )
            self.assertEqual(
                result["predictionDigest"],
                independent_digest(independent_simulate(450)),
            )
            self.assertEqual(result["exportPointCount"], 601)
            self.assertEqual(result["invalidInputCount"], 10)
            self.assertTrue(result["exportCleanedOnReset"])
            self.assertTrue(result["profileCleaned"])
            self.assertFalse(profile.exists())
        finally:
            remove_tree(profile)

    def test_browser_verifier_refuses_destructive_profile_paths(self):
        require_tools(self, Node=NODE, Browser=BROWSER)
        readme_before = README_PATH.read_bytes()
        completed = subprocess.run(
            [
                NODE,
                str(VERIFY_DOM_PATH),
                "--browser",
                BROWSER,
                "--profile",
                str(CANDIDATE),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("direct child", completed.stderr)
        self.assertEqual(README_PATH.read_bytes(), readme_before)


class TestFrame000303MediaExecution(unittest.TestCase):
    def test_lossless_master_decodes_to_exact_renderer_frames(self):
        require_tools(self, FFmpeg=FFMPEG)
        frame_size = RENDERER.SPEC.width * RENDERER.SPEC.height * 3
        process = subprocess.Popen(
            [
                FFMPEG,
                "-v",
                "error",
                "-i",
                str(MASTER_PATH),
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
            blocks = []
            remaining = size
            while remaining:
                block = process.stdout.read(remaining)
                if not block:
                    break
                blocks.append(block)
                remaining -= len(block)
            return b"".join(blocks)

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
        error = process.stderr.read().decode("utf-8", errors="replace").strip()
        return_code = process.wait()
        process.stdout.close()
        process.stderr.close()
        self.assertEqual(return_code, 0, error)

    def test_real_ffprobe_matches_delivery_and_publication_validator(self):
        require_tools(self, FFprobe=FFPROBE)
        self.assertEqual(
            VALIDATOR.ffprobe_local_media(
                load_json(CHANNEL_PATH),
                CHANNEL_PATH,
                executable=FFPROBE,
            ),
            [],
        )
        self.assertEqual(
            load_json(DELIVERY_PATH),
            RENDERER.delivery_document(FFPROBE),
        )
        delivery = load_json(DELIVERY_PATH)
        self.assertEqual(delivery["media"]["master"]["codec"], "ffv1")
        self.assertEqual(
            (
                delivery["media"]["master"]["width"],
                delivery["media"]["master"]["height"],
                delivery["media"]["master"]["duration"],
            ),
            (960, 540, 22),
        )
        self.assertEqual(delivery["media"]["master"]["pixelFormat"], "bgr0")
        self.assertEqual(delivery["media"]["master"]["colorSpace"], "gbr")
        self.assertEqual(delivery["media"]["master"]["colorRange"], "pc")
        self.assertIsNone(delivery["media"]["master"]["colorTransfer"])
        self.assertIsNone(delivery["media"]["master"]["colorPrimaries"])
        for kind, codec in (("mp4", "h264"), ("webm", "vp9")):
            record = delivery["media"][kind]
            with self.subTest(kind=kind):
                self.assertEqual(record["codec"], codec)
                self.assertEqual(record["pixelFormat"], "yuv420p")
                self.assertEqual(
                    (record["width"], record["height"], record["duration"]),
                    (960, 540, 22),
                )
                self.assertEqual(record["colorSpace"], "bt709")
                self.assertEqual(record["colorTransfer"], "bt709")
                self.assertEqual(record["colorPrimaries"], "bt709")
                self.assertEqual(record["colorRange"], "tv")
        for kind, record in delivery["media"].items():
            with self.subTest(streams=kind):
                self.assertEqual(record["streamCount"], 1)
                self.assertEqual(record["audioStreamCount"], 0)

        for path in (MASTER_PATH, MP4_PATH, WEBM_PATH):
            completed = subprocess.run(
                [
                    FFPROBE,
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            embedded_metadata = {
                "formatTags": payload["format"].get("tags", {}),
                "streamTags": [
                    stream.get("tags", {}) for stream in payload["streams"]
                ],
            }
            metadata = json.dumps(embedded_metadata, sort_keys=True).lower()
            self.assertNotIn(Path.home().name.lower(), metadata)
            self.assertNotIn(str(ROOT).lower(), metadata)
            self.assertEqual(
                [stream["codec_type"] for stream in payload["streams"]],
                ["video"],
            )

    def test_clean_renderer_and_compiler_rebuild_is_byte_stable(self):
        require_tools(self, FFmpeg=FFMPEG, FFprobe=FFPROBE)
        scratch = CANDIDATE / "_test-rebuild"
        remove_tree(scratch)
        try:
            rebuilt_master = (
                scratch / "masters" / f"{PUBLICATION_ID}.mkv"
            )
            RENDERER.render_master(FFMPEG, rebuilt_master)
            self.assertEqual(sha256(rebuilt_master), sha256(MASTER_PATH))

            scratch.mkdir(parents=True, exist_ok=True)
            scratch_manifest = scratch / "channel.production.json"
            scratch_manifest.write_bytes(MANIFEST_PATH.read_bytes())
            compilation = COMPILER.prepare_compilation(scratch_manifest)
            rebuilt_channel = COMPILER.build_compilation(
                compilation,
                ffmpeg=FFMPEG,
                ffprobe=FFPROBE,
            )
            self.assertEqual(
                rebuilt_channel.read_bytes(), CHANNEL_PATH.read_bytes()
            )
            self.assertEqual(
                sha256(scratch / "media" / f"{PUBLICATION_ID}.mp4"),
                sha256(MP4_PATH),
            )
            self.assertEqual(
                sha256(scratch / "media" / f"{PUBLICATION_ID}.webm"),
                sha256(WEBM_PATH),
            )
        finally:
            remove_tree(scratch)


if __name__ == "__main__":
    unittest.main()
