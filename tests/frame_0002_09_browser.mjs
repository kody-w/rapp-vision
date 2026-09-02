import { spawn } from "node:child_process";
import { mkdir, rm } from "node:fs/promises";
import readline from "node:readline";

const [browserExecutable, appUrl, actionsBase64, profileDirectory] =
  process.argv.slice(2);

if (!browserExecutable || !appUrl || !actionsBase64 || !profileDirectory) {
  throw new Error(
    "usage: node frame_0002_09_browser.mjs <browser> <app-url> <actions-base64> <profile-directory>",
  );
}

const actions = JSON.parse(Buffer.from(actionsBase64, "base64").toString("utf8"));
if (!Array.isArray(actions) || actions.some((action) => action.do !== "click")) {
  throw new Error("browser replay only accepts authored click actions");
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

function waitForDevTools(child) {
  return new Promise((resolve, reject) => {
    const lines = [];
    const reader = readline.createInterface({ input: child.stderr });
    const timeout = setTimeout(() => {
      reader.close();
      reject(
        new Error(
          `timed out waiting for DevTools endpoint: ${lines.join(" | ")}`,
        ),
      );
    }, 20_000);
    reader.on("line", (line) => {
      lines.push(line);
      const match = line.match(/DevTools listening on (ws:\/\/\S+)/);
      if (match) {
        clearTimeout(timeout);
        reader.close();
        resolve(match[1]);
      }
    });
    child.once("exit", (code) => {
      clearTimeout(timeout);
      reader.close();
      reject(
        new Error(
          `browser exited before DevTools was ready (${code}): ${lines.join(" | ")}`,
        ),
      );
    });
  });
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
  "--remote-debugging-port=0",
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
  const endpoint = await waitForDevTools(browser);
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
    offGridDisabled: document.querySelector("#off-grid-btn").disabled
  })`;
  const initial = await evaluate(client, sessionId, captureExpression);
  const supported = await evaluate(
    client,
    sessionId,
    "window.vectorIconSystem.supportedStrokes",
  );
  const nondefault = [];
  for (const stroke of supported.filter((value) => value !== 2)) {
    const result = await evaluate(
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
    );
    nondefault.push({ stroke, ...result });
  }

  await evaluate(
    client,
    sessionId,
    'document.querySelector("#restore-btn").click()',
  );
  const steps = [];
  for (const action of actions) {
    const result = await evaluate(
      client,
      sessionId,
      `(() => {
        const target = document.querySelector(${JSON.stringify(action.selector)});
        if (!target) throw new Error("missing replay selector");
        target.click();
        return ${captureExpression};
      })()`,
    );
    steps.push({ selector: action.selector, ...result });
  }

  process.stdout.write(
    JSON.stringify({
      browser: version.product,
      initial,
      nondefault,
      steps,
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
