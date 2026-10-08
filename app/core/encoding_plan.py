"""Pure data models and policy helpers for future encoding decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import math
from typing import Any

from app.core.media import (
    FrameRateType,
    HDRClassification,
    MediaAnalysis,
)


class ResolutionMode(str, Enum):
    """Resolution target policy, independent of UI labels."""

    AUTO = "auto"
    SOURCE = "source"
    P720 = "720p"
    P1080 = "1080p"
    P1440 = "1440p"
    P2160 = "2160p"
    CUSTOM = "custom"


class FPSMode(str, Enum):
    """Frame-rate intent; CFR/CUSTOM request constant-frame-rate output."""

    AUTO = "auto"
    SMART = "smart"
    SOURCE = "source"
    CFR = "cfr"
    CUSTOM = "custom"


class AudioMode(str, Enum):
    """Audio stream handling intent."""

    AUTO = "auto"
    COPY = "copy"
    AAC = "aac"


class HDRMode(str, Enum):
    """Color/HDR output intent. Tone mapping is not performed in this phase."""

    AUTO = "auto"
    PRESERVE = "preserve"
    TONE_MAP_SDR = "tone_map_sdr"


class Codec(str, Enum):
    """Video codec family or editing intermediate profile."""

    AUTO = "auto"
    H264 = "h264"
    HEVC = "hevc"
    AV1 = "av1"
    PRORES_PROXY = "prores_proxy"
    PRORES_LT = "prores_lt"
    PRORES_422 = "prores_422"
    DNXHR_LB = "dnxhr_lb"
    DNXHR_SQ = "dnxhr_sq"
    DNXHR_HQ = "dnxhr_hq"


class RateControl(str, Enum):
    """Encoder rate-control family."""

    CQ = "cq"
    CBR = "cbr"
    VBR = "vbr"


class EncodingStrategyError(ValueError):
    """Raised when no permitted encoder strategy satisfies an encoding plan."""


class HDRPreservationError(EncodingStrategyError):
    """Raised when the selected pipeline cannot safely preserve source HDR."""


@dataclass(frozen=True)
class HardwareCapabilities:
    """Optional capability snapshot supplied by a future planner integration.

    Hardware probing remains owned by ``app.core.hardware.HardwareInfo``.
    This value only transports relevant facts; it does not probe hardware.
    """

    h264_nvenc: bool = False
    hevc_nvenc: bool = False
    av1_nvenc: bool = False
    cuda: bool = False
    scale_cuda: bool = False
    nvidia_available: bool = False
    gpu_name: str | None = None
    nvdec_available: bool = False
    available_encoders: tuple[str, ...] = ()


@dataclass(frozen=True)
class UserEncodingOptions:
    """User intent as values, with no dependency on UI widgets."""

    codec: Codec = Codec.AUTO
    resolution_mode: ResolutionMode = ResolutionMode.AUTO
    custom_width: int | None = None
    custom_height: int | None = None
    fps_mode: FPSMode = FPSMode.AUTO
    custom_fps: float | None = None
    target_fps: float | None = None
    audio_mode: AudioMode = AudioMode.AUTO
    audio_bitrate: int | None = None
    sample_rate: int | None = None
    channel_count: int | None = None
    audio_fallback_mode: AudioMode = AudioMode.AAC
    audio_fallback_bitrate: int | None = 192_000
    audio_fallback_sample_rate: int | None = 48_000
    audio_fallback_channel_count: int | None = 2
    hdr_mode: HDRMode = HDRMode.AUTO
    container: str = "mp4"
    prefer_gpu: bool = True
    allow_cpu_fallback: bool = True
    rate_control: RateControl = RateControl.CQ
    quality: float | None = 18
    bitrate: int | None = None
    encoder_preset: str | None = None
    gop_size: int | None = None
    preserve_aspect_ratio: bool = True
    prevent_upscale: bool = True
    require_even_dimensions: bool = True
    preserve_metadata: bool = True
    faststart: bool = True


@dataclass(frozen=True)
class EncodingPlan:
    """Resolved, serializable decisions for one encode (no command strings)."""

    codec: Codec
    resolution_mode: ResolutionMode
    output_width: int
    output_height: int
    custom_width: int | None
    custom_height: int | None
    fps_mode: FPSMode
    resolved_fps: float | None
    cfr_required: bool
    audio_mode: AudioMode
    audio_bitrate: int | None
    sample_rate: int | None
    channel_count: int | None
    audio_fallback_mode: AudioMode
    audio_fallback_bitrate: int | None
    audio_fallback_sample_rate: int | None
    audio_fallback_channel_count: int | None
    hdr_mode: HDRMode
    container: str
    prefer_gpu: bool
    allow_cpu_fallback: bool
    rate_control: RateControl
    quality: float | None
    bitrate: int | None
    encoder_preset: str | None
    gop_size: int | None
    preserve_aspect_ratio: bool
    prevent_upscale: bool
    require_even_dimensions: bool
    preserve_metadata: bool
    faststart: bool
    source_hdr_classification: HDRClassification = HDRClassification.UNKNOWN
    source_color_primaries: str | None = None
    source_color_transfer: str | None = None
    source_color_space: str | None = None
    source_color_range: str | None = None
    source_bit_depth: int | None = None
    source_hdr_metadata_types: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation with enum values."""
        result = asdict(self)
        return {
            key: value.value if isinstance(value, Enum) else value
            for key, value in result.items()
        }


