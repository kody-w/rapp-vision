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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from unittest import mock
from urllib.parse import urljoin, urlsplit


ROOT = Path(__file__).resolve().parents[1]
WORKING_ROOT = ROOT / "working-proofs"
CHANNEL_PATH = WORKING_ROOT / "channel.json"
EVIDENCE_INDEX_PATH = WORKING_ROOT / "evidence-index.json"
BUILDER_PATH = ROOT / "scripts" / "build_working_proofs.py"
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
VIEWPORT_RUNNER_PATH = ROOT / "tests" / "working_proofs_viewport_browser.mjs"
SCREENSHOT_ROOT = WORKING_ROOT / "screenshots"


@dataclass(frozen=True)
class PublicationSpec:
    candidate_frame: str
    source_directory: str
    commission_id: str
    publication_id: str
    title: str

    @property
    def source_root(self) -> Path:
        return ROOT / self.candidate_frame / self.source_directory


PUBLICATIONS = (
    PublicationSpec(
        "candidate-frame-0002",
        "learn-grid-overflow",
        "learn-grid-overflow",
        "learn-grid-overflow",
        "Why the Grid Overflows",
    ),
    PublicationSpec(
        "candidate-frame-0002",
        "use-keyboard-invoice-triage",
        "use-keyboard-invoice-triage",
        "use-keyboard-invoice-triage",
        "Triage Invoices Without a Pointer",
    ),
    PublicationSpec(
        "candidate-frame-0002",
        "create-vector-icon-system",
        "create-vector-icon-system",
        "create-vector-icon-system",
        "Six Shapes, One Grid",
    ),
    PublicationSpec(
        "candidate-frame-0003",
        "ecosystem-island-threshold",
        "explore-ecosystem-threshold",
        "ecosystem-island-threshold",
        "Will the Island Herd Hold?",
    ),
    PublicationSpec(
        "candidate-frame-0003",
        "archive-wetland-contrast",
        "explore-archive-map-contrast",
        "explore-archive-map-contrast",
        "Read the Wetland Twice",
    ),
    PublicationSpec(
        "candidate-frame-0004",
        "maze-fogline",
        "play-seeded-maze-return",
        "maze-fogline",
        "Fogline Survey",
    ),
)
EXPECTED_CODECS = {
    "video/mp4": "h264",
    "video/webm": "vp9",
}
EXPECTED_ACTION_COUNTS = {
    "learn-grid-overflow": 21,
    "use-keyboard-invoice-triage": 33,
    "create-vector-icon-system": 17,
    "ecosystem-island-threshold": 23,
    "explore-archive-map-contrast": 25,
    "maze-fogline": 71,
}
EXPECTED_CHECKPOINTS = {
    "learn-grid-overflow": ["positive", "failure", "reset"],
    "use-keyboard-invoice-triage": ["positive", "rejected", "reset"],
    "create-vector-icon-system": ["positive", "rejected", "reset"],
    "ecosystem-island-threshold": [
        "stable",
        "collapse",
        "export",
        "reset",
        "your-turn",
    ],
    "explore-archive-map-contrast": ["positive", "failure", "reset"],
    "maze-fogline": [
        "hint",
        "trap",
        "detour",
        "resetAfterTrap",
        "optimal",
        "resetAfterOptimal",
        "handoff",
    ],
}
EXPECTED_CAPTURE_CHECKPOINTS = {
    **{
        publication_id: checkpoints
        for publication_id, checkpoints in EXPECTED_CHECKPOINTS.items()
        if publication_id != "maze-fogline"
    },
    "maze-fogline": [
        "failure",
        "reset",
        "challenge",
        "trap",
        "success",
        "FOG-7",
    ],
}
EXPECTED_CAPTURE_COUNT = 2 * sum(
    len(checkpoints)
    for checkpoints in EXPECTED_CAPTURE_CHECKPOINTS.values()
)
EXPECTED_VIEWPORT_GEOMETRY = {
    "desktop": {
        "pageWidth": 1387,
        "pageHeight": 900,
        "frameWidth": 960,
        "frameHeight": 599.25,
        "stageWidth": 962,
        "stageHeight": 601.25,
        "screenshotWidth": 962,
        "screenshotHeight": 601,
        "outerClientWidths": [1372, 1387],
        "scrollbarWidths": [0, 15],
    },
    "390": {
        "pageWidth": 435,
        "pageHeight": 900,
        "frameWidth": 390,
        "frameHeight": 243,
        "stageWidth": 392,
        "stageHeight": 245,
        "screenshotWidth": 392,
        "screenshotHeight": 245,
        "outerClientWidths": [420, 435],
        "scrollbarWidths": [0, 15],
    },
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


def manifest_source_bindings(manifest):
    bindings = manifest["sourceBindings"]
    yield bindings["player"]
    yield bindings["aggregate"]["channel"]
    yield bindings["aggregate"]["evidenceIndex"]
    for publication in bindings["publications"]:
        yield from publication["apps"]
        yield publication["sourceChannel"]
        yield publication["evidence"]


def clean_git_environment():
    environment = os.environ.copy()
    for name in tuple(environment):
        if (
            name == "GIT_CONFIG_COUNT"
            or name.startswith("GIT_CONFIG_KEY_")
            or name.startswith("GIT_CONFIG_VALUE_")
        ):
            environment.pop(name)
    return environment


def source_binding_errors(manifest):
    errors = []
    git_environment = clean_git_environment()
    for binding in manifest_source_bindings(manifest):
        path = ROOT.joinpath(
            *PurePosixPath(binding["path"]).parts
        ).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            errors.append(binding["path"])
            continue
        repository_relative = path.relative_to(ROOT).as_posix()
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "show",
                f":{repository_relative}",
            ],
            check=False,
            capture_output=True,
            env=git_environment,
        )
        if completed.returncode != 0 or completed.stdout != path.read_bytes():
            errors.append(binding["path"])
            continue
        if (
            binding["bytes"] != len(completed.stdout)
            or binding["sha256"] != hashlib.sha256(
                completed.stdout
            ).hexdigest()
        ):
            errors.append(binding["path"])
    return errors


