import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, rm } from "node:fs/promises";
import { createServer } from "node:net";

const [browserExecutable, appUrl, actionsBase64, profileDirectory] =
  process.argv.slice(2);

if (!browserExecutable || !appUrl || !actionsBase64 || !profileDirectory) {
  throw new Error(
    "usage: node frame_0002_09_browser.mjs <browser> <app-url> <actions-base64> <profile-directory>",
  );
}

const actions = JSON.parse(Buffer.from(actionsBase64, "base64").toString("utf8"));
if (
  !Array.isArray(actions) ||
  actions.some((action) => !["click", "scroll"].includes(action.do))
) {
  throw new Error("browser replay only accepts authored click and scroll actions");
}
for (const action of actions) {
  if (typeof action.selector !== "string" || !action.selector.startsWith("#")) {
    throw new Error("browser replay actions require stable id selectors");
  }
  if ("from" in action || "to" in action) {
    throw new Error("browser replay actions cannot use coordinates");
  }
}

class CdpClient {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Set();
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) {
          pending.reject(
            new Error(
              `${pending.method}: ${message.error.message || JSON.stringify(message.error)}`,
            ),
          );
        } else {
          pending.resolve(message.result || {});
        }
        return;
      }
      for (const listener of this.listeners) listener(message);
    });
  }

  static connect(url) {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(url);
      const timeout = setTimeout(
        () => reject(new Error("timed out connecting to browser DevTools")),
        15_000,
      );
      socket.addEventListener("open", () => {
        clearTimeout(timeout);
        resolve(new CdpClient(socket));
      });
      socket.addEventListener("error", () => {
        clearTimeout(timeout);
        reject(new Error("browser DevTools WebSocket failed"));
      });
    });
  }

  send(method, params = {}, sessionId = undefined) {
    const id = this.nextId++;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { method, resolve, reject });
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

async function waitForDevTools(child, port, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`browser exited before DevTools was ready (${child.exitCode})`);
    }
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) {
        const version = await response.json();
        if (version.webSocketDebuggerUrl) return version.webSocketDebuggerUrl;
      }
    } catch {}
    await new Promise(resolveDelay => setTimeout(resolveDelay, 75));
  }
  throw new Error("timed out waiting for explicit browser DevTools port");
}

async function evaluate(client, sessionId, expression) {
  const response = await client.send(
    "Runtime.evaluate",
    {
      expression,
      returnByValue: true,
      awaitPromise: true,
    },
    sessionId,
  );
  if (response.exceptionDetails) {
    const detail =
      response.exceptionDetails.exception?.description ||
      response.exceptionDetails.text ||
      "unknown browser exception";
    throw new Error(detail);
  }
  return response.result?.value;
}

async function waitForApp(client, sessionId) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    try {
      const ready = await evaluate(
        client,
        sessionId,
        'document.readyState === "complete" && Boolean(window.vectorIconSystem)',
      );
      if (ready) return;
    } catch {
      // Navigation can briefly invalidate the execution context.
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("vector icon application did not become ready");
}

