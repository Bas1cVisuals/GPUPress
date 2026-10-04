from dataclasses import dataclass


@dataclass
class CompressionPreset:
    name: str

    # Video
    max_dimension: int = 1920
    codec: str = "h264"
    cq: int = 18
    fps: str = "30"
    encoder_preset: str = "p6"

    # Audio
    audio_mode: str = "aac"
    audio_bitrate: str = "192k"
    audio_rate: int = 48000
    audio_channels: int = 2

    # Behaviour
    preserve_aspect: bool = True
    force_even_dimensions: bool = True
    faststart: bool = True
    copy_metadata: bool = True


PRESETS = {
    "reel_1080p": CompressionPreset(
        name="Reel — 1080p",
        max_dimension=1920,
        codec="h264",
        cq=18,
        fps="30",
    ),

    "reel_4k": CompressionPreset(
        name="Reel — 4K",
        max_dimension=3840,
        codec="h264",
        cq=18,
        fps="30",
    ),

    "video_1080p": CompressionPreset(
        name="Video — 1080p",
        max_dimension=1920,
        codec="h264",
        cq=18,
        fps="30",
    ),

    "video_4k": CompressionPreset(
        name="Video — 4K",
        max_dimension=3840,
        codec="h264",
        cq=18,
        fps="30",
    ),

    "compatibility": CompressionPreset(
        name="Maximum Compatibility",
        max_dimension=1920,
        codec="h264",
        cq=20,
        fps="30",
        encoder_preset="p5",
        audio_mode="aac",
        audio_bitrate="192k",
        audio_rate=48000,
        audio_channels=2,
    ),

    "quality": CompressionPreset(
        name="High Quality",
        max_dimension=3840,
        codec="h264",
        cq=16,
        fps="original",
        encoder_preset="p6",
    ),

    "small_file": CompressionPreset(
        name="Small File",
        max_dimension=1920,
        codec="h264",
        cq=23,
        fps="30",
        encoder_preset="p5",
        audio_bitrate="128k",
    ),

    "custom": CompressionPreset(
        name="Custom",
        max_dimension=3840,
        codec="h264",
        cq=18,
        fps="30",
        encoder_preset="p6",
    ),
}


def get_preset(preset_id: str) -> CompressionPreset:
    return PRESETS.get(
        preset_id,
        PRESETS["reel_1080p"]
    )