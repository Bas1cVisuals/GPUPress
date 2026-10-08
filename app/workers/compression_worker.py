from pathlib import Path
import re
import uuid

from PySide6.QtCore import QThread, Signal

from app.core.encoding_plan import (
    EncodingPlan,
    EncodingStrategyError,
    HardwareCapabilities,
    HDRMode,
    UserEncodingOptions,
    create_encoding_plan,
    resolve_encoding_pipelines,
)
from app.core.ffmpeg import (
    CommandGenerationError,
    EncodingPipeline,
    FFmpegEngine,
)
from app.core.hardware import HardwareInfo
from app.core.media import MediaAnalysis, MediaInfo
from app.core.presets import CompressionPreset


class CompressionWorker(QThread):

    # =========================================================
    # SIGNALS
    # =========================================================

    progress_changed = Signal(int)
    status_changed = Signal(str)
    log_message = Signal(str)

    compression_finished = Signal(str)
    compression_failed = Signal(str)
    compression_cancelled = Signal()

    stats_changed = Signal(dict)

    # =========================================================
    # INIT
    # =========================================================

    def __init__(
        self,
        input_file,
        output_file,
        preset,
        use_gpu=True,
        allow_cpu_fallback=True,
        overwrite_existing=False,
        hardware=None,
        media_analysis=None,
        parent=None,
    ):
        super().__init__(parent)

        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.working_output_file = self._make_working_output_path(
            self.output_file
        )

        self.preset = preset

        self.use_gpu = bool(use_gpu)
        self.allow_cpu_fallback = bool(
            allow_cpu_fallback
        )
        self.overwrite_existing = bool(
            overwrite_existing
        )

        self.cancel_requested = False
        self._output_may_be_removed = False

        self.process_holder = {}

        # -----------------------------------------------------
        # HARDWARE / FFMPEG
        # -----------------------------------------------------

        self.hardware = (
            hardware
            if hardware is not None
            else HardwareInfo()
        )

        if not self.hardware.ffmpeg_exists:
            raise FileNotFoundError(
                "FFmpeg was not found.\n\n"
                f"Expected path:\n"
                f"{self.hardware.ffmpeg_path}"
            )

        self.ffmpeg = FFmpegEngine(
            self.hardware.ffmpeg_path
        )

        # -----------------------------------------------------
        # MEDIA / PROGRESS DATA
        # -----------------------------------------------------

        self.duration_seconds = 0.0
        self.input_size_bytes = 0
        self.media_analysis: MediaAnalysis | None = media_analysis
        self.encoding_plan: EncodingPlan | None = (
            preset if isinstance(preset, EncodingPlan) else None
        )
        self.hardware_capabilities = (
            self.hardware.get_capabilities()
            if hasattr(self.hardware, "get_capabilities")
            else None
        )
        self._last_pipeline_error = ""
        self._output_validation_error = ""
        self.output_analysis: MediaAnalysis | None = None

        self.current_seconds = 0.0
        self.current_frame = 0
        self.current_fps = 0.0
        self.current_speed = 0.0
        self.current_bitrate = ""

    @staticmethod
    def _make_working_output_path(output_file):
        output_file = Path(output_file)
        return output_file.with_name(
            f".gpupress-{uuid.uuid4().hex}.partial{output_file.suffix}"
        )

    def _set_output_container(self, plan):
        """Match target suffix to the resolved preset container."""
        suffix = f".{plan.container.lower().lstrip('.')}"
        if self.output_file.suffix.lower() != suffix:
            self.output_file = self.output_file.with_suffix(suffix)
            if not self.overwrite_existing:
                base = self.output_file
                index = 1
                while self.output_file.exists():
                    self.output_file = base.with_name(
                        f"{base.stem}_{index}{base.suffix}"
                    )
                    index += 1
            self.working_output_file = self._make_working_output_path(
                self.output_file
            )

    def _resolve_plan(self) -> EncodingPlan:
        if isinstance(self.preset, EncodingPlan):
            return self.preset
        media_analysis = self.media_analysis
        if media_analysis is None:
            raise ValueError(
                "Cannot create an encoding plan without successful media analysis."
            )
        if isinstance(self.preset, UserEncodingOptions):
            return create_encoding_plan(
                media_analysis,
                self.preset,
                self.hardware_capabilities or HardwareCapabilities(),
            )
        if not isinstance(self.preset, CompressionPreset):
            raise ValueError("The selected preset does not provide encoding intent.")
        options = self.preset.to_legacy_worker_options(
            use_gpu=self.use_gpu,
            allow_cpu_fallback=self.allow_cpu_fallback,
        )
        return create_encoding_plan(
            media_analysis,
            options,
            self.hardware_capabilities or HardwareCapabilities(),
        )

    # =========================================================
    # CANCEL
    # =========================================================

    def cancel(self):

        self.cancel_requested = True

        self.status_changed.emit(
            "Cancelling..."
        )

        self.log_message.emit(
            "[CANCEL] Cancellation requested."
        )

        process = self.process_holder.get(
            "process"
        )

        if process is not None:

            try:
                FFmpegEngine.terminate(
                    process
                )
            except (OSError, RuntimeError, ValueError) as error:
                self.log_message.emit(
                    "[ERROR] Could not terminate FFmpeg: "
                    f"{error}"
                )

    # =========================================================
    # OUTPUT CLEANUP
    # =========================================================

    def cleanup_output(self):

        if not self._output_may_be_removed:
            return

        try:

            if self.working_output_file.exists():

                self.working_output_file.unlink()

            self._output_may_be_removed = False

        except Exception as error:

            self.log_message.emit(
                "[WARNING] Could not remove "
                f"incomplete output: {error}"
            )

    # =========================================================
    # OUTPUT VALIDATION
    # =========================================================

    def validate_output(self):

        self._output_validation_error = (
            "Output validation failed: output file is missing or empty."
        )
        plan = self.encoding_plan
        if plan is None:
            self._output_validation_error = (
                "Output validation failed: encoding plan is unavailable."
            )
            return False
        if not self.working_output_file.is_file():
            return False

        try:
            size = (
                self.working_output_file
                .stat()
                .st_size
            )

            if size <= 0:
                return False

            ffprobe_path = (
                Path(self.hardware.ffmpeg_path).parent
                / "ffprobe.exe"
            )
            analyzed = MediaInfo(ffprobe_path).probe(
                self.working_output_file
            )
            if not analyzed or analyzed.video is None:
                self._output_validation_error = (
                    "FFprobe could not find a valid video stream in the output."
                )
                return False
            if (
                analyzed.video.width is None
                or analyzed.video.height is None
            ):
                self._output_validation_error = (
                    "FFprobe output is missing valid video dimensions."
                )
                return False
            if (
                analyzed.video.width != plan.output_width
                or analyzed.video.height != plan.output_height
            ):
                self._output_validation_error = (
                    "Output dimensions do not match the resolved plan: "
                    f"expected {plan.output_width}x{plan.output_height}, got "
                    f"{analyzed.video.width}x{analyzed.video.height}."
                )
                return False
            supported_container_formats = {
                "mp4": {"mp4", "mov"},
                "m4v": {"mp4", "mov"},
                "mov": {"mp4", "mov"},
                "mkv": {"matroska"},
            }
            expected_formats = supported_container_formats.get(
                plan.container.lower().lstrip(".")
            )
            if expected_formats is None:
                self._output_validation_error = (
                    "Output container is not supported for validation: "
                    f"{plan.container}."
                )
                return False
            if analyzed.format_name:
                actual_formats = {
                    value.strip().lower()
                    for value in analyzed.format_name.split(",")
                }
                if not actual_formats.intersection(expected_formats):
                    self._output_validation_error = (
                        "Output container does not match the resolved plan: "
                        f"expected {plan.container}, got "
                        f"{analyzed.format_name}."
                    )
                    return False
            expected_video_codec = {
                "h264": "h264",
                "hevc": "hevc",
                "av1": "av1",
                "prores_proxy": "prores",
                "prores_lt": "prores",
                "prores_422": "prores",
                "dnxhr_lb": "dnxhd",
                "dnxhr_sq": "dnxhd",
                "dnxhr_hq": "dnxhd",
            }.get(plan.codec.value)
            if (
                expected_video_codec
                and analyzed.video.codec_name != expected_video_codec
            ):
                self._output_validation_error = (
                    "Output video codec does not match the resolved plan: "
                    f"expected {expected_video_codec}, got "
                    f"{analyzed.video.codec_name}."
                )
                return False
            if self.media_analysis and self.media_analysis.audio:
                if not analyzed.audio:
                    self._output_validation_error = (
                        "The source contains audio, but the output has no audio stream."
                    )
                    return False
                if plan.audio_mode.value == "copy":
                    source_audio_codec = self.media_analysis.audio.codec_name
                    if (
                        source_audio_codec
                        and analyzed.audio.codec_name != source_audio_codec
                    ):
                        self._output_validation_error = (
                            "Audio copy was requested, but output audio codec "
                            f"changed from {source_audio_codec} to "
                            f"{analyzed.audio.codec_name}."
                        )
                        return False
                elif plan.audio_mode.value == "aac":
                    if analyzed.audio.codec_name != "aac":
                        self._output_validation_error = (
                            "AAC audio was requested, but FFprobe found "
                            f"{analyzed.audio.codec_name}."
                        )
                        return False
                    if (
                        plan.sample_rate
                        and analyzed.audio.sample_rate != plan.sample_rate
                    ):
                        self._output_validation_error = (
                            "Output audio sample rate does not match the plan."
                        )
                        return False
                    if (
                        plan.channel_count
                        and analyzed.audio.channels != plan.channel_count
                    ):
                        self._output_validation_error = (
                            "Output audio channel count does not match the plan."
                        )
                        return False
            if plan.resolved_fps and analyzed.video.frame_rate:
                if abs(analyzed.video.frame_rate - plan.resolved_fps) > 0.1:
                    self._output_validation_error = (
                        "Output frame rate does not match the resolved plan: "
                        f"expected {plan.resolved_fps:.3f}, got "
                        f"{analyzed.video.frame_rate:.3f}."
                    )
                    return False
            if (
                self.media_analysis
                and self.media_analysis.video
                and self.media_analysis.duration
                and analyzed.duration
            ):
                tolerance = max(2.0, self.media_analysis.duration * 0.05)
                if abs(analyzed.duration - self.media_analysis.duration) > tolerance:
                    self._output_validation_error = (
                        "Output duration differs significantly from source "
                        f"({analyzed.duration:.2f}s vs "
                        f"{self.media_analysis.duration:.2f}s)."
                    )
                    return False
            if not self._validate_hdr_output(analyzed):
                return False
            self.output_analysis = analyzed
        except (OSError, ValueError, TypeError) as error:
            self._output_validation_error = f"FFprobe validation failed: {error}"
            return False

        self._output_validation_error = ""
        return True

    def _validate_hdr_output(self, analyzed):
        plan = self.encoding_plan
        if (
            plan is None
            or plan.hdr_mode is not HDRMode.PRESERVE
            or plan.source_hdr_classification.value
            not in {"hlg", "pq", "hdr_unknown"}
        ):
            return True
        output = analyzed.video
        if output.bit_depth is None or output.bit_depth < 10:
            self._output_validation_error = (
                "HDR preservation failed: output is not at least 10-bit."
            )
            return False
        for name, expected, actual in (
            ("color primaries", plan.source_color_primaries, output.color_primaries),
            ("transfer", plan.source_color_transfer, output.color_transfer),
            ("colorspace", plan.source_color_space, output.color_space),
        ):
            if expected and actual and expected.lower() != actual.lower():
                self._output_validation_error = (
                    f"HDR preservation failed: {name} changed from "
                    f"{expected} to {actual}."
                )
                return False
        if plan.source_hdr_classification.value in {"hlg", "pq"}:
            if output.hdr_classification.value != plan.source_hdr_classification.value:
                self._output_validation_error = (
                    "HDR preservation failed: output HDR transfer classification "
                    "does not match the source."
                )
                return False
        output_side_data = {
            value.lower() for value in output.hdr_metadata_types
        }
        missing_side_data = {
            value.lower() for value in plan.source_hdr_metadata_types
        } - output_side_data
        if missing_side_data:
            self._output_validation_error = (
                "HDR preservation failed: FFprobe no longer reports source HDR "
                "metadata: " + ", ".join(sorted(missing_side_data))
            )
            return False
        return True

    # =========================================================
    # COMMAND DISPLAY
    # =========================================================

    @staticmethod
    def command_to_text(command):

        parts = []

        for part in command:

            part = str(part)

            if (
                " " in part
                or "\t" in part
            ):

                parts.append(
                    f'"{part}"'
                )

            else:

                parts.append(part)

        return " ".join(parts)

    # =========================================================
    # TIME PARSER
    # =========================================================

    @staticmethod
    def parse_time_value(value):

        if not value:
            return 0.0

        value = str(value).strip()

        try:

            if ":" in value:

                parts = value.split(":")

                if len(parts) == 3:

                    hours = float(parts[0])
                    minutes = float(parts[1])
                    seconds = float(parts[2])

                    return (
                        hours * 3600
                        + minutes * 60
                        + seconds
                    )

            return float(value)

        except Exception:

            return 0.0

    # =========================================================
    # FPS PARSER
    # =========================================================

    @staticmethod
    def parse_fps(value):

        if not value:
            return 0.0

        value = str(value).strip()

        try:

            return float(
                value
                .replace("fps", "")
                .strip()
            )

        except Exception:

            return 0.0

    # =========================================================
    # SPEED PARSER
    # =========================================================

    @staticmethod
    def parse_speed(value):

        if not value:
            return 0.0

        value = str(value).strip()

        try:

            return float(
                value
                .replace("x", "")
                .strip()
            )

        except Exception:

            return 0.0

    # =========================================================
    # PROGRESS PARSER
    # =========================================================

    @staticmethod
    def parse_progress(
        line,
        duration_seconds,
    ):

        if not line:
            return None

        # -----------------------------------------------------
        # FFmpeg -progress output
        # -----------------------------------------------------

        match = re.search(
            r"out_time_(?:ms|us)=(\d+)",
            line,
        )

        if match:

            try:

                value = int(
                    match.group(1)
                )

                current_seconds = (
                    value / 1_000_000
                )

                if (
                    duration_seconds
                    and duration_seconds > 0
                ):

                    percent = (
                        current_seconds
                        / duration_seconds
                    ) * 100

                    return max(
                        0,
                        min(
                            100,
                            int(percent),
                        ),
                    )

            except Exception:
                pass

        # -----------------------------------------------------
        # Standard FFmpeg time= output
        # -----------------------------------------------------

        match = re.search(
            r"time=(\d+):(\d+):(\d+(?:\.\d+)?)",
            line,
        )

        if match:

            try:

                hours = int(
                    match.group(1)
                )

                minutes = int(
                    match.group(2)
                )

                seconds = float(
                    match.group(3)
                )

                current_seconds = (
                    hours * 3600
                    + minutes * 60
                    + seconds
                )

                if (
                    duration_seconds
                    and duration_seconds > 0
                ):

                    percent = (
                        current_seconds
                        / duration_seconds
                    ) * 100

                    return max(
                        0,
                        min(
                            100,
                            int(percent),
                        ),
                    )

            except Exception:
                pass

        return None

    # =========================================================
    # LIVE STATS PARSER
    # =========================================================

    def parse_live_stats(self, line):

        if not line:
            return None

        stats = {}

        # -----------------------------------------------------
        # FRAME
        # -----------------------------------------------------

        match = re.search(
            r"\bframe=\s*(\d+)",
            line,
        )

        if match:

            try:

                self.current_frame = int(
                    match.group(1)
                )

                stats["frame"] = (
                    self.current_frame
                )

            except Exception:
                pass

        # -----------------------------------------------------
        # FPS
        # -----------------------------------------------------

        match = re.search(
            r"\bfps=\s*([0-9.]+)",
            line,
        )

        if match:

            try:

                self.current_fps = float(
                    match.group(1)
                )

                stats["fps"] = (
                    self.current_fps
                )

            except Exception:
                pass

        # -----------------------------------------------------
        # BITRATE
        # -----------------------------------------------------

        match = re.search(
            r"\bbitrate=\s*([^\s]+)",
            line,
        )

        if match:

            self.current_bitrate = (
                match.group(1)
            )

            stats["bitrate"] = (
                self.current_bitrate
            )

        # -----------------------------------------------------
        # TIME
        # -----------------------------------------------------

        match = re.search(
            r"\btime=\s*([0-9:.]+)",
            line,
        )

        if match:

            self.current_seconds = (
                self.parse_time_value(
                    match.group(1)
                )
            )

            stats["time"] = (
                self.current_seconds
            )

        # -----------------------------------------------------
        # SPEED
        # -----------------------------------------------------

        match = re.search(
            r"\bspeed=\s*([0-9.]+)x",
            line,
        )

        if match:

            try:

                self.current_speed = float(
                    match.group(1)
                )

                stats["speed"] = (
                    self.current_speed
                )

            except Exception:
                pass

        # -----------------------------------------------------
        # PROGRESS
        # -----------------------------------------------------

        progress = self.parse_progress(
            line,
            self.duration_seconds,
        )

        if progress is not None:

            stats["progress"] = progress

        # -----------------------------------------------------
        # ETA
        # -----------------------------------------------------

        if (
            self.current_speed > 0
            and self.duration_seconds > 0
            and self.current_seconds >= 0
        ):

            remaining_seconds = max(
                0,
                self.duration_seconds
                - self.current_seconds,
            )

            eta_seconds = (
                remaining_seconds
                / self.current_speed
            )

            stats["eta"] = eta_seconds

        if not stats:
            return None

        stats["duration"] = (
            self.duration_seconds
        )

        return stats

    # =========================================================
    # INITIAL MEDIA DATA
    # =========================================================

    def read_input_metadata(self):
        """Probe full input media once; retain the old method name."""
        self.duration_seconds = 0.0
        self.input_size_bytes = 0
        try:
            source_size = self.input_file.stat().st_size
            if (
                self.media_analysis is None
                or not self.media_analysis
                or (
                    self.media_analysis.size is not None
                    and self.media_analysis.size != source_size
                )
            ):
                ffprobe_path = (
                    Path(self.hardware.ffmpeg_path).parent / "ffprobe.exe"
                )
                self.media_analysis = MediaInfo(ffprobe_path).probe(
                    self.input_file
                )
            if not self.media_analysis:
                raise ValueError(
                    f"FFprobe could not analyze input media: {self.input_file}"
                )
            self.duration_seconds = self.media_analysis.duration or 0.0
            self.input_size_bytes = (
                self.media_analysis.size
                or source_size
            )
            return self.media_analysis
        except (OSError, ValueError, TypeError) as error:
            self.log_message.emit(
                f"[ERROR] Could not analyze input media: {error}"
            )
            raise

    # =========================================================
    # FINAL STATS
    # =========================================================

    def emit_final_stats(self):

        output_size = 0

        try:

            if self.output_file.exists():

                output_size = (
                    self.output_file
                    .stat()
                    .st_size
                )

        except Exception:

            output_size = 0

        saved_bytes = 0
        reduction_percent = 0.0

        if (
            self.input_size_bytes > 0
            and output_size > 0
        ):

            saved_bytes = max(
                0,
                self.input_size_bytes
                - output_size,
            )

            reduction_percent = (
                saved_bytes
                / self.input_size_bytes
            ) * 100

        self.stats_changed.emit({

            "frame":
                self.current_frame,

            "fps":
                self.current_fps,

            "speed":
                self.current_speed,

            "time":
                self.current_seconds,

            "duration":
                self.duration_seconds,

            "eta":
                0.0,

            "progress":
                100,

            "bitrate":
                self.current_bitrate,

            "input_size":
                self.input_size_bytes,

            "output_size":
                output_size,

            "saved_bytes":
                saved_bytes,

            "reduction_percent":
                reduction_percent,
        })

    # =========================================================
    # RUN PIPELINE
    # =========================================================

    def run_pipeline(
        self,
        pipeline_name,
        command,
        duration_seconds,
    ):

        if self.cancel_requested:
            return False

        self.status_changed.emit(
            pipeline_name
        )

        self.log_message.emit("")
        self.log_message.emit(
            "=" * 70
        )

        self.log_message.emit(
            f"[ENGINE] {pipeline_name}"
        )

        self.log_message.emit(
            "=" * 70
        )

        self.log_message.emit(
            self.command_to_text(command)
        )

        self.log_message.emit("")

        last_progress = -1

        self.duration_seconds = (
            duration_seconds
        )

        def handle_output(line):

            nonlocal last_progress

            if self.cancel_requested:
                return

            self.log_message.emit(
                line
            )

            # -------------------------------------------------
            # LIVE STATS
            # -------------------------------------------------

            stats = (
                self.parse_live_stats(
                    line
                )
            )

            if stats:

                self.stats_changed.emit(
                    stats
                )

            # -------------------------------------------------
            # PROGRESS
            # -------------------------------------------------

            progress = (
                self.parse_progress(
                    line,
                    duration_seconds,
                )
            )

            if (
                progress is not None
                and progress != last_progress
            ):

                last_progress = progress

                self.progress_changed.emit(
                    progress
                )

        try:

            return_code = self.ffmpeg.run(

                command,

                on_output=handle_output,

                process_holder=(
                    self.process_holder
                ),
            )

        except Exception as error:

            self.log_message.emit(
                "[ERROR] FFmpeg process error: "
                f"{error}"
            )
            self._last_pipeline_error = str(error)
            self.cleanup_output()

            return False

        if self.cancel_requested:

            self.log_message.emit(
                "[CANCEL] Compression cancelled."
            )

            self.cleanup_output()

            return False

        if return_code == 0 and self.validate_output():

            try:
                if self.overwrite_existing:
                    self.working_output_file.replace(
                        self.output_file
                    )
                else:
                    self.working_output_file.rename(
                        self.output_file
                    )

                self._output_may_be_removed = False

            except OSError as error:
                self.log_message.emit(
                    "[ERROR] Could not finalize output file: "
                    f"{error}"
                )
                self.cleanup_output()
                return False

            self.progress_changed.emit(
                100
            )

            self.emit_final_stats()

            self.log_message.emit("")

            self.log_message.emit(
                "[OK] Output created successfully."
            )

            return True

        if return_code == 0:
            self._last_pipeline_error = (
                self._output_validation_error
                or "FFmpeg exited successfully but the output failed validation."
            )
            self.log_message.emit(
                f"[ERROR] {self._last_pipeline_error}"
            )
            self.cleanup_output()
            return False

        self.log_message.emit("")

        self.log_message.emit(
            "[ERROR] FFmpeg exited with "
            f"code {return_code}."
        )
        self._last_pipeline_error = (
            f"FFmpeg exited with code {return_code}."
        )

        self.cleanup_output()

        return False

    # =========================================================
    # MAIN THREAD RUN
    # =========================================================

    def run(self):

        self.current_seconds = 0.0
        self.current_frame = 0
        self.current_fps = 0.0
        self.current_speed = 0.0
        self.current_bitrate = ""

        self.progress_changed.emit(0)

        self.status_changed.emit("Analyzing...")

        if self.cancel_requested:
            self.compression_cancelled.emit()
            return

        # -----------------------------------------------------
        # INPUT CHECK
        # -----------------------------------------------------

        if not self.input_file.exists():

            self.compression_failed.emit(
                "Input file not found:\n"
                f"{self.input_file}"
            )

            return

        try:
            self.read_input_metadata()
            plan = self._resolve_plan()
            self.encoding_plan = plan
            self._set_output_container(plan)

            if self.input_file.resolve() == self.output_file.resolve():
                raise ValueError("Output file must not be the input file.")
            if self.output_file.exists() and not self.overwrite_existing:
                raise FileExistsError(
                    f"Output file already exists:\n{self.output_file}"
                )

            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            self._output_may_be_removed = True
            duration_seconds = self.duration_seconds
            self.stats_changed.emit({
                "frame": 0,
                "fps": 0.0,
                "speed": 0.0,
                "time": 0.0,
                "duration": duration_seconds,
                "eta": duration_seconds,
                "progress": 0,
                "bitrate": "",
                "input_size": self.input_size_bytes,
                "output_size": 0,
                "saved_bytes": 0,
                "reduction_percent": 0.0,
            })
        except (OSError, RuntimeError, ValueError, TypeError) as error:
            self.cleanup_output()
            self.compression_failed.emit(str(error))
            return

        capabilities = self.hardware_capabilities or HardwareCapabilities()
        try:
            candidates = resolve_encoding_pipelines(plan, capabilities)
        except EncodingStrategyError as error:
            self.compression_failed.emit(str(error))
            return

        for pipeline in candidates:
            if self.cancel_requested:
                self.cleanup_output()
                self.compression_cancelled.emit()
                return

            try:
                command = self.ffmpeg.build_plan_command(
                    self.input_file,
                    self.working_output_file,
                    plan,
                    pipeline=pipeline,
                    capabilities=capabilities,
                    overwrite=self.overwrite_existing,
                )
            except CommandGenerationError as error:
                self._last_pipeline_error = str(error)
                self.log_message.emit(f"[ERROR] {error}")
                continue

            pipeline_label = {
                EncodingPipeline.GPU: "GPU: NVDEC + CUDA SCALE + NVENC",
                EncodingPipeline.NVENC: "CPU DECODE + NVENC",
                EncodingPipeline.CPU: f"CPU: {plan.codec.value}",
            }[pipeline]
            if self.run_pipeline(
                pipeline_label,
                command,
                self.duration_seconds,
            ):
                if self.cancel_requested:
                    self.cleanup_output()
                    self.compression_cancelled.emit()
                    return
                self.compression_finished.emit(str(self.output_file))
                return
            if self.cancel_requested:
                self.cleanup_output()
                self.compression_cancelled.emit()
                return
            self.cleanup_output()

        self.cleanup_output()
        reason = self._last_pipeline_error or (
            "All permitted encoding pipelines failed."
        )
        self.compression_failed.emit(
            f"Encoding failed for {plan.codec.value}: {reason}"
        )