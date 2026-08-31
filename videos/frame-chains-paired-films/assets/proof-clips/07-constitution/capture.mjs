import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { chromium } from "playwright";

const execFileAsync = promisify(execFile);
const outputDir = dirname(fileURLToPath(import.meta.url));
const sourceUrl = "https://kody-w.github.io/frame-chains/showcase/07-constitution/";
const rawPath = join(outputDir, ".capture-raw.webm");
const sourcePath = join(outputDir, "source.webm");
const posterPath = join(outputDir, "poster.jpg");
const manifestPath = join(outputDir, "clip.json");
const workDir = join(outputDir, ".capture-work");

const expected = {
  guided: "Guided history complete.",
  fork: "Fork comparison ready.",
  rejection:
    "Replay refused frame 8: Action cites superseded law LAW-TREASURY-1; LAW-TREASURY-2 is the active authority.",
  preserved:
    "Replay stopped before frame 8; the visible society remains at valid frame 7.",
};

const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

async function run(command, args) {
  return execFileAsync(command, args, { maxBuffer: 10 * 1024 * 1024 });
}

async function sha256(path) {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

async function scrollTo(page, top) {
  await page.evaluate((nextTop) => {
    window.scrollTo({ top: nextTop, behavior: "smooth" });
  }, top);
  await sleep(1400);
}

async function text(page, selector) {
  return (await page.locator(selector).innerText()).trim();
}

async function assertFinalState(page) {
  const state = await page.evaluate(() => {
    const getText = (selector) =>
      document.querySelector(selector)?.textContent?.replace(/\s+/g, " ").trim() || "";
    const rows = [...document.querySelectorAll("#ledgerBody tr")].map((row) =>
      [...row.cells]
        .map((cell) => cell.textContent.replace(/\s+/g, " ").trim())
        .join(" "),
    );
    const assertions = [...document.querySelectorAll("#assertionView .assertion")].map(
      (node) => node.textContent.replace(/\s+/g, " ").trim(),
    );
    return {
      frameStat: getText("#frameStat"),
      headStat: getText("#headStat"),
      law: getText("#lawView"),
      status: getText("#status"),
      assertions,
      rows,
      forks: getText("#forkView"),
    };
  });

  const checks = [
    [state.frameStat === "8/9", `expected valid frame count 8/9, got ${state.frameStat}`],
    [
      state.law.includes("LAW-TREASURY-1 · SUPERSEDED → LAW-TREASURY-2"),
      "superseded LAW-TREASURY-1 was not visible",
    ],
    [
      state.law.includes("LAW-TREASURY-2 · ACTIVE"),
      "active LAW-TREASURY-2 was not visible",
    ],
    [state.status.includes(expected.rejection), "exact replay refusal was not visible"],
    [
      state.assertions.some((value) => value.includes(expected.preserved)),
      "valid frame 7 preservation assertion was not visible",
    ],
    [
      state.assertions.some(
        (value) =>
          value.includes("FAIL · Semantic constitution") &&
          value.includes(
            "Action cites superseded law LAW-TREASURY-1; LAW-TREASURY-2 is the active authority. Exact law: LAW-TREASURY-1.",
          ),
      ),
      "semantic-law rejection assertion was not visible",
    ],
    [
      state.forks.includes("Canal Commonwealth") &&
        state.forks.includes("Clinic Compact"),
      "both lawful societies were not preserved",
    ],
    [
      state.rows.some(
        (value) =>
          value.startsWith("7 office.transfer") &&
          value.includes(state.headStat),
      ),
      "visible chain head did not remain on valid frame 7",
    ],
    [
      state.rows.some(
        (value) =>
          value.startsWith("8 action.spend") &&
          value.includes("Tyrant Vale") &&
          value.includes("LAW-TREASURY-1"),
      ),
      "rejected tyrant frame 8 was not present in the ledger",
    ],
  ];

  const failure = checks.find(([passed]) => !passed);
  if (failure) throw new Error(`Final DOM assertion failed: ${failure[1]}`);
  return state;
}

async function main() {
  await Promise.all([
    rm(rawPath, { force: true }),
    rm(sourcePath, { force: true }),
    rm(posterPath, { force: true }),
    rm(manifestPath, { force: true }),
    rm(workDir, { force: true, recursive: true }),
  ]);
  await mkdir(workDir);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    reducedMotion: "reduce",
    recordVideo: {
      dir: workDir,
      size: { width: 1920, height: 1080 },
    },
  });
  const page = await context.newPage();
  const recording = page.video();

  try {
    await page.goto(sourceUrl, { waitUntil: "networkidle", timeout: 60_000 });
    await page.locator("#guidedBtn").waitFor({ state: "visible" });
    await sleep(1800);

    await page.locator("#guidedBtn").click();
    await page.waitForFunction(
      (message) => document.querySelector("#status strong")?.textContent === message,
      expected.guided,
      { timeout: 20_000 },
    );
    await scrollTo(page, 350);
    await sleep(4300);

    await scrollTo(page, 1510);
    await page.locator("#forkBtn").click();
    await page.waitForFunction(
      (message) => document.querySelector("#status strong")?.textContent === message,
      expected.fork,
      { timeout: 20_000 },
    );
    await sleep(4300);

    await scrollTo(page, 350);
    await page.locator("#tyrantBtn").click();
    await page.waitForFunction(
      (message) => document.querySelector("#status span")?.textContent === message,
      expected.rejection,
      { timeout: 20_000 },
    );
    await scrollTo(page, 430);
    const finalState = await assertFinalState(page);
    await sleep(7600);

    await page.screenshot({
      path: posterPath,
      type: "jpeg",
      quality: 92,
      animations: "disabled",
    });

    await context.close();
    await recording.saveAs(rawPath);
    await rm(workDir, { force: true, recursive: true });
    await browser.close();

    await run("ffmpeg", [
      "-y",
      "-i",
      rawPath,
      "-map",
      "0:v:0",
      "-vf",
      "fps=30,scale=1920:1080:flags=lanczos",
      "-c:v",
      "libvpx-vp9",
      "-crf",
      "32",
      "-b:v",
      "0",
      "-deadline",
      "good",
      "-cpu-used",
      "2",
      "-an",
      sourcePath,
    ]);
    await rm(rawPath, { force: true });

    const { stdout } = await run("ffprobe", [
      "-v",
      "error",
      "-show_entries",
      "format=duration,size:stream=index,codec_name,codec_type,width,height,r_frame_rate,avg_frame_rate",
      "-of",
      "json",
      sourcePath,
    ]);
    const probe = JSON.parse(stdout);
    const video = probe.streams.find((stream) => stream.codec_type === "video");
    const audioStreams = probe.streams.filter(
      (stream) => stream.codec_type === "audio",
    ).length;
    const durationSeconds = Number(probe.format.duration);
    const sourceSize = (await stat(sourcePath)).size;

    if (video.width !== 1920 || video.height !== 1080) {
      throw new Error(`Unexpected dimensions: ${video.width}x${video.height}`);
    }
    if (video.avg_frame_rate !== "30/1") {
      throw new Error(`Unexpected frame rate: ${video.avg_frame_rate}`);
    }
    if (audioStreams !== 0) {
      throw new Error(`Expected silent footage, found ${audioStreams} audio stream(s)`);
    }
    if (durationSeconds < 15 || durationSeconds > 35) {
      throw new Error(`Unexpected duration: ${durationSeconds}s`);
    }
    if (sourceSize >= 25 * 1024 * 1024) {
      throw new Error(`source.webm exceeds 25 MiB: ${sourceSize} bytes`);
    }

    const manifest = {
      schema: "rapp-vision.proof-clip/1",
      frame: 7,
      slug: "07-constitution",
      provenance: {
        source_url: sourceUrl,
        source_kind: "public-app-browser-capture",
        captured_at: new Date().toISOString(),
        capture_script: "capture.mjs",
        viewport: { width: 1920, height: 1080 },
        actions: ["#guidedBtn", "#forkBtn", "#tyrantBtn"],
      },
      outcome:
        "Two lawful societies remain visible while replay refuses the tyrant frame under the exact superseding law.",
      observed_outcomes: [
        "Guided history completed with LAW-TREASURY-1 superseded by active LAW-TREASURY-2.",
        "Canal Commonwealth and Clinic Compact remained visible as two lawful descendants.",
        expected.rejection,
        expected.preserved,
        `The derived chain head remained ${finalState.headStat}, the hash shown for valid frame 7.`,
      ],
      media: {
        source: {
          file: "source.webm",
          sha256: await sha256(sourcePath),
          bytes: sourceSize,
          duration_seconds: durationSeconds,
          codec: video.codec_name,
          width: video.width,
          height: video.height,
          frame_rate: video.avg_frame_rate,
          audio_streams: audioStreams,
        },
        poster: {
          file: "poster.jpg",
          sha256: await sha256(posterPath),
          bytes: (await stat(posterPath)).size,
          width: 1920,
          height: 1080,
        },
        capture_script: {
          file: "capture.mjs",
          sha256: await sha256(fileURLToPath(import.meta.url)),
          bytes: (await stat(fileURLToPath(import.meta.url))).size,
        },
      },
    };
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
    console.log(JSON.stringify(manifest, null, 2));
  } catch (error) {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
    await Promise.all([
      rm(rawPath, { force: true }),
      rm(workDir, { force: true, recursive: true }),
    ]);
    throw error;
  }
}

await main();
