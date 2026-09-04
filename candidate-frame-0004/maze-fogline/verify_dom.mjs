#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import { access, readFile, rm } from "node:fs/promises";
import { createServer } from "node:net";
import {
  basename,
  delimiter,
  dirname,
  extname,
  isAbsolute,
  join,
  resolve,
} from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const DEFAULTS = {
  app: join(ROOT, "apps", "maze-fogline.html"),
  continuity: join(ROOT, "snapshots", "film-live-continuity.json"),
  evidence: join(ROOT, "evidence.json"),
  manifest: join(ROOT, "channel.production.json"),
  profile: join(ROOT, `.browser-profile-${process.pid}`),
};
const CANONICAL_ROUTE = "SEESSWWSSENEESENNE".split("");
const CANONICAL_DIGEST =
  "126bf70440d3ef542c8dc97251726994e0f23422675e831f93309235ae085eda";
const ALTERNATE_SEEDS = Object.freeze(["FOG-7", "MIST-Δ", "A|B;C"]);
const INVALID_SEED_MESSAGE =
  "Seed must contain 1–64 UTF-8 bytes and no controls.";
const CHALLENGE_ERROR_MESSAGE =
  "Challenge fragment must contain exactly seed, topologyDigest, and " +
  "referenceLength matching the generated maze.";
const DIRECTIONS = Object.freeze([
  Object.freeze(["N", 0, -1, "S"]),
  Object.freeze(["E", 1, 0, "W"]),
  Object.freeze(["S", 0, 1, "N"]),
  Object.freeze(["W", -1, 0, "E"]),
]);
const VECTOR = Object.freeze({
  N: Object.freeze([0, -1]),
  E: Object.freeze([1, 0]),
  S: Object.freeze([0, 1]),
  W: Object.freeze([-1, 0]),
});
const OPPOSITE = Object.freeze({ N: "S", E: "W", S: "N", W: "E" });
const CODE_DIRECTION = Object.freeze({
  ArrowUp: "N",
  ArrowRight: "E",
  ArrowDown: "S",
  ArrowLeft: "W",
  KeyW: "N",
  KeyD: "E",
  KeyS: "S",
  KeyA: "W",
});
const KEY_DATA = Object.freeze({
  ArrowUp: Object.freeze({
    key: "ArrowUp",
    code: "ArrowUp",
    windowsVirtualKeyCode: 38,
    nativeVirtualKeyCode: 38,
  }),
  ArrowRight: Object.freeze({
    key: "ArrowRight",
    code: "ArrowRight",
    windowsVirtualKeyCode: 39,
    nativeVirtualKeyCode: 39,
  }),
  ArrowDown: Object.freeze({
    key: "ArrowDown",
    code: "ArrowDown",
    windowsVirtualKeyCode: 40,
    nativeVirtualKeyCode: 40,
  }),
  ArrowLeft: Object.freeze({
    key: "ArrowLeft",
    code: "ArrowLeft",
    windowsVirtualKeyCode: 37,
    nativeVirtualKeyCode: 37,
  }),
  KeyW: Object.freeze({
    key: "w",
    code: "KeyW",
    windowsVirtualKeyCode: 87,
    nativeVirtualKeyCode: 87,
  }),
  KeyD: Object.freeze({
    key: "d",
    code: "KeyD",
    windowsVirtualKeyCode: 68,
    nativeVirtualKeyCode: 68,
  }),
  KeyS: Object.freeze({
    key: "s",
    code: "KeyS",
    windowsVirtualKeyCode: 83,
    nativeVirtualKeyCode: 83,
  }),
  KeyA: Object.freeze({
    key: "a",
    code: "KeyA",
    windowsVirtualKeyCode: 65,
    nativeVirtualKeyCode: 65,
  }),
});

function parseOptions(argv) {
  const options = { ...DEFAULTS, browser: null, findBrowser: false };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--find-browser") {
      options.findBrowser = true;
      continue;
    }
    const key = {
      "--browser": "browser",
      "--app": "app",
      "--continuity": "continuity",
      "--evidence": "evidence",
      "--manifest": "manifest",
      "--profile": "profile",
    }[argument];
    if (!key || index + 1 >= argv.length) {
      throw new Error(
        "usage: node verify_dom.mjs [--browser PATH] [--app PATH] " +
        "[--continuity PATH] [--evidence PATH] [--manifest PATH] " +
        "[--profile PATH] [--find-browser]"
      );
    }
    options[key] = argv[index + 1];
    index += 1;
  }
  return options;
}

async function isExecutable(path) {
  try {
    await access(
      path,
      process.platform === "win32" ? fsConstants.F_OK : fsConstants.X_OK
    );
    return true;
  } catch (error) {
    return false;
  }
}

async function findOnPath(command) {
  const directories = String(process.env.PATH || "")
    .split(delimiter)
    .filter(Boolean);
  const hasExtension = extname(command) !== "";
  const extensions =
    process.platform === "win32" && !hasExtension
      ? String(process.env.PATHEXT || ".EXE;.CMD;.BAT;.COM")
          .split(";")
          .filter(Boolean)
      : [""];
  for (const directory of directories) {
    for (const extension of extensions) {
      const candidate = join(directory, `${command}${extension}`);
      if (await isExecutable(candidate)) return resolve(candidate);
    }
  }
  return null;
}

function isChromiumFamily(path) {
  return /(chrome|chromium|edge|brave)/i.test(path);
}

async function resolveBrowserCandidate(value) {
  if (!value) return null;
  const candidate = String(value).trim().replace(/^"(.*)"$/, "$1");
  let found = null;
  if (isAbsolute(candidate) || /[\\/]/.test(candidate)) {
    found = (await isExecutable(candidate)) ? resolve(candidate) : null;
  } else {
    found = await findOnPath(candidate);
  }
  return found && isChromiumFamily(found) ? found : null;
}

function commonBrowserCandidates() {
  if (process.platform === "win32") {
    const roots = [
      process.env.ProgramFiles,
      process.env["ProgramFiles(x86)"],
      process.env.LOCALAPPDATA,
    ].filter(Boolean);
    const candidates = [];
    for (const root of roots) {
      candidates.push(
        join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
        join(root, "Google", "Chrome", "Application", "chrome.exe"),
        join(root, "Chromium", "Application", "chrome.exe"),
        join(root, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
      );
    }
    return candidates;
  }
  if (process.platform === "darwin") {
    return [
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
      "/Applications/Chromium.app/Contents/MacOS/Chromium",
      "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ];
  }
  return [
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
  ];
}

async function discoverBrowser(explicit) {
  if (explicit) {
    const found = await resolveBrowserCandidate(explicit);
    if (!found) {
      throw new Error(`Chromium-family browser does not exist: ${explicit}`);
    }
    return found;
  }
  for (const variable of [
    "RAPP_BROWSER",
    "RAPP_VISION_BROWSER",
    "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH",
    "EDGE_BIN",
    "CHROME_BIN",
    "CHROMIUM_BIN",
    "BROWSER",
  ]) {
    const found = await resolveBrowserCandidate(process.env[variable]);
    if (found) return found;
  }
  for (const command of [
    "msedge",
    "microsoft-edge",
    "microsoft-edge-stable",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "brave-browser",
  ]) {
    const found = await findOnPath(command);
    if (found && isChromiumFamily(found)) return found;
  }
  for (const candidate of commonBrowserCandidates()) {
    if (await isExecutable(candidate)) return resolve(candidate);
  }
  throw new Error(
    "Chromium-family browser not found via RAPP_BROWSER, environment, PATH, or common locations"
  );
}

function fnv1a32(value) {
  let result = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(value)) {
    result ^= byte;
    result = Math.imul(result, 0x01000193) >>> 0;
  }
  return result >>> 0;
}

function mulberry32(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1) >>> 0;
    const mixed = Math.imul(value ^ (value >>> 7), value | 61) >>> 0;
    value = (value ^ ((value + mixed) >>> 0)) >>> 0;
    return (value ^ (value >>> 14)) >>> 0;
  };
}

const keyOf = cell => `${cell[0]},${cell[1]}`;
const sameCell = (left, right) =>
  left[0] === right[0] && left[1] === right[1];

function nextCell(cell, direction) {
  const vector = VECTOR[direction];
  return [cell[0] + vector[0], cell[1] + vector[1]];
}

function independentMaze(seed, width = 6, height = 6) {
  const random = mulberry32(fnv1a32(seed));
  const maze = new Map();
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      maze.set(`${x},${y}`, new Set());
    }
  }
  const visited = new Set(["0,0"]);
  const stack = [[0, 0]];
  while (stack.length) {
    const [x, y] = stack[stack.length - 1];
    const candidates = [];
    for (const [direction, dx, dy, opposite] of DIRECTIONS) {
      const neighbor = [x + dx, y + dy];
      if (
        neighbor[0] >= 0 &&
        neighbor[0] < width &&
        neighbor[1] >= 0 &&
        neighbor[1] < height &&
        !visited.has(keyOf(neighbor))
      ) {
        candidates.push([direction, opposite, neighbor]);
      }
    }
    if (!candidates.length) {
      stack.pop();
      continue;
    }
    const [direction, opposite, neighbor] =
      candidates[random() % candidates.length];
    maze.get(`${x},${y}`).add(direction);
    maze.get(keyOf(neighbor)).add(opposite);
    visited.add(keyOf(neighbor));
    stack.push(neighbor);
  }
  return maze;
}

function independentSignature(maze, seed, width = 6, height = 6) {
  const cells = [];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const openings = maze.get(`${x},${y}`);
      cells.push(
        `${x},${y}:` +
          "NESW".split("").filter(direction => openings.has(direction)).join("")
      );
    }
  }
  return `${seed}|${width}x${height}|${cells.join(";")}`;
}

function independentRoute(maze, start = [0, 0], finish = [5, 3]) {
  const queue = [[...start]];
  const previous = new Map([[keyOf(start), null]]);
  const previousMove = new Map();
  while (queue.length) {
    const cell = queue.shift();
    if (sameCell(cell, finish)) break;
    for (const direction of "NESW") {
      if (!maze.get(keyOf(cell)).has(direction)) continue;
      const neighbor = nextCell(cell, direction);
      if (previous.has(keyOf(neighbor))) continue;
      previous.set(keyOf(neighbor), [...cell]);
      previousMove.set(keyOf(neighbor), direction);
      queue.push(neighbor);
    }
  }
  assert(previous.has(keyOf(finish)), "independent BFS could not reach exit");
  const route = [];
  let cursor = [...finish];
  while (!sameCell(cursor, start)) {
    route.push(previousMove.get(keyOf(cursor)));
    cursor = previous.get(keyOf(cursor));
  }
  return route.reverse();
}

function independentTrap(maze, route) {
  const positions = [[0, 0]];
  for (const direction of route) {
    positions.push(nextCell(positions[positions.length - 1], direction));
  }
  const routeCells = new Set(positions.map(keyOf));
  for (let index = positions.length - 2; index >= 0; index -= 1) {
    for (const direction of "NESW") {
      if (!maze.get(keyOf(positions[index])).has(direction)) continue;
      const neighbor = nextCell(positions[index], direction);
      if (!routeCells.has(keyOf(neighbor))) {
        return {
          approachIndex: index,
          approach: positions[index],
          turn: direction,
          cell: neighbor,
          returnDirection: OPPOSITE[direction],
          selection: "latest off-route branch before exit; NESW tie-break",
        };
      }
    }
  }
  const index = Math.max(1, Math.floor(route.length / 2));
  return {
    approachIndex: index,
    approach: positions[index],
    turn: OPPOSITE[route[index - 1]],
    cell: positions[index - 1],
    returnDirection: route[index - 1],
    selection: "deterministic backtrack fallback for a Hamiltonian route",
  };
}

