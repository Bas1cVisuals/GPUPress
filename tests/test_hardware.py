import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.hardware import HardwareInfo


ENCODER_LIST = """\
 V....D h264_nvenc NVIDIA NVENC H.264 encoder
 V....D hevc_nvenc NVIDIA NVENC HEVC encoder
 V....D av1_nvenc NVIDIA NVENC AV1 encoder
 V....D libx264 libx264 H.264 / AVC
 V....D libx265 libx265 H.265 / HEVC
 V....D prores_ks Apple ProRes
 V....D dnxhd VC3/DNxHD
"""
DECODER_LIST = """\
 V....D h264_cuvid Nvidia CUVID H264 decoder
 V....D hevc_cuvid Nvidia CUVID HEVC decoder
"""


def make_hardware(outputs, gpu_name=None):
    temporary = tempfile.TemporaryDirectory()
    executable = Path(temporary.name) / "ffmpeg.exe"
    executable.touch()

    def fake_run(arguments):
        if "-version" in arguments:
            return "ffmpeg version test"
        if "-encoders" in arguments:
            return outputs.get("encoders", "")
        if "-decoders" in arguments:
            return outputs.get("decoders", "")
        if "-hwaccels" in arguments:
            return outputs.get("hwaccels", "")
        if "-filters" in arguments:
            return outputs.get("filters", "")
        return ""

    with (
        patch.object(HardwareInfo, "_get_ffmpeg_path", return_value=executable),
        patch.object(HardwareInfo, "_run_ffmpeg", side_effect=fake_run),
        patch.object(
            HardwareInfo,
            "_detect_nvidia_gpu_name",
            return_value=gpu_name,
        ),
    ):
        hardware = HardwareInfo()
    temporary.cleanup()
    return hardware


class HardwareCapabilityTests(unittest.TestCase):
    def test_no_nvidia_keeps_software_capabilities(self):
        hardware = make_hardware(
            {"encoders": " V....D libx264 H.264 encoder\n"}
        )
        self.assertFalse(hardware.nvidia_available)
        self.assertFalse(hardware.nvenc)
        self.assertFalse(hardware.cuda)
        self.assertIn("libx264", hardware.available_encoders)
        self.assertFalse(hardware.get_capabilities().available_encoders == ())

    def test_nvenc_h264_and_hevc_detection(self):
        hardware = make_hardware(
            {"encoders": ENCODER_LIST},
            gpu_name="Detected NVIDIA GPU",
        )
        self.assertTrue(hardware.nvidia_available)
        self.assertEqual(hardware.gpu_name, "Detected NVIDIA GPU")
        self.assertTrue(hardware.nvenc)
        self.assertTrue(hardware.h264_nvenc)
        self.assertTrue(hardware.hevc_nvenc)

    def test_av1_requires_actual_encoder_listing(self):
        has_av1 = make_hardware({"encoders": ENCODER_LIST})
        self.assertTrue(has_av1.av1_nvenc)
        self.assertIn("av1_nvenc", has_av1.get_capabilities().available_encoders)

        without_av1 = make_hardware(
            {"encoders": ENCODER_LIST.replace(
                " V....D av1_nvenc NVIDIA NVENC AV1 encoder\n", ""
            )}
        )
        self.assertFalse(without_av1.av1_nvenc)

    def test_cuda_and_nvdec_detection(self):
        hardware = make_hardware(
            {
                "encoders": ENCODER_LIST,
                "hwaccels": "Hardware acceleration methods:\nCUDA\n",
                "decoders": DECODER_LIST,
                "filters": " ... scale_cuda V->V CUDA video scaling\n",
            },
        )
        self.assertTrue(hardware.cuda)
        self.assertTrue(hardware.scale_cuda)
        self.assertTrue(hardware.nvdec_available)

    def test_missing_or_malformed_capability_output_fails_safely(self):
        hardware = make_hardware(
            {
                "encoders": "malformed listing without encoder entries",
                "hwaccels": "not a capability list",
                "decoders": "",
                "filters": "",
            }
        )
        self.assertFalse(hardware.nvenc)
        self.assertFalse(hardware.cuda)
        self.assertEqual(hardware.available_encoders, ())
        self.assertEqual(hardware.ffmpeg_version, "ffmpeg version test")

    def test_ffmpeg_executable_failure_fails_safely(self):
        temporary = tempfile.TemporaryDirectory()
        executable = Path(temporary.name) / "ffmpeg.exe"
        executable.touch()
        with (
            patch.object(HardwareInfo, "_get_ffmpeg_path", return_value=executable),
            patch(
                "app.core.hardware.subprocess.run",
                side_effect=OSError("not executable"),
            ),
            patch.object(HardwareInfo, "_detect_nvidia_gpu_name", return_value=None),
        ):
            hardware = HardwareInfo()
        temporary.cleanup()
        self.assertEqual(hardware.ffmpeg_version, "Unknown")
        self.assertFalse(hardware.nvenc)
        self.assertFalse(hardware.nvidia_available)
        self.assertEqual(hardware.get_capabilities().available_encoders, ())

    def test_missing_ffmpeg_produces_software_only_capability(self):
        with patch.object(
            HardwareInfo,
            "_get_ffmpeg_path",
            return_value=Path("missing-ffmpeg.exe"),
        ):
            hardware = HardwareInfo()
        self.assertFalse(hardware.ffmpeg_exists)
        self.assertFalse(hardware.nvenc)
        self.assertFalse(hardware.cuda)
        self.assertEqual(hardware.available_encoders, ())


if __name__ == "__main__":
    unittest.main()
