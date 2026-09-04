#!/usr/bin/env python3
"""Build the deterministic Fogline Survey publication and its evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
PUBLICATION_ID = "maze-fogline"
CHANNEL_ID = "candidate-frame-0004-01-maze-fogline"
TITLE = "Fogline Survey"
CANONICAL_SEED = "RAPP-42"
HANDOFF_SEED = "FOG-7"
ALTERNATE_AUDIT_SEEDS = ("FOG-7", "MIST-Δ", "A|B;C")
WIDTH = 960
HEIGHT = 540
FPS = 12
DURATION = 24
GRID_WIDTH = 6
GRID_HEIGHT = 6
ENTRANCE = (0, 0)
EXIT = (5, 3)
CANONICAL_DIGEST = (
    "126bf70440d3ef542c8dc97251726994e0f23422675e831f93309235ae085eda"
)
CANONICAL_ROUTE = tuple("SEESSWWSSENEESENNE")
CANONICAL_DETOUR = tuple("SEESSWWSSENEESWEENNE")
MAXIMUM_SEED_BYTES = 64
COMMISSION_CRITERION = (
    "Seed RAPP-42 always generates the same topology digest and an 18-step "
    "shortest route from the marked entrance to the exit."
)
INVALID_SEED = "X" * (MAXIMUM_SEED_BYTES + 1)
INVALID_SEED_MESSAGE = "Seed must contain 1–64 UTF-8 bytes and no controls."
CHALLENGE_FRAGMENT_PREFIX = "#challenge="

MANIFEST_PATH = ROOT / "channel.production.json"
CHANNEL_PATH = ROOT / "channel.json"
APP_PATH = ROOT / "apps" / f"{PUBLICATION_ID}.html"
MASTER_PATH = ROOT / "masters" / f"{PUBLICATION_ID}.mkv"
MP4_PATH = ROOT / "media" / f"{PUBLICATION_ID}.mp4"
WEBM_PATH = ROOT / "media" / f"{PUBLICATION_ID}.webm"
THUMB_PATH = ROOT / "thumbs" / f"{PUBLICATION_ID}.svg"
SNAPSHOT_PATH = ROOT / "snapshots" / "canonical-states.json"
EVIDENCE_PATH = ROOT / "evidence.json"
DELIVERY_PATH = ROOT / "delivery.json"
CONTINUITY_PATH = ROOT / "snapshots" / "film-live-continuity.json"
LIVE_RENDERER_PATH = ROOT / "render_live.mjs"

Cell = tuple[int, int]
Maze = dict[Cell, frozenset[str]]

DIRECTIONS = (
    ("N", 0, -1, "S"),
    ("E", 1, 0, "W"),
    ("S", 0, 1, "N"),
    ("W", -1, 0, "E"),
)
DIRECTION_VECTOR = {
    direction: (dx, dy) for direction, dx, dy, _opposite in DIRECTIONS
}
OPPOSITE = {
    direction: opposite
    for direction, _dx, _dy, opposite in DIRECTIONS
}
DIRECTION_NAME = {
    "N": "north",
    "E": "east",
    "S": "south",
    "W": "west",
}
KEY_CODE = {
    "N": "ArrowUp",
    "E": "ArrowRight",
    "S": "ArrowDown",
    "W": "ArrowLeft",
}

FILM_TIMELINE = (
    ("challenge", 0.0, 3.0),
    ("trap-approach", 3.0, 5.5),
    ("trap-plus-two", 5.5, 8.0),
    ("reset-after-trap", 8.0, 10.0),
    ("optimal-18", 10.0, 15.0),
    ("optimal-complete", 15.0, 17.0),
    ("reset-after-optimal", 17.0, 19.0),
    ("alternate-fresh", 19.0, 21.0),
    ("takeover", 21.0, 24.0),
)
FILM_SAMPLE_TIMES = {
    "challenge": 1.5,
    "trap-approach": 4.5,
    "trap-plus-two": 6.0,
    "reset-after-trap": 9.0,
    "optimal-18": 12.5,
    "optimal-complete": 16.0,
    "reset-after-optimal": 18.0,
    "alternate-fresh": 20.0,
    "takeover": 22.5,
}
FILM_CAPTIONS = {
    "challenge": (
        "Copy-ready offline challenge",
        "Seed · full digest · reference only",
    ),
    "trap-approach": (
        "Trap first · exit stays marked",
        "Earn one bearing, then choose the knot",
    ),
    "trap-plus-two": (
        "Knot / trap +2 · best finish 20",
        "Exit remains visible",
    ),
    "reset-after-trap": (
        "Exact reset after trap",
        "Entrance · north · zero · empty trail",
    ),
    "optimal-18": (
        "Unassisted direct survey",
        "18 individual Arrow-key moves",
    ),
    "optimal-complete": (
        "Exit open · 18 = reference",
        "Unassisted optimal",
    ),
    "reset-after-optimal": (
        "Exact reset repeats",
        "Closed exit · zero · empty trail",
    ),
    "alternate-fresh": (
        "Untouched FOG-7 challenge",
        "Zero steps · no assistance",
    ),
    "takeover": (
        "Your turn · movement focused",
        "FOG-7 · Arrow or WASD now",
    ),
}
FILM_CRITICAL_TEXT_PIXELS = 22


@dataclass(frozen=True)
class RenderSpec:
    publication_id: str = PUBLICATION_ID
    title: str = TITLE
    width: int = WIDTH
    height: int = HEIGHT
    fps: int = FPS
    duration: int = DURATION
    frame_count: int = FPS * DURATION
    master_relative: Path = Path("masters") / f"{PUBLICATION_ID}.mkv"
    thumbnail_relative: Path = Path("thumbs") / f"{PUBLICATION_ID}.svg"


@dataclass(frozen=True)
class Trap:
    approach_index: int
    approach: Cell
    turn: str
    cell: Cell
    return_direction: str
    selection: str


@dataclass(frozen=True)
class MazeFixture:
    seed: str
    width: int
    height: int
    entrance: Cell
    exit: Cell
    maze: Maze
    topology_signature: str
    topology_digest: str
    shortest_route: tuple[str, ...]
    route_positions: tuple[Cell, ...]
    trap: Trap
    detour_route: tuple[str, ...]


@dataclass(frozen=True)
class MazeState:
    position: Cell
    facing: str
    accepted_moves: tuple[str, ...]
    trail: tuple[Cell, ...]
    revealed: frozenset[Cell]
    status: str
    message: str
    last_attempt: str | None
    last_rejected: str | None
    exit_open: bool
    completed: bool
    matched_optimal: bool | None
    projected_total: int
    survey_earned: bool
    hint_available: bool
    assistance_used: bool
    hint_requests: int
    hint_direction: str | None


SPEC = RenderSpec()


def normalize_seed(seed: str) -> str:
    if not isinstance(seed, str):
        raise ValueError("seed must be text")
    encoded = seed.encode("utf-8")
    if not 1 <= len(encoded) <= MAXIMUM_SEED_BYTES:
        raise ValueError(INVALID_SEED_MESSAGE)
    if any(ord(character) < 32 or ord(character) == 127 for character in seed):
        raise ValueError(INVALID_SEED_MESSAGE)
    return seed


def fnv1a_32(value: str) -> int:
    value = normalize_seed(value)
    result = 0x811C9DC5
    for byte in value.encode("utf-8"):
        result ^= byte
        result = (result * 0x01000193) & 0xFFFFFFFF
    return result


class Mulberry32:
    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFF

    def next_uint32(self) -> int:
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        value = self.state
        value = ((value ^ (value >> 15)) * (value | 1)) & 0xFFFFFFFF
        mixed = ((value ^ (value >> 7)) * (value | 61)) & 0xFFFFFFFF
        value = (value ^ ((value + mixed) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return (value ^ (value >> 14)) & 0xFFFFFFFF


def generate_maze(
    seed: str,
    width: int = GRID_WIDTH,
    height: int = GRID_HEIGHT,
) -> Maze:
    seed = normalize_seed(seed)
    if isinstance(width, bool) or isinstance(height, bool):
        raise ValueError("maze dimensions must be positive integers")
    if not isinstance(width, int) or not isinstance(height, int):
        raise ValueError("maze dimensions must be positive integers")
    if width <= 0 or height <= 0:
        raise ValueError("maze dimensions must be positive integers")

    random = Mulberry32(fnv1a_32(seed))
    mutable: dict[Cell, set[str]] = {
        (x, y): set() for y in range(height) for x in range(width)
    }
    visited = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        x, y = stack[-1]
        candidates: list[tuple[str, str, Cell]] = []
        for direction, dx, dy, opposite in DIRECTIONS:
            neighbor = (x + dx, y + dy)
            if (
                0 <= neighbor[0] < width
                and 0 <= neighbor[1] < height
                and neighbor not in visited
            ):
                candidates.append((direction, opposite, neighbor))
        if not candidates:
            stack.pop()
            continue
        direction, opposite, neighbor = candidates[
            random.next_uint32() % len(candidates)
        ]
        mutable[(x, y)].add(direction)
        mutable[neighbor].add(opposite)
        visited.add(neighbor)
        stack.append(neighbor)
    return {
        cell: frozenset(openings)
        for cell, openings in mutable.items()
    }


def step(cell: Cell, direction: str) -> Cell:
    if direction not in DIRECTION_VECTOR:
        raise ValueError(f"unknown direction: {direction!r}")
    dx, dy = DIRECTION_VECTOR[direction]
    return cell[0] + dx, cell[1] + dy


def topology_signature(
    maze: Mapping[Cell, Iterable[str]],
    seed: str,
    width: int = GRID_WIDTH,
    height: int = GRID_HEIGHT,
) -> str:
    seed = normalize_seed(seed)
    cells = []
    for y in range(height):
        for x in range(width):
            openings = set(maze[(x, y)])
            ordered = "".join(
                direction for direction in "NESW" if direction in openings
            )
            cells.append(f"{x},{y}:{ordered}")
    return f"{seed}|{width}x{height}|" + ";".join(cells)


def topology_digest(
    maze: Mapping[Cell, Iterable[str]],
    seed: str,
    width: int = GRID_WIDTH,
    height: int = GRID_HEIGHT,
) -> str:
    signature = topology_signature(maze, seed, width, height)
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()


def shortest_route(
    maze: Mapping[Cell, Iterable[str]],
    start: Cell = ENTRANCE,
    finish: Cell = EXIT,
) -> tuple[str, ...]:
    if start not in maze or finish not in maze:
        raise ValueError("start and finish must be maze cells")
    queue = deque([start])
    previous: dict[Cell, Cell | None] = {start: None}
    previous_move: dict[Cell, str] = {}
    while queue:
        cell = queue.popleft()
        if cell == finish:
            break
        openings = set(maze[cell])
        for direction in "NESW":
            if direction not in openings:
                continue
            neighbor = step(cell, direction)
            if neighbor in previous:
                continue
            previous[neighbor] = cell
            previous_move[neighbor] = direction
            queue.append(neighbor)
    if finish not in previous:
        raise ValueError("exit is unreachable")
    route: list[str] = []
    cursor = finish
    while cursor != start:
        route.append(previous_move[cursor])
        parent = previous[cursor]
        if parent is None:
            raise RuntimeError("invalid BFS parent chain")
        cursor = parent
    route.reverse()
    return tuple(route)


def route_positions(
    route: Sequence[str],
    start: Cell = ENTRANCE,
) -> tuple[Cell, ...]:
    positions = [start]
    cursor = start
    for direction in route:
        cursor = step(cursor, direction)
        positions.append(cursor)
    return tuple(positions)


def select_trap(
    maze: Mapping[Cell, Iterable[str]],
    route: Sequence[str],
    start: Cell = ENTRANCE,
) -> Trap:
    positions = route_positions(route, start)
    route_cells = set(positions)
    for index in range(len(positions) - 2, -1, -1):
        approach = positions[index]
        for direction in "NESW":
            if direction not in maze[approach]:
                continue
            neighbor = step(approach, direction)
            if neighbor not in route_cells:
                return Trap(
                    approach_index=index,
                    approach=approach,
                    turn=direction,
                    cell=neighbor,
                    return_direction=OPPOSITE[direction],
                    selection="latest off-route branch before exit; NESW tie-break",
                )

    if len(route) < 2:
        raise ValueError("route is too short to derive a trap")
    index = max(1, len(route) // 2)
    previous_direction = route[index - 1]
    return Trap(
        approach_index=index,
        approach=positions[index],
        turn=OPPOSITE[previous_direction],
        cell=positions[index - 1],
        return_direction=previous_direction,
        selection="deterministic backtrack fallback for a Hamiltonian route",
    )


def build_fixture(seed: str) -> MazeFixture:
    seed = normalize_seed(seed)
    maze = generate_maze(seed)
    signature = topology_signature(maze, seed)
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    route = shortest_route(maze)
    positions = route_positions(route)
    trap = select_trap(maze, route)
    detour = (
        route[: trap.approach_index]
        + (trap.turn, trap.return_direction)
        + route[trap.approach_index :]
    )
    return MazeFixture(
        seed=seed,
        width=GRID_WIDTH,
        height=GRID_HEIGHT,
        entrance=ENTRANCE,
        exit=EXIT,
        maze=maze,
        topology_signature=signature,
        topology_digest=digest,
        shortest_route=route,
        route_positions=positions,
        trap=trap,
        detour_route=detour,
    )


def challenge_contract(fixture: MazeFixture) -> dict[str, object]:
    return {
        "seed": fixture.seed,
        "topologyDigest": fixture.topology_digest,
        "referenceLength": len(fixture.shortest_route),
    }


def challenge_fragment(fixture: MazeFixture) -> str:
    payload = json.dumps(
        challenge_contract(fixture),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return CHALLENGE_FRAGMENT_PREFIX + encoded


CANONICAL = build_fixture(CANONICAL_SEED)
HANDOFF = build_fixture(HANDOFF_SEED)

if CANONICAL.topology_digest != CANONICAL_DIGEST:
    raise RuntimeError("canonical topology digest drifted")
if CANONICAL.shortest_route != CANONICAL_ROUTE:
    raise RuntimeError("canonical shortest route drifted")
if CANONICAL.detour_route != CANONICAL_DETOUR:
    raise RuntimeError("canonical trap detour drifted")
if CANONICAL.trap.cell != (2, 5) or CANONICAL.trap.turn != "W":
    raise RuntimeError("canonical marked trap drifted")
if len(CANONICAL.shortest_route) != 18 or len(CANONICAL.detour_route) != 20:
    raise RuntimeError("canonical route lengths drifted")


def revealed_from(
    fixture: MazeFixture,
    cell: Cell,
) -> frozenset[Cell]:
    revealed = {cell}
    for direction in fixture.maze[cell]:
        revealed.add(step(cell, direction))
    return frozenset(revealed)


def initial_state(fixture: MazeFixture = CANONICAL) -> MazeState:
    return MazeState(
        position=fixture.entrance,
        facing="N",
        accepted_moves=(),
        trail=(),
        revealed=revealed_from(fixture, fixture.entrance),
        status="ready",
        message=(
            f"Seed {fixture.seed} ready. Find the marked exit; "
            f"reference length {len(fixture.shortest_route)}."
        ),
        last_attempt=None,
        last_rejected=None,
        exit_open=False,
        completed=False,
        matched_optimal=None,
        projected_total=len(fixture.shortest_route),
        survey_earned=False,
        hint_available=False,
        assistance_used=False,
        hint_requests=0,
        hint_direction=None,
    )


def move_state(
    fixture: MazeFixture,
    state: MazeState,
    direction: str,
) -> MazeState:
    if direction not in DIRECTION_VECTOR:
        raise ValueError(f"unknown direction: {direction!r}")
    if state.completed:
        return replace(
            state,
            facing=direction,
            status="closed",
            message="Exit already open. Restart or load another seed.",
            last_attempt=direction,
            last_rejected=direction,
            hint_direction=None,
        )
    if direction not in fixture.maze[state.position]:
        return replace(
            state,
            facing=direction,
            status="wall",
            message=(
                f"{DIRECTION_NAME[direction].title()} is fogbound by a wall; "
                "accepted steps, hint charge, and trail are preserved."
            ),
            last_attempt=direction,
            last_rejected=direction,
        )

    position = step(state.position, direction)
    accepted_moves = state.accepted_moves + (direction,)
    trail = state.trail + (position,)
    revealed = frozenset(
        set(state.revealed) | set(revealed_from(fixture, position))
    )
    accepted_steps = len(accepted_moves)
    projected_total = accepted_steps + len(
        shortest_route(fixture.maze, position, fixture.exit)
    )
    completed = position == fixture.exit
    survey_earned = state.survey_earned or accepted_steps >= 4
    hint_available = survey_earned and not state.assistance_used

    if completed:
        matched_optimal = accepted_steps == len(fixture.shortest_route)
        status = "complete-optimal" if matched_optimal else "complete-detour"
        if matched_optimal:
            message = (
                f"Exit open in {accepted_steps}. "
                "Direct survey matched the reference."
            )
        else:
            delta = accepted_steps - len(fixture.shortest_route)
            message = (
                f"Exit open in {accepted_steps}: +{delta} over "
                f"reference {len(fixture.shortest_route)}."
            )
    elif position == fixture.trap.cell:
        matched_optimal = None
        delta = projected_total - len(fixture.shortest_route)
        status = "trap"
        message = (
            f"Marked trap entered. Best finish is now {projected_total} "
            f"(+{delta}); exit beacon remains marked."
        )
    elif projected_total > len(fixture.shortest_route):
        matched_optimal = None
        delta = projected_total - len(fixture.shortest_route)
        status = "detour"
        message = (
            f"Valid detour recorded. Best finish {projected_total} "
            f"(+{delta})."
        )
    else:
        matched_optimal = None
        status = "moving"
        message = (
            f"{direction} accepted. {accepted_steps} steps; "
            f"best finish {projected_total}."
        )

    return MazeState(
        position=position,
        facing=direction,
        accepted_moves=accepted_moves,
        trail=trail,
        revealed=revealed,
        status=status,
        message=message,
        last_attempt=direction,
        last_rejected=None,
        exit_open=completed,
        completed=completed,
        matched_optimal=matched_optimal,
        projected_total=projected_total,
        survey_earned=survey_earned,
        hint_available=hint_available,
        assistance_used=state.assistance_used,
        hint_requests=state.hint_requests,
        hint_direction=None,
    )


def request_hint(
    fixture: MazeFixture,
    state: MazeState,
) -> MazeState:
    if state.completed:
        return replace(
            state,
            status="hint-unavailable",
            message="Survey hint unavailable after completion.",
        )
    if not state.hint_available:
        message = (
            "Survey charge unlocks after four accepted moves."
            if not state.survey_earned
            else "The one-step survey hint has already been spent."
        )
        return replace(
            state,
            status="hint-unavailable",
            message=message,
        )
    route = shortest_route(fixture.maze, state.position, fixture.exit)
    if not route:
        raise RuntimeError("hint requested at the exit")
    direction = route[0]
    return replace(
        state,
        status="hint",
        message=(
            f"One-step survey: {direction}. "
            "Assistance is recorded; no later moves are revealed."
        ),
        hint_available=False,
        assistance_used=True,
        hint_requests=state.hint_requests + 1,
        hint_direction=direction,
    )


def state_after(
    fixture: MazeFixture,
    moves: Sequence[str],
    *,
    state: MazeState | None = None,
) -> MazeState:
    current = initial_state(fixture) if state is None else state
    for direction in moves:
        current = move_state(fixture, current, direction)
    return current


def detour_state(fixture: MazeFixture = CANONICAL) -> MazeState:
    approach = state_after(
        fixture,
        fixture.shortest_route[: fixture.trap.approach_index],
    )
    assisted = request_hint(fixture, approach)
    tail = (
        fixture.trap.turn,
        fixture.trap.return_direction,
    ) + fixture.shortest_route[fixture.trap.approach_index :]
    return state_after(fixture, tail, state=assisted)


def session_snapshot(
    fixture: MazeFixture,
    state: MazeState,
    *,
    seed_input: str | None = None,
    seed_error: str | None = None,
    seed_change_count: int = 0,
) -> dict[str, object]:
    return {
        "schema": "fogline-survey-state/1.0",
        "seed": fixture.seed,
        "seedInput": fixture.seed if seed_input is None else seed_input,
        "seedError": seed_error,
        "seedChangeCount": seed_change_count,
        "grid": {"width": fixture.width, "height": fixture.height},
        "topologyDigest": fixture.topology_digest,
        "topologySignature": fixture.topology_signature,
        "position": {"x": state.position[0], "y": state.position[1]},
        "facing": state.facing,
        "steps": len(state.accepted_moves),
        "acceptedMoves": list(state.accepted_moves),
        "referenceLength": len(fixture.shortest_route),
        "projectedTotal": state.projected_total,
        "trail": [[x, y] for x, y in state.trail],
        "revealed": [
            [x, y]
            for x, y in sorted(state.revealed, key=lambda cell: (cell[1], cell[0]))
        ],
        "status": state.status,
        "message": state.message,
        "lastAttempt": state.last_attempt,
        "lastRejected": state.last_rejected,
        "completed": state.completed,
        "matchedOptimal": state.matched_optimal,
        "exit": {
            "x": fixture.exit[0],
            "y": fixture.exit[1],
            "state": "open" if state.exit_open else "closed",
            "marked": True,
        },
        "trap": {
            "x": fixture.trap.cell[0],
            "y": fixture.trap.cell[1],
            "approachStep": fixture.trap.approach_index,
            "enteredStep": fixture.trap.approach_index + 1,
            "turn": fixture.trap.turn,
            "marked": fixture.trap.cell in state.revealed,
            "entered": fixture.trap.cell in state.trail,
        },
        "assistance": {
            "earned": state.survey_earned,
            "available": state.hint_available,
            "used": state.assistance_used,
            "requests": state.hint_requests,
            "hintDirection": state.hint_direction,
            "scope": "one next move only",
        },
    }


def canonical_states_document() -> dict[str, object]:
    opening_state = initial_state(CANONICAL)
    wall_rejected = move_state(CANONICAL, opening_state, "N")
    optimal_state = state_after(CANONICAL, CANONICAL.shortest_route)
    approach_state = state_after(
        CANONICAL,
        CANONICAL.shortest_route[: CANONICAL.trap.approach_index],
    )
    hint_state = request_hint(CANONICAL, approach_state)
    trap_state = move_state(CANONICAL, hint_state, CANONICAL.trap.turn)
    detour_complete = detour_state(CANONICAL)
    handoff_opening = initial_state(HANDOFF)
    return {
        "schema": "fogline-survey-snapshots/1.0",
        "opening": session_snapshot(CANONICAL, opening_state),
        "wallRejected": session_snapshot(CANONICAL, wall_rejected),
        "optimal": session_snapshot(CANONICAL, optimal_state),
        "hint": session_snapshot(CANONICAL, hint_state),
        "trap": session_snapshot(CANONICAL, trap_state),
        "detour": session_snapshot(CANONICAL, detour_complete),
        "reset": session_snapshot(CANONICAL, opening_state),
        "invalidSeedPreserved": session_snapshot(
            CANONICAL,
            opening_state,
            seed_input=INVALID_SEED,
            seed_error=INVALID_SEED_MESSAGE,
        ),
        "handoff": session_snapshot(
            HANDOFF,
            handoff_opening,
            seed_change_count=1,
        ),
    }


def _action(at: float, operation: str, **fields: object) -> dict[str, object]:
    return {"at": at, "do": operation, **fields}


def checkpoint_state_gates() -> dict[str, dict[str, object]]:
    approach = state_after(
        CANONICAL,
        CANONICAL.shortest_route[: CANONICAL.trap.approach_index],
    )
    hinted = request_hint(CANONICAL, approach)
    trap = move_state(CANONICAL, hinted, CANONICAL.trap.turn)
    detour = detour_state(CANONICAL)
    optimal = state_after(CANONICAL, CANONICAL.shortest_route)
    opening = initial_state(CANONICAL)
    handoff = initial_state(HANDOFF)

    def gate(fixture: MazeFixture, state: MazeState) -> dict[str, object]:
        return {
            "seed": fixture.seed,
            "topologyDigest": fixture.topology_digest,
            "position": list(state.position),
            "facing": state.facing,
            "steps": len(state.accepted_moves),
            "projectedTotal": state.projected_total,
            "status": state.status,
            "completed": state.completed,
            "matchedOptimal": state.matched_optimal,
            "exitState": "open" if state.exit_open else "closed",
            "trailLength": len(state.trail),
            "assistanceUsed": state.assistance_used,
            "hintAvailable": state.hint_available,
            "hintRequests": state.hint_requests,
            "hintDirection": state.hint_direction,
        }

    return {
        "hint": gate(CANONICAL, hinted),
        "trap": gate(CANONICAL, trap),
        "detour": gate(CANONICAL, detour),
        "resetAfterTrap": gate(CANONICAL, opening),
        "optimal": gate(CANONICAL, optimal),
        "resetAfterOptimal": gate(CANONICAL, opening),
        "handoff": gate(HANDOFF, handoff),
    }


def production_actions() -> tuple[list[dict[str, object]], dict[str, object]]:
    actions: list[dict[str, object]] = []
    checkpoints: list[dict[str, object]] = []
    segments: dict[str, object] = {}

    def add(at: float, operation: str, **fields: object) -> None:
        actions.append(_action(at, operation, **fields))

    def checkpoint(claim: str, selector: str) -> None:
        start = float(actions[-1]["at"])
        checkpoints.append(
            {
                "claim": claim,
                "selector": selector,
                "stateGate": checkpoint_state_gates()[claim],
                "timeWindow": {
                    "start": start,
                    "end": round(start + 1.25, 2),
                },
            }
        )

    add(
        0.20,
        "scroll",
        selector="#copy-challenge-btn",
        block="center",
        behavior="auto",
    )
    add(0.45, "click", selector="#copy-challenge-btn")
    add(
        0.70,
        "scroll",
        selector="#maze-board",
        block="center",
        behavior="auto",
    )
    add(0.90, "click", selector="#maze-board")
    detour_start = len(actions) + 1
    for index, direction in enumerate(
        CANONICAL.shortest_route[: CANONICAL.trap.approach_index]
    ):
        add(round(1.10 + index * 0.23, 2), "key", code=KEY_CODE[direction])
    add(
        4.32,
        "scroll",
        selector="#hint-btn",
        block="center",
        behavior="auto",
    )
    add(4.52, "click", selector="#hint-btn")
    checkpoint("hint", "#hint-panel")
    add(
        4.66,
        "scroll",
        selector="#hint-panel",
        block="center",
        behavior="auto",
    )
    add(
        4.82,
        "scroll",
        selector="#maze-board",
        block="center",
        behavior="auto",
    )
    add(4.98, "click", selector="#maze-board")
    add(5.18, "key", code=KEY_CODE[CANONICAL.trap.turn])
    add(
        5.38,
        "scroll",
        selector="#trap-panel",
        block="center",
        behavior="auto",
    )
    checkpoint("trap", "#trap-panel")
    add(
        5.58,
        "scroll",
        selector="#maze-board",
        block="center",
        behavior="auto",
    )
    add(5.74, "click", selector="#maze-board")
    tail = (
        CANONICAL.trap.return_direction,
    ) + CANONICAL.shortest_route[CANONICAL.trap.approach_index :]
    for index, direction in enumerate(tail):
        add(round(5.92 + index * 0.22, 2), "key", code=KEY_CODE[direction])
    detour_end = len(actions)
    segments["detour"] = {
        "firstAction": detour_start,
        "lastAction": detour_end,
        "directions": list(CANONICAL.detour_route),
        "hintRequestedAfterAcceptedStep": CANONICAL.trap.approach_index,
        "assistance": True,
    }
    add(
        7.02,
        "scroll",
        selector="#success-panel",
        block="center",
        behavior="auto",
    )
    checkpoint("detour", "#success-panel")
    add(
        7.25,
        "scroll",
        selector="#restart-btn",
        block="center",
        behavior="auto",
    )
    add(7.45, "click", selector="#restart-btn")
    add(
        7.62,
        "scroll",
        selector="#reset-proof",
        block="center",
        behavior="auto",
    )
    checkpoint("resetAfterTrap", "#reset-proof")
    add(
        7.80,
        "scroll",
        selector="#maze-board",
        block="center",
        behavior="auto",
    )
    add(7.95, "click", selector="#maze-board")
    optimal_start = len(actions) + 1
    for index, direction in enumerate(CANONICAL.shortest_route):
        add(round(8.15 + index * 0.23, 2), "key", code=KEY_CODE[direction])
    optimal_end = len(actions)
    segments["optimal"] = {
        "firstAction": optimal_start,
        "lastAction": optimal_end,
        "directions": list(CANONICAL.shortest_route),
        "assistance": False,
    }
    add(
        12.28,
        "scroll",
        selector="#success-panel",
        block="center",
        behavior="auto",
    )
    checkpoint("optimal", "#success-panel")
    add(
        12.52,
        "scroll",
        selector="#restart-btn",
        block="center",
        behavior="auto",
    )
    add(12.72, "click", selector="#restart-btn")
    add(
        12.90,
        "scroll",
        selector="#reset-proof",
        block="center",
        behavior="auto",
    )
    checkpoint("resetAfterOptimal", "#reset-proof")
    add(
        13.10,
        "scroll",
        selector="#seed-input",
        block="center",
        behavior="auto",
    )
    add(13.28, "click", selector="#seed-input")
    add(13.45, "type", text=HANDOFF_SEED)
    add(
        13.70,
        "scroll",
        selector="#load-seed-btn",
        block="center",
        behavior="auto",
    )
    add(13.88, "click", selector="#load-seed-btn")
    add(
        14.10,
        "scroll",
        selector="#takeover-prompt",
        block="center",
        behavior="auto",
    )
    checkpoint("handoff", "#takeover-prompt")
    add(
        14.35,
        "scroll",
        selector="#copy-challenge-btn",
        block="center",
        behavior="auto",
    )
    add(14.55, "click", selector="#copy-challenge-btn")
    add(
        14.80,
        "scroll",
        selector="#takeover-prompt",
        block="center",
        behavior="auto",
    )
    add(
        15.00,
        "scroll",
        selector="#maze-board",
        block="center",
        behavior="auto",
    )
    add(15.20, "click", selector="#maze-board")

    if [action["at"] for action in actions] != sorted(
        action["at"] for action in actions
    ):
        raise RuntimeError("live actions are not time ordered")
    return actions, {
        "checkpoints": checkpoints,
        "segments": segments,
    }


def production_document() -> dict[str, object]:
    actions, _metadata = production_actions()
    return {
        "schema": "rapp-vision-production/1.0",
        "id": CHANNEL_ID,
        "name": "Candidate Frame 0004 · Fogline Survey",
        "tagline": (
            "Read only the revealed ground, keep the exit beacon, and earn "
            "one assisted bearing."
        ),
        "avatar": "⌁",
        "creator": {
            "name": "RAPP Vision autonomous studio",
            "identity": "machine-produced, artifact-reviewed",
        },
        "commission": {
            "id": "play-seeded-maze-return",
            "candidateFrame": "0004-01",
        },
        "videos": [
            {
                "id": PUBLICATION_ID,
                "title": TITLE,
                "description": (
                    "A top-down fogline survey keeps unexplored walls hidden "
                    "while a compass, revealed trail, and marked exit remain "
                    "legible. RAPP-42 binds the canonical SHA-256 topology and "
                    "18-step reference. A three-field offline challenge "
                    "fragment "
                    "contains only seed, digest, and reference length. The "
                    "trap-first cut explicitly requests one bearing, proves "
                    "the marked +2 knot in 20, resets exactly, then completes "
                    "18 unassisted. A second exact reset leaves untouched "
                    "FOG-7 focused for immediate Arrow/WASD takeover."
                ),
                "published": "2026-09-03",
                "duration": SPEC.duration,
                "width": SPEC.width,
                "height": SPEC.height,
                "orientation": "landscape",
                "tags": [
                    "fog-of-war",
                    "seeded-maze",
                    "compass",
                    "keyboard-play",
                    "deterministic",
                    "one-step-hint",
                    "exact-reset",
                    "multi-seed",
                    "offline-challenge",
                ],
                "thumb": SPEC.thumbnail_relative.as_posix(),
                "production": {
                    "master": SPEC.master_relative.as_posix(),
                },
                "chapters": [
                    {"t": start, "label": label}
                    for label, start, _end in (
                        (
                            "Three-field offline RAPP-42 challenge",
                            0.0,
                            3.0,
                        ),
                        ("Approach the marked knot", 3.0, 5.5),
                        ("Valid trap adds exactly two", 5.5, 8.0),
                        ("Exact reset after the trap", 8.0, 10.0),
                        ("Unassisted direct survey in 18", 10.0, 15.0),
                        ("Optimal result: 18 equals reference", 15.0, 17.0),
                        ("Exact reset after optimal", 17.0, 19.0),
                        ("Untouched FOG-7 challenge", 19.0, 21.0),
                        ("YOUR TURN with movement focused", 21.0, 24.0),
                    )
                ],
                "live": {
                    "kind": "rapp-vision-live/1.0",
                    "duration": SPEC.duration,
                    "chapters": [
                        {"t": 0.0, "label": "Export the offline challenge"},
                        {
                            "t": 1.1,
                            "label": "Take the valid marked trap first",
                        },
                        {"t": 7.25, "label": "Reset the exact opening"},
                        {"t": 8.15, "label": "Complete 18 unassisted"},
                        {"t": 12.52, "label": "Reset exactly again"},
                        {"t": 13.10, "label": "Load untouched FOG-7"},
                        {"t": 15.0, "label": "Focus movement for YOUR TURN"},
                    ],
                    "scenes": [
                        {
                            "t": 0,
                            "dur": SPEC.duration,
                            "app": f"apps/{PUBLICATION_ID}.html",
                            "ready": {
                                "selector": "#maze-board",
                                "enabled": True,
                            },
                            "lower": {
                                "title": TITLE,
                                "bench": (
                                    "RAPP-42 · SHA-256 126bf70440d3… · "
                                    "reference 18 · KNOT/TRAP +2 · best 20."
                                ),
                                "fix": (
                                    "YOUR TURN — FOG-7 starts untouched at "
                                    "zero; Arrow/WASD movement is focused."
                                ),
                            },
                            "actions": actions,
                        }
                    ],
                },
            }
        ],
    }


def fixture_document(fixture: MazeFixture) -> dict[str, object]:
    return {
        "seed": fixture.seed,
        "grid": {"width": fixture.width, "height": fixture.height},
        "generator": {
            "algorithm": "recursive-backtracker",
            "candidateOrder": ["N", "E", "S", "W"],
            "seedHash": "FNV-1a 32-bit over UTF-8",
            "prng": "Mulberry32 unsigned integer output",
            "start": [0, 0],
        },
        "entrance": list(fixture.entrance),
        "exit": list(fixture.exit),
        "topologySerialization": (
            "seed|6x6| then row-major x,y:NESW-openings cells joined by ;"
        ),
        "topologySignature": fixture.topology_signature,
        "topologyDigest": fixture.topology_digest,
        "shortestRoute": list(fixture.shortest_route),
        "shortestLength": len(fixture.shortest_route),
        "trap": {
            "cell": list(fixture.trap.cell),
            "approach": list(fixture.trap.approach),
            "approachStep": fixture.trap.approach_index,
            "enteredStep": fixture.trap.approach_index + 1,
            "turn": fixture.trap.turn,
            "return": fixture.trap.return_direction,
            "selection": fixture.trap.selection,
        },
        "detourRoute": list(fixture.detour_route),
        "detourLength": len(fixture.detour_route),
        "cells": [
            {
                "x": x,
                "y": y,
                "openings": "".join(
                    direction
                    for direction in "NESW"
                    if direction in fixture.maze[(x, y)]
                ),
            }
            for y in range(fixture.height)
            for x in range(fixture.width)
        ],
    }


EVIDENCE_SOURCE_PATHS = (
    ".gitattributes",
    "README.md",
    "apps/maze-fogline.html",
    "channel.production.json",
    "render.py",
    "render_live.mjs",
    "snapshots/canonical-states.json",
    "thumbs/maze-fogline.svg",
    "verify_dom.mjs",
)

DELIVERY_SOURCE_PATHS = (
    ".gitattributes",
    "README.md",
    "apps/maze-fogline.html",
    "channel.production.json",
    "channel.json",
    "evidence.json",
    "render.py",
    "render_live.mjs",
    "snapshots/canonical-states.json",
    "snapshots/film-live-continuity.json",
    "thumbs/maze-fogline.svg",
    "verify_dom.mjs",
)


def film_phase(time_seconds: float) -> str:
    if not 0 <= time_seconds < SPEC.duration:
        raise ValueError("film time is outside the publication")
    for name, start, end in FILM_TIMELINE:
        if start <= time_seconds < end:
            return name
    raise RuntimeError("film timeline has a gap")


def film_sample_schedule() -> dict[str, dict[str, object]]:
    samples: dict[str, dict[str, object]] = {}
    for name, start, end in FILM_TIMELINE:
        timestamp = FILM_SAMPLE_TIMES[name]
        if not start <= timestamp < end:
            raise RuntimeError(f"film sample for {name} is outside its phase")
        frame_index = min(SPEC.frame_count - 1, int(timestamp * SPEC.fps))
        samples[name] = {
            "timestamp": frame_index / SPEC.fps,
            "frame": frame_index,
        }
    return samples


def browser_film_plan() -> dict[str, object]:
    actions: list[dict[str, object]] = [
        {"frame": 0, "do": "click", "selector": "#copy-challenge-btn"},
        {"frame": 1, "do": "selectChallenge"},
        {"frame": 35, "do": "click", "selector": "#maze-board"},
    ]
    for index, direction in enumerate(
        CANONICAL.shortest_route[: CANONICAL.trap.approach_index]
    ):
        actions.append(
            {
                "frame": 36 + index * 2,
                "do": "key",
                "code": KEY_CODE[direction],
            }
        )
    actions.extend(
        [
            {"frame": 64, "do": "click", "selector": "#hint-btn"},
            {"frame": 65, "do": "click", "selector": "#maze-board"},
            {
                "frame": 66,
                "do": "key",
                "code": KEY_CODE[CANONICAL.trap.turn],
            },
        ]
    )
    tail = (
        CANONICAL.trap.return_direction,
    ) + CANONICAL.shortest_route[CANONICAL.trap.approach_index :]
    for index, direction in enumerate(tail):
        actions.append(
            {
                "frame": 78 + index * 4,
                "do": "key",
                "code": KEY_CODE[direction],
            }
        )
    actions.append({"frame": 96, "do": "click", "selector": "#restart-btn"})
    for index, direction in enumerate(CANONICAL.shortest_route):
        actions.append(
            {
                "frame": 120 + index * 3,
                "do": "key",
                "code": KEY_CODE[direction],
            }
        )
    actions.extend(
        [
            {"frame": 204, "do": "click", "selector": "#restart-btn"},
            {
                "frame": 228,
                "do": "navigate",
                "fragment": challenge_fragment(HANDOFF),
            },
            {"frame": 252, "do": "click", "selector": "#maze-board"},
        ]
    )
    actions.sort(key=lambda action: (int(action["frame"]), str(action["do"])))
    return {
        "schema": "fogline-survey-film-plan/1.0",
        "width": SPEC.width,
        "height": SPEC.height,
        "fps": SPEC.fps,
        "frames": SPEC.frame_count,
        "phases": [
            {
                "name": name,
                "startFrame": int(start * SPEC.fps),
                "endFrame": int(end * SPEC.fps),
                "sampleFrame": film_sample_schedule()[name]["frame"],
                "callout": FILM_CAPTIONS[name][0],
                "detail": FILM_CAPTIONS[name][1],
            }
            for name, start, end in FILM_TIMELINE
        ],
        "actions": actions,
        "canonical": challenge_contract(CANONICAL),
        "handoff": challenge_contract(HANDOFF),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_text(path: Path) -> str:
    return (
        path.read_bytes()
        .decode("utf-8")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def source_json(path: Path) -> object:
    return json.loads(source_text(path))


def artifact_binding(path: Path, root: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def continuity_binding(root: Path) -> dict[str, object]:
    path = root / "snapshots" / "film-live-continuity.json"
    if not path.is_file():
        return {
            "path": "snapshots/film-live-continuity.json",
            "pending": True,
        }
    document = source_json(path)
    if document.get("schema") != "fogline-survey-film-live-continuity/1.0":
        raise RuntimeError("film/live continuity evidence has the wrong schema")
    return {
        **artifact_binding(path, root),
        "schema": document["schema"],
        "renderer": document["renderer"]["kind"],
    }


def evidence_document(root: Path = ROOT) -> dict[str, object]:
    _actions, replay = production_actions()
    gates = checkpoint_state_gates()
    claims = [
        {"id": claim_id, "stateGate": gates[claim_id]}
        for claim_id in (
            "hint",
            "trap",
            "detour",
            "resetAfterTrap",
            "optimal",
            "resetAfterOptimal",
            "handoff",
        )
    ]
    return {
        "schema": "fogline-survey-evidence/1.0",
        "channel": CHANNEL_ID,
        "publication": PUBLICATION_ID,
        "commission": {
            "id": "play-seeded-maze-return",
            "statusAtBuild": "open",
            "criterion": COMMISSION_CRITERION,
            "pairedDelivery": {
                "mp4": True,
                "webm": True,
                "live": True,
                "samePublication": True,
            },
            "positivePath": (
                "The trap-first replay proves the valid +2 knot, resets, then "
                "individual semantic keys complete RAPP-42 in exactly 18 "
                "without assistance."
            ),
            "visibleFailure": (
                "After an explicitly requested one-step E hint, the valid W "
                "turn enters the marked trap, raises the projected and final "
                "length to 20, and never hides the exit beacon."
            ),
            "exactReset": (
                "Restart same seed restores RAPP-42, its digest, entrance "
                "(0,0), north, zero steps, closed exit, empty trail, and no "
                "assistance."
            ),
            "offlineChallenge": (
                "A portable fragment exports exactly seed, full topology "
                "digest, and reference length; validation failure preserves "
                "the accepted game."
            ),
        },
        "fixtures": {
            "canonical": fixture_document(CANONICAL),
            "handoff": fixture_document(HANDOFF),
            "alternateAudit": [
                fixture_document(build_fixture(seed))
                for seed in ALTERNATE_AUDIT_SEEDS
            ],
        },
        "challengeContract": {
            "keys": ["seed", "topologyDigest", "referenceLength"],
            "example": challenge_contract(CANONICAL),
            "fragment": challenge_fragment(CANONICAL),
            "routeIncluded": False,
            "trailIncluded": False,
            "fragmentOnly": True,
            "invalidPreservesAcceptedState": True,
        },
        "claims": claims,
        "manifestReplay": {
            "manifest": "channel.production.json",
            "scene": 0,
            "actionCount": len(production_document()["videos"][0]["live"]["scenes"][0]["actions"]),
            "allowedActions": ["scroll", "click", "key", "type"],
            "individualSemanticKeyEvents": True,
            "autoSolveApi": False,
            "publicFixtureApi": False,
            "actualInputVerification": "CDP mouse and keyboard events",
            "exactTiming": True,
            "timingMode": "scheduled actions with bounded lateness",
            "maxActionLatenessSeconds": 0.8,
            "maxSceneOverrunSeconds": 1.0,
            "checkpointMode": "state-gated within bounded time windows",
            "activationVisibilityRequired": True,
            "checkpointVisibilityRequired": True,
            "checkpoints": replay["checkpoints"],
            "segments": replay["segments"],
        },
        "browserRuntime": {
            "contract": "real Chromium-family browser over reserved DevTools port",
            "startupTimeoutSeconds": 45,
            "earlyChildExitIsFatal": True,
            "viewports": [
                {"name": "desktop", "width": 1120, "height": 720},
                {"name": "mobile", "width": 390, "height": 844},
            ],
            "network": {
                "expectedExternalRequests": 0,
                "httpBlocked": True,
                "webSocketBlocked": True,
            },
            "routePrivacy": {
                "visibleTextChecked": True,
                "renderedDomChecked": True,
                "accessibilityTreeChecked": True,
                "fullRouteBeforeAttempt": False,
            },
            "geometry": {
                "perAction": True,
                "perCheckpoint": True,
                "horizontalOverflowAllowedPixels": 1,
                "minimumVisibleFontPixels": 12,
                "lowerThirdCriticalContent": False,
                "mobileCriticalSpanMaximumPixels": 800,
                "mobileDocumentHeightMaximumPixels": 1800,
            },
            "cleanup": {
                "browserExitRequired": True,
                "profileRemovalRequired": True,
                "errorsAreFatal": True,
            },
        },
        "film": {
            "renderer": "live-app-chromium-capture",
            "width": SPEC.width,
            "height": SPEC.height,
            "fps": SPEC.fps,
            "duration": SPEC.duration,
            "frames": SPEC.frame_count,
            "timeline": [
                {"phase": name, "start": start, "end": end}
                for name, start, end in FILM_TIMELINE
            ],
            "contentSamples": film_sample_schedule(),
            "sequence": [
                phase for phase, _start, _end in FILM_TIMELINE
            ],
            "typography": {
                "criticalTextSourcePixels": FILM_CRITICAL_TEXT_PIXELS,
                "fullDigestSourcePixels": FILM_CRITICAL_TEXT_PIXELS,
                "fullDigestCharacters": 64,
                "liveHierarchyMatched": True,
            },
            "routePrintedBeforeAttempt": False,
            "exitBeaconAlwaysMarked": True,
            "continuity": continuity_binding(root),
        },
        "attestations": {
            "rights": (
                "All code, prose, maze graphics, typography, film frames, "
                "and interface artwork were created for this candidate."
            ),
            "privacy": (
                "The bundle contains no people, personal data, customer data, "
                "locations, analytics, credentials, or secrets."
            ),
            "noSecrets": True,
            "networkRequests": False,
            "externalRuntimeResources": False,
            "copiedImagery": False,
            "audio": False,
        },
        "sourceBindings": [
            artifact_binding(root / relative, root)
            for relative in EVIDENCE_SOURCE_PATHS
        ],
    }


FONT = {
    " ": ("00000",) * 7,
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    ":": ("00000", "00110", "00110", "00000", "00110", "00110", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "=": ("00000", "11111", "00000", "11111", "00000", "00000", "00000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    ",": ("00000", "00000", "00000", "00000", "00110", "00100", "01000"),
    "#": ("01010", "11111", "01010", "01010", "11111", "01010", "00000"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
}

BG = (5, 17, 18)
HEADER = (9, 35, 35)
PANEL = (11, 31, 31)
FOG = (5, 13, 15)
FOG_LINE = (18, 47, 49)
FLOOR = (25, 66, 59)
WALL = (213, 232, 214)
INK = (232, 241, 228)
MUTED = (133, 169, 157)
MINT = (91, 229, 174)
AMBER = (255, 203, 105)
RED = (255, 105, 105)
PURPLE = (215, 169, 255)
BLUE = (94, 184, 211)


def _rgb(color: RGB) -> bytes:
    return bytes(color)


class Canvas:
    def __init__(self, width: int, height: int, background: RGB):
        self.width = width
        self.height = height
        self.pixels = bytearray(_rgb(background) * (width * height))

    def rect(self, x: int, y: int, width: int, height: int, color: RGB) -> None:
        left = max(0, x)
        top = max(0, y)
        right = min(self.width, x + width)
        bottom = min(self.height, y + height)
        if left >= right or top >= bottom:
            return
        row = _rgb(color) * (right - left)
        stride = self.width * 3
        for row_index in range(top, bottom):
            start = row_index * stride + left * 3
            self.pixels[start : start + len(row)] = row

    def border(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: RGB,
        thickness: int = 2,
    ) -> None:
        self.rect(x, y, width, thickness, color)
        self.rect(x, y + height - thickness, width, thickness, color)
        self.rect(x, y, thickness, height, color)
        self.rect(x + width - thickness, y, thickness, height, color)

    def line(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        color: RGB,
        thickness: int = 1,
    ) -> None:
        x0, y0 = start
        x1, y1 = end
        delta_x = abs(x1 - x0)
        delta_y = -abs(y1 - y0)
        step_x = 1 if x0 < x1 else -1
        step_y = 1 if y0 < y1 else -1
        error = delta_x + delta_y
        radius = max(0, thickness // 2)
        while True:
            self.rect(
                x0 - radius,
                y0 - radius,
                max(1, thickness),
                max(1, thickness),
                color,
            )
            if x0 == x1 and y0 == y1:
                break
            doubled = error * 2
            if doubled >= delta_y:
                error += delta_y
                x0 += step_x
            if doubled <= delta_x:
                error += delta_x
                y0 += step_y

    def circle(self, x: int, y: int, radius: int, color: RGB) -> None:
        radius_squared = radius * radius
        for offset_y in range(-radius, radius + 1):
            width = int((radius_squared - offset_y * offset_y) ** 0.5)
            self.rect(x - width, y + offset_y, width * 2 + 1, 1, color)

    def ring(
        self,
        x: int,
        y: int,
        radius: int,
        color: RGB,
        inner: RGB,
        thickness: int = 3,
    ) -> None:
        self.circle(x, y, radius, color)
        self.circle(x, y, max(0, radius - thickness), inner)

    def text(
        self,
        x: int,
        y: int,
        value: str,
        color: RGB,
        scale: int = 1,
    ) -> None:
        cursor = x
        for character in value.upper():
            glyph = FONT.get(character, FONT["?"])
            for row_index, row in enumerate(glyph):
                for column_index, bit in enumerate(row):
                    if bit == "1":
                        self.rect(
                            cursor + column_index * scale,
                            y + row_index * scale,
                            scale,
                            scale,
                            color,
                        )
            cursor += 6 * scale

    def centered_text(
        self,
        center_x: int,
        y: int,
        value: str,
        color: RGB,
        scale: int = 1,
    ) -> None:
        width = max(0, len(value) * 6 * scale - scale)
        self.text(center_x - width // 2, y, value, color, scale)


def _cell_center(cell: Cell) -> tuple[int, int]:
    map_x = 38
    map_y = 88
    cell_size = 64
    return (
        map_x + cell[0] * cell_size + cell_size // 2,
        map_y + cell[1] * cell_size + cell_size // 2,
    )


def _draw_maze(
    canvas: Canvas,
    fixture: MazeFixture,
    state: MazeState,
) -> None:
    map_x = 38
    map_y = 88
    cell_size = 64
    canvas.rect(map_x - 7, map_y - 7, 398, 398, PANEL)
    canvas.border(map_x - 7, map_y - 7, 398, 398, FOG_LINE, 3)

    for y in range(fixture.height):
        for x in range(fixture.width):
            cell = (x, y)
            left = map_x + x * cell_size
            top = map_y + y * cell_size
            if cell in state.revealed:
                canvas.rect(left, top, cell_size, cell_size, FLOOR)
                canvas.border(left, top, cell_size, cell_size, FOG_LINE, 1)
                openings = fixture.maze[cell]
                if "N" not in openings:
                    canvas.rect(left, top, cell_size, 3, WALL)
                if "E" not in openings:
                    canvas.rect(left + cell_size - 3, top, 3, cell_size, WALL)
                if "S" not in openings:
                    canvas.rect(left, top + cell_size - 3, cell_size, 3, WALL)
                if "W" not in openings:
                    canvas.rect(left, top, 3, cell_size, WALL)
            else:
                canvas.rect(left, top, cell_size, cell_size, FOG)
                canvas.border(left, top, cell_size, cell_size, (8, 25, 27), 1)
                for offset in range(-cell_size, cell_size * 2, 14):
                    canvas.line(
                        (left + max(0, offset), top + max(0, -offset)),
                        (
                            left + min(cell_size - 1, offset + cell_size),
                            top + min(cell_size - 1, cell_size - offset),
                        ),
                        (8, 24, 27),
                        1,
                    )

    trail = (fixture.entrance,) + state.trail
    for start, end in zip(trail, trail[1:]):
        canvas.line(_cell_center(start), _cell_center(end), MINT, 8)
        canvas.line(_cell_center(start), _cell_center(end), (25, 96, 75), 3)
    for cell in set(trail):
        center_x, center_y = _cell_center(cell)
        canvas.circle(center_x, center_y, 5, MINT)

    entrance_x, entrance_y = _cell_center(fixture.entrance)
    canvas.centered_text(entrance_x, entrance_y + 17, "IN", MUTED, 1)

    exit_x, exit_y = _cell_center(fixture.exit)
    exit_inner = FLOOR if fixture.exit in state.revealed else FOG
    canvas.ring(exit_x, exit_y, 18, PURPLE, exit_inner, 5)
    canvas.centered_text(exit_x, exit_y - 4, "X", PURPLE, 2)
    canvas.centered_text(exit_x, exit_y + 21, "EXIT", PURPLE, 1)

    if fixture.trap.cell in state.revealed:
        trap_x, trap_y = _cell_center(fixture.trap.cell)
        trap_inner = FLOOR
        canvas.ring(trap_x, trap_y, 16, RED, trap_inner, 5)
        canvas.centered_text(trap_x, trap_y - 5, "!", RED, 2)

    player_x, player_y = _cell_center(state.position)
    canvas.circle(player_x, player_y, 12, AMBER)
    dx, dy = DIRECTION_VECTOR[state.facing]
    canvas.line(
        (player_x, player_y),
        (player_x + dx * 20, player_y + dy * 20),
        INK,
        5,
    )


def _draw_compass(canvas: Canvas, state: MazeState) -> None:
    center_x = 850
    center_y = 222
    canvas.ring(center_x, center_y, 48, MUTED, PANEL, 3)
    canvas.centered_text(center_x, center_y - 68, "N", INK, 2)
    canvas.centered_text(center_x, center_y + 55, "S", MUTED, 2)
    canvas.centered_text(center_x - 66, center_y - 7, "W", MUTED, 2)
    canvas.centered_text(center_x + 67, center_y - 7, "E", MUTED, 2)
    dx, dy = DIRECTION_VECTOR[state.facing]
    canvas.line(
        (center_x, center_y),
        (center_x + dx * 34, center_y + dy * 34),
        AMBER,
        8,
    )
    canvas.circle(center_x, center_y, 6, INK)


def _film_scene(
    time_seconds: float,
) -> tuple[MazeFixture, MazeState, str, str, str | None]:
    phase = film_phase(time_seconds)
    if phase == "challenge":
        return (
            CANONICAL,
            initial_state(CANONICAL),
            phase,
            "COPY / SHARE / OPEN OFFLINE",
            "SEED + DIGEST + REFERENCE ONLY",
        )
    if phase == "trap-approach":
        progress = min(
            CANONICAL.trap.approach_index,
            int(
                (time_seconds - 3.0)
                / (5.5 - 3.0)
                * (CANONICAL.trap.approach_index + 1)
            ),
        )
        return (
            CANONICAL,
            state_after(CANONICAL, CANONICAL.shortest_route[:progress]),
            phase,
            "TRAP FIRST / EXIT STAYS MARKED",
            "APPROACH THE KNOT",
        )
    if phase == "trap-plus-two":
        approach = state_after(
            CANONICAL,
            CANONICAL.shortest_route[: CANONICAL.trap.approach_index],
        )
        trap = move_state(CANONICAL, approach, CANONICAL.trap.turn)
        if time_seconds < 6.5:
            state = trap
        else:
            tail = (
                CANONICAL.trap.return_direction,
            ) + CANONICAL.shortest_route[CANONICAL.trap.approach_index :]
            progress = min(
                len(tail),
                max(0, int((time_seconds - 6.5) / 1.5 * (len(tail) + 1))),
            )
            state = state_after(CANONICAL, tail[:progress], state=trap)
        return (
            CANONICAL,
            state,
            phase,
            "KNOT / TRAP +2 / EXIT VISIBLE",
            "BEST FINISH 20",
        )
    if phase == "reset-after-trap":
        return (
            CANONICAL,
            initial_state(CANONICAL),
            phase,
            "EXACT RESET / NORTH / ZERO",
            "CLOSED EXIT / EMPTY TRAIL",
        )
    if phase == "optimal-18":
        progress = min(
            len(CANONICAL.shortest_route),
            int(
                (time_seconds - 10.0)
                / (15.0 - 10.0)
                * (len(CANONICAL.shortest_route) + 1)
            ),
        )
        return (
            CANONICAL,
            state_after(CANONICAL, CANONICAL.shortest_route[:progress]),
            phase,
            "UNASSISTED / DIRECT / 18",
            "INDIVIDUAL ARROW KEYS",
        )
    if phase == "optimal-complete":
        return (
            CANONICAL,
            state_after(CANONICAL, CANONICAL.shortest_route),
            phase,
            "EXIT OPEN / 18 = REFERENCE",
            "UNASSISTED OPTIMAL",
        )
    if phase == "reset-after-optimal":
        return (
            CANONICAL,
            initial_state(CANONICAL),
            phase,
            "EXACT RESET / PROOF REPEATS",
            "NORTH / ZERO / EMPTY TRAIL",
        )
    if phase == "alternate-fresh":
        return (
            HANDOFF,
            initial_state(HANDOFF),
            phase,
            "FOG-7 / UNTOUCHED CHALLENGE",
            "ZERO STEPS / NO ASSISTANCE",
        )
    return (
        HANDOFF,
        initial_state(HANDOFF),
        phase,
        "YOUR TURN / MOVEMENT FOCUSED",
        "FOG-7 / ARROWS OR WASD NOW",
    )


def frame_rgb(
    frame_index: int,
    spec: RenderSpec = SPEC,
) -> bytes:
    raise RuntimeError(
        "standalone bitmap film rendering is retired; use render_live.mjs"
    )
    if not 0 <= frame_index < spec.frame_count:
        raise ValueError("frame index is outside the film")
    time_seconds = frame_index / spec.fps
    fixture, state, phase, banner, extra = _film_scene(time_seconds)
    canvas = Canvas(spec.width, spec.height, BG)
    canvas.rect(0, 0, spec.width, 64, HEADER)
    canvas.text(24, 14, "FOGLINE SURVEY", INK, 5)
    canvas.text(500, 21, phase.replace("-", " / "), MINT, 3)
    canvas.text(38, 68, "REVEALED SURVEY", MUTED, 2)
    _draw_maze(canvas, fixture, state)

    panel_x = 462
    canvas.rect(panel_x, 82, 470, 382, PANEL)
    canvas.border(panel_x, 82, 470, 382, FOG_LINE, 2)
    canvas.text(panel_x + 20, 96, f"SEED {fixture.seed}", INK, 3)
    canvas.text(panel_x + 20, 120, "FULL TOPOLOGY DIGEST", MUTED, 2)
    for index in range(4):
        start = index * 16
        canvas.text(
            panel_x + 20,
            140 + index * 29,
            fixture.topology_digest[start : start + 16],
            BLUE,
            FILM_CRITICAL_TEXT_SCALE,
        )
    canvas.text(
        panel_x + 20,
        262,
        f"STEPS {len(state.accepted_moves)} / REF {len(fixture.shortest_route)}",
        INK,
        3,
    )
    projection_color = (
        RED
        if state.projected_total > len(fixture.shortest_route)
        else MINT
    )
    canvas.text(
        panel_x + 20,
        288,
        f"BEST FINISH {state.projected_total}",
        projection_color,
        FILM_CRITICAL_TEXT_SCALE,
    )
    canvas.text(
        panel_x + 20,
        322,
        f"EXIT {'OPEN' if state.exit_open else 'CLOSED'} / MARKED",
        PURPLE,
        3,
    )

    assist_color = AMBER if state.assistance_used else MUTED
    assist = (
        f"FACE {state.facing} / ASSISTED"
        if state.assistance_used
        else f"FACE {state.facing} / UNASSISTED"
    )
    canvas.text(panel_x + 20, 350, assist, assist_color, 3)
    canvas.text(
        panel_x + 20,
        374,
        "TRAIL " + ("EMPTY" if not state.trail else "REVEALED"),
        MINT,
        2,
    )

    if state.status == "trap" or phase == "trap-plus-two":
        notice = "KNOT / TRAP +2"
        notice_color = RED
        notice_fill = (61, 26, 28)
    elif state.completed and state.matched_optimal:
        notice = "OPTIMAL / 18"
        notice_color = MINT
        notice_fill = (18, 51, 42)
    elif phase in {"reset-after-trap", "reset-after-optimal"}:
        notice = "EXACT RESET"
        notice_color = MINT
        notice_fill = (18, 51, 42)
    elif phase == "challenge":
        notice = "OFFLINE / 3 FIELDS"
        notice_color = BLUE
        notice_fill = (12, 42, 48)
    elif phase in {"alternate-fresh", "takeover"}:
        notice = "FRESH / ZERO STEPS"
        notice_color = AMBER
        notice_fill = (45, 39, 20)
    else:
        notice = "DIRECT PLAY"
        notice_color = MINT
        notice_fill = (18, 51, 42)
    canvas.rect(panel_x + 18, 396, 430, 56, notice_fill)
    canvas.border(panel_x + 18, 396, 430, 56, notice_color, 2)
    canvas.text(
        panel_x + 30,
        409,
        notice,
        notice_color,
        FILM_CRITICAL_TEXT_SCALE,
    )

    banner_color = RED if phase == "trap-plus-two" else MINT
    if phase == "takeover":
        banner_color = AMBER
    canvas.rect(0, 470, spec.width, 70, HEADER)
    canvas.text(
        20,
        478,
        banner,
        banner_color,
        FILM_CRITICAL_TEXT_SCALE,
    )
    canvas.text(20, 513, extra or "ARROWS / WASD / EXACT RESET", MUTED, 3)
    return bytes(canvas.pixels)


def frame_digest(
    frame_index: int,
    spec: RenderSpec = SPEC,
) -> str:
    return hashlib.sha256(frame_rgb(frame_index, spec)).hexdigest()


def iter_frames(spec: RenderSpec = SPEC) -> Iterator[bytes]:
    for frame_index in range(spec.frame_count):
        yield frame_rgb(frame_index, spec)


def thumbnail_svg(spec: RenderSpec = SPEC) -> str:
    digest = CANONICAL.topology_digest
    revealed = set(initial_state(CANONICAL).revealed)
    cells = []
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            left = 64 + x * 58
            top = 108 + y * 58
            cell = (x, y)
            fill = "#19423b" if cell in revealed else "#071012"
            cells.append(
                f'<rect x="{left}" y="{top}" width="58" height="58" '
                f'fill="{fill}" stroke="#123033" stroke-width="1"/>'
            )
            if cell in revealed:
                openings = CANONICAL.maze[cell]
                if "N" not in openings:
                    cells.append(
                        f'<path d="M{left} {top}h58" stroke="#d5e8d6" '
                        'stroke-width="4"/>'
                    )
                if "E" not in openings:
                    cells.append(
                        f'<path d="M{left + 58} {top}v58" '
                        'stroke="#d5e8d6" stroke-width="4"/>'
                    )
                if "S" not in openings:
                    cells.append(
                        f'<path d="M{left} {top + 58}h58" '
                        'stroke="#d5e8d6" stroke-width="4"/>'
                    )
                if "W" not in openings:
                    cells.append(
                        f'<path d="M{left} {top}v58" stroke="#d5e8d6" '
                        'stroke-width="4"/>'
                    )
    exit_x = 64 + EXIT[0] * 58 + 29
    exit_y = 108 + EXIT[1] * 58 + 29
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" aria-labelledby="title desc">
  <title id="title">Fogline Survey</title>
  <desc id="desc">Original top-down fog maze artwork with a compass, marked exit beacon, RAPP-42 digest, and reference length 18.</desc>
  <rect width="960" height="540" fill="#051112"/>
  <rect width="960" height="76" fill="#092323"/>
  <text x="38" y="49" fill="#e8f1e4" font-family="monospace" font-size="32" font-weight="800">FOGLINE SURVEY</text>
  <g>{''.join(cells)}</g>
  <circle cx="{exit_x}" cy="{exit_y}" r="20" fill="none" stroke="#d7a9ff" stroke-width="7"/>
  <text x="{exit_x}" y="{exit_y + 7}" text-anchor="middle" fill="#d7a9ff" font-family="monospace" font-size="22" font-weight="800">X</text>
  <circle cx="93" cy="137" r="13" fill="#ffcb69"/>
  <path d="M93 137v-28" stroke="#e8f1e4" stroke-width="7" stroke-linecap="round"/>
  <rect x="458" y="108" width="450" height="344" rx="18" fill="#0b1f1f" stroke="#123033" stroke-width="3"/>
  <text x="490" y="154" fill="#e8f1e4" font-family="monospace" font-size="25" font-weight="800">SEED RAPP-42</text>
  <text x="490" y="194" fill="#85a99d" font-family="monospace" font-size="16">SHA-256 TOPOLOGY</text>
  <text x="490" y="224" fill="#5eb8d3" font-family="monospace" font-size="14">{escape(digest[:32])}</text>
  <text x="490" y="247" fill="#5eb8d3" font-family="monospace" font-size="14">{escape(digest[32:])}</text>
  <text x="490" y="301" fill="#5be5ae" font-family="monospace" font-size="27" font-weight="800">REFERENCE 18</text>
  <text x="490" y="345" fill="#ffcb69" font-family="monospace" font-size="18">ONE EARNED BEARING</text>
  <text x="490" y="385" fill="#d7a9ff" font-family="monospace" font-size="18">EXIT BEACON ALWAYS MARKED</text>
  <text x="490" y="425" fill="#85a99d" font-family="monospace" font-size="16">ARROWS / WASD · ANY VALID SEED</text>
</svg>
"""


