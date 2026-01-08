"""Main entry point for Project Fluxx."""

import argparse
import csv
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from fluxx.data.persistence import FileFormatError, VersionError, load_project
from fluxx.gui.main_window import MainWindow
from fluxx.logging_config import DEFAULT_LOG_LEVEL, LOG_LEVELS, configure_logging


def write_historical_data_csv(project_path: Path, output_path: Path) -> int:
    """Export Jira historical data from a project file to CSV.

    Args:
        project_path: Path to the .fluxx project file
        output_path: Path to write the CSV output

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        project = load_project(project_path)
    except (FileFormatError, VersionError) as e:
        print(f"Error loading project: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error loading project: {e}", file=sys.stderr)
        return 1

    if project.jira_config is None:
        print("No Jira configuration found in project.", file=sys.stderr)
        return 1

    history_entries = project.jira_config.sync_metadata.history_entries

    if not history_entries:
        print("No historical data entries found in project.", file=sys.stderr)
        return 1

    # Define CSV columns
    fieldnames = [
        "server_url",
        "issue_key",
        "issue_type",
        "worker_jira_id",
        "original_estimate_hours",
        "total_logged_hours",
        "remaining_estimate_hours",
        "story_points",
        "created_datetime",
        "resolved_datetime",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for entry in history_entries:
            # Convert seconds to hours for time fields
            original_estimate_hours = (
                entry.original_estimate_seconds / 3600.0
                if entry.original_estimate_seconds is not None
                else None
            )
            total_logged_hours = (
                entry.total_logged_time_seconds / 3600.0
                if entry.total_logged_time_seconds is not None
                else None
            )
            remaining_estimate_hours = (
                entry.remaining_estimate_seconds / 3600.0
                if entry.remaining_estimate_seconds is not None
                else None
            )

            writer.writerow(
                {
                    "server_url": entry.server_url,
                    "issue_key": str(entry.issue_key),
                    "issue_type": entry.issue_type,
                    "worker_jira_id": entry.worker_jira_id,
                    "original_estimate_hours": original_estimate_hours,
                    "total_logged_hours": total_logged_hours,
                    "remaining_estimate_hours": remaining_estimate_hours,
                    "story_points": entry.story_points,
                    "created_datetime": (
                        entry.created_datetime.isoformat()
                        if entry.created_datetime is not None
                        else None
                    ),
                    "resolved_datetime": (
                        entry.resolved_datetime.isoformat()
                        if entry.resolved_datetime is not None
                        else None
                    ),
                }
            )

    print(f"Wrote {len(history_entries)} entries to {output_path}")
    return 0


def main() -> int:
    """Run the Project Fluxx application.

    Returns:
        Exit code (0 for success)
    """
    parser = argparse.ArgumentParser(description="Project Fluxx")
    parser.add_argument(
        "file", nargs="?", help="Path to a Project Fluxx (.fluxx) file to open"
    )
    parser.add_argument(
        "--write-historical-data-csv",
        metavar="OUTPUT",
        help="Export Jira historical data to CSV file and exit",
    )
    parser.add_argument(
        "--log-level",
        choices=sorted(LOG_LEVELS),
        default=DEFAULT_LOG_LEVEL,
        type=str.upper,
        metavar="LEVEL",
        help=(
            f"Set logging verbosity (default: {DEFAULT_LOG_LEVEL}). "
            f"Choices: {', '.join(sorted(LOG_LEVELS))}"
        ),
    )
    args = parser.parse_args()

    # Configure logging early
    configure_logging(args.log_level)

    # Handle CSV export mode
    if args.write_historical_data_csv:
        if not args.file:
            print(
                "Error: --write-historical-data-csv requires a .fluxx file argument",
                file=sys.stderr,
            )
            return 1
        return write_historical_data_csv(
            Path(args.file), Path(args.write_historical_data_csv)
        )

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