function sha256(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function geometrySignature(geometry) {
  return geometry
    .map((icon) =>
      [
        icon.name,
        icon.viewBox,
        icon.stroke,
        icon.linecap,
        icon.linejoin,
        icon.paths.join(";"),
      ].join("|"),
    )
    .join("\n");
}

function summarizeCapture(raw) {
  const { spriteText, generatedGeometry, ...capture } = raw;
  const iconGeometrySha256 = generatedGeometry.map((icon) => ({
    name: icon.name,
    sha256: sha256(geometrySignature([icon])),
  }));
  return {
    ...capture,
    spriteTextSha256: sha256(spriteText),
    spriteBytes: Buffer.byteLength(spriteText, "utf8"),
    generatedGeometrySha256: sha256(geometrySignature(generatedGeometry)),
    generatedIconCount: generatedGeometry.length,
    generatedStrokeWidths: generatedGeometry.map((icon) => icon.stroke),
    iconGeometrySha256,
  };
}

function assertPositivePath(initial, steps) {
  const expectedPrefix = [
    "#stroke-15-btn",
    "#regenerate-btn",
    "#stroke-2-btn",
    "#regenerate-btn",
    "#export-btn",
  ];
  const actualPrefix = steps.slice(0, expectedPrefix.length).map(
    (step) => step.selector,
  );
  const require = (condition, message) => {
    if (!condition) {
      throw new Error(`positive live path assertion failed: ${message}`);
    }
  };
  require(
    JSON.stringify(actualPrefix) === JSON.stringify(expectedPrefix),
    `expected ${expectedPrefix.join(" -> ")}, got ${actualPrefix.join(" -> ")}`,
  );

  const [drafted, edited, returnDraft, returned, exported] = steps;
  require(initial.state.accepted.rules.stroke === 2, "initial stroke is not 2");
  require(drafted.state.draftStroke === 1.5, "draft stroke did not change to 1.5");
  require(
    drafted.state.accepted.rules.stroke === 2,
    "drafting 1.5 mutated accepted geometry before regeneration",
  );
  require(
    edited.state.accepted.rules.stroke === 1.5,
    "first regeneration did not accept stroke 1.5",
  );
  require(
    edited.generatedIconCount === 6
      && edited.generatedStrokeWidths.every((stroke) => stroke === "1.5"),
    "first regeneration did not update all six generated geometries to 1.5",
  );
  require(
    edited.generatedGeometrySha256
      === edited.state.accepted.generatedGeometrySha256,
    "browser geometry hash does not match the 1.5 contract",
  );
  require(
    edited.spriteTextSha256 === edited.state.accepted.spriteSha256,
    "browser sprite hash does not match the 1.5 contract",
  );
  require(
    edited.generatedGeometrySha256 !== initial.generatedGeometrySha256,
    "generated geometry hash did not change at 1.5",
  );
  require(
    edited.spriteTextSha256 !== initial.spriteTextSha256,
    "generated sprite hash did not change at 1.5",
  );
  const initialIcons = new Map(
    initial.iconGeometrySha256.map((icon) => [icon.name, icon.sha256]),
  );
  const changedIconCount = edited.iconGeometrySha256.filter(
    (icon) => initialIcons.get(icon.name) !== icon.sha256,
  ).length;
  require(changedIconCount === 6, `only ${changedIconCount} generated icons changed`);

  require(returnDraft.state.draftStroke === 2, "draft stroke did not return to 2");
  require(
    returnDraft.state.accepted.rules.stroke === 1.5,
    "return draft mutated accepted geometry before regeneration",
  );
  require(
    returned.state.accepted.rules.stroke === 2,
    "second regeneration did not return accepted stroke to 2",
  );
  require(
    returned.generatedGeometrySha256 === initial.generatedGeometrySha256,
    "returned geometry is not the exact opening 2 px geometry",
  );
  require(
    returned.spriteTextSha256 === initial.spriteTextSha256,
    "returned sprite is not the exact opening 2 px sprite",
  );
  require(
    returned.state.lastExport === null,
    "passing reference was exported before the deliberate return regeneration",
  );
  require(
    exported.state.lastExport?.sha256 === returned.spriteTextSha256,
    "export is not bound to the returned passing sprite",
  );

  return {
    initialStroke: initial.state.accepted.rules.stroke,
    editedStroke: edited.state.accepted.rules.stroke,
    returnedStroke: returned.state.accepted.rules.stroke,
    changedIconCount,
    initialGeometrySha256: initial.generatedGeometrySha256,
    editedGeometrySha256: edited.generatedGeometrySha256,
    returnedGeometrySha256: returned.generatedGeometrySha256,
    initialSpriteSha256: initial.spriteTextSha256,
    editedSpriteSha256: edited.spriteTextSha256,
    returnedSpriteSha256: returned.spriteTextSha256,
  };
}

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

const browserArguments = [
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
  "--remote-allow-origins=*",
  `--remote-debugging-port=${debugPort}`,
  `--user-data-dir=${profileDirectory}`,
  "about:blank",
];

await rm(profileDirectory, { recursive: true, force: true });
await mkdir(profileDirectory, { recursive: true });

const browser = spawn(browserExecutable, browserArguments, {
  stdio: ["ignore", "ignore", "pipe"],
  windowsHide: true,
});

let client;
let targetId;
try {
  const endpoint = await waitForDevTools(browser, debugPort);
  client = await CdpClient.connect(endpoint);
  const version = await client.send("Browser.getVersion");
  ({ targetId } = await client.send("Target.createTarget", { url: appUrl }));
  const attached = await client.send("Target.attachToTarget", {
    targetId,
    flatten: true,
  });
  const sessionId = attached.sessionId;
  const consoleErrors = [];
  const pageErrors = [];
  client.onEvent((message) => {
    if (message.sessionId !== sessionId) return;
    if (
      message.method === "Runtime.consoleAPICalled" &&
      message.params.type === "error"
    ) {
      consoleErrors.push(
        message.params.args
          .map((argument) => argument.value || argument.description || "")
          .join(" "),
      );
    }
    if (message.method === "Runtime.exceptionThrown") {
      pageErrors.push(
        message.params.exceptionDetails.exception?.description ||
          message.params.exceptionDetails.text,
      );
    }
  });
  await client.send("Runtime.enable", {}, sessionId);
  await client.send("Page.enable", {}, sessionId);
  await waitForApp(client, sessionId);

  const captureExpression = `({
    state: window.vectorIconSystem.getState(),
    hashText: document.querySelector("#sprite-hash").textContent,
    diffText: document.querySelector("#diff-value").textContent,
    statusText: document.querySelector("#status-label").textContent,
    exportDisabled: document.querySelector("#export-btn").disabled,
    offGridDisabled: document.querySelector("#off-grid-btn").disabled,
    spriteText: document.querySelector("#sprite-output").value,
    generatedGeometry: Array.from(
      document.querySelectorAll("[data-icon-preview]")
    ).map((svg) => {
      const group = svg.querySelector("g");
      return {
        name: svg.dataset.iconPreview,
        viewBox: svg.getAttribute("viewBox"),
        stroke: group.getAttribute("stroke-width"),
        linecap: group.getAttribute("stroke-linecap"),
        linejoin: group.getAttribute("stroke-linejoin"),
        paths: Array.from(group.querySelectorAll("path")).map(
          (path) => path.getAttribute("d")
        )
      };
    })
  })`;
  const initial = summarizeCapture(
    await evaluate(client, sessionId, captureExpression),
  );
  const supported = await evaluate(
    client,
    sessionId,
    "window.vectorIconSystem.supportedStrokes",
  );
  const nondefault = [];
  for (const stroke of supported.filter((value) => value !== 2)) {
    const result = summarizeCapture(
      await evaluate(
        client,
        sessionId,
        `(() => {
        document.querySelector("#restore-btn").click();
        const input = document.querySelector("#stroke-rule");
        input.value = ${JSON.stringify(String(stroke))};
        input.dispatchEvent(new Event("change", { bubbles: true }));
        document.querySelector("#regenerate-btn").click();
        return ${captureExpression};
      })()`,
      ),
    );
    nondefault.push({ stroke, ...result });
  }

  await evaluate(
    client,
    sessionId,
    'document.querySelector("#restore-btn").click()',
  );
  const steps = [];
  const framing = [];
  for (let actionIndex = 0; actionIndex < actions.length; actionIndex += 1) {
    const action = actions[actionIndex];
    if (action.do === "scroll") {
      const result = await evaluate(
        client,
        sessionId,
        `(() => {
          const target = document.querySelector(${JSON.stringify(action.selector)});
          if (!target) throw new Error("missing replay selector");
          target.scrollIntoView({
            block: ${JSON.stringify(action.block || "center")},
            inline: "nearest",
            behavior: "auto"
          });
          const bounds = target.getBoundingClientRect();
          return {
            top: bounds.top,
            bottom: bounds.bottom,
            width: bounds.width,
            height: bounds.height,
            viewportWidth: innerWidth,
            viewportHeight: innerHeight
          };
        })()`,
      );
      framing.push({
        actionIndex,
        selector: action.selector,
        ...result,
      });
      continue;
    }
    const result = summarizeCapture(
      await evaluate(
        client,
        sessionId,
        `(() => {
          const target = document.querySelector(${JSON.stringify(action.selector)});
          if (!target) throw new Error("missing replay selector");
          target.click();
          return ${captureExpression};
        })()`,
      ),
    );
    steps.push({ actionIndex, selector: action.selector, ...result });
  }
  const positivePath = assertPositivePath(initial, steps);

  process.stdout.write(
    JSON.stringify({
      browser: version.product,
      initial,
      nondefault,
      actionCount: actions.length,
      framing,
      steps,
      positivePath,
      consoleErrors,
      pageErrors,
    }),
  );
  await client.send("Target.closeTarget", { targetId });
  targetId = undefined;
  await client.send("Browser.close");
} finally {
  if (client) {
    if (targetId) {
      await client.send("Target.closeTarget", { targetId }).catch(() => {});
    }
    client.close();
  }
  await new Promise((resolve) => {
    if (browser.exitCode !== null) {
      resolve();
      return;
    }
    const timeout = setTimeout(() => {
      browser.kill("SIGKILL");
      resolve();
    }, 5_000);
    browser.once("exit", () => {
      clearTimeout(timeout);
      resolve();
    });
  });
  await rm(profileDirectory, { recursive: true, force: true });
}
