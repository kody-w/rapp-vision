import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { chromium } from "playwright";

const execFileAsync = promisify(execFile);
const outputDir = dirname(fileURLToPath(import.meta.url));
const workDir = join(outputDir, ".capture-work");
const sourcePath = join(outputDir, "source.webm");
const posterPath = join(outputDir, "poster.jpg");
const manifestPath = join(outputDir, "clip.json");
const sourceUrl =
  "https://kody-w.github.io/frame-chains/showcase/03-mars-colony/";
const viewport = { width: 1920, height: 1080 };
const capturedAt = new Date().toISOString();

const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

async function sha256(path) {
  const bytes = await readFile(path);
  return createHash("sha256").update(bytes).digest("hex");
}

async function run(command, args) {
  try {
    return await execFileAsync(command, args, {
      cwd: outputDir,
      maxBuffer: 10 * 1024 * 1024,
    });
  } catch (error) {
    const details = [error.stdout, error.stderr].filter(Boolean).join("\n");
    throw new Error(`${command} failed${details ? `:\n${details}` : ""}`, {
      cause: error,
    });
  }
}

async function smoothScroll(page, top) {
  await page.evaluate((target) => {
    window.scrollTo({ top: target, left: 0, behavior: "smooth" });
  }, top);
  await sleep(900);
}

async function frameElement(page, selector, topPadding = 110) {
  const top = await page.locator(selector).evaluate(
    (element, padding) =>
      Math.max(
        0,
        element.getBoundingClientRect().top + window.scrollY - padding,
      ),
    topPadding,
  );
  await smoothScroll(page, top);
}

async function clickWithoutReframing(page, selector) {
  await page.locator(selector).evaluate((element) => element.click());
}

async function probeVideo() {
  const { stdout } = await run("ffprobe", [
    "-v",
    "error",
    "-count_frames",
    "-show_streams",
    "-show_format",
    "-of",
    "json",
    sourcePath,
  ]);
  return JSON.parse(stdout);
}

await mkdir(outputDir, { recursive: true });
await rm(workDir, { recursive: true, force: true });
await rm(sourcePath, { force: true });
await rm(posterPath, { force: true });
await rm(manifestPath, { force: true });
await mkdir(workDir, { recursive: true });

let browser;
let context;

