"""Offline production-contract tests for the Tiny Systems seed channel."""

import ast
import copy
import hashlib
import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TINY_ROOT = ROOT / "tiny-systems"
MANIFEST_PATH = TINY_ROOT / "channel.production.json"
CHANNEL_PATH = TINY_ROOT / "channel.json"
EVIDENCE_PATH = TINY_ROOT / "evidence.json"
DELIVERY_PATH = TINY_ROOT / "delivery.json"
RENDERER_PATH = ROOT / "scripts" / "render_tiny_systems.py"
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
COMPILER_PATH = ROOT / "scripts" / "compile_publications.py"

PUBLICATIONS = [
    ("one-block-three-trains", "One Block, Three Trains"),
    ("four-and-a-half-to-one", "Four-and-a-Half to One"),
    ("three-tokens-make-nine", "Three Tokens Make Nine"),
]

REQUIRED_SELECTORS = {
    "one-block-three-trains": {
        "#dispatch-btn",
        "#depart-btn",
        "#reset-btn",
    },
    "four-and-a-half-to-one": {
        "#apply-boundary-btn",
        "#apply-near-miss-btn",
        "#reset-btn",
    },
    "three-tokens-make-nine": {
        "#token-1",
        "#token-2",
        "#token-3",
        "#token-4",
        "#submit-btn",
        "#reset-btn",
    },
}

FRAME_SAMPLES = {
    "one-block-three-trains": {
        0: "db911ce25f526184a15f7ab766e7b785580cdff388b6023d3c310b31a4ac423d",
        60: "ead44e3234bc2626df998cec438e732e69d004abe5f9f246dd39be480c384df2",
        119: "53fece679f38501e5883104beb5596d9262c6e3293ddeab504c3f271db311d3a",
    },
    "four-and-a-half-to-one": {
        0: "838fea5b32678a682af74ef20075b48ae48a2220cf1685fddc58de30745ce55e",
        54: "69f1d8fe3912f060c6189d8319c13ea04285b3b518dd468cf6b0db91f2d2e21b",
        107: "3869f7291839bdbbdb89441eaae8cc9392e8e5cfed34ac9336246e2f35ecae4f",
    },
    "three-tokens-make-nine": {
        0: "3abd60340d0e0b8759bfb94abee6ec0b8639728e9e27a7c6decaa2fd05958995",
        72: "d92f19c1e4144dcbf9f50d3ede5cace0014fce0e23d5f411a5297e3df592b060",
        143: "a407bcc148647e089c36f4eb375601ba41b51caa91fb1ec8e176b8e39a337423",
    },
}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_module("validate_tiny_system_publications", VALIDATOR_PATH)
RENDERER = load_module("render_tiny_systems", RENDERER_PATH)
COMPILER = load_module("compile_tiny_system_publications", COMPILER_PATH)


