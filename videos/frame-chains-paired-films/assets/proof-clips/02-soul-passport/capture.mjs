import { createHash } from "node:crypto";
import { readFile, rm, mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { chromium } from "playwright";

const SOURCE_URL =
  "https://kody-w.github.io/frame-chains/showcase/02-soul-passport/";
const outputDir = fileURLToPath(new URL(".", import.meta.url));
const workDir = path.join(outputDir, ".capture-work");
const sourcePath = path.join(outputDir, "source.webm");
const posterPath = path.join(outputDir, "poster.jpg");
const clipPath = path.join(outputDir, "clip.json");

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function run(command, args) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.status !== 0) {
    throw new Error(
      `${command} failed:\n${result.stderr || result.stdout || "unknown error"}`,
    );
  }
  return result.stdout.trim();
}

async function smoothScroll(page, y, duration = 1000) {
  await page.evaluate(
    ({ targetY, durationMs }) =>
      new Promise((resolve) => {
        const startY = window.scrollY;
        const distance = targetY - startY;
        const start = performance.now();

        const tick = (now) => {
          const progress = Math.min(1, (now - start) / durationMs);
          const eased =
            progress < 0.5
              ? 4 * progress ** 3
              : 1 - (-2 * progress + 2) ** 3 / 2;
          window.scrollTo(0, startY + distance * eased);
          if (progress < 1) requestAnimationFrame(tick);
          else resolve();
        };

        requestAnimationFrame(tick);
      }),
    { targetY: y, durationMs: duration },
  );
}

await rm(workDir, { recursive: true, force: true });
await mkdir(workDir, { recursive: true });

