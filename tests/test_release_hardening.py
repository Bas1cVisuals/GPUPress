import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import __version__
from app.core.hardware import HardwareInfo
from app.ui.settings_widget import SettingsManager


ROOT = Path(__file__).resolve().parents[1]


class ReleaseVersionTests(unittest.TestCase):
    def test_release_version_is_consistent_in_runtime_and_installer(self):
        installer = (ROOT / "installer" / "GPUPress.iss").read_text(
            encoding="utf-8"
        )
        installer_builder = (ROOT / "build_installer.py").read_text(
            encoding="utf-8"
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertEqual(__version__, "0.1.0")
        self.assertIn('#define AppVersion "0.1.0"', installer)
        self.assertIn("VersionInfoVersion=0.1.0.0", installer)
        self.assertIn("GPUPress-Setup-v0.1.0", installer)
        self.assertIn("GPUPress-Setup-v0.1.0.exe", installer_builder)
        self.assertIn("# GPUPress 0.1.0", readme)
        self.assertNotIn("v1.0.0", installer + installer_builder + readme)


class PortablePathTests(unittest.TestCase):
    def test_frozen_ffmpeg_path_prefers_bundle_relative_bin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundled = root / "bundle" / "bin"
            bundled.mkdir(parents=True)
            executable = bundled / "ffmpeg.exe"
            executable.touch()
            app_executable = root / "installed" / "GPUPress.exe"
            app_executable.parent.mkdir()
            app_executable.touch()

            instance = HardwareInfo.__new__(HardwareInfo)
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "_MEIPASS", str(root / "bundle"), create=True),
                patch.object(sys, "executable", str(app_executable)),
            ):
                self.assertEqual(instance._get_ffmpeg_path(), executable)

    def test_frozen_settings_use_user_config_and_local_data_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "local-data"
            config = root / "roaming-config"
            with (
                patch.object(sys, "frozen", True, create=True),
                patch(
                    "app.ui.settings_widget.QStandardPaths.writableLocation",
                    side_effect=[str(data), str(config)],
                ),
            ):
                manager = SettingsManager()

            self.assertEqual(manager.root_dir, data)
            self.assertEqual(manager.config_dir, config)
            self.assertEqual(manager.config_file, config / "settings.json")
            self.assertEqual(
                manager.settings["general"]["output_folder"],
                "Compressed",
            )


class SettingsRecoveryTests(unittest.TestCase):
    def test_missing_and_malformed_settings_use_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = SettingsManager(root)
            self.assertEqual(
                manager.settings,
                SettingsManager.DEFAULT_SETTINGS,
            )

            manager.config_dir.mkdir(parents=True)
            manager.config_file.write_text("{ invalid json", encoding="utf-8")
            self.assertEqual(
                manager.load(),
                SettingsManager.DEFAULT_SETTINGS,
            )

            manager.config_file.write_text("[]", encoding="utf-8")
            self.assertEqual(
                manager.load(),
                SettingsManager.DEFAULT_SETTINGS,
            )

    def test_save_replaces_settings_file_and_leaves_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = SettingsManager(Path(directory))
            settings = json.loads(json.dumps(SettingsManager.DEFAULT_SETTINGS))
            settings["general"]["output_folder"] = "Custom Output"

            manager.save(settings)

            self.assertEqual(
                json.loads(manager.config_file.read_text(encoding="utf-8")),
                settings,
            )
            self.assertFalse(manager.config_file.with_suffix(".tmp").exists())


if __name__ == "__main__":
    unittest.main()
