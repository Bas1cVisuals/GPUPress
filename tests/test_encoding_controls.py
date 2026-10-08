import unittest

from app.core.encoding_plan import (
    AudioMode,
    Codec,
    FPSMode,
    HDRMode,
    HardwareCapabilities,
    RateControl,
    ResolutionMode,
    create_encoding_plan,
)
from app.core.media import MediaAnalysis
from app.ui.encoding_controls import (
    adaptive_control_visibility,
    build_user_options,
    codec_choices,
    containers_for_codec,
    format_media_summary,
    format_plan_summary,
)
from app.ui.settings_widget import SettingsManager


def make_media(
    width=3840,
    height=2160,
    nominal="60000/1001",
    average="60000/1001",
    color_transfer="bt709",
):
    return MediaAnalysis.from_ffprobe({
        "streams": [{
            "codec_type": "video",
            "codec_name": "hevc",
            "width": width,
            "height": height,
            "r_frame_rate": nominal,
            "avg_frame_rate": average,
            "pix_fmt": "yuv420p10le",
            "color_transfer": color_transfer,
        }, {
            "codec_type": "audio",
            "codec_name": "aac",
            "sample_rate": "48000",
            "channels": 2,
            "channel_layout": "stereo",
        }],
        "format": {"duration": "32", "size": "1000"},
    })