@dataclass(frozen=True)
class ResolvedFrameRate:
    """Resolved numeric frame rate and whether output CFR is required."""

    fps: float | None
    cfr_required: bool


def resolve_encoding_pipelines(
    plan: EncodingPlan,
    capabilities: HardwareCapabilities,
) -> tuple[str, ...]:
    """Return allowed pipeline names in preferred order for this codec plan."""
    nvenc_names = {
        Codec.H264: ("h264_nvenc", capabilities.h264_nvenc),
        Codec.HEVC: ("hevc_nvenc", capabilities.hevc_nvenc),
        Codec.AV1: ("av1_nvenc", capabilities.av1_nvenc),
    }
    software_names = {
        Codec.H264: "libx264",
        Codec.HEVC: "libx265",
        Codec.PRORES_PROXY: "prores_ks",
        Codec.PRORES_LT: "prores_ks",
        Codec.PRORES_422: "prores_ks",
        Codec.DNXHR_LB: "dnxhd",
        Codec.DNXHR_SQ: "dnxhd",
        Codec.DNXHR_HQ: "dnxhd",
    }
    available = set(capabilities.available_encoders)
    candidates: list[str] = []
    nvenc_info = nvenc_names.get(plan.codec)
    if plan.prefer_gpu and nvenc_info:
        nvenc_name, flagged = nvenc_info
        nvenc_available = flagged or nvenc_name in available
        if nvenc_available:
            if (
                capabilities.nvidia_available
                and capabilities.cuda
                and capabilities.scale_cuda
            ):
                candidates.append("gpu")
            candidates.append("nvenc")

    software_name = software_names.get(plan.codec)
    software_available = software_name in available if software_name else False
    if not plan.prefer_gpu or plan.allow_cpu_fallback:
        if software_available:
            candidates.append("cpu")

    if candidates:
        return tuple(dict.fromkeys(candidates))

    codec_names = {
        Codec.H264: ("H.264", "h264_nvenc"),
        Codec.HEVC: ("HEVC", "hevc_nvenc"),
        Codec.AV1: ("AV1", "av1_nvenc"),
    }
    if plan.prefer_gpu and plan.codec in codec_names:
        display_name, nvenc_name = codec_names[plan.codec]
        nvenc_available = (
            nvenc_names[plan.codec][1]
            or nvenc_name in available
        )
        if not nvenc_available and (
            not plan.allow_cpu_fallback or not software_available
        ):
            if plan.codec is Codec.AV1:
                raise EncodingStrategyError(
                    "AV1 NVENC is unavailable in the installed FFmpeg build."
                )
            raise EncodingStrategyError(
                f"{display_name} NVENC is unavailable on this system."
            )
    raise EncodingStrategyError(
        f"No permitted encoder is available for {plan.codec.value}."
    )


_RESOLUTION_TARGETS: dict[ResolutionMode, tuple[int, int]] = {
    ResolutionMode.P720: (1280, 720),
    ResolutionMode.P1080: (1920, 1080),
    ResolutionMode.P1440: (2560, 1440),
    ResolutionMode.P2160: (3840, 2160),
}


