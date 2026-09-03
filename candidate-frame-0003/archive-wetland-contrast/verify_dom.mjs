import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createServer } from "node:net";
import { constants as fsConstants } from "node:fs";
import { access, readFile, rm } from "node:fs/promises";
import {
  delimiter,
  basename,
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
if (
  profilePath === ROOT ||
  profilePath === dirname(profilePath) ||
  !basename(profilePath).startsWith(".")
) {
  throw new Error("browser profile must be a hidden, non-root scratch directory");
}
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
const browserRunning = () =>
  browser.exitCode === null && browser.signalCode === null;
const errorText = error =>
  error instanceof Error ? `${error.name}: ${error.message}` : String(error);

async function activePort(timeout = 45000) {
  const deadline = Date.now() + timeout;
  let lastError = null;
  while (Date.now() < deadline) {
    if (launchError) throw launchError;
    if (!browserRunning()) {
      throw new Error(
        `browser exited before DevTools was ready: ${browser.exitCode ?? browser.signalCode}`
      );
    }
    try {
      const response = await fetch(`http://127.0.0.1:${debugPort}/json/version`);
      if (response.ok) return String(debugPort);
    } catch (error) {
      lastError = error;
    }
    await delay(75);
  }
  throw new Error(
    "browser did not publish its reserved explicit DevTools port" +
    (lastError ? `; last error: ${errorText(lastError)}` : "")
  );
}

async function readJson(url, timeout = 15000) {
  const deadline = Date.now() + timeout;
  let lastError = null;
  while (Date.now() < deadline) {
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
        clearTimeout(waiter.timer);
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
    const rejectPending = event => {
      const reason = new Error(
        `DevTools socket ${event.type === "close" ? "closed" : "failed"}`
      );
      for (const waiter of this.pending.values()) {
        clearTimeout(waiter.timer);
        waiter.reject(reason);
      }
      this.pending.clear();
    };
    this.socket.addEventListener("close", rejectPending);
    this.socket.addEventListener("error", rejectPending);
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) || [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  command(method, params = {}, timeout = 15000) {
    const id = this.nextId++;
    return new Promise((resolveCommand, rejectCommand) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        rejectCommand(new Error(`DevTools command timed out: ${method}`));
      }, timeout);
      this.pending.set(id, {
        resolve: resolveCommand,
        reject: rejectCommand,
        timer,
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
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      if (await evaluate(expression)) return;
    } catch (error) {
      lastError = error;
    }
    await delay(75);
  }
  throw new Error(
    `timed out waiting for browser condition: ${expression}` +
    (lastError ? `; last error: ${errorText(lastError)}` : "")
  );
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
  await assertVisible(selector);
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
  await delay(40);
  await assertVisible(action.selector);
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
      ),
      width: element?.getBoundingClientRect().width || 0,
      height: element?.getBoundingClientRect().height || 0,
      left: element?.getBoundingClientRect().left || 0,
      right: element?.getBoundingClientRect().right || 0,
      top: element?.getBoundingClientRect().top || 0,
      bottom: element?.getBoundingClientRect().bottom || 0,
      display: element ? getComputedStyle(element).display : "",
      visibility: element ? getComputedStyle(element).visibility : ""
    };
  })()`);
  assert.equal(active.editable, true, `typing target ${active.id || active.tag} is not editable`);
  assert.ok(active.width > 0 && active.height > 0, "typing target has no box");
  assert.notEqual(active.display, "none", "typing target is display:none");
  assert.notEqual(active.visibility, "hidden", "typing target is hidden");
  assert.ok(
    active.right > 0 &&
      active.left < (await evaluate("innerWidth")) &&
      active.bottom > 0 &&
      active.top < (await evaluate("innerHeight")),
    "typing target is outside the viewport"
  );
  await cdp.command("Input.insertText", { text });
}

async function pressKey(key, code = key) {
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyDown",
    key,
    code,
  });
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyUp",
    key,
    code,
  });
  await delay(35);
}

async function tabSequence(count) {
  await evaluate(`(() => {
    document.body.setAttribute("tabindex", "-1");
    document.body.focus({ preventScroll: true });
    return document.activeElement === document.body;
  })()`);
  const sequence = [];
  for (let index = 0; index < count; index += 1) {
    await pressKey("Tab", "Tab");
    sequence.push(await evaluate("document.activeElement?.id || ''"));
  }
  await evaluate(`(() => {
    document.activeElement?.blur();
    document.body.removeAttribute("tabindex");
    return true;
  })()`);
  return sequence;
}

async function auditEditorialLayout(viewport) {
  const audit = await evaluate(`(() => {
    const firstRecord = document.querySelector("#record-wl-001");
    const compare = document.querySelector("#compare-btn");
    const markers = [...document.querySelectorAll(".record-marker")];
    const visibleOwnText = [...document.querySelectorAll("body *")]
      .filter(element => {
        if (["SCRIPT", "STYLE", "DATALIST", "OPTION"].includes(element.tagName)) return false;
        if (element.hidden) return false;
        const style = getComputedStyle(element);
        if (style.display === "none" || style.visibility === "hidden") return false;
        return [...element.childNodes].some(
          node => node.nodeType === Node.TEXT_NODE && node.textContent.trim()
        );
      })
      .map(element => ({
        id: element.id || "",
        tag: element.tagName,
        text: element.textContent.trim().slice(0, 80),
        pixels: Number.parseFloat(getComputedStyle(element).fontSize)
      }));
    const shell = document.querySelector(".shell").getBoundingClientRect();
    const workspace = document.querySelector(".workspace").getBoundingClientRect();
    return {
      controlsBeforeRecords: Boolean(
        compare.compareDocumentPosition(firstRecord) & Node.DOCUMENT_POSITION_FOLLOWING
      ),
      rovingStops: markers.filter(marker => !marker.hidden && marker.tabIndex === 0)
        .map(marker => marker.id),
      nonRovingStops: markers.filter(marker => marker.tabIndex > 0).map(marker => marker.id),
      smallText: visibleOwnText.filter(item => item.pixels < 12),
      exportPixels: Number.parseFloat(
        getComputedStyle(document.querySelector("#export-json")).fontSize
      ),
      digestPixels: Number.parseFloat(
        getComputedStyle(document.querySelector("#export-digest")).fontSize
      ),
      documentWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      bodyWidth: document.body.scrollWidth,
      shellWidth: shell.width,
      shellLeft: shell.left,
      shellRight: shell.right,
      workspaceWidth: workspace.width,
      htmlOverflowX: getComputedStyle(document.documentElement).overflowX,
      bodyOverflowX: getComputedStyle(document.body).overflowX
    };
  })()`);
  assert.equal(audit.controlsBeforeRecords, true);
  assert.deepEqual(audit.rovingStops, ["record-wl-001"]);
  assert.deepEqual(audit.nonRovingStops, []);
  assert.deepEqual(audit.smallText, []);
  if (viewport.width === 390) {
    assert.ok(audit.clientWidth <= 390 && audit.clientWidth >= 370);
    assert.equal(audit.documentWidth, audit.clientWidth);
    assert.ok(audit.bodyWidth <= audit.clientWidth);
    assert.ok(audit.shellWidth <= audit.clientWidth);
    assert.ok(audit.workspaceWidth <= audit.clientWidth - 12);
    assert.ok(
      audit.shellLeft >= -0.5 &&
        audit.shellRight <= audit.clientWidth + 0.5
    );
    assert.ok(!["clip", "hidden"].includes(audit.htmlOverflowX));
    assert.ok(!["clip", "hidden"].includes(audit.bodyOverflowX));
    assert.ok(audit.exportPixels >= 13);
    assert.ok(audit.digestPixels >= 13);
  }
  return audit;
}

async function auditRovingKeyboard(opening) {
  await scroll({ selector: "#record-wl-001", block: "center" });
  await evaluate(`document.querySelector("#record-wl-001").focus({ preventScroll: true })`);
  await pressKey("ArrowRight", "ArrowRight");
  assert.equal(await evaluate("document.activeElement.id"), "record-wl-002");
  assert.equal(await evaluate("window.archiveWetlandMap.snapshot().focus"), null);
  await pressKey("Enter", "Enter");
  assert.equal(await evaluate("window.archiveWetlandMap.snapshot().focus"), "WL-002");
  await pressKey("ArrowRight", "ArrowRight");
  assert.equal(await evaluate("document.activeElement.id"), "record-wl-003");
  await pressKey(" ", "Space");
  assert.equal(await evaluate("window.archiveWetlandMap.snapshot().focus"), "WL-003");
  const tabStops = await evaluate(
    `[...document.querySelectorAll(".record-marker")]
      .filter(marker => !marker.hidden && marker.tabIndex === 0)
      .map(marker => marker.id)`
  );
  assert.deepEqual(tabStops, ["record-wl-003"]);
  assert.deepEqual(
    await evaluate(`window.archiveWetlandMap.dispatch({ type: "RESET" })`),
    opening
  );
  assert.equal(await evaluate("window.archiveWetlandMap.rovingRecord()"), "WL-001");
  return {
    arrowTarget: "record-wl-002",
    enterSelection: "WL-002",
    spaceSelection: "WL-003",
    tabStops: 1,
  };
}

async function auditFailureLayout(viewport) {
  const layout = await evaluate(`(() => {
    const error = document.querySelector("#query-error");
    const map = document.querySelector(".map-card");
    const workspace = document.querySelector(".workspace");
    const errorBounds = error.getBoundingClientRect();
    const mapBounds = map.getBoundingClientRect();
    const workspaceBounds = workspace.getBoundingClientRect();
    const visibleFailureNotices = [
      document.querySelector("#query-error"),
      document.querySelector("#status-message")
    ].filter(element => {
      const style = getComputedStyle(element);
      return !element.hidden && style.display !== "none" && style.visibility !== "hidden";
    });
    return {
      errorTitle: document.querySelector("#query-error-title").textContent,
      errorBody: document.querySelector("#query-error-body").textContent,
      statusHidden: document.querySelector("#status-message").hidden,
      noticeCount: visibleFailureNotices.length,
      errorWidth: errorBounds.width,
      workspaceWidth: workspaceBounds.width,
      errorLeft: errorBounds.left,
      workspaceLeft: workspaceBounds.left,
      adjacentGap: Math.min(
        Math.abs(errorBounds.bottom - mapBounds.top),
        Math.abs(mapBounds.bottom - errorBounds.top)
      ),
      viewportWidth: innerWidth
    };
  })()`);
  assert.equal(layout.errorTitle, "INVALID RANGE — NOT A VALID ZERO-CHANGE RESULT");
  assert.match(layout.errorBody, /accepted seven-ID export remains preserved/);
  assert.equal(layout.statusHidden, true);
  assert.equal(layout.noticeCount, 1);
  assert.ok(Math.abs(layout.errorWidth - layout.workspaceWidth) <= 1);
  assert.ok(Math.abs(layout.errorLeft - layout.workspaceLeft) <= 1);
  assert.ok(layout.adjacentGap <= 15);
  assert.equal(layout.viewportWidth, viewport.width);
  return {
    fullWidth: true,
    adjacent: true,
    visibleNotices: 1,
  };
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
      left: bounds.left,
      right: bounds.right,
      display: style.display,
      visibility: style.visibility,
      opacity: style.opacity,
      viewportHeight: innerHeight,
      viewportWidth: innerWidth
    };
  })()`);
  assert.equal(result.exists, true, `missing visible checkpoint ${selector}`);
  assert.ok(result.width > 0 && result.height > 0, `${selector} has no box`);
  assert.notEqual(result.display, "none", `${selector} is display:none`);
  assert.notEqual(result.visibility, "hidden", `${selector} is hidden`);
  assert.notEqual(result.opacity, "0", `${selector} is transparent`);
  assert.ok(result.bottom > 0 && result.top < result.viewportHeight, `${selector} is offscreen`);
  assert.ok(result.right > 0 && result.left < result.viewportWidth, `${selector} is offscreen`);
}

