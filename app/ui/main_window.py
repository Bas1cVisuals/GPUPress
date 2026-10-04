from copy import deepcopy
from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QThreadPool,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.settings_widget import (
    SettingsDialog,
    SettingsManager,
)
from app.core.hardware import HardwareInfo
from app.core.media import MediaInfo
from app.core.presets import get_preset, PRESETS
from app.workers.compression_worker import CompressionWorker


APP_TITLE = "GPUPress - by BAS1C VISUALS"

RESPONSIVE_BREAKPOINT = 900
HEADER_BREAKPOINT = 760


# =============================================================
# HELPERS
# =============================================================

def format_bytes(value):

    try:
        value = float(value)
    except Exception:
        return "—"

    if value <= 0:
        return "—"

    units = [
        "B",
        "KB",
        "MB",
        "GB",
        "TB",
    ]

    size = value

    for unit in units:

        if size < 1024 or unit == units[-1]:

            if unit == "B":
                return f"{int(size)} B"

            return f"{size:.1f} {unit}"

        size /= 1024

    return "—"


def format_duration(seconds):

    try:
        seconds = max(
            0,
            int(float(seconds))
        )
    except Exception:
        return "00:00"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{secs:02d}"
        )

    return (
        f"{minutes:02d}:"
        f"{secs:02d}"
    )


def format_speed(value):

    try:
        value = float(value)
    except Exception:
        return "—"

    if value <= 0:
        return "—"

    return f"{value:.2f}x"


def format_fps(value):

    try:
        value = float(value)
    except Exception:
        return "—"

    if value <= 0:
        return "—"

    return f"{value:.1f} FPS"


class MediaProbeSignals(QObject):

    completed = Signal(object, object, object, object)


class MediaProbeTask(QRunnable):

    def __init__(self, input_file, ffprobe_path):
        super().__init__()

        self.input_file = Path(input_file)
        self.ffprobe_path = Path(ffprobe_path)
        self.signals = MediaProbeSignals()
        self.setAutoDelete(False)

    def run(self):

        try:
            info = MediaInfo(
                self.ffprobe_path
            ).probe(
                self.input_file
            )
            error = None
        except Exception as probe_error:
            info = {}
            error = str(probe_error)

        self.signals.completed.emit(
            self,
            self.input_file,
            info,
            error,
        )


# =============================================================
# CARD
# =============================================================

class Card(QFrame):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setObjectName(
            "Card"
        )

# =============================================================
# SETTINGS GUIDE
# =============================================================

class SettingsGuideDialog(QDialog):

    GUIDE = {
        "Presets": {
            "Preset": (
                "A preset automatically fills the main compression "
                "settings for a specific workflow.\n\n"
                "Reel presets are aimed at social-media style exports, "
                "while Video presets are intended for general video."
            ),

            "Reel — 1080p": (
                "Balanced preset for vertical reels and standard "
                "1080p social-media exports.\n\n"
                "Maximum resolution: 1920\n"
                "Quality: CQ 18\n"
                "Frame rate: 30 FPS\n"
                "Encoder: NVENC P6"
            ),

            "Reel — 4K": (
                "Keeps the output capable of retaining 4K resolution "
                "when the source is 4K.\n\n"
                "Quality: CQ 18\n"
                "Frame rate: 30 FPS\n"
                "Encoder: NVENC P6"
            ),

            "Video — 1080p": (
                "General-purpose 1080p compression preset.\n\n"
                "Useful when you want a smaller Full HD file without "
                "changing the overall workflow."
            ),

            "Video — 4K": (
                "General-purpose 4K compression preset.\n\n"
                "Useful when the source is already high resolution and "
                "you want to retain up to 4K."
            ),

            "Maximum Compatibility": (
                "Prioritizes broad playback compatibility over maximum "
                "compression efficiency.\n\n"
                "Uses H.264 with a slightly more conservative quality "
                "and encoder configuration."
            ),

            "High Quality": (
                "Prioritizes image quality over file size.\n\n"
                "Uses a lower CQ value and keeps the original frame rate."
            ),

            "Small File": (
                "Prioritizes a smaller output file.\n\n"
                "Uses a higher CQ value and lower audio bitrate."
            ),

            "Custom": (
                "Lets you manually control the compression settings."
            ),
        },

        "Video": {
            "Max Resolution": (
                "Sets the maximum output dimension.\n\n"
                "The compressor will not upscale a smaller source. "
                "When downscaling, the original aspect ratio is preserved.\n\n"
                "1920 → Full HD\n"
                "2560 → 1440p-class output\n"
                "3840 → 4K-class output"
            ),

            "Codec": (
                "Controls the video compression format.\n\n"
                "H.264 — maximum compatibility and widely supported.\n\n"
                "HEVC / H.265 — generally more efficient compression "
                "but can have lower playback compatibility."
            ),

            "CQ Quality": (
                "Controls constant-quality encoding.\n\n"
                "LOWER CQ = higher visual quality + larger file.\n\n"
                "HIGHER CQ = more compression + smaller file.\n\n"
                "Typical guide:\n"
                "16 → very high quality\n"
                "18 → balanced\n"
                "20 → more compression\n"
                "23 → smaller file"
            ),

            "Frame Rate": (
                "Controls the output frame rate.\n\n"
                "Original keeps the source frame rate.\n\n"
                "24 / 25 / 30 / 50 / 60 forces the selected output "
                "frame rate."
            ),

            "NVENC Preset": (
                "Controls the NVIDIA hardware encoder's speed/quality "
                "trade-off.\n\n"
                "P1 → faster encoding\n"
                "P7 → slower encoding with more encoder optimization\n\n"
                "P5/P6 are useful balanced choices."
            ),
        },

        "Audio": {
            "Audio Codec": (
                "AAC re-encodes the audio for a predictable compressed "
                "output.\n\n"
                "Copy keeps the existing audio stream when the output "
                "container/codec combination allows it."
            ),

            "Bitrate": (
                "Controls the audio bitrate when AAC encoding is used.\n\n"
                "Higher bitrate generally means better audio quality "
                "and a slightly larger file.\n\n"
                "192k is a practical general-purpose setting."
            ),

            "Channels": (
                "Controls the number of audio channels in the output.\n\n"
                "Stereo → 2 channels\n"
                "Mono → 1 channel"
            ),
        },

        "Processing": {
            "NVIDIA GPU Acceleration": (
                "Uses the NVIDIA GPU hardware acceleration path when "
                "supported by FFmpeg and your GPU.\n\n"
                "This is the preferred BAS1C processing path because "
                "NVENC can perform hardware video encoding."
            ),

            "CPU Fallback": (
                "Allows the compressor to fall back to another encoding "
                "path if the preferred NVIDIA hardware path cannot be used."
            ),

            "Copy Metadata": (
                "Copies metadata from the source into the output when "
                "supported by the output container.\n\n"
                "Disable this if you want a cleaner output without "
                "source metadata."
            ),

            "Enable Faststart": (
                "Moves MP4 metadata required for progressive playback "
                "toward the beginning of the file.\n\n"
                "Useful for videos intended for web delivery or "
                "streaming-style playback."
            ),
        },
    }

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle(
            "GPUPress - Settings Guide"
        )

        self.setMinimumSize(
            760,
            520
        )

        self.resize(
            820,
            570
        )

        self.build_ui()
        self.apply_styles()

    def build_ui(self):

        root_layout = QVBoxLayout(self)

        root_layout.setContentsMargins(
            22,
            20,
            22,
            20
        )

        root_layout.setSpacing(
            16
        )

        # -----------------------------------------------------
        # HEADER
        # -----------------------------------------------------

        header_layout = QHBoxLayout()

        title_layout = QVBoxLayout()

        title = QLabel(
            "Settings Guide"
        )

        title.setObjectName(
            "GuideTitle"
        )

        subtitle = QLabel(
            "Understand what each compression setting actually does."
        )

        subtitle.setObjectName(
            "GuideSubtitle"
        )

        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        header_layout.addLayout(
            title_layout
        )

        header_layout.addStretch(1)

        close_button = QPushButton(
            "Close"
        )

        close_button.setObjectName(
            "GuideClose"
        )

        close_button.clicked.connect(
            self.close
        )

        header_layout.addWidget(
            close_button
        )

        root_layout.addLayout(
            header_layout
        )

        # -----------------------------------------------------
        # BODY
        # -----------------------------------------------------

        body_layout = QHBoxLayout()

        body_layout.setSpacing(
            14
        )

        # -----------------------------------------------------
        # CATEGORY LIST
        # -----------------------------------------------------

        self.category_list = QListWidget()

        self.category_list.setFixedWidth(
            170
        )

        for category in self.GUIDE.keys():

            item = QListWidgetItem(
                category
            )

            self.category_list.addItem(
                item
            )

        self.category_list.currentRowChanged.connect(
            self.category_changed
        )

        body_layout.addWidget(
            self.category_list
        )

        # -----------------------------------------------------
        # CONTENT
        # -----------------------------------------------------

        self.guide_scroll = QScrollArea()

        self.guide_scroll.setWidgetResizable(
            True
        )

        self.guide_scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.guide_content = QWidget()

        self.guide_layout = QVBoxLayout(
            self.guide_content
        )

        self.guide_layout.setContentsMargins(
            4,
            4,
            8,
            4
        )

        self.guide_layout.setSpacing(
            8
        )

        self.guide_scroll.setWidget(
            self.guide_content
        )

        body_layout.addWidget(
            self.guide_scroll,
            1
        )

        root_layout.addLayout(
            body_layout,
            1
        )

        self.category_list.setCurrentRow(
            0
        )

    def category_changed(
        self,
        row
    ):

        while self.guide_layout.count():

            item = self.guide_layout.takeAt(0)

            if item is None:
                continue

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        if row < 0:
            return

        category = list(
            self.GUIDE.keys()
        )[row]

        entries = self.GUIDE[
            category
        ]

        for title, description in entries.items():

            card = QFrame()

            card.setObjectName(
                "GuideItem"
            )

            card_layout = QVBoxLayout(
                card
            )

            card_layout.setContentsMargins(
                16,
                13,
                16,
                13
            )

            card_layout.setSpacing(
                7
            )

            title_label = QLabel(
                title
            )

            title_label.setObjectName(
                "GuideItemTitle"
            )

            description_label = QLabel(
                description
            )

            description_label.setObjectName(
                "GuideItemText"
            )

            description_label.setWordWrap(
                True
            )

            description_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )

            card_layout.addWidget(
                title_label
            )

            card_layout.addWidget(
                description_label
            )

            self.guide_layout.addWidget(
                card
            )

        self.guide_layout.addStretch(
            1
        )

    def apply_styles(self):

        self.setStyleSheet(
            """
            QDialog {
                background: #101011;
            }

            QLabel {
                color: #D8D8DA;
            }

            QLabel#GuideTitle {
                color: #FFFFFF;
                font-size: 17pt;
                font-weight: 700;
            }

            QLabel#GuideSubtitle {
                color: #8F8F95;
                font-size: 9pt;
            }

            QListWidget {
                background: #181819;
                color: #AFAFB4;
                border: 1px solid #2C2C30;
                border-radius: 10px;
                padding: 5px;
                outline: none;
            }

            QListWidget::item {
                padding: 11px 12px;
                border-radius: 7px;
                margin: 2px 0px;
            }

            QListWidget::item:hover {
                background: #242427;
                color: #EEEEEF;
            }

            QListWidget::item:selected {
                background: #E9E9EA;
                color: #111112;
                font-weight: 700;
            }

            QScrollArea {
                background: transparent;
                border: none;
            }

            QFrame#GuideItem {
                background: #181819;
                border: 1px solid #2C2C30;
                border-radius: 10px;
            }

            QLabel#GuideItemTitle {
                color: #F4F4F5;
                font-size: 10pt;
                font-weight: 700;
            }

            QLabel#GuideItemText {
                color: #A6A6AC;
                font-size: 9pt;
                line-height: 140%;
            }

            QPushButton#GuideClose {
                background: #242427;
                color: #EEEEEF;
                border: 1px solid #37373C;
                border-radius: 7px;
                padding: 7px 15px;
            }

            QPushButton#GuideClose:hover {
                background: #303035;
                border-color: #4A4A50;
            }
            """
        )
        
