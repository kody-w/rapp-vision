"""Runtime-oriented checks for the exact paired-publication player code."""

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (
    (ROOT / "index.html")
    .read_text(encoding="utf-8")
    .replace("\r\n", "\n")
    .replace("\r", "\n")
)
NODE = shutil.which("node")


def source_block(start_marker, end_marker):
    start = INDEX.index(start_marker)
    end = INDEX.index(end_marker, start)
    return INDEX[start:end]


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


def channel_loader_block():
    start = INDEX.index("function absolutise(url, base)")
    end = INDEX.index("async function loadLegacyPolicy()")
    return INDEX[start:end]


class TestConsumerDiscovery(unittest.TestCase):
    def test_machine_readable_creator_and_catalog_discovery(self):
        head = source_block("<head>", "</head>")
        self.assertRegex(
            head,
            r"<link\s+rel=(?:['\"])?alternate(?:['\"])?\s+"
            r"type=(?:['\"])?application/json(?:['\"])?\s+"
            r"href=(?:['\"])?agent\.json(?:['\"])?\s+"
            r"title=['\"]RAPP Vision creator contract['\"]>",
        )
        self.assertRegex(
            head,
            r"<link\s+rel=(?:['\"])?alternate(?:['\"])?\s+"
            r"type=(?:['\"])?application/json(?:['\"])?\s+"
            r"href=(?:['\"])?channels\.json(?:['\"])?\s+"
            r"title=['\"]RAPP Vision channel catalog['\"]>",
        )

    def test_creator_cta_is_small_prominent_and_only_in_unfiltered_home_hero(self):
        header = source_block("<header>", "</header>")
        home = source_block("function viewHome(", "/* ---------------------------------------------------------------- *")
        self.assertRegex(
            header,
            r'<a class="navbtn" href="agent\.json"[^>]*>Create with an agent</a>',
        )
        self.assertIn('${q || tag ? "" : `<section class="hero">', home)
        self.assertRegex(
            home,
            r'<a class="tbtn mode-switch" href="agent\.json">'
            r"Create with an agent</a>",
        )
        self.assertLess(home.index('href="agent.json"'), home.index("Under the hood"))
        self.assertIn('id="nav-ch">RAPP Hive</button>', header)
        self.assertIn(
            "https://github.com/kody-w/rapp-vision/tree/main/template",
            INDEX,
        )

    def test_machine_review_indicator_is_review_gated_and_honest(self):
        indicator = source_block(
            "function reviewIndicatorHTML(", "function reviewHTML(",
        )
        card = source_block("function cardHTML(", "function matches(")
        watch = source_block("function viewWatch(", "function viewLibrary(")
        self.assertIn("!m.review.on", indicator)
        self.assertIn("m.review.on !== v._recordSha8", indicator)
        self.assertIn(">Machine reviewed</span>", indicator)
        self.assertIn("not human approval or registry curation", indicator)
        self.assertIn("m = mget(v)", card)
        self.assertIn("${reviewIndicatorHTML(v, m)}", card)
        self.assertIn("reviewIndicatorHTML(v, mget(v))", watch)
        self.assertIn('${reviewIndicator ? ` ${reviewIndicator}` : ""}', watch)

        gate = indicator[: indicator.index("return `<span")]
        self.assertNotIn("_trustedLive", gate)
        self.assertNotIn("_registry", gate)
        self.assertNotRegex(indicator, r">\s*(?:Approved|Curated|Verified)\s*<")

    def test_late_metrics_patch_review_indicators_once_per_surface(self):
        patch = source_block(
            "function patchReviewIndicator(", "function applyMetrics(",
        )
        apply_metrics = source_block(
            "function applyMetrics()", "/* registry identity:start */",
        )
        self.assertIn('$(".machine-reviewed", target)', patch)
        self.assertIn(
            "const indicator = reviewIndicatorHTML(v, m);",
            patch,
        )
        self.assertEqual(apply_metrics.count("patchReviewIndicator("), 2)
        self.assertIn('const watchReview = $("#watch-review[data-vk]");', apply_metrics)
        self.assertIn(
            "videoForKey(watchReview.dataset.vk)",
            apply_metrics,
        )
        self.assertIn(
            'document.querySelectorAll(".card[data-vk]").forEach',
            apply_metrics,
        )
        self.assertIn("patchReviewIndicator(wrap, video, m);", apply_metrics)


