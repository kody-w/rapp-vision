#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
  CdpClient,
  delay,
  discoverBrowser,
  dispatchKey,
  dispatchMouseClick,
  evaluate,
  removeProfile,
  reservePort,
  settle,
  waitForDevTools,
  waitForExit,
  waitForReady,
} from "./verify_dom.mjs";

function parseOptions(argv) {
  const options = {
    app: null,
    browser: null,
    continuity: null,
    ffmpeg: null,
    output: null,
    plan: null,
    profile: null,
    sampleDir: null,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    const key = {
      "--app": "app",
      "--browser": "browser",
      "--continuity": "continuity",
      "--ffmpeg": "ffmpeg",
      "--output": "output",
      "--plan": "plan",
      "--profile": "profile",
      "--sample-dir": "sampleDir",
    }[argument];
    if (!key || index + 1 >= argv.length) {
      throw new Error(
        "usage: node render_live.mjs --app PATH --browser PATH " +
          "--continuity PATH --ffmpeg PATH --output PATH --plan PATH " +
          "--profile PATH --sample-dir PATH"
      );
    }
    options[key] = argv[index + 1];
    index += 1;
  }
  for (const [key, value] of Object.entries(options)) {
    if (!value) throw new Error(`missing required option --${key}`);
  }
  return options;
}

function phaseAt(plan, frame) {
  const phase = plan.phases.find(
    item => item.startFrame <= frame && frame < item.endFrame
  );
  assert(phase, `film plan has no phase for frame ${frame}`);
  return phase;
}

async function setFilmPhase(cdp, phase) {
  await evaluate(
    cdp,
    `(() => {
      document.documentElement.dataset.filmPhase = ${JSON.stringify(phase.name)};
      document.querySelector("#film-phase").textContent =
        ${JSON.stringify(phase.name.replaceAll("-", " "))};
      document.querySelector("#film-callout").textContent =
        ${JSON.stringify(phase.callout)};
      document.querySelector("#film-detail").textContent =
        ${JSON.stringify(phase.detail)};
    })()`
  );
  await settle(cdp);
}

async function selectChallenge(cdp) {
  await dispatchMouseClick(
    cdp,
    "#challenge-link",
    "film select challenge fragment"
  );
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "Control",
    code: "ControlLeft",
    windowsVirtualKeyCode: 17,
    nativeVirtualKeyCode: 17,
    modifiers: 2,
  });
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "a",
    code: "KeyA",
    text: "",
    unmodifiedText: "a",
    windowsVirtualKeyCode: 65,
    nativeVirtualKeyCode: 65,
    modifiers: 2,
  });
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "a",
    code: "KeyA",
    windowsVirtualKeyCode: 65,
    nativeVirtualKeyCode: 65,
    modifiers: 2,
  });
  await cdp.command("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "Control",
    code: "ControlLeft",
    windowsVirtualKeyCode: 17,
    nativeVirtualKeyCode: 17,
  });
  await settle(cdp);
}

async function captureStructure(cdp) {
  return await evaluate(
    cdp,
    `(() => {
      const describe = selector => {
        const element = document.querySelector(selector);
        const style = getComputedStyle(element);
        return {
          selector,
          tag: element.tagName.toLowerCase(),
          classes: [...element.classList],
          role: element.getAttribute("role"),
          fontFamily: style.fontFamily,
          fontSize: Number.parseFloat(style.fontSize),
          color: style.color,
          backgroundColor: style.backgroundColor,
          borderRadius: style.borderRadius
        };
      };
      return {
        fontsReady: document.fonts.status,
        bodyFontFamily: getComputedStyle(document.body).fontFamily,
        headingFontFamily: getComputedStyle(document.querySelector("h1")).fontFamily,
        buttonFontFamily:
          getComputedStyle(document.querySelector("#restart-btn")).fontFamily,
        outputFontFamily:
          getComputedStyle(document.querySelector("#digest-value")).fontFamily,
        criticalTypography: Object.fromEntries(
          [
            "#seed-value",
            "#reference-value",
            "#digest-value",
            "#film-callout",
            "#film-detail",
            "#challenge-status"
          ].map(selector => {
            const style = getComputedStyle(document.querySelector(selector));
            return [
              selector,
              {
                fontFamily: style.fontFamily,
                fontSize: Number.parseFloat(style.fontSize),
                fontWeight: style.fontWeight
              }
            ];
          })
        ),
        components: [
          describe(".proof-strip"),
          describe(".map-card"),
          describe("#maze-board"),
          describe(".panel"),
          describe(".challenge-card"),
          describe("#film-slate")
        ]
      };
    })()`
  );
}