try {
  browser = await chromium.launch({ headless: true });
  const browserVersion = browser.version();
  context = await browser.newContext({
    viewport,
    screen: viewport,
    deviceScaleFactor: 1,
    recordVideo: {
      dir: workDir,
      size: viewport,
    },
  });

  const page = await context.newPage();
  const video = page.video();
  assert(video, "Playwright did not initialize video recording.");

  await page.goto(sourceUrl, {
    waitUntil: "networkidle",
    timeout: 30_000,
  });
  await page.evaluate(() => document.fonts.ready);

  assert.equal(
    await page.title(),
    "Mars Colony Immune System — Frame 03",
    "Unexpected public app title.",
  );
  for (const selector of [
    "#nextButton",
    "#resetButton",
    "#injectButton",
    "#scanButton",
    "#sweepButton",
  ]) {
    await page.locator(selector).waitFor({ state: "visible" });
  }

  await sleep(1_700);
  await smoothScroll(page, 790);
  await sleep(1_100);

  for (let step = 1; step <= 8; step += 1) {
    const priorInstruction = await page.locator("#nextAction").innerText();
    await clickWithoutReframing(page, "#nextButton");
    await page.waitForFunction(
      (previous) =>
        document.querySelector("#nextAction")?.innerText !== previous,
      priorInstruction,
      { timeout: 12_000 },
    );
    await sleep(step === 8 ? 2_500 : 1_550);
  }

  const guidedCompletion = await page.locator("#nextAction").innerText();
  assert.match(
    guidedCompletion,
    /Scenario complete/,
    "The eight guided steps did not reach Scenario complete.",
  );

  await frameElement(page, "#manualTitle", 180);
  await clickWithoutReframing(page, "#resetButton");
  await page.waitForFunction(
    () =>
      document.querySelector("#liveRegion")?.textContent?.includes(
        "Reset complete",
      ),
  );
  await sleep(900);

  await clickWithoutReframing(page, "#injectButton");
  await page.waitForFunction(
    () => document.querySelector("#stableMetric")?.textContent === "9/12",
  );
  await sleep(1_250);

  await clickWithoutReframing(page, "#scanButton");
  await page.waitForFunction(
    () =>
      document.querySelector("#deltaMetric")?.textContent === "3" &&
      document
        .querySelector("#assertions")
        ?.textContent?.includes("12/12 responses reference tile"),
    undefined,
    { timeout: 12_000 },
  );
  await sleep(1_700);

  const acceptedHead = (await page.locator("#headMetric").innerText()).trim();
  const authorizedDelta = (await page.locator("#deltaMetric").innerText()).trim();
  const ledgerBefore = await page.locator("#ledgerBody").innerText();
  assert.equal(authorizedDelta, "3", "The exact authorized delta was not 3.");

  await clickWithoutReframing(page, "#sweepButton");
  await page.waitForFunction(
    () =>
      document
        .querySelector("#liveRegion")
        ?.textContent?.includes("Valid-hash mutation") &&
      document.querySelector("#liveRegion")?.textContent?.includes("rejected"),
  );

  const semanticRejection = await page.locator("#liveRegion").innerText();
  const assertionText = await page.locator("#assertions").innerText();
  const acceptedHeadAfter = (await page.locator("#headMetric").innerText()).trim();
  const ledgerAfter = await page.locator("#ledgerBody").innerText();

  assert.match(
    semanticRejection,
    /Valid-hash mutation [0-9a-f]{8} rejected: 12 actual targets exceeded the linked report delta of 3/,
    "The correctly hashed, semantically overbroad repair was not rejected.",
  );
  assert.match(
    assertionText,
    /authorized \[agriculture, oxygen, water\]/,
    "The exact authorized repair delta was not shown.",
  );
  assert.match(
    assertionText,
    /Writer scope_valid=true was ignored/,
    "The semantic oracle did not override the writer's scope claim.",
  );
  assert.equal(
    acceptedHeadAfter,
    acceptedHead,
    "The rejected repair changed the accepted head.",
  );
  assert.equal(
    ledgerAfter,
    ledgerBefore,
    "The rejected repair changed the accepted ledger.",
  );
  assert.match(
    assertionText,
    new RegExp(`accepted head ${acceptedHead} and prior module state stayed intact`),
    "The visible assertion did not preserve the accepted head.",
  );

  await sleep(1_400);
  await frameElement(page, "#assertions", 105);
  await sleep(4_600);
  await page.screenshot({
    path: posterPath,
    type: "jpeg",
    quality: 92,
  });
  await sleep(900);

  const rawPath = await video.path();
  await context.close();
  context = undefined;
  await browser.close();
  browser = undefined;

  await run("ffmpeg", [
    "-y",
    "-loglevel",
    "error",
    "-i",
    rawPath,
    "-map",
    "0:v:0",
    "-vf",
    "fps=30",
    "-an",
    "-map_metadata",
    "-1",
    "-c:v",
    "libvpx-vp9",
    "-crf",
    "34",
    "-b:v",
    "0",
    "-deadline",
    "good",
    "-cpu-used",
    "2",
    "-row-mt",
    "1",
    "-pix_fmt",
    "yuv420p",
    sourcePath,
  ]);

  const probe = await probeVideo();
  const videoStream = probe.streams.find(
    (stream) => stream.codec_type === "video",
  );
  const audioStreams = probe.streams.filter(
    (stream) => stream.codec_type === "audio",
  );
  assert(videoStream, "ffprobe found no video stream.");
  assert.equal(videoStream.width, viewport.width);
  assert.equal(videoStream.height, viewport.height);
  assert.equal(videoStream.avg_frame_rate, "30/1");
  assert.equal(audioStreams.length, 0, "The final clip contains audio.");

  const durationSeconds = Number(probe.format.duration);
  const sourceStats = await stat(sourcePath);
  const posterStats = await stat(posterPath);
  assert(
    durationSeconds <= 45,
    `The final clip is ${durationSeconds.toFixed(3)}s; expected no more than 45s.`,
  );
  assert(
    sourceStats.size < 30 * 1024 * 1024,
    `The final clip is ${(sourceStats.size / 1024 / 1024).toFixed(2)} MiB; expected under 30 MiB.`,
  );

  const candidateHash =
    semanticRejection.match(/Valid-hash mutation ([0-9a-f]{8}) rejected/)?.[1];
  const resolvedUrl = page.url();
  const manifest = {
    schema: "rapp-vision.proof-clip/1",
    id: "03-mars-colony",
    title: "Mars Colony — Semantic Repair Rejection",
    description:
      "Eight-step colony recovery followed by rejection of a correctly hashed but semantically overbroad repair.",
    source: {
      url: sourceUrl,
      resolved_url: resolvedUrl,
      public: true,
      synthetic: true,
      application_title: "Mars Colony Immune System — Frame 03",
    },
    provenance: {
      captured_at: capturedAt,
      branch: "frame-film/03-mars-colony-capture",
      capture_script: "capture.mjs",
      capture_tool: "Playwright",
      playwright_version: "1.62.1",
      browser: "Chromium",
      browser_version: browserVersion,
      recording_mode: "headless page-only browser context",
      desktop_or_browser_chrome_captured: false,
      private_data_captured: false,
      network_source: "public GitHub Pages application",
      actions: [
        "#nextButton ×8",
        "#resetButton",
        "#injectButton",
        "#scanButton",
        "#sweepButton",
      ],
    },
    evidence: {
      guided_completion: "Scenario complete",
      semantic_result: semanticRejection.trim(),
      correctly_hashed_candidate: candidateHash,
      authorized_delta_count: Number(authorizedDelta),
      authorized_delta_modules: ["agriculture", "oxygen", "water"],
      accepted_head_preserved: acceptedHead,
      accepted_ledger_preserved: true,
      accepted_ledger_rows: ledgerAfter
        .split("\n")
        .filter((line) => /^M\d+$/.test(line.trim())).length,
      assertion:
        assertionText
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean)
          .find((line) => line.startsWith("Correctly hashed candidate")) ?? null,
    },
    video: {
      file: "source.webm",
      container: probe.format.format_name,
      codec: videoStream.codec_name,
      profile: videoStream.profile,
      pixel_format: videoStream.pix_fmt,
      width: videoStream.width,
      height: videoStream.height,
      frame_rate: videoStream.avg_frame_rate,
      frames: Number(videoStream.nb_read_frames),
      duration_seconds: durationSeconds,
      bit_rate: Number(probe.format.bit_rate),
      audio_streams: audioStreams.length,
      size_bytes: sourceStats.size,
      sha256: await sha256(sourcePath),
    },
    poster: {
      file: "poster.jpg",
      format: "jpeg",
      width: viewport.width,
      height: viewport.height,
      state: "correctly hashed overbroad repair rejected",
      size_bytes: posterStats.size,
      sha256: await sha256(posterPath),
    },
  };

  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(
    `Captured ${manifest.video.duration_seconds.toFixed(3)}s, ` +
      `${(manifest.video.size_bytes / 1024 / 1024).toFixed(2)} MiB, ` +
      `sha256 ${manifest.video.sha256}`,
  );
} finally {
  if (context) await context.close().catch(() => {});
  if (browser) await browser.close().catch(() => {});
  await rm(workDir, { recursive: true, force: true });
}
