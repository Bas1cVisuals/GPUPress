"""Deterministic, safety-conscious discovery and output helpers for batch jobs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.encoding_plan import UserEncodingOptions


SUPPORTED_MEDIA_EXTENSIONS = frozenset({
    ".mp4",
    ".mov",
    ".mkv",
    ".m4v",
    ".avi",
    ".webm",
    ".ts",
    ".mts",
    ".m2ts",
})


@dataclass(frozen=True)
class BatchJobSnapshot:
    """Immutable per-file input, output, and encoding-intent capture."""

    input_path: Path
    output_path: Path
    options: UserEncodingOptions
    preset_id: str


def discover_media_files(
    folder: str | Path,
    *,
    recursive: bool = False,
    excluded_directories: tuple[str | Path, ...] = (),
) -> tuple[Path, ...]:
    """Find supported video files in deterministic order without following links."""
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Input folder is not a directory: {root}")
    excluded = {
        Path(path).expanduser().resolve()
        for path in excluded_directories
    }

    def is_excluded(path: Path) -> bool:
        resolved = path.resolve()
        return any(
            resolved == directory or directory in resolved.parents
            for directory in excluded
        )

    files: list[Path] = []
    if recursive:
        for current, directories, filenames in os.walk(
            root,
            topdown=True,
            followlinks=False,
        ):
            current_path = Path(current)
            directories[:] = sorted(
                directory
                for directory in directories
                if not (current_path / directory).is_symlink()
                and not is_excluded(current_path / directory)
            )
            for filename in filenames:
                path = current_path / filename
                if (
                    path.is_symlink()
                    or path.suffix.lower() not in SUPPORTED_MEDIA_EXTENSIONS
                    or _is_generated_output(path)
                    or is_excluded(path)
                ):
                    continue
                files.append(path)
    else:
        for path in root.iterdir():
            if (
                path.is_file()
                and not path.is_symlink()
                and path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS
                and not _is_generated_output(path)
                and not is_excluded(path)
            ):
                files.append(path)

    unique: dict[str, Path] = {}
    for path in files:
        unique.setdefault(os.path.normcase(str(path.resolve())), path)
    return tuple(
        sorted(
            unique.values(),
            key=lambda path: (
                path.relative_to(root).as_posix().casefold(),
                path.relative_to(root).as_posix(),
            ),
        )
    )


def _is_generated_output(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.startswith(".gpupress-")
        or ".partial." in name
        or name.endswith("_compressed.mp4")
        or "_compressed_" in name
    )


def relative_output_directory(
    source_root: str | Path | None,
    input_file: str | Path,
) -> Path:
    """Return source-relative subdirectories when processing a folder batch."""
    if source_root is None:
        return Path()
    root = Path(source_root).expanduser().resolve()
    source = Path(input_file).expanduser().resolve()
    try:
        relative = source.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"Input {source} is outside the selected folder {root}."
        ) from error
    return relative.parent


def unique_output_path(
    output_directory: str | Path,
    input_file: str | Path,
    *,
    container: str,
    reserved_paths: set[str] | None = None,
) -> Path:
    """Build a non-overwriting output path, disambiguating equal source names."""
    output_directory = Path(output_directory)
    input_file = Path(input_file)
    extension = str(container).lower().lstrip(".")
    base = output_directory / f"{input_file.stem}_compressed.{extension}"
    reserved = reserved_paths if reserved_paths is not None else set()
    candidate = base
    index = 1
    while (
        candidate.exists()
        or os.path.normcase(str(candidate.resolve())) in reserved
    ):
        candidate = base.with_name(
            f"{base.stem}_{index}{base.suffix}"
        )
        index += 1
    reserved.add(os.path.normcase(str(candidate.resolve())))
    return candidate
