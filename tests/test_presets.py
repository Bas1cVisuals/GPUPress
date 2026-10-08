import unittest

from app.core.encoding_plan import (
    AudioMode,
    Codec,
    FPSMode,
    HDRMode,
    HardwareCapabilities,
    RateControl,
    ResolutionMode,
)
from app.core.media import MediaAnalysis
from app.core.presets import (
    PRESETS,
    CompressionPreset,
    ContainerPreference,
    get_preset,
)


def make_media(width=3840, height=2160):
    return MediaAnalysis.from_ffprobe(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "hevc",
                    "width": width,
                    "height": height,
                    "r_frame_rate": "60000/1001",
                    "avg_frame_rate": "60000/1001",
                    "pix_fmt": "yuv420p10le",
                }
            ]
        }
    )


class PresetTests(unittest.TestCase):
    def test_every_preset_has_valid_typed_intent(self):
        for preset_id, preset in PRESETS.items():
            with self.subTest(preset=preset_id):
                self.assertIsInstance(preset, CompressionPreset)
                self.assertIsInstance(preset.codec_intent, Codec)
                self.assertIsInstance(preset.resolution_mode, ResolutionMode)
                self.assertIsInstance(preset.fps_mode, FPSMode)
                self.assertIsInstance(preset.audio_intent, AudioMode)
                self.assertIsInstance(preset.hdr_mode, HDRMode)
                self.assertIsInstance(preset.to_user_options().codec, Codec)
                plan = preset.to_encoding_plan(
                    make_media(),
                    HardwareCapabilities(),
                )
                self.assertGreater(plan.output_width, 0)
                self.assertGreater(plan.output_height, 0)

    def test_delivery_presets_preserve_smart_source_fps_and_audio_copy(self):
        for preset_id in (
            "fast_web_social",
            "high_quality_delivery",
            "small_file_delivery",
        ):
            preset = PRESETS[preset_id]
            self.assertEqual(preset.fps_mode, FPSMode.SMART)
            self.assertNotEqual(preset.target_fps, 30)
            self.assertEqual(preset.audio_intent, AudioMode.AUTO)
            self.assertEqual(preset.audio_fallback_mode, AudioMode.AAC)
            self.assertEqual(preset.audio_fallback_sample_rate, 48_000)
        self.assertEqual(
            PRESETS["fast_web_social"].audio_fallback_bitrate,
            192_000,
        )

    def test_editing_and_proxy_presets(self):
        proxy_720 = PRESETS["h264_proxy_720p"]
        proxy_1080 = PRESETS["h264_proxy_1080p"]
        fast_scrub = PRESETS["fast_scrub_h264"]
        self.assertEqual(proxy_720.resolution_mode, ResolutionMode.P720)
        self.assertEqual(proxy_1080.resolution_mode, ResolutionMode.P1080)
        self.assertEqual(fast_scrub.codec_intent, Codec.H264)
        self.assertEqual(fast_scrub.rate_control, RateControl.CBR)
        self.assertEqual(fast_scrub.gop_size, 15)
        self.assertEqual(fast_scrub.fps_mode, FPSMode.SMART)
        self.assertFalse(fast_scrub.allow_upscale)

    def test_intermediate_presets_use_codec_profiles_not_quality_values(self):
        expected = {
            "prores_proxy": Codec.PRORES_PROXY,
            "prores_lt": Codec.PRORES_LT,
            "prores_422": Codec.PRORES_422,
            "dnxhr_lb": Codec.DNXHR_LB,
            "dnxhr_sq": Codec.DNXHR_SQ,
            "dnxhr_hq": Codec.DNXHR_HQ,
        }
        for preset_id, codec in expected.items():
            with self.subTest(preset=preset_id):
                preset = PRESETS[preset_id]
                self.assertEqual(preset.codec_intent, codec)
                self.assertIsNone(preset.quality)
                self.assertEqual(preset.container, ContainerPreference.MOV)
                self.assertFalse(preset.prefer_gpu)

    def test_source_quality_and_hdr_intent(self):
        preset = PRESETS["original_source_quality"]
        self.assertEqual(preset.resolution_mode, ResolutionMode.SOURCE)
        self.assertEqual(preset.hdr_mode, HDRMode.PRESERVE)
        self.assertEqual(preset.fps_mode, FPSMode.SMART)
        plan = preset.to_encoding_plan(make_media())
        self.assertEqual((plan.output_width, plan.output_height), (3840, 2160))

    def test_resolution_tier_is_adaptive_to_orientation_and_aspect(self):
        preset = PRESETS["fast_web_social"]
        self.assertEqual(
            (
                preset.to_encoding_plan(make_media()).output_width,
                preset.to_encoding_plan(make_media()).output_height,
            ),
            (1920, 1080),
        )
        portrait = preset.to_encoding_plan(make_media(2160, 3840))
        self.assertEqual((portrait.output_width, portrait.output_height), (1080, 1920))
        square = preset.to_encoding_plan(make_media(1080, 1080))
        self.assertEqual((square.output_width, square.output_height), (1080, 1080))
        ultrawide = preset.to_encoding_plan(make_media(2560, 1080))
        self.assertEqual((ultrawide.output_width, ultrawide.output_height), (1920, 810))

    def test_smart_fps_keeps_5994_source(self):
        plan = PRESETS["fast_web_social"].to_encoding_plan(make_media())
        self.assertAlmostEqual(plan.resolved_fps, 60000 / 1001, places=5)
        self.assertFalse(plan.cfr_required)

    def test_audio_copy_has_aac_fallback_intent_in_plan(self):
        plan = PRESETS["fast_web_social"].to_encoding_plan(make_media())
        self.assertEqual(plan.audio_mode, AudioMode.COPY)
        self.assertEqual(plan.audio_fallback_mode, AudioMode.AAC)
        self.assertEqual(plan.audio_fallback_bitrate, 192_000)
        self.assertEqual(plan.audio_fallback_sample_rate, 48_000)
        self.assertEqual(plan.audio_fallback_channel_count, 2)

    def test_legacy_worker_fields_and_fresh_instances(self):
        first = get_preset("reel_1080p")
        second = get_preset("reel_1080p")
        self.assertEqual(first.max_dimension, 1920)
        self.assertEqual(first.fps, "original")
        self.assertEqual(first.codec, "h264")
        first.cq = 40
        self.assertEqual(second.cq, 18)
        self.assertEqual(get_preset("not-a-preset").name, "Reel — 1080p")


if __name__ == "__main__":
    unittest.main()
