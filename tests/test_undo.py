"""Tests for undo/redo operations."""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest

from fluxx.data import (
    UndoError,
    add_branch,
    add_dependency,
    add_task,
    can_redo,
    can_undo,
    redo,
    undo,
    update_task,
)
from fluxx.data.models import (
    DAG,
    ConstraintType,
    DAGId,
    DAGVersionId,
    Dependency,
    Endpoint,
    PossibleWorld,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    Triangular,
    Worker,
    WorkerId,
)


@pytest.fixture
def empty_project() -> Generator[Project]:
    """Create an empty project for testing."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test Project",
        created=now,
        last_modified=now,
    )
    dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))
    worker = Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0)

    yield Project(
        metadata=metadata,
        dag=dag,
        workers=[worker],
    )


def test_undo_single_operation(empty_project: Project) -> None:
    """Test undoing a single operation."""
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Verify task exists
    assert task_id in project.dag.node_map

    # Undo
    undone_project = undo(project)

    # Task should no longer exist in current version
    assert task_id not in undone_project.dag.node_map
    # Should be back to empty state
    assert len(undone_project.dag.node_map) == 0
    assert undone_project.current_event_id is None


def test_undo_multiple_operations(empty_project: Project) -> None:
    """Test undoing multiple operations."""
    # Add three tasks
    project = empty_project
    for i in range(3):
        project, _ = add_task(
            project,
            title=f"Task {i}",
            description="Test",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        )

    # Undo once
    project = undo(project)
    # Should have 2 tasks
    assert len(project.dag.node_map) == 2

    # Undo again
    project = undo(project)
    # Should have 1 task
    assert len(project.dag.node_map) == 1

    # Undo once more
    project = undo(project)
    # Should be back to empty
    assert len(project.dag.node_map) == 0
    assert project.current_event_id is None


def test_undo_at_initial_state_raises_error(empty_project: Project) -> None:
    """Test that undoing at initial state raises error."""
    with pytest.raises(UndoError, match="Nothing to undo"):
        undo(empty_project)


def test_undo_preserves_history(empty_project: Project) -> None:
    """Test that undo preserves event history."""
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    events_before = len(project.history_events)

    # Undo
    undone_project = undo(project)

    # History should be preserved (not deleted)
    assert len(undone_project.history_events) == events_before


def test_redo_single_operation(empty_project: Project) -> None:
    """Test redoing a single operation."""
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    version_with_task = project.dag.current_version_id

    # Undo
    project = undo(project)
    assert task_id not in project.dag.node_map

    # Redo
    redone_project = redo(project)

    # Task should exist again
    assert task_id in redone_project.dag.node_map
    assert redone_project.dag.current_version_id == version_with_task


def test_redo_multiple_operations(empty_project: Project) -> None:
    """Test redoing multiple operations."""
    # Add three tasks
    project = empty_project
    task_ids = []
    for i in range(3):
        project, task_id = add_task(
            project,
            title=f"Task {i}",
            description="Test",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        )
        task_ids.append(task_id)

    # Undo all three
    project = undo(project)
    project = undo(project)
    project = undo(project)
    assert len(project.dag.node_map) == 0

    # Redo all three
    project = redo(project)
    assert len(project.dag.node_map) == 1
    project = redo(project)
    assert len(project.dag.node_map) == 2
    project = redo(project)
    assert len(project.dag.node_map) == 3


def test_redo_when_nothing_to_redo_raises_error(empty_project: Project) -> None:
    """Test that redoing when there's nothing to redo raises error."""
    # Add and undo a task
    project, _ = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Can't redo without undoing first
    with pytest.raises(UndoError, match="Nothing to redo"):
        redo(project)


