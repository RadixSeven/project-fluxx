"""Tests for ControlBar widget."""

from collections.abc import Generator

import pytest
from pytestqt.qtbot import QtBot

from fluxx.gui.controller import ProjectController
from fluxx.gui.panels.control_bar import ControlBar


@pytest.fixture
def controller(qtbot: QtBot) -> Generator[ProjectController]:
    """Create a ProjectController for testing.

    Args:
        qtbot: QtBot fixture

    Yields:
        ProjectController instance
    """
    ctrl = ProjectController()
    yield ctrl


@pytest.fixture
def control_bar(qtbot: QtBot, controller: ProjectController) -> Generator[ControlBar]:
    """Create a ControlBar for testing.

    Args:
        qtbot: QtBot fixture
        controller: ProjectController fixture

    Yields:
        ControlBar instance
    """
    bar = ControlBar(controller)
    qtbot.addWidget(bar)
    yield bar


def test_control_bar_initialization(control_bar: ControlBar) -> None:
    """Test that control bar initializes correctly."""
    assert control_bar.controller is not None
    assert not control_bar.is_list_view  # Starts with DAG view
    assert control_bar.view_toggle_button.text() == "List View"


def test_control_bar_toggle_view(control_bar: ControlBar) -> None:
    """Test toggling between DAG and list views."""
    # Initially DAG view
    assert not control_bar.is_list_view
    assert control_bar.get_current_view() == "dag"
    assert control_bar.view_toggle_button.text() == "List View"

    # Toggle to list view
    control_bar._on_toggle_view()
    assert control_bar.is_list_view
    assert control_bar.get_current_view() == "list"
    assert control_bar.view_toggle_button.text() == "DAG View"

    # Toggle back to DAG view
    control_bar._on_toggle_view()
    assert not control_bar.is_list_view
    assert control_bar.get_current_view() == "dag"
    assert control_bar.view_toggle_button.text() == "List View"


def test_control_bar_edit_workers_button_exists(control_bar: ControlBar) -> None:
    """Test that Edit Workers button exists and is configured correctly."""
    assert hasattr(control_bar, "edit_workers_button")
    assert control_bar.edit_workers_button.text() == "Edit Workers"
    assert control_bar.edit_workers_button.toolTip() == "Open worker list editor"


def test_control_bar_edit_workers_signal(control_bar: ControlBar, qtbot: QtBot) -> None:
    """Test that Edit Workers button emits signal when clicked."""
    # Connect signal to track emissions
    signal_received = []
    control_bar.edit_workers_clicked.connect(lambda: signal_received.append(True))

    # Click the button
    control_bar.edit_workers_button.click()

    # Signal should have been emitted
    assert len(signal_received) == 1


def test_control_bar_edit_workers_handler(control_bar: ControlBar) -> None:
    """Test _on_edit_workers handler emits signal."""
    # Connect signal to track emissions
    signal_received = []
    control_bar.edit_workers_clicked.connect(lambda: signal_received.append(True))

    # Call handler directly
    control_bar._on_edit_workers()

    # Signal should have been emitted
    assert len(signal_received) == 1


def test_control_bar_history_label_exists(control_bar: ControlBar) -> None:
    """Test that history label exists."""
    assert hasattr(control_bar, "history_label")
    assert control_bar.history_label.text() == "Current Version"


def test_control_bar_toggle_button_click(control_bar: ControlBar, qtbot: QtBot) -> None:
    """Test clicking the toggle button changes view."""
    initial_view = control_bar.is_list_view

    # Click toggle button
    control_bar.view_toggle_button.click()

    # View should be toggled
    assert control_bar.is_list_view != initial_view