function independentFixture(seed) {
  const maze = independentMaze(seed);
  const signature = independentSignature(maze, seed);
  const route = independentRoute(maze);
  const trap = independentTrap(maze, route);
  const detour = [
    ...route.slice(0, trap.approachIndex),
    trap.turn,
    trap.returnDirection,
    ...route.slice(trap.approachIndex),
  ];
  let edges = 0;
  for (const openings of maze.values()) edges += openings.size;
  return {
    seed,
    maze,
    signature,
    digest: createHash("sha256").update(signature, "utf8").digest("hex"),
    route,
    trap,
    detour,
    edges: edges / 2,
  };
}

function normalizeSeed(value) {
  assert.equal(typeof value, "string");
  const bytes = new TextEncoder().encode(value);
  if (
    bytes.length < 1 ||
    bytes.length > 64 ||
    /[\u0000-\u001f\u007f]/.test(value)
  ) {
    throw new Error(INVALID_SEED_MESSAGE);
  }
  return value;
}

function auditIndependentFixture(seed) {
  normalizeSeed(seed);
  const fixture = independentFixture(seed);
  assert.equal(fixture.maze.size, 36);
  assert.equal(fixture.edges, 35);
  const visited = new Set(["0,0"]);
  const queue = [[0, 0]];
  while (queue.length) {
    const cell = queue.shift();
    const openings = fixture.maze.get(keyOf(cell));
    assert(openings, `missing independent cell ${keyOf(cell)}`);
    for (const direction of openings) {
      const neighbor = nextCell(cell, direction);
      assert(
        neighbor[0] >= 0 &&
          neighbor[0] < 6 &&
          neighbor[1] >= 0 &&
          neighbor[1] < 6,
        `out-of-bounds opening ${keyOf(cell)} ${direction}`
      );
      assert(
        fixture.maze.get(keyOf(neighbor)).has(OPPOSITE[direction]),
        `nonreciprocal opening ${keyOf(cell)} ${direction}`
      );
      if (!visited.has(keyOf(neighbor))) {
        visited.add(keyOf(neighbor));
        queue.push(neighbor);
      }
    }
  }
  assert.equal(visited.size, 36);
  assert.deepEqual(independentRoute(fixture.maze), fixture.route);
  let cursor = [0, 0];
  for (const direction of fixture.detour) {
    assert(
      fixture.maze.get(keyOf(cursor)).has(direction),
      `detour leaves topology at ${keyOf(cursor)} ${direction}`
    );
    cursor = nextCell(cursor, direction);
  }
  assert.deepEqual(cursor, [5, 3]);
  assert.equal(fixture.detour.length, fixture.route.length + 2);
  return fixture;
}

function challengeContract(fixture) {
  return {
    seed: fixture.seed,
    topologyDigest: fixture.digest,
    referenceLength: fixture.route.length,
  };
}

function challengeFragment(fixture) {
  const payload = JSON.stringify(challengeContract(fixture));
  return `#challenge=${Buffer.from(payload, "utf8").toString("base64url")}`;
}

function decodeChallengeUrl(value) {
  assert.match(value, /^#challenge=[A-Za-z0-9_-]+$/);
  const encoded = value.slice("#challenge=".length);
  const contract = JSON.parse(Buffer.from(encoded, "base64url").toString("utf8"));
  assert.deepEqual(
    Object.keys(contract).sort(),
    ["referenceLength", "seed", "topologyDigest"]
  );
  assert.equal("route" in contract, false);
  assert.equal("trail" in contract, false);
  return { fragment: value, contract };
}

function revealedFrom(fixture, cell) {
  const revealed = new Set([keyOf(cell)]);
  for (const direction of fixture.maze.get(keyOf(cell))) {
    revealed.add(keyOf(nextCell(cell, direction)));
  }
  return revealed;
}

function initialState(fixture) {
  return {
    position: [0, 0],
    facing: "N",
    acceptedMoves: [],
    trail: [],
    revealed: revealedFrom(fixture, [0, 0]),
    status: "ready",
    message:
      `Seed ${fixture.seed} ready. Find the marked exit; ` +
      `reference length ${fixture.route.length}.`,
    lastAttempt: null,
    lastRejected: null,
    exitOpen: false,
    completed: false,
    matchedOptimal: null,
    projectedTotal: fixture.route.length,
    surveyEarned: false,
    hintAvailable: false,
    assistanceUsed: false,
    hintRequests: 0,
    hintDirection: null,
  };
}

function moveState(fixture, current, direction) {
  assert(VECTOR[direction], `unknown direction ${direction}`);
  if (current.completed) {
    return {
      ...current,
      facing: direction,
      status: "closed",
      message: "Exit already open. Restart or load another seed.",
      lastAttempt: direction,
      lastRejected: direction,
      hintAvailable: false,
      hintDirection: null,
    };
  }
  if (!fixture.maze.get(keyOf(current.position)).has(direction)) {
    const directionName = {
      N: "North",
      E: "East",
      S: "South",
      W: "West",
    }[direction];
    return {
      ...current,
      facing: direction,
      status: "wall",
      message:
        `${directionName} is fogbound by a wall; ` +
        "accepted steps, hint charge, and trail are preserved.",
      lastAttempt: direction,
      lastRejected: direction,
    };
  }
  const position = nextCell(current.position, direction);
  const acceptedMoves = [...current.acceptedMoves, direction];
  const trail = [...current.trail, position];
  const revealed = new Set(current.revealed);
  for (const cellKey of revealedFrom(fixture, position)) revealed.add(cellKey);
  const acceptedSteps = acceptedMoves.length;
  const projectedTotal =
    acceptedSteps + independentRoute(fixture.maze, position, [5, 3]).length;
  const completed = sameCell(position, [5, 3]);
  const surveyEarned = current.surveyEarned || acceptedSteps >= 4;
  const hintAvailable =
    !completed && surveyEarned && !current.assistanceUsed;
  let status;
  let message;
  let matchedOptimal = null;
  if (completed) {
    matchedOptimal = acceptedSteps === fixture.route.length;
    status = matchedOptimal ? "complete-optimal" : "complete-detour";
    message = matchedOptimal
      ? `Exit open in ${acceptedSteps}. Direct survey matched the reference ${
          current.assistanceUsed
            ? "with assistance"
            : "without assistance"
        }.`
      : `Exit open in ${acceptedSteps}: +${
          acceptedSteps - fixture.route.length
        } over reference ${fixture.route.length}.`;
  } else if (sameCell(position, fixture.trap.cell)) {
    status = "trap";
    message =
      `Marked trap entered. Best finish is now ${projectedTotal} ` +
      `(+${projectedTotal - fixture.route.length}); ` +
      "exit beacon remains marked.";
  } else if (projectedTotal > fixture.route.length) {
    status = "detour";
    message =
      `Valid detour recorded. Best finish ${projectedTotal} ` +
      `(+${projectedTotal - fixture.route.length}).`;
  } else {
    status = "moving";
    message =
      `${direction} accepted. ${acceptedSteps} steps; ` +
      `best finish ${projectedTotal}.`;
  }
  return {
    position,
    facing: direction,
    acceptedMoves,
    trail,
    revealed,
    status,
    message,
    lastAttempt: direction,
    lastRejected: null,
    exitOpen: completed,
    completed,
    matchedOptimal,
    projectedTotal,
    surveyEarned,
    hintAvailable,
    assistanceUsed: current.assistanceUsed,
    hintRequests: current.hintRequests,
    hintDirection: null,
  };
}

function requestHintState(fixture, current) {
  if (current.completed) {
    return {
      ...current,
      status: "hint-unavailable",
      message: "Survey hint unavailable after completion.",
      hintAvailable: false,
      hintDirection: null,
    };
  }
  if (!current.hintAvailable) {
    return {
      ...current,
      status: "hint-unavailable",
      message: current.surveyEarned
        ? "The one-step survey hint has already been spent."
        : "Survey charge unlocks after four accepted moves.",
    };
  }
  const direction = independentRoute(
    fixture.maze,
    current.position,
    [5, 3]
  )[0];
  return {
    ...current,
    status: "hint",
    message:
      `One-step survey: ${direction}. Assistance is recorded; ` +
      "no later moves are revealed.",
    hintAvailable: false,
    assistanceUsed: true,
    hintRequests: current.hintRequests + 1,
    hintDirection: direction,
  };
}

class CdpClient {
  constructor(url) {
    this.url = url;
    this.socket = null;
    this.nextId = 0;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async connect() {
    assert.equal(
      typeof WebSocket,
      "function",
      "Node WebSocket support is required"
    );
    this.socket = new WebSocket(this.url);
    await new Promise((resolveConnection, rejectConnection) => {
      this.socket.onopen = resolveConnection;
      this.socket.onerror = () =>
        rejectConnection(
          new Error(`cannot connect to DevTools target ${this.url}`)
        );
    });
    this.socket.onmessage = event => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) {
          pending.reject(
            new Error(
              `${pending.method}: ${message.error.message || "CDP error"}`
            )
          );
        } else {
          pending.resolve(message.result || {});
        }
        return;
      }
      const callbacks = this.listeners.get(message.method) || [];
      for (const callback of callbacks) callback(message.params || {});
    };
    this.socket.onclose = () => {
      for (const pending of this.pending.values()) {
        pending.reject(new Error(`DevTools socket closed during ${pending.method}`));
      }
      this.pending.clear();
    };
  }

  command(method, params = {}) {
    assert(this.socket && this.socket.readyState === WebSocket.OPEN);
    const id = (this.nextId += 1);
    const request = { id, method, params };
    return new Promise((resolveCommand, rejectCommand) => {
      this.pending.set(id, {
        method,
        resolve: resolveCommand,
        reject: rejectCommand,
      });
      this.socket.send(JSON.stringify(request));
    });
  }

  on(method, callback) {
    const callbacks = this.listeners.get(method) || [];
    callbacks.push(callback);
    this.listeners.set(method, callbacks);
  }

  close() {
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) {
      this.socket.close();
    }
  }
}

const delay = milliseconds =>
  new Promise(resolveDelay => setTimeout(resolveDelay, milliseconds));

async function reservePort() {
  return await new Promise((resolvePort, rejectPort) => {
    const reservation = createServer();
    reservation.once("error", rejectPort);
    reservation.listen(0, "127.0.0.1", () => {
      const address = reservation.address();
      reservation.close(error => {
        if (error) rejectPort(error);
        else resolvePort(address.port);
      });
    });
  });
}

async function waitForDevTools(child, port, launchLog, timeout = 45000) {
  const deadline = Date.now() + timeout;
  let lastError = null;
  while (Date.now() < deadline) {
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error(
        `browser exited before DevTools was ready: ` +
        `${child.exitCode ?? child.signalCode}\n${launchLog.value}`
      );
    }
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) return await response.json();
    } catch (error) {
      lastError = error;
    }
    await delay(75);
  }
  throw new Error(
    `browser did not publish reserved DevTools port ${port}: ` +
    `${lastError ? lastError.message : "timeout"}\n${launchLog.value}`
  );
}

function processIsRunning(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error && error.code === "EPERM") return true;
    if (error && error.code === "ESRCH") return false;
    throw error;
  }
}

async function waitForExit(child, timeout = 15000) {
  if (child.exitCode !== null || child.signalCode !== null) return true;
  const exited = new Promise(resolveExit => {
    child.once("exit", resolveExit);
    child.once("close", resolveExit);
  });
  const timedOut = await Promise.race([
    exited.then(() => false),
    delay(timeout).then(() => true),
  ]);
  if (!timedOut) return true;
  child.kill("SIGTERM");
  await Promise.race([exited, delay(5000)]);
  if (
    child.exitCode === null &&
    child.signalCode === null &&
    processIsRunning(child.pid)
  ) {
    child.kill("SIGKILL");
    await Promise.race([exited, delay(10000)]);
  }
  return (
    child.exitCode !== null ||
    child.signalCode !== null ||
    !processIsRunning(child.pid)
  );
}

