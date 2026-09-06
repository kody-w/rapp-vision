"""Keep the public creator north star discoverable and bound to one authority."""

import hashlib
import json
import re
import unicodedata
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HandbookParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.tags = []
        self.attributes = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.append(attrs)
        identifier = dict(attrs).get("id")
        if identifier:
            self.ids.add(identifier)

    def handle_data(self, data):
        self.text.append(data)


class TestCreatorHandbook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / "creator-handbook.html").read_bytes()
        cls.manifest = json.loads((ROOT / "creator-handbook.manifest.json").read_text())
        cls.parser = HandbookParser()
        cls.parser.feed(cls.raw.decode("utf-8"))

    def test_canonical_document_and_particle_are_bound(self):
        self.assertEqual(self.manifest["schema"], "rapp/1-html")
        self.assertEqual(self.manifest["file"], "creator-handbook.html")
        self.assertEqual(self.manifest["bytes"], len(self.raw))
        self.assertEqual(self.manifest["sha256"], hashlib.sha256(self.raw).hexdigest())
        particle = hashlib.sha256(b"rapp/1:particle\n" + self.raw).hexdigest()
        self.assertEqual(self.manifest["particle_hash"], particle)
        self.assertNotEqual(hashlib.sha256(b"rapp/1:particle\n" + self.raw + b"mutation").hexdigest(), particle)
        self.assertNotIn(b"\r", self.raw)
        self.assertEqual(unicodedata.normalize("NFC", self.raw.decode()), self.raw.decode())
        for attrs in self.parser.attributes:
            names = [name for name, _value in attrs]
            self.assertEqual(names, sorted(names))
            self.assertEqual(len(names), len(set(names)))

    def test_document_is_inactive_and_has_the_actual_quality_sections(self):
        for forbidden in ("script", "style", "iframe", "object", "embed", "base"):
            self.assertNotIn(forbidden, self.parser.tags)
        for attrs in self.parser.attributes:
            self.assertFalse(any(name.startswith("on") for name, _value in attrs))
        self.assertTrue({
            "north-star", "grounding", "frames", "good-bad", "craft", "proof",
            "truth", "culture", "process", "automation", "release", "brief", "agent-instructions",
        }.issubset(self.parser.ids))
        text = " ".join(self.parser.text)
        for phrase in (
            "what the viewer understands",
            "cold-reader test",
            "format, not the topic",
            "Necessary context may repeat",
            "Technical validity is the floor",
            "generation and publication separate",
            "Publish, revise, or reject",
        ):
            self.assertIn(phrase.lower(), text.lower())

    def test_every_creator_entry_point_references_the_same_authority(self):
        agent = json.loads((ROOT / "agent.json").read_text())
        self.assertEqual(agent["creator_handbook"], "creator-handbook.html")
        self.assertEqual(agent["creator_handbook_manifest"], "creator-handbook.manifest.json")
        schema = json.loads((ROOT / "agent.schema.json").read_text())
        self.assertIn("creator_handbook", schema["properties"])
        for relative in ("README.md", "CREATOR-HANDBOOK.md", "docs/CREATOR-INGRESS.md", "index.html"):
            self.assertIn("creator-handbook.html", (ROOT / relative).read_text(), relative)
        adapter = (ROOT / "CREATOR-HANDBOOK.md").read_text()
        self.assertIn(self.manifest["particle_hash"], adapter)
        self.assertIn("not a second editorial policy", adapter)
        self.assertIn("creator-handbook.html", json.loads((ROOT / "template/channel.json").read_text())["_howto"])

    def test_public_handbook_has_no_private_paths_or_celebrity_affiliation(self):
        text = self.raw.decode()
        for forbidden in ("/Users/", "/private/var/", "file://", "gho_", "github_pat_", "MrBeast"):
            self.assertNotIn(forbidden, text)
        self.assertNotRegex(text, re.compile(r"(?:javascript|data|blob):", re.I))


if __name__ == "__main__":
    unittest.main()
