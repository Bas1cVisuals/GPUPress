"""Pure helpers that translate visible UI choices into typed encoding intent."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.encoding_plan import (
    AudioMode,
    Codec,
    EncodingPlan,
    FPSMode,
    HDRMode,
    HardwareCapabilities,
    RateControl,
    ResolutionMode,
    UserEncodingOptions,
)
from app.core.media import FrameRateType, HDRClassification, MediaAnalysis


@dataclass(frozen=True)
class CodecChoice:
    """A human-readable UI codec choice and its intended processing path."""

    key: str
    label: str
    codec: Codec
    prefer_gpu: bool


_CODEC_CHOICES = (
    ("h264_nvenc", "H.264 (NVIDIA)", Codec.H264, True, "h264_nvenc"),
    ("hevc_nvenc", "HEVC (NVIDIA)", Codec.HEVC, True, "hevc_nvenc"),
    ("av1_nvenc", "AV1 (NVIDIA)", Codec.AV1, True, "av1_nvenc"),
    ("h264_software", "H.264 (Software)", Codec.H264, False, "libx264"),
    ("hevc_software", "HEVC (Software)", Codec.HEVC, False, "libx265"),
    ("prores_proxy", "ProRes Proxy", Codec.PRORES_PROXY, False, "prores_ks"),
    ("prores_lt", "ProRes LT", Codec.PRORES_LT, False, "prores_ks"),
    ("prores_422", "ProRes 422", Codec.PRORES_422, False, "prores_ks"),
    ("dnxhr_lb", "DNxHR LB", Codec.DNXHR_LB, False, "dnxhd"),
    ("dnxhr_sq", "DNxHR SQ", Codec.DNXHR_SQ, False, "dnxhd"),
    ("dnxhr_hq", "DNxHR HQ", Codec.DNXHR_HQ, False, "dnxhd"),
)


def codec_choices(capabilities: HardwareCapabilities) -> tuple[CodecChoice, ...]:
    """List only software/NVENC encoders reported as available."""
    encoders = set(capabilities.available_encoders)
    flags = {
        "h264_nvenc": capabilities.h264_nvenc,
        "hevc_nvenc": capabilities.hevc_nvenc,
        "av1_nvenc": capabilities.av1_nvenc,
    }
    choices = []
    for key, label, codec, gpu, encoder in _CODEC_CHOICES:
        available = (
            capabilities.nvidia_available
            and (encoder in encoders or flags.get(encoder, False))
            if gpu
            else encoder in encoders
        )
        if available:
            choices.append(CodecChoice(key, label, codec, gpu))
    return tuple(choices)


def codec_choice_key(codec: Codec, prefer_gpu: bool) -> str:
    """Map preset/core codec intent to the matching UI codec choice."""
    for key, _, choice_codec, choice_gpu, _ in _CODEC_CHOICES:
        if choice_codec is codec and choice_gpu is prefer_gpu:
            return key
    for key, _, choice_codec, _, _ in _CODEC_CHOICES:
        if choice_codec is codec:
            return key
    raise ValueError(f"No UI codec choice is defined for {codec.value}.")


def parse_audio_bitrate(value: str | int) -> int:
    """Convert familiar UI bitrate labels (for example, ``192k``) to bps."""
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    multiplier = 1000 if text.endswith("k") else 1
    number = text[:-1] if multiplier == 1000 else text
    return int(float(number) * multiplier)


def containers_for_codec(codec: Codec) -> tuple[str, ...]:
    """Return supported UI container intent choices for a codec family."""
    if codec in {
        Codec.PRORES_PROXY,
        Codec.PRORES_LT,
        Codec.PRORES_422,
        Codec.DNXHR_LB,
        Codec.DNXHR_SQ,
        Codec.DNXHR_HQ,
    }:
        return ("mov", "mkv")
    return ("mp4", "mkv", "mov")


def adaptive_control_visibility(
    *,
    codec: Codec,
    nvenc: bool,
    resolution_mode: str,
    fps_value: str,
    rate_control: str,
    audio_mode: str,
) -> dict[str, bool]:
    """Return visibility state for controls that depend on current intent."""
    intermediate = codec not in (Codec.H264, Codec.HEVC, Codec.AV1)
    quality_mode = rate_control == RateControl.CQ.value
    audio_encoded = audio_mode != AudioMode.COPY.value
    return {
        "custom_resolution": resolution_mode == ResolutionMode.CUSTOM.value,
        "custom_fps": fps_value == "custom",
        "quality": not intermediate,
        "rate_control": not intermediate,
        "cq_value": not intermediate and quality_mode,
        "bitrate_value": not intermediate and not quality_mode,
        "nvenc_preset": nvenc,
        "encoder_preset": (
            codec in (Codec.H264, Codec.HEVC) or nvenc
        ),
        "gop": not intermediate,
        "hardware": not intermediate,
        "audio_encoding": audio_encoded,
    }


def build_user_options(
    *,
    codec_key: str,
    resolution_mode: ResolutionMode,
    custom_width: int = 1920,
    custom_height: int = 1080,
    preserve_aspect_ratio: bool = True,
    allow_upscale: bool = False,
    fps_value: str = "smart",
    custom_fps: float | None = None,
    audio_mode: AudioMode = AudioMode.AUTO,
    audio_bitrate: str | int = 192_000,
    sample_rate: int = 48_000,
    channel_count: int = 2,
    hdr_mode: HDRMode = HDRMode.AUTO,
    rate_control: RateControl = RateControl.CQ,
    quality: float = 20,
    bitrate: int | None = None,
    encoder_preset: str | None = None,
    gop_size: int | None = None,
    container: str | None = None,
    prefer_gpu: bool | None = None,
    allow_cpu_fallback: bool = True,
    preserve_metadata: bool = True,
    faststart: bool = True,
) -> UserEncodingOptions:
    """Construct typed intent from validated UI-level values."""
    choices = {choice[0]: choice for choice in _CODEC_CHOICES}
    if codec_key not in choices:
        raise ValueError(f"Unknown codec choice: {codec_key}")
    _, _, codec, choice_prefers_gpu, _ = choices[codec_key]
    if fps_value == "smart":
        fps_mode = FPSMode.SMART
        requested_fps = None
    elif fps_value == "custom":
        if custom_fps is None or custom_fps <= 0:
            raise ValueError("Enter a positive custom frame rate.")
        fps_mode = FPSMode.CUSTOM
        requested_fps = custom_fps
    else:
        try:
            requested_fps = float(fps_value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid frame-rate choice: {fps_value}") from error
        fps_mode = FPSMode.CUSTOM

    selected_container = container or (
        "mov"
        if codec in {
            Codec.PRORES_PROXY, Codec.PRORES_LT, Codec.PRORES_422,
            Codec.DNXHR_LB, Codec.DNXHR_SQ, Codec.DNXHR_HQ,
        }
        else "mp4"
    )
    if selected_container not in containers_for_codec(codec):
        raise ValueError(
            f"{selected_container.upper()} is not an available container "
            f"for {codec.value}."
        )
    gpu_preference = (
        choice_prefers_gpu if prefer_gpu is None else prefer_gpu and choice_prefers_gpu
    )
    return UserEncodingOptions(
        codec=codec,
        resolution_mode=resolution_mode,
        custom_width=custom_width if resolution_mode is ResolutionMode.CUSTOM else None,
        custom_height=custom_height if resolution_mode is ResolutionMode.CUSTOM else None,
        fps_mode=fps_mode,
        custom_fps=requested_fps if fps_mode is FPSMode.CUSTOM else None,
        target_fps=requested_fps if fps_mode is FPSMode.CFR else None,
        audio_mode=audio_mode,
        audio_bitrate=parse_audio_bitrate(audio_bitrate) if audio_mode is AudioMode.AAC else None,
        sample_rate=sample_rate if audio_mode is AudioMode.AAC else None,
        channel_count=channel_count if audio_mode is AudioMode.AAC else None,
        audio_fallback_mode=AudioMode.AAC,
        audio_fallback_bitrate=parse_audio_bitrate(audio_bitrate),
        audio_fallback_sample_rate=sample_rate,
        audio_fallback_channel_count=channel_count,
        hdr_mode=hdr_mode,
        container=selected_container,
        prefer_gpu=gpu_preference,
        allow_cpu_fallback=allow_cpu_fallback,
        rate_control=rate_control,
        quality=(
            quality
            if codec in (Codec.H264, Codec.HEVC, Codec.AV1)
            and rate_control is RateControl.CQ
            else None
        ),
        bitrate=bitrate,
        encoder_preset=encoder_preset,
        gop_size=gop_size,
        preserve_aspect_ratio=preserve_aspect_ratio,
        prevent_upscale=not allow_upscale,
        preserve_metadata=preserve_metadata,
        faststart=faststart,
    )


def format_media_summary(media: MediaAnalysis) -> str:
    """Format analyzed source details without independently interpreting probe data."""
    video = media.video
    audio = media.audio
    if video is None:
        return "Video information unavailable"
    lines = []
    if video.width and video.height:
        lines.append(f"{video.width} × {video.height}")
    orientation = video.orientation.value.title()
    aspect = "aspect ratio unknown"
    if video.width and video.height:
        ratio = video.width / video.height
        common_ratios = (
            (16 / 9, "16:9"),
            (9 / 16, "9:16"),
            (4 / 3, "4:3"),
            (1.0, "1:1"),
        )
        closest = min(common_ratios, key=lambda item: abs(item[0] - ratio))
        aspect = (
            closest[1]
            if abs(closest[0] - ratio) <= 0.01
            else f"{ratio:.2f}:1"
        )
    lines.append(f"{orientation} · {aspect}")
    codec = (video.codec_name or "Unknown").upper()
    if video.bit_depth:
        codec += f" · {video.bit_depth}-bit"
    lines.append(codec)
    if video.pixel_format:
        lines.append(f"Pixel format: {video.pixel_format}")
    color = [
        value
        for value in (video.color_primaries, video.color_transfer, video.color_space)
        if value
    ]
    if color:
        lines.append(f"Color: {' · '.join(color)}")
    fps = (
        f"{video.frame_rate:.2f} FPS"
        if video.frame_rate
        else "FPS unknown"
    )
    cadence = {
        FrameRateType.CFR: "CFR",
        FrameRateType.VFR: "VFR",
        FrameRateType.UNKNOWN: "cadence unknown",
    }[video.frame_rate_type]
    cadence_text = (
        "VFR source — output will use deterministic CFR when required"
        if video.frame_rate_type is FrameRateType.VFR
        else f"{fps} · {cadence}"
    )
    lines.append(cadence_text)
    hdr = {
        HDRClassification.SDR: "SDR",
        HDRClassification.HLG: "HLG",
        HDRClassification.PQ: "HDR10 / PQ",
        HDRClassification.DOLBY_VISION:
            "Dolby Vision metadata detected · preservation not guaranteed",
        HDRClassification.HDR_UNKNOWN: "HDR detected",
        HDRClassification.UNKNOWN: "HDR status unknown",
    }[video.hdr_classification]
    lines.append(hdr)
    if audio:
        audio_text = (audio.codec_name or "Audio").upper()
        if audio.sample_rate:
            audio_text += f" · {audio.sample_rate // 1000} kHz"
        if audio.channel_layout:
            audio_text += f" · {audio.channel_layout.title()}"
        elif audio.channels:
            audio_text += f" · {audio.channels} channels"
        lines.append(audio_text)
    if media.duration is not None:
        total = int(media.duration)
        lines.append(f"{total // 60:02d}:{total % 60:02d}")
    return "\n".join(lines)


def format_plan_summary(
    plan: EncodingPlan,
    *,
    encoder_label: str,
    gpu_name: str | None = None,
) -> str:
    """Summarize resolved plan decisions for the output preview."""
    fps = (
        f"{plan.resolved_fps:.2f} FPS"
        if plan.resolved_fps is not None
        else "Source FPS"
    )
    if plan.cfr_required:
        fps += " CFR"
    audio = (
        "Audio copy"
        if plan.audio_mode is AudioMode.COPY
        else f"AAC {plan.audio_bitrate // 1000} kbps"
        if plan.audio_mode is AudioMode.AAC and plan.audio_bitrate
        else "Audio auto"
    )
    hdr = (
        "HDR preservation requested"
        if plan.hdr_mode is HDRMode.PRESERVE
        else plan.hdr_mode.value
    )
    details = [
        f"{plan.output_width} × {plan.output_height}",
        encoder_label,
        fps,
        audio,
        hdr,
    ]
    if plan.prefer_gpu and gpu_name:
        details.append(gpu_name)
    elif not plan.prefer_gpu:
        details.append("CPU encoding")
    return "Output\n" + "\n".join(details)
