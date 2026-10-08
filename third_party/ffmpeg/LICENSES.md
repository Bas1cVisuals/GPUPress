# Third-party component and license inventory

## GPUPress

GPUPress project source is separately licensed under the MIT License. See the repository root [LICENSE](../../LICENSE). This does not identify or relicense third-party executables or libraries.

## FFmpeg and FFprobe

The verified executables identify themselves as Gyan.dev FFmpeg/FFprobe `9.0.1-full_build-www.gyan.dev`. Both `-L` outputs state GNU GPL version 3 or later. Their captured configuration includes `--enable-gpl`, `--enable-version3`, and `--enable-static`; it contains no `--enable-nonfree` option. See [BUILD-OUTPUTS.txt](BUILD-OUTPUTS.txt) for captured output and [SOURCE.md](SOURCE.md) for exact archive and executable hashes.

This describes the license identity and configuration reported by the tools. It is not a conclusion about obligations for any particular distribution method.

## Dependency inventory basis and limits

The table below is based on exact configure options captured from the verified executables. An enabled configure option indicates a requested build feature; it does not, by itself, prove which dependency code or version is present in the final executable. The repository does not contain a complete link map, dependency manifest, dependency source revisions, or patches for the Gyan package. Except for the FFmpeg tool outputs and the verified archive contents, no dependency has been individually version-matched to this build here.

