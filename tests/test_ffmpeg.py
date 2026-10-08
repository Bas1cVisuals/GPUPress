import tempfile
import unittest
from pathlib import Path

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
from app.core.ffmpeg import (
    CommandGenerationError,
    EncodingPipeline,
    FFmpegEngine,
)
from app.core.media import MediaAnalysis


def media(width=3840, height=2160, fps="60000/1001"):
    return MediaAnalysis.from_ffprobe(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "width": width,
                    "height": height,
                    "r_frame_rate": fps,
                    "avg_frame_rate": fps,
                    "pix_fmt": "yuv420p",
                }
            ]
        }
    )


def plan_for(
    codec,
    *,
    width=3840,
    height=2160,
    fps="60000/1001",
    resolution=ResolutionMode.P1080,
    fps_mode=FPSMode.AUTO,
    audio_mode=AudioMode.COPY,
    **options,
):
    return create_encoding_plan(
        media(width, height, fps),
        UserEncodingOptions(
            codec=codec,
            resolution_mode=resolution,
            fps_mode=fps_mode,
            audio_mode=audio_mode,
            **options,
        ),
    )


class FFmpegPlanCommandTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        ffmpeg_path = Path(self.tempdir.name) / "ffmpeg.exe"
        ffmpeg_path.touch()
        self.engine = FFmpegEngine(ffmpeg_path)
        self.input = Path(self.tempdir.name) / "input.mov"
        self.output = Path(self.tempdir.name) / "output.mp4"

    def tearDown(self):
        self.tempdir.cleanup()

    def command(
        self,
        plan,
        pipeline=EncodingPipeline.CPU,
        encoders=(),
        **caps,
    ):
        capabilities = HardwareCapabilities(
            available_encoders=tuple(encoders),
            **caps,
        )
        return self.engine.build_plan_command(
            self.input,
            self.output,
            plan,
            pipeline=pipeline,
            capabilities=capabilities,
        )

    def test_h264_nvenc_command_and_known_quality_options(self):
        plan = plan_for(Codec.H264, encoder_preset="p5", quality=19)
        command = self.command(
            plan,
            EncodingPipeline.NVENC,
            ("h264_nvenc",),
        )
        self.assertIn("h264_nvenc", command)
        self.assertIn("-cq", command)
        self.assertIn("19", command)
        self.assertIn("-preset", command)
        self.assertIn("p5", command)
        self.assertIn("-profile:v", command)
        self.assertIn("high", command)

    def test_hevc_nvenc_command(self):
        command = self.command(
            plan_for(Codec.HEVC),
            EncodingPipeline.NVENC,
            ("hevc_nvenc",),
        )
        self.assertIn("hevc_nvenc", command)
        self.assertIn("main", command)

    def test_av1_nvenc_command_structure(self):
        command = self.command(
            plan_for(Codec.AV1),
            EncodingPipeline.NVENC,
            ("av1_nvenc",),
        )
        self.assertIn("av1_nvenc", command)
        self.assertIn("-cq", command)

    def test_h264_and_hevc_cpu_commands(self):
        h264 = self.command(
            plan_for(Codec.H264),
            encoders=("libx264",),
        )
        self.assertIn("libx264", h264)
        self.assertIn("-crf", h264)
        self.assertIn("yuv420p", h264)

        hevc = self.command(
            plan_for(Codec.HEVC),
            encoders=("libx265",),
        )
        self.assertIn("libx265", hevc)
        self.assertIn("-crf", hevc)
        self.assertNotIn("libx264", hevc)
        self.assertNotIn("h264_nvenc", hevc)

        hevc_gop = self.command(
            plan_for(Codec.HEVC, gop_size=30),
            encoders=("libx265",),
        )
        self.assertIn("-g", hevc_gop)
        self.assertNotIn("-keyint_min", hevc_gop)

    def test_prores_proxy_and_dnxhr_lb(self):
        prores = self.command(
            plan_for(Codec.PRORES_PROXY),
            encoders=("prores_ks",),
        )
        self.assertIn("prores_ks", prores)
        self.assertEqual(prores[prores.index("-profile:v") + 1], "0")
        self.assertIn("yuv422p10le", prores)

        dnxhr = self.command(
            plan_for(Codec.DNXHR_LB),
            encoders=("dnxhd",),
        )
        self.assertIn("dnxhd", dnxhr)
        self.assertEqual(
            dnxhr[dnxhr.index("-profile:v") + 1],
            "dnxhr_lb",
        )

    def test_hdr_preserve_emits_10bit_pixel_format_and_color_signaling(self):
        hdr = MediaAnalysis.from_ffprobe({
            "streams": [{
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "24000/1001",
                "avg_frame_rate": "24000/1001",
                "pix_fmt": "yuv420p10le",
                "color_primaries": "bt2020",
                "color_transfer": "smpte2084",
                "color_space": "bt2020nc",
                "color_range": "tv",
            }]
        })
        hdr_plan = create_encoding_plan(
            hdr,
            UserEncodingOptions(
                codec=Codec.HEVC,
                hdr_mode=HDRMode.PRESERVE,
            ),
        )
        command = self.command(
            hdr_plan,
            encoders=("libx265",),
        )
        self.assertEqual(
            command[command.index("-pix_fmt") + 1],
            "yuv420p10le",
        )
        self.assertEqual(
            command[command.index("-x265-params") + 1],
            "colorprim=9:transfer=16:colormatrix=9:range=limited",
        )
        self.assertNotIn("-color_trc", command)

    def test_landscape_and_portrait_scaling(self):
        landscape = self.command(
            plan_for(Codec.H264),
            encoders=("libx264",),
        )
        self.assertIn(
            "scale=w=1920:h=1080:flags=lanczos",
            landscape,
        )

        portrait = self.command(
            plan_for(Codec.H264, width=2160, height=3840),
            encoders=("libx264",),
        )
        self.assertIn(
            "scale=w=1080:h=1920:flags=lanczos",
            portrait,
        )

    def test_fractional_cfr_rates(self):
        cases = (
            (24000 / 1001, "23.97602398"),
            (30000 / 1001, "29.97002997"),
            (60000 / 1001, "59.94005994"),
        )
        for fps, expected in cases:
            with self.subTest(fps=fps):
                plan = plan_for(
                    Codec.H264,
                    fps_mode=FPSMode.CUSTOM,
                    custom_fps=fps,
                )
                command = self.command(plan, encoders=("libx264",))
                self.assertEqual(command[command.index("-r") + 1], expected)
                self.assertEqual(
                    command[command.index("-fps_mode") + 1],
                    "cfr",
                )

    def test_audio_copy_and_aac(self):
        copy_command = self.command(
            plan_for(Codec.H264),
            encoders=("libx264",),
        )
        self.assertEqual(
            copy_command[copy_command.index("-c:a") + 1],
            "copy",
        )

        aac_plan = plan_for(
            Codec.H264,
            audio_mode=AudioMode.AAC,
            audio_bitrate=192_000,
            sample_rate=48_000,
            channel_count=2,
        )
        aac_command = self.command(aac_plan, encoders=("libx264",))
        self.assertEqual(aac_command[aac_command.index("-c:a") + 1], "aac")
        self.assertEqual(aac_command[aac_command.index("-b:a") + 1], "192000")
        self.assertEqual(aac_command[aac_command.index("-ar") + 1], "48000")
        self.assertEqual(aac_command[aac_command.index("-ac") + 1], "2")

    def test_faststart_metadata_and_fast_scrub_gop(self):
        plan = plan_for(
            Codec.H264,
            gop_size=15,
            faststart=True,
            preserve_metadata=True,
        )
        command = self.command(plan, encoders=("libx264",))
        self.assertIn("-map_metadata", command)
        self.assertIn("+faststart", command)
        self.assertEqual(command[command.index("-g") + 1], "15")
        self.assertEqual(command[command.index("-keyint_min") + 1], "15")

        intra_plan = plan_for(Codec.PRORES_PROXY, gop_size=15)
        intra_command = self.command(intra_plan, encoders=("prores_ks",))
        self.assertNotIn("-g", intra_command)

    def test_gpu_pipeline_uses_cuda_frames_and_cuda_scale(self):
        command = self.command(
            plan_for(Codec.H264),
            EncodingPipeline.GPU,
            ("h264_nvenc",),
            cuda=True,
            scale_cuda=True,
        )
        self.assertIn("-hwaccel", command)
        self.assertIn("cuda", command)
        self.assertIn("-hwaccel_output_format", command)
        self.assertIn(
            "scale_cuda=w=1920:h=1080",
            command,
        )
        self.assertNotIn("-pix_fmt", command)

    def test_cpu_pipeline_uses_software_scale(self):
        command = self.command(
            plan_for(Codec.H264),
            encoders=("libx264",),
        )
        self.assertNotIn("-hwaccel", command)
        self.assertIn(
            "scale=w=1920:h=1080:flags=lanczos",
            command,
        )

    def test_cpu_decode_nvenc_pipeline(self):
        command = self.command(
            plan_for(Codec.HEVC),
            EncodingPipeline.NVENC,
            ("hevc_nvenc",),
        )
        self.assertIn("hevc_nvenc", command)
        self.assertIn("scale=w=1920:h=1080:flags=lanczos", command)
        self.assertNotIn("-hwaccel", command)

    def test_capability_errors_and_no_wrong_codec_fallback(self):
        with self.assertRaisesRegex(CommandGenerationError, "unavailable"):
            self.command(
                plan_for(Codec.HEVC),
                encoders=("h264_nvenc",),
            )
        with self.assertRaisesRegex(CommandGenerationError, "unavailable"):
            self.command(plan_for(Codec.AV1), EncodingPipeline.NVENC)
        with self.assertRaisesRegex(CommandGenerationError, "not supported"):
            self.command(
                plan_for(Codec.PRORES_LT),
                EncodingPipeline.NVENC,
                ("h264_nvenc",),
            )

    def test_no_forced_30fps_and_no_upscale(self):
        plan = plan_for(
            Codec.H264,
            width=1280,
            height=720,
            fps="59/1",
            resolution=ResolutionMode.P1080,
        )
        command = self.command(plan, encoders=("libx264",))
        self.assertNotIn("-r", command)
        self.assertEqual(plan.output_width, 1280)
        self.assertEqual(plan.output_height, 720)
        self.assertIn(
            "scale=w=1280:h=720:flags=lanczos",
            command,
        )

    def test_faststart_is_limited_to_supported_output_containers(self):
        output = Path(self.tempdir.name) / "output.mkv"
        command = self.engine.build_plan_command(
            self.input,
            output,
            plan_for(Codec.H264),
            capabilities=HardwareCapabilities(
                available_encoders=("libx264",)
            ),
        )
        self.assertNotIn("-movflags", command)

    def test_legacy_cpu_builder_remains_available(self):
        class LegacyPreset:
            max_dimension = 1920
            force_even_dimensions = True
            codec = "h264"
            cq = 18
            fps = "original"
            encoder_preset = "p6"
            audio_mode = "copy"
            copy_metadata = True
            faststart = True

        command = self.engine.build_cpu_command(
            self.input,
            self.output,
            LegacyPreset(),
        )
        self.assertIn("libx264", command)
        self.assertIn("scale=", command[command.index("-vf") + 1])


if __name__ == "__main__":
    unittest.main()
