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
const channel = JSON.parse(await readFile(channelPath, "utf8"));
const evidenceIndex = JSON.parse(await readFile(evidenceIndexPath, "utf8"));

const VIEWPORTS = [
  {
    id: "desktop",
    pageWidth: 1387,
    pageHeight: 900,
    minFrameWidth: 958,
    maxFrameWidth: 962,
  },
  {
    id: "390",
    pageWidth: 435,
    pageHeight: 900,
    minFrameWidth: 388,
    maxFrameWidth: 392,
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
};

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
  return fileURLToPath(new URL(reference, pathToFileURL(basePath)));
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
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

async function activePort(timeout = 45_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (browser.exitCode !== null) {
      throw new Error(`browser exited before DevTools was ready: ${browser.exitCode}`);
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
  await waitFor(
    `Boolean(document.querySelector("#stage iframe")?.contentWindow?.[${JSON.stringify(
      config.contract,
    )}])`,
  );
  await delay(100);
}

async function snapshot(config) {
  return evaluate(`(() => {
    const frame = document.querySelector("#stage iframe");
    return frame.contentWindow[${JSON.stringify(config.contract)}][${JSON.stringify(
      config.snapshotMethod,
    )}]();
  })()`);
}

async function targetMetrics(selector = null) {
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
    const rect = target.getBoundingClientRect();
    const safeHeight = Math.max(
      0,
      Math.min(
        frameRect.height,
        lowerRect ? lowerRect.top - frameRect.top : frameRect.height
      )
    );
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
    return {
      id: target.id,
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
      visible: visibleWidth >= requiredWidth && visibleHeight >= requiredHeight,
      frameWidth: frameRect.width,
      frameHeight: frameRect.height,
      stageWidth: stageRect.width,
      stageHeight: stageRect.height,
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

function keyFromCode(code) {
  const letter = /^Key([A-Z])$/.exec(code);
  if (letter) return letter[1].toLowerCase();
  const digit = /^Digit(\d)$/.exec(code);
  if (digit) return digit[1];
  if (code === "Space") return " ";
  return String(code || "").replace(/(Left|Right)$/, "");
}

async function applyAction(action) {
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
      target.scrollIntoView({
        block: action.block || "center",
        inline: "nearest",
        behavior: "auto"
      });
      return;
    }
    if (action.do === "click") {
      const target = doc.querySelector(action.selector);
      if (!target) throw new Error("missing click target " + action.selector);
      if (target.disabled || target.getAttribute("aria-disabled") === "true") {
        throw new Error("disabled click target " + action.selector);
      }
      target.click();
      return;
    }
    if (action.do === "keydown") {
      doc.dispatchEvent(keyEvent("keydown", action.code, action.key));
      return;
    }
    if (action.do === "keyup") {
      doc.dispatchEvent(keyEvent("keyup", action.code, action.key));
      return;
    }
    if (action.do === "key") {
      doc.dispatchEvent(keyEvent("keydown", action.code, action.key));
      doc.dispatchEvent(keyEvent("keyup", action.code, action.key));
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
        if (target.isContentEditable) target.textContent += character;
        else target.value += character;
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

function requiresVisibleActivation(action) {
  return (
    action.do === "click" ||
    action.do === "type" ||
    (action.do === "key" && /^(Enter|NumpadEnter)$/.test(action.code || ""))
  );
}

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
  ]);
  cdp.on("Runtime.exceptionThrown", ({ exceptionDetails }) => {
    browserErrors.push(
      exceptionDetails.exception?.description || exceptionDetails.text,
    );
  });
  cdp.on("Log.entryAdded", ({ entry }) => {
    if (entry.level === "error" && entry.source === "javascript") {
      browserErrors.push(entry.text);
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
      const checkpoints = new Map(
        evidenceContract.checkpoints.map((checkpoint) => [
          checkpoint.afterAction,
          checkpoint,
        ]),
      );

      assert.equal(
        evidenceContract.checkpoints.length,
        3,
        `${publicationId} must expose success, failure, and reset framing`,
      );
      await openReplay(publicationId, config);
      const resetClaim =
        claims.get("reset") ||
        claims.get(evidenceContract.checkpoints.at(-1).claim);
      assert.deepEqual(await snapshot(config), resetClaim.expectedState);

      const frame = await targetMetrics(
        aggregatePublication.live.scenes[0].ready.selector,
      );
      assert.ok(
        frame.frameWidth >= viewport.minFrameWidth &&
          frame.frameWidth <= viewport.maxFrameWidth,
        `${viewport.id} iframe width is outside the player-stage target: ` +
          JSON.stringify(frame),
      );

      const activationVisibility = [];
      const checkpointResults = [];
      for (let actionIndex = 0; actionIndex < actions.length; actionIndex += 1) {
        const action = actions[actionIndex];
        if (requiresVisibleActivation(action)) {
          const metrics = await targetMetrics(
            action.do === "click" ? action.selector : null,
          );
          assertVisible(
            metrics,
            `${publicationId}/${viewport.id} action ${actionIndex}`,
          );
          activationVisibility.push({
            actionIndex,
            do: action.do,
            selector: action.do === "click" ? action.selector : `#${metrics.id}`,
            metrics,
          });
        }

        await applyAction(action);
        const checkpoint = checkpoints.get(actionIndex);
        if (!checkpoint) continue;

        const actual = await snapshot(config);
        const claim = claims.get(checkpoint.claim);
        assert.ok(claim, `missing evidence claim ${checkpoint.claim}`);
        assert.deepEqual(
          actual,
          claim.expectedState,
          `${publicationId}/${viewport.id}/${checkpoint.claim}`,
        );
        const metrics = await targetMetrics(checkpoint.selector);
        assertVisible(
          metrics,
          `${publicationId}/${viewport.id}/${checkpoint.claim} result`,
        );
        const filename =
          `${publicationId}-${viewport.id}-${checkpoint.claim}.png`;
        const screenshot = await captureStage(join(outputRoot, filename));
        const entry = {
          publication: publicationId,
          viewport: viewport.id,
          checkpoint: checkpoint.claim,
          actionIndex,
          resultSelector: checkpoint.selector,
          metrics,
          screenshot: {
            path: filename,
            ...screenshot,
          },
        };
        captures.push(entry);
        checkpointResults.push(entry);
      }

      assert.equal(checkpointResults.length, 3);
      runs.push({
        publication: publicationId,
        viewport: viewport.id,
        actionCount: actions.length,
        frameWidth: frame.frameWidth,
        frameHeight: frame.frameHeight,
        safeHeight: checkpointResults.map((entry) => entry.metrics.safeHeight),
        activationsChecked: activationVisibility.length,
        checkpoints: checkpointResults.map((entry) => entry.checkpoint),
      });
    }
  }

  assert.equal(captures.length, 18);
  assert.deepEqual(browserErrors, []);
  const manifest = {
    schema: "working-proofs-viewport-evidence/1.0",
    browser: version.product,
    channel: channel.id,
    viewports: VIEWPORTS.map(({ id, pageWidth, pageHeight }) => ({
      id,
      pageWidth,
      pageHeight,
    })),
    captures,
  };
  await writeFile(
    join(outputRoot, "manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
  process.stdout.write(
    JSON.stringify({
      browser: version.product,
      captures: captures.length,
      errors: browserErrors,
      output: relative(ROOT, outputRoot),
      runs,
    }),
  );
} finally {
  if (cdp) cdp.close();
  if (browser.exitCode === null) browser.kill();
  await new Promise((resolveExit) => {
    if (browser.exitCode !== null) {
      resolveExit();
      return;
    }
    const timeout = setTimeout(resolveExit, 3_000);
    browser.once("exit", () => {
      clearTimeout(timeout);
      resolveExit();
    });
  });
  server.close();
  await new Promise((resolveClose) => server.once("close", resolveClose));
  try {
    await rm(profilePath, {
      recursive: true,
      force: true,
      maxRetries: 12,
      retryDelay: 150,
    });
  } catch {}
}