async function removeProfile(path, timeout = 30000) {
  const deadline = Date.now() + timeout;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      await rm(path, {
        recursive: true,
        force: true,
        maxRetries: 4,
        retryDelay: 125,
      });
      return true;
    } catch (error) {
      lastError = error;
      await delay(250);
    }
  }
  throw new Error(
    `could not remove browser profile ${path}: ${
      lastError ? lastError.message : "timeout"
    }`
  );
}

async function evaluate(cdp, expression) {
  const response = await cdp.command("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
    userGesture: true,
  });
  if (response.exceptionDetails) {
    throw new Error(
      `page evaluation failed: ${
        response.exceptionDetails.text || "unknown exception"
      }`
    );
  }
  return response.result ? response.result.value : undefined;
}

async function waitForReady(cdp, timeout = 10000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const ready = await evaluate(
      cdp,
      `document.documentElement.dataset.ready === "true" &&
       document.querySelectorAll("#maze-board > .cell").length === 36`
    );
    if (ready) return;
    await delay(50);
  }
  throw new Error("Fogline Survey did not reach its ready contract");
}

async function settle(cdp) {
  await evaluate(
    cdp,
    `new Promise(resolve => requestAnimationFrame(resolve))`
  );
}

async function geometry(cdp, selector) {
  return await evaluate(
    cdp,
    `(() => {
      const selector = ${JSON.stringify(selector)};
      const element = document.querySelector(selector);
      if (!element) return { exists: false, selector };
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        exists: true,
        selector,
        rect: {
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height
        },
        viewport: { width: innerWidth, height: innerHeight },
        display: style.display,
        visibility: style.visibility,
        opacity: Number(style.opacity),
        fontSize: Number.parseFloat(style.fontSize),
        hidden: element.hidden,
        disabled: !!element.disabled ||
          element.getAttribute("aria-disabled") === "true",
        activeId: document.activeElement ? document.activeElement.id : "",
        scrollWidth: document.scrollingElement.scrollWidth,
        clientWidth: document.scrollingElement.clientWidth
      };
    })()`
  );
}

async function criticalPlayGeometry(cdp) {
  return await evaluate(
    cdp,
    `(() => {
      const selectors = [
        "#maze-board",
        ".controls",
        "#hint-btn",
        "#restart-btn",
        "#step-value",
        "#projection-value",
        "#exit-value"
      ];
      const records = selectors.map(selector => {
        const element = document.querySelector(selector);
        const rect = element.getBoundingClientRect();
        return {
          selector,
          top: rect.top + scrollY,
          bottom: rect.bottom + scrollY,
          left: rect.left,
          right: rect.right,
          width: rect.width,
          height: rect.height
        };
      });
      return {
        records,
        span:
          Math.max(...records.map(record => record.bottom)) -
          Math.min(...records.map(record => record.top)),
        documentHeight: document.scrollingElement.scrollHeight,
        viewport: { width: innerWidth, height: innerHeight }
      };
    })()`
  );
}

async function liveContinuityStyle(cdp) {
  return await evaluate(
    cdp,
    `(() => {
      const describe = selector => {
        const element = document.querySelector(selector);
        const style = getComputedStyle(element);
        return {
          selector,
          tag: element.tagName.toLowerCase(),
          classes: [...element.classList],
          fontFamily: style.fontFamily,
          color: style.color,
          backgroundColor: style.backgroundColor
        };
      };
      return {
        fontsReady: document.fonts.status,
        bodyFontFamily: getComputedStyle(document.body).fontFamily,
        headingFontFamily: getComputedStyle(document.querySelector("h1")).fontFamily,
        buttonFontFamily:
          getComputedStyle(document.querySelector("#restart-btn")).fontFamily,
        outputFontFamily:
          getComputedStyle(document.querySelector("#digest-value")).fontFamily,
        components: [
          describe(".proof-strip"),
          describe(".map-card"),
          describe("#maze-board"),
          describe(".panel"),
          describe(".challenge-card")
        ]
      };
    })()`
  );
}

function assertFilmLiveStructure(live, continuity) {
  const film = continuity.sharedStyle;
  assert.equal(live.fontsReady, "loaded");
  for (const field of [
    "bodyFontFamily",
    "headingFontFamily",
    "buttonFontFamily",
    "outputFontFamily",
  ]) {
    assert.equal(live[field], film[field], `film/live ${field}`);
  }
  for (const liveComponent of live.components) {
    const filmComponent = film.components.find(
      component => component.selector === liveComponent.selector
    );
    assert(filmComponent, `film component missing ${liveComponent.selector}`);
    for (const field of [
      "tag",
      "classes",
      "fontFamily",
      "color",
      "backgroundColor",
    ]) {
      assert.deepEqual(
        liveComponent[field],
        filmComponent[field],
        `film/live ${liveComponent.selector} ${field}`
      );
    }
  }
}

function isVisibleGeometry(record) {
  return (
    record.exists &&
    !record.hidden &&
    record.display !== "none" &&
    record.visibility !== "hidden" &&
    record.opacity > 0 &&
    record.rect.width > 0 &&
    record.rect.height > 0 &&
    record.rect.left >= -1 &&
    record.rect.right <= record.viewport.width + 1 &&
    record.rect.top >= -1 &&
    record.rect.bottom <= record.viewport.height + 1 &&
    record.scrollWidth <= record.clientWidth + 1
  );
}

function assertVisibleGeometry(record, label) {
  assert(record.exists, `${label}: missing ${record.selector}`);
  assert.equal(record.hidden, false, `${label}: hidden ${record.selector}`);
  assert.notEqual(record.display, "none", `${label}: display none`);
  assert.notEqual(record.visibility, "hidden", `${label}: visibility hidden`);
  assert(record.opacity > 0, `${label}: transparent`);
  assert(record.rect.width > 0 && record.rect.height > 0, `${label}: empty rect`);
  assert(
    isVisibleGeometry(record),
    `${label}: ${record.selector} outside viewport ${JSON.stringify(record.rect)}`
  );
}

async function assertVisible(cdp, selector, label) {
  const record = await geometry(cdp, selector);
  assertVisibleGeometry(record, label);
  return record;
}

async function dispatchKey(cdp, code) {
  const data = KEY_DATA[code];
  assert(data, `unsupported semantic key code ${code}`);
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyDown",
    autoRepeat: false,
    isKeypad: false,
    ...data,
  });
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyUp",
    ...data,
  });
}

async function dispatchMouseClick(cdp, selector, label, allowDisabled = false) {
  const record = await assertVisible(cdp, selector, label);
  if (!allowDisabled) {
    assert.equal(record.disabled, false, `${label}: disabled target`);
  }
  const x = record.rect.left + record.rect.width / 2;
  const y = record.rect.top + record.rect.height / 2;
  await cdp.command("Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x,
    y,
  });
  await cdp.command("Input.dispatchMouseEvent", {
    type: "mousePressed",
    x,
    y,
    button: "left",
    buttons: 1,
    clickCount: 1,
  });
  await cdp.command("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x,
    y,
    button: "left",
    buttons: 0,
    clickCount: 1,
  });
  await settle(cdp);
  return record;
}

async function scrollTo(cdp, selector, block = "center") {
  await evaluate(
    cdp,
    `(() => {
      const target = document.querySelector(${JSON.stringify(selector)});
      if (!target) throw new Error("missing scroll target");
      target.scrollIntoView({
        block: ${JSON.stringify(block)},
        inline: "nearest",
        behavior: "auto"
      });
      const rect = target.getBoundingClientRect();
      const safeBottom = innerHeight - 112;
      if (rect.top < 8) {
        scrollBy(0, rect.top - 8);
      } else if (rect.bottom > safeBottom && rect.height <= safeBottom - 8) {
        scrollBy(0, rect.bottom - safeBottom);
      }
    })()`
  );
  await settle(cdp);
}

async function executeAction(cdp, action, index, viewportName) {
  let selector = action.selector || null;
  let before = null;
  if (action.do === "scroll") {
    before = await geometry(cdp, selector);
    assert(before.exists, `action ${index}: missing scroll target ${selector}`);
    await scrollTo(cdp, selector, action.block || "center");
  } else if (action.do === "click") {
    before = await dispatchMouseClick(
      cdp,
      selector,
      `${viewportName} action ${index} click before`
    );
  } else if (action.do === "key") {
    const activeId = await evaluate(
      cdp,
      `document.activeElement ? document.activeElement.id : ""`
    );
    assert.equal(
      activeId,
      "maze-board",
      `action ${index}: key target must be focused maze board`
    );
    selector = "#maze-board";
    before = await assertVisible(
      cdp,
      selector,
      `${viewportName} action ${index} key before`
    );
    await dispatchKey(cdp, action.code);
    await settle(cdp);
  } else if (action.do === "type") {
    const active = await evaluate(
      cdp,
      `(() => {
        const element = document.activeElement;
        return {
          id: element ? element.id : "",
          tag: element ? element.tagName : "",
          disabled: element ? !!element.disabled : true
        };
      })()`
    );
    assert.equal(active.id, "seed-input", `action ${index}: type target`);
    assert.equal(active.disabled, false);
    selector = "#seed-input";
    before = await assertVisible(
      cdp,
      selector,
      `${viewportName} action ${index} type before`
    );
    const selection = await evaluate(
      cdp,
      `(() => {
        const input = document.querySelector("#seed-input");
        return {
          value: input.value,
          start: input.selectionStart,
          end: input.selectionEnd
        };
      })()`
    );
    assert.equal(selection.start, 0, `action ${index}: input selection start`);
    assert.equal(
      selection.end,
      selection.value.length,
      `action ${index}: input must be selected before replacement`
    );
    await cdp.command("Input.insertText", { text: String(action.text || "") });
    await settle(cdp);
  } else {
    throw new Error(`unsupported manifest action ${action.do}`);
  }
  const after = await assertVisible(
    cdp,
    selector,
    `${viewportName} action ${index} after`
  );
  return {
    index,
    action,
    inputMethod:
      action.do === "click"
        ? "cdp-mouse"
        : action.do === "key" || action.do === "type"
          ? "cdp-keyboard"
          : "cdp-scroll",
    before,
    after,
  };
}

function keyDirections(actions, segment) {
  return actions
    .slice(segment.firstAction - 1, segment.lastAction)
    .filter(action => action.do === "key")
    .map(action => {
      assert(CODE_DIRECTION[action.code], `unknown route code ${action.code}`);
      return CODE_DIRECTION[action.code];
    });
}

