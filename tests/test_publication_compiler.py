"""Tests for the deterministic production publication compiler."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "production"
COMPILER_PATH = ROOT / "scripts" / "compile_publications.py"
SPEC = importlib.util.spec_from_file_location(
    "compile_publications", COMPILER_PATH
)
COMPILER = importlib.util.module_from_spec(SPEC)
sys.modules["compile_publications"] = COMPILER
SPEC.loader.exec_module(COMPILER)


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        command,
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


class CompilerTestCase(unittest.TestCase):
    def make_source(self, parent: Path) -> Path:
        source_root = parent / "source"
        shutil.copytree(FIXTURE, source_root)
        return source_root / "channel.production.json"

    def successful_runner(self, calls):
        def runner(command, **kwargs):
            self.assertEqual(
                kwargs,
                {
                    "check": False,
                    "capture_output": True,
                    "text": True,
                },
            )
            calls.append(command)
            if command[0] == "custom-ffmpeg":
                Path(command[-1]).write_bytes(b"encoded")
                return completed(command)
            codec = "h264" if command[-1].endswith(".mp4") else "vp9"
            return completed(
                command,
                stdout=json.dumps({"streams": [{"codec_name": codec}]}),
            )

        return runner


class TestProductionPaths(CompilerTestCase):
    def test_safe_relative_master_resolves_inside_source_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            compilation = COMPILER.prepare_compilation(source)
            self.assertEqual(len(compilation.publications), 1)
            self.assertEqual(
                compilation.publications[0].master,
                source.parent / "masters" / "paired-master.mov",
            )

    def test_unsafe_master_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            source = self.make_source(parent)
            outside = parent / "outside.mov"
            outside.write_bytes(b"outside")
            absolute = str((source.parent / "masters" / "paired-master.mov").resolve())
            unsafe = {
                "https://example.test/master.mov": "URLs are not allowed",
                absolute: "absolute paths are not allowed",
                "../outside.mov": "escapes the source repository",
                "masters\\paired-master.mov": "backslashes are not allowed",
                "masters/\npaired-master.mov": "control characters are not allowed",
                "masters/\u0085paired-master.mov": "control characters are not allowed",
                "masters%2Fpaired-master.mov": "encoded path separators are not allowed",
                "masters%5cpaired-master.mov": "encoded path separators are not allowed",
            }
            for value, expected in unsafe.items():
                with self.subTest(master=value):
                    with self.assertRaises(COMPILER.CompilerFailure) as raised:
                        COMPILER.resolve_master_path(
                            value,
                            source.parent,
                            "source.videos[0].production.master",
                        )
                    self.assertIn(expected, str(raised.exception))

    def test_source_requires_production_master_and_forbids_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            document = json.loads(source.read_text(encoding="utf-8"))
            document["videos"][0]["sources"] = []
            del document["videos"][0]["production"]
            source.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.prepare_compilation(source)
            message = str(raised.exception)
            self.assertIn("must not define sources", message)
            self.assertIn(".production: must be an object", message)


class TestProductionTransform(CompilerTestCase):
    def test_production_schema_requires_master_and_inline_live_without_sources(self):
        schema = json.loads(
            (ROOT / "channel.production.schema.json").read_text(encoding="utf-8")
        )
        publication = schema["$defs"]["publication"]
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            "rapp-vision-production/1.0",
        )
        self.assertIn("production", publication["required"])
        self.assertIn("live", publication["required"])
        self.assertEqual(publication["not"], {"required": ["sources"]})
        self.assertEqual(
            publication["properties"]["production"]["required"],
            ["master"],
        )

    def test_transform_preserves_metadata_and_creates_ordered_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            original = json.loads(source.read_text(encoding="utf-8"))
            compilation = COMPILER.prepare_compilation(source)
            channel = compilation.channel

            self.assertEqual(channel["schema"], "rapp-vision-channel/2.0")
            self.assertEqual(
                channel["customChannelMetadata"],
                original["customChannelMetadata"],
            )
            publication = channel["videos"][0]
            self.assertEqual(
                publication["customPublicationMetadata"],
                original["videos"][0]["customPublicationMetadata"],
            )
            self.assertNotIn("production", publication)
            self.assertEqual(
                publication["sources"],
                [
                    {"src": "media/paired.mp4", "type": "video/mp4"},
                    {"src": "media/paired.webm", "type": "video/webm"},
                ],
            )

    def test_existing_validator_errors_are_authoritative(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            document = json.loads(source.read_text(encoding="utf-8"))
            document["videos"][0]["live"]["scenes"][1]["t"] = 3
            source.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.prepare_compilation(source)
            self.assertIn(
                "channel.videos[0].live.scenes[1].t: "
                "scenes must be contiguous; expected 2",
                str(raised.exception),
            )

    def test_output_and_plan_are_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            output = Path(temporary) / "dist"
            first = COMPILER.prepare_compilation(source, output)
            second = COMPILER.prepare_compilation(source, output)

            channel_one = COMPILER.deterministic_json(first.channel)
            channel_two = COMPILER.deterministic_json(second.channel)
            plan_one = COMPILER.deterministic_json(
                COMPILER.make_plan(
                    first,
                    ffmpeg="custom-ffmpeg",
                    ffprobe="custom-ffprobe",
                )
            )
            plan_two = COMPILER.deterministic_json(
                COMPILER.make_plan(
                    second,
                    ffmpeg="custom-ffmpeg",
                    ffprobe="custom-ffprobe",
                )
            )

            self.assertEqual(channel_one, channel_two)
            self.assertEqual(plan_one, plan_two)
            self.assertFalse(output.exists())
            self.assertTrue(channel_one.endswith("\n"))
            self.assertNotIn("\r", channel_one)
            self.assertEqual(
                json.loads(plan_one)["operations"],
                COMPILER.make_plan(
                    first,
                    ffmpeg="custom-ffmpeg",
                    ffprobe="custom-ffprobe",
                )["operations"],
            )
            self.assertNotIn("timestamp", plan_one.lower())
            self.assertNotIn("version", plan_one.lower())
            self.assertNotIn("random", plan_one.lower())


class TestProductionBuild(CompilerTestCase):
    def test_build_encodes_and_probes_both_formats_then_writes_channel(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            output = Path(temporary) / "dist"
            compilation = COMPILER.prepare_compilation(source, output)
            calls = []
            expected_commands = [
                operation["command"]
                for operation in COMPILER.make_plan(
                    compilation,
                    ffmpeg="custom-ffmpeg",
                    ffprobe="custom-ffprobe",
                )["operations"]
            ]
            replace_destinations = []
            real_replace = COMPILER.os.replace

            def tracked_replace(source_path, destination_path):
                replace_destinations.append(Path(destination_path))
                return real_replace(source_path, destination_path)

            with mock.patch.object(
                COMPILER.os,
                "replace",
                side_effect=tracked_replace,
            ):
                channel_path = COMPILER.build_compilation(
                    compilation,
                    ffmpeg="custom-ffmpeg",
                    ffprobe="custom-ffprobe",
                    runner=self.successful_runner(calls),
                )

            self.assertEqual(calls, expected_commands)
            self.assertEqual([call[0] for call in calls], [
                "custom-ffmpeg",
                "custom-ffmpeg",
                "custom-ffprobe",
                "custom-ffprobe",
            ])
            self.assertIn("libx264", calls[0])
            self.assertIn("libvpx-vp9", calls[1])
            self.assertTrue((output / "media" / "paired.mp4").is_file())
            self.assertTrue((output / "media" / "paired.webm").is_file())
            self.assertEqual(channel_path, output / "channel.json")
            channel_bytes = channel_path.read_bytes()
            self.assertTrue(channel_bytes.endswith(b"\n"))
            self.assertNotIn(b"\r\n", channel_bytes)
            channel = json.loads(channel_bytes)
            self.assertEqual(
                [source["src"] for source in channel["videos"][0]["sources"]],
                ["media/paired.mp4", "media/paired.webm"],
            )
            self.assertEqual(replace_destinations[-1], output / "channel.json")
            self.assertFalse((output / COMPILER.STAGE_DIRECTORY).exists())

    def test_codec_mismatch_removes_staging_and_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            output = Path(temporary) / "dist"
            compilation = COMPILER.prepare_compilation(source, output)

            def runner(command, **_kwargs):
                if command[0] == "custom-ffmpeg":
                    Path(command[-1]).write_bytes(b"encoded")
                    return completed(command)
                codec = "h264" if command[-1].endswith(".mp4") else "av1"
                return completed(
                    command,
                    stdout=json.dumps({"streams": [{"codec_name": codec}]}),
                )

            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.build_compilation(
                    compilation,
                    ffmpeg="custom-ffmpeg",
                    ffprobe="custom-ffprobe",
                    runner=runner,
                )
            self.assertIn("expected 'vp9' video codec, found 'av1'", str(raised.exception))
            self.assertFalse((output / "media" / "paired.mp4").exists())
            self.assertFalse((output / "media" / "paired.webm").exists())
            self.assertFalse((output / "channel.json").exists())
            self.assertFalse((output / COMPILER.STAGE_DIRECTORY).exists())

    def test_failed_second_encoding_never_leaves_one_format_or_channel(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            output = Path(temporary) / "dist"
            compilation = COMPILER.prepare_compilation(source, output)
            encode_count = 0

            def runner(command, **_kwargs):
                nonlocal encode_count
                if command[0] == "custom-ffmpeg":
                    encode_count += 1
                    Path(command[-1]).write_bytes(b"partial")
                    if encode_count == 2:
                        return completed(command, returncode=1, stderr="encode failed")
                    return completed(command)
                self.fail("ffprobe must not run after a failed encoding")

            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.build_compilation(
                    compilation,
                    ffmpeg="custom-ffmpeg",
                    ffprobe="custom-ffprobe",
                    runner=runner,
                )
            self.assertIn("encode failed", str(raised.exception))
            self.assertFalse((output / "media" / "paired.mp4").exists())
            self.assertFalse((output / "media" / "paired.webm").exists())
            self.assertFalse((output / "channel.json").exists())
            self.assertFalse((output / COMPILER.STAGE_DIRECTORY).exists())

    def test_failed_rebuild_preserves_previous_complete_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            output = Path(temporary) / "dist"
            output_media = output / "media"
            output_media.mkdir(parents=True)
            old_mp4 = output_media / "paired.mp4"
            old_webm = output_media / "paired.webm"
            old_channel = output / "channel.json"
            old_mp4.write_bytes(b"old mp4")
            old_webm.write_bytes(b"old webm")
            old_channel.write_bytes(b'{"old":true}\n')
            compilation = COMPILER.prepare_compilation(source, output)

            def runner(command, **_kwargs):
                if command[0] == "custom-ffmpeg":
                    Path(command[-1]).write_bytes(b"new")
                    if command[-1].endswith(".webm"):
                        return completed(command, 1, stderr="failed")
                    return completed(command)
                self.fail("probe should not run")

            with self.assertRaises(COMPILER.CompilerFailure):
                COMPILER.build_compilation(
                    compilation,
                    ffmpeg="custom-ffmpeg",
                    ffprobe="custom-ffprobe",
                    runner=runner,
                )
            self.assertEqual(old_mp4.read_bytes(), b"old mp4")
            self.assertEqual(old_webm.read_bytes(), b"old webm")
            self.assertEqual(old_channel.read_bytes(), b'{"old":true}\n')


class TestCompilerCli(CompilerTestCase):
    def test_cli_check_plan_and_invalid_exit_codes(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = COMPILER.main(["check", str(source)])
            self.assertEqual(result, 0)
            self.assertIn(": valid", stdout.getvalue())
            self.assertEqual(stderr.getvalue(), "")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = COMPILER.main([
                    "plan",
                    str(source),
                    "--ffmpeg",
                    "other-ffmpeg",
                    "--ffprobe",
                    "other-ffprobe",
                ])
            self.assertEqual(result, 0)
            plan = json.loads(stdout.getvalue())
            self.assertEqual(plan["operations"][0]["command"][0], "other-ffmpeg")
            self.assertEqual(plan["operations"][2]["command"][0], "other-ffprobe")

            invalid = copy.deepcopy(json.loads(source.read_text(encoding="utf-8")))
            invalid["videos"][0]["live"]["kind"] = "wrong"
            source.write_text(json.dumps(invalid), encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = COMPILER.main(["check", str(source)])
            self.assertEqual(result, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("must equal 'rapp-vision-live/1.0'", stderr.getvalue())

    def test_executable_script_returns_cli_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            valid = subprocess.run(
                [sys.executable, str(COMPILER_PATH), "check", str(source)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(valid.returncode, 0, valid.stderr)

            document = json.loads(source.read_text(encoding="utf-8"))
            document["videos"][0]["live"]["scenes"][1]["t"] = 4
            source.write_text(json.dumps(document), encoding="utf-8")
            invalid = subprocess.run(
                [sys.executable, str(COMPILER_PATH), "check", str(source)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(invalid.returncode, 1)
            self.assertIn("scenes must be contiguous", invalid.stderr)

    def test_build_cli_uses_process_overrides_and_returns_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            output = Path(temporary) / "dist"
            calls = []
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(
                COMPILER.subprocess,
                "run",
                side_effect=self.successful_runner(calls),
            ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = COMPILER.main([
                    "build",
                    str(source),
                    "--output",
                    str(output),
                    "--ffmpeg",
                    "custom-ffmpeg",
                    "--ffprobe",
                    "custom-ffprobe",
                ])
            self.assertEqual(result, 0, stderr.getvalue())
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(Path(stdout.getvalue().strip()), output / "channel.json")
            self.assertEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
