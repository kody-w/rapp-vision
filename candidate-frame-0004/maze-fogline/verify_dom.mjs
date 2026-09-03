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
  evidence: join(ROOT, "evidence.json"),
  manifest: join(ROOT, "channel.production.json"),
  profile: join(ROOT, ".browser-profile"),
};
const CANONICAL_ROUTE = "SEESSWWSSENEESENNE".split("");
const CANONICAL_DIGEST =
  "126bf70440d3ef542c8dc97251726994e0f23422675e831f93309235ae085eda";
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
      "--evidence": "evidence",
      "--manifest": "manifest",
      "--profile": "profile",
    }[argument];
    if (!key || index + 1 >= argv.length) {
      throw new Error(
        "usage: node verify_dom.mjs [--browser PATH] [--app PATH] " +
        "[--evidence PATH] [--manifest PATH] [--profile PATH] [--find-browser]"
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

function mapFromAppCells(cells) {
  const maze = new Map();
  for (const cell of cells) {
    maze.set(`${cell.x},${cell.y}`, new Set(cell.openings.split("")));
  }
  return maze;
}

function auditFixture(appFixture, expectedSeed) {
  const independent = independentFixture(expectedSeed);
  assert.equal(appFixture.seed, expectedSeed);
  assert.equal(appFixture.width, 6);
  assert.equal(appFixture.height, 6);
  assert.deepEqual(appFixture.entrance, [0, 0]);
  assert.deepEqual(appFixture.exit, [5, 3]);
  assert.equal(appFixture.topologySignature, independent.signature);
  assert.equal(appFixture.topologyDigest, independent.digest);
  assert.equal(appFixture.referenceLength, independent.route.length);
  assert.deepEqual(appFixture.trap, independent.trap);
  assert.equal(appFixture.detourLength, independent.detour.length);
  assert.equal(appFixture.cells.length, 36);
  assert.equal(independent.edges, 35);

  const appMaze = mapFromAppCells(appFixture.cells);
  for (const [cellKey, openings] of appMaze) {
    const [x, y] = cellKey.split(",").map(Number);
    for (const direction of openings) {
      const neighbor = nextCell([x, y], direction);
      assert(
        appMaze.get(keyOf(neighbor)).has(OPPOSITE[direction]),
        `nonreciprocal opening ${cellKey} ${direction}`
      );
    }
  }
  assert.deepEqual(independentRoute(appMaze), independent.route);
  return independent;
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

async function waitForExit(child, timeout = 8000) {
  if (child.exitCode !== null || child.signalCode !== null) return true;
  const exited = new Promise(resolveExit => child.once("exit", resolveExit));
  const timedOut = await Promise.race([
    exited.then(() => false),
    delay(timeout).then(() => true),
  ]);
  if (!timedOut) return true;
  child.kill();
  await Promise.race([exited, delay(3000)]);
  return child.exitCode !== null || child.signalCode !== null;
}

async function removeProfile(path) {
  for (let attempt = 0; attempt < 12; attempt += 1) {
    try {
      await rm(path, { recursive: true, force: true });
      return true;
    } catch (error) {
      if (attempt === 11) throw error;
      await delay(100 * (attempt + 1));
    }
  }
  return false;
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
       !!window.foglineSurvey &&
       !!document.querySelector("#maze-board")`
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

function assertVisibleGeometry(record, label) {
  assert(record.exists, `${label}: missing ${record.selector}`);
  assert.equal(record.hidden, false, `${label}: hidden ${record.selector}`);
  assert.notEqual(record.display, "none", `${label}: display none`);
  assert.notEqual(record.visibility, "hidden", `${label}: visibility hidden`);
  assert(record.opacity > 0, `${label}: transparent`);
  assert(record.rect.width > 0 && record.rect.height > 0, `${label}: empty rect`);
  assert(
    record.rect.left >= -1 &&
      record.rect.right <= record.viewport.width + 1 &&
      record.rect.top >= -1 &&
      record.rect.bottom <= record.viewport.height + 1,
    `${label}: ${record.selector} outside viewport ${JSON.stringify(record.rect)}`
  );
  assert(
    record.scrollWidth <= record.clientWidth + 1,
    `${label}: horizontal overflow ${record.scrollWidth}/${record.clientWidth}`
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

async function executeAction(cdp, action, index, viewportName) {
  let selector = action.selector || null;
  let before = null;
  if (action.do === "scroll") {
    before = await geometry(cdp, selector);
    assert(before.exists, `action ${index}: missing scroll target ${selector}`);
    await evaluate(
      cdp,
      `(() => {
        const target = document.querySelector(${JSON.stringify(selector)});
        target.scrollIntoView({
          block: ${JSON.stringify(action.block || "center")},
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
  } else if (action.do === "click") {
    before = await assertVisible(
      cdp,
      selector,
      `${viewportName} action ${index} click before`
    );
    assert.equal(before.disabled, false, `action ${index}: disabled target`);
    await evaluate(
      cdp,
      `(() => {
        const target = document.querySelector(${JSON.stringify(selector)});
        target.focus({ preventScroll: true });
        if (typeof target.select === "function") target.select();
        target.click();
      })()`
    );
    await settle(cdp);
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
  return { index, action, before, after };
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

async function stateAndDom(cdp) {
  return await evaluate(
    cdp,
    `(() => ({
      snapshot: window.foglineSurvey.snapshot(),
      fixture: window.foglineSurvey.fixture(),
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
        exitBeaconPresent: !!document.querySelector("#exit-beacon"),
        routeText: document.body.innerText
      },
      activeId: document.activeElement ? document.activeElement.id : "",
      width: {
        scroll: document.scrollingElement.scrollWidth,
        client: document.scrollingElement.clientWidth
      }
    }))()`
  );
}

function assertDomMatchesState(record) {
  const { snapshot, dom } = record;
  assert.equal(dom.seed, snapshot.seed);
  assert.equal(dom.reference, `${snapshot.referenceLength} moves`);
  assert.equal(dom.digest, snapshot.topologyDigest);
  assert.equal(dom.steps, `${snapshot.steps} / ${snapshot.referenceLength}`);
  assert.equal(dom.projection, String(snapshot.projectedTotal));
  assert.equal(dom.position, `(${snapshot.position.x},${snapshot.position.y})`);
  assert.equal(
    dom.exit,
    `${snapshot.exit.state} · marked`
  );
  assert.equal(dom.compass, {
    N: "NORTH",
    E: "EAST",
    S: "SOUTH",
    W: "WEST",
  }[snapshot.facing]);
  assert(dom.exitBeaconPresent, "exit beacon disappeared");
  assert(record.width.scroll <= record.width.client + 1, "page overflowed");
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

  const initial = await stateAndDom(cdp);
  assertDomMatchesState(initial);
  const canonical = auditFixture(initial.fixture, "RAPP-42");
  assert.deepEqual(canonical.route, CANONICAL_ROUTE);
  assert.equal(canonical.digest, CANONICAL_DIGEST);
  assert.deepEqual(canonical.trap.cell, [2, 5]);
  assert.equal(canonical.trap.turn, "W");
  assert.equal(canonical.detour.length, 20);
  assert.equal(initial.snapshot.steps, 0);
  assert.equal(initial.snapshot.facing, "N");
  assert.equal(initial.snapshot.exit.state, "closed");
  assert.deepEqual(initial.snapshot.trail, []);
  assert.equal(initial.snapshot.assistance.used, false);
  assert(
    !initial.dom.routeText.includes(CANONICAL_ROUTE.join("")),
    "canonical route leaked into visible DOM"
  );
  assert(
    !initial.dom.routeText.includes(CANONICAL_ROUTE.join(" ")),
    "spaced canonical route leaked into visible DOM"
  );

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

  const claims = new Map(
    evidence.claims.map(claim => [claim.id, claim.expectedState])
  );
  const checkpoints = new Map();
  for (const checkpoint of replay.checkpoints) {
    const records = checkpoints.get(checkpoint.afterAction) || [];
    records.push(checkpoint);
    checkpoints.set(checkpoint.afterAction, records);
  }

  const actionReports = [];
  const checkpointReports = [];
  const started = process.hrtime.bigint();
  for (let index = 0; index < actions.length; index += 1) {
    const action = actions[index];
    await waitUntil(started, action.at);
    const executedAt =
      Number(process.hrtime.bigint() - started) / 1_000_000_000;
    assert(
      executedAt - action.at < 0.45,
      `${viewport.name} action ${index + 1} missed timing by ${
        executedAt - action.at
      }s`
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

    for (const checkpoint of checkpoints.get(index + 1) || []) {
      const visible = await assertVisible(
        cdp,
        checkpoint.selector,
        `${viewport.name} checkpoint ${checkpoint.claim}`
      );
      const actual = await stateAndDom(cdp);
      assertDomMatchesState(actual);
      assert.deepEqual(
        actual.snapshot,
        claims.get(checkpoint.claim),
        `${viewport.name} checkpoint ${checkpoint.claim} state`
      );
      if (checkpoint.claim === "hint") {
        const hint = await evaluate(
          cdp,
          `document.querySelector("#hint-panel").textContent.trim()`
        );
        assert.match(hint, /^ONE STEP ONLY: [NESW] · assistance recorded$/);
        assert(!hint.includes(CANONICAL_ROUTE.join("")));
      }
      if (checkpoint.claim === "trap") {
        assert.equal(actual.snapshot.projectedTotal, 20);
        assert.equal(actual.snapshot.exit.marked, true);
        assert.equal(actual.snapshot.exit.state, "closed");
      }
      checkpointReports.push({
        afterAction: index + 1,
        claim: checkpoint.claim,
        selector: checkpoint.selector,
        geometry: visible,
        snapshot: actual.snapshot,
      });
    }
  }

  await waitUntil(started, scene.dur);
  await settle(cdp);
  const authoredFinal = await stateAndDom(cdp);
  assertDomMatchesState(authoredFinal);
  assert.deepEqual(authoredFinal.snapshot, claims.get("handoff"));
  const handoff = auditFixture(authoredFinal.fixture, "FOG-7");
  assert.notEqual(handoff.digest, canonical.digest);
  assert.notEqual(handoff.route.length, canonical.route.length);
  await assertVisible(
    cdp,
    "#takeover-prompt",
    `${viewport.name} final YOUR TURN`
  );

  await evaluate(
    cdp,
    `document.querySelector("#maze-board").scrollIntoView({
      block: "center", inline: "nearest", behavior: "auto"
    });
    document.querySelector("#maze-board").focus({ preventScroll: true });`
  );
  await settle(cdp);
  assert.equal(
    await evaluate(
      cdp,
      `document.activeElement ? document.activeElement.id : ""`
    ),
    "maze-board"
  );
  await dispatchKey(
    cdp,
    {
      N: "ArrowUp",
      E: "ArrowRight",
      S: "ArrowDown",
      W: "ArrowLeft",
    }[handoff.route[0]]
  );
  await settle(cdp);
  const takeoverMoved = await stateAndDom(cdp);
  assert.equal(takeoverMoved.snapshot.steps, 1);
  assert.equal(
    takeoverMoved.snapshot.acceptedMoves[0],
    handoff.route[0]
  );
  await evaluate(
    cdp,
    `document.querySelector("#restart-btn").click()`
  );
  await settle(cdp);
  const takeoverReset = await stateAndDom(cdp);
  assert.equal(takeoverReset.snapshot.seed, "FOG-7");
  assert.equal(takeoverReset.snapshot.steps, 0);
  assert.equal(takeoverReset.snapshot.facing, "N");
  assert.deepEqual(takeoverReset.snapshot.trail, []);

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
    authoredFinal: authoredFinal.snapshot,
    takeover: {
      firstDirection: handoff.route[0],
      movedSteps: takeoverMoved.snapshot.steps,
      restartSteps: takeoverReset.snapshot.steps,
      restartFacing: takeoverReset.snapshot.facing,
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
  const evidence = JSON.parse(await readFile(evidencePath, "utf8"));
  assert.equal(manifest.schema, "rapp-vision-production/1.0");
  assert.equal(manifest.videos.length, 1);
  assert.equal(manifest.videos[0].live.kind, "rapp-vision-live/1.0");
  assert.equal(evidence.manifestReplay.exactTiming, true);

  const port = await reservePort();
  const launchLog = { value: "" };
  const child = spawn(
    browserPath,
    [
      "--headless=new",
      "--disable-background-networking",
      "--disable-component-update",
      "--disable-default-apps",
      "--disable-dev-shm-usage",
      "--disable-extensions",
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
      }
    });
    cdp.on("Network.loadingFailed", event => {
      errors.failed.push({
        requestId: event.requestId,
        errorText: event.errorText,
        url: event.blockedReason || "",
      });
    });

    await cdp.command("Page.enable");
    await cdp.command("Runtime.enable");
    await cdp.command("Network.enable");
    await cdp.command("Network.setBlockedURLs", {
      urls: ["http://*", "https://*", "ws://*", "wss://*"],
    });

    const appUrl = pathToFileURL(appPath).href;
    const reports = [];
    for (const viewport of evidence.browserRuntime.viewports) {
      reports.push(
        await replayViewport(
          cdp,
          appUrl,
          viewport,
          manifest,
          evidence,
          errors
        )
      );
    }

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
        individualSemanticKeys: true,
        independentGeneratorDigestBfs: true,
        desktopGeometry: true,
        mobile390Geometry: true,
        stateAndDom: true,
        keyboardFocus: true,
        invalidInputPreservation: true,
        noNetworkOrScriptErrors: true,
      },
      viewports: reports,
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
    const profileRemoved = await removeProfile(profilePath);
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
      await removeProfile(profilePath);
    }
  }
}

main().catch(error => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
});
