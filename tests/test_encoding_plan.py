import unittest
from fractions import Fraction

from app.core.encoding_plan import (
    AudioMode,
    Codec,
    EncodingPlan,
    FPSMode,
    HDRPreservationError,
    HDRMode,
    ResolutionMode,
    UserEncodingOptions,
    create_encoding_plan,
    resolve_dimensions,
    resolve_frame_rate,
)
from app.core.media import (
    MediaAnalysis,
)


def make_media(
    width=3840,
    height=2160,
    nominal="60000/1001",
    average="60000/1001",
):
    analysis = MediaAnalysis.from_ffprobe(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "width": width,
                    "height": height,
                    "r_frame_rate": nominal,
                    "avg_frame_rate": average,
                    "pix_fmt": "yuv420p",
                }
            ]
        }
    )
    return analysis


class ResolutionPolicyTests(unittest.TestCase):
    def test_1080p_landscape(self):
        self.assertEqual(
            resolve_dimensions(3840, 2160, ResolutionMode.P1080),
            (1920, 1080),
        )

    def test_1080p_portrait(self):
        self.assertEqual(
            resolve_dimensions(2160, 3840, ResolutionMode.P1080),
            (1080, 1920),
        )

    def test_square_source(self):
        self.assertEqual(
            resolve_dimensions(1080, 1080, ResolutionMode.P1080),
            (1080, 1080),
        )

    def test_no_upscale(self):
        self.assertEqual(
            resolve_dimensions(
                1280,
                720,
                ResolutionMode.P1080,
                prevent_upscale=True,
            ),
            (1280, 720),
        )

    def test_source_and_custom_modes(self):
        self.assertEqual(
            resolve_dimensions(3840, 2160, ResolutionMode.SOURCE),
            (3840, 2160),
        )
        self.assertEqual(
            resolve_dimensions(
                1920,
                1080,
                ResolutionMode.CUSTOM,
                custom_width=1280,
                custom_height=720,
            ),
            (1280, 720),
        )

    def test_named_sizes_are_explicit_canvas_targets(self):
        self.assertEqual(
            resolve_dimensions(3840, 2160, ResolutionMode.P720),
            (1280, 720),
        )
        self.assertEqual(
            resolve_dimensions(3840, 2160, ResolutionMode.P1440),
            (2560, 1440),
        )
        self.assertEqual(
            resolve_dimensions(3840, 2160, ResolutionMode.P2160),
            (3840, 2160),
        )

    def test_invalid_custom_target_rejected(self):
        with self.assertRaises(ValueError):
            resolve_dimensions(1920, 1080, ResolutionMode.CUSTOM)


class FrameRatePolicyTests(unittest.TestCase):
    def test_auto_preserves_cfr_source_rates(self):
        for rate in ("60000/1001", "30/1", "25/1"):
            with self.subTest(rate=rate):
                resolved = resolve_frame_rate(
                    make_media(nominal=rate, average=rate),
                    FPSMode.AUTO,
                )
                self.assertAlmostEqual(
                    resolved.fps,
                    float(Fraction(rate)),
                    places=5,
                )
                self.assertFalse(resolved.cfr_required)

    def test_auto_normalizes_vfr_at_observed_average_rate(self):
        resolved = resolve_frame_rate(
            make_media(nominal="60000/1001", average="30000/1001"),
            FPSMode.AUTO,
        )
        self.assertEqual(resolved.fps, 30000 / 1001)
        self.assertTrue(resolved.cfr_required)

    def test_source_mode_does_not_force_cfr(self):
        resolved = resolve_frame_rate(
            make_media(nominal="60/1", average="30000/1001"),
            FPSMode.SOURCE,
        )
        self.assertAlmostEqual(resolved.fps, 30000 / 1001, places=5)
        self.assertFalse(resolved.cfr_required)

    def test_explicit_cfr_and_custom_modes(self):
        self.assertEqual(
            resolve_frame_rate(
                make_media(), FPSMode.CFR, target_fps=30
            ).fps,
            30,
        )
        self.assertTrue(
            resolve_frame_rate(
                make_media(), FPSMode.CFR, target_fps=30
            ).cfr_required
        )
        self.assertEqual(
            resolve_frame_rate(
                make_media(), FPSMode.CUSTOM, custom_fps=23.976
            ).fps,
            23.976,
        )

    def test_missing_fps_is_not_assumed_to_be_30(self):
        resolved = resolve_frame_rate(
            make_media(nominal="0/0", average="0/0"),
            FPSMode.AUTO,
        )
        self.assertIsNone(resolved.fps)
        self.assertFalse(resolved.cfr_required)


