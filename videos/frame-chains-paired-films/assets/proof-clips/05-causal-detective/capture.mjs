#!/usr/bin/env node

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const SOURCE_URL = "https://kody-w.github.io/frame-chains/showcase/05-causal-detective/";
const OUTPUT_DIR = dirname(fileURLToPath(import.meta.url));
const WORK_DIR = join(OUTPUT_DIR, ".capture-work");
const RAW_VIDEO = join(WORK_DIR, "raw.webm");
const SOURCE_VIDEO = join(OUTPUT_DIR, "source.webm");
const POSTER = join(OUTPUT_DIR, "poster.jpg");
const METADATA = join(OUTPUT_DIR, "clip.json");
const EVIDENCE_IDS = ["E02", "E03", "E04", "E06", "E07"];

const focusCss = `
  html { scroll-behavior: auto !important; }
  body { overflow-x: hidden; }
  .shell { max-width: none !important; padding: 24px 42px 34px !important; }
  .masthead, .newcomer-grid, .scope, .prompt-box, .footer { display: none !important; }
  .workspace {
    display: grid !important;
    grid-template-columns: minmax(0, 1.55fr) minmax(480px, .75fr) !important;
    gap: 18px !important;
    align-items: start !important;
  }
  .main-stack, .side-stack { display: contents !important; }
  .main-stack > section:nth-child(1) { grid-column: 1; grid-row: 1; }
  .main-stack > section:nth-child(2) { grid-column: 1; grid-row: 2; }
  .main-stack > section:nth-child(3) { display: none !important; }
  .side-stack > section:nth-child(1) { grid-column: 2; grid-row: 1; }
  .side-stack > section:nth-child(2) { display: none !important; }
  .side-stack > section:nth-child(3) { grid-column: 2; grid-row: 2; }
  .scene, .legend { display: none !important; }
  #timeline { display: block !important; }
  #timeline .event { min-height: 58px !important; padding: 8px 10px !important; }
  #timeline .event:not(:nth-child(2)):not(:nth-child(3)):not(:nth-child(4)):not(:nth-child(6)):not(:nth-child(7)) {
    display: none !important;
  }
  .panel { padding: 16px !important; }
  .panel-head { margin-bottom: 10px !important; }
  .slot { padding: 8px 10px !important; }
  .slots { gap: 8px !important; }
  .assertion { padding: 9px !important; }
  .mutation { padding: 16px !important; }
  body.capture-final .main-stack > section:nth-child(1) { display: none !important; }
  body.capture-final .main-stack > section:nth-child(2) { grid-column: 1; grid-row: 1; }
  body.capture-final .side-stack > section:nth-child(1) { grid-column: 2; grid-row: 1; }
  body.capture-final .side-stack > section:nth-child(2) {
    display: block !important;
    grid-column: 1;
    grid-row: 2;
  }
  body.capture-final .side-stack > section:nth-child(3) { grid-column: 2; grid-row: 2; }
  body.capture-final .ledger { max-height: 255px !important; }
`;

