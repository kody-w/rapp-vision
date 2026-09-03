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
  app: join(ROOT, "apps", "use-keyboard-invoice-triage.html"),
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
    const programFiles = [
      process.env.ProgramFiles,
      process.env["ProgramFiles(x86)"],
    ].filter(Boolean);
    const local = process.env.LOCALAPPDATA;
    const candidates = [];
    for (const root of programFiles) {
      candidates.push(
        join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
        join(root, "Google", "Chrome", "Application", "chrome.exe"),
        join(root, "Chromium", "Application", "chrome.exe"),
        join(root, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
      );
    }
    if (local) {
      candidates.push(
        join(local, "Microsoft", "Edge", "Application", "msedge.exe"),
        join(local, "Google", "Chrome", "Application", "chrome.exe"),
        join(local, "Chromium", "Application", "chrome.exe"),
        join(
          local,
          "BraveSoftware",
          "Brave-Browser",
          "Application",
          "brave.exe"
        )
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
    "Chromium-family browser not found via environment, PATH, or common locations"
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
  const server = createServer();
  server.once("error", rejectPort);
  server.listen(0, "127.0.0.1", () => {
    const address = server.address();
    server.close(error => {
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

async function activePort(timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (launchError) throw launchError;
    if (browser.exitCode !== null) {
      throw new Error(`browser exited before DevTools was ready: ${browser.exitCode}`);
    }
    try {
      const response = await fetch(
        `http://127.0.0.1:${debugPort}/json/version`
      );
      if (response.ok) return String(debugPort);
    } catch {}
    await delay(75);
  }
  throw new Error("browser did not publish DevToolsActivePort");
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
    this.socket.close();
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

async function navigate(url) {
  await cdp.command("Page.navigate", { url });
  await waitFor(
    "document.readyState === 'complete' && Boolean(window.invoiceTriage)"
  );
}

function keyFromCode(code) {
  if (/^Key[A-Z]$/.test(code)) return code.slice(-1).toLowerCase();
  if (/^Digit\d$/.test(code)) return code.slice(-1);
  if (/^Shift(Left|Right)$/.test(code)) return "Shift";
  if (code === "Space") return " ";
  return code;
}

let modifiers = 0;
const SHIFT_MODIFIER = 8;

async function dispatchKey(type, action) {
  const code = action.code;
  const key = action.key || keyFromCode(code);
  const isShift = /^Shift(Left|Right)$/.test(code);
  if (type === "keyDown" && isShift) modifiers |= SHIFT_MODIFIER;
  const eventModifiers =
    type === "keyUp" && isShift ? modifiers & ~SHIFT_MODIFIER : modifiers;
  await cdp.command("Input.dispatchKeyEvent", {
    type,
    code,
    key,
    modifiers: eventModifiers,
  });
  if (type === "keyUp" && isShift) modifiers &= ~SHIFT_MODIFIER;
}

async function replayAction(action) {
  assert.ok(
    !("from" in action) && !("to" in action),
    "invoice replay actions cannot target pointer coordinates"
  );
  if (action.do === "scroll") {
    assert.equal(typeof action.selector, "string", "scroll action requires selector");
    assert.ok(action.selector.startsWith("#"), "scroll selector must be a stable id");
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
  } else if (action.do === "type") {
    assert.ok(!("selector" in action), "typing follows the declared focus path");
    assert.equal(typeof action.text, "string", "type action requires text");
    await cdp.command("Input.insertText", { text: action.text });
  } else if (action.do === "keydown") {
    assert.ok(!("selector" in action), "keydown follows the declared focus path");
    await dispatchKey("keyDown", action);
  } else if (action.do === "keyup") {
    assert.ok(!("selector" in action), "keyup follows the declared focus path");
    await dispatchKey("keyUp", action);
  } else if (action.do === "key") {
    assert.ok(!("selector" in action), "key action follows the declared focus path");
    await dispatchKey("keyDown", action);
    await dispatchKey("keyUp", action);
  } else {
    throw new Error(`unsupported invoice manifest action: ${action.do}`);
  }
  await delay(45);
}

try {
  const port = await activePort();
  const targets = await readJson(`http://127.0.0.1:${port}/json/list`);
  const page = targets.find(target => target.type === "page");
  assert.ok(page?.webSocketDebuggerUrl, "browser exposed no page target");
  cdp = new Cdp(page.webSocketDebuggerUrl);
  await cdp.connect();
  await Promise.all([
    cdp.command("Page.enable"),
    cdp.command("Runtime.enable"),
    cdp.command("Log.enable"),
    cdp.command("Emulation.setDeviceMetricsOverride", {
      width: 1120,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    }),
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
  assert.equal(scene.app, "apps/use-keyboard-invoice-triage.html");
  assert.equal(scene.actions.length, replay.actionCount);
  assert.equal(replay.focusAfterEachAction.length, scene.actions.length);
  const actionKinds = [...new Set(scene.actions.map(action => action.do))].sort();
  assert.deepEqual(actionKinds, [...replay.allowedActions].sort());
  assert.deepEqual(
    scene.actions
      .filter(action => action.do === replay.framingAction)
      .map(action => action.selector),
    replay.scrollSelectors
  );
  assert.deepEqual(
    [...new Set(scene.actions
      .filter(action => action.do !== replay.framingAction)
      .map(action => action.do))].sort(),
    [...replay.activationActions].sort()
  );
  for (const action of scene.actions) {
    assert.ok(replay.allowedActions.includes(action.do));
    assert.ok(action.at >= 0 && action.at < scene.dur);
    if (action.do === "scroll") {
      assert.match(action.selector, /^#[A-Za-z][A-Za-z0-9_-]*$/);
      assert.equal(action.block, "start");
      assert.equal(action.behavior, "auto");
    }
  }

  const appUrl = pathToFileURL(appPath).href;
  await navigate(appUrl);
  const opening = await evaluate("window.invoiceTriage.snapshot()");
  assert.deepEqual(opening, claims.get("reset").expectedState);
  assert.deepEqual(
    await evaluate("[...window.invoiceTriage.focusOrder]"),
    replay.declaredFocusOrder
  );
  assert.equal(await evaluate("document.activeElement.id"), "invoice-syn-001");
  assert.equal(
    await evaluate("document.querySelector('#export-button').disabled"),
    true
  );

  const checkpoints = new Map(
    replay.checkpoints.map(checkpoint => [
      checkpoint.afterAction,
      checkpoint.claim,
    ])
  );
  const observedCheckpoints = [];
  let positive;
  let rejected;
  let reset;

  for (let index = 0; index < scene.actions.length; index += 1) {
    await replayAction(scene.actions[index]);
    const activeElement = await evaluate("document.activeElement.id");
    const snapshot = await evaluate("window.invoiceTriage.snapshot()");
    assert.equal(activeElement, replay.focusAfterEachAction[index]);
    assert.equal(snapshot.focus, activeElement);

    const claimId = checkpoints.get(index);
    if (!claimId) continue;
    assert.deepEqual(snapshot, claims.get(claimId).expectedState);
    observedCheckpoints.push(claimId);
    if (claimId === "positive") {
      positive = snapshot;
      assert.equal(snapshot.acceptedTotal, "196.25");
      assert.equal(snapshot.exported.acceptedTotal, "196.25");
      assert.equal(activeElement, "export-button");
      assert.equal(
        await evaluate("document.querySelector('#export-json').textContent"),
        JSON.stringify(snapshot.exported)
      );
    } else if (claimId === "rejected") {
      rejected = snapshot;
      assert.equal(activeElement, "amount-input");
      assert.equal(snapshot.editor.amountText, "-1.00");
      assert.equal(snapshot.error, "Amount must be zero or greater.");
      assert.equal(
        await evaluate("document.querySelector('#export-button').disabled"),
        true
      );
      assert.equal(
        await evaluate(
          "document.querySelector('#amount-input').getAttribute('aria-invalid')"
        ),
        "true"
      );
      assert.equal(
        await evaluate("document.querySelector('#validation-error').hidden"),
        false
      );
    } else if (claimId === "reset") {
      reset = snapshot;
      assert.deepEqual(snapshot, opening);
      assert.equal(activeElement, "invoice-syn-001");
      assert.equal(
        await evaluate("document.querySelector('#restore-confirmation').hidden"),
        true
      );
    }
  }

  assert.deepEqual(observedCheckpoints, ["positive", "rejected", "reset"]);
  assert.ok(positive && rejected && reset);
  assert.deepEqual(browserErrors, []);

  console.log(
    JSON.stringify({
      actionCount: scene.actions.length,
      fixtureTotal: opening.fixtureTotal,
      acceptedTotal: positive.exported.acceptedTotal,
      negativeAmount: rejected.editor.amountText,
      errorFocus: rejected.focus,
      exportDisabledOnError: !rejected.canExport,
      resetFocus: reset.focus,
      checkpoints: observedCheckpoints,
      browserErrors: browserErrors.length,
    })
  );
} finally {
  if (cdp) cdp.close();
  if (browser.exitCode === null) browser.kill();
  await delay(600);
  try {
    await rm(profilePath, {
      recursive: true,
      force: true,
      maxRetries: 12,
      retryDelay: 150,
    });
  } catch {}
}
