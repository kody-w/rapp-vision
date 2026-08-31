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


def identity_block():
    start = INDEX.index("/* publication identity:start */")
    end = INDEX.index("/* publication identity:end */") + len("/* publication identity:end */")
    return INDEX[start:end]


def registry_identity_block():
    start = INDEX.index("/* registry identity:start */")
    end = INDEX.index("/* registry identity:end */") + len("/* registry identity:end */")
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
        frame_chains = json.dumps(json.loads(
            (ROOT / "frame-chains/channel.json").read_text()
        ))
        script = f"""
        if (!globalThis.crypto) globalThis.crypto = require("crypto").webcrypto;
        let LEGACY_POLICY = {policy};
        {contract_block()}
        (async () => {{
          const validErrors = await validateChannelContract({valid}, "https://example.test/channel.json");
          const invalidErrors = await validateChannelContract({invalid}, "https://example.test/channel.json");
          if (validErrors.length) throw new Error(validErrors.join("\\n"));
          if (replayDuration({valid}.videos[0].live) !== 12)
            throw new Error("browser validator reused the 10 second film duration");
          const derivedReplay = JSON.parse(JSON.stringify({valid}.videos[0].live));
          delete derivedReplay.duration;
          if (replayDuration(derivedReplay) !== 12)
            throw new Error("browser player did not derive replay duration from scenes");
          if (!invalidErrors.some(e => e.includes("missing required video/webm")))
            throw new Error("browser validator accepted an MP4-only publication");
          const legacyErrors = await validateChannelContract(
            {frame_chains},
            "https://kody-w.github.io/rapp-vision/frame-chains/channel.json"
          );
          if (legacyErrors.length) throw new Error(legacyErrors.join("\\n"));
        }})().catch(error => {{ console.error(error); process.exit(1); }});
        """
        self.run_node(script)

    def test_channel_scoped_routes_state_and_collision_migration(self):
        script = f"""
        const rvObject = v => !!v && typeof v === "object" && !Array.isArray(v);
        let VIDEOS = [], ALL_VIDEOS = [], state = {{history: {{}}, liked: [], later: []}};
        let LEGACY_POLICY = {{channels:[{{
          id:"alpha", publications:[{{id:"shared",sha256:"unused"}}]
        }}]}};
        {identity_block()}
        const channelA = {{id:"alpha"}}, channelB = {{id:"beta"}};
        const a = {{id:"shared", _ch:channelA, sources:[{{src:"a.mp4"}}], live:{{scenes:[]}}}};
        const b = {{id:"shared", _ch:channelB, sources:[{{src:"b.mp4"}}], live:{{scenes:[]}}}};
        ALL_VIDEOS = [a, b]; VIDEOS = [b, a];
        if (byId("shared") !== a) throw new Error("frozen owner mapping ignored");
        VIDEOS = [a, b];
        if (byId("shared") !== a) throw new Error("subscription reorder changed migration");
        if (byId("beta/shared") !== b) throw new Error("scoped route collision");
        if (historyKey(a, "video") !== "alpha/shared::video") throw new Error("alpha history key");
        if (historyKey(b, "live") !== "beta/shared::live") throw new Error("beta history key");
        state.history["shared::video"] = {{t:3,d:10}};
        if (historyRecord(a, "video").t !== 3) throw new Error("old history did not migrate");
        if (historyRecord(b, "video") !== null) throw new Error("old history leaked across collision");
        state.history[historyKey(b, "video")] = {{t:8,d:20}};
        if (historyRecord(b, "video").t !== 8) throw new Error("scoped history missing");
        if (historyVideo("beta/shared::video") !== b) throw new Error("scoped recent history collision");
        if (historyVideo("shared::video") !== a) throw new Error("old recent history migration");
        state.liked = ["shared"];
        if (!stateHasVideo(state.liked, a)) throw new Error("old like did not migrate");
        if (stateHasVideo(state.liked, b)) throw new Error("old like leaked across collision");
        state.later = ["beta/shared"];
        if (stateVideos(state.later)[0] !== b) throw new Error("scoped watch-later collision");
        LEGACY_POLICY = {{channels:[]}};
        if (byId("shared") !== undefined) throw new Error("ambiguous old link was silently assigned");
        if (stateHasVideo(["shared"], a) || stateHasVideo(["shared"], b))
          throw new Error("ambiguous old state was silently migrated");
        """
        self.run_node(script)

    def test_browser_rejects_legacy_content_replacement_boundary_action_and_mime_case(self):
        script = f"""
        if (!globalThis.crypto) globalThis.crypto = require("crypto").webcrypto;
        let LEGACY_POLICY = {{channels:[]}};
        {contract_block()}
        (async () => {{
          const video = {{id:"legacy",title:"Original",duration:5,sources:[]}};
          const source = "https://example.test/channel.json";
          const policy = {{channels:[{{id:"old",source,publications:[
            {{id:"legacy",sha256:await publicationSha256(video)}}
          ]}}]}};
          const channel = {{schema:LEGACY_CHANNEL_SCHEMA,id:"old",name:"Old",videos:[video]}};
          if ((await validateChannelContract(channel, source, policy)).length)
            throw new Error("exact legacy content rejected");
          channel.videos[0].title = "Replacement";
          const replaced = await validateChannelContract(channel, source, policy);
          if (!replaced.some(e => e.includes("frozen legacy digest")))
            throw new Error("legacy replacement accepted");

          const paired = {json.dumps(json.loads(
              (ROOT / "tests/fixtures/publications/valid-paired.json").read_text()
          ))};
          paired.videos[0].live.scenes[1].actions[0].at = paired.videos[0].live.scenes[1].dur;
          const boundary = await validateChannelContract(paired, source, policy);
          if (!boundary.some(e => e.includes("less than the scene duration")))
            throw new Error("boundary action accepted");
          paired.videos[0].live.scenes[1].actions[0].at = 1;
          paired.videos[0].sources[0].type = "Video/MP4";
          const mime = await validateChannelContract(paired, source, policy);
          if (!mime.some(e => e.includes("only video/mp4 and video/webm")))
            throw new Error("uppercase MIME accepted");
        }})().catch(error => {{ console.error(error); process.exit(1); }});
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
        self.assertIn("const total = replayDuration(v.live);", INDEX)
        self.assertIn('next === "live" ? ((v.live && v.live.chapters) || [])', INDEX)
        self.assertIn('mode === "live" ? replayDuration(v.live) : v.duration', INDEX)
        self.assertIn('href="#/watch/${encodeURIComponent(vkey(v))}"', INDEX)
        self.assertIn('href="#/watch/${encodeURIComponent(vkey(x))}"', INDEX)

    def test_browser_rejects_registry_id_mismatch_and_duplicate_resolved_channels(self):
        self.assertIn("entry._registry && entry.id !== c.id", INDEX)
        script = f"""
        {registry_identity_block()}
        const duplicate = {{id:"resolved"}};
        const result = collectUniqueChannels(
          [
            {{status:"fulfilled",value:duplicate}},
            {{status:"fulfilled",value:duplicate}}
          ],
          [{{id:"first"}},{{id:"second"}}]
        );
        if (result.channels.length !== 1) throw new Error("duplicate channel loaded twice");
        if (result.failed.length !== 1 || result.failed[0] !== "second")
          throw new Error("duplicate channel was not rejected deterministically");
        """
        self.run_node(script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