def ffmpeg_command(
    executable: str,
    target: Path,
    spec: RenderSpec = SPEC,
) -> list[str]:
    return [
        executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-f",
        "image2pipe",
        "-framerate",
        str(spec.fps),
        "-vcodec",
        "png",
        "-i",
        "pipe:0",
        "-an",
        "-map_metadata",
        "-1",
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-coder",
        "1",
        "-context",
        "1",
        "-g",
        "1",
        "-slicecrc",
        "1",
        "-threads",
        "1",
        "-pix_fmt",
        "bgr0",
        "-color_range",
        "pc",
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-f",
        "matroska",
        str(target),
    ]


def _executable_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def _configured_tool_values(name: str) -> Iterator[str]:
    upper = name.upper()
    for variable in (
        f"RAPP_{upper}",
        f"RAPP_VISION_{upper}",
        upper,
        f"{upper}_PATH",
        f"{upper}_BIN",
    ):
        value = os.environ.get(variable)
        if value:
            yield value
    bin_directory = os.environ.get("FFMPEG_BIN")
    if bin_directory and name in {"ffmpeg", "ffprobe"}:
        yield str(Path(bin_directory) / _executable_name(name))


def _common_tool_candidates(name: str) -> Iterator[Path]:
    executable = _executable_name(name)
    for path in (
        Path("/usr/bin") / name,
        Path("/usr/local/bin") / name,
        Path("/opt/homebrew/bin") / name,
        Path("/opt/local/bin") / name,
    ):
        yield path
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if packages.is_dir():
            for package in sorted(packages.glob("Gyan.FFmpeg.*")):
                yield from sorted(package.glob(f"ffmpeg-*/bin/{executable}"))
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            yield Path(root) / "ffmpeg" / "bin" / executable


