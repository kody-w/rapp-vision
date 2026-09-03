import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFile, rm, stat } from "node:fs/promises";
import { createServer as createHttpServer } from "node:http";
import { createServer as createNetServer } from "node:net";
import { extname, resolve, sep } from "node:path";

const [browserExecutable, rootArgument, profileArgument] = process.argv.slice(2);
if (!browserExecutable || !rootArgument || !profileArgument) {
  throw new Error(
    "usage: node paired_player_takeover_browser.mjs <browser> <root> <profile>",
  );
}

const ROOT = resolve(rootArgument);
const profilePath = resolve(profileArgument);
const registry = {
  schema: "rapp-vision-network/1.0",
  id: "takeover-test",
  name: "Takeover test",
  channels: [
    {
      id: "use-keyboard-invoice-triage",
      url: "candidate-frame-0002/use-keyboard-invoice-triage/channel.json",
      contract: "rapp-vision-channel/2.0",
    },
    {
      id: "candidate-frame-0002-04",
      url: "candidate-frame-0002/learn-grid-overflow/channel.json",
      contract: "rapp-vision-channel/2.0",
    },
  ],
};
const types = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".mp4", "video/mp4"],
  [".svg", "image/svg+xml"],
  [".webm", "video/webm"],
]);

const httpServer = createHttpServer(async (request, response) => {
  try {
    const requestUrl = new URL(request.url || "/", "http://127.0.0.1");
    if (requestUrl.pathname === "/channels.json") {
      const body = Buffer.from(JSON.stringify(registry));
      response.writeHead(200, {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": body.length,
        "Cache-Control": "no-store",
      });
      response.end(request.method === "HEAD" ? undefined : body);
      return;
    }

    const pathname =
      requestUrl.pathname === "/" ? "/index.html" : requestUrl.pathname;
    const relative = decodeURIComponent(pathname)
      .replace(/^[/\\]+/, "")
      .replaceAll("/", sep);
    const filePath = resolve(ROOT, relative);
    if (filePath !== ROOT && !filePath.startsWith(ROOT + sep)) {
      response.writeHead(403).end();
      return;
    }
    const fileStat = await stat(filePath);
    if (!fileStat.isFile()) {
      response.writeHead(404).end();
      return;
    }
    const body = await readFile(filePath);
    const headers = {
      "Accept-Ranges": "bytes",
      "Cache-Control": "no-store",
      "Content-Type": types.get(extname(filePath).toLowerCase()) ||
        "application/octet-stream",
    };
    const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.range || "");
    if (range) {
      const start = range[1] ? Number(range[1]) : 0;
      const end = range[2]
        ? Math.min(Number(range[2]), body.length - 1)
        : body.length - 1;
      if (!Number.isInteger(start) || !Number.isInteger(end) ||
          start < 0 || end < start || start >= body.length) {
        response.writeHead(416, { "Content-Range": `bytes */${body.length}` });
        response.end();
        return;
      }
      const chunk = body.subarray(start, end + 1);
      response.writeHead(206, {
        ...headers,
        "Content-Length": chunk.length,
        "Content-Range": `bytes ${start}-${end}/${body.length}`,
      });
      response.end(request.method === "HEAD" ? undefined : chunk);
      return;
    }
    response.writeHead(200, { ...headers, "Content-Length": body.length });
    response.end(request.method === "HEAD" ? undefined : body);
  } catch (error) {
    response.writeHead(error?.code === "ENOENT" ? 404 : 500).end();
  }
});

await new Promise((resolveListen, rejectListen) => {
  httpServer.once("error", rejectListen);
  httpServer.listen(0, "127.0.0.1", resolveListen);
});
const httpAddress = httpServer.address();
assert.ok(httpAddress && typeof httpAddress === "object");
const origin = `http://127.0.0.1:${httpAddress.port}`;

const debugPort = await new Promise((resolvePort, rejectPort) => {
  const reservation = createNetServer();
  reservation.once("error", rejectPort);
  reservation.listen(0, "127.0.0.1", () => {
    const address = reservation.address();
    reservation.close((error) => {
      if (error) rejectPort(error);
      else resolvePort(address.port);
    });
  });
});

