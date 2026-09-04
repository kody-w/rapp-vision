import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { createServer as createNetServer } from "node:net";
import {
  mkdir,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import {
  dirname,
  extname,
  join,
  relative,
  resolve,
  sep,
} from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const [
  browserPath,
  channelArgument,
  evidenceIndexArgument,
  outputArgument,
  profileArgument,
] = process.argv.slice(2);

if (
  !browserPath ||
  !channelArgument ||
  !evidenceIndexArgument ||
  !outputArgument ||
  !profileArgument
) {
  throw new Error(
    "usage: node working_proofs_viewport_browser.mjs " +
      "<browser> <channel> <evidence-index> <output> <profile>",
  );
}

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const channelPath = resolve(channelArgument);
const evidenceIndexPath = resolve(evidenceIndexArgument);
const outputRoot = resolve(outputArgument);
const profilePath = resolve(profileArgument);
const workingRoot = resolve(ROOT, "working-proofs");
const channel = JSON.parse(await readFile(channelPath, "utf8"));
const evidenceIndex = JSON.parse(await readFile(evidenceIndexPath, "utf8"));
const registry = JSON.parse(
  await readFile(resolve(ROOT, "channels.json"), "utf8"),
);
const harnessRegistry = Buffer.from(JSON.stringify({
  ...registry,
  channels: registry.channels.filter(
    entry => entry.id === channel.id,
  ),
}));

function assertWorkingScratch(path, label) {
  const prefix = workingRoot.endsWith(sep)
    ? workingRoot
    : `${workingRoot}${sep}`;
  assert.ok(
    path !== workingRoot && path.startsWith(prefix),
    `${label} must be a child of ${workingRoot}`,
  );
}

assertWorkingScratch(outputRoot, "output");
assertWorkingScratch(profilePath, "browser profile");

const VIEWPORTS = [
  {
    id: "desktop",
    pageWidth: 1387,
    pageHeight: 900,
    frameWidth: 960,
    frameHeight: 599.25,
    stageWidth: 962,
    stageHeight: 601.25,
    screenshotWidth: 962,
    screenshotHeight: 601,
    outerClientWidths: [1372, 1387],
    scrollbarWidths: [0, 15],
  },
  {
    id: "390",
    pageWidth: 435,
    pageHeight: 900,
    frameWidth: 390,
    frameHeight: 243,
    stageWidth: 392,
    stageHeight: 245,
    screenshotWidth: 392,
    screenshotHeight: 245,
    outerClientWidths: [420, 435],
    scrollbarWidths: [0, 15],
  },
];

const CONFIG = {
  "learn-grid-overflow": {
    contract: "gridOverflowLesson",
    snapshotMethod: "snapshot",
    evidence(document) {
      const publication = document.publications[0];
      return {
        checkpoints: publication.liveFraming.checkpoints,
        claims: publication.claims,
      };
    },
  },
  "use-keyboard-invoice-triage": {
    contract: "invoiceTriage",
    snapshotMethod: "snapshot",
    evidence(document) {
      return {
        checkpoints: document.manifestReplay.checkpoints,
        claims: document.claims,
      };
    },
  },
  "create-vector-icon-system": {
    contract: "vectorIconSystem",
    snapshotMethod: "getState",
    evidence(document) {
      return {
        checkpoints: document.browserReplay.checkpoints,
        claims: document.claims,
      };
    },
  },
  "ecosystem-island-threshold": {
    contract: "islandLab",
    snapshotMethod: "summary",
    evidence(document) {
      return {
        actionCount: document.manifestReplay.actionCount,
        checkpoints: document.manifestReplay.checkpoints,
        claims: document.claims,
      };
    },
  },
  "explore-archive-map-contrast": {
    contract: "archiveWetlandMap",
    snapshotMethod: "snapshot",
    evidence(document) {
      return {
        actionCount: document.manifestReplay.actionCount,
        activationActions: document.manifestReplay.activationActions,
        checkpoints: document.manifestReplay.checkpoints,
        claims: document.claims,
        finalPrompt: document.manifestReplay.finalPrompt,
      };
    },
  },
  "maze-fogline": {
    openingClaim: "resetAfterTrap",
    realInput: true,
    readyExpression:
      'frame.contentDocument.documentElement.dataset.ready === "true" && ' +
      'frame.contentDocument.querySelectorAll("#maze-board > .cell").length === 36',
    snapshotExpression: foglineSnapshotExpression,
    captureClaims: {
      trap: "trap",
      optimal: "success",
      handoff: "FOG-7",
    },
    evidence(document) {
      return {
        actionCount: document.manifestReplay.actionCount,
        checkpointMode: "state-gated",
        checkpoints: document.manifestReplay.checkpoints,
        claims: document.claims.map(claim => ({
          id: claim.id,
          expectedState: claim.stateGate,
        })),
        maxActionLatenessSeconds:
          document.manifestReplay.maxActionLatenessSeconds,
      };
    },
  },
};

assert.deepEqual(
  channel.videos.map(item => item.id),
  Object.keys(CONFIG),
  "aggregate publication order and browser configuration diverged",
);

function publication(id) {
  const found = channel.videos.find((item) => item.id === id);
  assert.ok(found, `aggregate publication is missing: ${id}`);
  return found;
}

function indexRecord(id) {
  const found = evidenceIndex.publications.find(
    (item) => item.publication_id === id,
  );
  assert.ok(found, `aggregate evidence record is missing: ${id}`);
  return found;
}

function referencedPath(basePath, reference) {
  const path = resolve(fileURLToPath(new URL(reference, pathToFileURL(basePath))));
  const prefix = ROOT.endsWith(sep) ? ROOT : `${ROOT}${sep}`;
  assert.ok(
    path === ROOT || path.startsWith(prefix),
    `reference escapes the repository: ${reference}`,
  );
  return path;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

const mimeTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".mp4", "video/mp4"],
  [".png", "image/png"],
  [".svg", "image/svg+xml; charset=utf-8"],
  [".webm", "video/webm"],
]);

function repositoryPath(requestUrl) {
  const pathname = decodeURIComponent(
    new URL(requestUrl, "http://127.0.0.1").pathname,
  );
  const parts = pathname.split("/").filter(Boolean);
  const candidate = resolve(ROOT, ...(parts.length ? parts : ["index.html"]));
  const prefix = ROOT.endsWith(sep) ? ROOT : `${ROOT}${sep}`;
  if (candidate !== ROOT && !candidate.startsWith(prefix)) return null;
  return candidate;
}

const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(
      request.url || "/",
      "http://127.0.0.1",
    ).pathname;
    if (pathname === "/channels.json") {
      response.writeHead(200, {
        "Cache-Control": "no-store",
        "Content-Length": harnessRegistry.length,
        "Content-Type": "application/json; charset=utf-8",
      });
      response.end(harnessRegistry);
      return;
    }
    const path = repositoryPath(request.url || "/");
    if (!path || !(await stat(path)).isFile()) {
      response.writeHead(404);
      response.end("not found");
      return;
    }
    const bytes = await readFile(path);
    response.writeHead(200, {
      "Cache-Control": "no-store",
      "Content-Length": bytes.length,
      "Content-Type": mimeTypes.get(extname(path).toLowerCase()) ||
        "application/octet-stream",
    });
    response.end(bytes);
  } catch {
    response.writeHead(404);
    response.end("not found");
  }
});

