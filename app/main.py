import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import __version__
from app.ui.main_window import MainWindow


APP_NAME = "GPUPress"
APP_BRAND = "by BAS1C VISUALS"


def main():
    app = QApplication(sys.argv)

    # -----------------------------------------------------
    # APPLICATION INFO
    # -----------------------------------------------------

    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setApplicationDisplayName(
        f"{APP_BRAND}"
    )
    app.setOrganizationName("BAS1C VISUALS")

    # -----------------------------------------------------
    # APPLICATION ICON
    # -----------------------------------------------------

    root_dir = Path(__file__).resolve().parent.parent
    icon_path = root_dir / "assets" / "icon.ico"

    app_icon = QIcon(str(icon_path))

    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    else:
        print(
            f"[WARNING] Could not load application icon:\n"
            f"{icon_path}"
        )

    # -----------------------------------------------------
    # DEFAULT FONT
    # -----------------------------------------------------

    font = app.font()
    font.setPointSize(10)
    app.setFont(font)

    # -----------------------------------------------------
    # MAIN WINDOW
    # -----------------------------------------------------

    window = MainWindow()

    # Explicitly apply icon to the window as well.
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)

    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())