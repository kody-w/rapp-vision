"""The rappvision-* owner convention, tested against the REAL function in index.html.

The player is one HTML file, so the discovery logic can drift from the documented
convention without any build step noticing. This test extracts conventionEntries()
verbatim from index.html and runs it under node against fixture repo listings —
the same bytes the browser executes, not a Python re-implementation that could
agree with the docs while the page disagrees.

Run: python3 tests/test_follow_convention.py   (skips cleanly if node is absent)
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


def extract_convention_entries():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    m = re.search(r"function conventionEntries\(owner, repos\) \{.*?\n\}", html, re.S)
    if not m:
        raise AssertionError("conventionEntries() not found in index.html")
    return m.group(0)


def run(owner, repos):
    src = extract_convention_entries()
    script = f"{src}\nprocess.stdout.write(JSON.stringify(conventionEntries({json.dumps(owner)}, {json.dumps(repos)})));"
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "node not available; browser-function test skipped")
class TestOwnerConvention(unittest.TestCase):
    def test_filters_to_convention_and_builds_both_urls(self):
        repos = [
            {"name": "rappvision-pokemon", "default_branch": "main"},
            {"name": "rappvision-Field-Notes", "default_branch": "master"},
            {"name": "rapp-vision"},                                   # the player, not a channel
            {"name": "rappvision-fork", "fork": True},                 # forks excluded
            {"name": "rappvision-old", "archived": True},              # archives excluded
            {"name": "rappvision-secret", "private": True},            # private never enters a public view
            {"name": "totally-unrelated"},
        ]
        entries = run("Kody-W", repos)
        self.assertEqual([e["id"] for e in entries],
                         ["gh:kody-w/rappvision-pokemon", "gh:kody-w/rappvision-field-notes"])
        self.assertEqual(entries[0]["url"],
                         "https://Kody-W.github.io/rappvision-pokemon/channel.json")
        self.assertEqual(entries[0]["alt"],
                         "https://raw.githubusercontent.com/Kody-W/rappvision-pokemon/main/channel.json")
        # the raw fallback honours a non-main default branch
        self.assertEqual(entries[1]["alt"],
                         "https://raw.githubusercontent.com/Kody-W/rappvision-Field-Notes/master/channel.json")
        self.assertEqual(entries[0]["repo"], "https://github.com/Kody-W/rappvision-pokemon")

    def test_hostile_or_empty_listings_yield_no_entries(self):
        self.assertEqual(run("kody-w", []), [])
        self.assertEqual(run("kody-w", [None, {}, {"name": None}]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
