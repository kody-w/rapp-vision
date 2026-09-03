import assert from "node:assert/strict";
import { spawn } from "node:child_process";
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
  app: join(ROOT, "apps", "ecosystem-island-threshold.html"),
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
await rm(profilePath, { recursive: true, force: true });

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

async function activePort(timeout = 45000) {
  const deadline = Date.now() + timeout;
  const activePortPath = join(profilePath, "DevToolsActivePort");
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
    } catch {}
    await delay(75);
  }
  throw new Error(
    `browser did not publish an OS-reserved DevTools port within ${timeout} ms`
  );
}

async function readJson(url, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (browser.exitCode !== null) {
      throw new Error(`browser exited while waiting for ${url}: ${browser.exitCode}`);
    }
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
    if (browser.exitCode !== null) {
      throw new Error(`browser exited during condition wait: ${browser.exitCode}`);
    }
    try {
      if (await evaluate(expression)) return;
    } catch {}
    await delay(60);
  }
  throw new Error(`timed out waiting for browser condition: ${expression}`);
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
  await evaluate(`(() => {
    const element = document.querySelector(${encoded});
    if (!element) throw new Error("missing selector " + ${encoded});
    if (element.disabled || element.getAttribute("aria-disabled") === "true") {
      throw new Error("disabled selector " + ${encoded});
    }
    const bounds = element.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) {
      throw new Error("hidden selector " + ${encoded});
    }
    element.focus({ preventScroll: true });
    element.click();
    return true;
  })()`);
  await delay(45);
}

async function scrollTo(selector, action) {
  assert.match(selector, /^#[A-Za-z][A-Za-z0-9_-]*$/);
  assert.equal(action.block, "start");
  assert.equal(action.behavior, "auto");
  const encoded = JSON.stringify(selector);
  await evaluate(`(() => {
    const element = document.querySelector(${encoded});
    if (!element) throw new Error("missing selector " + ${encoded});
    element.scrollIntoView({ block: "start", inline: "nearest", behavior: "auto" });
    return true;
  })()`);
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

  await setViewport(1120);
  await navigate(pathToFileURL(appPath).href);
  const opening = await evaluate("window.islandLab.summary()");
  assert.deepEqual(opening, claims.get("reset").expectedState);
  assert.deepEqual(await evaluate("window.islandLab.snapshot().trace"), []);
  assert.equal(await evaluate("document.querySelector('#run-btn').disabled"), true);
  assert.equal(await evaluate("document.querySelector('#hidden-trace-label').hidden"), false);
  await assertLegible(
    ["#predict-band-btn", "#predict-collapse-btn", "#run-btn", "#reset-btn"],
    1120
  );
  await assertLegible(
    ["#predict-band-btn", "#predict-collapse-btn", "#run-btn", "#reset-btn"],
    390
  );
  await setViewport(1120);

  const checkpoints = new Map(
    replay.checkpoints.map(checkpoint => [checkpoint.afterAction, checkpoint])
  );
  const observed = [];
  const replayStarted = Date.now();
  for (let index = 0; index < scene.actions.length; index += 1) {
    const action = scene.actions[index];
    const wait = replayStarted + action.at * 1000 - Date.now();
    if (wait > 0) await delay(wait);
    await replayAction(action);
    const checkpoint = checkpoints.get(index);
    if (!checkpoint) continue;
    const expected = claims.get(checkpoint.claim).expectedState;
    await waitFor(
      `window.islandLab.summary().status === ${JSON.stringify(expected.status)}`
    );
    const actual = await evaluate("window.islandLab.summary()");
    assert.deepEqual(actual, expected, checkpoint.claim);
    const visible = await evaluate(`(() => {
      const element = document.querySelector(${JSON.stringify(checkpoint.selector)});
      const style = getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return {
        hidden: element.hidden,
        display: style.display,
        visibility: style.visibility,
        width: box.width,
        height: box.height,
        text: element.textContent.replace(/\\s+/g, " ").trim()
      };
    })()`);
    assert.equal(visible.hidden, false);
    assert.notEqual(visible.display, "none");
    assert.notEqual(visible.visibility, "hidden");
    assert.ok(visible.width > 100 && visible.height > 20);

    if (checkpoint.claim === "stable") {
      assert.match(visible.text, /112/);
      assert.match(visible.text, /80.+120/);
      assert.deepEqual(
        await evaluate("window.islandLab.snapshot().trace"),
        fixtures.get("stable-band").series
      );
      assert.equal(
        await evaluate("document.querySelector('#predict-band-btn').getAttribute('aria-pressed')"),
        "true"
      );
      assert.ok(
        (await evaluate("document.querySelector('#trace-path').getAttribute('points')")).length > 100
      );
      await assertLegible(["#stable-result", "#inspect-trace-btn"], 390);
      await setViewport(1120);
    } else if (checkpoint.claim === "collapse") {
      assert.match(visible.text, /tick 134/i);
      assert.match(visible.text, /ends at 8/i);
      assert.deepEqual(
        await evaluate("window.islandLab.snapshot().trace"),
        fixtures.get("collapse").series
      );
      assert.equal(await evaluate("document.querySelector('#crossing-line').hidden"), false);
      assert.equal(await evaluate("document.querySelector('#crossing-dot').hidden"), false);
      assert.equal(
        await evaluate("document.querySelector('#speed-2-btn').getAttribute('aria-pressed')"),
        "true"
      );
      await assertLegible(["#collapse-result", "#reset-btn"], 390);
      await setViewport(1120);
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
        await evaluate("document.querySelector('#predict-collapse-btn').getAttribute('aria-pressed')"),
        "false"
      );
      await assertLegible(["#reset-proof", "#predict-band-btn"], 390);
      await setViewport(1120);
    }
    observed.push(checkpoint.claim);
  }

  assert.deepEqual(observed, ["stable", "collapse", "reset"]);
  assert.deepEqual(browserErrors, []);
  assert.deepEqual(
    networkRequests.filter(url => /^https?:/i.test(url)),
    [],
    "standalone app made an external network request"
  );

  console.log(JSON.stringify({
    browser: browserVersion.product,
    actionCount: scene.actions.length,
    checkpoints: observed,
    stableFinal: fixtures.get("stable-band").final.population,
    collapseCrossingTick: fixtures.get("collapse").collapseCrossingTick,
    collapseFinal: fixtures.get("collapse").final.population,
    resetTraceLength: opening.traceLength,
    responsiveWidth: 390,
    browserErrors: browserErrors.length,
    externalRequests: 0,
  }));
} finally {
  if (cdp) cdp.close();
  if (browser.exitCode === null) browser.kill();
  await Promise.race([
    new Promise(resolveExit => browser.once("exit", resolveExit)),
    delay(2000),
  ]);
  try {
    await rm(profilePath, {
      recursive: true,
      force: true,
      maxRetries: 12,
      retryDelay: 150,
    });
  } catch {}
}
