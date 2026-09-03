"""Release contracts for frame 0003-09, Archive Wetland Contrast."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import math
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
EXPECTED_COMMISSION_GATES = {
    "paired_delivery": {
        "mp4": True,
        "webm": True,
        "live": True,
        "same_publication": True,
    },
    "objective_evidence": {
        "required": True,
        "criterion": (
            "Comparing the fixture's 1990 and 2020 snapshots yields exactly "
            "seven changed record ids, and the exported sorted id list "
            "matches the embedded expected list."
        ),
        "acceptance": (
            "Snapshot labels, total record count, changed count, sorted ids, "
            "spatial extent, and export digest are inspectable."
        ),
    },
    "positive_path": {
        "required": True,
        "demonstration": (
            "Compare the two snapshots, filter to the seven changed records, "
            "inspect one record, and export the sorted id list."
        ),
    },
    "visible_failure": {
        "required": True,
        "demonstration": (
            "Select the supplied impossible date range and show a clear empty "
            "state that is not rendered as a successful zero-change comparison."
        ),
    },
    "exact_reset": {
        "required": True,
        "steps": [
            "Activate Restore archive view.",
            "Set snapshots to 1990 and 2020.",
            "Reset filters, selection, pan, and zoom.",
        ],
        "restored_state": (
            "All 24 records are visible at the original extent, the "
            "seven-change comparison is selected, no record is focused, and "
            "the expected export digest is restored."
        ),
    },
    "rights_privacy": {
        "rights_attestation": True,
        "privacy_attestation": True,
        "no_secrets": True,
        "scope": (
            "Records, coordinates, names, images, and dates must be synthetic "
            "or cleared for public redistribution."
        ),
    },
    "review_quorum": {
        "minimum_approvals": 2,
        "required_roles": ["technical", "curation"],
        "independent_reviewers": True,
    },
}
UNICODE_DIGEST_TEXT = "wetland · marsh"
UNICODE_DIGEST = (
    "64ab66483871ac72d1c8f8ab01df762469d56247d8aad98fbb2100c49a58492e"
)
EXPECTED_SOURCE_ARTIFACTS = {
    ".gitattributes",
    "README.md",
    "apps/explore-archive-map-contrast.html",
    "channel.production.json",
    "channel.json",
    "evidence.json",
    "exports/changed-record-ids.json",
    "render.py",
    "thumbs/explore-archive-map-contrast.svg",
    "verify_dom.mjs",
}
EXPECTED_DELIVERY_ARTIFACTS = EXPECTED_SOURCE_ARTIFACTS | {
    "masters/explore-archive-map-contrast.mkv",
    "media/explore-archive-map-contrast.mp4",
    "media/explore-archive-map-contrast.webm",
}
FILM_CONTENT_SAMPLES = {
    "opening": (
        1.0,
        12,
        "3a4db7663e001e76eb224f478d822fae2ef41594d1a8bdabcd8dcb879463f082",
    ),
    "compare": (
        3.5,
        42,
        "6f7c76fd6366aefc0bff90b424bcee1eaaa653e1a22f4f317dafffc59cc18627",
    ),
    "export": (
        10.0,
        120,
        "c5632471b9c9ffe9e802a90b09fb30fc6fd71f55dc71917ff18436bde4cbf4ce",
    ),
    "failure": (
        14.0,
        168,
        "bb7de74d0fbd91c045d8600b05151dd18a45386c7856a9af7c7843dfb6dcaa29",
    ),
    "reset": (
        17.5,
        210,
        "88cb8c577ffdbf083c40561cec5b14479f7643fa2b5c96abe6d8dd767f819270",
    ),
    "takeover": (
        20.5,
        246,
        "b6179efc63bcc8421b9bf8370b8f837ec17cad320ccccee7794d2587e46986a1",
    ),
}
LOSSY_FRAME_LIMITS = {
    "mp4": {
        "maximumMae": 2.25,
        "minimumPsnr": 35.5,
        "maximumOver16Fraction": 0.015,
        "maximumChannelError": 96,
    },
    "webm": {
        "maximumMae": 2.5,
        "minimumPsnr": 34.5,
        "maximumOver16Fraction": 0.0175,
        "maximumChannelError": 96,
    },
}


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


def read_exact(stream, size: int) -> bytes:
    blocks = []
    remaining = size
    while remaining:
        block = stream.read(remaining)
        if not block:
            break
        blocks.append(block)
        remaining -= len(block)
    return b"".join(blocks)


def decode_rgb_samples(path: Path, ffmpeg: Path) -> dict[int, bytes]:
    frame_size = RENDERER.SPEC.width * RENDERER.SPEC.height * 3
    sample_indexes = {
        frame_index
        for _timestamp, frame_index, _digest in FILM_CONTENT_SAMPLES.values()
    }
    process = subprocess.Popen(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-i",
            str(path),
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
    if process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()
        raise AssertionError(f"{path}: FFmpeg pipes were not created")

    samples = {}
    try:
        for frame_index in range(RENDERER.SPEC.frame_count):
            frame = read_exact(process.stdout, frame_size)
            if len(frame) != frame_size:
                process.kill()
                error = process.stderr.read().decode(
                    "utf-8",
                    errors="replace",
                ).strip()
                process.wait()
                raise AssertionError(
                    f"{path}: decoded {frame_index} complete frames; "
                    f"frame {frame_index} had {len(frame)} of {frame_size} "
                    f"bytes; stderr={error!r}"
                )
            if frame_index in sample_indexes:
                samples[frame_index] = frame

        trailing = process.stdout.read(1)
        if trailing:
            process.kill()
            process.wait()
            raise AssertionError(
                f"{path}: decoded more than "
                f"{RENDERER.SPEC.frame_count} frames"
            )
        error = process.stderr.read().decode(
            "utf-8",
            errors="replace",
        ).strip()
        return_code = process.wait()
        if return_code:
            raise AssertionError(
                f"{path}: FFmpeg decode exited {return_code}: {error}"
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()

    if set(samples) != sample_indexes:
        raise AssertionError(
            f"{path}: missing sampled frames "
            f"{sorted(sample_indexes - set(samples))}"
        )
    return samples


def rgb_fidelity(reference: bytes, encoded: bytes) -> dict[str, float | int]:
    if len(reference) != len(encoded):
        raise AssertionError(
            f"RGB frame size mismatch: {len(reference)} != {len(encoded)}"
        )
    absolute_error = 0
    squared_error = 0
    over_16 = 0
    maximum = 0
    for expected, actual in zip(reference, encoded, strict=True):
        difference = abs(expected - actual)
        absolute_error += difference
        squared_error += difference * difference
        over_16 += difference > 16
        maximum = max(maximum, difference)
    count = len(reference)
    mean_absolute_error = absolute_error / count
    mean_squared_error = squared_error / count
    psnr = (
        99.0
        if mean_squared_error == 0
        else 10 * math.log10((255 * 255) / mean_squared_error)
    )
    return {
        "mae": mean_absolute_error,
        "psnr": psnr,
        "over16Fraction": over_16 / count,
        "maximumChannelError": maximum,
    }


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


def delivery_errors(document) -> list[str]:
    records = list(document.get("artifacts", {}).values())
    records.extend(document.get("sourceArtifacts", []))
    errors = []
    observed = set()
    for record in records:
        relative = record.get("path")
        if not isinstance(relative, str):
            errors.append("delivery record has no string path")
            continue
        if relative in observed:
            errors.append(f"duplicate delivery path: {relative}")
            continue
        observed.add(relative)
        if "\\" in relative or relative.startswith("/") or ".." in Path(relative).parts:
            errors.append(f"unsafe delivery path: {relative}")
            continue
        path = CANDIDATE / relative
        if not path.is_file():
            errors.append(f"missing delivery path: {relative}")
            continue
        if path.stat().st_size != record.get("bytes"):
            errors.append(f"stale delivery size: {relative}")
        if sha256(path) != record.get("sha256"):
            errors.append(f"stale delivery hash: {relative}")
    if observed != EXPECTED_DELIVERY_ARTIFACTS:
        errors.append(
            "delivery coverage mismatch: "
            f"{sorted(observed ^ EXPECTED_DELIVERY_ARTIFACTS)}"
        )
    actual = {
        path.relative_to(CANDIDATE).as_posix()
        for path in CANDIDATE.rglob("*")
        if path.is_file()
        and path.name != "delivery.json"
        and "__pycache__" not in path.parts
    }
    if actual != observed:
        errors.append(f"unbound candidate files: {sorted(actual ^ observed)}")
    return errors


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

    def test_closed_commission_fulfillment_and_original_gates_are_bound(self):
        commissions = load_json(ROOT / "commissions.json")["commissions"]
        commission = next(
            item for item in commissions
            if item["id"] == "explore-archive-map-contrast"
        )
        self.assertEqual(commission["status"], "closed")
        self.assertEqual(
            commission["fulfillment"],
            {
                "result_channel": "working-proofs",
                "publication_id": PUBLICATION_ID,
                "source_candidate": (
                    "candidate-frame-0003/archive-wetland-contrast"
                ),
            },
        )
        self.assertEqual(
            commission["brief"],
            (
                "Build a spatial comparison over a synthetic 24-record archive "
                "where the viewer can isolate changed records, trigger an empty "
                "query, and return to the same view."
            ),
        )
        self.assertEqual(commission["gates"], EXPECTED_COMMISSION_GATES)
        self.assertEqual(
            self.evidence["commission"]["id"],
            commission["id"],
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
        self.assertEqual(len(actions), 25)
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
        replay = self.evidence["manifestReplay"]
        self.assertTrue(replay["exactTiming"])
        self.assertTrue(replay["activationVisibilityRequired"])
        self.assertTrue(replay["checkpointVisibilityRequired"])
        self.assertEqual(
            actions[-1],
            {
                "at": 16,
                "do": "scroll",
                "selector": "#takeover-prompt",
                "block": "center",
                "behavior": "auto",
            },
        )
        self.assertTrue(
            VALIDATOR.validate_action(
                {"at": 0, "do": "drag"},
                scene["dur"],
                "probe",
            )
        )

    def test_film_chapters_follow_renderer_and_live_story_order(self):
        chapters = self.video["chapters"]
        self.assertEqual(
            [RENDERER.film_phase(chapter["t"]) for chapter in chapters],
            [
                "opening",
                "compare",
                "inspect",
                "export",
                "failure",
                "reset",
                "takeover",
            ],
        )
        self.assertEqual(
            [chapter["label"] for chapter in chapters],
            [
                "Twenty-four synthetic field records",
                "1990 and 2020 reveal seven changes",
                "Filter and inspect WL-016",
                "Hold all seven IDs and readable digest",
                "Reject the impossible range as invalid",
                "Restore the exact archive view",
                "Your turn to explore the wetland",
            ],
        )
        self.assertEqual(
            [
                chapter["label"]
                for chapter in self.video["live"]["chapters"]
            ],
            [
                "Compare the archive sheets",
                "Filter to seven changed records",
                "Inspect, zoom, and pan",
                "Export the sorted ID list",
                "Supply impossible dates and reject",
                "Restore the canonical view",
                "YOUR TURN — choose any WL plot",
            ],
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
        self.assertTrue(self.fixture["synthetic"])
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
        raw_export = EXPORT_PATH.read_bytes()
        self.assertEqual(raw_export, EXPECTED_EXPORT)
        self.assertTrue(raw_export.endswith(b"\n"))
        self.assertFalse(raw_export.endswith(b"\r\n"))
        self.assertEqual(
            hashlib.sha256(EXPECTED_EXPORT).hexdigest(),
            EXPECTED_EXPORT_DIGEST,
        )
        self.assertEqual(
            hashlib.sha256(raw_export).hexdigest(),
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
        self.assertEqual(positive["acceptedYears"], {"from": 1990, "to": 2020})
        self.assertEqual(positive["visibleRecordIds"], list(EXPECTED_CHANGED_IDS))
        self.assertEqual(positive["focus"], "WL-016")
        self.assertEqual(
            positive["focusedRecord"]["coordinate"],
            "east position 1400 · north position 2280",
        )
        self.assertEqual(positive["filter"], "changed")
        self.assertEqual(positive["view"], {"panX": 40, "panY": 0, "zoom": 1.25})
        self.assertEqual(positive["export"]["status"], "exported")

        self.assertEqual(failure["years"], {"from": 1880, "to": 1885})
        self.assertEqual(failure["acceptedYears"], positive["acceptedYears"])
        self.assertEqual(failure["comparison"]["status"], "rejected-empty")
        self.assertEqual(
            failure["comparison"]["message"],
            (
                "No archive sheets exist for 1880 → 1885. "
                "The accepted seven-ID export remains preserved."
            ),
        )
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
        self.assertEqual(reset["acceptedYears"], {"from": 1990, "to": 2020})
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
        self.assertEqual(
            replay["finalPrompt"],
            {
                "afterAction": 24,
                "selector": "#takeover-prompt",
                "text": (
                    "YOUR TURN — choose any WL plot; arrows pan; −/+ zoom; "
                    "Compare reruns; Export binds the result."
                ),
            },
        )
        manifest_activations = [
            {
                key: value
                for key, value in action.items()
                if key != "at"
            }
            for action in actions
            if action["do"] in replay["activationActions"]
        ]
        claimed_activations = [
            action
            for claim_id in ("positive", "failure", "reset")
            for action in self.claims[claim_id]["actions"]
        ]
        self.assertEqual(manifest_activations, claimed_activations)

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
            "query-error-title",
            "query-error-body",
            "status-message",
            "export-output",
            "export-provenance",
            "map-window",
            "view-readout",
            "change-legend",
            "takeover-prompt",
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
            "function sha256Utf8(text)",
            "function parseYear(value)",
            "function moveRecordFocus(currentId, key)",
            'case "COMPARE":',
            'case "RESET":',
            "return initialState();",
            "window.archiveWetlandMap = contract;",
            "window.tinySystem = contract;",
            "queryResultCount: null",
            'preserved: "Canonical export preserved"',
            "rejected-invalid",
            "new TextEncoder().encode(text)",
            "rust ring = changed 1990→2020; dark ring = unchanged",
            "INVALID RANGE — NOT A VALID ZERO-CHANGE RESULT",
            "Observed from 24 synthetic records.",
            "YOUR TURN — choose any WL plot; arrows pan; −/+ zoom; Compare reruns; Export binds the result.",
            'data-reset="exact"',
            "@media (max-width: 520px)",
        ):
            self.assertIn(fragment, self.source)
        self.assertNotIn("overflow-x: clip", self.source)
        self.assertNotIn("failure-fixture", self.source)
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

    def test_record_markers_bind_fixture_ids_coordinates_and_names(self):
        index = AppIndex()
        index.feed(self.source)
        for record in self.fixture["records"]:
            marker_id = f"record-{record['id'].lower()}"
            tag, attributes = index.controls[marker_id]
            self.assertEqual(tag, "button")
            self.assertEqual(attributes["data-record-id"], record["id"])
            self.assertEqual(
                attributes["tabindex"],
                "0" if record["id"] == "WL-001" else "-1",
            )
            self.assertEqual(
                attributes["style"],
                f"--x:{record['x']};--y:{record['y']}",
            )
            self.assertIn(record["id"], attributes["aria-label"])
            self.assertIn(record["name"], attributes["aria-label"])

    def test_editorial_contract_binds_order_legibility_failure_and_takeover(self):
        self.assertLess(
            self.source.index('id="from-year"'),
            self.source.index('id="record-wl-001"'),
        )
        self.assertLess(
            self.source.index('id="compare-btn"'),
            self.source.index('id="record-wl-001"'),
        )
        self.assertEqual(self.source.count('id="query-error"'), 1)
        self.assertIn(
            (
                "Synthetic bounds: west 1000 to east 1600; south 2000 to "
                "north 2400. Exact extent: SYN E 1000–1600 / N 2000–2400."
            ),
            self.source,
        )
        rem_sizes = [
            float(value)
            for value in re.findall(r"font-size:\s*([0-9.]+)rem", self.source)
        ]
        self.assertTrue(rem_sizes)
        self.assertGreaterEqual(min(rem_sizes), 0.75)
        editorial = self.evidence["editorialAudit"]
        self.assertEqual(editorial["minimumPlayerWidth"], 390)
        self.assertFalse(editorial["horizontalExpansionAllowed"])
        self.assertEqual(editorial["minimumTextPixels"], 12)
        self.assertEqual(editorial["mobileExportTextPixels"], 13)
        self.assertEqual(
            editorial["spatialLanguage"]["exactExtentRetained"],
            "SYN E 1000–1600 / N 2000–2400",
        )
        self.assertEqual(editorial["domOrder"]["rovingRecordTabStopCount"], 1)
        self.assertEqual(
            editorial["legend"],
            "rust ring = changed 1990→2020; dark ring = unchanged",
        )
        self.assertEqual(editorial["failure"]["visibleNoticeCount"], 1)
        self.assertEqual(editorial["export"]["filmHoldSeconds"], 4)
        self.assertEqual(
            editorial["takeover"],
            (
                "YOUR TURN — choose any WL plot; arrows pan; −/+ zoom; "
                "Compare reruns; Export binds the result."
            ),
        )

    def test_utf8_digest_vector_and_invalid_query_contract_are_independent(self):
        runtime = self.evidence["runtimeAudit"]
        self.assertEqual(runtime["digestEncoding"], "UTF-8")
        self.assertEqual(runtime["unicodeDigestVector"]["text"], UNICODE_DIGEST_TEXT)
        self.assertEqual(runtime["unicodeDigestVector"]["sha256"], UNICODE_DIGEST)
        self.assertEqual(
            hashlib.sha256(UNICODE_DIGEST_TEXT.encode("utf-8")).hexdigest(),
            UNICODE_DIGEST,
        )
        invalid = runtime["invalidQuery"]
        self.assertEqual(invalid["status"], "rejected-invalid")
        self.assertIsNone(invalid["queryResultCount"])
        self.assertEqual(
            invalid["preservesAcceptedYears"],
            {"from": 1990, "to": 2020},
        )
        self.assertEqual(invalid["preservesChangedCount"], 7)
        self.assertEqual(
            invalid["preservesExportDigest"],
            EXPECTED_EXPORT_DIGEST,
        )
        self.assertEqual(
            runtime["network"]["blockedSchemes"],
            ["http", "https", "ws", "wss"],
        )
        self.assertEqual(runtime["network"]["expectedExternalRequests"], 0)
        self.assertTrue(runtime["cleanup"]["browserExitRequired"])
        self.assertTrue(runtime["cleanup"]["profileRemovalRequired"])
        self.assertTrue(runtime["cleanup"]["errorsAreFatal"])

    def test_browser_verifier_observes_network_errors_visibility_and_cleanup(self):
        source = normalized_text(VERIFY_DOM_PATH)
        for fragment in (
            'cdp.command("Network.enable")',
            'cdp.command("Network.setBlockedURLs"',
            'cdp.on("Network.requestWillBeSent"',
            'cdp.on("Network.loadingFailed"',
            'cdp.on("Runtime.exceptionThrown"',
            'cdp.on("Runtime.consoleAPICalled"',
            "await assertVisible(selector);",
            "const cleanup = await cleanupBrowser();",
            "profileRemoved: cleanup.profileRemoved",
        ):
            self.assertIn(fragment, source)
        self.assertNotIn("catch {}", source)

    def test_crlf_source_parsing_does_not_weaken_raw_export_contract(self):
        crlf_source = self.source.replace("\n", "\r\n")
        self.assertEqual(
            embedded_json(crlf_source, "wetland-fixture"),
            self.fixture,
        )
        self.assertEqual(EXPORT_PATH.read_bytes(), EXPECTED_EXPORT)

    def test_scoped_text_has_no_secret_material(self):
        secret_patterns = (
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
            r"\bAKIA[0-9A-Z]{16}\b",
            r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b",
            r"\bAIza[0-9A-Za-z_-]{30,}\b",
        )
        for path in CANDIDATE.rglob("*"):
            if not path.is_file() or path.suffix in {".mkv", ".mp4", ".webm", ".pyc"}:
                continue
            source = normalized_text(path)
            for pattern in secret_patterns:
                with self.subTest(path=path.name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, source))

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
        fixture = embedded_json(normalized_text(APP_PATH), "wetland-fixture")
        self.assertEqual(
            RENDERER.RECORDS,
            tuple(
                (record["id"], record["x"], record["y"])
                for record in fixture["records"]
            ),
        )
        self.assertEqual(RENDERER.CHANGED_IDS, EXPECTED_CHANGED_IDS)
        self.assertEqual(
            RENDERER.POSITIVE_VIEW,
            {"panX": 40, "panY": 0, "zoom": 1.25},
        )
        self.assertEqual(
            RENDERER.FILM_TIMELINE,
            (
                ("opening", 0.0, 2.0),
                ("compare", 2.0, 5.0),
                ("inspect", 5.0, 8.0),
                ("export", 8.0, 12.0),
                ("failure", 12.0, 16.0),
                ("reset", 16.0, 19.0),
                ("takeover", 19.0, 22.0),
            ),
        )
        self.assertEqual(
            self.delivery["render"]["positiveView"],
            {"panX": 40, "panY": 0, "zoom": 1.25},
        )
        self.assertEqual(
            self.delivery["render"]["timeline"],
            [
                {"phase": name, "start": start, "end": end}
                for name, start, end in RENDERER.FILM_TIMELINE
            ],
        )
        self.assertEqual(
            self.delivery["render"]["openingChanged"],
            "7 of 24 changed",
        )
        self.assertEqual(
            self.delivery["render"]["legend"],
            RENDERER.LEGEND_TEXT,
        )
        self.assertEqual(
            self.delivery["render"]["exportProvenance"],
            "OBSERVED FROM 24 SYNTHETIC RECORDS",
        )
        self.assertGreaterEqual(
            self.delivery["render"]["exportHoldSeconds"],
            2,
        )
        self.assertEqual(
            self.delivery["render"]["takeover"],
            RENDERER.TAKEOVER_TEXT,
        )
        export_phase = next(
            phase
            for phase in RENDERER.FILM_TIMELINE
            if phase[0] == "export"
        )
        self.assertGreaterEqual(export_phase[2] - export_phase[1], 2)
        for name, start, end in RENDERER.FILM_TIMELINE:
            self.assertEqual(RENDERER.film_phase(start), name)
            self.assertEqual(
                RENDERER.film_phase(end - 1 / RENDERER.SPEC.fps),
                name,
            )
        inspect_frame = RENDERER.frame_rgb(90)
        marker_x, marker_y = RENDERER._map_point(
            1400,
            2280,
            zoom=1.25,
            pan_x=40,
        )
        pixel_offset = (
            marker_y * RENDERER.SPEC.width + marker_x + 8
        ) * 3
        self.assertEqual(
            tuple(inspect_frame[pixel_offset:pixel_offset + 3]),
            RENDERER.RUST,
        )
        canvas_text_scales = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "canvas"
                and node.func.attr in {"text", "centered_text"}
            ):
                scale = node.args[-1]
                self.assertIsInstance(scale, ast.Constant)
                canvas_text_scales.append(scale.value)
        self.assertTrue(canvas_text_scales)
        self.assertGreaterEqual(min(canvas_text_scales), 2)
        self.assertEqual(
            len(RENDERER.frame_rgb(0)),
            RENDERER.SPEC.width * RENDERER.SPEC.height * 3,
        )
        for frame_index in (0, 24, 60, 96, 144, 192, 263):
            frame = RENDERER.frame_rgb(frame_index)
            legend_offset = (505 * RENDERER.SPEC.width + 5) * 3
            self.assertEqual(
                tuple(frame[legend_offset:legend_offset + 3]),
                RENDERER.INK_DARK,
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
        circles = [
            element
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1].lower() == "circle"
        ]
        self.assertEqual(len(circles), 24)
        self.assertTrue(all(circle.attrib.get("fill") == "#fffaf0" for circle in circles))
        self.assertTrue(all(circle.attrib.get("stroke-width") == "4" for circle in circles))
        text_sizes = [
            int(element.attrib["font-size"])
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1].lower() == "text"
        ]
        self.assertTrue(text_sizes)
        self.assertGreaterEqual(min(text_sizes), 12)
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
        self.assertEqual(
            set(RENDERER.SOURCE_ARTIFACTS),
            EXPECTED_SOURCE_ARTIFACTS,
        )
        self.assertEqual(delivery_errors(self.delivery), [])
        self.assertEqual(
            self.delivery["binding"],
            {
                "algorithm": "sha256",
                "artifactCount": 13,
                "pathStyle": "POSIX-relative",
                "selfExcluded": "delivery.json",
            },
        )

    def test_stale_delivery_hash_is_rejected(self):
        mutated = copy.deepcopy(self.delivery)
        mutated["sourceArtifacts"][0]["sha256"] = "0" * 64
        errors = delivery_errors(mutated)
        self.assertTrue(
            any(error.startswith("stale delivery hash:") for error in errors),
            errors,
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
                completed = subprocess.run(
                    [
                        str(FFPROBE),
                        "-v",
                        "error",
                        "-show_entries",
                        "stream=codec_type,avg_frame_rate",
                        "-of",
                        "json",
                        str(path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                )
                streams = json.loads(completed.stdout)["streams"]
                self.assertEqual(
                    [stream["codec_type"] for stream in streams],
                    ["video"],
                )
                self.assertEqual(streams[0]["avg_frame_rate"], "12/1")
        self.assertEqual(
            VALIDATOR.ffprobe_local_media(
                load_json(CHANNEL_PATH),
                CHANNEL_PATH,
                executable=str(FFPROBE),
            ),
            [],
        )

    @unittest.skipUnless(
        FFMPEG,
        "ffmpeg not found via RAPP_FFMPEG or portable locations",
    )
    def test_committed_media_pixels_bind_the_renderer_story(self):
        master_samples = decode_rgb_samples(MASTER_PATH, FFMPEG)
        for phase, (
            timestamp,
            frame_index,
            expected_digest,
        ) in FILM_CONTENT_SAMPLES.items():
            with self.subTest(master_phase=phase, frame=frame_index):
                self.assertEqual(
                    frame_index,
                    round(timestamp * RENDERER.SPEC.fps),
                )
                self.assertEqual(RENDERER.film_phase(timestamp), phase)
                rendered = RENDERER.frame_rgb(frame_index)
                decoded = master_samples[frame_index]
                rendered_digest = hashlib.sha256(rendered).hexdigest()
                decoded_digest = hashlib.sha256(decoded).hexdigest()
                self.assertEqual(rendered_digest, expected_digest)
                self.assertEqual(decoded_digest, expected_digest)
                if decoded != rendered:
                    first_difference = next(
                        index
                        for index, (actual, expected) in enumerate(
                            zip(decoded, rendered, strict=True)
                        )
                        if actual != expected
                    )
                    self.fail(
                        f"{phase} frame {frame_index}: committed FFV1 "
                        f"master differs from renderer at RGB byte "
                        f"{first_difference}; decoded={decoded_digest}, "
                        f"renderer={rendered_digest}"
                    )

        for kind, path in (("mp4", MP4_PATH), ("webm", WEBM_PATH)):
            decoded_samples = decode_rgb_samples(path, FFMPEG)
            limits = LOSSY_FRAME_LIMITS[kind]
            for phase, (
                _timestamp,
                frame_index,
                _expected_digest,
            ) in FILM_CONTENT_SAMPLES.items():
                metrics = rgb_fidelity(
                    master_samples[frame_index],
                    decoded_samples[frame_index],
                )
                diagnostic = (
                    f"{kind}/{phase} frame {frame_index}: "
                    f"MAE={metrics['mae']:.4f}, "
                    f"PSNR={metrics['psnr']:.3f} dB, "
                    f">16={metrics['over16Fraction']:.6%}, "
                    f"max={metrics['maximumChannelError']}"
                )
                with self.subTest(kind=kind, phase=phase):
                    self.assertLessEqual(
                        metrics["mae"],
                        limits["maximumMae"],
                        diagnostic,
                    )
                    self.assertGreaterEqual(
                        metrics["psnr"],
                        limits["minimumPsnr"],
                        diagnostic,
                    )
                    self.assertLessEqual(
                        metrics["over16Fraction"],
                        limits["maximumOver16Fraction"],
                        diagnostic,
                    )
                    self.assertLessEqual(
                        metrics["maximumChannelError"],
                        limits["maximumChannelError"],
                        diagnostic,
                    )

    @unittest.skipUnless(
        FFMPEG and FFPROBE,
        "ffmpeg/ffprobe not found via RAPP_FFMPEG, RAPP_FFPROBE, or portable locations",
    )
    def test_two_fresh_rebuilds_are_byte_identical_with_same_toolchain(self):
        scratches = [
            CANDIDATE / ".frame-0003-09-rebuild-a",
            CANDIDATE / ".frame-0003-09-rebuild-b",
        ]
        for scratch in scratches:
            shutil.rmtree(scratch, ignore_errors=True)
        self.addCleanup(
            lambda: [
                shutil.rmtree(scratch, ignore_errors=True)
                for scratch in scratches
            ]
        )

        rebuilt_deliveries = []
        for scratch in scratches:
            scratch.mkdir(parents=True)
            for relative in (
                ".gitattributes",
                "README.md",
                "apps/explore-archive-map-contrast.html",
                "channel.production.json",
                "evidence.json",
                "exports/changed-record-ids.json",
                "render.py",
                "verify_dom.mjs",
            ):
                source = CANDIDATE / relative
                target = scratch / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

            RENDERER.render(scratch, str(FFMPEG))
            compilation = COMPILER.prepare_compilation(
                scratch / "channel.production.json",
                scratch,
            )
            COMPILER.build_compilation(
                compilation,
                ffmpeg=str(FFMPEG),
                ffprobe=str(FFPROBE),
            )
            rebuilt_deliveries.append(
                RENDERER.delivery_document(scratch, str(FFPROBE))
            )

        self.assertEqual(
            (scratches[0] / "channel.json").read_bytes(),
            CHANNEL_PATH.read_bytes(),
        )
        self.assertEqual(
            (
                scratches[0]
                / "thumbs"
                / f"{PUBLICATION_ID}.svg"
            ).read_bytes(),
            THUMB_PATH.read_bytes(),
        )
        for relative in (
            Path("masters") / f"{PUBLICATION_ID}.mkv",
            Path("media") / f"{PUBLICATION_ID}.mp4",
            Path("media") / f"{PUBLICATION_ID}.webm",
            Path("thumbs") / f"{PUBLICATION_ID}.svg",
            Path("channel.json"),
        ):
            with self.subTest(rebuilt=relative.as_posix()):
                self.assertEqual(
                    sha256(scratches[0] / relative),
                    sha256(scratches[1] / relative),
                )

        self.assertEqual(rebuilt_deliveries[0], rebuilt_deliveries[1])
        for kind in ("master", "mp4", "webm"):
            rebuilt = rebuilt_deliveries[0]["artifacts"][kind]
            delivered = self.delivery["artifacts"][kind]
            for field in (
                "codec",
                "pixelFormat",
                "width",
                "height",
                "duration",
                "colorSpace",
                "colorTransfer",
                "colorPrimaries",
                "colorRange",
            ):
                with self.subTest(kind=kind, field=field):
                    self.assertEqual(
                        rebuilt.get(field),
                        delivered.get(field),
                    )

    def test_tool_discovery_rejects_missing_and_accepts_quoted_explicit_path(self):
        with self.assertRaises(RuntimeError):
            RENDERER.discover_executable(
                "ffmpeg",
                str(CANDIDATE / "missing-ffmpeg"),
            )
        if FFMPEG:
            self.assertEqual(
                Path(
                    RENDERER.discover_executable(
                        "ffmpeg",
                        f'"{FFMPEG}"',
                    )
                ),
                FFMPEG.resolve(),
            )


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
        timing_skew = payload.pop("maxTimingSkewMs")
        self.assertGreaterEqual(timing_skew, 0)
        self.assertLess(timing_skew, 1000)
        mobile_layout = payload.pop("mobileLayout")
        self.assertEqual(
            mobile_layout["documentWidth"],
            mobile_layout["clientWidth"],
        )
        self.assertGreaterEqual(mobile_layout["clientWidth"], 370)
        self.assertLessEqual(mobile_layout["clientWidth"], 390)
        self.assertEqual(mobile_layout["minimumTextPixels"], 12)
        self.assertGreaterEqual(mobile_layout["exportPixels"], 13)
        self.assertGreaterEqual(mobile_layout["digestPixels"], 13)
        self.assertFalse(mobile_layout["overflowClipped"])
        self.assertEqual(
            payload,
            {
                "actionCount": 25,
                "manifestActivationChecks": 12,
                "checkpointVisibilityChecks": 6,
                "exactTiming": True,
                "viewports": ["desktop", "mobile-390"],
                "tabOrder": [
                    "from-year",
                    "to-year",
                    "compare-btn",
                    "filter-changed-btn",
                    "filter-all-btn",
                    "export-btn",
                    "restore-btn",
                    "pan-west-btn",
                    "pan-north-btn",
                    "pan-south-btn",
                    "pan-east-btn",
                    "zoom-out-btn",
                    "zoom-in-btn",
                    "record-wl-001",
                ],
                "rovingFocus": {
                    "arrowTarget": "record-wl-002",
                    "enterSelection": "WL-002",
                    "spaceSelection": "WL-003",
                    "tabStops": 1,
                },
                "failureLayout": {
                    "fullWidth": True,
                    "adjacent": True,
                    "visibleNotices": 1,
                },
                "finalPromptChecks": 2,
                "recordCount": 24,
                "changedCount": 7,
                "changedIds": list(EXPECTED_CHANGED_IDS),
                "digest": EXPECTED_EXPORT_DIGEST,
                "failureStatus": "rejected-empty",
                "failureResultCount": None,
                "failureExportStatus": "preserved",
                "failureAcceptedYears": {"from": 1990, "to": 2020},
                "invalidStatus": "rejected-invalid",
                "resetVisibleCount": 24,
                "resetFocus": None,
                "resetView": {"panX": 0, "panY": 0, "zoom": 1},
                "takeover": {
                    "focus": "WL-024",
                    "visibleCount": 24,
                    "view": {"panX": 0, "panY": -40, "zoom": 0.75},
                    "transform": {
                        "a": 0.75,
                        "d": 0.75,
                        "e": 0,
                        "f": -40,
                    },
                },
                "networkBlocked": True,
                "externalNetworkRequests": 0,
                "blockedExternalRequests": 0,
                "browserErrors": 0,
                "cleanup": {
                    "browserExited": True,
                    "profileRemoved": True,
                },
            },
        )

    @unittest.skipUnless(
        NODE and BROWSER,
        "Node/browser not found via RAPP_BROWSER or portable locations",
    )
    def test_browser_verifier_propagates_input_errors_and_cleans_up(self):
        profile = CANDIDATE / ".frame-0003-09-browser-error"
        shutil.rmtree(profile, ignore_errors=True)
        self.addCleanup(lambda: shutil.rmtree(profile, ignore_errors=True))
        completed = subprocess.run(
            [
                str(NODE),
                str(VERIFY_DOM_PATH),
                "--browser",
                str(BROWSER),
                "--evidence",
                str(CANDIDATE / "missing-evidence.json"),
                "--profile",
                str(profile),
            ],
            cwd=CANDIDATE,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("wetland browser verification failed", completed.stderr)
        self.assertFalse(profile.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
