# Corresponding-source record

This record identifies information available in the repository and distinguishes it from materials not established for the exact binaries.

## Identified binaries

- FFmpeg version/build string: `9.0.1-full_build-www.gyan.dev`
- FFprobe version/build string: `9.0.1-full_build-www.gyan.dev`
- Build compiler reported: GCC `16.1.0` (Rev2, built by the MSYS2 project)
- FFmpeg and FFprobe report GPL version 3 or later.
- Captured configure output: [BUILD-OUTPUTS.txt](BUILD-OUTPUTS.txt)

| Binary | SHA-256 |
|---|---|
| `ffmpeg.exe` | `57C56E369D5B4873B4D93FC1A1D833CB7CD8BC9325C14B05C34CE60B22842D8A` |
| `ffprobe.exe` | `AFE05347CAAABE479B3C4EAE71992B6EC1E11C57266A1D665DEB0F9FE9847208` |

The configure flags are recorded verbatim in [BUILD-OUTPUTS.txt](BUILD-OUTPUTS.txt); they include `--enable-gpl`, `--enable-version3`, `--enable-static`, `--enable-libx264`, and `--enable-libx265`. No `--enable-nonfree` flag appears in that output.

## Upstream and build references

- FFmpeg's official download/source information: <https://ffmpeg.org/download.html>
- FFmpeg upstream source repository: <https://git.ffmpeg.org/ffmpeg.git>
- FFmpeg legal information: <https://ffmpeg.org/legal.html>
- Gyan.dev Windows build page: <https://www.gyan.dev/ffmpeg/builds/>
- Gyan.dev build-site repository, which describes itself as the support site and mirror for the build site: <https://github.com/GyanD/codexffmpeg>

## Candidate Gyan package and upstream revision

The GyanD/codexffmpeg release record identifies a candidate matching package:

- Gyan release: [9.0.1](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.1)
- Candidate archive: `ffmpeg-9.0.1-full_build.7z`
- GitHub release asset SHA-256: `4b9c814cb07a1f90d05b768ef4eb2abbf89af94bbb924df5b7dbd6e64e1e2b96`
- Release record's upstream source pointer: `https://github.com/FFmpeg/FFmpeg/commit/bf1b838f2a`
- Full upstream commit: [`bf1b838f2ab88b4f8fd83443325c782ea0e0f7fa`](https://github.com/FFmpeg/FFmpeg/commit/bf1b838f2ab88b4f8fd83443325c782ea0e0f7fa)
- The full commit is the target of upstream tag [`n9.0.1`](https://github.com/FFmpeg/FFmpeg/tree/n9.0.1); the tag object is signed and GitHub reports its signature as verified.

### Exact local binary verification

The candidate archive was downloaded from the GyanD 9.0.1 release asset URL and its SHA-256 was verified before extraction:

`4b9c814cb07a1f90d05b768ef4eb2abbf89af94bbb924df5b7dbd6e64e1e2b96`

The SHA-256 values of both executables extracted from that archive match the local GPUPress binaries exactly:

| File | Local SHA-256 | Extracted archive SHA-256 | Exact match |
|---|---|---|---|
| `ffmpeg.exe` | `57C56E369D5B4873B4D93FC1A1D833CB7CD8BC9325C14B05C34CE60B22842D8A` | `57C56E369D5B4873B4D93FC1A1D833CB7CD8BC9325C14B05C34CE60B22842D8A` | Yes |
| `ffprobe.exe` | `AFE05347CAAABE479B3C4EAE71992B6EC1E11C57266A1D665DEB0F9FE9847208` | `AFE05347CAAABE479B3C4EAE71992B6EC1E11C57266A1D665DEB0F9FE9847208` | Yes |

**Exact binary-to-archive match confirmed.** The extracted and local executables also produced matching `-version`, `-buildconf`, `-encoders`, and `-L` command outputs. Both report FFmpeg 9.0.1, GCC 16.1.0 (Rev2, MSYS2), `--enable-gpl`, `--enable-version3`, `--enable-static`, and no `--enable-nonfree` in the configuration; relevant encoder registrations match. The command-output comparison is corroborative; the identical executable SHA-256 values establish exact binary identity.

The Gyan release record points to upstream FFmpeg commit `bf1b838f2ab88b4f8fd83443325c782ea0e0f7fa`, which is the target of tag `n9.0.1`. This establishes the source pointer published with the Gyan release, but does not by itself provide Gyan's full build recipe or all statically included dependency sources.

## Corresponding-source and build-material status

### Verified available

- Exact Gyan 9.0.1 full-build release archive identity and archive SHA-256.
- Byte-for-byte match of both local executables to the executables extracted from that verified archive.
- Upstream FFmpeg commit and tag identified by the Gyan release record; the upstream source revision can be retrieved independently.
- Executable-reported FFmpeg version, configure flags, compiler string (`GCC 16.1.0`, Rev2, MSYS2), library versions, and license output in [BUILD-OUTPUTS.txt](BUILD-OUTPUTS.txt).

### Partially available

- Gyan package metadata: release name, archive name, archive digest, and upstream source pointer are published in the [Gyan 9.0.1 release record](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.1). This record does not provide a complete build recipe or dependency source bundle.
- Build configuration and toolchain: executable-embedded configuration and compiler identification are captured, but exact toolchain package versions, build environment, build scripts, and reproducibility settings are not established.
- Upstream source: the FFmpeg revision is identified and independently retrievable, but this is not a package-specific archive of all corresponding FFmpeg and dependency sources for the static binaries.

### Not verified or missing

- Gyan build scripts and full build instructions/environment.
- Whether Gyan patches or modifications were applied, and any such patches.
- Exact source revisions and patches for dependencies, and a complete dependency source/notice bundle.
- A package-specific complete corresponding-source archive for this build.
- Reproducible-build information sufficient to recreate the exact executable bytes.

## Materials not currently available or verified

The following build materials remain missing or unverified:

- Any Gyan-specific patches or modifications, or a verified statement that none were applied.
- The complete build scripts, dependency versions/revisions, patches, and build environment/instructions used to produce the exact Gyan package.
- Exact source versions/revisions and any additional corresponding-source materials for external libraries statically linked into the executables.
- A complete dependency license inventory tied to the exact package, and all license texts/notices required for those exact included versions.
- Reproducible-build information sufficient to reproduce these exact executable bytes.

The upstream FFmpeg 9.0.1 source revision can be independently retrieved; that is useful evidence, but it is not by itself the complete corresponding source/build materials for these statically linked Gyan executables. The captured configure flags, verified local-to-archive executable hashes, Gyan release record, and upstream revision do not fill the dependency-source, patch, build-script, and full build-environment gaps.

## Distribution status

This record confirms the local executables are byte-for-byte the executables in the identified Gyan 9.0.1 full-build archive. It does not determine whether available materials satisfy any distribution obligation. Assemble and review the exact corresponding-source/build materials and obtain qualified licensing review before redistributing these binaries.