async function observeDom(cdp) {
  return await evaluate(
    cdp,
    `(() => {
      const clone = document.documentElement.cloneNode(true);
      clone.querySelectorAll("script, style, template").forEach(node => node.remove());
      return {
      dom: {
        seed: document.querySelector("#seed-value").textContent.trim(),
        reference: document.querySelector("#reference-value").textContent.trim(),
        digest: document.querySelector("#digest-value").textContent.trim(),
        steps: document.querySelector("#step-value").textContent.trim(),
        projection: document.querySelector("#projection-value").textContent.trim(),
        position: document.querySelector("#position-value").textContent.trim(),
        exit: document.querySelector("#exit-value").textContent.trim(),
        compass: document.querySelector("#compass-value").textContent.trim(),
        assist: document.querySelector("#assist-value").textContent.trim(),
        status: document.querySelector("#status-message").textContent.trim(),
        hint: {
          hidden: document.querySelector("#hint-panel").hidden,
          text: document.querySelector("#hint-panel").textContent.trim()
        },
        trap: {
          hidden: document.querySelector("#trap-panel").hidden,
          text: document.querySelector("#trap-panel").textContent.trim()
        },
        success: {
          hidden: document.querySelector("#success-panel").hidden,
          text: document.querySelector("#success-panel").textContent.trim()
        },
        hintButton: {
          disabled: document.querySelector("#hint-btn").disabled,
          text: document.querySelector("#hint-btn").textContent.trim()
        },
        seedInput: {
          type: document.querySelector("#seed-input").type,
          value: document.querySelector("#seed-input").value,
          selectionStart: document.querySelector("#seed-input").selectionStart,
          selectionEnd: document.querySelector("#seed-input").selectionEnd,
          ariaInvalid:
            document.querySelector("#seed-input").getAttribute("aria-invalid"),
          textSecurity:
            getComputedStyle(document.querySelector("#seed-input"))
              .webkitTextSecurity || "none"
        },
        seedError: {
          hidden: document.querySelector("#seed-error").hidden,
          text: document.querySelector("#seed-error").textContent.trim()
        },
        seedProof:
          document.querySelector("#seed-change-proof").textContent.trim(),
        challenge: {
          link: document.querySelector("#challenge-link").value,
          selectionStart:
            document.querySelector("#challenge-link").selectionStart,
          selectionEnd:
            document.querySelector("#challenge-link").selectionEnd,
          ariaInvalid:
            document.querySelector("#challenge-link")
              .getAttribute("aria-invalid"),
          status: document.querySelector("#challenge-status").textContent.trim(),
          errorHidden: document.querySelector("#challenge-error").hidden,
          error: document.querySelector("#challenge-error").textContent.trim()
        },
        takeover: {
          hidden: document.querySelector("#takeover-prompt").hidden,
          text: document.querySelector("#takeover-prompt").textContent.trim(),
          tabIndex: document.querySelector("#takeover-prompt").tabIndex,
          pointerEvents:
            getComputedStyle(document.querySelector("#takeover-prompt"))
              .pointerEvents
        },
        boardLabel: document.querySelector("#maze-board").getAttribute("aria-label"),
        exitBeaconPresent: !!document.querySelector("#exit-beacon"),
        cells: [...document.querySelectorAll("#maze-board > .cell")].map(cell => ({
          id: cell.id,
          classes: [...cell.classList],
          ariaHidden: cell.getAttribute("aria-hidden"),
          borders: {
            N: cell.style.borderTopWidth,
            E: cell.style.borderRightWidth,
            S: cell.style.borderBottomWidth,
            W: cell.style.borderLeftWidth
          },
          exitMarker: cell.querySelector(".exit-marker")
            ? {
                text: cell.querySelector(".exit-marker").textContent,
                title: cell.querySelector(".exit-marker").title
              }
            : null,
          trapMarker: cell.querySelector(".trap-marker")
            ? {
                text: cell.querySelector(".trap-marker").textContent,
                title: cell.querySelector(".trap-marker").title
              }
            : null,
          player: cell.querySelector(".player")
            ? {
                text: cell.querySelector(".player").textContent,
                title: cell.querySelector(".player").title
              }
            : null
        })),
        renderedText: clone.textContent,
        visibleText: document.body.innerText,
        renderedMarkup: clone.innerHTML,
        publicFixtureApi:
          Object.prototype.hasOwnProperty.call(window, "foglineSurvey")
      },
      activeId: document.activeElement ? document.activeElement.id : "",
      width: {
        scroll: document.scrollingElement.scrollWidth,
        client: document.scrollingElement.clientWidth,
        height: document.scrollingElement.scrollHeight
      }
    };
    })()`
  );
}

function assertDomMatchesExpected(
  record,
  fixture,
  state,
  {
    seedInput = fixture.seed,
    seedError = null,
    challengeError = null,
    challengeStatus = null,
    label = fixture.seed,
  } = {}
) {
  const { dom } = record;
  assert.equal(dom.publicFixtureApi, false, `${label}: public fixture API`);
  assert.equal(dom.seed, fixture.seed, `${label}: accepted seed`);
  assert.equal(
    dom.reference,
    `${fixture.route.length} moves`,
    `${label}: reference`
  );
  assert.equal(dom.digest, fixture.digest, `${label}: digest`);
  assert.equal(
    dom.steps,
    `${state.acceptedMoves.length} / ${fixture.route.length}`,
    `${label}: steps`
  );
  assert.equal(
    dom.projection,
    String(state.projectedTotal),
    `${label}: projection`
  );
  assert.equal(
    dom.position,
    `(${state.position[0]},${state.position[1]})`,
    `${label}: position`
  );
  assert.equal(
    dom.exit,
    `${state.exitOpen ? "open" : "closed"} · marked`,
    `${label}: exit`
  );
  assert.equal(dom.compass, {
    N: "NORTH",
    E: "EAST",
    S: "SOUTH",
    W: "WEST",
  }[state.facing], `${label}: compass`);
  assert.equal(
    dom.assist,
    state.completed
      ? state.assistanceUsed
        ? "ASSISTED · completion locked"
        : "UNASSISTED · completion locked"
      : state.assistanceUsed
        ? "ASSISTED · one bearing spent"
        : state.hintAvailable
          ? "Earned · one bearing ready"
          : "Survey charge locked · earn at 4",
    `${label}: assistance`
  );
  assert.equal(dom.status, state.message, `${label}: status`);
  assert.equal(
    dom.hint.hidden,
    state.hintDirection === null,
    `${label}: hint visibility`
  );
  assert.equal(
    dom.hint.text,
    state.hintDirection === null
      ? ""
      : `ONE STEP ONLY: ${state.hintDirection} · assistance recorded`,
    `${label}: hint text`
  );
  assert.equal(
    dom.trap.hidden,
    state.status !== "trap",
    `${label}: trap visibility`
  );
  assert.equal(
    dom.trap.text,
    state.status === "trap"
      ? `MARKED TRAP · projected ${state.projectedTotal} · exit still marked`
      : "",
    `${label}: trap text`
  );
  assert.equal(
    dom.success.hidden,
    !state.completed,
    `${label}: success visibility`
  );
  assert.equal(
    dom.success.text,
    state.completed
      ? state.matchedOptimal
        ? `EXIT OPEN · ${state.acceptedMoves.length} = reference · ${
            state.assistanceUsed ? "assisted" : "unassisted"
          }`
        : `EXIT OPEN · final ${state.acceptedMoves.length} · reference ${
            fixture.route.length
          } · ${state.assistanceUsed ? "assisted" : "unassisted"}`
      : "",
    `${label}: success text`
  );
  assert.equal(
    dom.hintButton.disabled,
    state.completed || !state.hintAvailable,
    `${label}: hint disabled`
  );
  assert.equal(
    dom.hintButton.text,
    state.completed
      ? "Run complete · hint unavailable"
      : state.hintAvailable
        ? "Request earned one-step hint"
        : state.assistanceUsed
          ? "One-step hint spent"
          : "Earn hint after 4 moves",
    `${label}: hint button`
  );
  assert.equal(dom.seedInput.type, "text", `${label}: input type`);
  assert.equal(dom.seedInput.textSecurity, "none", `${label}: masked input`);
  assert.equal(dom.seedInput.value, seedInput, `${label}: seed draft`);
  assert.equal(
    dom.seedInput.ariaInvalid,
    seedError === null ? "false" : "true",
    `${label}: seed aria-invalid`
  );
  assert.equal(
    dom.seedError.hidden,
    seedError === null,
    `${label}: seed error visibility`
  );
  assert.equal(dom.seedError.text, seedError || "", `${label}: seed error`);
  assert.equal(
    dom.seedProof,
    `Active topology: ${fixture.seed} · reference ${fixture.route.length} · ` +
      `digest ${fixture.digest.slice(0, 12)}…`,
    `${label}: seed proof`
  );
  const exported = decodeChallengeUrl(dom.challenge.link);
  assert.deepEqual(
    exported.contract,
    challengeContract(fixture),
    `${label}: challenge contract`
  );
  assert.equal(
    dom.challenge.errorHidden,
    challengeError === null,
    `${label}: challenge error visibility`
  );
  assert.equal(
    dom.challenge.error,
    challengeError || "",
    `${label}: challenge error`
  );
  assert.equal(
    dom.challenge.ariaInvalid,
    challengeError === null ? "false" : "true",
    `${label}: challenge aria-invalid`
  );
  if (challengeStatus !== null) {
    assert.equal(
      dom.challenge.status,
      challengeStatus,
      `${label}: challenge status`
    );
  } else {
    assert(dom.challenge.status.length > 0, `${label}: challenge status empty`);
  }
  const handoffReady =
    fixture.seed === "FOG-7" &&
    state.acceptedMoves.length === 0 &&
    state.trail.length === 0 &&
    !state.assistanceUsed;
  assert.equal(
    dom.takeover.hidden,
    !handoffReady,
    `${label}: takeover visibility`
  );
  assert.equal(dom.takeover.tabIndex, -1, `${label}: takeover tab stop`);
  assert.equal(
    dom.takeover.pointerEvents,
    "none",
    `${label}: takeover pointer capture`
  );
  if (handoffReady) {
    assert.match(dom.takeover.text, /YOUR TURN · FOG-7 READY/);
    assert.match(dom.takeover.text, /zero steps/i);
    assert.match(dom.takeover.text, /Movement\s+is focused/i);
  }
  assert.equal(
    dom.boardLabel,
    `Fogline maze, seed ${fixture.seed}. Position ` +
      `${state.position[0]},${state.position[1]}, facing ${
        { N: "north", E: "east", S: "south", W: "west" }[state.facing]
      }. ${state.acceptedMoves.length} accepted steps.`,
    `${label}: board label`
  );
  assert(dom.exitBeaconPresent, `${label}: exit beacon disappeared`);
  assert.equal(dom.cells.length, 36, `${label}: board cell count`);
  const trail = new Set(state.trail.map(keyOf));
  let players = 0;
  for (const cell of dom.cells) {
    const match = /^cell-(\d)-(\d)$/.exec(cell.id);
    assert(match, `${label}: invalid cell id ${cell.id}`);
    const position = [Number(match[1]), Number(match[2])];
    const cellKey = keyOf(position);
    const revealed = state.revealed.has(cellKey);
    assert(cell.classes.includes("cell"), `${label}: cell class ${cellKey}`);
    assert.equal(
      cell.classes.includes("revealed"),
      revealed,
      `${label}: revealed ${cellKey}`
    );
    assert.equal(
      cell.classes.includes("trail"),
      trail.has(cellKey),
      `${label}: trail ${cellKey}`
    );
    assert.equal(
      cell.classes.includes("entrance"),
      sameCell(position, [0, 0]),
      `${label}: entrance ${cellKey}`
    );
    assert.equal(cell.ariaHidden, "true", `${label}: cell aria ${cellKey}`);
    const openings = fixture.maze.get(cellKey);
    for (const direction of "NESW") {
      assert.equal(
        cell.borders[direction],
        revealed ? (openings.has(direction) ? "1px" : "3px") : "",
        `${label}: ${cellKey} ${direction} wall`
      );
    }
    const isExit = sameCell(position, [5, 3]);
    assert.equal(!!cell.exitMarker, isExit, `${label}: exit marker ${cellKey}`);
    if (cell.exitMarker) {
      assert.deepEqual(
        cell.exitMarker,
        { text: "X", title: "Marked exit beacon" },
        `${label}: exit marker content`
      );
    }
    const isTrap =
      sameCell(position, fixture.trap.cell) && state.revealed.has(cellKey);
    assert.equal(!!cell.trapMarker, isTrap, `${label}: trap marker ${cellKey}`);
    if (cell.trapMarker) {
      assert.deepEqual(
        cell.trapMarker,
        { text: "!", title: "Marked trap" },
        `${label}: trap marker content`
      );
    }
    const isPlayer = sameCell(position, state.position);
    assert.equal(!!cell.player, isPlayer, `${label}: player ${cellKey}`);
    if (cell.player) {
      players += 1;
      assert.equal(cell.player.text, "▲", `${label}: player glyph`);
      assert.equal(
        cell.player.title,
        `Surveyor facing ${
          { N: "north", E: "east", S: "south", W: "west" }[state.facing]
        }`,
        `${label}: player title`
      );
    }
  }
  assert.equal(players, 1, `${label}: player count`);
  assert(
    record.width.scroll <= record.width.client + 1,
    `${label}: page overflowed`
  );
}