await rm(profilePath, { recursive: true, force: true });
const browser = spawn(
  browserExecutable,
  [
    "--headless=new",
    "--disable-background-networking",
    "--disable-breakpad",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--disable-gpu",
    "--disable-sync",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-first-run",
    "--no-sandbox",
    "--no-default-browser-check",
    "--host-resolver-rules=MAP * 0.0.0.0, EXCLUDE 127.0.0.1",
    "--remote-allow-origins=*",
    `--remote-debugging-port=${debugPort}`,
    `--user-data-dir=${profilePath}`,
    "about:blank",
  ],
  { stdio: ["ignore", "ignore", "pipe"], windowsHide: true },
);

const delay = (milliseconds) =>
  new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));

async function browserEndpoint(timeout = 45_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (browser.exitCode !== null) {
      throw new Error(`browser exited before DevTools was ready (${browser.exitCode})`);
    }
    try {
      const response = await fetch(`http://127.0.0.1:${debugPort}/json/version`);
      if (response.ok) {
        const version = await response.json();
        if (version.webSocketDebuggerUrl) return version.webSocketDebuggerUrl;
      }
    } catch {}
    await delay(75);
  }
  throw new Error("timed out waiting for browser DevTools");
}

class CdpClient {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Set();
  }

  async connect() {
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result || {});
        return;
      }
      for (const listener of this.listeners) listener(message);
    });
    await new Promise((resolveConnect, rejectConnect) => {
      this.socket.addEventListener("open", resolveConnect, { once: true });
      this.socket.addEventListener("error", rejectConnect, { once: true });
    });
  }

  send(method, params = {}, sessionId = undefined) {
    const id = this.nextId++;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    return new Promise((resolveSend, rejectSend) => {
      this.pending.set(id, { resolve: resolveSend, reject: rejectSend });
      this.socket.send(JSON.stringify(payload));
    });
  }

  onEvent(listener) {
    this.listeners.add(listener);
  }

  close() {
    this.socket.close();
  }
}

let client;
let targetId;
let sessionId;
const consoleErrors = [];
const pageErrors = [];
const networkErrors = [];
const externalRequests = [];
const requests = [];

async function evaluate(expression) {
  const result = await client.send(
    "Runtime.evaluate",
    { expression, awaitPromise: true, returnByValue: true },
    sessionId,
  );
  if (result.exceptionDetails) {
    throw new Error(
      result.exceptionDetails.exception?.description ||
      result.exceptionDetails.text ||
      "browser evaluation failed",
    );
  }
  return result.result?.value;
}

async function waitFor(expression, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      if (await evaluate(expression)) return;
    } catch {}
    await delay(60);
  }
  throw new Error(`timed out waiting for: ${expression}`);
}

const keyDefinitions = {
  ArrowDown: { key: "ArrowDown", code: "ArrowDown", virtualKeyCode: 40 },
  ArrowRight: { key: "ArrowRight", code: "ArrowRight", virtualKeyCode: 39 },
  Enter: { key: "Enter", code: "Enter", virtualKeyCode: 13 },
  Escape: { key: "Escape", code: "Escape", virtualKeyCode: 27 },
  KeyW: { key: "w", code: "KeyW", virtualKeyCode: 87, text: "w" },
};

async function dispatchKey(name) {
  const definition = keyDefinitions[name];
  assert.ok(definition, `unknown key ${name}`);
  const common = {
    key: definition.key,
    code: definition.code,
    windowsVirtualKeyCode: definition.virtualKeyCode,
    nativeVirtualKeyCode: definition.virtualKeyCode,
  };
  await client.send(
    "Input.dispatchKeyEvent",
    { type: "rawKeyDown", ...common, text: definition.text || "" },
    sessionId,
  );
  await client.send(
    "Input.dispatchKeyEvent",
    { type: "keyUp", ...common },
    sessionId,
  );
}

async function activate(selector) {
  await evaluate(`(() => {
    const control = document.querySelector(${JSON.stringify(selector)});
    if (!control) throw new Error("missing control: ${selector}");
    control.focus({ preventScroll: true });
    control.click();
  })()`);
}

