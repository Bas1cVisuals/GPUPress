from pathlib import Path
import shutil
import subprocess
import sys


# =========================================================
# PATHS
# =========================================================

ROOT = Path(__file__).resolve().parent

ENTRY = ROOT / "run.py"

BIN_DIR = ROOT / "bin"

ASSETS_DIR = ROOT / "assets"

INPUT_DIR = ROOT / "Input"

COMPRESSED_DIR = ROOT / "Compressed"

LOGS_DIR = ROOT / "logs"

CONFIG_DIR = ROOT / "config"

DIST_DIR = ROOT / "dist"

BUILD_DIR = ROOT / "build"

SPEC_FILE = ROOT / "GPUPress.spec"

EXE_NAME = "GPUPress"


# =========================================================
# CHECK
# =========================================================

def check_required_files():

    required = [

        ENTRY,

        BIN_DIR / "ffmpeg.exe",

        BIN_DIR / "ffprobe.exe",

        ASSETS_DIR / "icon.ico",

    ]

    missing = [
        path
        for path in required
        if not path.exists()
    ]

    if missing:

        print()
        print("=" * 60)
        print("MISSING REQUIRED FILES")
        print("=" * 60)

        for path in missing:
            print(
                f"[MISSING] {path}"
            )

        print()

        return False

    return True


# =========================================================
# CREATE DIRECTORIES
# =========================================================

def create_directories():

    for directory in [

        INPUT_DIR,

        COMPRESSED_DIR,

        LOGS_DIR,

        CONFIG_DIR,

    ]:

        directory.mkdir(
            parents=True,
            exist_ok=True
        )


# =========================================================
# CLEAN OLD BUILD
# =========================================================

def clean_old_build():

    print()
    print("[BUILD] Cleaning old build files...")

    for path in [

        BUILD_DIR,

        DIST_DIR,

        SPEC_FILE,

    ]:

        if path.is_dir():

            shutil.rmtree(
                path,
                ignore_errors=True
            )

        elif path.exists():

            try:
                path.unlink()
            except Exception:
                pass


# =========================================================
# PYINSTALLER
# =========================================================

def build_exe():

    print()
    print("=" * 60)
    print("BAS1C VISUALS")
    print("GPUPress EXE BUILD")
    print("=" * 60)
    print()

    command = [

        sys.executable,

        "-m",
        "PyInstaller",

        "--noconfirm",

        "--clean",

        "--windowed",

        "--name",
        EXE_NAME,

        "--icon",
        str(
            ASSETS_DIR / "icon.ico"
        ),

        # -------------------------------------------------
        # APPLICATION
        # -------------------------------------------------

        "--add-data",
        f"{ASSETS_DIR};assets",

        # -------------------------------------------------
        # FFMPEG
        # -------------------------------------------------

        "--add-binary",
        f"{BIN_DIR / 'ffmpeg.exe'};bin",

        "--add-binary",
        f"{BIN_DIR / 'ffprobe.exe'};bin",

        # -------------------------------------------------
        # APPLICATION DIRECTORIES
        # -------------------------------------------------

        "--add-data",
        f"{INPUT_DIR};Input",

        "--add-data",
        f"{COMPRESSED_DIR};Compressed",

        "--add-data",
        f"{LOGS_DIR};logs",

        "--add-data",
        f"{CONFIG_DIR};config",

        # -------------------------------------------------
        # ENTRY
        # -------------------------------------------------

        str(ENTRY),
    ]

    print(
        "[BUILD] Running PyInstaller..."
    )

    print()

    print(
        " ".join(
            f'"{x}"'
            if " " in str(x)
            else str(x)
            for x in command
        )
    )

    print()

    result = subprocess.run(
        command,
        cwd=str(ROOT)
    )

    if result.returncode != 0:

        print()
        print(
            "[ERROR] PyInstaller build failed."
        )

        return False

    return True


# =========================================================
# COPY USER-WRITABLE DIRECTORIES
# =========================================================

def prepare_portable_folders():

    exe_dir = (
        DIST_DIR / EXE_NAME
    )

    if not exe_dir.exists():

        return

    print()
    print(
        "[BUILD] Preparing application folders..."
    )

    for folder in [

        "Input",

        "Compressed",

        "logs",

        "config",

    ]:

        target = (
            exe_dir / folder
        )

        target.mkdir(
            parents=True,
            exist_ok=True
        )


# =========================================================
# FINAL REPORT
# =========================================================

def show_result():

    exe_path = (
        DIST_DIR
        / EXE_NAME
        / f"{EXE_NAME}.exe"
    )

    print()
    print("=" * 60)

    if exe_path.exists():

        print(
            "[SUCCESS] GPUPress built successfully."
        )

        print()
        print(
            "EXE:"
        )

        print(
            exe_path
        )

        print()
        print(
            "Folder:"
        )

        print(
            exe_path.parent
        )

        print()
        print(
            "You can distribute the entire"
        )

        print(
            f"'{EXE_NAME}' folder."
        )

    else:

        print(
            "[ERROR] EXE was not found."
        )

    print("=" * 60)
    print()


# =========================================================
# MAIN
# =========================================================

def main():

    print()
    print(
        "BAS1C VISUALS - GPUPress Builder"
    )
    print()

    if not check_required_files():

        sys.exit(1)

    create_directories()

    clean_old_build()

    success = build_exe()

    if not success:

        sys.exit(1)

    prepare_portable_folders()

    show_result()


if __name__ == "__main__":
    main()