#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import {
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const require = createRequire(import.meta.url);
const { version: playwrightVersion } = require("playwright/package.json");

const outputDir = dirname(fileURLToPath(import.meta.url));
const sourceUrl =
  "https://kody-w.github.io/frame-chains/showcase/04-five-realities/";
const viewport = { width: 1920, height: 1080 };
const rawVideoPath = join(outputDir, "capture-raw.webm");
const sourceVideoPath = join(outputDir, "source.webm");
const posterPath = join(outputDir, "poster.jpg");
const manifestPath = join(outputDir, "clip.json");
const scriptPath = fileURLToPath(import.meta.url);
const maxBytes = 25 * 1024 * 1024;

let browser;
let context;
let browserVersion;

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: outputDir,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve(stdout);
      } else {
        reject(
          new Error(
            `${command} exited with ${code}\n${stderr.trim() || stdout.trim()}`,
          ),
        );
      }
    });
  });
}

async function sha256(path) {
  const contents = await readFile(path);
  return createHash("sha256").update(contents).digest("hex");
}

async function probe(path) {
  const output = await run("ffprobe", [
    "-v",
    "error",
    "-show_entries",
    "format=format_name,duration,size:stream=index,codec_type,codec_name,width,height,pix_fmt,r_frame_rate,avg_frame_rate",
    "-of",
    "json",
    path,
  ]);
  return JSON.parse(output);
}

function normalizedText(value) {
  return value.replace(/\s+/g, " ").trim();
}

async function removeGeneratedMedia() {
  const entries = await readdir(outputDir);
  await Promise.all(
    entries
      .filter(
        (name) =>
          name === "source.webm" ||
          name === "poster.jpg" ||
          name === "clip.json" ||
          name === "capture-raw.webm" ||
          /^[0-9a-f-]+\.webm$/i.test(name),
      )
      .map((name) => rm(join(outputDir, name), { force: true })),
  );
}

async function smoothScrollTo(page, top) {
  await page.evaluate((scrollTop) => {
    window.scrollTo({ top: scrollTop, behavior: "smooth" });
  }, Math.max(0, Math.round(top)));
  await page.waitForTimeout(850);
}

async function scrollElementTo(page, selector, topOffset) {
  const top = await page.locator(selector).evaluate(
    (element, offset) =>
      element.getBoundingClientRect().top + window.scrollY - offset,
    topOffset,
  );
  await smoothScrollTo(page, top);
}

async function waitForPrefix(page, minimum) {
  await page.waitForFunction(
    (target) => {
      const label = document.querySelector("#prefixLabel")?.textContent ?? "";
      return Number.parseInt(label, 10) >= target;
    },
    minimum,
    { timeout: 20_000 },
  );
}

async function readProjectionState(page) {
  return page.evaluate(() => {
    const hashes = Object.fromEntries(
      [...document.querySelectorAll("[data-hash]")].map((element) => [
        element.getAttribute("data-hash"),
        element.textContent.trim(),
      ]),
    );
    return {
      prefix: document.querySelector("#prefixLabel")?.textContent?.trim(),
      consensus: document
        .querySelector("#consensusBadge")
        ?.textContent?.trim(),
      summary: document
        .querySelector("#projectionSummary")
        ?.textContent?.trim(),
      detector: document.querySelector("#detectorText")?.textContent?.trim(),
      assertions: document.querySelector("#assertionList")?.innerText?.trim(),
      announcer: document.querySelector("#announcer")?.textContent?.trim(),
      commandClass:
        document.querySelector('[data-view="command"]')?.className ?? "",
      commandText:
        document.querySelector('[data-view="command"]')?.innerText?.trim() ??
        "",
      hashes,
    };
  });
}