const captureExpression = `(() => {
  const host = document.querySelector("#host");
  const stage = document.querySelector("#stage");
  const frame = stage?.querySelector("iframe");
  const lower = stage?.querySelector(".l3");
  const button = document.querySelector("#b-take-control");
  const lbar = document.querySelector(".lbar");
  const takebar = document.querySelector("#takebar");
  const round = value => Math.round(value * 100) / 100;
  const rect = element => {
    const value = element.getBoundingClientRect();
    return {
      left: round(value.left),
      top: round(value.top),
      right: round(value.right),
      bottom: round(value.bottom),
      width: round(value.width),
      height: round(value.height)
    };
  };
  const lowerStyle = lower ? getComputedStyle(lower) : null;
  const buttonStyle = button ? getComputedStyle(button) : null;
  const stageRect = rect(stage);
  const frameRect = rect(frame);
  return {
    page: {
      innerWidth,
      innerHeight,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth
    },
    host: {
      takeover: host.classList.contains("live-takeover"),
      state: host.dataset.takeover || ""
    },
    stage: {
      ...stageRect,
      clientWidth: stage.clientWidth,
      clientHeight: stage.clientHeight,
      scrollWidth: stage.scrollWidth,
      scrollHeight: stage.scrollHeight
    },
    frame: {
      ...frameRect,
      title: frame.title,
      widthDelta: round(frameRect.width - stage.clientWidth),
      heightDelta: round(frameRect.height - stage.clientHeight)
    },
    lower: lower ? {
      display: lowerStyle.display,
      visibility: lowerStyle.visibility,
      height: rect(lower).height
    } : null,
    lbarDisplay: lbar ? getComputedStyle(lbar).display : null,
    takebarDisplay: takebar ? getComputedStyle(takebar).display : null,
    button: button ? {
      hidden: button.hidden,
      display: buttonStyle.display,
      rect: rect(button),
      text: button.textContent.trim(),
      label: button.getAttribute("aria-label"),
      pressed: button.getAttribute("aria-pressed")
    } : null,
    progress: Number.parseFloat(document.querySelector("#ls i")?.style.width || "0"),
    playText: document.querySelector("#lp")?.textContent.trim() || "",
    topFocus: document.activeElement?.tagName || "",
    childFocus: frame.contentDocument?.activeElement?.id || "",
    childHasFocus: frame.contentDocument?.hasFocus() || false,
    appState: frame.contentWindow.invoiceTriage.snapshot(),
    appTimeOrigin: frame.contentWindow.performance.timeOrigin,
    keyLog: [...(frame.contentWindow.__rvTakeoverKeys || [])]
  };
})()`;

async function capture() {
  return evaluate(captureExpression);
}

function assertNoHorizontalOverflow(captureValue, label) {
  assert.ok(
    captureValue.page.scrollWidth <= captureValue.page.clientWidth,
    `${label}: document overflowed horizontally`,
  );
  assert.ok(
    captureValue.page.bodyScrollWidth <= captureValue.page.clientWidth,
    `${label}: body overflowed horizontally`,
  );
  assert.ok(
    captureValue.stage.scrollWidth <= captureValue.stage.clientWidth,
    `${label}: stage overflowed horizontally`,
  );
  assert.ok(
    captureValue.stage.scrollHeight <= captureValue.stage.clientHeight,
    `${label}: stage overflowed vertically`,
  );
  assert.ok(
    captureValue.stage.right <= captureValue.page.clientWidth + 0.5,
    `${label}: stage escaped the viewport`,
  );
  assert.ok(
    Math.abs(captureValue.frame.widthDelta) <= 0.5,
    `${label}: iframe width does not exactly match the stage`,
  );
  assert.ok(
    Math.abs(captureValue.frame.heightDelta) <= 0.5,
    `${label}: iframe height does not exactly match the stage`,
  );
}

const viewports = [
  { name: "desktop", width: 1280, height: 900 },
  { name: "mobile-390", width: 390, height: 844 },
];
const runs = [];

