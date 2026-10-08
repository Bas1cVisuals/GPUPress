from pathlib import Path
import subprocess

from app.core.encoding_plan import (
    AudioMode,
    Codec,
    EncodingPlan,
    FPSMode,
    HDRMode,
    HardwareCapabilities,
    RateControl,
)


class CommandGenerationError(ValueError):
    """Raised when a plan cannot be expressed by the selected FFmpeg path."""


class EncodingPipeline(str):
    """Named plan-driven pipeline choices accepted by the command builder."""

    GPU = "gpu"
    NVENC = "nvenc"
    CPU = "cpu"


class FFmpegEngine:

    def __init__(self, ffmpeg_path):

        self.ffmpeg_path = Path(ffmpeg_path)

        if not self.ffmpeg_path.exists():
            raise FileNotFoundError(
                f"FFmpeg not found:\n{self.ffmpeg_path}"
            )

    # ---------------------------------------------------------
    # PLAN-DRIVEN COMMAND GENERATION
    # ---------------------------------------------------------

    @staticmethod
    def _has_encoder(capabilities, encoder):
        if encoder in capabilities.available_encoders:
            return True
        encoder_flags = {
            "h264_nvenc": capabilities.h264_nvenc,
            "hevc_nvenc": capabilities.hevc_nvenc,
            "av1_nvenc": capabilities.av1_nvenc,
        }
        return encoder_flags.get(encoder, False)

    @staticmethod
    def _require_encoder(capabilities, encoder):
        if not FFmpegEngine._has_encoder(capabilities, encoder):
            raise CommandGenerationError(
                f"Required FFmpeg encoder is unavailable: {encoder}"
            )

    @staticmethod
    def _fps_text(value):
        if value is None or value <= 0:
            raise CommandGenerationError(
                "CFR output requires a positive resolved frame rate."
            )
        return f"{value:.8f}".rstrip("0").rstrip(".")

    @staticmethod
    def _scale_filter(plan, cuda=False):
        if plan.output_width <= 0 or plan.output_height <= 0:
            raise CommandGenerationError(
                "Resolved output dimensions must be positive."
            )
        if (
            plan.require_even_dimensions
            and (plan.output_width % 2 or plan.output_height % 2)
        ):
            raise CommandGenerationError(
                "The resolved output dimensions must be even for this plan."
            )
        filter_name = "scale_cuda" if cuda else "scale"
        options = (
            f"w={plan.output_width}:h={plan.output_height}"
        )
        if cuda:
            return f"{filter_name}={options}"
        return f"{filter_name}={options}:flags=lanczos"

    @staticmethod
    def _nvenc_encoder(codec):
        return {
            Codec.H264: "h264_nvenc",
            Codec.HEVC: "hevc_nvenc",
            Codec.AV1: "av1_nvenc",
        }.get(codec)

    @staticmethod
    def _software_encoder(codec):
        return {
            Codec.H264: "libx264",
            Codec.HEVC: "libx265",
            Codec.PRORES_PROXY: "prores_ks",
            Codec.PRORES_LT: "prores_ks",
            Codec.PRORES_422: "prores_ks",
            Codec.DNXHR_LB: "dnxhd",
            Codec.DNXHR_SQ: "dnxhd",
            Codec.DNXHR_HQ: "dnxhd",
        }.get(codec)

    def build_plan_command(
        self,
        input_file,
        output_file,
        plan: EncodingPlan,
        pipeline: str = EncodingPipeline.CPU,
        capabilities: HardwareCapabilities | None = None,
        overwrite=False,
    ):
        """Build a deterministic command from resolved encoding decisions.

        ``pipeline`` selects GPU NVENC, CPU-decode NVENC, or CPU software
        encoding. Encoder availability is verified against a supplied
        capability snapshot; this method does not probe FFmpeg itself.
        """
        capabilities = capabilities or HardwareCapabilities()
        if plan.hdr_mode.value == "tone_map_sdr":
            raise CommandGenerationError(
                "HDR to SDR tone mapping is not yet implemented."
            )
        pipeline = str(pipeline).lower()
        if pipeline not in {
            EncodingPipeline.GPU,
            EncodingPipeline.NVENC,
            EncodingPipeline.CPU,
        }:
            raise CommandGenerationError(
                f"Unsupported encoding pipeline: {pipeline}"
            )

        nvenc = pipeline in {
            EncodingPipeline.GPU,
            EncodingPipeline.NVENC,
        }
        encoder = (
            self._nvenc_encoder(plan.codec)
            if nvenc
            else self._software_encoder(plan.codec)
        )
        if encoder is None:
            raise CommandGenerationError(
                f"Codec {plan.codec.value} is not supported by "
                f"the {pipeline} pipeline."
            )
        self._require_encoder(capabilities, encoder)

        if pipeline == EncodingPipeline.GPU and not (
            capabilities.cuda and capabilities.scale_cuda
        ):
            raise CommandGenerationError(
                "GPU pipeline requires CUDA and the scale_cuda filter."
            )
        if not nvenc and pipeline == EncodingPipeline.GPU:
            raise CommandGenerationError(
                "The GPU pipeline only supports NVENC codecs."
            )

        command = [
            str(self.ffmpeg_path),
            "-hide_banner",
            "-y" if overwrite else "-n",
            "-autorotate",
        ]
        if pipeline == EncodingPipeline.GPU:
            command += [
                "-hwaccel", "cuda",
                "-hwaccel_output_format", "cuda",
            ]
        command += [
            "-i", str(input_file),
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-vf",
            self._scale_filter(
                plan,
                cuda=(pipeline == EncodingPipeline.GPU),
            ),
        ]

        if nvenc:
            self._add_nvenc_options(command, plan, encoder)
        else:
            self._add_software_video_options(command, plan, encoder)

        self._add_gop_options(command, plan, encoder)
        self._add_hdr_preservation_options(command, plan, encoder)
        self._add_fps_plan_options(command, plan)
        self._add_audio_plan_options(command, plan)
        self._add_container_plan_options(command, plan, output_file)
        command.append(str(output_file))
        return command

    def build_command(
        self,
        input_file,
        output_file,
        plan: EncodingPlan,
        pipeline: str = EncodingPipeline.CPU,
        capabilities: HardwareCapabilities | None = None,
        overwrite=False,
    ):
        """Alias for :meth:`build_plan_command`."""
        return self.build_plan_command(
            input_file,
            output_file,
            plan,
            pipeline,
            capabilities,
            overwrite,
        )

    @staticmethod
    def _add_nvenc_options(command, plan, encoder):
        command += ["-c:v", encoder]
        if plan.encoder_preset:
            command += ["-preset", plan.encoder_preset]
        else:
            command += ["-preset", "p6"]
        command += ["-tune", "hq"]

        if plan.rate_control is RateControl.CQ:
            if plan.quality is None:
                raise CommandGenerationError(
                    "NVENC CQ rate control requires a quality value."
                )
            command += [
                "-rc", "vbr",
                "-cq", str(plan.quality),
                "-b:v", "0",
            ]
        elif plan.rate_control is RateControl.CBR:
            if not plan.bitrate:
                raise CommandGenerationError(
                    "NVENC CBR rate control requires a bitrate."
                )
            command += ["-rc", "cbr", "-b:v", str(plan.bitrate)]
        elif plan.rate_control is RateControl.VBR:
            if not plan.bitrate:
                raise CommandGenerationError(
                    "NVENC VBR rate control requires a bitrate."
                )
            command += ["-rc", "vbr", "-b:v", str(plan.bitrate)]
            if plan.quality is not None:
                command += ["-cq", str(plan.quality)]

        profile = {
            Codec.H264: "high",
            Codec.HEVC: (
                "main10"
                if plan.hdr_mode is HDRMode.PRESERVE
                and plan.source_hdr_classification.value
                in {"hlg", "pq", "hdr_unknown"}
                else "main"
            ),
        }.get(plan.codec)
        if profile:
            command += ["-profile:v", profile]

    @staticmethod
    def _add_software_video_options(command, plan, encoder):
        command += ["-c:v", encoder]
        if plan.codec in (Codec.H264, Codec.HEVC):
            software_presets = {
                "ultrafast", "superfast", "veryfast", "faster", "fast",
                "medium", "slow", "slower", "veryslow", "placebo",
            }
            if plan.encoder_preset in software_presets:
                command += ["-preset", plan.encoder_preset]
            elif plan.codec is Codec.H264:
                command += ["-preset", "medium"]
            else:
                command += ["-preset", "medium"]
            if plan.rate_control is RateControl.CQ:
                if plan.quality is None:
                    raise CommandGenerationError(
                        f"{encoder} CQ requires a quality value."
                    )
                command += [
                    "-crf",
                    str(plan.quality),
                ]
            else:
                if not plan.bitrate:
                    raise CommandGenerationError(
                        f"{encoder} {plan.rate_control.value.upper()} "
                        "requires a bitrate."
                    )
                command += ["-b:v", str(plan.bitrate)]
                if plan.rate_control is RateControl.CBR:
                    command += [
                        "-minrate", str(plan.bitrate),
                        "-maxrate", str(plan.bitrate),
                        "-bufsize", str(plan.bitrate * 2),
                    ]
            if plan.codec is Codec.H264:
                command += ["-profile:v", "high", "-pix_fmt", "yuv420p"]
            return

        prores_profiles = {
            Codec.PRORES_PROXY: "0",
            Codec.PRORES_LT: "1",
            Codec.PRORES_422: "2",
        }
        if plan.codec in prores_profiles:
            command += [
                "-profile:v", prores_profiles[plan.codec],
                "-pix_fmt", "yuv422p10le",
            ]
            return

        dnxhr_profiles = {
            Codec.DNXHR_LB: "dnxhr_lb",
            Codec.DNXHR_SQ: "dnxhr_sq",
            Codec.DNXHR_HQ: "dnxhr_hq",
        }
        if plan.codec in dnxhr_profiles:
            command += [
                "-profile:v", dnxhr_profiles[plan.codec],
                "-pix_fmt", "yuv422p",
            ]
            return

        raise CommandGenerationError(
            f"No software encoder configuration for {plan.codec.value}."
        )

    @staticmethod
    def _add_hdr_preservation_options(command, plan, encoder):
        if (
            plan.hdr_mode is not HDRMode.PRESERVE
            or plan.source_hdr_classification.value not in {
                "hlg", "pq", "hdr_unknown",
            }
        ):
            return
        pixel_formats = {
            "hevc_nvenc": "p010le",
            "av1_nvenc": "p010le",
            "libx265": "yuv420p10le",
            "prores_ks": "yuv422p10le",
            "dnxhd": "yuv422p10le",
        }
        pixel_format = pixel_formats.get(encoder)
        if not pixel_format:
            raise CommandGenerationError(
                f"{encoder} cannot preserve HDR at 10-bit. "
                "Select a 10-bit-capable output codec."
            )
        command += ["-pix_fmt", pixel_format]
        color_options = (
            ("-color_primaries", plan.source_color_primaries),
            ("-color_trc", plan.source_color_transfer),
            ("-colorspace", plan.source_color_space),
            ("-color_range", plan.source_color_range),
        )
        if encoder == "libx265":
            x265_color_values = {
                "colorprim": {
                    "bt709": "1",
                    "bt2020": "9",
                }.get((plan.source_color_primaries or "").lower()),
                "transfer": {
                    "bt709": "1",
                    "smpte2084": "16",
                    "arib-std-b67": "18",
                }.get((plan.source_color_transfer or "").lower()),
                "colormatrix": {
                    "bt709": "1",
                    "bt2020nc": "9",
                    "bt2020ncl": "9",
                    "bt2020c": "10",
                    "bt2020cl": "10",
                }.get((plan.source_color_space or "").lower()),
                "range": {
                    "tv": "limited",
                    "mpeg": "limited",
                    "pc": "full",
                    "jpeg": "full",
                }.get((plan.source_color_range or "").lower()),
            }
            x265_options = [
                f"{name}={value}"
                for name, value in x265_color_values.items()
                if value is not None
            ]
            if x265_options:
                command += ["-x265-params", ":".join(x265_options)]
        else:
            for flag, value in color_options:
                if value:
                    command += [flag, value]
        if plan.source_hdr_metadata_types:
            command += ["-map_metadata:s:v:0", "0:s:v:0"]

    @staticmethod
    def _add_gop_options(command, plan, encoder):
        if plan.gop_size is None:
            return
        if plan.gop_size <= 0:
            raise CommandGenerationError("GOP size must be positive.")
        if encoder in {
            "h264_nvenc", "hevc_nvenc", "av1_nvenc",
            "libx264", "libx265",
        }:
            command += ["-g", str(plan.gop_size)]
            if encoder == "libx264":
                command += ["-keyint_min", str(plan.gop_size)]

    @staticmethod
    def _add_fps_plan_options(command, plan):
        if plan.cfr_required:
            command += [
                "-r", FFmpegEngine._fps_text(plan.resolved_fps),
                "-fps_mode", "cfr",
            ]
        elif plan.fps_mode in (FPSMode.AUTO, FPSMode.SOURCE):
            command += ["-fps_mode", "passthrough"]

    @staticmethod
    def _add_audio_plan_options(command, plan):
        if plan.audio_mode is AudioMode.COPY:
            command += ["-c:a", "copy"]
            return
        if plan.audio_mode is AudioMode.AAC:
            if not plan.audio_bitrate or not plan.sample_rate or not plan.channel_count:
                raise CommandGenerationError(
                    "AAC audio requires bitrate, sample rate, and channel count."
                )
            command += [
                "-c:a", "aac",
                "-b:a", str(plan.audio_bitrate),
                "-ar", str(plan.sample_rate),
                "-ac", str(plan.channel_count),
            ]
            return
        raise CommandGenerationError(
            "Audio mode AUTO must be resolved before command generation."
        )

    @staticmethod
    def _add_container_plan_options(command, plan, output_file):
        if plan.preserve_metadata:
            command += ["-map_metadata", "0"]
        if (
            plan.faststart
            and Path(output_file).suffix.lower() in {".mp4", ".m4v", ".mov"}
        ):
            command += ["-movflags", "+faststart"]

    # ---------------------------------------------------------
    # SCALE FILTERS
    # ---------------------------------------------------------

    def build_cpu_scale_filter(self, preset):

        max_dimension = int(
            preset.max_dimension
        )
        even_option = (
            "force_divisible_by=2:"
            if preset.force_even_dimensions
            else ""
        )

        return (
            f"scale="
            f"w='min(iw,{max_dimension})':"
            f"h='min(ih,{max_dimension})':"
            f"force_original_aspect_ratio=decrease:"
            f"{even_option}"
            f"flags=lanczos"
        )

    def build_cuda_scale_filter(self, preset):

        max_dimension = int(
            preset.max_dimension
        )
        even_option = (
            ":force_divisible_by=2"
            if preset.force_even_dimensions
            else ""
        )

        return (
            f"scale_cuda="
            f"w='min(iw,{max_dimension})':"
            f"h='min(ih,{max_dimension})':"
            f"force_original_aspect_ratio=decrease"
            f"{even_option}"
        )

    # ---------------------------------------------------------
    # FPS
    # ---------------------------------------------------------

    def add_fps_options(
        self,
        command,
        preset
    ):

        if (
            preset.fps
            and preset.fps != "original"
        ):

            command += [
                "-r",
                str(preset.fps),
                "-fps_mode",
                "cfr",
            ]

        else:

            command += [
                "-fps_mode",
                "passthrough",
            ]

    # ---------------------------------------------------------
    # NVIDIA VIDEO ENCODER
    # ---------------------------------------------------------

    def add_nvenc_video_options(
        self,
        command,
        preset,
        hardware_frames=False,
    ):

        codec = (
            preset.codec
            .lower()
            .strip()
        )

        # -----------------------------
        # H.264 NVENC
        # -----------------------------

        if codec == "h264":

            command += [

                "-c:v",
                "h264_nvenc",

                "-preset",
                preset.encoder_preset,

                "-tune",
                "hq",

                "-rc",
                "vbr",

                "-cq",
                str(preset.cq),

                "-b:v",
                "0",

                "-profile:v",
                "high",
            ]

            if not hardware_frames:
                command += ["-pix_fmt", "yuv420p"]

            return

        # -----------------------------
        # HEVC / H.265 NVENC
        # -----------------------------

        if codec == "hevc":

            command += [

                "-c:v",
                "hevc_nvenc",

                "-preset",
                preset.encoder_preset,

                "-tune",
                "hq",

                "-rc",
                "vbr",

                "-cq",
                str(preset.cq),

                "-b:v",
                "0",

                "-profile:v",
                "main",
            ]

            if not hardware_frames:
                command += ["-pix_fmt", "yuv420p"]

            return

        raise ValueError(
            f"Unsupported NVENC codec: {preset.codec}"
        )

    # ---------------------------------------------------------
    # CPU VIDEO ENCODER
    # ---------------------------------------------------------

    def add_cpu_video_options(
        self,
        command,
        preset
    ):

        command += [

            "-c:v",
            "libx264",

            "-preset",
            "medium",

            "-crf",
            str(preset.cq),

            "-pix_fmt",
            "yuv420p",

            "-profile:v",
            "high",
        ]

    # ---------------------------------------------------------
    # AUDIO
    # ---------------------------------------------------------

    def add_audio_options(
        self,
        command,
        preset
    ):

        mode = (
            preset.audio_mode
            .lower()
            .strip()
        )

        # -----------------------------
        # COPY AUDIO
        # -----------------------------

        if mode == "copy":

            command += [
                "-c:a",
                "copy",
            ]

            return

        # -----------------------------
        # AAC
        # -----------------------------

        command += [

            "-c:a",
            "aac",

            "-b:a",
            preset.audio_bitrate,

            "-ar",
            str(preset.audio_rate),

            "-ac",
            str(preset.audio_channels),
        ]

    # ---------------------------------------------------------
    # CONTAINER OPTIONS
    # ---------------------------------------------------------

    def add_container_options(
        self,
        command,
        preset
    ):

        if preset.copy_metadata:

            command += [
                "-map_metadata",
                "0",
            ]

        if preset.faststart:

            command += [
                "-movflags",
                "+faststart",
            ]

    # ---------------------------------------------------------
    # BASE INPUT OPTIONS
    # ---------------------------------------------------------

    def build_base_command(
        self,
        input_file,
        overwrite=False,
    ):

        return [

            str(self.ffmpeg_path),

            "-hide_banner",

            "-y" if overwrite else "-n",

            # Respect rotation metadata
            "-autorotate",

            "-i",
            str(input_file),

            "-map",
            "0:v:0",

            "-map",
            "0:a:0?",
        ]

    # ---------------------------------------------------------
    # GPU PIPELINE
    #
    # NVDEC
    #   ↓
    # CUDA
    #   ↓
    # CUDA SCALE
    #   ↓
    # NVENC
    # ---------------------------------------------------------

    def build_gpu_command(
        self,
        input_file,
        output_file,
        preset,
        overwrite=False,
    ):

        command = [

            str(self.ffmpeg_path),

            "-hide_banner",

            "-y" if overwrite else "-n",

            "-autorotate",

            "-hwaccel",
            "cuda",

            "-hwaccel_output_format",
            "cuda",

            "-i",
            str(input_file),

            "-map",
            "0:v:0",

            "-map",
            "0:a:0?",
        ]

        # CUDA scaling
        command += [

            "-vf",
            self.build_cuda_scale_filter(
                preset
            ),
        ]

        # NVENC
        self.add_nvenc_video_options(
            command,
            preset,
            hardware_frames=True,
        )

        # FPS
        self.add_fps_options(
            command,
            preset
        )

        # Audio
        self.add_audio_options(
            command,
            preset
        )

        # Metadata / faststart
        self.add_container_options(
            command,
            preset
        )

        command += [
            str(output_file)
        ]

        return command

    # ---------------------------------------------------------
    # CPU DECODE + NVENC
    #
    # CPU
    #   ↓
    # CPU SCALE
    #   ↓
    # NVENC
    # ---------------------------------------------------------

    def build_nvenc_fallback_command(
        self,
        input_file,
        output_file,
        preset,
        overwrite=False,
    ):

        command = self.build_base_command(
            input_file,
            overwrite,
        )

        # CPU scaling
        command += [

            "-vf",
            self.build_cpu_scale_filter(
                preset
            ),
        ]

        # NVENC
        self.add_nvenc_video_options(
            command,
            preset
        )

        # FPS
        self.add_fps_options(
            command,
            preset
        )

        # Audio
        self.add_audio_options(
            command,
            preset
        )

        # Metadata / faststart
        self.add_container_options(
            command,
            preset
        )

        command += [
            str(output_file)
        ]

        return command

    # ---------------------------------------------------------
    # CPU DECODE + CPU SCALE + X264
    # ---------------------------------------------------------

    def build_cpu_command(
        self,
        input_file,
        output_file,
        preset,
        overwrite=False,
    ):

        command = self.build_base_command(
            input_file,
            overwrite,
        )

        # CPU scaling
        command += [

            "-vf",
            self.build_cpu_scale_filter(
                preset
            ),
        ]

        # x264
        self.add_cpu_video_options(
            command,
            preset
        )

        # FPS
        self.add_fps_options(
            command,
            preset
        )

        # Audio
        self.add_audio_options(
            command,
            preset
        )

        # Metadata / faststart
        self.add_container_options(
            command,
            preset
        )

        command += [
            str(output_file)
        ]

        return command

    # ---------------------------------------------------------
    # RUN FFMPEG
    # ---------------------------------------------------------

    def run(
        self,
        command,
        on_output=None,
        process_holder=None
    ):

        if process_holder is None:
            process_holder = {}

        creation_flags = 0

        if hasattr(
            subprocess,
            "CREATE_NO_WINDOW"
        ):

            creation_flags = (
                subprocess.CREATE_NO_WINDOW
            )

        process = subprocess.Popen(

            command,

            stdout=subprocess.PIPE,

            stderr=subprocess.STDOUT,

            text=True,

            encoding="utf-8",

            errors="replace",

            bufsize=1,

            creationflags=creation_flags,
        )

        process_holder[
            "process"
        ] = process

        try:

            if process.stdout:

                for line in process.stdout:

                    line = line.rstrip()

                    if on_output:

                        on_output(line)

            return_code = (
                process.wait()
            )

            return return_code

        finally:

            try:
                if process.poll() is None:
                    self.terminate(process)
            finally:
                if process.stdout:
                    process.stdout.close()

                process_holder.pop(
                    "process",
                    None
                )

    # ---------------------------------------------------------
    # TERMINATE PROCESS
    # ---------------------------------------------------------

    @staticmethod
    def terminate(process):

        if process is None:
            return

        if process.poll() is not None:
            return

        try:
            process.terminate()
        except OSError:
            if process.poll() is not None:
                return
            raise

        try:
            process.wait(
                timeout=3
            )
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                if process.poll() is not None:
                    return
                raise

            process.wait()