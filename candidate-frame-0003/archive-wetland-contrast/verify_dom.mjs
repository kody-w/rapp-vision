import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { constants as fsConstants } from "node:fs";
import { access, readFile, rm } from "node:fs/promises";
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
  app: join(ROOT, "apps", "explore-archive-map-contrast.html"),
  evidence: join(ROOT, "evidence.json"),
  manifest: join(ROOT, "channel.production.json"),
  profile: join(ROOT, ".browser-profile"),
};

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
    await access(path, fsConstants.X_OK);
    return true;
  } catch {
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
await rm(profilePath, { recursive: true, force: true });

const debugPort = await new Promise((resolvePort, rejectPort) => {
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

let launchError = null;
const browser = spawn(
  browserPath,
  [
    "--headless=new",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-sandbox",
    "--no-first-run",
    "--no-default-browser-check",
    `--remote-debugging-port=${debugPort}`,
    "--remote-allow-origins=*",
    `--user-data-dir=${profilePath}`,
    "about:blank",
  ],
  { stdio: "ignore" }
);
browser.once("error", error => {
  launchError = error;
});

const delay = milliseconds =>
  new Promise(resolveDelay => setTimeout(resolveDelay, milliseconds));

async function activePort(timeout = 45000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (launchError) throw launchError;
    if (browser.exitCode !== null) {
      throw new Error(`browser exited before DevTools was ready: ${browser.exitCode}`);
    }
    try {
      const response = await fetch(`http://127.0.0.1:${debugPort}/json/version`);
      if (response.ok) return String(debugPort);
    } catch {}
    await delay(75);
  }
  throw new Error("browser did not publish its reserved explicit DevTools port");
}

async function readJson(url, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch {}
    await delay(75);
  }
  throw new Error(`timed out waiting for ${url}`);
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
      this.pending.set(id, {
        resolve: resolveCommand,
        reject: rejectCommand,
      });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.close();
  }
}

let cdp;
const browserErrors = [];

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
  while (Date.now() < deadline) {
    try {
      if (await evaluate(expression)) return;
    } catch {}
    await delay(75);
  }
  throw new Error(`timed out waiting for browser condition: ${expression}`);
}

