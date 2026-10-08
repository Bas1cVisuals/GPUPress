from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from fractions import Fraction
import json
import logging
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping


class Orientation(str, Enum):
    """Orientation inferred from unrotated FFprobe stream dimensions."""

    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    SQUARE = "square"
    UNKNOWN = "unknown"


class FrameRateType(str, Enum):
    """Confidence-conscious classification of a stream's frame cadence."""

    CFR = "cfr"
    VFR = "vfr"
    UNKNOWN = "unknown"


class HDRClassification(str, Enum):
    """HDR/color-transfer classification based on available stream metadata."""

    SDR = "sdr"
    HLG = "hlg"
    PQ = "pq"
    DOLBY_VISION = "dolby_vision"
    HDR_UNKNOWN = "hdr_unknown"
    UNKNOWN = "unknown"


def parse_frame_rate(value: Any) -> float | None:
    """Parse an FFprobe rational or numeric frame rate, if valid."""
    if value is None:
        return None
    try:
        rate = float(Fraction(str(value).strip()))
    except (ValueError, ZeroDivisionError, TypeError, OverflowError):
        try:
            rate = float(value)
        except (ValueError, TypeError, OverflowError):
            return None
    if rate <= 0 or rate == float("inf") or rate != rate:
        return None
    return rate


def _positive_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result > 0 else None


def _optional_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 and result != float("inf") else None


def _classify_frame_rate(
    nominal: float | None,
    average: float | None,
) -> FrameRateType:
    if nominal is None or average is None:
        return FrameRateType.UNKNOWN
    # FFprobe's r_frame_rate is a nominal/base cadence and avg_frame_rate
    # reflects observed timestamps. Their numeric divergence is a VFR signal.
    tolerance = max(0.01, nominal * 0.001)
    return (
        FrameRateType.CFR
        if abs(nominal - average) <= tolerance
        else FrameRateType.VFR
    )


