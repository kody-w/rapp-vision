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
            if "pix_fmt" in command[command.index("-show_entries") + 1]:
                return completed(
                    command,
                    stdout=json.dumps({"streams": [{"pix_fmt": "bgr0"}]}),
                )
            codec = "h264" if command[-1].endswith(".mp4") else "vp9"
            return completed(
                command,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "codec_name": codec,
                                **COMPILER.EXPECTED_COLOR,
                            }
                        ]
                    }
                ),
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

    def test_output_directory_may_contain_spaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            compilation = COMPILER.prepare_compilation(
                source,
                Path(temporary) / "output with spaces",
            )
            self.assertEqual(compilation.output_root.name, "output with spaces")

    def test_generated_outputs_cannot_alias_sources_or_masters(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            source_as_channel = source.with_name("channel.json")
            source.rename(source_as_channel)
            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.prepare_compilation(source_as_channel)
            self.assertIn("aliases production source", str(raised.exception))

        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            document = json.loads(source.read_text(encoding="utf-8"))
            media = source.parent / "media"
            media.mkdir()
            master = media / "paired.mp4"
            master.write_bytes(b"master")
            document["videos"][0]["production"]["master"] = "media/paired.mp4"
            source.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.prepare_compilation(source)
            self.assertIn("aliases master input", str(raised.exception))

    def test_portable_output_names_reject_case_collisions_and_devices(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            document = json.loads(source.read_text(encoding="utf-8"))
            duplicate = copy.deepcopy(document["videos"][0])
            duplicate["id"] = "PAIRED"
            document["videos"].append(duplicate)
            source.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.prepare_compilation(source)
            self.assertIn("paths collide", str(raised.exception))

        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            document = json.loads(source.read_text(encoding="utf-8"))
            document["videos"][0]["id"] = "CON"
            source.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.prepare_compilation(source)
            self.assertIn("reserved Windows device name", str(raised.exception))


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

    def test_malformed_schema_types_are_user_facing_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            document = json.loads(source.read_text(encoding="utf-8"))
            document["videos"][0]["id"] = []
            source.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.prepare_compilation(source)
            self.assertIn(
                "source.videos[0].id: must be a string",
                str(raised.exception),
            )

    def test_oversized_numbers_are_user_facing_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            document = json.loads(source.read_text(encoding="utf-8"))
            document["videos"][0]["duration"] = 10**400
            source.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.prepare_compilation(source)
            self.assertIn("malformed structural value", str(raised.exception))

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
                "custom-ffprobe",
                "custom-ffmpeg",
                "custom-ffmpeg",
                "custom-ffprobe",
                "custom-ffprobe",
            ])
            self.assertIn("libx264", calls[1])
            self.assertIn("libvpx-vp9", calls[2])
            for command in calls[1:3]:
                self.assertIn("+bitexact", command)
                self.assertIn("-threads", command)
                self.assertEqual(command[command.index("-threads") + 1], "1")
                self.assertIn("0:a:0?", command)
                self.assertIn(
                    (
                        "scale=in_range=auto:out_range=tv:"
                        "out_color_matrix=bt709,format=yuv420p,"
                        "setparams=range=limited:color_primaries=bt709:"
                        "color_trc=bt709:colorspace=bt709"
                    ),
                    command,
                )
                self.assertEqual(
                    command[command.index("-color_primaries") + 1],
                    "bt709",
                )
                self.assertEqual(
                    command[command.index("-colorspace") + 1],
                    "bt709",
                )
            self.assertEqual(calls[2][calls[2].index("-row-mt") + 1], "0")
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
                if "pix_fmt" in command[command.index("-show_entries") + 1]:
                    return completed(
                        command,
                        stdout=json.dumps({"streams": [{"pix_fmt": "bgr0"}]}),
                    )
                codec = "h264" if command[-1].endswith(".mp4") else "av1"
                return completed(
                    command,
                    stdout=json.dumps(
                        {
                            "streams": [
                                {
                                    "codec_name": codec,
                                    **COMPILER.EXPECTED_COLOR,
                                }
                            ]
                        }
                    ),
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

    def test_incompatible_yuv_master_is_rejected_before_encoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            output = Path(temporary) / "dist"
            compilation = COMPILER.prepare_compilation(source, output)
            calls = []

            def runner(command, **_kwargs):
                calls.append(command)
                return completed(
                    command,
                    stdout=json.dumps(
                        {
                            "streams": [
                                {
                                    "pix_fmt": "yuv420p",
                                    "color_space": "smpte170m",
                                    "color_transfer": "bt709",
                                    "color_primaries": "bt470bg",
                                    "color_range": "tv",
                                }
                            ]
                        }
                    ),
                )

            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.build_compilation(
                    compilation,
                    ffmpeg="custom-ffmpeg",
                    ffprobe="custom-ffprobe",
                    runner=runner,
                )
            self.assertIn("unsupported color description", str(raised.exception))
            self.assertEqual(len(calls), 1)
            self.assertFalse((output / "channel.json").exists())

    def test_conflicting_rgb_color_tags_are_rejected_before_encoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            output = Path(temporary) / "dist"
            compilation = COMPILER.prepare_compilation(source, output)

            def runner(command, **_kwargs):
                return completed(
                    command,
                    stdout=json.dumps(
                        {
                            "streams": [
                                {
                                    "pix_fmt": "gbrp",
                                    "color_space": "gbr",
                                    "color_transfer": "smpte2084",
                                    "color_primaries": "bt2020",
                                    "color_range": "pc",
                                }
                            ]
                        }
                    ),
                )

            with self.assertRaises(COMPILER.CompilerFailure) as raised:
                COMPILER.build_compilation(
                    compilation,
                    ffprobe="custom-ffprobe",
                    runner=runner,
                )
            self.assertIn("unsupported color description", str(raised.exception))

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
                if "pix_fmt" in command[command.index("-show_entries") + 1]:
                    return completed(
                        command,
                        stdout=json.dumps({"streams": [{"pix_fmt": "bgr0"}]}),
                    )
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
                if "pix_fmt" in command[command.index("-show_entries") + 1]:
                    return completed(
                        command,
                        stdout=json.dumps({"streams": [{"pix_fmt": "bgr0"}]}),
                    )
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

    def test_failed_rollback_preserves_recovery_stage(self):
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
            calls = []
            real_replace = COMPILER.os.replace

            def failing_replace(source_path, destination_path):
                source_path = Path(source_path)
                destination_path = Path(destination_path)
                if source_path == compilation.stage_root / "channel.json":
                    raise OSError("channel busy")
                if (
                    compilation.stage_root / "backups" in source_path.parents
                    and destination_path == old_mp4
                ):
                    raise OSError("restore denied")
                return real_replace(source_path, destination_path)

            with mock.patch.object(
                COMPILER.os,
                "replace",
                side_effect=failing_replace,
            ):
                with self.assertRaises(COMPILER.CompilerFailure) as raised:
                    COMPILER.build_compilation(
                        compilation,
                        ffmpeg="custom-ffmpeg",
                        ffprobe="custom-ffprobe",
                        runner=self.successful_runner(calls),
                    )

            self.assertTrue(raised.exception.preserve_stage)
            self.assertIn("recovery files preserved", str(raised.exception))
            self.assertTrue(compilation.stage_root.is_dir())
            self.assertTrue(
                (
                    compilation.stage_root
                    / "backups"
                    / "media"
                    / "paired.mp4"
                ).is_file()
            )

    def test_keyboard_interrupt_rolls_back_complete_previous_delivery(self):
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
            calls = []
            real_replace = COMPILER.os.replace

            def interrupted_replace(source_path, destination_path):
                if Path(source_path) == compilation.stage_root / "channel.json":
                    raise KeyboardInterrupt()
                return real_replace(source_path, destination_path)

            with mock.patch.object(
                COMPILER.os,
                "replace",
                side_effect=interrupted_replace,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    COMPILER.build_compilation(
                        compilation,
                        ffmpeg="custom-ffmpeg",
                        ffprobe="custom-ffprobe",
                        runner=self.successful_runner(calls),
                    )

            self.assertEqual(old_mp4.read_bytes(), b"old mp4")
            self.assertEqual(old_webm.read_bytes(), b"old webm")
            self.assertEqual(old_channel.read_bytes(), b'{"old":true}\n')
            self.assertFalse(compilation.stage_root.exists())

    def test_post_replace_interrupt_rolls_back_uncertain_destination(self):
        for target_kind in ("first-media", "channel"):
            with self.subTest(target=target_kind), tempfile.TemporaryDirectory() as temporary:
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
                calls = []
                real_replace = COMPILER.os.replace
                target_source = (
                    compilation.publications[0].staged_mp4
                    if target_kind == "first-media"
                    else compilation.stage_root / "channel.json"
                )

                def replace_then_interrupt(source_path, destination_path):
                    result = real_replace(source_path, destination_path)
                    if Path(source_path) == target_source:
                        raise KeyboardInterrupt()
                    return result

                with mock.patch.object(
                    COMPILER.os,
                    "replace",
                    side_effect=replace_then_interrupt,
                ):
                    with self.assertRaises(KeyboardInterrupt):
                        COMPILER.build_compilation(
                            compilation,
                            ffmpeg="custom-ffmpeg",
                            ffprobe="custom-ffprobe",
                            runner=self.successful_runner(calls),
                        )

                self.assertEqual(old_mp4.read_bytes(), b"old mp4")
                self.assertEqual(old_webm.read_bytes(), b"old webm")
                self.assertEqual(old_channel.read_bytes(), b'{"old":true}\n')
                self.assertFalse(compilation.stage_root.exists())

    def test_preexisting_stage_is_never_deleted_by_losing_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            output = Path(temporary) / "dist"
            output.mkdir()
            compilation = COMPILER.prepare_compilation(source, output)
            compilation.stage_root.mkdir()
            marker = compilation.stage_root / "owned-by-other-build"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaises(COMPILER.CompilerFailure):
                COMPILER.build_compilation(compilation)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_output_creation_errors_are_user_facing(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary))
            output = Path(temporary) / "denied"
            compilation = COMPILER.prepare_compilation(source, output)
            real_mkdir = COMPILER.Path.mkdir

            def denied(path, *args, **kwargs):
                if path == output:
                    raise PermissionError("access denied")
                return real_mkdir(path, *args, **kwargs)

            with mock.patch.object(COMPILER.Path, "mkdir", new=denied):
                with self.assertRaises(COMPILER.CompilerFailure) as raised:
                    COMPILER.build_compilation(compilation)
            self.assertIn("build failed: access denied", str(raised.exception))


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
            self.assertEqual(plan["operations"][0]["command"][0], "other-ffprobe")
            self.assertEqual(plan["operations"][1]["command"][0], "other-ffmpeg")
            self.assertEqual(plan["operations"][3]["command"][0], "other-ffprobe")

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
            self.assertEqual(len(calls), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
