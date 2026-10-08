import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.core.encoding_plan import (
    AudioMode,
    Codec,
    FPSMode,
    HDRMode,
    HardwareCapabilities,
    ResolutionMode,
)
from app.core.media import MediaAnalysis
from app.core.presets import get_preset
from app.workers.compression_worker import CompressionWorker
from app.ui.encoding_controls import build_user_options


def analyzed_media(
    *,
    width=3840,
    height=2160,
    rate="60000/1001",
    average=None,
    codec="h264",
    audio_codec="aac",
):
    return MediaAnalysis.from_ffprobe(
        {
            "format": {"duration": "10", "size": "4096"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": codec,
                    "width": width,
                    "height": height,
                    "pix_fmt": "yuv420p",
                    "r_frame_rate": rate,
                    "avg_frame_rate": average or rate,
                    "color_transfer": "bt709",
                },
                {
                    "codec_type": "audio",
                    "codec_name": audio_codec,
                    "sample_rate": "48000",
                    "channels": 2,
                    "channel_layout": "stereo",
                },
            ],
        }
    )


class FakeHardware:
    def __init__(self, root, capabilities):
        self.ffmpeg_path = root / "ffmpeg.exe"
        self.ffmpeg_path.touch(exist_ok=True)
        self.ffmpeg_exists = True
        self.capabilities = capabilities

    def get_capabilities(self):
        return self.capabilities


class CompressionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.input = self.root / "source.mp4"
        self.input.write_bytes(b"synthetic input")
        self.output = self.root / "encoded.mp4"
        self.hardware = FakeHardware(
            self.root,
            HardwareCapabilities(
                nvidia_available=True,
                cuda=True,
                scale_cuda=True,
                h264_nvenc=True,
                hevc_nvenc=True,
                av1_nvenc=True,
                available_encoders=(
                    "h264_nvenc",
                    "hevc_nvenc",
                    "av1_nvenc",
                    "libx264",
                    "libx265",
                    "prores_ks",
                    "dnxhd",
                ),
            ),
        )
        self.input_analysis = analyzed_media()
        self.output_analysis = analyzed_media(
            width=1920,
            height=1080,
            rate="60000/1001",
        )
        self.media_probe = patch(
            "app.workers.compression_worker.MediaInfo.probe",
            side_effect=[self.input_analysis, self.output_analysis],
        )
        self.media_probe.start()
        self.addCleanup(self.media_probe.stop)

    def tearDown(self):
        self.tempdir.cleanup()

    def make_worker(
        self,
        preset_id="fast_web_social",
        *,
        use_gpu=True,
        fallback=True,
        overwrite=False,
        output=None,
        capabilities=None,
    ):
        hardware = self.hardware
        if capabilities is not None:
            hardware = FakeHardware(self.root, capabilities)
        worker = CompressionWorker(
            input_file=self.input,
            output_file=output or self.output,
            preset=get_preset(preset_id),
            use_gpu=use_gpu,
            allow_cpu_fallback=fallback,
            overwrite_existing=overwrite,
            hardware=hardware,
        )
        self.finished = []
        self.failed = []
        self.cancelled = []
        worker.compression_finished.connect(self.finished.append)
        worker.compression_failed.connect(self.failed.append)
        worker.compression_cancelled.connect(
            lambda: self.cancelled.append(True)
        )
        return worker

    @staticmethod
    def succeed_and_write(worker, _command, on_output=None, process_holder=None):
        path = Path(_command[-1])
        path.write_bytes(b"encoded-output")
        return 0

    def install_successful_run(self, worker):
        worker.ffmpeg.run = lambda command, **kwargs: self.succeed_and_write(
            worker, command, **kwargs
        )

    def test_worker_resolves_primary_ui_intent_without_legacy_preset_adapter(self):
        options = build_user_options(
            codec_key="hevc_software",
            resolution_mode=ResolutionMode.P720,
            fps_value="smart",
            audio_mode=AudioMode.AUTO,
        )
        worker = CompressionWorker(
            input_file=self.input,
            output_file=self.output,
            preset=options,
            hardware=self.hardware,
        )
        worker.media_analysis = self.input_analysis

        plan = worker._resolve_plan()

        self.assertEqual(plan.codec, Codec.HEVC)
        self.assertEqual((plan.output_width, plan.output_height), (1280, 720))
        self.assertAlmostEqual(plan.resolved_fps, 60000 / 1001)
        self.assertFalse(plan.prefer_gpu)

    def test_successful_plan_resolution_command_and_capability_injection(self):
        worker = self.make_worker()
        self.install_successful_run(worker)
        build = Mock(wraps=worker.ffmpeg.build_plan_command)
        worker.ffmpeg.build_plan_command = build

        worker.run()

        self.assertEqual(self.failed, [])
        self.assertEqual(len(self.finished), 1)
        self.assertEqual(worker.encoding_plan.resolution_mode, ResolutionMode.P1080)
        self.assertAlmostEqual(worker.encoding_plan.resolved_fps, 60000 / 1001, places=5)
        self.assertFalse(worker.encoding_plan.cfr_required)
        self.assertTrue(build.called)
        self.assertEqual(
            build.call_args.kwargs["capabilities"],
            self.hardware.capabilities,
        )
        self.assertEqual(
            build.call_args.kwargs["pipeline"],
            "gpu",
        )
        self.assertTrue(Path(self.finished[0]).is_file())

    def test_fractional_fps_and_vfr_policy_reach_plan(self):
        self.input_analysis = analyzed_media(
            rate="60000/1001",
            average="30000/1001",
        )
        self.output_analysis = analyzed_media(
            width=1920,
            height=1080,
            rate="30000/1001",
        )
        self.media_probe.stop()
        self.media_probe = patch(
            "app.workers.compression_worker.MediaInfo.probe",
            side_effect=[self.input_analysis, self.output_analysis],
        )
        self.media_probe.start()
        self.addCleanup(self.media_probe.stop)
        worker = self.make_worker()
        self.install_successful_run(worker)
        worker.run()
        self.assertAlmostEqual(
            worker.encoding_plan.resolved_fps,
            30000 / 1001,
            places=5,
        )
        self.assertTrue(worker.encoding_plan.cfr_required)

    def test_hevc_unavailable_has_specific_error_no_h264_fallback(self):
        caps = HardwareCapabilities(
            available_encoders=("libx264",),
        )
        worker = self.make_worker(
            preset_id="fast_web_social",
            capabilities=caps,
        )
        preset = get_preset("fast_web_social")
        preset.codec = "hevc"
        worker.preset = preset
        worker.run()
        self.assertTrue(any("HEVC NVENC is unavailable" in error for error in self.failed))
        self.assertEqual(self.finished, [])

    def test_av1_unavailable_has_specific_error(self):
        worker = self.make_worker(
            capabilities=HardwareCapabilities(
                available_encoders=("libx264",),
            )
        )
        preset = get_preset("fast_web_social")
        preset.codec = "av1"
        worker.preset = preset
        worker.run()
        self.assertTrue(
            any(
                "AV1 NVENC is unavailable in the installed FFmpeg build"
                in error
                for error in self.failed
            )
        )

    def test_software_only_environment_uses_requested_cpu_codec(self):
        self.output_analysis = analyzed_media(
            width=1920,
            height=1080,
            codec="hevc",
        )
        self.media_probe.stop()
        self.media_probe = patch(
            "app.workers.compression_worker.MediaInfo.probe",
            side_effect=[self.input_analysis, self.output_analysis],
        )
        self.media_probe.start()
        self.addCleanup(self.media_probe.stop)
        worker = self.make_worker(
            use_gpu=False,
            capabilities=HardwareCapabilities(
                available_encoders=("libx264", "libx265")
            ),
        )
        preset = get_preset("fast_web_social")
        preset.codec = "hevc"
        worker.preset = preset
        self.install_successful_run(worker)
        commands = []

        def capture_command(command, **kwargs):
            commands.append(command)
            return self.succeed_and_write(worker, command, **kwargs)

        worker.ffmpeg.run = capture_command
        worker.run()
        self.assertEqual(len(self.finished), 1)
        self.assertEqual(commands[0][commands[0].index("-c:v") + 1], "libx265")

    def test_audio_copy_and_aac_fallback_intent_are_preserved(self):
        worker = self.make_worker()
        self.install_successful_run(worker)
        worker.run()
        self.assertEqual(worker.encoding_plan.audio_mode, AudioMode.COPY)
        self.assertEqual(
            worker.encoding_plan.audio_fallback_mode,
            AudioMode.AAC,
        )
        self.assertEqual(
            worker.encoding_plan.audio_fallback_bitrate,
            192_000,
        )

    def test_incompatible_audio_is_resolved_to_aac_before_command_build(self):
        self.input_analysis = analyzed_media(audio_codec="opus")
        self.media_probe.stop()
        self.media_probe = patch(
            "app.workers.compression_worker.MediaInfo.probe",
            side_effect=[self.input_analysis, self.output_analysis],
        )
        self.media_probe.start()
        worker = self.make_worker()
        self.install_successful_run(worker)
        worker.run()
        self.assertEqual(worker.encoding_plan.audio_mode, AudioMode.AAC)
        self.assertEqual(worker.encoding_plan.audio_bitrate, 192_000)
        self.assertEqual(worker.encoding_plan.sample_rate, 48_000)
        self.assertEqual(worker.encoding_plan.channel_count, 2)

    def test_explicit_legacy_fps_setting_resolves_to_cfr(self):
        self.output_analysis = analyzed_media(
            width=1920,
            height=1080,
            rate="30000/1001",
        )
        self.media_probe.stop()
        self.media_probe = patch(
            "app.workers.compression_worker.MediaInfo.probe",
            side_effect=[self.input_analysis, self.output_analysis],
        )
        self.media_probe.start()
        self.addCleanup(self.media_probe.stop)
        preset = get_preset("fast_web_social")
        preset.fps = "29.97"
        worker = self.make_worker()
        worker.preset = preset
        self.install_successful_run(worker)
        worker.run()
        self.assertEqual(worker.encoding_plan.fps_mode, FPSMode.CFR)
        self.assertAlmostEqual(worker.encoding_plan.resolved_fps, 29.97)
        self.assertTrue(worker.encoding_plan.cfr_required)

    def test_cancellation_never_emits_success_or_keeps_partial(self):
        worker = self.make_worker()

        def cancel_during_encode(command, **_kwargs):
            Path(command[-1]).write_bytes(b"partial output")
            worker.cancel()
            return 0

        worker.ffmpeg.run = cancel_during_encode
        worker.run()
        self.assertEqual(self.finished, [])
        self.assertEqual(self.cancelled, [True])
        self.assertFalse(worker.working_output_file.exists())

    def test_failed_encode_and_missing_output_do_not_emit_success(self):
        worker = self.make_worker()
        worker.ffmpeg.run = lambda *_args, **_kwargs: 1
        worker.run()
        self.assertEqual(self.finished, [])
        self.assertTrue(any("code 1" in error for error in self.failed))

        self.media_probe.stop()
        self.media_probe = patch(
            "app.workers.compression_worker.MediaInfo.probe",
            side_effect=[self.input_analysis, self.output_analysis],
        )
        self.media_probe.start()
        worker = self.make_worker()
        worker.ffmpeg.run = lambda *_args, **_kwargs: 0
        worker.run()
        self.assertEqual(self.finished, [])
        self.assertTrue(any("validation" in error.lower() for error in self.failed))

    def test_overwrite_protection_and_safe_overwrite_finalization(self):
        self.output.write_bytes(b"existing")
        protected = self.make_worker(overwrite=False)
        self.install_successful_run(protected)
        protected.run()
        self.assertEqual(self.failed, ["Output file already exists:\n" + str(self.output)])
        self.assertEqual(self.output.read_bytes(), b"existing")

        self.media_probe.stop()
        self.media_probe = patch(
            "app.workers.compression_worker.MediaInfo.probe",
            side_effect=[self.input_analysis, self.output_analysis],
        )
        self.media_probe.start()
        overwrite_worker = self.make_worker(overwrite=True)
        self.install_successful_run(overwrite_worker)
        overwrite_worker.run()
        self.assertEqual(len(self.finished), 1)
        self.assertEqual(self.output.read_bytes(), b"encoded-output")

    def test_container_extension_and_partial_names_are_unique(self):
        self.output_analysis = analyzed_media(
            width=1920,
            height=1080,
            codec="prores",
        )
        self.media_probe.stop()
        self.media_probe = patch(
            "app.workers.compression_worker.MediaInfo.probe",
            side_effect=[self.input_analysis, self.output_analysis],
        )
        self.media_probe.start()
        self.addCleanup(self.media_probe.stop)
        first = self.make_worker(preset_id="prores_proxy")
        first_finished = self.finished
        second = self.make_worker(preset_id="prores_proxy")
        self.assertEqual(first.output_file.suffix, ".mp4")
        self.assertNotEqual(
            first.working_output_file,
            second.working_output_file,
        )
        self.install_successful_run(first)
        first.run()
        self.assertEqual(first.output_file.suffix, ".mov")
        self.assertEqual(first.output_file, Path(first_finished[0]))

    def test_container_change_avoids_existing_output_name(self):
        self.output_analysis = analyzed_media(
            width=1920,
            height=1080,
            codec="prores",
        )
        self.media_probe.stop()
        self.media_probe = patch(
            "app.workers.compression_worker.MediaInfo.probe",
            side_effect=[self.input_analysis, self.output_analysis],
        )
        self.media_probe.start()
        self.addCleanup(self.media_probe.stop)
        occupied = self.root / "encoded.mov"
        occupied.write_bytes(b"existing")
        worker = self.make_worker(
            preset_id="prores_proxy",
            output=self.root / "encoded.mp4",
        )
        self.install_successful_run(worker)
        worker.run()
        self.assertEqual(worker.output_file, self.root / "encoded_1.mov")
        self.assertEqual(occupied.read_bytes(), b"existing")
        self.assertTrue(worker.output_file.exists())

    def test_hdr_policy_flows_and_unsupported_tone_map_fails_clearly(self):
        self.media_probe.stop()
        self.media_probe = patch(
            "app.workers.compression_worker.MediaInfo.probe",
            side_effect=[
                self.input_analysis,
                analyzed_media(
                    width=1920,
                    height=1080,
                    codec="hevc",
                ),
            ],
        )
        self.media_probe.start()
        self.addCleanup(self.media_probe.stop)
        preset = get_preset("fast_web_social")
        preset.hdr_mode = HDRMode.PRESERVE
        preset.codec = "hevc"
        worker = self.make_worker()
        worker.preset = preset
        self.install_successful_run(worker)
        worker.run()
        self.assertEqual(worker.encoding_plan.hdr_mode, HDRMode.PRESERVE)

        self.media_probe.stop()
        self.media_probe = patch(
            "app.workers.compression_worker.MediaInfo.probe",
            side_effect=[self.input_analysis],
        )
        self.media_probe.start()
        tone_map = get_preset("fast_web_social")
        tone_map.hdr_mode = HDRMode.TONE_MAP_SDR
        worker = self.make_worker(output=self.root / "tone-map.mp4")
        worker.preset = tone_map
        worker.run()
        self.assertEqual(self.finished, [])
        self.assertTrue(
            any("tone mapping is not yet implemented" in error.lower()
                for error in self.failed)
        )

    def test_hdr_output_validation_requires_10bit_and_matching_transfer(self):
        hdr_source = MediaAnalysis.from_ffprobe({
            "streams": [{
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "24/1",
                "avg_frame_rate": "24/1",
                "pix_fmt": "yuv420p10le",
                "color_primaries": "bt2020",
                "color_transfer": "smpte2084",
                "color_space": "bt2020nc",
            }]
        })
        preset = get_preset("fast_web_social")
        preset.hdr_mode = HDRMode.PRESERVE
        preset.codec = "hevc"
        worker = self.make_worker()
        worker.preset = preset
        worker.media_analysis = hdr_source
        worker.encoding_plan = worker._resolve_plan()

        valid_output = MediaAnalysis.from_ffprobe({
            "streams": [{
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuv420p10le",
                "color_primaries": "bt2020",
                "color_transfer": "smpte2084",
                "color_space": "bt2020nc",
            }]
        })
        self.assertTrue(worker._validate_hdr_output(valid_output))

        sdr_output = MediaAnalysis.from_ffprobe({
            "streams": [{
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuv420p",
                "color_primaries": "bt709",
                "color_transfer": "bt709",
                "color_space": "bt709",
            }]
        })
        self.assertFalse(worker._validate_hdr_output(sdr_output))
        self.assertIn("not at least 10-bit", worker._output_validation_error)

    def test_output_validation_rejects_container_mismatch(self):
        worker = self.make_worker()
        worker.media_analysis = self.input_analysis
        worker.encoding_plan = worker._resolve_plan()
        worker.working_output_file.write_bytes(b"encoded-output")
        mismatched_output = MediaAnalysis.from_ffprobe({
            "format": {
                "format_name": "matroska,webm",
                "duration": "10",
            },
            "streams": [{
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "60000/1001",
                "avg_frame_rate": "60000/1001",
                "pix_fmt": "yuv420p",
                "color_transfer": "bt709",
            }, {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "channel_layout": "stereo",
            }],
        })
        with patch(
            "app.workers.compression_worker.MediaInfo.probe",
            return_value=mismatched_output,
        ):
            self.assertFalse(worker.validate_output())
        self.assertIn("container does not match", worker._output_validation_error)


if __name__ == "__main__":
    unittest.main()