class PlanTests(unittest.TestCase):
    def test_defaults_resolve_audio_and_hdr_intent(self):
        plan = create_encoding_plan(make_media())
        self.assertEqual(plan.audio_mode, AudioMode.COPY)
        self.assertEqual(plan.hdr_mode, HDRMode.PRESERVE)
        self.assertEqual(plan.codec, Codec.H264)

    def test_auto_audio_uses_aac_fallback_for_incompatible_mp4_source(self):
        incompatible = MediaAnalysis.from_ffprobe(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "width": 1920,
                        "height": 1080,
                        "r_frame_rate": "30/1",
                        "avg_frame_rate": "30/1",
                    },
                    {
                        "codec_type": "audio",
                        "codec_name": "opus",
                        "sample_rate": "44100",
                        "channels": 6,
                    },
                ]
            }
        )
        plan = create_encoding_plan(incompatible)
        self.assertEqual(plan.audio_mode, AudioMode.AAC)
        self.assertEqual(plan.audio_bitrate, 192_000)
        self.assertEqual(plan.sample_rate, 48_000)
        self.assertEqual(plan.channel_count, 2)

    def test_explicit_audio_copy_intent_is_not_overridden(self):
        incompatible = MediaAnalysis.from_ffprobe(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "width": 1920,
                        "height": 1080,
                        "r_frame_rate": "30/1",
                        "avg_frame_rate": "30/1",
                    },
                    {"codec_type": "audio", "codec_name": "opus"},
                ]
            }
        )
        plan = create_encoding_plan(
            incompatible,
            UserEncodingOptions(audio_mode=AudioMode.COPY),
        )
        self.assertEqual(plan.audio_mode, AudioMode.COPY)

    def test_hdr_auto_and_preserve_retain_source_signaling(self):
        hdr = MediaAnalysis.from_ffprobe({
            "streams": [{
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "24000/1001",
                "avg_frame_rate": "24000/1001",
                "pix_fmt": "yuv420p10le",
                "color_primaries": "bt2020",
                "color_transfer": "smpte2084",
                "color_space": "bt2020nc",
                "side_data_list": [{
                    "side_data_type": "Mastering display metadata",
                }],
            }]
        })
        options = UserEncodingOptions(codec=Codec.HEVC)
        automatic = create_encoding_plan(hdr, options)
        explicit = create_encoding_plan(
            hdr,
            UserEncodingOptions(codec=Codec.HEVC, hdr_mode=HDRMode.PRESERVE),
        )
        for plan in (automatic, explicit):
            self.assertEqual(plan.hdr_mode, HDRMode.PRESERVE)
            self.assertEqual(plan.source_color_transfer, "smpte2084")
            self.assertEqual(
                plan.source_hdr_metadata_types,
                ("Mastering display metadata",),
            )

    def test_hdr_cannot_be_silently_encoded_as_8bit_or_tone_mapped(self):
        hdr = MediaAnalysis.from_ffprobe({
            "streams": [{
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuv420p10le",
                "color_transfer": "arib-std-b67",
            }]
        })
        with self.assertRaisesRegex(HDRPreservationError, "cannot safely preserve HDR"):
            create_encoding_plan(
                hdr,
                UserEncodingOptions(codec=Codec.H264, hdr_mode=HDRMode.PRESERVE),
            )
        with self.assertRaisesRegex(HDRPreservationError, "tone mapping is not yet implemented"):
            create_encoding_plan(
                hdr,
                UserEncodingOptions(codec=Codec.HEVC, hdr_mode=HDRMode.TONE_MAP_SDR),
            )

    def test_dolby_vision_metadata_does_not_claim_reencode_preservation(self):
        dolby = MediaAnalysis.from_ffprobe({
            "streams": [{
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuv420p10le",
                "color_transfer": "smpte2084",
                "tags": {"DOVI": "configuration record"},
            }]
        })
        with self.assertRaisesRegex(HDRPreservationError, "Dolby Vision dynamic metadata"):
            create_encoding_plan(
                dolby,
                UserEncodingOptions(codec=Codec.HEVC),
            )

    def test_resolved_plan_carries_controls_and_serializes(self):
        options = UserEncodingOptions(
            codec=Codec.HEVC,
            resolution_mode=ResolutionMode.CUSTOM,
            custom_width=1280,
            custom_height=720,
            fps_mode=FPSMode.CUSTOM,
            custom_fps=29.97,
            audio_mode=AudioMode.AAC,
            audio_bitrate=192_000,
            sample_rate=48_000,
            channel_count=2,
            prefer_gpu=False,
            allow_cpu_fallback=True,
            preserve_metadata=False,
            faststart=False,
        )
        plan = create_encoding_plan(make_media(), options)
        self.assertIsInstance(plan, EncodingPlan)
        self.assertEqual((plan.output_width, plan.output_height), (1280, 720))
        self.assertEqual(plan.resolved_fps, 29.97)
        self.assertTrue(plan.cfr_required)
        self.assertFalse(plan.prefer_gpu)
        self.assertEqual(plan.to_dict()["codec"], "hevc")
        self.assertEqual(plan.to_dict()["audio_mode"], "aac")
        self.assertIn("EncodingPlan", repr(plan))

    def test_planning_requires_video_dimensions(self):
        with self.assertRaises(ValueError):
            create_encoding_plan(MediaAnalysis())


if __name__ == "__main__":
    unittest.main()