def test_redo_after_new_operation_uses_last_child(empty_project: Project) -> None:
    """Test that redo uses the most recent child when there are branches."""
    # Add first task
    project, task1_id = add_task(
        empty_project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Undo
    project = undo(project)

    # Add different task (creates a branch in history)
    project, task2_id = add_task(
        project,
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Now there are two children of the initial state
    # Undo to go back to initial state
    project = undo(project)

    # Redo should use the most recent child (Task 2)
    redone_project = redo(project)
    assert task2_id in redone_project.dag.node_map


def test_can_undo_returns_true_when_undo_available(empty_project: Project) -> None:
    """Test that can_undo returns True when undo is available."""
    # Initially cannot undo
    assert can_undo(empty_project) is False

    # Add a task
    project, _ = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Now can undo
    assert can_undo(project) is True


def test_can_undo_returns_false_after_undo_to_initial(empty_project: Project) -> None:
    """Test that can_undo returns False after undoing to initial state."""
    # Add a task
    project, _ = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Undo
    project = undo(project)

    # Cannot undo anymore
    assert can_undo(project) is False


def test_can_redo_returns_true_after_undo(empty_project: Project) -> None:
    """Test that can_redo returns True after undo."""
    # Initially cannot redo
    assert can_redo(empty_project) is False

    # Add a task
    project, _ = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Still cannot redo
    assert can_redo(project) is False

    # Undo
    project = undo(project)

    # Now can redo
    assert can_redo(project) is True


def test_can_redo_returns_false_after_redo(empty_project: Project) -> None:
    """Test that can_redo returns False after redoing everything."""
    # Add a task
    project, _ = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Undo
    project = undo(project)
    assert can_redo(project) is True

    # Redo
    project = redo(project)

    # Cannot redo anymore
    assert can_redo(project) is False


def test_undo_redo_cycle_preserves_data(empty_project: Project) -> None:
    """Test that undo/redo cycle preserves all data correctly."""
    # Add a task with specific properties
    project, task_id = add_task(
        empty_project,
        title="Important Task",
        description="Very important",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[WorkerId("w1")],
    )

    # Get the original task
    persistent_id = project.dag.node_map[task_id]
    original_task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]

    # Undo and redo
    project = undo(project)
    project = redo(project)

    # Get the task after redo
    redone_task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]

    # Should be identical
    assert redone_task.title == original_task.title
    assert redone_task.description == original_task.description
    assert redone_task.duration_distribution == original_task.duration_distribution
    assert redone_task.allowed_workers == original_task.allowed_workers


def test_undo_update_operation(empty_project: Project) -> None:
    """Test undoing an update operation."""
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Original Title",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Update the task
    project = update_task(project, task_id, title="Updated Title")

    # Get the updated task
    persistent_id = project.dag.node_map[task_id]
    updated_task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert updated_task.title == "Updated Title"

    # Undo the update
    project = undo(project)

    # Should be back to original title
    original_task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert original_task.title == "Original Title"


def test_undo_dependency_operation(empty_project: Project) -> None:
    """Test undoing a dependency addition."""
    # Add two tasks
    project, task1_id = add_task(
        empty_project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    project, task2_id = add_task(
        project,
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, task1_id, dep)

    # Verify dependency exists
    persistent_id = project.dag.node_map[task1_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert dep in task.dependencies

    # Undo
    project = undo(project)

    # Dependency should be gone
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert dep not in task.dependencies


def test_undo_with_branches_and_tasks(empty_project: Project) -> None:
    """Test undo/redo with both branches and tasks."""
    # Add a branch
    project, branch_id = add_branch(
        empty_project,
        title="Branch",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Add a task
    project, task_id = add_task(
        project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Should have both
    assert branch_id in project.dag.node_map
    assert task_id in project.dag.node_map

    # Undo task addition
    project = undo(project)
    assert branch_id in project.dag.node_map
    assert task_id not in project.dag.node_map

    # Undo branch addition
    project = undo(project)
    assert branch_id not in project.dag.node_map

    # Redo branch
    project = redo(project)
    assert branch_id in project.dag.node_map
    assert task_id not in project.dag.node_map

    # Redo task
    project = redo(project)
    assert branch_id in project.dag.node_map
    assert task_id in project.dag.node_map
