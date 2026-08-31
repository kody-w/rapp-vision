"""Focused offline contract and privacy tests for the Frame Chains channel."""

import json
import os
import re
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlparse


ROOT = Path(__file__).resolve().parents[1]
CHANNEL_PATH = ROOT / "frame-chains" / "channel.json"
CHANNEL_URL = "https://kody-w.github.io/rapp-vision/frame-chains/channel.json"
SHOWCASE_ROOT = "https://kody-w.github.io/frame-chains/showcase/"

VIDEO_IDS = [
    "frame-chains-ten-frame-loop",
    "many-worlds-mission-control",
    "ai-soul-passport",
    "teleporting-roguelike",
    "attack-the-timeline",
]

APP_SELECTORS = {
    "01-many-worlds": {"#guided-btn", "#mutate-btn"},
    "02-soul-passport": {
        "#guided-button",
        "#forge-button",
        "#verify-button",
    },
    "03-mars-colony": {"#nextButton"},
    "04-five-realities": {"#guideBtn", "#mutationBtn"},
    "05-causal-detective": {
        "#guidedBtn",
        '.cite-btn[data-id="E02"]',
        '.cite-btn[data-id="E03"]',
        '.cite-btn[data-id="E04"]',
        '.cite-btn[data-id="E06"]',
        '.cite-btn[data-id="E07"]',
        "#accuseBtn",
        "#mutateBtn",
    },
    "06-space-station": {"#guided"},
    "07-constitution": {"#guidedBtn", "#tyrantBtn"},
    "08-teleporting-roguelike": {"#runDemo", "#forgeItem", "#forgeParent"},
    "09-attack-timeline": {"#controlBtn", "#attackAllBtn", "#replayBtn"},
    "10-futures-museum": {"#playBtn", "#mutateBtn"},
}