def resolve_dimensions(
    source_width: int,
    source_height: int,
    mode: ResolutionMode,
    *,
    custom_width: int | None = None,
    custom_height: int | None = None,
    preserve_aspect_ratio: bool = True,
    prevent_upscale: bool = True,
    require_even_dimensions: bool = True,
) -> tuple[int, int]:
    """Resolve output dimensions without rotating source dimensions.

    Named targets are explicit landscape canvases whose axes are swapped for
    portrait sources. Square inputs are fitted inside that canvas, naturally
    receiving the short-edge limit of a resolution class such as 1080p.
    """
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Source width and height must be positive.")

    if mode in (ResolutionMode.AUTO, ResolutionMode.SOURCE):
        target_width, target_height = source_width, source_height
    elif mode is ResolutionMode.CUSTOM:
        if custom_width is None or custom_height is None:
            raise ValueError("Custom resolution requires width and height.")
        if custom_width <= 0 or custom_height <= 0:
            raise ValueError("Custom width and height must be positive.")
        target_width, target_height = custom_width, custom_height
    else:
        target_width, target_height = _RESOLUTION_TARGETS[mode]
        if source_width < source_height:
            target_width, target_height = target_height, target_width

    if mode in (ResolutionMode.AUTO, ResolutionMode.SOURCE):
        out_width, out_height = source_width, source_height
    elif preserve_aspect_ratio:
        scale = min(target_width / source_width, target_height / source_height)
        if prevent_upscale:
            scale = min(scale, 1.0)
        out_width = max(1, round(source_width * scale))
        out_height = max(1, round(source_height * scale))
    else:
        out_width, out_height = target_width, target_height
        if prevent_upscale:
            out_width = min(out_width, source_width)
            out_height = min(out_height, source_height)

    if require_even_dimensions:
        out_width = max(2, out_width - out_width % 2)
        out_height = max(2, out_height - out_height % 2)
    return out_width, out_height


def resolve_frame_rate(
    media: MediaAnalysis,
    mode: FPSMode = FPSMode.AUTO,
    *,
    custom_fps: float | None = None,
    target_fps: float | None = None,
) -> ResolvedFrameRate:
    """Resolve a target FPS without defaulting unknown/source media to 30."""
    video = media.video
    if video is None:
        source_nominal = source_average = None
        classification = FrameRateType.UNKNOWN
    else:
        source_nominal = video.frame_rate
        source_average = video.average_frame_rate
        classification = video.frame_rate_type

    if mode is FPSMode.CUSTOM:
        requested = custom_fps
        if requested is None or not math.isfinite(requested) or requested <= 0:
            raise ValueError("Custom FPS must be a positive finite number.")
        return ResolvedFrameRate(float(requested), True)

    if mode is FPSMode.CFR:
        requested = target_fps
        if requested is None:
            requested = source_nominal or source_average
        if requested is None or not math.isfinite(requested) or requested <= 0:
            raise ValueError("CFR output requires a valid target or source FPS.")
        return ResolvedFrameRate(float(requested), True)

    if mode is FPSMode.SOURCE:
        return ResolvedFrameRate(
            source_average or source_nominal,
            False,
        )

    if classification is FrameRateType.VFR:
        return ResolvedFrameRate(source_average or source_nominal, True)
    if classification is FrameRateType.CFR:
        return ResolvedFrameRate(source_average or source_nominal, False)
    # For uncertain cadence, expose the best available estimate but avoid
    # claiming the source is CFR or silently converting its timing.
    return ResolvedFrameRate(source_average or source_nominal, False)


