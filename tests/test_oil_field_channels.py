"""Offline registry contract tests for the ten-channel Oil Field season."""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = [
    ("signal-garden", "Signal Garden", "rappvision-signal-garden"),
    ("null-arcade", "Null Arcade", "rappvision-null-arcade"),
    ("tiny-bureau", "Tiny Bureau", "rappvision-tiny-bureau"),
    (
        "kitchen-table-physics",
        "Kitchen Table Physics",
        "rappvision-kitchen-table-physics",
    ),
    (
        "after-midnight-maps",
        "After Midnight Maps",
        "rappvision-after-midnight-maps",
    ),
    (
        "patch-notes-tomorrow",
        "Patch Notes from Tomorrow",
        "rappvision-patch-notes-tomorrow",
    ),
    ("repair-manual", "The Repair Manual", "rappvision-repair-manual"),
    (
        "one-minute-orchestra",
        "One Minute Orchestra",
        "rappvision-one-minute-orchestra",
    ),
    (
        "creature-office-hours",
        "Creature Office Hours",
        "rappvision-creature-office-hours",
    ),
    ("receipt-culture", "Receipt Culture", "rappvision-receipt-culture"),
]


class TestOilFieldChannels(unittest.TestCase):
    def test_default_registry_lists_each_channel_once(self):
        registry = json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))
        entries = {entry["id"]: entry for entry in registry["channels"]}

        for channel_id, name, repository in EXPECTED:
            with self.subTest(channel=channel_id):
                self.assertEqual(
                    entries[channel_id],
                    {
                        "id": channel_id,
                        "name": name,
                        "url": f"../{repository}/channel.json",
                        "repo": f"https://github.com/kody-w/{repository}",
                        "contract": "rapp-vision-channel/2.0",
                        "_why": entries[channel_id]["_why"],
                    },
                )
                self.assertTrue(entries[channel_id]["_why"])
                self.assertNotIn("legacy", entries[channel_id])

        listed_ids = [entry["id"] for entry in registry["channels"]]
        self.assertEqual(len(listed_ids), len(set(listed_ids)))

    def test_registry_revision_advanced_for_the_season(self):
        registry = json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(registry["revision"]["sequence"], 5)
        self.assertGreaterEqual(
            registry["revision"]["updated"],
            "2026-09-02T16:09:47Z",
        )

    def test_new_way_of_work_draft_channel_is_listed(self):
        registry = json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))
        entries = {entry["id"]: entry for entry in registry["channels"]}

        self.assertEqual(
            entries["new-way-of-work"],
            {
                "id": "new-way-of-work",
                "name": "The New Way of Work",
                "url": "../rappvision-new-way-of-work/channel.json",
                "repo": "https://github.com/kody-w/rappvision-new-way-of-work",
                "contract": "rapp-vision-channel/2.0",
                "_why": (
                    "Narration-neutral production drafts paired with live, "
                    "creator-driven storyboards for an open AI-worker build series."
                ),
            },
        )


if __name__ == "__main__":
    unittest.main()
