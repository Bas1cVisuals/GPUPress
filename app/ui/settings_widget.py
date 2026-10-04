from pathlib import Path
import json
import logging
import os
import sys

from PySide6.QtCore import (
    QStandardPaths,
    Qt,
)
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SettingsManager:
    """
    Persistent GPUPress settings manager.

    Development settings are stored in:
        config/settings.json

    Packaged settings use the user's application config directory.
    """

    DEFAULT_SETTINGS = {
        "general": {
            "output_folder": "Compressed",
            "remember_settings": True,
            "auto_open_output": False,
            "overwrite_existing": False,
        },
        "video": {
            "codec": "h264",
            "cq": 18,
            "max_resolution": "1920",
            "fps": "30",
            "nvenc_preset": "p6",
            "preserve_aspect_ratio": True,
        },
        "audio": {
            "codec": "aac",
            "bitrate": "192k",
            "sample_rate": 48000,
            "channels": "2",
        },
        "processing": {
            "gpu_acceleration": True,
            "cpu_fallback": True,
            "faststart": True,
            "copy_metadata": True,
        },
    }

    def __init__(self, root_dir=None):

        root_was_provided = root_dir is not None

        if root_dir is None:
            if getattr(sys, "frozen", False):
                root_location = (
                    QStandardPaths.writableLocation(
                        QStandardPaths.StandardLocation.AppLocalDataLocation
                    )
                )

                if not root_location:
                    root_location = str(
                        Path(
                            os.environ.get(
                                "LOCALAPPDATA",
                                Path.home() / "AppData" / "Local",
                            )
                        )
                        / "BAS1C VISUALS"
                        / "GPUPress"
                    )

                root_dir = Path(root_location)
            else:
                root_dir = (
                    Path(__file__)
                    .resolve()
                    .parents[2]
                )

        self.root_dir = Path(root_dir)

        if (
            getattr(sys, "frozen", False)
            and not root_was_provided
        ):
            config_location = (
                QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.AppConfigLocation
                )
            )

            if not config_location:
                config_location = str(
                    Path(
                        os.environ.get(
                            "APPDATA",
                            Path.home() / "AppData" / "Roaming",
                        )
                    )
                    / "BAS1C VISUALS"
                    / "GPUPress"
                )

            self.config_dir = Path(config_location)
        else:
            self.config_dir = (
                self.root_dir / "config"
            )

        self.config_file = (
            self.config_dir / "settings.json"
        )

        self.settings = self.load()

    @staticmethod
    def _deep_merge(defaults, saved):

        result = {}

        for key, default_value in defaults.items():

            if (
                key in saved
                and isinstance(default_value, dict)
                and isinstance(saved[key], dict)
            ):
                result[key] = (
                    SettingsManager._deep_merge(
                        default_value,
                        saved[key],
                    )
                )

            elif key in saved:
                saved_value = saved[key]

                if isinstance(default_value, dict):
                    result[key] = default_value
                elif isinstance(saved_value, type(default_value)):
                    result[key] = saved_value
                else:
                    result[key] = default_value

            else:
                result[key] = default_value

        return result

    def load(self):

        defaults = json.loads(
            json.dumps(
                self.DEFAULT_SETTINGS
            )
        )

        if not self.config_file.exists():
            return defaults

        try:

            with self.config_file.open(
                "r",
                encoding="utf-8",
            ) as file:

                saved = json.load(file)

            if not isinstance(saved, dict):
                logging.warning(
                    "Ignoring invalid GPUPress settings in %s: "
                    "expected a JSON object",
                    self.config_file,
                )
                return defaults

            settings = self._deep_merge(
                defaults,
                saved,
            )

            if not settings["general"]["remember_settings"]:
                defaults["general"]["remember_settings"] = False
                return defaults

            return settings

        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            logging.warning(
                "Could not load GPUPress settings from %s: %s",
                self.config_file,
                error,
            )
            return defaults

    def save(self, settings=None):

        if settings is not None:
            self.settings = settings

        self.config_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_file = (
            self.config_file.with_suffix(
                ".tmp"
            )
        )

        with temporary_file.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                self.settings,
                file,
                indent=4,
            )

        temporary_file.replace(
            self.config_file
        )

    def reset(self):

        self.settings = json.loads(
            json.dumps(
                self.DEFAULT_SETTINGS
            )
        )

        self.save()

        return self.settings


