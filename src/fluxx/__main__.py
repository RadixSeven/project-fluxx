"""Main entry point for Project Fluxx."""

import argparse
import csv
import sys
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from fluxx.data.persistence import FileFormatError, VersionError, load_project
from fluxx.gui.main_window import MainWindow
from fluxx.logging_config import DEFAULT_LOG_LEVEL, LOG_LEVELS, configure_logging
from fluxx.simulation.engine import SimulationEngine


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


def run_simulation(
    project_path: Path, num_samples: int, json_output_path: Path | None = None
) -> int:
    """Run a headless simulation on a project file.

    Args:
        project_path: Path to the .fluxx project file
        num_samples: Number of simulation samples to run
        json_output_path: Optional path to write JSON results

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

    # Get workers from project
    workers = project.workers
    if not workers:
        print("Error: Project has no workers configured.", file=sys.stderr)
        return 1

    # Run simulation
    engine = SimulationEngine(num_samples=num_samples, start_date=datetime.now(UTC))
    samples = engine.run(project, workers)

    # Calculate statistics
    successful = [s for s in samples if not s.failed_tasks]
    failed = [s for s in samples if s.failed_tasks]

    # Print summary
    print(f"Simulation complete: {len(samples)} samples")
    print(
        f"  Successful: {len(successful)} ({len(successful) / len(samples) * 100:.1f}%)"
    )
    print(f"  Failed: {len(failed)} ({len(failed) / len(samples) * 100:.1f}%)")

    if successful:
        # Calculate completion time statistics from successful samples
        completion_times = []
        for sample in successful:
            complete_events = [e for e in sample.events if e.event_type == "complete"]
            if complete_events:
                last_complete = max(e.timestamp for e in complete_events)
                # Calculate hours from start
                start_time = min(
                    e.timestamp for e in sample.events if e.event_type == "start"
                )
                hours = (last_complete - start_time).total_seconds() / 3600.0
                completion_times.append(hours)

        if completion_times:
            completion_times.sort()
            p50_idx = int(len(completion_times) * 0.5)
            p90_idx = int(len(completion_times) * 0.9)
            p95_idx = int(len(completion_times) * 0.95)

            print(f"  P50 completion: {completion_times[p50_idx]:.1f} hours")
            print(f"  P90 completion: {completion_times[p90_idx]:.1f} hours")
            print(f"  P95 completion: {completion_times[p95_idx]:.1f} hours")

    # Export JSON if requested
    if json_output_path is not None:
        from pydantic import TypeAdapter

        from fluxx.data.models import Sample

        adapter = TypeAdapter(list[Sample])
        json_content = adapter.dump_json(samples, indent=2)
        json_output_path.write_bytes(json_content)
        print(f"Wrote simulation results to {json_output_path}")

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
    parser.add_argument(
        "--run-simulation",
        type=int,
        metavar="N",
        help="Run N simulation samples headlessly and print summary statistics",
    )
    parser.add_argument(
        "--write-simulation-results-json",
        metavar="FILE",
        help="Export simulation results to JSON file (requires --run-simulation)",
    )
    args = parser.parse_args()

    # Configure logging early
    configure_logging(args.log_level)

    # Validate --write-simulation-results-json requires --run-simulation
    if args.write_simulation_results_json is not None and args.run_simulation is None:
        print(
            "Error: --write-simulation-results-json requires --run-simulation",
            file=sys.stderr,
        )
        return 1

    # Handle simulation mode
    if args.run_simulation is not None:
        if not args.file:
            print(
                "Error: --run-simulation requires a .fluxx file argument",
                file=sys.stderr,
            )
            return 1
        if args.run_simulation < 1:
            print(
                "Error: --run-simulation requires a positive integer",
                file=sys.stderr,
            )
            return 1
        json_output = (
            Path(args.write_simulation_results_json)
            if args.write_simulation_results_json
            else None
        )
        return run_simulation(Path(args.file), args.run_simulation, json_output)

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
