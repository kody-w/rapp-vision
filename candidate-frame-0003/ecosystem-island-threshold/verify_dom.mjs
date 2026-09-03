import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { constants as fsConstants } from "node:fs";
import {
  access,
  lstat,
  mkdir,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import {
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
  app: join(ROOT, "apps", "ecosystem-island-threshold.html"),
  evidence: join(ROOT, "evidence.json"),
  manifest: join(ROOT, "channel.production.json"),
  profile: join(ROOT, ".browser-profile"),
};
const PROFILE_MARKER = ".rapp-island-verifier-profile";
const PROFILE_MARKER_CONTENT = "rapp-island-verifier-profile/1\n";

function hasErrorCode(error, codes) {
  return Boolean(
    error &&
    typeof error === "object" &&
    "code" in error &&
    codes.includes(error.code)
  );
}

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
    const metadata = await lstat(path);
    if (!metadata.isFile() || metadata.isSymbolicLink()) return false;
    await access(path, fsConstants.X_OK);
    return true;
  } catch (error) {
    if (hasErrorCode(error, ["ENOENT", "EACCES", "EPERM", "ENOTDIR"])) {
      return false;
    }
    throw error;
  }
}

async function prepareProfile(path) {
  if (dirname(path) !== ROOT) {
    throw new Error("browser profile must be a direct child of the candidate directory");
  }
  let metadata = null;
  try {
    metadata = await lstat(path);
  } catch (error) {
    if (!hasErrorCode(error, ["ENOENT"])) throw error;
  }
  if (metadata) {
    if (!metadata.isDirectory() || metadata.isSymbolicLink()) {
      throw new Error("browser profile path must be a real directory");
    }
    let marker;
    try {
      marker = await readFile(join(path, PROFILE_MARKER), "utf8");
    } catch (error) {
      if (hasErrorCode(error, ["ENOENT"])) {
        throw new Error("refusing to remove an unowned browser profile directory");
      }
      throw error;
    }
    if (marker !== PROFILE_MARKER_CONTENT) {
      throw new Error("refusing to remove a browser profile with an invalid marker");
    }
    await rm(path, { recursive: true, force: false, maxRetries: 12, retryDelay: 150 });
  }
  await mkdir(path);
  await writeFile(join(path, PROFILE_MARKER), PROFILE_MARKER_CONTENT, "utf8");
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
    return roots.flatMap(root => [
      join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
      join(root, "Google", "Chrome", "Application", "chrome.exe"),
      join(root, "Chromium", "Application", "chrome.exe"),
      join(root, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ]);
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
    "Chromium-family browser not found via RAPP_BROWSER, PATH, or common locations"
  );
}

const options = parseOptions(process.argv.slice(2));
const browserPath = await discoverBrowser(options.browser);
if (options.findBrowser) {
  console.log(browserPath);
  process.exit(0);
}

const appPath = resolve(options.app);
const evidencePath = resolve(options.evidence);
const manifestPath = resolve(options.manifest);
const profilePath = resolve(options.profile);
await prepareProfile(profilePath);

let launchError = null;
let stderrText = "";
const browser = spawn(
  browserPath,
  [
    "--headless=new",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-dev-shm-usage",
    "--disable-features=OptimizationHints,MediaRouter",
    "--disable-gpu",
    "--metrics-recording-only",
    "--no-sandbox",
    "--no-first-run",
    "--no-default-browser-check",
    "--remote-debugging-port=0",
    "--remote-allow-origins=*",
    `--user-data-dir=${profilePath}`,
    "about:blank",
  ],
  { stdio: ["ignore", "ignore", "pipe"] }
);
browser.once("error", error => {
  launchError = error;
});
browser.stderr?.on("data", chunk => {
  if (stderrText.length < 16000) stderrText += chunk.toString("utf8");
});

const delay = milliseconds =>
  new Promise(resolveDelay => setTimeout(resolveDelay, milliseconds));

function errorText(error) {
  return error instanceof Error ? error.message : String(error);
}

async function activePort(timeout = 45000) {
  const deadline = Date.now() + timeout;
  const activePortPath = join(profilePath, "DevToolsActivePort");
  let lastError = null;
  while (Date.now() < deadline) {
    if (launchError) throw launchError;
    if (browser.exitCode !== null) {
      throw new Error(
        `browser exited before DevTools was ready: ${browser.exitCode}\n${stderrText}`
      );
    }
    try {
      const lines = (await readFile(activePortPath, "utf8"))
        .trim()
        .split(/\r?\n/);
      const port = Number(lines[0]);
      if (Number.isInteger(port) && port > 0 && port < 65536) {
        const response = await fetch(`http://127.0.0.1:${port}/json/version`);
        if (response.ok) return port;
      }
    } catch (error) {
      lastError = error;
    }
    await delay(75);
  }
  throw new Error(
    `browser did not publish an OS-reserved DevTools port within ${timeout} ms` +
      (lastError ? `; last error: ${errorText(lastError)}` : "")
  );
}