def _resolve_candidate(value: str) -> str | None:
    candidate = value.strip()
    if (
        len(candidate) >= 2
        and candidate[0] == candidate[-1]
        and candidate[0] in {'"', "'"}
    ):
        candidate = candidate[1:-1]
    expanded = Path(os.path.expandvars(candidate)).expanduser()
    if expanded.is_absolute() or expanded.parent != Path("."):
        if expanded.is_file() and os.access(expanded, os.X_OK):
            return str(expanded.resolve())
        return None
    found = shutil.which(candidate)
    return str(Path(found).resolve()) if found else None


def discover_executable(name: str, explicit: str | None = None) -> str:
    if explicit:
        resolved = _resolve_candidate(explicit)
        if not resolved:
            raise RuntimeError(f"{name} executable does not exist: {explicit}")
        return resolved
    for value in _configured_tool_values(name):
        resolved = _resolve_candidate(value)
        if resolved:
            return resolved
    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())
    for candidate in _common_tool_candidates(name):
        if candidate.is_file():
            return str(candidate.resolve())
    raise RuntimeError(
        f"{name} executable not found via RAPP_{name.upper()}, environment, "
        "PATH, or common portable locations"
    )


def _browser_candidate(value: str | None) -> str | None:
    if not value:
        return None
    resolved = _resolve_candidate(value)
    if resolved and re.search(
        r"(chrome|chromium|edge|brave)",
        Path(resolved).name,
        flags=re.IGNORECASE,
    ):
        return resolved
    return None


