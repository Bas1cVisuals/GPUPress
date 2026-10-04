from pathlib import Path
import subprocess


class FFmpegEngine:

    def __init__(self, ffmpeg_path):

        self.ffmpeg_path = Path(ffmpeg_path)

        if not self.ffmpeg_path.exists():
            raise FileNotFoundError(
                f"FFmpeg not found:\n{self.ffmpeg_path}"
            )

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