@unittest.skipUnless(NODE, "node not available; exact player validation test skipped")
class TestPairedPlayer(unittest.TestCase):
    def run_node(self, body):
        completed = subprocess.run(
            [NODE, "-"],
            cwd=ROOT,
            input=body,
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

    def test_browser_review_fingerprint_matches_metrics_writer(self):
        record = json.loads(
            (ROOT / "tiny-systems" / "channel.json").read_text(
                encoding="utf-8"
            )
        )["videos"][0]
        record["integral_float"] = 10.0
        record["exponent"] = 1e-7
        record["negative_zero"] = -0.0
        record["rounding_tie"] = 707693033.1894531
        record["unpaired_surrogate"] = "\ud800"
        record["\udfff"] = "surrogate key"
        clean = {
            key: value
            for key, value in record.items()
            if not str(key).startswith("_")
        }
        sys.path.insert(0, str(ROOT / "scripts"))
        import rapp_metrics

        expected = rapp_metrics.record_fingerprint(clean)
        helpers = source_block(
            "function canonicalRecordJSON(", "function parseRecord(",
        )
        script = f"""
        if (!globalThis.crypto) globalThis.crypto = require("crypto").webcrypto;
        {helpers}
        recordSha8({json.dumps(record, ensure_ascii=True)}).then(actual => {{
          if (actual !== {json.dumps(expected)})
            throw new Error(`fingerprint mismatch: ${{actual}}`);
        }}).catch(error => {{ console.error(error); process.exit(1); }});
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

    def test_browser_rejects_explicit_null_optionals(self):
        nulls = json.dumps(json.loads(
            (ROOT / "tests/fixtures/publications/invalid-null-optionals.json").read_text()
        ))
        script = f"""
        if (!globalThis.crypto) globalThis.crypto = require("crypto").webcrypto;
        let LEGACY_POLICY = {{channels:[]}};
        {contract_block()}
        (async () => {{
          const errors = await validateChannelContract(
            {nulls}, "https://example.test/channel.json"
          );
          for (const expected of [
            "videos[0].chapters: must be an array",
            "live.duration: must be greater than zero",
            "live.chapters: must be an array",
            "scenes[0].actions: must be an array"
          ]) {{
            if (!errors.some(error => error.includes(expected)))
              throw new Error(`browser accepted explicit null: ${{expected}}`);
          }}
        }})().catch(error => {{ console.error(error); process.exit(1); }});
        """
        self.run_node(script)

    def test_browser_rejects_unsafe_apps_and_fake_dual_sources(self):
        valid = json.dumps(json.loads(
            (ROOT / "tests/fixtures/publications/valid-paired.json").read_text()
        ))
        script = f"""
        if (!globalThis.crypto) globalThis.crypto = require("crypto").webcrypto;
        let LEGACY_POLICY = {{channels:[]}};
        {contract_block()}
        (async () => {{
          for (const app of [
            "javascript:alert(1)", "data:text/html,bad", "blob:https://example.test/id",
            "file:///tmp/app.html", "http://example.test/app.html",
            "//example.test/app.html", "\\\\\\\\example.test\\\\app.html",
            "https://[", "../app.html;execute", "../app.html%3Bexecute",
            "../app%2Fchild.html", "../app%5Cchild.html",
            "https://example.test:999999/app.html"
          ]) {{
            const channel = {valid};
            channel.videos[0].live.scenes[1].app = app;
            const errors = await validateChannelContract(
              channel, "https://example.test/channel.json"
            );
            if (!errors.some(error => error.includes("safe relative URL or absolute HTTPS URL")))
              throw new Error(`unsafe app accepted: ${{app}}`);
          }}
          if (!safeResolvedAppUrl(
            "../app.html",
            "https://example.test/app.html",
            "https://example.test/channel.json"
          )) throw new Error("safe relative app resolution rejected");
          if (safeResolvedAppUrl(
            "javascript:alert(1)",
            "javascript:alert(1)",
            "https://example.test/channel.json"
          )) throw new Error("unsafe resolved app accepted");

          const wrong = {valid};
          wrong.videos[0].sources[0].src = "paired.webm";
          let errors = await validateChannelContract(
            wrong, "https://example.test/channel.json"
          );
          if (!errors.some(error => error.includes("video/mp4 requires a .mp4 pathname")))
            throw new Error("mismatched extension accepted");

          const parameterized = {valid};
          parameterized.videos[0].sources[0].src = "paired.mp4;served-as-html";
          errors = await validateChannelContract(
            parameterized, "https://example.test/channel.json"
          );
          if (!errors.some(error => error.includes("pathname parameters are not allowed")))
            throw new Error("parameterized media path accepted");

          const encoded = {valid};
          encoded.videos[0].sources[0].src = "paired.mp4%3Bserved-as-html";
          errors = await validateChannelContract(
            encoded, "https://example.test/channel.json"
          );
          if (!errors.some(error => error.includes("pathname parameters are not allowed")))
            throw new Error("encoded parameterized media path accepted");

          const whitespaceMime = {valid};
          whitespaceMime.videos[0].sources[0].type = "video/mp4 ; codecs=\\\"avc1\\\"";
          errors = await validateChannelContract(
            whitespaceMime, "https://example.test/channel.json"
          );
          if (errors.some(error => error.includes("only video/mp4 and video/webm")))
            throw new Error("trimmed lowercase MIME was rejected");

          const duplicate = {valid};
          duplicate.videos[0].sources = [
            {{src:"same.mp4#one",type:"video/mp4"}},
            {{src:"same.mp4#two",type:"video/mp4"}},
            {{src:"other.webm",type:"video/webm"}}
          ];
          errors = await validateChannelContract(
            duplicate, "https://example.test/channel.json"
          );
          if (!errors.some(error => error.includes("media source URLs must be distinct")))
            throw new Error("duplicate media URL accepted");
        }})().catch(error => {{ console.error(error); process.exit(1); }});
        """
        self.run_node(script)

    def test_browser_rejects_scoped_identity_separator_collisions(self):
        valid = json.dumps(json.loads(
            (ROOT / "tests/fixtures/publications/valid-paired.json").read_text()
        ))
        script = f"""
        if (!globalThis.crypto) globalThis.crypto = require("crypto").webcrypto;
        let LEGACY_POLICY = {{channels:[]}};
        {contract_block()}
        (async () => {{
          const channelSlash = {valid};
          channelSlash.id = "a/b";
          let errors = await validateChannelContract(
            channelSlash, "https://example.test/channel.json"
          );
          if (!errors.some(error => error.includes("channel.id: must start alphanumeric")))
            throw new Error("channel slash collision accepted");
          const publicationSlash = {valid};
          publicationSlash.videos[0].id = "b/c";
          errors = await validateChannelContract(
            publicationSlash, "https://example.test/channel.json"
          );
          if (!errors.some(error => error.includes("videos[0].id: must start alphanumeric")))
            throw new Error("publication slash collision accepted");
        }})().catch(error => {{ console.error(error); process.exit(1); }});
        """
        self.run_node(script)

    def test_same_permalink_switch_defaults_to_video_and_cleans_up(self):
        self.assertIn('mountMode(hasVideo ? "video" : "live", false)', INDEX)
        self.assertIn(">Try live replay</button>", INDEX)
        self.assertIn(">Watch guided video</button>", INDEX)
        self.assertIn(
            "function mountMode(next, announce = true, userInitiated = false) {\n    cleanupMode();",
            INDEX,
        )
        self.assertIn('document.removeEventListener("keydown", live.keys);', INDEX)
        self.assertIn("retryTimers.forEach(clearTimeout);", INDEX)
        self.assertIn('host.dataset.watchMode = mode;', INDEX)
        self.assertIn("const total = replayDuration(v.live);", INDEX)
        self.assertIn('next === "live" ? ((v.live && v.live.chapters) || [])', INDEX)
        self.assertIn('mode === "live" ? replayDuration(v.live) : v.duration', INDEX)
        self.assertIn('href="#/watch/${encodeURIComponent(vkey(v))}"', INDEX)
        self.assertIn('href="#/watch/${encodeURIComponent(vkey(x))}"', INDEX)
        self.assertIn("const appSrc = renderableAppUrl(s.app);", INDEX)
        self.assertIn("frame.src = appSrc;", INDEX)
        self.assertIn("sc.app = safeResolvedAppUrl(rawApp, resolvedApp, url);", INDEX)
        self.assertIn("c._trustedLive = !!entry._registry;", INDEX)
        self.assertIn("let liveAuthorized = !!v._ch._trustedLive;", INDEX)
        self.assertIn("Start live replay", INDEX)
        self.assertIn('mountMode(hasVideo ? "video" : "live", false);', INDEX)

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

    def test_browser_rejects_registry_contract_schema_mismatch(self):
        legacy = json.dumps(json.loads(
            (ROOT / "channel.json").read_text(encoding="utf-8")
        ))
        policy = json.dumps(json.loads(
            (ROOT / "policy/legacy-publications.json").read_text(encoding="utf-8")
        ))
        script = f"""
        if (!globalThis.crypto) globalThis.crypto = require("crypto").webcrypto;
        globalThis.location = {{href:"https://kody-w.github.io/rapp-vision/"}};
        let LEGACY_POLICY = {policy};
        {contract_block()}
        {channel_loader_block()}
        globalThis.fetch = async () => ({{
          ok:true,
          json:async () => ({legacy})
        }});
        (async () => {{
          try {{
            await fetchChannel({{
              id:"rock-tumbler",
              url:"channel.json",
              contract:CURRENT_CHANNEL_SCHEMA,
              _registry:true
            }});
            throw new Error("registry accepted v1 content declared as v2");
          }} catch (error) {{
            if (!String(error.message).includes(
              "registry declaration requires channel schema rapp-vision-channel/2.0"
            )) throw error;
          }}
        }})().catch(error => {{ console.error(error); process.exit(1); }});
        """
        self.run_node(script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