def discover_browser(explicit: str | None = None) -> str:
    if explicit:
        found = _browser_candidate(explicit)
        if not found:
            raise RuntimeError(
                f"Chromium-family browser does not exist: {explicit}"
            )
        return found
    for variable in (
        "RAPP_BROWSER",
        "RAPP_VISION_BROWSER",
        "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH",
        "EDGE_BIN",
        "CHROME_BIN",
        "CHROMIUM_BIN",
    ):
        found = _browser_candidate(os.environ.get(variable))
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
        found = _browser_candidate(command)
        if found:
            return found
    candidates: list[Path] = []
    if os.name == "nt":
        roots = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        for root in filter(None, roots):
            candidates.extend(
                [
                    Path(root)
                    / "Microsoft"
                    / "Edge"
                    / "Application"
                    / "msedge.exe",
                    Path(root)
                    / "Google"
                    / "Chrome"
                    / "Application"
                    / "chrome.exe",
                    Path(root)
                    / "Chromium"
                    / "Application"
                    / "chrome.exe",
                    Path(root)
                    / "BraveSoftware"
                    / "Brave-Browser"
                    / "Application"
                    / "brave.exe",
                ]
            )
    else:
        candidates.extend(
            [
                Path("/usr/bin/google-chrome"),
                Path("/usr/bin/microsoft-edge"),
                Path("/usr/bin/chromium"),
                Path("/usr/bin/brave-browser"),
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path(
                    "/Applications/Microsoft Edge.app/Contents/MacOS/"
                    "Microsoft Edge"
                ),
            ]
        )
    for candidate in candidates:
        found = _browser_candidate(str(candidate))
        if found:
            return found
    raise RuntimeError(
        "Chromium-family browser not found via RAPP_BROWSER, environment, "
        "PATH, or common locations"
    )


