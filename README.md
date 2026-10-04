# GPUPress
### by BAS1C VISUALS

GPUPress is a Windows desktop application for compressing video files with FFmpeg. It provides a configurable video and audio pipeline, a sequential job queue, and NVIDIA GPU encoding paths when the local hardware and bundled FFmpeg support them.

## Features

- NVIDIA video processing using NVDEC, CUDA scaling, and NVENC when available and enabled.
- CPU decode and scaling with NVENC fallback, followed by CPU decode, scaling, and x264 fallback when CPU fallback is enabled.
- H.264 and H.265/HEVC NVENC encoding options. The CPU x264 fallback produces H.264.
- Queueing of supported video files, sequential processing, duplicate input suppression, and cancellation.
- H.264/HEVC codec selection, CQ quality, maximum resolution, frame rate, and NVENC preset controls.
- AAC or audio-copy selection; AAC bitrate, sample rate, and channel controls.
- Metadata-copy and MP4 faststart options.
- Collision-safe output names when overwrite is disabled and an explicit overwrite setting.
- Persistent settings, including output folder and processing options.
- A Windows onedir executable build that includes locally provided FFmpeg, FFprobe, and the application assets.

FFmpeg determines which containers, codecs, and media streams can be read or written. The file picker lists MP4, MOV, MKV, AVI, WebM, M4V, TS, MTS, and M2TS extensions, but successful processing depends on the actual file, FFmpeg build, encoder, and selected options.

## Processing paths

When NVIDIA GPU acceleration is enabled, GPUPress tries:

1. **GPU path:** NVDEC decode → CUDA scaling → NVENC encode.
2. **Fallback:** CPU decode → CPU scaling → NVENC encode.
3. **Final fallback:** CPU decode → CPU scaling → x264 encode.

If GPU acceleration is disabled, GPUPress uses the CPU x264 path. The fallback paths are controlled by the CPU fallback setting. Available FFmpeg encoders do not by themselves guarantee that a particular GPU, driver, input stream, or filter combination will work; GPUPress may move to the next enabled path after a failure.

The application exposes H.264 and H.265/HEVC options for NVENC. If processing reaches the x264 fallback, the video output is H.264.

## Queue and output safety

The same resolved input path is not added to the queue more than once. Different input files with the same base filename can be queued.

The output container is MP4. By default, GPUPress writes `<input-name>_compressed.mp4`. If that name already exists and overwrite is disabled, it selects the first available numbered name, such as `<input-name>_compressed_1.mp4`. It encodes to a temporary file and finalizes the output after a successful encode. When overwrite is enabled, the final output replaces the existing target only after the new encode succeeds.

Cancelling stops the current job and pauses the remaining queue. The user can remove the cancelled item or start the queue again.

## Settings

The Settings dialog saves general, video, audio, and processing preferences. With **Remember my settings** enabled, the preferences are restored on the next launch. With it disabled, other saved preferences are ignored and defaults are used on the next launch.

In source mode, settings are stored in `config/settings.json`. In packaged mode, settings are stored using the Windows user application configuration location; the default output folder is under the application’s writable user data location. Relative output-folder values are resolved against the application’s settings root.

The saved controls cover output folder, automatic output-folder opening, overwrite, GPU acceleration, CPU fallback, codec, CQ, maximum resolution, FPS, NVENC preset, audio codec/bitrate/sample rate/channels, metadata copying, and faststart. The maximum resolution is a limit; smaller sources are not upscaled, and scaling preserves aspect ratio. **Audio sample rate and channel settings apply when encoding AAC; audio copy retains the source stream when supported.**

## Run from source

Requirements:

- Windows
- A Python version supported by the listed PySide6 release
- PySide6, installed from `requirements.txt`
- FFmpeg and FFprobe executables at `bin\ffmpeg.exe` and `bin\ffprobe.exe`
- The application assets in `assets\`

GPUPress requires FFmpeg and FFprobe, but the large Windows binaries are not included in this source repository. Obtain a compatible FFmpeg build separately and place `ffmpeg.exe` and `ffprobe.exe` in the local `bin\` directory before running or building GPUPress. The exact FFmpeg build used during development was the Gyan.dev FFmpeg 9.0.1 full build, which reports GPL version 3 or later. This third-party license is separate from GPUPress’s MIT source-code license.

From the project root, create and activate a virtual environment, then install the runtime dependency and launch:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

The application resolves its development FFmpeg, assets, settings, and default output paths from the project files rather than relying on the shell’s current working directory.

## Build the Windows executable

Install the development/build requirements and run the builder from the project root:

```powershell
python -m pip install -r requirements-dev.txt
python build.py
```

`build.py` invokes PyInstaller in **onedir** mode. The executable is written to `dist\GPUPress\GPUPress.exe`; distribute the complete `dist\GPUPress` folder, not only the executable. The build expects `bin\ffmpeg.exe`, `bin\ffprobe.exe`, and `assets\icon.ico`, and bundles the assets and application directories.

**Build cleanup warning:** `build.py` removes the existing project-root `build\`, `dist\`, and `GPUPress.spec` before building. Back up anything in those paths that you need before running it.

## Third-party components and distribution

The application invokes FFmpeg and FFprobe as separate executables. The large Windows binaries are not included in the source repository; the build workflow expects locally obtained executables in `bin\`. The exact build used during development identifies itself as `ffmpeg/ffprobe 9.0.1-full_build-www.gyan.dev`; its `-L` output states GPL version 3 or later and its build configuration enables GPL components. It is not licensed under GPUPress’s MIT source-code license.

The repository does not contain a provenance manifest, the exact binary-source archive, or a complete set of corresponding third-party notices/source materials. Before distributing these executables, verify the precise build’s applicable license obligations and obtain/archive the required notices and corresponding source as applicable. Each local executable is over 200 MB, exceeding GitHub’s regular 100 MB per-file limit.

Do not assume the MIT license in this repository grants rights to third-party binaries or components. Verify the provenance and redistribution terms for bundled application assets if they are not owned by BAS1C VISUALS.

## Known limitations / Remaining verification

The following checks remain outstanding and should not be considered release-verified:

- Real long-duration footage and variable-frame-rate footage.
- Filesystem permission edge cases, including read-only or inaccessible output directories.
- Sustained memory and process soak testing across many jobs.
- Manual packaged-EXE Settings save and restart verification.
- Broad playback testing in external media players.

The actual containers, codecs, resolutions, and rates supported depend on the input media and installed/bundled FFmpeg build. GPU acceleration is hardware-, driver-, and pipeline-dependent. Compression is not lossless, output files are not guaranteed to be smaller, and broad playback compatibility is not guaranteed.

## License

The GPUPress source code in this repository is offered under the MIT License; see [LICENSE](LICENSE). Third-party components, binaries, and assets are subject to their own applicable terms as described above.