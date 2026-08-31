import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFile, rm, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const SOURCE_URL =
  "https://kody-w.github.io/frame-chains/showcase/01-many-worlds/";
const outputDir = path.dirname(fileURLToPath(import.meta.url));
const rawDir = path.join(outputDir, ".capture-raw");
const sourcePath = path.join(outputDir, "source.webm");
const posterPath = path.join(outputDir, "poster.jpg");
const clipPath = path.join(outputDir, "clip.json");

const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

async function smoothScroll(page, targetSelector, offset = 100) {
  await page.evaluate(
    ({ selector, topOffset }) => {
      const target = document.querySelector(selector);
      if (!target) throw new Error(`Missing scroll target: ${selector}`);
      const top = target.getBoundingClientRect().top + window.scrollY - topOffset;
      window.scrollTo({ top, behavior: "smooth" });
    },
    { selector: targetSelector, topOffset: offset },
  );
  await sleep(1400);
}

function run(command, args) {
  execFileSync(command, args, { stdio: "inherit" });
}

async function sha256(filePath) {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

await rm(rawDir, { recursive: true, force: true });
await rm(sourcePath, { force: true });
await rm(posterPath, { force: true });
await rm(clipPath, { force: true });
await mkdir(rawDir, { recursive: true });

let browser;
let context;

try {
  browser = await chromium.launch({ headless: true });
  context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: {
      dir: rawDir,
      size: { width: 1920, height: 1080 },
    },
    colorScheme: "dark",
    reducedMotion: "no-preference",
  });

  const page = await context.newPage();
  const video = page.video();

  await page.goto(`${SOURCE_URL}?scoutTheme=dark`, {
    waitUntil: "networkidle",
  });
  await page.locator("#guided-btn").waitFor({ state: "visible" });
  await sleep(2500);

  await page.locator("#guided-btn").click();
  await page.waitForFunction(
    () => {
      const branchPasses = document.querySelectorAll(
        ".branch-card.valid",
      ).length;
      const score = document.querySelector(".score-number")?.textContent.trim();
      const verifier = [...document.querySelectorAll(".assertion")].find(
        (node) => node.textContent.includes("Independent branch verification"),
      );
      return (
        branchPasses === 3 &&
        score === "0.6" &&
        verifier?.classList.contains("pass")
      );
    },
    undefined,
    { timeout: 15_000 },
  );
  await sleep(1800);

  await smoothScroll(page, ".branch-stack", 110);
  await sleep(3800);

  await smoothScroll(page, ".merge-score", 110);
  await sleep(3200);

  await page.locator("#mutate-btn").click();
  await page.waitForFunction(
    () => {
      const rejectedRescue = document.querySelector(".branch-card.invalid");
      const verifier = [...document.querySelectorAll(".assertion")].find(
        (node) => node.textContent.includes("Independent branch verification"),
      );
      const isolation = [...document.querySelectorAll(".assertion")].find(
        (node) => node.textContent.includes("Failure is isolated"),
      );
      return (
        rejectedRescue?.textContent.includes("Rescue SABLE-2") &&
        verifier?.classList.contains("fail") &&
        isolation?.classList.contains("pass")
      );
    },
    undefined,
    { timeout: 10_000 },
  );
  await sleep(2400);

  await page.evaluate(() => {
    document.documentElement.style.zoom = "0.82";
  });
  await sleep(700);
  await page.evaluate(() => {
    const rescue = document.querySelector(".branch-card.invalid");
    if (!rescue) throw new Error("Missing invalid Rescue SABLE-2 branch");
    const top = rescue.getBoundingClientRect().top + window.scrollY - 110;
    window.scrollTo({ top, behavior: "smooth" });
  });
  await sleep(1600);

  const finalOutcome = await page.evaluate(() => {
    const rejectedRescue = document.querySelector(".branch-card.invalid");
    const verifier = [...document.querySelectorAll(".assertion")].find(
      (node) => node.textContent.includes("Independent branch verification"),
    );
    const isolation = [...document.querySelectorAll(".assertion")].find(
      (node) => node.textContent.includes("Failure is isolated"),
    );
    return {
      rejectedRescue: rejectedRescue?.textContent.replace(/\s+/g, " ").trim(),
      verifier: verifier?.textContent.replace(/\s+/g, " ").trim(),
      verifierFailed: verifier?.classList.contains("fail") ?? false,
      isolation: isolation?.textContent.replace(/\s+/g, " ").trim(),
      isolationPassed: isolation?.classList.contains("pass") ?? false,
    };
  });

  assert.match(finalOutcome.rejectedRescue ?? "", /Rescue SABLE-2.*FAIL/);
  assert.equal(finalOutcome.verifierFailed, true);
  assert.match(
    finalOutcome.verifier ?? "",
    /FAIL · Independent branch verification/,
  );
  assert.equal(finalOutcome.isolationPassed, true);
  assert.match(finalOutcome.isolation ?? "", /PASS · Failure is isolated/);

  await page.screenshot({
    path: posterPath,
    type: "jpeg",
    quality: 92,
  });
  await sleep(6200);

  await context.close();
  context = undefined;
  const rawVideoPath = await video.path();
  await browser.close();
  browser = undefined;

  run("ffmpeg", [
    "-y",
    "-hide_banner",
    "-loglevel",
    "warning",
    "-i",
    rawVideoPath,
    "-an",
    "-vf",
    "fps=30",
    "-c:v",
    "libvpx-vp9",
    "-crf",
    "31",
    "-b:v",
    "0",
    "-deadline",
    "good",
    "-cpu-used",
    "2",
    "-row-mt",
    "1",
    sourcePath,
  ]);

  const probe = JSON.parse(
    execFileSync(
      "ffprobe",
      [
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,codec_name",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        sourcePath,
      ],
      { encoding: "utf8" },
    ),
  );
  const stream = probe.streams[0];
  const [fpsNumerator, fpsDenominator] = stream.r_frame_rate
    .split("/")
    .map(Number);
  const fps = fpsNumerator / fpsDenominator;
  const duration = Number(probe.format.duration);

  assert.equal(stream.codec_name, "vp9");
  assert.equal(stream.width, 1920);
  assert.equal(stream.height, 1080);
  assert.equal(fps, 30);
  assert(duration >= 15 && duration <= 35);

  const clip = {
    frame: 1,
    slug: "01-many-worlds",
    title: "Many-Worlds Mission Control — Isolated Rescue Rejection",
    source_url: SOURCE_URL,
    duration: Number(duration.toFixed(3)),
    width: stream.width,
    height: stream.height,
    fps,
    selectors: [
      "#guided-btn",
      "#mutate-btn",
      ".branch-card.invalid",
      ".assertion.fail",
    ],
    positive_outcome:
      "Three deterministic branches verify from the same canonical parent and merge at 3/5 fidelity.",
    failure_outcome:
      "Rescue SABLE-2 alone fails after its parent hash is mutated; independent branch verification fails while isolation passes.",
    sha256: await sha256(sourcePath),
    synthetic_only: true,
    audio: false,
  };

  await writeFile(clipPath, `${JSON.stringify(clip, null, 2)}\n`);
  console.log(JSON.stringify({ clip, finalOutcome }, null, 2));
} finally {
  if (context) await context.close().catch(() => {});
  if (browser) await browser.close().catch(() => {});
  await rm(rawDir, { recursive: true, force: true });
}
