from pathlib import Path
import logging
import subprocess
import sys


class HardwareInfo:

    def __init__(self):

        self.ffmpeg_path = self._get_ffmpeg_path()

        self.ffmpeg_exists = (
            self.ffmpeg_path.exists()
        )

        self.nvenc = False
        self.h264_nvenc = False
        self.hevc_nvenc = False

        self.cuda = False
        self.scale_cuda = False

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
        encoder_names = {
            token
            for line in encoders.splitlines()
            for token in line.split()
        }

        self.h264_nvenc = (
            "h264_nvenc"
            in encoder_names
        )

        self.hevc_nvenc = (
            "hevc_nvenc"
            in encoder_names
        )

        self.nvenc = (
            self.h264_nvenc
            or self.hevc_nvenc
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

                creationflags=creation_flags,
            )

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

            "cuda":
                self.cuda,

            "scale_cuda":
                self.scale_cuda,
        }

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