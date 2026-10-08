from pathlib import Path
import logging
import re
import shutil
import subprocess
import sys

from app.core.encoding_plan import HardwareCapabilities


class HardwareInfo:

    def __init__(self):

        self.ffmpeg_path = self._get_ffmpeg_path()

        self.ffmpeg_exists = (
            self.ffmpeg_path.exists()
        )

        self.nvenc = False
        self.h264_nvenc = False
        self.hevc_nvenc = False
        self.av1_nvenc = False

        self.cuda = False
        self.scale_cuda = False
        self.nvidia_available = False
        self.gpu_name = None
        self.nvdec_available = False
        self.available_encoders = ()
        self.available_decoders = ()

        self.ffmpeg_version = "Unknown"

        if self.ffmpeg_exists:
            self.detect()

    # =========================================================
    # FFMPEG PATH
    # =========================================================

    def _get_ffmpeg_path(self):

        # -----------------------------------------------------
        # PYINSTALLER / FROZEN APPLICATION
        # -----------------------------------------------------

        if getattr(sys, "frozen", False):

            # One-file PyInstaller:
            # bundled files are extracted into _MEIPASS

            meipass = getattr(
                sys,
                "_MEIPASS",
                None
            )

            if meipass:

                bundled_ffmpeg = (
                    Path(meipass)
                    / "bin"
                    / "ffmpeg.exe"
                )

                if bundled_ffmpeg.exists():

                    return bundled_ffmpeg

            # -------------------------------------------------
            # EXTERNAL BIN BESIDE EXE
            # -------------------------------------------------

            exe_dir = (
                Path(sys.executable)
                .resolve()
                .parent
            )

            external_ffmpeg = (
                exe_dir
                / "bin"
                / "ffmpeg.exe"
            )

            if external_ffmpeg.exists():

                return external_ffmpeg

            # -------------------------------------------------
            # EXE DIRECTORY DIRECT FALLBACK
            # -------------------------------------------------

            direct_ffmpeg = (
                exe_dir
                / "ffmpeg.exe"
            )

            if direct_ffmpeg.exists():

                return direct_ffmpeg

        # -----------------------------------------------------
        # NORMAL PYTHON DEVELOPMENT
        # -----------------------------------------------------

        project_root = (
            Path(__file__)
            .resolve()
            .parents[2]
        )

        development_ffmpeg = (
            project_root
            / "bin"
            / "ffmpeg.exe"
        )

        return development_ffmpeg

    # =========================================================
    # DETECT FFMPEG CAPABILITIES
    # =========================================================

    def detect(self):

        self.h264_nvenc = False
        self.hevc_nvenc = False
        self.av1_nvenc = False
        self.cuda = False
        self.scale_cuda = False
        self.nvdec_available = False
        self.available_encoders = ()
        self.available_decoders = ()

        self.ffmpeg_version = (
            self._get_version()
        )

        # -----------------------------------------------------
        # ENCODERS
        # -----------------------------------------------------

        encoders = self._run_ffmpeg(
            [
                "-hide_banner",
                "-encoders",
            ]
        )
        encoder_names = self._parse_capability_names(encoders)
        self.available_encoders = tuple(sorted(encoder_names))

        self.h264_nvenc = (
            "h264_nvenc"
            in encoder_names
        )

        self.hevc_nvenc = (
            "hevc_nvenc"
            in encoder_names
        )
        self.av1_nvenc = "av1_nvenc" in encoder_names

        self.nvenc = (
            self.h264_nvenc
            or self.hevc_nvenc
            or self.av1_nvenc
        )

        # -----------------------------------------------------
        # HARDWARE ACCELERATION
        # -----------------------------------------------------

        hwaccels = self._run_ffmpeg(
            [
                "-hide_banner",
                "-hwaccels",
            ]
        )

        self.cuda = (
            any(
                line.strip().lower() == "cuda"
                for line in hwaccels.splitlines()
            )
        )

        # Decoder listing distinguishes FFmpeg builds with exposed CUVID
        # decoders; hardware acceleration still also requires CUDA support.
        decoders = self._run_ffmpeg(
            [
                "-hide_banner",
                "-decoders",
            ]
        )
        decoder_names = self._parse_capability_names(decoders)
        self.available_decoders = tuple(sorted(decoder_names))
        self.nvdec_available = self.cuda and any(
            name.endswith("_cuvid")
            for name in decoder_names
        )

        # -----------------------------------------------------
        # CUDA FILTERS
        # -----------------------------------------------------

        filters = self._run_ffmpeg(
            [
                "-hide_banner",
                "-filters",
            ]
        )

        self.scale_cuda = any(
            "scale_cuda" in line.split()
            for line in filters.splitlines()
        )

        self.gpu_name = self._detect_nvidia_gpu_name()
        self.nvidia_available = self.gpu_name is not None

    @staticmethod
    def _parse_capability_names(output):
        """Parse encoder/decoder names from FFmpeg capability listings."""
        names = set()
        for line in (output or "").splitlines():
            match = re.match(
                r"^\s*[A-Z.]{6}\s+([A-Za-z0-9_]+)\s+",
                line,
            )
            if match:
                names.add(match.group(1))
        return names

    @staticmethod
    def _detect_nvidia_gpu_name():
        """Return a detected NVIDIA device name when nvidia-smi is available."""
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return None
        try:
            result = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=name",
                    "--format=csv,noheader",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            logging.debug("Could not query NVIDIA GPU name: %s", error)
            return None
        if result.returncode != 0:
            return None
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return names[0] if names else None

    # =========================================================
    # RUN FFMPEG
    # =========================================================

    def _run_ffmpeg(
        self,
        arguments
    ):

        if not self.ffmpeg_exists:
            return ""

        try:

            command = [
                str(self.ffmpeg_path),
                *arguments,
            ]

            creation_flags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0
            )

            result = subprocess.run(
                command,

                stdout=subprocess.PIPE,

                stderr=subprocess.STDOUT,

                text=True,

                encoding="utf-8",

                errors="replace",
                timeout=15,
                creationflags=creation_flags,
            )

            if result.returncode != 0:
                logging.warning(
                    "FFmpeg capability check failed for %s with exit code %s",
                    arguments,
                    result.returncode,
                )
                return ""
            return (
                result.stdout
                or ""
            )

        except (OSError, subprocess.SubprocessError) as error:
            logging.warning(
                "Could not run FFmpeg capability check %s: %s",
                arguments,
                error,
            )

            return ""

    # =========================================================
    # VERSION
    # =========================================================

    def _get_version(self):

        output = self._run_ffmpeg(
            [
                "-version"
            ]
        )

        if not output:
            return "Unknown"

        lines = (
            output
            .splitlines()
        )

        if not lines:
            return "Unknown"

        return (
            lines[0]
            .strip()
        )

    # =========================================================
    # STATUS
    # =========================================================

    def get_status(self):

        return {

            "ffmpeg":
                self.ffmpeg_exists,

            "ffmpeg_path":
                str(self.ffmpeg_path),

            "ffmpeg_version":
                self.ffmpeg_version,

            "nvenc":
                self.nvenc,

            "h264_nvenc":
                self.h264_nvenc,

            "hevc_nvenc":
                self.hevc_nvenc,

            "av1_nvenc":
                self.av1_nvenc,

            "cuda":
                self.cuda,

            "scale_cuda":
                self.scale_cuda,

            "nvidia_available":
                self.nvidia_available,

            "gpu_name":
                self.gpu_name,

            "nvdec_available":
                self.nvdec_available,

            "available_encoders":
                self.available_encoders,
        }

    def get_capabilities(self) -> HardwareCapabilities:
        """Return detected FFmpeg/GPU capabilities for planning and encoding."""
        return HardwareCapabilities(
            h264_nvenc=self.h264_nvenc,
            hevc_nvenc=self.hevc_nvenc,
            av1_nvenc=self.av1_nvenc,
            cuda=self.cuda,
            scale_cuda=self.scale_cuda,
            nvidia_available=self.nvidia_available,
            gpu_name=self.gpu_name,
            nvdec_available=self.nvdec_available,
            available_encoders=self.available_encoders,
        )

    # =========================================================
    # ENGINE
    # =========================================================

    def get_engine(self):

        if (
            self.cuda
            and self.scale_cuda
            and self.nvenc
        ):

            return (
                "NVDEC + CUDA SCALE + NVENC"
            )

        if self.nvenc:

            return (
                "CPU DECODE + NVENC"
            )

        return (
            "CPU DECODE + x264"
        )