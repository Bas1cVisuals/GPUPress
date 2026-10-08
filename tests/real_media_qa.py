"""Opt-in generated-media integration QA; run with unittest discovery explicitly."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from app.core.encoding_plan import (
    AudioMode,
    Codec,
    FPSMode,
    HDRMode,
    ResolutionMode,
    UserEncodingOptions,
    create_encoding_plan,
)
from app.core.ffmpeg import EncodingPipeline
from app.core.hardware import HardwareInfo
from app.core.media import FrameRateType, HDRClassification, MediaAnalysis, MediaInfo
from app.workers.compression_worker import CompressionWorker


ROOT = Path(__file__).resolve().parents[1]


class GeneratedRealMediaQATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = ROOT / "bin" / "ffmpeg.exe"
        cls.ffprobe = ROOT / "bin" / "ffprobe.exe"
        if not cls.ffmpeg.is_file() or not cls.ffprobe.is_file():
            raise unittest.SkipTest("Bundled FFmpeg/FFprobe are unavailable.")
        cls.hardware = HardwareInfo()
        cls.capabilities = cls.hardware.get_capabilities()
        cls.temporary = tempfile.TemporaryDirectory(prefix="gpupress-media-qa-")
        cls.work = Path(cls.temporary.name)
        cls.tested_media: set[str] = set()
        cls.tested_codecs: set[str] = set()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
        print("Generated media cases tested:", ", ".join(sorted(cls.tested_media)))
        print("Encoder paths tested:", ", ".join(sorted(cls.tested_codecs)))

    @classmethod
    def run_ffmpeg(cls, arguments):
        result = subprocess.run(
            [str(cls.ffmpeg), "-hide_banner", "-loglevel", "error", "-y", *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode:
            raise AssertionError(
                f"FFmpeg exited {result.returncode}: {result.stderr.strip()}"
            )

    @classmethod
    def probe(cls, path):
        media = MediaInfo(cls.ffprobe).probe(path)
        if not media or media.video is None:
            raise AssertionError(f"FFprobe could not open {path}")
        return media

    @classmethod
    def create_h264(cls, path, rate, width=640, height=360, audio=True):
        arguments = [
            "-f", "lavfi",
            "-i", f"testsrc2=size={width}x{height}:rate={rate}:duration=1.2",
        ]
        if audio:
            arguments += [
                "-f", "lavfi",
                "-i", "sine=frequency=440:sample_rate=48000:duration=1.2",
                "-map", "0:v:0", "-map", "1:a:0",
            ]
        arguments += [
            "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
        ]
        if audio:
            arguments += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
        arguments.append(str(path))
        cls.run_ffmpeg(arguments)

    @classmethod
    def encode_with_worker(cls, input_path, output_path, options, analysis=None):
        worker = CompressionWorker(
            input_file=input_path,
            output_file=output_path,
            preset=options,
            use_gpu=options.prefer_gpu,
            allow_cpu_fallback=options.allow_cpu_fallback,
            hardware=cls.hardware,
            media_analysis=analysis,
        )
        finished = []
        failed = []
        cancelled = []
        worker.compression_finished.connect(finished.append)
        worker.compression_failed.connect(failed.append)
        worker.compression_cancelled.connect(lambda: cancelled.append(True))
        worker.run()
        if cancelled:
            raise AssertionError("Unexpected cancellation in generated-media QA.")
        if failed:
            raise AssertionError("; ".join(failed))
        if len(finished) != 1:
            raise AssertionError("Worker did not report exactly one success.")
        output = Path(finished[0])
        if not output.is_file() or output.stat().st_size <= 0:
            raise AssertionError("Worker returned a missing/empty output.")
        return output, worker.encoding_plan

    def test_generated_fractional_and_vfr_media_through_worker(self):
        for rate, label in (
            ("24000/1001", "23.976"),
            ("30000/1001", "29.97"),
            ("60000/1001", "59.94"),
            ("60/1", "60"),
        ):
            with self.subTest(rate=rate):
                source = self.work / f"source_{label}.mp4"
                target = self.work / f"fps_{label}.mp4"
                self.create_h264(source, rate)
                analyzed = self.probe(source)
                self.assertEqual(analyzed.video.frame_rate_type, FrameRateType.CFR)
                options = UserEncodingOptions(
                    codec=Codec.H264,
                    resolution_mode=ResolutionMode.SOURCE,
                    fps_mode=FPSMode.SMART,
                    audio_mode=AudioMode.AUTO,
                    prefer_gpu=False,
                    encoder_preset="ultrafast",
                    quality=28,
                )
                output, plan = self.encode_with_worker(
                    source, target, options, analyzed
                )
                output_media = self.probe(output)
                self.assertAlmostEqual(
                    output_media.video.average_frame_rate,
                    float(rate.split("/")[0]) / float(rate.split("/")[1]),
                    delta=0.08,
                )
                self.assertEqual(output_media.audio.codec_name, "aac")
                self.assertEqual(plan.cfr_required, False)
                self.tested_media.add(f"CFR {label} FPS + H.264 + AAC")
                self.tested_codecs.add("libx264")

        vfr_source = self.work / "source_vfr.mkv"
        self.run_ffmpeg([
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10:duration=1",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=1",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-fps_mode", "vfr",
            "-c:v", "libx264", "-preset", "ultrafast", str(vfr_source),
        ])
        vfr_analysis = self.probe(vfr_source)
        self.assertEqual(vfr_analysis.video.frame_rate_type, FrameRateType.VFR)
        self.assertIsNotNone(vfr_analysis.video.average_frame_rate)
        vfr_output, vfr_plan = self.encode_with_worker(
            vfr_source,
            self.work / "vfr_cfr.mp4",
            UserEncodingOptions(
                codec=Codec.H264,
                resolution_mode=ResolutionMode.SOURCE,
                fps_mode=FPSMode.SMART,
                audio_mode=AudioMode.COPY,
                prefer_gpu=False,
                encoder_preset="ultrafast",
                quality=28,
            ),
            vfr_analysis,
        )
        actual = self.probe(vfr_output)
        self.assertTrue(vfr_plan.cfr_required)
        self.assertAlmostEqual(
            actual.video.average_frame_rate,
            vfr_plan.resolved_fps,
            delta=0.15,
        )
        self.assertGreater(actual.duration, 1.8)
        self.assertLess(actual.duration, 2.5)
        self.tested_media.add("irregular-timestamp VFR → deterministic CFR")
        self.tested_codecs.add("libx264")

    def test_generated_orientation_resolution_and_no_upscale(self):
        cases = (
            (1920, 1080, "landscape"),
            (1080, 1920, "portrait"),
            (1080, 1080, "square"),
        )
        for width, height, label in cases:
            with self.subTest(orientation=label):
                source = self.work / f"{label}.mp4"
                self.create_h264(source, "24/1", width, height, audio=False)
                analysis = self.probe(source)
                plan = create_encoding_plan(
                    analysis,
                    UserEncodingOptions(
                        codec=Codec.H264,
                        resolution_mode=ResolutionMode.P1080,
                        fps_mode=FPSMode.SMART,
                        prefer_gpu=False,
                    ),
                )
                self.assertEqual(
                    (plan.output_width, plan.output_height),
                    (width, height),
                )
                self.assertLessEqual(plan.output_width, width)
                self.assertLessEqual(plan.output_height, height)
                self.tested_media.add(f"generated 1080p {label} SDR")

        unrotated = self.work / "landscape_track.mp4"
        rotated = self.work / "portrait_display.mp4"
        self.create_h264(unrotated, "24/1", 640, 360, audio=False)
        self.run_ffmpeg([
            "-display_rotation:v:0", "90",
            "-i", str(unrotated),
            "-c", "copy",
            str(rotated),
        ])
        rotated_analysis = self.probe(rotated)
        self.assertEqual(rotated_analysis.video.rotation_degrees, 90)
        self.assertEqual(
            (rotated_analysis.video.width, rotated_analysis.video.height),
            (360, 640),
        )
        rotated_output, _ = self.encode_with_worker(
            rotated,
            self.work / "portrait_display_output.mp4",
            UserEncodingOptions(
                codec=Codec.H264,
                resolution_mode=ResolutionMode.P1080,
                fps_mode=FPSMode.SMART,
                prefer_gpu=False,
                encoder_preset="ultrafast",
            ),
            rotated_analysis,
        )
        rotated_output_analysis = self.probe(rotated_output)
        self.assertEqual(
            (rotated_output_analysis.video.width, rotated_output_analysis.video.height),
            (360, 640),
        )
        self.tested_media.add("rotated display-matrix portrait video")

        for width, height, label in (
            (3840, 2160, "landscape"),
            (2160, 3840, "portrait"),
        ):
            with self.subTest(orientation_4k=label):
                source = self.work / f"4k_{label}.mkv"
                self.run_ffmpeg([
                    "-f", "lavfi",
                    "-i", f"color=c=black:s={width}x{height}:r=1:d=1",
                    "-frames:v", "1",
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", str(source),
                ])
                analysis = self.probe(source)
                self.assertEqual(
                    (analysis.video.width, analysis.video.height),
                    (width, height),
                )
                output, _ = self.encode_with_worker(
                    source,
                    self.work / f"4k_{label}_1080p.mp4",
                    UserEncodingOptions(
                        codec=Codec.H264,
                        resolution_mode=ResolutionMode.P1080,
                        fps_mode=FPSMode.SMART,
                        prefer_gpu=False,
                        encoder_preset="ultrafast",
                    ),
                    analysis,
                )
                output_analysis = self.probe(output)
                expected = (1920, 1080) if width > height else (1080, 1920)
                self.assertEqual(
                    (output_analysis.video.width, output_analysis.video.height),
                    expected,
                )
                self.assertAlmostEqual(
                    output_analysis.video.aspect_ratio,
                    width / height,
                )
                self.tested_media.add(f"generated 4K {label} → 1080p")

        source = self.work / "small_720.mp4"
        self.create_h264(source, "24/1", 640, 360, audio=False)
        analysis = self.probe(source)
        for mode in (ResolutionMode.P720, ResolutionMode.SOURCE):
            plan = create_encoding_plan(
                analysis,
                UserEncodingOptions(
                    codec=Codec.H264,
                    resolution_mode=mode,
                    fps_mode=FPSMode.SMART,
                ),
            )
            self.assertEqual((plan.output_width, plan.output_height), (640, 360))
        custom_no_upscale = create_encoding_plan(
            analysis,
            UserEncodingOptions(
                codec=Codec.H264,
                resolution_mode=ResolutionMode.CUSTOM,
                custom_width=1280,
                custom_height=720,
                prevent_upscale=True,
            ),
        )
        custom_upscale = create_encoding_plan(
            analysis,
            UserEncodingOptions(
                codec=Codec.H264,
                resolution_mode=ResolutionMode.CUSTOM,
                custom_width=1280,
                custom_height=720,
                prevent_upscale=False,
            ),
        )
        self.assertEqual((custom_no_upscale.output_width, custom_no_upscale.output_height), (640, 360))
        self.assertEqual((custom_upscale.output_width, custom_upscale.output_height), (1280, 720))
        self.tested_media.add("720p no-upscale and custom upscale intent")

    def test_audio_auto_copy_and_incompatible_fallback(self):
        aac_source = self.work / "audio_aac.mp4"
        self.create_h264(aac_source, "30/1")
        aac_analysis = self.probe(aac_source)
        copy_plan = create_encoding_plan(
            aac_analysis,
            UserEncodingOptions(codec=Codec.H264, audio_mode=AudioMode.AUTO),
        )
        self.assertEqual(copy_plan.audio_mode, AudioMode.COPY)
        copied, _ = self.encode_with_worker(
            aac_source,
            self.work / "audio_copy.mp4",
            UserEncodingOptions(codec=Codec.H264, prefer_gpu=False, encoder_preset="ultrafast"),
            aac_analysis,
        )
        self.assertEqual(self.probe(copied).audio.codec_name, "aac")

        opus_source = self.work / "audio_opus.mkv"
        self.run_ffmpeg([
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=700:sample_rate=48000:duration=1",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "libopus", str(opus_source),
        ])
        opus_analysis = self.probe(opus_source)
        fallback_plan = create_encoding_plan(
            opus_analysis,
            UserEncodingOptions(codec=Codec.H264, container="mp4"),
        )
        self.assertEqual(fallback_plan.audio_mode, AudioMode.AAC)
        converted, _ = self.encode_with_worker(
            opus_source,
            self.work / "audio_fallback.mp4",
            UserEncodingOptions(
                codec=Codec.H264,
                container="mp4",
                audio_mode=AudioMode.AUTO,
                prefer_gpu=False,
                encoder_preset="ultrafast",
            ),
            opus_analysis,
        )
        converted_media = self.probe(converted)
        self.assertEqual(converted_media.audio.codec_name, "aac")
        self.assertEqual(converted_media.audio.sample_rate, 48_000)
        self.assertEqual(converted_media.audio.channels, 2)
        self.tested_media.update({"AAC audio copy", "Opus audio → AAC fallback"})
        self.tested_codecs.add("libx264")

    def test_hdr10_and_hlg_signaling_survive_hevc_reencode(self):
        for transfer, label, classification in (
            ("smpte2084", "hdr10", HDRClassification.PQ),
            ("arib-std-b67", "hlg", HDRClassification.HLG),
        ):
            with self.subTest(hdr=label):
                source = self.work / f"{label}_source.mkv"
                self.run_ffmpeg([
                    "-f", "lavfi",
                    "-i", "testsrc2=size=320x180:rate=24:duration=1",
                    "-vf", "format=yuv420p10le",
                    "-c:v", "libx265", "-preset", "ultrafast",
                    "-x265-params",
                    (
                        "log-level=error:colorprim=9:transfer="
                        f"{16 if transfer == 'smpte2084' else 18}:colormatrix=9"
                    ),
                    "-pix_fmt", "yuv420p10le",
                    str(source),
                ])
                source_analysis = self.probe(source)
                self.assertEqual(
                    source_analysis.video.hdr_classification,
                    classification,
                )
                self.assertGreaterEqual(source_analysis.video.bit_depth, 10)
                output, plan = self.encode_with_worker(
                    source,
                    self.work / f"{label}_preserved.mkv",
                    UserEncodingOptions(
                        codec=Codec.HEVC,
                        resolution_mode=ResolutionMode.SOURCE,
                        hdr_mode=HDRMode.AUTO,
                        prefer_gpu=False,
                        encoder_preset="ultrafast",
                        quality=28,
                    ),
                    source_analysis,
                )
                output_analysis = self.probe(output)
                self.assertEqual(plan.hdr_mode, HDRMode.PRESERVE)
                self.assertEqual(
                    output_analysis.video.hdr_classification,
                    classification,
                )
                self.assertGreaterEqual(output_analysis.video.bit_depth, 10)
                self.assertEqual(
                    output_analysis.video.color_primaries, "bt2020"
                )
                self.assertEqual(output_analysis.video.color_transfer, transfer)
                self.assertEqual(output_analysis.video.color_space, "bt2020nc")
                self.tested_media.add(f"synthetic {label.upper()} signaling + 10-bit")
                self.tested_codecs.add("libx265 10-bit HDR preservation")

    def test_real_worker_codec_matrix(self):
        source = self.work / "codec_source.mp4"
        self.create_h264(source, "30000/1001")
        analysis = self.probe(source)
        codec_cases = [
            (Codec.H264, "libx264", False, "mp4"),
            (Codec.HEVC, "libx265", False, "mp4"),
            (Codec.PRORES_PROXY, "prores_ks", False, "mov"),
            (Codec.DNXHR_LB, "dnxhd", False, "mov"),
        ]
        for codec, label, use_gpu, container in (
            (Codec.H264, "h264_nvenc", True, "mp4"),
            (Codec.HEVC, "hevc_nvenc", True, "mp4"),
            (Codec.AV1, "av1_nvenc", True, "mp4"),
        ):
            capability = {
                Codec.H264: self.capabilities.h264_nvenc,
                Codec.HEVC: self.capabilities.hevc_nvenc,
                Codec.AV1: self.capabilities.av1_nvenc,
            }[codec]
            if capability:
                codec_cases.append((codec, label, use_gpu, container))

        completed_labels = []
        for codec, encoder_label, use_gpu, container in codec_cases:
            with self.subTest(encoder=encoder_label):
                options = UserEncodingOptions(
                    codec=codec,
                    resolution_mode=ResolutionMode.SOURCE,
                    fps_mode=FPSMode.SMART,
                    audio_mode=AudioMode.AUTO,
                    container=container,
                    prefer_gpu=use_gpu,
                    allow_cpu_fallback=not use_gpu,
                    encoder_preset="p5" if use_gpu else "ultrafast",
                    quality=30,
                )
                output, _ = self.encode_with_worker(
                    source,
                    self.work / f"codec_{encoder_label}.{container}",
                    options,
                    analysis,
                )
                actual = self.probe(output)
                expected_codec = {
                    Codec.H264: "h264",
                    Codec.HEVC: "hevc",
                    Codec.AV1: "av1",
                    Codec.PRORES_PROXY: "prores",
                    Codec.DNXHR_LB: "dnxhd",
                }[codec]
                self.assertEqual(actual.video.codec_name, expected_codec)
                self.assertEqual(actual.audio.codec_name, "aac")
                self.assertAlmostEqual(actual.duration, analysis.duration, delta=0.2)
                completed_labels.append(encoder_label)
                self.tested_codecs.add(encoder_label)
        self.assertGreaterEqual(len(completed_labels), 4)
        self.tested_media.add("worker end-to-end codec output/container/audio validation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