def _decode_rgb_frame(path: Path, ffmpeg: str) -> bytes:
    completed = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        check=False,
        capture_output=True,
        timeout=120,
    )
    if completed.returncode:
        raise RuntimeError(
            completed.stderr.decode("utf-8", errors="replace").strip()
            or f"cannot decode {path}"
        )
    expected = SPEC.width * SPEC.height * 3
    if len(completed.stdout) != expected:
        raise RuntimeError(
            f"decoded {len(completed.stdout)} bytes from {path}, "
            f"expected {expected}"
        )
    return completed.stdout


def _decode_rgb_samples(
    path: Path,
    indexes: Sequence[int],
    ffmpeg: str,
) -> list[bytes]:
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
        timeout=180,
    )
    if completed.returncode:
        raise RuntimeError(
            completed.stderr.decode("utf-8", errors="replace").strip()
            or f"cannot decode samples from {path}"
        )
    frame_bytes = SPEC.width * SPEC.height * 3
    if len(completed.stdout) != frame_bytes * len(indexes):
        raise RuntimeError("decoded browser-film sample count is incomplete")
    return [
        completed.stdout[offset * frame_bytes : (offset + 1) * frame_bytes]
        for offset in range(len(indexes))
    ]


def _finalize_continuity(
    continuity_path: Path,
    master_path: Path,
    sample_dir: Path,
    ffmpeg: str,
) -> None:
    document = source_json(continuity_path)
    phases = document.get("phases")
    if not isinstance(phases, list):
        raise RuntimeError("browser renderer emitted no continuity phases")
    expected_names = [phase for phase, _start, _end in FILM_TIMELINE]
    if [phase.get("phase") for phase in phases] != expected_names:
        raise RuntimeError("browser renderer continuity phases drifted")
    indexes = [int(phase["frame"]) for phase in phases]
    master_frames = _decode_rgb_samples(master_path, indexes, ffmpeg)
    for phase, master_rgb in zip(phases, master_frames, strict=True):
        screenshot = sample_dir / f"{phase['phase']}.png"
        if not screenshot.is_file():
            raise RuntimeError(f"browser screenshot missing: {screenshot.name}")
        live_rgb = _decode_rgb_frame(screenshot, ffmpeg)
        if live_rgb != master_rgb:
            raise RuntimeError(
                f"master pixels differ from live screenshot: {phase['phase']}"
            )
        digest = hashlib.sha256(live_rgb).hexdigest()
        phase["liveRgbSha256"] = digest
        phase["masterRgbSha256"] = digest
        phase["pixelExact"] = True
    document["pixelBinding"] = {
        "algorithm": "sha256-rgb24",
        "exactAtEveryDeclaredPhase": True,
        "sampleCount": len(phases),
        "width": SPEC.width,
        "height": SPEC.height,
    }
    document["masterSha256"] = _sha256(master_path)
    write_json(continuity_path, document)