# =============================================================
# QUEUE ITEM
# =============================================================

class QueueItemWidget(Card):

    def __init__(
        self,
        input_file,
        remove_callback,
        parent=None,
    ):

        super().__init__(parent)

        self.input_file = Path(
            input_file
        )

        self.remove_callback = (
            remove_callback
        )

        self.worker = None

        self.finished = False

        self.input_size = 0

        self.output_size = 0

        self.duration = 0

        self.build_ui()

    # ---------------------------------------------------------
    # UI
    # ---------------------------------------------------------

    def build_ui(self):

        self.grid_layout = QGridLayout(
            self
        )

        self.grid_layout.setContentsMargins(
            14,
            12,
            14,
            12
        )

        self.grid_layout.setHorizontalSpacing(
            10
        )

        self.grid_layout.setVerticalSpacing(
            5
        )

        # -----------------------------------------------------
        # FILENAME
        # -----------------------------------------------------

        self.filename_label = QLabel(
            self.input_file.name
        )

        self.filename_label.setObjectName(
            "QueueFilename"
        )

        self.filename_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.grid_layout.addWidget(
            self.filename_label,
            0,
            0,
            1,
            2
        )

        # -----------------------------------------------------
        # REMOVE
        # -----------------------------------------------------

        self.remove_button = QPushButton(
            "×"
        )

        self.remove_button.setObjectName(
            "IconButton"
        )

        self.remove_button.setFixedSize(
            32,
            32
        )

        self.remove_button.clicked.connect(
            self.remove_item
        )

        self.grid_layout.addWidget(
            self.remove_button,
            0,
            2,
            2,
            1,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight
        )

        # -----------------------------------------------------
        # MEDIA INFO
        # -----------------------------------------------------

        self.media_label = QLabel(
            "Preparing media information..."
        )

        self.media_label.setObjectName(
            "QueueMeta"
        )

        self.media_label.setWordWrap(
            True
        )

        self.grid_layout.addWidget(
            self.media_label,
            1,
            0,
            1,
            2
        )

        # -----------------------------------------------------
        # STATUS
        # -----------------------------------------------------

        self.status_label = QLabel(
            "Waiting"
        )

        self.status_label.setObjectName(
            "QueueStatus"
        )

        self.grid_layout.addWidget(
            self.status_label,
            2,
            0,
            1,
            1
        )

        # -----------------------------------------------------
        # PROGRESS
        # -----------------------------------------------------

        self.progress_bar = QProgressBar()

        self.progress_bar.setRange(
            0,
            100
        )

        self.progress_bar.setValue(
            0
        )

        self.progress_bar.setTextVisible(
            False
        )

        self.progress_bar.setFixedHeight(
            7
        )

        self.grid_layout.addWidget(
            self.progress_bar,
            2,
            1,
            1,
            1
        )

        # -----------------------------------------------------
        # LIVE STATS
        # -----------------------------------------------------

        self.stats_label = QLabel(
            "FPS —    Speed —    ETA —    Time —"
        )

        self.stats_label.setObjectName(
            "QueueStats"
        )

        self.stats_label.setWordWrap(
            True
        )

        self.grid_layout.addWidget(
            self.stats_label,
            3,
            0,
            1,
            2
        )

        # -----------------------------------------------------
        # SIZE STATS
        # -----------------------------------------------------

        self.size_label = QLabel(
            ""
        )

        self.size_label.setObjectName(
            "QueueSize"
        )

        self.size_label.setWordWrap(
            True
        )

        self.grid_layout.addWidget(
            self.size_label,
            4,
            0,
            1,
            2
        )

    # ---------------------------------------------------------
    # MEDIA INFO
    # ---------------------------------------------------------

    def set_media_info(self, info):

        if not info:
            return

        width = info.get(
            "width",
            0
        )

        height = info.get(
            "height",
            0
        )

        fps = info.get(
            "fps",
            0
        )

        codec = info.get(
            "video_codec",
            "Unknown"
        )

        size = info.get(
            "size",
            0
        )

        duration = info.get(
            "duration",
            0
        )

        self.input_size = (
            int(size or 0)
        )

        self.duration = (
            float(duration or 0)
        )

        if width and height:

            resolution = (
                f"{width}×{height}"
            )

        else:

            resolution = "Unknown"

        fps_text = (
            f"{fps:.2f} FPS"
            if fps
            else "Unknown FPS"
        )

        self.media_label.setText(
            f"{resolution}  •  "
            f"{fps_text}  •  "
            f"{codec.upper()}  •  "
            f"{format_bytes(self.input_size)}  •  "
            f"{format_duration(self.duration)}"
        )

    # ---------------------------------------------------------
    # WORKER
    # ---------------------------------------------------------

    def set_worker(
        self,
        worker
    ):

        self.worker = worker

        worker.progress_changed.connect(
            self.set_progress
        )

        worker.status_changed.connect(
            self.set_status
        )

        worker.stats_changed.connect(
            self.update_stats
        )

        worker.compression_finished.connect(
            self.compression_finished
        )

        worker.compression_failed.connect(
            self.compression_failed
        )

    # ---------------------------------------------------------
    # PROGRESS
    # ---------------------------------------------------------

    def set_progress(
        self,
        value
    ):

        try:
            value = int(value)
        except Exception:
            value = 0

        value = max(
            0,
            min(
                100,
                value
            )
        )

        self.progress_bar.setValue(
            value
        )

    # ---------------------------------------------------------
    # STATUS
    # ---------------------------------------------------------

    def set_status(
        self,
        text
    ):

        self.status_label.setText(
            text
        )

    # ---------------------------------------------------------
    # LIVE STATS
    # ---------------------------------------------------------

    def update_stats(
        self,
        stats
    ):

        if not isinstance(
            stats,
            dict
        ):
            return

        progress = stats.get(
            "progress"
        )

        if progress is not None:
            self.set_progress(
                progress
            )

        fps = stats.get(
            "fps",
            0
        )

        speed = stats.get(
            "speed",
            0
        )

        current_time = stats.get(
            "time",
            0
        )

        duration = stats.get(
            "duration",
            self.duration
        )

        eta = stats.get(
            "eta",
            0
        )

        bitrate = stats.get(
            "bitrate",
            ""
        )

        self.stats_label.setText(
            f"{format_fps(fps)}    "
            f"Speed {format_speed(speed)}    "
            f"ETA {format_duration(eta)}    "
            f"Time "
            f"{format_duration(current_time)} / "
            f"{format_duration(duration)}"
            + (
                f"    {bitrate}"
                if bitrate
                else ""
            )
        )

        input_size = stats.get(
            "input_size"
        )

        if input_size:

            try:
                self.input_size = int(
                    input_size
                )
            except Exception:
                pass

    # ---------------------------------------------------------
    # FINISHED
    # ---------------------------------------------------------

    def compression_finished(
        self,
        output_file
    ):

        self.finished = True

        self.status_label.setText(
            "Completed"
        )

        self.progress_bar.setValue(
            100
        )

        try:

            output_path = Path(
                output_file
            )

            if output_path.exists():

                self.output_size = (
                    output_path
                    .stat()
                    .st_size
                )

        except Exception:

            self.output_size = 0

        saved = 0
        reduction = 0.0

        if (
            self.input_size > 0
            and self.output_size > 0
        ):

            saved = max(
                0,
                self.input_size
                - self.output_size
            )

            reduction = (
                saved
                / self.input_size
            ) * 100

        self.size_label.setText(
            f"{format_bytes(self.input_size)}"
            f"  →  "
            f"{format_bytes(self.output_size)}"
            f"    •    "
            f"Saved "
            f"{format_bytes(saved)}"
            f"    •    "
            f"{reduction:.1f}% smaller"
        )

        self.stats_label.setText(
            "Compression completed"
        )

    # ---------------------------------------------------------
    # FAILED
    # ---------------------------------------------------------

    def compression_failed(
        self,
        message
    ):

        self.status_label.setText(
            "Failed"
        )

        self.stats_label.setText(
            "Compression failed"
        )

        self.size_label.setText(
            message
        )

    # ---------------------------------------------------------
    # REMOVE
    # ---------------------------------------------------------

    def remove_item(self):

        if self.worker is not None:

            if self.worker.isRunning():

                self.worker.cancel()

                return

        self.remove_callback(
            self
        )


