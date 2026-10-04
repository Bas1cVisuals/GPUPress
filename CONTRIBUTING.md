# Contributing to GPUPress

## Development setup

Use Windows and a Python version supported by the listed PySide6 release. Create a virtual environment and install runtime dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

To build the Windows executable, also install the build requirements:

```powershell
python -m pip install -r requirements-dev.txt
```

GPUPress requires FFmpeg and FFprobe. The large Windows binaries are not included in the source repository. Obtain a compatible FFmpeg build separately and place `ffmpeg.exe` and `ffprobe.exe` in the local `bin\` directory; the build also requires `assets\icon.ico`. The exact build used during development was the Gyan.dev FFmpeg 9.0.1 full build, which reports GPL version 3 or later. FFmpeg/FFprobe are third-party components and are not covered by GPUPress’s MIT source-code license. Run the application from the project root with `python run.py`.

## Checks and build

Before submitting a change, run the available syntax checks:

```powershell
python -m compileall app
python -m py_compile run.py
```

The project does not currently include a formal automated test suite. Test relevant behavior manually with suitable media where practical, and do not use valuable originals as test outputs. To build the onedir executable, run `python build.py`; note that the script deletes the existing `build\`, `dist\`, and `GPUPress.spec` paths before building.

## Issues and pull requests

For a bug report, include the Windows version, GPUPress version or source revision, GPU and NVIDIA driver when relevant, input container/codec/resolution/FPS, selected output codec and settings, and relevant error/log output. Remove private paths or other sensitive information before posting logs.

Feature requests should describe the problem or use case, the desired behavior, and why it would help. An implementation idea is optional.

Pull requests should be focused, explain user-visible behavior changes, preserve existing compression and file-safety behavior unless the change specifically addresses it, and include the checks or manual tests performed. Do not include local settings, logs, input media, generated compressed files, build output, or unlicensed third-party files.
