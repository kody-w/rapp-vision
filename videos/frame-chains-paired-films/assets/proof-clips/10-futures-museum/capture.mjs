import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const SOURCE_URL = "https://kody-w.github.io/frame-chains/showcase/10-futures-museum/?scoutTheme=light";
const outputDir = path.dirname(fileURLToPath(import.meta.url));
const workDir = path.join(outputDir, ".capture-work");
const sourcePath = path.join(outputDir, "source.webm");
const posterPath = path.join(outputDir, "poster.jpg");
const metadataPath = path.join(outputDir, "clip.json");
const capturePath = fileURLToPath(import.meta.url);
const frameSize = { width: 1920, height: 1080 };

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function run(command, args) {
  return execFileSync(command, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
}

async function sha256(filePath) {
  const bytes = await fs.readFile(filePath);
  return createHash("sha256").update(bytes).digest("hex");
}

async function scrollTo(page, selector, offset = 88, horizontal = null) {
  await page.evaluate(
    ({ selector: targetSelector, offset: topOffset, horizontal: horizontalPosition }) => {
      const target = document.querySelector(targetSelector);
      if (!target) throw new Error(`Missing scroll target: ${targetSelector}`);
      window.scrollTo({ top: Math.max(0, target.getBoundingClientRect().top + window.scrollY - topOffset), behavior: "smooth" });
      if (horizontalPosition) {
        const scroller = target.matches(".timeline-wrap, .branch-map-panel")
          ? target
          : target.querySelector(".timeline-wrap, .branch-map-panel");
        if (scroller) {
          scroller.scrollTo({
            left: horizontalPosition === "end" ? scroller.scrollWidth : 0,
            behavior: "smooth"
          });
        }
      }
    },
    { selector, offset, horizontal }
  );
  await sleep(550);
}

async function waitForFrame(page, frameId, timeout = 30_000) {
  await page.waitForFunction(
    (id) => document.querySelector("#readoutMeta")?.textContent?.startsWith(`${id} ·`),
    frameId,
    { timeout }
  );
}

async function text(page, selector) {
  return (await page.locator(selector).innerText()).trim();
}

async function assertText(page, selector, expected) {
  const actual = await text(page, selector);
  if (actual !== expected) {
    throw new Error(`${selector} expected "${expected}", received "${actual}"`);
  }
}

async function assertIncludes(page, selector, expected) {
  const actual = await text(page, selector);
  if (!actual.includes(expected)) {
    throw new Error(`${selector} did not include "${expected}". Received "${actual}"`);
  }
}

await fs.mkdir(outputDir, { recursive: true });
await fs.rm(workDir, { recursive: true, force: true });
await fs.mkdir(workDir, { recursive: true });
await Promise.all([
  fs.rm(sourcePath, { force: true }),
  fs.rm(posterPath, { force: true }),
  fs.rm(metadataPath, { force: true })
]);

let browser;
let chromiumVersion;
let rawVideoPath;
let finalState;
const consoleErrors = [];

try {
  browser = await chromium.launch({
    headless: true,
    args: [
      "--hide-scrollbars",
      "--force-device-scale-factor=1",
      "--disable-notifications",
      "--disable-features=Translate,MediaRouter"
    ]
  });
  chromiumVersion = browser.version();

  const context = await browser.newContext({
    viewport: frameSize,
    screen: frameSize,
    deviceScaleFactor: 1,
    colorScheme: "light",
    reducedMotion: "no-preference",
    locale: "en-US",
    timezoneId: "UTC",
    recordVideo: { dir: workDir, size: frameSize }
  });
  const page = await context.newPage();
  const video = page.video();

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto(SOURCE_URL, { waitUntil: "networkidle", timeout: 60_000 });
  await page.waitForFunction(
    () => document.querySelector("#headerStatus")?.textContent === "9 verified frames",
    null,
    { timeout: 30_000 }
  );
  await page.addStyleTag({
    content: `
      html { scroll-behavior: smooth !important; }
      body { cursor: none !important; }
      .shell { width: min(1720px, 100%) !important; }
      .toast { right: 44px !important; bottom: 32px !important; }
      * { caret-color: transparent !important; }
    `
  });

  await sleep(900);
  await page.locator("#playBtn").click();
  await waitForFrame(page, "F00");
  await scrollTo(page, "#museum", 18);

  await waitForFrame(page, "F01");
  await scrollTo(page, ".gallery-grid", 92);
  await waitForFrame(page, "F02");
  await scrollTo(page, ".timeline-wrap", 130, "end");
  await waitForFrame(page, "F03");
  await scrollTo(page, ".gallery-grid", 92);
  await waitForFrame(page, "S02");
  await scrollTo(page, ".artifact-stage", 92);
  await waitForFrame(page, "S03");
  await scrollTo(page, ".branch-lab", 92, "end");
  await waitForFrame(page, "M04");
  await scrollTo(page, ".ledger-grid", 92);
  await waitForFrame(page, "D02");
  await scrollTo(page, ".branch-lab", 92, "end");
  await waitForFrame(page, "D03");
  await page.waitForFunction(
    () => document.querySelector("#playBtn")?.getAttribute("aria-label") === "Start guided replay",
    null,
    { timeout: 10_000 }
  );
  await assertText(page, "#assertionScore", "7 / 7");
  await scrollTo(page, ".gallery-grid", 92);
  await sleep(850);

  await page.locator("#forkBtn").click();
  await waitForFrame(page, "V01");
  await assertText(page, "#detailParents", "D03");
  await scrollTo(page, ".gallery-grid", 92);
  await sleep(1_000);

  await scrollTo(page, ".branch-lab", 92, "end");
  await page.locator("#compareSelect").selectOption("D02");
  await assertIncludes(page, "#compareResult", "V01 · Mirror Orchard");
  await assertIncludes(page, "#compareResult", "D02 · The Quiet Index");
  await assertIncludes(page, "#compareResult", "Compatible exhibit vocabulary");
  await sleep(1_000);

  await page.locator("#mergeBtn").click();
  await waitForFrame(page, "U01");
  await assertText(page, "#detailParents", "D02 + V01");
  await assertIncludes(page, "#artifactTitle", "Accord of Mirror Orchard & The Quiet Index");
  await scrollTo(page, ".gallery-grid", 92);
  await sleep(1_350);
  await scrollTo(page, ".branch-lab", 92, "end");
  await sleep(1_100);

  await page.locator("#mutateBtn").click();
  await page.locator("#integrityBanner.visible").waitFor({ state: "visible", timeout: 10_000 });
  await waitForFrame(page, "U01");
  await assertText(page, "#headerStatus", "Frozen at F01");
  await assertText(page, "#detailParents", "D02 + V01");
  await assertText(page, "#assertionScore", "7 / 7");
  await assertText(
    page,
    "#integrityText",
    "First corrupt frame: F02. Frozen on last valid F01; accepted branches remain intact."
  );

  const ledger = await page.locator("#ledgerBody tr").allInnerTexts();
  for (const acceptedId of ["S02", "S03", "D02", "D03", "V01", "U01"]) {
    const row = ledger.find((value) => value.trim().startsWith(acceptedId));
    if (!row?.includes("VERIFIED")) throw new Error(`Expected independent branch ${acceptedId} to remain VERIFIED.`);
  }
  const corruptRow = ledger.find((value) => value.trim().startsWith("F02"));
  if (!corruptRow?.includes("DIGEST MISMATCH")) throw new Error("F02 was not identified as the first digest mismatch.");

  await scrollTo(page, ".gallery-grid", 92);
  await page.screenshot({
    path: posterPath,
    type: "jpeg",
    quality: 92,
    animations: "disabled"
  });
  await sleep(5_000);

  finalState = {
    currentFrame: "U01",
    mergeParents: ["D02", "V01"],
    firstCorruptFrame: "F02",
    frozenOn: "F01",
    assertionScore: "7 / 7",
    independentAcceptedFrames: ["S02", "S03", "D02", "D03", "V01", "U01"],
    integrityBanner: await text(page, "#integrityText")
  };

  await page.close();
  await context.close();
  rawVideoPath = await video.path();
  await browser.close();
  browser = null;

  run("ffmpeg", [
    "-y",
    "-hide_banner",
    "-loglevel", "error",
    "-i", rawVideoPath,
    "-map", "0:v:0",
    "-an",
    "-vf", "fps=30",
    "-c:v", "libvpx-vp9",
    "-crf", "31",
    "-b:v", "0",
    "-deadline", "good",
    "-cpu-used", "2",
    "-row-mt", "1",
    "-pix_fmt", "yuv420p",
    sourcePath
  ]);

  const probe = JSON.parse(run("ffprobe", [
    "-v", "error",
    "-show_entries", "format=duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate",
    "-of", "json",
    sourcePath
  ]));
  const videoStream = probe.streams.find((stream) => stream.codec_type === "video");
  const audioStreams = probe.streams.filter((stream) => stream.codec_type === "audio");
  const durationSeconds = Number(probe.format.duration);
  const byteSize = Number(probe.format.size);

  if (videoStream?.width !== frameSize.width || videoStream?.height !== frameSize.height) {
    throw new Error(`Unexpected output dimensions: ${videoStream?.width}x${videoStream?.height}`);
  }
  if (videoStream?.avg_frame_rate !== "30/1") {
    throw new Error(`Unexpected frame rate: ${videoStream?.avg_frame_rate}`);
  }
  if (audioStreams.length !== 0) throw new Error("The proof clip unexpectedly contains audio.");
  if (durationSeconds > 45) throw new Error(`The proof clip is ${durationSeconds}s; maximum is 45s.`);
  if (byteSize >= 30_000_000) throw new Error(`The proof clip is ${byteSize} bytes; maximum is under 30 MB.`);
  if (consoleErrors.length) throw new Error(`Browser errors detected: ${consoleErrors.join(" | ")}`);

  const posterStat = await fs.stat(posterPath);
  const hashes = {
    "source.webm": await sha256(sourcePath),
    "poster.jpg": await sha256(posterPath),
    "capture.mjs": await sha256(capturePath)
  };
  const ffmpegVersion = run("ffmpeg", ["-version"]).split("\n")[0];

  const metadata = {
    schema: "rapp-vision.proof-clip/1",
    slug: "10-futures-museum",
    title: "The Museum of Possible Futures — Branch, Merge, and Corruption Isolation",
    provenance: {
      sourceUrl: SOURCE_URL,
      sourceType: "public synthetic interactive proof",
      capturedAt: new Date().toISOString(),
      captureMethod: "Playwright Chromium viewport recording with deterministic scripted interaction",
      viewport: frameSize,
      browser: `Chromium ${chromiumVersion}`,
      encoder: ffmpegVersion,
      actions: [
        "Click #playBtn and wait for guided replay completion at 7 / 7 assertions",
        "Click #forkBtn to create V01 from D03",
        "Select D02 in #compareSelect",
        "Click #mergeBtn to create U01 from D02 + V01",
        "Click #mutateBtn and hold on the F02 corruption boundary frozen at F01"
      ],
      privacy: "Page viewport only; no browser chrome, desktop, local paths, credentials, or private data."
    },
    media: {
      video: {
        path: "source.webm",
        mimeType: "video/webm",
        codec: videoStream.codec_name,
        width: videoStream.width,
        height: videoStream.height,
        framesPerSecond: 30,
        durationSeconds: Number(durationSeconds.toFixed(3)),
        bytes: byteSize,
        silent: true,
        sha256: hashes["source.webm"]
      },
      poster: {
        path: "poster.jpg",
        mimeType: "image/jpeg",
        width: frameSize.width,
        height: frameSize.height,
        bytes: posterStat.size,
        depicts: "U01 preserved while the integrity banner identifies F02 and freezes the affected history at F01.",
        sha256: hashes["poster.jpg"]
      }
    },
    outcomes: {
      guidedReplay: "Completed on D03 with 7 / 7 live assertions passing.",
      fork: "Created visitor frame V01 from D03 without altering its source history.",
      comparison: "Compared V01 with D02 and confirmed compatible archive/silence vocabulary.",
      merge: "Created U01 with exact parents D02 + V01 and preserved both parents.",
      corruptionIsolation: "Mutation identified F02 as the first corrupt frame and froze the affected path on F01.",
      independentBranches: "S02, S03, D02, D03, V01, and U01 remained verified after the mutation."
    },
    finalState,
    sha256: hashes
  };

  await fs.writeFile(metadataPath, `${JSON.stringify(metadata, null, 2)}\n`);
  console.log(JSON.stringify({ sourcePath, posterPath, metadataPath, probe, finalState, hashes }, null, 2));
} finally {
  if (browser) await browser.close().catch(() => {});
  await fs.rm(workDir, { recursive: true, force: true });
}