function routeLeakPatterns(route) {
  const separator = String.raw`[\s,;|:/·→>\-"'[\]]*`;
  const letterPattern = route.join(separator);
  const words = {
    N: "north",
    E: "east",
    S: "south",
    W: "west",
  };
  const arrows = { N: "↑", E: "→", S: "↓", W: "←" };
  return [
    new RegExp(`(^|[^A-Z])${letterPattern}([^A-Z]|$)`, "i"),
    new RegExp(
      `(^|[^a-z])${route.map(direction => words[direction]).join(String.raw`[\s,;|:/·→>\-]+`)}([^a-z]|$)`,
      "i"
    ),
    new RegExp(
      route
        .map(direction => arrows[direction])
        .join(String.raw`[\s,;|:/·→>\-]*`)
    ),
  ];
}

function assertNoRouteLeak(value, fixture, label) {
  const text = String(value || "");
  for (const pattern of routeLeakPatterns(fixture.route)) {
    assert.equal(
      pattern.test(text),
      false,
      `${label}: full route leaked via ${pattern}`
    );
  }
}

async function auditOpeningPrivacy(cdp, fixture, label) {
  const observation = await observeDom(cdp);
  assertNoRouteLeak(observation.dom.visibleText, fixture, `${label} visible text`);
  assertNoRouteLeak(
    observation.dom.renderedText,
    fixture,
    `${label} rendered text`
  );
  assertNoRouteLeak(
    observation.dom.renderedMarkup,
    fixture,
    `${label} rendered markup`
  );
  for (const forbidden of [
    "topologySignature",
    "shortestRoute",
    "detourRoute",
    "routePositions",
    "acceptedMoves",
    "data-route",
    "data-solution",
    "data-topology",
  ]) {
    assert.equal(
      observation.dom.renderedMarkup.includes(forbidden),
      false,
      `${label}: hidden route-bearing DOM field ${forbidden}`
    );
  }
  assert.equal(
    observation.dom.publicFixtureApi,
    false,
    `${label}: route-bearing window API`
  );
  const tree = await cdp.command("Accessibility.getFullAXTree");
  const accessibleText = (tree.nodes || [])
    .flatMap(node => [
      node.name && node.name.value,
      node.description && node.description.value,
      node.value && node.value.value,
    ])
    .filter(value => typeof value === "string")
    .join("\n");
  assertNoRouteLeak(accessibleText, fixture, `${label} accessibility tree`);
  return {
    visibleCharacters: observation.dom.visibleText.length,
    renderedCharacters: observation.dom.renderedText.length,
    accessibilityCharacters: accessibleText.length,
    publicFixtureApi: false,
  };
}

function expectedSummary(fixture, state) {
  return {
    seed: fixture.seed,
    digest: fixture.digest,
    topologyDigest: fixture.digest,
    referenceLength: fixture.route.length,
    position: [...state.position],
    facing: state.facing,
    steps: state.acceptedMoves.length,
    projectedTotal: state.projectedTotal,
    status: state.status,
    completed: state.completed,
    matchedOptimal: state.matchedOptimal,
    exitState: state.exitOpen ? "open" : "closed",
    trailLength: state.trail.length,
    assistanceUsed: state.assistanceUsed,
    hintAvailable: state.hintAvailable,
    hintRequests: state.hintRequests,
    hintDirection: state.hintDirection,
    trapMarked: state.revealed.has(keyOf(fixture.trap.cell)),
  };
}

function stateGateMatches(summary, gate) {
  return Object.entries(gate).every(
    ([key, expected]) =>
      JSON.stringify(summary[key]) === JSON.stringify(expected)
  );
}

function applyExpectedAction(context, action) {
  if (action.do === "key") {
    context.state = moveState(
      context.fixture,
      context.state,
      CODE_DIRECTION[action.code]
    );
    return;
  }
  if (action.do === "type") {
    context.seedInput = String(action.text || "");
    return;
  }
  if (action.do !== "click") return;
  if (action.selector === "#restart-btn") {
    context.state = initialState(context.fixture);
    context.seedInput = context.fixture.seed;
    context.seedError = null;
  } else if (action.selector === "#hint-btn") {
    context.state = requestHintState(context.fixture, context.state);
  } else if (action.selector === "#load-seed-btn") {
    try {
      normalizeSeed(context.seedInput);
      context.fixture = auditIndependentFixture(context.seedInput);
      context.state = initialState(context.fixture);
      context.seedError = null;
    } catch (error) {
      assert.equal(error.message, INVALID_SEED_MESSAGE);
      context.seedError = INVALID_SEED_MESSAGE;
    }
  }
}

function codeForDirection(direction, family = "arrow") {
  const codes =
    family === "wasd"
      ? { N: "KeyW", E: "KeyD", S: "KeyS", W: "KeyA" }
      : {
          N: "ArrowUp",
          E: "ArrowRight",
          S: "ArrowDown",
          W: "ArrowLeft",
        };
  return codes[direction];
}

async function focusBoard(cdp, label) {
  await scrollTo(cdp, "#maze-board");
  await dispatchMouseClick(cdp, "#maze-board", `${label} focus board`);
  assert.equal(
    await evaluate(
      cdp,
      `document.activeElement ? document.activeElement.id : ""`
    ),
    "maze-board",
    `${label}: board did not receive focus`
  );
}

async function driveDirections(cdp, context, directions, label, family = "arrow") {
  await focusBoard(cdp, label);
  for (let index = 0; index < directions.length; index += 1) {
    await assertVisible(
      cdp,
      "#maze-board",
      `${label} key ${index + 1} before`
    );
    const direction = directions[index];
    await dispatchKey(cdp, codeForDirection(direction, family));
    await settle(cdp);
    context.state = moveState(context.fixture, context.state, direction);
    const observation = await observeDom(cdp);
    assertDomMatchesExpected(observation, context.fixture, context.state, {
      seedInput: context.seedInput,
      seedError: context.seedError,
      label: `${label} key ${index + 1}`,
    });
    if (context.state.status === "trap") {
      await assertVisible(
        cdp,
        "#exit-beacon",
        `${label} key ${index + 1} visible exit`
      );
      await assertVisible(
        cdp,
        ".trap-marker",
        `${label} key ${index + 1} visible trap`
      );
    }
  }
}

async function clickControl(cdp, selector, label) {
  await scrollTo(cdp, selector);
  await dispatchMouseClick(cdp, selector, label);
}

async function restartThroughUi(cdp, context, label) {
  await clickControl(cdp, "#restart-btn", `${label} restart`);
  context.state = initialState(context.fixture);
  context.seedInput = context.fixture.seed;
  context.seedError = null;
  const observation = await observeDom(cdp);
  assertDomMatchesExpected(observation, context.fixture, context.state, {
    seedInput: context.seedInput,
    seedError: context.seedError,
    label: `${label} reset`,
  });
}

async function loadSeedThroughUi(cdp, context, seed, label) {
  await scrollTo(cdp, "#seed-input");
  await dispatchMouseClick(cdp, "#seed-input", `${label} seed input`);
  const selection = await evaluate(
    cdp,
    `(() => {
      const input = document.querySelector("#seed-input");
      return {
        value: input.value,
        start: input.selectionStart,
        end: input.selectionEnd
      };
    })()`
  );
  assert.equal(selection.start, 0, `${label}: seed selection start`);
  assert.equal(
    selection.end,
    selection.value.length,
    `${label}: seed selection end`
  );
  await cdp.command("Input.insertText", { text: seed });
  await settle(cdp);
  assert.equal(
    await evaluate(cdp, `document.querySelector("#seed-input").value`),
    seed,
    `${label}: actual seed typing`
  );
  context.seedInput = seed;
  await clickControl(cdp, "#load-seed-btn", `${label} generate`);
  context.fixture = auditIndependentFixture(seed);
  context.state = initialState(context.fixture);
  context.seedError = null;
  const observation = await observeDom(cdp);
  assertDomMatchesExpected(observation, context.fixture, context.state, {
    seedInput: seed,
    seedError: null,
    label: `${label} opening`,
  });
}

async function rejectSeedThroughUi(cdp, context, seed, label) {
  const before = expectedSummary(context.fixture, context.state);
  await scrollTo(cdp, "#seed-input");
  await dispatchMouseClick(cdp, "#seed-input", `${label} seed input`);
  const selection = await evaluate(
    cdp,
    `(() => {
      const input = document.querySelector("#seed-input");
      return [input.selectionStart, input.selectionEnd, input.value.length];
    })()`
  );
  assert.deepEqual(selection, [0, selection[2], selection[2]]);
  await cdp.command("Input.insertText", { text: seed });
  await settle(cdp);
  context.seedInput = seed;
  await clickControl(cdp, "#load-seed-btn", `${label} reject`);
  context.seedError = INVALID_SEED_MESSAGE;
  const observation = await observeDom(cdp);
  assertDomMatchesExpected(observation, context.fixture, context.state, {
    seedInput: seed,
    seedError: INVALID_SEED_MESSAGE,
    label,
  });
  assert.deepEqual(expectedSummary(context.fixture, context.state), before);
}

async function clearSeedErrorThroughValidEdit(cdp, context, label) {
  const before = expectedSummary(context.fixture, context.state);
  await scrollTo(cdp, "#seed-input");
  await dispatchMouseClick(cdp, "#seed-input", `${label} seed input`);
  await cdp.command("Input.insertText", { text: context.fixture.seed });
  await settle(cdp);
  context.seedInput = context.fixture.seed;
  context.seedError = null;
  assertDomMatchesExpected(
    await observeDom(cdp),
    context.fixture,
    context.state,
    {
      seedInput: context.seedInput,
      seedError: null,
      label,
    }
  );
  assert.deepEqual(expectedSummary(context.fixture, context.state), before);
}