await new Promise((resolveListen, rejectListen) => {
  server.once("error", rejectListen);
  server.listen(0, "127.0.0.1", resolveListen);
});
const address = server.address();
assert.ok(address && typeof address === "object");
const origin = `http://127.0.0.1:${address.port}`;

await rm(outputRoot, { recursive: true, force: true });
await mkdir(outputRoot, { recursive: true });
await rm(profilePath, { recursive: true, force: true });
const debugPort = await new Promise((resolvePort, rejectPort) => {
  const server = createNetServer();
  server.once("error", rejectPort);
  server.listen(0, "127.0.0.1", () => {
    const reserved = server.address();
    server.close(error => {
      if (error) rejectPort(error);
      else resolvePort(reserved.port);
    });
  });
});

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
  { stdio: "ignore", windowsHide: true },
);

const delay = (milliseconds) =>
  new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));
const browserRunning = () =>
  browser.exitCode === null && browser.signalCode === null;

async function activePort(timeout = 45_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (!browserRunning()) {
      throw new Error(
        "browser exited before DevTools was ready: " +
          `${browser.exitCode ?? browser.signalCode}`,
      );
    }
    try {
      const response = await fetch(
        `http://127.0.0.1:${debugPort}/json/version`,
      );
      if (response.ok) return String(debugPort);
    } catch {}
    await delay(75);
  }
  throw new Error("browser did not publish DevToolsActivePort");
}

async function readJson(url, timeout = 15_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (!browserRunning()) {
      throw new Error(
        `browser exited while waiting for ${url}: ` +
          `${browser.exitCode ?? browser.signalCode}`,
      );
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
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result);
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
const externalRequests = [];
const networkErrors = [];
const requests = [];

async function evaluate(expression) {
  const response = await cdp.command("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error(
      response.exceptionDetails.exception?.description ||
        response.exceptionDetails.text ||
        "browser evaluation failed",
    );
  }
  return response.result.value;
}

async function waitFor(expression, timeout = 20_000) {
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
    width: viewport.pageWidth,
    height: viewport.pageHeight,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await delay(50);
}

async function openReplay(publicationId, config) {
  const key = encodeURIComponent(`working-proofs/${publicationId}`);
  await cdp.command("Page.navigate", {
    url: `${origin}/index.html#/watch/${key}`,
  });
  await waitFor(
    `document.querySelector(".vtitle")?.textContent.includes(${JSON.stringify(
      publication(publicationId).title,
    )}) && Boolean(document.querySelector("#b-switch"))`,
  );
  await evaluate('document.querySelector("#b-switch").click()');
  if (config.readyExpression) {
    await waitFor(`(() => {
      const frame = document.querySelector("#stage iframe");
      return Boolean(frame) && (${config.readyExpression});
    })()`);
  } else {
    await waitFor(
      `Boolean(document.querySelector("#stage iframe")?.contentWindow?.[${JSON.stringify(
        config.contract,
      )}])`,
    );
  }
  await delay(100);
}

async function snapshot(config) {
  if (config.snapshotExpression) {
    return evaluate(config.snapshotExpression());
  }
  return evaluate(`(() => {
    const frame = document.querySelector("#stage iframe");
    return frame.contentWindow[${JSON.stringify(config.contract)}][${JSON.stringify(
      config.snapshotMethod,
    )}]();
  })()`);
}

function foglineSnapshotExpression() {
  return `(() => {
    const frame = document.querySelector("#stage iframe");
    const doc = frame.contentDocument;
    const text = selector => doc.querySelector(selector).textContent.trim();
    const hidden = selector => doc.querySelector(selector).hidden;
    const integer = value => Number.parseInt(value.match(/-?\\d+/)?.[0] || "0", 10);
    const position = text("#position-value")
      .replace(/[()]/g, "")
      .split(",")
      .map(value => Number.parseInt(value, 10));
    const compass = {
      NORTH: "N",
      EAST: "E",
      SOUTH: "S",
      WEST: "W"
    }[text("#compass-value")];
    const successText = text("#success-panel");
    const statusText = text("#status-message");
    const hintText = text("#hint-panel");
    const assistanceText = text("#assist-value");
    const completed = !hidden("#success-panel");
    let status = "ready";
    if (completed) {
      status = /matched the reference|= reference/i.test(successText)
        ? "complete-optimal"
        : "complete-detour";
    } else if (!hidden("#trap-panel")) {
      status = "trap";
    } else if (!hidden("#hint-panel")) {
      status = "hint";
    } else if (/fogbound by a wall/i.test(statusText)) {
      status = "wall";
    } else if (!/\\bready\\b/i.test(statusText)) {
      status = "moving";
    }
    const steps = integer(text("#step-value"));
    const assistanceUsed = /^ASSISTED\\b/.test(assistanceText);
    return {
      assistanceUsed,
      completed,
      exitState: text("#exit-value").split(/\\s+/)[0],
      facing: compass,
      hintAvailable: !doc.querySelector("#hint-btn").disabled,
      hintDirection: hidden("#hint-panel")
        ? null
        : (hintText.match(/ONE STEP ONLY:\\s*([NESW])/i)?.[1] || null),
      hintRequests: assistanceUsed ? 1 : 0,
      matchedOptimal: completed
        ? /matched the reference|= reference/i.test(successText)
        : null,
      position,
      projectedTotal: integer(text("#projection-value")),
      seed: text("#seed-value"),
      status,
      steps,
      topologyDigest: text("#digest-value"),
      trailLength: steps
    };
  })()`;
}

async function waitForSnapshot(config, expected, label, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  let actual = null;
  let mismatch = null;
  while (Date.now() < deadline) {
    actual = await snapshot(config);
    try {
      assert.deepEqual(actual, expected);
      return actual;
    } catch (error) {
      mismatch = error;
    }
    await delay(75);
  }
  throw new Error(
    `${label} did not reach its evidence state: ${mismatch?.message || ""}\n` +
      `actual=${canonicalJson(actual)}\nexpected=${canonicalJson(expected)}`,
  );
}