let browser;
try {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: {
      dir: workDir,
      size: { width: 1920, height: 1080 },
    },
  });
  const page = await context.newPage();
  const video = page.video();

  await page.goto(SOURCE_URL, { waitUntil: "networkidle" });
  await page.locator("#guided-button").waitFor({ state: "visible" });
  await wait(1300);

  await page.locator("#guided-button").click();
  await smoothScroll(page, 780, 1100);
  await page.waitForFunction(
    () =>
      document.querySelector("#guided-button")?.textContent?.trim() ===
      "Run guided",
    null,
    { timeout: 12_000 },
  );
  await wait(2200);

  const migrationState = await page.evaluate(() => ({
    lumen: document.querySelector("#device-lumen")?.textContent ?? "",
    archive: document.querySelector("#device-archive")?.textContent ?? "",
    field: document.querySelector("#device-field")?.textContent ?? "",
    provenance: document.querySelector("#provenance-content")?.textContent ?? "",
  }));
  if (
    !migrationState.lumen.includes("origin retained") ||
    !migrationState.archive.includes("verified head") ||
    !migrationState.field.includes("offline frame grafted") ||
    !migrationState.provenance.toLowerCase().includes("selected base")
  ) {
    throw new Error(
      `Guided identity migration did not reach the grafted state: ${JSON.stringify(migrationState)}`,
    );
  }

  await smoothScroll(page, 0, 900);
  await wait(700);
  const verifiedHead = (await page.locator("#head-hash").innerText()).trim();
  const verifiedTimeline = (
    await page.locator("#timeline").textContent()
  ).trim();

  await page.locator("#forge-button").click();
  await wait(600);
  await smoothScroll(page, 1850, 1050);
  await wait(2600);

  const forgedText = (await page.locator("#mutation-diff").innerText()).trim();
  if (
    !forgedText.includes("memory[0]") ||
    !forgedText.includes("declared_reads.memory_anchor") ||
    !forgedText.includes("claimed_address")
  ) {
    throw new Error("Counterfeit mutations were not visibly forged.");
  }

  await smoothScroll(page, 0, 900);
  await wait(650);
  await page.locator("#verify-button").click();
  await wait(650);
  await smoothScroll(page, 1850, 1050);
  await wait(5500);

  const outcome = await page.evaluate(() => ({
    mutation: document.querySelector("#mutation-diff")?.textContent ?? "",
    status: document.querySelector("#live-status")?.textContent ?? "",
    head: document.querySelector("#head-hash")?.textContent?.trim() ?? "",
    timeline: document.querySelector("#timeline")?.textContent?.trim() ?? "",
    ledger: document.querySelector("#ledger-list")?.textContent?.trim() ?? "",
  }));
  if (
    !outcome.mutation.toLowerCase().includes("rejected") ||
    !outcome.mutation.includes("verified_head_preserved") ||
    !outcome.mutation.includes("hologram_source_preserved") ||
    !outcome.status.includes("Counterfeit rejected") ||
    !outcome.status.includes("Verified head preserved") ||
    outcome.head !== verifiedHead ||
    outcome.timeline !== verifiedTimeline ||
    !outcome.ledger.toLowerCase().includes("rejected")
  ) {
    throw new Error(
      `Independent counterfeit rejection assertion failed: ${JSON.stringify({ outcome, verifiedHead, verifiedTimeline })}`,
    );
  }

  await page.screenshot({
    path: posterPath,
    type: "jpeg",
    quality: 92,
  });

  await page.close();
  await context.close();
  const rawVideoPath = await video.path();
  await browser.close();
  browser = undefined;

  run("ffmpeg", [
    "-y",
    "-loglevel",
    "error",
    "-i",
    rawVideoPath,
    "-vf",
    "fps=30",
    "-c:v",
    "libvpx-vp9",
    "-deadline",
    "good",
    "-cpu-used",
    "3",
    "-b:v",
    "1800k",
    "-maxrate",
    "2400k",
    "-bufsize",
    "4800k",
    "-pix_fmt",
    "yuv420p",
    "-an",
    sourcePath,
  ]);

  const probe = JSON.parse(
    run("ffprobe", [
      "-v",
      "error",
      "-show_entries",
      "stream=codec_type,width,height,avg_frame_rate:format=duration",
      "-of",
      "json",
      sourcePath,
    ]),
  );
  const videoStream = probe.streams.find(
    (stream) => stream.codec_type === "video",
  );
  const audioStream = probe.streams.find(
    (stream) => stream.codec_type === "audio",
  );
  const duration = Number(probe.format.duration);
  if (
    !videoStream ||
    videoStream.width !== 1920 ||
    videoStream.height !== 1080 ||
    videoStream.avg_frame_rate !== "30/1" ||
    audioStream ||
    duration < 15 ||
    duration > 35
  ) {
    throw new Error(`Unexpected encoded media properties: ${JSON.stringify(probe)}`);
  }

  const bytes = await readFile(sourcePath);
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  const clip = {
    frame: 2,
    slug: "02-soul-passport",
    title: "The AI Soul Passport — Counterfeit Rejected",
    source_url: SOURCE_URL,
    duration: Number(duration.toFixed(3)),
    dimensions: { width: 1920, height: 1080 },
    fps: 30,
    selectors: ["#guided-button", "#forge-button", "#verify-button"],
    positive_outcome:
      "Identity migrates across three synthetic devices, an isolated offline frame is deterministically reattached, and the accepted head remains verified.",
    failure_outcome:
      "Independent verification rejects the copied-appearance counterfeit for content address, morphology seed, and state-read-address failures while preserving the verified head and hologram source.",
    sha256,
    synthetic_only: true,
    audio: false,
  };
  await writeFile(clipPath, `${JSON.stringify(clip, null, 2)}\n`);

  console.log(
    JSON.stringify(
      {
        source: path.basename(sourcePath),
        poster: path.basename(posterPath),
        clip: path.basename(clipPath),
        duration,
        sha256,
        rejection: outcome.status.trim(),
      },
      null,
      2,
    ),
  );
} finally {
  if (browser) await browser.close();
  await rm(workDir, { recursive: true, force: true });
}
