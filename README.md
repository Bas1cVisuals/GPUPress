# GPUPress 0.1.0

### by BAS1C VISUALS

GPUPress is a Windows desktop video transcoding application for editors working
with demanding camera and smartphone footage. It uses FFprobe to analyze input,
resolves the selected settings into a per-job encoding plan, invokes FFmpeg,
validates the temporary output, and only then finalizes the output file.

This is the corrected initial public release, **0.1.0**.

## Capabilities

- Sequential multi-file queues and folder discovery, including optional
  recursive scanning. Supported extensions are centrally defined; unsupported
  files and generated partial outputs are excluded.
- Per-job settings snapshots, duplicate-input suppression, collision-safe
  output paths, per-file status, batch progress, and failure isolation.
- Adaptive 720p, 1080p, 1440p, 2160p/4K, source, and custom resolution
  targets. Aspect ratio is preserved by default, smaller sources are not
  enlarged by default, and custom upscaling can be explicitly enabled.
- Smart/source FPS behavior preserves the detected source cadence when known.
  VFR input is normalized to a deterministic CFR rate when the plan requires
  it; GPUPress does not unconditionally force 30 FPS. Detection samples a
  bounded initial packet window and is an estimate, not full-file analysis.
- Audio Auto prefers passthrough when the selected container supports the
  source codec. Otherwise it uses AAC fallback. Explicit Copy and AAC choices
  remain available; audio-less video is supported.
- Preset and custom encoding intent, including editing proxy, fast-scrub,
  social/web delivery, high-quality/smaller-file, compatibility, ProRes, and
  DNxHR choices where the installed FFmpeg exposes the necessary encoders.
- H.264 and HEVC software encoding, ProRes and DNxHR software encoding, and
  H.264/HEVC/AV1 NVENC when reported by FFmpeg and usable on the local system.
  NVIDIA decode and CUDA scaling are used only when their capabilities are
  available. A fallback retains the requested codec; GPUPress does not
  silently switch, for example, from HEVC to H.264.
- FFprobe source details include dimensions, orientation, aspect ratio, codec,
  pixel format/bit depth, frame rates, color/HDR signaling, audio information,
  and duration when present in the input metadata.

Actual support depends on the selected plan, input, FFmpeg build, GPU, and
driver. An encoder appearing in FFmpeg's capability list does not guarantee
that every encode will succeed.

## HDR and known limitations

GPUPress detects HDR transfer/color metadata when FFprobe exposes it. HDR
preservation is attempted only for supported 10-bit-capable output paths and
is checked for retained signaling/bit depth where the source exposes those
facts. This is metadata and encoding-path validation; it is **not** validation
of colorimetric or visual fidelity on mastered HDR footage.

Dolby Vision dynamic metadata is not preserved by re-encoding; Dolby Vision
re-encoding is rejected rather than presented as supported. HDR-to-SDR tone
mapping is not implemented and requests fail clearly. Synthetic HDR test
fixtures validate signaling and bit depth only. No personal or camera footage
was available for release QA. Whole-file VFR analysis, long-duration footage,
filesystem permission edge cases, sustained multi-job soak testing, and broad
external-player compatibility remain unverified.

## Output and cancellation safety

The default output folder is `Compressed` under the user's writable GPUPress
data location in packaged mode, and under the project root in source mode.
Batch folder outputs retain source-relative subdirectories to avoid same-name
collisions. Existing output files are not overwritten unless overwrite is
explicitly enabled. Each encode writes a unique temporary file; FFprobe
validation must succeed before it is renamed to the final output. Failed or
cancelled work does not emit success, and cancellation stops the active encode
and pauses the remaining queue while retaining completed outputs.

## Installation and running

For source use, install a supported Python version and the runtime dependency:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