class EncodingControlTests(unittest.TestCase):
    def test_codec_availability_requires_detected_usable_nvenc(self):
        software_only = HardwareCapabilities(
            available_encoders=("libx264", "libx265", "prores_ks", "dnxhd")
        )
        keys = {choice.key for choice in codec_choices(software_only)}
        self.assertNotIn("av1_nvenc", keys)
        self.assertNotIn("h264_nvenc", keys)
        self.assertIn("h264_software", keys)
        self.assertIn("prores_proxy", keys)

        nvenc = HardwareCapabilities(
            nvidia_available=True,
            h264_nvenc=True,
            hevc_nvenc=True,
            av1_nvenc=False,
            available_encoders=(
                "h264_nvenc", "hevc_nvenc", "libx264", "libx265",
                "prores_ks", "dnxhd",
            ),
        )
        keys = {choice.key for choice in codec_choices(nvenc)}
        self.assertIn("h264_nvenc", keys)
        self.assertIn("hevc_nvenc", keys)
        self.assertNotIn("av1_nvenc", keys)

    def test_resolution_intent_is_resolved_by_core_for_orientation(self):
        options = build_user_options(
            codec_key="h264_software",
            resolution_mode=ResolutionMode.P1080,
            fps_value="smart",
        )
        landscape = create_encoding_plan(make_media(), options)
        portrait = create_encoding_plan(make_media(2160, 3840), options)
        square = create_encoding_plan(make_media(1080, 1080), options)
        self.assertEqual((landscape.output_width, landscape.output_height), (1920, 1080))
        self.assertEqual((portrait.output_width, portrait.output_height), (1080, 1920))
        self.assertEqual((square.output_width, square.output_height), (1080, 1080))

    def test_smart_fps_does_not_default_to_30_and_vfr_requests_cfr(self):
        source_options = build_user_options(
            codec_key="h264_software",
            resolution_mode=ResolutionMode.SOURCE,
            fps_value="smart",
        )
        source_plan = create_encoding_plan(make_media(), source_options)
        self.assertAlmostEqual(source_plan.resolved_fps, 60000 / 1001)
        self.assertFalse(source_plan.cfr_required)

        vfr_plan = create_encoding_plan(
            make_media(average="30000/1001"),
            source_options,
        )
        self.assertTrue(vfr_plan.cfr_required)
        self.assertAlmostEqual(vfr_plan.resolved_fps, 30000 / 1001)

        explicit = build_user_options(
            codec_key="h264_software",
            resolution_mode=ResolutionMode.SOURCE,
            fps_value="59.94",
        )
        self.assertEqual(explicit.fps_mode, FPSMode.CUSTOM)
        self.assertAlmostEqual(
            create_encoding_plan(make_media(), explicit).resolved_fps,
            59.94,
        )

    def test_audio_modes_hdr_and_custom_rate_controls_are_typed(self):
        auto = build_user_options(
            codec_key="h264_software",
            resolution_mode=ResolutionMode.SOURCE,
            fps_value="smart",
            audio_mode=AudioMode.AUTO,
            hdr_mode=HDRMode.PRESERVE,
        )
        plan = create_encoding_plan(make_media(), auto)
        self.assertEqual(plan.audio_mode, AudioMode.COPY)
        self.assertEqual(plan.hdr_mode, HDRMode.PRESERVE)

        aac = build_user_options(
            codec_key="h264_software",
            resolution_mode=ResolutionMode.SOURCE,
            fps_value="smart",
            audio_mode=AudioMode.AAC,
            audio_bitrate="192k",
            rate_control=RateControl.CBR,
            bitrate=8_000_000,
        )
        self.assertEqual(aac.audio_bitrate, 192_000)
        self.assertEqual(aac.rate_control, RateControl.CBR)
        self.assertEqual(aac.bitrate, 8_000_000)

    def test_container_choices_adapt_to_intermediate_codecs(self):
        self.assertEqual(containers_for_codec(Codec.PRORES_PROXY), ("mov", "mkv"))
        with self.assertRaises(ValueError):
            build_user_options(
                codec_key="prores_proxy",
                resolution_mode=ResolutionMode.SOURCE,
                container="mp4",
            )
        options = build_user_options(
            codec_key="prores_proxy",
            resolution_mode=ResolutionMode.SOURCE,
        )
        self.assertEqual(options.container, "mov")

    def test_dynamic_visibility_matches_codec_and_custom_intent(self):
        prores = adaptive_control_visibility(
            codec=Codec.PRORES_PROXY,
            nvenc=False,
            resolution_mode="custom",
            fps_value="custom",
            rate_control=RateControl.CQ.value,
            audio_mode=AudioMode.AAC.value,
        )
        self.assertTrue(prores["custom_resolution"])
        self.assertTrue(prores["custom_fps"])
        self.assertFalse(prores["quality"])
        self.assertFalse(prores["rate_control"])
        self.assertFalse(prores["gop"])
        self.assertFalse(prores["nvenc_preset"])
        self.assertTrue(prores["audio_encoding"])

        nvenc = adaptive_control_visibility(
            codec=Codec.H264,
            nvenc=True,
            resolution_mode="1080p",
            fps_value="smart",
            rate_control=RateControl.CQ.value,
            audio_mode=AudioMode.COPY.value,
        )
        self.assertTrue(nvenc["nvenc_preset"])
        self.assertTrue(nvenc["cq_value"])
        self.assertFalse(nvenc["audio_encoding"])

    def test_plan_summary_uses_resolved_plan(self):
        options = build_user_options(
            codec_key="h264_software",
            resolution_mode=ResolutionMode.P1080,
            fps_value="smart",
            audio_mode=AudioMode.COPY,
        )
        plan = create_encoding_plan(make_media(), options)
        summary = format_plan_summary(plan, encoder_label="H.264 Software")
        self.assertIn("1920 × 1080", summary)
        self.assertIn("59.94 FPS", summary)
        self.assertIn("Audio copy", summary)

    def test_source_summary_uses_analyzed_media_fields(self):
        summary = format_media_summary(
            make_media(
                average="30000/1001",
                color_transfer="smpte2084",
            )
        )
        self.assertIn("3840 × 2160", summary)
        self.assertIn("Landscape · 16:9", summary)
        self.assertIn("10-bit", summary)
        self.assertIn("Pixel format: yuv420p10le", summary)
        self.assertIn("VFR source — output will use deterministic CFR", summary)
        self.assertIn("HDR10 / PQ", summary)
        self.assertIn("AAC · 48 kHz · Stereo", summary)

    def test_new_settings_defaults_do_not_force_30_fps(self):
        defaults = SettingsManager.DEFAULT_SETTINGS
        self.assertEqual(defaults["video"]["fps_mode"], "smart")
        self.assertEqual(defaults["video"]["resolution_mode"], "1080p")
        self.assertEqual(defaults["audio"]["mode"], "auto")

    def test_settings_merge_retains_legacy_values_and_adds_new_intent_defaults(self):
        legacy = SettingsManager._migrate_legacy_settings({
            "video": {"codec": "hevc", "fps": "30", "max_resolution": "2560"},
            "audio": {"codec": "copy"},
        })
        merged = SettingsManager._deep_merge(SettingsManager.DEFAULT_SETTINGS, legacy)
        self.assertEqual(merged["video"]["codec"], "hevc")
        self.assertEqual(merged["video"]["fps_mode"], "smart")
        self.assertEqual(merged["video"]["resolution_mode"], "1440p")
        self.assertEqual(merged["video"]["codec_choice"], "hevc_nvenc")
        self.assertEqual(merged["audio"]["codec"], "copy")
        self.assertEqual(merged["audio"]["mode"], "copy")
        aac_default = SettingsManager._migrate_legacy_settings(
            {"audio": {"codec": "aac"}}
        )
        self.assertEqual(aac_default["audio"]["mode"], "auto")


if __name__ == "__main__":
    unittest.main()