def render_master(
    output_root: Path,
    ffmpeg: str,
    spec: RenderSpec = SPEC,
    *,
    browser: str | None = None,
    node: str | None = None,
) -> Path:
    target = output_root / spec.master_relative
    partial = target.with_name(f"{target.stem}.partial.mkv")
    continuity = output_root / "snapshots" / "film-live-continuity.json"
    partial_continuity = continuity.with_name(
        "film-live-continuity.partial.json"
    )
    plan_path = output_root / ".film-plan.json"
    sample_dir = output_root / ".film-samples"
    profile = output_root / ".film-browser-profile"
    live_renderer = output_root / "render_live.mjs"
    if not live_renderer.is_file():
        live_renderer = LIVE_RENDERER_PATH
    if target.exists() or partial.exists():
        raise RuntimeError(f"refusing to replace existing master: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    continuity.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(sample_dir, ignore_errors=True)
    shutil.rmtree(profile, ignore_errors=True)
    partial_continuity.unlink(missing_ok=True)
    write_json(plan_path, browser_film_plan())
    command = [
        node or discover_executable("node"),
        str(live_renderer),
        "--app",
        str(output_root / "apps" / f"{PUBLICATION_ID}.html"),
        "--browser",
        browser or discover_browser(),
        "--continuity",
        str(partial_continuity),
        "--ffmpeg",
        ffmpeg,
        "--output",
        str(partial),
        "--plan",
        str(plan_path),
        "--profile",
        str(profile),
        "--sample-dir",
        str(sample_dir),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=900,
        )
        if completed.returncode:
            raise RuntimeError(
                "live-app browser render failed: "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        if not partial.is_file() or partial.stat().st_size <= 0:
            raise RuntimeError("browser renderer produced no lossless master")
        if not partial_continuity.is_file():
            raise RuntimeError("browser renderer produced no continuity evidence")
        _finalize_continuity(
            partial_continuity,
            partial,
            sample_dir,
            ffmpeg,
        )
        partial.replace(target)
        partial_continuity.replace(continuity)
    finally:
        partial.unlink(missing_ok=True)
        partial_continuity.unlink(missing_ok=True)
        plan_path.unlink(missing_ok=True)
        shutil.rmtree(sample_dir, ignore_errors=True)
        shutil.rmtree(profile, ignore_errors=True)
    return target


def _probe(path: Path, ffprobe: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            (
                "stream=codec_type,codec_name,pix_fmt,width,height,color_space,"
                "color_transfer,color_primaries,color_range,avg_frame_rate:"
                "format=duration"
            ),
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(
            f"ffprobe failed for {path}: "
            f"{completed.stderr.strip() or completed.returncode}"
        )
    try:
        payload = json.loads(completed.stdout)
        streams = payload["streams"]
        videos = [
            stream for stream in streams if stream.get("codec_type") == "video"
        ]
        audios = [
            stream for stream in streams if stream.get("codec_type") == "audio"
        ]
        if len(videos) != 1:
            raise ValueError("expected one video stream")
        stream = videos[0]
        duration = float(payload["format"]["duration"])
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError(f"ffprobe returned malformed metadata for {path}") from exc
    record: dict[str, object] = {
        "codec": stream.get("codec_name"),
        "pixelFormat": stream.get("pix_fmt"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "duration": round(duration, 6),
        "averageFrameRate": stream.get("avg_frame_rate"),
        "streamCount": len(streams),
        "audioStreamCount": len(audios),
    }
    for source, target in (
        ("color_space", "colorSpace"),
        ("color_transfer", "colorTransfer"),
        ("color_primaries", "colorPrimaries"),
        ("color_range", "colorRange"),
    ):
        if stream.get(source) is not None:
            record[target] = stream[source]
    return record


def _artifact(path: Path, root: Path, ffprobe: str) -> dict[str, object]:
    return {
        **artifact_binding(path, root),
        **_probe(path, ffprobe),
    }


def delivery_document(
    root: Path,
    ffprobe: str,
) -> dict[str, object]:
    master = root / SPEC.master_relative
    mp4 = root / "media" / f"{PUBLICATION_ID}.mp4"
    webm = root / "media" / f"{PUBLICATION_ID}.webm"
    required = [master, mp4, webm]
    required.extend(root / relative for relative in DELIVERY_SOURCE_PATHS)
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"delivery artifact missing: {missing[0]}")
    continuity = source_json(
        root / "snapshots" / "film-live-continuity.json"
    )
    if continuity.get("schema") != "fogline-survey-film-live-continuity/1.0":
        raise RuntimeError("delivery continuity evidence has the wrong schema")
    content_samples = {
        phase["phase"]: {
            "frame": phase["frame"],
            "timestamp": phase["timestamp"],
            "sha256": phase["masterRgbSha256"],
        }
        for phase in continuity["phases"]
    }
    return {
        "schema": "fogline-survey-delivery/1.0",
        "channel": CHANNEL_ID,
        "publication": PUBLICATION_ID,
        "artifacts": {
            "master": _artifact(master, root, ffprobe),
            "mp4": _artifact(mp4, root, ffprobe),
            "webm": _artifact(webm, root, ffprobe),
        },
        "sourceArtifacts": [
            artifact_binding(root / relative, root)
            for relative in DELIVERY_SOURCE_PATHS
        ],
        "binding": {
            "algorithm": "sha256",
            "artifactCount": 3 + len(DELIVERY_SOURCE_PATHS),
            "pathStyle": "POSIX-relative",
            "selfExcluded": "delivery.json",
        },
        "objective": {
            "seed": CANONICAL.seed,
            "topologyDigest": CANONICAL.topology_digest,
            "referenceLength": len(CANONICAL.shortest_route),
            "detourLength": len(CANONICAL.detour_route),
            "handoffSeed": HANDOFF.seed,
            "handoffDigest": HANDOFF.topology_digest,
            "handoffReferenceLength": len(HANDOFF.shortest_route),
            "challengeContract": challenge_contract(CANONICAL),
            "challengeFragment": challenge_fragment(CANONICAL),
            "alternateSeeds": [
                {
                    "seed": fixture.seed,
                    "topologyDigest": fixture.topology_digest,
                    "referenceLength": len(fixture.shortest_route),
                    "trap": list(fixture.trap.cell),
                    "detourLength": len(fixture.detour_route),
                }
                for fixture in (
                    build_fixture(seed)
                    for seed in ALTERNATE_AUDIT_SEEDS
                )
            ],
        },
        "render": {
            "renderer": "live-app-chromium-capture",
            "width": SPEC.width,
            "height": SPEC.height,
            "fps": SPEC.fps,
            "frames": SPEC.frame_count,
            "duration": SPEC.duration,
            "masterCodec": "ffv1",
            "audio": False,
            "timeline": [
                {"phase": name, "start": start, "end": end}
                for name, start, end in FILM_TIMELINE
            ],
            "contentSamples": content_samples,
            "continuity": {
                "path": "snapshots/film-live-continuity.json",
                "sourceAppSha256": continuity["sourceAppSha256"],
                "renderer": continuity["renderer"]["kind"],
                "pixelBinding": continuity["pixelBinding"],
            },
            "sequence": [
                phase for phase, _start, _end in FILM_TIMELINE
            ],
            "typography": {
                "criticalTextSourcePixels": FILM_CRITICAL_TEXT_PIXELS,
                "fullDigestSourcePixels": FILM_CRITICAL_TEXT_PIXELS,
                "fullDigestCharacters": 64,
                "liveHierarchyMatched": True,
            },
        },
    }


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def write_artifacts(root: Path = ROOT) -> list[Path]:
    manifest = write_json(root / "channel.production.json", production_document())
    snapshots = write_json(
        root / "snapshots" / "canonical-states.json",
        canonical_states_document(),
    )
    thumbnail = root / SPEC.thumbnail_relative
    thumbnail.parent.mkdir(parents=True, exist_ok=True)
    thumbnail.write_text(
        thumbnail_svg(),
        encoding="utf-8",
        newline="\n",
    )
    evidence = write_json(
        root / "evidence.json",
        evidence_document(root),
    )
    return [manifest, snapshots, thumbnail, evidence]


def write_delivery(root: Path, ffprobe: str) -> Path:
    return write_json(root / "delivery.json", delivery_document(root, ffprobe))


def validate_manifest(path: Path = MANIFEST_PATH) -> None:
    try:
        document = source_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read production manifest: {exc}") from exc
    if document != production_document():
        raise RuntimeError("production manifest differs from renderer source")


def check_delivery(root: Path, ffprobe: str) -> list[str]:
    errors: list[str] = []
    expected_source = {
        record["path"]: record
        for record in delivery_document(root, ffprobe)["sourceArtifacts"]
    }
    try:
        actual = source_json(root / "delivery.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read delivery.json: {exc}"]
    actual_source = {
        record["path"]: record
        for record in actual.get("sourceArtifacts", [])
        if isinstance(record, dict) and "path" in record
    }
    if actual_source != expected_source:
        errors.append("delivery source artifact bindings are stale")
    expected_artifacts = delivery_document(root, ffprobe)["artifacts"]
    if actual.get("artifacts") != expected_artifacts:
        errors.append("delivery media artifact bindings or probes are stale")
    for field in ("schema", "channel", "publication", "binding", "objective", "render"):
        expected = delivery_document(root, ffprobe)[field]
        if actual.get(field) != expected:
            errors.append(f"delivery field is stale: {field}")
    return errors


def check_release(root: Path, ffprobe: str) -> None:
    validate_manifest(root / "channel.production.json")
    expected_snapshots = canonical_states_document()
    actual_snapshots = source_json(
        root / "snapshots" / "canonical-states.json"
    )
    if actual_snapshots != expected_snapshots:
        raise RuntimeError("canonical snapshots are stale")
    if source_text(root / SPEC.thumbnail_relative) != thumbnail_svg():
        raise RuntimeError("thumbnail is stale")
    continuity_path = root / "snapshots" / "film-live-continuity.json"
    continuity = source_json(continuity_path)
    if continuity.get("renderer", {}).get("kind") != "live-app-chromium-capture":
        raise RuntimeError("film was not rendered from the live app")
    if continuity.get("sourceAppSha256") != _sha256(
        root / "apps" / f"{PUBLICATION_ID}.html"
    ):
        raise RuntimeError("film/live app source binding is stale")
    if continuity.get("masterSha256") != _sha256(root / SPEC.master_relative):
        raise RuntimeError("film/live master binding is stale")
    if not continuity.get("pixelBinding", {}).get(
        "exactAtEveryDeclaredPhase"
    ):
        raise RuntimeError("film/live phase pixel binding is incomplete")
    expected_evidence = evidence_document(root)
    actual_evidence = source_json(root / "evidence.json")
    if actual_evidence != expected_evidence:
        raise RuntimeError("evidence is stale")
    delivery_errors = check_delivery(root, ffprobe)
    if delivery_errors:
        raise RuntimeError("; ".join(delivery_errors))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("artifacts", "render", "delivery", "check", "tools"),
    )
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    parser.add_argument("--browser")
    parser.add_argument("--node")
    parser.add_argument("--output-root", type=Path, default=ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.output_root.resolve()
    try:
        if args.command == "tools":
            print(
                json.dumps(
                    {
                        "ffmpeg": discover_executable("ffmpeg", args.ffmpeg),
                        "ffprobe": discover_executable("ffprobe", args.ffprobe),
                        "browser": discover_browser(args.browser),
                        "node": discover_executable("node", args.node),
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "artifacts":
            for path in write_artifacts(root):
                print(path)
        elif args.command == "render":
            validate_manifest(root / "channel.production.json")
            print(
                render_master(
                    root,
                    discover_executable("ffmpeg", args.ffmpeg),
                    browser=discover_browser(args.browser),
                    node=discover_executable("node", args.node),
                )
            )
        elif args.command == "delivery":
            print(
                write_delivery(
                    root,
                    discover_executable("ffprobe", args.ffprobe),
                )
            )
        elif args.command == "check":
            check_release(
                root,
                discover_executable("ffprobe", args.ffprobe),
            )
            print("Fogline Survey release checks passed.")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