async function setViewport(viewport) {
  await cdp.command("Emulation.setDeviceMetricsOverride", {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await delay(60);
}

async function navigate(url) {
  await cdp.command("Page.navigate", { url });
  await waitFor(
    "document.readyState === 'complete' && Boolean(window.archiveWetlandMap)"
  );
}

async function click(selector) {
  const encoded = JSON.stringify(selector);
  await evaluate(`(() => {
    const element = document.querySelector(${encoded});
    if (!element) throw new Error("missing click selector " + ${encoded});
    if (element.disabled || element.getAttribute("aria-disabled") === "true") {
      throw new Error("disabled click selector " + ${encoded});
    }
    const bounds = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    if (!bounds.width || !bounds.height || style.display === "none" || style.visibility === "hidden") {
      throw new Error("hidden click selector " + ${encoded});
    }
    element.focus({ preventScroll: true });
    if (typeof element.select === "function") element.select();
    element.click();
    return true;
  })()`);
}

async function scroll(action) {
  assert.match(action.selector, /^#[A-Za-z][A-Za-z0-9_-]*$/);
  const selector = JSON.stringify(action.selector);
  const block = JSON.stringify(action.block || "center");
  await evaluate(`(() => {
    const target = document.querySelector(${selector});
    if (!target) throw new Error("missing scroll selector " + ${selector});
    target.scrollIntoView({
      block: ${block},
      inline: "nearest",
      behavior: "auto"
    });
    return true;
  })()`);
}

async function typeText(text) {
  assert.equal(typeof text, "string");
  const active = await evaluate(`(() => {
    const element = document.activeElement;
    return {
      id: element?.id || "",
      tag: element?.tagName || "",
      editable: Boolean(
        element &&
        (element.matches("input,textarea") || element.isContentEditable)
      )
    };
  })()`);
  assert.equal(active.editable, true, `typing target ${active.id || active.tag} is not editable`);
  await cdp.command("Input.insertText", { text });
}

async function replayAction(action) {
  assert.ok(!("from" in action) && !("to" in action), "replay cannot use coordinates");
  if (action.do === "scroll") {
    await scroll(action);
  } else if (action.do === "click") {
    assert.match(action.selector, /^#[A-Za-z][A-Za-z0-9_-]*$/);
    await click(action.selector);
  } else if (action.do === "type") {
    assert.ok(!("selector" in action), "typing follows semantic input focus");
    await typeText(action.text);
  } else {
    throw new Error(`unsupported archive manifest action: ${action.do}`);
  }
  await delay(55);
}

async function assertVisible(selector) {
  const result = await evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)});
    if (!element) return { exists: false };
    const bounds = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return {
      exists: true,
      width: bounds.width,
      height: bounds.height,
      top: bounds.top,
      bottom: bounds.bottom,
      display: style.display,
      visibility: style.visibility,
      viewportHeight: innerHeight
    };
  })()`);
  assert.equal(result.exists, true, `missing visible checkpoint ${selector}`);
  assert.ok(result.width > 0 && result.height > 0, `${selector} has no box`);
  assert.notEqual(result.display, "none", `${selector} is display:none`);
  assert.notEqual(result.visibility, "hidden", `${selector} is hidden`);
  assert.ok(result.bottom > 0 && result.top < result.viewportHeight, `${selector} is offscreen`);
}

async function assertDisplayed(snapshot, viewport) {
  const displayed = await evaluate(`(() => {
    const visibleMarkers = [...document.querySelectorAll(".record-marker")]
      .filter(marker => !marker.hidden)
      .map(marker => marker.dataset.recordId)
      .sort();
    return {
      fromLabel: document.querySelector("#from-label").textContent,
      toLabel: document.querySelector("#to-label").textContent,
      total: document.querySelector("#total-count").textContent,
      changed: document.querySelector("#changed-count").textContent,
      visibleFilter: document.querySelector("#visible-filter").textContent,
      focus: document.querySelector("#focus-readout").textContent,
      extent: document.querySelector("#extent-readout").textContent,
      view: document.querySelector("#view-readout").textContent,
      status: document.querySelector("#status-message").textContent,
      statusKind: document.querySelector("#status-message").dataset.status,
      errorHidden: document.querySelector("#query-error").hidden,
      error: document.querySelector("#query-error").textContent,
      exportText: document.querySelector("#export-json").textContent,
      digest: document.querySelector("#export-digest").textContent,
      visibleMarkers,
      horizontalFit: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      overflowing: [...document.querySelectorAll("body *")]
        .map(element => ({
          id: element.id || "",
          className: typeof element.className === "string" ? element.className : "",
          right: Math.round(element.getBoundingClientRect().right)
        }))
        .filter(item => item.right > document.documentElement.clientWidth + 1)
        .slice(0, 12),
      viewportWidth: innerWidth
    };
  })()`);
  assert.equal(displayed.fromLabel, snapshot.snapshotLabels.from);
  assert.equal(displayed.toLabel, snapshot.snapshotLabels.to);
  assert.equal(displayed.total, `${snapshot.totalRecords} records`);
  assert.equal(displayed.changed, `${snapshot.changedCount} records`);
  assert.equal(displayed.visibleFilter, `${snapshot.visibleCount} · ${snapshot.filter}`);
  assert.equal(displayed.focus, snapshot.focus || "none");
  assert.equal(displayed.extent, `Synthetic extent · ${snapshot.extent.label}`);
  assert.equal(
    displayed.view,
    `pan ${snapshot.view.panX},${snapshot.view.panY} · zoom ${snapshot.view.zoom.toFixed(2)}×`
  );
  assert.equal(displayed.status, snapshot.message);
  assert.equal(displayed.statusKind, snapshot.status);
  assert.equal(displayed.errorHidden, snapshot.comparison.status !== "rejected-empty");
  assert.equal(displayed.error, snapshot.comparison.message);
  assert.equal(displayed.exportText, snapshot.export.text.trimEnd());
  assert.equal(displayed.digest, `sha256 ${snapshot.export.digest}`);
  assert.deepEqual(displayed.visibleMarkers, snapshot.visibleRecordIds);
  assert.equal(displayed.viewportWidth, viewport.width);
  if (viewport.width === 390) {
    assert.equal(
      displayed.horizontalFit,
      true,
      `390 px presentation overflows horizontally: ${JSON.stringify({
        scrollWidth: displayed.scrollWidth,
        clientWidth: displayed.clientWidth,
        overflowing: displayed.overflowing,
      })}`
    );
  }
}

try {
  const port = await activePort(45000);
  const targets = await readJson(`http://127.0.0.1:${port}/json/list`);
  const page = targets.find(target => target.type === "page");
  assert.ok(page?.webSocketDebuggerUrl, "browser exposed no page target");
  cdp = new Cdp(page.webSocketDebuggerUrl);
  await cdp.connect();
  const browserVersion = await cdp.command("Browser.getVersion");
  assert.match(browserVersion.product, /(Chrome|Chromium|Edge|Edg)\//);
  await Promise.all([
    cdp.command("Page.enable"),
    cdp.command("Runtime.enable"),
    cdp.command("Log.enable"),
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

  const evidence = JSON.parse(await readFile(evidencePath, "utf8"));
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  const claims = new Map(evidence.claims.map(claim => [claim.id, claim]));
  const replay = evidence.manifestReplay;
  const scene = manifest.videos?.[0]?.live?.scenes?.[replay.scene];
  assert.ok(scene, "manifest replay scene is missing");
  assert.equal(scene.app, "apps/explore-archive-map-contrast.html");
  assert.equal(scene.actions.length, replay.actionCount);
  assert.deepEqual(
    [...new Set(scene.actions.map(action => action.do))].sort(),
    [...replay.allowedActions].sort()
  );
  assert.deepEqual(
    scene.actions
      .filter(action => action.do === replay.framingAction)
      .map(action => action.selector),
    replay.scrollSelectors
  );
  for (const action of scene.actions) {
    assert.ok(replay.allowedActions.includes(action.do));
    assert.ok(action.at >= 0 && action.at < scene.dur);
    assert.ok(!("from" in action) && !("to" in action));
    if (action.do === "scroll") {
      assert.equal(action.behavior, "auto");
      assert.ok(["start", "center"].includes(action.block));
    }
  }

  const appUrl = pathToFileURL(appPath).href;
  const checkpoints = new Map(
    replay.checkpoints.map(checkpoint => [
      checkpoint.afterAction,
      checkpoint,
    ])
  );
  const viewportResults = [];
  let lastReset = null;
  let lastFailure = null;

  for (const viewport of replay.viewports) {
    await setViewport(viewport);
    await navigate(appUrl);
    const readySelector = scene.ready.selector;
    await waitFor(`Boolean(document.querySelector(${JSON.stringify(readySelector)}))`);
    assert.equal(
      await evaluate(`document.querySelector(${JSON.stringify(readySelector)}).disabled`),
      false
    );
    const opening = await evaluate("window.archiveWetlandMap.snapshot()");
    assert.deepEqual(opening, claims.get("reset").expectedState);
    assert.equal(
      await evaluate(
        "window.archiveWetlandMap.digestText(window.archiveWetlandMap.fixture.exportText)"
      ),
      evidence.fixture.export.sha256
    );
    await assertDisplayed(opening, viewport);

    const observed = [];
    for (let index = 0; index < scene.actions.length; index += 1) {
      await replayAction(scene.actions[index]);
      const checkpoint = checkpoints.get(index);
      if (!checkpoint) continue;
      const actual = await evaluate("window.archiveWetlandMap.snapshot()");
      assert.deepEqual(actual, claims.get(checkpoint.claim).expectedState);
      await assertDisplayed(actual, viewport);
      await assertVisible(checkpoint.selector);
      observed.push(checkpoint.claim);
      if (checkpoint.claim === "failure") {
        assert.equal(actual.comparison.queryResultCount, null);
        assert.equal(actual.changedCount, 7);
        assert.equal(actual.export.status, "preserved");
        assert.equal(actual.export.digest, evidence.fixture.export.sha256);
        lastFailure = actual;
      }
      if (checkpoint.claim === "reset") {
        assert.deepEqual(actual, opening);
        lastReset = actual;
      }
    }
    assert.deepEqual(observed, ["positive", "failure", "reset"]);
    viewportResults.push(viewport.name);
  }

  await click("#record-wl-024");
  await click("#zoom-out-btn");
  await click("#pan-north-btn");
  const takeover = await evaluate("window.archiveWetlandMap.snapshot()");
  assert.equal(takeover.focus, "WL-024");
  assert.equal(takeover.visibleCount, 24);
  assert.deepEqual(takeover.view, { panX: 0, panY: -40, zoom: 0.75 });
  assert.deepEqual(browserErrors, []);

  console.log(
    JSON.stringify({
      browser: browserVersion.product,
      actionCount: scene.actions.length,
      viewports: viewportResults,
      recordCount: lastReset.totalRecords,
      changedCount: lastReset.changedCount,
      changedIds: lastReset.changedIds,
      digest: lastReset.export.digest,
      failureStatus: lastFailure.comparison.status,
      failureResultCount: lastFailure.comparison.queryResultCount,
      failureExportStatus: lastFailure.export.status,
      resetVisibleCount: lastReset.visibleCount,
      resetFocus: lastReset.focus,
      resetView: lastReset.view,
      takeover: {
        focus: takeover.focus,
        visibleCount: takeover.visibleCount,
        view: takeover.view,
      },
      browserErrors: browserErrors.length,
    })
  );
} finally {
  if (cdp) {
    try {
      await cdp.command("Browser.close");
    } catch {}
    cdp.close();
  }
  const exitDeadline = Date.now() + 2500;
  while (browser.exitCode === null && Date.now() < exitDeadline) {
    await delay(75);
  }
  if (browser.exitCode === null) browser.kill();
  await delay(500);
  try {
    await rm(profilePath, {
      recursive: true,
      force: true,
      maxRetries: 12,
      retryDelay: 150,
    });
  } catch {}
}
