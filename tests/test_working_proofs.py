"""Integration tests for the recurring Working Proofs winner channel."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlsplit


ROOT = Path(__file__).resolve().parents[1]
WORKING_ROOT = ROOT / "working-proofs"
CHANNEL_PATH = WORKING_ROOT / "channel.json"
EVIDENCE_INDEX_PATH = WORKING_ROOT / "evidence-index.json"
BUILDER_PATH = ROOT / "scripts" / "build_working_proofs.py"
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
VIEWPORT_RUNNER_PATH = ROOT / "tests" / "working_proofs_viewport_browser.mjs"
CANDIDATE_ROOT = ROOT / "candidate-frame-0002"
SCREENSHOT_ROOT = WORKING_ROOT / "screenshots"

PUBLICATIONS = (
    (
        "learn-grid-overflow",
        "learn-grid-overflow",
        "Why the Grid Overflows",
    ),
    (
        "use-keyboard-invoice-triage",
        "use-keyboard-invoice-triage",
        "Triage Invoices Without a Pointer",
    ),
    (
        "create-vector-icon-system",
        "create-vector-icon-system",
        "Six Shapes, One Grid",
    ),
)
EXPECTED_CODECS = {
    "video/mp4": "h264",
    "video/webm": "vp9",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path}: not a PNG")
    return struct.unpack(">II", header[16:24])


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def resolve_reference(base_file: Path, reference: str) -> Path:
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc:
        raise AssertionError(f"expected a repository-relative URL: {reference}")
    return base_file.parent.joinpath(*PurePosixPath(parsed.path).parts).resolve()


def resolve_browser() -> str | None:
    for environment_name in (
        "BROWSER",
        "CHROME_PATH",
        "CHROMIUM_PATH",
        "EDGE_PATH",
        "FRAME_BROWSER",
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
        found = shutil.which(name)
        if found:
            return found
    roots = (
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    )
    candidates = (
        Path("Google") / "Chrome" / "Application" / "chrome.exe",
        Path("Microsoft") / "Edge" / "Application" / "msedge.exe",
    )
    for root in filter(None, roots):
        for relative in candidates:
            candidate = Path(root) / relative
            if candidate.is_file():
                return str(candidate.resolve())
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        cache = Path(local_app_data) / "ms-playwright"
        for pattern in (
            "chromium-*/chrome-win*/chrome.exe",
            "chromium-*/chrome-linux*/chrome",
            "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
        ):
            matches = sorted(cache.glob(pattern))
            if matches:
                return str(matches[-1].resolve())
    return None


def resolve_ffprobe() -> str | None:
    for environment_name in ("FFPROBE", "FFPROBE_PATH", "FRAME_FFPROBE"):
        value = os.environ.get(environment_name)
        if value and Path(value).is_file():
            return str(Path(value).resolve())
    found = shutil.which("ffprobe")
    if found:
        return found
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        matches = sorted(
            packages.glob("Gyan.FFmpeg*/**/bin/ffprobe.exe")
        )
        if matches:
            return str(matches[-1].resolve())
    return None


BUILDER = load_module("build_working_proofs_tests", BUILDER_PATH)
VALIDATOR = load_module("validate_working_proofs_tests", VALIDATOR_PATH)
NODE = shutil.which("node")
FFPROBE = resolve_ffprobe()
BROWSER = resolve_browser()


class TestWorkingProofsBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.channel = load_json(CHANNEL_PATH)
        cls.evidence_index = load_json(EVIDENCE_INDEX_PATH)

    def test_builder_output_is_sorted_utf8_lf_and_current(self):
        expected_channel, expected_index = BUILDER.build_documents()
        self.assertEqual(CHANNEL_PATH.read_bytes(), BUILDER.json_bytes(expected_channel))
        self.assertEqual(
            EVIDENCE_INDEX_PATH.read_bytes(),
            BUILDER.json_bytes(expected_index),
        )
        for path in (CHANNEL_PATH, EVIDENCE_INDEX_PATH):
            raw = path.read_bytes()
            with self.subTest(path=path.name):
                self.assertNotIn(b"\r", raw)
                self.assertTrue(raw.endswith(b"\n"))
                raw.decode("utf-8", errors="strict")
                self.assertEqual(raw, BUILDER.json_bytes(load_json(path)))

        source_hashes = {
            path: sha256(path)
            for source_directory, _publication_id, _title in PUBLICATIONS
            for path in (
                CANDIDATE_ROOT / source_directory / "channel.json",
                CANDIDATE_ROOT / source_directory / "evidence.json",
                CANDIDATE_ROOT / source_directory / "delivery.json",
            )
        }
        completed = subprocess.run(
            [sys.executable, str(BUILDER_PATH), "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            {path: sha256(path) for path in source_hashes},
            source_hashes,
        )

    def test_channel_identity_order_and_constitution_are_exact(self):
        self.assertEqual(
            {
                "id": self.channel["id"],
                "name": self.channel["name"],
                "tagline": self.channel["tagline"],
                "cadence": self.channel["cadence"],
                "visibility": self.channel["visibility"],
            },
            {
                "id": "working-proofs",
                "name": "Working Proofs",
                "tagline": (
                    "Useful work, measurable results, controls included."
                ),
                "cadence": "recurring",
                "visibility": "public",
            },
        )
        self.assertEqual(self.channel["schema"], "rapp-vision-channel/2.0")
        self.assertEqual(
            [
                (publication["id"], publication["title"])
                for publication in self.channel["videos"]
            ],
            [
                (publication_id, title)
                for _source_directory, publication_id, title in PUBLICATIONS
            ],
        )
        self.assertEqual(len(self.channel["videos"]), 3)

        policy = load_json(ROOT / "policy" / "legacy-publications.json")
        self.assertEqual(
            VALIDATOR.validate_channel(
                self.channel,
                CHANNEL_PATH.resolve().as_uri(),
                policy,
            ),
            [],
        )
        for publication in self.channel["videos"]:
            with self.subTest(publication=publication["id"]):
                self.assertEqual(
                    {source["type"] for source in publication["sources"]},
                    set(EXPECTED_CODECS),
                )
                self.assertEqual(publication["live"]["kind"], "rapp-vision-live/1.0")
                self.assertTrue(publication["live"]["scenes"])

    def test_candidate_branding_and_review_metadata_are_not_public(self):
        serialized = json.dumps(self.channel, ensure_ascii=False).lower()
        self.assertNotIn("candidate frame", serialized)
        self.assertNotIn("candidate frame", (WORKING_ROOT / "README.md").read_text(
            encoding="utf-8"
        ).lower())
        for publication in self.channel["videos"]:
            keys = set()
            pending = [publication]
            while pending:
                value = pending.pop()
                if isinstance(value, dict):
                    keys.update(value)
                    pending.extend(value.values())
                elif isinstance(value, list):
                    pending.extend(value)
            with self.subTest(publication=publication["id"]):
                self.assertFalse(keys & BUILDER.CANDIDATE_ONLY_KEYS)
                self.assertFalse(any(key.startswith("_") for key in keys))

    def test_paths_resolve_to_source_files_without_binary_copies(self):
        channel_uri = CHANNEL_PATH.resolve().as_uri()
        for source_directory, publication_id, _title in PUBLICATIONS:
            publication = next(
                item
                for item in self.channel["videos"]
                if item["id"] == publication_id
            )
            references = [publication["thumb"]]
            references.extend(source["src"] for source in publication["sources"])
            references.extend(
                scene["app"]
                for scene in publication["live"]["scenes"]
                if "app" in scene
            )
            expected_root = (CANDIDATE_ROOT / source_directory).resolve()
            for reference in references:
                with self.subTest(publication=publication_id, reference=reference):
                    resolved = resolve_reference(CHANNEL_PATH, reference)
                    self.assertTrue(resolved.is_file(), resolved)
                    self.assertEqual(urljoin(channel_uri, reference), resolved.as_uri())
                    self.assertTrue(resolved.is_relative_to(expected_root))

        binaries = [
            path
            for path in WORKING_ROOT.rglob("*")
            if path.suffix.lower() in {".mp4", ".webm", ".mkv", ".mov"}
        ]
        self.assertEqual(binaries, [])

    def test_evidence_index_binds_source_documents_by_sha256(self):
        self.assertEqual(
            {
                "schema": self.evidence_index["schema"],
                "channel": self.evidence_index["channel"],
            },
            {
                "schema": "working-proofs-evidence-index/1.0",
                "channel": "working-proofs",
            },
        )
        self.assertEqual(
            [
                record["publication_id"]
                for record in self.evidence_index["publications"]
            ],
            [item[1] for item in PUBLICATIONS],
        )

        for expected, record in zip(
            PUBLICATIONS,
            self.evidence_index["publications"],
            strict=True,
        ):
            source_directory, publication_id, _title = expected
            with self.subTest(publication=publication_id):
                self.assertEqual(record["commission_id"], source_directory)
                self.assertEqual(record["publication_id"], publication_id)
                source_root = resolve_reference(
                    EVIDENCE_INDEX_PATH,
                    record["source_candidate"],
                )
                self.assertEqual(
                    source_root,
                    (CANDIDATE_ROOT / source_directory).resolve(),
                )
                self.assertTrue(source_root.is_dir())

                for binding_name in ("source_channel", "evidence", "delivery"):
                    binding = record[binding_name]
                    path = resolve_reference(
                        EVIDENCE_INDEX_PATH,
                        binding["path"],
                    )
                    self.assertTrue(path.is_file(), path)
                    self.assertEqual(binding["sha256"], sha256(path))
                    self.assertEqual(
                        urljoin(
                            EVIDENCE_INDEX_PATH.resolve().as_uri(),
                            binding["path"],
                        ),
                        path.as_uri(),
                    )

                source_channel = load_json(
                    resolve_reference(
                        EVIDENCE_INDEX_PATH,
                        record["source_channel"]["path"],
                    )
                )
                delivery = load_json(
                    resolve_reference(
                        EVIDENCE_INDEX_PATH,
                        record["delivery"]["path"],
                    )
                )
                self.assertEqual(
                    record["source_channel"]["id"],
                    source_channel["id"],
                )
                self.assertEqual(delivery["publication"], publication_id)

    def test_registry_readme_and_fulfilled_commissions_are_bound(self):
        registry = load_json(ROOT / "channels.json")
        self.assertEqual(registry["revision"]["sequence"], 6)
        updated = datetime.fromisoformat(
            registry["revision"]["updated"].replace("Z", "+00:00")
        )
        self.assertEqual(updated.tzinfo, timezone.utc)
        entry = next(
            item
            for item in registry["channels"]
            if item["id"] == "working-proofs"
        )
        self.assertEqual(
            {
                "id": entry["id"],
                "name": entry["name"],
                "url": entry["url"],
                "repo": entry["repo"],
                "contract": entry["contract"],
            },
            {
                "id": "working-proofs",
                "name": "Working Proofs",
                "url": "working-proofs/channel.json",
                "repo": "https://github.com/kody-w/rapp-vision",
                "contract": "rapp-vision-channel/2.0",
            },
        )
        self.assertIn(
            "| **Working Proofs** | ✓ |",
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )

        commissions = {
            commission["id"]: commission
            for commission in load_json(ROOT / "commissions.json")["commissions"]
        }
        closed = {
            commission_id
            for commission_id, commission in commissions.items()
            if commission["status"] == "closed"
        }
        self.assertEqual(closed, {item[0] for item in PUBLICATIONS})
        for source_directory, publication_id, _title in PUBLICATIONS:
            self.assertEqual(
                commissions[source_directory]["fulfillment"],
                {
                    "result_channel": "working-proofs",
                    "publication_id": publication_id,
                    "source_candidate": (
                        f"candidate-frame-0002/{source_directory}"
                    ),
                },
            )


class TestWorkingProofsMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.channel = load_json(CHANNEL_PATH)
        cls.index_by_publication = {
            record["publication_id"]: record
            for record in load_json(EVIDENCE_INDEX_PATH)["publications"]
        }

    def delivery_record(self, publication_id: str, kind: str):
        index_record = self.index_by_publication[publication_id]
        delivery = load_json(
            resolve_reference(
                EVIDENCE_INDEX_PATH,
                index_record["delivery"]["path"],
            )
        )
        container = delivery.get("media", delivery.get("artifacts"))
        return container[kind]

    def test_delivery_hashes_dimensions_durations_and_declared_codecs(self):
        for publication in self.channel["videos"]:
            for source in publication["sources"]:
                kind = source["type"].removeprefix("video/")
                record = self.delivery_record(publication["id"], kind)
                path = resolve_reference(CHANNEL_PATH, source["src"])
                with self.subTest(
                    publication=publication["id"],
                    media_type=source["type"],
                ):
                    self.assertEqual(record["codec"], EXPECTED_CODECS[source["type"]])
                    self.assertEqual(record["width"], publication["width"])
                    self.assertEqual(record["height"], publication["height"])
                    self.assertAlmostEqual(
                        float(record["duration"]),
                        float(publication["duration"]),
                        places=3,
                    )
                    self.assertEqual(record["bytes"], path.stat().st_size)
                    self.assertEqual(record["sha256"], sha256(path))

    @unittest.skipUnless(FFPROBE, "ffprobe is required for real media probing")
    def test_ffprobe_confirms_all_aggregate_media(self):
        for publication in self.channel["videos"]:
            for source in publication["sources"]:
                path = resolve_reference(CHANNEL_PATH, source["src"])
                completed = subprocess.run(
                    [
                        FFPROBE,
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=codec_name,width,height:format=duration",
                        "-of",
                        "json",
                        str(path),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                with self.subTest(
                    publication=publication["id"],
                    media_type=source["type"],
                ):
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    probe = json.loads(completed.stdout)
                    stream = probe["streams"][0]
                    self.assertEqual(
                        stream["codec_name"],
                        EXPECTED_CODECS[source["type"]],
                    )
                    self.assertEqual(stream["width"], publication["width"])
                    self.assertEqual(stream["height"], publication["height"])
                    self.assertAlmostEqual(
                        float(probe["format"]["duration"]),
                        float(publication["duration"]),
                        delta=0.05,
                    )

        completed = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_PATH),
                "--ffprobe-local",
                str(CHANNEL_PATH),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
            env={
                **os.environ,
                "PATH": (
                    str(Path(FFPROBE).parent)
                    + os.pathsep
                    + os.environ.get("PATH", "")
                ),
            },
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(f"{CHANNEL_PATH}: valid", completed.stdout)


@unittest.skipUnless(
    NODE and BROWSER,
    "Node and a Chromium-family browser are required for aggregate live replay",
)
class TestWorkingProofsBrowserExecution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.channel = load_json(CHANNEL_PATH)
        cls.publications = {
            publication["id"]: publication
            for publication in cls.channel["videos"]
        }
        cls.index = {
            record["publication_id"]: record
            for record in load_json(EVIDENCE_INDEX_PATH)["publications"]
        }

    def run_json(self, command: list[str], profile: Path):
        shutil.rmtree(profile, ignore_errors=True)
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
            )
            return json.loads(completed.stdout.strip().splitlines()[-1])
        finally:
            shutil.rmtree(profile, ignore_errors=True)

    def aggregate_app(self, publication_id: str) -> Path:
        scene = self.publications[publication_id]["live"]["scenes"][0]
        path = resolve_reference(CHANNEL_PATH, scene["app"])
        self.assertEqual(
            urljoin(CHANNEL_PATH.resolve().as_uri(), scene["app"]),
            path.as_uri(),
        )
        return path

    def evidence_path(self, publication_id: str) -> Path:
        return resolve_reference(
            EVIDENCE_INDEX_PATH,
            self.index[publication_id]["evidence"]["path"],
        )

    def test_all_three_aggregate_live_replays_execute_in_real_browser(self):
        grid_id = "learn-grid-overflow"
        grid_profile = WORKING_ROOT / ".browser-grid"
        grid = self.run_json(
            [
                NODE,
                str(CANDIDATE_ROOT / grid_id / "verify_dom.mjs"),
                BROWSER,
                str(self.aggregate_app(grid_id)),
                str(self.evidence_path(grid_id)),
                str(grid_profile),
            ],
            grid_profile,
        )
        self.assertEqual(grid["browserErrors"], 0)
        self.assertEqual(grid["opening"], "612>320")
        self.assertEqual(grid["fixed320"], "320=320")
        self.assertEqual(grid["fixed1280"], "1280=1280")
        self.assertEqual(grid["resetX"], 0)

        keyboard_id = "use-keyboard-invoice-triage"
        keyboard_profile = WORKING_ROOT / ".browser-keyboard"
        source_channel_path = resolve_reference(
            EVIDENCE_INDEX_PATH,
            self.index[keyboard_id]["source_channel"]["path"],
        )
        keyboard = self.run_json(
            [
                NODE,
                str(CANDIDATE_ROOT / keyboard_id / "verify_dom.mjs"),
                "--browser",
                BROWSER,
                "--app",
                str(self.aggregate_app(keyboard_id)),
                "--evidence",
                str(self.evidence_path(keyboard_id)),
                "--manifest",
                str(source_channel_path),
                "--profile",
                str(keyboard_profile),
            ],
            keyboard_profile,
        )
        self.assertEqual(keyboard["browserErrors"], 0)
        self.assertEqual(keyboard["actionCount"], 33)
        self.assertEqual(
            keyboard["checkpoints"],
            ["positive", "rejected", "reset"],
        )
        self.assertEqual(keyboard["acceptedTotal"], "196.25")
        self.assertEqual(keyboard["resetFocus"], "invoice-syn-001")

        vector_id = "create-vector-icon-system"
        vector_profile = WORKING_ROOT / ".browser-vector"
        actions = self.publications[vector_id]["live"]["scenes"][0]["actions"]
        encoded_actions = base64.b64encode(
            json.dumps(actions, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        vector = self.run_json(
            [
                NODE,
                str(ROOT / "tests" / "frame_0002_09_browser.mjs"),
                BROWSER,
                self.aggregate_app(vector_id).resolve().as_uri(),
                encoded_actions,
                str(vector_profile),
            ],
            vector_profile,
        )
        self.assertEqual(vector["consoleErrors"], [])
        self.assertEqual(vector["pageErrors"], [])
        self.assertEqual(
            [step["selector"] for step in vector["steps"]],
            [
                action["selector"]
                for action in actions
                if action["do"] == "click"
            ],
        )
        self.assertEqual(vector["actionCount"], len(actions))
        self.assertEqual(
            [step["selector"] for step in vector["framing"]],
            [
                action["selector"]
                for action in actions
                if action["do"] == "scroll"
            ],
        )
        self.assertEqual(vector["steps"][-1]["state"], vector["initial"]["state"])
        self.assertEqual(vector["positivePath"]["changedIconCount"], 6)

    def test_desktop_and_390_player_stage_evidence_is_visible(self):
        profile = WORKING_ROOT / ".browser-viewports"
        scratch = WORKING_ROOT / ".viewport-captures"
        shutil.rmtree(scratch, ignore_errors=True)
        try:
            result = self.run_json(
                [
                    NODE,
                    str(VIEWPORT_RUNNER_PATH),
                    BROWSER,
                    str(CHANNEL_PATH),
                    str(EVIDENCE_INDEX_PATH),
                    str(scratch),
                    str(profile),
                ],
                profile,
            )
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["captures"], 18)
            self.assertEqual(len(result["runs"]), 6)

            expected_counts = {
                "learn-grid-overflow": 21,
                "use-keyboard-invoice-triage": 33,
                "create-vector-icon-system": 17,
            }
            for run in result["runs"]:
                with self.subTest(
                    publication=run["publication"],
                    viewport=run["viewport"],
                ):
                    self.assertEqual(
                        run["actionCount"],
                        expected_counts[run["publication"]],
                    )
                    self.assertEqual(
                        run["checkpoints"],
                        (
                            ["positive", "failure", "reset"]
                            if run["publication"] == "learn-grid-overflow"
                            else ["positive", "rejected", "reset"]
                        ),
                    )
                    self.assertGreater(run["activationsChecked"], 0)
                    self.assertAlmostEqual(
                        run["frameWidth"],
                        960 if run["viewport"] == "desktop" else 390,
                        delta=1,
                    )
                    self.assertTrue(all(height >= 90 for height in run["safeHeight"]))

            generated_manifest = load_json(scratch / "manifest.json")
            self.assertEqual(
                generated_manifest["schema"],
                "working-proofs-viewport-evidence/1.0",
            )
            self.assertEqual(generated_manifest["channel"], "working-proofs")
            self.assertEqual(len(generated_manifest["captures"]), 18)
            for capture in generated_manifest["captures"]:
                screenshot = scratch / capture["screenshot"]["path"]
                with self.subTest(
                    publication=capture["publication"],
                    viewport=capture["viewport"],
                    checkpoint=capture["checkpoint"],
                ):
                    self.assertTrue(capture["metrics"]["visible"])
                    self.assertGreaterEqual(
                        capture["metrics"]["visibleHeight"],
                        capture["metrics"]["requiredHeight"],
                    )
                    self.assertEqual(
                        png_dimensions(screenshot),
                        (
                            capture["screenshot"]["width"],
                            capture["screenshot"]["height"],
                        ),
                    )

            committed_manifest = load_json(SCREENSHOT_ROOT / "manifest.json")
            self.assertEqual(
                {
                    (
                        item["publication"],
                        item["viewport"],
                        item["checkpoint"],
                        item["resultSelector"],
                    )
                    for item in committed_manifest["captures"]
                },
                {
                    (
                        item["publication"],
                        item["viewport"],
                        item["checkpoint"],
                        item["resultSelector"],
                    )
                    for item in generated_manifest["captures"]
                },
            )
            self.assertEqual(len(committed_manifest["captures"]), 18)
            for capture in committed_manifest["captures"]:
                screenshot = SCREENSHOT_ROOT / capture["screenshot"]["path"]
                with self.subTest(committed=capture["screenshot"]["path"]):
                    self.assertTrue(screenshot.is_file())
                    self.assertEqual(
                        capture["screenshot"]["sha256"],
                        sha256(screenshot),
                    )
                    self.assertEqual(
                        capture["screenshot"]["bytes"],
                        screenshot.stat().st_size,
                    )
                    self.assertEqual(
                        png_dimensions(screenshot),
                        (
                            capture["screenshot"]["width"],
                            capture["screenshot"]["height"],
                        ),
                    )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
