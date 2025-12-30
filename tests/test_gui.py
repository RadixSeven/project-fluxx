"""Tests for GUI components."""

from pytestqt.qtbot import QtBot

from fluxx.gui.main_window import MainWindow


def test_main_window_creation(qtbot: QtBot) -> None:
    """Test creating the main window."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "Project Fluxx"


def test_main_window_geometry(qtbot: QtBot) -> None:
    """Test main window has correct initial geometry."""
    window = MainWindow()
    qtbot.addWidget(window)
    # Window should be reasonably sized
    assert window.width() > 0
    assert window.height() > 0
