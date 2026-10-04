from pathlib import Path
import json
import logging
import subprocess


class MediaInfo:

    def __init__(self, ffprobe_path):

        self.ffprobe_path = Path(
            ffprobe_path
        )

    def probe(self, input_file):

        if not self.ffprobe_path.exists():
            logging.warning(
                "FFprobe was not found: %s",
                self.ffprobe_path,
            )
            return {}

        command = [
            str(self.ffprobe_path),

            "-v",
            "error",

            "-show_entries",
            "format=duration,size,format_name",

            "-show_entries",
            (
                "stream="
                "index,"
                "codec_name,"
                "codec_type,"
                "width,"
                "height,"
                "r_frame_rate,"
                "pix_fmt,"
                "sample_rate,"
                "channels"
            ),

            "-of",
            "json",

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

                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                ),
            )

            if result.returncode != 0:
                logging.warning(
                    "FFprobe failed for %s with exit code %s: %s",
                    input_file,
                    result.returncode,
                    result.stderr.strip(),
                )
                return {}

            return json.loads(
                result.stdout
            )

        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
        ) as error:
            logging.warning(
                "Could not probe media file %s: %s",
                input_file,
                error,
            )
            return {}

    @staticmethod
    def video_stream(info):

        for stream in info.get(
            "streams",
            []
        ):

            if (
                stream.get("codec_type")
                == "video"
            ):
                return stream

        return {}

    @staticmethod
    def audio_stream(info):

        for stream in info.get(
            "streams",
            []
        ):

            if (
                stream.get("codec_type")
                == "audio"
            ):
                return stream

        return {}

    @staticmethod
    def format_name(info):

        return (
            info.get(
                "format",
                {}
            )
            .get(
                "format_name",
                "Unknown"
            )
        )

    @staticmethod
    def duration(info):

        value = (
            info.get(
                "format",
                {}
            )
            .get(
                "duration",
                0
            )
        )

        try:
            return float(value)

        except Exception:
            return 0.0