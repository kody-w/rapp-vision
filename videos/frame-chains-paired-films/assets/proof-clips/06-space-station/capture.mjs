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
const sourceUrl = "https://kody-w.github.io/frame-chains/showcase/06-space-station/";
const viewport = { width: 1920, height: 1080 };
const ffmpeg = process.env.FFMPEG_BIN || "ffmpeg";
const ffprobe = process.env.FFPROBE_BIN || "ffprobe";

function normalized(text) {
  return text.replace(/\s+/g, " ").trim();
}

async function run(command, args) {
  try {
    return await execFileAsync(command, args, { maxBuffer: 10 * 1024 * 1024 });
  } catch (error) {
    const details = [error.stdout, error.stderr].filter(Boolean).join("\n");
    throw new Error(`${command} failed${details ? `:\n${details}` : ""}`);
  }
}

async function sha256(path) {
  const bytes = await readFile(path);
  return createHash("sha256").update(bytes).digest("hex");
}

async function text(page, selector) {
  return normalized(await page.locator(selector).innerText());
}

async function assertVisibleInViewport(page, selector) {
  const box = await page.locator(selector).boundingBox();
  if (!box) throw new Error(`${selector} is not visible`);
  const top = box.y;
  const bottom = top + box.height;
  if (top < 0 || bottom > viewport.height) {
    throw new Error(`${selector} is outside the viewport: ${top}..${bottom}`);
  }
}

