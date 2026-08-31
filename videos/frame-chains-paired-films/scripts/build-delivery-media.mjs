import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const projectRoot = resolve(dirname(new URL(import.meta.url).pathname), "..");
const source = resolve(process.argv[2] || "renders/video.mp4");
const outputDir = resolve(process.argv[3] || "../../frame-chains/media");
const audioMeta = JSON.parse(
  await readFile(resolve(projectRoot, "audio_meta.json"), "utf8"),
);

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error(`${command} exited ${result.status}`);
  }
}

function probe(path) {
  const result = spawnSync(
    "ffprobe",
    [
      "-v",
      "error",
      "-show_entries",
      "format=duration,size",
      "-show_entries",
      "stream=codec_name,width,height,r_frame_rate",
      "-of",
      "json",
      path,
    ],
    { encoding: "utf8" },
  );
  if (result.status !== 0) throw new Error(`ffprobe failed for ${path}`);
  return JSON.parse(result.stdout);
}

async function sha256(path) {
  const bytes = await readFile(path);
  return createHash("sha256").update(bytes).digest("hex");
}

function timelineWindows() {
  let cursor = 0;
  return audioMeta.voices.map((voice) => {
    const window = {
      frame: voice.frame,
      start: cursor,
      end: cursor + voice.duration_s,
      duration: voice.duration_s,
    };
    cursor = window.end;
    return window;
  });
}

function concatFilter(segments) {
  const filters = [];
  const inputs = [];
  segments.forEach((segment, index) => {
    filters.push(
      `[0:v]trim=start=${segment.start.toFixed(3)}:end=${segment.end.toFixed(3)},`
        + `setpts=PTS-STARTPTS,fps=30,format=yuv420p[v${index}]`,
      `[0:a]atrim=start=${segment.start.toFixed(3)}:end=${segment.end.toFixed(3)},`
        + `asetpts=PTS-STARTPTS[a${index}]`,
    );
    inputs.push(`[v${index}][a${index}]`);
  });
  filters.push(
    `${inputs.join("")}concat=n=${segments.length}:v=1:a=1[vout][aout]`,
  );
  return filters.join(";");
}

await mkdir(outputDir, { recursive: true });
const windows = timelineWindows();
const total = windows.at(-1).end;
const opener = { start: 0, end: Math.min(3.5, windows[0].end) };
const closer = { start: Math.max(0, total - 3.5), end: total };

const deliveries = [
  {
    id: "frame-chains-ten-frame-loop",
    title: "Ten Impossible Worlds, One Verifiable History",
    segments: [{ start: 0, end: total }],
    flagship: true,
  },
  {
    id: "many-worlds-mission-control",
    title: "Many Worlds Mission Control",
    segments: [
      { start: windows[0].start, end: windows[0].end },
      closer,
    ],
  },
  {
    id: "ai-soul-passport",
    title: "AI Soul Passport",
    segments: [opener, windows[1], closer],
  },
  {
    id: "teleporting-roguelike",
    title: "Teleporting Roguelike",
    segments: [opener, windows[7], closer],
  },
  {
    id: "attack-the-timeline",
    title: "Attack the Timeline",
    segments: [opener, windows[8], closer],
  },
];

const manifest = {
  schema: "rapp-vision.delivery-media/1",
  source: basename(source),
  generated_from_frames: windows,
  videos: [],
};

for (const delivery of deliveries) {
  const mp4 = resolve(outputDir, `${delivery.id}.mp4`);
  const webm = resolve(outputDir, `${delivery.id}.webm`);
  if (delivery.flagship) {
    run("ffmpeg", [
      "-y",
      "-hide_banner",
      "-loglevel",
      "error",
      "-i",
      source,
      "-map",
      "0:v:0",
      "-map",
      "0:a:0",
      "-c",
      "copy",
      "-movflags",
      "+faststart",
      mp4,
    ]);
  } else {
    run("ffmpeg", [
      "-y",
      "-hide_banner",
      "-loglevel",
      "error",
      "-i",
      source,
      "-filter_complex",
      concatFilter(delivery.segments),
      "-map",
      "[vout]",
      "-map",
      "[aout]",
      "-c:v",
      "libx264",
      "-preset",
      "slow",
      "-crf",
      "20",
      "-pix_fmt",
      "yuv420p",
      "-c:a",
      "aac",
      "-b:a",
      "160k",
      "-movflags",
      "+faststart",
      mp4,
    ]);
  }

  run("ffmpeg", [
    "-y",
    "-hide_banner",
    "-loglevel",
    "error",
    "-i",
    mp4,
    "-c:v",
    "libvpx-vp9",
    "-row-mt",
    "1",
    "-b:v",
    "0",
    "-crf",
    "32",
    "-c:a",
    "libopus",
    "-b:a",
    "128k",
    webm,
  ]);

  const mp4Probe = probe(mp4);
  const webmProbe = probe(webm);
  manifest.videos.push({
    id: delivery.id,
    title: delivery.title,
    segments: delivery.segments,
    duration_s: Number(mp4Probe.format.duration),
    mp4: {
      path: `media/${basename(mp4)}`,
      bytes: Number(mp4Probe.format.size),
      sha256: await sha256(mp4),
    },
    webm: {
      path: `media/${basename(webm)}`,
      bytes: Number(webmProbe.format.size),
      sha256: await sha256(webm),
    },
  });
  console.log(
    `built ${delivery.id}: ${Number(mp4Probe.format.duration).toFixed(3)}s`,
  );
}

const manifestPath = resolve(outputDir, "frame-chains-delivery-manifest.json");
await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`wrote ${manifestPath}`);