async function captureDomEvidence(cdp) {
  return await evaluate(
    cdp,
    `(() => {
      const text = selector =>
        document.querySelector(selector).textContent.trim();
      const visible = selector => {
        const element = document.querySelector(selector);
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return !element.hidden &&
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          rect.width > 0 &&
          rect.height > 0 &&
          rect.left >= -1 &&
          rect.top >= -1 &&
          rect.right <= innerWidth + 1 &&
          rect.bottom <= innerHeight + 1;
      };
      const challenge = document.querySelector("#challenge-link");
      return {
        seed: text("#seed-value"),
        digest: text("#digest-value"),
        reference: text("#reference-value"),
        steps: text("#step-value"),
        bestFinish: text("#projection-value"),
        exit: text("#exit-value"),
        status: text("#status-message"),
        hint: {
          hidden: document.querySelector("#hint-panel").hidden,
          text: text("#hint-panel")
        },
        trap: {
          hidden: document.querySelector("#trap-panel").hidden,
          text: text("#trap-panel")
        },
        success: {
          hidden: document.querySelector("#success-panel").hidden,
          text: text("#success-panel")
        },
        challenge: {
          fragment: challenge.value,
          status: text("#challenge-status"),
          selectionStart: challenge.selectionStart,
          selectionEnd: challenge.selectionEnd,
          ariaInvalid: challenge.getAttribute("aria-invalid")
        },
        film: {
          phase: text("#film-phase"),
          callout: text("#film-callout"),
          detail: text("#film-detail")
        },
        activeId: document.activeElement ? document.activeElement.id : "",
        viewport: { width: innerWidth, height: innerHeight },
        scroll: {
          width: document.scrollingElement.scrollWidth,
          height: document.scrollingElement.scrollHeight
        },
        visibleComponents: [
          "#seed-value",
          "#reference-value",
          "#digest-value",
          "#maze-board",
          "#exit-beacon",
          "#film-slate",
          "#challenge-link",
          "#challenge-status",
          "#trap-panel",
          "#success-panel",
          "#takeover-prompt"
        ].filter(visible)
      };
    })()`
  );
}

