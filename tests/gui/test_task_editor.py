"""Tests for TaskEditor widget."""

from collections.abc import Generator

import pytest
from pytestqt.qtbot import QtBot

from fluxx.data.models import Triangular
from fluxx.gui.controller import ProjectController
from fluxx.gui.widgets.editors.task_editor import TaskEditor


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
def task_editor(qtbot: QtBot, controller: ProjectController) -> Generator[TaskEditor]:
    """Create a TaskEditor for testing.

    Args:
        qtbot: QtBot fixture
        controller: ProjectController fixture

    Yields:
        TaskEditor instance
    """
    editor = TaskEditor(controller)
    qtbot.addWidget(editor)
    yield editor


def test_task_editor_initialization(task_editor: TaskEditor) -> None:
    """Test that task editor initializes correctly."""
    assert task_editor.controller is not None
    assert task_editor.current_task_id is None
    assert task_editor.pending_changes == {}
    assert not task_editor.apply_button.isEnabled()
    assert not task_editor.revert_button.isEnabled()


def test_task_editor_loads_task(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test loading a task into the editor."""
    # Create a task
    task_id = controller.create_task(
        title="Test Task",
        description="Test description",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Load task into editor
    task_editor.load_task(task_id)

    # Verify fields are populated
    assert task_editor.title_field.text() == "Test Task"
    assert task_editor.description_field.toPlainText() == "Test description"
    assert task_editor.distribution_type.currentText() == "Triangular"


def test_task_editor_title_change(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test changing task title."""
    # Create and load a task
    task_id = controller.create_task(
        title="Original Title",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Change title
    task_editor.title_field.setText("New Title")

    # Verify pending changes
    assert "title" in task_editor.pending_changes
    assert task_editor.pending_changes["title"] == "New Title"
    assert task_editor.apply_button.isEnabled()
    assert task_editor.revert_button.isEnabled()


def test_task_editor_description_change(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test changing task description."""
    # Create and load a task
    task_id = controller.create_task(
        title="Task",
        description="Original",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Change description
    task_editor.description_field.setPlainText("New description")

    # Verify pending changes
    assert "description" in task_editor.pending_changes
    assert task_editor.pending_changes["description"] == "New description"
    assert task_editor.apply_button.isEnabled()


def test_task_editor_apply_changes(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test applying changes to a task."""
    # Create and load a task
    task_id = controller.create_task(
        title="Original",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Make changes
    task_editor.title_field.setText("Updated")

    # Apply changes
    task_editor._on_apply()

    # Verify task was updated
    project = controller.get_project()
    from fluxx.data.models import NodeId

    node_id = NodeId(task_id)
    persistent_id = project.dag.node_map[node_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert task.title == "Updated"

    # Verify pending changes cleared
    assert task_editor.pending_changes == {}
    assert not task_editor.apply_button.isEnabled()


def test_task_editor_revert_changes(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test reverting changes."""
    # Create and load a task
    task_id = controller.create_task(
        title="Original",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Make changes
    task_editor.title_field.setText("Changed")
    assert "title" in task_editor.pending_changes

    # Revert
    task_editor._on_revert()

    # Verify reverted to original
    assert task_editor.title_field.text() == "Original"
    assert task_editor.pending_changes == {}
    assert not task_editor.apply_button.isEnabled()


def test_task_editor_empty_title_validation(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test that empty title is invalid."""
    # Create and load a task
    task_id = controller.create_task(
        title="Valid Title",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Change to empty title
    task_editor.title_field.setText("")

    # Verify apply button is disabled (invalid)
    assert not task_editor.apply_button.isEnabled()


def test_task_editor_distribution_type_change(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test changing distribution type."""
    # Create and load a task with triangular distribution
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Change to None
    task_editor.distribution_type.setCurrentText("None")

    # Verify pending changes
    assert "duration_distribution" in task_editor.pending_changes
    assert task_editor.pending_changes["duration_distribution"] is None


def test_task_editor_triangular_params(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test editing triangular distribution parameters."""
    # Create and load a task
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Verify fields are populated
    assert task_editor.min_field.text() == "1.0"
    assert task_editor.mode_field.text() == "2.0"
    assert task_editor.max_field.text() == "3.0"

    # Change values to a valid distribution (min < mode < max)
    task_editor.max_field.setText("5.0")

    # Verify pending changes
    assert "duration_distribution" in task_editor.pending_changes
    dist = task_editor.pending_changes["duration_distribution"]
    assert isinstance(dist, Triangular)
    assert dist.max == 5.0