async function exerciseChallengeContract(cdp, appUrl) {
  await cdp.command("Page.navigate", { url: appUrl });
  await waitForReady(cdp);
  await settle(cdp);
  const context = {
    fixture: auditIndependentFixture("RAPP-42"),
    state: null,
    seedInput: "RAPP-42",
    seedError: null,
  };
  context.state = initialState(context.fixture);
  await loadSeedThroughUi(cdp, context, "MIST-Δ", "contract alternate");
  await driveDirections(
    cdp,
    context,
    context.fixture.route.slice(0, 2),
    "contract nontrivial trail",
    "wasd"
  );
  assert.equal(context.state.trail.length, 2);

  await clickControl(
    cdp,
    "#copy-challenge-btn",
    "contract copy export"
  );
  const exportedObservation = await observeDom(cdp);
  assertDomMatchesExpected(
    exportedObservation,
    context.fixture,
    context.state,
    { label: "contract export state" }
  );
  const exported = decodeChallengeUrl(exportedObservation.dom.challenge.link);
  assert.deepEqual(exported.contract, challengeContract(context.fixture));
  assert.match(
    exportedObservation.dom.challenge.status,
    /^Challenge fragment (copied|ready)/
  );
  if (exportedObservation.dom.challenge.status.startsWith("Challenge fragment ready")) {
    assert.equal(exportedObservation.dom.challenge.selectionStart, 0);
    assert.equal(
      exportedObservation.dom.challenge.selectionEnd,
      exportedObservation.dom.challenge.link.length
    );
  }
  assert.equal(JSON.stringify(exported.contract).includes("route"), false);
  assert.equal(JSON.stringify(exported.contract).includes("trail"), false);

  const exportedUrl = new URL(appUrl);
  exportedUrl.hash = exported.fragment;
  await cdp.command("Page.navigate", {
    url: exportedUrl.href,
  });
  await waitForReady(cdp);
  await settle(cdp);
  context.state = initialState(context.fixture);
  context.seedInput = context.fixture.seed;
  let loaded = await observeDom(cdp);
  assertDomMatchesExpected(loaded, context.fixture, context.state, {
    seedInput: context.seedInput,
    challengeStatus:
      "Challenge loaded from fragment · zero steps · empty trail.",
    label: "contract fragment round trip",
  });
  assert.equal(loaded.activeId, "maze-board");
  await auditOpeningPrivacy(cdp, context.fixture, "contract round trip");

  await driveDirections(
    cdp,
    context,
    context.fixture.route.slice(0, 1),
    "contract preservation setup"
  );
  const preserved = expectedSummary(context.fixture, context.state);
  const invalidContract = {
    ...challengeContract(context.fixture),
    route: "forbidden",
  };
  const invalidUrl = new URL(appUrl);
  invalidUrl.hash =
    "#challenge=" +
    Buffer.from(JSON.stringify(invalidContract), "utf8").toString("base64url");
  await cdp.command("Page.navigate", { url: invalidUrl.href });
  await settle(cdp);
  let rejected = await observeDom(cdp);
  assertDomMatchesExpected(rejected, context.fixture, context.state, {
    seedInput: context.seedInput,
    challengeError: CHALLENGE_ERROR_MESSAGE,
    challengeStatus: "Challenge rejected; accepted game preserved.",
    label: "contract extra-field rejection",
  });
  assert.deepEqual(expectedSummary(context.fixture, context.state), preserved);

  const mismatch = {
    ...challengeContract(context.fixture),
    topologyDigest: "0".repeat(64),
  };
  const mismatchUrl = new URL(appUrl);
  mismatchUrl.hash =
    "#challenge=" +
    Buffer.from(JSON.stringify(mismatch), "utf8").toString("base64url");
  await cdp.command("Page.navigate", { url: mismatchUrl.href });
  await settle(cdp);
  rejected = await observeDom(cdp);
  assertDomMatchesExpected(rejected, context.fixture, context.state, {
    seedInput: context.seedInput,
    challengeError: CHALLENGE_ERROR_MESSAGE,
    challengeStatus: "Challenge rejected; accepted game preserved.",
    label: "contract digest rejection",
  });
  assert.deepEqual(expectedSummary(context.fixture, context.state), preserved);

  const lengthMismatch = {
    ...challengeContract(context.fixture),
    referenceLength: context.fixture.route.length + 1,
  };
  const lengthMismatchUrl = new URL(appUrl);
  lengthMismatchUrl.hash =
    "#challenge=" +
    Buffer.from(JSON.stringify(lengthMismatch), "utf8").toString("base64url");
  await cdp.command("Page.navigate", { url: lengthMismatchUrl.href });
  await settle(cdp);
  rejected = await observeDom(cdp);
  assertDomMatchesExpected(rejected, context.fixture, context.state, {
    seedInput: context.seedInput,
    challengeError: CHALLENGE_ERROR_MESSAGE,
    challengeStatus: "Challenge rejected; accepted game preserved.",
    label: "contract length rejection",
  });
  assert.deepEqual(expectedSummary(context.fixture, context.state), preserved);

  const canonical = auditIndependentFixture("RAPP-42");
  const canonicalUrl = new URL(appUrl);
  canonicalUrl.hash = challengeFragment(canonical);
  await cdp.command("Page.navigate", { url: canonicalUrl.href });
  await settle(cdp);
  context.fixture = canonical;
  context.state = initialState(canonical);
  context.seedInput = canonical.seed;
  loaded = await observeDom(cdp);
  assertDomMatchesExpected(loaded, context.fixture, context.state, {
    seedInput: context.seedInput,
    challengeStatus:
      "Challenge loaded from fragment · zero steps · empty trail.",
    label: "contract canonical load",
  });
  assert.equal(loaded.activeId, "maze-board");
  return {
    keys: Object.keys(exported.contract).sort(),
    seed: exported.contract.seed,
    digest: exported.contract.topologyDigest,
    referenceLength: exported.contract.referenceLength,
    routeExcluded: true,
    trailExcluded: true,
    fragmentOnly: exported.fragment.startsWith("#challenge="),
    roundTripReset: true,
    invalidExtraFieldPreserved: true,
    mismatchedDigestPreserved: true,
    mismatchedLengthPreserved: true,
    invalidSetsAriaInvalid: true,
    validLoadClearsAriaInvalid: true,
  };
}

async function exerciseHintGate(cdp, appUrl) {
  await cdp.command("Page.navigate", { url: appUrl });
  await waitForReady(cdp);
  await settle(cdp);
  const context = {
    fixture: auditIndependentFixture("RAPP-42"),
    state: null,
    seedInput: "RAPP-42",
    seedError: null,
  };
  context.state = initialState(context.fixture);
  assertDomMatchesExpected(
    await observeDom(cdp),
    context.fixture,
    context.state,
    { label: "hint gate opening" }
  );
  const privacy = await auditOpeningPrivacy(
    cdp,
    context.fixture,
    "hint gate opening"
  );

  await driveDirections(
    cdp,
    context,
    ["N"],
    "hint gate rejected opening wall"
  );
  assert.equal(context.state.acceptedMoves.length, 0);
  assert.equal(context.state.hintAvailable, false);
  assert.equal(context.state.hintDirection, null);

  await scrollTo(cdp, "#hint-btn");
  const disabled = await geometry(cdp, "#hint-btn");
  assert.equal(disabled.disabled, true);
  await dispatchMouseClick(
    cdp,
    "#hint-btn",
    "hint gate disabled click",
    true
  );
  assertDomMatchesExpected(
    await observeDom(cdp),
    context.fixture,
    context.state,
    { label: "hint gate disabled click" }
  );

  await driveDirections(
    cdp,
    context,
    context.fixture.route.slice(0, 3),
    "hint gate first three"
  );
  assert.equal(context.state.hintAvailable, false);
  await driveDirections(
    cdp,
    context,
    context.fixture.route.slice(3, 4),
    "hint gate fourth move"
  );
  assert.equal(context.state.hintAvailable, true);
  await clickControl(cdp, "#hint-btn", "hint gate earned request");
  context.state = requestHintState(context.fixture, context.state);
  assert.equal(context.state.hintRequests, 1);
  assert.equal(context.state.assistanceUsed, true);
  assertDomMatchesExpected(
    await observeDom(cdp),
    context.fixture,
    context.state,
    { label: "hint gate requested" }
  );
  const direction = context.state.hintDirection;
  await driveDirections(
    cdp,
    context,
    ["E"],
    "hint gate rejected wall after request"
  );
  assert.equal(context.state.hintDirection, direction);
  assert.equal(context.state.hintRequests, 1);
  await scrollTo(cdp, "#hint-btn");
  await dispatchMouseClick(
    cdp,
    "#hint-btn",
    "hint gate spent click",
    true
  );
  assertDomMatchesExpected(
    await observeDom(cdp),
    context.fixture,
    context.state,
    { label: "hint gate spent click" }
  );
  await driveDirections(cdp, context, [direction], "hint gate one-step clear");
  assert.equal(context.state.hintDirection, null);
  assert.equal(context.state.hintRequests, 1);
  assert.equal(context.state.assistanceUsed, true);
  await rejectSeedThroughUi(
    cdp,
    context,
    "X".repeat(65),
    "hint gate invalid preservation"
  );
  await clearSeedErrorThroughValidEdit(
    cdp,
    context,
    "hint gate valid edit clears error"
  );
  await rejectSeedThroughUi(
    cdp,
    context,
    "X".repeat(65),
    "hint gate reset clearing setup"
  );
  await restartThroughUi(cdp, context, "hint gate invalid reset");
  assert.equal(
    (await observeDom(cdp)).dom.seedInput.ariaInvalid,
    "false"
  );
  return {
    privacy,
    disabledBeforeFour: true,
    enabledAtFour: true,
    rejectedWallDoesNotEarnHint: true,
    rejectedWallDoesNotConsumeGuidance: true,
    oneRequestOnly: true,
    clearedAfterOneMove: true,
    assistancePersisted: true,
    invalidPreservedNontrivialState: true,
    validEditClearsAriaInvalid: true,
    resetClearsAriaInvalid: true,
  };
}

async function assertCompletionHintLocked(cdp, context, label) {
  const before = await observeDom(cdp);
  assert.equal(context.state.completed, true);
  assert.equal(context.state.hintAvailable, false);
  assert.equal(context.state.hintDirection, null);
  assert.equal(before.dom.hintButton.disabled, true);
  const expectedAssist = context.state.assistanceUsed
    ? "ASSISTED · completion locked"
    : "UNASSISTED · completion locked";
  const expectedSuccess = `EXIT OPEN · ${
    context.state.acceptedMoves.length
  } = reference · ${context.state.assistanceUsed ? "assisted" : "unassisted"}`;
  assert.equal(before.dom.assist, expectedAssist);
  assert.equal(before.dom.success.text, expectedSuccess);

  await scrollTo(cdp, "#hint-btn");
  await dispatchMouseClick(
    cdp,
    "#hint-btn",
    `${label} disabled hint click`,
    true
  );
  await focusBoard(cdp, `${label} keyboard lock`);
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "Enter",
    code: "Enter",
    windowsVirtualKeyCode: 13,
    nativeVirtualKeyCode: 13,
  });
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "Enter",
    code: "Enter",
    windowsVirtualKeyCode: 13,
    nativeVirtualKeyCode: 13,
  });
  await settle(cdp);
  let after = await observeDom(cdp);
  assertDomMatchesExpected(after, context.fixture, context.state, {
    seedInput: context.seedInput,
    seedError: context.seedError,
    label: `${label} click and Enter`,
  });
  assert.equal(after.dom.assist, expectedAssist);
  assert.equal(after.dom.success.text, expectedSuccess);
  assert.equal(after.dom.hint.text, "");

  await dispatchKey(cdp, "ArrowUp");
  await settle(cdp);
  context.state = moveState(context.fixture, context.state, "N");
  after = await observeDom(cdp);
  assertDomMatchesExpected(after, context.fixture, context.state, {
    seedInput: context.seedInput,
    seedError: context.seedError,
    label: `${label} completed movement key`,
  });
  assert.equal(context.state.hintAvailable, false);
  assert.equal(context.state.hintDirection, null);
  assert.equal(after.dom.hintButton.disabled, true);
  assert.equal(after.dom.assist, expectedAssist);
  assert.equal(after.dom.success.text, expectedSuccess);
  return {
    hintDisabled: true,
    disabledClickPreserved: true,
    enterPreserved: true,
    movementKeyPreserved: true,
    assist: expectedAssist,
    success: expectedSuccess,
  };
}

async function exerciseCompletionAssistance(cdp, appUrl) {
  async function complete(assisted) {
    await cdp.command("Page.navigate", { url: appUrl });
    await waitForReady(cdp);
    await settle(cdp);
    const fixture = auditIndependentFixture("RAPP-42");
    const context = {
      fixture,
      state: initialState(fixture),
      seedInput: fixture.seed,
      seedError: null,
    };
    if (assisted) {
      await driveDirections(
        cdp,
        context,
        fixture.route.slice(0, 4),
        "assisted optimal earn"
      );
      await clickControl(cdp, "#hint-btn", "assisted optimal request");
      context.state = requestHintState(fixture, context.state);
      assert.equal(context.state.assistanceUsed, true);
      await driveDirections(
        cdp,
        context,
        fixture.route.slice(4),
        "assisted optimal finish"
      );
    } else {
      await driveDirections(
        cdp,
        context,
        fixture.route,
        "unassisted optimal finish"
      );
    }
    assert.equal(context.state.completed, true);
    assert.equal(context.state.matchedOptimal, true);
    assert.equal(context.state.hintAvailable, false);
    assert.equal(context.state.hintDirection, null);
    const observation = await observeDom(cdp);
    assertDomMatchesExpected(observation, fixture, context.state, {
      label: assisted ? "assisted optimal" : "unassisted optimal",
    });
    const locked = await assertCompletionHintLocked(
      cdp,
      context,
      assisted ? "assisted optimal" : "unassisted optimal"
    );
    return {
      assisted,
      steps: 18,
      matchedOptimal: true,
      hintAvailable: false,
      hintDirection: null,
      locked,
    };
  }

  return {
    assisted: await complete(true),
    unassisted: await complete(false),
  };
}