def create_encoding_plan(
    media: MediaAnalysis,
    options: UserEncodingOptions | None = None,
    capabilities: HardwareCapabilities | None = None,
) -> EncodingPlan:
    """Combine source analysis, user intent, and capabilities into decisions."""
    options = options or UserEncodingOptions()
    # Capabilities are accepted for forward compatibility; encoder strategy
    # selection is intentionally deferred to the command/strategy phase.
    _ = capabilities

    if options.codec is Codec.AUTO:
        codec = Codec.H264
    else:
        codec = options.codec

    audio_mode = options.audio_mode
    audio_bitrate = options.audio_bitrate
    sample_rate = options.sample_rate
    channel_count = options.channel_count
    if audio_mode is AudioMode.AUTO:
        source_audio_codec = (
            media.audio.codec_name.lower()
            if media.audio and media.audio.codec_name
            else None
        )
        container = options.container.lower().lstrip(".")
        compatible_copy_codecs = {
            "mp4": {
                "aac", "mp3", "ac3", "eac3", "alac",
            },
            "m4v": {
                "aac", "mp3", "ac3", "eac3", "alac",
            },
            "mov": {
                "aac", "mp3", "ac3", "eac3", "alac",
                "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le",
                "pcm_s16be", "pcm_s24be", "pcm_s8", "pcm_u8",
                "pcm_alaw", "pcm_mulaw",
            },
        }
        compatible = (
            source_audio_codec is None
            or source_audio_codec
            in compatible_copy_codecs.get(container, set())
        )
        if compatible:
            audio_mode = AudioMode.COPY
        else:
            audio_mode = options.audio_fallback_mode
            audio_bitrate = options.audio_fallback_bitrate
            sample_rate = options.audio_fallback_sample_rate
            channel_count = options.audio_fallback_channel_count

    hdr_mode = options.hdr_mode
    if hdr_mode is HDRMode.AUTO:
        hdr_mode = HDRMode.PRESERVE

    if (
        media.video is None
        or media.video.width is None
        or media.video.height is None
    ):
        raise ValueError("Encoding plans require analyzed video dimensions.")

    video = media.video
    hdr_source = video.hdr_classification in {
        HDRClassification.HLG,
        HDRClassification.PQ,
        HDRClassification.DOLBY_VISION,
        HDRClassification.HDR_UNKNOWN,
    }
    if hdr_mode is HDRMode.TONE_MAP_SDR:
        raise HDRPreservationError(
            "HDR to SDR tone mapping is not yet implemented."
        )
    if hdr_source and hdr_mode is HDRMode.PRESERVE:
        if video.hdr_classification is HDRClassification.DOLBY_VISION:
            raise HDRPreservationError(
                "Dolby Vision dynamic metadata preservation is not supported "
                "for re-encoding. Choose a source-preserving workflow."
            )
        hdr_capable_codecs = {
            Codec.HEVC,
            Codec.AV1,
            Codec.PRORES_PROXY,
            Codec.PRORES_LT,
            Codec.PRORES_422,
            Codec.DNXHR_SQ,
            Codec.DNXHR_HQ,
        }
        if codec not in hdr_capable_codecs:
            raise HDRPreservationError(
                f"{codec.value} output cannot safely preserve HDR signaling "
                "and 10-bit video. Select HEVC, AV1, ProRes, or DNxHR SQ/HQ."
            )

    output_width, output_height = resolve_dimensions(
        media.video.width,
        media.video.height,
        options.resolution_mode,
        custom_width=options.custom_width,
        custom_height=options.custom_height,
        preserve_aspect_ratio=options.preserve_aspect_ratio,
        prevent_upscale=options.prevent_upscale,
        require_even_dimensions=options.require_even_dimensions,
    )
    fps = resolve_frame_rate(
        media,
        options.fps_mode,
        custom_fps=options.custom_fps,
        target_fps=options.target_fps,
    )
    return EncodingPlan(
        codec=codec,
        resolution_mode=options.resolution_mode,
        output_width=output_width,
        output_height=output_height,
        custom_width=options.custom_width,
        custom_height=options.custom_height,
        fps_mode=options.fps_mode,
        resolved_fps=fps.fps,
        cfr_required=fps.cfr_required,
        audio_mode=audio_mode,
        audio_bitrate=audio_bitrate,
        sample_rate=sample_rate,
        channel_count=channel_count,
        audio_fallback_mode=options.audio_fallback_mode,
        audio_fallback_bitrate=options.audio_fallback_bitrate,
        audio_fallback_sample_rate=options.audio_fallback_sample_rate,
        audio_fallback_channel_count=options.audio_fallback_channel_count,
        hdr_mode=hdr_mode,
        container=options.container,
        prefer_gpu=options.prefer_gpu,
        allow_cpu_fallback=options.allow_cpu_fallback,
        rate_control=options.rate_control,
        quality=options.quality,
        bitrate=options.bitrate,
        encoder_preset=options.encoder_preset,
        gop_size=options.gop_size,
        preserve_aspect_ratio=options.preserve_aspect_ratio,
        prevent_upscale=options.prevent_upscale,
        require_even_dimensions=options.require_even_dimensions,
        preserve_metadata=options.preserve_metadata,
        faststart=options.faststart,
        source_hdr_classification=video.hdr_classification,
        source_color_primaries=video.color_primaries,
        source_color_transfer=video.color_transfer,
        source_color_space=video.color_space,
        source_color_range=video.color_range,
        source_bit_depth=video.bit_depth,
        source_hdr_metadata_types=video.hdr_metadata_types,
    )