def _classify_timestamps(
    timestamps: list[float],
) -> tuple[FrameRateType, float | None]:
    ordered = sorted(set(timestamps))
    if len(ordered) < 4:
        return FrameRateType.UNKNOWN, None
    intervals = [
        later - earlier
        for earlier, later in zip(ordered, ordered[1:])
        if later > earlier
    ]
    if len(intervals) < 3:
        return FrameRateType.UNKNOWN, None
    median = sorted(intervals)[len(intervals) // 2]
    if median <= 0:
        return FrameRateType.UNKNOWN, None
    tolerance = max(0.0011, median * 0.03)
    cadence = (
        FrameRateType.CFR
        if all(abs(interval - median) <= tolerance for interval in intervals)
        else FrameRateType.VFR
    )
    average = (len(ordered) - 1) / (ordered[-1] - ordered[0])
    return cadence, average


def _infer_bit_depth(pixel_format: str | None) -> int | None:
    if not pixel_format:
        return None
    name = pixel_format.lower()

    if name.startswith("p010"):
        return 10

    depth_match = re.search(r"(?<!\d)(9|10|12|14|16)(?:le|be|$)", name)
    if depth_match:
        return int(depth_match.group(1))

    if name in {
        "nv12", "nv21", "yuv420p", "yuv422p", "yuv444p",
        "yuv410p", "yuv411p", "yuv440p", "yuvj420p", "yuvj422p",
        "yuvj444p", "gbrp", "gray", "gray8", "rgb24", "bgr24",
        "rgba", "bgra", "argb", "abgr", "yuyv422", "uyvy422",
    }:
        return 8
    return None


def _metadata_contains(value: Any, terms: tuple[str, ...]) -> bool:
    if isinstance(value, Mapping):
        return any(
            _metadata_contains(key, terms)
            or _metadata_contains(item, terms)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_metadata_contains(item, terms) for item in value)
    text = str(value).lower()
    return any(term in text for term in terms)


def _classify_hdr(stream: Mapping[str, Any]) -> HDRClassification:
    transfer = str(stream.get("color_transfer") or "").lower()
    side_data = stream.get("side_data_list", [])
    tags = stream.get("tags", {})

    if _metadata_contains(
        (side_data, tags),
        ("dolby vision", "dolby_vision", "dovi", "dovi configuration"),
    ):
        return HDRClassification.DOLBY_VISION
    if transfer == "smpte2084":
        return HDRClassification.PQ
    if transfer == "arib-std-b67":
        return HDRClassification.HLG
    if _metadata_contains(
        side_data,
        ("mastering display metadata", "content light level metadata"),
    ):
        return HDRClassification.HDR_UNKNOWN
    if str(stream.get("color_primaries") or "").lower() == "bt2020":
        return HDRClassification.HDR_UNKNOWN
    if transfer in {
        "bt709", "bt470m", "bt470bg", "smpte170m", "smpte240m",
        "gamma22", "gamma28", "iec61966-2-1", "smpte428",
    }:
        return HDRClassification.SDR
    return HDRClassification.UNKNOWN


@dataclass(frozen=True)
class VideoStreamInfo:
    """Structured information for the first video stream."""

    codec_name: str | None = None
    width: int | None = None
    height: int | None = None
    coded_width: int | None = None
    coded_height: int | None = None
    rotation_degrees: float | None = None
    orientation: Orientation = Orientation.UNKNOWN
    aspect_ratio: float | None = None
    pixel_format: str | None = None
    bit_depth: int | None = None
    r_frame_rate: str | None = None
    avg_frame_rate: str | None = None
    frame_rate: float | None = None
    average_frame_rate: float | None = None
    frame_rate_type: FrameRateType = FrameRateType.UNKNOWN
    color_space: str | None = None
    color_transfer: str | None = None
    color_primaries: str | None = None
    color_range: str | None = None
    hdr_classification: HDRClassification = HDRClassification.UNKNOWN
    hdr_metadata_types: tuple[str, ...] = ()
    duration: float | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def codec_type(self) -> str:
        return "video"

    @property
    def is_vfr(self) -> bool | None:
        if self.frame_rate_type is FrameRateType.UNKNOWN:
            return None
        return self.frame_rate_type is FrameRateType.VFR

    def get(self, key: str, default: Any = None) -> Any:
        """Provide a small dict-compatible view for existing UI callers."""
        aliases = {
            "codec_name": self.codec_name,
            "codec_type": self.codec_type,
            "width": self.width,
            "height": self.height,
            "r_frame_rate": self.r_frame_rate,
            "avg_frame_rate": self.avg_frame_rate,
            "pix_fmt": self.pixel_format,
            "duration": self.duration,
        }
        value = aliases.get(key)
        return default if value is None else value


@dataclass(frozen=True)
class AudioStreamInfo:
    """Structured information for the first audio stream."""

    codec_name: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    channel_layout: str | None = None
    duration: float | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def codec_type(self) -> str:
        return "audio"

    def get(self, key: str, default: Any = None) -> Any:
        aliases = {
            "codec_name": self.codec_name,
            "codec_type": self.codec_type,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "channel_layout": self.channel_layout,
            "duration": self.duration,
        }
        value = aliases.get(key)
        return default if value is None else value


@dataclass(frozen=True)
class MediaAnalysis:
    """Typed FFprobe result with first video/audio streams and format data."""

    video: VideoStreamInfo | None = None
    audio: AudioStreamInfo | None = None
    format_name: str | None = None
    duration: float | None = None
    size: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Provide a compatibility mapping view for the current UI."""
        if key == "streams":
            return [stream for stream in (self.video, self.audio) if stream]
        if key == "format":
            values = {
                "format_name": self.format_name,
                "duration": self.duration,
                "size": self.size,
            }
            return {name: value for name, value in values.items() if value is not None}
        return default

    def __bool__(self) -> bool:
        """Match the old probe result's falsy behavior when no data was read."""
        return bool(
            self.video
            or self.audio
            or self.format_name
            or self.duration is not None
            or self.size is not None
        )

    @classmethod
    def from_ffprobe(cls, data: Mapping[str, Any]) -> MediaAnalysis:
        """Convert raw FFprobe JSON into immutable structured media data."""
        streams = data.get("streams", [])
        if not isinstance(streams, list):
            streams = []
        video_raw = next(
            (
                item for item in streams
                if isinstance(item, Mapping) and item.get("codec_type") == "video"
            ),
            None,
        )
        audio_raw = next(
            (
                item for item in streams
                if isinstance(item, Mapping) and item.get("codec_type") == "audio"
            ),
            None,
        )
        format_raw = data.get("format", {})
        if not isinstance(format_raw, Mapping):
            format_raw = {}

        video = _parse_video_stream(video_raw) if video_raw else None
        audio = _parse_audio_stream(audio_raw) if audio_raw else None
        return cls(
            video=video,
            audio=audio,
            format_name=_optional_text(format_raw.get("format_name")),
            duration=_optional_float(format_raw.get("duration")),
            size=_positive_int(format_raw.get("size")),
            raw=data,
        )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _parse_video_stream(stream: Mapping[str, Any]) -> VideoStreamInfo:
    coded_width = _positive_int(stream.get("width"))
    coded_height = _positive_int(stream.get("height"))
    rotation = _parse_rotation(stream)
    width, height = coded_width, coded_height
    if (
        width is not None
        and height is not None
        and rotation is not None
        and abs(round(rotation) % 180) == 90
    ):
        width, height = height, width
    if width is None or height is None:
        orientation = Orientation.UNKNOWN
        aspect_ratio = None
    elif width == height:
        orientation = Orientation.SQUARE
        aspect_ratio = 1.0
    elif width > height:
        orientation = Orientation.LANDSCAPE
        aspect_ratio = width / height
    else:
        orientation = Orientation.PORTRAIT
        aspect_ratio = width / height

    pixel_format = _optional_text(stream.get("pix_fmt"))
    r_frame_rate = _optional_text(stream.get("r_frame_rate"))
    avg_frame_rate = _optional_text(stream.get("avg_frame_rate"))
    frame_rate = parse_frame_rate(r_frame_rate)
    average_frame_rate = parse_frame_rate(avg_frame_rate)
    side_data = stream.get("side_data_list", [])
    hdr_metadata_types = tuple(
        sorted({
            str(item.get("side_data_type")).strip()
            for item in side_data
            if isinstance(item, Mapping)
            and item.get("side_data_type")
            and any(
                term in str(item.get("side_data_type")).lower()
                for term in (
                    "mastering display",
                    "content light",
                    "dolby vision",
                    "dovi",
                )
            )
        })
    ) if isinstance(side_data, (list, tuple)) else ()
    return VideoStreamInfo(
        codec_name=_optional_text(stream.get("codec_name")),
        width=width,
        height=height,
        coded_width=coded_width,
        coded_height=coded_height,
        rotation_degrees=rotation,
        orientation=orientation,
        aspect_ratio=aspect_ratio,
        pixel_format=pixel_format,
        bit_depth=(
            _infer_bit_depth(pixel_format)
            or _positive_int(stream.get("bits_per_raw_sample"))
        ),
        r_frame_rate=r_frame_rate,
        avg_frame_rate=avg_frame_rate,
        frame_rate=frame_rate,
        average_frame_rate=average_frame_rate,
        frame_rate_type=_classify_frame_rate(frame_rate, average_frame_rate),
        color_space=_optional_text(stream.get("color_space")),
        color_transfer=_optional_text(stream.get("color_transfer")),
        color_primaries=_optional_text(stream.get("color_primaries")),
        color_range=_optional_text(stream.get("color_range")),
        hdr_classification=_classify_hdr(stream),
        hdr_metadata_types=hdr_metadata_types,
        duration=_optional_float(stream.get("duration")),
        raw=stream,
    )


def _parse_rotation(stream: Mapping[str, Any]) -> float | None:
    side_data = stream.get("side_data_list", [])
    if isinstance(side_data, (list, tuple)):
        for item in side_data:
            if (
                isinstance(item, Mapping)
                and str(item.get("side_data_type", "")).lower()
                == "display matrix"
            ):
                rotation = _optional_float(item.get("rotation"))
                if rotation is not None:
                    return rotation
                try:
                    rotation = float(item["rotation"])
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
                if rotation == rotation and abs(rotation) != float("inf"):
                    return rotation
    tags = stream.get("tags", {})
    if isinstance(tags, Mapping):
        rotation_tag = tags.get("rotate")
        if not isinstance(rotation_tag, (str, int, float)):
            return None
        try:
            rotation = float(rotation_tag)
        except (TypeError, ValueError, OverflowError):
            return None
        return rotation if rotation == rotation and abs(rotation) != float("inf") else None
    return None


def _parse_audio_stream(stream: Mapping[str, Any]) -> AudioStreamInfo:
    return AudioStreamInfo(
        codec_name=_optional_text(stream.get("codec_name")),
        sample_rate=_positive_int(stream.get("sample_rate")),
        channels=_positive_int(stream.get("channels")),
        channel_layout=_optional_text(stream.get("channel_layout")),
        duration=_optional_float(stream.get("duration")),
        raw=stream,
    )


class MediaInfo:
    """FFprobe client retained under its historical public name.

    ``probe`` now returns :class:`MediaAnalysis`; the mapping-style helpers
    preserve compatibility for existing callers during staged integration.
    """

    def __init__(self, ffprobe_path: str | Path):
        self.ffprobe_path = Path(ffprobe_path)

    def probe(self, input_file: str | Path) -> MediaAnalysis:
        if not self.ffprobe_path.exists():
            logging.warning("FFprobe was not found: %s", self.ffprobe_path)
            return MediaAnalysis()

        command = [
            str(self.ffprobe_path),
            "-v", "error",
            "-show_entries", "format=duration,size,format_name",
            "-show_entries",
            (
                "stream=index,codec_name,codec_type,width,height,"
                "r_frame_rate,avg_frame_rate,pix_fmt,bits_per_raw_sample,"
                "sample_rate,channels,channel_layout,duration,color_space,"
                "color_transfer,color_primaries,color_range,side_data_list,"
                "tags"
            ),
            "-show_entries",
            "stream_side_data=side_data_type,rotation",
            "-of", "json",
            str(input_file),
        ]
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                logging.warning(
                    "FFprobe failed for %s with exit code %s: %s",
                    input_file,
                    result.returncode,
                    result.stderr.strip(),
                )
                return MediaAnalysis()
            data = json.loads(result.stdout)
            if not isinstance(data, Mapping):
                logging.warning("FFprobe returned invalid media JSON for %s", input_file)
                return MediaAnalysis()
            analysis = MediaAnalysis.from_ffprobe(data)
            if analysis.video is None:
                return analysis
            sampled_timestamps = self._sample_video_timestamps(input_file)
            sampled_cadence, sampled_average = _classify_timestamps(
                sampled_timestamps
            )
            if sampled_cadence is FrameRateType.UNKNOWN:
                return analysis
            video = replace(
                analysis.video,
                frame_rate_type=sampled_cadence,
                average_frame_rate=(
                    analysis.video.average_frame_rate or sampled_average
                ),
            )
            return replace(analysis, video=video)
        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
        ) as error:
            logging.warning("Could not probe media file %s: %s", input_file, error)
            return MediaAnalysis()

    def _sample_video_timestamps(self, input_file: str | Path) -> list[float]:
        """Inspect a bounded initial packet window for variable timestamp gaps."""
        command = [
            str(self.ffprobe_path),
            "-v", "error",
            "-read_intervals", "0%+3",
            "-select_streams", "v:0",
            "-show_packets",
            "-show_entries", "packet=pts_time",
            "-of", "csv=p=0",
            str(input_file),
        ]
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            logging.debug(
                "Could not sample packet cadence for %s: %s",
                input_file,
                error,
            )
            return []
        if result.returncode != 0:
            logging.debug(
                "Could not sample packet cadence for %s: %s",
                input_file,
                result.stderr.strip(),
            )
            return []
        timestamps = []
        for line in result.stdout.splitlines():
            try:
                timestamp = float(line.split(",", 1)[0].strip())
            except (TypeError, ValueError, IndexError):
                continue
            if timestamp == timestamp and abs(timestamp) != float("inf"):
                timestamps.append(timestamp)
        return timestamps

    @staticmethod
    def video_stream(info: MediaAnalysis | Mapping[str, Any]) -> VideoStreamInfo | Mapping[str, Any]:
        if isinstance(info, MediaAnalysis):
            return info.video or VideoStreamInfo()
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                return stream
        return {}

    @staticmethod
    def audio_stream(info: MediaAnalysis | Mapping[str, Any]) -> AudioStreamInfo | Mapping[str, Any]:
        if isinstance(info, MediaAnalysis):
            return info.audio or AudioStreamInfo()
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "audio":
                return stream
        return {}

    @staticmethod
    def format_name(info: MediaAnalysis | Mapping[str, Any]) -> str:
        if isinstance(info, MediaAnalysis):
            return info.format_name or "Unknown"
        return info.get("format", {}).get("format_name", "Unknown")

    @staticmethod
    def duration(info: MediaAnalysis | Mapping[str, Any]) -> float:
        value = (
            info.duration
            if isinstance(info, MediaAnalysis)
            else info.get("format", {}).get("duration", 0)
        )
        try:
            return float(value or 0)
        except (TypeError, ValueError, OverflowError):
            return 0.0
