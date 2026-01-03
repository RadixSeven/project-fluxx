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
    node_id = task_id
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
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)

    # Load task 2
    task_editor.load_task(task2_id)

    # Verify dependency is shown
    assert task_editor.dependencies_list.count() == 1
    item = task_editor.dependencies_list.item(0)
    assert item is not None
    assert item.text() == "start ≥ Task 1.end"


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

    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)

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


def test_task_editor_add_dependency_and_apply(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test that adding a dependency and applying works without errors."""
    from fluxx.data.models import (
        ConstraintType,
        Dependency,
        Endpoint,
        Triangular,
    )

    # Create two tasks
    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Load task2 in editor
    task_editor.load_task(task2_id)

    # Simulate adding a dependency to task1
    # This is what the UI does when user adds a dependency
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # Get current dependencies from task
    project = controller.get_project()
    current_version = project.dag.current_version_id
    persistent_id = project.dag.node_map[task2_id]
    task2 = project.persistent_tasks[persistent_id].versions[current_version]
    current_deps = list(task2.dependencies)
    current_deps.append(dep)

    # Update pending changes with new dependencies list
    task_editor.pending_changes["dependencies"] = current_deps
    task_editor._update_button_states()

    # Apply should work without raising TypeError
    # This is the bug: update_task doesn't accept 'dependencies' parameter
    task_editor._on_apply()

    # Verify the dependency was added
    project_after = controller.get_project()
    persistent_id_after = project_after.dag.node_map[task2_id]
    task2_after = project_after.persistent_tasks[persistent_id_after].versions[
        project_after.dag.current_version_id
    ]
    assert len(task2_after.dependencies) == 1
    assert task2_after.dependencies[0].target_node_id == task1_id


def test_task_editor_load_task_not_in_node_map(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test loading a task that doesn't exist in node_map."""
    from fluxx.data.models import TaskId

    # Load nonexistent task
    fake_id = TaskId("nonexistent")
    task_editor.load_task(fake_id)

    # Should set current_task_id but no content loaded
    assert task_editor.current_task_id == fake_id


def test_task_editor_load_task_with_no_distribution(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test loading a task with None distribution (parent task)."""
    # Create a leaf task first, then convert to parent to get None distribution
    parent_id = controller.create_task(
        title="Parent Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Convert to parent - this makes the duration distribution None
    controller.convert_to_parent(parent_id, "Child Task")

    task_editor.load_task(parent_id)

    assert task_editor.distribution_type.currentText() == "None"


def test_task_editor_on_delete(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test delete button handler (currently a no-op)."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Call delete handler - should not raise
    task_editor._on_delete()


def test_task_editor_is_dirty(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test is_dirty method."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Initially not dirty
    assert not task_editor.is_dirty()

    # Make changes
    task_editor.title_field.setText("Changed")

    # Now dirty
    assert task_editor.is_dirty()


def test_task_editor_apply_changes_method(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test apply_changes method."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # When not dirty, should return True immediately
    assert task_editor.apply_changes() is True

    # Make changes
    task_editor.title_field.setText("Updated")
    assert task_editor.is_dirty()

    # Apply changes
    result = task_editor.apply_changes()

    # Should return True and clear pending changes
    assert result is True
    assert not task_editor.is_dirty()


def test_task_editor_revert_changes_method(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test revert_changes method."""
    task_id = controller.create_task(
        title="Original",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Make changes
    task_editor.title_field.setText("Changed")
    assert task_editor.is_dirty()

    # Revert changes
    task_editor.revert_changes()

    # Should restore original and clear pending changes
    assert task_editor.title_field.text() == "Original"
    assert not task_editor.is_dirty()


def test_task_editor_apply_with_no_task(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test apply when no task is loaded."""
    # Make some pending changes without loading a task
    task_editor.pending_changes["title"] = "New Title"

    # Apply should do nothing
    task_editor._on_apply()

    # Pending changes should still be there
    assert "title" in task_editor.pending_changes


def test_task_editor_apply_invalid_changes(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test that apply with invalid changes does nothing."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Set empty title (invalid)
    task_editor.title_field.setText("")

    # Manually call apply (button would be disabled)
    task_editor._on_apply()

    # Changes should not be cleared because validation failed
    assert "title" in task_editor.pending_changes


def test_task_editor_add_dependency_no_task(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test add dependency when no task is loaded."""
    # Call without loading a task
    task_editor._on_add_dependency()

    # Should do nothing (early return)
    assert task_editor._editing_dependency_index is None


def test_task_editor_add_dependency_button(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test add dependency button enables dependency editing mode."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Click add dependency
    task_editor._on_add_dependency()

    # Editing mode should be active
    assert task_editor._editing_dependency_index is None  # None means adding new
    # Apply/revert buttons should be disabled during dependency editing
    assert not task_editor.apply_button.isEnabled()
    assert not task_editor.add_dependency_button.isEnabled()


def test_task_editor_cancel_dependency(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test canceling dependency editing."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Start adding dependency
    task_editor._on_add_dependency()
    assert task_editor._editing_dependency_index is None
    assert not task_editor.add_dependency_button.isEnabled()

    # Cancel
    task_editor._on_dependency_cancelled()

    # Should exit editing mode
    assert task_editor._editing_dependency_index is None
    # Add dependency button should be re-enabled
    assert task_editor.add_dependency_button.isEnabled()


def test_task_editor_finish_dependency_no_task(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test finish dependency editing when no task is loaded."""

    # Set up dependency editor with complete dependency but no task loaded
    target_id = controller.create_task(
        title="Target",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.dependency_editor.set_target_node(target_id)
    task_editor.dependency_editor.source_endpoint_combo.setCurrentIndex(0)  # START
    task_editor.dependency_editor.target_endpoint_combo.setCurrentIndex(1)  # END
    task_editor.dependency_editor.constraint_type_combo.setCurrentIndex(0)  # >=

    # Call without loading a task
    task_editor.finish_dependency_editing()

    # Should do nothing
    assert "dependencies" not in task_editor.pending_changes


def test_task_editor_finish_dependency_with_valid_dependency(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test finishing dependency editing with a valid dependency."""

    # Create two tasks
    target_task_id = controller.create_task(
        title="Target Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Start adding dependency
    task_editor._on_add_dependency()

    # Set up dependency editor with a complete dependency
    task_editor.dependency_editor.set_target_node(target_task_id)
    task_editor.dependency_editor.source_endpoint_combo.setCurrentIndex(0)  # START
    task_editor.dependency_editor.target_endpoint_combo.setCurrentIndex(1)  # END
    task_editor.dependency_editor.constraint_type_combo.setCurrentIndex(0)  # >=

    # Finish editing
    task_editor.finish_dependency_editing()

    # Dependency should be in pending changes
    assert "dependencies" in task_editor.pending_changes
    assert len(task_editor.pending_changes["dependencies"]) == 1

    # Add button should be re-enabled
    assert task_editor.add_dependency_button.isEnabled()


def test_task_editor_finish_dependency_editing_update_existing(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test updating an existing dependency."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    # Create three tasks
    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task3_id = controller.create_task(
        title="Task 3",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add initial dependency: task3 depends on task1
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task3_id, dep)

    task_editor.load_task(task3_id)
    assert task_editor.dependencies_list.count() == 1

    # Simulate editing existing dependency (index 0)
    task_editor._editing_dependency_index = 0

    # Set up dependency editor with updated target (task2 instead of task1)
    task_editor.dependency_editor.set_target_node(task2_id)
    task_editor.dependency_editor.source_endpoint_combo.setCurrentIndex(0)  # START
    task_editor.dependency_editor.target_endpoint_combo.setCurrentIndex(1)  # END
    task_editor.dependency_editor.constraint_type_combo.setCurrentIndex(0)  # >=

    # Finish editing
    task_editor.finish_dependency_editing()

    # Should still have 1 dependency, but updated
    assert "dependencies" in task_editor.pending_changes
    assert len(task_editor.pending_changes["dependencies"]) == 1
    assert task_editor.pending_changes["dependencies"][0].target_node_id == task2_id


def test_task_editor_finish_dependency_editing_with_pending_deps(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test finishing dependency editing when there are already pending dependencies."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    # Create three tasks
    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task3_id = controller.create_task(
        title="Task 3",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task3_id)

    # Pre-populate pending_changes with a dependency
    existing_dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    task_editor.pending_changes["dependencies"] = [existing_dep]

    # Start adding a new dependency
    task_editor._on_add_dependency()

    # Set up dependency editor with a complete dependency
    task_editor.dependency_editor.set_target_node(task2_id)
    task_editor.dependency_editor.source_endpoint_combo.setCurrentIndex(0)  # START
    task_editor.dependency_editor.target_endpoint_combo.setCurrentIndex(1)  # END
    task_editor.dependency_editor.constraint_type_combo.setCurrentIndex(0)  # >=

    # Finish editing
    task_editor.finish_dependency_editing()

    # Should now have 2 dependencies
    assert "dependencies" in task_editor.pending_changes
    assert len(task_editor.pending_changes["dependencies"]) == 2


def test_task_editor_remove_dependency_no_task(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test remove dependency when no task is loaded."""
    # Try to remove without loading a task
    task_editor._on_remove_dependency()
    # Should not crash


def test_task_editor_remove_dependency_no_selection(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test remove dependency when nothing is selected."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)

    task_editor.load_task(task2_id)

    # Clear selection
    task_editor.dependencies_list.clearSelection()

    # Try to remove - should do nothing
    task_editor._on_remove_dependency()

    # Dependencies should still be there
    assert task_editor.dependencies_list.count() == 1


def test_task_editor_remove_dependency_with_pending_changes(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test removing a dependency from pending changes."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency via controller
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)

    task_editor.load_task(task2_id)

    # Put dependencies in pending changes
    task_editor.pending_changes["dependencies"] = [dep]
    task_editor._load_dependencies([dep])

    # Select and remove
    task_editor.dependencies_list.setCurrentRow(0)
    task_editor._on_remove_dependency()

    # Pending changes should have empty dependencies
    assert "dependencies" in task_editor.pending_changes
    assert len(task_editor.pending_changes["dependencies"]) == 0


def test_task_editor_dependency_changed_handler(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test dependency changed handler (currently a no-op)."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Call handler - should not raise
    task_editor._on_dependency_changed()


def test_task_editor_set_dependency_target(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test setting dependency target."""
    target_task_id = controller.create_task(
        title="Target Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Start adding dependency
    task_editor._on_add_dependency()

    # Set target
    task_editor.set_dependency_target(target_task_id)

    # Target should be set in dependency editor
    assert task_editor.dependency_editor._target_node_id == target_task_id


def test_task_editor_dependency_select_target_signal(
    task_editor: TaskEditor, controller: ProjectController, qtbot: QtBot
) -> None:
    """Test that select target button emits signal."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Connect signal to detect emission
    signal_received = []
    task_editor.select_dependency_target_requested.connect(
        lambda: signal_received.append(True)
    )

    # Trigger select target
    task_editor._on_dependency_select_target()

    # Signal should have been emitted
    assert len(signal_received) == 1


def test_task_editor_apply_with_dependency_removal(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test applying changes that remove a dependency."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency via controller
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)

    # Load task
    task_editor.load_task(task2_id)

    # Remove dependency in pending changes
    task_editor.pending_changes["dependencies"] = []
    task_editor._update_button_states()

    # Apply
    task_editor._on_apply()

    # Verify dependency was removed
    project = controller.get_project()
    persistent_id = project.dag.node_map[task2_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert len(task.dependencies) == 0


def test_task_editor_dependency_to_possible_world(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test loading dependencies to possible worlds."""
    from fluxx.data.models import (
        ConstraintType,
        Dependency,
        Endpoint,
        PossibleWorld,
        PossibleWorldId,
        PossibleWorldReference,
    )

    # Create task and branch
    task_id = controller.create_task(
        title="Source Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    pw_id = PossibleWorldId("pw_target_001")
    branch_id = controller.create_branch(
        title="Target Branch",
        possible_worlds=[PossibleWorld(id=pw_id, title="Target World", weight=1.0)],
    )

    # Add dependency to a possible world
    pw_ref = PossibleWorldReference(f"{branch_id}:{pw_id}")
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=pw_ref,
        target_endpoint=Endpoint.OCCURRENCE,  # PW must use OCCURRENCE
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task_id, dep)

    # Load task
    task_editor.load_task(task_id)

    # Verify dependency is displayed
    assert task_editor.dependencies_list.count() == 1
    item = task_editor.dependencies_list.item(0)
    assert item is not None
    assert "Target World" in item.text()


def test_task_editor_dependency_to_branch(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test loading dependencies to branches."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import (
        ConstraintType,
        Dependency,
        Endpoint,
        PossibleWorld,
    )

    # Create task and branch
    task_id = controller.create_task(
        title="Source Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Target Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="World 1", weight=1.0)
        ],
    )

    # Add dependency to branch (occurrence point)
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=branch_id,
        target_endpoint=Endpoint.OCCURRENCE,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task_id, dep)

    # Load task
    task_editor.load_task(task_id)

    # Verify dependency is displayed
    assert task_editor.dependencies_list.count() == 1
    item = task_editor.dependencies_list.item(0)
    assert item is not None
    assert "Target Branch" in item.text()


def test_task_editor_is_required_dependency_subtask(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test that parent-child dependency is detected as required."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    # Create parent and convert to parent to create a subtask
    parent_id = controller.create_task(
        title="Parent Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    controller.convert_to_parent(parent_id, "Child Task")

    # Get the child task ID
    project = controller.get_project()
    persistent_id = project.dag.node_map[parent_id]
    parent_task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    child_id = parent_task.children[0]

    # Load child task
    task_editor.load_task(child_id)

    # The child should have a required dependency: start >= parent.start
    req_dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=parent_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    assert task_editor._is_required_dependency(req_dep) is True


def test_task_editor_is_required_dependency_parent(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test that parent-child dependency (parent end >= child end) is detected."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    # Create parent and convert to parent to create a subtask
    parent_id = controller.create_task(
        title="Parent Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    controller.convert_to_parent(parent_id, "Child Task")

    # Get the child task ID
    project = controller.get_project()
    persistent_id = project.dag.node_map[parent_id]
    parent_task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    child_id = parent_task.children[0]

    # Load parent task
    task_editor.load_task(parent_id)

    # The parent should have a required dependency: end >= child.end
    req_dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=child_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    assert task_editor._is_required_dependency(req_dep) is True


def test_task_editor_is_required_dependency_no_task(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test _is_required_dependency when no task is loaded."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=controller.create_task(
            title="Target",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        ),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # No task loaded
    assert task_editor._is_required_dependency(dep) is False


def test_task_editor_subtask_buttons_enabled(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test subtask operation buttons are enabled/disabled correctly."""
    # Create a leaf task
    task_id = controller.create_task(
        title="Leaf Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Leaf task: convert to parent enabled, add sibling disabled
    assert task_editor.convert_to_parent_button.isEnabled()
    assert not task_editor.add_sibling_button.isEnabled()

    # Convert to parent
    controller.convert_to_parent(task_id, "Child Task")

    # Get child ID
    project = controller.get_project()
    persistent_id = project.dag.node_map[task_id]
    parent_task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    child_id = parent_task.children[0]

    # Load child (subtask)
    task_editor.load_task(child_id)

    # Subtask: add sibling enabled, convert to parent enabled (because it's a leaf)
    assert task_editor.add_sibling_button.isEnabled()
    assert task_editor.convert_to_parent_button.isEnabled()


def test_task_editor_update_button_states_task_not_found(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test _update_button_states when task is not found."""
    from fluxx.data.models import TaskId

    # Set a fake task ID
    task_editor.current_task_id = TaskId("nonexistent")

    # Update button states
    task_editor._update_button_states()

    # Both subtask buttons should be disabled
    assert not task_editor.convert_to_parent_button.isEnabled()
    assert not task_editor.add_sibling_button.isEnabled()


# ==================== Allowed Workers Tests ====================


def test_task_editor_allowed_workers_empty_state(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test allowed workers section shows empty state when all workers allowed."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Empty state label should be visible, list should be hidden
    # Note: isHidden() checks explicit visibility state;
    # isVisible() requires parent to be shown
    assert not task_editor.allowed_workers_empty_label.isHidden()
    assert task_editor.allowed_workers_list.isHidden()
    assert task_editor.allowed_workers_button_container.isHidden()


def test_task_editor_allowed_workers_with_restrictions(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test allowed workers section shows list when workers are restricted."""
    # Add workers first
    worker_id = controller.add_worker(name="Alice", hours_per_workday=8.0)

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[worker_id],
    )
    task_editor.load_task(task_id)

    # List should be visible, empty state hidden
    assert task_editor.allowed_workers_empty_label.isHidden()
    assert not task_editor.allowed_workers_list.isHidden()
    assert not task_editor.allowed_workers_button_container.isHidden()
    assert task_editor.allowed_workers_list.count() == 1


def test_task_editor_restrict_workers_clicked(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test clicking restrict workers link switches to restricted mode."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Initially empty state
    assert not task_editor.allowed_workers_empty_label.isHidden()

    # Click restrict workers link
    task_editor._on_restrict_workers_clicked("#")

    # Should switch to list mode
    assert task_editor.allowed_workers_empty_label.isHidden()
    assert not task_editor.allowed_workers_list.isHidden()
    assert not task_editor.allowed_workers_button_container.isHidden()

    # Pending changes should have empty list
    assert "allowed_workers" in task_editor.pending_changes
    assert task_editor.pending_changes["allowed_workers"] == []


def test_task_editor_allowed_worker_selection_changes(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test allowed worker selection enables/disables remove button."""
    worker_id = controller.add_worker(name="Alice", hours_per_workday=8.0)

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[worker_id],
    )
    task_editor.load_task(task_id)

    # Initially no selection
    task_editor.allowed_workers_list.clearSelection()
    task_editor._on_allowed_worker_selection_changed()
    assert not task_editor.remove_allowed_worker_button.isEnabled()

    # Select the worker
    task_editor.allowed_workers_list.setCurrentRow(0)
    assert task_editor.remove_allowed_worker_button.isEnabled()


def test_task_editor_remove_allowed_worker(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test removing a worker from allowed list."""
    worker1_id = controller.add_worker(name="Alice", hours_per_workday=8.0)
    worker2_id = controller.add_worker(name="Bob", hours_per_workday=7.5)

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[worker1_id, worker2_id],
    )
    task_editor.load_task(task_id)

    assert task_editor.allowed_workers_list.count() == 2

    # Select and remove first worker
    task_editor.allowed_workers_list.setCurrentRow(0)
    task_editor._on_remove_allowed_worker()

    # Should have one worker left
    assert "allowed_workers" in task_editor.pending_changes
    assert len(task_editor.pending_changes["allowed_workers"]) == 1


def test_task_editor_remove_allowed_worker_no_selection(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test removing allowed worker when nothing is selected."""
    worker_id = controller.add_worker(name="Alice", hours_per_workday=8.0)

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[worker_id],
    )
    task_editor.load_task(task_id)

    # Clear selection and try to remove
    task_editor.allowed_workers_list.clearSelection()
    task_editor._on_remove_allowed_worker()

    # Nothing should change
    assert "allowed_workers" not in task_editor.pending_changes


def test_task_editor_allow_all_workers(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test clicking allow all workers button."""
    worker_id = controller.add_worker(name="Alice", hours_per_workday=8.0)

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[worker_id],
    )
    task_editor.load_task(task_id)

    # Click allow all workers
    task_editor._on_allow_all_workers()

    # Should set to None and show empty state
    assert "allowed_workers" in task_editor.pending_changes
    assert task_editor.pending_changes["allowed_workers"] is None
    assert not task_editor.allowed_workers_empty_label.isHidden()


def test_task_editor_load_allowed_workers_unknown_worker(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test loading allowed workers with an unknown worker ID."""
    from fluxx.data.models import WorkerId

    # Create task without allowed workers
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Directly call _load_allowed_workers with an unknown worker ID
    # This simulates loading a task that was created when the worker existed
    # but the worker has since been deleted
    task_editor._load_allowed_workers([WorkerId("unknown-worker-id")])

    # Should show unknown worker in list
    assert task_editor.allowed_workers_list.count() == 1
    item = task_editor.allowed_workers_list.item(0)
    assert item is not None
    assert "Unknown" in item.text()


# ==================== Excluded Assignees Tests ====================


def test_task_editor_excluded_assignees_empty(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test excluded assignees list is empty by default."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    assert task_editor.excluded_assignees_list.count() == 0


def test_task_editor_load_excluded_assignees(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test loading excluded assignee tasks."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add required dependency first
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)

    # Update task2 to exclude task1's assignee
    controller.update_task(task2_id, excluded_worker_tasks=[task1_id])

    task_editor.load_task(task2_id)

    assert task_editor.excluded_assignees_list.count() == 1
    item = task_editor.excluded_assignees_list.item(0)
    assert item is not None
    assert item.text() == "Task 1"


def test_task_editor_excluded_assignee_selection_changed(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test excluded assignee selection enables/disables remove button."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add required dependency
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)
    controller.update_task(task2_id, excluded_worker_tasks=[task1_id])

    task_editor.load_task(task2_id)

    # Initially no selection
    task_editor.excluded_assignees_list.clearSelection()
    task_editor._on_excluded_assignee_selection_changed()
    assert not task_editor.remove_excluded_task_button.isEnabled()

    # Select the task
    task_editor.excluded_assignees_list.setCurrentRow(0)
    assert task_editor.remove_excluded_task_button.isEnabled()


def test_task_editor_get_current_excluded_tasks_empty(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test _get_current_excluded_tasks returns empty list when no task loaded."""
    assert task_editor._get_current_excluded_tasks() == []


def test_task_editor_get_current_excluded_tasks_from_pending(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test _get_current_excluded_tasks returns pending changes if present."""
    from fluxx.data.models import TaskId

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Set pending changes
    fake_excluded = [TaskId("fake-id")]
    task_editor.pending_changes["excluded_worker_tasks"] = fake_excluded

    result = task_editor._get_current_excluded_tasks()
    assert result == fake_excluded


def test_task_editor_get_available_tasks_for_exclusion(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test _get_available_tasks_for_exclusion returns other tasks."""
    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    task_editor.load_task(task1_id)

    available = task_editor._get_available_tasks_for_exclusion()

    # Should include task2 but not task1 (current task)
    task_ids = [t[0] for t in available]
    assert task2_id in task_ids
    assert task1_id not in task_ids


def test_task_editor_get_available_tasks_for_exclusion_no_task(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test _get_available_tasks_for_exclusion with no task loaded."""
    assert task_editor._get_available_tasks_for_exclusion() == []


def test_task_editor_remove_excluded_task(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test removing an excluded task."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add required dependency
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)
    controller.update_task(task2_id, excluded_worker_tasks=[task1_id])

    task_editor.load_task(task2_id)
    assert task_editor.excluded_assignees_list.count() == 1

    # Select and remove
    task_editor.excluded_assignees_list.setCurrentRow(0)
    task_editor._on_remove_excluded_task()

    # Should be empty now
    assert "excluded_worker_tasks" in task_editor.pending_changes
    assert len(task_editor.pending_changes["excluded_worker_tasks"]) == 0


def test_task_editor_remove_excluded_task_no_selection(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test removing excluded task when nothing is selected."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)
    controller.update_task(task2_id, excluded_worker_tasks=[task1_id])

    task_editor.load_task(task2_id)

    # Clear selection and try to remove
    task_editor.excluded_assignees_list.clearSelection()
    task_editor._on_remove_excluded_task()

    # Nothing should change
    assert "excluded_worker_tasks" not in task_editor.pending_changes


def test_task_editor_add_dependency_to_pending(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test _add_dependency_to_pending adds dependency to pending changes."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    task_editor.load_task(task2_id)

    # Add dependency
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    task_editor._add_dependency_to_pending(dep)

    assert "dependencies" in task_editor.pending_changes
    assert dep in task_editor.pending_changes["dependencies"]


def test_task_editor_add_dependency_to_pending_no_task(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test _add_dependency_to_pending with no task loaded."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint, TaskId

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("some-id"),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    task_editor._add_dependency_to_pending(dep)

    # Should not add anything
    assert "dependencies" not in task_editor.pending_changes


def test_task_editor_add_dependency_to_pending_already_exists(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test _add_dependency_to_pending doesn't duplicate existing dependencies."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency first
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)

    task_editor.load_task(task2_id)

    # Try to add same dependency again
    task_editor._add_dependency_to_pending(dep)

    # Should only have one dependency
    if "dependencies" in task_editor.pending_changes:
        count = sum(1 for d in task_editor.pending_changes["dependencies"] if d == dep)
        assert count <= 1


def test_task_editor_load_excluded_assignees_unknown_task(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test loading excluded assignees with unknown task ID."""
    from fluxx.data.models import TaskId

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Directly call load with unknown task ID
    task_editor.load_task(task_id)
    task_editor._load_excluded_assignees([TaskId("unknown-task-id")])

    # Should show unknown task
    assert task_editor.excluded_assignees_list.count() == 1
    item = task_editor.excluded_assignees_list.item(0)
    assert item is not None
    assert "Unknown" in item.text()


def test_task_editor_apply_allowed_workers_change(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test applying allowed workers changes."""
    worker_id = controller.add_worker(name="Alice", hours_per_workday=8.0)

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Set allowed workers
    task_editor.pending_changes["allowed_workers"] = [worker_id]
    task_editor._update_button_states()

    # Apply changes
    task_editor._on_apply()

    # Verify task was updated
    project = controller.get_project()
    node_id = task_id
    persistent_id = project.dag.node_map[node_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert task.allowed_workers is not None
    assert worker_id in task.allowed_workers


def test_task_editor_apply_excluded_tasks_change(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test applying excluded worker tasks changes."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add required dependency
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)

    task_editor.load_task(task2_id)

    # Set excluded worker tasks
    task_editor.pending_changes["excluded_worker_tasks"] = [task1_id]
    task_editor._update_button_states()

    # Apply changes
    task_editor._on_apply()

    # Verify task was updated
    project = controller.get_project()
    node_id = task2_id
    persistent_id = project.dag.node_map[node_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert task1_id in task.excluded_worker_tasks


# ==================== Dialog-mocking tests for coverage ====================


def test_task_editor_add_allowed_worker_no_workers(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test adding allowed worker when no workers exist in project."""
    from unittest.mock import patch

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Switch to restricted mode first
    task_editor._on_restrict_workers_clicked("#")

    # Mock QMessageBox to avoid modal dialog
    with patch(
        "fluxx.gui.widgets.editors.task_editor.QMessageBox.information"
    ) as mock_info:
        task_editor._on_add_allowed_worker()
        mock_info.assert_called_once()


def test_task_editor_add_allowed_worker_all_added(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test adding allowed worker when all workers already in list."""
    from unittest.mock import patch

    worker_id = controller.add_worker(name="Alice", hours_per_workday=8.0)

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[worker_id],
    )
    task_editor.load_task(task_id)

    # Mock QMessageBox
    with patch(
        "fluxx.gui.widgets.editors.task_editor.QMessageBox.information"
    ) as mock_info:
        task_editor._on_add_allowed_worker()
        mock_info.assert_called_once()


def test_task_editor_add_allowed_worker_with_dialog(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test adding allowed worker via dialog selection."""
    from unittest.mock import patch

    worker_id = controller.add_worker(name="Bob", hours_per_workday=8.0)
    controller.add_worker(name="Charlie", hours_per_workday=7.5)

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[worker_id],  # Bob is already allowed
    )
    task_editor.load_task(task_id)

    # Mock QInputDialog.getItem to return "Charlie"
    with patch(
        "fluxx.gui.widgets.editors.task_editor.QInputDialog.getItem"
    ) as mock_dialog:
        mock_dialog.return_value = ("Charlie", True)
        task_editor._on_add_allowed_worker()

        # Should have added Charlie
        assert "allowed_workers" in task_editor.pending_changes
        assert len(task_editor.pending_changes["allowed_workers"]) == 2


def test_task_editor_add_allowed_worker_cancelled(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test cancelling the add allowed worker dialog."""
    from unittest.mock import patch

    controller.add_worker(name="Alice", hours_per_workday=8.0)

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)
    task_editor._on_restrict_workers_clicked("#")

    # Mock dialog returning cancelled
    with patch(
        "fluxx.gui.widgets.editors.task_editor.QInputDialog.getItem"
    ) as mock_dialog:
        mock_dialog.return_value = ("", False)
        task_editor._on_add_allowed_worker()

        # allowed_workers should still be empty
        assert task_editor.pending_changes["allowed_workers"] == []


def test_task_editor_add_excluded_task_emits_signal(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test that clicking add excluded task emits the selection signal."""
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Track signal emission
    signal_received = []
    task_editor.select_excluded_task_requested.connect(
        lambda: signal_received.append(True)
    )

    task_editor._on_add_excluded_task()

    assert len(signal_received) == 1


def test_task_editor_set_excluded_task_invalid_branch(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test set_excluded_task rejects branch nodes."""
    from unittest.mock import patch

    from fluxx.data.models import BranchId

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Try to set a branch as excluded task (using valid branch ID pattern)
    with patch(
        "fluxx.gui.widgets.editors.task_editor.QMessageBox.warning"
    ) as mock_warning:
        task_editor.set_excluded_task(BranchId("b1"))
        mock_warning.assert_called_once()

    # Should not have added anything
    assert "excluded_worker_tasks" not in task_editor.pending_changes


def test_task_editor_set_excluded_task_with_existing_dep(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test set_excluded_task when dependency already exists."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add required dependency first
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task1_id, dep)

    task_editor.load_task(task1_id)

    # Directly call set_excluded_task (simulating DAG selection)
    task_editor.set_excluded_task(task2_id)

    # Should have added Task 2 to exclusion list
    assert "excluded_worker_tasks" in task_editor.pending_changes
    assert task2_id in task_editor.pending_changes["excluded_worker_tasks"]


def test_task_editor_set_excluded_task_add_dep_accepted(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test set_excluded_task with auto-add dependency accepted."""
    from unittest.mock import patch

    from PySide6.QtWidgets import QMessageBox

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    task_editor.load_task(task1_id)

    # Mock the question dialog - user accepts adding dependency
    with patch(
        "fluxx.gui.widgets.editors.task_editor.QMessageBox.question"
    ) as mock_question:
        mock_question.return_value = QMessageBox.StandardButton.Yes

        task_editor.set_excluded_task(task2_id)

        # Should have added both the exclusion and the dependency
        assert "excluded_worker_tasks" in task_editor.pending_changes
        assert task2_id in task_editor.pending_changes["excluded_worker_tasks"]
        assert "dependencies" in task_editor.pending_changes


def test_task_editor_set_excluded_task_add_dep_rejected(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test set_excluded_task with auto-add dependency rejected."""
    from unittest.mock import patch

    from PySide6.QtWidgets import QMessageBox

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    task_editor.load_task(task1_id)

    # Mock the question dialog - user rejects adding dependency
    with patch(
        "fluxx.gui.widgets.editors.task_editor.QMessageBox.question"
    ) as mock_question:
        mock_question.return_value = QMessageBox.StandardButton.No

        task_editor.set_excluded_task(task2_id)

        # Should NOT have added the exclusion
        assert "excluded_worker_tasks" not in task_editor.pending_changes


def test_task_editor_set_excluded_task_self_reference(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test set_excluded_task rejects self-reference."""
    from unittest.mock import patch

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Try to exclude same task
    with patch(
        "fluxx.gui.widgets.editors.task_editor.QMessageBox.warning"
    ) as mock_warning:
        task_editor.set_excluded_task(task_id)
        mock_warning.assert_called_once()

    # Should not have added anything
    assert "excluded_worker_tasks" not in task_editor.pending_changes


def test_task_editor_set_excluded_task_already_excluded(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test set_excluded_task rejects already excluded task."""
    from unittest.mock import patch

    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add required dependency
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task1_id, dep)
    controller.update_task(task1_id, excluded_worker_tasks=[task2_id])

    task_editor.load_task(task1_id)

    # Try to add same task again
    with patch(
        "fluxx.gui.widgets.editors.task_editor.QMessageBox.information"
    ) as mock_info:
        task_editor.set_excluded_task(task2_id)
        mock_info.assert_called_once()

    # Should not have modified pending changes
    assert "excluded_worker_tasks" not in task_editor.pending_changes


def test_task_editor_add_allowed_worker_with_worker_id(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test adding worker that has a worker_id field."""
    from unittest.mock import patch

    controller.add_worker(name="Alice", hours_per_workday=8.0, worker_id="alice_001")

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)
    task_editor._on_restrict_workers_clicked("#")

    # Mock dialog
    with patch(
        "fluxx.gui.widgets.editors.task_editor.QInputDialog.getItem"
    ) as mock_dialog:
        mock_dialog.return_value = ("Alice (alice_001)", True)
        task_editor._on_add_allowed_worker()

        # Should have added worker
        assert "allowed_workers" in task_editor.pending_changes
        assert len(task_editor.pending_changes["allowed_workers"]) == 1


def test_task_editor_remove_allowed_worker_from_pending(
    task_editor: TaskEditor, controller: ProjectController
) -> None:
    """Test removing worker from pending allowed workers list."""
    worker1_id = controller.add_worker(name="Alice", hours_per_workday=8.0)
    worker2_id = controller.add_worker(name="Bob", hours_per_workday=7.5)

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_editor.load_task(task_id)

    # Set pending changes with both workers
    task_editor.pending_changes["allowed_workers"] = [worker1_id, worker2_id]
    task_editor._load_allowed_workers([worker1_id, worker2_id])

    # Select and remove first worker
    task_editor.allowed_workers_list.setCurrentRow(0)
    task_editor._on_remove_allowed_worker()

    # Should have one worker left
    assert len(task_editor.pending_changes["allowed_workers"]) == 1
