"""Typed user-intent presets with temporary legacy worker compatibility."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

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
    create_encoding_plan,
)
from app.core.media import MediaAnalysis


class ContainerPreference(str, Enum):
    """Container preference for planned output; not a command-line option."""

    MP4 = "mp4"
    MOV = "mov"


@dataclass
class CompressionPreset:
    """Preset intent plus the legacy fields consumed by the current worker.

    ``to_user_options`` and ``to_encoding_plan`` are the new architecture
    boundary. Legacy video/audio fields remain until worker migration.
    """

    name: str

    # Legacy worker fields
    max_dimension: int = 1920
    codec: str = "h264"
    cq: int = 18
    fps: str = "original"
    encoder_preset: str = "p6"
    audio_mode: str = "copy"
    audio_bitrate: str = "192k"
    audio_rate: int = 48000
    audio_channels: int = 2
    preserve_aspect: bool = True
    force_even_dimensions: bool = True
    faststart: bool = True
    copy_metadata: bool = True

    # Typed encoding intent
    category: str = "delivery"
    codec_intent: Codec = Codec.H264
    resolution_mode: ResolutionMode = ResolutionMode.P1080
    fps_mode: FPSMode = FPSMode.SMART
    target_fps: float | None = None
    rate_control: RateControl = RateControl.CQ
    quality: float | None = 18
    bitrate: int | None = None
    audio_intent: AudioMode = AudioMode.AUTO
    audio_fallback_mode: AudioMode = AudioMode.AAC
    audio_fallback_bitrate: int | None = 192_000
    audio_fallback_sample_rate: int | None = 48_000
    audio_fallback_channel_count: int | None = 2
    hdr_mode: HDRMode = HDRMode.AUTO
    gop_size: int | None = None
    container: ContainerPreference = ContainerPreference.MP4
    prefer_gpu: bool = True
    allow_cpu_fallback: bool = True
    preserve_metadata: bool = True
    allow_upscale: bool = False

    def to_user_options(self) -> UserEncodingOptions:
        """Convert this preset's intent into typed planner input."""
        return UserEncodingOptions(
            codec=self.codec_intent,
            resolution_mode=self.resolution_mode,
            fps_mode=self.fps_mode,
            target_fps=self.target_fps,
            audio_mode=self.audio_intent,
            audio_bitrate=self._bitrate_value(self.audio_bitrate),
            sample_rate=self.audio_rate,
            channel_count=self.audio_channels,
            audio_fallback_mode=self.audio_fallback_mode,
            audio_fallback_bitrate=self.audio_fallback_bitrate,
            audio_fallback_sample_rate=self.audio_fallback_sample_rate,
            audio_fallback_channel_count=self.audio_fallback_channel_count,
            hdr_mode=self.hdr_mode,
            prefer_gpu=self.prefer_gpu,
            allow_cpu_fallback=self.allow_cpu_fallback,
            rate_control=self.rate_control,
            quality=self.quality,
            bitrate=self.bitrate,
            encoder_preset=self.encoder_preset,
            gop_size=self.gop_size,
            preserve_aspect_ratio=self.preserve_aspect,
            prevent_upscale=not self.allow_upscale,
            require_even_dimensions=self.force_even_dimensions,
            preserve_metadata=self.preserve_metadata,
            faststart=self.faststart,
            container=self.container.value,
        )

    def to_encoding_plan(
        self,
        media: MediaAnalysis,
        capabilities: HardwareCapabilities | None = None,
    ) -> EncodingPlan:
        """Resolve preset intent against analyzed source media."""
        return create_encoding_plan(
            media,
            self.to_user_options(),
            capabilities,
        )

    def to_legacy_worker_options(
        self,
        *,
        use_gpu: bool,
        allow_cpu_fallback: bool,
    ) -> UserEncodingOptions:
        """Adapt values still supplied by the pre-migration settings UI."""
        options = self.to_user_options()
        codec = {
            "h264": Codec.H264,
            "hevc": Codec.HEVC,
            "h265": Codec.HEVC,
            "av1": Codec.AV1,
            "prores_proxy": Codec.PRORES_PROXY,
            "prores_lt": Codec.PRORES_LT,
            "prores_422": Codec.PRORES_422,
            "dnxhr_lb": Codec.DNXHR_LB,
            "dnxhr_sq": Codec.DNXHR_SQ,
            "dnxhr_hq": Codec.DNXHR_HQ,
        }.get(str(self.codec).lower(), options.codec)
        resolution = {
            1280: ResolutionMode.P720,
            1920: ResolutionMode.P1080,
            2560: ResolutionMode.P1440,
            3840: ResolutionMode.P2160,
        }.get(self.max_dimension, options.resolution_mode)
        fps = str(self.fps).strip().lower()
        if fps and fps != "original":
            try:
                explicit_fps = float(fps)
            except ValueError as error:
                raise ValueError(f"Invalid selected frame rate: {fps}") from error
            fps_mode = FPSMode.CFR
        else:
            explicit_fps = None
            fps_mode = options.fps_mode

        audio_mode = (
            AudioMode.AAC
            if str(self.audio_mode).lower() == "aac"
            else options.audio_mode
        )
        return replace(
            options,
            codec=codec,
            resolution_mode=resolution,
            fps_mode=fps_mode,
            target_fps=(
                explicit_fps
                if fps_mode is FPSMode.CFR
                else options.target_fps
            ),
            audio_mode=audio_mode,
            audio_bitrate=(
                self._bitrate_value(self.audio_bitrate)
                if audio_mode is AudioMode.AAC
                else options.audio_bitrate
            ),
            sample_rate=self.audio_rate,
            channel_count=self.audio_channels,
            quality=(
                self.cq
                if codec in (Codec.H264, Codec.HEVC, Codec.AV1)
                else options.quality
            ),
            encoder_preset=self.encoder_preset or options.encoder_preset,
            preserve_aspect_ratio=self.preserve_aspect,
            prevent_upscale=True,
            require_even_dimensions=self.force_even_dimensions,
            preserve_metadata=self.copy_metadata,
            faststart=self.faststart,
            prefer_gpu=use_gpu and self.prefer_gpu,
            allow_cpu_fallback=(
                allow_cpu_fallback and self.allow_cpu_fallback
            ),
        )

    @staticmethod
    def _bitrate_value(value: str | int | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = value.strip().lower()
        try:
            if text.endswith("k"):
                return int(float(text[:-1]) * 1000)
            if text.endswith("m"):
                return int(float(text[:-1]) * 1_000_000)
            return int(text)
        except (ValueError, OverflowError):
            return None


def _preset(
    name: str,
    *,
    category: str,
    codec: Codec,
    resolution: ResolutionMode,
    quality: float | None = 18,
    rate_control: RateControl = RateControl.CQ,
    bitrate: int | None = None,
    fps: FPSMode = FPSMode.SMART,
    target_fps: float | None = None,
    audio: AudioMode = AudioMode.AUTO,
    audio_fallback_bitrate: int | None = 192_000,
    gop_size: int | None = None,
    container: ContainerPreference = ContainerPreference.MP4,
    hdr: HDRMode = HDRMode.AUTO,
    prefer_gpu: bool = True,
    allow_upscale: bool = False,
    legacy_max_dimension: int = 1920,
    legacy_codec: str | None = None,
    legacy_cq: int | None = None,
    legacy_fps: str = "original",
    legacy_audio_mode: str = "copy",
) -> CompressionPreset:
    return CompressionPreset(
        name=name,
        max_dimension=legacy_max_dimension,
        codec=legacy_codec or codec.value,
        cq=int(quality) if legacy_cq is None and quality is not None else (legacy_cq or 18),
        fps=legacy_fps,
        audio_mode=legacy_audio_mode,
        category=category,
        codec_intent=codec,
        resolution_mode=resolution,
        fps_mode=fps,
        target_fps=target_fps,
        rate_control=rate_control,
        quality=quality,
        bitrate=bitrate,
        audio_intent=audio,
        audio_fallback_bitrate=audio_fallback_bitrate,
        gop_size=gop_size,
        container=container,
        hdr_mode=hdr,
        prefer_gpu=prefer_gpu,
        allow_upscale=allow_upscale,
        audio_bitrate=f"{audio_fallback_bitrate // 1000}k"
        if audio_fallback_bitrate
        else "192k",
    )


_PRESETS = {
    # Current UI/worker identifiers remain available until Phase 4.
    "reel_1080p": _preset(
        "Reel — 1080p", category="legacy", codec=Codec.H264,
        resolution=ResolutionMode.P1080, quality=18,
        legacy_max_dimension=1920, legacy_cq=18,
    ),
    "reel_4k": _preset(
        "Reel — 4K", category="legacy", codec=Codec.H264,
        resolution=ResolutionMode.P2160, quality=18,
        legacy_max_dimension=3840, legacy_cq=18,
    ),
    "video_1080p": _preset(
        "Video — 1080p", category="legacy", codec=Codec.H264,
        resolution=ResolutionMode.P1080, quality=18,
        legacy_max_dimension=1920, legacy_cq=18,
    ),
    "video_4k": _preset(
        "Video — 4K", category="legacy", codec=Codec.H264,
        resolution=ResolutionMode.P2160, quality=18,
        legacy_max_dimension=3840, legacy_cq=18,
    ),
    "compatibility": _preset(
        "Maximum Compatibility", category="legacy", codec=Codec.H264,
        resolution=ResolutionMode.P1080, quality=20,
        legacy_max_dimension=1920, legacy_cq=20,
        legacy_audio_mode="aac",
    ),
    "quality": _preset(
        "High Quality", category="legacy", codec=Codec.H264,
        resolution=ResolutionMode.P2160, quality=16,
        legacy_max_dimension=3840, legacy_fps="original", legacy_cq=16,
    ),
    "small_file": _preset(
        "Small File", category="legacy", codec=Codec.H264,
        resolution=ResolutionMode.P1080, quality=23,
        legacy_max_dimension=1920, legacy_cq=23,
        audio_fallback_bitrate=128_000,
    ),
    "custom": _preset(
        "Custom", category="legacy", codec=Codec.H264,
        resolution=ResolutionMode.P2160, quality=18,
        legacy_max_dimension=3840, legacy_cq=18,
    ),

    # Delivery
    "fast_web_social": _preset(
        "Fast Web / Social", category="delivery", codec=Codec.H264,
        resolution=ResolutionMode.P1080, quality=20,
    ),
    "high_quality_delivery": _preset(
        "High Quality Delivery", category="delivery", codec=Codec.H264,
        resolution=ResolutionMode.P2160, quality=17,
    ),
    "small_file_delivery": _preset(
        "Small File", category="delivery", codec=Codec.H264,
        resolution=ResolutionMode.P1080, quality=24,
        audio_fallback_bitrate=128_000,
    ),

    # Editing
    "h264_proxy_1080p": _preset(
        "H.264 Proxy 1080p", category="editing", codec=Codec.H264,
        resolution=ResolutionMode.P1080, quality=22,
    ),
    "h264_proxy_720p": _preset(
        "H.264 Proxy 720p", category="editing", codec=Codec.H264,
        resolution=ResolutionMode.P720, quality=23,
    ),
    "fast_scrub_h264": _preset(
        "Fast Scrub H.264", category="editing", codec=Codec.H264,
        resolution=ResolutionMode.SOURCE, rate_control=RateControl.CBR,
        bitrate=8_000_000, gop_size=15,
    ),

    # Master / intermediate
    "prores_proxy": _preset(
        "ProRes Proxy", category="intermediate", codec=Codec.PRORES_PROXY,
        resolution=ResolutionMode.P1080, quality=None,
        container=ContainerPreference.MOV, prefer_gpu=False,
    ),
    "prores_lt": _preset(
        "ProRes LT", category="intermediate", codec=Codec.PRORES_LT,
        resolution=ResolutionMode.SOURCE, quality=None,
        container=ContainerPreference.MOV, prefer_gpu=False,
    ),
    "prores_422": _preset(
        "ProRes 422", category="intermediate", codec=Codec.PRORES_422,
        resolution=ResolutionMode.SOURCE, quality=None,
        container=ContainerPreference.MOV, prefer_gpu=False,
    ),
    "dnxhr_lb": _preset(
        "DNxHR LB", category="intermediate", codec=Codec.DNXHR_LB,
        resolution=ResolutionMode.P1080, quality=None,
        container=ContainerPreference.MOV, prefer_gpu=False,
    ),
    "dnxhr_sq": _preset(
        "DNxHR SQ", category="intermediate", codec=Codec.DNXHR_SQ,
        resolution=ResolutionMode.SOURCE, quality=None,
        container=ContainerPreference.MOV, prefer_gpu=False,
    ),
    "dnxhr_hq": _preset(
        "DNxHR HQ", category="intermediate", codec=Codec.DNXHR_HQ,
        resolution=ResolutionMode.SOURCE, quality=None,
        container=ContainerPreference.MOV, prefer_gpu=False,
    ),

    # Source-oriented delivery
    "original_source_quality": _preset(
        "Original / Source Quality", category="source",
        codec=Codec.H264, resolution=ResolutionMode.SOURCE,
        quality=18, hdr=HDRMode.PRESERVE,
    ),
}

PRESETS = _PRESETS


def get_preset(preset_id: str) -> CompressionPreset:
    """Return a fresh preset instance by ID, with legacy default fallback."""
    preset = PRESETS.get(preset_id, PRESETS["reel_1080p"])
    from copy import deepcopy

    return deepcopy(preset)
