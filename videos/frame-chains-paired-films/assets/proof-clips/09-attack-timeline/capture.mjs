#!/usr/bin/env node

import { execFile } from "node:child_process";
import { mkdir, rm, stat } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { chromium } from "playwright";

const execFileAsync = promisify(execFile);
const defaultOutputDir = dirname(fileURLToPath(import.meta.url));
const outputDir = resolve(process.env.OUTPUT_DIR || defaultOutputDir);
const sourceUrl =
  process.env.SOURCE_URL ||
  "https://kody-w.github.io/frame-chains/showcase/09-attack-timeline/";
const sourcePath = resolve(outputDir, "source.webm");
const posterPath = resolve(outputDir, "poster.jpg");
const rawDir = resolve(outputDir, ".capture-raw");

const wait = (page, milliseconds) => page.waitForTimeout(milliseconds);

async function smoothScroll(page, top, holdMilliseconds = 0) {
  await page.evaluate(
    ({ targetTop }) =>
      new Promise((done) => {
        const startTop = window.scrollY;
        const distance = targetTop - startTop;
        const duration = 650;
        const startedAt = performance.now();

        function step(now) {
          const progress = Math.min(1, (now - startedAt) / duration);
          const eased = 1 - Math.pow(1 - progress, 3);
          window.scrollTo(0, startTop + distance * eased);
          if (progress < 1) requestAnimationFrame(step);
          else done();
        }

        requestAnimationFrame(step);
      }),
    { targetTop: top },
  );
  if (holdMilliseconds) await wait(page, holdMilliseconds);
}

async function assertText(page, selector, expected) {
  const text = (await page.locator(selector).innerText()).trim();
  if (!text.includes(expected)) {
    throw new Error(`${selector} did not include ${JSON.stringify(expected)}: ${text}`);
  }
}

async function run() {
  await mkdir(outputDir, { recursive: true });
  await rm(rawDir, { recursive: true, force: true });
  await rm(sourcePath, { force: true });
  await rm(posterPath, { force: true });
  await mkdir(rawDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: {
      dir: rawDir,
      size: { width: 1920, height: 1080 },
    },
  });
  const page = await context.newPage();
  const video = page.video();
  let trustedBefore;

  try {
    await page.goto(sourceUrl, { waitUntil: "networkidle", timeout: 60_000 });
    await page.evaluate(() => document.fonts.ready);
    await page.locator("#controlBtn").waitFor({ state: "visible" });

    trustedBefore = await page.evaluate(() => ({
      world: document.querySelector("#worldTitle")?.textContent?.trim(),
      head: document.querySelector("#worldHead")?.textContent?.trim(),
      highWater: document.querySelector("#worldHighWater")?.textContent?.trim(),
    }));

    await smoothScroll(page, 250, 1_500);
    await page.locator("#controlBtn").click();
    await page.waitForFunction(
      () =>
        document.querySelector("#resultCode")?.textContent?.trim() === "ACCEPT" &&
        document.querySelectorAll("#detectorRows .signal.pass").length === 9,
    );
    await assertText(page, "#resultTitle", "Control run verified");
    await wait(page, 1_500);

    await smoothScroll(page, 1_060, 2_000);
    await smoothScroll(page, 250, 600);

    await page.locator("#attackAllBtn").click();
    await smoothScroll(page, 1_060);
    await page.waitForFunction(
      () => document.querySelector("#live")?.textContent?.includes("Attack all complete"),
      null,
      { timeout: 30_000 },
    );

    await page.waitForFunction(
      () =>
        document.querySelectorAll("#quarantine .quarantine-item").length === 9 &&
        [...document.querySelectorAll("#assertions p")].filter((node) =>
          /red observed/i.test(node.textContent || ""),
        ).length === 9,
    );
    await assertText(page, "#resultCode", "REJECT");
    await wait(page, 2_500);

    const trustedAfterAttack = await page.evaluate(() => ({
      world: document.querySelector("#worldTitle")?.textContent?.trim(),
      head: document.querySelector("#worldHead")?.textContent?.trim(),
      highWater: document.querySelector("#worldHighWater")?.textContent?.trim(),
    }));
    if (JSON.stringify(trustedAfterAttack) !== JSON.stringify(trustedBefore)) {
      throw new Error(
        `Trusted projection changed after attack: ${JSON.stringify({
          trustedBefore,
          trustedAfterAttack,
        })}`,
      );
    }

    await smoothScroll(page, 1_720, 3_000);
    await smoothScroll(page, 2_500, 2_500);
    await smoothScroll(page, 480, 2_000);

    await page.locator("#replayBtn").click();
    await page.waitForFunction(
      () =>
        document
          .querySelector("#live")
          ?.textContent?.includes("Last verified projection preserved"),
    );
    await page.waitForFunction(
      () => document.querySelectorAll("#quarantine .quarantine-item").length === 10,
    );

    const trustedAfterReplay = await page.evaluate(() => ({
      world: document.querySelector("#worldTitle")?.textContent?.trim(),
      head: document.querySelector("#worldHead")?.textContent?.trim(),
      highWater: document.querySelector("#worldHighWater")?.textContent?.trim(),
    }));
    if (JSON.stringify(trustedAfterReplay) !== JSON.stringify(trustedBefore)) {
      throw new Error(
        `Trusted projection changed after replay: ${JSON.stringify({
          trustedBefore,
          trustedAfterReplay,
        })}`,
      );
    }

    await assertText(page, "#resultCode", "REJECT");
    await assertText(page, "#resultTitle", "Provenance stopped the candidate");
    await assertText(page, "#ledger li:first-child", "REJECTED · Provenance");
    await smoothScroll(page, 1_060, 4_500);
    await page.screenshot({
      path: posterPath,
      type: "jpeg",
      quality: 92,
      animations: "disabled",
    });
  } finally {
    await context.close();
    await browser.close();
  }

  const rawPath = await video.path();
  await execFileAsync(
    "ffmpeg",
    [
      "-y",
      "-hide_banner",
      "-loglevel",
      "error",
      "-i",
      rawPath,
      "-vf",
      "fps=30,scale=1920:1080:flags=lanczos",
      "-an",
      "-c:v",
      "libvpx-vp9",
      "-crf",
      "34",
      "-b:v",
      "0",
      "-deadline",
      "good",
      "-cpu-used",
      "4",
      "-row-mt",
      "1",
      "-pix_fmt",
      "yuv420p",
      sourcePath,
    ],
    { maxBuffer: 10 * 1024 * 1024 },
  );
  await rm(rawDir, { recursive: true, force: true });

  const sourceStats = await stat(sourcePath);
  if (sourceStats.size >= 30 * 1024 * 1024) {
    throw new Error(`source.webm is ${sourceStats.size} bytes; expected less than 30 MB`);
  }

  console.log(
    JSON.stringify(
      {
        sourceUrl,
        sourcePath,
        posterPath,
        bytes: sourceStats.size,
        trustedProjection: trustedBefore,
      },
      null,
      2,
    ),
  );
}

run().catch(async (error) => {
  await rm(rawDir, { recursive: true, force: true });
  console.error(error);
  process.exitCode = 1;
});
