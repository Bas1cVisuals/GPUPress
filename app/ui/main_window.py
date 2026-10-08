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
from app.core.batch import (
    BatchJobSnapshot,
    SUPPORTED_MEDIA_EXTENSIONS,
    discover_media_files,
    relative_output_directory,
    unique_output_path,
)
from app.core.media import MediaAnalysis, MediaInfo
from app.core.encoding_plan import (
    AudioMode,
    Codec,
    FPSMode,
    HDRMode,
    RateControl,
    ResolutionMode,
    create_encoding_plan,
    resolve_encoding_pipelines,
)
from app.core.presets import get_preset
from app.ui.encoding_controls import (
    adaptive_control_visibility,
    build_user_options,
    codec_choice_key,
    codec_choices,
    containers_for_codec,
    format_media_summary,
    format_plan_summary,
    parse_audio_bitrate,
)
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
                "A preset selects encoding intent for a workflow. Review the "
                "output plan before starting; the resolved output also "
                "depends on the analyzed source and available encoders."
            ),
            "Fast Web / Social": "Delivery-oriented H.264 settings for web and social exports.",
            "High Quality Delivery": "Higher-quality delivery intent; file size and visual results depend on the source and encoder.",
            "Small File": "Uses stronger compression intent; output is not guaranteed to be smaller.",
            "Maximum Compatibility": "Selects H.264 and AAC-oriented compatibility settings where applicable.",
            "Editing proxies": "H.264 Proxy presets create smaller-resolution H.264 files for editing workflows.",
            "Fast Scrub H.264": "Uses a shorter keyframe interval to support seeking; this can increase output size.",
            "ProRes and DNxHR": "Creates editing intermediates in the selected profile. These files may be substantially larger than delivery encodes.",
            "Original / Source Quality": "Keeps source resolution and requests source-oriented quality. This is not lossless encoding.",
            "Custom": "Use the available controls to specify codec, dimensions, frame rate, rate control, audio, and other options.",
        },

        "Video": {
            "Resolution": (
                "Selects an adaptive target tier, source dimensions, or "
                "custom dimensions. Aspect ratio is preserved by default; "
                "smaller footage is not enlarged unless upscaling is enabled."
            ),
            "Codec": (
                "Selects the requested output codec. H.264, HEVC, AV1, "
                "ProRes, and DNxHR choices depend on the installed FFmpeg "
                "encoders. Fallbacks retain the requested codec; GPUPress "
                "does not silently substitute a different codec."
            ),
            "Frame Rate": (
                "Auto/Source keeps the detected cadence where possible; "
                "explicit rates request constant-frame-rate output. VFR "
                "detection samples an initial packet window and is an estimate. "
                "GPUPress does not force every input to 30 FPS."
            ),
            "Quality and rate control": (
                "Quality values and bitrate controls are encoder-dependent. "
                "A quality setting does not guarantee a particular visual "
                "result, output size, or compression ratio."
            ),
            "NVENC Preset": (
                "Selects an NVIDIA encoder preset when a compatible NVENC "
                "encoder is available. Hardware, driver, input, and FFmpeg "
                "support affect whether a particular encode succeeds."
            ),
        },

        "Audio": {
            "Auto / Copy / AAC": (
                "Auto prefers copying audio when compatible with the output "
                "container and otherwise uses AAC fallback. Copy explicitly "
                "requests passthrough; AAC explicitly requests encoding."
            ),
            "Bitrate": (
                "The audio bitrate, sample rate, and channel controls apply "
                "when AAC encoding is selected. Copy retains the source audio "
                "stream's encoding properties."
            ),
            "Channels": (
                "Choose the output channel count when encoding AAC. Audio "
                "passthrough does not apply this conversion."
            ),
        },

        "HDR": {
            "HDR handling": (
                "Auto and Preserve request HDR signaling and a 10-bit-capable "
                "output path where supported. Output checks verify exposed "
                "metadata and bit depth; they do not establish visual or "
                "colorimetric HDR fidelity."
            ),
            "Tone Map to SDR": (
                "HDR-to-SDR tone mapping is not implemented. This option is "
                "disabled and requests are rejected rather than silently "
                "converted."
            ),
            "Dolby Vision": (
                "Dolby Vision metadata may be detected, but dynamic metadata "
                "preservation during re-encoding is unsupported. Such "
                "re-encoding is rejected."
            ),
        },

        "Processing": {
            "NVIDIA GPU Acceleration": (
                "Uses available NVIDIA decode, CUDA scaling, and NVENC paths. "
                "Capability listings do not guarantee every device/driver "
                "combination will encode successfully."
            ),
            "CPU Fallback": (
                "Allows a software path for the selected codec when the "
                "preferred hardware path fails. The requested codec is not "
                "silently changed."
            ),
            "Copy Metadata": (
                "Copies supported source metadata. Container and codec "
                "limitations may prevent some metadata from being retained."
            ),
            "Enable Faststart": (
                "Moves supported MP4/MOV index data toward the beginning "
                "of the file for progressive playback."
            ),
            "Folder queue": "Add Folder scans supported video extensions. Include subfolders enables recursive discovery; symbolic links and the selected output directory are excluded.",
            "Cancellation": "Cancelling terminates the active job and pauses pending jobs. Completed outputs remain available.",
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
        self.job_state = "Pending"
        self.error_detail = ""
        self.encoding_options = None
        self.output_file_path = None
        self.source_root = None

        self.input_size = 0

        self.output_size = 0

        self.duration = 0
        self.media_analysis = None
        self.encoding_options = None

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

        if isinstance(info, MediaAnalysis):
            self.media_analysis = info
            self.input_size = int(info.size or 0)
            self.duration = float(info.duration or 0)
            self.media_label.setText(format_media_summary(info))
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
        self.overwrite_existing = False
        self.auto_open_output = False
        self.queue_succeeded = False
        self.last_output_dir = None
        self._queue_encoding_options = None
        self._batch_output_root = None
        self._reserved_outputs = set()

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
            ("Fast Web / Social", "fast_web_social"),
            ("High Quality Delivery", "high_quality_delivery"),
            ("Small File", "small_file_delivery"),
            ("Maximum Compatibility", "compatibility"),
            ("H.264 Proxy 720p", "h264_proxy_720p"),
            ("H.264 Proxy 1080p", "h264_proxy_1080p"),
            ("Fast Scrub H.264", "fast_scrub_h264"),
            ("ProRes Proxy", "prores_proxy"),
            ("ProRes LT", "prores_lt"),
            ("ProRes 422", "prores_422"),
            ("DNxHR LB", "dnxhr_lb"),
            ("DNxHR SQ", "dnxhr_sq"),
            ("DNxHR HQ", "dnxhr_hq"),
            ("Original / Source Quality", "original_source_quality"),
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

        self.resolution_label = QLabel("Resolution")
        self.settings_grid.addWidget(self.resolution_label, 1, 0)

        self.resolution_combo = QComboBox()
        for label, mode in (
            ("Adaptive / Auto", ResolutionMode.AUTO),
            ("Source", ResolutionMode.SOURCE),
            ("720p", ResolutionMode.P720),
            ("1080p", ResolutionMode.P1080),
            ("1440p", ResolutionMode.P1440),
            ("2160p / 4K", ResolutionMode.P2160),
            ("Custom", ResolutionMode.CUSTOM),
        ):
            self.resolution_combo.addItem(label, mode.value)
        self.settings_grid.addWidget(
            self.resolution_combo,
            1,
            1
        )
        self.custom_resolution_widget = QWidget()
        custom_resolution_layout = QHBoxLayout(self.custom_resolution_widget)
        custom_resolution_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_width_spin = QSpinBox()
        self.custom_width_spin.setRange(2, 16384)
        self.custom_width_spin.setValue(1920)
        self.custom_width_spin.setPrefix("W ")
        self.custom_height_spin = QSpinBox()
        self.custom_height_spin.setRange(2, 16384)
        self.custom_height_spin.setValue(1080)
        self.custom_height_spin.setPrefix("H ")
        self.aspect_ratio_check = QCheckBox("Keep aspect ratio")
        self.aspect_ratio_check.setChecked(True)
        self.allow_upscale_check = QCheckBox("Allow upscale")
        custom_resolution_layout.addWidget(self.custom_width_spin)
        custom_resolution_layout.addWidget(self.custom_height_spin)
        custom_resolution_layout.addWidget(self.aspect_ratio_check)
        custom_resolution_layout.addWidget(self.allow_upscale_check)
        self.settings_grid.addWidget(self.custom_resolution_widget, 2, 0, 1, 2)

        # -----------------------------------------------------
        # CODEC
        # -----------------------------------------------------

        self.codec_label = QLabel("Codec")
        self.settings_grid.addWidget(self.codec_label, 3, 0)

        self.codec_combo = QComboBox()
        self.codec_choices_by_key = {
            choice.key: choice
            for choice in codec_choices(self.hardware.get_capabilities())
        }
        for index in range(self.preset_combo.count()):
            preset_id = self.preset_combo.itemData(index)
            if preset_id == "custom":
                continue
            preset_options = get_preset(preset_id).to_user_options()
            has_codec = any(
                choice.codec is preset_options.codec
                for choice in self.codec_choices_by_key.values()
            )
            if not has_codec:
                self.preset_combo.model().item(index).setEnabled(False)
        for choice in self.codec_choices_by_key.values():
            self.codec_combo.addItem(choice.label, choice.key)
        self.settings_grid.addWidget(self.codec_combo, 3, 1)

        self.quality_label = QLabel("Rate control")
        self.settings_grid.addWidget(self.quality_label, 4, 0)
        self.rate_control_combo = QComboBox()
        self.rate_control_combo.addItem("Quality", RateControl.CQ.value)
        self.rate_control_combo.addItem("Bitrate", RateControl.VBR.value)
        self.rate_control_combo.addItem("CBR", RateControl.CBR.value)
        self.settings_grid.addWidget(self.rate_control_combo, 4, 1)

        self.cq_spin = QSpinBox()
        self.cq_spin.setRange(1, 51)
        self.cq_spin.setValue(18)
        self.cq_spin.setPrefix("Quality ")
        self.bitrate_spin = QSpinBox()
        self.bitrate_spin.setRange(100, 200000)
        self.bitrate_spin.setValue(12000)
        self.bitrate_spin.setSuffix(" kbps")
        self.quality_value_widget = QWidget()
        quality_value_layout = QHBoxLayout(self.quality_value_widget)
        quality_value_layout.setContentsMargins(0, 0, 0, 0)
        quality_value_layout.addWidget(self.cq_spin)
        quality_value_layout.addWidget(self.bitrate_spin)
        self.settings_grid.addWidget(self.quality_value_widget, 5, 0, 1, 2)

        # -----------------------------------------------------
        # FPS
        # -----------------------------------------------------

        self.fps_label = QLabel("Frame rate")
        self.settings_grid.addWidget(self.fps_label, 6, 0)

        self.fps_combo = QComboBox()
        self.fps_combo.addItem("Source / Smart", "smart")
        for rate in ("23.976", "24", "25", "29.97", "30", "50", "59.94", "60"):
            self.fps_combo.addItem(f"{rate} FPS", rate)
        self.fps_combo.addItem("Custom", "custom")
        self.settings_grid.addWidget(self.fps_combo, 6, 1)
        self.custom_fps_spin = QDoubleSpinBox()
        self.custom_fps_spin.setRange(1.0, 240.0)
        self.custom_fps_spin.setDecimals(3)
        self.custom_fps_spin.setValue(30.0)
        self.custom_fps_spin.setSuffix(" FPS")
        self.settings_grid.addWidget(self.custom_fps_spin, 7, 1)

        # -----------------------------------------------------
        # ENCODER PRESET
        # -----------------------------------------------------

        self.encoder_label = QLabel("NVENC preset")
        self.settings_grid.addWidget(self.encoder_label, 8, 0)

        self.encoder_combo = QComboBox()
        for label, preset in (
            ("P1 Fastest", "p1"), ("P3 Fast", "p3"),
            ("P5 Balanced", "p5"), ("P6 Quality", "p6"),
            ("P7 Highest Quality", "p7"),
        ):
            self.encoder_combo.addItem(label, preset)
        self.encoder_combo.setCurrentIndex(3)
        self.settings_grid.addWidget(self.encoder_combo, 8, 1)

        self.gop_label = QLabel("Keyframe interval")
        self.settings_grid.addWidget(self.gop_label, 9, 0)
        self.gop_spin = QSpinBox()
        self.gop_spin.setRange(0, 1000)
        self.gop_spin.setSpecialValueText("Automatic")
        self.gop_spin.setValue(0)
        self.settings_grid.addWidget(self.gop_spin, 9, 1)

        self.hardware_label_option = QLabel("Encoding hardware")
        self.settings_grid.addWidget(self.hardware_label_option, 10, 0)
        self.hardware_combo = QComboBox()
        self.hardware_combo.addItem("Auto", "auto")
        self.hardware_combo.addItem("CPU", "cpu")
        self.hardware_combo.addItem("NVIDIA GPU", "gpu")
        if not any(choice.prefer_gpu for choice in self.codec_choices_by_key.values()):
            gpu_index = self.hardware_combo.findData("gpu")
            self.hardware_combo.model().item(gpu_index).setEnabled(False)
        self.settings_grid.addWidget(self.hardware_combo, 10, 1)
        self.capability_label = QLabel()
        self.capability_label.setWordWrap(True)
        self.capability_label.setObjectName("hardwareStatus")
        self.settings_grid.addWidget(self.capability_label, 11, 0, 1, 2)
        self.output_summary_label = QLabel("Output plan will appear when media is analyzed.")
        self.output_summary_label.setWordWrap(True)
        self.output_summary_label.setObjectName("hardwareStatus")
        self.settings_grid.addWidget(self.output_summary_label, 12, 0, 1, 2)

        self.container_label = QLabel("Container")
        self.settings_grid.addWidget(self.container_label, 13, 0)
        self.container_combo = QComboBox()
        self.settings_grid.addWidget(self.container_combo, 13, 1)

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
            "Auto (copy when compatible)",
            AudioMode.AUTO.value
        )

        self.audio_combo.addItem(
            "AAC",
            AudioMode.AAC.value
        )

        self.audio_combo.addItem(
            "Copy",
            AudioMode.COPY.value
        )

        self.audio_grid.addWidget(
            self.audio_combo,
            0,
            1
        )

        self.audio_bitrate_label = QLabel("Bitrate")
        self.audio_grid.addWidget(
            self.audio_bitrate_label,
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
                value,
                value,
            )

        self.audio_bitrate_combo.setCurrentText(
            "192k"
        )

        self.audio_grid.addWidget(
            self.audio_bitrate_combo,
            1,
            1
        )

        self.audio_channels_label = QLabel("Channels")
        self.audio_grid.addWidget(
            self.audio_channels_label,
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

        self.audio_sample_rate_label = QLabel("Sample rate")
        self.audio_grid.addWidget(self.audio_sample_rate_label, 3, 0)
        self.audio_sample_rate_combo = QComboBox()
        self.audio_sample_rate_combo.addItem("44.1 kHz", 44100)
        self.audio_sample_rate_combo.addItem("48 kHz", 48000)
        self.audio_sample_rate_combo.setCurrentIndex(1)
        self.audio_grid.addWidget(self.audio_sample_rate_combo, 3, 1)

        self.settings_layout.addLayout(
            self.audio_grid
        )

        self.hdr_grid = QGridLayout()
        self.hdr_grid.addWidget(QLabel("HDR handling"), 0, 0)
        self.hdr_combo = QComboBox()
        self.hdr_combo.addItem("Auto", HDRMode.AUTO.value)
        self.hdr_combo.addItem("Preserve", HDRMode.PRESERVE.value)
        self.hdr_combo.addItem("Tone Map to SDR — Coming soon", HDRMode.TONE_MAP_SDR.value)
        self.hdr_combo.model().item(2).setEnabled(False)
        self.hdr_grid.addWidget(self.hdr_combo, 0, 1)
        self.settings_layout.addLayout(self.hdr_grid)

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
        self.gpu_check.hide()

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

        self.codec_combo.currentIndexChanged.connect(self.update_adaptive_controls)
        self.resolution_combo.currentIndexChanged.connect(self.update_adaptive_controls)
        self.fps_combo.currentIndexChanged.connect(self.update_adaptive_controls)
        self.rate_control_combo.currentIndexChanged.connect(self.update_adaptive_controls)
        self.audio_combo.currentIndexChanged.connect(self.update_adaptive_controls)
        self.hardware_combo.currentIndexChanged.connect(self.update_adaptive_controls)
        self.container_combo.currentIndexChanged.connect(self.refresh_output_preview)
        for control in (
            self.custom_width_spin, self.custom_height_spin, self.custom_fps_spin,
            self.cq_spin, self.bitrate_spin, self.gop_spin,
            self.audio_bitrate_combo, self.audio_channels_combo,
            self.audio_sample_rate_combo, self.hdr_combo,
            self.aspect_ratio_check, self.allow_upscale_check,
            self.metadata_check, self.faststart_check, self.fallback_check,
        ):
            signal = getattr(control, "valueChanged", None) or getattr(control, "currentIndexChanged", None) or getattr(control, "toggled", None)
            if signal is not None:
                signal.connect(self.refresh_output_preview)

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

        self.folder_options = QHBoxLayout()
        self.recursive_check = QCheckBox("Include subfolders")
        self.folder_options.addWidget(self.add_folder_button)
        self.folder_options.addWidget(self.recursive_check)
        self.folder_options.addStretch(1)
        self.input_layout.addLayout(self.folder_options)

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
        self.batch_status_label = QLabel("Ready")
        self.batch_status_label.setObjectName("QueueStatus")
        self.queue_layout.addWidget(self.batch_status_label)
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setRange(0, 100)
        self.batch_progress_bar.setValue(0)
        self.batch_progress_bar.setTextVisible(False)
        self.batch_progress_bar.setFixedHeight(5)
        self.queue_layout.addWidget(self.batch_progress_bar)

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

        self.preset_combo.setCurrentIndex(max(0, self.preset_combo.findData("custom")))
        selected_codec = str(video.get("codec_choice", ""))
        if selected_codec not in self.codec_choices_by_key:
            selected_codec = self._legacy_codec_choice(video.get("codec", "h264"))
        self._set_combo_data(self.codec_combo, selected_codec)

        legacy_resolution = str(video.get("max_resolution", ""))
        resolution_mode = video.get("resolution_mode")
        if not resolution_mode:
            resolution_mode = {
                "1280": ResolutionMode.P720.value,
                "1920": ResolutionMode.P1080.value,
                "2560": ResolutionMode.P1440.value,
                "3840": ResolutionMode.P2160.value,
            }.get(legacy_resolution, ResolutionMode.AUTO.value)
        self._set_combo_data(self.resolution_combo, resolution_mode)
        self.custom_width_spin.setValue(int(video.get("custom_width", 1920)))
        self.custom_height_spin.setValue(int(video.get("custom_height", 1080)))
        self.aspect_ratio_check.setChecked(bool(video.get("preserve_aspect_ratio", True)))
        self.allow_upscale_check.setChecked(bool(video.get("allow_upscale", False)))

        try:
            self.cq_spin.setValue(
                int(video.get("cq", 18))
            )
        except (TypeError, ValueError):
            self.cq_spin.setValue(18)

        fps = str(video.get("fps_mode", video.get("fps", "smart"))).lower()
        if fps in ("original", "source", "auto", "smart"):
            fps = "smart"
        if fps not in ("smart", "custom") and fps not in {
            self.fps_combo.itemData(index)
            for index in range(self.fps_combo.count())
        }:
            fps = "smart"
        self._set_combo_data(self.fps_combo, fps)
        try:
            self.custom_fps_spin.setValue(float(video.get("custom_fps", 30)))
        except (TypeError, ValueError):
            self.custom_fps_spin.setValue(30)
        self._set_combo_data(
            self.rate_control_combo,
            video.get("rate_control", RateControl.CQ.value),
        )
        self.bitrate_spin.setValue(int(video.get("bitrate_kbps", 12000)))
        self._set_combo_data(
            self.encoder_combo,
            video.get("nvenc_preset", "p6"),
        )
        self.gop_spin.setValue(int(video.get("gop_size", 0) or 0))

        audio_mode = str(audio.get("mode", audio.get("codec", "auto"))).lower()
        if audio_mode == "aac":
            audio_mode = AudioMode.AAC.value
        elif audio_mode == "copy":
            audio_mode = AudioMode.COPY.value
        else:
            audio_mode = AudioMode.AUTO.value
        self.audio_combo.setCurrentIndex(
            max(
                0,
                self.audio_combo.findData(
                    audio_mode
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
            sample_rate = int(audio.get("sample_rate", 48000))
        except (TypeError, ValueError):
            sample_rate = 48000
        self._set_combo_data(self.audio_sample_rate_combo, sample_rate)
        self._set_combo_data(self.hdr_combo, video.get("hdr_mode", "auto"))
        self.preferred_container = video.get("container")

        hardware_mode = video.get("hardware_mode")
        if hardware_mode not in ("auto", "gpu", "cpu"):
            hardware_mode = (
                "auto"
                if processing.get("gpu_acceleration", True)
                else "cpu"
            )
        self._set_combo_data(self.hardware_combo, hardware_mode)
        self.gpu_check.setChecked(hardware_mode != "cpu")

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
        self.update_adaptive_controls()
        if self.preferred_container:
            self._set_combo_data(self.container_combo, self.preferred_container)
            self.refresh_output_preview()

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

        if preset_id == "custom":
            self.update_adaptive_controls()
            self.refresh_output_preview()
            return
        preset = get_preset(preset_id)
        options = preset.to_user_options()
        codec_key = codec_choice_key(options.codec, options.prefer_gpu)
        if codec_key not in self.codec_choices_by_key:
            software_choice = next(
                (
                    choice.key
                    for choice in self.codec_choices_by_key.values()
                    if choice.codec is options.codec
                ),
                None,
            )
            if software_choice is None:
                self.append_log(
                    f"[WARNING] {preset.name} is unavailable because its encoder "
                    "is not present in this FFmpeg installation."
                )
                self._set_combo_data(self.preset_combo, "custom")
                return
            codec_key = software_choice
        self._set_combo_data(self.codec_combo, codec_key)
        self._set_combo_data(self.resolution_combo, options.resolution_mode.value)
        self._set_combo_data(self.fps_combo, self._preset_fps_value(options))
        self._set_combo_data(self.audio_combo, options.audio_mode.value)
        self._set_combo_data(self.hdr_combo, options.hdr_mode.value)
        self._set_combo_data(self.rate_control_combo, options.rate_control.value)
        if options.quality is not None:
            self.cq_spin.setValue(max(self.cq_spin.minimum(), min(self.cq_spin.maximum(), int(options.quality))))
        if options.audio_fallback_bitrate:
            self.audio_bitrate_combo.setCurrentText(
                f"{options.audio_fallback_bitrate // 1000}k"
            )
        if options.sample_rate:
            self._set_combo_data(self.audio_sample_rate_combo, options.sample_rate)
        if options.encoder_preset:
            self._set_combo_data(self.encoder_combo, options.encoder_preset)
        self.gop_spin.setValue(options.gop_size or 0)
        self._set_combo_data(self.hardware_combo, "auto")
        self.update_adaptive_controls()
        self._set_combo_data(self.container_combo, options.container)
        self.refresh_output_preview()

    # =========================================================
    # BUILD ENCODING INTENT
    # =========================================================

    @staticmethod
    def _legacy_codec_choice(codec):
        return {
            "h264": "h264_nvenc",
            "hevc": "hevc_nvenc",
            "h265": "hevc_nvenc",
            "av1": "av1_nvenc",
        }.get(str(codec).lower(), "h264_software")

    @staticmethod
    def _preset_fps_value(options):
        if options.fps_mode in (FPSMode.AUTO, FPSMode.SMART, FPSMode.SOURCE):
            return "smart"
        if options.custom_fps is not None:
            return "custom"
        if options.target_fps is not None:
            return str(options.target_fps)
        return "smart"

    def build_current_options(self):
        choice = self.codec_choices_by_key.get(self.codec_combo.currentData())
        if choice is None:
            raise ValueError("The selected video encoder is unavailable.")
        hardware_mode = self.hardware_combo.currentData()
        prefer_gpu = (
            choice.prefer_gpu
            if hardware_mode == "auto"
            else hardware_mode == "gpu"
        )
        audio_mode = AudioMode(self.audio_combo.currentData())
        fps_value = self.fps_combo.currentData()
        resolution_mode = ResolutionMode(self.resolution_combo.currentData())
        rate_control = RateControl(self.rate_control_combo.currentData())
        bitrate = (
            self.bitrate_spin.value() * 1000
            if rate_control is not RateControl.CQ
            else None
        )
        container = self.container_combo.currentData() or "mp4"
        return build_user_options(
            codec_key=choice.key,
            resolution_mode=resolution_mode,
            custom_width=self.custom_width_spin.value(),
            custom_height=self.custom_height_spin.value(),
            preserve_aspect_ratio=self.aspect_ratio_check.isChecked(),
            allow_upscale=self.allow_upscale_check.isChecked(),
            fps_value=fps_value,
            custom_fps=self.custom_fps_spin.value(),
            audio_mode=audio_mode,
            audio_bitrate=parse_audio_bitrate(self.audio_bitrate_combo.currentData()),
            sample_rate=self.audio_sample_rate_combo.currentData(),
            channel_count=self.audio_channels_combo.currentData(),
            hdr_mode=HDRMode(self.hdr_combo.currentData()),
            rate_control=rate_control,
            quality=self.cq_spin.value(),
            bitrate=bitrate,
            encoder_preset=self.encoder_combo.currentData(),
            gop_size=self.gop_spin.value() or None,
            container=container,
            prefer_gpu=prefer_gpu,
            allow_cpu_fallback=self.fallback_check.isChecked(),
            preserve_metadata=self.metadata_check.isChecked(),
            faststart=self.faststart_check.isChecked(),
        )

    def update_adaptive_controls(self, *_):
        choice = self.codec_choices_by_key.get(self.codec_combo.currentData())
        codec = choice.codec if choice else Codec.H264
        hardware_mode = self.hardware_combo.currentData()
        if choice and hardware_mode in ("gpu", "cpu"):
            desired_gpu = hardware_mode == "gpu"
            if choice.prefer_gpu != desired_gpu:
                desired_key = codec_choice_key(codec, desired_gpu)
                if desired_key in self.codec_choices_by_key:
                    self._set_combo_data(self.codec_combo, desired_key)
                    choice = self.codec_choices_by_key[desired_key]
                    codec = choice.codec
                elif hardware_mode == "gpu":
                    self._set_combo_data(self.hardware_combo, "auto")
                    hardware_mode = "auto"
                else:
                    self._set_combo_data(self.hardware_combo, "auto")
                    hardware_mode = "auto"
        is_nvenc = bool(choice and choice.prefer_gpu)
        visibility = adaptive_control_visibility(
            codec=codec,
            nvenc=is_nvenc,
            resolution_mode=self.resolution_combo.currentData(),
            fps_value=self.fps_combo.currentData(),
            rate_control=self.rate_control_combo.currentData(),
            audio_mode=self.audio_combo.currentData(),
        )
        self.custom_resolution_widget.setVisible(visibility["custom_resolution"])
        self.custom_fps_spin.setVisible(visibility["custom_fps"])
        self.cq_spin.setVisible(visibility["cq_value"])
        self.bitrate_spin.setVisible(visibility["bitrate_value"])
        self.encoder_label.setText(
            "NVENC preset" if visibility["nvenc_preset"] else "Software preset"
        )
        self.encoder_label.setVisible(visibility["encoder_preset"])
        self.encoder_combo.setVisible(visibility["encoder_preset"])
        self.quality_label.setVisible(visibility["quality"])
        self.rate_control_combo.setVisible(visibility["rate_control"])
        self.quality_value_widget.setVisible(visibility["quality"])
        self.gop_label.setVisible(visibility["gop"])
        self.gop_spin.setVisible(visibility["gop"])
        self.hardware_label_option.setVisible(visibility["hardware"])
        self.hardware_combo.setVisible(visibility["hardware"])
        self.encoder_combo.blockSignals(True)
        self.encoder_combo.clear()
        encoder_choices = (
            (
                ("P1 Fastest", "p1"), ("P3 Fast", "p3"),
                ("P5 Balanced", "p5"), ("P6 Quality", "p6"),
                ("P7 Highest Quality", "p7"),
            )
            if is_nvenc
            else (
                ("Ultrafast", "ultrafast"), ("Fast", "fast"),
                ("Medium", "medium"), ("Slow", "slow"),
                ("Very slow", "veryslow"),
            )
            if codec in (Codec.H264, Codec.HEVC)
            else ()
        )
        for label, value in encoder_choices:
            self.encoder_combo.addItem(label, value)
        preferred_preset = (
            "p6" if is_nvenc else "medium"
        )
        self._set_combo_data(self.encoder_combo, preferred_preset)
        self.encoder_combo.blockSignals(False)
        audio_is_encoded = visibility["audio_encoding"]
        for widget in (
            self.audio_bitrate_combo, self.audio_sample_rate_combo,
            self.audio_channels_combo,
        ):
            widget.setVisible(audio_is_encoded)
        for widget in (
            self.audio_bitrate_label, self.audio_sample_rate_label,
            self.audio_channels_label,
        ):
            widget.setVisible(audio_is_encoded)
        self.container_combo.blockSignals(True)
        old_container = self.container_combo.currentData()
        self.container_combo.clear()
        for container in containers_for_codec(codec):
            self.container_combo.addItem(container.upper(), container)
        if old_container in containers_for_codec(codec):
            self._set_combo_data(self.container_combo, old_container)
        self.container_combo.blockSignals(False)
        gpu_enabled = (
            codec in (Codec.H264, Codec.HEVC, Codec.AV1)
            and codec_choice_key(codec, True) in self.codec_choices_by_key
        )
        cpu_enabled = (
            codec in (Codec.H264, Codec.HEVC, Codec.AV1)
            and codec_choice_key(codec, False) in self.codec_choices_by_key
        )
        gpu_index = self.hardware_combo.findData("gpu")
        self.hardware_combo.model().item(gpu_index).setEnabled(gpu_enabled)
        cpu_index = self.hardware_combo.findData("cpu")
        self.hardware_combo.model().item(cpu_index).setEnabled(cpu_enabled)
        if not gpu_enabled and self.hardware_combo.currentData() == "gpu":
            self._set_combo_data(self.hardware_combo, "auto")
        self.capability_label.setText(self._capability_summary())
        self.refresh_output_preview()

    def _capability_summary(self):
        caps = self.hardware.get_capabilities()
        gpu = caps.gpu_name or ("NVIDIA GPU detected" if caps.nvidia_available else "NVIDIA GPU unavailable")
        check = lambda available: "Available" if available else "Unavailable"
        return (
            f"GPU: {gpu}  ·  NVENC H.264: {check(caps.h264_nvenc)}  ·  "
            f"HEVC: {check(caps.hevc_nvenc)}  ·  AV1: {check(caps.av1_nvenc)}  ·  "
            f"CUDA: {check(caps.cuda)}"
        )

    def refresh_output_preview(self, *_):
        item = next(
            (queue_item for queue_item in self.queue_items if queue_item.media_analysis),
            None,
        )
        if item is None:
            self.output_summary_label.setText(
                "Output plan will appear when media is analyzed."
            )
            return
        try:
            options = self.build_current_options()
            plan = create_encoding_plan(
                item.media_analysis,
                options,
                self.hardware.get_capabilities(),
            )
            choice = self.codec_choices_by_key[self.codec_combo.currentData()]
            pipelines = resolve_encoding_pipelines(
                plan,
                self.hardware.get_capabilities(),
            )
            if pipelines[0] == "gpu":
                encoder_label = f"{choice.codec.value.upper()} NVENC · CUDA"
            elif pipelines[0] == "nvenc":
                encoder_label = f"{choice.codec.value.upper()} NVENC"
            else:
                encoder_label = (
                    choice.label
                    if choice.codec not in (Codec.H264, Codec.HEVC, Codec.AV1)
                    else f"{choice.codec.value.upper()} Software"
                )
            self.output_summary_label.setText(
                format_plan_summary(
                    plan,
                    encoder_label=encoder_label,
                    gpu_name=(
                        self.hardware.gpu_name
                        if pipelines[0] in ("gpu", "nvenc")
                        else None
                    ),
                )
            )
        except (ValueError, KeyError) as error:
            self.output_summary_label.setText(f"Output plan unavailable: {error}")

    @staticmethod
    def _set_combo_data(combo, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    # =========================================================
    # ADD VIDEOS
    # =========================================================

    def add_videos(self):

        files, _ = QFileDialog.getOpenFileNames(

            self,

            "Select Videos",

            "",

            (
                "Video Files ("
                + " ".join(f"*{extension}" for extension in sorted(SUPPORTED_MEDIA_EXTENSIONS))
                + ");;All Files (*)"
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

        folder_path = Path(
            folder
        ).resolve()
        output_directory = Path(self.output_edit.text()).expanduser()
        if not output_directory.is_absolute():
            output_directory = self.settings_manager.root_dir / output_directory
        try:
            files = discover_media_files(
                folder_path,
                recursive=self.recursive_check.isChecked(),
                excluded_directories=(output_directory,),
            )
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Folder Scan Failed", str(error))
            return
        for file_path in files:
            self.add_queue_item(file_path, source_root=folder_path)
        self.input_edit.setText(
            f"{len(files)} discovered · {len(self.queue_items)} total in queue"
        )

    # =========================================================
    # ADD QUEUE ITEM
    # =========================================================

    def add_queue_item(
        self,
        file_path,
        source_root=None,
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
        item.preset_id = self.preset_combo.currentData()

        self.queue_items.append(
            item
        )
        item.source_root = source_root
        if self._queue_encoding_options is not None:
            item.encoding_options = self._queue_encoding_options

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
                item.set_media_info(info)
                self.refresh_output_preview()
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

        try:
            self._queue_encoding_options = self.build_current_options()
            self._persist_encoding_options()
            output_text = self.output_edit.text().strip()
            self._batch_output_root = (
                Path(output_text).expanduser()
                if output_text
                else self.settings_manager.root_dir / "Compressed"
            )
            if not self._batch_output_root.is_absolute():
                self._batch_output_root = (
                    self.settings_manager.root_dir / self._batch_output_root
                )
            self._reserved_outputs.clear()
            for item in self.queue_items:
                if item.finished:
                    continue
                item.encoding_options = self._queue_encoding_options
                relative_directory = relative_output_directory(
                    item.source_root,
                    item.input_file,
                )
                item.output_file_path = unique_output_path(
                    self._batch_output_root / relative_directory,
                    item.input_file,
                    container=self._queue_encoding_options.container,
                    reserved_paths=self._reserved_outputs,
                )
                item.preset_id = self.preset_combo.currentData()
                item.batch_snapshot = BatchJobSnapshot(
                    input_path=item.input_file,
                    output_path=item.output_file_path,
                    options=self._queue_encoding_options,
                    preset_id=item.preset_id,
                )
                item.job_state = "Pending"
                item.error_detail = ""
                item.set_status("Pending")
                item.status_label.setToolTip("")
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(
                self,
                "Could Not Prepare Batch",
                str(error),
            )
            return

        self.log_edit.clear()

        self.start_button.setEnabled(
            False
        )

        self.cancel_button.setEnabled(
            True
        )
        self.input_button.setEnabled(False)
        self.add_folder_button.setEnabled(False)
        self.recursive_check.setEnabled(False)
        self.clear_queue_button.setEnabled(False)
        for item in self.queue_items:
            item.remove_button.setEnabled(False)
        self.batch_progress_bar.setValue(0)
        self.update_batch_status()

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
            self._queue_encoding_options = None

            self.start_button.setEnabled(
                True
            )

            self.cancel_button.setEnabled(
                False
            )
            self.input_button.setEnabled(True)
            self.add_folder_button.setEnabled(True)
            self.recursive_check.setEnabled(True)
            self.clear_queue_button.setEnabled(True)
            for queued_item in self.queue_items:
                queued_item.remove_button.setEnabled(True)
            self.update_batch_status()

            self.log_edit.append(
                "\n[QUEUE] Batch processing finished."
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

        output_file = item.output_file_path
        if output_file is None:
            self._fail_current_queue_item(
                "Batch item is missing its captured output path."
            )
            return
        output_dir = output_file.parent

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
            QMessageBox.critical(
                self,
                "Invalid Output Folder",
                "GPUPress could not create or access the selected "
                "output folder.\n\n"
                f"{output_dir}\n\n{error}",
            )
            self._fail_current_queue_item(
                f"Could not prepare output folder {output_dir}: {error}"
            )
            return

        preset = item.encoding_options
        if preset is None:
            self._fail_current_queue_item(
                "Queue item is missing its captured encoding intent."
            )
            return
        snapshot = getattr(item, "batch_snapshot", None)
        if snapshot is None:
            self._fail_current_queue_item(
                "Batch item has no immutable job snapshot."
            )
            return

        worker = CompressionWorker(

            input_file=snapshot.input_path,

            output_file=snapshot.output_path,

            preset=snapshot.options,

            use_gpu=preset.prefer_gpu,

            allow_cpu_fallback=preset.allow_cpu_fallback,

            overwrite_existing=(
                self.overwrite_existing
            ),

            hardware=self.hardware,
            media_analysis=item.media_analysis,
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

        item.job_state = "Analyzing"
        item.status_label.setText(
            f"Analyzing · {self.current_queue_index + 1}/{len(self.queue_items)}"
        )
        worker.stats_changed.connect(
            lambda stats, queue_item=item, job_index=self.current_queue_index:
                self.update_batch_progress(queue_item, job_index, stats)
        )
        worker.status_changed.connect(
            lambda status, queue_item=item:
                self.set_queue_item_encoding_status(queue_item, status)
        )
        self.update_batch_status()

        worker.start()

    def set_queue_item_encoding_status(self, item, status):
        if item.job_state in ("Completed", "Failed", "Cancelled"):
            return
        if str(status).lower().startswith("analy"):
            item.job_state = "Analyzing"
            item.set_status("Analyzing")
        else:
            item.job_state = "Encoding"
            item.set_status(f"Encoding · {status}")
        self.update_batch_status()

    def update_batch_progress(self, current_item, job_index, stats):
        progress = int(stats.get("progress", 0) or 0)
        current_item.set_progress(progress)
        durations = [
            item.media_analysis.duration
            if item.media_analysis and item.media_analysis.duration
            else None
            for item in self.queue_items
        ]
        weighted = all(duration is not None for duration in durations)
        weights = durations if weighted else [1.0] * len(self.queue_items)
        total_weight = sum(weights)
        completed_weight = sum(
            weight
            for index, (item, weight) in enumerate(zip(self.queue_items, weights))
            if index < job_index or item.job_state in ("Completed", "Failed")
        )
        overall = int(
            100 * (completed_weight + weights[job_index] * progress / 100)
            / total_weight
        ) if total_weight else 0
        self.batch_progress_bar.setValue(max(0, min(100, overall)))
        mode = "duration-weighted" if weighted else "approximate"
        self.batch_status_label.setText(
            f"Processing {job_index + 1} / {len(self.queue_items)} · "
            f"{current_item.input_file.name} · {progress}% "
            f"(overall {mode}: {overall}%)"
        )

    def update_batch_status(self):
        counts = {
            state: sum(item.job_state == state for item in self.queue_items)
            for state in (
                "Completed", "Failed", "Cancelled", "Pending",
                "Analyzing", "Encoding",
            )
        }
        self.batch_status_label.setText(
            f"Completed: {counts['Completed']}  ·  "
            f"Failed: {counts['Failed']}  ·  "
            f"Cancelled: {counts['Cancelled']}  ·  "
            f"Pending: {counts['Pending']}  ·  "
            f"Active: {counts['Analyzing'] + counts['Encoding']}"
        )

    def _persist_encoding_options(self):
        settings = self.settings_manager.settings
        video = settings.setdefault("video", {})
        selected_choice = self.codec_choices_by_key[self.codec_combo.currentData()]
        video.update({
            "codec_choice": self.codec_combo.currentData(),
            "codec": selected_choice.codec.value,
            "resolution_mode": self.resolution_combo.currentData(),
            "max_resolution": {
                ResolutionMode.P720.value: "1280",
                ResolutionMode.P1080.value: "1920",
                ResolutionMode.P1440.value: "2560",
                ResolutionMode.P2160.value: "3840",
            }.get(self.resolution_combo.currentData(), "source"),
            "custom_width": self.custom_width_spin.value(),
            "custom_height": self.custom_height_spin.value(),
            "fps_mode": self.fps_combo.currentData(),
            "custom_fps": self.custom_fps_spin.value(),
            "rate_control": self.rate_control_combo.currentData(),
            "cq": self.cq_spin.value(),
            "bitrate_kbps": self.bitrate_spin.value(),
            "nvenc_preset": self.encoder_combo.currentData(),
            "gop_size": self.gop_spin.value(),
            "hdr_mode": self.hdr_combo.currentData(),
            "hardware_mode": self.hardware_combo.currentData(),
            "container": self.container_combo.currentData(),
            "preserve_aspect_ratio": self.aspect_ratio_check.isChecked(),
            "allow_upscale": self.allow_upscale_check.isChecked(),
        })
        audio = settings.setdefault("audio", {})
        audio.update({
            "mode": self.audio_combo.currentData(),
            "bitrate": self.audio_bitrate_combo.currentData(),
            "sample_rate": self.audio_sample_rate_combo.currentData(),
            "channels": self.audio_channels_combo.currentData(),
        })
        processing = settings.setdefault("processing", {})
        processing.update({
            "gpu_acceleration": self.hardware_combo.currentData() != "cpu",
            "cpu_fallback": self.fallback_check.isChecked(),
            "faststart": self.faststart_check.isChecked(),
            "copy_metadata": self.metadata_check.isChecked(),
        })
        self.settings_manager.save(settings)

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
        item = self.queue_items[self.current_queue_index]
        item.job_state = "Completed"
        self.last_output_dir = Path(
            output_file
        ).parent
        self.update_batch_status()

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
        self._fail_current_queue_item(str(message))

    def _fail_current_queue_item(self, message):
        self.append_log("")
        self.append_log("[QUEUE] Job failed:")
        self.append_log(str(message))
        if 0 <= self.current_queue_index < len(self.queue_items):
            item = self.queue_items[self.current_queue_index]
            item.job_state = "Failed"
            item.error_detail = str(message)
            item.set_status("Failed")
            item.status_label.setToolTip(str(message))
        self.update_batch_status()

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
            item.job_state = "Cancelled"
            item.error_detail = "Cancelled by user."

        self.append_log(
            "[QUEUE] Current job cancelled. "
            "The remaining queue is paused."
        )
        self.update_batch_status()

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
                self.input_button.setEnabled(True)
                self.add_folder_button.setEnabled(True)
                self.recursive_check.setEnabled(True)
                self.clear_queue_button.setEnabled(True)
                for queued_item in self.queue_items:
                    queued_item.remove_button.setEnabled(True)
                self._queue_encoding_options = None
                self.update_batch_status()

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