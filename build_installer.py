from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACKAGE_DIR = ROOT / "dist" / "GPUPress"
STAGE_DIR = ROOT / "build" / "installer-stage" / "GPUPress"
INSTALLER_SCRIPT = ROOT / "installer" / "GPUPress.iss"
INSTALLER_OUTPUT_DIR = ROOT / "dist" / "installer"
INSTALLER_OUTPUT = (
    INSTALLER_OUTPUT_DIR
    / "GPUPress-Setup-v0.1.0.exe"
)

EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
}
USER_DATA_DIRECTORY_NAMES = {
    "input",
    "compressed",
    "logs",
}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
    ".partial",
    ".log",
}


def find_inno_compiler() -> Path | None:
    configured_path = os.environ.get("INNO_SETUP_HOME")
    candidates = []

    if configured_path:
        configured = Path(configured_path)
        candidates.append(
            configured
            if configured.name.lower() == "iscc.exe"
            else configured / "ISCC.exe"
        )

    compiler_on_path = shutil.which("ISCC.exe")
    if compiler_on_path:
        candidates.append(Path(compiler_on_path))

    for program_files in (
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramFiles"),
    ):
        if program_files:
            for version in ("7", "6"):
                candidates.append(
                    Path(program_files)
                    / f"Inno Setup {version}"
                    / "ISCC.exe"
                )

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    return None


def validate_package() -> None:
    required_files = (
        ROOT / "assets" / "icon.ico",
        ROOT / "LICENSE",
        PACKAGE_DIR / "GPUPress.exe",
        PACKAGE_DIR / "_internal" / "assets" / "icon.ico",
        PACKAGE_DIR / "_internal" / "bin" / "ffmpeg.exe",
        PACKAGE_DIR / "_internal" / "bin" / "ffprobe.exe",
        PACKAGE_DIR / "_internal" / "PySide6" / "Qt6Widgets.dll",
    )
    missing = [path for path in required_files if not path.is_file()]

    if missing:
        details = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(
            "The existing PyInstaller onedir package is incomplete. "
            "Run `python build.py` first, then retry the installer build. "
            "Note: build.py cleans the existing build/ and dist/ folders.\n"
            f"Missing:\n{details}"
        )

    if not INSTALLER_SCRIPT.is_file():
        raise FileNotFoundError(
            f"Inno Setup script not found: {INSTALLER_SCRIPT}"
        )


def is_excluded(relative_path: Path, is_directory: bool) -> bool:
    parts = {part.lower() for part in relative_path.parts}

    if parts & EXCLUDED_DIRECTORY_NAMES:
        return True

    if parts & USER_DATA_DIRECTORY_NAMES:
        return not (
            is_directory
            and len(relative_path.parts) == 1
            and relative_path.name.lower() in USER_DATA_DIRECTORY_NAMES
        )

    if is_directory:
        return False

    if relative_path.name.lower() == "settings.json":
        return True

    return (
        relative_path.name.lower() == ".gitkeep"
        or relative_path.name.lower().endswith(".partial.mp4")
        or relative_path.suffix.lower() in EXCLUDED_SUFFIXES
    )


def stage_package() -> None:
    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)

    STAGE_DIR.mkdir(parents=True)

    for source in PACKAGE_DIR.rglob("*"):
        relative_path = source.relative_to(PACKAGE_DIR)
        is_directory = source.is_dir()

        if is_excluded(relative_path, is_directory):
            continue

        destination = STAGE_DIR / relative_path

        if is_directory:
            destination.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    for directory in ("Input", "Compressed", "logs"):
        (STAGE_DIR / directory).mkdir(parents=True, exist_ok=True)


def validate_staged_package() -> None:
    required_files = (
        STAGE_DIR / "GPUPress.exe",
        STAGE_DIR / "_internal" / "assets" / "icon.ico",
        STAGE_DIR / "_internal" / "bin" / "ffmpeg.exe",
        STAGE_DIR / "_internal" / "bin" / "ffprobe.exe",
        STAGE_DIR / "_internal" / "PySide6" / "Qt6Widgets.dll",
    )
    missing = [path for path in required_files if not path.is_file()]

    if missing:
        details = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(
            "Required files were not copied into the installer staging "
            f"directory:\n{details}"
        )

    forbidden_files = []
    for path in STAGE_DIR.rglob("*"):
        if path.is_dir():
            if path.name.lower() == "__pycache__":
                forbidden_files.append(path)
            continue

        relative = path.relative_to(STAGE_DIR)
        if is_excluded(relative, is_directory=False):
            forbidden_files.append(path)

    if forbidden_files:
        details = "\n".join(f"  - {path}" for path in forbidden_files)
        raise RuntimeError(
            "Local or generated files unexpectedly entered the installer "
            f"staging directory:\n{details}"
        )


def main() -> int:
    compiler = find_inno_compiler()
    if compiler is None:
        print(
            "Inno Setup compiler (ISCC.exe) was not found. "
            "Install Inno Setup 6 or 7, or set INNO_SETUP_HOME to its "
            "installation directory.",
            file=sys.stderr,
        )
        return 1

    try:
        validate_package()
        stage_package()
        validate_staged_package()
    except (FileNotFoundError, OSError, RuntimeError) as error:
        print(f"Installer preparation failed: {error}", file=sys.stderr)
        return 1

    INSTALLER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        str(compiler),
        str(INSTALLER_SCRIPT),
        f"--output-dir={INSTALLER_OUTPUT_DIR}",
        f"--output-filename={INSTALLER_OUTPUT.stem}",
    ]

    print(f"Using Inno Setup compiler: {compiler}")
    print(f"Staged packaged application: {STAGE_DIR}")
    print(f"Compiling installer: {INSTALLER_SCRIPT}")

    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
        )
    except OSError as error:
        print(f"Could not start Inno Setup compiler: {error}", file=sys.stderr)
        return 1

    if result.returncode != 0:
        print(
            f"Inno Setup compilation failed with exit code {result.returncode}.",
            file=sys.stderr,
        )
        return result.returncode or 1

    if not INSTALLER_OUTPUT.is_file():
        print(
            f"Inno Setup completed but installer was not created: "
            f"{INSTALLER_OUTPUT}",
            file=sys.stderr,
        )
        return 1

    size = INSTALLER_OUTPUT.stat().st_size
    print(f"Installer created: {INSTALLER_OUTPUT}")
    print(f"Installer size: {size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
