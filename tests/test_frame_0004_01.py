"""Release-grade checks for candidate frame 0004-01, Fogline Survey."""

from __future__ import annotations

import ast
import base64
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
from collections import deque
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate-frame-0004" / "maze-fogline"
PUBLICATION_ID = "maze-fogline"
CHANNEL_ID = "candidate-frame-0004-01-maze-fogline"
APP_PATH = CANDIDATE / "apps" / f"{PUBLICATION_ID}.html"
MANIFEST_PATH = CANDIDATE / "channel.production.json"
CHANNEL_PATH = CANDIDATE / "channel.json"
EVIDENCE_PATH = CANDIDATE / "evidence.json"
DELIVERY_PATH = CANDIDATE / "delivery.json"
RENDERER_PATH = CANDIDATE / "render.py"
VERIFY_PATH = CANDIDATE / "verify_dom.mjs"
LIVE_RENDERER_PATH = CANDIDATE / "render_live.mjs"
SNAPSHOT_PATH = CANDIDATE / "snapshots" / "canonical-states.json"
CONTINUITY_PATH = CANDIDATE / "snapshots" / "film-live-continuity.json"
THUMB_PATH = CANDIDATE / "thumbs" / f"{PUBLICATION_ID}.svg"
MASTER_PATH = CANDIDATE / "masters" / f"{PUBLICATION_ID}.mkv"
MP4_PATH = CANDIDATE / "media" / f"{PUBLICATION_ID}.mp4"
WEBM_PATH = CANDIDATE / "media" / f"{PUBLICATION_ID}.webm"
COMPILER_PATH = ROOT / "scripts" / "compile_publications.py"
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
POLICY_PATH = ROOT / "policy" / "legacy-publications.json"

EXPECTED_DIGEST = (
    "126bf70440d3ef542c8dc97251726994e0f23422675e831f93309235ae085eda"
)
EXPECTED_ROUTE = tuple("SEESSWWSSENEESENNE")
EXPECTED_DETOUR = tuple("SEESSWWSSENEESWEENNE")
ALTERNATE_SEEDS = ("FOG-7", "MIST-Δ", "A|B;C")
EXPECTED_FULFILLMENT = {
    "result_channel": "working-proofs",
    "publication_id": PUBLICATION_ID,
    "source_candidate": "candidate-frame-0004/maze-fogline",
}


