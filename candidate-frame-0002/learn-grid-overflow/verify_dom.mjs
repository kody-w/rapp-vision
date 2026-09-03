import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [browserPath, appPath, evidencePath, profilePath] = process.argv.slice(2);
if (!browserPath || !appPath || !evidencePath || !profilePath) {
  throw new Error(
    "usage: node verify_dom.mjs <edge-or-chrome> <app> <evidence> <profile>"
  );
}

await rm(profilePath, { recursive: true, force: true });
const browser = spawn(browserPath, [
  "--headless=new",
  "--disable-gpu",
  "--disable-dev-shm-usage",
  "--no-sandbox",
  "--no-first-run",
  "--no-default-browser-check",
  "--remote-debugging-port=0",
  `--user-data-dir=${profilePath}`,
  "about:blank",
], { stdio: "ignore" });

const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function waitForActivePort(timeout = 15000) {
  const activePortPath = join(profilePath, "DevToolsActivePort");
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      const [port, browserId] = (await readFile(activePortPath, "utf8")).trim().split(/\r?\n/);
      if (port && browserId) return { port, browserId };
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
      result.exceptionDetails.exception?.description || "browser evaluation failed"
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
    "document.readyState === 'complete' && Boolean(window.gridOverflowLesson)"
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
    if (!bounds.width || !bounds.height) throw new Error("hidden selector " + ${encoded});
    element.click();
    return true;
  })()`);
  await delay(40);
}

async function setViewport(width, height = 900) {
  await cdp.command("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await delay(50);
}

async function assertDisplayed(snapshot) {
  const displayed = await evaluate(`(() => {
    const preview = document.querySelector("#preview-viewport");
    const payload = document.querySelector("#payload");
    const rail = document.querySelector("#token-rail");
    const itemStyle = getComputedStyle(payload);
    return {
      viewport: document.querySelector("#viewport-value").textContent,
      scrollWidth: document.querySelector("#scroll-width").textContent,
      clientWidth: document.querySelector("#client-width").textContent,
      comparison: document.querySelector("#comparison").textContent,
      source: document.querySelector("#css-source").textContent,
      token: document.querySelector("#fixture-token").textContent,
      domScrollWidth: preview.scrollWidth,
      domClientWidth: preview.clientWidth,
      domX: Math.round(preview.scrollLeft),
      cause: {
        itemMinWidth: itemStyle.minWidth,
        itemOverflow: itemStyle.overflow,
        payloadWidth: payload.offsetWidth,
        railWidth: rail.offsetWidth
      }
    };
  })()`);
  const operator = snapshot.verdict === "overflow" ? ">" : "=";
  assert.equal(displayed.viewport, `${snapshot.viewport} px`);
  assert.equal(displayed.scrollWidth, `${snapshot.scrollWidth} px`);
  assert.equal(displayed.clientWidth, `${snapshot.clientWidth} px`);
  assert.equal(
    displayed.comparison,
    `${snapshot.scrollWidth} ${operator} ${snapshot.clientWidth} / x ${snapshot.x}`
  );
  assert.equal(displayed.source, snapshot.cssText);
  assert.equal(displayed.token, snapshot.token);
  assert.equal(displayed.domScrollWidth, snapshot.scrollWidth);
  assert.equal(displayed.domClientWidth, snapshot.clientWidth);
  assert.equal(displayed.domX, snapshot.x);
  assert.deepEqual(displayed.cause, snapshot.cause);
}

try {
  const { port } = await waitForActivePort();
  const targets = await readJson(`http://127.0.0.1:${port}/json/list`);
  const pageTarget = targets.find(target => target.type === "page");
  assert.ok(pageTarget?.webSocketDebuggerUrl, "browser exposed no page target");
  cdp = new Cdp(pageTarget.webSocketDebuggerUrl);
  await cdp.connect();
  const browserVersion = await cdp.command("Browser.getVersion");
  assert.match(
    browserVersion.product,
    /(Chrome|Chromium|Edge|Edg)\//,
    "verification requires an Edge/Chrome-family browser"
  );
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
  const claims = new Map(
    evidence.publications[0].claims.map(claim => [claim.id, claim])
  );
  const appUrl = pathToFileURL(appPath).href;

  await navigate(appUrl);
  const opening = await evaluate("window.gridOverflowLesson.snapshot()");
  assert.deepEqual(opening, claims.get("reset").expectedState);
  assert.ok(opening.scrollWidth > opening.clientWidth);
  assert.deepEqual(opening.cause, {
    itemMinWidth: "auto",
    itemOverflow: "clip",
    payloadWidth: 480,
    railWidth: 480,
  });
  await assertDisplayed(opening);
  await setViewport(320);
  assert.equal(
    await evaluate(
      "document.documentElement.scrollWidth === document.documentElement.clientWidth"
    ),
    true,
    "lesson shell overflows the real 320 px browser viewport"
  );
  assert.deepEqual(
    await evaluate("window.gridOverflowLesson.snapshot()"),
    opening,
    "responsive presentation changed the simulator contract"
  );
  await setViewport(1120);

  for (const claimId of ["positive", "failure"]) {
    await navigate(appUrl);
    const claim = claims.get(claimId);
    for (const action of claim.actions) await click(action.selector);
    const actual = await evaluate("window.gridOverflowLesson.snapshot()");
    assert.deepEqual(actual, claim.expectedState, claimId);
    await assertDisplayed(actual);
    if (claimId === "positive") {
      assert.equal(actual.checks["320"].scrollWidth, actual.checks["320"].clientWidth);
      assert.equal(actual.checks["1280"].scrollWidth, actual.checks["1280"].clientWidth);
      assert.deepEqual(actual.checks["320"].cause, {
        itemMinWidth: "0px",
        itemOverflow: "clip",
        payloadWidth: 174,
        railWidth: 480,
      });
      assert.deepEqual(actual.checks["1280"].cause, {
        itemMinWidth: "0px",
        itemOverflow: "clip",
        payloadWidth: 1134,
        railWidth: 480,
      });
      const before = claims.get("reset").expectedState.cssText.split("\n");
      const after = actual.cssText.split("\n");
      assert.equal(before.length, after.length);
      const changed = before
        .map((line, index) => ({ before: line, after: after[index] }))
        .filter(pair => pair.before !== pair.after);
      assert.deepEqual(changed, [
        { before: "  min-width: auto;", after: "  min-width: 0;" },
      ]);
    } else {
      assert.ok(actual.x > 0);
      assert.ok(actual.scrollWidth > actual.clientWidth);
      assert.equal(actual.cause.itemMinWidth, "auto");
      assert.equal(actual.cause.payloadWidth, 480);
    }
  }

  const reset = claims.get("reset");
  for (const action of reset.actions) await click(action.selector);
  const resetState = await evaluate("window.gridOverflowLesson.snapshot()");
  assert.deepEqual(resetState, reset.expectedState, "reset");
  await assertDisplayed(resetState);
  assert.equal(resetState.x, 0);
  assert.deepEqual(browserErrors, []);

  console.log(JSON.stringify({
    browser: browserVersion.product,
    opening: `${opening.scrollWidth}>${opening.clientWidth}`,
    fixed320: `${claims.get("positive").expectedState.checks["320"].scrollWidth}=${claims.get("positive").expectedState.checks["320"].clientWidth}`,
    fixed1280: `${claims.get("positive").expectedState.checks["1280"].scrollWidth}=${claims.get("positive").expectedState.checks["1280"].clientWidth}`,
    sourceChanges: 1,
    fixedPayload320: claims.get("positive").expectedState.checks["320"].cause.payloadWidth,
    restoredX: claims.get("failure").expectedState.x,
    resetX: resetState.x,
    browserErrors: browserErrors.length,
  }));
} finally {
  if (cdp) cdp.close();
  browser.kill();
  await delay(750);
  try {
    await rm(profilePath, {
      recursive: true,
      force: true,
      maxRetries: 12,
      retryDelay: 150,
    });
  } catch {}
}
