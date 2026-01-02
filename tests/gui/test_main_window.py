"""Tests for MainWindow."""

from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from fluxx.data.models import Triangular
from fluxx.gui.main_window import MainWindow

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _set_check_unsaved_changes(
    monkeypatch: pytest.MonkeyPatch, window: MainWindow, value: bool
) -> MagicMock:
    mock = MagicMock(return_value=value)
    monkeypatch.setattr(window, "_check_unsaved_changes", mock)
    return mock


@pytest.fixture
def window(qtbot: "QtBot", monkeypatch: pytest.MonkeyPatch) -> Generator[MainWindow]:
    """Create a MainWindow for testing."""
    win = MainWindow()
    qtbot.addWidget(win)
    # Mock _check_unsaved_changes to always return True (discard changes)
    # This prevents the unsaved changes modal from appearing during test cleanup
    _set_check_unsaved_changes(monkeypatch, win, True)
    yield win


def test_main_window_initialization(window: MainWindow) -> None:
    """Test that main window initializes correctly."""
    assert window.windowTitle() == "Project Fluxx - Untitled"
    assert window.controller is not None
    assert window.dag_panel is not None
    assert window.editor_panel is not None


def test_menu_bar_creation(window: MainWindow) -> None:
    """Test that menu bar is created with correct menus."""
    from typing import cast

    from PySide6.QtWidgets import QMenu

    menubar = window.menuBar()
    assert menubar is not None

    # Check File menu
    file_menu_found = False
    edit_menu_found = False
    for action in menubar.actions():
        text = action.text()
        if text == "&File":
            # Need cast: PySide6 stubs incorrectly type menu() as returning QObject
            file_menu = cast(QMenu | None, action.menu())
            # Check File menu actions immediately while menu is valid
            if file_menu is not None:
                file_actions = [a.text() for a in file_menu.actions()]
                assert "&New" in file_actions
                assert "&Open..." in file_actions
                assert "&Save" in file_actions
                assert "Save &As..." in file_actions
                assert "E&xit" in file_actions
                file_menu_found = True
        elif text == "&Edit":
            # Need cast: PySide6 stubs incorrectly type menu() as returning QObject
            edit_menu = cast(QMenu | None, action.menu())
            # Check Edit menu actions immediately while menu is valid
            if edit_menu is not None:
                edit_actions = [a.text() for a in edit_menu.actions()]
                assert "&Undo" in edit_actions
                assert "&Redo" in edit_actions
                edit_menu_found = True

    assert file_menu_found
    assert edit_menu_found


def test_window_title_updates_on_new_project(window: MainWindow) -> None:
    """Test that window title updates when creating new project."""
    window.controller.new_project("Test Project")
    assert "Untitled" in window.windowTitle()
    assert window.controller.get_file_path() is None


def test_window_title_shows_modified_state(window: MainWindow) -> None:
    """Test that window title shows asterisk when modified."""
    # Initially not modified
    assert "*" not in window.windowTitle()

    # Create task - should show modified
    window.controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    assert "*" in window.windowTitle()


def test_window_title_shows_filename(window: MainWindow) -> None:
    """Test that window title shows filename when file is saved."""
    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.fluxx"

        # Create task and save
        window.controller.create_task(
            title="Task 1",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        )
        window.controller.save_project_as(file_path)

        assert "test.fluxx" in window.windowTitle()
        assert "*" not in window.windowTitle()


def test_save_action_enabled_state(window: MainWindow) -> None:
    """Test that Save action is enabled/disabled correctly."""
    # Initially disabled (no file path)
    assert not window.save_action.isEnabled()

    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.fluxx"

        # Create task and save
        task_id = window.controller.create_task(
            title="Task 1",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        )
        window.controller.save_project_as(file_path)

        # After save, should be disabled (not modified)
        assert not window.save_action.isEnabled()

        # Modify project
        window.controller.update_task(
            task_id,
            title="Updated",
        )

        # Should be enabled (modified and has file path)
        assert window.save_action.isEnabled()


def test_undo_redo_actions_enabled_state(window: MainWindow) -> None:
    """Test that Undo/Redo actions are enabled/disabled correctly."""
    # Initially disabled
    assert not window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()

    # Create task
    window.controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Undo should be enabled
    assert window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()

    # Undo
    window.controller.undo()

    # Redo should be enabled
    assert not window.undo_action.isEnabled()
    assert window.redo_action.isEnabled()


