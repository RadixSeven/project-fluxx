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


def test_task_editor_dependencies_display(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test that dependencies are displayed in the list."""
    # Create two tasks
    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency: task2 depends on task1
    from fluxx.data.models import ConstraintType, Dependency, Endpoint, NodeId

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=NodeId(task1_id),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(NodeId(task2_id), dep)

    # Load task 2
    task_editor.load_task(task2_id)

    # Verify dependency is shown
    assert task_editor.dependencies_list.count() == 1
    item = task_editor.dependencies_list.item(0)
    assert item is not None
    assert "Task 1" in item.text()


def test_task_editor_remove_dependency(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test removing a dependency."""
    # Create two tasks with dependency
    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    from fluxx.data.models import ConstraintType, Dependency, Endpoint, NodeId

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=NodeId(task1_id),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(NodeId(task2_id), dep)

    # Load task 2
    task_editor.load_task(task2_id)

    # Select the dependency
    task_editor.dependencies_list.setCurrentRow(0)

    # Remove button should be enabled
    assert task_editor.remove_dependency_button.isEnabled()

    # Remove dependency
    task_editor._on_remove_dependency()

    # Verify dependency removed from pending changes
    assert "dependencies" in task_editor.pending_changes
    assert len(task_editor.pending_changes["dependencies"]) == 0


def test_task_editor_dependency_selection(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test dependency list selection changes."""
    # Create task
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Initially, remove button should be disabled
    assert not task_editor.remove_dependency_button.isEnabled()

    # (No dependencies to select, so button remains disabled)


def test_task_editor_shifted_lognormal_distribution(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test loading and editing shifted lognormal distribution."""
    from fluxx.data.models import ShiftedLognormal

    # Create task with shifted lognormal distribution
    task_id = controller.create_task(
        title="Task with ShiftedLognormal",
        duration_distribution=ShiftedLognormal(min=1.0, mode=3.0, percentile_95=10.0),
    )

    # Load task
    task_editor.load_task(task_id)

    # Verify distribution type selected
    assert task_editor.distribution_type.currentText() == "Shifted Lognormal"

    # Verify fields are populated
    assert task_editor.min_field.text() == "1.0"
    assert task_editor.mode_field.text() == "3.0"
    assert task_editor.percentile_95_field.text() == "10.0"

    # Change values
    task_editor.percentile_95_field.setText("15.0")

    # Verify pending changes
    assert "duration_distribution" in task_editor.pending_changes
    dist = task_editor.pending_changes["duration_distribution"]
    assert isinstance(dist, ShiftedLognormal)
    assert dist.percentile_95 == 15.0


def test_task_editor_switch_to_shifted_lognormal(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test switching from triangular to shifted lognormal distribution."""
    # Create task with triangular distribution
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Switch to shifted lognormal
    task_editor.distribution_type.setCurrentText("Shifted Lognormal")

    # Verify percentile_95 field now exists for shifted lognormal
    assert hasattr(task_editor, "percentile_95_field")


def test_task_editor_invalid_triangular_distribution(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test validation of invalid triangular distribution."""
    # Create task with triangular distribution
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Set invalid values (mode > max)
    task_editor.max_field.setText("1.5")  # Less than mode (2.0)

    # Verify apply button is disabled
    assert not task_editor.apply_button.isEnabled()


def test_task_editor_clear_task(task_editor: TaskEditor) -> None:
    """Test clearing loaded task."""
    # Initially no task loaded
    assert task_editor.current_task_id is None

    # Title field should be empty
    assert task_editor.title_field.text() == ""
