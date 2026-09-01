import { existsSync } from "node:fs";
import {
  copyFile,
  mkdir,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const assembler = process.argv[2]
  || (
    process.env.PRODUCT_LAUNCH_SKILL_DIR
      ? resolve(process.env.PRODUCT_LAUNCH_SKILL_DIR, "scripts/assemble-index.mjs")
      : null
  );
if (!assembler || !existsSync(assembler)) {
  console.error(
    "usage: node scripts/assemble-flagship.mjs <product-launch assemble-index.mjs>",
  );
  process.exit(1);
}

const plan = JSON.parse(
  await readFile(resolve(projectRoot, "FRAME-BUILD-LOOP.json"), "utf8"),
);
const sourceDir = resolve(
  projectRoot,
  ".hyperframes/approved-frame-sources",
);
const indexPath = resolve(projectRoot, "index.html");
const indexBefore = existsSync(indexPath) ? await readFile(indexPath) : null;
await mkdir(sourceDir, { recursive: true });

const sources = plan.frames.map((frame) => ({
  live: resolve(projectRoot, frame.path),
  backup: resolve(sourceDir, basename(frame.path)),
}));

for (const source of sources) {
  const html = await readFile(source.live, "utf8");
  if (html.includes('data-frame-video="approved"')) {
    await copyFile(source.live, source.backup);
  } else if (existsSync(source.backup)) {
    await copyFile(source.backup, source.live);
  } else {
      throw new Error(
        `${basename(source.live)} has no approved frame video to preserve`,
      );
  }
}

const result = spawnSync(
  process.execPath,
  [
    assembler,
    "--storyboard",
    resolve(projectRoot, "STORYBOARD.md"),
    "--hyperframes",
    projectRoot,
  ],
  { cwd: projectRoot, encoding: "utf8", stdio: "pipe" },
);

if (result.status !== 0) {
  for (const source of sources) {
    await copyFile(source.backup, source.live);
  }
  if (indexBefore) await writeFile(indexPath, indexBefore);
  else await rm(indexPath, { force: true });
  process.stderr.write(result.stderr);
  process.stdout.write(result.stdout);
  console.error("assembly failed; approved frame sources and index restored");
  process.exit(result.status || 1);
}

const assembled = await readFile(indexPath, "utf8");
for (const frame of plan.frames) {
  if (!assembled.includes(frame.asset)) {
    throw new Error(`assembled index omitted ${frame.asset}`);
  }
}
process.stdout.write(result.stdout);
process.stderr.write(result.stderr);
console.log(
  `rollback-safe assembly preserved ${sources.length} approved frame source files`,
);