try {
  await removeGeneratedMedia();

  browser = await chromium.launch({ headless: true });
  browserVersion = browser.version();
  context = await browser.newContext({
    viewport,
    screen: viewport,
    deviceScaleFactor: 1,
    recordVideo: {
      dir: outputDir,
      size: viewport,
    },
  });

  const page = await context.newPage();
  const video = page.video();
  assert(video, "Playwright did not create a video recorder");

  await page.emulateMedia({
    colorScheme: "dark",
    reducedMotion: "no-preference",
  });
  await page.goto(sourceUrl, {
    waitUntil: "networkidle",
    timeout: 30_000,
  });

  assert.equal(page.url(), sourceUrl, "Unexpected final capture URL");
  assert.equal(
    await page.title(),
    "One History, Five Realities",
    "Unexpected page title",
  );
  await page.locator("#guideBtn").waitFor({ state: "visible" });
  await page.locator("#mutationBtn").waitFor({ state: "attached" });

  const initialState = await readProjectionState(page);
  assert.equal(initialState.prefix, "0 / 9");
  assert.equal(initialState.consensus, "5 / 5 canonical agreement");

  await page.waitForTimeout(1_200);
  await page.locator("#guideBtn").click();
  await page.waitForTimeout(700);
  await scrollElementTo(page, "#simulator", 52);

  await waitForPrefix(page, 3);
  await scrollElementTo(page, "#projectionHost", 178);
  await waitForPrefix(page, 6);
  await scrollElementTo(page, "#simulator", 52);
  await waitForPrefix(page, 8);
  await scrollElementTo(page, "#projectionHost", 178);
  await waitForPrefix(page, 9);

  const replayState = await readProjectionState(page);
  const replayHashes = Object.values(replayState.hashes);
  assert.equal(replayState.prefix, "9 / 9");
  assert.equal(replayState.consensus, "5 / 5 canonical agreement");
  assert.equal(
    replayState.summary,
    "All projectors read prefix 9; 0 events remain outside the selected history.",
  );
  assert.equal(
    replayState.announcer,
    "Guided run complete. All selected events are projected.",
  );
  assert.equal(replayHashes.length, 5);
  assert.equal(new Set(replayHashes).size, 1);
  assert.match(replayHashes[0], /^[0-9a-f]{64}$/);
  assert.match(replayState.detector, /^Unanimous: five views resolve to /);

  await page.waitForTimeout(2_200);
  await scrollElementTo(page, "#simulator", 52);
  await page.waitForTimeout(900);
  await page.locator("#mutationBtn").click();
  await page.waitForFunction(
    () =>
      document.querySelector("#consensusBadge")?.textContent?.trim() ===
      "1 divergent view",
    undefined,
    { timeout: 5_000 },
  );

  const mutationState = await readProjectionState(page);
  const canonicalHash = mutationState.hashes.kanban;
  const honestViews = ["kanban", "city", "graph", "comic"];
  assert.equal(mutationState.prefix, "9 / 9");
  assert.equal(mutationState.consensus, "1 divergent view");
  assert.match(mutationState.commandClass, /\bdivergent\b/);
  assert.match(mutationState.commandText, /\bLINK\s+none\b/);
  assert.match(mutationState.hashes.command, /^[0-9a-f]{64}$/);
  assert.notEqual(mutationState.hashes.command, canonicalHash);
  for (const view of honestViews) {
    assert.equal(mutationState.hashes[view], canonicalHash);
  }
  assert.match(
    mutationState.detector,
    /^Isolated:\s*Command Dashboard\s*\. The other 4 views still resolve to /,
  );
  assert.match(
    mutationState.assertions,
    /Four honest projections still agree/,
  );
  assert.match(mutationState.assertions, /Exactly Command is isolated/);

  await page.waitForTimeout(1_500);
  await scrollElementTo(page, "#projectionHost", 178);
  await page.screenshot({
    path: posterPath,
    type: "jpeg",
    quality: 92,
    fullPage: false,
  });
  await page.waitForTimeout(3_200);
  await scrollElementTo(page, "#evidence-title", 100);
  await page.waitForTimeout(5_000);

  await context.close();
  context = undefined;
  await video.saveAs(rawVideoPath);
  await video.delete();
  await browser.close();
  browser = undefined;

  await run("ffmpeg", [
    "-y",
    "-i",
    rawVideoPath,
    "-an",
    "-vf",
    "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p",
    "-c:v",
    "libvpx-vp9",
    "-deadline",
    "good",
    "-cpu-used",
    "2",
    "-row-mt",
    "1",
    "-crf",
    "30",
    "-b:v",
    "0",
    sourceVideoPath,
  ]);
  await rm(rawVideoPath, { force: true });

  const [videoProbe, posterProbe, videoStats, posterStats] = await Promise.all([
    probe(sourceVideoPath),
    probe(posterPath),
    stat(sourceVideoPath),
    stat(posterPath),
  ]);
  const videoStream = videoProbe.streams.find(
    (stream) => stream.codec_type === "video",
  );
  const audioStreams = videoProbe.streams.filter(
    (stream) => stream.codec_type === "audio",
  );
  const posterStream = posterProbe.streams.find(
    (stream) => stream.codec_type === "video",
  );
  const durationSeconds = Number(videoProbe.format.duration);

  assert(videoStream, "source.webm has no video stream");
  assert.equal(videoStream.width, viewport.width);
  assert.equal(videoStream.height, viewport.height);
  assert.equal(videoStream.avg_frame_rate, "30/1");
  assert.equal(audioStreams.length, 0);
  assert(
    durationSeconds >= 15 && durationSeconds <= 35,
    `Duration ${durationSeconds}s is outside the required 15-35s range`,
  );
  assert(
    videoStats.size < maxBytes,
    `source.webm is ${videoStats.size} bytes; limit is ${maxBytes}`,
  );
  assert(posterStream, "poster.jpg has no image stream");
  assert.equal(posterStream.width, viewport.width);
  assert.equal(posterStream.height, viewport.height);

  const capturedAt = new Date().toISOString();
  const [videoSha256, posterSha256, scriptSha256] = await Promise.all([
    sha256(sourceVideoPath),
    sha256(posterPath),
    sha256(scriptPath),
  ]);

  const manifest = {
    schema: "rapp-vision.proof-clip/1",
    slug: "04-five-realities",
    title: "One History, Five Realities",
    source: {
      url: sourceUrl,
      pageTitle: "One History, Five Realities",
      capturedAt,
      publicSyntheticMaterial: true,
      captureScope: "Chromium viewport only",
    },
    provenance: {
      branch: "frame-film/04-five-realities-capture",
      captureScript: "capture.mjs",
      captureScriptSha256: scriptSha256,
      playwrightVersion,
      browser: browserVersion,
      viewport,
      deviceScaleFactor: 1,
    },
    actions: [
      {
        selector: "#guideBtn",
        action: "click",
        outcome:
          "Guided replay advanced the selected immutable history from prefix 0 / 9 through 9 / 9.",
      },
      {
        selector: "#prefixLabel",
        action: "wait",
        outcome: replayState.prefix,
      },
      {
        selector: "#consensusBadge",
        action: "assert after full replay",
        outcome: replayState.consensus,
      },
      {
        selector: "[data-hash]",
        action: "assert after full replay",
        outcome: `All five independently exposed oracle hashes resolved to ${replayHashes[0]}.`,
      },
      {
        selector: "#mutationBtn",
        action: "click",
        outcome:
          "The Command projector omitted the relationship event without changing the selected history.",
      },
      {
        selector: '[data-view="command"]',
        action: "assert divergence",
        outcome: `Command Dashboard was marked divergent with LINK none and hash ${mutationState.hashes.command}.`,
      },
      {
        selector:
          '[data-hash="kanban"], [data-hash="city"], [data-hash="graph"], [data-hash="comic"]',
        action: "assert honest majority",
        outcome: `The four honest projections remained in agreement at ${canonicalHash}.`,
      },
      {
        selector: "#detectorText",
        action: "assert isolation",
        outcome: normalizedText(mutationState.detector),
      },
      {
        selector: "#assertionList",
        action: "assert live contract",
        outcome:
          "Four honest projections still agree; exactly Command is isolated.",
      },
    ],
    outcome:
      "Five projections converge from one history; one mutated Command projector is visibly isolated while the other four remain in canonical agreement.",
    media: {
      "source.webm": {
        sha256: videoSha256,
        bytes: videoStats.size,
        durationSeconds,
        format: videoProbe.format.format_name,
        codec: videoStream.codec_name,
        width: videoStream.width,
        height: videoStream.height,
        pixelFormat: videoStream.pix_fmt,
        frameRate: videoStream.avg_frame_rate,
        audioStreams: audioStreams.length,
      },
      "poster.jpg": {
        sha256: posterSha256,
        bytes: posterStats.size,
        codec: posterStream.codec_name,
        width: posterStream.width,
        height: posterStream.height,
        pixelFormat: posterStream.pix_fmt,
        state:
          "Full-prefix divergence view showing the Command projector isolated among four matching projections.",
      },
    },
  };

  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(
    JSON.stringify(
      {
        ok: true,
        outputDir,
        durationSeconds,
        bytes: videoStats.size,
        sha256: videoSha256,
      },
      null,
      2,
    ),
  );
} catch (error) {
  if (context) {
    await context.close().catch(() => {});
  }
  if (browser) {
    await browser.close().catch(() => {});
  }
  await removeGeneratedMedia().catch(() => {});
  console.error(error);
  process.exitCode = 1;
}
