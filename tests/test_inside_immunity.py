"""Contract, media, and state-transition checks for the T-cell publication."""

import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHANNEL = ROOT / "inside-immunity" / "channel.json"
SOURCE_URL = "https://kody-w.github.io/rapp-vision/inside-immunity/channel.json"


class ElementIds(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        value = dict(attrs).get("id")
        if value:
            self.ids.add(value)


class TestInsideImmunity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.channel = json.loads(CHANNEL.read_text(encoding="utf-8"))
        cls.video = cls.channel["videos"][0]

    def test_current_publication_contract_and_registry(self):
        spec = importlib.util.spec_from_file_location(
            "inside_immunity_validator", ROOT / "scripts" / "validate_publications.py"
        )
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        policy = json.loads((ROOT / "policy" / "legacy-publications.json").read_text())
        self.assertEqual(validator.validate_channel(self.channel, SOURCE_URL, policy), [])
        registry = json.loads((ROOT / "channels.json").read_text())
        matches = [item for item in registry["channels"] if item["id"] == "inside-immunity"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["url"], "inside-immunity/channel.json")
        self.assertEqual(matches[0]["contract"], "rapp-vision-channel/2.0")
        self.assertEqual(self.video["duration"], 300)
        self.assertEqual(len(self.video["chapters"]), 12)

    def test_both_real_media_formats_have_video_and_narration(self):
        ffprobe = os.environ.get("RAPP_FFPROBE") or shutil.which("ffprobe")
        self.assertTrue(ffprobe, "A real ffprobe is required for this publication.")
        expected = {"video/mp4": "h264", "video/webm": "vp9"}
        self.assertEqual({source["type"] for source in self.video["sources"]}, set(expected))
        for source in self.video["sources"]:
            path = CHANNEL.parent / source["src"]
            with self.subTest(format=source["type"]):
                self.assertGreater(path.stat().st_size, 1000000)
                result = subprocess.run(
                    [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                    capture_output=True, text=True, check=True,
                )
                probe = json.loads(result.stdout)
                video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
                self.assertEqual(video["codec_name"], expected[source["type"]])
                self.assertEqual((video["width"], video["height"]), (1920, 1080))
                self.assertTrue(any(stream["codec_type"] == "audio" for stream in probe["streams"]))
                self.assertAlmostEqual(float(probe["format"]["duration"]), 300, delta=0.1)

    def test_live_script_targets_real_controls_and_finishes_with_reset(self):
        live = self.video["live"]
        self.assertEqual(live["duration"], 60)
        cursor = 0
        app_scene = None
        for scene in live["scenes"]:
            self.assertEqual(scene["t"], cursor)
            cursor += scene["dur"]
            if "app" in scene:
                app_scene = scene
        self.assertEqual(cursor, 60)
        self.assertIsNotNone(app_scene)
        source = (CHANNEL.parent / app_scene["app"]).read_text(encoding="utf-8")
        parser = ElementIds()
        parser.feed(source)
        selectors = []
        for action in app_scene["actions"]:
            self.assertGreaterEqual(action["at"], 0)
            self.assertLess(action["at"], app_scene["dur"])
            self.assertIn(action["selector"][1:], parser.ids)
            selectors.append(action["selector"])
        self.assertEqual(selectors[-1], "#reset-btn")
        for selector in ("#signal-btn", "#different-btn", "#class-two-btn", "#inactive-btn", "#antibody-btn"):
            self.assertIn(selector, selectors)
        self.assertIn('data-ready=\\"true\\"', json.dumps(app_scene["ready"]))

    def test_evidence_binds_the_published_media_and_reset(self):
        evidence = json.loads((CHANNEL.parent / "evidence.json").read_text())
        self.assertEqual(evidence["publication"], self.video["id"])
        for extension in ("mp4", "webm"):
            item = evidence["guided"][extension]
            actual = hashlib.sha256((CHANNEL.parent / item["path"]).read_bytes()).hexdigest()
            self.assertEqual(actual, item["sha256"])
        self.assertTrue(evidence["live"]["reset"]["observed_exact"])
        self.assertTrue(evidence["live"]["assembled_replay_reached_exact_reset"])
        self.assertEqual(evidence["live"]["accepted_projection"],
                         ["acceptedCount", "lastAccepted", "targetStatus"])

    def test_actual_model_positive_rejections_preservation_and_reset(self):
        node = shutil.which("node")
        self.assertTrue(node, "Node is required to execute the shipped model.")
        model_uri = (CHANNEL.parent / "apps" / "t-cell-model.mjs").resolve().as_uri()
        script = """
import assert from 'node:assert/strict';
import {initialState, selectScenario, applyAction} from MODEL;
const accepted = s => ({acceptedCount:s.acceptedCount, lastAccepted:s.lastAccepted, targetStatus:s.targetStatus});
const opening = initialState();
const success = applyAction(opening, 'signal');
assert.equal(success.acceptedCount, 1);
assert.equal(success.targetStatus, 'apoptosis');
assert.equal(success.decision, 'accepted');
assert.deepEqual(opening, initialState());
for (const scenario of ['different','class-two','inactive']) {
  const before = selectScenario(success, scenario);
  const rejected = applyAction(before, 'signal');
  assert.equal(rejected.decision, 'rejected');
  assert.deepEqual(accepted(rejected), accepted(before));
  assert.match(rejected.message, /Rejected/);
}
const wrongJob = applyAction(success, 'antibody');
assert.equal(wrongJob.decision, 'rejected');
assert.deepEqual(accepted(wrongJob), accepted(success));
assert.match(wrongJob.message, /plasma cells/);
assert.deepEqual(applyAction(wrongJob, 'reset'), opening);
assert.throws(()=>selectScenario(opening, '__proto__'), RangeError);
assert.throws(()=>applyAction(opening, 'unknown'), RangeError);
console.log('All real model transitions passed.');
""".replace("MODEL", json.dumps(model_uri))
        result = subprocess.run([node, "--input-type=module", "-e", script],
                                capture_output=True, text=True, check=True)
        self.assertIn("All real model transitions passed.", result.stdout)

    def test_public_payload_has_no_private_production_paths_or_credentials(self):
        for path in CHANNEL.parent.rglob("*"):
            if path.suffix not in {".json", ".html", ".mjs", ".srt", ".vtt"}:
                continue
            text = path.read_text(encoding="utf-8")
            for forbidden in ("/Users/", "/private/var/", "file://", "gho_", "github_pat_"):
                self.assertNotIn(forbidden, text, f"{path.name} contains a private marker")
        self.assertTrue((CHANNEL.parent / "captions" / "t-cells.en.vtt").is_file())
        self.assertTrue((CHANNEL.parent / "sources.html").is_file())


if __name__ == "__main__":
    unittest.main()
