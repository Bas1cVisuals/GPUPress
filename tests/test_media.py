import unittest

from app.core.media import (
    AudioStreamInfo,
    FrameRateType,
    HDRClassification,
    MediaAnalysis,
    MediaInfo,
    Orientation,
    _classify_timestamps,
    parse_frame_rate,
)


class FrameRateParsingTests(unittest.TestCase):
    def test_rational_rates(self):
        cases = (
            ("30000/1001", 29.97002997),
            ("60000/1001", 59.94005994),
            ("24000/1001", 23.97602398),
            ("30/1", 30.0),
            ("60/1", 60.0),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertAlmostEqual(parse_frame_rate(value), expected, places=5)

    def test_invalid_rates_return_none(self):
        for value in (None, "", "0/0", "0/1", "n/a", "-25/1"):
            with self.subTest(value=value):
                self.assertIsNone(parse_frame_rate(value))


class MediaAnalysisTests(unittest.TestCase):
    def analyze_video(self, **overrides):
        stream = {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "pix_fmt": "yuv420p",
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "color_space": "bt709",
            "color_transfer": "bt709",
            "color_primaries": "bt709",
        }
        stream.update(overrides)
        return MediaAnalysis.from_ffprobe({"streams": [stream]})

    def test_aspect_ratio_and_orientation(self):
        landscape = self.analyze_video().video
        self.assertEqual(landscape.orientation, Orientation.LANDSCAPE)
        self.assertAlmostEqual(landscape.aspect_ratio, 16 / 9)

        portrait = self.analyze_video(width=1080, height=1920).video
        self.assertEqual(portrait.orientation, Orientation.PORTRAIT)
        self.assertAlmostEqual(portrait.aspect_ratio, 1080 / 1920)

        square = self.analyze_video(width=1080, height=1080).video
        self.assertEqual(square.orientation, Orientation.SQUARE)
        self.assertEqual(square.aspect_ratio, 1.0)

    def test_display_matrix_rotation_updates_display_dimensions(self):
        portrait = self.analyze_video(
            width=1920,
            height=1080,
            side_data_list=[{
                "side_data_type": "Display Matrix",
                "rotation": -90,
            }],
        ).video
        self.assertEqual((portrait.width, portrait.height), (1080, 1920))
        self.assertEqual((portrait.coded_width, portrait.coded_height), (1920, 1080))
        self.assertEqual(portrait.rotation_degrees, -90)
        self.assertEqual(portrait.orientation, Orientation.PORTRAIT)

        unchanged = self.analyze_video(
            side_data_list=[{
                "side_data_type": "Display Matrix",
                "rotation": 180,
            }],
        ).video
        self.assertEqual((unchanged.width, unchanged.height), (1920, 1080))
        self.assertEqual(unchanged.orientation, Orientation.LANDSCAPE)

        malformed = self.analyze_video(
            side_data_list=[{
                "side_data_type": "Display Matrix",
                "rotation": "nan",
            }],
        ).video
        self.assertIsNone(malformed.rotation_degrees)
        self.assertEqual((malformed.width, malformed.height), (1920, 1080))

    def test_bit_depth_inference(self):
        expected = {
            "yuv420p": 8,
            "yuv420p10le": 10,
            "p010le": 10,
            "gbrp12le": 12,
        }
        for pixel_format, depth in expected.items():
            with self.subTest(pixel_format=pixel_format):
                self.assertEqual(
                    self.analyze_video(pix_fmt=pixel_format).video.bit_depth,
                    depth,
                )
        self.assertIsNone(self.analyze_video(pix_fmt="mystery").video.bit_depth)

    def test_hdr_classification(self):
        hlg = self.analyze_video(color_transfer="arib-std-b67").video
        self.assertEqual(hlg.hdr_classification, HDRClassification.HLG)

        pq = self.analyze_video(color_transfer="smpte2084").video
        self.assertEqual(pq.hdr_classification, HDRClassification.PQ)

        sdr = self.analyze_video(color_transfer="bt709").video
        self.assertEqual(sdr.hdr_classification, HDRClassification.SDR)

        unknown_hdr = self.analyze_video(
            color_transfer="unknown",
            color_primaries="bt2020",
        ).video
        self.assertEqual(
            unknown_hdr.hdr_classification,
            HDRClassification.HDR_UNKNOWN,
        )

        dolby = self.analyze_video(
            side_data_list=[{"side_data_type": "DOVI configuration record"}],
        ).video
        self.assertEqual(
            dolby.hdr_classification,
            HDRClassification.DOLBY_VISION,
        )

        unknown = self.analyze_video(
            color_transfer="",
            color_primaries="",
            color_space="",
        ).video
        self.assertEqual(unknown.hdr_classification, HDRClassification.UNKNOWN)

    def test_cfr_vfr_and_unknown_classification(self):
        cfr = self.analyze_video(
            r_frame_rate="60000/1001",
            avg_frame_rate="60000/1001",
        ).video
        self.assertEqual(cfr.frame_rate_type, FrameRateType.CFR)
        self.assertFalse(cfr.is_vfr)
        self.assertAlmostEqual(cfr.frame_rate, 59.94005994, places=5)

        vfr = self.analyze_video(
            r_frame_rate="60/1",
            avg_frame_rate="30000/1001",
        ).video
        self.assertEqual(vfr.frame_rate_type, FrameRateType.VFR)
        self.assertTrue(vfr.is_vfr)

        unknown = self.analyze_video(avg_frame_rate="0/0").video
        self.assertEqual(unknown.frame_rate_type, FrameRateType.UNKNOWN)
        self.assertIsNone(unknown.is_vfr)

    def test_timestamp_sample_detects_vfr_and_tolerates_muxer_rounding(self):
        cfr, avg = _classify_timestamps(
            [i / 24.0 for i in range(48)]
        )
        self.assertEqual(cfr, FrameRateType.CFR)
        self.assertAlmostEqual(avg, 24.0)

        rounded_cfr, _ = _classify_timestamps(
            [round(i / 24.0, 3) for i in range(20)]
        )
        self.assertEqual(rounded_cfr, FrameRateType.CFR)

        vfr, average = _classify_timestamps(
            [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9,
             1.0, 1.033, 1.067, 1.1, 1.133, 1.167, 1.2, 1.233]
        )
        self.assertEqual(vfr, FrameRateType.VFR)
        self.assertIsNotNone(average)

    def test_audio_and_format_parsing(self):
        analysis = MediaAnalysis.from_ffprobe(
            {
                "format": {
                    "format_name": "mov,mp4",
                    "duration": "12.5",
                    "size": "1000",
                },
                "streams": [
                    {
                        "codec_type": "audio",
                        "codec_name": "aac",
                        "sample_rate": "48000",
                        "channels": 2,
                        "channel_layout": "stereo",
                        "duration": "12.4",
                    }
                ],
            }
        )
        self.assertEqual(analysis.format_name, "mov,mp4")
        self.assertEqual(analysis.duration, 12.5)
        self.assertEqual(analysis.size, 1000)
        self.assertEqual(
            analysis.audio,
            AudioStreamInfo(
                codec_name="aac",
                sample_rate=48000,
                channels=2,
                channel_layout="stereo",
                duration=12.4,
            ),
        )

    def test_legacy_helpers_accept_structured_results(self):
        analysis = self.analyze_video()
        self.assertEqual(MediaInfo.video_stream(analysis).codec_name, "h264")
        self.assertEqual(MediaInfo.duration(analysis), 0.0)
        self.assertEqual(analysis.get("format", {}).get("format_name"), None)


if __name__ == "__main__":
    unittest.main()