async function targetMetrics(selector = null, reveal = false) {
  return evaluate(`(() => {
    const stage = document.querySelector("#stage");
    const frame = stage.querySelector("iframe");
    const lower = stage.querySelector(".l3");
    const doc = frame.contentDocument;
    const target = ${selector === null
      ? "doc.activeElement"
      : `doc.querySelector(${JSON.stringify(selector)})`};
    if (!target) throw new Error("missing viewport target");
    const frameRect = frame.getBoundingClientRect();
    const stageRect = stage.getBoundingClientRect();
    const lowerRect = lower ? lower.getBoundingClientRect() : null;
    const style = frame.contentWindow.getComputedStyle(target);
    const safeHeight = Math.max(
      0,
      Math.min(
        frameRect.height,
        lowerRect ? lowerRect.top - frameRect.top : frameRect.height
      )
    );
    let rect = target.getBoundingClientRect();
    if (${JSON.stringify(reveal)}) {
      if (rect.bottom > safeHeight - 8) {
        const clearance = Math.max(0, frameRect.height - safeHeight + 16);
        doc.documentElement.style.paddingBottom =
          clearance ? clearance + "px" : "";
        doc.documentElement.style.scrollPaddingBottom =
          clearance ? clearance + "px" : "";
        rect = target.getBoundingClientRect();
        frame.contentWindow.scrollBy(0, rect.bottom - safeHeight + 8);
      } else if (rect.top < 8) {
        frame.contentWindow.scrollBy(0, rect.top - 8);
      }
      rect = target.getBoundingClientRect();
    }
    const visibleWidth = Math.max(
      0,
      Math.min(rect.right, frameRect.width) - Math.max(rect.left, 0)
    );
    const visibleHeight = Math.max(
      0,
      Math.min(rect.bottom, safeHeight) - Math.max(rect.top, 0)
    );
    const requiredWidth = Math.min(32, Math.max(1, rect.width / 2));
    const requiredHeight = Math.min(24, Math.max(1, rect.height / 2));
    const rendered =
      !target.hidden &&
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      Number(style.opacity) > 0.5 &&
      rect.width > 0 &&
      rect.height > 0;
    return {
      id: target.id,
      tag: target.tagName,
      disabled:
        Boolean(target.disabled) ||
        target.getAttribute("aria-disabled") === "true",
      rendered,
      left: rect.left,
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom,
      width: rect.width,
      height: rect.height,
      visibleWidth,
      visibleHeight,
      requiredWidth,
      requiredHeight,
      visible:
        rendered &&
        visibleWidth >= requiredWidth &&
        visibleHeight >= requiredHeight,
      frameWidth: frameRect.width,
      frameHeight: frameRect.height,
      stageWidth: stageRect.width,
      stageHeight: stageRect.height,
      outerViewportWidth: innerWidth,
      outerClientWidth: document.documentElement.clientWidth,
      outerScrollbarWidth:
        innerWidth - document.documentElement.clientWidth,
      outerScrollHeight: document.documentElement.scrollHeight,
      outerClientHeight: document.documentElement.clientHeight,
      htmlOverflowY: getComputedStyle(document.documentElement).overflowY,
      bodyOverflowY: getComputedStyle(document.body).overflowY,
      scrollbarGutter:
        getComputedStyle(document.documentElement).scrollbarGutter,
      safeHeight,
      lowerThirdHeight: lowerRect ? lowerRect.height : 0
    };
  })()`);
}

function assertVisible(metrics, label) {
  assert.equal(
    metrics.visible,
    true,
    `${label} is not visible above the live-player lower third: ` +
      JSON.stringify(metrics),
  );
}

function assertViewportGeometry(metrics, viewport, label) {
  const diagnostic = `${label}: ${JSON.stringify(metrics)}`;
  assert.ok(
    Math.abs(metrics.frameWidth - viewport.frameWidth) <= 0.5,
    diagnostic,
  );
  assert.ok(
    Math.abs(metrics.frameHeight - viewport.frameHeight) <= 0.5,
    diagnostic,
  );
  assert.ok(
    Math.abs(metrics.stageWidth - viewport.stageWidth) <= 0.5,
    diagnostic,
  );
  assert.ok(
    Math.abs(metrics.stageHeight - viewport.stageHeight) <= 0.5,
    diagnostic,
  );
  assert.equal(metrics.outerViewportWidth, viewport.pageWidth, diagnostic);
  assert.ok(
    viewport.outerClientWidths.includes(metrics.outerClientWidth),
    diagnostic,
  );
  assert.ok(
    viewport.scrollbarWidths.includes(metrics.outerScrollbarWidth),
    diagnostic,
  );
  assert.equal(metrics.htmlOverflowY, "scroll", diagnostic);
  assert.equal(metrics.bodyOverflowY, "visible", diagnostic);
  assert.match(metrics.scrollbarGutter, /^stable/, diagnostic);
  assert.ok(
    metrics.outerScrollHeight > metrics.outerClientHeight,
    `real page scrolling was lost; ${diagnostic}`,
  );
}

function keyFromCode(code) {
  const letter = /^Key([A-Z])$/.exec(code);
  if (letter) return letter[1].toLowerCase();
  const digit = /^Digit(\d)$/.exec(code);
  if (digit) return digit[1];
  if (code === "Space") return " ";
  return String(code || "").replace(/(Left|Right)$/, "");
}

const REAL_KEYS = {
  ArrowDown: { key: "ArrowDown", code: "ArrowDown", virtualKeyCode: 40 },
  ArrowLeft: { key: "ArrowLeft", code: "ArrowLeft", virtualKeyCode: 37 },
  ArrowRight: { key: "ArrowRight", code: "ArrowRight", virtualKeyCode: 39 },
  ArrowUp: { key: "ArrowUp", code: "ArrowUp", virtualKeyCode: 38 },
  Escape: { key: "Escape", code: "Escape", virtualKeyCode: 27 },
  KeyD: { key: "d", code: "KeyD", virtualKeyCode: 68, text: "d" },
};

async function dispatchRealKey(code) {
  const definition = REAL_KEYS[code];
  assert.ok(definition, `unsupported real key ${code}`);
  const common = {
    key: definition.key,
    code: definition.code,
    windowsVirtualKeyCode: definition.virtualKeyCode,
    nativeVirtualKeyCode: definition.virtualKeyCode,
  };
  await cdp.command("Input.dispatchKeyEvent", {
    type: "rawKeyDown",
    ...common,
    text: definition.text || "",
  });
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyUp",
    ...common,
  });
}

async function dispatchMousePoint({ x, y }) {
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
}

async function dispatchRealFrameClick(selector) {
  const point = await evaluate(`(() => {
    const stage = document.querySelector("#stage");
    stage.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "auto" });
    const frame = stage.querySelector("iframe");
    const target = frame.contentDocument.querySelector(${JSON.stringify(selector)});
    if (!target) throw new Error("missing real click target ${selector}");
    const frameRect = frame.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    return {
      x: frameRect.left + targetRect.left + targetRect.width / 2,
      y: frameRect.top + targetRect.top + targetRect.height / 2
    };
  })()`);
  await dispatchMousePoint(point);
}

async function dispatchRealOuterClick(selector) {
  const point = await evaluate(`(() => {
    const target = document.querySelector(${JSON.stringify(selector)});
    if (!target) throw new Error("missing outer click target ${selector}");
    target.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "auto" });
    const rect = target.getBoundingClientRect();
    return {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2
    };
  })()`);
  await dispatchMousePoint(point);
}