UNSAFE_TEXT = (
    re.compile(r"file://", re.I),
    re.compile(r"\b(?:localhost|0\.0\.0\.0|127(?:\.\d{1,3}){3}|::1)\b", re.I),
    re.compile(r"(?:^|[\s\"'])/(?:Users|home|private|Volumes)/", re.I),
    re.compile(r"\b[A-Z]:\\"),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b", re.I),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def app_scenes(video):
    return [scene for scene in video["live"]["scenes"] if "app" in scene]


class ElementIndex(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, _tag, attrs):
        self.elements.append(dict(attrs))


def static_selector_exists(selector, elements):
    if selector.startswith("#"):
        target_id = selector[1:]
        return any(attrs.get("id") == target_id for attrs in elements)

    match = re.fullmatch(
        r'\.([A-Za-z0-9_-]+)\[([A-Za-z0-9_-]+)="([^"]+)"\]',
        selector,
    )
    if not match:
        raise AssertionError(f"unsupported action selector in local HTML test: {selector}")
    class_name, attribute, value = match.groups()
    return any(
        class_name in attrs.get("class", "").split()
        and attrs.get(attribute) == value
        for attrs in elements
    )


def generated_selector_contract_exists(selector, source):
    match = re.fullmatch(
        r'\.([A-Za-z0-9_-]+)\[([A-Za-z0-9_-]+)="([^"]+)"\]',
        selector,
    )
    if not match:
        return False

    class_name, attribute, value = match.groups()
    class_template = re.search(
        rf'(?:class\s*=\s*"[^"]*(?<![\w-]){re.escape(class_name)}(?![\w-])'
        rf"|class\s*=\s*'[^']*(?<![\w-]){re.escape(class_name)}(?![\w-]))",
        source,
    )
    dynamic_attribute = re.search(
        rf'{re.escape(attribute)}\s*=\s*["\']\s*\$\{{\s*'
        r'[A-Za-z_$][\w$]*\.id\s*\}\s*["\']',
        source,
    )
    evidence_ids = set(re.findall(
        r'\bid\s*:\s*["\']([A-Za-z0-9_-]+)["\']',
        source,
    ))
    return bool(class_template and dynamic_attribute and value in evidence_ids)


class TestFrameChainsChannel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.channel = load_json(CHANNEL_PATH)
        cls.videos = {video["id"]: video for video in cls.channel["videos"]}

    def test_channel_and_registry_contract(self):
        self.assertEqual(self.channel["schema"], "rapp-vision-channel/1.0")
        self.assertEqual(self.channel["id"], "frame-chains")
        self.assertEqual(list(self.videos), VIDEO_IDS)

        registry = load_json(ROOT / "channels.json")
        matches = [entry for entry in registry["channels"] if entry["id"] == "frame-chains"]
        self.assertEqual(
            matches,
            [{
                "id": "frame-chains",
                "name": "Frame Chains",
                "url": "frame-chains/channel.json",
                "repo": "https://github.com/kody-w/frame-chains",
                "legacy": "legacy-publications-2026-08-31",
                "_why": (
                    "Ten public synthetic showcase apps replayed live from GitHub Pages, "
                    "including focused adversarial proofs for branching, identity, "
                    "provenance, and timeline integrity."
                ),
            }],
        )
        self.assertEqual(registry["channels"][-1]["id"], "frame-chains")

    def test_every_entry_is_a_landscape_live_replay(self):
        for video in self.videos.values():
            with self.subTest(video=video["id"]):
                self.assertEqual(video["sources"], [])
                self.assertEqual(video["live"]["kind"], "rapp-vision-live/1.0")
                self.assertEqual(video["published"], "2026-08-30")
                self.assertEqual((video["width"], video["height"]), (1280, 800))
                self.assertEqual(video["orientation"], "landscape")
                self.assertTrue(video["chapters"])
                self.assertEqual(video["chapters"][0]["t"], 0)
                self.assertIn("live", video["description"].lower())
                self.assertTrue(
                    any("captured" in scene["card"].get("sub", "").lower()
                        or "captured" in scene["card"].get("note", "").lower()
                        or "recorded" in scene["card"].get("title", "").lower()
                        for scene in video["live"]["scenes"] if "card" in scene)
                )

    def test_scenes_are_contiguous_and_fill_declared_duration(self):
        for video in self.videos.values():
            cursor = 0
            for scene in video["live"]["scenes"]:
                with self.subTest(video=video["id"], scene=scene["t"]):
                    self.assertEqual(scene["t"], cursor)
                    self.assertGreater(scene["dur"], 0)
                    cursor += scene["dur"]
            self.assertEqual(cursor, video["duration"])

    def test_all_app_paths_resolve_to_public_showcase_pages(self):
        for video in self.videos.values():
            for scene in app_scenes(video):
                relative = scene["app"]
                slug = PurePosixPath(relative).parts[-2]
                with self.subTest(video=video["id"], app=relative):
                    self.assertEqual(
                        relative,
                        f"../../frame-chains/showcase/{slug}/index.html",
                    )
                    self.assertIn(slug, APP_SELECTORS)
                    self.assertEqual(
                        urljoin(CHANNEL_URL, relative),
                        f"{SHOWCASE_ROOT}{slug}/index.html",
                    )
                    parsed = urlparse(urljoin(CHANNEL_URL, relative))
                    self.assertEqual(parsed.scheme, "https")
                    self.assertEqual(parsed.netloc, "kody-w.github.io")

    def test_ten_frame_loop_covers_every_app_in_order(self):
        loop = self.videos["frame-chains-ten-frame-loop"]
        slugs = [PurePosixPath(scene["app"]).parts[-2] for scene in app_scenes(loop)]
        self.assertEqual(slugs, list(APP_SELECTORS))
        self.assertIn("card", loop["live"]["scenes"][0])
        self.assertIn("card", loop["live"]["scenes"][-1])
        mars_actions = app_scenes(loop)[2]["actions"]
        self.assertEqual(
            [action["selector"] for action in mars_actions],
            ["#nextButton"] * 8,
        )
        self.assertEqual(
            [action["at"] for action in mars_actions],
            [0.5, 6.5, 12.5, 18.5, 24.5, 30.5, 36.5, 42.5],
        )
        soul_actions = app_scenes(loop)[1]["actions"]
        self.assertEqual(
            [action["selector"] for action in soul_actions],
            ["#guided-button", "#forge-button", "#verify-button"],
        )
        self.assertGreaterEqual(
            soul_actions[2]["at"] - soul_actions[1]["at"],
            4,
            "Frame 02 needs settling time before independent verification",
        )
        causal_actions = app_scenes(loop)[4]["actions"]
        self.assertEqual(
            [action["selector"] for action in causal_actions],
            [
                "#guidedBtn",
                '.cite-btn[data-id="E02"]',
                '.cite-btn[data-id="E03"]',
                '.cite-btn[data-id="E04"]',
                '.cite-btn[data-id="E06"]',
                '.cite-btn[data-id="E07"]',
                "#accuseBtn",
                "#mutateBtn",
            ],
        )
        causal_times = [action["at"] for action in causal_actions]
        self.assertTrue(
            all(later - earlier >= 4
                for earlier, later in zip(causal_times, causal_times[1:])),
            "Frame 05 actions need settling time between selector clicks",
        )
        station_actions = app_scenes(loop)[5]["actions"]
        self.assertEqual(
            [action["selector"] for action in station_actions],
            ["#guided"],
        )

    def test_focused_entries_use_the_required_sequences(self):
        expected = {
            "many-worlds-mission-control": [
                "#guided-btn", "#mutate-btn",
            ],
            "ai-soul-passport": [
                "#guided-button", "#forge-button", "#verify-button",
            ],
            "teleporting-roguelike": [
                "#runDemo", "#forgeItem", "#forgeParent",
            ],
            "attack-the-timeline": [
                "#controlBtn", "#attackAllBtn", "#replayBtn",
            ],
        }
        for video_id, selectors in expected.items():
            scenes = app_scenes(self.videos[video_id])
            self.assertEqual(len(scenes), 1)
            self.assertEqual(
                [action["selector"] for action in scenes[0]["actions"]],
                selectors,
            )

    def test_actions_are_selector_clicks_only(self):
        for video in self.videos.values():
            for scene in app_scenes(video):
                slug = PurePosixPath(scene["app"]).parts[-2]
                self.assertIn(scene["ready"]["selector"], APP_SELECTORS[slug])
                for action in scene["actions"]:
                    with self.subTest(video=video["id"], selector=action.get("selector")):
                        self.assertEqual(set(action), {"at", "do", "selector"})
                        self.assertEqual(action["do"], "click")
                        self.assertIn(action["selector"], APP_SELECTORS[slug])
                        self.assertGreaterEqual(action["at"], 0)
                        self.assertLess(action["at"], scene["dur"])

    def test_dynamic_selector_contract_checks_template_and_evidence(self):
        source = """
        const evidence = [{ id: "E02" }, { id: "E03" }];
        panel.innerHTML = evidence.map(e =>
          `<button class="cite-btn ${selected ? 'active' : ''}"
                   data-id="${e.id}">cite</button>`
        ).join("");
        """
        self.assertTrue(generated_selector_contract_exists(
            '.cite-btn[data-id="E02"]',
            source,
        ))
        self.assertFalse(generated_selector_contract_exists(
            '.cite-btn[data-id="E04"]',
            source,
        ))
        self.assertFalse(generated_selector_contract_exists(
            '.other-btn[data-id="E02"]',
            source,
        ))

    def test_action_selector_contracts_in_supplied_local_app_html(self):
        configured_root = os.environ.get("FRAME_CHAINS_ROOT")
        if not configured_root:
            self.skipTest("FRAME_CHAINS_ROOT not supplied")

        frame_chains_root = Path(configured_root).expanduser()
        self.assertTrue(
            frame_chains_root.is_dir(),
            f"FRAME_CHAINS_ROOT is not a directory: {frame_chains_root}",
        )
        indexes = {}
        sources = {}
        for video in self.videos.values():
            for scene in app_scenes(video):
                slug = PurePosixPath(scene["app"]).parts[-2]
                html_path = frame_chains_root / "showcase" / slug / "index.html"
                with self.subTest(video=video["id"], app=slug):
                    self.assertTrue(html_path.is_file(), f"missing local app: {html_path}")
                if slug not in indexes and html_path.is_file():
                    sources[slug] = html_path.read_text(encoding="utf-8")
                    parser = ElementIndex()
                    parser.feed(sources[slug])
                    indexes[slug] = parser.elements
                for action in scene["actions"]:
                    with self.subTest(
                        video=video["id"],
                        app=slug,
                        selector=action["selector"],
                    ):
                        selector = action["selector"]
                        self.assertTrue(
                            static_selector_exists(
                                selector,
                                indexes.get(slug, []),
                            )
                            or generated_selector_contract_exists(
                                selector,
                                sources.get(slug, ""),
                            ),
                            (
                                f"{selector} has neither a static element nor a "
                                f"generating template/evidence contract in {html_path}"
                            ),
                        )

    def test_thumbnails_exist_and_are_safe_authored_svg(self):
        for video in self.videos.values():
            thumb = video["thumb"]
            path = CHANNEL_PATH.parent / thumb
            with self.subTest(video=video["id"], thumb=thumb):
                self.assertTrue(thumb.startswith("thumbs/"))
                self.assertTrue(thumb.endswith(".svg"))
                self.assertTrue(path.is_file())
                root = ET.fromstring(path.read_text(encoding="utf-8"))
                self.assertTrue(root.tag.endswith("svg"))
                for element in root.iter():
                    tag = element.tag.rsplit("}", 1)[-1].lower()
                    self.assertNotIn(tag, {"script", "image", "foreignobject", "iframe"})
                    for name, value in element.attrib.items():
                        self.assertFalse(name.lower().startswith("on"))
                        self.assertNotIn("javascript:", value.lower())
                        self.assertNotIn("data:", value.lower())
                        self.assertNotIn("url(http", value.lower())

    def test_channel_and_thumbnails_contain_no_private_indicators(self):
        files = [CHANNEL_PATH, *sorted((CHANNEL_PATH.parent / "thumbs").glob("*.svg"))]
        for path in files:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                for pattern in UNSAFE_TEXT:
                    self.assertIsNone(pattern.search(text), pattern.pattern)

        for link in self.channel["links"]:
            parsed = urlparse(link["url"])
            self.assertEqual(parsed.scheme, "https")
            self.assertIn(parsed.netloc, {"github.com", "kody-w.github.io"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
