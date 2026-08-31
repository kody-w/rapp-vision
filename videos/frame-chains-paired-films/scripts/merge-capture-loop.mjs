import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = git(["rev-parse", "--show-toplevel"], projectRoot);
const planPath = resolve(projectRoot, "CAPTURE-LOOP.json");
const plan = JSON.parse(await readFile(planPath, "utf8"));

function git(args, cwd = repoRoot) {
  return execFileSync("git", args, { cwd, encoding: "utf8" }).trim();
}

function fail(message) {
  console.error(`capture loop merge: ${message}`);
  process.exit(1);
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

if (git(["status", "--porcelain"])) {
  fail("integration worktree must be clean");
}
if (plan.frame_count !== 10 || plan.frames?.length !== 10) {
  fail("plan must contain exactly ten frames");
}
if (plan.merge_strategy !== "git merge --no-ff" || plan.squash !== false) {
  fail("plan must require non-squash merges");
}
git(["cat-file", "-e", `${plan.base_commit}^{commit}`]);

const merged = [];
for (const frame of plan.frames) {
  const branchHead = git(["rev-parse", `${frame.branch}^{commit}`]);
  const prefix =
    `videos/frame-chains-paired-films/${frame.owned_path.replace(/\/+$/, "")}/`;
  const changed = git([
    "diff",
    "--name-only",
    `${plan.base_commit}..${branchHead}`,
  ]).split("\n").filter(Boolean);

  if (!changed.length) fail(`${frame.slug}: branch has no changes`);
  const outside = changed.filter((path) => !path.startsWith(prefix));
  if (outside.length) {
    fail(`${frame.slug}: changed files outside ownership:\n${outside.join("\n")}`);
  }

  const required = ["source.webm", "poster.jpg", "capture.mjs", "clip.json"];
  for (const name of required) {
    const path = `${prefix}${name}`;
    const exists = git(["cat-file", "-e", `${branchHead}:${path}`], repoRoot);
    if (exists !== "") fail(`${frame.slug}: missing ${name}`);
  }

  const clipPath = `${prefix}clip.json`;
  const clip = JSON.parse(
    git(["show", `${branchHead}:${clipPath}`], repoRoot),
  );
  if (clip.frame !== frame.frame || clip.slug !== frame.slug) {
    fail(`${frame.slug}: clip metadata identity mismatch`);
  }
  if (
    clip.synthetic_only !== true
    || clip.audio !== false
    || clip.width !== 1920
    || clip.height !== 1080
    || Number(clip.fps) !== 30
  ) {
    fail(`${frame.slug}: clip media contract mismatch`);
  }
  if (!(Number(clip.duration) > 0 && Number(clip.duration) <= 60)) {
    fail(`${frame.slug}: duration must be within (0, 60] seconds`);
  }
  const sourceBytes = execFileSync(
    "git",
    ["show", `${branchHead}:${prefix}source.webm`],
    { cwd: repoRoot, maxBuffer: 100 * 1024 * 1024 },
  );
  if (sha256(sourceBytes) !== clip.sha256) {
    fail(`${frame.slug}: source.webm sha256 does not match clip.json`);
  }
  const metadataText = JSON.stringify(clip);
  if (
    /(?:file:\/\/|localhost|127\.\d+\.\d+\.\d+|\/Users\/|\/home\/|[A-Z]:\\)/i
      .test(metadataText)
  ) {
    fail(`${frame.slug}: private path or local-network indicator in clip.json`);
  }

  git(["merge", "--no-ff", "--no-edit", frame.branch], repoRoot);
  const commits = git([
    "rev-list",
    "--reverse",
    `${plan.base_commit}..${branchHead}`,
    "--",
    prefix,
  ]).split("\n").filter(Boolean);
  merged.push({
    frame: frame.frame,
    slug: frame.slug,
    branch: frame.branch,
    path: frame.owned_path,
    commit: branchHead,
    commits,
    media: {
      duration: clip.duration,
      width: clip.width,
      height: clip.height,
      fps: clip.fps,
      sha256: clip.sha256,
    },
  });
  console.log(`merged ${frame.slug} @ ${branchHead.slice(0, 12)}`);
}

const ledger = {
  schema: "rapp-vision.capture-loop-ledger/1",
  loop: plan.loop,
  base_commit: plan.base_commit,
  integration_head_before_ledger: git(["rev-parse", "HEAD"], repoRoot),
  merge_strategy: plan.merge_strategy,
  squash: false,
  frame_count: merged.length,
  frames: merged,
};
const ledgerPath = resolve(projectRoot, "CAPTURE-LEDGER.json");
await writeFile(ledgerPath, `${JSON.stringify(ledger, null, 2)}\n`);
console.log(`wrote ${ledgerPath}`);