async function applyRealAction(action) {
  if (action.do === "scroll") {
    await evaluate(`(() => {
      const action = ${JSON.stringify(action)};
      const frame = document.querySelector("#stage iframe");
      const doc = frame.contentDocument;
      const target = doc.querySelector(action.selector);
      if (!target) throw new Error("missing scroll target " + action.selector);
      const frameRect = frame.getBoundingClientRect();
      const lower = document.querySelector("#stage .l3");
      const lowerRect = lower ? lower.getBoundingClientRect() : null;
      const safeBottom = Math.max(
        0,
        Math.min(
          frameRect.height,
          lowerRect ? lowerRect.top - frameRect.top : frameRect.height
        )
      );
      target.scrollIntoView({
        block: action.block || "center",
        inline: "nearest",
        behavior: "auto"
      });
      let rect = target.getBoundingClientRect();
      if (rect.bottom > safeBottom - 8) {
        const clearance = Math.max(0, frameRect.height - safeBottom + 16);
        doc.documentElement.style.paddingBottom =
          clearance ? clearance + "px" : "";
        doc.documentElement.style.scrollPaddingBottom =
          clearance ? clearance + "px" : "";
        rect = target.getBoundingClientRect();
        frame.contentWindow.scrollBy(0, rect.bottom - safeBottom + 8);
      } else if (rect.top < 8) {
        frame.contentWindow.scrollBy(0, rect.top - 8);
      }
    })()`);
  } else if (action.do === "click") {
    await dispatchRealFrameClick(action.selector);
  } else if (action.do === "key") {
    await dispatchRealKey(action.code);
  } else if (action.do === "type") {
    await cdp.command("Input.insertText", {
      text: String(action.text || ""),
    });
  } else {
    throw new Error(`unsupported real replay action ${action.do}`);
  }
  await delay(60);
}

async function applyAction(action, realInput = false) {
  if (realInput) {
    await applyRealAction(action);
    return;
  }
  const encoded = JSON.stringify(action);
  await evaluate(`(() => {
    const action = ${encoded};
    const frame = document.querySelector("#stage iframe");
    const doc = frame.contentDocument;
    const win = frame.contentWindow;
    const keyFromCode = ${keyFromCode.toString()};
    const keyEvent = (type, code, key) => new win.KeyboardEvent(type, {
      code,
      key: key || keyFromCode(code),
      bubbles: true,
      cancelable: true,
      composed: true
    });
    if (action.do === "scroll") {
      const target = doc.querySelector(action.selector);
      if (!target) throw new Error("missing scroll target " + action.selector);
      const frameRect = frame.getBoundingClientRect();
      const lower = document.querySelector("#stage .l3");
      const lowerRect = lower ? lower.getBoundingClientRect() : null;
      const safeBottom = Math.max(
        0,
        Math.min(
          frameRect.height,
          lowerRect ? lowerRect.top - frameRect.top : frameRect.height
        )
      );
      target.scrollIntoView({
        block: action.block || "center",
        inline: "nearest",
        behavior: "auto"
      });
      let rect = target.getBoundingClientRect();
      if (rect.bottom > safeBottom - 8) {
        const clearance = Math.max(0, frameRect.height - safeBottom + 16);
        doc.documentElement.style.paddingBottom =
          clearance ? clearance + "px" : "";
        doc.documentElement.style.scrollPaddingBottom =
          clearance ? clearance + "px" : "";
        rect = target.getBoundingClientRect();
        win.scrollBy(0, rect.bottom - safeBottom + 8);
      } else if (rect.top < 8) {
        win.scrollBy(0, rect.top - 8);
      }
      return;
    }
    if (action.do === "click") {
      const target = doc.querySelector(action.selector);
      if (!target) throw new Error("missing click target " + action.selector);
      if (target.disabled || target.getAttribute("aria-disabled") === "true") {
        throw new Error("disabled click target " + action.selector);
      }
      target.focus({ preventScroll: true });
      if (typeof target.select === "function") target.select();
      target.click();
      return;
    }
    if (action.do === "keydown") {
      (doc.activeElement || doc).dispatchEvent(
        keyEvent("keydown", action.code, action.key)
      );
      return;
    }
    if (action.do === "keyup") {
      (doc.activeElement || doc).dispatchEvent(
        keyEvent("keyup", action.code, action.key)
      );
      return;
    }
    if (action.do === "key") {
      const target = doc.activeElement || doc;
      target.dispatchEvent(keyEvent("keydown", action.code, action.key));
      target.dispatchEvent(keyEvent("keyup", action.code, action.key));
      return;
    }
    if (action.do === "type") {
      const target = doc.activeElement;
      if (!target || target === doc.body) throw new Error("typing target is missing");
      for (const character of String(action.text || "")) {
        const code = /[a-z]/i.test(character)
          ? "Key" + character.toUpperCase()
          : /\\d/.test(character)
            ? "Digit" + character
            : character === " "
              ? "Space"
              : "";
        target.dispatchEvent(keyEvent("keydown", code, character));
        if (target.isContentEditable) {
          target.textContent += character;
        } else if (
          typeof target.setRangeText === "function" &&
          typeof target.selectionStart === "number" &&
          typeof target.selectionEnd === "number"
        ) {
          target.setRangeText(
            character,
            target.selectionStart,
            target.selectionEnd,
            "end"
          );
        } else {
          target.value += character;
        }
        try {
          target.dispatchEvent(new win.InputEvent("input", {
            bubbles: true,
            data: character,
            inputType: "insertText"
          }));
        } catch {
          target.dispatchEvent(new win.Event("input", { bubbles: true }));
        }
        target.dispatchEvent(keyEvent("keyup", code, character));
      }
      return;
    }
    throw new Error("unsupported replay action " + action.do);
  })()`);
  await delay(60);
}

async function captureStage(path) {
  const clip = await evaluate(`(() => {
    document.querySelector("body > header").style.visibility = "hidden";
    const rect = document.querySelector("#stage").getBoundingClientRect();
    return {
      x: rect.left + scrollX,
      y: rect.top + scrollY,
      width: rect.width,
      height: rect.height,
      scale: 1
    };
  })()`);
  const screenshot = await cdp.command("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: true,
    clip,
  });
  const bytes = Buffer.from(screenshot.data, "base64");
  await writeFile(path, bytes);
  await evaluate(
    'document.querySelector("body > header").style.removeProperty("visibility")',
  );
  assert.equal(bytes.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
  return {
    bytes: bytes.length,
    sha256: sha256(bytes),
    width: bytes.readUInt32BE(16),
    height: bytes.readUInt32BE(20),
  };
}

async function captureEvidence({
  publicationId,
  viewport,
  checkpoint,
  actionIndex,
  resultSelector,
  metrics,
  actual,
  expected,
}) {
  const filename =
    `${publicationId}-${viewport.id}-${checkpoint}.png`;
  const screenshot = await captureStage(join(outputRoot, filename));
  assert.equal(
    screenshot.width,
    viewport.screenshotWidth,
    `${filename}: screenshot width drifted`,
  );
  assert.equal(
    screenshot.height,
    viewport.screenshotHeight,
    `${filename}: screenshot height drifted`,
  );
  return {
    publication: publicationId,
    viewport: viewport.id,
    checkpoint,
    actionIndex,
    resultSelector,
    metrics,
    state: {
      actualSha256: sha256(
        Buffer.from(canonicalJson(actual), "utf8"),
      ),
      expectedSha256: sha256(
        Buffer.from(canonicalJson(expected), "utf8"),
      ),
    },
    screenshot: {
      path: filename,
      ...screenshot,
    },
  };
}

