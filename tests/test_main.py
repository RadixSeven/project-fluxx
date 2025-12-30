"""Tests for main entry point."""

from unittest.mock import MagicMock, patch

from fluxx.__main__ import main


@patch("fluxx.__main__.MainWindow")
@patch("fluxx.__main__.QApplication")
def test_main(mock_qapplication: MagicMock, mock_main_window: MagicMock) -> None:
    """Test that main() initializes and runs the application correctly."""
    # Set up mocks
    mock_app_instance = MagicMock()
    mock_app_instance.exec.return_value = 0
    mock_qapplication.return_value = mock_app_instance

    mock_window_instance = MagicMock()
    mock_main_window.return_value = mock_window_instance

    # Call main
    result = main()

    # Verify QApplication was created with sys.argv
    mock_qapplication.assert_called_once()
    call_args = mock_qapplication.call_args
    # First argument should be sys.argv
    assert len(call_args[0]) == 1
    assert isinstance(call_args[0][0], list)

    # Verify MainWindow was created
    mock_main_window.assert_called_once_with()

    # Verify window.show() was called
    mock_window_instance.show.assert_called_once()

    # Verify app.exec() was called
    mock_app_instance.exec.assert_called_once()

    # Verify main() returns the app.exec() result
    assert result == 0


@patch("fluxx.__main__.MainWindow")
@patch("fluxx.__main__.QApplication")
def test_main_returns_app_exit_code(
    mock_qapplication: MagicMock, mock_main_window: MagicMock
) -> None:
    """Test that main() returns the exit code from app.exec()."""
    # Set up mocks with non-zero exit code
    mock_app_instance = MagicMock()
    mock_app_instance.exec.return_value = 42
    mock_qapplication.return_value = mock_app_instance

    mock_window_instance = MagicMock()
    mock_main_window.return_value = mock_window_instance

    # Call main
    result = main()

    # Verify main() returns the app.exec() result
    assert result == 42
