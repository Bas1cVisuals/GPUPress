from pathlib import Path

# ============================================================
# GPUPress
# Project Structure Generator
# ============================================================

ROOT = Path(__file__).resolve().parent

folders = [
    "app",
    "app/core",
    "app/workers",
    "app/ui",

    "bin",

    "Input",
    "Compressed",

    "logs",

    "assets",

    "config",
]

files = [
    "app/__init__.py",
    "app/main.py",

    "app/core/__init__.py",

    "app/core/ffmpeg.py",
    "app/core/hardware.py",
    "app/core/media.py",
    "app/core/presets.py",

    "app/workers/__init__.py",
    "app/workers/compression_worker.py",

    "app/ui/__init__.py",
    "app/ui/main_window.py",
    "app/ui/settings_widget.py",
    "app/ui/styles.py",

    "config/settings.json",

    "requirements.txt",
    "requirements-dev.txt",
    "run.py",
    "build.py",
    "README.md",
]


def create_structure():
    print()
    print("=" * 65)
    print("     GPUPress")
    print("     Project Structure Generator")
    print("=" * 65)
    print()

    # Create folders
    for folder in folders:
        path = ROOT / folder
        path.mkdir(parents=True, exist_ok=True)
        print(f"[DIR ] {path.relative_to(ROOT)}")

    print()

    # Create files only if they don't already exist
    for file in files:
        path = ROOT / file

        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            print(f"[FILE] {path.relative_to(ROOT)}")
        else:
            print(f"[SKIP] {path.relative_to(ROOT)} already exists")

    # Create default settings
    settings_file = ROOT / "config" / "settings.json"

    if settings_file.stat().st_size == 0:
        settings_file.write_text(
            """{
    "general": {
        "output_folder": "Compressed",
        "remember_settings": true,
        "auto_open_output": false,
        "overwrite_existing": false
    },
    "video": {
        "codec": "h264",
        "cq": 18,
        "max_resolution": "1920",
        "fps": "30",
        "nvenc_preset": "p6",
        "preserve_aspect_ratio": true
    },
    "audio": {
        "codec": "aac",
        "bitrate": "192k",
        "sample_rate": 48000,
        "channels": "2"
    },
    "processing": {
        "gpu_acceleration": true,
        "cpu_fallback": true,
        "faststart": true,
        "copy_metadata": true
    }
}
""",
            encoding="utf-8"
        )

    print()
    print("=" * 65)
    print("STRUCTURE CREATED SUCCESSFULLY")
    print("=" * 65)
    print()
    print(f"Location: {ROOT}")
    print()


if __name__ == "__main__":
    create_structure()