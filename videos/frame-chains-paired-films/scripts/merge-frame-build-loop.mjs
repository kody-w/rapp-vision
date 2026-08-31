import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = git(["rev-parse", "--show-toplevel"], projectRoot);
const plan = JSON.parse(
  await readFile(resolve(projectRoot, "FRAME-BUILD-LOOP.json"), "utf8"),
);

function git(args, cwd = repoRoot) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    maxBuffer: 20 * 1024 * 1024,
  }).trim();
}

function fail(message) {
  console.error(`frame build merge: ${message}`);
  process.exit(1);
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

const merged = [];
for (const frame of plan.frames) {
  const branchHead = git(["rev-parse", `${frame.branch}^{commit}`]);
  const repoPath = `videos/frame-chains-paired-films/${frame.path}`;
  const changed = git([
    "diff",
    "--name-only",
    `${plan.base_commit}..${branchHead}`,
  ]).split("\n").filter(Boolean);
  if (changed.length !== 1 || changed[0] !== repoPath) {
    fail(
      `${frame.slug}: expected only ${repoPath}, got:\n${changed.join("\n")}`,
    );
  }

  const html = git(["show", `${branchHead}:${repoPath}`]);
  const expectedAsset = `../../${frame.asset}`;
  for (const [label, expression] of [
    ["template", /<template[\s>]/i],
    [
      "composition id",
      new RegExp(`data-composition-id=["']${frame.slug}["']`),
    ],
    [
      "timeline registration",
      new RegExp(
        `__timelines\\s*\\[\\s*["']${frame.slug}["']\\s*\\]`,
      ),
    ],
    ["real proof footage", new RegExp(expectedAsset.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))],
    ["video element", /<video[\s>]/i],
    ["paused GSAP timeline", /gsap\.timeline\(\s*\{\s*paused:\s*true/i],
  ]) {
    if (!expression.test(html)) fail(`${frame.slug}: missing ${label}`);
  }
  if (/(?:Date\.now|Math\.random|repeat\s*:\s*-1|<script[^>]+src=["']https?:)/i.test(html)) {
    fail(`${frame.slug}: non-deterministic or external runtime code detected`);
  }

  git(["merge", "--no-ff", "--no-edit", frame.branch]);
  const commits = git([
    "rev-list",
    "--reverse",
    `${plan.base_commit}..${branchHead}`,
    "--",
    repoPath,
  ]).split("\n").filter(Boolean);
  merged.push({
    frame: frame.frame,
    slug: frame.slug,
    branch: frame.branch,
    path: frame.path,
    asset: frame.asset,
    commit: branchHead,
    commits,
  });
  console.log(`merged ${frame.slug} @ ${branchHead.slice(0, 12)}`);
}

const ledger = {
  schema: "rapp-vision.frame-build-loop-ledger/1",
  loop: plan.loop,
  base_commit: plan.base_commit,
  integration_head_before_ledger: git(["rev-parse", "HEAD"]),
  merge_strategy: plan.merge_strategy,
  squash: false,
  frame_count: merged.length,
  frames: merged,
};
const ledgerPath = resolve(projectRoot, "FRAME-BUILD-LEDGER.json");
await writeFile(ledgerPath, `${JSON.stringify(ledger, null, 2)}\n`);
console.log(`wrote ${ledgerPath}`);
