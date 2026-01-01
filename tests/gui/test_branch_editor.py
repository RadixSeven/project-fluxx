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