async function readJson(url, timeout = 15000) {
  const deadline = Date.now() + timeout;
  let lastError = null;
  while (Date.now() < deadline) {
    if (browser.exitCode !== null) {
      throw new Error(`browser exited while waiting for ${url}: ${browser.exitCode}`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
      lastError = new Error(`HTTP ${response.status} from ${url}`);
    } catch (error) {
      lastError = error;
    }
    await delay(75);
  }
  throw new Error(
    `timed out waiting for ${url}` +
      (lastError ? `; last error: ${errorText(lastError)}` : "")
  );
}

class Cdp {
  constructor(url) {
    this.url = url;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async connect() {
    this.socket = new WebSocket(this.url);
    this.socket.addEventListener("message", event => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const waiter = this.pending.get(message.id);
        if (!waiter) return;
        this.pending.delete(message.id);
        if (message.error) waiter.reject(new Error(message.error.message));
        else waiter.resolve(message.result);
        return;
      }
      for (const listener of this.listeners.get(message.method) || []) {
        listener(message.params || {});
      }
    });
    await new Promise((resolveConnect, rejectConnect) => {
      this.socket.addEventListener("open", resolveConnect, { once: true });
      this.socket.addEventListener("error", rejectConnect, { once: true });
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) || [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  command(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolveCommand, rejectCommand) => {
      this.pending.set(id, { resolve: resolveCommand, reject: rejectCommand });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket?.close();
  }
}

let cdp = null;
const browserErrors = [];
const networkRequests = [];

const ORACLE = Object.freeze({
  seed: 31415,
  horizon: 600,
  initialPopulationMilli: 104000,
  initialResourcesMilli: 146000,
  resourceCeilingMilli: 180000,
  stableLowMilli: 80000,
  stableHighMilli: 120000,
  collapseMilli: 10000,
});

function oracleXorshift32(value) {
  let next = value >>> 0;
  next ^= next << 13;
  next ^= next >>> 17;
  next ^= next << 5;
  return next >>> 0;
}

function oracleSupport(resourcesMilli) {
  if (resourcesMilli <= 90000) return 8000;
  if (resourcesMilli >= 120000) return 112000;
  const distance = resourcesMilli - 90000;
  return 8000 + Math.floor(
    (104000 * distance * distance) / (30000 * 30000)
  );
}

function oracleSimulate(rateMilli, seed = ORACLE.seed, ticks = ORACLE.horizon) {
  let point = [
    0,
    ORACLE.initialPopulationMilli,
    ORACLE.initialResourcesMilli,
    oracleSupport(ORACLE.initialResourcesMilli),
    0,
    seed,
  ];
  const points = [[...point]];
  for (let tick = 1; tick <= ticks; tick += 1) {
    const randomState = oracleXorshift32(point[5]);
    const weatherMilli = Math.floor(
      (((randomState & 1023) - 512) * 550) / 1024
    );
    const regrowthMilli = Math.floor(
      ((ORACLE.resourceCeilingMilli - point[2]) * 40) / 1000
    );
    const grazingLossMilli = Math.floor((rateMilli * 6400) / 1000);
    const resourcesMilli = Math.max(
      0,
      Math.min(
        ORACLE.resourceCeilingMilli,
        point[2] + regrowthMilli - grazingLossMilli + weatherMilli
      )
    );
    const supportMilli = oracleSupport(resourcesMilli);
    const gap = supportMilli - point[1];
    let movement = Math.floor((Math.abs(gap) * 35) / 1000);
    if (gap !== 0 && movement === 0) movement = 1;
    if (gap < 0) movement = -movement;
    point = [
      tick,
      Math.max(0, point[1] + movement),
      resourcesMilli,
      supportMilli,
      weatherMilli,
      randomState,
    ];
    points.push([...point]);
  }
  return points;
}

function oracleDigest(points) {
  let value = 0x811c9dc5;
  for (const point of points) {
    const text = `${point.join(":")};`;
    for (const character of text) {
      value ^= character.charCodeAt(0);
      value = Math.imul(value, 0x01000193) >>> 0;
    }
  }
  return value.toString(16).padStart(8, "0");
}

function displayMilli(value) {
  return value / 1000;
}

function oracleExport(points) {
  return points.map(point => ({
    tick: point[0],
    population: displayMilli(point[1]),
    populationMilli: point[1],
    resources: displayMilli(point[2]),
    resourcesMilli: point[2],
    support: displayMilli(point[3]),
    supportMilli: point[3],
    weatherMilli: point[4],
    randomState: point[5],
  }));
}

async function evaluate(expression) {
  const result = await cdp.command("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(
      result.exceptionDetails.exception?.description ||
        result.exceptionDetails.text ||
        "browser evaluation failed"
    );
  }
  return result.result.value;
}

async function waitFor(expression, timeout = 15000) {
  const deadline = Date.now() + timeout;
  let lastError = null;
  while (Date.now() < deadline) {
    if (browser.exitCode !== null) {
      throw new Error(`browser exited during condition wait: ${browser.exitCode}`);
    }
    try {
      if (await evaluate(expression)) return;
    } catch (error) {
      lastError = error;
    }
    await delay(60);
  }
  throw new Error(
    `timed out waiting for browser condition: ${expression}` +
      (lastError ? `; last error: ${errorText(lastError)}` : "")
  );
}

async function setViewport(width, height = 860) {
  await cdp.command("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await delay(80);
}

async function navigate(url) {
  await cdp.command("Page.navigate", { url });
  await waitFor(
    "document.readyState === 'complete' && Boolean(window.islandLab)"
  );
}

async function click(selector) {
  const encoded = JSON.stringify(selector);
  const target = await evaluate(`(() => {
    const element = document.querySelector(${encoded});
    if (!element) throw new Error("missing selector " + ${encoded});
    if (element.disabled || element.getAttribute("aria-disabled") === "true") {
      throw new Error("disabled selector " + ${encoded});
    }
    const bounds = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    if (
      bounds.width <= 0 ||
      bounds.height <= 0 ||
      style.display === "none" ||
      style.visibility === "hidden" ||
      Number(style.opacity) <= 0.5
    ) {
      throw new Error("hidden selector " + ${encoded});
    }
    const x = bounds.left + bounds.width / 2;
    const y = bounds.top + bounds.height / 2;
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) {
      throw new Error("offscreen selector " + ${encoded});
    }
    const hit = document.elementFromPoint(x, y);
    if (!hit || (hit !== element && !element.contains(hit))) {
      throw new Error("covered selector " + ${encoded});
    }
    return { x, y };
  })()`);
  await cdp.command("Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x: target.x,
    y: target.y,
  });
  await cdp.command("Input.dispatchMouseEvent", {
    type: "mousePressed",
    button: "left",
    buttons: 1,
    clickCount: 1,
    x: target.x,
    y: target.y,
  });
  await cdp.command("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    button: "left",
    buttons: 0,
    clickCount: 1,
    x: target.x,
    y: target.y,
  });
  await delay(45);
}

async function scrollTo(selector, action) {
  assert.match(selector, /^#[A-Za-z][A-Za-z0-9_-]*$/);
  assert.equal(action.block, "start");
  assert.equal(action.behavior, "auto");
  const encoded = JSON.stringify(selector);
  const bounds = await evaluate(`(() => {
    const element = document.querySelector(${encoded});
    if (!element) throw new Error("missing selector " + ${encoded});
    element.scrollIntoView({ block: "start", inline: "nearest", behavior: "auto" });
    const box = element.getBoundingClientRect();
    return {
      top: box.top,
      bottom: box.bottom,
      left: box.left,
      right: box.right,
      viewportWidth: innerWidth,
      viewportHeight: innerHeight
    };
  })()`);
  assert.ok(
    bounds.bottom > 0 &&
      bounds.top < bounds.viewportHeight &&
      bounds.right > 0 &&
      bounds.left < bounds.viewportWidth,
    `${selector} did not scroll into the viewport`
  );
  await delay(35);
}

function keyFromCode(code) {
  if (/^Key[A-Z]$/.test(code)) return code.slice(-1).toLowerCase();
  if (/^Digit\d$/.test(code)) return code.slice(-1);
  if (code === "Space") return " ";
  return code;
}

async function keyAction(action) {
  const code = action.code;
  assert.equal(typeof code, "string");
  const key = action.key || keyFromCode(code);
  await cdp.command("Input.dispatchKeyEvent", { type: "keyDown", code, key });
  await cdp.command("Input.dispatchKeyEvent", { type: "keyUp", code, key });
  await delay(35);
}

async function replayAction(action) {
  assert.ok(!("from" in action) && !("to" in action), "coordinate actions are forbidden");
  if (action.do === "scroll") {
    assert.equal(typeof action.selector, "string");
    await scrollTo(action.selector, action);
  } else if (action.do === "click") {
    assert.equal(typeof action.selector, "string");
    await click(action.selector);
  } else if (action.do === "key") {
    assert.ok(!("selector" in action), "key actions follow DOM focus");
    await keyAction(action);
  } else if (action.do === "type") {
    assert.ok(!("selector" in action), "type actions follow DOM focus");
    assert.equal(typeof action.text, "string");
    await cdp.command("Input.insertText", { text: action.text });
    await delay(35);
  } else {
    throw new Error(`unsupported semantic action: ${action.do}`);
  }
}

async function assertLegible(selectors, width) {
  await setViewport(width, width === 390 ? 844 : 860);
  const result = await evaluate(`(() => {
    const selectors = ${JSON.stringify(selectors)};
    return {
      pageWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      items: selectors.map(selector => {
        const element = document.querySelector(selector);
        if (!element) return { selector, missing: true };
        const style = getComputedStyle(element);
        const box = element.getBoundingClientRect();
        return {
          selector,
          display: style.display,
          visibility: style.visibility,
          opacity: Number(style.opacity),
          fontSize: parseFloat(style.fontSize),
          width: box.width,
          height: box.height
        };
      })
    };
  })()`);
  assert.ok(
    result.pageWidth <= result.clientWidth + 1,
    `page overflows ${width}px player: ${result.pageWidth} > ${result.clientWidth}`
  );
  for (const item of result.items) {
    assert.ok(!item.missing, `missing responsive selector ${item.selector}`);
    assert.notEqual(item.display, "none", `${item.selector} is not displayed`);
    assert.notEqual(item.visibility, "hidden", `${item.selector} is hidden`);
    assert.ok(item.opacity > 0.5, `${item.selector} is too faint`);
    assert.ok(item.fontSize >= 12, `${item.selector} text is too small`);
    assert.ok(item.width > 20 && item.height >= 20, `${item.selector} has no legible box`);
    if (item.selector.endsWith("-btn")) {
      assert.ok(item.height >= 44, `${item.selector} is below the 44px target`);
    }
  }
}

async function elementState(selector) {
  return evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)});
    if (!element) return { missing: true };
    const style = getComputedStyle(element);
    const box = element.getBoundingClientRect();
    return {
      missing: false,
      hidden: element.hasAttribute("hidden") || element.hidden === true,
      display: style.display,
      visibility: style.visibility,
      opacity: Number(style.opacity),
      width: box.width,
      height: box.height,
      inViewport:
        box.bottom > 0 &&
        box.top < innerHeight &&
        box.right > 0 &&
        box.left < innerWidth,
      text: element.textContent.replace(/\\s+/g, " ").trim(),
      value: "value" in element ? element.value : null
    };
  })()`);
}

function assertVisible(state, selector) {
  assert.equal(state.missing, false, `${selector} is missing`);
  assert.equal(state.hidden, false, `${selector} is hidden`);
  assert.notEqual(state.display, "none", `${selector} is not displayed`);
  assert.notEqual(state.visibility, "hidden", `${selector} is invisible`);
  assert.ok(state.opacity > 0.5, `${selector} is too faint`);
  assert.ok(state.width > 100 && state.height > 20, `${selector} has no visible box`);
  assert.equal(state.inViewport, true, `${selector} is outside the viewport`);
}

async function assertTraceOverlayHidden(hidden) {
  const overlay = await elementState("#hidden-trace-label");
  assert.equal(overlay.missing, false);
  assert.equal(overlay.hidden, hidden);
  if (hidden) {
    assert.equal(overlay.display, "none", "TRACE HIDDEN overlay remained visible");
  } else {
    assert.notEqual(overlay.display, "none", "opening TRACE HIDDEN label is absent");
  }
}

async function assertLargeAxisLabels() {
  const labels = await evaluate(`[
    "#population-axis-title",
    "#tick-axis-title"
  ].map(selector => {
    const element = document.querySelector(selector);
    const style = getComputedStyle(element);
    const box = element.getBoundingClientRect();
    return { selector, fontSize: parseFloat(style.fontSize), width: box.width, height: box.height };
  })`);
  for (const label of labels) {
    assert.ok(label.fontSize >= 18, `${label.selector} is not enlarged`);
    assert.ok(
      label.width > 8 && label.height > 4,
      `${label.selector} is not legible: ${JSON.stringify(label)}`
    );
  }
}

async function assertClickEffect(index, opening) {
  const summary = await evaluate("window.islandLab.summary()");
  if (index === 1) {
    assert.equal(summary.prediction, "band");
    assert.equal(summary.traceLength, 0);
    assert.equal(await evaluate("document.querySelector('#run-btn').disabled"), false);
  } else if (index === 3) {
    assert.equal(summary.running, true);
    assert.ok(summary.traceLength >= 1);
    await assertTraceOverlayHidden(true);
  } else if (index === 5) {
    assert.equal(summary.inspectionOpen, true);
    assert.equal(summary.status, "stable-inspected");
  } else if (index === 8) {
    assert.equal(summary.grazingRate, 0.6);
    assert.equal(summary.prediction, null);
    assert.equal(summary.traceLength, 0);
  } else if (index === 10) {
    assert.equal(summary.prediction, "collapse");
    assert.equal(summary.predictionRevision, 1);
  } else if (index === 12) {
    assert.equal(summary.speed, 2);
  } else if (index === 14) {
    assert.equal(summary.running, true);
    assert.ok(summary.traceLength >= 1);
    await assertTraceOverlayHidden(true);
  } else if (index === 17) {
    assert.equal(summary.status, "exported");
    assert.equal(summary.exportPrepared, true);
    assert.equal(summary.exportPointCount, 601);
    assert.equal(summary.exportTraceDigest, "8bb46765");
  } else if (index === 20) {
    assert.deepEqual(summary, opening);
    assert.equal(await evaluate("document.querySelector('#reset-proof').hidden"), false);
  }
}

async function runManifestReplay(width, scene, replay, claims, fixtures, oracleFixtures) {
  await setViewport(width, width === 390 ? 844 : 860);
  await navigate(pathToFileURL(appPath).href);
  const opening = await evaluate("window.islandLab.summary()");
  assert.deepEqual(opening, claims.get("reset").expectedState);
  assert.equal(opening.seed, ORACLE.seed);
  assert.equal(opening.grazingRate, 0.24);
  assert.equal(opening.speed, 1);
  assert.equal(opening.tick, 0);
  assert.equal(opening.population, 104);
  assert.equal(opening.resources, 146);
  assert.equal(opening.prediction, null);
  assert.deepEqual(opening.predictionHistory, []);
  assert.equal(opening.traceLength, 0);
  assert.equal(opening.traceDigest, null);
  assert.equal(opening.exportPrepared, false);
  assert.equal(opening.exportPointCount, 0);
  assert.equal(opening.exportTraceDigest, null);
  assert.deepEqual(await evaluate("window.islandLab.snapshot().trace"), []);
  assert.equal(await evaluate("document.querySelector('#run-btn').disabled"), true);
  await assertTraceOverlayHidden(false);
  await assertLargeAxisLabels();
  await assertLegible(
    ["#predict-band-btn", "#predict-transition-btn", "#predict-collapse-btn", "#run-btn", "#reset-btn"],
    width
  );

  const checkpoints = new Map(
    replay.checkpoints.map(checkpoint => [checkpoint.afterAction, checkpoint])
  );
  const observed = [];
  let activatedClicks = 0;
  const replayStarted = Date.now();
  for (let index = 0; index < scene.actions.length; index += 1) {
    const action = scene.actions[index];
    const wait = replayStarted + action.at * 1000 - Date.now();
    if (wait > 0) await delay(wait);
    await replayAction(action);
    if (action.do === "click") {
      activatedClicks += 1;
      await assertClickEffect(index, opening);
    }
    const checkpoint = checkpoints.get(index);
    if (!checkpoint) continue;
    const expected = claims.get(checkpoint.claim).expectedState;
    await waitFor(
      `window.islandLab.summary().status === ${JSON.stringify(expected.status)}`
    );
    const actual = await evaluate("window.islandLab.summary()");
    assert.deepEqual(actual, expected, `${checkpoint.claim} at ${width}px`);
    const visible = await elementState(checkpoint.selector);
    assertVisible(visible, checkpoint.selector);

    if (checkpoint.claim === "stable") {
      assert.match(visible.text, /112/);
      assert.match(visible.text, /80.+120/);
      const trace = await evaluate("window.islandLab.snapshot().trace");
      assert.deepEqual(trace, fixtures.get("stable-band").series);
      assert.deepEqual(trace, oracleFixtures.stable);
      await assertTraceOverlayHidden(true);
      assert.equal(
        await evaluate("document.querySelector('#predict-band-btn').getAttribute('aria-pressed')"),
        "true"
      );
      assert.ok(
        (await evaluate("document.querySelector('#trace-path').getAttribute('points')")).length > 100
      );
      await assertLegible(["#stable-result", "#inspect-trace-btn"], width);
    } else if (checkpoint.claim === "collapse") {
      assert.match(visible.text, /tick 134/i);
      assert.match(visible.text, /ends at 8/i);
      const trace = await evaluate("window.islandLab.snapshot().trace");
      assert.deepEqual(trace, fixtures.get("collapse").series);
      assert.deepEqual(trace, oracleFixtures.collapse);
      await assertTraceOverlayHidden(true);
      assert.equal(
        await evaluate("document.querySelector('#crossing-line').hasAttribute('hidden')"),
        false
      );
      assert.equal(
        await evaluate("document.querySelector('#crossing-dot').hasAttribute('hidden')"),
        false
      );
      assert.equal(
        await evaluate("document.querySelector('#speed-2-btn').getAttribute('aria-pressed')"),
        "true"
      );
      await assertLegible(["#collapse-result", "#reset-btn"], width);
    } else if (checkpoint.claim === "export") {
      const payload = JSON.parse(visible.value);
      assert.equal(payload.schema, "island-herd-run-export/1.0");
      assert.equal(payload.seed, ORACLE.seed);
      assert.equal(payload.grazingRate, 0.6);
      assert.equal(payload.collapseCrossingTick, 134);
      assert.equal(payload.traceDigest, oracleDigest(oracleFixtures.collapse));
      assert.deepEqual(payload.series, oracleExport(oracleFixtures.collapse));
      const proof = await elementState("#export-proof");
      assertVisible(proof, "#export-proof");
      assert.match(proof.text, /601 points/i);
      assert.match(proof.text, /8bb46765/i);
      assert.match(
        await evaluate("document.querySelector('#download-series-link').href"),
        /^blob:/
      );
      await assertTraceOverlayHidden(true);
    } else if (checkpoint.claim === "reset") {
      assert.match(visible.text, /Exact reset complete/i);
      assert.deepEqual(actual, opening);
      assert.deepEqual(await evaluate("window.islandLab.snapshot().trace"), []);
      assert.equal(await evaluate("document.querySelector('#trace-path').getAttribute('points')"), "");
      assert.equal(await evaluate("document.querySelector('#grazing-input').value"), "0.24");
      assert.equal(
        await evaluate("document.querySelector('#speed-1-btn').getAttribute('aria-pressed')"),
        "true"
      );
      assert.equal(
        await evaluate("document.querySelector('#predict-band-btn').getAttribute('aria-pressed')"),
        "false"
      );
      assert.equal(
        await evaluate("document.querySelector('#predict-transition-btn').getAttribute('aria-pressed')"),
        "false"
      );
      assert.equal(
        await evaluate("document.querySelector('#predict-collapse-btn').getAttribute('aria-pressed')"),
        "false"
      );
      assert.equal(await evaluate("document.querySelector('#run-btn').disabled"), true);
      assert.equal(await evaluate("document.querySelector('#stable-result').hidden"), true);
      assert.equal(await evaluate("document.querySelector('#transition-result').hidden"), true);
      assert.equal(await evaluate("document.querySelector('#collapse-result').hidden"), true);
      assert.equal(await evaluate("document.querySelector('#trace-inspection').hidden"), true);
      assert.equal(await evaluate("document.querySelector('#trace-table-body').childElementCount"), 0);
      assert.equal(await evaluate("document.querySelector('#export-panel').hidden"), true);
      assert.equal(await evaluate("document.querySelector('#series-export').value"), "");
      assert.equal(
        await evaluate("document.querySelector('#download-series-link').hasAttribute('href')"),
        false
      );
      assert.equal(
        await evaluate("document.querySelector('#crossing-line').hasAttribute('hidden')"),
        true
      );
      assert.equal(
        await evaluate("document.querySelector('#crossing-dot').hasAttribute('hidden')"),
        true
      );
      await assertTraceOverlayHidden(false);
      await assertLegible(["#reset-proof", "#predict-band-btn"], width);
    } else if (checkpoint.claim === "your-turn") {
      assert.deepEqual(actual, opening);
      assert.match(visible.text, /YOUR TURN/i);
      assert.match(visible.text, /choose a grazing rate/i);
      assert.match(visible.text, /predict stable band, transition, or collapse/i);
      assert.match(visible.text, /reveal the trace/i);
      assert.match(visible.text, /inspect the observed outcome/i);
      assert.match(visible.text, /export all 601 points/i);
    }
    observed.push(checkpoint.claim);
  }

  assert.deepEqual(observed, ["stable", "collapse", "export", "reset", "your-turn"]);
  return { activatedClicks, checkpoints: observed, opening };
}

async function compactAppSeries(rate, ticks, seed) {
  return evaluate(
    `window.islandLab.simulate(${JSON.stringify(rate)}, ${ticks}, ${seed})` +
      ".map(point => [point.tick, point.populationMilli, point.resourcesMilli, " +
      "point.supportMilli, point.weatherMilli, point.randomState])"
  );
}

async function expectBrowserThrow(expression) {
  const outcome = await evaluate(`(() => {
    try {
      ${expression};
      return null;
    } catch (error) {
      return { name: error.name, message: error.message };
    }
  })()`);
  assert.ok(outcome, `${expression} did not reject invalid input`);
  assert.match(outcome.name, /^(RangeError|TypeError)$/);
  return outcome;
}

async function semanticScroll(selector) {
  await scrollTo(selector, { block: "start", behavior: "auto" });
}

async function runSupplementalBehavior(opening, oracleFixtures, transitionExpected) {
  await setViewport(1120);
  await navigate(pathToFileURL(appPath).href);
  assert.deepEqual(await compactAppSeries(0.24, 600, ORACLE.seed), oracleFixtures.stable);
  assert.deepEqual(await compactAppSeries(0.6, 600, ORACLE.seed), oracleFixtures.collapse);

  const arbitraryRate = await compactAppSeries(0.451, 600, ORACLE.seed);
  assert.deepEqual(arbitraryRate, oracleSimulate(451));
  assert.notEqual(oracleDigest(arbitraryRate), oracleDigest(oracleFixtures.stable));
  const seedOne = await compactAppSeries(0.45, 600, 1);
  const seedTwo = await compactAppSeries(0.45, 600, 2);
  assert.deepEqual(seedOne, oracleSimulate(450, 1));
  assert.deepEqual(seedTwo, oracleSimulate(450, 2));
  assert.notEqual(oracleDigest(seedOne), oracleDigest(seedTwo));

  const invalidInputs = [];
  for (const expression of [
    "window.islandLab.simulate(-0.001)",
    "window.islandLab.simulate(0.751)",
    "window.islandLab.simulate(0.2405)",
    "window.islandLab.simulate(Number.NaN)",
    "window.islandLab.simulate(Number.POSITIVE_INFINITY)",
    "window.islandLab.simulate(0.24, -1)",
    "window.islandLab.simulate(0.24, 600.5)",
    "window.islandLab.simulate(0.24, 601)",
    "window.islandLab.simulate(0.24, 600, 0)",
    "window.islandLab.simulate(0.24, 600, 4294967296)",
  ]) {
    invalidInputs.push(await expectBrowserThrow(expression));
  }

  await navigate(pathToFileURL(appPath).href);
  await semanticScroll("#rate-45-btn");
  await click("#rate-45-btn");
  await semanticScroll("#predict-transition-btn");
  await click("#predict-transition-btn");
  await semanticScroll("#speed-4-btn");
  await click("#speed-4-btn");
  await semanticScroll("#run-btn");
  await click("#run-btn");
  await waitFor(
    "window.islandLab.summary().running === false && window.islandLab.summary().tick === 600"
  );
  const transitionSummary = await evaluate("window.islandLab.summary()");
  assert.deepEqual(transitionSummary, transitionExpected);
  await semanticScroll("#transition-result");
  const transitionResult = await elementState("#transition-result");
  assertVisible(transitionResult, "#transition-result");
  assert.match(transitionResult.text, /Prediction: transition/i);
  assert.match(transitionResult.text, /Observed outcome: intermediate transition/i);
  await assertTraceOverlayHidden(true);
  const transitionPredictionTrace = await evaluate("window.islandLab.snapshot().trace");
  await semanticScroll("#predict-band-btn");
  await click("#predict-band-btn");
  await semanticScroll("#run-btn");
  await click("#run-btn");
  await waitFor(
    "window.islandLab.summary().running === false && window.islandLab.summary().tick === 600"
  );
  const bandPredictionTrace = await evaluate("window.islandLab.snapshot().trace");
  assert.deepEqual(bandPredictionTrace, transitionPredictionTrace);
  assert.deepEqual(bandPredictionTrace, oracleFixtures.transition);
  await semanticScroll("#transition-result");
  const mismatchedPredictionResult = await elementState("#transition-result");
  assertVisible(mismatchedPredictionResult, "#transition-result");
  assert.match(mismatchedPredictionResult.text, /Prediction: stable band/i);
  assert.match(
    mismatchedPredictionResult.text,
    /Observed outcome: intermediate transition/i
  );
  await assertTraceOverlayHidden(true);

  await navigate(pathToFileURL(appPath).href);
  await semanticScroll("#predict-band-btn");
  await click("#predict-band-btn");
  await semanticScroll("#speed-4-btn");
  await click("#speed-4-btn");
  await semanticScroll("#run-btn");
  await click("#run-btn");
  await waitFor(
    "window.islandLab.summary().running === false && window.islandLab.summary().tick === 600"
  );
  await assertTraceOverlayHidden(true);
  await semanticScroll("#export-series-btn");
  await click("#export-series-btn");
  const exported = await evaluate(
    "JSON.parse(document.querySelector('#series-export').value)"
  );
  assert.equal(exported.schema, "island-herd-run-export/1.0");
  assert.equal(exported.seed, ORACLE.seed);
  assert.equal(exported.grazingRate, 0.24);
  assert.equal(exported.collapseCrossingTick, null);
  assert.equal(exported.traceDigest, oracleDigest(oracleFixtures.stable));
  assert.deepEqual(exported.series, oracleExport(oracleFixtures.stable));
  const downloadUrl = await evaluate(
    "document.querySelector('#download-series-link').href"
  );
  assert.match(downloadUrl, /^blob:/);
  assert.equal(await evaluate("document.querySelector('#export-panel').hidden"), false);
  await evaluate(`(() => {
    const revoke = URL.revokeObjectURL.bind(URL);
    window.__revokedObjectUrls = [];
    URL.revokeObjectURL = value => {
      window.__revokedObjectUrls.push(value);
      return revoke(value);
    };
  })()`);

  await semanticScroll("#reset-btn");
  await click("#reset-btn");
  assert.deepEqual(await evaluate("window.islandLab.summary()"), opening);
  assert.equal(await evaluate("document.querySelector('#series-export').value"), "");
  assert.equal(
    await evaluate("document.querySelector('#download-series-link').hasAttribute('href')"),
    false
  );
  assert.equal(await evaluate("document.querySelector('#export-panel').hidden"), true);
  await assertTraceOverlayHidden(false);
  assert.deepEqual(
    await evaluate("window.__revokedObjectUrls"),
    [downloadUrl]
  );

  return {
    arbitraryRateDigest: oracleDigest(arbitraryRate),
    seedDigests: [oracleDigest(seedOne), oracleDigest(seedTwo)],
    predictionDigest: oracleDigest(transitionPredictionTrace),
    transitionFinal: transitionSummary.population,
    transitionOutcome: transitionSummary.outcome,
    traceOverlayHidden: true,
    exportPointCount: exported.series.length,
    invalidInputCount: invalidInputs.length,
    exportCleanedOnReset: true,
  };
}

function waitForBrowserExit(timeout) {
  if (browser.exitCode !== null || browser.signalCode !== null) {
    return Promise.resolve(true);
  }
  return new Promise(resolveExit => {
    const onExit = () => {
      clearTimeout(timer);
      resolveExit(true);
    };
    const timer = setTimeout(() => {
      browser.off("exit", onExit);
      resolveExit(false);
    }, timeout);
    browser.once("exit", onExit);
    if (browser.exitCode !== null || browser.signalCode !== null) onExit();
  });
}

async function removeOwnedProfile() {
  await rm(profilePath, {
    recursive: true,
    force: true,
    maxRetries: 12,
    retryDelay: 150,
  });
  try {
    await lstat(profilePath);
  } catch (error) {
    if (hasErrorCode(error, ["ENOENT"])) return;
    throw error;
  }
  throw new Error("browser profile cleanup did not remove the owned directory");
}

let report = null;
try {
  const port = await activePort();
  const targets = await readJson(`http://127.0.0.1:${port}/json/list`);
  const page = targets.find(target => target.type === "page");
  assert.ok(page?.webSocketDebuggerUrl, "browser exposed no page target");
  cdp = new Cdp(page.webSocketDebuggerUrl);
  await cdp.connect();
  const browserVersion = await cdp.command("Browser.getVersion");
  assert.match(
    browserVersion.product,
    /(Chrome|Chromium|Edge|Edg)\//,
    "verification requires a Chromium-family browser"
  );
  await Promise.all([
    cdp.command("Page.enable"),
    cdp.command("Runtime.enable"),
    cdp.command("Log.enable"),
    cdp.command("Network.enable"),
  ]);
  cdp.on("Runtime.exceptionThrown", ({ exceptionDetails }) => {
    browserErrors.push(
      exceptionDetails.exception?.description || exceptionDetails.text
    );
  });
  cdp.on("Log.entryAdded", ({ entry }) => {
    if (entry.level === "error" && entry.source === "javascript") {
      browserErrors.push(entry.text);
    }
  });
  cdp.on("Network.requestWillBeSent", ({ request }) => {
    networkRequests.push(request.url);
  });

  const evidence = JSON.parse(await readFile(evidencePath, "utf8"));
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  const claims = new Map(evidence.claims.map(claim => [claim.id, claim]));
  const fixtures = new Map(evidence.fixtures.map(fixture => [fixture.id, fixture]));
  const replay = evidence.manifestReplay;
  const scene = manifest.videos?.[0]?.live?.scenes?.[replay.scene];
  assert.ok(scene, "manifest replay scene is missing");
  assert.equal(scene.app, "apps/ecosystem-island-threshold.html");
  assert.deepEqual(scene.ready, { enabled: true, selector: replay.readySelector });
  assert.equal(scene.actions.length, replay.actionCount);
  assert.equal(replay.coordinateFree, true);
  assert.deepEqual(
    [...new Set(scene.actions.map(action => action.do))].sort(),
    ["click", "scroll"]
  );
  for (const action of scene.actions) {
    assert.ok(replay.allowedActions.includes(action.do));
    assert.ok(action.at >= 0 && action.at < scene.dur);
    assert.ok(!("from" in action) && !("to" in action));
  }

  const oracleFixtures = {
    stable: oracleSimulate(240),
    transition: oracleSimulate(450),
    collapse: oracleSimulate(600),
  };
  assert.ok(
    oracleFixtures.stable.every(
      point =>
        point[1] >= ORACLE.stableLowMilli &&
        point[1] <= ORACLE.stableHighMilli
    )
  );
  assert.equal(oracleFixtures.stable.at(-1)[1], 112000);
  assert.equal(oracleFixtures.transition.at(-1)[1], 45117);
  assert.equal(
    oracleFixtures.transition.some(point => point[1] < ORACLE.stableLowMilli),
    true
  );
  assert.equal(
    oracleFixtures.transition.some(point => point[1] < ORACLE.collapseMilli),
    false
  );
  const collapseCrossing = oracleFixtures.collapse.find(
    point => point[0] > 0 && point[1] < ORACLE.collapseMilli
  )?.[0];
  assert.equal(collapseCrossing, 134);
  assert.ok(collapseCrossing < 300);
  assert.equal(oracleFixtures.collapse.at(-1)[1], 8000);
  assert.deepEqual(fixtures.get("stable-band").series, oracleFixtures.stable);
  assert.deepEqual(fixtures.get("transition").series, oracleFixtures.transition);
  assert.deepEqual(fixtures.get("collapse").series, oracleFixtures.collapse);

  const desktop = await runManifestReplay(
    1120,
    scene,
    replay,
    claims,
    fixtures,
    oracleFixtures
  );
  const responsive = await runManifestReplay(
    390,
    scene,
    replay,
    claims,
    fixtures,
    oracleFixtures
  );
  const supplemental = await runSupplementalBehavior(
    desktop.opening,
    oracleFixtures,
    claims.get("transition").expectedState
  );

  assert.deepEqual(browserErrors, []);
  const externalRequests = networkRequests.filter(url => /^https?:/i.test(url));
  assert.deepEqual(
    externalRequests,
    [],
    "standalone app made an external network request"
  );

  report = {
    browser: browserVersion.product,
    actionCount: scene.actions.length,
    replayedWidths: [1120, 390],
    activatedClicks: {
      desktop: desktop.activatedClicks,
      responsive: responsive.activatedClicks,
    },
    checkpoints: desktop.checkpoints,
    responsiveCheckpoints: responsive.checkpoints,
    stableFinal: oracleFixtures.stable.at(-1)[1] / 1000,
    collapseCrossingTick: collapseCrossing,
    collapseFinal: oracleFixtures.collapse.at(-1)[1] / 1000,
    canonicalExportPointCount: oracleFixtures.collapse.length,
    canonicalExportDigest: oracleDigest(oracleFixtures.collapse),
    resetTraceLength: desktop.opening.traceLength,
    responsiveWidth: 390,
    browserErrors: browserErrors.length,
    externalRequests: externalRequests.length,
    ...supplemental,
  };
} finally {
  if (cdp) cdp.close();
  if (browser.exitCode === null && browser.signalCode === null) browser.kill();
  let exited = await waitForBrowserExit(3000);
  if (!exited) {
    browser.kill("SIGKILL");
    exited = await waitForBrowserExit(3000);
  }
  assert.equal(exited, true, "browser process did not terminate");
  await removeOwnedProfile();
}

report.profileCleaned = true;
console.log(JSON.stringify(report));