async function exerciseAlternateSeeds(cdp, appUrl) {
  await cdp.command("Page.navigate", { url: appUrl });
  await waitForReady(cdp);
  await settle(cdp);
  const context = {
    fixture: auditIndependentFixture("RAPP-42"),
    state: null,
    seedInput: "RAPP-42",
    seedError: null,
  };
  context.state = initialState(context.fixture);
  const results = [];
  const digests = new Set([context.fixture.digest]);
  for (let index = 0; index < ALTERNATE_SEEDS.length; index += 1) {
    const seed = ALTERNATE_SEEDS[index];
    const label = `alternate ${seed}`;
    await loadSeedThroughUi(cdp, context, seed, label);
    assert.equal(digests.has(context.fixture.digest), false, `${label}: digest`);
    digests.add(context.fixture.digest);
    const privacy = await auditOpeningPrivacy(cdp, context.fixture, label);

    await driveDirections(
      cdp,
      context,
      context.fixture.route,
      `${label} optimal`,
      index % 2 ? "wasd" : "arrow"
    );
    assert.equal(context.state.completed, true, `${label}: optimal completion`);
    assert.equal(context.state.matchedOptimal, true, `${label}: optimal mark`);
    assert.equal(
      context.state.acceptedMoves.length,
      context.fixture.route.length,
      `${label}: optimal length`
    );

    await restartThroughUi(cdp, context, label);
    await driveDirections(
      cdp,
      context,
      context.fixture.route.slice(0, context.fixture.trap.approachIndex),
      `${label} trap approach`,
      index % 2 ? "arrow" : "wasd"
    );
    await driveDirections(
      cdp,
      context,
      [context.fixture.trap.turn],
      `${label} trap entry`,
      index % 2 ? "arrow" : "wasd"
    );
    assert.equal(context.state.status, "trap", `${label}: trap status`);
    assert.equal(
      context.state.projectedTotal,
      context.fixture.route.length + 2,
      `${label}: trap projection`
    );
    assert.equal(context.state.exitOpen, false, `${label}: exit remained closed`);
    const tail = [
      context.fixture.trap.returnDirection,
      ...context.fixture.route.slice(context.fixture.trap.approachIndex),
    ];
    await driveDirections(
      cdp,
      context,
      tail,
      `${label} detour finish`,
      index % 2 ? "arrow" : "wasd"
    );
    assert.equal(context.state.completed, true, `${label}: detour completion`);
    assert.equal(context.state.matchedOptimal, false, `${label}: detour mark`);
    assert.equal(
      context.state.acceptedMoves.length,
      context.fixture.route.length + 2,
      `${label}: detour length`
    );
    results.push({
      seed,
      digest: context.fixture.digest,
      edges: context.fixture.edges,
      connectedCells: 36,
      routeLength: context.fixture.route.length,
      trap: context.fixture.trap,
      detourLength: context.fixture.detour.length,
      privacy,
      optimalCompleted: true,
      trapCompleted: true,
      inputFamilies: ["arrow", "wasd"],
    });
  }
  return results;
}

async function waitUntil(started, targetSeconds) {
  const targetNanoseconds = BigInt(Math.round(targetSeconds * 1_000_000_000));
  while (process.hrtime.bigint() - started < targetNanoseconds) {
    const remaining =
      Number(targetNanoseconds - (process.hrtime.bigint() - started)) / 1e6;
    await delay(Math.max(1, Math.min(remaining, 25)));
  }
}

async function replayViewport(
  cdp,
  appUrl,
  viewport,
  manifest,
  evidence,
  continuity,
  errors
) {
  await cdp.command("Emulation.setDeviceMetricsOverride", {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: 1,
    mobile: viewport.width === 390,
  });
  const exceptionStart = errors.exceptions.length;
  const consoleStart = errors.console.length;
  const requestStart = errors.requests.length;
  const failedStart = errors.failed.length;
  await cdp.command("Page.navigate", { url: appUrl });
  await waitForReady(cdp);
  await settle(cdp);

  const canonical = auditIndependentFixture("RAPP-42");
  const context = {
    fixture: canonical,
    state: initialState(canonical),
    seedInput: "RAPP-42",
    seedError: null,
  };
  const initial = await observeDom(cdp);
  assertDomMatchesExpected(initial, context.fixture, context.state, {
    seedInput: context.seedInput,
    seedError: context.seedError,
    label: `${viewport.name} opening`,
  });
  const openingPrivacy = await auditOpeningPrivacy(
    cdp,
    canonical,
    `${viewport.name} opening`
  );
  const playGeometry = await criticalPlayGeometry(cdp);
  const continuityStyle = await liveContinuityStyle(cdp);
  assertFilmLiveStructure(continuityStyle, continuity);
  if (viewport.width === 390) {
    assert(
      playGeometry.span <=
        evidence.browserRuntime.geometry.mobileCriticalSpanMaximumPixels,
      `mobile critical controls span ${playGeometry.span}px`
    );
    assert(
      playGeometry.documentHeight <=
        evidence.browserRuntime.geometry.mobileDocumentHeightMaximumPixels,
      `mobile document height ${playGeometry.documentHeight}px`
    );
  }
  assert.deepEqual(canonical.route, CANONICAL_ROUTE);
  assert.equal(canonical.digest, CANONICAL_DIGEST);
  assert.deepEqual(canonical.trap.cell, [2, 5]);
  assert.equal(canonical.trap.turn, "W");
  assert.equal(canonical.detour.length, 20);

  const scene = manifest.videos[0].live.scenes[0];
  const actions = scene.actions;
  const replay = evidence.manifestReplay;
  assert.equal(scene.dur, 24);
  assert.deepEqual(
    keyDirections(actions, replay.segments.optimal),
    canonical.route
  );
  assert.deepEqual(
    keyDirections(actions, replay.segments.detour),
    canonical.detour
  );

  const actionReports = [];
  const checkpointReports = [];
  const privacyReports = [{ claim: "opening", report: openingPrivacy }];
  const pendingCheckpoints = replay.checkpoints.map(checkpoint => ({
    ...checkpoint,
    resolved: false,
  }));
  let checkpointIndex = 0;
  const maxLateness = replay.maxActionLatenessSeconds;
  const started = process.hrtime.bigint();
  for (let index = 0; index < actions.length; index += 1) {
    const action = actions[index];
    await waitUntil(started, action.at);
    const executedAt =
      Number(process.hrtime.bigint() - started) / 1_000_000_000;
    assert(
      executedAt - action.at <= maxLateness,
      `${viewport.name} action ${index + 1} missed timing by ${
        executedAt - action.at
      }s (bound ${maxLateness}s)`
    );
    const report = await executeAction(
      cdp,
      action,
      index + 1,
      viewport.name
    );
    report.executedAt = executedAt;
    report.lateness = executedAt - action.at;
    actionReports.push(report);
    applyExpectedAction(context, action);
    const actual = await observeDom(cdp);
    assertDomMatchesExpected(actual, context.fixture, context.state, {
      seedInput: context.seedInput,
      seedError: context.seedError,
      label: `${viewport.name} action ${index + 1}`,
    });
    if (action.do === "key" && context.state.status === "trap") {
      await assertVisible(
        cdp,
        "#exit-beacon",
        `${viewport.name} trap action visible exit`
      );
      await assertVisible(
        cdp,
        ".trap-marker",
        `${viewport.name} trap action visible marker`
      );
    }

    while (checkpointIndex < pendingCheckpoints.length) {
      const checkpoint = pendingCheckpoints[checkpointIndex];
      const observedAt =
        Number(process.hrtime.bigint() - started) / 1_000_000_000;
      if (
        observedAt >
        checkpoint.timeWindow.end + maxLateness
      ) {
        throw new Error(
          `${viewport.name} checkpoint ${checkpoint.claim} missed bounded ` +
          `window ${JSON.stringify(checkpoint.timeWindow)} at ${observedAt}`
        );
      }
      if (observedAt < checkpoint.timeWindow.start) break;
      const summary = expectedSummary(context.fixture, context.state);
      if (!stateGateMatches(summary, checkpoint.stateGate)) break;
      const visible = await geometry(cdp, checkpoint.selector);
      if (!isVisibleGeometry(visible)) break;
      assert.deepEqual(
        Object.fromEntries(
          Object.keys(checkpoint.stateGate).map(key => [key, summary[key]])
        ),
        checkpoint.stateGate,
        `${viewport.name} checkpoint ${checkpoint.claim}`
      );
      if (checkpoint.claim === "hint") {
        assertNoRouteLeak(actual.dom.hint.text, canonical, "hint panel");
      }
      if (checkpoint.claim === "trap") {
        assert.equal(actual.dom.exitBeaconPresent, true);
      }
      if (
        checkpoint.claim === "resetAfterTrap" ||
        checkpoint.claim === "resetAfterOptimal" ||
        checkpoint.claim === "handoff"
      ) {
        privacyReports.push({
          claim: checkpoint.claim,
          report: await auditOpeningPrivacy(
            cdp,
            context.fixture,
            `${viewport.name} ${checkpoint.claim}`
          ),
        });
      }
      checkpoint.resolved = true;
      checkpointReports.push({
        resolvedAfterAction: index + 1,
        resolvedAt: observedAt,
        claim: checkpoint.claim,
        selector: checkpoint.selector,
        geometry: visible,
        stateGate: checkpoint.stateGate,
      });
      checkpointIndex += 1;
    }
  }

  assert.equal(
    checkpointIndex,
    pendingCheckpoints.length,
    `${viewport.name}: unresolved state-gated checkpoints`
  );
  await waitUntil(started, scene.dur);
  await settle(cdp);
  const sceneElapsed =
    Number(process.hrtime.bigint() - started) / 1_000_000_000;
  assert(
    sceneElapsed <= scene.dur + replay.maxSceneOverrunSeconds,
    `${viewport.name}: scene overrun ${sceneElapsed - scene.dur}s`
  );
  const authoredFinal = await observeDom(cdp);
  assertDomMatchesExpected(authoredFinal, context.fixture, context.state, {
    seedInput: context.seedInput,
    seedError: context.seedError,
    label: `${viewport.name} authored final`,
  });
  const handoff = auditIndependentFixture("FOG-7");
  assert.equal(context.fixture.digest, handoff.digest);
  assert.notEqual(handoff.digest, canonical.digest);
  assert.notEqual(handoff.route.length, canonical.route.length);
  assert.equal(context.state.acceptedMoves.length, 0);
  assert.equal(context.state.trail.length, 0);
  assert.equal(context.state.assistanceUsed, false);
  assert.equal(context.state.hintRequests, 0);
  assert.equal(authoredFinal.activeId, "maze-board");
  assert.equal(authoredFinal.dom.takeover.hidden, false);
  await assertVisible(
    cdp,
    "#takeover-prompt",
    `${viewport.name} final YOUR TURN`
  );

  await focusBoard(cdp, `${viewport.name} takeover`);
  await dispatchKey(
    cdp,
    codeForDirection(handoff.route[0], "wasd")
  );
  await settle(cdp);
  context.state = moveState(context.fixture, context.state, handoff.route[0]);
  const takeoverMoved = await observeDom(cdp);
  assertDomMatchesExpected(takeoverMoved, context.fixture, context.state, {
    seedInput: context.seedInput,
    seedError: context.seedError,
    label: `${viewport.name} takeover moved`,
  });
  assert.equal(context.state.acceptedMoves.length, 1);
  assert.equal(
    context.state.acceptedMoves[0],
    handoff.route[0]
  );
  await restartThroughUi(cdp, context, `${viewport.name} takeover`);
  const takeoverReset = await observeDom(cdp);
  assert.equal(context.fixture.seed, "FOG-7");
  assert.equal(context.state.acceptedMoves.length, 0);
  assert.equal(context.state.facing, "N");
  assert.deepEqual(context.state.trail, []);

  const externalRequests = errors.requests
    .slice(requestStart)
    .filter(url => /^(https?|wss?):/i.test(url));
  const networkFailures = errors.failed
    .slice(failedStart)
    .filter(item => /^(https?|wss?):/i.test(item.url || ""));
  assert.deepEqual(externalRequests, []);
  assert.deepEqual(networkFailures, []);
  assert.deepEqual(errors.exceptions.slice(exceptionStart), []);
  assert.deepEqual(errors.console.slice(consoleStart), []);

  for (const selector of [
    "#seed-value",
    "#reference-value",
    "#digest-value",
    "#step-value",
    "#projection-value",
    "#position-value",
    "#exit-value",
    "#compass-value",
    "#assist-value",
    "#seed-input",
    "#load-seed-btn",
    "#copy-challenge-btn",
    "#challenge-link",
    "#challenge-status",
    "#takeover-prompt",
  ]) {
    const fontSize = await evaluate(
      cdp,
      `Number.parseFloat(getComputedStyle(
        document.querySelector(${JSON.stringify(selector)})
      ).fontSize)`
    );
    assert(
      fontSize >= 12,
      `${viewport.name}: ${selector} font ${fontSize}px is too small`
    );
  }

  return {
    viewport,
    fixture: {
      digest: canonical.digest,
      route: canonical.route,
      trap: canonical.trap,
      detourLength: canonical.detour.length,
    },
    actionReports,
    checkpointReports,
    privacyReports,
    playGeometry,
    continuityStyle,
    maximumActionLateness: Math.max(
      ...actionReports.map(report => report.lateness)
    ),
    sceneElapsed,
    authoredFinal: expectedSummary(handoff, initialState(handoff)),
    authoredFinalFocus: authoredFinal.activeId,
    authoredFinalTakeoverVisible: !authoredFinal.dom.takeover.hidden,
    takeover: {
      firstDirection: handoff.route[0],
      movedSteps: 1,
      restartSteps: context.state.acceptedMoves.length,
      restartFacing: context.state.facing,
      inputMethod: "cdp-keyboard-wasd",
    },
    errors: {
      externalRequests,
      networkFailures,
      exceptions: errors.exceptions.slice(exceptionStart),
      console: errors.console.slice(consoleStart),
    },
  };
}