try {
  client = new CdpClient(await browserEndpoint());
  await client.connect();
  const version = await client.send("Browser.getVersion");
  ({ targetId } = await client.send("Target.createTarget", { url: "about:blank" }));
  ({ sessionId } = await client.send(
    "Target.attachToTarget",
    { targetId, flatten: true },
  ));
  client.onEvent((message) => {
    if (message.sessionId !== sessionId) return;
    const { method, params } = message;
    if (method === "Runtime.consoleAPICalled" && params.type === "error") {
      consoleErrors.push(
        params.args
          .map(argument => argument.value || argument.description || "")
          .join(" "),
      );
    } else if (method === "Runtime.exceptionThrown") {
      pageErrors.push(
        params.exceptionDetails.exception?.description ||
        params.exceptionDetails.text,
      );
    } else if (method === "Network.requestWillBeSent") {
      requests.push(params.request.url);
      if (/^https?:/.test(params.request.url) &&
          !params.request.url.startsWith(origin + "/")) {
        externalRequests.push(params.request.url);
      }
    } else if (method === "Network.responseReceived" &&
               /^https?:/.test(params.response.url) &&
               params.response.status >= 400) {
      networkErrors.push(`${params.response.status} ${params.response.url}`);
    } else if (method === "Network.loadingFailed" &&
               !params.canceled && params.errorText !== "net::ERR_ABORTED") {
      networkErrors.push(params.errorText);
    }
  });
  await Promise.all([
    client.send("Page.enable", {}, sessionId),
    client.send("Runtime.enable", {}, sessionId),
    client.send("Network.enable", {}, sessionId),
    client.send("Log.enable", {}, sessionId),
  ]);

  for (const viewport of viewports) {
    await client.send(
      "Emulation.setDeviceMetricsOverride",
      {
        width: viewport.width,
        height: viewport.height,
        screenWidth: viewport.width,
        screenHeight: viewport.height,
        deviceScaleFactor: 1,
        mobile: viewport.name === "mobile-390",
      },
      sessionId,
    );
    await client.send(
      "Storage.clearDataForOrigin",
      { origin, storageTypes: "all" },
      sessionId,
    );
    const invoiceKey = encodeURIComponent(
      "use-keyboard-invoice-triage/use-keyboard-invoice-triage",
    );
    await client.send(
      "Page.navigate",
      { url: `${origin}/index.html#/watch/${invoiceKey}` },
      sessionId,
    );
    await waitFor(
      'document.readyState === "complete" && document.querySelector("#b-switch")?.textContent.includes("Try live replay")',
    );
    await waitFor('document.querySelector("video")?.readyState >= 2');
    assert.equal(
      await evaluate(
        '!document.querySelector("#b-take-control") && !document.querySelector(".live-takeover")',
      ),
      true,
      `${viewport.name}: encoded default unexpectedly entered takeover`,
    );
    await evaluate('document.querySelector("#b-switch").click()');
    await waitFor(
      'Boolean(document.querySelector("#stage iframe")?.contentWindow?.invoiceTriage) && !document.querySelector("#b-take-control").hidden',
    );
    await delay(100);
    const normal = await capture();
    assert.equal(normal.host.takeover, false);
    assert.equal(normal.host.state, "false");
    assert.equal(normal.button.text, "Take control");
    assert.equal(normal.button.pressed, "false");
    assert.notEqual(normal.lower.display, "none");
    assert.notEqual(normal.lbarDisplay, "none");
    assert.ok(
      Math.abs(normal.stage.width / normal.stage.height - 1.6) < 0.01,
      `${viewport.name}: default live stage geometry changed`,
    );
    assertNoHorizontalOverflow(normal, `${viewport.name} normal`);

    await evaluate(`(() => {
      const frame = document.querySelector("#stage iframe");
      frame.contentWindow.__rvTakeoverKeys = [];
      frame.contentWindow.__rvTakeoverMarker = "preserve-${viewport.name}";
      frame.contentDocument.addEventListener("keydown", event => {
        frame.contentWindow.__rvTakeoverKeys.push(event.code || event.key);
      }, true);
      document.querySelector("#lp").click();
    })()`);
    await waitFor('document.querySelector("#lp").textContent.includes("Pause")');
    await waitFor(
      'Number.parseFloat(document.querySelector("#ls i").style.width) > 0.02',
    );
    const appRequestsBefore = requests.filter(
      url => url.endsWith("/apps/use-keyboard-invoice-triage.html"),
    ).length;
    await activate("#b-take-control");
    await waitFor('document.querySelector("#host").classList.contains("live-takeover")');
    await waitFor('document.activeElement?.tagName === "IFRAME"');
    const takeover = await capture();
    assert.equal(takeover.host.state, "true");
    assert.equal(takeover.button.text, "Show captions");
    assert.equal(takeover.button.pressed, "true");
    assert.equal(takeover.lower.display, "none");
    assert.equal(takeover.lbarDisplay, "none");
    assert.ok(takeover.playText.includes("Play"));
    assert.equal(takeover.button.hidden, false);
    assert.notEqual(takeover.button.display, "none");
    assert.ok(
      takeover.button.rect.top >= takeover.stage.top &&
      takeover.button.rect.bottom <= takeover.stage.bottom &&
      takeover.button.rect.right <= takeover.stage.right,
      `${viewport.name}: Show captions control is not visible over the stage`,
    );
    assert.equal(takeover.topFocus, "IFRAME");
    assert.equal(takeover.childHasFocus, true);
    assert.ok(
      takeover.frame.height >= 520,
      `${viewport.name}: takeover iframe is only ${takeover.frame.height}px tall`,
    );
    assert.ok(
      takeover.stage.height <= 820.5,
      `${viewport.name}: takeover stage exceeded its bound`,
    );
    assert.ok(
      Math.abs(takeover.stage.width - normal.stage.width) <= 0.5,
      `${viewport.name}: takeover changed the exact stage width`,
    );
    assertNoHorizontalOverflow(takeover, `${viewport.name} takeover`);
    await delay(700);
    const paused = await capture();
    assert.ok(
      Math.abs(paused.progress - takeover.progress) <= 0.01,
      `${viewport.name}: replay clock advanced during takeover`,
    );

    await dispatchKey("ArrowDown");
    await waitFor(
      'document.querySelector("#stage iframe").contentWindow.invoiceTriage.snapshot().focus === "invoice-syn-002"',
    );
    await dispatchKey("ArrowRight");
    await dispatchKey("KeyW");
    const keyed = await capture();
    assert.deepEqual(
      keyed.keyLog.slice(-3),
      ["ArrowDown", "ArrowRight", "KeyW"],
      `${viewport.name}: real keys did not reach the live app`,
    );
    assert.ok(
      Math.abs(keyed.progress - takeover.progress) <= 0.01,
      `${viewport.name}: parent player stole a game key`,
    );
    assert.equal(keyed.appState.focus, "invoice-syn-002");

    await activate("#b-take-control");
    await waitFor(
      '!document.querySelector("#host").classList.contains("live-takeover") && document.querySelector("#lp").textContent.includes("Pause")',
    );
    await evaluate('document.querySelector("#lp").click()');
    const restored = await capture();
    assert.equal(restored.button.text, "Take control");
    assert.equal(restored.button.pressed, "false");
    assert.notEqual(restored.lower.display, "none");
    assert.notEqual(restored.lbarDisplay, "none");
    assert.equal(restored.appState.focus, "invoice-syn-002");
    assert.equal(restored.appTimeOrigin, normal.appTimeOrigin);
    assert.equal(
      await evaluate(
        'document.querySelector("#stage iframe").contentWindow.__rvTakeoverMarker',
      ),
      `preserve-${viewport.name}`,
    );
    assert.ok(
      Math.abs(restored.stage.width - normal.stage.width) <= 0.5 &&
      Math.abs(restored.stage.height - normal.stage.height) <= 0.5,
      `${viewport.name}: normal stage geometry was not restored`,
    );
    assertNoHorizontalOverflow(restored, `${viewport.name} restored`);
    const appRequestsAfter = requests.filter(
      url => url.endsWith("/apps/use-keyboard-invoice-triage.html"),
    ).length;
    assert.equal(
      appRequestsAfter,
      appRequestsBefore,
      `${viewport.name}: exiting takeover reloaded the iframe`,
    );

    await activate("#b-take-control");
    await waitFor('document.activeElement?.tagName === "IFRAME"');
    await dispatchKey("Escape");
    await waitFor(
      '!document.querySelector("#host").classList.contains("live-takeover") && document.activeElement?.id === "b-take-control"',
    );
    const escapeFocus = await evaluate(`(() => {
      const button = document.querySelector("#b-take-control");
      const style = getComputedStyle(button);
      return {
        active: document.activeElement === button,
        outlineStyle: style.outlineStyle,
        outlineWidth: style.outlineWidth
      };
    })()`);
    assert.equal(escapeFocus.active, true);
    assert.notEqual(escapeFocus.outlineStyle, "none");
    assert.notEqual(escapeFocus.outlineWidth, "0px");

    await activate("#b-take-control");
    await waitFor('document.querySelector("#host").classList.contains("live-takeover")');
    await evaluate('document.querySelector("#b-switch").click()');
    await waitFor(
      'document.querySelector("#host").dataset.watchMode === "video" && Boolean(document.querySelector("#host video"))',
    );
    const modeCleanup = await evaluate(`({
      takeoverNodes: document.querySelectorAll(".live-takeover").length,
      takeoverButton: Boolean(document.querySelector("#b-take-control")),
      takeoverState: document.querySelector("#host").dataset.takeover || ""
    })`);
    assert.deepEqual(modeCleanup, {
      takeoverNodes: 0,
      takeoverButton: false,
      takeoverState: "",
    });
    await waitFor('document.querySelector("#host video").readyState >= 2');

    await evaluate('document.querySelector("#b-switch").click()');
    await waitFor(
      'Boolean(document.querySelector("#stage iframe")?.contentWindow?.invoiceTriage)',
    );
    await activate("#b-take-control");
    await waitFor('document.querySelector("#host").classList.contains("live-takeover")');
    const gridKey = encodeURIComponent(
      "candidate-frame-0002-04/learn-grid-overflow",
    );
    await evaluate(`location.hash = "#/watch/${gridKey}"`);
    await waitFor(
      'document.querySelector("#host")?.dataset.watchMode === "video" && document.querySelector(".vtitle")?.textContent.includes("Grid")',
    );
    const publicationCleanup = await evaluate(`({
      takeoverNodes: document.querySelectorAll(".live-takeover").length,
      takeoverButton: Boolean(document.querySelector("#b-take-control")),
      takeoverState: document.querySelector("#host").dataset.takeover || ""
    })`);
    assert.deepEqual(publicationCleanup, {
      takeoverNodes: 0,
      takeoverButton: false,
      takeoverState: "",
    });
    await waitFor('document.querySelector("#host video").readyState >= 2');

    runs.push({
      viewport,
      normal: {
        stage: normal.stage,
        frame: normal.frame,
        lowerHeight: normal.lower.height,
      },
      takeover: {
        stage: takeover.stage,
        frame: takeover.frame,
        lowerDisplay: takeover.lower.display,
      },
      restored: {
        stage: restored.stage,
        frame: restored.frame,
        lowerHeight: restored.lower.height,
      },
      clock: {
        entered: takeover.progress,
        after700ms: paused.progress,
      },
      keys: keyed.keyLog.slice(-3),
      appRequestsBefore,
      appRequestsAfter,
      escapeFocus,
      modeCleanup,
      publicationCleanup,
    });
  }

  assert.deepEqual(consoleErrors, []);
  assert.deepEqual(pageErrors, []);
  assert.deepEqual(networkErrors, []);
  assert.deepEqual(externalRequests, []);
  process.stdout.write(JSON.stringify({
    browser: version.product,
    consoleErrors,
    pageErrors,
    networkErrors,
    externalRequests,
    runs,
  }));
} finally {
  try {
    if (client) await client.send("Browser.close");
  } catch {}
  client?.close();
  const deadline = Date.now() + 10_000;
  while (browser.exitCode === null && Date.now() < deadline) await delay(50);
  if (browser.exitCode === null) browser.kill();
  await new Promise(resolveClose => httpServer.close(resolveClose));
  await rm(profilePath, {
    recursive: true,
    force: true,
    maxRetries: 12,
    retryDelay: 150,
  });
}
