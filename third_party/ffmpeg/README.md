# Bundled FFmpeg and FFprobe provenance

## Build identity

The local executables recorded for this project identify themselves as:

- FFmpeg `9.0.1-full_build-www.gyan.dev`
- FFprobe `9.0.1-full_build-www.gyan.dev`
- GCC `16.1.0` (Rev2, built by the MSYS2 project)
- Static Windows build; `-L` reports GNU GPL version 3 or later.

The complete output of `-version`, `-buildconf`, and `-L` for both programs is preserved in [BUILD-OUTPUTS.txt](BUILD-OUTPUTS.txt). The configure options include `--enable-gpl`, `--enable-version3`, `--enable-static`, `--enable-libx264`, and `--enable-libx265`. No `--enable-nonfree` option appears in the captured configuration.

## Binary hashes

SHA-256 hashes recorded from the local source binaries:

| File | SHA-256 |
|---|---|
| `bin\ffmpeg.exe` | `57C56E369D5B4873B4D93FC1A1D833CB7CD8BC9325C14B05C34CE60B22842D8A` |
| `bin\ffprobe.exe` | `AFE05347CAAABE479B3C4EAE71992B6EC1E11C57266A1D665DEB0F9FE9847208` |

The same hashes were observed in `dist\GPUPress\_internal\bin\`. See [SOURCE.md](SOURCE.md) for the corresponding-source record and remaining gaps.

## Use in GPUPress

GPUPress invokes FFmpeg as a separate process to compress media and invokes FFprobe as a separate process to inspect media. The PyInstaller onedir build places these executables under `_internal\bin\`; the installer includes them as part of the staged application.

GPUPress itself is licensed separately under the MIT License; see the repository root [LICENSE](../../LICENSE). FFmpeg and FFprobe are separately licensed third-party software. This provenance record does not assert legal compliance or resolve the effect of distributing these programs with GPUPress.

## References

- Gyan.dev Windows FFmpeg builds: <https://www.gyan.dev/ffmpeg/builds/>
- FFmpeg source and release information: <https://ffmpeg.org/download.html>
- FFmpeg legal information: <https://ffmpeg.org/legal.html>

These general references do not establish that the exact source, dependencies, patches, or build scripts for the binaries identified by the hashes above are available. See [SOURCE.md](SOURCE.md).