class AppIndex(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.resource_attributes = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        for name in ("src", "href", "poster", "action"):
            if attributes.get(name):
                self.resource_attributes.append((tag, name, attributes[name]))


def embedded_contract_states(source):
    match = re.search(
        r'<script\s+type="application/json"\s+id="contract-states">\s*'
        r"(.*?)\s*</script>",
        source,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError("app has no embedded contract-states JSON")
    return json.loads(match.group(1))


def resolve_path(document, path):
    current = document
    for component in path.split("."):
        current = current[component]
    return current


def is_subsequence(needle, haystack):
    cursor = iter(haystack)
    return all(any(candidate == item for candidate in cursor) for item in needle)


class TestTinySystemsManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(MANIFEST_PATH)
        cls.videos = {
            video["id"]: video for video in cls.manifest["videos"]
        }

    def test_production_manifest_shape_and_master_paths(self):
        self.assertEqual(self.manifest["schema"], "rapp-vision-production/1.0")
        self.assertEqual(self.manifest["id"], "tiny-systems")
        self.assertEqual(
            [(video["id"], video["title"]) for video in self.manifest["videos"]],
            PUBLICATIONS,
        )

        dimensions = set()
        orientations = set()
        for publication_id, _title in PUBLICATIONS:
            video = self.videos[publication_id]
            with self.subTest(publication=publication_id):
                self.assertNotIn("sources", video)
                self.assertEqual(
                    video["production"],
                    {"master": f"masters/{publication_id}.mkv"},
                )
                self.assertEqual(
                    video["thumb"],
                    f"thumbs/{publication_id}.svg",
                )
                self.assertEqual(video["live"]["kind"], "rapp-vision-live/1.0")
                self.assertTrue(video["live"]["scenes"])
                dimensions.add((video["width"], video["height"]))
                orientations.add(video["orientation"])
        self.assertEqual(len(dimensions), 3)
        self.assertEqual(orientations, {"landscape", "square", "portrait"})

    def test_synthetic_delivery_transform_passes_existing_validator(self):
        delivery = copy.deepcopy(self.manifest)
        delivery["schema"] = "rapp-vision-channel/2.0"
        for video in delivery["videos"]:
            video.pop("production")
            video["sources"] = [
                {
                    "src": f"https://example.test/media/{video['id']}.mp4",
                    "type": "video/mp4",
                },
                {
                    "src": f"https://example.test/media/{video['id']}.webm",
                    "type": "video/webm",
                },
            ]
        policy = load_json(ROOT / "policy" / "legacy-publications.json")
        errors = VALIDATOR.validate_channel(
            delivery,
            "https://example.test/tiny-systems/channel.json",
            policy,
        )
        self.assertEqual(errors, [])

    def test_live_replays_are_contiguous_and_cover_all_paths(self):
        evidence = {
            publication["id"]: publication
            for publication in load_json(EVIDENCE_PATH)["publications"]
        }
        for publication_id, video in self.videos.items():
            with self.subTest(publication=publication_id):
                cursor = 0
                action_selectors = []
                for scene in video["live"]["scenes"]:
                    self.assertEqual(scene["t"], cursor)
                    cursor += scene["dur"]
                    action_selectors.extend(
                        action["selector"]
                        for action in scene.get("actions", [])
                        if action["do"] == "click"
                    )
                self.assertEqual(cursor, video["live"]["duration"])
                for claim in evidence[publication_id]["claims"]:
                    selectors = [action["selector"] for action in claim["actions"]]
                    self.assertTrue(
                        is_subsequence(selectors, action_selectors),
                        (publication_id, claim["id"], selectors, action_selectors),
                    )


class TestTinySystemsEvidenceAndApps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(MANIFEST_PATH)
        cls.evidence = load_json(EVIDENCE_PATH)
        cls.evidence_by_id = {
            publication["id"]: publication
            for publication in cls.evidence["publications"]
        }

    def test_evidence_is_complete_exact_and_self_checking(self):
        self.assertEqual(self.evidence["schema"], "tiny-systems-evidence/1.0")
        self.assertEqual(self.evidence["channel"], "tiny-systems")
        self.assertEqual(list(self.evidence_by_id), [item[0] for item in PUBLICATIONS])

        preserved_fields = {
            "one-block-three-trains": ("waiting", "block", "completed"),
            "four-and-a-half-to-one": ("accepted",),
            "three-tokens-make-nine": ("accepted",),
        }
        for publication_id, publication in self.evidence_by_id.items():
            source = (TINY_ROOT / publication["app"]).read_text(encoding="utf-8")
            embedded = embedded_contract_states(source)
            claims = {claim["id"]: claim for claim in publication["claims"]}
            with self.subTest(publication=publication_id):
                self.assertEqual(set(claims), {"positive", "rejected", "reset"})
                self.assertEqual(
                    embedded,
                    {
                        claim_id: claims[claim_id]["expectedState"]
                        for claim_id in ("positive", "rejected", "reset")
                    },
                )
                for claim in claims.values():
                    self.assertTrue(claim["claim"].strip())
                    self.assertTrue(claim["actions"])
                    self.assertTrue(claim["assertions"])
                    for assertion in claim["assertions"]:
                        self.assertEqual(
                            resolve_path(claim["expectedState"], assertion["path"]),
                            assertion["equals"],
                        )
                for field in preserved_fields[publication_id]:
                    self.assertEqual(
                        claims["rejected"]["expectedState"][field],
                        claims["positive"]["expectedState"][field],
                    )
                self.assertEqual(claims["rejected"]["preserves"], "positive")

    def test_app_selectors_reducers_and_exact_reset_markers(self):
        videos = {video["id"]: video for video in self.manifest["videos"]}
        for publication_id, publication in self.evidence_by_id.items():
            path = TINY_ROOT / publication["app"]
            source = path.read_text(encoding="utf-8")
            index = AppIndex()
            index.feed(source)
            with self.subTest(publication=publication_id):
                self.assertTrue(path.is_file())
                self.assertIn('<html lang="en">', source)
                self.assertIn("<main", source)
                self.assertIn("aria-live=", source)
                self.assertIn("function initialState()", source)
                self.assertIn("function reduce(state, action)", source)
                self.assertIn('case "RESET":', source)
                self.assertIn("return initialState();", source)
                self.assertIn('data-reset="exact"', source)
                self.assertIn("window.tinySystem = Object.freeze", source)
                self.assertEqual(index.resource_attributes, [])
                self.assertTrue(
                    {selector[1:] for selector in REQUIRED_SELECTORS[publication_id]}
                    <= index.ids
                )

                live = videos[publication_id]["live"]
                selectors = {
                    scene["ready"]["selector"]
                    for scene in live["scenes"]
                    if "ready" in scene
                }
                selectors.update(
                    action["selector"]
                    for scene in live["scenes"]
                    for action in scene.get("actions", [])
                    if action["do"] == "click"
                )
                self.assertTrue(all(selector.startswith("#") for selector in selectors))
                self.assertTrue({selector[1:] for selector in selectors} <= index.ids)

                action_types = {
                    action["type"]
                    for claim in publication["claims"]
                    for action in claim["actions"]
                }
                for action_type in action_types:
                    self.assertIn(f'data-action="{action_type}"', source)

    def test_wcag_boundary_values_are_computed_on_opposite_sides(self):
        claims = {
            claim["id"]: claim
            for claim in self.evidence_by_id["four-and-a-half-to-one"]["claims"]
        }

        def contrast(gray):
            channel = gray / 255
            linear = (
                channel / 12.92
                if channel <= 0.04045
                else ((channel + 0.055) / 1.055) ** 2.4
            )
            return 1.05 / (linear + 0.05)

        boundary = contrast(118)
        near_miss = contrast(119)
        self.assertEqual(round(boundary, 2), 4.54)
        self.assertEqual(round(near_miss, 2), 4.48)
        self.assertGreaterEqual(claims["positive"]["expectedState"]["accepted"]["ratio"], 4.5)
        self.assertLess(claims["rejected"]["expectedState"]["rejected"]["ratio"], 4.5)

    def test_apps_have_no_network_or_external_asset_capabilities(self):
        forbidden = [
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
        ]
        for path in sorted((TINY_ROOT / "apps").glob("*.html")):
            source = path.read_text(encoding="utf-8")
            with self.subTest(app=path.name):
                for pattern in forbidden:
                    self.assertIsNone(re.search(pattern, source, flags=re.IGNORECASE), pattern)

    def test_thumbnails_are_safe_and_match_the_renderer(self):
        for spec in RENDERER.SPECS:
            path = TINY_ROOT / spec.thumbnail_relative
            source = path.read_text(encoding="utf-8")
            root = ET.fromstring(source)
            with self.subTest(publication=spec.publication_id):
                self.assertEqual(source, RENDERER.thumbnail_svg(spec))
                self.assertTrue(root.tag.endswith("svg"))
                self.assertEqual(
                    root.attrib["viewBox"],
                    f"0 0 {spec.width} {spec.height}",
                )
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


class TestTinySystemsRenderer(unittest.TestCase):
    def test_renderer_uses_only_the_standard_library(self):
        tree = ast.parse(RENDERER_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        self.assertTrue(
            imported <= {
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

    def test_render_plan_and_ffmpeg_contract_are_deterministic(self):
        output_root = TINY_ROOT / "_dry-run-never-created"
        first = RENDERER.build_render_plan(output_root)
        second = RENDERER.build_render_plan(output_root)
        self.assertEqual(first, second)
        self.assertEqual([job.spec for job in first], list(RENDERER.SPECS))
        self.assertEqual(len({job.spec.style for job in first}), 3)
        self.assertEqual(
            {
                (job.spec.width, job.spec.height)
                for job in first
            },
            {(960, 540), (720, 720), (540, 960)},
        )

        for job in first:
            command = RENDERER.ffmpeg_command("ffmpeg-contract", job.spec, job.master_path)
            with self.subTest(publication=job.spec.publication_id):
                self.assertIn("rawvideo", command)
                self.assertIn("rgb24", command)
                self.assertIn("pipe:0", command)
                self.assertIn("-an", command)
                self.assertIn("ffv1", command)
                self.assertIn("matroska", command)
                self.assertEqual(command[-1], str(job.master_path))
                self.assertEqual(job.master_path.suffix, ".mkv")
                self.assertEqual(
                    len(RENDERER.frame_rgb(job.spec, 0)),
                    job.spec.width * job.spec.height * 3,
                )

    def test_frame_samples_are_stable(self):
        for publication_id, samples in FRAME_SAMPLES.items():
            for frame_index, expected in samples.items():
                with self.subTest(
                    publication=publication_id,
                    frame=frame_index,
                ):
                    self.assertEqual(
                        RENDERER.frame_digest(publication_id, frame_index),
                        expected,
                    )
                    self.assertEqual(
                        RENDERER.frame_digest(publication_id, frame_index),
                        expected,
                    )

    def test_cli_dry_run_honors_all_options_without_side_effects(self):
        output_root = TINY_ROOT / "_dry-run-never-created"
        self.assertFalse(output_root.exists())
        completed = subprocess.run(
            [
                sys.executable,
                str(RENDERER_PATH),
                "--ffmpeg",
                "ffmpeg-not-invoked",
                "--only",
                "three-tokens-make-nine,one-block-three-trains",
                "--output-root",
                str(output_root),
                "--dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        plan = json.loads(completed.stdout)
        self.assertEqual(plan["schema"], "tiny-systems-render-plan/1.0")
        self.assertEqual(plan["ffmpeg"], "ffmpeg-not-invoked")
        self.assertEqual(
            [job["id"] for job in plan["jobs"]],
            ["one-block-three-trains", "three-tokens-make-nine"],
        )
        self.assertTrue(
            all(str(output_root) in job["master"] for job in plan["jobs"])
        )
        self.assertFalse(output_root.exists())

    def test_cli_rejects_unknown_publications_without_writing(self):
        output_root = TINY_ROOT / "_dry-run-never-created"
        completed = subprocess.run(
            [
                sys.executable,
                str(RENDERER_PATH),
                "--only",
                "not-a-publication",
                "--output-root",
                str(output_root),
                "--dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("unknown publication id", completed.stderr)
        self.assertFalse(output_root.exists())

    def test_compiled_delivery_is_complete_and_digest_bound(self):
        channel = load_json(CHANNEL_PATH)
        delivery = load_json(DELIVERY_PATH)
        self.assertEqual(channel["schema"], "rapp-vision-channel/2.0")
        self.assertEqual(delivery["schema"], "tiny-systems-delivery/1.0")
        by_id = {record["id"]: record for record in delivery["videos"]}
        self.assertEqual(set(by_id), {publication_id for publication_id, _ in PUBLICATIONS})

        for video in channel["videos"]:
            with self.subTest(publication=video["id"]):
                record = by_id[video["id"]]
                self.assertEqual(
                    video["sources"],
                    [
                        {
                            "src": f"media/{video['id']}.mp4",
                            "type": "video/mp4",
                        },
                        {
                            "src": f"media/{video['id']}.webm",
                            "type": "video/webm",
                        },
                    ],
                )
                for kind in ("master", "mp4", "webm"):
                    artifact = record[kind]
                    path = TINY_ROOT / artifact["path"]
                    self.assertTrue(path.is_file(), path)
                    self.assertEqual(path.stat().st_size, artifact["bytes"])
                    self.assertEqual(
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                        artifact["sha256"],
                    )
                for kind in ("mp4", "webm"):
                    self.assertEqual(record[kind]["color_space"], "bt709")
                    self.assertEqual(record[kind]["color_transfer"], "bt709")
                    self.assertEqual(record[kind]["color_primaries"], "bt709")
                    self.assertEqual(record[kind]["color_range"], "tv")

        registry = load_json(ROOT / "channels.json")
        matches = [
            entry for entry in registry["channels"]
            if entry["id"] == "tiny-systems"
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["url"], "tiny-systems/channel.json")
        self.assertEqual(matches[0]["contract"], "rapp-vision-channel/2.0")

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "ffmpeg and ffprobe are required for byte-stability integration",
    )
    def test_real_compiler_rebuild_is_byte_stable_and_bt709(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            (source_root / "masters").mkdir(parents=True)
            manifest = load_json(MANIFEST_PATH)
            manifest["videos"] = manifest["videos"][:1]
            source = source_root / "channel.production.json"
            source.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )
            master_name = manifest["videos"][0]["production"]["master"]
            shutil.copy2(TINY_ROOT / master_name, source_root / master_name)

            outputs = []
            for name in ("first", "second"):
                output = root / name
                compilation = COMPILER.prepare_compilation(source, output)
                COMPILER.build_compilation(compilation)
                outputs.append(output)

            for extension in ("mp4", "webm"):
                relative = Path("media") / f"one-block-three-trains.{extension}"
                first = outputs[0] / relative
                second = outputs[1] / relative
                self.assertEqual(
                    hashlib.sha256(first.read_bytes()).hexdigest(),
                    hashlib.sha256(second.read_bytes()).hexdigest(),
                )
                probe = json.loads(
                    subprocess.check_output(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-select_streams",
                            "v:0",
                            "-show_entries",
                            (
                                "stream=codec_name,color_space,color_transfer,"
                                "color_primaries,color_range"
                            ),
                            "-of",
                            "json",
                            str(first),
                        ],
                        text=True,
                    )
                )["streams"][0]
                self.assertEqual(probe["color_space"], "bt709")
                self.assertEqual(probe["color_transfer"], "bt709")
                self.assertEqual(probe["color_primaries"], "bt709")
                self.assertEqual(probe["color_range"], "tv")


if __name__ == "__main__":
    unittest.main(verbosity=2)