function rectanglesIntersect(a, b) {
  return a.left < b.right && a.right > b.left &&
    a.top < b.bottom && a.bottom > b.top;
}

async function takeoverChrome() {
  return evaluate(`(() => {
    const host = document.querySelector("#host");
    const stage = document.querySelector("#stage");
    const frame = stage.querySelector("iframe");
    const lower = stage.querySelector(".l3");
    const replay = document.querySelector(".lbar");
    const toolbar = document.querySelector("#takebar");
    const button = document.querySelector("#b-take-control");
    const rect = element => {
      const value = element.getBoundingClientRect();
      return {
        left: value.left,
        top: value.top,
        right: value.right,
        bottom: value.bottom,
        width: value.width,
        height: value.height
      };
    };
    return {
      takeover: host.classList.contains("live-takeover"),
      state: host.dataset.takeover || "",
      stage: rect(stage),
      frame: rect(frame),
      lowerDisplay: lower ? getComputedStyle(lower).display : null,
      replayDisplay: replay ? getComputedStyle(replay).display : null,
      toolbar: {
        display: getComputedStyle(toolbar).display,
        rect: rect(toolbar)
      },
      button: {
        display: getComputedStyle(button).display,
        hidden: button.hidden,
        pressed: button.getAttribute("aria-pressed"),
        text: button.textContent.trim(),
        rect: rect(button)
      },
      progress: Number.parseFloat(
        document.querySelector("#ls i").style.width || "0"
      ),
      playText: document.querySelector("#lp").textContent.trim(),
      page: {
        innerHeight,
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth
      },
      topFocus: document.activeElement?.tagName || "",
      childFocus: frame.contentDocument?.activeElement?.id || "",
      childHasFocus: frame.contentDocument?.hasFocus() || false,
      frameSrc: frame.src,
      timeOrigin: frame.contentWindow.performance.timeOrigin,
      marker: frame.contentWindow.__workingProofsTakeoverMarker || "",
      keyLog: [...(frame.contentWindow.__workingProofsTakeoverKeys || [])]
    };
  })()`);
}

async function runFoglineTakeover(
  viewport,
  config,
  normalFrameWidth,
  handoffState,
) {
  await evaluate(`(() => {
    const frame = document.querySelector("#stage iframe");
    frame.contentWindow.__workingProofsTakeoverMarker =
      ${JSON.stringify(`fogline-${viewport.id}`)};
    frame.contentWindow.__workingProofsTakeoverKeys = [];
    frame.contentDocument.addEventListener("keydown", event => {
      frame.contentWindow.__workingProofsTakeoverKeys.push(event.code || event.key);
    }, true);
  })()`);
  const before = {
    state: await snapshot(config),
    chrome: await takeoverChrome(),
  };
  assert.deepEqual(before.state, handoffState);
  const appRequestsBefore = requests.filter(
    url => url === before.chrome.frameSrc,
  ).length;

  await dispatchRealOuterClick("#lp");
  await waitFor(
    'document.querySelector("#lp").textContent.includes("Pause") && ' +
      'Number.parseFloat(document.querySelector("#ls i").style.width || "0") > 0',
  );
  await dispatchRealOuterClick("#b-take-control");
  await waitFor(
    'document.querySelector("#host").classList.contains("live-takeover") && ' +
      'document.activeElement?.tagName === "IFRAME"',
  );
  const entered = await takeoverChrome();
  assert.equal(entered.state, "true");
  assert.equal(entered.button.text, "Show captions");
  assert.equal(entered.button.pressed, "true");
  assert.equal(entered.lowerDisplay, "none");
  assert.equal(entered.replayDisplay, "none");
  assert.ok(entered.playText.includes("Play"));
  assert.equal(entered.button.hidden, false);
  assert.notEqual(entered.button.display, "none");
  assert.ok(entered.button.rect.height >= 44);
  assert.ok(entered.toolbar.rect.height >= 52);
  assert.equal(
    rectanglesIntersect(entered.button.rect, entered.frame),
    false,
  );
  assert.equal(
    rectanglesIntersect(entered.toolbar.rect, entered.frame),
    false,
  );
  assert.ok(entered.toolbar.rect.top >= entered.frame.bottom);
  assert.ok(
    entered.toolbar.rect.bottom <= entered.page.innerHeight + 0.5,
  );
  assert.ok(entered.page.scrollWidth <= entered.page.clientWidth);
  assert.ok(
    Math.abs(entered.frame.width - normalFrameWidth) <= 0.5,
    `${viewport.id}: takeover changed the exact iframe width`,
  );
  assert.ok(
    entered.frame.height >= (viewport.id === "390" ? 600 : 520),
    `${viewport.id}: takeover iframe is only ${entered.frame.height}px tall`,
  );
  assert.equal(entered.topFocus, "IFRAME");
  assert.equal(entered.childHasFocus, true);
  assert.equal(entered.timeOrigin, before.chrome.timeOrigin);
  assert.equal(entered.marker, `fogline-${viewport.id}`);
  assert.deepEqual(await snapshot(config), handoffState);

  await delay(700);
  const paused = await takeoverChrome();
  assert.ok(
    Math.abs(paused.progress - entered.progress) <= 0.01,
    `${viewport.id}: replay clock advanced during takeover`,
  );

  await dispatchRealKey("KeyD");
  await waitFor(`(() => {
    const frame = document.querySelector("#stage iframe");
    return frame.contentDocument.querySelector("#step-value")
      ?.textContent.trim().startsWith("1 /");
  })()`);
  const movedState = await snapshot(config);
  const movedChrome = await takeoverChrome();
  assert.equal(movedState.seed, "FOG-7");
  assert.equal(movedState.facing, "E");
  assert.deepEqual(movedState.position, [1, 0]);
  assert.equal(movedState.steps, 1);
  assert.equal(movedState.trailLength, 1);
  assert.deepEqual(movedChrome.keyLog.slice(-1), ["KeyD"]);
  assert.equal(movedChrome.timeOrigin, before.chrome.timeOrigin);
  assert.ok(
    Math.abs(movedChrome.progress - entered.progress) <= 0.01,
    `${viewport.id}: real east move changed the replay clock`,
  );

  await dispatchRealOuterClick("#b-take-control");
  await waitFor(
    '!document.querySelector("#host").classList.contains("live-takeover") && ' +
      'document.querySelector("#lp").textContent.includes("Pause")',
  );
  await dispatchRealOuterClick("#lp");
  await waitFor('document.querySelector("#lp").textContent.includes("Play")');
  const shown = await takeoverChrome();
  assert.equal(shown.button.text, "Take control");
  assert.equal(shown.button.pressed, "false");
  assert.notEqual(shown.lowerDisplay, "none");
  assert.notEqual(shown.replayDisplay, "none");
  assert.equal(shown.timeOrigin, before.chrome.timeOrigin);
  assert.equal(shown.marker, `fogline-${viewport.id}`);
  assert.deepEqual(await snapshot(config), movedState);

  await dispatchRealOuterClick("#b-take-control");
  await waitFor(
    'document.querySelector("#host").classList.contains("live-takeover") && ' +
      'document.activeElement?.tagName === "IFRAME"',
  );
  await dispatchRealKey("Escape");
  await waitFor(
    '!document.querySelector("#host").classList.contains("live-takeover") && ' +
      'document.activeElement?.id === "b-take-control"',
  );
  const escaped = await takeoverChrome();
  assert.equal(escaped.button.text, "Take control");
  assert.notEqual(escaped.lowerDisplay, "none");
  assert.notEqual(escaped.replayDisplay, "none");
  assert.equal(escaped.timeOrigin, before.chrome.timeOrigin);
  assert.equal(escaped.marker, `fogline-${viewport.id}`);
  assert.deepEqual(await snapshot(config), movedState);
  const appRequestsAfter = requests.filter(
    url => url === before.chrome.frameSrc,
  ).length;
  assert.equal(
    appRequestsAfter,
    appRequestsBefore,
    `${viewport.id}: takeover exit reloaded Fogline`,
  );

  return {
    appRequestsBefore,
    appRequestsAfter,
    clock: {
      entered: entered.progress,
      after700ms: paused.progress,
      afterEast: movedChrome.progress,
    },
    eastMove: {
      direction: "E",
      code: "KeyD",
      position: movedState.position,
      steps: movedState.steps,
    },
    entered: {
      frame: entered.frame,
      toolbar: entered.toolbar.rect,
      button: entered.button.rect,
      lowerDisplay: entered.lowerDisplay,
      replayDisplay: entered.replayDisplay,
    },
    preserved: {
      marker: escaped.marker,
      stateAfterShowCaptions: canonicalJson(movedState) ===
        canonicalJson(await snapshot(config)),
      timeOrigin: escaped.timeOrigin === before.chrome.timeOrigin,
    },
    restoredBy: ["Show captions", "Escape"],
  };
}