function decodeChallenge(fragment) {
  assert.match(fragment, /^#challenge=[A-Za-z0-9_-]+$/);
  const payload = fragment.slice("#challenge=".length);
  const contract = JSON.parse(
    Buffer.from(payload, "base64url").toString("utf8")
  );
  assert.deepEqual(
    Object.keys(contract).sort(),
    ["referenceLength", "seed", "topologyDigest"]
  );
  assert.equal("route" in contract, false);
  assert.equal("trail" in contract, false);
  return contract;
}

function assertSample(phase, dom, plan) {
  assert.equal(dom.viewport.width, plan.width);
  assert.equal(dom.viewport.height, plan.height);
  assert.equal(dom.scroll.width, plan.width);
  assert.equal(dom.scroll.height, plan.height);
  assert.equal(dom.digest.length, 64);
  assert.match(dom.reference, /^\d+ moves$/);
  assert(dom.visibleComponents.includes("#film-slate"));
  assert.equal(dom.film.callout, phase.callout);
  assert.equal(dom.film.detail, phase.detail);
  if (phase.name === "challenge") {
    const contract = decodeChallenge(dom.challenge.fragment);
    assert.deepEqual(contract, plan.canonical);
    assert.match(dom.challenge.status, /^Challenge fragment (copied|ready)/);
    assert.equal(dom.challenge.selectionStart, 0);
    assert.equal(dom.challenge.selectionEnd, dom.challenge.fragment.length);
    assert(dom.visibleComponents.includes("#challenge-link"));
    assert(dom.visibleComponents.includes("#challenge-status"));
  }
  if (phase.name === "trap-plus-two") {
    assert.equal(dom.steps, "15 / 18");
    assert.equal(dom.bestFinish, "20");
    assert.match(dom.trap.text, /MARKED TRAP/);
    assert.match(dom.trap.text, /exit still marked/);
    assert(dom.visibleComponents.includes("#exit-beacon"));
    assert(dom.visibleComponents.includes("#trap-panel"));
  }
  if (phase.name === "optimal-complete") {
    assert.equal(dom.steps, "18 / 18");
    assert.match(dom.success.text, /18 = reference · unassisted/);
  }
  if (
    phase.name === "reset-after-trap" ||
    phase.name === "reset-after-optimal"
  ) {
    assert.equal(dom.steps, "0 / 18");
    assert.equal(dom.exit, "closed · marked");
  }
  if (phase.name === "alternate-fresh" || phase.name === "takeover") {
    assert.equal(dom.seed, plan.handoff.seed);
    assert.equal(dom.digest, plan.handoff.topologyDigest);
    assert.equal(dom.reference, `${plan.handoff.referenceLength} moves`);
    assert.equal(dom.steps, `0 / ${plan.handoff.referenceLength}`);
    assert.match(dom.status, /Seed FOG-7 ready/);
  }
  if (phase.name === "takeover") {
    assert.equal(dom.activeId, "maze-board");
    assert(dom.visibleComponents.includes("#takeover-prompt"));
  }
}

function ffmpegCommand(output, plan) {
  return [
    "-hide_banner",
    "-loglevel",
    "error",
    "-nostdin",
    "-y",
    "-f",
    "image2pipe",
    "-framerate",
    String(plan.fps),
    "-vcodec",
    "png",
    "-i",
    "pipe:0",
    "-an",
    "-map_metadata",
    "-1",
    "-c:v",
    "ffv1",
    "-level",
    "3",
    "-coder",
    "1",
    "-context",
    "1",
    "-g",
    "1",
    "-slicecrc",
    "1",
    "-threads",
    "1",
    "-pix_fmt",
    "bgr0",
    "-color_range",
    "pc",
    "-fflags",
    "+bitexact",
    "-flags:v",
    "+bitexact",
    "-f",
    "matroska",
    output,
  ];
}

async function executePlanAction(cdp, action, appUrl, phase) {
  if (action.do === "click") {
    await dispatchMouseClick(
      cdp,
      action.selector,
      `film frame ${action.frame} click ${action.selector}`
    );
  } else if (action.do === "key") {
    assert.equal(
      await evaluate(
        cdp,
        `document.activeElement ? document.activeElement.id : ""`
      ),
      "maze-board",
      `film frame ${action.frame}: board focus`
    );
    await dispatchKey(cdp, action.code);
    await settle(cdp);
  } else if (action.do === "selectChallenge") {
    await selectChallenge(cdp);
  } else if (action.do === "navigate") {
    const target = new URL(appUrl);
    target.hash = action.fragment;
    await cdp.command("Page.navigate", { url: target.href });
    await waitForReady(cdp);
    await evaluate(cdp, `document.fonts.ready`);
    await setFilmPhase(cdp, phase);
  } else {
    throw new Error(`unsupported film action ${action.do}`);
  }
  await delay(12);
}

async function main() {
  const options = parseOptions(process.argv.slice(2));
  const appPath = resolve(options.app);
  const outputPath = resolve(options.output);
  const continuityPath = resolve(options.continuity);
  const profilePath = resolve(options.profile);
  const sampleDir = resolve(options.sampleDir);
  const browserPath = await discoverBrowser(options.browser);
  const plan = JSON.parse(await readFile(resolve(options.plan), "utf8"));
  assert.equal(plan.schema, "fogline-survey-film-plan/1.0");
  assert.equal(plan.frames, plan.fps * 24);
  assert.equal(plan.width, 960);
  assert.equal(plan.height, 540);
  assert(basename(profilePath).startsWith("."));
  await removeProfile(profilePath);
  await mkdir(sampleDir, { recursive: true });

  const port = await reservePort();
  const launchLog = { value: "" };
  const browser = spawn(
    browserPath,
    [
      "--headless=new",
      "--disable-background-networking",
      "--disable-background-mode",
      "--disable-breakpad",
      "--disable-component-update",
      "--disable-crash-reporter",
      "--disable-default-apps",
      "--disable-dev-shm-usage",
      "--disable-extensions",
      "--disable-features=Crashpad",
      "--disable-gpu",
      "--disable-sync",
      "--hide-scrollbars",
      "--metrics-recording-only",
      "--no-first-run",
      "--no-default-browser-check",
      "--no-sandbox",
      `--remote-debugging-port=${port}`,
      "--remote-allow-origins=*",
      `--user-data-dir=${profilePath}`,
      "about:blank",
    ],
    { stdio: ["ignore", "pipe", "pipe"] }
  );
  const captureLaunch = chunk => {
    launchLog.value += chunk.toString();
    if (launchLog.value.length > 20000) {
      launchLog.value = launchLog.value.slice(-20000);
    }
  };
  browser.stdout.on("data", captureLaunch);
  browser.stderr.on("data", captureLaunch);

  const ffmpeg = spawn(
    resolve(options.ffmpeg),
    ffmpegCommand(outputPath, plan),
    { stdio: ["pipe", "ignore", "pipe"] }
  );
  let ffmpegError = "";
  ffmpeg.stderr.on("data", chunk => {
    ffmpegError += chunk.toString();
    if (ffmpegError.length > 20000) ffmpegError = ffmpegError.slice(-20000);
  });
  const ffmpegExited = once(ffmpeg, "exit");

  let cdp = null;
  const pageErrors = { exceptions: [], console: [], externalRequests: [] };
  try {
    await waitForDevTools(browser, port, launchLog, 45000);
    const targets = await (
      await fetch(`http://127.0.0.1:${port}/json/list`)
    ).json();
    const page = targets.find(target => target.type === "page");
    assert(page && page.webSocketDebuggerUrl);
    cdp = new CdpClient(page.webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.command("Page.enable");
    await cdp.command("Runtime.enable");
    await cdp.command("Network.enable");
    await cdp.command("Network.setBlockedURLs", {
      urls: ["http://*", "https://*", "ws://*", "wss://*"],
    });
    cdp.on("Runtime.exceptionThrown", event => {
      pageErrors.exceptions.push(event.exceptionDetails || event);
    });
    cdp.on("Runtime.consoleAPICalled", event => {
      if (event.type === "error" || event.type === "assert") {
        pageErrors.console.push(event);
      }
    });
    cdp.on("Network.requestWillBeSent", event => {
      const url = event.request && event.request.url;
      if (url && /^(https?|wss?):/i.test(url)) {
        pageErrors.externalRequests.push(url);
      }
    });
    await cdp.command("Emulation.setDeviceMetricsOverride", {
      width: plan.width,
      height: plan.height,
      deviceScaleFactor: 1,
      mobile: false,
    });

    const appUrl = new URL(pathToFileURL(appPath).href);
    appUrl.searchParams.set("film", "1");
    await cdp.command("Page.navigate", { url: appUrl.href });
    await waitForReady(cdp);
    await evaluate(cdp, `document.fonts.ready`);
    await settle(cdp);

    const actions = new Map();
    for (const action of plan.actions) {
      const records = actions.get(action.frame) || [];
      records.push(action);
      actions.set(action.frame, records);
    }
    const samples = new Map(
      plan.phases.map(phase => [phase.sampleFrame, phase])
    );
    const phaseEvidence = [];
    const initialPhase = phaseAt(plan, 0);
    await setFilmPhase(cdp, initialPhase);
    const structure = await captureStructure(cdp);
    assert.equal(structure.fontsReady, "loaded");
    let currentPhase = initialPhase;

    for (let frame = 0; frame < plan.frames; frame += 1) {
      const phase = phaseAt(plan, frame);
      if (!currentPhase || currentPhase.name !== phase.name) {
        await setFilmPhase(cdp, phase);
        currentPhase = phase;
      }
      for (const action of actions.get(frame) || []) {
        await executePlanAction(cdp, action, appUrl, phase);
      }
      const screenshot = await cdp.command("Page.captureScreenshot", {
        format: "png",
        fromSurface: true,
        captureBeyondViewport: false,
      });
      const png = Buffer.from(screenshot.data, "base64");
      if (!ffmpeg.stdin.write(png)) await once(ffmpeg.stdin, "drain");
      if (samples.has(frame)) {
        const samplePhase = samples.get(frame);
        const dom = await captureDomEvidence(cdp);
        assertSample(samplePhase, dom, plan);
        await writeFile(join(sampleDir, `${samplePhase.name}.png`), png);
        phaseEvidence.push({
          phase: samplePhase.name,
          frame,
          timestamp: frame / plan.fps,
          screenshotPngSha256: createHash("sha256").update(png).digest("hex"),
          dom,
        });
      }
    }

    ffmpeg.stdin.end();
    const [ffmpegCode] = await ffmpegExited;
    if (ffmpegCode !== 0) {
      throw new Error(`ffmpeg failed: ${ffmpegError || ffmpegCode}`);
    }
    assert.deepEqual(pageErrors, {
      exceptions: [],
      console: [],
      externalRequests: [],
    });
    assert.equal(phaseEvidence.length, plan.phases.length);

    const appBytes = await readFile(appPath);
    const continuity = {
      schema: "fogline-survey-film-live-continuity/1.0",
      renderer: {
        kind: "live-app-chromium-capture",
        app: "apps/maze-fogline.html?film=1",
        width: plan.width,
        height: plan.height,
        fps: plan.fps,
        frames: plan.frames,
      },
      sourceAppSha256: createHash("sha256").update(appBytes).digest("hex"),
      sharedStyle: structure,
      phases: phaseEvidence,
      errors: pageErrors,
    };
    await writeFile(
      continuityPath,
      JSON.stringify(continuity, null, 2) + "\n",
      "utf8"
    );

    try {
      await cdp.command("Browser.close");
    } catch (error) {
      launchLog.value += `\nBrowser.close: ${error.message}`;
    }
    cdp.close();
    cdp = null;
    assert(await waitForExit(browser), "browser did not exit");
    assert(await removeProfile(profilePath, 45000), "profile cleanup failed");
    console.log(
      JSON.stringify({
        renderer: continuity.renderer.kind,
        frames: plan.frames,
        phases: phaseEvidence.length,
      })
    );
  } finally {
    if (ffmpeg.stdin && !ffmpeg.stdin.destroyed) ffmpeg.stdin.destroy();
    if (ffmpeg.exitCode === null && ffmpeg.signalCode === null) {
      ffmpeg.kill("SIGKILL");
      await Promise.race([ffmpegExited, delay(5000)]);
    }
    if (cdp) cdp.close();
    if (browser.exitCode === null && browser.signalCode === null) {
      browser.kill("SIGKILL");
      await waitForExit(browser);
    }
    await removeProfile(profilePath, 45000);
  }
}

main().catch(error => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
});
