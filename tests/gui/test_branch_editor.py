"""Tests for BranchEditor widget."""

from collections.abc import Generator

import pytest
from pytestqt.qtbot import QtBot

from fluxx.data.models import PossibleWorld
from fluxx.gui.controller import ProjectController
from fluxx.gui.widgets.editors.branch_editor import BranchEditor


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
def branch_editor(
    qtbot: QtBot, controller: ProjectController
) -> Generator[BranchEditor]:
    """Create a BranchEditor for testing.

    Args:
        qtbot: QtBot fixture
        controller: ProjectController fixture

    Yields:
        BranchEditor instance
    """
    editor = BranchEditor(controller)
    qtbot.addWidget(editor)
    yield editor


def test_branch_editor_initialization(branch_editor: BranchEditor) -> None:
    """Test that branch editor initializes correctly."""
    assert branch_editor.controller is not None
    assert branch_editor.current_branch_id is None
    assert branch_editor.pending_changes == {}
    assert not branch_editor.apply_button.isEnabled()
    assert not branch_editor.revert_button.isEnabled()


def test_branch_editor_loads_branch(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test loading a branch into the editor."""
    # Create a branch
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Test Branch",
        description="Test description",
        possible_worlds=[
            PossibleWorld(
                id=generate_possible_world_id(), title="Option A", weight=1.0
            ),
            PossibleWorld(
                id=generate_possible_world_id(), title="Option B", weight=2.0
            ),
        ],
    )

    # Load branch into editor
    branch_editor.load_branch(branch_id)

    # Verify fields are populated
    assert branch_editor.title_field.text() == "Test Branch"
    assert branch_editor.description_field.toPlainText() == "Test description"
    assert branch_editor.worlds_table.rowCount() == 2


def test_branch_editor_title_change(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test changing branch title."""
    # Create and load a branch
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Original Title",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Change title
    branch_editor.title_field.setText("New Title")

    # Verify pending changes
    assert "title" in branch_editor.pending_changes
    assert branch_editor.pending_changes["title"] == "New Title"
    assert branch_editor.apply_button.isEnabled()
    assert branch_editor.revert_button.isEnabled()


def test_branch_editor_description_change(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test changing branch description."""
    # Create and load a branch
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        description="Original",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Change description
    branch_editor.description_field.setPlainText("New description")

    # Verify pending changes
    assert "description" in branch_editor.pending_changes
    assert branch_editor.pending_changes["description"] == "New description"
    assert branch_editor.apply_button.isEnabled()


def test_branch_editor_apply_changes(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test applying changes to a branch."""
    # Create and load a branch
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Original",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Make changes
    branch_editor.title_field.setText("Updated")

    # Apply changes
    branch_editor._on_apply()

    # Verify branch was updated
    project = controller.get_project()
    node_id = branch_id
    persistent_id = project.dag.node_map[node_id]
    branch = project.persistent_branches[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert branch.title == "Updated"

    # Verify pending changes cleared
    assert branch_editor.pending_changes == {}
    assert not branch_editor.apply_button.isEnabled()


def test_branch_editor_revert_changes(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test reverting changes."""
    # Create and load a branch
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Original",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Make changes
    branch_editor.title_field.setText("Changed")
    assert "title" in branch_editor.pending_changes

    # Revert
    branch_editor._on_revert()

    # Verify reverted to original
    assert branch_editor.title_field.text() == "Original"
    assert branch_editor.pending_changes == {}
    assert not branch_editor.apply_button.isEnabled()


def test_branch_editor_empty_title_validation(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test that empty title is invalid."""
    # Create and load a branch
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Valid Title",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Change to empty title
    branch_editor.title_field.setText("")

    # Verify apply button is disabled (invalid)
    assert not branch_editor.apply_button.isEnabled()


def test_branch_editor_add_world(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test adding a new possible world."""
    # Create and load a branch
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Initial count
    initial_count = branch_editor.worlds_table.rowCount()

    # Add a world
    branch_editor._on_add_world()

    # Verify row added
    assert branch_editor.worlds_table.rowCount() == initial_count + 1

    # Verify pending changes
    assert "possible_worlds" in branch_editor.pending_changes


def test_branch_editor_remove_world(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test removing a possible world."""
    # Create and load a branch with two worlds
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(
                id=generate_possible_world_id(), title="Option A", weight=1.0
            ),
            PossibleWorld(
                id=generate_possible_world_id(), title="Option B", weight=1.0
            ),
        ],
    )
    branch_editor.load_branch(branch_id)

    # Select first world
    branch_editor.worlds_table.setCurrentCell(0, 0)

    # Remove button should be enabled
    assert branch_editor.remove_world_button.isEnabled()

    # Remove world
    branch_editor._on_remove_world()

    # Verify row removed
    assert branch_editor.worlds_table.rowCount() == 1


def test_branch_editor_add_dependency_and_apply(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test that adding a dependency to a branch and applying works without errors."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import (
        ConstraintType,
        Dependency,
        Endpoint,
        PossibleWorld,
        Triangular,
    )

    # Create a task and a branch
    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Branch 1",
        possible_worlds=[
            PossibleWorld(
                id=generate_possible_world_id(), title="Option A", weight=1.0
            ),
        ],
    )

    # Load branch in editor
    branch_editor.load_branch(branch_id)

    # Simulate adding a dependency to the task
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=task_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # Get current dependencies from branch
    project = controller.get_project()
    current_version = project.dag.current_version_id
    persistent_id = project.dag.node_map[branch_id]
    branch = project.persistent_branches[persistent_id].versions[current_version]
    current_deps = list(branch.dependencies)
    current_deps.append(dep)

    # Update pending changes with new dependencies list
    branch_editor.pending_changes["dependencies"] = current_deps
    branch_editor._update_button_states()

    # Apply should work without raising TypeError
    branch_editor._on_apply()

    # Verify the dependency was added
    project_after = controller.get_project()
    persistent_id_after = project_after.dag.node_map[branch_id]
    branch_after = project_after.persistent_branches[persistent_id_after].versions[
        project_after.dag.current_version_id
    ]
    assert len(branch_after.dependencies) == 1
    assert branch_after.dependencies[0].target_node_id == task_id


def test_branch_editor_dependency_display(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test that dependencies are displayed in the correct format."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import (
        ConstraintType,
        Dependency,
        Endpoint,
        PossibleWorld,
        Triangular,
    )

    # Create a task and a branch
    task_id = controller.create_task(
        title="Make Plan",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Source Branch",
        possible_worlds=[
            PossibleWorld(
                id=generate_possible_world_id(), title="Option A", weight=1.0
            ),
        ],
    )

    # Add dependency: branch.occurrence >= task.end
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=task_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(branch_id, dep)

    # Load branch in editor
    branch_editor.load_branch(branch_id)

    # Verify dependency display format
    assert branch_editor.dependencies_list.count() == 1
    item = branch_editor.dependencies_list.item(0)
    assert item is not None
    assert item.text() == "occurrence_point ≥ Make Plan.end"


def test_branch_editor_load_nonexistent_branch(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test loading a non-existent branch does nothing."""
    from fluxx.data.models import BranchId

    # Load a branch that doesn't exist
    fake_id = BranchId("nonexistent")
    branch_editor.load_branch(fake_id)

    # Editor should have no content
    assert branch_editor.current_branch_id == fake_id
    # Fields should be empty or unchanged from default


def test_branch_editor_world_weight_invalid(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test handling of invalid weight values."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Set invalid weight (non-numeric)
    weight_item = branch_editor.worlds_table.item(0, 2)
    if weight_item is not None:
        weight_item.setText("abc")

    # Trigger update manually
    worlds = branch_editor._get_worlds_from_table()
    assert worlds is None  # Should return None for invalid weight


def test_branch_editor_world_weight_negative(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test handling of negative weight values."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Set negative weight
    weight_item = branch_editor.worlds_table.item(0, 2)
    if weight_item is not None:
        weight_item.setText("-1.0")

    # Get worlds should return None for invalid weight
    worlds = branch_editor._get_worlds_from_table()
    assert worlds is None


def test_branch_editor_probability_column_readonly(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test that changing probability column is ignored."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Try to change probability column (should be skipped)
    branch_editor._on_world_cell_changed(0, 3)  # Column 3 is probability

    # Should not add pending changes for probability
    assert "possible_worlds" not in branch_editor.pending_changes


def test_branch_editor_add_dependency_button(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test add dependency button enables dependency editing mode."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Click add dependency
    branch_editor._on_add_dependency()

    # Editing mode should be active
    assert branch_editor._editing_dependency_index is None  # None means adding new
    # Apply/revert buttons should be disabled during dependency editing
    assert not branch_editor.apply_button.isEnabled()
    assert not branch_editor.add_dependency_button.isEnabled()


def test_branch_editor_cancel_dependency(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test canceling dependency editing."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Start adding dependency
    branch_editor._on_add_dependency()
    # Editing index should be set to None (adding new)
    assert branch_editor._editing_dependency_index is None
    assert not branch_editor.add_dependency_button.isEnabled()

    # Cancel
    branch_editor._on_dependency_cancelled()

    # Should exit editing mode
    assert branch_editor._editing_dependency_index is None
    # Add dependency button should be re-enabled
    assert branch_editor.add_dependency_button.isEnabled()


def test_branch_editor_set_dependency_target(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test setting dependency target."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import Triangular

    task_id = controller.create_task(
        title="Target Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Start adding dependency
    branch_editor._on_add_dependency()

    # Set target
    branch_editor.set_dependency_target(task_id)

    # Target should be set in dependency editor
    assert branch_editor.dependency_editor._target_node_id == task_id


def test_branch_editor_remove_dependency(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test removing a dependency."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import ConstraintType, Dependency, Endpoint, Triangular

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )

    # Add dependency via controller
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=task_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(branch_id, dep)

    # Load branch
    branch_editor.load_branch(branch_id)
    assert branch_editor.dependencies_list.count() == 1

    # Select and remove
    branch_editor.dependencies_list.setCurrentRow(0)
    branch_editor._on_remove_dependency()

    # Pending changes should have empty dependencies
    assert "dependencies" in branch_editor.pending_changes
    assert len(branch_editor.pending_changes["dependencies"]) == 0


def test_branch_editor_is_dirty(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test is_dirty method."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Initially not dirty
    assert not branch_editor.is_dirty()

    # Make changes
    branch_editor.title_field.setText("Changed")

    # Now dirty
    assert branch_editor.is_dirty()


def test_branch_editor_apply_changes_method(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test apply_changes method."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # When not dirty, should return True immediately
    assert branch_editor.apply_changes() is True

    # Make changes
    branch_editor.title_field.setText("Updated Title")
    assert branch_editor.is_dirty()

    # Apply changes
    result = branch_editor.apply_changes()

    # Should return True and clear pending changes
    assert result is True
    assert not branch_editor.is_dirty()


def test_branch_editor_revert_changes_method(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test revert_changes method."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Original",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Make changes
    branch_editor.title_field.setText("Changed")
    assert branch_editor.is_dirty()

    # Revert changes
    branch_editor.revert_changes()

    # Should restore original and clear pending changes
    assert branch_editor.title_field.text() == "Original"
    assert not branch_editor.is_dirty()


def test_branch_editor_on_delete(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test delete button handler (currently a no-op)."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Call delete handler - should not raise
    branch_editor._on_delete()


def test_branch_editor_apply_invalid_changes(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test that apply with invalid changes does nothing."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Set empty title (invalid)
    branch_editor.title_field.setText("")

    # Manually call apply (button would be disabled)
    branch_editor._on_apply()

    # Changes should not be cleared because validation failed
    assert "title" in branch_editor.pending_changes


def test_branch_editor_apply_with_dependency_removal(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test applying changes that remove a dependency."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import ConstraintType, Dependency, Endpoint, Triangular

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )

    # Add dependency via controller
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=task_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(branch_id, dep)

    # Load branch
    branch_editor.load_branch(branch_id)

    # Remove dependency in pending changes
    branch_editor.pending_changes["dependencies"] = []
    branch_editor._update_button_states()

    # Apply
    branch_editor._on_apply()

    # Verify dependency was removed
    project = controller.get_project()
    persistent_id = project.dag.node_map[branch_id]
    branch = project.persistent_branches[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert len(branch.dependencies) == 0


def test_branch_editor_dependency_to_possible_world(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test loading dependencies to possible worlds."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import (
        ConstraintType,
        Dependency,
        Endpoint,
        PossibleWorldId,
        PossibleWorldReference,
    )

    # Create two branches
    pw_id = PossibleWorldId("pw_target_001")
    branch1_id = controller.create_branch(
        title="Source Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch2_id = controller.create_branch(
        title="Target Branch",
        possible_worlds=[PossibleWorld(id=pw_id, title="Target World", weight=1.0)],
    )

    # Add dependency to a possible world using correct format: "branch_id:world_id"
    # Possible worlds can only use OCCURRENCE endpoint
    pw_ref = PossibleWorldReference(f"{branch2_id}:{pw_id}")
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=pw_ref,
        target_endpoint=Endpoint.OCCURRENCE,  # PW must use OCCURRENCE
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(branch1_id, dep)

    # Load branch
    branch_editor.load_branch(branch1_id)

    # Verify dependency is displayed
    assert branch_editor.dependencies_list.count() == 1
    item = branch_editor.dependencies_list.item(0)
    assert item is not None
    assert "Target World" in item.text()


def test_branch_editor_add_dependency_no_branch(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test add dependency when no branch is loaded."""
    # Call without loading a branch
    branch_editor._on_add_dependency()

    # Should do nothing (early return)
    assert not branch_editor.dependency_editor.isVisible()


def test_branch_editor_finish_dependency_no_branch(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test finish dependency editing when no branch is loaded."""
    # Call without loading a branch
    branch_editor.finish_dependency_editing()

    # Should do nothing


def test_branch_editor_remove_dependency_no_selection(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test remove dependency when nothing is selected."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import ConstraintType, Dependency, Endpoint, Triangular

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )

    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=task_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(branch_id, dep)

    branch_editor.load_branch(branch_id)

    # Clear selection
    branch_editor.dependencies_list.clearSelection()

    # Try to remove - should do nothing
    branch_editor._on_remove_dependency()

    # Dependencies should still be there
    assert branch_editor.dependencies_list.count() == 1


def test_branch_editor_world_selection_changed(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test world table selection change handler."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(
                id=generate_possible_world_id(), title="Option A", weight=1.0
            ),
            PossibleWorld(
                id=generate_possible_world_id(), title="Option B", weight=1.0
            ),
        ],
    )
    branch_editor.load_branch(branch_id)

    # Select a world
    branch_editor.worlds_table.setCurrentCell(0, 0)

    # Remove button should be enabled
    assert branch_editor.remove_world_button.isEnabled()

    # Deselect
    branch_editor.worlds_table.setCurrentCell(-1, -1)
    branch_editor._on_world_selection_changed(-1, 0, 0, 0)

    # Remove button should be disabled
    assert not branch_editor.remove_world_button.isEnabled()


def test_branch_editor_dependency_changed_handler(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test dependency changed handler (currently a no-op)."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Call handler - should not raise
    branch_editor._on_dependency_changed()


def test_branch_editor_dependency_select_target_signal(
    branch_editor: BranchEditor, controller: ProjectController, qtbot: QtBot
) -> None:
    """Test that select target button emits signal."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Connect signal to detect emission
    signal_received = []
    branch_editor.select_dependency_target_requested.connect(
        lambda: signal_received.append(True)
    )

    # Trigger select target
    branch_editor._on_dependency_select_target()

    # Signal should have been emitted
    assert len(signal_received) == 1


def test_branch_editor_finish_dependency_editing_with_valid_dependency(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test finishing dependency editing with a valid dependency."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import Triangular

    # Create task as target
    task_id = controller.create_task(
        title="Target Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Start adding dependency
    branch_editor._on_add_dependency()

    # Set up dependency editor with a complete dependency
    branch_editor.dependency_editor.set_target_node(task_id)
    # Branch editor doesn't have source_endpoint_combo (always OCCURRENCE)
    branch_editor.dependency_editor.target_endpoint_combo.setCurrentIndex(1)  # END
    branch_editor.dependency_editor.constraint_type_combo.setCurrentIndex(0)  # >=

    # Finish editing
    branch_editor.finish_dependency_editing()

    # Dependency should be in pending changes
    assert "dependencies" in branch_editor.pending_changes
    assert len(branch_editor.pending_changes["dependencies"]) == 1

    # Add button should be re-enabled
    assert branch_editor.add_dependency_button.isEnabled()


def test_branch_editor_finish_dependency_editing_update_existing(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test updating an existing dependency."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import ConstraintType, Dependency, Endpoint, Triangular

    # Create two tasks
    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )

    # Add initial dependency
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(branch_id, dep)

    branch_editor.load_branch(branch_id)
    assert branch_editor.dependencies_list.count() == 1

    # Simulate editing existing dependency (index 0)
    branch_editor._editing_dependency_index = 0

    # Set up dependency editor with updated target
    branch_editor.dependency_editor.set_target_node(task2_id)
    # Branch editor doesn't have source_endpoint_combo (always OCCURRENCE)
    branch_editor.dependency_editor.target_endpoint_combo.setCurrentIndex(1)  # END
    branch_editor.dependency_editor.constraint_type_combo.setCurrentIndex(0)  # >=

    # Finish editing
    branch_editor.finish_dependency_editing()

    # Should still have 1 dependency, but updated
    assert "dependencies" in branch_editor.pending_changes
    assert len(branch_editor.pending_changes["dependencies"]) == 1
    assert branch_editor.pending_changes["dependencies"][0].target_node_id == task2_id


def test_branch_editor_remove_dependency_no_branch(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test remove dependency when no branch is loaded."""
    # Try to remove without loading a branch
    branch_editor._on_remove_dependency()
    # Should not crash


def test_branch_editor_remove_dependency_with_pending_changes(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test removing a dependency from pending changes."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import ConstraintType, Dependency, Endpoint, Triangular

    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )

    # Add dependency via controller
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=task_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(branch_id, dep)

    branch_editor.load_branch(branch_id)

    # Put dependencies in pending changes
    branch_editor.pending_changes["dependencies"] = [dep]

    # Select and remove
    branch_editor.dependencies_list.setCurrentRow(0)
    branch_editor._on_remove_dependency()

    # Pending changes should have empty dependencies
    assert "dependencies" in branch_editor.pending_changes
    assert len(branch_editor.pending_changes["dependencies"]) == 0


def test_branch_editor_update_probabilities_with_invalid_worlds(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test update probabilities when worlds are invalid."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Set invalid weight
    weight_item = branch_editor.worlds_table.item(0, 2)
    if weight_item is not None:
        weight_item.setText("invalid")

    # Update probabilities should handle None from get_worlds
    branch_editor._update_probabilities()  # Should not crash


def test_branch_editor_load_branch_not_in_persistent(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test loading a branch that is not in persistent storage."""
    from fluxx.data.models import BranchId

    # Manipulate to create a case where node_map has an entry but
    # persistent_branches doesn't - this is an edge case
    controller.new_project("Test")

    # Load a branch with valid format but that doesn't exist
    fake_id = BranchId("nonexistent_branch")
    branch_editor.load_branch(fake_id)

    # Editor should have the ID but nothing loaded
    assert branch_editor.current_branch_id == fake_id


def test_branch_editor_apply_with_no_branch(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test apply when no branch is loaded."""
    # Make some pending changes without loading a branch
    branch_editor.pending_changes["title"] = "New Title"

    # Apply should do nothing
    branch_editor._on_apply()

    # Pending changes should still be there
    assert "title" in branch_editor.pending_changes


def test_branch_editor_finish_dependency_editing_with_pending_deps(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test finishing dependency editing when there are already pending dependencies."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import ConstraintType, Dependency, Endpoint, Triangular

    # Create two tasks
    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=generate_possible_world_id(), title="Option A", weight=1.0)
        ],
    )
    branch_editor.load_branch(branch_id)

    # Pre-populate pending_changes with a dependency
    existing_dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    branch_editor.pending_changes["dependencies"] = [existing_dep]

    # Start adding a new dependency
    branch_editor._on_add_dependency()

    # Set up dependency editor with a complete dependency
    branch_editor.dependency_editor.set_target_node(task2_id)
    # Branch editor doesn't have source_endpoint_combo (always OCCURRENCE)
    branch_editor.dependency_editor.target_endpoint_combo.setCurrentIndex(1)  # END
    branch_editor.dependency_editor.constraint_type_combo.setCurrentIndex(0)  # >=

    # Finish editing
    branch_editor.finish_dependency_editing()

    # Should now have 2 dependencies
    assert "dependencies" in branch_editor.pending_changes
    assert len(branch_editor.pending_changes["dependencies"]) == 2


def test_branch_editor_finish_dependency_with_complete_dependency_no_branch(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test finish dependency editing with complete dependency but no branch."""
    from fluxx.data.models import Triangular

    # Create a task for the dependency
    task_id = controller.create_task(
        title="Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # DON'T load a branch, but set up dependency editor with complete dependency
    branch_editor.dependency_editor.set_target_node(task_id)
    # Branch editor doesn't have source_endpoint_combo (always OCCURRENCE)
    branch_editor.dependency_editor.target_endpoint_combo.setCurrentIndex(1)  # END
    branch_editor.dependency_editor.constraint_type_combo.setCurrentIndex(0)  # >=

    # Finish editing - should early return due to no branch
    branch_editor.finish_dependency_editing()

    # No pending changes should be created
    assert "dependencies" not in branch_editor.pending_changes


def test_branch_editor_resolution_combo_initialization(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test that resolution combo is initialized correctly when loading a branch."""
    from fluxx.data.id_generation import generate_possible_world_id

    pw1_id = generate_possible_world_id()
    pw2_id = generate_possible_world_id()

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=pw1_id, title="Option A", weight=1.0),
            PossibleWorld(id=pw2_id, title="Option B", weight=2.0),
        ],
    )
    branch_editor.load_branch(branch_id)

    # Resolution combo should have 3 items: "Not resolved" + 2 worlds
    assert branch_editor.resolution_combo.count() == 3
    assert branch_editor.resolution_combo.itemText(0) == "Not resolved"
    assert branch_editor.resolution_combo.itemText(1) == "Option A"
    assert branch_editor.resolution_combo.itemText(2) == "Option B"

    # Should be set to "Not resolved" initially
    assert branch_editor.resolution_combo.currentIndex() == 0


def test_branch_editor_resolution_change_creates_pending_change(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test that changing resolution creates a pending change."""
    from fluxx.data.id_generation import generate_possible_world_id

    pw1_id = generate_possible_world_id()
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=pw1_id, title="Option A", weight=1.0),
        ],
    )
    branch_editor.load_branch(branch_id)

    # Change resolution to Option A
    branch_editor.resolution_combo.setCurrentIndex(1)

    # Should have pending change
    assert "chosen_world_id" in branch_editor.pending_changes
    assert branch_editor.pending_changes["chosen_world_id"] == pw1_id
    assert branch_editor.is_dirty()


def test_branch_editor_resolution_clear_creates_pending_change(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test that clearing resolution (setting to None) creates a pending change."""
    from fluxx.data.id_generation import generate_possible_world_id

    pw1_id = generate_possible_world_id()
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=pw1_id, title="Option A", weight=1.0),
        ],
    )

    # Resolve the branch first
    controller.update_branch(branch_id, chosen_world_id=pw1_id)

    branch_editor.load_branch(branch_id)

    # Resolution should be set to Option A
    assert branch_editor.resolution_combo.currentIndex() == 1

    # Clear resolution
    branch_editor.resolution_combo.setCurrentIndex(0)

    # Should have pending change with None
    assert "chosen_world_id" in branch_editor.pending_changes
    assert branch_editor.pending_changes["chosen_world_id"] is None


def test_branch_editor_resolution_apply(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test applying resolution changes."""
    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import NodeId

    pw1_id = generate_possible_world_id()
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=pw1_id, title="Option A", weight=1.0),
        ],
    )
    branch_editor.load_branch(branch_id)

    # Change resolution
    branch_editor.resolution_combo.setCurrentIndex(1)

    # Apply changes
    branch_editor._on_apply()

    # Verify change was applied
    project = controller.get_project()
    node_id: NodeId = branch_id
    persistent_id = project.dag.node_map[node_id]
    branch = project.persistent_branches[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert branch.chosen_world_id == pw1_id

    # Pending changes should be cleared
    assert not branch_editor.is_dirty()


def test_branch_editor_resolution_loads_resolved_branch(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test loading a branch that is already resolved."""
    from fluxx.data.id_generation import generate_possible_world_id

    pw1_id = generate_possible_world_id()
    pw2_id = generate_possible_world_id()
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=pw1_id, title="Option A", weight=1.0),
            PossibleWorld(id=pw2_id, title="Option B", weight=2.0),
        ],
    )

    # Resolve to Option B
    controller.update_branch(branch_id, chosen_world_id=pw2_id)

    branch_editor.load_branch(branch_id)

    # Resolution combo should be set to Option B (index 2)
    assert branch_editor.resolution_combo.currentIndex() == 2


def test_branch_editor_resolution_combo_updates_with_world_changes(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test that resolution combo updates when possible worlds are modified."""
    from fluxx.data.id_generation import generate_possible_world_id

    pw1_id = generate_possible_world_id()
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(id=pw1_id, title="Option A", weight=1.0),
        ],
    )
    branch_editor.load_branch(branch_id)

    # Add a new world via the table
    branch_editor._on_add_world()

    # Resolution combo should now have 4 items: "Not resolved" + 2 worlds
    assert branch_editor.resolution_combo.count() == 3
    assert branch_editor.resolution_combo.itemText(2) == "New World"


def test_branch_editor_resolution_invalid_index(
    branch_editor: BranchEditor, controller: ProjectController
) -> None:
    """Test that invalid resolution index is handled gracefully."""
    from fluxx.data.id_generation import generate_possible_world_id

    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(
                id=generate_possible_world_id(), title="Option A", weight=1.0
            ),
        ],
    )
    branch_editor.load_branch(branch_id)

    # Call handler with invalid index
    branch_editor._on_resolution_changed(-1)
    branch_editor._on_resolution_changed(999)

    # Should not crash and no pending change
    assert "chosen_world_id" not in branch_editor.pending_changes
