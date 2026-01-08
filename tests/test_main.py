"""Tests for main entry point."""

import csv
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fluxx.__main__ import main, write_historical_data_csv
from fluxx.data.persistence import FileFormatError
from fluxx.jira.models import (
    JiraConfig,
    JiraDurationHistoryEntry,
    JiraIssueKey,
    JiraSyncMetadata,
)


@pytest.fixture
def mock_qt(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock, MagicMock]:
    mock_app = MagicMock()
    mock_app.exec.return_value = 0
    mock_window = MagicMock()
    mock_msgbox = MagicMock()

    monkeypatch.setattr("fluxx.__main__.QApplication", MagicMock(return_value=mock_app))
    monkeypatch.setattr(
        "fluxx.__main__.MainWindow", MagicMock(return_value=mock_window)
    )
    monkeypatch.setattr("fluxx.__main__.QMessageBox", mock_msgbox)

    return mock_app, mock_window, mock_msgbox


def test_main_no_args(
    mock_qt: tuple[MagicMock, MagicMock, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test main() with no arguments."""
    mock_app, mock_window, mock_msgbox = mock_qt
    monkeypatch.setattr(sys, "argv", ["fluxx"])

    with patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse:
        mock_parse.return_value = MagicMock(
            file=None, write_historical_data_csv=None, log_level="INFO"
        )
        result = main()

    assert result == 0
    mock_window.controller.open_project.assert_not_called()
    mock_window.show.assert_called_once()


def test_main_new_file_no_suffix(
    mock_qt: tuple[MagicMock, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test main() with a new file that has no suffix."""
    mock_app, mock_window, mock_msgbox = mock_qt
    new_file_base = tmp_path / "new_project"

    with patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse:
        mock_parse.return_value = MagicMock(
            file=str(new_file_base), write_historical_data_csv=None, log_level="INFO"
        )
        main()

    mock_window.controller.new_project.assert_called_once_with("Untitled")
    # Path should have .fluxx suffix
    mock_window.controller.save_project_as.assert_called_once_with(
        new_file_base.with_suffix(".fluxx")
    )
    mock_window.show.assert_called_once()


def test_main_existing_file(
    mock_qt: tuple[MagicMock, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test main() with an existing valid file."""
    mock_app, mock_window, mock_msgbox = mock_qt
    existing_file = tmp_path / "existing.fluxx"
    existing_file.touch()

    with patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse:
        mock_parse.return_value = MagicMock(
            file=str(existing_file), write_historical_data_csv=None, log_level="INFO"
        )
        main()

    mock_window.controller.open_project.assert_called_once_with(
        Path(str(existing_file))
    )
    mock_window.show.assert_called_once()


def test_main_bad_format_file(
    mock_qt: tuple[MagicMock, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test main() with a file that has an invalid format."""
    mock_app, mock_window, mock_msgbox = mock_qt
    bad_file = tmp_path / "bad.fluxx"
    bad_file.touch()

    # Mock open_project to raise FileFormatError
    mock_window.controller.open_project.side_effect = FileFormatError("Bad format")

    with patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse:
        mock_parse.return_value = MagicMock(
            file=str(bad_file), write_historical_data_csv=None, log_level="INFO"
        )
        main()

    mock_window.controller.open_project.assert_called_once_with(Path(str(bad_file)))
    mock_msgbox.critical.assert_called_once()
    # Check that error dialog was shown
    assert "Failed to open project" in mock_msgbox.critical.call_args[0][2]
    # Should still show window (behave as if no file was specified)
    mock_window.show.assert_called_once()


def test_main_returns_app_exit_code(
    mock_qt: tuple[MagicMock, MagicMock, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that main() returns the exit code from app.exec()."""
    mock_app, mock_window, mock_msgbox = mock_qt
    mock_app.exec.return_value = 42
    monkeypatch.setattr(sys, "argv", ["fluxx"])

    with patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse:
        mock_parse.return_value = MagicMock(
            file=None, write_historical_data_csv=None, log_level="INFO"
        )
        result = main()

    assert result == 42


def test_main_create_project_error(
    mock_qt: tuple[MagicMock, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test main() when creating a new project fails."""
    mock_app, mock_window, mock_msgbox = mock_qt
    new_file = tmp_path / "new_project.fluxx"

    # Mock save_project_as to raise an exception
    mock_window.controller.save_project_as.side_effect = RuntimeError("Save failed")

    with patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse:
        mock_parse.return_value = MagicMock(
            file=str(new_file), write_historical_data_csv=None, log_level="INFO"
        )
        result = main()

    # Should show error dialog
    mock_msgbox.critical.assert_called_once()
    assert "Error Creating Project" in mock_msgbox.critical.call_args[0][1]
    assert "Save failed" in mock_msgbox.critical.call_args[0][2]
    # Should still show window
    mock_window.show.assert_called_once()
    assert result == 0


def test_main_open_project_unexpected_error(
    mock_qt: tuple[MagicMock, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test main() when opening a project encounters unexpected error."""
    mock_app, mock_window, mock_msgbox = mock_qt
    existing_file = tmp_path / "test.fluxx"
    existing_file.touch()

    # Mock open_project to raise an unexpected exception
    # (not FileFormatError/VersionError)
    mock_window.controller.open_project.side_effect = RuntimeError("Unexpected error")

    with patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse:
        mock_parse.return_value = MagicMock(
            file=str(existing_file), write_historical_data_csv=None, log_level="INFO"
        )
        result = main()

    # Should show error dialog
    mock_msgbox.critical.assert_called_once()
    assert "Error Opening Project" in mock_msgbox.critical.call_args[0][1]
    assert "Unexpected error" in mock_msgbox.critical.call_args[0][2]
    # Should still show window
    mock_window.show.assert_called_once()
    assert result == 0


# Tests for --write-historical-data-csv


def test_write_historical_data_csv_success(tmp_path: Path) -> None:
    """Test successful CSV export of historical data."""
    # Create mock project with Jira config
    mock_project = MagicMock()
    mock_project.jira_config = JiraConfig(
        server_url="https://jira.example.com",
        sync_metadata=JiraSyncMetadata(
            server_url="https://jira.example.com",
            last_history_sync=datetime(2025, 1, 1, tzinfo=UTC),
            history_entries=[
                JiraDurationHistoryEntry(
                    server_url="https://jira.example.com",
                    issue_key=JiraIssueKey(project_key="PROJ", issue_number=1),
                    issue_type="Story",
                    original_estimate_seconds=14400,  # 4 hours
                    total_logged_time_seconds=18000,  # 5 hours
                    worker_jira_id="user1",
                    story_points=5.0,
                    remaining_estimate_seconds=3600,  # 1 hour
                    created_datetime=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
                    resolved_datetime=datetime(2025, 1, 2, 12, 0, tzinfo=UTC),
                ),
                JiraDurationHistoryEntry(
                    server_url="https://jira.example.com",
                    issue_key=JiraIssueKey(project_key="PROJ", issue_number=2),
                    issue_type="Bug",
                    original_estimate_seconds=None,
                    total_logged_time_seconds=7200,  # 2 hours
                    worker_jira_id=None,
                    story_points=None,
                    remaining_estimate_seconds=None,
                    created_datetime=None,
                    resolved_datetime=None,
                ),
            ],
        ),
    )

    project_file = tmp_path / "test.fluxx"
    output_file = tmp_path / "output.csv"

    with patch("fluxx.__main__.load_project", return_value=mock_project):
        result = write_historical_data_csv(project_file, output_file)

    assert result == 0
    assert output_file.exists()

    # Read and verify CSV content
    with open(output_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 2

    # Check first row (with all fields)
    assert rows[0]["server_url"] == "https://jira.example.com"
    assert rows[0]["issue_key"] == "PROJ-1"
    assert rows[0]["issue_type"] == "Story"
    assert rows[0]["worker_jira_id"] == "user1"
    assert float(rows[0]["original_estimate_hours"]) == 4.0
    assert float(rows[0]["total_logged_hours"]) == 5.0
    assert float(rows[0]["remaining_estimate_hours"]) == 1.0
    assert float(rows[0]["story_points"]) == 5.0
    assert "2025-01-01" in rows[0]["created_datetime"]
    assert "2025-01-02" in rows[0]["resolved_datetime"]

    # Check second row (with None values)
    assert rows[1]["issue_key"] == "PROJ-2"
    assert rows[1]["issue_type"] == "Bug"
    assert rows[1]["worker_jira_id"] == ""
    assert rows[1]["original_estimate_hours"] == ""
    assert rows[1]["story_points"] == ""


def test_write_historical_data_csv_no_file_arg(
    mock_qt: tuple[MagicMock, MagicMock, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test --write-historical-data-csv without file argument."""
    mock_app, mock_window, mock_msgbox = mock_qt
    output_file = tmp_path / "output.csv"

    with patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse:
        mock_parse.return_value = MagicMock(
            file=None, write_historical_data_csv=str(output_file), log_level="INFO"
        )
        result = main()

    assert result == 1
    captured = capsys.readouterr()
    assert "requires a .fluxx file argument" in captured.err


def test_write_historical_data_csv_no_jira_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test CSV export when project has no Jira config."""
    mock_project = MagicMock()
    mock_project.jira_config = None

    project_file = tmp_path / "test.fluxx"
    output_file = tmp_path / "output.csv"

    with patch("fluxx.__main__.load_project", return_value=mock_project):
        result = write_historical_data_csv(project_file, output_file)

    assert result == 1
    captured = capsys.readouterr()
    assert "No Jira configuration found" in captured.err


def test_write_historical_data_csv_no_history_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test CSV export when project has no history entries."""
    mock_project = MagicMock()
    mock_project.jira_config = JiraConfig(
        server_url="https://jira.example.com",
        sync_metadata=JiraSyncMetadata(
            server_url="https://jira.example.com",
            last_history_sync=datetime(2025, 1, 1, tzinfo=UTC),
            history_entries=[],
        ),
    )

    project_file = tmp_path / "test.fluxx"
    output_file = tmp_path / "output.csv"

    with patch("fluxx.__main__.load_project", return_value=mock_project):
        result = write_historical_data_csv(project_file, output_file)

    assert result == 1
    captured = capsys.readouterr()
    assert "No historical data entries found" in captured.err


def test_write_historical_data_csv_file_load_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test CSV export when project file fails to load."""
    project_file = tmp_path / "test.fluxx"
    output_file = tmp_path / "output.csv"

    with patch(
        "fluxx.__main__.load_project", side_effect=FileFormatError("Invalid format")
    ):
        result = write_historical_data_csv(project_file, output_file)

    assert result == 1
    captured = capsys.readouterr()
    assert "Error loading project" in captured.err


def test_write_historical_data_csv_unexpected_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test CSV export when project file encounters unexpected error."""
    project_file = tmp_path / "test.fluxx"
    output_file = tmp_path / "output.csv"

    with patch(
        "fluxx.__main__.load_project", side_effect=RuntimeError("Unexpected error")
    ):
        result = write_historical_data_csv(project_file, output_file)

    assert result == 1
    captured = capsys.readouterr()
    assert "Unexpected error loading project" in captured.err


def test_main_with_csv_export(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main() with --write-historical-data-csv flag through argparse."""
    # Create mock project with Jira config
    mock_project = MagicMock()
    mock_project.jira_config = JiraConfig(
        server_url="https://jira.example.com",
        sync_metadata=JiraSyncMetadata(
            server_url="https://jira.example.com",
            last_history_sync=datetime(2025, 1, 1, tzinfo=UTC),
            history_entries=[
                JiraDurationHistoryEntry(
                    server_url="https://jira.example.com",
                    issue_key=JiraIssueKey(project_key="PROJ", issue_number=1),
                    issue_type="Story",
                    original_estimate_seconds=14400,
                    total_logged_time_seconds=18000,
                ),
            ],
        ),
    )

    project_file = tmp_path / "test.fluxx"
    output_file = tmp_path / "output.csv"

    with (
        patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse,
        patch("fluxx.__main__.load_project", return_value=mock_project),
    ):
        mock_parse.return_value = MagicMock(
            file=str(project_file),
            write_historical_data_csv=str(output_file),
            log_level="INFO",
        )
        result = main()

    assert result == 0
    assert output_file.exists()


# Tests for --log-level


def test_main_log_level_debug(
    mock_qt: tuple[MagicMock, MagicMock, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test main() with --log-level DEBUG."""
    mock_app, mock_window, mock_msgbox = mock_qt
    monkeypatch.setattr(sys, "argv", ["fluxx"])

    with (
        patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse,
        patch("fluxx.__main__.configure_logging") as mock_configure,
    ):
        mock_parse.return_value = MagicMock(
            file=None, write_historical_data_csv=None, log_level="DEBUG"
        )
        main()

    mock_configure.assert_called_once_with("DEBUG")


def test_main_log_level_warning(
    mock_qt: tuple[MagicMock, MagicMock, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test main() with --log-level WARNING."""
    mock_app, mock_window, mock_msgbox = mock_qt
    monkeypatch.setattr(sys, "argv", ["fluxx"])

    with (
        patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse,
        patch("fluxx.__main__.configure_logging") as mock_configure,
    ):
        mock_parse.return_value = MagicMock(
            file=None, write_historical_data_csv=None, log_level="WARNING"
        )
        main()

    mock_configure.assert_called_once_with("WARNING")


def test_main_log_level_default(
    mock_qt: tuple[MagicMock, MagicMock, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test main() uses default log level INFO."""
    mock_app, mock_window, mock_msgbox = mock_qt
    monkeypatch.setattr(sys, "argv", ["fluxx"])

    with (
        patch("fluxx.__main__.argparse.ArgumentParser.parse_args") as mock_parse,
        patch("fluxx.__main__.configure_logging") as mock_configure,
    ):
        mock_parse.return_value = MagicMock(
            file=None, write_historical_data_csv=None, log_level="INFO"
        )
        main()

    mock_configure.assert_called_once_with("INFO")
