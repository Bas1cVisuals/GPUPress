from pathlib import Path
import json
import re
import subprocess
import uuid

from PySide6.QtCore import QThread, Signal

from app.core.ffmpeg import FFmpegEngine
from app.core.hardware import HardwareInfo


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
        parent=None,
    ):
        super().__init__(parent)

        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.working_output_file = (
            self.output_file.with_name(
                f".gpupress-{uuid.uuid4().hex}.partial"
                f"{self.output_file.suffix}"
            )
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

        self.current_seconds = 0.0
        self.current_frame = 0
        self.current_fps = 0.0
        self.current_speed = 0.0
        self.current_bitrate = ""

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

        if not self.working_output_file.exists():
            return False

        try:

            size = (
                self.working_output_file
                .stat()
                .st_size
            )

            if size < 1024:
                return False

        except Exception:

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

        self.duration_seconds = 0.0
        self.input_size_bytes = 0

        # -----------------------------------------------------
        # FILE SIZE
        # -----------------------------------------------------

        try:

            if self.input_file.exists():

                self.input_size_bytes = (
                    self.input_file
                    .stat()
                    .st_size
                )

        except Exception:

            self.input_size_bytes = 0

        # -----------------------------------------------------
        # FFPROBE
        # -----------------------------------------------------

        try:

            ffprobe_path = (
                Path(
                    self.hardware.ffmpeg_path
                ).parent
                / "ffprobe.exe"
            )

            if not ffprobe_path.exists():

                self.log_message.emit(
                    "[WARNING] ffprobe.exe not found:\n"
                    f"{ffprobe_path}"
                )

                return

            probe_command = [

                str(ffprobe_path),

                "-v",
                "error",

                "-show_entries",
                "format=duration,size",

                "-of",
                "json",

                str(self.input_file),
            ]

            creation_flags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )

            result = subprocess.run(

                probe_command,

                stdout=subprocess.PIPE,

                stderr=subprocess.PIPE,

                text=True,

                encoding="utf-8",

                errors="replace",

                creationflags=creation_flags,
            )

            if result.returncode != 0:
                return

            data = json.loads(
                result.stdout
            )

            format_data = data.get(
                "format",
                {}
            )

            # -------------------------------------------------
            # DURATION
            # -------------------------------------------------

            try:

                self.duration_seconds = float(
                    format_data.get(
                        "duration",
                        0,
                    )
                )

            except Exception:

                self.duration_seconds = 0.0

            # -------------------------------------------------
            # FILE SIZE
            # -------------------------------------------------

            try:

                probed_size = int(
                    float(
                        format_data.get(
                            "size",
                            0,
                        )
                    )
                )

                if probed_size > 0:

                    self.input_size_bytes = (
                        probed_size
                    )

            except Exception:
                pass

        except Exception as error:

            self.log_message.emit(
                "[WARNING] Could not read "
                f"media metadata: {error}"
            )

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

            return False

        if self.cancel_requested:

            self.log_message.emit(
                "[CANCEL] Compression cancelled."
            )

            self.cleanup_output()

            return False

        if (
            return_code == 0
            and self.validate_output()
        ):

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

        self.log_message.emit("")

        self.log_message.emit(
            "[ERROR] FFmpeg exited with "
            f"code {return_code}."
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

        self.status_changed.emit(
            "Preparing..."
        )

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

        # -----------------------------------------------------
        # OUTPUT SAFETY
        # -----------------------------------------------------

        try:

            if (
                self.input_file.resolve()
                == self.output_file.resolve()
            ):
                self.compression_failed.emit(
                    "Output file must not be the input file."
                )
                return

            if self.output_file.exists():

                if not self.overwrite_existing:
                    self.compression_failed.emit(
                        "Output file already exists:\n"
                        f"{self.output_file}"
                    )
                    return

            self._output_may_be_removed = True

        except (OSError, RuntimeError, ValueError) as error:

            self.compression_failed.emit(
                "Could not prepare output file:\n"
                f"{error}"
            )
            return

        # -----------------------------------------------------
        # OUTPUT FOLDER
        # -----------------------------------------------------

        try:

            self.output_file.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

        except (OSError, ValueError) as error:

            self.compression_failed.emit(
                "Could not create output folder:\n"
                f"{error}"
            )

            return

        # -----------------------------------------------------
        # READ MEDIA INFO
        # -----------------------------------------------------

        self.read_input_metadata()

        duration_seconds = (
            self.duration_seconds
        )

        self.stats_changed.emit({

            "frame": 0,

            "fps": 0.0,

            "speed": 0.0,

            "time": 0.0,

            "duration":
                duration_seconds,

            "eta":
                duration_seconds,

            "progress": 0,

            "bitrate": "",

            "input_size":
                self.input_size_bytes,

            "output_size": 0,

            "saved_bytes": 0,

            "reduction_percent": 0.0,
        })

        # =====================================================
        # GPU MODE
        # =====================================================

        if self.use_gpu:

            # -------------------------------------------------
            # GPU: NVDEC + CUDA SCALE + NVENC
            # -------------------------------------------------

            gpu_command = (
                self.ffmpeg
                .build_gpu_command(
                    self.input_file,
                    self.working_output_file,
                    self.preset,
                    self.overwrite_existing,
                )
            )

            gpu_success = (
                self.run_pipeline(
                    "GPU: NVDEC + CUDA SCALE + NVENC",
                    gpu_command,
                    duration_seconds,
                )
            )

            if gpu_success:

                self.compression_finished.emit(
                    str(
                        self.output_file
                    )
                )

                return

            if self.cancel_requested:
                self.compression_cancelled.emit()
                return

            if not self.allow_cpu_fallback:

                self.compression_failed.emit(
                    "GPU compression failed and "
                    "CPU fallback is disabled."
                )

                return

            self.log_message.emit("")

            self.log_message.emit(
                "[FALLBACK] GPU pipeline failed."
            )

            self.log_message.emit(
                "[FALLBACK] Trying CPU decode + NVENC..."
            )

            # -------------------------------------------------
            # CPU DECODE + NVENC
            # -------------------------------------------------

            self.cleanup_output()

            nvenc_command = (
                self.ffmpeg
                .build_nvenc_fallback_command(
                    self.input_file,
                    self.working_output_file,
                    self.preset,
                    self.overwrite_existing,
                )
            )

            nvenc_success = (
                self.run_pipeline(
                    "FALLBACK: CPU DECODE + NVENC",
                    nvenc_command,
                    duration_seconds,
                )
            )

            if nvenc_success:

                self.compression_finished.emit(
                    str(
                        self.output_file
                    )
                )

                return

            if self.cancel_requested:
                self.compression_cancelled.emit()
                return

            if not self.allow_cpu_fallback:

                self.compression_failed.emit(
                    "NVENC fallback failed."
                )

                return

            self.log_message.emit("")

            self.log_message.emit(
                "[FALLBACK] NVENC pipeline failed."
            )

            self.log_message.emit(
                "[FALLBACK] Trying CPU x264..."
            )

        # =====================================================
        # CPU X264
        # =====================================================

        if (
            not self.use_gpu
            or self.allow_cpu_fallback
        ):

            self.cleanup_output()

            cpu_command = (
                self.ffmpeg
                .build_cpu_command(
                    self.input_file,
                    self.working_output_file,
                    self.preset,
                    self.overwrite_existing,
                )
            )

            cpu_success = (
                self.run_pipeline(
                    "CPU: x264"
                    if not self.use_gpu
                    else "FALLBACK: CPU DECODE + x264",
                    cpu_command,
                    duration_seconds,
                )
            )

            if cpu_success:

                self.compression_finished.emit(
                    str(
                        self.output_file
                    )
                )

                return

            if self.cancel_requested:
                self.compression_cancelled.emit()
                return

        # =====================================================
        # FINAL FAILURE
        # =====================================================

        self.cleanup_output()

        self.compression_failed.emit(
            "Compression failed on all available "
            "encoding pipelines."
        )