FFmpeg binaries are intentionally excluded from this Git repository. The
locally tested build used Gyan.dev FFmpeg 9.0.1. Obtain the corresponding
`ffmpeg.exe` and `ffprobe.exe` files separately and verify the archive and
executable SHA-256 hashes against
[`third_party/ffmpeg/SOURCE.md`](third_party/ffmpeg/SOURCE.md); that record
documents the exact Gyan archive and executable hashes. The hash match
identifies the tested binaries, but does not establish a reproducible build or
resolve all third-party source, notice, or licensing questions. Place the
verified executables in the local `bin\` directory, then launch from the
project root:

```powershell
python run.py
```

GPUPress resolves development assets and FFmpeg relative to the application
files, not the shell's current directory. Packaged mode resolves FFmpeg and
assets from the PyInstaller bundle and stores settings in the user's Windows
application configuration location. It does not require the developer's
project path to exist.

## Development and tests

Install development dependencies and run the unit suite:

```powershell
python -m pip install -r requirements-dev.txt
pytest
```

The generated-media integration suite is opt-in and requires local FFmpeg and
FFprobe executables at `bin\ffmpeg.exe` and `bin\ffprobe.exe`:

```powershell
python -m unittest discover -s tests -p "real_media_qa.py" -v
```

It creates fixtures in a temporary directory and does not download media or
write generated media into the repository. Additional useful checks:

```powershell
python -m compileall app tests
git diff --check
```

## Windows build and installer

The onedir executable build requires local FFmpeg/FFprobe binaries and the
application icon:

```powershell
python -m pip install -r requirements-dev.txt
python build.py
```

The build result is `dist\GPUPress\GPUPress.exe`. **`build.py` removes the
project-root `build\`, `dist\`, and generated `GPUPress.spec` before building.
Back up anything in those locations that you need.**

The installer builder uses an existing onedir package and Inno Setup 6 or 7.
The GPUPress 0.1.0 application build succeeded. The Windows installer was
built locally and tested with Inno Setup 7.1.0:

```powershell
python build_installer.py
```

It stages into `build\installer-stage\` and writes
`dist\installer\GPUPress-Setup-v0.1.0.exe`. Its SHA-256 from local QA was
`C931809B284EDE19E3FF77E88C02EC40E80E8F57F3A892A8149792B6EA03BD43`.
A fresh installation into a temporary test directory, application startup,
basic UI loading, and uninstall were tested. The uninstall test found a
pre-existing `C:\Program Files\GPUPress` directory; its previous uninstall
registration was replaced during installation. Uninstall removed the test
registration and test directory, but did not remove that pre-existing
directory, so the result should not be interpreted as a completely clean
uninstall.

Automated unit and generated-media tests cover many application functions.
GUI batch processing, GUI cancellation, and end-to-end settings-save
persistence were not independently verified through the installed GUI. The
Start Menu shortcut is created by default; the Desktop shortcut is optional
and unchecked by default.

The source-code repository update and Windows installer have separate status:
the source release remains GPUPress 0.1.0, but the installer has **not** been
approved for public binary distribution. FFmpeg
redistribution, complete dependency source and notice availability, full
build provenance, and commercial licensing questions remain unresolved. Local
build/testing is not legal or commercial clearance.

The scripts locate an installed `ISCC.exe` by `INNO_SETUP_HOME`, `PATH`, or
standard Inno Setup 6/7 install directories. They do not pin or check the
compiler version. Verify the applicable Inno Setup compiler/toolchain terms
independently before commercial distribution.

## Licensing and third-party components

GPUPress source code is offered under the MIT License; see [LICENSE](LICENSE).
The recorded local FFmpeg/FFprobe executables identify as Gyan.dev
`9.0.1-full_build-www.gyan.dev`; both report GNU GPL version 3 or later. Their
configuration enables GPL, version3, and static build options. They are
separate third-party programs and are not covered by GPUPress's MIT license.

The executable hashes have been verified against Gyan's
`ffmpeg-9.0.1-full_build.7z` release archive. Gyan's release record points to
upstream FFmpeg commit `bf1b838f2ab88b4f8fd83443325c782ea0e0f7fa` (tag
`n9.0.1`). This confirms the archive identity of the recorded binaries, but
does not establish reproducibility or provide the complete Gyan build recipe,
dependency source revisions, patches, or a complete dependency notice/source
bundle. The verification record and remaining provenance gaps are documented
in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[third_party/ffmpeg](third_party/ffmpeg/). Review applicable third-party
source, notice, and distribution questions before public distribution; these
documents are factual records, not legal advice or a compliance determination.

The enabled codecs and related technologies, including H.264, HEVC/H.265,
AV1, and AAC, may warrant separate specialist legal/patent review. This
documentation is not a patent analysis and does not establish patent
clearance.

### GPUPress project assets

The existing project attribution identifies `assets/icon.ico`,
`assets/check.svg`, `assets/chevron-down.svg`, and
`assets/chevron-up.svg` as original GPUPress assets created for BAS1C VISUALS
and included under the project's MIT License.
