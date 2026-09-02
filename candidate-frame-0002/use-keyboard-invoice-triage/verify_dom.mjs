import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFile, rm } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const [edgePath, appPath, evidencePath, profilePath] = process.argv.slice(2);
if (!edgePath || !appPath || !evidencePath || !profilePath) {
  throw new Error(
    "usage: node verify_dom.mjs <edge> <app> <evidence> <profile>"
  );
}

await rm(profilePath, { recursive: true, force: true });
const browser = spawn(edgePath, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--remote-debugging-port=0",
  `--user-data-dir=${profilePath}`,
  "about:blank",
], { stdio: "ignore" });

const delay = milliseconds =>
  new Promise(resolve => setTimeout(resolve, milliseconds));

async function activePort(timeout = 15000) {
  const path = `${profilePath}\\DevToolsActivePort`;
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      const [port] = (await readFile(path, "utf8")).trim().split(/\r?\n/);
      if (port) return port;
    } catch {}
    await delay(75);
  }
  throw new Error("Edge did not publish DevToolsActivePort");
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
    await new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) || [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  command(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
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

const keyNames = {
  ArrowDown: { key: "ArrowDown", code: "ArrowDown" },
  Enter: { key: "Enter", code: "Enter" },
  Tab: { key: "Tab", code: "Tab" },
  Minus: { key: "-", code: "Minus" },
  Digit1: { key: "1", code: "Digit1" },
  Period: { key: ".", code: "Period" },
  Digit0: { key: "0", code: "Digit0" },
};

async function press(code) {
  const key = keyNames[code];
  if (!key) throw new Error(`unsupported verifier key ${code}`);
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: key.key,
    code: key.code,
  });
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: key.key,
    code: key.code,
  });
  await delay(35);
}

async function click(selector) {
  const encoded = JSON.stringify(selector);
  await evaluate(`(() => {
    const element = document.querySelector(${encoded});
    if (!element) throw new Error("missing selector " + ${encoded});
    if (element.disabled) throw new Error("disabled selector " + ${encoded});
    const box = element.getBoundingClientRect();
    if (!box.width || !box.height) throw new Error("hidden selector " + ${encoded});
    element.click();
    return true;
  })()`);
  await delay(35);
}

async function replayKey(action) {
  const fallback = keyNames[action.code];
  const key = action.key || fallback?.key || action.code;
  const code = action.code;
  await evaluate(`(() => {
    const options = {
      code: ${JSON.stringify(code)},
      key: ${JSON.stringify(key)},
      bubbles: true,
      cancelable: true,
      composed: true
    };
    document.dispatchEvent(new KeyboardEvent("keydown", options));
    document.dispatchEvent(new KeyboardEvent("keyup", options));
    return true;
  })()`);
  await delay(35);
}

try {
  const port = await activePort();
  const targets = await readJson(`http://127.0.0.1:${port}/json/list`);
  const page = targets.find(target => target.type === "page");
  assert.ok(page?.webSocketDebuggerUrl, "Edge exposed no page target");
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
  const claims = new Map(evidence.claims.map(claim => [claim.id, claim]));
  const appUrl = pathToFileURL(appPath).href;
  await navigate(appUrl);

  const opening = await evaluate("window.invoiceTriage.snapshot()");
  assert.deepEqual(opening, claims.get("reset").expectedState);
  assert.equal(await evaluate("document.activeElement.id"), "invoice-syn-001");
  assert.equal(await evaluate("document.querySelector('#export-button').disabled"), true);

  for (const code of [
    "Enter",
    "ArrowDown",
    "Enter",
    "ArrowDown",
    "Enter",
    "ArrowDown",
    "Enter",
    "Tab",
    "Enter",
  ]) {
    await press(code);
  }
  const positive = await evaluate("window.invoiceTriage.snapshot()");
  assert.deepEqual(positive, claims.get("positive").expectedState);
  assert.equal(await evaluate("document.activeElement.id"), "export-button");
  assert.equal(
    await evaluate("document.querySelector('#export-json').textContent"),
    JSON.stringify(positive.exported)
  );

  await click("#invoice-syn-003");
  await click("#amount-input");
  for (const code of ["Minus", "Digit1", "Period", "Digit0", "Digit0", "Enter"]) {
    await press(code);
  }
  const rejected = await evaluate("window.invoiceTriage.snapshot()");
  assert.deepEqual(rejected, claims.get("rejected").expectedState);
  assert.equal(await evaluate("document.activeElement.id"), "amount-input");
  assert.equal(await evaluate("document.querySelector('#export-button').disabled"), true);
  assert.equal(
    await evaluate("document.querySelector('#amount-input').getAttribute('aria-invalid')"),
    "true"
  );
  assert.equal(await evaluate("document.querySelector('#validation-error').hidden"), false);

  await click("#restore-button");
  assert.equal(await evaluate("document.activeElement.id"), "confirm-restore-btn");
  assert.equal(
    await evaluate("document.querySelector('#restore-confirmation').hidden"),
    false
  );
  await press("Enter");
  const reset = await evaluate("window.invoiceTriage.snapshot()");
  assert.deepEqual(reset, claims.get("reset").expectedState);
  assert.equal(await evaluate("document.activeElement.id"), "invoice-syn-001");

  await navigate(appUrl);
  const positiveActions = claims.get("positive").actions;
  for (const action of positiveActions) {
    if (action.do === "click") await click(action.selector);
    else await replayKey(action);
  }
  assert.deepEqual(
    await evaluate("window.invoiceTriage.snapshot()"),
    claims.get("positive").expectedState,
    "scripted positive replay"
  );
  const rejectionTail = claims.get("rejected").actions.slice(positiveActions.length);
  for (const action of rejectionTail) {
    if (action.do === "click") await click(action.selector);
    else await replayKey(action);
  }
  assert.deepEqual(
    await evaluate("window.invoiceTriage.snapshot()"),
    claims.get("rejected").expectedState,
    "scripted rejected replay"
  );
  for (const action of claims.get("reset").actions) {
    if (action.do === "click") await click(action.selector);
    else await replayKey(action);
  }
  assert.deepEqual(
    await evaluate("window.invoiceTriage.snapshot()"),
    claims.get("reset").expectedState,
    "scripted exact reset"
  );
  assert.deepEqual(browserErrors, []);

  console.log(JSON.stringify({
    fixtureTotal: opening.fixtureTotal,
    exportedAcceptedTotal: positive.exported.acceptedTotal,
    negativeAmount: rejected.editor.amountText,
    exportDisabledOnError: !rejected.canExport,
    resetFocus: reset.focus,
    scriptedReplay: "positive-rejected-reset",
    browserErrors: browserErrors.length,
  }));
} finally {
  if (cdp) cdp.close();
  browser.kill();
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