async function assertDisplayed(snapshot, viewport) {
  const displayed = await evaluate(`(() => {
    const visibleMarkers = [...document.querySelectorAll(".record-marker")]
      .filter(marker => !marker.hidden)
      .map(marker => marker.dataset.recordId)
      .sort();
    const legendBounds = document.querySelector("#change-legend").getBoundingClientRect();
    return {
      fromLabel: document.querySelector("#from-label").textContent,
      toLabel: document.querySelector("#to-label").textContent,
      total: document.querySelector("#total-count").textContent,
      changed: document.querySelector("#changed-count").textContent,
      visibleFilter: document.querySelector("#visible-filter").textContent,
      changedButton: document.querySelector("#filter-changed-btn").textContent,
      focus: document.querySelector("#focus-readout").textContent,
      extent: document.querySelector("#extent-readout").textContent,
      view: document.querySelector("#view-readout").textContent,
      status: document.querySelector("#status-message").textContent,
      statusKind: document.querySelector("#status-message").dataset.status,
      statusHidden: document.querySelector("#status-message").hidden,
      errorHidden: document.querySelector("#query-error").hidden,
      errorTitle: document.querySelector("#query-error-title").textContent,
      errorBody: document.querySelector("#query-error-body").textContent,
      exportText: document.querySelector("#export-json").textContent,
      digest: document.querySelector("#export-digest").textContent,
      exportProvenance: document.querySelector("#export-provenance").textContent,
      legend: document.querySelector("#change-legend").getAttribute("aria-label"),
      legendVisible:
        legendBounds.width > 0 &&
        legendBounds.height > 0 &&
        legendBounds.bottom > 0 &&
        legendBounds.top < innerHeight,
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
  assert.equal(displayed.changedButton, `Show ${snapshot.changedCount} changed`);
  assert.equal(displayed.focus, snapshot.focus || "none");
  assert.equal(
    displayed.extent,
    "Synthetic bounds: west 1000 to east 1600; south 2000 to north 2400. " +
      `Exact extent: ${snapshot.extent.label}.`
  );
  assert.equal(
    displayed.view,
    `horizontal shift ${snapshot.view.panX} px · vertical shift ${snapshot.view.panY} px · ` +
      `zoom ${snapshot.view.zoom.toFixed(2)}×`
  );
  assert.equal(displayed.status, snapshot.message);
  assert.equal(displayed.statusKind, snapshot.status);
  assert.equal(displayed.statusHidden, snapshot.status === "failure");
  assert.equal(displayed.errorHidden, !snapshot.comparison.status.startsWith("rejected-"));
  assert.equal(displayed.errorBody, snapshot.comparison.message);
  assert.equal(
    displayed.errorTitle,
    snapshot.comparison.status === "rejected-empty"
      ? "INVALID RANGE — NOT A VALID ZERO-CHANGE RESULT"
      : "INVALID QUERY — ENTER WHOLE-YEAR SNAPSHOTS"
  );
  assert.equal(displayed.exportText, snapshot.export.text.trimEnd());
  assert.equal(displayed.digest, `SHA-256 ${snapshot.export.digest}`);
  assert.equal(displayed.exportProvenance, "Observed from 24 synthetic records.");
  assert.equal(
    displayed.legend,
    "rust ring = changed 1990→2020; dark ring = unchanged"
  );
  assert.equal(displayed.legendVisible, true);
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

const EXPECTED_CHANGED_IDS = [
  "WL-002",
  "WL-005",
  "WL-009",
  "WL-012",
  "WL-016",
  "WL-020",
  "WL-023",
];
const EXPECTED_EXPORT_DIGEST =
  "fe05f5f52ddd174f2756d865e6e1baea3c0aa5497e8052ce430d1c4c8c1761e6";
const requestUrls = new Map();
const externalRequests = [];
const blockedExternalRequests = [];
let report = null;
let runError = null;

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
    cdp.command("Network.enable"),
  ]);
  await cdp.command("Network.setBlockedURLs", {
    urls: ["http://*", "https://*", "ws://*", "wss://*"],
  });
  cdp.on("Runtime.exceptionThrown", ({ exceptionDetails }) => {
    browserErrors.push(
      exceptionDetails.exception?.description || exceptionDetails.text
    );
  });
  cdp.on("Runtime.consoleAPICalled", ({ type, args }) => {
    if (type === "error") {
      browserErrors.push(
        args.map(value => value.value ?? value.description ?? "").join(" ")
      );
    }
  });
  cdp.on("Log.entryAdded", ({ entry }) => {
    if (entry.level === "error" && entry.source === "javascript") {
      browserErrors.push(entry.text);
    }
  });
  cdp.on("Network.requestWillBeSent", ({ requestId, request }) => {
    requestUrls.set(requestId, request.url);
    if (/^(?:https?|wss?):/i.test(request.url)) {
      externalRequests.push(request.url);
    }
  });
  cdp.on("Network.loadingFailed", ({ requestId, blockedReason }) => {
    const url = requestUrls.get(requestId);
    if (blockedReason && url && /^(?:https?|wss?):/i.test(url)) {
      blockedExternalRequests.push({ url, blockedReason });
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
  assert.equal(replay.exactTiming, true);
  assert.equal(replay.activationVisibilityRequired, true);
  assert.equal(replay.checkpointVisibilityRequired, true);
  assert.equal(replay.finalPrompt.afterAction, scene.actions.length - 1);
  assert.equal(
    scene.actions[replay.finalPrompt.afterAction].selector,
    replay.finalPrompt.selector
  );
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
  const timingSkews = [];
  const tabOrders = [];
  const editorialLayouts = [];
  const rovingResults = [];
  const failureLayouts = [];
  let finalPromptChecks = 0;
  let lastReset = null;
  let lastFailure = null;

  for (const viewport of replay.viewports) {
    await setViewport(viewport);
    await navigate(appUrl);
    const readySelector = scene.ready.selector;
    await waitFor(`Boolean(document.querySelector(${JSON.stringify(readySelector)}))`);
    await assertVisible(readySelector);
    assert.equal(
      await evaluate(`document.querySelector(${JSON.stringify(readySelector)}).disabled`),
      false
    );
    assert.equal(
      await evaluate("window.tinySystem === window.archiveWetlandMap"),
      true
    );
    const actualFixture = await evaluate("window.archiveWetlandMap.fixture");
    assert.equal(actualFixture.synthetic, true);
    assert.equal(actualFixture.records.length, 24);
    assert.deepEqual(
      actualFixture.records.map(record => record.id),
      Array.from({ length: 24 }, (_, index) => `WL-${String(index + 1).padStart(3, "0")}`)
    );
    const independentlyChanged = actualFixture.records
      .filter(record => record.snapshots["1990"] !== record.snapshots["2020"])
      .map(record => record.id)
      .sort();
    const canonicalText = `${JSON.stringify(independentlyChanged)}\n`;
    const independentDigest = createHash("sha256")
      .update(canonicalText, "utf8")
      .digest("hex");
    assert.deepEqual(independentlyChanged, EXPECTED_CHANGED_IDS);
    assert.equal(independentDigest, EXPECTED_EXPORT_DIGEST);
    assert.equal(canonicalText, evidence.fixture.export.text);

    const opening = await evaluate("window.archiveWetlandMap.snapshot()");
    assert.deepEqual(opening, claims.get("reset").expectedState);
    assert.equal(
      await evaluate(
        "window.archiveWetlandMap.digestText(window.archiveWetlandMap.fixture.exportText)"
      ),
      evidence.fixture.export.sha256
    );
    assert.equal(
      await evaluate(
        `window.archiveWetlandMap.digestText(${JSON.stringify(
          evidence.runtimeAudit.unicodeDigestVector.text
        )})`
      ),
      evidence.runtimeAudit.unicodeDigestVector.sha256
    );
    await assertDisplayed(opening, viewport);
    editorialLayouts.push(await auditEditorialLayout(viewport));
    const tabs = await tabSequence(14);
    assert.deepEqual(tabs, [
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
    ]);
    tabOrders.push(tabs);
    rovingResults.push(await auditRovingKeyboard(opening));
    await assertDisplayed(opening, viewport);

    const observed = [];
    let positiveState = null;
    const replayStarted = performance.now();
    for (let index = 0; index < scene.actions.length; index += 1) {
      const action = scene.actions[index];
      const remaining = action.at * 1000 - (performance.now() - replayStarted);
      if (remaining > 0) await delay(remaining);
      const actualAt = performance.now() - replayStarted;
      assert.ok(
        actualAt + 5 >= action.at * 1000,
        `action ${index} ran before its authored time`
      );
      timingSkews.push(actualAt - action.at * 1000);
      await replayAction(action);
      if (index === replay.finalPrompt.afterAction) {
        assert.deepEqual(
          await evaluate("window.archiveWetlandMap.snapshot()"),
          opening
        );
        await assertVisible(replay.finalPrompt.selector);
        assert.equal(
          await evaluate(
            `document.querySelector(${JSON.stringify(
              replay.finalPrompt.selector
            )}).textContent`
          ),
          replay.finalPrompt.text
        );
        finalPromptChecks += 1;
      }
      const checkpoint = checkpoints.get(index);
      if (!checkpoint) continue;
      const actual = await evaluate("window.archiveWetlandMap.snapshot()");
      assert.deepEqual(actual, claims.get(checkpoint.claim).expectedState);
      await assertDisplayed(actual, viewport);
      await assertVisible(checkpoint.selector);
      observed.push(checkpoint.claim);
      if (checkpoint.claim === "positive") {
        positiveState = actual;
        const focusPlacement = await evaluate(`(() => {
          const marker = document.querySelector(
            "#record-" + window.archiveWetlandMap.snapshot().focus.toLowerCase()
          );
          const markerBounds = marker.getBoundingClientRect();
          const mapBounds = document.querySelector("#map-window").getBoundingClientRect();
          const center = {
            x: markerBounds.left + markerBounds.width / 2,
            y: markerBounds.top + markerBounds.height / 2
          };
          return {
            center,
            inside:
              center.x >= mapBounds.left &&
              center.x <= mapBounds.right &&
              center.y >= mapBounds.top &&
              center.y <= mapBounds.bottom,
            focused: marker.dataset.focused,
            hidden: marker.hidden
          };
        })()`);
        assert.equal(focusPlacement.inside, true);
        assert.equal(focusPlacement.focused, "true");
        assert.equal(focusPlacement.hidden, false);
        assert.equal(
          await evaluate("window.archiveWetlandMap.rovingRecord()"),
          "WL-016"
        );
      }
      if (checkpoint.claim === "failure") {
        assert.equal(actual.comparison.queryResultCount, null);
        assert.equal(actual.changedCount, 7);
        assert.equal(actual.export.status, "preserved");
        assert.equal(actual.export.digest, evidence.fixture.export.sha256);
        assert.deepEqual(actual.acceptedYears, positiveState.acceptedYears);
        assert.deepEqual(actual.changedIds, positiveState.changedIds);
        assert.equal(actual.filter, positiveState.filter);
        assert.equal(actual.focus, positiveState.focus);
        assert.deepEqual(actual.view, positiveState.view);
        assert.deepEqual(actual.export.ids, positiveState.export.ids);
        assert.equal(actual.export.text, positiveState.export.text);
        assert.equal(actual.export.digest, positiveState.export.digest);
        failureLayouts.push(await auditFailureLayout(viewport));
        lastFailure = actual;
      }
      if (checkpoint.claim === "reset") {
        assert.deepEqual(actual, opening);
        assert.equal(
          await evaluate("window.archiveWetlandMap.rovingRecord()"),
          "WL-001"
        );
        lastReset = actual;
      }
    }
    assert.deepEqual(observed, ["positive", "failure", "reset"]);
    viewportResults.push(viewport.name);
  }
  assert.equal(finalPromptChecks, replay.viewports.length);

  const beforeInvalid = await evaluate("window.archiveWetlandMap.snapshot()");
  await scroll({ selector: "#from-year", block: "start" });
  await click("#from-year");
  await typeText(evidence.runtimeAudit.invalidQuery.input.from);
  await scroll({ selector: "#compare-btn", block: "start" });
  await click("#compare-btn");
  const invalid = await evaluate("window.archiveWetlandMap.snapshot()");
  assert.equal(invalid.comparison.status, "rejected-invalid");
  assert.equal(invalid.comparison.queryResultCount, null);
  assert.deepEqual(invalid.years, beforeInvalid.years);
  assert.deepEqual(invalid.acceptedYears, beforeInvalid.acceptedYears);
  assert.deepEqual(invalid.changedIds, beforeInvalid.changedIds);
  assert.equal(invalid.filter, beforeInvalid.filter);
  assert.equal(invalid.focus, beforeInvalid.focus);
  assert.deepEqual(invalid.view, beforeInvalid.view);
  assert.deepEqual(invalid.export.ids, beforeInvalid.export.ids);
  assert.equal(invalid.export.text, beforeInvalid.export.text);
  assert.equal(invalid.export.digest, beforeInvalid.export.digest);
  assert.equal(invalid.export.status, "preserved");
  await scroll({ selector: "#query-error", block: "start" });
  await assertVisible("#query-error");
  assert.equal(
    await evaluate(`(() => {
      try {
        window.archiveWetlandMap.changedIds(1880, 1885);
        return "not-rejected";
      } catch (error) {
        return error.name;
      }
    })()`),
    "RangeError"
  );
  assert.equal(
    await evaluate(`(() => {
      try {
        window.archiveWetlandMap.digestText(17);
        return "not-rejected";
      } catch (error) {
        return error.name;
      }
    })()`),
    "TypeError"
  );
  assert.equal(
    await evaluate(`(() => {
      try {
        window.archiveWetlandMap.reduce(
          window.archiveWetlandMap.initialState(),
          { type: "UNKNOWN" }
        );
        return "not-rejected";
      } catch (error) {
        return error.name;
      }
    })()`),
    "RangeError"
  );
  await scroll({ selector: "#restore-btn", block: "start" });
  await click("#restore-btn");
  assert.deepEqual(
    await evaluate("window.archiveWetlandMap.snapshot()"),
    lastReset
  );

  await scroll({ selector: "#record-wl-024", block: "center" });
  const beforeTakeover = await evaluate(`(() => {
    const marker = document.querySelector("#record-wl-024");
    const bounds = marker.getBoundingClientRect();
    return {
      center: { x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2 },
      mapTransform: getComputedStyle(document.querySelector("#map-sheet")).transform
    };
  })()`);
  await click("#record-wl-024");
  await scroll({ selector: "#zoom-out-btn", block: "start" });
  await click("#zoom-out-btn");
  await click("#pan-north-btn");
  await delay(250);
  const takeover = await evaluate("window.archiveWetlandMap.snapshot()");
  const takeoverDom = await evaluate(`(() => {
    const marker = document.querySelector("#record-wl-024");
    const bounds = marker.getBoundingClientRect();
    const matrix = new DOMMatrixReadOnly(
      getComputedStyle(document.querySelector("#map-sheet")).transform
    );
    return {
      center: { x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2 },
      matrix: { a: matrix.a, d: matrix.d, e: matrix.e, f: matrix.f },
      focused: marker.dataset.focused,
      pressed: marker.getAttribute("aria-pressed"),
      detailHidden: document.querySelector("#record-detail").hidden,
      detailTitle: document.querySelector("#record-detail-title").textContent,
      mapTransform: getComputedStyle(document.querySelector("#map-sheet")).transform
    };
  })()`);
  assert.equal(takeover.focus, "WL-024");
  assert.equal(takeover.visibleCount, 24);
  assert.deepEqual(takeover.view, { panX: 0, panY: -40, zoom: 0.75 });
  assert.deepEqual(takeoverDom.matrix, { a: 0.75, d: 0.75, e: 0, f: -40 });
  assert.equal(takeoverDom.focused, "true");
  assert.equal(takeoverDom.pressed, "true");
  assert.equal(takeoverDom.detailHidden, false);
  assert.equal(takeoverDom.detailTitle, "WL-024 · Zephyr Sedge");
  assert.notEqual(takeoverDom.mapTransform, beforeTakeover.mapTransform);
  assert.ok(
    Math.hypot(
      takeoverDom.center.x - beforeTakeover.center.x,
      takeoverDom.center.y - beforeTakeover.center.y
    ) > 5,
    "takeover controls did not move the visible map record"
  );

  await delay(150);
  assert.deepEqual(externalRequests, []);
  assert.deepEqual(blockedExternalRequests, []);
  assert.deepEqual(browserErrors, []);
  report = {
    browser: browserVersion.product,
    actionCount: scene.actions.length,
    manifestActivationChecks: scene.actions.filter(action =>
      ["click", "type"].includes(action.do)
    ).length,
    checkpointVisibilityChecks: replay.checkpoints.length * replay.viewports.length,
    exactTiming: true,
    maxTimingSkewMs: Math.round(Math.max(...timingSkews)),
    viewports: viewportResults,
    tabOrder: tabOrders[0],
    rovingFocus: rovingResults[0],
    mobileLayout: {
      documentWidth: editorialLayouts[1].documentWidth,
      clientWidth: editorialLayouts[1].clientWidth,
      minimumTextPixels: 12,
      exportPixels: editorialLayouts[1].exportPixels,
      digestPixels: editorialLayouts[1].digestPixels,
      overflowClipped: false,
    },
    failureLayout: failureLayouts[1],
    finalPromptChecks,
    recordCount: lastReset.totalRecords,
    changedCount: lastReset.changedCount,
    changedIds: lastReset.changedIds,
    digest: lastReset.export.digest,
    failureStatus: lastFailure.comparison.status,
    failureResultCount: lastFailure.comparison.queryResultCount,
    failureExportStatus: lastFailure.export.status,
    failureAcceptedYears: lastFailure.acceptedYears,
    invalidStatus: invalid.comparison.status,
    resetVisibleCount: lastReset.visibleCount,
    resetFocus: lastReset.focus,
    resetView: lastReset.view,
    takeover: {
      focus: takeover.focus,
      visibleCount: takeover.visibleCount,
      view: takeover.view,
      transform: takeoverDom.matrix,
    },
    networkBlocked: true,
    externalNetworkRequests: externalRequests.length,
    blockedExternalRequests: blockedExternalRequests.length,
    browserErrors: browserErrors.length,
  };
} catch (error) {
  runError = error;
}

async function pathExists(path) {
  try {
    await access(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function cleanupBrowser() {
  const errors = [];
  if (cdp) {
    try {
      await cdp.command("Browser.close", {}, 5000);
    } catch (error) {
      if (browserRunning()) {
        errors.push(new Error(`Browser.close failed: ${errorText(error)}`));
      }
    }
    cdp.close();
  }
  let exitDeadline = Date.now() + 5000;
  while (browserRunning() && Date.now() < exitDeadline) {
    await delay(75);
  }
  if (browserRunning()) {
    if (!browser.kill()) {
      errors.push(new Error("browser process could not be terminated"));
    }
    exitDeadline = Date.now() + 5000;
    while (browserRunning() && Date.now() < exitDeadline) {
      await delay(75);
    }
  }
  if (browserRunning()) {
    errors.push(new Error("browser process remained alive after cleanup"));
  }
  try {
    await rm(profilePath, {
      recursive: true,
      force: true,
      maxRetries: 12,
      retryDelay: 150,
    });
  } catch (error) {
    errors.push(new Error(`profile removal failed: ${errorText(error)}`));
  }
  let profileRemoved = false;
  try {
    profileRemoved = !(await pathExists(profilePath));
  } catch (error) {
    errors.push(new Error(`profile verification failed: ${errorText(error)}`));
  }
  if (!profileRemoved) {
    errors.push(new Error(`browser profile still exists: ${profilePath}`));
  }
  return {
    browserExited: !browserRunning(),
    profileRemoved,
    errors,
  };
}

const cleanup = await cleanupBrowser();
if (runError || cleanup.errors.length) {
  throw new AggregateError(
    [runError, ...cleanup.errors].filter(Boolean),
    "wetland browser verification failed"
  );
}
report.cleanup = {
  browserExited: cleanup.browserExited,
  profileRemoved: cleanup.profileRemoved,
};
console.log(JSON.stringify(report));
