import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const SOURCE_URL =
  "https://kody-w.github.io/frame-chains/showcase/08-teleporting-roguelike/";
const OUTPUT_DIR = dirname(fileURLToPath(import.meta.url));
const WORK_DIR = join(OUTPUT_DIR, ".capture-work");
const SOURCE_FILE = join(OUTPUT_DIR, "source.webm");
const POSTER_FILE = join(OUTPUT_DIR, "poster.jpg");
const CLIP_FILE = join(OUTPUT_DIR, "clip.json");
const CAPTURE_FILE = join(OUTPUT_DIR, "capture.mjs");
const PROJECT_DIR = join(OUTPUT_DIR, "..", "..", "..");
const VIEWPORT = { width: 1920, height: 1080 };

const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

function run(command, args, options = {}) {
  return execFileSync(command, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  }).trim();
}

async function sha256(file) {
  return createHash("sha256").update(await readFile(file)).digest("hex");
}

async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true });
  } catch (bundledError) {
    for (const channel of ["chrome", "msedge"]) {
      try {
        return await chromium.launch({ channel, headless: true });
      } catch {
        // Continue to the next locally installed Chromium channel.
      }
    }
    throw bundledError;
  }
}

function probeMedia(file) {
  const streams = JSON.parse(
    run("ffprobe", [
      "-v",
      "error",
      "-show_streams",
      "-show_format",
      "-of",
      "json",
      file,
    ]),
  );
  const video = streams.streams.find((stream) => stream.codec_type === "video");
  const audioStreams = streams.streams.filter(
    (stream) => stream.codec_type === "audio",
  );
  assert(video, "source.webm must contain a video stream");
  return {
    codec: video.codec_name,
    width: video.width,
    height: video.height,
    pixel_format: video.pix_fmt,
    frame_rate: video.avg_frame_rate,
    duration_seconds: Number(streams.format.duration),
    audio_streams: audioStreams.length,
  };
}

await rm(WORK_DIR, { recursive: true, force: true });
await mkdir(WORK_DIR, { recursive: true });

let browser;
let rawVideo;
let observed;

