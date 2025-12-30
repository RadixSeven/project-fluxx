"""Main entry point for Project Fluxx."""

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from fluxx.data.persistence import FileFormatError, VersionError
from fluxx.gui.main_window import MainWindow


def main() -> int:
    """Run the Project Fluxx application.

    Returns:
        Exit code (0 for success)
    """
    parser = argparse.ArgumentParser(description="Project Fluxx")
    parser.add_argument(
        "file", nargs="?", help="Path to a Project Fluxx (.fluxx) file to open"
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MainWindow()

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            try:
                # Ensure it has .fluxx extension if not provided?
                # The requirement doesn't specify, but MainWindow._on_save_as does it.
                if file_path.suffix != ".fluxx":
                    file_path = file_path.with_suffix(".fluxx")

                window.controller.new_project("Untitled")
                window.controller.save_project_as(file_path)
            except Exception as e:
                QMessageBox.critical(
                    window,
                    "Error Creating Project",
                    f"Failed to create project at {file_path}: {e}",
                )
        else:
            try:
                window.controller.open_project(file_path)
            except (FileFormatError, VersionError) as e:
                QMessageBox.critical(
                    window,
                    "Error Opening Project",
                    f"Failed to open project: {e}",
                )
            except Exception as e:
                QMessageBox.critical(
                    window,
                    "Error Opening Project",
                    f"Unexpected error: {e}",
                )

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
