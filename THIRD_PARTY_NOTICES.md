# Third-Party Notices and Inventory

## GPUPress

GPUPress by BAS1C VISUALS is licensed under the MIT License. See [LICENSE](LICENSE). This license applies to GPUPress project code and does not relicense third-party software bundled with a Windows distribution.

## FFmpeg and FFprobe

The recorded binaries identify themselves as Gyan.dev FFmpeg/FFprobe `9.0.1-full_build-www.gyan.dev`. Both tools' `-L` output states GNU GPL version 3 or later. The captured build configuration enables `--enable-gpl`, `--enable-version3`, and `--enable-static`; no `--enable-nonfree` flag is present. These are tool-reported identity/configuration facts, not conclusions about obligations for a particular distribution.

| Executable | SHA-256 |
|---|---|
| `ffmpeg.exe` | `57C56E369D5B4873B4D93FC1A1D833CB7CD8BC9325C14B05C34CE60B22842D8A` |
| `ffprobe.exe` | `AFE05347CAAABE479B3C4EAE71992B6EC1E11C57266A1D665DEB0F9FE9847208` |

The local executable hashes exactly match the executables extracted from Gyan's release archive:

- Gyan release: [9.0.1](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.1)
- Archive: `ffmpeg-9.0.1-full_build.7z`
- Archive SHA-256: `4b9c814cb07a1f90d05b768ef4eb2abbf89af94bbb924df5b7dbd6e64e1e2b96`
- Gyan release record's upstream FFmpeg source pointer: [commit `bf1b838f2ab88b4f8fd83443325c782ea0e0f7fa`](https://github.com/FFmpeg/FFmpeg/commit/bf1b838f2ab88b4f8fd83443325c782ea0e0f7fa), target of tag [`n9.0.1`](https://github.com/FFmpeg/FFmpeg/tree/n9.0.1)

The archive digest and executable hashes were verified; this establishes binary-to-archive identity. The upstream commit is the source pointer published by Gyan, not independent evidence of Gyan's complete build recipe. See [`third_party/ffmpeg/SOURCE.md`](third_party/ffmpeg/SOURCE.md) for verification details and remaining provenance gaps. Captured version, configuration, and license outputs are in [`third_party/ffmpeg/BUILD-OUTPUTS.txt`](third_party/ffmpeg/BUILD-OUTPUTS.txt).

## Other third-party dependencies

The FFmpeg configuration reports numerous external libraries and platform/hardware integration features. A configure flag does not, on its own, verify the exact linked component, its version, or its license. The component names, configuration flags, available project license references, and unknowns are itemized in [`third_party/ffmpeg/LICENSES.md`](third_party/ffmpeg/LICENSES.md). GPUPress does not currently include a complete version-matched dependency source and notice bundle for this Gyan build.

## Source, distribution, and specialist review status

The upstream FFmpeg 9.0.1 revision can be retrieved, and the binary archive match is confirmed. Gyan's complete build scripts/environment, any patches, dependency source revisions, and a full dependency-source/notice bundle have not been verified or assembled here. These gaps are documented in [`third_party/ffmpeg/SOURCE.md`](third_party/ffmpeg/SOURCE.md). This notice does not claim that source obligations or any other distribution requirements are resolved.

Codec implementations and formats enabled or relevant to this build include H.264, HEVC/H.265, AV1, AAC, and other audio/video technologies. **Specialist legal/patent review required**; this inventory is not a patent analysis and does not establish patent clearance.

This document distinguishes project code from third-party software and is a factual inventory, not legal advice or a compliance determination. It does not claim that GPUPress is GPL-licensed, that all FFmpeg dependencies are GPL-licensed, or that the installer or all its contents are MIT-licensed.