function pause(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function sha256(path) {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

function ffprobe(path) {
  return JSON.parse(execFileSync("ffprobe", [
    "-v", "error",
    "-show_entries", "format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate",
    "-of", "json",
    path
  ], { encoding: "utf8" }));
}

async function main() {
  await mkdir(OUTPUT_DIR, { recursive: true });
  await rm(WORK_DIR, { recursive: true, force: true });
  await mkdir(WORK_DIR, { recursive: true });
  await rm(SOURCE_VIDEO, { force: true });
  await rm(POSTER, { force: true });
  await rm(METADATA, { force: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    reducedMotion: "reduce",
    recordVideo: {
      dir: WORK_DIR,
      size: { width: 1920, height: 1080 }
    }
  });
  const page = await context.newPage();
  const video = page.video();

  try {
    await page.goto(SOURCE_URL, { waitUntil: "networkidle" });
    await page.waitForFunction(() => {
      const head = document.querySelector("#caseHead")?.textContent || "";
      return head.startsWith("evidence head") && !head.includes("minting");
    });
    await pause(1200);

    await page.locator("#guidedBtn").hover();
    await pause(250);
    await page.locator("#guidedBtn").click();
    await pause(650);

    await page.addStyleTag({ content: focusCss });
    await page.locator("#timeViewBtn").click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await pause(1000);

    for (const id of EVIDENCE_IDS) {
      const cite = page.locator(`.cite-btn[data-id="${id}"]`);
      await cite.hover();
      await pause(300);
      await cite.click();
      await pause(900);
    }

    const selectedEvidence = await page.locator("#slots select").evaluateAll(selects =>
      selects.map(select => select.selectedOptions[0]?.textContent?.trim() || "")
    );
    EVIDENCE_IDS.forEach((id, index) => {
      if (!selectedEvidence[index]?.startsWith(`${id} ·`)) {
        throw new Error(`Expected ${id} in guided slot ${index + 1}, got "${selectedEvidence[index]}"`);
      }
    });

    await page.locator("#accuseBtn").hover();
    await pause(300);
    await page.locator("#accuseBtn").click();
    await page.waitForFunction(() =>
      document.querySelector("#verdict")?.textContent.includes("Accusation accepted") &&
      document.querySelector("#oracleTitle")?.textContent.includes("green")
    );
    await pause(2400);

    await page.locator("#mutateBtn").hover();
    await pause(300);
    await page.locator("#mutateBtn").click();
    await page.waitForFunction(() => {
      const assertionText = document.querySelector("#assertions")?.textContent || "";
      const ledgerText = document.querySelector("#ledger")?.textContent || "";
      return document.querySelector("#verdict")?.textContent.includes("Accusation accepted") &&
        document.querySelector("#oracleTitle")?.textContent.includes("red") &&
        assertionText.includes("Cryptographic shape") &&
        assertionText.includes("Causal transitions") &&
        ledgerText.includes("F01");
    });

    await page.evaluate(() => {
      document.body.classList.add("capture-final");
      window.scrollTo(0, 0);
    });
    await pause(1000);

    const finalState = await page.evaluate(() => {
      const assertions = [...document.querySelectorAll("#assertions .assertion")].map(node => ({
        text: node.textContent.replace(/\s+/g, " ").trim(),
        classes: [...node.classList]
      }));
      return {
        url: location.href,
        viewport: { width: innerWidth, height: innerHeight },
        verdict: document.querySelector("#verdict")?.textContent.replace(/\s+/g, " ").trim(),
        oracleTitle: document.querySelector("#oracleTitle")?.textContent.trim(),
        oracleDetail: document.querySelector("#oracleDetail")?.textContent.trim(),
        assertionStates: assertions,
        failureLedger: document.querySelector("#ledger")?.textContent.replace(/\s+/g, " ").trim()
      };
    });

    const cryptoPass = finalState.assertionStates.some(item =>
      item.classes.includes("pass") && item.text.includes("Cryptographic shape")
    );
    const causalFail = finalState.assertionStates.some(item =>
      item.classes.includes("fail") && item.text.includes("Causal transitions")
    );
    if (
      finalState.viewport.width !== 1920 ||
      finalState.viewport.height !== 1080 ||
      !finalState.verdict?.includes("Accusation accepted") ||
      finalState.oracleTitle !== "Causal transition oracle: red" ||
      !cryptoPass ||
      !causalFail ||
      !finalState.failureLedger?.includes("F01")
    ) {
      throw new Error(`Final DOM assertion failed: ${JSON.stringify(finalState)}`);
    }

    await page.screenshot({
      path: POSTER,
      type: "jpeg",
      quality: 92,
      fullPage: false
    });
    await pause(4200);
    await page.close();
    await video.saveAs(RAW_VIDEO);
  } finally {
    await context.close();
    await browser.close();
  }

  execFileSync("ffmpeg", [
    "-y",
    "-i", RAW_VIDEO,
    "-vf", "fps=30,scale=1920:1080:flags=lanczos",
    "-an",
    "-c:v", "libvpx-vp9",
    "-b:v", "0",
    "-crf", "34",
    "-deadline", "good",
    "-cpu-used", "2",
    "-row-mt", "1",
    "-pix_fmt", "yuv420p",
    SOURCE_VIDEO
  ], { stdio: "inherit" });

  const probe = ffprobe(SOURCE_VIDEO);
  const videoStream = probe.streams.find(stream => stream.codec_type === "video");
  const audioStreams = probe.streams.filter(stream => stream.codec_type === "audio").length;
  const technical = {
    container: "webm",
    codec: videoStream?.codec_name,
    width: videoStream?.width,
    height: videoStream?.height,
    frameRate: videoStream?.avg_frame_rate,
    nominalFrameRate: videoStream?.r_frame_rate,
    durationSeconds: Number(probe.format.duration),
    audioStreams,
    sizeBytes: Number(probe.format.size)
  };
  if (
    technical.width !== 1920 ||
    technical.height !== 1080 ||
    technical.frameRate !== "30/1" ||
    technical.audioStreams !== 0 ||
    technical.durationSeconds > 45 ||
    technical.sizeBytes >= 30_000_000
  ) {
    throw new Error(`Technical validation failed: ${JSON.stringify(technical)}`);
  }

  const clip = {
    schema: "rapp-vision.proof-clip/1",
    slug: "05-causal-detective",
    provenance: {
      sourceUrl: SOURCE_URL,
      sourceType: "public-web-page",
      capturedAt: new Date().toISOString(),
      captureMethod: "Playwright Chromium viewport recording with capture-only CSS reframing",
      branch: "frame-film/05-causal-detective-capture",
      interactions: [
        "#guidedBtn",
        ...EVIDENCE_IDS,
        "#accuseBtn",
        "#mutateBtn"
      ],
      outcome: "The supported accusation remains accepted while forged frame F01 retains valid cryptographic shape and fails the causal-transition oracle."
    },
    technical,
    assertions: {
      selectedEvidence: EVIDENCE_IDS,
      acceptedAccusation: true,
      cryptographicShape: "pass",
      causalTransitionOracle: "fail",
      isolatedFailureFrame: "F01",
      finalOracle: "Causal transition oracle: red"
    },
    sha256: {
      "source.webm": await sha256(SOURCE_VIDEO),
      "poster.jpg": await sha256(POSTER)
    }
  };
  await writeFile(METADATA, `${JSON.stringify(clip, null, 2)}\n`);
  await rm(WORK_DIR, { recursive: true, force: true });
  console.log(JSON.stringify({ technical, sha256: clip.sha256 }, null, 2));
}

main().catch(async error => {
  await rm(WORK_DIR, { recursive: true, force: true });
  console.error(error);
  process.exitCode = 1;
});
