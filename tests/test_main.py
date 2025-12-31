"""Tests for main entry point."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fluxx.__main__ import main
from fluxx.data.persistence import FileFormatError


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
        mock_parse.return_value = MagicMock(file=None)
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
        mock_parse.return_value = MagicMock(file=str(new_file_base))
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
        mock_parse.return_value = MagicMock(file=str(existing_file))
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
        mock_parse.return_value = MagicMock(file=str(bad_file))
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
        mock_parse.return_value = MagicMock(file=None)
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
        mock_parse.return_value = MagicMock(file=str(new_file))
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
        mock_parse.return_value = MagicMock(file=str(existing_file))
        result = main()

    # Should show error dialog
    mock_msgbox.critical.assert_called_once()
    assert "Error Opening Project" in mock_msgbox.critical.call_args[0][1]
    assert "Unexpected error" in mock_msgbox.critical.call_args[0][2]
    # Should still show window
    mock_window.show.assert_called_once()
    assert result == 0