try {
  browser = await launchBrowser();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
    colorScheme: "dark",
    reducedMotion: "no-preference",
    recordVideo: {
      dir: WORK_DIR,
      size: VIEWPORT,
    },
  });
  const page = await context.newPage();
  const video = page.video();

  await page.goto(SOURCE_URL, {
    waitUntil: "networkidle",
    timeout: 60_000,
  });
  await page.waitForFunction(
    () =>
      document.querySelector("#chainSize")?.textContent === "1 FRAME" &&
      !document.querySelector("#status")?.textContent.includes("Minting"),
  );

  await page.evaluate(() => {
    const nativeSetTimeout = window.setTimeout.bind(window);
    window.setTimeout = (callback, delay = 0, ...args) =>
      nativeSetTimeout(callback, delay === 220 ? 800 : delay, ...args);
  });

  await sleep(1_500);
  await page.locator("#runDemo").click();
  await page.evaluate(() =>
    window.scrollTo({ top: 300, behavior: "smooth" }),
  );

  await page.waitForFunction(
    () => document.querySelector("#demoCounter")?.textContent === "STEP 8 / 8",
    undefined,
    { timeout: 30_000 },
  );
  await page.waitForFunction(
    () =>
      document.querySelector("#status")?.textContent.includes(
        "Inventory forgery refused",
      ),
  );
  await sleep(2_500);

  const transferObserved = await page.evaluate(() => ({
    active_device: document.querySelector("#viewTag")?.textContent.trim(),
    device_b_state: document.querySelector("#bState")?.textContent.trim(),
    transfer_assertion_passed:
      document
        .querySelector('[data-assert="transfer"]')
        ?.classList.contains("pass") ?? false,
    a_b_assertion: document
      .querySelector('[data-assert="transfer"]')
      ?.textContent.trim(),
  }));
  assert.equal(transferObserved.active_device, "LIVE · DEVICE B");
  assert.equal(transferObserved.device_b_state, "LIVE");
  assert.equal(transferObserved.transfer_assertion_passed, true);

  const goodHead = await page.locator("#bHead").textContent();
  const goodFrameCount = await page.locator("#chainSize").textContent();
  const displayedWorldHash = await page.locator("#worldHash").textContent();

  await page.evaluate(() => document.querySelector("#forgeItem").click());
  await page.waitForFunction(
    () =>
      document.querySelector("#status")?.textContent.includes(
        "Inventory forgery refused",
      ),
  );
  const inventoryStatus = (await page.locator("#status").textContent()).trim();
  const headAfterInventory = await page.locator("#bHead").textContent();
  const framesAfterInventory = await page.locator("#chainSize").textContent();
  assert.match(inventoryStatus, /forged inventory item/i);
  assert.match(inventoryStatus, /Last good head preserved/);
  assert.equal(headAfterInventory, goodHead);
  assert.equal(framesAfterInventory, goodFrameCount);
  await sleep(4_000);

  await page.evaluate(() => document.querySelector("#forgeParent").click());
  await page.waitForFunction(
    () =>
      document.querySelector("#status")?.textContent.includes(
        "Parent forgery refused",
      ),
  );
  const parentStatus = (await page.locator("#status").textContent()).trim();
  const headAfterParent = await page.locator("#bHead").textContent();
  const framesAfterParent = await page.locator("#chainSize").textContent();
  assert.match(parentStatus, /parent provenance is not the previous verified frame/i);
  assert.match(parentStatus, /Last good head preserved/);
  assert.equal(headAfterParent, goodHead);
  assert.equal(framesAfterParent, goodFrameCount);

  const finalAssertions = await page.evaluate(() =>
    Object.fromEntries(
      [...document.querySelectorAll("[data-assert]")].map((element) => [
        element.dataset.assert,
        {
          label: element.textContent.trim(),
          passed: element.classList.contains("pass"),
        },
      ]),
    ),
  );
  assert.equal(finalAssertions.mutation.passed, true);

  await sleep(5_000);
  await page.screenshot({
    path: POSTER_FILE,
    type: "jpeg",
    quality: 92,
  });

  observed = {
    transfer: transferObserved,
    verified_head_sha256: goodHead.trim(),
    displayed_world_sha256: displayedWorldHash.trim(),
    accepted_chain_size: goodFrameCount.trim(),
    inventory_forgery: {
      status_exact: inventoryStatus,
      rejected: true,
      last_good_head_preserved:
        headAfterInventory === goodHead &&
        framesAfterInventory === goodFrameCount,
    },
    parent_provenance_forgery: {
      status_exact: parentStatus,
      rejected: true,
      last_good_head_preserved:
        headAfterParent === goodHead && framesAfterParent === goodFrameCount,
    },
    final_assertions: finalAssertions,
  };

  await context.close();
  rawVideo = await video.path();
  await browser.close();
  browser = undefined;

  run("ffmpeg", [
    "-y",
    "-i",
    rawVideo,
    "-vf",
    "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p",
    "-c:v",
    "libvpx-vp9",
    "-b:v",
    "0",
    "-crf",
    "31",
    "-deadline",
    "good",
    "-cpu-used",
    "2",
    "-row-mt",
    "1",
    "-an",
    SOURCE_FILE,
  ]);

  const media = probeMedia(SOURCE_FILE);
  const sourceStats = await stat(SOURCE_FILE);
  const posterStats = await stat(POSTER_FILE);
  assert.equal(media.width, 1920);
  assert.equal(media.height, 1080);
  assert.equal(media.frame_rate, "30/1");
  assert.equal(media.audio_streams, 0);
  assert(media.duration_seconds <= 45);
  assert(sourceStats.size < 30_000_000);

  const branch = run("git", ["branch", "--show-current"], { cwd: PROJECT_DIR });
  const commit = run("git", ["rev-parse", "HEAD"], { cwd: PROJECT_DIR });
  const capturedAt = new Date().toISOString();

  const clip = {
    schema: "rapp-vision.proof-clip/1",
    frame: 8,
    slug: "08-teleporting-roguelike",
    provenance: {
      source_url: SOURCE_URL,
      source_kind: "public live browser application",
      capture_method:
        "Playwright headless Chromium viewport recording with no browser or desktop chrome",
      captured_at_utc: capturedAt,
      repository_branch: branch,
      repository_commit: commit,
      capture_script: "capture.mjs",
      selectors_run_in_order: ["#runDemo", "#forgeItem", "#forgeParent"],
      viewport_css_pixels: VIEWPORT,
      synthetic_public_content_only: true,
    },
    media: {
      file: "source.webm",
      container: "webm",
      video_codec: media.codec,
      pixel_format: media.pixel_format,
      width: media.width,
      height: media.height,
      frame_rate: media.frame_rate,
      duration_seconds: media.duration_seconds,
      audio_streams: media.audio_streams,
      size_bytes: sourceStats.size,
      sha256: await sha256(SOURCE_FILE),
    },
    poster: {
      file: "poster.jpg",
      width: VIEWPORT.width,
      height: VIEWPORT.height,
      size_bytes: posterStats.size,
      depicts: "final parent-provenance rejection with the last good head preserved",
      sha256: await sha256(POSTER_FILE),
    },
    capture_script: {
      file: "capture.mjs",
      sha256: await sha256(CAPTURE_FILE),
    },
    outcome: {
      expected:
        "The dungeon transfers live to another device; forged inventory and parent provenance are refused.",
      observed,
      all_required_paths_asserted: true,
    },
  };

  await writeFile(CLIP_FILE, `${JSON.stringify(clip, null, 2)}\n`);
  console.log(JSON.stringify({ media: clip.media, outcome: observed }, null, 2));
} finally {
  if (browser) await browser.close().catch(() => {});
  await rm(WORK_DIR, { recursive: true, force: true });
}