def test_save_as_with_file_dialog(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test Save As with file dialog."""
    # Mock dialogs to prevent them from appearing
    mock_critical = MagicMock()
    monkeypatch.setattr("fluxx.gui.main_window.QMessageBox.critical", mock_critical)

    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.fluxx"
        mock_dialog = MagicMock(return_value=(str(file_path), ""))
        monkeypatch.setattr(
            "fluxx.gui.main_window.QFileDialog.getSaveFileName", mock_dialog
        )

        # Create task
        window.controller.create_task(
            title="Task 1",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        )

        # Trigger save as
        window._on_save_as()

        # Check that file was saved
        assert window.controller.get_file_path() == file_path
        assert not window.controller.is_modified()
        mock_critical.assert_not_called()


def test_save_as_adds_fluxx_extension(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that Save As adds .fluxx extension if missing."""
    # Mock dialogs to prevent them from appearing
    mock_critical = MagicMock()
    monkeypatch.setattr("fluxx.gui.main_window.QMessageBox.critical", mock_critical)

    with TemporaryDirectory() as tmpdir:
        file_path_no_ext = Path(tmpdir) / "test"
        mock_dialog = MagicMock(return_value=(str(file_path_no_ext), ""))
        monkeypatch.setattr(
            "fluxx.gui.main_window.QFileDialog.getSaveFileName", mock_dialog
        )

        # Create task
        window.controller.create_task(
            title="Task 1",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        )

        # Trigger save as
        window._on_save_as()

        # Check that .fluxx extension was added
        file_path_result = window.controller.get_file_path()
        assert file_path_result is not None
        assert file_path_result.suffix == ".fluxx"
        mock_critical.assert_not_called()


def test_open_with_file_dialog(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test Open with file dialog."""
    # Mock dialogs to prevent them from appearing
    mock_critical = MagicMock()
    monkeypatch.setattr("fluxx.gui.main_window.QMessageBox.critical", mock_critical)

    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.fluxx"

        # Create and save a project
        window.controller.create_task(
            title="Task 1",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        )
        window.controller.save_project_as(file_path)

        # Create new project
        window.controller.new_project("New")

        # Mock file dialog to return saved file
        mock_dialog = MagicMock(return_value=(str(file_path), ""))
        monkeypatch.setattr(
            "fluxx.gui.main_window.QFileDialog.getOpenFileName", mock_dialog
        )

        # Trigger open
        window._on_open()

        # Check that file was loaded
        assert window.controller.get_file_path() == file_path
        assert len(window.controller.get_project().dag.node_map) == 1
        mock_critical.assert_not_called()


def test_unsaved_changes_on_new(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test unsaved changes warning on New."""
    # Create task to make project modified
    window.controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Mock _check_unsaved_changes to return True (discard changes)
    check_mock = _set_check_unsaved_changes(monkeypatch, window, True)

    # Trigger new
    window._on_new()

    # Should have called check method
    check_mock.assert_called_once()

    # Should have created new project
    assert len(window.controller.get_project().dag.node_map) == 0


def test_unsaved_changes_on_new_cancel(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test canceling unsaved changes warning on New."""
    # Create task
    task_id = window.controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Mock _check_unsaved_changes to return False (cancel)
    check_mock = _set_check_unsaved_changes(monkeypatch, window, False)

    # Trigger new
    window._on_new()

    # Should have called check method
    check_mock.assert_called_once()

    # Should NOT have created new project (task still exists)
    assert task_id in window.controller.get_project().dag.node_map


def test_unsaved_changes_on_new_save(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test saving via unsaved changes warning on New."""
    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.fluxx"

        # Create task and save it first
        task_id = window.controller.create_task(
            title="Task 1",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        )
        window.controller.save_project_as(file_path)

        # Modify project
        window.controller.update_task(
            task_id,
            title="Updated",
        )

        # Mock _check_unsaved_changes to return True (saved successfully)
        check_mock = _set_check_unsaved_changes(monkeypatch, window, True)

        # Trigger new
        window._on_new()

        # Should have called check method
        check_mock.assert_called_once()

        # Should have created new project
        assert len(window.controller.get_project().dag.node_map) == 0


def test_undo_action_triggered(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test Undo action."""
    # Mock QMessageBox to prevent any error dialogs
    mock_critical = MagicMock()
    monkeypatch.setattr("fluxx.gui.main_window.QMessageBox.critical", mock_critical)

    # Create task
    task_id = window.controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    assert task_id in window.controller.get_project().dag.node_map

    # Trigger undo
    window._on_undo()

    # Task should be gone
    assert task_id not in window.controller.get_project().dag.node_map
    # No error should have occurred
    mock_critical.assert_not_called()


def test_redo_action_triggered(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test Redo action."""
    # Mock QMessageBox to prevent any error dialogs
    mock_critical = MagicMock()
    monkeypatch.setattr("fluxx.gui.main_window.QMessageBox.critical", mock_critical)

    # Create task
    task_id = window.controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Undo
    window.controller.undo()

    assert task_id not in window.controller.get_project().dag.node_map

    # Trigger redo
    window._on_redo()

    # Task should be back
    assert task_id in window.controller.get_project().dag.node_map
    # No error should have occurred
    mock_critical.assert_not_called()


def test_two_panel_layout(window: MainWindow) -> None:
    """Test that window has two-panel layout."""
    # Central widget should be a splitter
    central_widget = window.centralWidget()
    assert central_widget is not None

    # Should have two children (dag_panel and editor_panel)
    assert window.dag_panel is not None
    assert window.editor_panel is not None


def test_close_event_with_unsaved_changes(
    window: MainWindow, qtbot: "QtBot", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test close event with unsaved changes."""
    # Create task to make project modified
    window.controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Mock _check_unsaved_changes to return True (discard changes)
    check_mock = _set_check_unsaved_changes(monkeypatch, window, True)

    # Trigger close
    window.close()

    # Should have called check method
    check_mock.assert_called_once()


def test_close_event_cancel(
    window: MainWindow, qtbot: "QtBot", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test canceling close event with unsaved changes."""
    # Create task to make project modified
    window.controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Mock _check_unsaved_changes to return False (cancel)
    check_mock = _set_check_unsaved_changes(monkeypatch, window, False)

    # Create close event
    from PySide6.QtGui import QCloseEvent

    event = QCloseEvent()

    # Trigger close event
    window.closeEvent(event)

    # Should have called check method
    check_mock.assert_called_once()

    # Event should be ignored (not accepted)
    assert event.isAccepted() is False