def semantic_capture_contract(capture):
    metrics = capture["metrics"]
    return {
        "identity": {
            "publication": capture["publication"],
            "viewport": capture["viewport"],
            "checkpoint": capture["checkpoint"],
            "actionIndex": capture["actionIndex"],
            "resultSelector": capture["resultSelector"],
        },
        "state": capture["state"],
        "target": {
            "id": metrics["id"],
            "tag": metrics["tag"],
            "disabled": metrics["disabled"],
            "rendered": metrics["rendered"],
            "visible": metrics["visible"],
        },
        "playerGeometry": {
            "frameWidth": metrics["frameWidth"],
            "frameHeight": metrics["frameHeight"],
            "stageWidth": metrics["stageWidth"],
            "stageHeight": metrics["stageHeight"],
            "outerViewportWidth": metrics["outerViewportWidth"],
        },
        "visibilityContract": {
            "widthSatisfied": (
                metrics["visibleWidth"] >= metrics["requiredWidth"]
            ),
            "heightSatisfied": (
                metrics["visibleHeight"] >= metrics["requiredHeight"]
            ),
        },
        "overflowPolicy": {
            "htmlOverflowY": metrics["htmlOverflowY"],
            "bodyOverflowY": metrics["bodyOverflowY"],
            "scrollbarGutter": metrics["scrollbarGutter"],
            "pageScrolls": (
                metrics["outerScrollHeight"]
                > metrics["outerClientHeight"]
            ),
        },
        "screenshot": {
            "path": capture["screenshot"]["path"],
            "width": capture["screenshot"]["width"],
            "height": capture["screenshot"]["height"],
        },
    }


def semantic_capture_mismatches(committed, generated):
    expected = semantic_capture_contract(committed)
    actual = semantic_capture_contract(generated)
    mismatches = []

    def compare(expected_value, actual_value, path):
        if isinstance(expected_value, dict) and isinstance(actual_value, dict):
            for key in sorted(set(expected_value) | set(actual_value)):
                if key not in expected_value:
                    mismatches.append(f"{path}.{key}: unexpected")
                elif key not in actual_value:
                    mismatches.append(f"{path}.{key}: missing")
                else:
                    compare(
                        expected_value[key],
                        actual_value[key],
                        f"{path}.{key}",
                    )
        elif expected_value != actual_value:
            mismatches.append(
                f"{path}: committed={expected_value!r}, "
                f"generated={actual_value!r}"
            )

    compare(expected, actual, "capture")
    return mismatches