# =============================================================
# MAIN WINDOW
# =============================================================

class MainWindow(QMainWindow):

    def __init__(self, settings_manager=None):

        super().__init__()

        self.setWindowTitle(
            APP_TITLE
        )

        self.setMinimumSize(
            700,
            520
        )

        self.resize(
            1200,
            760
        )

        self.queue_items = []

        self.current_worker = None

        self.current_queue_index = -1
        self._media_probe_workers = set()
        self.settings_manager = (
            settings_manager
            or SettingsManager()
        )
        self.audio_sample_rate = 48000
        self.overwrite_existing = False
        self.auto_open_output = False
        self.queue_succeeded = False
        self.last_output_dir = None

        self.hardware = HardwareInfo()

        self.build_ui()

        self.apply_settings(
            self.settings_manager.settings
        )

        self.apply_styles()

        self.update_hardware_status()
        self.update_queue_height()

        self.update_responsive_layout()

    # =========================================================
    # UI
    # =========================================================

    def build_ui(self):

        self.scroll_area = QScrollArea()

        self.scroll_area.setWidgetResizable(
            True
        )

        self.scroll_area.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.setCentralWidget(
            self.scroll_area
        )

        self.root = QWidget()

        self.scroll_area.setWidget(
            self.root
        )

        self.root_layout = QVBoxLayout(
            self.root
        )

        self.root_layout.setContentsMargins(
            18,
            18,
            18,
            18
        )

        self.root_layout.setSpacing(
            14
        )

        # =====================================================
        # HEADER
        # =====================================================

        self.header_card = Card()

        self.header_layout = QBoxLayout(
            QBoxLayout.Direction.LeftToRight
        )

        self.header_layout.setContentsMargins(
            18,
            16,
            18,
            16
        )

        self.header_card.setLayout(
            self.header_layout
        )

        self.brand_layout = QVBoxLayout()

        self.brand_label = QLabel(
            "GPUPress"
        )

        self.brand_label.setObjectName(
            "Brand"
        )

        self.title_label = QLabel(
            "GPU Video Compressor"
        )

        self.title_label.setObjectName(
            "Title"
        )

        self.brand_layout.addWidget(
            self.brand_label
        )

        self.brand_layout.addWidget(
            self.title_label
        )

        self.header_layout.addLayout(
            self.brand_layout
        )

        self.header_layout.addStretch(
            1
        )

        self.hardware_label = QLabel(
            "Checking hardware..."
        )

        self.hardware_label.setObjectName(
            "Hardware"
        )

        self.header_layout.addWidget(
            self.hardware_label,
            0,
            Qt.AlignmentFlag.AlignVCenter
        )

        self.root_layout.addWidget(
            self.header_card
        )

        # =====================================================
        # CONTENT
        # =====================================================

        self.content_widget = QWidget()

        self.content_layout = QBoxLayout(
            QBoxLayout.Direction.LeftToRight
        )

        self.content_layout.setSpacing(
            14
        )

        self.content_widget.setLayout(
            self.content_layout
        )

        self.root_layout.addWidget(
            self.content_widget
        )

        # =====================================================
        # SETTINGS CARD
        # =====================================================

        self.settings_card = Card()

        self.settings_layout = QVBoxLayout(
            self.settings_card
        )

        self.settings_layout.setContentsMargins(
            18,
            18,
            18,
            18
        )

        self.settings_layout.setSpacing(
            12
        )

        self.settings_header = QBoxLayout(
            QBoxLayout.Direction.LeftToRight
        )

        self.settings_title = QLabel(
            "Compression Settings"
        )

        self.settings_title.setObjectName(
            "SectionTitle"
        )

        self.settings_header.addWidget(
            self.settings_title
        )

        self.settings_header.addStretch(
            1
        )

        self.settings_guide_button = QPushButton(
            "?  Guide"
        )

        self.settings_guide_button.setObjectName(
            "GuideButton"
        )

        self.settings_guide_button.setToolTip(
            "Learn what each compression setting does"
        )

        self.settings_guide_button.clicked.connect(
            self.open_settings_guide
        )

        self.settings_header.addWidget(
            self.settings_guide_button
        )

        self.settings_button = QPushButton(
            "⚙  Settings"
        )

        self.settings_button.setObjectName(
            "SettingsButton"
        )

        self.settings_button.setToolTip(
            "Open application settings"
        )

        self.settings_button.clicked.connect(
            self.open_settings
        )

        self.settings_header.addWidget(
            self.settings_button
        )

        self.settings_layout.addLayout(
            self.settings_header
        )

        

        # -----------------------------------------------------
        # SETTINGS GRID
        # -----------------------------------------------------

        self.settings_grid = QGridLayout()

        self.settings_grid.setHorizontalSpacing(
            10
        )

        self.settings_grid.setVerticalSpacing(
            9
        )

        # -----------------------------------------------------
        # PRESET
        # -----------------------------------------------------

        self.settings_grid.addWidget(
            QLabel("Preset"),
            0,
            0
        )

        self.preset_combo = QComboBox()

        self.preset_items = [
            ("Reel — 1080p", "reel_1080p"),
            ("Reel — 4K", "reel_4k"),
            ("Video — 1080p", "video_1080p"),
            ("Video — 4K", "video_4k"),
            ("Maximum Compatibility", "compatibility"),
            ("High Quality", "quality"),
            ("Small File", "small_file"),
            ("Custom", "custom"),
        ]

        for label, preset_id in self.preset_items:

            self.preset_combo.addItem(
                label,
                preset_id
            )

        self.preset_combo.currentIndexChanged.connect(
            self.preset_changed
        )

        self.settings_grid.addWidget(
            self.preset_combo,
            0,
            1
        )

        # -----------------------------------------------------
        # RESOLUTION
        # -----------------------------------------------------

        self.settings_grid.addWidget(
            QLabel("Max Resolution"),
            1,
            0
        )

        self.resolution_combo = QComboBox()

        self.resolution_combo.addItem(
            "1920",
            1920
        )

        self.resolution_combo.addItem(
            "2560",
            2560
        )

        self.resolution_combo.addItem(
            "3840",
            3840
        )

        self.settings_grid.addWidget(
            self.resolution_combo,
            1,
            1
        )

        # -----------------------------------------------------
        # CODEC
        # -----------------------------------------------------

        self.settings_grid.addWidget(
            QLabel("Codec"),
            2,
            0
        )

        self.codec_combo = QComboBox()

        self.codec_combo.addItem(
            "H.264",
            "h264"
        )

        self.codec_combo.addItem(
            "HEVC / H.265",
            "hevc"
        )

        self.settings_grid.addWidget(
            self.codec_combo,
            2,
            1
        )

        # -----------------------------------------------------
        # CQ
        # -----------------------------------------------------

        self.settings_grid.addWidget(
            QLabel("CQ Quality"),
            3,
            0
        )

        self.cq_spin = QSpinBox()

        self.cq_spin.setRange(
            1,
            51
        )

        self.cq_spin.setValue(
            18
        )

        self.settings_grid.addWidget(
            self.cq_spin,
            3,
            1
        )

        # -----------------------------------------------------
        # FPS
        # -----------------------------------------------------

        self.settings_grid.addWidget(
            QLabel("Frame Rate"),
            4,
            0
        )

        self.fps_combo = QComboBox()

        for label in [
            "Original",
            "24",
            "25",
            "30",
            "50",
            "60",
        ]:

            self.fps_combo.addItem(
                label
            )

        self.fps_combo.setCurrentText(
            "30"
        )

        self.settings_grid.addWidget(
            self.fps_combo,
            4,
            1
        )

        # -----------------------------------------------------
        # ENCODER PRESET
        # -----------------------------------------------------

        self.settings_grid.addWidget(
            QLabel("NVENC Preset"),
            5,
            0
        )

        self.encoder_combo = QComboBox()

        for preset in [
            "p1",
            "p2",
            "p3",
            "p4",
            "p5",
            "p6",
            "p7",
        ]:

            self.encoder_combo.addItem(
                preset
            )

        self.encoder_combo.setCurrentText(
            "p6"
        )

        self.settings_grid.addWidget(
            self.encoder_combo,
            5,
            1
        )

        self.settings_layout.addLayout(
            self.settings_grid
        )

        # =====================================================
        # AUDIO
        # =====================================================

        self.audio_title = QLabel(
            "Audio"
        )

        self.audio_title.setObjectName(
            "SubTitle"
        )

        self.settings_layout.addWidget(
            self.audio_title
        )

        self.audio_grid = QGridLayout()

        self.audio_grid.setHorizontalSpacing(
            10
        )

        self.audio_grid.setVerticalSpacing(
            9
        )

        self.audio_grid.addWidget(
            QLabel("Codec"),
            0,
            0
        )

        self.audio_combo = QComboBox()

        self.audio_combo.addItem(
            "AAC",
            "aac"
        )

        self.audio_combo.addItem(
            "Copy",
            "copy"
        )

        self.audio_grid.addWidget(
            self.audio_combo,
            0,
            1
        )

        self.audio_grid.addWidget(
            QLabel("Bitrate"),
            1,
            0
        )

        self.audio_bitrate_combo = QComboBox()

        for value in [
            "128k",
            "160k",
            "192k",
            "256k",
            "320k",
        ]:

            self.audio_bitrate_combo.addItem(
                value
            )

        self.audio_bitrate_combo.setCurrentText(
            "192k"
        )

        self.audio_grid.addWidget(
            self.audio_bitrate_combo,
            1,
            1
        )

        self.audio_grid.addWidget(
            QLabel("Channels"),
            2,
            0
        )

        self.audio_channels_combo = QComboBox()

        self.audio_channels_combo.addItem(
            "Stereo",
            2
        )

        self.audio_channels_combo.addItem(
            "Mono",
            1
        )

        self.audio_grid.addWidget(
            self.audio_channels_combo,
            2,
            1
        )

        self.settings_layout.addLayout(
            self.audio_grid
        )

        # =====================================================
        # OPTIONS
        # =====================================================

        self.options_title = QLabel(
            "Options"
        )

        self.options_title.setObjectName(
            "SubTitle"
        )

        self.settings_layout.addWidget(
            self.options_title
        )

        self.gpu_check = QCheckBox(
            "Use NVIDIA GPU acceleration"
        )

        self.gpu_check.setChecked(
            True
        )

        self.settings_layout.addWidget(
            self.gpu_check
        )

        self.fallback_check = QCheckBox(
            "Allow CPU fallback"
        )

        self.fallback_check.setChecked(
            True
        )

        self.settings_layout.addWidget(
            self.fallback_check
        )

        self.metadata_check = QCheckBox(
            "Copy metadata"
        )

        self.metadata_check.setChecked(
            True
        )

        self.settings_layout.addWidget(
            self.metadata_check
        )

        self.faststart_check = QCheckBox(
            "Enable faststart"
        )

        self.faststart_check.setChecked(
            True
        )

        self.settings_layout.addWidget(
            self.faststart_check
        )

        self.settings_layout.addStretch(
            1
        )

        self.content_layout.addWidget(
            self.settings_card
        )

        # =====================================================
        # RIGHT SIDE
        # =====================================================

        self.right_widget = QWidget()

        self.right_layout = QVBoxLayout(
            self.right_widget
        )

        self.right_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        self.right_layout.setSpacing(
            14
        )

        # =====================================================
        # INPUT
        # =====================================================

        self.input_card = Card()

        self.input_layout = QVBoxLayout(
            self.input_card
        )

        self.input_layout.setContentsMargins(
            18,
            18,
            18,
            18
        )

        self.input_title = QLabel(
            "Input"
        )

        self.input_title.setObjectName(
            "SectionTitle"
        )

        self.input_layout.addWidget(
            self.input_title
        )

        self.input_row = QBoxLayout(
            QBoxLayout.Direction.LeftToRight
        )

        self.input_edit = QLineEdit()

        self.input_edit.setPlaceholderText(
            "Select video files..."
        )

        self.input_edit.setReadOnly(
            True
        )

        self.input_button = QPushButton(
            "Add Videos"
        )

        self.input_button.clicked.connect(
            self.add_videos
        )

        self.input_row.addWidget(
            self.input_edit,
            1
        )

        self.input_row.addWidget(
            self.input_button
        )

        self.input_layout.addLayout(
            self.input_row
        )

        self.add_folder_button = QPushButton(
            "Add Folder"
        )

        self.add_folder_button.clicked.connect(
            self.add_folder
        )

        self.input_layout.addWidget(
            self.add_folder_button
        )

        self.right_layout.addWidget(
            self.input_card
        )

        # =====================================================
        # QUEUE
        # =====================================================

        self.queue_card = Card()
        self.queue_card.setMinimumHeight(200)
        self.queue_card.setMaximumHeight(430)

        self.queue_layout = QVBoxLayout(self.queue_card)
        self.queue_layout.setContentsMargins(18, 18, 18, 18)
        self.queue_layout.setSpacing(10)

        self.queue_header = QBoxLayout(QBoxLayout.Direction.LeftToRight)

        self.queue_title = QLabel("Queue")
        self.queue_title.setObjectName("SectionTitle")
        self.queue_header.addWidget(self.queue_title)
        self.queue_header.addStretch(1)

        self.clear_queue_button = QPushButton("Clear")
        self.clear_queue_button.clicked.connect(self.clear_queue)
        self.queue_header.addWidget(self.clear_queue_button)

        self.queue_layout.addLayout(self.queue_header)

        self.queue_scroll = QScrollArea()
        self.queue_scroll.setObjectName("QueueScroll")
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.queue_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.queue_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.queue_container = QWidget()
        self.queue_container_layout = QVBoxLayout(self.queue_container)
        self.queue_container_layout.setContentsMargins(0, 2, 6, 2)
        self.queue_container_layout.setSpacing(8)
        self.queue_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.empty_queue_label = QLabel("No videos in queue.")
        self.empty_queue_label.setObjectName("EmptyQueue")
        self.empty_queue_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_queue_label.setMinimumHeight(90)
        self.queue_container_layout.addWidget(self.empty_queue_label)

        self.queue_scroll.setWidget(self.queue_container)
        self.queue_layout.addWidget(self.queue_scroll, 1)

        self.right_layout.addWidget(self.queue_card)

        # =====================================================
        # OUTPUT
        # =====================================================

        self.output_card = Card()

        self.output_layout = QVBoxLayout(
            self.output_card
        )

        self.output_layout.setContentsMargins(
            18,
            18,
            18,
            18
        )

        self.output_title = QLabel(
            "Output"
        )

        self.output_title.setObjectName(
            "SectionTitle"
        )

        self.output_layout.addWidget(
            self.output_title
        )

        self.output_row = QBoxLayout(
            QBoxLayout.Direction.LeftToRight
        )

        self.output_edit = QLineEdit()

        self.output_edit.setText(
            str(
                self.settings_manager.root_dir
                / "Compressed"
            )
        )

        self.output_button = QPushButton(
            "Choose"
        )

        self.output_button.clicked.connect(
            self.choose_output
        )

        self.output_row.addWidget(
            self.output_edit,
            1
        )

        self.output_row.addWidget(
            self.output_button
        )

        self.output_layout.addLayout(
            self.output_row
        )

        self.right_layout.addWidget(
            self.output_card
        )

        # =====================================================
        # ACTIONS
        # =====================================================

        self.action_row = QBoxLayout(
            QBoxLayout.Direction.LeftToRight
        )

        self.start_button = QPushButton(
            "Start Compression"
        )

        self.start_button.setObjectName(
            "PrimaryButton"
        )

        self.start_button.clicked.connect(
            self.start_compression
        )

        self.cancel_button = QPushButton(
            "Cancel"
        )

        self.cancel_button.setEnabled(
            False
        )

        self.cancel_button.clicked.connect(
            self.cancel_compression
        )

        self.action_row.addWidget(
            self.start_button,
            1
        )

        self.action_row.addWidget(
            self.cancel_button
        )

        self.right_layout.addLayout(
            self.action_row
        )

        # =====================================================
        # LOG
        # =====================================================

        self.log_card = Card()

        self.log_layout = QVBoxLayout(
            self.log_card
        )

        self.log_layout.setContentsMargins(
            18,
            18,
            18,
            18
        )

        self.log_title = QLabel(
            "Log"
        )

        self.log_title.setObjectName(
            "SectionTitle"
        )

        self.log_layout.addWidget(
            self.log_title
        )

        self.log_edit = QTextEdit()

        self.log_edit.setReadOnly(
            True
        )

        self.log_edit.setMinimumHeight(
            130
        )

        self.log_layout.addWidget(
            self.log_edit
        )

        self.right_layout.addWidget(
            self.log_card
        )

        self.content_layout.addWidget(
            self.right_widget,
            1
        )

    # =========================================================
    # STYLES
    # =========================================================

    def apply_styles(self):

        assets_dir = (
            Path(__file__).resolve().parents[2] / "assets"
        )

        chevron_up = (
            assets_dir / "chevron-up.svg"
        ).as_posix()

        chevron_down = (
            assets_dir / "chevron-down.svg"
        ).as_posix()

        check_icon = (
            assets_dir / "check.svg"
        ).as_posix()

        self.setStyleSheet(
            f"""
            QMainWindow {{
                background: #0F0F10;
            }}

            QWidget {{
                color: #E8E8E8;
                font-size: 10pt;
            }}

            QLabel {{
                color: #D8D8D8;
            }}

            QScrollArea {{
                background: transparent;
                border: none;
            }}

            QScrollArea#QueueScroll {{
                background: transparent;
                border: none;
            }}

            QScrollArea#QueueScroll QWidget {{
                background: transparent;
            }}

            QScrollBar:vertical {{
                background: transparent;
                width: 7px;
                margin: 4px 1px 4px 1px;
                border: none;
            }}

            QScrollBar::handle:vertical {{
                background: #3C3C40;
                min-height: 38px;
                border-radius: 3px;
            }}

            QScrollBar::handle:vertical:hover {{
                background: #5A5A60;
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
                background: transparent;
                border: none;
            }}

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
            }}

            QScrollBar:horizontal {{
                height: 7px;
                background: transparent;
                border: none;
            }}

            QScrollBar::handle:horizontal {{
                background: #3C3C40;
                min-width: 38px;
                border-radius: 3px;
            }}

            QScrollBar::handle:horizontal:hover {{
                background: #5A5A60;
            }}

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: transparent;
                border: none;
            }}

            QFrame#Card {{
                background: #181819;
                border: 1px solid #2B2B2E;
                border-radius: 12px;
            }}

            QLabel#Brand {{
                color: #F6F6F6;
                font-size: 9pt;
                font-weight: 700;
            }}

            QLabel#Title {{
                color: #FFFFFF;
                font-size: 17pt;
                font-weight: 700;
            }}

            QLabel#Hardware {{
                color: #A7A7AD;
                font-size: 9pt;
            }}

            QLabel#SectionTitle {{
                color: #F5F5F5;
                font-size: 12pt;
                font-weight: 700;
            }}

            QLabel#SubTitle {{
                color: #D6D6D8;
                font-size: 9pt;
                font-weight: 700;
            }}

            QLabel#QueueFilename {{
                color: #FFFFFF;
                font-size: 10pt;
                font-weight: 700;
            }}

            QLabel#QueueMeta {{
                color: #A0A0A5;
                font-size: 8.5pt;
            }}

            QLabel#QueueStatus {{
                color: #D7D7DA;
                font-size: 8.5pt;
            }}

            QLabel#QueueStats {{
                color: #B5B5BA;
                font-size: 8.5pt;
            }}

            QLabel#QueueSize {{
                color: #E0E0E2;
                font-size: 8.5pt;
            }}

            QLabel#EmptyQueue {{
                color: #808086;
                padding: 30px;
                font-size: 9pt;
            }}

            QLineEdit,
            QComboBox,
            QSpinBox,
            QDoubleSpinBox {{
                background: #101011;
                color: #F0F0F2;
                border: 1px solid #333338;
                border-radius: 7px;
                padding: 6px 9px;
                min-height: 19px;
                selection-background-color: #3C3C42;
                selection-color: #FFFFFF;
            }}

            QLineEdit:hover,
            QComboBox:hover,
            QSpinBox:hover,
            QDoubleSpinBox:hover {{
                background: #131315;
                border-color: #444449;
            }}

            QLineEdit:focus,
            QComboBox:focus,
            QSpinBox:focus,
            QDoubleSpinBox:focus {{
                background: #121214;
                border-color: #5A5A60;
            }}

            QLineEdit:disabled,
            QComboBox:disabled,
            QSpinBox:disabled,
            QDoubleSpinBox:disabled {{
                color: #66666B;
                background: #171718;
                border-color: #27272A;
            }}

            QComboBox {{
                padding-right: 30px;
            }}

            QComboBox::drop-down {{
                width: 26px;
                border: none;
                border-left: 1px solid #29292D;
                background: transparent;
            }}

            QComboBox::down-arrow {{
                image: url("{chevron_down}");
                width: 9px;
                height: 9px;
            }}

            QComboBox QAbstractItemView {{
                background: #19191B;
                color: #F2F2F2;
                border: 1px solid #38383D;
                border-radius: 7px;
                padding: 4px;
                outline: none;
                selection-background-color: #303036;
                selection-color: #FFFFFF;
            }}

            QComboBox QAbstractItemView::item {{
                min-height: 30px;
                padding: 5px 8px;
                border-radius: 5px;
            }}

            QComboBox QAbstractItemView::item:hover {{
                background: #28282D;
            }}

            QSpinBox,
            QDoubleSpinBox {{
                padding-right: 28px;
            }}

            QSpinBox::up-button,
            QSpinBox::down-button,
            QDoubleSpinBox::up-button,
            QDoubleSpinBox::down-button {{
                width: 22px;
                background: #18181A;
                border: none;
            }}

            QSpinBox::up-button,
            QDoubleSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                border-top-right-radius: 6px;
            }}

            QSpinBox::down-button,
            QDoubleSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                border-bottom-right-radius: 6px;
            }}

            QSpinBox::up-button:hover,
            QSpinBox::down-button:hover,
            QDoubleSpinBox::up-button:hover,
            QDoubleSpinBox::down-button:hover {{
                background: #29292E;
            }}

            QSpinBox::up-arrow,
            QDoubleSpinBox::up-arrow {{
                image: url("{chevron_up}");
                width: 8px;
                height: 8px;
            }}

            QSpinBox::down-arrow,
            QDoubleSpinBox::down-arrow {{
                image: url("{chevron_down}");
                width: 8px;
                height: 8px;
            }}

            QCheckBox {{
                color: #CFCFCF;
                spacing: 8px;
            }}

            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                background: #111111;
                border: 1px solid #3A3A3A;
                border-radius: 4px;
            }}

            QCheckBox::indicator:hover {{
                background: #181818;
                border-color: #555555;
            }}

            QCheckBox::indicator:checked {{
                background: #E8E8E8;
                border: 1px solid #E8E8E8;
                image: url("{check_icon}");
            }}

            QCheckBox::indicator:checked:hover {{
                background: #FFFFFF;
                border-color: #FFFFFF;
            }}

            QCheckBox::indicator:disabled {{
                background: #151515;
                border-color: #252525;
            }}

            QPushButton#GuideButton {{
                background: #1F1F21;
                color: #BDBDC2;
                border: 1px solid #343438;
                border-radius: 7px;
                padding: 6px 10px;
                min-height: 17px;
                font-size: 8.5pt;
                font-weight: 600;
            }}

            QPushButton#GuideButton:hover {{
                background: #29292D;
                color: #FFFFFF;
                border-color: #4A4A50;
            }}

            QPushButton#GuideButton:pressed {{
                background: #19191B;
                border-color: #303034;
            }}

            QPushButton#SettingsButton {{
                background: #1F1F21;
                color: #BDBDC2;
                border: 1px solid #343438;
                border-radius: 7px;
                padding: 6px 10px;
                min-height: 17px;
                font-size: 8.5pt;
                font-weight: 600;
            }}

            QPushButton#SettingsButton:hover {{
                background: #29292D;
                color: #FFFFFF;
                border-color: #4A4A50;
            }}

            QPushButton#SettingsButton:pressed {{
                background: #19191B;
                border-color: #303034;
            }}

            QPushButton {{
                background: #252528;
                color: #EEEEF0;
                border: 1px solid #38383D;
                border-radius: 7px;
                padding: 7px 13px;
                min-height: 19px;
                font-weight: 500;
            }}

            QPushButton:hover {{
                background: #303035;
                border-color: #4A4A50;
            }}

            QPushButton:pressed {{
                background: #202023;
                border-color: #343438;
            }}

            QPushButton:disabled {{
                color: #626267;
                background: #19191B;
                border-color: #29292D;
            }}

            QPushButton#PrimaryButton {{
                background: #F2F2F3;
                color: #101011;
                border: 1px solid #F2F2F3;
                border-radius: 8px;
                font-weight: 700;
                padding: 8px 18px;
            }}

            QPushButton#PrimaryButton:hover {{
                background: #FFFFFF;
                border-color: #FFFFFF;
            }}

            QPushButton#PrimaryButton:pressed {{
                background: #D8D8DA;
                border-color: #D8D8DA;
            }}

            QPushButton#PrimaryButton:disabled {{
                background: #29292C;
                color: #69696F;
                border-color: #333338;
            }}

            QPushButton#IconButton {{
                background: transparent;
                border: none;
                padding: 0px;
                min-height: 0px;
                color: #85858B;
                font-size: 15pt;
            }}

            QPushButton#IconButton:hover {{
                background: #28282D;
                color: #FFFFFF;
            }}

            QPushButton#IconButton:pressed {{
                background: #343439;
            }}

            QProgressBar {{
                background: #101011;
                border: 1px solid #29292D;
                border-radius: 4px;
                text-align: center;
                color: #BDBDC2;
                min-height: 7px;
                max-height: 7px;
            }}

            QProgressBar::chunk {{
                background: #E9E9EA;
                border-radius: 3px;
            }}

            QTextEdit {{
                background: #0C0C0D;
                border: 1px solid #2D2D31;
                border-radius: 8px;
                color: #C8C8CC;
                padding: 8px;
                font-family: "Consolas";
                font-size: 8.5pt;
                selection-background-color: #3C3C42;
                selection-color: #FFFFFF;
            }}

            QTextEdit:focus {{
                border-color: #45454B;
            }}

            QToolTip {{
                background: #202024;
                color: #F2F2F2;
                border: 1px solid #414147;
                padding: 5px 7px;
            }}
            """
        )

    # =========================================================
    # HARDWARE
    # =========================================================

    def update_hardware_status(self):

        engine = self.hardware.get_engine()

        if self.hardware.nvenc:

            self.hardware_label.setText(
                f"● {engine}"
            )

        else:

            self.hardware_label.setText(
                f"● {engine}"
            )

    # =========================================================
    # RESPONSIVE LAYOUT
    # =========================================================

    def resizeEvent(self, event):

        super().resizeEvent(
            event
        )

        self.update_responsive_layout()

    def update_responsive_layout(self):

        width = self.width()

        # -----------------------------------------------------
        # MAIN CONTENT
        # -----------------------------------------------------

        if width <= RESPONSIVE_BREAKPOINT:

            self.content_layout.setDirection(
                QBoxLayout.Direction.TopToBottom
            )

            self.settings_card.setMinimumWidth(
                0
            )

            self.settings_card.setMaximumWidth(
                16777215
            )

        else:

            self.content_layout.setDirection(
                QBoxLayout.Direction.LeftToRight
            )

            self.settings_card.setMinimumWidth(
                340
            )

            self.settings_card.setMaximumWidth(
                410
            )

        # -----------------------------------------------------
        # HEADER
        # -----------------------------------------------------

        if width <= HEADER_BREAKPOINT:

            self.header_layout.setDirection(
                QBoxLayout.Direction.TopToBottom
            )

            self.hardware_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft
            )

        else:

            self.header_layout.setDirection(
                QBoxLayout.Direction.LeftToRight
            )

            self.hardware_label.setAlignment(
                Qt.AlignmentFlag.AlignRight
            )

        # -----------------------------------------------------
        # INPUT
        # -----------------------------------------------------

        if width <= HEADER_BREAKPOINT:

            self.input_row.setDirection(
                QBoxLayout.Direction.TopToBottom
            )

        else:

            self.input_row.setDirection(
                QBoxLayout.Direction.LeftToRight
            )

        # -----------------------------------------------------
        # OUTPUT
        # -----------------------------------------------------

        if width <= HEADER_BREAKPOINT:

            self.output_row.setDirection(
                QBoxLayout.Direction.TopToBottom
            )

        else:

            self.output_row.setDirection(
                QBoxLayout.Direction.LeftToRight
            )

        # -----------------------------------------------------
        # ACTIONS
        # -----------------------------------------------------

        if width <= HEADER_BREAKPOINT:

            self.action_row.setDirection(
                QBoxLayout.Direction.TopToBottom
            )

        else:

            self.action_row.setDirection(
                QBoxLayout.Direction.LeftToRight
            )

    # =========================================================
    # PRESET
    # =========================================================

    def open_settings(self):

        dialog = SettingsDialog(
            self,
            self.settings_manager,
        )

        if (
            dialog.exec()
            == QDialog.DialogCode.Accepted
            and dialog.settings_saved is not None
        ):
            self.apply_settings(
                dialog.settings_saved
            )

    def apply_settings(self, settings):

        general = settings.get(
            "general",
            {}
        )

        video = settings.get(
            "video",
            {}
        )

        audio = settings.get(
            "audio",
            {}
        )

        processing = settings.get(
            "processing",
            {}
        )

        self.preset_combo.setCurrentIndex(
            max(
                0,
                self.preset_combo.findData(
                    "custom"
                )
            )
        )

        self.codec_combo.setCurrentIndex(
            max(
                0,
                self.codec_combo.findData(
                    video.get("codec", "h264")
                )
            )
        )

        try:
            resolution = int(
                video.get(
                    "max_resolution",
                    1920
                )
            )
        except (TypeError, ValueError):
            resolution = 1920

        resolution_index = (
            self.resolution_combo.findData(
                resolution
            )
        )
        if resolution_index >= 0:
            self.resolution_combo.setCurrentIndex(
                resolution_index
            )

        try:
            self.cq_spin.setValue(
                int(video.get("cq", 18))
            )
        except (TypeError, ValueError):
            self.cq_spin.setValue(18)

        fps = str(
            video.get("fps", "30")
        )
        self.fps_combo.setCurrentText(
            "Original"
            if fps.lower() == "original"
            else fps
        )

        self.encoder_combo.setCurrentText(
            str(
                video.get(
                    "nvenc_preset",
                    "p6"
                )
            )
        )

        self.audio_combo.setCurrentIndex(
            max(
                0,
                self.audio_combo.findData(
                    audio.get("codec", "aac")
                )
            )
        )

        self.audio_bitrate_combo.setCurrentText(
            str(
                audio.get(
                    "bitrate",
                    "192k"
                )
            )
        )

        try:
            channels = int(
                audio.get("channels", 2)
            )
            channel_index = (
                self.audio_channels_combo.findData(
                    channels
                )
            )
            if channel_index >= 0:
                self.audio_channels_combo.setCurrentIndex(
                    channel_index
                )
        except (TypeError, ValueError):
            pass

        try:
            self.audio_sample_rate = int(
                audio.get("sample_rate", 48000)
            )
        except (TypeError, ValueError):
            self.audio_sample_rate = 48000

        self.gpu_check.setChecked(
            bool(
                processing.get(
                    "gpu_acceleration",
                    True
                )
            )
        )

        self.fallback_check.setChecked(
            bool(
                processing.get(
                    "cpu_fallback",
                    True
                )
            )
        )

        self.metadata_check.setChecked(
            bool(
                processing.get(
                    "copy_metadata",
                    True
                )
            )
        )

        self.faststart_check.setChecked(
            bool(
                processing.get(
                    "faststart",
                    True
                )
            )
        )

        self.overwrite_existing = bool(
            general.get(
                "overwrite_existing",
                False
            )
        )

        self.auto_open_output = bool(
            general.get(
                "auto_open_output",
                False
            )
        )

        output_folder = str(
            general.get(
                "output_folder",
                "Compressed"
            )
        ).strip()

        output_path = Path(
            output_folder
            if output_folder
            else "Compressed"
        ).expanduser()

        if not output_path.is_absolute():
            output_path = (
                self.settings_manager.root_dir
                / output_path
            )

        self.output_edit.setText(
            str(output_path)
        )

    def open_settings_guide(self):

        dialog = SettingsGuideDialog(
            self
        )

        dialog.exec()

    def preset_changed(self):

        preset_id = (
            self.preset_combo
            .currentData()
        )

        if not preset_id:
            return

        preset = get_preset(
            preset_id
        )

        self.resolution_combo.setCurrentIndex(
            max(
                0,
                self.resolution_combo.findData(
                    preset.max_dimension
                )
            )
        )

        self.cq_spin.setValue(
            preset.cq
        )

        fps = str(
            preset.fps
        )

        if fps == "original":

            self.fps_combo.setCurrentText(
                "Original"
            )

        else:

            self.fps_combo.setCurrentText(
                fps
            )

        self.encoder_combo.setCurrentText(
            preset.encoder_preset
        )

        self.audio_bitrate_combo.setCurrentText(
            preset.audio_bitrate
        )

    # =========================================================
    # BUILD PRESET
    # =========================================================

    def build_current_preset(self):

        preset_id = (
            self.preset_combo
            .currentData()
        )

        preset = deepcopy(
            get_preset(
                preset_id
            )
        )

        resolution = (
            self.resolution_combo
            .currentData()
        )

        if resolution:

            preset.max_dimension = int(
                resolution
            )

        preset.codec = (
            self.codec_combo
            .currentData()
            or "h264"
        )

        preset.cq = int(
            self.cq_spin.value()
        )

        fps_text = (
            self.fps_combo
            .currentText()
        )

        if fps_text == "Original":

            preset.fps = "original"

        else:

            preset.fps = fps_text

        preset.encoder_preset = (
            self.encoder_combo
            .currentText()
        )

        preset.audio_mode = (
            self.audio_combo
            .currentData()
            or "aac"
        )

        preset.audio_bitrate = (
            self.audio_bitrate_combo
            .currentText()
        )

        preset.audio_channels = (
            self.audio_channels_combo
            .currentData()
            or 2
        )

        preset.audio_rate = (
            self.audio_sample_rate
        )

        preset.copy_metadata = (
            self.metadata_check.isChecked()
        )

        preset.faststart = (
            self.faststart_check.isChecked()
        )

        return preset

    # =========================================================
    # ADD VIDEOS
    # =========================================================

    def add_videos(self):

        files, _ = QFileDialog.getOpenFileNames(

            self,

            "Select Videos",

            "",

            (
                "Video Files "
                "(*.mp4 *.mov *.mkv *.avi "
                "*.webm *.m4v *.ts *.mts *.m2ts);;"
                "All Files (*)"
            ),
        )

        if not files:
            return

        for file_path in files:

            self.add_queue_item(
                file_path
            )

        self.input_edit.setText(
            f"{len(self.queue_items)} video(s) in queue"
        )

    # =========================================================
    # ADD FOLDER
    # =========================================================

    def add_folder(self):

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Video Folder"
        )

        if not folder:
            return

        extensions = {
            ".mp4",
            ".mov",
            ".mkv",
            ".avi",
            ".webm",
            ".m4v",
            ".ts",
            ".mts",
            ".m2ts",
        }

        folder_path = Path(
            folder
        )

        files = [
            path
            for path in folder_path.iterdir()
            if path.is_file()
            and path.suffix.lower()
            in extensions
        ]

        for file_path in sorted(
            files
        ):

            self.add_queue_item(
                file_path
            )

        self.input_edit.setText(
            f"{len(self.queue_items)} video(s) in queue"
        )

    # =========================================================
    # ADD QUEUE ITEM
    # =========================================================

    def add_queue_item(
        self,
        file_path
    ):

        file_path = Path(
            file_path
        )

        # Avoid duplicates.
        for item in self.queue_items:

            if (
                item.input_file.resolve()
                == file_path.resolve()
            ):

                return

        item = QueueItemWidget(

            file_path,

            self.remove_queue_item
        )

        self.queue_items.append(
            item
        )

        self.queue_container_layout.insertWidget(
            self.queue_container_layout.count() - 1,
            item
        )

        self.empty_queue_label.hide()

        # -----------------------------------------------------
        # Media info
        # -----------------------------------------------------

        ffprobe_path = (
            Path(
                self.hardware.ffmpeg_path
            ).parent
            / "ffprobe.exe"
        )

        probe_worker = MediaProbeTask(
            file_path,
            ffprobe_path,
        )
        probe_worker.signals.completed.connect(
            self.media_probe_completed
        )
        self._media_probe_workers.add(
            probe_worker
        )
        QThreadPool.globalInstance().start(
            probe_worker
        )

        self.queue_container.adjustSize()
        self.update_queue_height()

    def media_probe_completed(
        self,
        worker,
        input_file,
        info,
        error,
    ):

        self._media_probe_workers.discard(
            worker
        )

        if error:
            self.append_log(
                "[WARNING] Could not read media information for "
                f"{input_file}: {error}"
            )
            return

        if not info:
            self.append_log(
                "[WARNING] FFprobe returned no media information for "
                f"{input_file}."
            )
            return

        for item in self.queue_items:
            if item.input_file == input_file:
                video = MediaInfo.video_stream(
                    info
                )

                try:
                    fps = float(
                        Fraction(
                            str(
                                video.get(
                                    "r_frame_rate",
                                    "0/1"
                                )
                            )
                        )
                    )
                except (ValueError, ZeroDivisionError):
                    fps = 0.0

                format_info = info.get(
                    "format",
                    {}
                )

                try:
                    size = int(
                        format_info.get(
                            "size",
                            item.input_file.stat().st_size,
                        )
                    )
                except (OSError, TypeError, ValueError):
                    size = 0

                item.set_media_info({
                    "width": video.get("width", 0),
                    "height": video.get("height", 0),
                    "fps": fps,
                    "video_codec": video.get(
                        "codec_name",
                        "Unknown"
                    ),
                    "size": size,
                    "duration": MediaInfo.duration(info),
                })
                break

    # =========================================================
    # QUEUE HEIGHT
    # =========================================================

    def update_queue_height(self):

        count = len(self.queue_items)

        if count <= 0:
            height = 200
        else:
            height = min(430, 150 + (count * 72))
            height = max(260, height)

        self.queue_card.setFixedHeight(height)

    # =========================================================
    # REMOVE QUEUE ITEM
    # =========================================================

    def remove_queue_item(
        self,
        item
    ):

        if item not in self.queue_items:
            return

        self.queue_items.remove(
            item
        )

        item.setParent(
            None
        )

        item.deleteLater()

        if not self.queue_items:

            self.empty_queue_label.show()

        self.input_edit.setText(
            (
                f"{len(self.queue_items)} "
                "video(s) in queue"
            )
            if self.queue_items
            else ""
        )

        self.update_queue_height()

    # =========================================================
    # CLEAR QUEUE
    # =========================================================

    def clear_queue(self):

        if (
            self.current_worker
            and self.current_worker.isRunning()
        ):

            QMessageBox.warning(
                self,
                "Compression Running",
                "Cancel the current compression "
                "before clearing the queue."
            )

            return

        for item in list(
            self.queue_items
        ):

            item.setParent(
                None
            )

            item.deleteLater()

        self.queue_items.clear()

        self.empty_queue_label.show()

        self.input_edit.clear()

        self.update_queue_height()

    # =========================================================
    # OUTPUT
    # =========================================================

    def choose_output(self):

        folder = QFileDialog.getExistingDirectory(

            self,

            "Select Output Folder",

            self.output_edit.text()
        )

        if folder:

            self.output_edit.setText(
                folder
            )

    # =========================================================
    # START COMPRESSION
    # =========================================================

    def start_compression(self):

        if not self.queue_items:

            QMessageBox.information(
                self,
                "Queue Empty",
                "Add at least one video "
                "to the queue."
            )

            return

        if (
            self.current_worker
            and self.current_worker.isRunning()
        ):

            return

        self.log_edit.clear()

        self.start_button.setEnabled(
            False
        )

        self.cancel_button.setEnabled(
            True
        )

        self.current_queue_index = 0
        self.queue_succeeded = False
        self.last_output_dir = None

        self.start_next_queue_item()

    # =========================================================
    # NEXT QUEUE ITEM
    # =========================================================

    def start_next_queue_item(self):

        # -----------------------------------------------------
        # Find next unfinished item
        # -----------------------------------------------------

        while (
            self.current_queue_index
            < len(self.queue_items)
        ):

            item = self.queue_items[
                self.current_queue_index
            ]

            if not item.finished:
                break

            self.current_queue_index += 1

        # -----------------------------------------------------
        # Queue complete
        # -----------------------------------------------------

        if (
            self.current_queue_index
            >= len(self.queue_items)
        ):

            self.current_worker = None

            self.start_button.setEnabled(
                True
            )

            self.cancel_button.setEnabled(
                False
            )

            self.log_edit.append(
                "\n[QUEUE] All compression jobs completed."
            )

            if (
                self.auto_open_output
                and self.queue_succeeded
                and self.last_output_dir is not None
            ):
                if not QDesktopServices.openUrl(
                    QUrl.fromLocalFile(
                        str(self.last_output_dir)
                    )
                ):
                    self.append_log(
                        "[WARNING] Could not open output folder."
                    )

            return

        # -----------------------------------------------------
        # Current item
        # -----------------------------------------------------

        item = self.queue_items[
            self.current_queue_index
        ]

        output_text = (
            self.output_edit.text().strip()
        )

        output_dir = (
            Path(output_text).expanduser()
            if output_text
            else self.settings_manager.root_dir
            / "Compressed"
        )

        if not output_dir.is_absolute():
            output_dir = (
                self.settings_manager.root_dir
                / output_dir
            )

        try:
            output_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            if not output_dir.is_dir():
                raise NotADirectoryError(
                    f"Output path is not a directory:\n{output_dir}"
                )

        except (OSError, ValueError) as error:
            self.append_log(
                f"[ERROR] Could not prepare output folder: {error}"
            )
            QMessageBox.critical(
                self,
                "Invalid Output Folder",
                "GPUPress could not create or access the selected "
                "output folder.\n\n"
                f"{output_dir}\n\n{error}",
            )
            self.current_queue_index = -1
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            return

        output_file = self.get_output_file(
            output_dir,
            item.input_file,
        )

        preset = (
            self.build_current_preset()
        )

        worker = CompressionWorker(

            input_file=item.input_file,

            output_file=output_file,

            preset=preset,

            use_gpu=(
                self.gpu_check.isChecked()
            ),

            allow_cpu_fallback=(
                self.fallback_check.isChecked()
            ),

            overwrite_existing=(
                self.overwrite_existing
            ),

            hardware=self.hardware,
        )

        self.current_worker = worker

        item.set_worker(
            worker
        )

        worker.log_message.connect(
            self.append_log
        )

        worker.compression_finished.connect(
            self.current_item_finished
        )

        worker.compression_failed.connect(
            self.current_item_failed
        )

        worker.compression_cancelled.connect(
            self.current_item_cancelled
        )

        worker.finished.connect(
            self.worker_thread_finished
        )

        item.status_label.setText(
            "Starting..."
        )

        worker.start()

    def get_output_file(
        self,
        output_dir,
        input_file,
    ):

        output_name = (
            f"{input_file.stem}_compressed.mp4"
        )

        candidate = output_dir / output_name

        if self.overwrite_existing:
            return candidate

        suffix = 1

        while candidate.exists():
            candidate = output_dir / (
                f"{input_file.stem}_compressed_"
                f"{suffix}.mp4"
            )
            suffix += 1

        return candidate

    # =========================================================
    # LOG
    # =========================================================

    def append_log(
        self,
        message
    ):

        self.log_edit.append(
            str(message)
        )

    # =========================================================
    # CURRENT ITEM FINISHED
    # =========================================================

    def current_item_finished(
        self,
        output_file
    ):

        self.append_log(
            f"[QUEUE] Finished: {output_file}"
        )

        self.queue_succeeded = True
        self.last_output_dir = Path(
            output_file
        ).parent

        self.current_queue_index += 1

        QTimer.singleShot(
            150,
            self.start_next_queue_item
        )

    # =========================================================
    # CURRENT ITEM FAILED
    # =========================================================

    def current_item_failed(
        self,
        message
    ):

        self.append_log(
            ""
        )

        self.append_log(
            "[QUEUE] Job failed:"
        )

        self.append_log(
            str(message)
        )

        self.current_queue_index += 1

        QTimer.singleShot(
            150,
            self.start_next_queue_item
        )

    def current_item_cancelled(self):

        if (
            0 <= self.current_queue_index
            < len(self.queue_items)
        ):
            item = self.queue_items[
                self.current_queue_index
            ]
            item.set_status("Cancelled")
            item.set_progress(0)

        self.append_log(
            "[QUEUE] Current job cancelled. "
            "The remaining queue is paused."
        )

    # =========================================================
    # WORKER FINISHED
    # =========================================================

    def worker_thread_finished(self):

        worker = self.sender()

        if worker is None:
            return

        # -----------------------------------------------------
        # Clear process reference
        # -----------------------------------------------------

        if worker is self.current_worker:

            self.current_worker = None

            if getattr(worker, "cancel_requested", False):
                self.current_queue_index = -1
                self.start_button.setEnabled(True)
                self.cancel_button.setEnabled(False)

    # =========================================================
    # CANCEL
    # =========================================================

    def cancel_compression(self):

        worker = self.current_worker

        if worker is None:
            return

        if not worker.isRunning():
            return

        worker.cancel()

        self.cancel_button.setEnabled(
            False
        )

        self.append_log(
            "[QUEUE] Cancellation requested."
        )

    # =========================================================
    # CLOSE EVENT
    # =========================================================

    def closeEvent(
        self,
        event
    ):

        if (
            self.current_worker
            and self.current_worker.isRunning()
        ):

            answer = QMessageBox.question(

                self,

                "Compression Running",

                (
                    "A compression job is still running.\n\n"
                    "Cancel it and close the application?"
                ),

                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,

                QMessageBox.StandardButton.No,
            )

            if answer == QMessageBox.StandardButton.Yes:

                self.current_worker.cancel()

                if self.current_worker.wait(3000):
                    event.accept()
                else:
                    self.append_log(
                        "[WARNING] Compression is still stopping. "
                        "Close the application after the worker exits."
                    )
                    event.ignore()

            else:

                event.ignore()

            return

        event.accept()