async function capture() {
  await mkdir(outputDir, { recursive: true });
  await rm(workDir, { recursive: true, force: true });
  await rm(sourcePath, { force: true });
  await rm(posterPath, { force: true });
  await rm(manifestPath, { force: true });
  await mkdir(workDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const browserVersion = browser.version();
  const context = await browser.newContext({
    viewport,
    screen: viewport,
    deviceScaleFactor: 1,
    colorScheme: "dark",
    reducedMotion: "no-preference",
    recordVideo: {
      dir: workDir,
      size: viewport,
    },
  });
  const page = await context.newPage();
  const recordedVideo = page.video();
  let rawVideoPath;

  try {
    await page.goto(sourceUrl, { waitUntil: "networkidle", timeout: 60_000 });
    await page.waitForSelector("#guided", { state: "visible" });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(1_500);

    await page.locator("#guided").click();
    await page.waitForFunction(
      () => {
        const value = (selector) => document.querySelector(selector)?.textContent?.trim();
        const alternatives = value("#alternatives") || "";
        return value("#head-count") === "35 verified frames"
          && value("#station-status") === "PASS · REATTACHED"
          && value("#fidelity") === "5 / 6"
          && alternatives.includes("68 kPa")
          && alternatives.includes("72 kPa");
      },
      null,
      { timeout: 30_000 },
    );

    const workspaceY = await page.locator(".workspace").evaluate((element) => element.offsetTop);
    await page.mouse.wheel(0, Math.max(0, workspaceY - 110));
    await page.waitForTimeout(1_200);
    await page.evaluate((top) => window.scrollTo({ top, behavior: "smooth" }), Math.max(0, workspaceY - 110));
    await page.waitForTimeout(4_500);

    const mutationDetails = page.locator("details").filter({ has: page.locator("#mutate-overwrite") });
    await mutationDetails.locator("summary").click();
    await page.waitForTimeout(700);
    await page.locator("#mutate-overwrite").click();
    await page.waitForFunction(
      () => {
        const result = document.querySelector("#mutation-result")?.textContent || "";
        return result.includes("PASS · REJECTED")
          && result.includes("proposal keeps 1 of 2 verified claim frames")
          && result.includes("Ledger unchanged: true");
      },
      null,
      { timeout: 10_000 },
    );

    const alternativesY = await page.locator("#alternatives").evaluate(
      (element) => element.getBoundingClientRect().top + window.scrollY,
    );
    const finalScroll = Math.max(0, alternativesY - 100);
    await page.evaluate((top) => window.scrollTo({ top, behavior: "smooth" }), finalScroll);
    await page.waitForTimeout(1_300);
    await page.mouse.move(920, 875);

    await assertVisibleInViewport(page, "#alternatives");
    await assertVisibleInViewport(page, "#mutation-result");

    const finalState = {
      station_status: await text(page, "#station-status"),
      verified_frames: await text(page, "#head-count"),
      fidelity: await text(page, "#fidelity"),
      fidelity_detail: await text(page, "#fidelity-detail"),
      alternatives: await text(page, "#alternatives"),
      mutation_result: await text(page, "#mutation-result"),
      verdict: await text(page, "#verdict"),
    };

    if (finalState.station_status !== "PASS · REATTACHED") {
      throw new Error(`Unexpected station state: ${finalState.station_status}`);
    }
    if (finalState.verified_frames !== "35 verified frames") {
      throw new Error(`Unexpected frame count: ${finalState.verified_frames}`);
    }
    if (finalState.fidelity !== "5 / 6") {
      throw new Error(`Unexpected fidelity: ${finalState.fidelity}`);
    }
    if (!finalState.alternatives.includes("68 kPa") || !finalState.alternatives.includes("72 kPa")) {
      throw new Error(`Missing airlock alternatives: ${finalState.alternatives}`);
    }
    if (!finalState.mutation_result.includes("proposal keeps 1 of 2 verified claim frames")) {
      throw new Error(`Missing overwrite-loss rejection: ${finalState.mutation_result}`);
    }

    await page.screenshot({
      path: posterPath,
      type: "jpeg",
      quality: 92,
      fullPage: false,
    });
    await page.waitForTimeout(10_000);

    await page.close();
    await context.close();
    rawVideoPath = await recordedVideo.path();
    await browser.close();

    await run(ffmpeg, [
      "-y",
      "-i", rawVideoPath,
      "-an",
      "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p",
      "-c:v", "libvpx-vp9",
      "-crf", "30",
      "-b:v", "0",
      "-row-mt", "1",
      "-deadline", "good",
      "-cpu-used", "2",
      sourcePath,
    ]);

    const { stdout } = await run(ffprobe, [
      "-v", "error",
      "-show_entries", "format=duration,size,format_name:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,pix_fmt",
      "-of", "json",
      sourcePath,
    ]);
    const probe = JSON.parse(stdout);
    const videoStream = probe.streams.find((stream) => stream.codec_type === "video");
    const audioStreams = probe.streams.filter((stream) => stream.codec_type === "audio");
    const duration = Number(probe.format.duration);
    const fileSize = Number(probe.format.size);

    if (videoStream?.width !== viewport.width || videoStream?.height !== viewport.height) {
      throw new Error(`Unexpected dimensions: ${videoStream?.width}x${videoStream?.height}`);
    }
    if (videoStream?.avg_frame_rate !== "30/1") {
      throw new Error(`Unexpected frame rate: ${videoStream?.avg_frame_rate}`);
    }
    if (audioStreams.length !== 0) {
      throw new Error(`Expected silent capture, found ${audioStreams.length} audio stream(s)`);
    }
    if (duration < 15 || duration > 35) {
      throw new Error(`Duration ${duration}s is outside 15-35s`);
    }
    if (fileSize >= 25 * 1024 * 1024) {
      throw new Error(`Capture is ${(fileSize / 1024 / 1024).toFixed(2)} MiB, exceeding 25 MiB`);
    }

    const posterStats = await stat(posterPath);
    const manifest = {
      schema: "rapp-vision.proof-clip/1",
      slug: "06-space-station",
      provenance: {
        source_url: sourceUrl,
        source_scope: "Public synthetic showcase state; viewport-only browser capture.",
        branch: "frame-film/06-space-station-capture",
        capture_tool: "Playwright Chromium with FFmpeg normalization",
        playwright_version: "1.62.1",
        browser: `Chromium ${browserVersion}`,
        captured_at: new Date().toISOString(),
        invocation: "node assets/proof-clips/06-space-station/capture.mjs",
      },
      selectors: {
        guided_action: "#guided",
        verified_frames: "#head-count",
        station_status: "#station-status",
        fidelity: "#fidelity",
        alternatives: "#alternatives",
        mutation_drawer: "details:has(#mutate-overwrite)",
        overwrite_action: "#mutate-overwrite",
        overwrite_result: "#mutation-result",
      },
      outcomes: finalState,
      media: {
        source: {
          file: "source.webm",
          format: probe.format.format_name,
          codec: videoStream.codec_name,
          pixel_format: videoStream.pix_fmt,
          width: videoStream.width,
          height: videoStream.height,
          fps: videoStream.avg_frame_rate,
          duration_seconds: Number(duration.toFixed(3)),
          audio_streams: audioStreams.length,
          bytes: fileSize,
          mebibytes: Number((fileSize / 1024 / 1024).toFixed(3)),
        },
        poster: {
          file: "poster.jpg",
          width: viewport.width,
          height: viewport.height,
          bytes: posterStats.size,
          viewport_only: true,
        },
      },
      sha256: {
        "source.webm": await sha256(sourcePath),
        "poster.jpg": await sha256(posterPath),
      },
    };

    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
    console.log(JSON.stringify({
      status: "PASS",
      source: manifest.media.source,
      outcomes: finalState,
      sha256: manifest.sha256,
    }, null, 2));
  } finally {
    if (browser.isConnected()) await browser.close();
    await rm(workDir, { recursive: true, force: true });
  }
}

await capture();