def resolve_browser() -> str | None:
    for environment_name in (
        "RAPP_BROWSER",
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
    for environment_name in (
        "RAPP_FFPROBE",
        "FFPROBE",
        "FFPROBE_PATH",
        "FRAME_FFPROBE",
    ):
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

    def test_full_suite_workflows_provision_release_tools(self):
        for filename in ("publication-policy.yml", "metrics.yml"):
            with self.subTest(workflow=filename):
                source = (
                    ROOT / ".github" / "workflows" / filename
                ).read_text(encoding="utf-8")
                self.assertIn("browser-actions/setup-chrome@v2", source)
                self.assertIn(
                    "apt-get install -y --no-install-recommends ffmpeg",
                    source,
                )
                self.assertIn(
                    "RAPP_BROWSER: ${{ steps.setup-chrome.outputs.chrome-path }}",
                    source,
                )
                self.assertIn("RAPP_FFMPEG: /usr/bin/ffmpeg", source)
                self.assertIn("RAPP_FFPROBE: /usr/bin/ffprobe", source)

    def test_release_tool_environment_precedes_path_shims(self):
        environment = {
            "RAPP_BROWSER": str(CHANNEL_PATH),
            "BROWSER": "",
            "CHROME_PATH": "",
            "CHROMIUM_PATH": "",
            "EDGE_PATH": "",
            "FRAME_BROWSER": "",
        }
        with (
            mock.patch.dict(os.environ, environment, clear=False),
            mock.patch.object(shutil, "which", return_value="/usr/bin/chromium"),
        ):
            self.assertEqual(resolve_browser(), str(CHANNEL_PATH.resolve()))

        with (
            mock.patch.dict(
                os.environ,
                {
                    "RAPP_FFPROBE": str(EVIDENCE_INDEX_PATH),
                    "FFPROBE": "",
                    "FFPROBE_PATH": "",
                    "FRAME_FFPROBE": "",
                },
                clear=False,
            ),
            mock.patch.object(shutil, "which", return_value="/usr/bin/ffprobe"),
        ):
            self.assertEqual(
                resolve_ffprobe(),
                str(EVIDENCE_INDEX_PATH.resolve()),
            )

    def test_player_semantic_actions_preserve_focus_and_clear_chrome(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn(
            "html{overflow-y:scroll;scrollbar-gutter:stable}",
            source,
        )
        self.assertIn("function keepLiveTargetAboveChrome(el)", source)
        self.assertIn('el.focus && el.focus({ preventScroll: true });', source)
        self.assertIn(
            'el.setRangeText(ch, el.selectionStart, el.selectionEnd, "end");',
            source,
        )
        self.assertIn(
            "requestAnimationFrame(() => keepLiveTargetAboveChrome(el));",
            source,
        )

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
            for spec in PUBLICATIONS
            for path in (
                spec.source_root / "channel.json",
                spec.source_root / "evidence.json",
                spec.source_root / "delivery.json",
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
        self.assertEqual(
            [
                (
                    winner.candidate_frame,
                    winner.source_directory,
                    winner.commission_id,
                    winner.publication_id,
                    winner.title,
                )
                for winner in BUILDER.WINNERS
            ],
            [
                (
                    spec.candidate_frame,
                    spec.source_directory,
                    spec.commission_id,
                    spec.publication_id,
                    spec.title,
                )
                for spec in PUBLICATIONS
            ],
        )

    def test_builder_rejects_candidate_path_escape_attempts(self):
        winner = BUILDER.WINNERS[-1]
        for reference in (
            "../outside.json",
            "../../outside.json",
            "%2e%2e/outside.json",
            r"..\outside.json",
        ):
            with self.subTest(reference=reference):
                with self.assertRaises(ValueError):
                    BUILDER.rebase_relative_url(reference, winner)
        self.assertEqual(
            BUILDER.rebase_relative_url(
                "https://example.test/proof.json",
                winner,
            ),
            "https://example.test/proof.json",
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
                (spec.publication_id, spec.title)
                for spec in PUBLICATIONS
            ],
        )
        self.assertEqual(len(self.channel["videos"]), 6)

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

        for spec, publication in zip(
            PUBLICATIONS,
            self.channel["videos"],
            strict=True,
        ):
            source_publication = load_json(
                spec.source_root / "channel.json"
            )["videos"][0]
            self.assertEqual(
                publication["live"]["scenes"][0]["actions"],
                source_publication["live"]["scenes"][0]["actions"],
            )
            self.assertEqual(
                publication["live"]["scenes"][0]["ready"],
                source_publication["live"]["scenes"][0]["ready"],
            )

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
        for spec in PUBLICATIONS:
            publication = next(
                item
                for item in self.channel["videos"]
                if item["id"] == spec.publication_id
            )
            references = [publication["thumb"]]
            references.extend(source["src"] for source in publication["sources"])
            references.extend(
                scene["app"]
                for scene in publication["live"]["scenes"]
                if "app" in scene
            )
            expected_root = spec.source_root.resolve()
            for reference in references:
                with self.subTest(
                    publication=spec.publication_id,
                    reference=reference,
                ):
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
            [spec.publication_id for spec in PUBLICATIONS],
        )

        for expected, record in zip(
            PUBLICATIONS,
            self.evidence_index["publications"],
            strict=True,
        ):
            with self.subTest(publication=expected.publication_id):
                self.assertEqual(
                    record["commission_id"],
                    expected.commission_id,
                )
                self.assertEqual(
                    record["publication_id"],
                    expected.publication_id,
                )
                source_root = resolve_reference(
                    EVIDENCE_INDEX_PATH,
                    record["source_candidate"],
                )
                self.assertEqual(
                    source_root,
                    expected.source_root.resolve(),
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
                self.assertEqual(
                    delivery["publication"],
                    expected.publication_id,
                )

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
        self.assertEqual(
            closed,
            {spec.commission_id for spec in PUBLICATIONS},
        )
        self.assertEqual(
            sum(
                commission["status"] == "open"
                for commission in commissions.values()
            ),
            6,
        )
        for spec in PUBLICATIONS:
            self.assertEqual(
                commissions[spec.commission_id]["fulfillment"],
                {
                    "result_channel": "working-proofs",
                    "publication_id": spec.publication_id,
                    "source_candidate": (
                        f"{spec.candidate_frame}/{spec.source_directory}"
                    ),
                },
            )

    def test_committed_screenshot_manifest_binds_every_runtime_source(self):
        manifest = load_json(SCREENSHOT_ROOT / "manifest.json")
        bindings = manifest["sourceBindings"]
        self.assertEqual(bindings["algorithm"], "sha256")
        self.assertEqual(bindings["pathBase"], "repository-root")
        self.assertEqual(bindings["player"]["path"], "index.html")
        self.assertEqual(
            bindings["aggregate"]["channel"]["path"],
            "working-proofs/channel.json",
        )
        self.assertEqual(
            bindings["aggregate"]["evidenceIndex"]["path"],
            "working-proofs/evidence-index.json",
        )
        self.assertEqual(
            [
                publication["publication"]
                for publication in bindings["publications"]
            ],
            [spec.publication_id for spec in PUBLICATIONS],
        )
        expected_paths = {
            "index.html",
            "working-proofs/channel.json",
            "working-proofs/evidence-index.json",
        }
        for spec, publication, binding in zip(
            PUBLICATIONS,
            self.channel["videos"],
            bindings["publications"],
            strict=True,
        ):
            expected_apps = [
                resolve_reference(CHANNEL_PATH, scene["app"])
                .relative_to(ROOT)
                .as_posix()
                for scene in publication["live"]["scenes"]
                if "app" in scene
            ]
            self.assertEqual(
                [item["path"] for item in binding["apps"]],
                list(dict.fromkeys(expected_apps)),
            )
            self.assertEqual(
                binding["sourceChannel"]["path"],
                (spec.source_root / "channel.json")
                .relative_to(ROOT)
                .as_posix(),
            )
            self.assertEqual(
                binding["evidence"]["path"],
                (spec.source_root / "evidence.json")
                .relative_to(ROOT)
                .as_posix(),
            )
            expected_paths.update(expected_apps)
            expected_paths.add(binding["sourceChannel"]["path"])
            expected_paths.add(binding["evidence"]["path"])

        self.assertEqual(
            {binding["path"] for binding in manifest_source_bindings(manifest)},
            expected_paths,
        )
        self.assertEqual(source_binding_errors(manifest), [])
        eol = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "ls-files",
                "--eol",
                "--",
                "index.html",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=clean_git_environment(),
        ).stdout
        self.assertIn("i/lf", eol)
        self.assertIn("w/lf", eol)
        self.assertIn("attr/text eol=lf", eol)

        stale = json.loads(json.dumps(manifest))
        stale["sourceBindings"]["player"]["sha256"] = "0" * 64
        stale["sourceBindings"]["publications"][0]["apps"][0][
            "sha256"
        ] = "f" * 64
        self.assertEqual(
            set(source_binding_errors(stale)),
            {
                "index.html",
                stale["sourceBindings"]["publications"][0]["apps"][0][
                    "path"
                ],
            },
        )

    def test_semantic_capture_contract_ignores_only_platform_layout_metrics(self):
        committed = load_json(SCREENSHOT_ROOT / "manifest.json")[
            "captures"
        ][0]
        platform_variant = json.loads(json.dumps(committed))
        for field in (
            "left",
            "top",
            "right",
            "bottom",
            "width",
            "height",
            "visibleWidth",
            "visibleHeight",
            "outerScrollHeight",
            "outerClientHeight",
            "safeHeight",
            "lowerThirdHeight",
        ):
            platform_variant["metrics"][field] += 3
        if platform_variant["metrics"]["outerScrollbarWidth"]:
            platform_variant["metrics"]["outerScrollbarWidth"] = 0
            platform_variant["metrics"]["outerClientWidth"] += 15
        else:
            platform_variant["metrics"]["outerScrollbarWidth"] = 15
            platform_variant["metrics"]["outerClientWidth"] -= 15
        self.assertEqual(
            semantic_capture_mismatches(committed, platform_variant),
            [],
        )

        threshold_variant = json.loads(json.dumps(committed))
        threshold_variant["metrics"]["requiredWidth"] += 3
        threshold_variant["metrics"]["requiredHeight"] += 2.125
        threshold_variant["metrics"]["visibleWidth"] = max(
            threshold_variant["metrics"]["visibleWidth"],
            threshold_variant["metrics"]["requiredWidth"],
        )
        threshold_variant["metrics"]["visibleHeight"] = max(
            threshold_variant["metrics"]["visibleHeight"],
            threshold_variant["metrics"]["requiredHeight"],
        )
        self.assertTrue(committed["metrics"]["visible"])
        self.assertTrue(threshold_variant["metrics"]["visible"])
        self.assertEqual(
            semantic_capture_mismatches(committed, threshold_variant),
            [],
        )

        mutations = {
            "frame width": (
                "capture.playerGeometry.frameWidth",
                lambda capture: capture["metrics"].__setitem__(
                    "frameWidth",
                    capture["metrics"]["frameWidth"] + 1,
                ),
            ),
            "stage width": (
                "capture.playerGeometry.stageWidth",
                lambda capture: capture["metrics"].__setitem__(
                    "stageWidth",
                    capture["metrics"]["stageWidth"] + 1,
                ),
            ),
            "screenshot width": (
                "capture.screenshot.width",
                lambda capture: capture["screenshot"].__setitem__(
                    "width",
                    capture["screenshot"]["width"] + 1,
                ),
            ),
            "hidden state": (
                "capture.target.rendered",
                lambda capture: capture["metrics"].__setitem__(
                    "rendered",
                    False,
                ),
            ),
            "visible state": (
                "capture.target.visible",
                lambda capture: capture["metrics"].__setitem__(
                    "visible",
                    False,
                ),
            ),
            "state hash": (
                "capture.state.actualSha256",
                lambda capture: capture["state"].__setitem__(
                    "actualSha256",
                    "0" * 64,
                ),
            ),
            "insufficient visibility": (
                "capture.visibilityContract.heightSatisfied",
                lambda capture: capture["metrics"].__setitem__(
                    "visibleHeight",
                    capture["metrics"]["requiredHeight"] - 1,
                ),
            ),
            "wrong checkpoint": (
                "capture.identity.checkpoint",
                lambda capture: capture.__setitem__(
                    "checkpoint",
                    "wrong-checkpoint",
                ),
            ),
        }
        for label, (field, mutate) in mutations.items():
            candidate = json.loads(json.dumps(committed))
            mutate(candidate)
            with self.subTest(change=label):
                mismatches = semantic_capture_mismatches(
                    committed,
                    candidate,
                )
                self.assertTrue(mismatches)
                self.assertTrue(
                    any(field in mismatch for mismatch in mismatches),
                    mismatches,
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

    def run_json(
        self,
        command: list[str],
        profile: Path,
        *,
        timeout: int = 120,
    ):
        shutil.rmtree(profile, ignore_errors=True)
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
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

    def source_spec(self, publication_id: str) -> PublicationSpec:
        return next(
            spec
            for spec in PUBLICATIONS
            if spec.publication_id == publication_id
        )

    def source_channel_path(self, publication_id: str) -> Path:
        return resolve_reference(
            EVIDENCE_INDEX_PATH,
            self.index[publication_id]["source_channel"]["path"],
        )

    def test_all_six_aggregate_live_replays_execute_in_real_browser(self):
        grid_id = "learn-grid-overflow"
        grid_profile = WORKING_ROOT / ".browser-grid"
        grid = self.run_json(
            [
                NODE,
                str(self.source_spec(grid_id).source_root / "verify_dom.mjs"),
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
        keyboard_profile = WORKING_ROOT / ".browser-keyboard"
        keyboard = self.run_json(
            [
                NODE,
                str(
                    self.source_spec(keyboard_id).source_root
                    / "verify_dom.mjs"
                ),
                "--browser",
                BROWSER,
                "--app",
                str(self.aggregate_app(keyboard_id)),
                "--evidence",
                str(self.evidence_path(keyboard_id)),
                "--manifest",
                str(self.source_channel_path(keyboard_id)),
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

        island_id = "ecosystem-island-threshold"
        island_profile = (
            self.source_spec(island_id).source_root
            / ".working-proofs-browser-profile"
        )
        island = self.run_json(
            [
                NODE,
                str(self.source_spec(island_id).source_root / "verify_dom.mjs"),
                "--browser",
                BROWSER,
                "--app",
                str(self.aggregate_app(island_id)),
                "--evidence",
                str(self.evidence_path(island_id)),
                "--manifest",
                str(self.source_channel_path(island_id)),
                "--profile",
                str(island_profile),
            ],
            island_profile,
        )
        self.assertEqual(island["browserErrors"], 0)
        self.assertEqual(island["externalRequests"], 0)
        self.assertEqual(island["actionCount"], 23)
        self.assertEqual(island["replayedWidths"], [1120, 390])
        self.assertEqual(
            island["checkpoints"],
            ["stable", "collapse", "export", "reset", "your-turn"],
        )
        self.assertEqual(
            island["responsiveCheckpoints"],
            island["checkpoints"],
        )
        self.assertEqual(island["stableFinal"], 112)
        self.assertEqual(island["collapseCrossingTick"], 134)
        self.assertEqual(island["collapseFinal"], 8)
        self.assertEqual(island["canonicalExportPointCount"], 601)
        self.assertEqual(island["canonicalExportDigest"], "8bb46765")
        self.assertTrue(island["exportCleanedOnReset"])
        self.assertTrue(island["profileCleaned"])

        wetland_id = "explore-archive-map-contrast"
        wetland_profile = WORKING_ROOT / ".browser-wetland"
        wetland = self.run_json(
            [
                NODE,
                str(
                    self.source_spec(wetland_id).source_root
                    / "verify_dom.mjs"
                ),
                "--browser",
                BROWSER,
                "--app",
                str(self.aggregate_app(wetland_id)),
                "--evidence",
                str(self.evidence_path(wetland_id)),
                "--manifest",
                str(self.source_channel_path(wetland_id)),
                "--profile",
                str(wetland_profile),
            ],
            wetland_profile,
        )
        self.assertEqual(wetland["browserErrors"], 0)
        self.assertEqual(wetland["externalNetworkRequests"], 0)
        self.assertEqual(wetland["blockedExternalRequests"], 0)
        self.assertEqual(wetland["actionCount"], 25)
        self.assertEqual(
            wetland["viewports"],
            ["desktop", "mobile-390"],
        )
        self.assertTrue(wetland["exactTiming"])
        self.assertEqual(wetland["recordCount"], 24)
        self.assertEqual(wetland["changedCount"], 7)
        self.assertEqual(wetland["failureStatus"], "rejected-empty")
        self.assertIsNone(wetland["failureResultCount"])
        self.assertEqual(wetland["failureExportStatus"], "preserved")
        self.assertEqual(wetland["resetVisibleCount"], 24)
        self.assertIsNone(wetland["resetFocus"])
        self.assertEqual(
            wetland["resetView"],
            {"panX": 0, "panY": 0, "zoom": 1},
        )
        self.assertEqual(
            wetland["cleanup"],
            {"browserExited": True, "profileRemoved": True},
        )

        fogline_id = "maze-fogline"
        fogline_profile = WORKING_ROOT / ".browser-fogline"
        fogline = self.run_json(
            [
                NODE,
                str(
                    self.source_spec(fogline_id).source_root
                    / "verify_dom.mjs"
                ),
                "--browser",
                BROWSER,
                "--app",
                str(self.aggregate_app(fogline_id)),
                "--evidence",
                str(self.evidence_path(fogline_id)),
                "--manifest",
                str(
                    self.source_spec(fogline_id).source_root
                    / "channel.production.json"
                ),
                "--continuity",
                str(
                    self.source_spec(fogline_id).source_root
                    / "snapshots"
                    / "film-live-continuity.json"
                ),
                "--profile",
                str(fogline_profile),
            ],
            fogline_profile,
            timeout=300,
        )
        self.assertEqual(
            fogline["schema"],
            "fogline-survey-browser-verifier/1.0",
        )
        self.assertTrue(all(fogline["checks"].values()), fogline["checks"])
        self.assertEqual(
            fogline["globalErrors"],
            {
                "externalRequests": [],
                "networkFailures": [],
                "exceptions": [],
                "console": [],
            },
        )
        self.assertEqual(
            [
                len(viewport["actionReports"])
                for viewport in fogline["viewports"]
            ],
            [71, 71],
        )
        self.assertEqual(
            [
                [
                    checkpoint["claim"]
                    for checkpoint in viewport["checkpointReports"]
                ]
                for viewport in fogline["viewports"]
            ],
            [EXPECTED_CHECKPOINTS[fogline_id]] * 2,
        )
        for viewport in fogline["viewports"]:
            self.assertEqual(viewport["authoredFinal"]["seed"], "FOG-7")
            self.assertEqual(viewport["authoredFinal"]["steps"], 0)
            self.assertEqual(viewport["takeover"]["firstDirection"], "E")
            self.assertEqual(viewport["takeover"]["movedSteps"], 1)

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
                timeout=300,
            )
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["externalRequests"], [])
            self.assertEqual(result["networkErrors"], [])
            self.assertEqual(
                result["cleanup"],
                {
                    "browserExited": True,
                    "profileRemoved": True,
                    "serverClosed": True,
                },
            )
            self.assertEqual(result["captures"], EXPECTED_CAPTURE_COUNT)
            self.assertEqual(len(result["runs"]), 12)

            for run in result["runs"]:
                with self.subTest(
                    publication=run["publication"],
                    viewport=run["viewport"],
                ):
                    self.assertEqual(
                        run["actionCount"],
                        EXPECTED_ACTION_COUNTS[run["publication"]],
                    )
                    self.assertEqual(
                        run["checkpoints"],
                        EXPECTED_CHECKPOINTS[run["publication"]],
                    )
                    self.assertEqual(
                        run["captureCheckpoints"],
                        EXPECTED_CAPTURE_CHECKPOINTS[
                            run["publication"]
                        ],
                    )
                    actions = self.publications[run["publication"]][
                        "live"
                    ]["scenes"][0]["actions"]
                    self.assertEqual(
                        run["activationsChecked"],
                        sum(
                            action["do"] != "scroll"
                            for action in actions
                        ),
                    )
                    self.assertEqual(
                        run["framingActionsChecked"],
                        sum(
                            action["do"] == "scroll"
                            for action in actions
                        ),
                    )
                    self.assertEqual(
                        run["finalPromptChecked"],
                        run["publication"] == "explore-archive-map-contrast",
                    )
                    if run["publication"] == "maze-fogline":
                        self.assertEqual(
                            run["inputMethods"],
                            [
                                "cdp-keyboard",
                                "cdp-mouse",
                                "cdp-scroll",
                            ],
                        )
                        self.assertEqual(
                            run["supplementalGeometryChecks"],
                            5,
                        )
                    else:
                        self.assertEqual(
                            run["inputMethods"],
                            ["dom-events"],
                        )
                        self.assertEqual(
                            run["supplementalGeometryChecks"],
                            0,
                        )
                    self.assertTrue(run["exactTiming"])
                    self.assertGreaterEqual(run["maxTimingSkewMs"], 0)
                    self.assertLess(run["maxTimingSkewMs"], 1000)
                    geometry = EXPECTED_VIEWPORT_GEOMETRY[run["viewport"]]
                    self.assertEqual(
                        run["geometryChecks"],
                        1
                        + len(actions)
                        + len(run["checkpoints"])
                        + int(run["finalPromptChecked"]),
                    )
                    self.assertEqual(
                        run["frameWidthsChecked"],
                        [geometry["frameWidth"]],
                    )
                    self.assertEqual(
                        run["stageWidthsChecked"],
                        [geometry["stageWidth"]],
                    )
                    self.assertTrue(
                        set(run["outerClientWidthsChecked"])
                        <= set(geometry["outerClientWidths"]),
                        run,
                    )
                    self.assertTrue(
                        set(run["scrollbarWidthsChecked"])
                        <= set(geometry["scrollbarWidths"]),
                        run,
                    )
                    self.assertEqual(
                        run["frameWidth"],
                        geometry["frameWidth"],
                    )
                    self.assertTrue(
                        all(height > 0 for height in run["safeHeight"]),
                        run,
                    )
                    if run["publication"] != "maze-fogline":
                        self.assertIsNone(run["takeover"])
                        continue

                    takeover = run["takeover"]
                    self.assertEqual(
                        takeover["restoredBy"],
                        ["Show captions", "Escape"],
                    )
                    self.assertEqual(
                        takeover["eastMove"],
                        {
                            "direction": "E",
                            "code": "KeyD",
                            "position": [1, 0],
                            "steps": 1,
                        },
                    )
                    self.assertEqual(
                        takeover["entered"]["lowerDisplay"],
                        "none",
                    )
                    self.assertEqual(
                        takeover["entered"]["replayDisplay"],
                        "none",
                    )
                    self.assertGreaterEqual(
                        takeover["entered"]["button"]["height"],
                        44,
                    )
                    self.assertGreaterEqual(
                        takeover["entered"]["toolbar"]["height"],
                        52,
                    )
                    self.assertGreaterEqual(
                        takeover["entered"]["toolbar"]["top"],
                        takeover["entered"]["frame"]["bottom"],
                    )
                    self.assertAlmostEqual(
                        takeover["entered"]["frame"]["width"],
                        geometry["frameWidth"],
                        delta=0.5,
                    )
                    self.assertGreaterEqual(
                        takeover["entered"]["frame"]["height"],
                        600 if run["viewport"] == "390" else 520,
                    )
                    self.assertAlmostEqual(
                        takeover["clock"]["entered"],
                        takeover["clock"]["after700ms"],
                        delta=0.01,
                    )
                    self.assertAlmostEqual(
                        takeover["clock"]["entered"],
                        takeover["clock"]["afterEast"],
                        delta=0.01,
                    )
                    self.assertEqual(
                        takeover["appRequestsBefore"],
                        takeover["appRequestsAfter"],
                    )
                    self.assertEqual(
                        takeover["preserved"],
                        {
                            "marker": (
                                f"fogline-{run['viewport']}"
                            ),
                            "stateAfterShowCaptions": True,
                            "timeOrigin": True,
                        },
                    )

            generated_manifest = load_json(scratch / "manifest.json")
            self.assertEqual(
                generated_manifest["schema"],
                "working-proofs-viewport-evidence/1.1",
            )
            self.assertEqual(generated_manifest["channel"], "working-proofs")
            self.assertEqual(
                generated_manifest["viewports"],
                [
                    {"id": name, **geometry}
                    for name, geometry in EXPECTED_VIEWPORT_GEOMETRY.items()
                ],
            )
            self.assertEqual(
                len(generated_manifest["captures"]),
                EXPECTED_CAPTURE_COUNT,
            )
            for viewport in EXPECTED_VIEWPORT_GEOMETRY:
                for publication_id, checkpoints in (
                    EXPECTED_CAPTURE_CHECKPOINTS.items()
                ):
                    self.assertEqual(
                        [
                            capture["checkpoint"]
                            for capture in generated_manifest["captures"]
                            if (
                                capture["publication"] == publication_id
                                and capture["viewport"] == viewport
                            )
                        ],
                        checkpoints,
                    )
            for capture in generated_manifest["captures"]:
                screenshot = scratch / capture["screenshot"]["path"]
                with self.subTest(
                    publication=capture["publication"],
                    viewport=capture["viewport"],
                    checkpoint=capture["checkpoint"],
                ):
                    self.assertTrue(capture["metrics"]["visible"])
                    self.assertGreaterEqual(
                        capture["metrics"]["visibleWidth"],
                        capture["metrics"]["requiredWidth"],
                    )
                    self.assertGreaterEqual(
                        capture["metrics"]["visibleHeight"],
                        capture["metrics"]["requiredHeight"],
                    )
                    self.assertEqual(
                        capture["state"]["actualSha256"],
                        capture["state"]["expectedSha256"],
                    )
                    geometry = EXPECTED_VIEWPORT_GEOMETRY[
                        capture["viewport"]
                    ]
                    self.assertEqual(
                        capture["metrics"]["frameWidth"],
                        geometry["frameWidth"],
                    )
                    self.assertEqual(
                        capture["metrics"]["frameHeight"],
                        geometry["frameHeight"],
                    )
                    self.assertEqual(
                        capture["metrics"]["stageWidth"],
                        geometry["stageWidth"],
                    )
                    self.assertEqual(
                        capture["metrics"]["stageHeight"],
                        geometry["stageHeight"],
                    )
                    self.assertIn(
                        capture["metrics"]["outerClientWidth"],
                        geometry["outerClientWidths"],
                    )
                    self.assertIn(
                        capture["metrics"]["outerScrollbarWidth"],
                        geometry["scrollbarWidths"],
                    )
                    self.assertEqual(
                        png_dimensions(screenshot),
                        (
                            geometry["screenshotWidth"],
                            geometry["screenshotHeight"],
                        ),
                    )
                    self.assertEqual(
                        (
                            capture["screenshot"]["width"],
                            capture["screenshot"]["height"],
                        ),
                        (
                            geometry["screenshotWidth"],
                            geometry["screenshotHeight"],
                        ),
                    )

            committed_manifest = load_json(SCREENSHOT_ROOT / "manifest.json")
            self.assertEqual(
                committed_manifest["sourceBindings"],
                generated_manifest["sourceBindings"],
            )
            self.assertEqual(
                source_binding_errors(generated_manifest),
                [],
            )
            self.assertEqual(
                source_binding_errors(committed_manifest),
                [],
            )
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
            self.assertEqual(
                len(committed_manifest["captures"]),
                EXPECTED_CAPTURE_COUNT,
            )
            for committed, generated in zip(
                committed_manifest["captures"],
                generated_manifest["captures"],
                strict=True,
            ):
                mismatches = semantic_capture_mismatches(
                    committed,
                    generated,
                )
                self.assertEqual(
                    mismatches,
                    [],
                    (
                        f"{generated['screenshot']['path']}: "
                        + "; ".join(mismatches)
                    ),
                )
            for capture in committed_manifest["captures"]:
                screenshot = SCREENSHOT_ROOT / capture["screenshot"]["path"]
                with self.subTest(committed=capture["screenshot"]["path"]):
                    self.assertTrue(screenshot.is_file())
                    self.assertTrue(capture["metrics"]["visible"])
                    self.assertGreaterEqual(
                        capture["metrics"]["visibleWidth"],
                        capture["metrics"]["requiredWidth"],
                    )
                    self.assertGreaterEqual(
                        capture["metrics"]["visibleHeight"],
                        capture["metrics"]["requiredHeight"],
                    )
                    self.assertGreater(
                        capture["metrics"]["outerScrollHeight"],
                        capture["metrics"]["outerClientHeight"],
                    )
                    self.assertEqual(
                        capture["screenshot"]["sha256"],
                        sha256(screenshot),
                    )
                    self.assertEqual(
                        capture["screenshot"]["bytes"],
                        screenshot.stat().st_size,
                    )
                    self.assertEqual(
                        capture["state"]["actualSha256"],
                        capture["state"]["expectedSha256"],
                    )
                    geometry = EXPECTED_VIEWPORT_GEOMETRY[
                        capture["viewport"]
                    ]
                    self.assertEqual(
                        capture["metrics"]["frameWidth"],
                        geometry["frameWidth"],
                    )
                    self.assertEqual(
                        capture["metrics"]["frameHeight"],
                        geometry["frameHeight"],
                    )
                    self.assertEqual(
                        capture["metrics"]["stageWidth"],
                        geometry["stageWidth"],
                    )
                    self.assertEqual(
                        capture["metrics"]["stageHeight"],
                        geometry["stageHeight"],
                    )
                    self.assertIn(
                        capture["metrics"]["outerClientWidth"],
                        geometry["outerClientWidths"],
                    )
                    self.assertIn(
                        capture["metrics"]["outerScrollbarWidth"],
                        geometry["scrollbarWidths"],
                    )
                    self.assertEqual(
                        png_dimensions(screenshot),
                        (
                            geometry["screenshotWidth"],
                            geometry["screenshotHeight"],
                        ),
                    )
                    self.assertEqual(
                        (
                            capture["screenshot"]["width"],
                            capture["screenshot"]["height"],
                        ),
                        (
                            geometry["screenshotWidth"],
                            geometry["screenshotHeight"],
                        ),
                    )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
