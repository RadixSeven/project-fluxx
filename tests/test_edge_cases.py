"""Tests for edge cases to achieve 100% coverage."""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest

from fluxx.data import (
    DAGOperationError,
    UndoError,
    add_branch,
    add_dependency,
    add_task,
    remove_dependency,
    undo,
    update_branch,
    update_task,
)
from fluxx.data.models import (
    DAG,
    ConstraintType,
    DAGId,
    DAGVersionId,
    Dependency,
    DoneCompletion,
    Endpoint,
    PossibleWorld,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    StartedCompletion,
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


def test_add_task_after_undo_to_initial(empty_project: Project) -> None:
    """Test adding a task after undoing to initial state.

    This tests the code path where current_version_id doesn't exist
    in persistent object versions (lines 90-92, 116-118 in dag_operations.py).
    """
    # Add a task
    project, task1_id = add_task(
        empty_project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add a branch to test line 117-118 (branch doesn't exist in initial version)
    project, branch1_id = add_branch(
        project,
        title="Branch 1",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Undo to initial state
    project = undo(project)
    project = undo(project)
    assert len(project.dag.node_map) == 0

    # Add a new task (current_version_id won't exist in the old task's and
    # branch's versions). This should hit both lines 90-92 (skipping task1)
    # and 117-118 (skipping branch1)
    project, task2_id = add_task(
        project,
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Should succeed
    assert task2_id in project.dag.node_map
    assert len(project.dag.node_map) == 1


def test_add_branch_after_undo_to_initial(empty_project: Project) -> None:
    """Test adding a branch after undoing to initial state.

    This tests the code path where current_version_id doesn't exist
    in persistent object versions (lines 220-222, 232-234 in dag_operations.py).
    """
    # Add a task first to test line 221-222 (task doesn't exist in initial version)
    project, task1_id = add_task(
        empty_project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add a branch
    project, branch1_id = add_branch(
        project,
        title="Branch 1",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Undo to initial state
    project = undo(project)
    project = undo(project)
    assert len(project.dag.node_map) == 0

    # Add a new branch (current_version_id won't exist in the old task's
    # and branch's versions). This should hit both lines 221-222 (skipping
    # task1) and later lines for branches
    project, branch2_id = add_branch(
        project,
        title="Branch 2",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
    )

    # Should succeed
    assert branch2_id in project.dag.node_map
    assert len(project.dag.node_map) == 1


def test_add_dependency_after_undo_to_initial(empty_project: Project) -> None:
    """Test adding a dependency after undoing, creating new branch in history.

    This tests the code path where current_version_id doesn't exist
    in persistent object versions (lines 335-337, 356-358 in dag_operations.py).
    """
    # Add task1 (version v1)
    project, task1_id = add_task(
        empty_project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    version_with_task1 = project.dag.current_version_id

    # Add task2 (version v2)
    project, task2_id = add_task(
        project,
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add a branch (version v3)
    project, branch1_id = add_branch(
        project,
        title="Branch 1",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Undo back to v1 (only task1 exists)
    project = undo(project)
    project = undo(project)
    assert project.dag.current_version_id == version_with_task1

    # Now add task3 (creates v4 from v1)
    # At this point, task2 and branch1 exist in persistent storage but not in v1
    project, task3_id = add_task(
        project,
        title="Task 3",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency from task1 to task3
    # This should hit lines 336-337 (skipping task2) and 356-358 (skipping branch1)
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=task3_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, task1_id, dep)

    # Should succeed
    persistent_id = project.dag.node_map[task1_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert dep in task.dependencies


def test_update_task_after_undo_to_initial(empty_project: Project) -> None:
    """Test updating a task after undoing, creating new branch in history.

    This tests the code path where current_version_id doesn't exist
    in persistent object versions (lines 495-496, 512-519 in dag_operations.py).
    """
    # Add task1 (version v1)
    project, task1_id = add_task(
        empty_project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    version_with_task1 = project.dag.current_version_id

    # Add task2 (version v2)
    project, task2_id = add_task(
        project,
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add a branch (version v3)
    project, branch1_id = add_branch(
        project,
        title="Branch 1",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Undo back to v1 (only task1 exists)
    project = undo(project)
    project = undo(project)
    assert project.dag.current_version_id == version_with_task1

    # Update task1 (creates new version from v1)
    # At this point, task2 and branch1 exist in persistent storage but not in v1
    # This should hit lines 495-496 (skipping task2) and 512-519 (skipping branch1)
    project = update_task(project, task1_id, title="Updated")

    # Should succeed
    persistent_id = project.dag.node_map[task1_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert task.title == "Updated"


def test_update_task_with_no_updates_returns_unchanged(empty_project: Project) -> None:
    """Test that update_task with no changes returns the same project.

    This covers the early return path (line 457 in dag_operations.py).
    """
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    initial_version = project.dag.current_version_id

    # Update with no changes
    updated_project = update_task(project, task_id)

    # Should return unchanged
    assert updated_project is project
    assert updated_project.dag.current_version_id == initial_version


def test_update_task_with_existing_branches(empty_project: Project) -> None:
    """Test updating a task when branches exist in current version.

    This covers lines 516-519 in dag_operations.py (normal branch copy path).
    """
    # Add a branch
    project, branch_id = add_branch(
        empty_project,
        title="Branch 1",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Add a task
    project, task_id = add_task(
        project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Update the task (branch exists in current version, should be copied normally)
    project = update_task(project, task_id, title="Updated Task")

    # Verify update succeeded and branch still exists
    assert task_id in project.dag.node_map
    assert branch_id in project.dag.node_map
    persistent_id = project.dag.node_map[task_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert task.title == "Updated Task"


def test_update_task_individual_fields(empty_project: Project) -> None:
    """Test updating individual task fields to cover all update paths."""
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Original",
        description="Old",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Update just description (line 474)
    project = update_task(project, task_id, description="New description")
    persistent_id = project.dag.node_map[task_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert task.description == "New description"

    # Update just duration (line 476)
    new_dist = Triangular(min=5.0, mode=10.0, max=15.0)
    project = update_task(project, task_id, duration_distribution=new_dist)
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert task.duration_distribution == new_dist

    # Update just allowed_workers (line 478)
    project = update_task(project, task_id, allowed_workers=[WorkerId("w1")])
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert task.allowed_workers == [WorkerId("w1")]


def test_update_branch_after_undo_to_initial(empty_project: Project) -> None:
    """Test updating a branch after undoing, creating new branch in history.

    This tests the code path where current_version_id doesn't exist
    in persistent object versions (lines 625-632, 684-685 in dag_operations.py).
    """
    # Add branch1 (version v1)
    project, branch1_id = add_branch(
        empty_project,
        title="Branch 1",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )
    version_with_branch1 = project.dag.current_version_id

    # Add a task (version v2)
    project, task1_id = add_task(
        project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add branch2 (version v3)
    project, branch2_id = add_branch(
        project,
        title="Branch 2",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
    )

    # Undo back to v1 (only branch1 exists)
    project = undo(project)
    project = undo(project)
    assert project.dag.current_version_id == version_with_branch1

    # Update branch1 (creates new version from v1)
    # At this point, task1 and branch2 exist in persistent storage but not
    # in v1. This should hit lines 625-632 (skipping task1 and branch2)
    # and 684-685 (skipping task1)
    project = update_branch(project, branch1_id, title="Updated")

    # Should succeed
    persistent_id = project.dag.node_map[branch1_id]
    branch = project.persistent_branches[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert branch.title == "Updated"


def test_update_branch_with_no_updates_returns_unchanged(
    empty_project: Project,
) -> None:
    """Test that update_branch with no changes returns the same project.

    This covers the early return path (line 596 in dag_operations.py).
    """
    # Add a branch
    project, branch_id = add_branch(
        empty_project,
        title="Branch",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    initial_version = project.dag.current_version_id

    # Update with no changes
    updated_project = update_branch(project, branch_id)

    # Should return unchanged
    assert updated_project is project
    assert updated_project.dag.current_version_id == initial_version


def test_update_branch_with_existing_tasks_and_branches(
    empty_project: Project,
) -> None:
    """Test updating a branch when tasks and other branches exist in current version.

    This covers lines 629-632, 648, 689-690 in dag_operations.py (normal copy paths).
    """
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add branch1
    project, branch1_id = add_branch(
        project,
        title="Branch 1",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Add branch2
    project, branch2_id = add_branch(
        project,
        title="Branch 2",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
    )

    # Update branch1 (task and branch2 exist in current version, should be
    # copied normally). This should hit lines 629-632 (copying task), 648
    # (copying non-updated branch2), 689-690 (copying task again)
    project = update_branch(project, branch1_id, title="Updated Branch")

    # Verify update succeeded and all nodes still exist
    assert task_id in project.dag.node_map
    assert branch1_id in project.dag.node_map
    assert branch2_id in project.dag.node_map
    persistent_id = project.dag.node_map[branch1_id]
    branch = project.persistent_branches[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert branch.title == "Updated Branch"


def test_update_branch_individual_fields(empty_project: Project) -> None:
    """Test updating individual branch fields to cover all update paths."""
    # Add a branch
    project, branch_id = add_branch(
        empty_project,
        title="Original",
        description="Old",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Update just description (line 607)
    project = update_branch(project, branch_id, description="New description")
    persistent_id = project.dag.node_map[branch_id]
    branch = project.persistent_branches[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert branch.description == "New description"


def test_remove_dependency_after_undo_to_initial(empty_project: Project) -> None:
    """Test removing a dependency after undoing, creating new branch in history.

    This tests the code path where current_version_id doesn't exist
    in persistent object versions (lines 724-725, 744-745 in dag_operations.py).
    """
    # Add task1 and task2 with dependency (version v1, v2)
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

    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, task1_id, dep)
    version_with_dep = project.dag.current_version_id

    # Add task3 (version v4)
    project, task3_id = add_task(
        project,
        title="Task 3",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add a branch (version v5)
    project, branch1_id = add_branch(
        project,
        title="Branch 1",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Undo back to version with dependency (task1 and task2 with dep exist)
    project = undo(project)
    project = undo(project)
    assert project.dag.current_version_id == version_with_dep

    # Remove dependency (creates new version from v3)
    # At this point, task3 and branch1 exist in persistent storage but not in v3
    # This should hit lines 724-725 (skipping task3) and 744-745 (skipping branch1)
    project = remove_dependency(project, task1_id, dep)

    # Should succeed
    persistent_id = project.dag.node_map[task1_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert dep not in task.dependencies


def test_update_task_is_not_task(empty_project: Project) -> None:
    """Test error when trying to update a branch as a task.

    This covers the error path (line 643 in dag_operations.py).
    """
    # Add a branch
    project, branch_id = add_branch(
        empty_project,
        title="Branch",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Try to update it as a task
    from fluxx.data.models import TaskId

    with pytest.raises(DAGOperationError, match="is not a task"):
        update_task(project, TaskId(branch_id), title="New Title")


def test_update_branch_is_not_branch(empty_project: Project) -> None:
    """Test error when trying to update a task as a branch.

    This covers the error path (line 758 in dag_operations.py).
    """
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Try to update it as a branch
    from fluxx.data.models import BranchId

    with pytest.raises(DAGOperationError, match="is not a branch"):
        update_branch(project, BranchId(task_id), title="New Title")


def test_undo_with_corrupted_event_history(empty_project: Project) -> None:
    """Test undo with corrupted event history.

    This covers error paths in undo.py (lines 35, 60, 83).
    """
    # Add a task
    project, _ = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Corrupt the project by setting current_event_id to non-existent event
    corrupted_project = project.model_copy(
        update={"current_event_id": "nonexistent_event"}
    )

    # Should raise error (line 35)
    with pytest.raises(UndoError, match="not found in history"):
        undo(corrupted_project)

    # Corrupt by removing an event from history while keeping reference
    corrupted_project2 = project.model_copy(update={"history_events": []})

    # Should raise error (line 35)
    with pytest.raises(UndoError, match="not found in history"):
        undo(corrupted_project2)

    # Test parent event not found (line 83)
    # Create a project with an event that references a non-existent parent
    from fluxx.data.id_generation import generate_event_id
    from fluxx.data.models import DAGEvent, EventId, EventType

    bad_event = DAGEvent(
        id=generate_event_id(),
        timestamp=datetime.now(UTC),
        parent_event_id=EventId("nonexistent_parent"),
        event_type=EventType.NODE_CREATED,
        affected_nodes=[],
        resulting_dag_version=project.dag.current_version_id,
    )

    corrupted_project3 = project.model_copy(
        update={
            "history_events": project.history_events + [bad_event],
            "current_event_id": bad_event.id,
        }
    )

    # Should raise error (line 83)
    with pytest.raises(UndoError, match="Parent event.*not found"):
        undo(corrupted_project3)


def test_undo_with_pre_event_versions(empty_project: Project) -> None:
    """Test undo to initial state when pre-event versions exist.

    This covers the normal path (line 60 in undo.py).
    """
    # Add a task
    project, _ = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Manually add an initial version to persistent objects
    # to simulate having a pre-event version
    from fluxx.data.models import PersistentTask

    initial_version_id = DAGVersionId("v_initial")
    new_persistent_tasks = {}
    for pid, ptask in project.persistent_tasks.items():
        # Add an initial version that doesn't correspond to any event
        task = ptask.versions[list(ptask.versions.keys())[0]]
        new_versions = dict(ptask.versions)
        new_versions[initial_version_id] = task.model_copy()
        new_persistent_tasks[pid] = PersistentTask(id=pid, versions=new_versions)

    modified_project = project.model_copy(
        update={"persistent_tasks": new_persistent_tasks}
    )

    # Undo should use the pre-event version (line 60)
    undone = undo(modified_project)
    assert undone.current_event_id is None
    assert undone.dag.current_version_id == initial_version_id
    assert len(undone.dag.node_map) == 0


def test_undo_with_no_pre_event_versions(empty_project: Project) -> None:
    """Test undo to initial state when no pre-event versions exist.

    This covers the fallback path (line 64 in undo.py).
    """
    # This is a bit tricky - we need a situation where there are events
    # but no versions that exist before those events
    # This should rarely happen in practice, but we test the fallback

    # Add a task
    project, _ = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Manually clean up any initial versions from persistent objects
    # to simulate the case where no pre-event versions exist
    new_persistent_tasks = {}
    for pid, ptask in project.persistent_tasks.items():
        # Keep only the version from the event
        event_version = project.history_events[0].resulting_dag_version
        if event_version in ptask.versions:
            from fluxx.data.models import PersistentTask

            new_persistent_tasks[pid] = PersistentTask(
                id=pid, versions={event_version: ptask.versions[event_version]}
            )

    corrupted_project = project.model_copy(
        update={"persistent_tasks": new_persistent_tasks}
    )

    # Undo should still work, using the fallback initial version
    undone = undo(corrupted_project)
    assert undone.current_event_id is None
    assert len(undone.dag.node_map) == 0


def test_update_task_with_multiple_tasks(empty_project: Project) -> None:
    """Test updating one task when multiple tasks exist.

    This covers the else branch (line 505) where we copy unchanged tasks.
    """
    # Add multiple tasks
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
    project, task3_id = add_task(
        project,
        title="Task 3",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Update only task2
    project = update_task(project, task2_id, title="Updated Task 2")

    # Task 2 should be updated
    persistent_id2 = project.dag.node_map[task2_id]
    task2 = project.persistent_tasks[persistent_id2].versions[
        project.dag.current_version_id
    ]
    assert task2.title == "Updated Task 2"

    # Task 1 and Task 3 should be unchanged
    persistent_id1 = project.dag.node_map[task1_id]
    task1 = project.persistent_tasks[persistent_id1].versions[
        project.dag.current_version_id
    ]
    assert task1.title == "Task 1"

    persistent_id3 = project.dag.node_map[task3_id]
    task3 = project.persistent_tasks[persistent_id3].versions[
        project.dag.current_version_id
    ]
    assert task3.title == "Task 3"


def test_update_task_excluded_worker_tasks(empty_project: Project) -> None:
    """Test updating excluded_worker_tasks field.

    This covers lines that update specific optional fields.
    """
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

    # Add required dependency: task1.start >= task2.start
    # This is required for excluded_worker_tasks validation
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, task1_id, dep)

    # Update task1's excluded_worker_tasks
    project = update_task(project, task1_id, excluded_worker_tasks=[task2_id])

    # Verify
    persistent_id = project.dag.node_map[task1_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert task.excluded_worker_tasks == [task2_id]


def test_update_task_completion(
    empty_project: Project,
) -> None:
    """Test updating task completion field.

    This covers completion state update paths.
    """
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    start_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

    # Update to started completion
    project = update_task(
        project,
        task_id,
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_time,
            hours_logged=2.0,
        ),
    )
    persistent_id = project.dag.node_map[task_id]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert isinstance(task.completion, StartedCompletion)
    assert task.completion.assignee == WorkerId("w1")
    assert task.completion.hours_logged == 2.0

    # Update to done completion
    end_time = datetime(2024, 1, 15, 18, 0, 0, tzinfo=UTC)
    project = update_task(
        project,
        task_id,
        completion=DoneCompletion(
            assignee=WorkerId("w1"),
            start_time=start_time,
            hours_logged=5.0,
            end_time=end_time,
        ),
    )
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert isinstance(task.completion, DoneCompletion)
    assert task.completion.hours_logged == 5.0


def test_remove_dependency_with_multiple_branches(empty_project: Project) -> None:
    """Test removing a dependency from one branch while another branch exists.

    This covers line 763 in dag_operations.py (copying non-modified branches).
    """
    # Add branch1 and branch2
    project, branch1_id = add_branch(
        empty_project,
        title="Branch 1",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )
    project, branch2_id = add_branch(
        project,
        title="Branch 2",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
    )

    # Add a task
    project, task_id = add_task(
        project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency from branch1 to task
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=task_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, branch1_id, dep)

    # Remove dependency from branch1 (branch2 exists and should be copied via line 763)
    project = remove_dependency(project, branch1_id, dep)

    # Verify dependency removed and both branches still exist
    assert branch1_id in project.dag.node_map
    assert branch2_id in project.dag.node_map
    persistent_id = project.dag.node_map[branch1_id]
    branch = project.persistent_branches[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert dep not in branch.dependencies


def test_remove_dependency_validation_failure(empty_project: Project) -> None:
    """Test that remove_dependency validates the result.

    This covers the validation error path (lines 799-800).
    """
    # Add two simple tasks with a dependency
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

    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, task1_id, dep)

    # Now manually corrupt the project to make remove_dependency create
    # an invalid state. We'll corrupt task1 so it has invalid worker constraints.

    # Get the current version's task
    persistent_id = project.dag.node_map[task1_id]
    task1 = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]

    # Manually create a corrupted version where task1 has invalid worker constraints
    from fluxx.data.models import PersistentTask

    corrupted_task = task1.model_copy(
        update={"allowed_workers": [WorkerId("nonexistent_worker")]}
    )

    new_versions = dict(project.persistent_tasks[persistent_id].versions)
    new_versions[project.dag.current_version_id] = corrupted_task

    corrupted_project = project.model_copy(
        update={
            "persistent_tasks": {
                **project.persistent_tasks,
                persistent_id: PersistentTask(id=persistent_id, versions=new_versions),
            }
        }
    )

    # Now try to remove the dependency - validation should fail due to corrupted task
    with pytest.raises(DAGOperationError, match="Failed to remove dependency"):
        remove_dependency(corrupted_project, task1_id, dep)