async function main() {
  const options = parseOptions(process.argv.slice(2));
  const browserPath = await discoverBrowser(options.browser);
  if (options.findBrowser) {
    console.log(browserPath);
    return;
  }

  const appPath = resolve(options.app);
  const continuityPath = resolve(options.continuity);
  const evidencePath = resolve(options.evidence);
  const manifestPath = resolve(options.manifest);
  const profilePath = resolve(options.profile);
  if (
    profilePath === ROOT ||
    profilePath === dirname(profilePath) ||
    !basename(profilePath).startsWith(".")
  ) {
    throw new Error("browser profile must be a hidden, non-root scratch directory");
  }
  await removeProfile(profilePath);

  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  const continuity = JSON.parse(await readFile(continuityPath, "utf8"));
  const evidence = JSON.parse(await readFile(evidencePath, "utf8"));
  const appSource = await readFile(appPath, "utf8");
  assert.equal(manifest.schema, "rapp-vision-production/1.0");
  assert.equal(manifest.videos.length, 1);
  assert.equal(manifest.videos[0].live.kind, "rapp-vision-live/1.0");
  assert.equal(evidence.manifestReplay.exactTiming, true);
  assert.equal(
    continuity.schema,
    "fogline-survey-film-live-continuity/1.0"
  );
  assert.equal(continuity.renderer.kind, "live-app-chromium-capture");
  assert.equal(
    continuity.sourceAppSha256,
    createHash("sha256").update(appSource, "utf8").digest("hex")
  );
  assert.equal(continuity.pixelBinding.exactAtEveryDeclaredPhase, true);
  assert.equal(
    evidence.manifestReplay.checkpointMode,
    "state-gated within bounded time windows"
  );
  assert(evidence.manifestReplay.maxActionLatenessSeconds >= 0.61);
  assert.deepEqual(
    evidence.challengeContract.keys,
    ["seed", "topologyDigest", "referenceLength"]
  );
  assert(
    evidence.claims.every(
      claim => claim.stateGate && !("expectedState" in claim)
    )
  );
  assert.equal(appSource.includes("window.foglineSurvey"), false);
  assert.equal(appSource.includes("MIST-Δ"), false);
  assert.equal(appSource.includes("A|B;C"), false);
  assert.equal(/type\s*=\s*["']password["']/i.test(appSource), false);
  assert.equal(/-webkit-text-security\s*:/i.test(appSource), false);

  const port = await reservePort();
  const launchLog = { value: "" };
  const child = spawn(
    browserPath,
    [
      "--headless=new",
      "--disable-background-networking",
      "--disable-background-mode",
      "--disable-breakpad",
      "--disable-component-update",
      "--disable-crash-reporter",
      "--disable-default-apps",
      "--disable-dev-shm-usage",
      "--disable-extensions",
      "--disable-features=Crashpad",
      "--disable-gpu",
      "--disable-sync",
      "--metrics-recording-only",
      "--no-first-run",
      "--no-default-browser-check",
      "--no-sandbox",
      `--remote-debugging-port=${port}`,
      "--remote-allow-origins=*",
      `--user-data-dir=${profilePath}`,
      "about:blank",
    ],
    { stdio: ["ignore", "pipe", "pipe"] }
  );
  let launchError = null;
  child.once("error", error => {
    launchError = error;
  });
  const capture = chunk => {
    launchLog.value += chunk.toString();
    if (launchLog.value.length > 20000) {
      launchLog.value = launchLog.value.slice(-20000);
    }
  };
  child.stdout.on("data", capture);
  child.stderr.on("data", capture);

  let cdp = null;
  let cleanupReport = null;
  try {
    if (launchError) throw launchError;
    await waitForDevTools(child, port, launchLog, 45000);
    const targetsResponse = await fetch(`http://127.0.0.1:${port}/json/list`);
    const targets = await targetsResponse.json();
    const page = targets.find(target => target.type === "page");
    assert(page && page.webSocketDebuggerUrl, "browser page target is missing");
    cdp = new CdpClient(page.webSocketDebuggerUrl);
    await cdp.connect();

    const errors = {
      exceptions: [],
      console: [],
      requests: [],
      failed: [],
      requestUrls: new Map(),
    };
    cdp.on("Runtime.exceptionThrown", event => {
      errors.exceptions.push(event.exceptionDetails || event);
    });
    cdp.on("Runtime.consoleAPICalled", event => {
      if (event.type === "error" || event.type === "assert") {
        errors.console.push(event);
      }
    });
    cdp.on("Network.requestWillBeSent", event => {
      if (event.request && event.request.url) {
        errors.requests.push(event.request.url);
        errors.requestUrls.set(event.requestId, event.request.url);
      }
    });
    cdp.on("Network.loadingFailed", event => {
      errors.failed.push({
        requestId: event.requestId,
        errorText: event.errorText,
        blockedReason: event.blockedReason || "",
        url: errors.requestUrls.get(event.requestId) || "",
      });
    });

    await cdp.command("Page.enable");
    await cdp.command("Runtime.enable");
    await cdp.command("Accessibility.enable");
    await cdp.command("Network.enable");
    await cdp.command("Network.setBlockedURLs", {
      urls: ["http://*", "https://*", "ws://*", "wss://*"],
    });

    const appUrl = pathToFileURL(appPath).href;
    await cdp.command("Emulation.setDeviceMetricsOverride", {
      width: 1120,
      height: 720,
      deviceScaleFactor: 1,
      mobile: false,
    });
    const challengeContractReport = await exerciseChallengeContract(
      cdp,
      appUrl
    );
    const hintGate = await exerciseHintGate(cdp, appUrl);
    const completionAssistance = await exerciseCompletionAssistance(
      cdp,
      appUrl
    );
    const reports = [];
    for (const viewport of evidence.browserRuntime.viewports) {
      reports.push(
        await replayViewport(
          cdp,
          appUrl,
          viewport,
          manifest,
          evidence,
          continuity,
          errors
        )
      );
    }
    await cdp.command("Emulation.setDeviceMetricsOverride", {
      width: 1120,
      height: 720,
      deviceScaleFactor: 1,
      mobile: false,
    });
    const alternateSeeds = await exerciseAlternateSeeds(cdp, appUrl);

    assert.equal(errors.requests.filter(url => /^(https?|wss?):/i.test(url)).length, 0);
    assert.equal(errors.exceptions.length, 0);
    assert.equal(errors.console.length, 0);

    const report = {
      schema: "fogline-survey-browser-verifier/1.0",
      browser: browserPath,
      devToolsPort: port,
      app: appPath,
      manifest: manifestPath,
      checks: {
        reservedExplicitPort: true,
        startupWithin45Seconds: true,
        earlyChildExitObserved: true,
        exactManifestTiming: true,
        boundedTimingUnderContention: true,
        stateGatedCheckpoints: true,
        individualSemanticKeys: true,
        independentGeneratorDigestBfs: true,
        independentStateAndDom: true,
        actualCdpMouseAndKeyboard: true,
        challengeContractRoundTrip: true,
        hintGatingAndOneStepOnly: true,
        completionAssistanceConsistency: true,
        postCompletionHintLocked: true,
        openingDomAndAccessibilityPrivacy: true,
        filmLivePixelAndStructureContinuity: true,
        alternateSeedRecomputation: true,
        unmaskedSeedInput: true,
        desktopGeometry: true,
        mobile390Geometry: true,
        compactMobilePlayCluster: true,
        keyboardFocus: true,
        freshFocusedHandoff: true,
        invalidInputPreservation: true,
        noNetworkOrScriptErrors: true,
      },
      viewports: reports,
      challengeContract: challengeContractReport,
      hintGate,
      completionAssistance,
      alternateSeeds,
      globalErrors: {
        externalRequests: errors.requests.filter(url =>
          /^(https?|wss?):/i.test(url)
        ),
        networkFailures: errors.failed.filter(item =>
          /^(https?|wss?):/i.test(item.url || "")
        ),
        exceptions: errors.exceptions,
        console: errors.console,
      },
      cleanup: null,
    };

    try {
      await cdp.command("Browser.close");
    } catch (error) {
      launchLog.value += `\nBrowser.close: ${error.message}`;
    }
    cdp.close();
    cdp = null;
    const browserExited = await waitForExit(child);
    const profileRemoved = await removeProfile(profilePath, 45000);
    cleanupReport = {
      browserExited,
      profileRemoved,
      profilePath,
    };
    assert(browserExited, "browser did not exit during cleanup");
    assert(profileRemoved, "browser profile was not removed");
    report.cleanup = cleanupReport;
    report.checks.cleanup = true;
    console.log(JSON.stringify(report));
  } finally {
    if (cdp) cdp.close();
    if (child.exitCode === null && child.signalCode === null) {
      child.kill();
      await waitForExit(child);
    }
    if (!cleanupReport || !cleanupReport.profileRemoved) {
      await removeProfile(profilePath, 45000);
    }
  }
}

export {
  CdpClient,
  delay,
  discoverBrowser,
  dispatchKey,
  dispatchMouseClick,
  evaluate,
  geometry,
  removeProfile,
  reservePort,
  settle,
  waitForDevTools,
  waitForExit,
  waitForReady,
};

const invokedDirectly =
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href;
if (invokedDirectly) {
  main().catch(error => {
    console.error(error && error.stack ? error.stack : String(error));
    process.exitCode = 1;
  });
}