| Component / feature | Configure option(s) captured | License information available from project | Exact version/revision verified here? | Component-specific notice in GPUPress? |
|---|---|---|---|---|
| x264 | `--enable-libx264` | GNU GPL; [x264 COPYING](https://github.com/mirror/x264/blob/master/COPYING) | No | No |
| x265 | `--enable-libx265` | GNU GPL; [x265 COPYING](https://github.com/videolan/x265/blob/master/COPYING) | No | No |
| SVT-AV1 | `--enable-libsvtav1` | BSD 3-Clause Clear License; [SVT-AV1 LICENSE](https://github.com/AOMediaCodec/SVT-AV1/blob/main/LICENSE.md) | No | No |
| libaom | `--enable-libaom` | BSD-style; [libaom LICENSE](https://aomedia.googlesource.com/aom/+/refs/heads/main/LICENSE) | No | No |
| libvpx | `--enable-libvpx` | BSD-style; [libvpx LICENSE](https://github.com/webmproject/libvpx/blob/main/LICENSE) | No | No |
| dav1d | `--enable-libdav1d` | BSD-style license information; [dav1d project](https://code.videolan.org/videolan/dav1d) | No | No |
| rav1e | `--enable-librav1e` | Project licensing is in the [rav1e repository](https://github.com/xiph/rav1e); exact applicable file/revision not verified | No | No |
| Opus | `--enable-libopus` | BSD-style; [Opus COPYING](https://github.com/xiph/opus/blob/main/COPYING) | No | No |
| libass | `--enable-libass` | ISC; [libass COPYING](https://github.com/libass/libass/blob/master/COPYING) | No | No |
| FreeType | `--enable-libfreetype` | FTL or GPL licensing; [license information](https://freetype.org/license.html) | No | No |
| zimg | `--enable-libzimg` | WTFPL version 2; [zimg COPYING](https://github.com/sekrit-twc/zimg/blob/master/COPYING) | No | No |
| libplacebo | `--enable-libplacebo` | Project license files; [libplacebo repository](https://github.com/haasn/libplacebo); exact applicable version/license not verified | No | No |
| libxml2 | `--enable-libxml2` | MIT-style; [libxml2 project](https://gitlab.gnome.org/GNOME/libxml2) | No | No |
| LAME | `--enable-libmp3lame` | LGPL license information; [LAME project](https://lame.sourceforge.io/) | No | No |
| Vorbis | `--enable-libvorbis` | BSD-style license information; [Xiph.Org licenses](https://www.xiph.org/licenses/) | No | No |
| Xvid | `--enable-libxvid` | Project license information; [Xvid](https://www.xvid.com/) | No | No |
| AVS2 / davs2 | `--enable-libxavs2`, `--enable-libdavs2` | Exact license/revision not verified here | No | No |
| XEVE / XEVD | `--enable-libxeve`, `--enable-libxevd` | Exact license/revision not verified here | No | No |
| vvenc | `--enable-libvvenc` | Exact license/revision not verified here | No | No |
| SVT-JPEG-XS | `--enable-libsvtjpegxs` | Exact license/revision not verified here | No | No |
| libjxl | `--enable-libjxl` | Project license files; [libjxl repository](https://github.com/libjxl/libjxl); exact applicable version/license not verified | No | No |
| libwebp | `--enable-libwebp` | BSD-style license information; [WebP project](https://chromium.googlesource.com/webm/libwebp/) | No | No |
| libopenjpeg | `--enable-libopenjpeg` | BSD-style license information; [OpenJPEG](https://github.com/uclouvain/openjpeg) | No | No |
| libshine / twolame | `--enable-libshine`, `--enable-libtwolame` | Project license information exists; exact versions and applicable notices not verified | No | No |
| Theora / Speex | `--enable-libtheora`, `--enable-libspeex` | Xiph project license information exists; exact versions and applicable notices not verified | No | No |

### Other explicitly configured external components

The captured configuration also enables `cairo`, `fontconfig`, `iconv`, `gnutls`, `lcms2`, `gmp`, `bzlib`, `lzma`, `libsnappy`, `zlib`, `librist`, `libsrt`, `libssh`, `libzmq`, AviSynth, `libbluray`, `libcaca`, `libdvdnav`, `libdvdread`, SDL2, `libaribb24`, `libaribbcaption`, `libquirc`, `libuavs3d`, `libzvbi`, `liboapv`, `libqrencode`, `frei0r`, `libfribidi`, `libharfbuzz`, `liblensfun`, `libvidstab`, `libvmaf`, Media Foundation, `libvpl`, `libcdio`, OpenAL, `libgme`, `libmodplug`, `libopenmpt`, OpenCORE AMR-NB/WB, `libvo-amrwbenc`, `libcodec2`, `libilbc`, `libgsm`, `liblc3`, LADSPA, `libbs2b`, `libflite`, `libmysofa`, `librubberband`, `libsoxr`, Chromaprint, and Whisper. These are configure facts; linked/embedded status, exact versions, applicable licenses, and notice requirements have not been established for this package.

### Hardware and system integration options

The captured configuration includes `--enable-cuda-llvm`, `--enable-cuvid`, `--enable-ffnvcodec`, `--enable-nvdec`, `--enable-nvenc`, `--enable-amf`, `--enable-vulkan`, `--enable-vaapi`, `--enable-dxva2`, `--enable-d3d11va`, `--enable-d3d12va`, `--enable-opencl`, `--enable-mediafoundation`, and `--enable-libvpl`. FFmpeg encoder/hardware listings are not a complete link inventory. These flags do not identify exact headers, SDK versions, runtime dependencies, or their applicable terms.

## Notice status and follow-up

This repository contains no per-dependency license-text bundle or component-specific notices for the external libraries listed above. Links identify project sources for further verification; they do not establish the exact dependency versions used here. Before a public binary distribution, prepare an inventory tied to the verified archive, establish which components are actually included, and review the applicable notices and source materials. Do not infer that all dependencies use FFmpeg's license or that the configure list is a complete linked-component list.

## Engineering distribution options

| Option | Engineering effort and user experience | Provenance/documentation work | Unresolved review |
|---|---|---|---|
| A. Bundle the verified Gyan binaries | Lowest integration effort; convenient packaged experience | Preserve archive/executable hashes and provide applicable third-party notices and corresponding materials | Distribution terms, source obligations, dependencies, and codec/patent questions |
| B. Require user-provided FFmpeg | Add executable selection/detection and compatibility checks; adds setup burden | Document supported executable expectations and avoid silently substituting a build | Application/separate-process boundary and user-directed installation implications |
| C. Download FFmpeg at runtime | Add secure download, integrity/version pinning, failure handling, and updates; first-run network dependency | Identify authoritative origin, exact package/hash, notices, source availability, and retain build records | Distribution/hosting method and the same third-party licensing questions |
| D. Build a controlled FFmpeg distribution | Highest build, maintenance, and QA effort; enables project-controlled configuration | Pin source/dependencies, retain patches, scripts, toolchain/environment records, licenses/notices, and publish corresponding materials | Applicable license obligations, dependencies, and codec/patent questions remain for review |

## Scope

This file is a factual inventory, not legal advice or a compliance opinion. It does not determine redistribution obligations. No claim is made that GPUPress, the FFmpeg binaries, or the complete installer share one license.
