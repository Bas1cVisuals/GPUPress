APP_STYLE = """
/* =========================================================
   GPUPress
   PREMIUM DARK UI
   ========================================================= */


/* =========================================================
   GLOBAL
   ========================================================= */

QMainWindow,
QWidget {
    background: #0b0c0f;
    color: #f3f4f6;
    font-family: "Segoe UI";
    font-size: 10pt;
}


/* =========================================================
   MAIN WINDOW
   ========================================================= */

QMainWindow {
    background: #0b0c0f;
}


/* =========================================================
   LABELS
   ========================================================= */

QLabel {
    color: #aeb2ba;
    background: transparent;
}

QLabel#appTitle {
    color: #ffffff;
    font-size: 23pt;
    font-weight: 700;
    letter-spacing: 1px;
}

QLabel#appSubtitle {
    color: #70757f;
    font-size: 8pt;
    font-weight: 600;
    letter-spacing: 2px;
}

QLabel#sectionTitle {
    color: #f4f5f7;
    font-size: 12pt;
    font-weight: 650;
}

QLabel#hardwareStatus {
    color: #9ee6b8;
    background: #101914;
    border: 1px solid #1c3325;
    border-radius: 8px;
    padding: 8px 13px;
    font-size: 9pt;
    font-weight: 600;
}

QLabel#queueFileName {
    color: #e8e9ec;
    font-size: 9pt;
    font-weight: 550;
}

QLabel#queueStatus {
    color: #858b95;
    font-size: 8pt;
    font-weight: 600;
}


/* =========================================================
   CARDS
   ========================================================= */

QFrame#card {
    background: #111318;
    border: 1px solid #1e2128;
    border-radius: 14px;
}

QFrame#dropZone {
    background: #0f1115;
    border: 1px dashed #30343d;
    border-radius: 14px;
}

QFrame#dropZone:hover {
    background: #11141a;
    border: 1px dashed #555b66;
}


/* =========================================================
   QUEUE ITEM
   ========================================================= */

QFrame#queueItem {
    background: #15171c;
    border: 1px solid #20242c;
    border-radius: 10px;
}

QFrame#queueItem:hover {
    background: #181b21;
    border: 1px solid #2b3039;
}


/* =========================================================
   BUTTONS
   ========================================================= */

QPushButton {
    background: #191c22;
    color: #e5e7eb;
    border: 1px solid #292d35;
    border-radius: 8px;
    padding: 9px 15px;
    min-height: 18px;
    font-weight: 600;
}

QPushButton:hover {
    background: #20242b;
    border: 1px solid #383e48;
}

QPushButton:pressed {
    background: #15171c;
}

QPushButton:disabled {
    color: #555a63;
    background: #121419;
    border: 1px solid #1d2026;
}

QPushButton#primaryButton {
    background: #f2f3f5;
    color: #0a0b0d;
    border: 1px solid #ffffff;
    border-radius: 9px;
    padding: 10px 20px;
    font-weight: 700;
}

QPushButton#primaryButton:hover {
    background: #ffffff;
    color: #000000;
}

QPushButton#primaryButton:pressed {
    background: #dcdfe4;
}

QPushButton#smallButton {
    background: transparent;
    color: #777d87;
    border: none;
    border-radius: 6px;
    padding: 0;
    font-size: 15pt;
    font-weight: 400;
}

QPushButton#smallButton:hover {
    background: #24272e;
    color: #ffffff;
}


/* =========================================================
   COMBO BOX
   ========================================================= */

QComboBox {
    background: #17191e;
    color: #e7e9ed;
    border: 1px solid #292d35;
    border-radius: 7px;
    padding: 8px 11px;
    min-height: 18px;
    selection-background-color: #2a2e36;
}

QComboBox:hover {
    border: 1px solid #3a404a;
}

QComboBox:focus {
    border: 1px solid #555c67;
}

QComboBox::drop-down {
    width: 28px;
    border: none;
    background: transparent;
}

QComboBox QAbstractItemView {
    background: #17191e;
    color: #e7e9ed;
    border: 1px solid #30343c;
    selection-background-color: #2a2e36;
    selection-color: #ffffff;
    outline: none;
    padding: 5px;
}


/* =========================================================
   SPIN BOX
   ========================================================= */

QSpinBox {
    background: #17191e;
    color: #e7e9ed;
    border: 1px solid #292d35;
    border-radius: 7px;
    padding: 7px 8px;
    min-height: 18px;
}

QSpinBox:hover {
    border: 1px solid #3a404a;
}

QSpinBox:focus {
    border: 1px solid #555c67;
}

QSpinBox::up-button,
QSpinBox::down-button {
    width: 18px;
    border: none;
    background: transparent;
}


/* =========================================================
   LINE EDIT
   ========================================================= */

QLineEdit {
    background: #17191e;
    color: #dfe1e5;
    border: 1px solid #292d35;
    border-radius: 7px;
    padding: 8px 10px;
    selection-background-color: #3a3f48;
}

QLineEdit:focus {
    border: 1px solid #555c67;
}


/* =========================================================
   CHECKBOX
   ========================================================= */

QCheckBox {
    color: #b9bdc5;
    spacing: 9px;
    padding: 3px 0;
}

QCheckBox:hover {
    color: #e8e9ec;
}

QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    background: #17191e;
    border: 1px solid #363a43;
}

QCheckBox::indicator:hover {
    border: 1px solid #5a606b;
}

QCheckBox::indicator:checked {
    background: #E8E8E8;
    border: 1px solid #E8E8E8;
    image: url("assets/check.svg");
}

QCheckBox::indicator:disabled {
    background: #121419;
    border: 1px solid #24272d;
}


/* =========================================================
   PROGRESS BAR
   ========================================================= */

QProgressBar {
    background: #0d0f12;
    color: #dfe2e6;
    border: 1px solid #252930;
    border-radius: 6px;
    text-align: center;
    min-height: 12px;
    max-height: 12px;
    font-size: 7pt;
    font-weight: 600;
}

QProgressBar::chunk {
    background: #e8e9eb;
    border-radius: 5px;
}


/* =========================================================
   TEXT EDIT / LOG
   ========================================================= */

QTextEdit {
    background: #08090b;
    color: #8e949e;
    border: 1px solid #1d2026;
    border-radius: 10px;
    padding: 10px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 8pt;
    selection-background-color: #30343c;
    selection-color: #ffffff;
}


/* =========================================================
   SCROLL AREA
   ========================================================= */

QScrollArea {
    background: transparent;
    border: none;
}

QScrollArea > QWidget > QWidget {
    background: transparent;
}


/* =========================================================
   SCROLL BARS
   ========================================================= */

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #292d34;
    border-radius: 4px;
    min-height: 35px;
}

QScrollBar::handle:vertical:hover {
    background: #3c424c;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
}

QScrollBar::handle:horizontal {
    background: #292d34;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #3c424c;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}


/* =========================================================
   TOOLTIPS
   ========================================================= */

QToolTip {
    background: #17191e;
    color: #f0f1f3;
    border: 1px solid #343943;
    padding: 7px 9px;
    border-radius: 6px;
    font-size: 8pt;
}


/* =========================================================
   MESSAGE BOX
   ========================================================= */

QMessageBox {
    background: #111318;
}

QMessageBox QLabel {
    color: #e5e7eb;
}

QMessageBox QPushButton {
    min-width: 80px;
}


/* =========================================================
   MENU
   ========================================================= */

QMenu {
    background: #17191e;
    color: #e5e7eb;
    border: 1px solid #30343c;
    padding: 5px;
}

QMenu::item {
    padding: 7px 20px;
    border-radius: 5px;
}

QMenu::item:selected {
    background: #292e36;
}


/* =========================================================
   SPLITTER
   ========================================================= */

QSplitter::handle {
    background: #1d2026;
}

QSplitter::handle:hover {
    background: #30353e;
}


/* =========================================================
   DISABLED
   ========================================================= */

QWidget:disabled {
    color: #555a63;
}
"""