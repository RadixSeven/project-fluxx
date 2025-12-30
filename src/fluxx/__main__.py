"""Main entry point for Project Fluxx."""

import sys

from PySide6.QtWidgets import QApplication

from fluxx.gui.main_window import MainWindow


def main() -> int:
    """Run the Project Fluxx application.

    Returns:
        Exit code (0 for success)
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
