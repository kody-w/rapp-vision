"""Publication regressions for the spoken, visible context repair."""

import hashlib
import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHANNEL = ROOT / "frame-chains"
PUBLICATION = "frame-chains-ten-frame-loop"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class FrameChainsGroundingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.channel = load(CHANNEL / "channel.json")
        cls.video = next(row for row in cls.channel["videos"] if row["id"] == PUBLICATION)
        cls.revision = load(CHANNEL / "context/ten-worlds-v2.json")
        cls.intro = load(CHANNEL / "context/intro-v2.json")

    def test_revision_is_not_a_new_episode_or_an_overwritten_source(self):
        self.assertEqual(self.revision["kind"], "context-repair")
        self.assertIs(self.revision["is_new_episode"], False)
        self.assertEqual(self.revision["publication"], PUBLICATION)
        self.assertEqual(len(self.channel["videos"]), 5)
        original = self.revision["ancestor"]["delivery"]
        for kind in ("mp4", "webm"):
            path = CHANNEL / original[kind]["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), original[kind]["sha256"])
            self.assertNotEqual(
                original[kind]["path"],
                next(source["src"] for source in self.video["sources"] if source["type"] == f"video/{kind}"),
            )

    def test_every_original_app_action_is_preserved_in_order(self):
        original = [
            scene for scene in self.revision["ancestor"]["publication"]["live"]["scenes"]
            if "app" in scene
        ]
        actual = [
            scene for scene in self.video["live"]["scenes"]
            if scene.get("app", "").startswith("../../frame-chains/showcase/")
        ]
        self.assertEqual(len(original), 10)
        self.assertEqual(len(actual), 10)
        for before, after in zip(original, actual):
            self.assertEqual(
                {key: value for key, value in before.items() if key != "t"},
                {key: value for key, value in after.items() if key != "t"},
            )
            position = self.video["live"]["scenes"].index(after)
            self.assertIn("card", self.video["live"]["scenes"][position - 1])

    def test_narrated_context_comes_before_the_original_tour(self):
        self.assertEqual(self.intro["schema"], "rapp-vision-topic-intro/1")
        self.assertEqual(len(self.intro["chapters"]), 3)
        scenes = self.video["live"]["scenes"]
        for index, chapter in enumerate(self.intro["chapters"]):
            self.assertEqual(scenes[index]["app"], f"apps/topic-intro.html?chapter={index}")
            self.assertEqual(scenes[index]["actions"], [{"at": 0.5, "do": "click", "selector": "#hear"}])
            self.assertEqual(scenes[index]["ready"], {"selector": "html[data-ready=\"true\"]"})
            self.assertGreaterEqual(scenes[index]["dur"], math.ceil(chapter["audio"]["duration_ms"] / 1000) + 1)
            self.assertTrue(chapter["copy"])
            audio = CHANNEL / "context" / chapter["audio"]["src"]
            self.assertTrue(audio.is_file())
            self.assertFalse(audio.is_symlink())
            self.assertEqual(hashlib.sha256(audio.read_bytes()).hexdigest(), chapter["audio"]["sha256"])
        all_apps = [scene["app"] for scene in scenes if "app" in scene]
        self.assertEqual(len(all_apps), 13)
        self.assertTrue(all(
            app.startswith("../../frame-chains/showcase/") or app in {
                f"apps/topic-intro.html?chapter={index}" for index in range(3)
            }
            for app in all_apps
        ))

    def test_plain_topic_definitions_and_synchronized_captions_are_present(self):
        narration = " ".join(row["narration"] for row in self.intro["chapters"]).lower()
        for term in ("state", "frame", "chain", "hash", "verifier", "accepted head", "branch"):
            self.assertIn(term, narration)
        self.assertIn("not a picture in a movie", narration)
        self.assertIn("not real colonies", narration)
        self.assertNotIn("rapp vision pairs", narration)
        captions = self.revision["captions"]
        path = CHANNEL / captions["path"]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), captions["sha256"])
        self.assertTrue(path.read_text(encoding="utf-8").startswith("WEBVTT"))


if __name__ == "__main__":
    unittest.main()
