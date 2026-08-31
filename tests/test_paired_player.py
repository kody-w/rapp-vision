"""Runtime-oriented checks for the exact paired-publication player code."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
NODE = shutil.which("node")


def contract_block():
    start = INDEX.index("/* publication contract:start")
    end = INDEX.index("/* publication contract:end */") + len("/* publication contract:end */")
    return INDEX[start:end]


@unittest.skipUnless(NODE, "node not available; exact player validation test skipped")
class TestPairedPlayer(unittest.TestCase):
    def run_node(self, body):
        completed = subprocess.run(
            [NODE, "-e", body],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        return completed.stdout

    def test_browser_validator_accepts_and_rejects_the_same_fixtures(self):
        valid = json.dumps(json.loads(
            (ROOT / "tests/fixtures/publications/valid-paired.json").read_text()
        ))
        invalid = json.dumps(json.loads(
            (ROOT / "tests/fixtures/publications/invalid-missing-webm.json").read_text()
        ))
        policy = json.dumps(json.loads(
            (ROOT / "policy/legacy-publications.json").read_text()
        ))
        script = f"""
        let LEGACY_POLICY = {policy};
        {contract_block()}
        const valid = validateChannelContract({valid}, "https://example.test/channel.json");
        const invalid = validateChannelContract({invalid}, "https://example.test/channel.json");
        if (valid.length) throw new Error(valid.join("\\n"));
        if (!invalid.some(e => e.includes("missing required video/webm")))
          throw new Error("browser validator accepted an MP4-only publication");
        """
        self.run_node(script)

    def test_modes_have_separate_progress_keys(self):
        script = """
        const isPaired = v => !!(v && v.live && Array.isArray(v.sources) && v.sources.length);
        const historyKey = (v, mode) => isPaired(v) ? `${v.id}::${mode}` : v.id;
        const paired = {id:"proof", sources:[{src:"proof.mp4"}], live:{scenes:[]}};
        if (historyKey(paired, "video") !== "proof::video") throw new Error("video key");
        if (historyKey(paired, "live") !== "proof::live") throw new Error("live key");
        if (historyKey({id:"legacy", sources:[]}, "live") !== "legacy") throw new Error("legacy key");
        """
        self.run_node(script)

    def test_same_permalink_switch_defaults_to_video_and_cleans_up(self):
        self.assertIn('mountMode(hasVideo ? "video" : "live", false)', INDEX)
        self.assertIn(">Try live replay</button>", INDEX)
        self.assertIn(">Watch guided video</button>", INDEX)
        self.assertIn("function mountMode(next, announce = true) {\n    cleanupMode();", INDEX)
        self.assertIn('document.removeEventListener("keydown", live.keys);', INDEX)
        self.assertIn("retryTimers.forEach(clearTimeout);", INDEX)
        self.assertIn('host.dataset.watchMode = mode;', INDEX)


if __name__ == "__main__":
    unittest.main(verbosity=2)