class SectionHeader(QLabel):

    def __init__(
        self,
        title,
        description="",
        parent=None,
    ):
        super().__init__(parent)

        if description:
            self.setText(
                f"{title}\n{description}"
            )
        else:
            self.setText(title)

        self.setProperty(
            "settingsSectionHeader",
            True,
        )

        self.setWordWrap(True)


class SettingsDialog(QDialog):
    """
    Dedicated GPUPress Settings dialog.

    The existing ? Guide dialog remains
    completely separate.
    """

    settings_saved = None

    def __init__(
        self,
        parent=None,
        settings_manager=None,
    ):
        super().__init__(parent)

        self.setWindowTitle(
            "GPUPress — Settings"
        )

        self.setModal(True)

        self.resize(
            760,
            720,
        )

        self.settings_manager = (
            settings_manager
            or SettingsManager()
        )

        self.settings = json.loads(
            json.dumps(
                self.settings_manager.settings
            )
        )

        self._build_ui()
        self._load_settings_into_ui()
        self._apply_styles()

    # =========================================================
    # BUILD UI
    # =========================================================

    def _build_ui(self):

        root_layout = QVBoxLayout(self)

        root_layout.setContentsMargins(
            24,
            22,
            24,
            18,
        )

        root_layout.setSpacing(14)

        # -----------------------------------------------------
        # Header
        # -----------------------------------------------------

        header_layout = QHBoxLayout()

        title_layout = QVBoxLayout()

        title_layout.setSpacing(3)

        title = QLabel("Settings")

        title.setProperty(
            "settingsTitle",
            True,
        )

        subtitle = QLabel(
            "Configure GPUPress defaults and processing behaviour."
        )

        subtitle.setProperty(
            "settingsSubtitle",
            True,
        )

        subtitle.setWordWrap(True)

        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        header_layout.addLayout(
            title_layout,
            1,
        )

        close_button = QPushButton("×")

        close_button.setFixedSize(
            36,
            36,
        )

        close_button.setProperty(
            "settingsCloseButton",
            True,
        )

        close_button.clicked.connect(
            self.reject
        )

        header_layout.addWidget(
            close_button,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        root_layout.addLayout(
            header_layout
        )

        # -----------------------------------------------------
        # Separator
        # -----------------------------------------------------

        separator = QFrame()

        separator.setFrameShape(
            QFrame.Shape.HLine
        )

        separator.setProperty(
            "settingsSeparator",
            True,
        )

        root_layout.addWidget(
            separator
        )

        # -----------------------------------------------------
        # Scroll Area
        # -----------------------------------------------------

        scroll = QScrollArea()

        scroll.setWidgetResizable(True)

        scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        content = QWidget()

        content_layout = QVBoxLayout(
            content
        )

        content_layout.setContentsMargins(
            4,
            4,
            10,
            12,
        )

        content_layout.setSpacing(18)

        # =====================================================
        # GENERAL
        # =====================================================

        content_layout.addWidget(
            SectionHeader(
                "General",
                "Default file and application behaviour.",
            )
        )

        general_box = QGroupBox()

        general_layout = QFormLayout(
            general_box
        )

        general_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )

        general_layout.setHorizontalSpacing(
            30
        )

        general_layout.setVerticalSpacing(
            13
        )

        self.output_folder_edit = QLabel()

        self.output_folder_edit.setProperty(
            "settingsPathLabel",
            True,
        )

        browse_button = QPushButton(
            "Browse…"
        )

        browse_button.clicked.connect(
            self.browse_output_folder
        )

        output_row = QWidget()

        output_row_layout = QHBoxLayout(
            output_row
        )

        output_row_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        output_row_layout.setSpacing(8)

        output_row_layout.addWidget(
            self.output_folder_edit,
            1,
        )

        output_row_layout.addWidget(
            browse_button
        )

        general_layout.addRow(
            "Default output folder",
            output_row,
        )

        self.remember_settings = QCheckBox(
            "Remember my settings"
        )

        general_layout.addRow(
            "",
            self.remember_settings,
        )

        self.auto_open_output = QCheckBox(
            "Open output folder after compression"
        )

        general_layout.addRow(
            "",
            self.auto_open_output,
        )

        self.overwrite_existing = QCheckBox(
            "Overwrite existing output files"
        )

        general_layout.addRow(
            "",
            self.overwrite_existing,
        )

        content_layout.addWidget(
            general_box
        )

        # =====================================================
        # VIDEO
        # =====================================================

        content_layout.addWidget(
            SectionHeader(
                "Video",
                "Default video encoding parameters.",
            )
        )

        video_box = QGroupBox()

        video_layout = QFormLayout(
            video_box
        )

        video_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )

        video_layout.setHorizontalSpacing(
            30
        )

        video_layout.setVerticalSpacing(
            13
        )

        self.video_codec = QComboBox()

        self.video_codec.addItem(
            "H.264",
            "h264",
        )

        self.video_codec.addItem(
            "H.265 / HEVC",
            "hevc",
        )

        video_layout.addRow(
            "Default codec",
            self.video_codec,
        )

        self.video_cq = QSpinBox()

        self.video_cq.setRange(
            1,
            51,
        )

        self.video_cq.setSingleStep(
            1
        )

        self.video_cq.setSuffix(
            " CQ"
        )

        self.video_cq.setToolTip(
            "Lower values produce higher quality and larger files."
        )

        video_layout.addRow(
            "CQ quality",
            self.video_cq,
        )

        self.video_resolution = QComboBox()

        self.video_resolution.addItem(
            "Original / Up to 4K",
            "3840",
        )

        self.video_resolution.addItem(
            "1080p",
            "1920",
        )

        self.video_resolution.addItem(
            "1440p",
            "2560",
        )

        self.video_resolution.addItem(
            "4K",
            "3840",
        )

        video_layout.addRow(
            "Maximum resolution",
            self.video_resolution,
        )

        self.video_fps = QComboBox()

        self.video_fps.addItem(
            "Original",
            "original",
        )

        self.video_fps.addItem(
            "24 FPS",
            "24",
        )

        self.video_fps.addItem(
            "25 FPS",
            "25",
        )

        self.video_fps.addItem(
            "30 FPS",
            "30",
        )

        self.video_fps.addItem(
            "50 FPS",
            "50",
        )

        self.video_fps.addItem(
            "60 FPS",
            "60",
        )

        video_layout.addRow(
            "Frame rate",
            self.video_fps,
        )

        self.nvenc_preset = QComboBox()

        for preset in (
            "p1",
            "p2",
            "p3",
            "p4",
            "p5",
            "p6",
            "p7",
        ):
            self.nvenc_preset.addItem(
                preset.upper(),
                preset,
            )

        video_layout.addRow(
            "NVENC preset",
            self.nvenc_preset,
        )

        self.preserve_aspect_ratio = QCheckBox(
            "Preserve aspect ratio"
        )

        video_layout.addRow(
            "",
            self.preserve_aspect_ratio,
        )

        content_layout.addWidget(
            video_box
        )

        # =====================================================
        # AUDIO
        # =====================================================

        content_layout.addWidget(
            SectionHeader(
                "Audio",
                "Default audio encoding parameters.",
            )
        )

        audio_box = QGroupBox()

        audio_layout = QFormLayout(
            audio_box
        )

        audio_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )

        audio_layout.setHorizontalSpacing(
            30
        )

        audio_layout.setVerticalSpacing(
            13
        )

        self.audio_codec = QComboBox()

        self.audio_codec.addItem(
            "AAC",
            "aac",
        )

        self.audio_codec.addItem(
            "Copy original",
            "copy",
        )

        audio_layout.addRow(
            "Audio codec",
            self.audio_codec,
        )

        self.audio_bitrate = QComboBox()

        for bitrate in (
            "96k",
            "128k",
            "160k",
            "192k",
            "256k",
            "320k",
        ):
            self.audio_bitrate.addItem(
                bitrate,
                bitrate,
            )

        audio_layout.addRow(
            "Bitrate",
            self.audio_bitrate,
        )

        self.audio_sample_rate = QComboBox()

        self.audio_sample_rate.addItem(
            "44.1 kHz",
            "44100",
        )

        self.audio_sample_rate.addItem(
            "48 kHz",
            "48000",
        )

        audio_layout.addRow(
            "Sample rate",
            self.audio_sample_rate,
        )

        self.audio_channels = QComboBox()

        self.audio_channels.addItem(
            "Mono",
            "1",
        )

        self.audio_channels.addItem(
            "Stereo",
            "2",
        )

        audio_layout.addRow(
            "Channels",
            self.audio_channels,
        )

        content_layout.addWidget(
            audio_box
        )

        # =====================================================
        # PROCESSING
        # =====================================================

        content_layout.addWidget(
            SectionHeader(
                "Processing",
                "Hardware acceleration and output behaviour.",
            )
        )

        processing_box = QGroupBox()

        processing_layout = QVBoxLayout(
            processing_box
        )

        processing_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )

        processing_layout.setSpacing(
            12
        )

        self.gpu_acceleration = QCheckBox(
            "Enable NVIDIA GPU acceleration"
        )

        self.gpu_acceleration.setToolTip(
            "Use NVIDIA NVENC when available."
        )

        processing_layout.addWidget(
            self.gpu_acceleration
        )

        self.cpu_fallback = QCheckBox(
            "Allow CPU fallback if GPU encoding fails"
        )

        processing_layout.addWidget(
            self.cpu_fallback
        )

        self.faststart = QCheckBox(
            "Enable Faststart for MP4"
        )

        processing_layout.addWidget(
            self.faststart
        )

        self.copy_metadata = QCheckBox(
            "Copy source metadata"
        )

        processing_layout.addWidget(
            self.copy_metadata
        )

        content_layout.addWidget(
            processing_box
        )

        content_layout.addStretch(1)

        scroll.setWidget(
            content
        )

        root_layout.addWidget(
            scroll,
            1,
        )

        # =====================================================
        # BOTTOM BUTTONS
        # =====================================================

        bottom_separator = QFrame()

        bottom_separator.setFrameShape(
            QFrame.Shape.HLine
        )

        bottom_separator.setProperty(
            "settingsSeparator",
            True,
        )

        root_layout.addWidget(
            bottom_separator
        )

        bottom_layout = QHBoxLayout()

        reset_button = QPushButton(
            "Reset to Defaults"
        )

        reset_button.setProperty(
            "settingsSecondaryButton",
            True,
        )

        reset_button.clicked.connect(
            self.reset_to_defaults
        )

        bottom_layout.addWidget(
            reset_button
        )

        bottom_layout.addStretch(1)

        cancel_button = QPushButton(
            "Cancel"
        )

        cancel_button.setProperty(
            "settingsSecondaryButton",
            True,
        )

        cancel_button.clicked.connect(
            self.reject
        )

        bottom_layout.addWidget(
            cancel_button
        )

        save_button = QPushButton(
            "Save Settings"
        )

        save_button.setProperty(
            "settingsPrimaryButton",
            True,
        )

        save_button.setDefault(True)

        save_button.clicked.connect(
            self.save_settings
        )

        bottom_layout.addWidget(
            save_button
        )

        root_layout.addLayout(
            bottom_layout
        )

    # =========================================================
    # LOAD SETTINGS
    # =========================================================

    def _load_settings_into_ui(self):

        general = self.settings.get(
            "general",
            {}
        )

        video = self.settings.get(
            "video",
            {}
        )

        audio = self.settings.get(
            "audio",
            {}
        )

        processing = self.settings.get(
            "processing",
            {}
        )

        self.output_folder_edit.setText(
            str(
                general.get(
                    "output_folder",
                    "Compressed",
                )
            )
        )

        self.remember_settings.setChecked(
            bool(
                general.get(
                    "remember_settings",
                    True,
                )
            )
        )

        self.auto_open_output.setChecked(
            bool(
                general.get(
                    "auto_open_output",
                    False,
                )
            )
        )

        self.overwrite_existing.setChecked(
            bool(
                general.get(
                    "overwrite_existing",
                    False,
                )
            )
        )

        self._set_combo_data(
            self.video_codec,
            video.get(
                "codec",
                "h264",
            ),
        )

        self.video_cq.setValue(
            int(
                video.get(
                    "cq",
                    18,
                )
            )
        )

        self._set_combo_data(
            self.video_resolution,
            str(
                video.get(
                    "max_resolution",
                    "1920",
                )
            ),
        )

        self._set_combo_data(
            self.video_fps,
            str(
                video.get(
                    "fps",
                    "30",
                )
            ),
        )

        self._set_combo_data(
            self.nvenc_preset,
            video.get(
                "nvenc_preset",
                "p6",
            ),
        )

        self.preserve_aspect_ratio.setChecked(
            bool(
                video.get(
                    "preserve_aspect_ratio",
                    True,
                )
            )
        )

        self._set_combo_data(
            self.audio_codec,
            audio.get(
                "codec",
                "aac",
            ),
        )

        self._set_combo_data(
            self.audio_bitrate,
            audio.get(
                "bitrate",
                "192k",
            ),
        )

        self._set_combo_data(
            self.audio_sample_rate,
            str(
                audio.get(
                    "sample_rate",
                    "48000",
                )
            ),
        )

        self._set_combo_data(
    self.audio_channels,
    str(
        audio.get(
            "channels",
            "2",
        )
    )
)

        self.gpu_acceleration.setChecked(
            bool(
                processing.get(
                    "gpu_acceleration",
                    True,
                )
            )
        )

        self.cpu_fallback.setChecked(
            bool(
                processing.get(
                    "cpu_fallback",
                    True,
                )
            )
        )

        self.faststart.setChecked(
            bool(
                processing.get(
                    "faststart",
                    True,
                )
            )
        )

        self.copy_metadata.setChecked(
            bool(
                processing.get(
                    "copy_metadata",
                    True,
                )
            )
        )

    @staticmethod
    def _set_combo_data(
        combo,
        value,
    ):

        index = combo.findData(
            value
        )

        if index >= 0:
            combo.setCurrentIndex(
                index
            )

    # =========================================================
    # SAVE
    # =========================================================

    def _collect_settings(self):

        self.settings = {
            "general": {
                "output_folder":
                    self.output_folder_edit.text(),

                "remember_settings":
                    self.remember_settings.isChecked(),

                "auto_open_output":
                    self.auto_open_output.isChecked(),

                "overwrite_existing":
                    self.overwrite_existing.isChecked(),
            },

            "video": {
                "codec":
                    self.video_codec.currentData(),

                "cq":
                    self.video_cq.value(),

                "max_resolution":
                    self.video_resolution.currentData(),

                "fps":
                    self.video_fps.currentData(),

                "nvenc_preset":
                    self.nvenc_preset.currentData(),

                "preserve_aspect_ratio":
                    self.preserve_aspect_ratio.isChecked(),
            },

            "audio": {
                "codec":
                    self.audio_codec.currentData(),

                "bitrate":
                    self.audio_bitrate.currentData(),

                "sample_rate":
                    int(
                        self.audio_sample_rate.currentData()
                    ),

                "channels":
                    self.audio_channels.currentData(),
            },

            "processing": {
                "gpu_acceleration":
                    self.gpu_acceleration.isChecked(),

                "cpu_fallback":
                    self.cpu_fallback.isChecked(),

                "faststart":
                    self.faststart.isChecked(),

                "copy_metadata":
                    self.copy_metadata.isChecked(),
            },
        }

        return self.settings

    def save_settings(self):

        try:

            settings = self._collect_settings()

            self.settings_manager.save(
                settings
            )

            self.settings_saved = settings

            self.accept()

        except Exception as error:

            QMessageBox.critical(
                self,
                "Could not save settings",
                "GPUPress could not save your settings.\n\n"
                f"{error}",
            )

    # =========================================================
    # BROWSE OUTPUT
    # =========================================================

    def browse_output_folder(self):

        current = (
            self.output_folder_edit.text()
        )

        start_dir = current

        if not Path(start_dir).is_absolute():

            start_dir = (
                self.settings_manager.root_dir
                / start_dir
            )

        if not Path(start_dir).exists():

            start_dir = (
                self.settings_manager.root_dir
            )

        folder = (
            QFileDialog.getExistingDirectory(
                self,
                "Select Default Output Folder",
                str(start_dir),
            )
        )

        if not folder:
            return

        try:

            selected = Path(folder)

            root = (
                self.settings_manager.root_dir
            )

            try:

                relative = selected.relative_to(
                    root
                )

                self.output_folder_edit.setText(
                    str(relative)
                )

            except ValueError:

                self.output_folder_edit.setText(
                    str(selected)
                )

        except Exception:

            self.output_folder_edit.setText(
                folder
            )

    # =========================================================
    # RESET
    # =========================================================

    def reset_to_defaults(self):

        answer = QMessageBox.question(
            self,
            "Reset Settings",
            "Reset all GPUPress settings to their defaults?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.settings = json.loads(
            json.dumps(
                SettingsManager.DEFAULT_SETTINGS
            )
        )

        self._load_settings_into_ui()

    # =========================================================
    # STYLE
    # =========================================================

    def _apply_styles(self):

        self.setStyleSheet(
            """
            QDialog {
                background: #101010;
                color: #F5F5F5;
            }

            QLabel[settingsTitle="true"] {
                color: #FFFFFF;
                font-size: 24px;
                font-weight: 700;
            }

            QLabel[settingsSubtitle="true"] {
                color: #8F8F8F;
                font-size: 12px;
            }

            QLabel[settingsSectionHeader="true"] {
                color: #FFFFFF;
                font-size: 15px;
                font-weight: 700;
                padding-top: 2px;
                padding-bottom: 1px;
            }

            QLabel[settingsPathLabel="true"] {
                background: #181818;
                border: 1px solid #2B2B2B;
                border-radius: 7px;
                color: #BDBDBD;
                padding: 8px 10px;
            }

            QFrame[settingsSeparator="true"] {
                color: #252525;
                background: #252525;
                min-height: 1px;
                max-height: 1px;
            }

            QGroupBox {
                background: #151515;
                border: 1px solid #252525;
                border-radius: 10px;
            }

            QFormLayout QLabel {
                color: #BDBDBD;
                font-size: 12px;
            }

            QCheckBox {
                color: #D6D6D6;
                font-size: 12px;
                spacing: 8px;
            }

            QCheckBox::indicator {
                width: 17px;
                height: 17px;
            }

            QComboBox,
            QSpinBox {
                background: #1B1B1B;
                border: 1px solid #303030;
                border-radius: 7px;
                color: #F0F0F0;
                min-height: 34px;
                padding-left: 10px;
                padding-right: 10px;
            }

            QComboBox:hover,
            QSpinBox:hover {
                border-color: #454545;
            }

            QComboBox:focus,
            QSpinBox:focus {
                border-color: #666666;
            }

            QComboBox QAbstractItemView {
                background: #181818;
                border: 1px solid #333333;
                color: #F0F0F0;
                selection-background-color: #2D2D2D;
                selection-color: #FFFFFF;
            }

            QPushButton {
                background: #202020;
                border: 1px solid #333333;
                border-radius: 7px;
                color: #E8E8E8;
                min-height: 34px;
                padding-left: 14px;
                padding-right: 14px;
            }

            QPushButton:hover {
                background: #292929;
                border-color: #444444;
            }

            QPushButton:pressed {
                background: #171717;
            }

            QPushButton[settingsPrimaryButton="true"] {
                background: #FFFFFF;
                border-color: #FFFFFF;
                color: #0E0E0E;
                font-weight: 700;
            }

            QPushButton[settingsPrimaryButton="true"]:hover {
                background: #E7E7E7;
                border-color: #E7E7E7;
            }

            QPushButton[settingsSecondaryButton="true"] {
                background: #181818;
                border-color: #2E2E2E;
                color: #BDBDBD;
            }

            QPushButton[settingsCloseButton="true"] {
                background: transparent;
                border: 1px solid transparent;
                color: #777777;
                font-size: 22px;
                font-weight: 400;
                padding: 0px;
            }

            QPushButton[settingsCloseButton="true"]:hover {
                background: #1C1C1C;
                border-color: #2D2D2D;
                color: #FFFFFF;
            }

            QScrollArea {
                background: transparent;
                border: none;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 2px;
            }

            QScrollBar::handle:vertical {
                background: #353535;
                border-radius: 4px;
                min-height: 30px;
            }

            QScrollBar::handle:vertical:hover {
                background: #4A4A4A;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
            """
        )


# =============================================================
# Backwards-compatible alias
# =============================================================

SettingsWidget = SettingsDialog