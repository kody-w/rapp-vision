#!/usr/bin/env python3
"""Compile local production masters into a paired RAPP Vision channel."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "validate_publications.py"
PRODUCTION_SCHEMA = "rapp-vision-production/1.0"
CHANNEL_SCHEMA = "rapp-vision-channel/2.0"
PLAN_SCHEMA = "rapp-vision-production-plan/1.0"
DEFAULT_SOURCE = "channel.production.json"
STAGE_DIRECTORY = ".rapp-vision-production-stage"
ENCODED_SEPARATOR = re.compile(r"%(?:2[fF]|5[cC])")
URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)

MP4_TYPE = "video/mp4"
WEBM_TYPE = "video/webm"
EXPECTED_CODECS = {"mp4": "h264", "webm": "vp9"}
EXPECTED_COLOR = {
    "color_space": "bt709",
    "color_transfer": "bt709",
    "color_primaries": "bt709",
    "color_range": "tv",
}

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "_rapp_vision_validate_publications", VALIDATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load publication validator: {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()


class CompilerFailure(Exception):
    """A deterministic, user-facing compilation failure."""

    def __init__(
        self,
        errors: str | Sequence[str],
        *,
        preserve_stage: bool = False,
    ):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = tuple(str(error) for error in errors)
        self.preserve_stage = preserve_stage
        super().__init__("\n".join(self.errors))


@dataclass(frozen=True)
class PublicationBuild:
    publication_id: str
    master: Path
    mp4: Path
    webm: Path
    staged_mp4: Path
    staged_webm: Path


@dataclass(frozen=True)
class Compilation:
    source_path: Path
    source_root: Path
    output_root: Path
    channel: dict[str, Any]
    publications: tuple[PublicationBuild, ...]

    @property
    def channel_path(self) -> Path:
        return self.output_root / "channel.json"

    @property
    def stage_root(self) -> Path:
        return self.output_root / STAGE_DIRECTORY


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON number {value!r}")


def load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CompilerFailure(f"{path}: cannot read source: {exc}") from exc
    try:
        return json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise CompilerFailure(f"{path}: invalid JSON: {exc}") from exc


def deterministic_json(value: Any) -> str:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    except (TypeError, ValueError) as exc:
        raise CompilerFailure(f"cannot serialize deterministic JSON: {exc}") from exc


def _contains_control(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def _path_key(path: Path) -> str:
    """A conservative key that stays collision-safe on case-insensitive hosts."""
    return os.path.normcase(str(path.resolve(strict=False))).casefold()


def _is_link_or_junction(path: Path) -> bool:
    return path.is_symlink() or (
        hasattr(path, "is_junction") and path.is_junction()
    )


def _portable_id_error(publication_id: str) -> str | None:
    device_name = publication_id.split(".", 1)[0].upper()
    if device_name in WINDOWS_RESERVED_NAMES:
        return (
            f"publication id {publication_id!r} maps to reserved Windows "
            f"device name {device_name!r}"
        )
    return None


def resolve_source_path(source: str | os.PathLike[str]) -> Path:
    raw = os.fspath(source)
    if _contains_control(raw):
        raise CompilerFailure("source path contains control characters")
    candidate = Path(raw).expanduser()
    if candidate.is_dir():
        candidate = candidate / DEFAULT_SOURCE
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise CompilerFailure(f"{candidate}: cannot resolve source path: {exc}") from exc
    if not resolved.is_file():
        raise CompilerFailure(f"{resolved}: production source does not exist")
    return resolved


def resolve_output_root(
    output: str | os.PathLike[str] | None, source_root: Path
) -> Path:
    candidate = Path(output).expanduser() if output is not None else source_root
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise CompilerFailure(f"{candidate}: cannot resolve output path: {exc}") from exc
    if resolved.exists() and not resolved.is_dir():
        raise CompilerFailure(f"{resolved}: output path must be a directory")
    return resolved


def resolve_master_path(master: Any, source_root: Path, label: str) -> Path:
    if not isinstance(master, str) or not master.strip():
        raise CompilerFailure(f"{label}: must be a non-empty relative path")
    if _contains_control(master):
        raise CompilerFailure(f"{label}: control characters are not allowed")
    if ENCODED_SEPARATOR.search(master):
        raise CompilerFailure(f"{label}: encoded path separators are not allowed")

    windows_path = PureWindowsPath(master)
    posix_path = PurePosixPath(master)
    if windows_path.drive or windows_path.is_absolute() or posix_path.is_absolute():
        raise CompilerFailure(f"{label}: absolute paths are not allowed")
    if "\\" in master:
        raise CompilerFailure(f"{label}: backslashes are not allowed")
    if URL_SCHEME.match(master) or master.startswith("//"):
        raise CompilerFailure(f"{label}: URLs are not allowed")

    candidate = source_root.joinpath(*posix_path.parts)
    try:
        resolved = candidate.resolve()
        resolved.relative_to(source_root)
    except (OSError, ValueError) as exc:
        raise CompilerFailure(f"{label}: path escapes the source repository") from exc
    if not resolved.is_file():
        raise CompilerFailure(f"{label}: master file does not exist: {resolved}")
    return resolved


def transform_production_channel(document: Any) -> Any:
    """Replace compiler-only master declarations with canonical paired sources."""

    transformed = copy.deepcopy(document)
    if not isinstance(transformed, dict):
        return transformed
    transformed["schema"] = CHANNEL_SCHEMA
    videos = transformed.get("videos")
    if not isinstance(videos, list):
        return transformed
    for video in videos:
        if not isinstance(video, dict):
            continue
        publication_id = video.get("id", "")
        video.pop("production", None)
        video["sources"] = [
            {
                "src": f"media/{publication_id}.mp4",
                "type": MP4_TYPE,
            },
            {
                "src": f"media/{publication_id}.webm",
                "type": WEBM_TYPE,
            },
        ]
    return transformed


def prepare_compilation(
    source: str | os.PathLike[str],
    output: str | os.PathLike[str] | None = None,
) -> Compilation:
    source_path = resolve_source_path(source)
    source_root = source_path.parent.resolve()
    output_root = resolve_output_root(output, source_root)
    document = load_json(source_path)
    errors: list[str] = []
    masters: dict[int, Path] = {}

    if not isinstance(document, dict):
        errors.append("source: must be an object")
    else:
        if document.get("schema") != PRODUCTION_SCHEMA:
            errors.append(f"source.schema: must equal {PRODUCTION_SCHEMA!r}")
        videos = document.get("videos")
        if isinstance(videos, list):
            for index, video in enumerate(videos):
                path = f"source.videos[{index}]"
                if not isinstance(video, dict):
                    continue
                if not isinstance(video.get("id"), str):
                    errors.append(f"{path}.id: must be a string")
                if "sources" in video:
                    errors.append(
                        f"{path}.sources: production publications must not define sources"
                    )
                production = video.get("production")
                if not isinstance(production, dict):
                    errors.append(f"{path}.production: must be an object")
                    continue
                try:
                    masters[index] = resolve_master_path(
                        production.get("master"),
                        source_root,
                        f"{path}.production.master",
                    )
                except CompilerFailure as exc:
                    errors.extend(exc.errors)

    transformed = transform_production_channel(document)
    try:
        errors.extend(
            VALIDATOR.validate_channel(
                transformed,
                "https://rapp-vision.invalid/channel.json",
                {},
            )
        )
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:
        errors.append(
            "source: malformed structural value prevented publication "
            f"validation: {exc}"
        )

    publications: list[PublicationBuild] = []
    if isinstance(document, dict) and isinstance(document.get("videos"), list):
        for index, video in enumerate(document["videos"]):
            if (
                not isinstance(video, dict)
                or index not in masters
                or not isinstance(video.get("id"), str)
                or not VALIDATOR.valid_id(video.get("id"))
            ):
                continue
            publication_id = video["id"]
            media_root = output_root / "media"
            stage_media_root = output_root / STAGE_DIRECTORY / "media"
            publications.append(
                PublicationBuild(
                    publication_id=publication_id,
                    master=masters[index],
                    mp4=media_root / f"{publication_id}.mp4",
                    webm=media_root / f"{publication_id}.webm",
                    staged_mp4=stage_media_root / f"{publication_id}.mp4",
                    staged_webm=stage_media_root / f"{publication_id}.webm",
                )
            )

    if errors:
        raise CompilerFailure(errors)
    compilation = Compilation(
        source_path=source_path,
        source_root=source_root,
        output_root=output_root,
        channel=transformed,
        publications=tuple(publications),
    )
    _validate_compilation_paths(compilation)
    return compilation


def _validate_compilation_paths(compilation: Compilation) -> None:
    destination_by_key: dict[str, Path] = {}
    errors: list[str] = []
    for publication in compilation.publications:
        portable_error = _portable_id_error(publication.publication_id)
        if portable_error:
            errors.append(portable_error)
        for destination in (
            publication.mp4,
            publication.webm,
            publication.staged_mp4,
            publication.staged_webm,
        ):
            key = _path_key(destination)
            previous = destination_by_key.get(key)
            if previous is not None and str(previous) != str(destination):
                errors.append(
                    f"generated paths collide on a portable filesystem: "
                    f"{previous} and {destination}"
                )
            destination_by_key[key] = destination

    final_destinations = {
        _path_key(compilation.channel_path): compilation.channel_path,
        **{
            _path_key(path): path
            for publication in compilation.publications
            for path in (publication.mp4, publication.webm)
        },
    }
    source_key = _path_key(compilation.source_path)
    if source_key in final_destinations:
        errors.append(
            f"generated output {final_destinations[source_key]} aliases "
            f"production source {compilation.source_path}"
        )
    for publication in compilation.publications:
        master_key = _path_key(publication.master)
        if master_key in final_destinations:
            errors.append(
                f"generated output {final_destinations[master_key]} aliases "
                f"master input {publication.master}"
            )
    if errors:
        raise CompilerFailure(errors)


def _mp4_command(executable: str, publication: PublicationBuild) -> list[str]:
    return [
        executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(publication.master),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-vf",
        (
            "scale=in_range=auto:out_range=tv:out_color_matrix=bt709,"
            "format=yuv420p,"
            "setparams=range=limited:color_primaries=bt709:"
            "color_trc=bt709:colorspace=bt709"
        ),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-color_range",
        "tv",
        "-threads",
        "1",
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(publication.staged_mp4),
    ]


def _webm_command(executable: str, publication: PublicationBuild) -> list[str]:
    return [
        executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(publication.master),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-vf",
        (
            "scale=in_range=auto:out_range=tv:out_color_matrix=bt709,"
            "format=yuv420p,"
            "setparams=range=limited:color_primaries=bt709:"
            "color_trc=bt709:colorspace=bt709"
        ),
        "-c:v",
        "libvpx-vp9",
        "-crf",
        "30",
        "-b:v",
        "0",
        "-row-mt",
        "0",
        "-threads",
        "1",
        "-pix_fmt",
        "yuv420p",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-color_range",
        "tv",
        "-c:a",
        "libopus",
        "-b:a",
        "128k",
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        str(publication.staged_webm),
    ]


def _master_probe_command(executable: str, path: Path) -> list[str]:
    return [
        executable,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        (
            "stream=pix_fmt,color_space,color_transfer,"
            "color_primaries,color_range"
        ),
        "-of",
        "json",
        str(path),
    ]


def _probe_command(executable: str, path: Path) -> list[str]:
    return [
        executable,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        (
            "stream=codec_name,color_space,color_transfer,"
            "color_primaries,color_range"
        ),
        "-of",
        "json",
        str(path),
    ]


def make_plan(
    compilation: Compilation,
    *,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    artifacts: list[dict[str, str]] = []
    for publication in compilation.publications:
        artifacts.append(
            {
                "mp4": str(publication.mp4),
                "publication": publication.publication_id,
                "webm": str(publication.webm),
            }
        )
        operations.extend(
            [
                {
                    "command": _master_probe_command(
                        ffprobe,
                        publication.master,
                    ),
                    "kind": "master_probe",
                    "publication": publication.publication_id,
                },
                {
                    "command": _mp4_command(ffmpeg, publication),
                    "format": "mp4",
                    "kind": "encode",
                    "output": str(publication.staged_mp4),
                    "publication": publication.publication_id,
                },
                {
                    "command": _webm_command(ffmpeg, publication),
                    "format": "webm",
                    "kind": "encode",
                    "output": str(publication.staged_webm),
                    "publication": publication.publication_id,
                },
                {
                    "command": _probe_command(ffprobe, publication.staged_mp4),
                    "expected_codec": EXPECTED_CODECS["mp4"],
                    "expected_color": EXPECTED_COLOR,
                    "format": "mp4",
                    "kind": "probe",
                    "publication": publication.publication_id,
                },
                {
                    "command": _probe_command(ffprobe, publication.staged_webm),
                    "expected_codec": EXPECTED_CODECS["webm"],
                    "expected_color": EXPECTED_COLOR,
                    "format": "webm",
                    "kind": "probe",
                    "publication": publication.publication_id,
                },
            ]
        )
    return {
        "artifacts": artifacts,
        "channel": str(compilation.channel_path),
        "operations": operations,
        "schema": PLAN_SCHEMA,
        "source": str(compilation.source_path),
    }


def _run_process(command: list[str], runner: Runner) -> subprocess.CompletedProcess[str]:
    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise CompilerFailure(f"{command[0]} failed to start: {exc}") from exc
    if completed.returncode:
        detail = (completed.stderr or "").strip() or str(completed.returncode)
        raise CompilerFailure(f"{command[0]} failed: {detail}")
    return completed


def _execute_plan(plan: dict[str, Any], runner: Runner) -> None:
    for operation in plan["operations"]:
        command = operation["command"]
        completed = _run_process(command, runner)
        if operation["kind"] == "master_probe":
            try:
                payload = json.loads(completed.stdout or "")
                streams = payload.get("streams", [])
                stream = streams[0] if len(streams) == 1 else {}
            except (AttributeError, IndexError, json.JSONDecodeError):
                stream = {}
            pixel_format = str(stream.get("pix_fmt") or "")
            rgb = pixel_format.startswith(("rgb", "bgr", "gbr"))
            rgb_tags_compatible = (
                stream.get("color_space") in (None, "unknown", "gbr", "bt709")
                and stream.get("color_transfer") in (None, "unknown", "bt709")
                and stream.get("color_primaries") in (None, "unknown", "bt709")
                and stream.get("color_range") in (None, "unknown", "pc", "tv")
            )
            bt709_yuv = (
                pixel_format.startswith(("yuv", "yuva"))
                and stream.get("color_space") == "bt709"
                and stream.get("color_transfer") == "bt709"
                and stream.get("color_primaries") == "bt709"
                and stream.get("color_range") in ("pc", "tv")
            )
            if not ((rgb and rgb_tags_compatible) or bt709_yuv):
                raise CompilerFailure(
                    f"{operation['publication']} master: unsupported color "
                    f"description for {pixel_format or 'unknown pixel format'}; "
                    "use RGB or tagged BT.709 YUV"
                )
            continue
        if operation["kind"] == "encode":
            output = Path(operation["output"])
            if output.is_symlink() or not output.is_file():
                raise CompilerFailure(
                    f"{operation['publication']} {operation['format']} encoding "
                    f"did not create a regular file at {output}"
                )
            continue

        try:
            payload = json.loads(completed.stdout or "")
            streams = payload.get("streams", [])
            codec = streams[0].get("codec_name") if streams else None
        except (AttributeError, IndexError, json.JSONDecodeError):
            codec = None
        expected = operation["expected_codec"]
        if codec != expected:
            raise CompilerFailure(
                f"{operation['publication']} {operation['format']} output: "
                f"expected {expected!r} video codec, found {codec!r}"
            )
        expected_color = operation.get("expected_color") or {}
        for field, expected_value in expected_color.items():
            if streams[0].get(field) != expected_value:
                raise CompilerFailure(
                    f"{operation['publication']} {operation['format']} output: "
                    f"expected {field}={expected_value!r}, found "
                    f"{streams[0].get(field)!r}"
                )


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _validate_output_layout(compilation: Compilation) -> None:
    media_root = compilation.output_root / "media"
    if media_root.exists():
        if not media_root.is_dir() or _is_link_or_junction(media_root):
            raise CompilerFailure(f"{media_root}: media output must be a real directory")
        try:
            media_root.resolve().relative_to(compilation.output_root)
        except ValueError as exc:
            raise CompilerFailure(f"{media_root}: media output escapes output directory") from exc
    for publication in compilation.publications:
        for artifact in (publication.mp4, publication.webm):
            if _path_exists(artifact) and (
                _is_link_or_junction(artifact) or not artifact.is_file()
            ):
                raise CompilerFailure(f"{artifact}: existing output must be a regular file")


def _backup_file(source: Path, backup: Path) -> None:
    backup.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, backup)
    except OSError:
        shutil.copy2(source, backup)


def _publish(compilation: Compilation, staged_channel: Path) -> None:
    backups: dict[Path, Path] = {}
    attempted: list[Path] = []
    backup_root = compilation.stage_root / "backups"
    replacements = [
        (staged, final)
        for publication in compilation.publications
        for staged, final in (
            (publication.staged_mp4, publication.mp4),
            (publication.staged_webm, publication.webm),
        )
    ] + [(staged_channel, compilation.channel_path)]

    try:
        _validate_output_layout(compilation)
        for _staged, final in replacements:
            if final.exists():
                backup = backup_root / final.relative_to(
                    compilation.output_root
                )
                _backup_file(final, backup)
                backups[final] = backup
        for staged, final in replacements:
            # Record before replacement: an interrupt may be delivered after
            # the kernel rename succeeds but before os.replace returns.
            attempted.append(final)
            os.replace(staged, final)
    except BaseException as exc:
        rollback_errors: list[str] = []
        for final in reversed(attempted):
            backup = backups.get(final)
            try:
                if backup is None:
                    final.unlink(missing_ok=True)
                else:
                    os.replace(backup, final)
            except BaseException as rollback_exc:
                action = "remove" if backup is None else "restore"
                rollback_errors.append(
                    f"cannot {action} {final}: {rollback_exc}"
                )
        errors = [f"cannot publish compiled channel: {exc}"]
        errors.extend(f"rollback failed: {error}" for error in rollback_errors)
        if rollback_errors:
            errors.append(
                f"recovery files preserved under {compilation.stage_root}"
            )
        if rollback_errors or isinstance(exc, OSError):
            raise CompilerFailure(
                errors,
                preserve_stage=bool(rollback_errors),
            ) from exc
        raise


def build_compilation(
    compilation: Compilation,
    *,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    runner: Runner | None = None,
) -> Path:
    runner = runner or subprocess.run
    deterministic_channel = deterministic_json(compilation.channel).encode("utf-8")
    plan = make_plan(compilation, ffmpeg=ffmpeg, ffprobe=ffprobe)

    staged_channel = compilation.stage_root / "channel.json"
    created_stage = False
    preserve_stage = False
    try:
        compilation.output_root.mkdir(parents=True, exist_ok=True)
        _validate_output_layout(compilation)
        try:
            compilation.stage_root.mkdir()
            created_stage = True
        except FileExistsError as exc:
            raise CompilerFailure(
                f"{compilation.stage_root}: staging path already exists; "
                "remove it and retry"
            ) from exc
        (compilation.stage_root / "media").mkdir()
        staged_channel.write_bytes(deterministic_channel)
        _execute_plan(plan, runner)
        (compilation.output_root / "media").mkdir(parents=True, exist_ok=True)
        _validate_output_layout(compilation)
        _publish(compilation, staged_channel)
    except CompilerFailure as exc:
        preserve_stage = exc.preserve_stage
        raise
    except OSError as exc:
        raise CompilerFailure(f"build failed: {exc}") from exc
    finally:
        if (
            created_stage
            and not preserve_stage
            and compilation.stage_root.exists()
            and not _is_link_or_junction(compilation.stage_root)
        ):
            shutil.rmtree(compilation.stage_root, ignore_errors=True)
    return compilation.channel_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("check", "validate the production source and local masters without writing"),
        ("plan", "print the exact deterministic ffmpeg and ffprobe operation plan"),
        ("build", "encode paired media, probe it, and publish channel.json last"),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument(
            "source",
            nargs="?",
            default=DEFAULT_SOURCE,
            help="channel.production.json or its containing directory",
        )
        subparser.add_argument(
            "-o",
            "--output",
            "--output-dir",
            dest="output",
            help="output directory (defaults to the production source directory)",
        )
        subparser.add_argument(
            "--ffmpeg",
            default="ffmpeg",
            help="ffmpeg executable or path",
        )
        subparser.add_argument(
            "--ffprobe",
            default="ffprobe",
            help="ffprobe executable or path",
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        compilation = prepare_compilation(args.source, args.output)
        if args.command == "check":
            print(f"{compilation.source_path}: valid")
        elif args.command == "plan":
            sys.stdout.write(
                deterministic_json(
                    make_plan(
                        compilation,
                        ffmpeg=args.ffmpeg,
                        ffprobe=args.ffprobe,
                    )
                )
            )
        else:
            channel_path = build_compilation(
                compilation,
                ffmpeg=args.ffmpeg,
                ffprobe=args.ffprobe,
            )
            print(channel_path)
    except CompilerFailure as exc:
        for error in exc.errors:
            print(f"compile_publications: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