def normalized_text(path: Path) -> str:
    return (
        path.read_text(encoding="utf-8")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def load_json(path: Path):
    return json.loads(normalized_text(path))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RENDERER = load_module("frame_0004_01_renderer", RENDERER_PATH)
COMPILER = load_module("frame_0004_01_compiler", COMPILER_PATH)
VALIDATOR = load_module("frame_0004_01_validator", VALIDATOR_PATH)


def optional_tool(name: str) -> str | None:
    try:
        return RENDERER.discover_executable(name)
    except RuntimeError:
        return None


FFMPEG = optional_tool("ffmpeg")
FFPROBE = optional_tool("ffprobe")
NODE = shutil.which("node")


def browser_candidate(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().strip('"')
    resolved = shutil.which(candidate)
    if resolved:
        candidate = resolved
    path = Path(candidate).expanduser()
    if path.is_file() and re.search(
        r"(chrome|chromium|edge|brave)",
        path.name,
        flags=re.IGNORECASE,
    ):
        return str(path.resolve())
    return None


def discover_browser() -> str | None:
    for variable in (
        "RAPP_BROWSER",
        "RAPP_VISION_BROWSER",
        "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH",
        "EDGE_BIN",
        "CHROME_BIN",
        "CHROMIUM_BIN",
    ):
        found = browser_candidate(os.environ.get(variable))
        if found:
            return found
    for command in (
        "msedge",
        "microsoft-edge",
        "google-chrome",
        "chromium",
        "brave-browser",
    ):
        found = browser_candidate(command)
        if found:
            return found
    if os.name == "nt":
        roots = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        for root in filter(None, roots):
            for relative in (
                Path("Microsoft") / "Edge" / "Application" / "msedge.exe",
                Path("Google") / "Chrome" / "Application" / "chrome.exe",
                Path("Chromium") / "Application" / "chrome.exe",
                Path("BraveSoftware")
                / "Brave-Browser"
                / "Application"
                / "brave.exe",
            ):
                found = browser_candidate(str(Path(root) / relative))
                if found:
                    return found
    return None


BROWSER = discover_browser()


DIRECTIONS = (
    ("N", 0, -1, "S"),
    ("E", 1, 0, "W"),
    ("S", 0, 1, "N"),
    ("W", -1, 0, "E"),
)
VECTOR = {direction: (dx, dy) for direction, dx, dy, _ in DIRECTIONS}
OPPOSITE = {
    direction: opposite
    for direction, _dx, _dy, opposite in DIRECTIONS
}


def independent_fnv1a(value: str) -> int:
    result = 0x811C9DC5
    for byte in value.encode("utf-8"):
        result ^= byte
        result = (result * 0x01000193) & 0xFFFFFFFF
    return result


class IndependentMulberry32:
    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFF

    def next(self) -> int:
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        value = self.state
        value = ((value ^ (value >> 15)) * (value | 1)) & 0xFFFFFFFF
        mixed = ((value ^ (value >> 7)) * (value | 61)) & 0xFFFFFFFF
        value ^= (value + mixed) & 0xFFFFFFFF
        return (value ^ (value >> 14)) & 0xFFFFFFFF


def independent_step(cell: tuple[int, int], direction: str) -> tuple[int, int]:
    dx, dy = VECTOR[direction]
    return cell[0] + dx, cell[1] + dy


def independent_maze(seed: str) -> dict[tuple[int, int], set[str]]:
    random = IndependentMulberry32(independent_fnv1a(seed))
    maze = {
        (x, y): set()
        for y in range(6)
        for x in range(6)
    }
    visited = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        x, y = stack[-1]
        candidates = []
        for direction, dx, dy, opposite in DIRECTIONS:
            neighbor = (x + dx, y + dy)
            if (
                0 <= neighbor[0] < 6
                and 0 <= neighbor[1] < 6
                and neighbor not in visited
            ):
                candidates.append((direction, opposite, neighbor))
        if not candidates:
            stack.pop()
            continue
        direction, opposite, neighbor = candidates[
            random.next() % len(candidates)
        ]
        maze[(x, y)].add(direction)
        maze[neighbor].add(opposite)
        visited.add(neighbor)
        stack.append(neighbor)
    return maze


def independent_signature(
    maze: dict[tuple[int, int], set[str]],
    seed: str,
) -> str:
    cells = []
    for y in range(6):
        for x in range(6):
            openings = "".join(
                direction
                for direction in "NESW"
                if direction in maze[(x, y)]
            )
            cells.append(f"{x},{y}:{openings}")
    return f"{seed}|6x6|" + ";".join(cells)


def independent_bfs(
    maze: dict[tuple[int, int], set[str]],
    start: tuple[int, int] = (0, 0),
    finish: tuple[int, int] = (5, 3),
) -> tuple[str, ...]:
    queue = deque([start])
    previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    moves: dict[tuple[int, int], str] = {}
    while queue:
        cell = queue.popleft()
        if cell == finish:
            break
        for direction in "NESW":
            if direction not in maze[cell]:
                continue
            neighbor = independent_step(cell, direction)
            if neighbor in previous:
                continue
            previous[neighbor] = cell
            moves[neighbor] = direction
            queue.append(neighbor)
    if finish not in previous:
        raise AssertionError("independent BFS found no exit")
    route = []
    cursor = finish
    while cursor != start:
        route.append(moves[cursor])
        parent = previous[cursor]
        if parent is None:
            raise AssertionError("invalid independent BFS parent")
        cursor = parent
    return tuple(reversed(route))


def independent_positions(
    route: tuple[str, ...],
) -> tuple[tuple[int, int], ...]:
    positions = [(0, 0)]
    for direction in route:
        positions.append(independent_step(positions[-1], direction))
    return tuple(positions)


def independent_trap(
    maze: dict[tuple[int, int], set[str]],
    route: tuple[str, ...],
) -> dict[str, object]:
    positions = independent_positions(route)
    route_cells = set(positions)
    for index in range(len(positions) - 2, -1, -1):
        for direction in "NESW":
            if direction not in maze[positions[index]]:
                continue
            neighbor = independent_step(positions[index], direction)
            if neighbor not in route_cells:
                return {
                    "approachIndex": index,
                    "approach": positions[index],
                    "turn": direction,
                    "cell": neighbor,
                    "return": OPPOSITE[direction],
                }
    index = max(1, len(route) // 2)
    return {
        "approachIndex": index,
        "approach": positions[index],
        "turn": OPPOSITE[route[index - 1]],
        "cell": positions[index - 1],
        "return": route[index - 1],
    }


def independent_fixture(seed: str) -> dict[str, object]:
    maze = independent_maze(seed)
    signature = independent_signature(maze, seed)
    route = independent_bfs(maze)
    trap = independent_trap(maze, route)
    detour = (
        route[: trap["approachIndex"]]
        + (trap["turn"], trap["return"])
        + route[trap["approachIndex"] :]
    )
    return {
        "maze": maze,
        "signature": signature,
        "digest": hashlib.sha256(signature.encode("utf-8")).hexdigest(),
        "route": route,
        "trap": trap,
        "detour": detour,
    }


def validate_perfect_maze(
    maze: dict[tuple[int, int], set[str]],
) -> None:
    edge_count = sum(len(openings) for openings in maze.values()) // 2
    if edge_count != 35:
        raise AssertionError(f"expected 35 edges, found {edge_count}")
    for cell, openings in maze.items():
        for direction in openings:
            neighbor = independent_step(cell, direction)
            if OPPOSITE[direction] not in maze[neighbor]:
                raise AssertionError(f"nonreciprocal {cell} {direction}")
    queue = deque([(0, 0)])
    visited = {(0, 0)}
    while queue:
        cell = queue.popleft()
        for direction in maze[cell]:
            neighbor = independent_step(cell, direction)
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    if len(visited) != 36:
        raise AssertionError(f"only {len(visited)} connected cells")


class AppIndex(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.resources: list[tuple[str, str]] = []
        self.visible_text: list[str] = []
        self.excluded_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.add(attributes["id"])
        for name in ("src", "href", "poster", "data"):
            if name in attributes:
                self.resources.append((tag, attributes[name]))
        if tag in {"script", "style", "template"}:
            self.excluded_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template"} and self.excluded_depth:
            self.excluded_depth -= 1

    def handle_data(self, data):
        if not self.excluded_depth:
            self.visible_text.append(data)


def route_from_actions(actions: list[dict], segment: dict) -> tuple[str, ...]:
    code_direction = {
        "ArrowUp": "N",
        "ArrowRight": "E",
        "ArrowDown": "S",
        "ArrowLeft": "W",
        "KeyW": "N",
        "KeyD": "E",
        "KeyS": "S",
        "KeyA": "W",
    }
    return tuple(
        code_direction[action["code"]]
        for action in actions[
            segment["firstAction"] - 1 : segment["lastAction"]
        ]
        if action["do"] == "key"
    )


def resolve_path(value, path: str):
    current = value
    for part in path.split("."):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def decode_rgb_samples(
    path: Path,
    indexes: list[int],
    ffmpeg: str,
) -> dict[int, bytes]:
    expression = "+".join(f"eq(n\\,{index})" for index in indexes)
    completed = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"select={expression},format=rgb24",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        check=False,
        capture_output=True,
        timeout=120,
    )
    if completed.returncode:
        raise AssertionError(completed.stderr.decode("utf-8", errors="replace"))
    frame_bytes = RENDERER.SPEC.width * RENDERER.SPEC.height * 3
    expected_bytes = frame_bytes * len(indexes)
    if len(completed.stdout) != expected_bytes:
        raise AssertionError(
            f"{path.name}: decoded {len(completed.stdout)}, "
            f"expected {expected_bytes}"
        )
    return {
        index: completed.stdout[offset * frame_bytes : (offset + 1) * frame_bytes]
        for offset, index in enumerate(indexes)
    }


def rgb_metrics(reference: bytes, actual: bytes) -> dict[str, float | int]:
    if len(reference) != len(actual):
        raise AssertionError("RGB sample lengths differ")
    total_absolute = 0
    total_squared = 0
    over_16 = 0
    maximum = 0
    for left, right in zip(reference, actual, strict=True):
        error = abs(left - right)
        total_absolute += error
        total_squared += error * error
        over_16 += error > 16
        maximum = max(maximum, error)
    count = len(reference)
    mse = total_squared / count
    psnr = math.inf if mse == 0 else 10 * math.log10((255 * 255) / mse)
    return {
        "mae": total_absolute / count,
        "psnr": psnr,
        "over16Fraction": over_16 / count,
        "maximumChannelError": maximum,
    }


class TestCommissionFixtureAndState(unittest.TestCase):
    def test_commission_is_exact_open_or_exact_future_fulfillment(self):
        commissions = load_json(ROOT / "commissions.json")["commissions"]
        commission = next(
            item
            for item in commissions
            if item["id"] == "play-seeded-maze-return"
        )
        def assert_compatible(document):
            self.assertEqual(document["category"], "play")
            self.assertEqual(
                document["gates"]["objective_evidence"]["criterion"],
                RENDERER.COMMISSION_CRITERION,
            )
            self.assertTrue(document["gates"]["paired_delivery"]["mp4"])
            self.assertTrue(document["gates"]["paired_delivery"]["webm"])
            self.assertTrue(document["gates"]["paired_delivery"]["live"])
            self.assertTrue(
                document["gates"]["paired_delivery"]["same_publication"]
            )
            self.assertTrue(document["gates"]["exact_reset"]["required"])
            if document["status"] == "open":
                self.assertNotIn("fulfillment", document)
            elif document["status"] == "closed":
                self.assertEqual(
                    document["fulfillment"],
                    EXPECTED_FULFILLMENT,
                )
            else:
                self.fail(
                    "commission must be exact open or future closed, not "
                    f"{document['status']!r}"
                )

        assert_compatible(commission)
        simulated_open = copy.deepcopy(commission)
        simulated_open["status"] = "open"
        simulated_open.pop("fulfillment", None)
        assert_compatible(simulated_open)
        simulated_closed = copy.deepcopy(commission)
        simulated_closed["status"] = "closed"
        simulated_closed["fulfillment"] = EXPECTED_FULFILLMENT
        assert_compatible(simulated_closed)

    def test_independent_canonical_generator_digest_bfs_and_trap_are_exact(self):
        fixture = independent_fixture("RAPP-42")
        validate_perfect_maze(fixture["maze"])
        self.assertEqual(independent_fnv1a("RAPP-42"), 2012980997)
        self.assertEqual(fixture["digest"], EXPECTED_DIGEST)
        self.assertEqual(fixture["route"], EXPECTED_ROUTE)
        self.assertEqual(len(fixture["route"]), 18)
        self.assertEqual(fixture["trap"]["approachIndex"], 14)
        self.assertEqual(fixture["trap"]["approach"], (3, 5))
        self.assertEqual(fixture["trap"]["turn"], "W")
        self.assertEqual(fixture["trap"]["cell"], (2, 5))
        self.assertEqual(fixture["trap"]["return"], "E")
        self.assertEqual(fixture["detour"], EXPECTED_DETOUR)
        self.assertEqual(len(fixture["detour"]), 20)
        self.assertEqual(
            independent_positions(fixture["route"])[-1],
            (5, 3),
        )
        self.assertEqual(
            independent_positions(fixture["detour"])[-1],
            (5, 3),
        )

    def test_renderer_matches_independent_arbitrary_seed_recomputation(self):
        for seed in ("RAPP-42", *ALTERNATE_SEEDS):
            with self.subTest(seed=seed):
                expected = independent_fixture(seed)
                validate_perfect_maze(expected["maze"])
                actual = RENDERER.build_fixture(seed)
                self.assertEqual(actual.topology_signature, expected["signature"])
                self.assertEqual(actual.topology_digest, expected["digest"])
                self.assertEqual(actual.shortest_route, expected["route"])
                self.assertEqual(actual.detour_route, expected["detour"])
                self.assertEqual(
                    actual.trap.approach_index,
                    expected["trap"]["approachIndex"],
                )
                self.assertEqual(actual.trap.cell, expected["trap"]["cell"])
                self.assertEqual(actual.trap.turn, expected["trap"]["turn"])
                cursor = actual.entrance
                for direction in actual.detour_route:
                    self.assertIn(direction, actual.maze[cursor])
                    cursor = RENDERER.step(cursor, direction)
                self.assertEqual(cursor, actual.exit)
                self.assertEqual(
                    len(actual.detour_route),
                    len(actual.shortest_route) + 2,
                )

    def test_invalid_seed_validation_is_strict_and_non_ambiguous(self):
        for seed in ("", "X" * 65, "line\nbreak", "\x7f"):
            with self.subTest(seed=repr(seed)):
                with self.assertRaises(ValueError):
                    RENDERER.build_fixture(seed)
        self.assertEqual(RENDERER.build_fixture(" ").seed, " ")
        self.assertEqual(RENDERER.build_fixture("Δ").seed, "Δ")

    def test_offline_challenge_contract_has_exactly_three_safe_fields(self):
        for seed in ("RAPP-42", "MIST-Δ"):
            fixture = RENDERER.build_fixture(seed)
            contract = RENDERER.challenge_contract(fixture)
            self.assertEqual(
                list(contract),
                ["seed", "topologyDigest", "referenceLength"],
            )
            self.assertEqual(contract["seed"], seed)
            self.assertEqual(contract["topologyDigest"], fixture.topology_digest)
            self.assertEqual(
                contract["referenceLength"],
                len(fixture.shortest_route),
            )
            self.assertNotIn("route", contract)
            self.assertNotIn("trail", contract)
            fragment = RENDERER.challenge_fragment(fixture)
            self.assertTrue(fragment.startswith("#challenge="))
            encoded = fragment.removeprefix("#challenge=")
            padding = "=" * ((4 - len(encoded) % 4) % 4)
            decoded = json.loads(
                base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
            )
            self.assertEqual(decoded, contract)

    def test_hint_trap_optimal_detour_and_exact_reset_states(self):
        states = RENDERER.canonical_states_document()
        self.assertEqual(load_json(SNAPSHOT_PATH), states)
        opening = states["opening"]
        self.assertEqual(opening["seed"], "RAPP-42")
        self.assertEqual(opening["topologyDigest"], EXPECTED_DIGEST)
        self.assertEqual(opening["position"], {"x": 0, "y": 0})
        self.assertEqual(opening["facing"], "N")
        self.assertEqual(opening["steps"], 0)
        self.assertEqual(opening["exit"]["state"], "closed")
        self.assertTrue(opening["exit"]["marked"])
        self.assertEqual(opening["trail"], [])
        self.assertFalse(opening["assistance"]["used"])
        self.assertEqual(states["reset"], opening)
        wall = states["wallRejected"]
        self.assertEqual(wall["steps"], 0)
        self.assertEqual(wall["trail"], [])
        self.assertFalse(wall["assistance"]["earned"])
        self.assertFalse(wall["assistance"]["available"])
        self.assertIsNone(wall["assistance"]["hintDirection"])
        self.assertEqual(wall["lastRejected"], "N")
        self.assertIn("hint charge", wall["message"])

        optimal = states["optimal"]
        self.assertEqual(optimal["steps"], 18)
        self.assertEqual(optimal["projectedTotal"], 18)
        self.assertEqual(optimal["exit"]["state"], "open")
        self.assertTrue(optimal["matchedOptimal"])
        self.assertFalse(optimal["assistance"]["used"])

        hint = states["hint"]
        self.assertEqual(hint["steps"], 14)
        self.assertTrue(hint["assistance"]["earned"])
        self.assertFalse(hint["assistance"]["available"])
        self.assertTrue(hint["assistance"]["used"])
        self.assertEqual(hint["assistance"]["requests"], 1)
        self.assertEqual(hint["assistance"]["hintDirection"], "E")
        self.assertTrue(hint["trap"]["marked"])

        trap = states["trap"]
        self.assertEqual(trap["position"], {"x": 2, "y": 5})
        self.assertEqual(trap["steps"], 15)
        self.assertEqual(trap["projectedTotal"], 20)
        self.assertTrue(trap["trap"]["entered"])
        self.assertEqual(trap["exit"]["state"], "closed")
        self.assertTrue(trap["exit"]["marked"])

        detour = states["detour"]
        self.assertEqual(detour["steps"], 20)
        self.assertEqual(detour["projectedTotal"], 20)
        self.assertEqual(detour["exit"]["state"], "open")
        self.assertFalse(detour["matchedOptimal"])
        self.assertTrue(detour["assistance"]["used"])

        invalid = states["invalidSeedPreserved"]
        preserved_fields = (
            "seed",
            "grid",
            "topologyDigest",
            "topologySignature",
            "position",
            "facing",
            "steps",
            "acceptedMoves",
            "referenceLength",
            "projectedTotal",
            "trail",
            "revealed",
            "status",
            "message",
            "completed",
            "exit",
            "trap",
            "assistance",
        )
        for field in preserved_fields:
            self.assertEqual(invalid[field], opening[field], field)
        self.assertEqual(invalid["seedInput"], "X" * 65)
        self.assertEqual(
            invalid["seedError"],
            RENDERER.INVALID_SEED_MESSAGE,
        )


class TestManifestEvidenceAndApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(MANIFEST_PATH)
        cls.channel = load_json(CHANNEL_PATH)
        cls.evidence = load_json(EVIDENCE_PATH)
        cls.delivery = load_json(DELIVERY_PATH)
        cls.continuity = load_json(CONTINUITY_PATH)
        cls.app_source = normalized_text(APP_PATH)
        cls.video = cls.manifest["videos"][0]

    def test_production_source_compiles_to_one_exact_paired_publication(self):
        self.assertEqual(self.manifest, RENDERER.production_document())
        self.assertEqual(self.manifest["schema"], "rapp-vision-production/1.0")
        self.assertEqual(self.manifest["id"], CHANNEL_ID)
        self.assertEqual(len(self.manifest["videos"]), 1)
        self.assertEqual(self.video["id"], PUBLICATION_ID)
        self.assertEqual(self.video["title"], "Fogline Survey")
        self.assertEqual(self.video["duration"], 24)
        self.assertGreaterEqual(self.video["duration"], 20)
        self.assertLessEqual(self.video["duration"], 24)
        self.assertEqual((self.video["width"], self.video["height"]), (960, 540))
        self.assertEqual(
            self.video["production"],
            {"master": "masters/maze-fogline.mkv"},
        )
        self.assertNotIn("sources", self.video)
        compilation = COMPILER.prepare_compilation(MANIFEST_PATH)
        self.assertEqual(self.channel, compilation.channel)
        self.assertEqual(
            self.channel["videos"][0]["sources"],
            [
                {"src": "media/maze-fogline.mp4", "type": "video/mp4"},
                {"src": "media/maze-fogline.webm", "type": "video/webm"},
            ],
        )
        policy = load_json(POLICY_PATH)
        self.assertEqual(
            VALIDATOR.validate_channel(
                self.channel,
                CHANNEL_PATH.resolve().as_uri(),
                policy,
            ),
            [],
        )

    def test_live_replay_uses_individual_semantic_keys_not_auto_solve(self):
        live = self.video["live"]
        self.assertEqual(live["kind"], "rapp-vision-live/1.0")
        self.assertEqual(live["duration"], 24)
        self.assertEqual(len(live["scenes"]), 1)
        scene = live["scenes"][0]
        self.assertEqual(scene["ready"], {
            "enabled": True,
            "selector": "#maze-board",
        })
        self.assertEqual(scene["app"], "apps/maze-fogline.html")
        actions = scene["actions"]
        replay = self.evidence["manifestReplay"]
        self.assertEqual(len(actions), replay["actionCount"])
        self.assertEqual(len(actions), 71)
        self.assertEqual(
            {action["do"] for action in actions},
            {"scroll", "click", "key", "type"},
        )
        self.assertEqual(
            [action["at"] for action in actions],
            sorted(action["at"] for action in actions),
        )
        self.assertTrue(replay["individualSemanticKeyEvents"])
        self.assertFalse(replay["autoSolveApi"])
        self.assertLess(
            replay["segments"]["detour"]["firstAction"],
            replay["segments"]["optimal"]["firstAction"],
        )
        self.assertEqual(
            route_from_actions(actions, replay["segments"]["optimal"]),
            EXPECTED_ROUTE,
        )
        self.assertEqual(
            route_from_actions(actions, replay["segments"]["detour"]),
            EXPECTED_DETOUR,
        )
        self.assertEqual(
            sum(action["do"] == "key" for action in actions),
            38,
        )
        for action in actions:
            self.assertLess(action["at"], scene["dur"])
            self.assertNotIn("from", action)
            self.assertNotIn("to", action)
            if action["do"] == "key":
                self.assertIn(
                    action["code"],
                    {"ArrowUp", "ArrowRight", "ArrowDown", "ArrowLeft"},
                )
                self.assertNotIn("selector", action)
            if action["do"] == "scroll":
                self.assertEqual(action["behavior"], "auto")
                self.assertIn(action["block"], {"center", "start"})
                self.assertRegex(action["selector"], r"^#[A-Za-z][\w-]*$")
            if action["do"] == "type":
                self.assertNotIn("selector", action)
        self.assertEqual(
            [action["text"] for action in actions if action["do"] == "type"],
            ["FOG-7"],
        )
        self.assertEqual(
            [checkpoint["claim"] for checkpoint in replay["checkpoints"]],
            [
                "hint",
                "trap",
                "detour",
                "resetAfterTrap",
                "optimal",
                "resetAfterOptimal",
                "handoff",
            ],
        )
        for checkpoint in replay["checkpoints"]:
            self.assertNotIn("afterAction", checkpoint)
            self.assertIn("stateGate", checkpoint)
            self.assertIn("timeWindow", checkpoint)
            self.assertLess(
                checkpoint["timeWindow"]["start"],
                checkpoint["timeWindow"]["end"],
            )
        self.assertEqual(replay["maxActionLatenessSeconds"], 0.8)
        self.assertEqual(
            replay["checkpointMode"],
            "state-gated within bounded time windows",
        )

    def test_evidence_is_renderer_exact_and_binds_every_replay_checkpoint(self):
        self.assertEqual(self.evidence, RENDERER.evidence_document(CANDIDATE))
        self.assertEqual(
            self.evidence["schema"],
            "fogline-survey-evidence/1.0",
        )
        self.assertEqual(
            self.evidence["fixtures"]["canonical"]["topologyDigest"],
            EXPECTED_DIGEST,
        )
        self.assertEqual(
            tuple(self.evidence["fixtures"]["canonical"]["shortestRoute"]),
            EXPECTED_ROUTE,
        )
        self.assertEqual(
            tuple(self.evidence["fixtures"]["canonical"]["detourRoute"]),
            EXPECTED_DETOUR,
        )
        alternates = self.evidence["fixtures"]["alternateAudit"]
        self.assertEqual(
            [fixture["seed"] for fixture in alternates],
            list(ALTERNATE_SEEDS),
        )
        for fixture in alternates:
            expected = independent_fixture(fixture["seed"])
            self.assertEqual(fixture["topologySignature"], expected["signature"])
            self.assertEqual(fixture["topologyDigest"], expected["digest"])
            self.assertEqual(
                tuple(fixture["shortestRoute"]),
                expected["route"],
            )
            self.assertEqual(tuple(fixture["detourRoute"]), expected["detour"])
        claims = {
            claim["id"]: claim["stateGate"]
            for claim in self.evidence["claims"]
        }
        self.assertEqual(
            set(claims),
            {
                "hint",
                "trap",
                "detour",
                "resetAfterTrap",
                "optimal",
                "resetAfterOptimal",
                "handoff",
            },
        )
        self.assertTrue(
            all("expectedState" not in claim for claim in self.evidence["claims"])
        )
        for checkpoint in self.evidence["manifestReplay"]["checkpoints"]:
            self.assertIn(checkpoint["claim"], claims)
            self.assertEqual(
                checkpoint["stateGate"],
                claims[checkpoint["claim"]],
            )
            self.assertRegex(checkpoint["selector"], r"^#[A-Za-z][\w-]*$")
        contract = self.evidence["challengeContract"]
        self.assertEqual(
            contract["keys"],
            ["seed", "topologyDigest", "referenceLength"],
        )
        self.assertEqual(
            contract["example"],
            RENDERER.challenge_contract(RENDERER.CANONICAL),
        )
        self.assertEqual(
            contract["fragment"],
            RENDERER.challenge_fragment(RENDERER.CANONICAL),
        )
        self.assertFalse(contract["routeIncluded"])
        self.assertFalse(contract["trailIncluded"])
        self.assertEqual(
            self.evidence["browserRuntime"]["viewports"],
            [
                {"height": 720, "name": "desktop", "width": 1120},
                {"height": 844, "name": "mobile", "width": 390},
            ],
        )
        self.assertTrue(
            self.evidence["browserRuntime"]["geometry"]["perAction"]
        )
        self.assertTrue(
            self.evidence["browserRuntime"]["geometry"]["perCheckpoint"]
        )
        self.assertFalse(
            self.evidence["browserRuntime"]["geometry"][
                "lowerThirdCriticalContent"
            ]
        )
        self.assertEqual(
            self.evidence["browserRuntime"]["geometry"][
                "mobileCriticalSpanMaximumPixels"
            ],
            800,
        )
        self.assertEqual(
            self.evidence["browserRuntime"]["geometry"][
                "mobileDocumentHeightMaximumPixels"
            ],
            1800,
        )
        self.assertEqual(
            self.evidence["manifestReplay"]["actualInputVerification"],
            "CDP mouse and keyboard events",
        )
        self.assertFalse(
            self.evidence["manifestReplay"]["publicFixtureApi"]
        )
        self.assertEqual(
            self.evidence["browserRuntime"]["routePrivacy"],
            {
                "visibleTextChecked": True,
                "renderedDomChecked": True,
                "accessibilityTreeChecked": True,
                "fullRouteBeforeAttempt": False,
            },
        )
        continuity = self.evidence["film"]["continuity"]
        self.assertEqual(
            self.evidence["film"]["renderer"],
            "live-app-chromium-capture",
        )
        self.assertEqual(
            continuity["path"],
            "snapshots/film-live-continuity.json",
        )
        self.assertEqual(
            continuity["renderer"],
            "live-app-chromium-capture",
        )
        self.assertEqual(
            continuity["sha256"],
            sha256_file(CONTINUITY_PATH),
        )

    def test_evidence_source_sha_bindings_are_current(self):
        records = self.evidence["sourceBindings"]
        self.assertEqual(
            {record["path"] for record in records},
            set(RENDERER.EVIDENCE_SOURCE_PATHS),
        )
        for record in records:
            path = CANDIDATE / record["path"]
            with self.subTest(path=record["path"]):
                self.assertEqual(path.stat().st_size, record["bytes"])
                self.assertEqual(sha256_file(path), record["sha256"])

    def test_app_is_standalone_responsive_keyboard_first_and_route_private(self):
        index = AppIndex()
        index.feed(self.app_source)
        required = {
            "maze-board",
            "seed-value",
            "reference-value",
            "digest-value",
            "step-value",
            "projection-value",
            "position-value",
            "exit-value",
            "compass-value",
            "assist-value",
            "status-message",
            "hint-panel",
            "trap-panel",
            "success-panel",
            "hint-btn",
            "restart-btn",
            "seed-input",
            "load-seed-btn",
            "seed-error",
            "seed-change-proof",
            "copy-challenge-btn",
            "challenge-link",
            "challenge-status",
            "challenge-error",
            "film-slate",
            "film-phase",
            "film-callout",
            "film-detail",
            "takeover-prompt",
            "move-north",
            "move-east",
            "move-south",
            "move-west",
        }
        self.assertTrue(required <= index.ids)
        self.assertEqual(index.resources, [])
        visible = " ".join(index.visible_text)
        self.assertNotIn("".join(EXPECTED_ROUTE), visible)
        self.assertNotIn(" ".join(EXPECTED_ROUTE), visible)
        self.assertNotIn("Replay exact", visible)
        self.assertNotRegex(
            self.app_source,
            r"\b(autoSolve|auto_solve|replayRoute|replayReference)\b",
        )
        for fragment in (
            'role="application"',
            "Arrow / WASD direct play",
            "No route is printed.",
            "Request earned one-step hint",
            'data-reset="exact"',
            "YOUR TURN",
            "@media (max-width: 430px)",
            "min-height: 44px",
            "function generateMaze(",
            "function canonicalTopology(",
            "function shortestRoute(",
            "function selectTrap(",
            "function challengeContract(",
            "function fixtureFromChallengeFragment(",
            'dataset.film = "true"',
            'aria-invalid="false"',
            'setAttribute(\n          "aria-invalid"',
            'window.addEventListener("hashchange"',
            'elements.seedInput.addEventListener("input"',
            "Route and trail are never included.",
            'elements.seedInput.addEventListener("click"',
            "if (error.message !== INVALID_SEED_MESSAGE) throw error;",
        ):
            self.assertIn(fragment, self.app_source)
        self.assertNotIn("window.foglineSurvey", self.app_source)
        self.assertNotIn("fixtureSnapshot", self.app_source)
        self.assertNotRegex(
            self.app_source,
            r'type\s*=\s*["\']password["\']|-webkit-text-security\s*:',
        )
        for uncanned in ("MIST-Δ", "A|B;C"):
            self.assertNotIn(uncanned, self.app_source)
        contract_body = re.search(
            r"function challengeContract\(sourceFixture\) \{(.*?)\n      \}",
            self.app_source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(contract_body)
        self.assertIn("seed:", contract_body.group(1))
        self.assertIn("topologyDigest:", contract_body.group(1))
        self.assertIn("referenceLength:", contract_body.group(1))
        self.assertNotRegex(contract_body.group(1), r"\b(route|trail)\s*:")
        for code in (
            "ArrowUp",
            "ArrowRight",
            "ArrowDown",
            "ArrowLeft",
            "KeyW",
            "KeyA",
            "KeyS",
            "KeyD",
        ):
            self.assertIn(code, self.app_source)
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
                re.search(pattern, self.app_source, flags=re.IGNORECASE),
                pattern,
            )

    def test_state_contract_has_no_pre_attempt_route_and_hint_is_one_step(self):
        opening = load_json(SNAPSHOT_PATH)["opening"]
        self.assertNotIn("shortestRoute", opening)
        self.assertNotIn("detourRoute", opening)
        self.assertEqual(opening["acceptedMoves"], [])
        self.assertEqual(opening["assistance"]["hintDirection"], None)
        hint = load_json(SNAPSHOT_PATH)["hint"]
        self.assertIn(hint["assistance"]["hintDirection"], "NESW")
        self.assertEqual(len(hint["assistance"]["hintDirection"]), 1)
        self.assertEqual(hint["assistance"]["scope"], "one next move only")
        self.assertEqual(hint["assistance"]["requests"], 1)

    def test_generated_text_is_lf_and_crlf_source_compiles_identically(self):
        for relative in (
            ".gitattributes",
            "README.md",
            "apps/maze-fogline.html",
            "render.py",
            "render_live.mjs",
            "verify_dom.mjs",
        ):
            with self.subTest(source=relative):
                self.assertTrue(normalized_text(CANDIDATE / relative))

        for relative in (
            "channel.production.json",
            "channel.json",
            "evidence.json",
            "snapshots/canonical-states.json",
            "snapshots/film-live-continuity.json",
            "thumbs/maze-fogline.svg",
        ):
            data = (CANDIDATE / relative).read_bytes()
            with self.subTest(path=relative):
                self.assertNotIn(b"\r\n", data)
                self.assertNotIn(b"\r", data)

        scratch = CANDIDATE / ".frame-0004-01-crlf.json"
        script_scratch = CANDIDATE / ".frame-0004-01-crlf.mjs"
        try:
            scratch.write_text(
                normalized_text(MANIFEST_PATH).replace("\n", "\r\n"),
                encoding="utf-8",
                newline="",
            )
            compilation = COMPILER.prepare_compilation(scratch)
            self.assertEqual(compilation.channel, self.channel)
            ast.parse(
                normalized_text(RENDERER_PATH).replace("\n", "\r\n"),
                filename="crlf-render.py",
            )
            index = AppIndex()
            index.feed(
                normalized_text(APP_PATH).replace("\n", "\r\n")
            )
            self.assertIn("maze-board", index.ids)
            if NODE:
                script_scratch.write_text(
                    normalized_text(VERIFY_PATH).replace("\n", "\r\n"),
                    encoding="utf-8",
                    newline="",
                )
                checked = subprocess.run(
                    [NODE, "--check", str(script_scratch)],
                    cwd=CANDIDATE,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                )
                self.assertEqual(
                    checked.returncode,
                    0,
                    checked.stderr or checked.stdout,
                )
        finally:
            scratch.unlink(missing_ok=True)
            script_scratch.unlink(missing_ok=True)

    def test_rights_privacy_and_secret_attestations_are_explicit(self):
        attestations = self.evidence["attestations"]
        self.assertTrue(attestations["noSecrets"])
        self.assertFalse(attestations["networkRequests"])
        self.assertFalse(attestations["externalRuntimeResources"])
        self.assertFalse(attestations["copiedImagery"])
        self.assertFalse(attestations["audio"])
        combined = (
            attestations["rights"] + " " + attestations["privacy"]
        ).lower()
        for phrase in ("all code", "no people", "credentials", "secrets"):
            self.assertIn(phrase, combined)
        secret_patterns = (
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
            r"\bAKIA[0-9A-Z]{16}\b",
            r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b",
            r"\bAIza[0-9A-Za-z_-]{30,}\b",
        )
        for path in CANDIDATE.rglob("*"):
            if (
                not path.is_file()
                or (
                    path.name != ".gitattributes"
                    and path.suffix
                    not in {".json", ".html", ".py", ".mjs", ".md", ".svg"}
                )
            ):
                continue
            source = normalized_text(path)
            for pattern in secret_patterns:
                with self.subTest(path=path.name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, source))


class TestRendererDeliveryAndMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delivery = load_json(DELIVERY_PATH)
        cls.continuity = load_json(CONTINUITY_PATH)

    def test_renderer_is_standard_library_only_and_declares_every_film_phase(self):
        tree = ast.parse(normalized_text(RENDERER_PATH))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
        self.assertTrue(
            imports
            <= {
                "__future__",
                "argparse",
                "base64",
                "collections",
                "dataclasses",
                "hashlib",
                "json",
                "os",
                "pathlib",
                "re",
                "shutil",
                "subprocess",
                "sys",
                "typing",
                "xml",
            },
            imports,
        )
        self.assertEqual(
            (
                RENDERER.SPEC.width,
                RENDERER.SPEC.height,
                RENDERER.SPEC.fps,
                RENDERER.SPEC.duration,
                RENDERER.SPEC.frame_count,
            ),
            (960, 540, 12, 24, 288),
        )
        self.assertEqual(
            tuple(item["phase"] for item in self.delivery["render"]["timeline"]),
            tuple(phase[0] for phase in RENDERER.FILM_TIMELINE),
        )
        self.assertEqual(
            tuple(phase[0] for phase in RENDERER.FILM_TIMELINE),
            (
                "challenge",
                "trap-approach",
                "trap-plus-two",
                "reset-after-trap",
                "optimal-18",
                "optimal-complete",
                "reset-after-optimal",
                "alternate-fresh",
                "takeover",
            ),
        )
        self.assertGreaterEqual(RENDERER.FILM_CRITICAL_TEXT_PIXELS, 22)
        self.assertEqual(
            self.delivery["render"]["typography"][
                "criticalTextSourcePixels"
            ],
            RENDERER.FILM_CRITICAL_TEXT_PIXELS,
        )
        self.assertEqual(
            self.delivery["render"]["typography"]["fullDigestCharacters"],
            64,
        )
        self.assertEqual(
            self.continuity["schema"],
            "fogline-survey-film-live-continuity/1.0",
        )
        self.assertEqual(
            self.continuity["renderer"]["kind"],
            "live-app-chromium-capture",
        )
        self.assertEqual(
            self.continuity["sourceAppSha256"],
            sha256_file(APP_PATH),
        )
        self.assertTrue(
            self.continuity["pixelBinding"][
                "exactAtEveryDeclaredPhase"
            ]
        )
        self.assertEqual(
            self.continuity["pixelBinding"]["sampleCount"],
            len(RENDERER.FILM_TIMELINE),
        )
        samples = self.delivery["render"]["contentSamples"]
        self.assertEqual(set(samples), {phase[0] for phase in RENDERER.FILM_TIMELINE})
        schedule = RENDERER.film_sample_schedule()
        continuity = {
            phase["phase"]: phase
            for phase in self.continuity["phases"]
        }
        self.assertEqual(set(continuity), set(samples))
        for phase, _start, _end in RENDERER.FILM_TIMELINE:
            sample = samples[phase]
            with self.subTest(phase=phase):
                self.assertEqual(
                    {
                        "frame": sample["frame"],
                        "timestamp": sample["timestamp"],
                    },
                    schedule[phase],
                )
                entry = continuity[phase]
                self.assertEqual(entry["frame"], sample["frame"])
                self.assertEqual(entry["timestamp"], sample["timestamp"])
                self.assertEqual(entry["masterRgbSha256"], sample["sha256"])
                self.assertEqual(
                    entry["liveRgbSha256"],
                    entry["masterRgbSha256"],
                )
                self.assertTrue(entry["pixelExact"])
                seed = entry["dom"]["seed"]
                expected = independent_fixture(seed)
                self.assertEqual(entry["dom"]["digest"], expected["digest"])
                self.assertEqual(
                    entry["dom"]["reference"],
                    f"{len(expected['route'])} moves",
                )
                self.assertEqual(
                    entry["dom"]["film"]["callout"],
                    RENDERER.FILM_CAPTIONS[phase][0],
                )
                self.assertEqual(
                    entry["dom"]["film"]["detail"],
                    RENDERER.FILM_CAPTIONS[phase][1],
                )
                if phase == "trap-plus-two":
                    self.assertEqual(entry["dom"]["steps"], "15 / 18")
                    self.assertEqual(entry["dom"]["bestFinish"], "20")
                    self.assertIn("MARKED TRAP", entry["dom"]["trap"]["text"])
                    self.assertIn(
                        "#exit-beacon",
                        entry["dom"]["visibleComponents"],
                    )
                if phase in {"alternate-fresh", "takeover"}:
                    self.assertEqual(seed, "FOG-7")
                    self.assertEqual(entry["dom"]["steps"], "0 / 10")

    def test_lossless_command_and_thumbnail_are_deterministic_and_safe(self):
        command = RENDERER.ffmpeg_command("fixed-ffmpeg", Path("master.mkv"))
        for value in (
            "image2pipe",
            "png",
            "pipe:0",
            "ffv1",
            "bgr0",
            "pc",
            "+bitexact",
            "matroska",
        ):
            self.assertIn(value, command)
        self.assertEqual(command[command.index("-threads") + 1], "1")
        renderer_source = normalized_text(RENDERER_PATH)
        render_master_source = renderer_source[
            renderer_source.index("def render_master("):
            renderer_source.index("\ndef _probe(")
        ]
        self.assertIn("LIVE_RENDERER_PATH", render_master_source)
        self.assertNotIn("iter_frames", render_master_source)
        with self.assertRaisesRegex(RuntimeError, "bitmap film rendering is retired"):
            RENDERER.frame_rgb(0)
        live_source = normalized_text(LIVE_RENDERER_PATH)
        for fragment in (
            'Page.captureScreenshot',
            'appUrl.searchParams.set("film", "1")',
            "dispatchKey(cdp, action.code)",
            "dispatchMouseClick(",
            "live-app-chromium-capture",
        ):
            self.assertIn(fragment, live_source)
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

    def test_film_uses_live_typography_components_and_safe_challenge(self):
        shared = self.continuity["sharedStyle"]
        self.assertEqual(shared["fontsReady"], "loaded")
        self.assertEqual(
            shared["bodyFontFamily"],
            shared["buttonFontFamily"],
        )
        self.assertEqual(
            shared["bodyFontFamily"],
            shared["outputFontFamily"],
        )
        self.assertIn("ui-monospace", shared["bodyFontFamily"])
        self.assertIn("system-ui", shared["headingFontFamily"])
        typography = shared["criticalTypography"]
        for selector in (
            "#seed-value",
            "#reference-value",
            "#digest-value",
            "#film-callout",
            "#challenge-status",
        ):
            self.assertGreaterEqual(
                typography[selector]["fontSize"],
                22,
                selector,
            )
        self.assertEqual(
            {component["selector"] for component in shared["components"]},
            {
                ".proof-strip",
                ".map-card",
                "#maze-board",
                ".panel",
                ".challenge-card",
                "#film-slate",
            },
        )

        challenge = self.continuity["phases"][0]["dom"]
        fragment = challenge["challenge"]["fragment"]
        self.assertTrue(fragment.startswith("#challenge="))
        encoded = fragment.removeprefix("#challenge=")
        padding = "=" * ((4 - len(encoded) % 4) % 4)
        contract = json.loads(
            base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
        )
        self.assertEqual(
            list(contract),
            ["seed", "topologyDigest", "referenceLength"],
        )
        self.assertNotIn("route", contract)
        self.assertNotIn("trail", contract)
        self.assertEqual(
            challenge["challenge"]["selectionStart"],
            0,
        )
        self.assertEqual(
            challenge["challenge"]["selectionEnd"],
            len(fragment),
        )
        self.assertRegex(
            challenge["challenge"]["status"],
            r"^Challenge fragment (copied|ready)",
        )
        self.assertEqual(
            challenge["film"]["detail"],
            "Seed · full digest · reference only",
        )

    def test_committed_delivery_hashes_are_complete_and_current(self):
        self.assertEqual(
            self.delivery["schema"],
            "fogline-survey-delivery/1.0",
        )
        self.assertEqual(self.delivery["channel"], CHANNEL_ID)
        self.assertEqual(self.delivery["publication"], PUBLICATION_ID)
        self.assertEqual(
            self.delivery["binding"],
            {
                "algorithm": "sha256",
                "artifactCount": 15,
                "pathStyle": "POSIX-relative",
                "selfExcluded": "delivery.json",
            },
        )
        self.assertEqual(
            {record["path"] for record in self.delivery["sourceArtifacts"]},
            set(RENDERER.DELIVERY_SOURCE_PATHS),
        )
        alternate_objective = self.delivery["objective"]["alternateSeeds"]
        self.assertEqual(
            self.delivery["objective"]["challengeContract"],
            RENDERER.challenge_contract(RENDERER.CANONICAL),
        )
        self.assertEqual(
            self.delivery["objective"]["challengeFragment"],
            RENDERER.challenge_fragment(RENDERER.CANONICAL),
        )
        self.assertEqual(
            [item["seed"] for item in alternate_objective],
            list(ALTERNATE_SEEDS),
        )
        for item in alternate_objective:
            fixture = independent_fixture(item["seed"])
            self.assertEqual(item["topologyDigest"], fixture["digest"])
            self.assertEqual(item["referenceLength"], len(fixture["route"]))
            self.assertEqual(item["trap"], list(fixture["trap"]["cell"]))
            self.assertEqual(item["detourLength"], len(fixture["detour"]))
        for record in self.delivery["sourceArtifacts"]:
            path = CANDIDATE / record["path"]
            with self.subTest(path=record["path"]):
                self.assertEqual(path.stat().st_size, record["bytes"])
                self.assertEqual(sha256_file(path), record["sha256"])
        for record in self.delivery["artifacts"].values():
            path = CANDIDATE / record["path"]
            with self.subTest(path=record["path"]):
                self.assertEqual(path.stat().st_size, record["bytes"])
                self.assertEqual(sha256_file(path), record["sha256"])
        stale = copy.deepcopy(self.delivery)
        stale["sourceArtifacts"][0]["sha256"] = "0" * 64
        self.assertNotEqual(
            stale["sourceArtifacts"],
            RENDERER.delivery_document(CANDIDATE, FFPROBE)[
                "sourceArtifacts"
            ] if FFPROBE else self.delivery["sourceArtifacts"],
        )

    def test_recorded_codecs_color_size_rate_and_duration_are_release_grade(self):
        expected = {
            "master": ("ffv1", "bgr0", "pc", "gbr"),
            "mp4": ("h264", "yuv420p", "tv", "bt709"),
            "webm": ("vp9", "yuv420p", "tv", "bt709"),
        }
        for kind, (codec, pixel, color_range, color_space) in expected.items():
            record = self.delivery["artifacts"][kind]
            with self.subTest(kind=kind):
                self.assertEqual(record["codec"], codec)
                self.assertEqual(record["pixelFormat"], pixel)
                self.assertEqual(record["colorRange"], color_range)
                self.assertEqual(record["colorSpace"], color_space)
                self.assertEqual(record["width"], 960)
                self.assertEqual(record["height"], 540)
                self.assertEqual(record["duration"], 24)
                self.assertEqual(record["averageFrameRate"], "12/1")
                self.assertEqual(record["audioStreamCount"], 0)
                self.assertEqual(record["streamCount"], 1)
        for kind in ("mp4", "webm"):
            record = self.delivery["artifacts"][kind]
            self.assertEqual(record["colorTransfer"], "bt709")
            self.assertEqual(record["colorPrimaries"], "bt709")

    @unittest.skipUnless(
        FFPROBE,
        "ffprobe not found via RAPP_FFPROBE or portable locations",
    )
    def test_actual_media_probes_match_committed_delivery_and_validator(self):
        for kind, path in (
            ("master", MASTER_PATH),
            ("mp4", MP4_PATH),
            ("webm", WEBM_PATH),
        ):
            with self.subTest(kind=kind):
                expected = {
                    key: value
                    for key, value in self.delivery["artifacts"][kind].items()
                    if key not in {"path", "bytes", "sha256"}
                }
                self.assertEqual(RENDERER._probe(path, FFPROBE), expected)
        self.assertEqual(
            VALIDATOR.ffprobe_local_media(
                load_json(CHANNEL_PATH),
                CHANNEL_PATH,
                executable=FFPROBE,
            ),
            [],
        )

    @unittest.skipUnless(
        FFMPEG,
        "ffmpeg not found via RAPP_FFMPEG or portable locations",
    )
    def test_committed_pixels_bind_every_declared_phase(self):
        samples = self.delivery["render"]["contentSamples"]
        indexes = [samples[phase]["frame"] for phase, _start, _end in RENDERER.FILM_TIMELINE]
        master = decode_rgb_samples(MASTER_PATH, indexes, FFMPEG)
        mp4 = decode_rgb_samples(MP4_PATH, indexes, FFMPEG)
        webm = decode_rgb_samples(WEBM_PATH, indexes, FFMPEG)
        limits = {
            "mp4": {
                "mae": 3.5,
                "psnr": 30.8,
                "over16": 0.038,
                "maximum": 160,
            },
            "webm": {
                "mae": 3.6,
                "psnr": 30.5,
                "over16": 0.04,
                "maximum": 160,
            },
        }
        continuity = {
            entry["phase"]: entry
            for entry in load_json(CONTINUITY_PATH)["phases"]
        }
        for phase, _start, _end in RENDERER.FILM_TIMELINE:
            sample = samples[phase]
            frame_index = sample["frame"]
            with self.subTest(kind="master", phase=phase):
                self.assertEqual(
                    hashlib.sha256(master[frame_index]).hexdigest(),
                    sample["sha256"],
                )
                self.assertEqual(
                    sample["sha256"],
                    continuity[phase]["masterRgbSha256"],
                )
                self.assertEqual(
                    continuity[phase]["liveRgbSha256"],
                    continuity[phase]["masterRgbSha256"],
                )
                self.assertTrue(continuity[phase]["pixelExact"])
            for kind, decoded in (("mp4", mp4), ("webm", webm)):
                metrics = rgb_metrics(master[frame_index], decoded[frame_index])
                diagnostic = (
                    f"{kind}/{phase}: MAE={metrics['mae']:.4f}, "
                    f"PSNR={metrics['psnr']:.3f}, "
                    f">16={metrics['over16Fraction']:.4%}, "
                    f"max={metrics['maximumChannelError']}"
                )
                with self.subTest(kind=kind, phase=phase):
                    self.assertLessEqual(
                        metrics["mae"],
                        limits[kind]["mae"],
                        diagnostic,
                    )
                    self.assertGreaterEqual(
                        metrics["psnr"],
                        limits[kind]["psnr"],
                        diagnostic,
                    )
                    self.assertLessEqual(
                        metrics["over16Fraction"],
                        limits[kind]["over16"],
                        diagnostic,
                    )
                    self.assertLessEqual(
                        metrics["maximumChannelError"],
                        limits[kind]["maximum"],
                        diagnostic,
                    )


class TestExecutableReleaseChecks(unittest.TestCase):
    @unittest.skipUnless(
        FFMPEG and FFPROBE and NODE and BROWSER,
        "ffmpeg/ffprobe/Node/Chromium are required for browser film rebuilds",
    )
    def test_two_fresh_same_toolchain_rebuilds_are_byte_identical(self):
        scratches = [
            CANDIDATE / ".frame-0004-01-rebuild-a",
            CANDIDATE / ".frame-0004-01-rebuild-b",
        ]
        for scratch in scratches:
            shutil.rmtree(scratch, ignore_errors=True)
        self.addCleanup(
            lambda: [
                shutil.rmtree(scratch, ignore_errors=True)
                for scratch in scratches
            ]
        )
        source_paths = (
            ".gitattributes",
            "README.md",
            "apps/maze-fogline.html",
            "channel.production.json",
            "evidence.json",
            "render.py",
            "render_live.mjs",
            "snapshots/canonical-states.json",
            "thumbs/maze-fogline.svg",
            "verify_dom.mjs",
        )
        for scratch in scratches:
            scratch.mkdir(parents=True)
            for relative in source_paths:
                source = CANDIDATE / relative
                target = scratch / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            RENDERER.render_master(
                scratch,
                FFMPEG,
                browser=BROWSER,
                node=NODE,
            )
            compilation = COMPILER.prepare_compilation(
                scratch / "channel.production.json",
                scratch,
            )
            COMPILER.build_compilation(
                compilation,
                ffmpeg=FFMPEG,
                ffprobe=FFPROBE,
            )

        for relative in (
            "masters/maze-fogline.mkv",
            "channel.json",
            "media/maze-fogline.mp4",
            "media/maze-fogline.webm",
            "snapshots/film-live-continuity.json",
            "thumbs/maze-fogline.svg",
        ):
            with self.subTest(path=relative):
                first = scratches[0] / relative
                second = scratches[1] / relative
                self.assertEqual(first.read_bytes(), second.read_bytes())
                self.assertEqual(
                    first.read_bytes(),
                    (CANDIDATE / relative).read_bytes(),
                )

    def test_compiler_check_and_source_transform_pass(self):
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
            timeout=60,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr or completed.stdout,
        )

    @unittest.skipUnless(
        FFPROBE,
        "ffprobe not found via RAPP_FFPROBE or portable locations",
    )
    def test_validator_and_candidate_release_check_pass(self):
        validator_environment = os.environ.copy()
        validator_environment["PATH"] = (
            str(Path(FFPROBE).resolve().parent)
            + os.pathsep
            + validator_environment.get("PATH", "")
        )
        validator = subprocess.run(
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
            encoding="utf-8",
            timeout=90,
            env=validator_environment,
        )
        self.assertEqual(
            validator.returncode,
            0,
            validator.stderr or validator.stdout,
        )
        release = subprocess.run(
            [
                sys.executable,
                str(RENDERER_PATH),
                "check",
                "--ffprobe",
                FFPROBE,
            ],
            cwd=CANDIDATE,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        self.assertEqual(
            release.returncode,
            0,
            release.stderr or release.stdout,
        )
        self.assertIn("release checks passed", release.stdout)

    def test_browser_verifier_source_covers_runtime_contract(self):
        source = normalized_text(VERIFY_PATH)
        for fragment in (
            "reservePort()",
            "waitForDevTools(child, port, launchLog, 45000)",
            'cdp.command("Network.enable")',
            'cdp.command("Network.setBlockedURLs"',
            'cdp.on("Network.requestWillBeSent"',
            'cdp.on("Runtime.exceptionThrown"',
            'cdp.on("Runtime.consoleAPICalled"',
            "Input.dispatchKeyEvent",
            "Input.dispatchMouseEvent",
            'cdp.command("Accessibility.enable")',
            'cdp.command("Accessibility.getFullAXTree")',
            "assertVisibleGeometry",
            "independentFixture",
            "exerciseAlternateSeeds",
            "exerciseChallengeContract",
            "auditOpeningPrivacy",
            "criticalPlayGeometry",
            "stateGateMatches",
            "assertFilmLiveStructure",
            "executedAt - action.at <= maxLateness",
            "await removeProfile(profilePath)",
        ):
            self.assertIn(fragment, source)
        self.assertNotIn("catch {}", source)
        self.assertNotIn("window.foglineSurvey.snapshot", source)
        self.assertNotIn("window.foglineSurvey.fixture", source)
        self.assertNotIn("target.click()", source)
        self.assertNotIn("executedAt - action.at < 0.45", source)
        film_source = normalized_text(LIVE_RENDERER_PATH)
        for fragment in (
            'Page.captureScreenshot',
            'appUrl.searchParams.set("film", "1")',
            "live-app-chromium-capture",
            "screenshotPngSha256",
            "dispatchKey(cdp, action.code)",
        ):
            self.assertIn(fragment, film_source)
        self.assertNotIn("class Canvas", film_source)

    @unittest.skipUnless(
        NODE and BROWSER,
        "Node.js and a Chromium-family RAPP_BROWSER are required",
    )
    def test_rapp_browser_and_explicit_argument_precedence(self):
        scratch = CANDIDATE / ".frame-0004-01-browser-precedence"
        shutil.rmtree(scratch, ignore_errors=True)
        self.addCleanup(lambda: shutil.rmtree(scratch, ignore_errors=True))
        scratch.mkdir()
        fake = scratch / ("chrome.exe" if os.name == "nt" else "chrome")
        fake.write_text("not launched\n", encoding="utf-8", newline="\n")
        fake.chmod(0o755)

        def discover(arguments, environment):
            completed = subprocess.run(
                [NODE, str(VERIFY_PATH), *arguments, "--find-browser"],
                cwd=CANDIDATE,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                env=environment,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr or completed.stdout,
            )
            return str(Path(completed.stdout.strip()).resolve())

        primary = os.environ.copy()
        primary["RAPP_BROWSER"] = BROWSER
        primary["RAPP_VISION_BROWSER"] = str(fake)
        self.assertEqual(
            discover([], primary),
            str(Path(BROWSER).resolve()),
        )

        alias = os.environ.copy()
        alias.pop("RAPP_BROWSER", None)
        alias["RAPP_VISION_BROWSER"] = str(fake)
        self.assertEqual(discover([], alias), str(fake.resolve()))

        explicit = os.environ.copy()
        explicit["RAPP_BROWSER"] = BROWSER
        self.assertEqual(
            discover(["--browser", str(fake)], explicit),
            str(fake.resolve()),
        )

    @unittest.skipUnless(
        NODE and BROWSER,
        "Node.js and a Chromium-family RAPP_BROWSER are required",
    )
    def test_real_browser_exactly_replays_desktop_mobile_and_takeover(self):
        completed = subprocess.run(
            [
                NODE,
                str(VERIFY_PATH),
                "--browser",
                BROWSER,
            ],
            cwd=CANDIDATE,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=240,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr or completed.stdout,
        )
        report = json.loads(completed.stdout)
        self.assertEqual(
            report["schema"],
            "fogline-survey-browser-verifier/1.0",
        )
        self.assertTrue(all(report["checks"].values()), report["checks"])
        self.assertEqual(report["cleanup"]["browserExited"], True)
        self.assertEqual(report["cleanup"]["profileRemoved"], True)
        self.assertFalse(Path(report["cleanup"]["profilePath"]).exists())
        self.assertTrue(all(report["hintGate"].values()))
        self.assertEqual(
            report["challengeContract"]["keys"],
            ["referenceLength", "seed", "topologyDigest"],
        )
        self.assertTrue(report["challengeContract"]["routeExcluded"])
        self.assertTrue(report["challengeContract"]["trailExcluded"])
        self.assertTrue(report["challengeContract"]["roundTripReset"])
        self.assertTrue(
            report["challengeContract"]["invalidExtraFieldPreserved"]
        )
        self.assertTrue(
            report["challengeContract"]["mismatchedDigestPreserved"]
        )
        self.assertTrue(
            report["challengeContract"]["mismatchedLengthPreserved"]
        )
        self.assertTrue(
            report["challengeContract"]["invalidSetsAriaInvalid"]
        )
        self.assertTrue(
            report["challengeContract"]["validLoadClearsAriaInvalid"]
        )
        self.assertTrue(report["hintGate"]["validEditClearsAriaInvalid"])
        self.assertTrue(report["hintGate"]["resetClearsAriaInvalid"])
        self.assertEqual(
            [item["seed"] for item in report["alternateSeeds"]],
            list(ALTERNATE_SEEDS),
        )
        for item in report["alternateSeeds"]:
            expected = independent_fixture(item["seed"])
            self.assertEqual(item["digest"], expected["digest"])
            self.assertEqual(item["edges"], 35)
            self.assertEqual(item["connectedCells"], 36)
            self.assertEqual(item["routeLength"], len(expected["route"]))
            self.assertEqual(item["trap"]["cell"], list(expected["trap"]["cell"]))
            self.assertEqual(item["detourLength"], len(expected["detour"]))
            self.assertTrue(item["optimalCompleted"])
            self.assertTrue(item["trapCompleted"])
            self.assertFalse(item["privacy"]["publicFixtureApi"])
        self.assertEqual(
            report["globalErrors"],
            {
                "externalRequests": [],
                "networkFailures": [],
                "exceptions": [],
                "console": [],
            },
        )
        self.assertEqual(
            [
                (item["viewport"]["width"], item["viewport"]["height"])
                for item in report["viewports"]
            ],
            [(1120, 720), (390, 844)],
        )
        film_style = load_json(CONTINUITY_PATH)["sharedStyle"]
        for viewport in report["viewports"]:
            with self.subTest(viewport=viewport["viewport"]["name"]):
                self.assertEqual(viewport["fixture"]["digest"], EXPECTED_DIGEST)
                self.assertEqual(
                    tuple(viewport["fixture"]["route"]),
                    EXPECTED_ROUTE,
                )
                self.assertEqual(viewport["fixture"]["detourLength"], 20)
                self.assertEqual(
                    viewport["continuityStyle"]["bodyFontFamily"],
                    film_style["bodyFontFamily"],
                )
                self.assertEqual(
                    viewport["continuityStyle"]["headingFontFamily"],
                    film_style["headingFontFamily"],
                )
                self.assertEqual(len(viewport["actionReports"]), 71)
                self.assertEqual(len(viewport["checkpointReports"]), 7)
                self.assertLessEqual(
                    viewport["maximumActionLateness"],
                    0.8,
                )
                self.assertLessEqual(viewport["sceneElapsed"], 25.0)
                self.assertEqual(
                    [
                        checkpoint["claim"]
                        for checkpoint in viewport["checkpointReports"]
                    ],
                    [
                        "hint",
                        "trap",
                        "detour",
                        "resetAfterTrap",
                        "optimal",
                        "resetAfterOptimal",
                        "handoff",
                    ],
                )
                self.assertTrue(
                    all(
                        item["inputMethod"]
                        in {"cdp-mouse", "cdp-keyboard", "cdp-scroll"}
                        for item in viewport["actionReports"]
                    )
                )
                self.assertTrue(
                    any(
                        item["inputMethod"] == "cdp-mouse"
                        for item in viewport["actionReports"]
                    )
                )
                self.assertTrue(
                    any(
                        item["inputMethod"] == "cdp-keyboard"
                        for item in viewport["actionReports"]
                    )
                )
                self.assertTrue(
                    all(
                        report_item["report"]["publicFixtureApi"] is False
                        for report_item in viewport["privacyReports"]
                    )
                )
                self.assertEqual(
                    viewport["authoredFinal"]["seed"],
                    "FOG-7",
                )
                self.assertEqual(viewport["authoredFinal"]["steps"], 0)
                self.assertEqual(
                    viewport["authoredFinal"]["trailLength"],
                    0,
                )
                self.assertFalse(
                    viewport["authoredFinal"]["assistanceUsed"]
                )
                self.assertEqual(
                    viewport["authoredFinal"]["hintRequests"],
                    0,
                )
                self.assertEqual(
                    viewport["authoredFinalFocus"],
                    "maze-board",
                )
                self.assertTrue(viewport["authoredFinalTakeoverVisible"])
                if viewport["viewport"]["width"] == 390:
                    self.assertLessEqual(
                        viewport["playGeometry"]["span"],
                        800,
                    )
                    self.assertLessEqual(
                        viewport["playGeometry"]["documentHeight"],
                        1800,
                    )
                self.assertEqual(
                    viewport["takeover"]["movedSteps"],
                    1,
                )
                self.assertEqual(
                    viewport["takeover"]["restartSteps"],
                    0,
                )
                self.assertEqual(
                    viewport["takeover"]["inputMethod"],
                    "cdp-keyboard-wasd",
                )
                self.assertEqual(viewport["errors"]["externalRequests"], [])
                self.assertEqual(viewport["errors"]["exceptions"], [])
                self.assertEqual(viewport["errors"]["console"], [])


if __name__ == "__main__":
    unittest.main()