function requiresVisibleActivation(action) {
  return action.do !== "scroll";
}

function waitForBrowserExit(timeout) {
  if (!browserRunning()) return Promise.resolve(true);
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
    if (!browserRunning()) onExit();
  });
}

async function pathExists(path) {
  try {
    await stat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

let report = null;
let cleanup = null;
try {
  const port = await activePort();
  const targets = await readJson(`http://127.0.0.1:${port}/json/list`);
  const page = targets.find((target) => target.type === "page");
  assert.ok(page?.webSocketDebuggerUrl, "browser exposed no page target");
  cdp = new Cdp(page.webSocketDebuggerUrl);
  await cdp.connect();
  await Promise.all([
    cdp.command("Page.enable"),
    cdp.command("Runtime.enable"),
    cdp.command("Log.enable"),
    cdp.command("Network.enable"),
  ]);
  cdp.on("Runtime.exceptionThrown", ({ exceptionDetails }) => {
    browserErrors.push(
      exceptionDetails.exception?.description || exceptionDetails.text,
    );
  });
  cdp.on("Runtime.consoleAPICalled", ({ type, args }) => {
    if (type === "error") {
      browserErrors.push(
        args.map(value => value.value ?? value.description ?? "").join(" "),
      );
    }
  });
  cdp.on("Log.entryAdded", ({ entry }) => {
    if (entry.level === "error" && entry.source === "javascript") {
      browserErrors.push(entry.text);
    }
  });
  cdp.on("Network.requestWillBeSent", ({ request }) => {
    requests.push(request.url);
    if (
      /^https?:/i.test(request.url) &&
      !request.url.startsWith(`${origin}/`)
    ) {
      externalRequests.push(request.url);
    }
  });
  cdp.on("Network.responseReceived", ({ response }) => {
    if (/^https?:/i.test(response.url) && response.status >= 400) {
      networkErrors.push(`${response.status} ${response.url}`);
    }
  });
  cdp.on("Network.loadingFailed", ({
    canceled,
    errorText,
  }) => {
    if (!canceled && errorText !== "net::ERR_ABORTED") {
      networkErrors.push(errorText);
    }
  });
  const version = await cdp.command("Browser.getVersion");
  const captures = [];
  const runs = [];

  for (const viewport of VIEWPORTS) {
    await setViewport(viewport);
    for (const publicationId of Object.keys(CONFIG)) {
      const config = CONFIG[publicationId];
      const aggregatePublication = publication(publicationId);
      const actions = aggregatePublication.live.scenes[0].actions;
      const record = indexRecord(publicationId);
      const evidencePath = referencedPath(
        evidenceIndexPath,
        record.evidence.path,
      );
      const evidence = JSON.parse(await readFile(evidencePath, "utf8"));
      const evidenceContract = config.evidence(evidence);
      const claims = new Map(
        evidenceContract.claims.map((claim) => [claim.id, claim]),
      );
      const checkpointMode =
        evidenceContract.checkpointMode || "after-action";
      const checkpoints = checkpointMode === "after-action"
        ? new Map(
            evidenceContract.checkpoints.map((checkpoint) => [
              checkpoint.afterAction,
              checkpoint,
            ]),
          )
        : null;
      let stateGatedCheckpointIndex = 0;

      assert.ok(
        evidenceContract.checkpoints.length >= 3,
        `${publicationId} must expose at least success, failure, and reset framing`,
      );
      if (evidenceContract.actionCount !== undefined) {
        assert.equal(
          actions.length,
          evidenceContract.actionCount,
          `${publicationId} action count diverged from evidence`,
        );
      }
      await openReplay(publicationId, config);
      const resetClaim =
        claims.get(config.openingClaim || "reset") ||
        claims.get(evidenceContract.checkpoints.at(-1).claim);
      assert.ok(resetClaim, `${publicationId} has no opening/reset claim`);
      const openingState = resetClaim.expectedState;
      await waitForSnapshot(
        config,
        openingState,
        `${publicationId}/${viewport.id}/opening`,
      );

      const geometrySamples = [];
      const supplementalGeometrySamples = [];
      const checkGeometry = (metrics, label) => {
        assertViewportGeometry(metrics, viewport, label);
        geometrySamples.push(metrics);
      };
      const checkSupplementalGeometry = (metrics, label) => {
        assertViewportGeometry(metrics, viewport, label);
        supplementalGeometrySamples.push(metrics);
      };
      const frame = await targetMetrics(
        aggregatePublication.live.scenes[0].ready.selector,
      );
      checkGeometry(
        frame,
        `${publicationId}/${viewport.id}/opening geometry`,
      );

      const activationVisibility = [];
      const framingVisibility = [];
      const checkpointResults = [];
      const captureResults = [];
      const timingSkews = [];
      const inputMethods = new Set();
      let finalPromptChecked = false;
      const addCapture = async ({
        checkpoint,
        actionIndex,
        selector,
        metrics,
        actual,
        expected,
      }) => {
        const entry = await captureEvidence({
          publicationId,
          viewport,
          checkpoint,
          actionIndex,
          resultSelector: selector,
          metrics,
          actual,
          expected,
        });
        captures.push(entry);
        captureResults.push(entry);
        return entry;
      };
      const resolveCheckpoint = async (
        checkpoint,
        observedState = null,
        resolvedActionIndex = checkpoint.afterAction ?? null,
        observedMetrics = null,
      ) => {
        const claim = claims.get(checkpoint.claim);
        assert.ok(claim, `missing evidence claim ${checkpoint.claim}`);
        const actual = observedState || await waitForSnapshot(
          config,
          claim.expectedState,
          `${publicationId}/${viewport.id}/${checkpoint.claim}`,
        );
        assert.deepEqual(
          actual,
          claim.expectedState,
          `${publicationId}/${viewport.id}/${checkpoint.claim}`,
        );
        const metrics =
          observedMetrics || await targetMetrics(checkpoint.selector);
        assertVisible(
          metrics,
          `${publicationId}/${viewport.id}/${checkpoint.claim} result`,
        );
        checkGeometry(
          metrics,
          `${publicationId}/${viewport.id}/${checkpoint.claim} geometry`,
        );
        const captureName = config.captureClaims
          ? config.captureClaims[checkpoint.claim]
          : checkpoint.claim;
        let capture = null;
        if (captureName) {
          capture = await addCapture({
            checkpoint: captureName,
            actionIndex: resolvedActionIndex,
            selector: checkpoint.selector,
            metrics,
            actual,
            expected: claim.expectedState,
          });
        }
        checkpointResults.push({
          checkpoint: checkpoint.claim,
          metrics,
          capture,
        });
      };

      if (publicationId === "maze-fogline") {
        const active = await targetMetrics(null, true);
        assert.equal(active.id, "maze-board");
        assertVisible(active, `${publicationId}/${viewport.id}/failure key`);
        checkSupplementalGeometry(
          active,
          `${publicationId}/${viewport.id}/failure key geometry`,
        );
        await dispatchRealKey("ArrowUp");
        await delay(60);
        const failureState = {
          ...openingState,
          facing: "N",
          status: "wall",
        };
        const actualFailure = await waitForSnapshot(
          config,
          failureState,
          `${publicationId}/${viewport.id}/failure`,
        );
        const failureMetrics = await targetMetrics("#status-message", true);
        assertVisible(
          failureMetrics,
          `${publicationId}/${viewport.id}/failure result`,
        );
        checkSupplementalGeometry(
          failureMetrics,
          `${publicationId}/${viewport.id}/failure geometry`,
        );
        await addCapture({
          checkpoint: "failure",
          actionIndex: null,
          selector: "#status-message",
          metrics: failureMetrics,
          actual: actualFailure,
          expected: failureState,
        });

        const restartMetrics = await targetMetrics("#restart-btn", true);
        assertVisible(
          restartMetrics,
          `${publicationId}/${viewport.id}/reset action`,
        );
        assert.equal(restartMetrics.disabled, false);
        checkSupplementalGeometry(
          restartMetrics,
          `${publicationId}/${viewport.id}/reset action geometry`,
        );
        await dispatchRealFrameClick("#restart-btn");
        await delay(60);
        const actualReset = await waitForSnapshot(
          config,
          openingState,
          `${publicationId}/${viewport.id}/reset`,
        );
        const resetMetrics = await targetMetrics("#reset-proof", true);
        assertVisible(
          resetMetrics,
          `${publicationId}/${viewport.id}/reset result`,
        );
        checkSupplementalGeometry(
          resetMetrics,
          `${publicationId}/${viewport.id}/reset geometry`,
        );
        await addCapture({
          checkpoint: "reset",
          actionIndex: null,
          selector: "#reset-proof",
          metrics: resetMetrics,
          actual: actualReset,
          expected: openingState,
        });
      }

      const replayStarted = performance.now();
      for (let actionIndex = 0; actionIndex < actions.length; actionIndex += 1) {
        const action = actions[actionIndex];
        const remaining =
          action.at * 1000 - (performance.now() - replayStarted);
        if (remaining > 0) await delay(remaining);
        const actualAt = performance.now() - replayStarted;
        assert.ok(
          actualAt + 5 >= action.at * 1000,
          `${publicationId}/${viewport.id} action ${actionIndex} ran early`,
        );
        timingSkews.push(actualAt - action.at * 1000);
        if (
          evidenceContract.maxActionLatenessSeconds !== undefined
        ) {
          assert.ok(
            actualAt - action.at * 1000 <=
              evidenceContract.maxActionLatenessSeconds * 1000,
            `${publicationId}/${viewport.id} action ${actionIndex} exceeded ` +
              `${evidenceContract.maxActionLatenessSeconds}s lateness`,
          );
        }
        if (requiresVisibleActivation(action)) {
          const metrics = await targetMetrics(
            action.do === "click" ? action.selector : null,
            true,
          );
          assertVisible(
            metrics,
            `${publicationId}/${viewport.id} action ${actionIndex}`,
          );
          checkGeometry(
            metrics,
            `${publicationId}/${viewport.id} action ${actionIndex} geometry`,
          );
          assert.equal(
            metrics.disabled,
            false,
            `${publicationId}/${viewport.id} action ${actionIndex} is disabled`,
          );
          activationVisibility.push({
            actionIndex,
            do: action.do,
            selector: action.do === "click" ? action.selector : `#${metrics.id}`,
            metrics,
          });
        }

        await applyAction(action, config.realInput);
        inputMethods.add(
          config.realInput
            ? action.do === "click"
              ? "cdp-mouse"
              : action.do === "scroll"
                ? "cdp-scroll"
                : "cdp-keyboard"
            : "dom-events",
        );
        if (action.do === "scroll") {
          const metrics = await targetMetrics(action.selector);
          assertVisible(
            metrics,
            `${publicationId}/${viewport.id} framing action ${actionIndex}`,
          );
          checkGeometry(
            metrics,
            `${publicationId}/${viewport.id} framing action ` +
              `${actionIndex} geometry`,
          );
          framingVisibility.push({
            actionIndex,
            selector: action.selector,
            metrics,
          });
        }

        if (
          publicationId === "maze-fogline" &&
          actionIndex === 1
        ) {
          await waitFor(`(() => {
            const frame = document.querySelector("#stage iframe");
            const text = frame.contentDocument
              .querySelector("#challenge-status")?.textContent || "";
            return /Challenge fragment (copied|ready and selected)/.test(text);
          })()`);
          const challengeState = await waitForSnapshot(
            config,
            openingState,
            `${publicationId}/${viewport.id}/challenge`,
          );
          const challengeMetrics = await targetMetrics(
            "#challenge-status",
            true,
          );
          assertVisible(
            challengeMetrics,
            `${publicationId}/${viewport.id}/challenge result`,
          );
          checkSupplementalGeometry(
            challengeMetrics,
            `${publicationId}/${viewport.id}/challenge geometry`,
          );
          await addCapture({
            checkpoint: "challenge",
            actionIndex,
            selector: "#challenge-status",
            metrics: challengeMetrics,
            actual: challengeState,
            expected: openingState,
          });
        }

        if (evidenceContract.finalPrompt?.afterAction === actionIndex) {
          const prompt = evidenceContract.finalPrompt;
          const metrics = await targetMetrics(prompt.selector);
          assertVisible(
            metrics,
            `${publicationId}/${viewport.id} final prompt`,
          );
          checkGeometry(
            metrics,
            `${publicationId}/${viewport.id} final prompt geometry`,
          );
          const promptText = await evaluate(`(() => {
            const frame = document.querySelector("#stage iframe");
            return frame.contentDocument
              .querySelector(${JSON.stringify(prompt.selector)})
              ?.textContent;
          })()`);
          assert.equal(promptText, prompt.text);
          await waitForSnapshot(
            config,
            resetClaim.expectedState,
            `${publicationId}/${viewport.id}/final prompt state`,
          );
          finalPromptChecked = true;
        }

        if (checkpointMode === "after-action") {
          const checkpoint = checkpoints.get(actionIndex);
          if (checkpoint) await resolveCheckpoint(checkpoint);
        } else {
          while (
            stateGatedCheckpointIndex <
            evidenceContract.checkpoints.length
          ) {
            const checkpoint =
              evidenceContract.checkpoints[stateGatedCheckpointIndex];
            const observedAt =
              (performance.now() - replayStarted) / 1000;
            const lateness =
              evidenceContract.maxActionLatenessSeconds || 0;
            assert.ok(
              observedAt <= checkpoint.timeWindow.end + lateness,
              `${publicationId}/${viewport.id} checkpoint ` +
                `${checkpoint.claim} missed its time window`,
            );
            if (observedAt < checkpoint.timeWindow.start) break;
            const claim = claims.get(checkpoint.claim);
            assert.ok(claim, `missing evidence claim ${checkpoint.claim}`);
            const actual = await snapshot(config);
            if (
              canonicalJson(actual) !==
              canonicalJson(claim.expectedState)
            ) {
              break;
            }
            const metrics = await targetMetrics(checkpoint.selector);
            if (!metrics.visible) break;
            await resolveCheckpoint(
              checkpoint,
              actual,
              actionIndex,
              metrics,
            );
            stateGatedCheckpointIndex += 1;
          }
        }
      }

      if (checkpointMode === "state-gated") {
        assert.equal(
          stateGatedCheckpointIndex,
          evidenceContract.checkpoints.length,
          `${publicationId}/${viewport.id} left state-gated checkpoints unresolved`,
        );
      }
      assert.equal(
        checkpointResults.length,
        evidenceContract.checkpoints.length,
      );
      assert.equal(
        finalPromptChecked,
        Boolean(evidenceContract.finalPrompt),
      );
      assert.equal(
        geometrySamples.length,
        1 +
          actions.length +
          evidenceContract.checkpoints.length +
          (evidenceContract.finalPrompt ? 1 : 0),
      );
      let takeover = null;
      if (publicationId === "maze-fogline") {
        takeover = await runFoglineTakeover(
          viewport,
          config,
          frame.frameWidth,
          claims.get("handoff").expectedState,
        );
      }
      runs.push({
        publication: publicationId,
        viewport: viewport.id,
        actionCount: actions.length,
        frameWidth: frame.frameWidth,
        frameHeight: frame.frameHeight,
        safeHeight: checkpointResults.map((entry) => entry.metrics.safeHeight),
        activationsChecked: activationVisibility.length,
        framingActionsChecked: framingVisibility.length,
        finalPromptChecked,
        captureCheckpoints: captureResults.map(
          entry => entry.checkpoint,
        ),
        exactTiming: true,
        maxTimingSkewMs: Math.round(Math.max(...timingSkews)),
        geometryChecks: geometrySamples.length,
        supplementalGeometryChecks:
          supplementalGeometrySamples.length,
        inputMethods: [...inputMethods].sort(),
        frameWidthsChecked: [
          ...new Set(geometrySamples.map(sample => sample.frameWidth)),
        ],
        stageWidthsChecked: [
          ...new Set(geometrySamples.map(sample => sample.stageWidth)),
        ],
        outerClientWidthsChecked: [
          ...new Set(geometrySamples.map(sample => sample.outerClientWidth)),
        ],
        scrollbarWidthsChecked: [
          ...new Set(
            geometrySamples.map(sample => sample.outerScrollbarWidth),
          ),
        ],
        checkpoints: checkpointResults.map((entry) => entry.checkpoint),
        takeover,
      });
    }
  }

  assert.equal(runs.length, VIEWPORTS.length * Object.keys(CONFIG).length);
  assert.equal(
    captures.length,
    runs.reduce(
      (total, run) => total + run.captureCheckpoints.length,
      0,
    ),
  );
  assert.deepEqual(browserErrors, []);
  assert.deepEqual(networkErrors, []);
  assert.deepEqual(externalRequests, []);
  const manifest = {
    schema: "working-proofs-viewport-evidence/1.0",
    browser: version.product,
    channel: channel.id,
    viewports: VIEWPORTS.map(({
      id,
      pageWidth,
      pageHeight,
      frameWidth,
      frameHeight,
      stageWidth,
      stageHeight,
      screenshotWidth,
      screenshotHeight,
      outerClientWidths,
      scrollbarWidths,
    }) => ({
      id,
      pageWidth,
      pageHeight,
      frameWidth,
      frameHeight,
      stageWidth,
      stageHeight,
      screenshotWidth,
      screenshotHeight,
      outerClientWidths,
      scrollbarWidths,
    })),
    captures,
  };
  await writeFile(
    join(outputRoot, "manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
  report = {
    browser: version.product,
    captures: captures.length,
    errors: browserErrors,
    externalRequests,
    networkErrors,
    output: relative(ROOT, outputRoot),
    runs,
  };
} finally {
  if (cdp) cdp.close();
  if (browserRunning()) browser.kill();
  let browserExited = await waitForBrowserExit(5_000);
  if (!browserExited) {
    browser.kill("SIGKILL");
    browserExited = await waitForBrowserExit(5_000);
  }
  assert.equal(browserExited, true, "browser process did not terminate");

  await new Promise((resolveClose, rejectClose) => {
    server.close(error => {
      if (error) rejectClose(error);
      else resolveClose();
    });
  });
  await rm(profilePath, {
    recursive: true,
    force: true,
    maxRetries: 12,
    retryDelay: 150,
  });
  const profileRemoved = !(await pathExists(profilePath));
  assert.equal(profileRemoved, true, "browser profile cleanup failed");
  cleanup = {
    browserExited,
    profileRemoved,
    serverClosed: !server.listening,
  };
}

assert.ok(report, "aggregate browser report was not produced");
process.stdout.write(JSON.stringify({ ...report, cleanup }));
