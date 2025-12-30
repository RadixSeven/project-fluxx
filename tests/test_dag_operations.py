"""Tests for DAG operations."""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest

from fluxx.data import (
    DAGOperationError,
    add_branch,
    add_dependency,
    add_task,
    generate_persistent_object_id,
    generate_task_id,
    remove_dependency,
    update_branch,
    update_task,
)
from fluxx.data.models import (
    DAG,
    Branch,
    BranchId,
    ConstraintType,
    DAGId,
    DAGVersionId,
    Dependency,
    Endpoint,
    EventType,
    NodeId,
    PossibleWorld,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    TaskId,
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


def test_add_task_creates_new_version(empty_project: Project) -> None:
    """Test that adding a task creates a new DAG version."""
    initial_version = empty_project.dag.current_version_id

    updated_project, task_id = add_task(
        empty_project,
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Version should change
    assert updated_project.dag.current_version_id != initial_version

    # Task should be in node map
    assert NodeId(task_id) in updated_project.dag.node_map

    # Event should be recorded
    assert len(updated_project.history_events) == 1
    event = updated_project.history_events[0]
    assert event.event_type == EventType.NODE_CREATED
    assert NodeId(task_id) in event.affected_nodes

    # Metadata last_modified should be updated
    assert updated_project.metadata.last_modified > empty_project.metadata.last_modified


def test_add_task_with_parent(empty_project: Project) -> None:
    """Test adding a task with a parent."""
    # Add parent task first (needs duration since it has no children yet)
    project_with_parent, parent_id = add_task(
        empty_project,
        title="Parent",
        description="Parent task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add child task
    updated_project, child_id = add_task(
        project_with_parent,
        title="Child",
        description="Child task",
        parent_id=parent_id,
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Get the parent task from the new version
    parent_persistent_id = updated_project.dag.node_map[NodeId(parent_id)]
    parent_task = updated_project.persistent_tasks[parent_persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Parent should list child
    assert child_id in parent_task.children
    # Parent still has duration (preserved but ignored)
    assert parent_task.duration_distribution == Triangular(min=1.0, mode=2.0, max=3.0)

    # Get the child task
    child_persistent_id = updated_project.dag.node_map[NodeId(child_id)]
    child_task = updated_project.persistent_tasks[child_persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Child should reference parent
    assert child_task.parent_id == parent_id


def test_add_task_with_allowed_workers(empty_project: Project) -> None:
    """Test adding a task with worker constraints."""
    updated_project, task_id = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[WorkerId("w1")],
    )

    # Get the task
    persistent_id = updated_project.dag.node_map[NodeId(task_id)]
    task = updated_project.persistent_tasks[persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    assert task.allowed_workers == [WorkerId("w1")]


def test_add_task_validation_failure(empty_project: Project) -> None:
    """Test that adding an invalid task raises error."""
    # Try to add task with non-existent worker
    with pytest.raises(DAGOperationError, match="Failed to add task"):
        add_task(
            empty_project,
            title="Task",
            description="Test",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
            allowed_workers=[WorkerId("nonexistent")],
        )


def test_add_branch_creates_new_version(empty_project: Project) -> None:
    """Test that adding a branch creates a new DAG version."""
    initial_version = empty_project.dag.current_version_id

    updated_project, branch_id = add_branch(
        empty_project,
        title="Branch 1",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
    )

    # Version should change
    assert updated_project.dag.current_version_id != initial_version

    # Branch should be in node map
    assert NodeId(branch_id) in updated_project.dag.node_map

    # Event should be recorded
    assert len(updated_project.history_events) == 1
    event = updated_project.history_events[0]
    assert event.event_type == EventType.NODE_CREATED
    assert NodeId(branch_id) in event.affected_nodes


def test_add_dependency_creates_new_version(empty_project: Project) -> None:
    """Test that adding a dependency creates a new DAG version."""
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

    initial_version = project.dag.current_version_id

    # Add dependency: task1.end >= task2.start
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task2_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    updated_project = add_dependency(project, NodeId(task1_id), dep)

    # Version should change
    assert updated_project.dag.current_version_id != initial_version

    # Task should have the dependency
    persistent_id = updated_project.dag.node_map[NodeId(task1_id)]
    task = updated_project.persistent_tasks[persistent_id].versions[
        updated_project.dag.current_version_id
    ]
    assert dep in task.dependencies

    # Event should be recorded
    last_event = updated_project.history_events[-1]
    assert last_event.event_type == EventType.NODE_MODIFIED
    assert NodeId(task1_id) in last_event.affected_nodes


def test_add_dependency_detects_cycle(empty_project: Project) -> None:
    """Test that adding a dependency that creates a cycle is rejected."""
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

    # Add dependency: task1 -> task2
    dep1 = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task2_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, NodeId(task1_id), dep1)

    # Try to add reverse dependency: task2 -> task1 (creates cycle)
    dep2 = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task1_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    with pytest.raises(DAGOperationError, match="Cycle detected"):
        add_dependency(project, NodeId(task2_id), dep2)


def test_add_dependency_invalid_endpoint(empty_project: Project) -> None:
    """Test that invalid endpoint dependencies are rejected."""
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Try to use OCCURRENCE endpoint on a task (invalid)
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=NodeId(task_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.EQUAL,
    )

    with pytest.raises(DAGOperationError, match="cannot use OCCURRENCE"):
        add_dependency(project, NodeId(task_id), dep)


def test_generate_task_id_is_unique() -> None:
    """Test that generated task IDs are unique."""
    id1 = generate_task_id()
    id2 = generate_task_id()

    assert id1 != id2
    assert str(id1).startswith("task_")
    assert str(id2).startswith("task_")


def test_add_multiple_tasks_creates_versions(empty_project: Project) -> None:
    """Test adding multiple tasks creates proper version history."""
    project = empty_project

    # Add 3 tasks
    for i in range(3):
        project, _ = add_task(
            project,
            title=f"Task {i}",
            description="Test",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        )

    # Should have 3 events
    assert len(project.history_events) == 3

    # Each event should have different resulting_dag_version
    versions = [event.resulting_dag_version for event in project.history_events]
    assert len(set(versions)) == 3  # All unique

    # Current version should be the last one
    assert project.dag.current_version_id == versions[-1]


def test_task_persists_across_versions(empty_project: Project) -> None:
    """Test that tasks from earlier versions are preserved."""
    # Add first task
    project, task1_id = add_task(
        empty_project,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    version1 = project.dag.current_version_id

    # Add second task
    project, task2_id = add_task(
        project,
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    version2 = project.dag.current_version_id

    # Task 1 should exist in both versions
    persistent_id = project.dag.node_map[NodeId(task1_id)]
    persistent_task = project.persistent_tasks[persistent_id]

    assert version1 in persistent_task.versions
    assert version2 in persistent_task.versions

    # Task 1 should be the same in both versions
    task1_v1 = persistent_task.versions[version1]
    task1_v2 = persistent_task.versions[version2]
    assert task1_v1.title == task1_v2.title
    assert task1_v1.description == task1_v2.description


def test_add_task_with_existing_branches(empty_project: Project) -> None:
    """Test adding a task when there are existing branches."""
    # Add a branch first
    project, branch_id = add_branch(
        empty_project,
        title="Branch",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
    )

    # Add a task - should copy branches to new version
    updated_project, task_id = add_task(
        project,
        title="Task",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Both branch and task should exist in the new version
    assert NodeId(branch_id) in updated_project.dag.node_map
    assert NodeId(task_id) in updated_project.dag.node_map


def test_add_branch_with_existing_tasks(empty_project: Project) -> None:
    """Test adding a branch when there are existing tasks."""
    # Add a task first
    project, task_id = add_task(
        empty_project,
        title="Task",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add a branch - should copy tasks to new version
    updated_project, branch_id = add_branch(
        project,
        title="Branch",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
    )

    # Both task and branch should exist in the new version
    assert NodeId(task_id) in updated_project.dag.node_map
    assert NodeId(branch_id) in updated_project.dag.node_map


def test_add_branch_with_existing_branches(empty_project: Project) -> None:
    """Test adding a branch when there are existing branches."""
    # Add first branch
    project, branch1_id = add_branch(
        empty_project,
        title="Branch 1",
        description="First branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Add second branch - should copy first branch to new version
    updated_project, branch2_id = add_branch(
        project,
        title="Branch 2",
        description="Second branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
    )

    # Both branches should exist in the new version
    assert NodeId(branch1_id) in updated_project.dag.node_map
    assert NodeId(branch2_id) in updated_project.dag.node_map


def test_add_dependency_with_nonexistent_source(empty_project: Project) -> None:
    """Test adding dependency from non-existent source node."""
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Try to add dependency from non-existent node
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    with pytest.raises(DAGOperationError, match="Source node.*does not exist"):
        add_dependency(project, NodeId("nonexistent"), dep)


def test_add_dependency_to_branch(empty_project: Project) -> None:
    """Test adding a dependency to a branch."""
    # Add a branch
    project, branch_id = add_branch(
        empty_project,
        title="Branch",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
    )

    # Add a task
    project, task_id = add_task(
        project,
        title="Task",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency from branch to task
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=NodeId(task_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    updated_project = add_dependency(project, NodeId(branch_id), dep)

    # Branch should have the dependency
    persistent_id = updated_project.dag.node_map[NodeId(branch_id)]
    branch = updated_project.persistent_branches[persistent_id].versions[
        updated_project.dag.current_version_id
    ]
    assert dep in branch.dependencies


def test_add_dependency_to_task_with_existing_branches(empty_project: Project) -> None:
    """Test adding a dependency to a task when there are existing branches."""
    # Add a branch
    project, branch_id = add_branch(
        empty_project,
        title="Branch",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Add two tasks
    project, task1_id = add_task(
        project,
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

    # Add dependency between tasks (should copy branch to new version)
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task2_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    updated_project = add_dependency(project, NodeId(task1_id), dep)

    # Branch should still exist in new version
    assert NodeId(branch_id) in updated_project.dag.node_map


def test_add_branch_that_creates_invalid_dag(empty_project: Project) -> None:
    """Test error handling when add_branch creates an invalid DAG state."""
    # First create a valid branch
    project, branch1_id = add_branch(
        empty_project,
        title="Branch 1",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Now manually corrupt the project's persistent_branches to simulate
    # an internal inconsistency that would cause validation to fail
    # We'll create a branch with a cycle that references itself
    from fluxx.data.models import PersistentBranch

    corrupted_branch = Branch(
        id=BranchId("corrupt"),
        title="Corrupt",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
        dependencies=[
            # Self-reference creates a cycle
            Dependency(
                source_endpoint=Endpoint.OCCURRENCE,
                target_node_id=NodeId("corrupt"),
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.EQUAL,
            )
        ],
    )

    persistent_corrupt = PersistentBranch(
        id=generate_persistent_object_id(),
        versions={project.dag.current_version_id: corrupted_branch},
    )

    # Manually inject the corrupted branch into the project
    corrupted_project = Project(
        **project.model_dump(exclude={"persistent_branches", "dag"}),
        dag=project.dag.model_copy(
            update={
                "node_map": {
                    **project.dag.node_map,
                    NodeId("corrupt"): persistent_corrupt.id,
                }
            }
        ),
        persistent_branches={
            **project.persistent_branches,
            persistent_corrupt.id: persistent_corrupt,
        },
    )

    # Try to add another branch - should fail during validation
    with pytest.raises(DAGOperationError, match="Failed to add branch"):
        add_branch(
            corrupted_project,
            title="New Branch",
            description="Test",
            possible_worlds=[
                PossibleWorld(id=PossibleWorldId("pw3"), title="Option C"),
            ],
        )


def test_update_task_title(empty_project: Project) -> None:
    """Test updating a task's title."""
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Original Title",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    initial_version = project.dag.current_version_id

    # Update the title
    updated_project = update_task(project, task_id, title="New Title")

    # Version should change
    assert updated_project.dag.current_version_id != initial_version

    # Get the updated task
    persistent_id = updated_project.dag.node_map[NodeId(task_id)]
    task = updated_project.persistent_tasks[persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Title should be updated, description unchanged
    assert task.title == "New Title"
    assert task.description == "Test"

    # Event should be recorded
    last_event = updated_project.history_events[-1]
    assert last_event.event_type == EventType.NODE_MODIFIED
    assert NodeId(task_id) in last_event.affected_nodes


def test_update_task_multiple_fields(empty_project: Project) -> None:
    """Test updating multiple task fields at once."""
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Original",
        description="Old description",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Update multiple fields
    new_duration = Triangular(min=5.0, mode=10.0, max=15.0)
    updated_project = update_task(
        project,
        task_id,
        title="Updated Title",
        description="Updated description",
        duration_distribution=new_duration,
        allowed_workers=[WorkerId("w1")],
    )

    # Get the updated task
    persistent_id = updated_project.dag.node_map[NodeId(task_id)]
    task = updated_project.persistent_tasks[persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    assert task.title == "Updated Title"
    assert task.description == "Updated description"
    assert task.duration_distribution == new_duration
    assert task.allowed_workers == [WorkerId("w1")]


def test_update_task_no_changes(empty_project: Project) -> None:
    """Test that updating with no changes returns unchanged project."""
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    initial_version = project.dag.current_version_id

    # Update with no changes (all parameters None)
    updated_project = update_task(project, task_id)

    # Should return the same project (same version)
    assert updated_project.dag.current_version_id == initial_version
    assert len(updated_project.history_events) == len(project.history_events)


def test_update_task_nonexistent(empty_project: Project) -> None:
    """Test that updating a non-existent task raises error."""
    with pytest.raises(DAGOperationError, match="Task.*not found"):
        update_task(
            empty_project,
            TaskId("nonexistent"),
            title="New Title",
        )


def test_update_task_validation_failure(empty_project: Project) -> None:
    """Test that updating a task with invalid data raises error."""
    # Add a task
    project, task_id = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Try to update with non-existent worker
    with pytest.raises(DAGOperationError, match="Failed to update task"):
        update_task(
            project,
            task_id,
            allowed_workers=[WorkerId("nonexistent")],
        )


def test_update_branch_title(empty_project: Project) -> None:
    """Test updating a branch's title."""
    # Add a branch
    project, branch_id = add_branch(
        empty_project,
        title="Original Title",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )
    initial_version = project.dag.current_version_id

    # Update the title
    updated_project = update_branch(project, branch_id, title="New Title")

    # Version should change
    assert updated_project.dag.current_version_id != initial_version

    # Get the updated branch
    persistent_id = updated_project.dag.node_map[NodeId(branch_id)]
    branch = updated_project.persistent_branches[persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Title should be updated, description unchanged
    assert branch.title == "New Title"
    assert branch.description == "Test"

    # Event should be recorded
    last_event = updated_project.history_events[-1]
    assert last_event.event_type == EventType.NODE_MODIFIED
    assert NodeId(branch_id) in last_event.affected_nodes


def test_update_branch_possible_worlds(empty_project: Project) -> None:
    """Test updating a branch's possible worlds."""
    # Add a branch
    project, branch_id = add_branch(
        empty_project,
        title="Branch",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    # Update possible worlds
    new_worlds = [
        PossibleWorld(id=PossibleWorldId("pw1"), title="Option A Updated"),
        PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
    ]
    updated_project = update_branch(project, branch_id, possible_worlds=new_worlds)

    # Get the updated branch
    persistent_id = updated_project.dag.node_map[NodeId(branch_id)]
    branch = updated_project.persistent_branches[persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    assert branch.possible_worlds == new_worlds


def test_update_branch_no_changes(empty_project: Project) -> None:
    """Test that updating a branch with no changes returns unchanged project."""
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

    # Should return the same project
    assert updated_project.dag.current_version_id == initial_version


def test_update_branch_nonexistent(empty_project: Project) -> None:
    """Test that updating a non-existent branch raises error."""
    with pytest.raises(DAGOperationError, match="Branch.*not found"):
        update_branch(
            empty_project,
            BranchId("nonexistent"),
            title="New Title",
        )


def test_remove_dependency_from_task(empty_project: Project) -> None:
    """Test removing a dependency from a task."""
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
        target_node_id=NodeId(task2_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, NodeId(task1_id), dep)

    initial_version = project.dag.current_version_id

    # Remove the dependency
    updated_project = remove_dependency(project, NodeId(task1_id), dep)

    # Version should change
    assert updated_project.dag.current_version_id != initial_version

    # Task should no longer have the dependency
    persistent_id = updated_project.dag.node_map[NodeId(task1_id)]
    task = updated_project.persistent_tasks[persistent_id].versions[
        updated_project.dag.current_version_id
    ]
    assert dep not in task.dependencies
    assert len(task.dependencies) == 0

    # Event should be recorded
    last_event = updated_project.history_events[-1]
    assert last_event.event_type == EventType.NODE_MODIFIED
    assert NodeId(task1_id) in last_event.affected_nodes


def test_remove_dependency_from_branch(empty_project: Project) -> None:
    """Test removing a dependency from a branch."""
    # Add a branch and a task
    project, branch_id = add_branch(
        empty_project,
        title="Branch",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )
    project, task_id = add_task(
        project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency from branch to task
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=NodeId(task_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, NodeId(branch_id), dep)

    # Remove the dependency
    updated_project = remove_dependency(project, NodeId(branch_id), dep)

    # Branch should no longer have the dependency
    persistent_id = updated_project.dag.node_map[NodeId(branch_id)]
    branch = updated_project.persistent_branches[persistent_id].versions[
        updated_project.dag.current_version_id
    ]
    assert dep not in branch.dependencies
    assert len(branch.dependencies) == 0


def test_remove_dependency_nonexistent_node(empty_project: Project) -> None:
    """Test that removing a dependency from a non-existent node raises error."""
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId("task_123"),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    with pytest.raises(DAGOperationError, match="Node.*not found"):
        remove_dependency(empty_project, NodeId("nonexistent"), dep)


def test_remove_dependency_preserves_other_dependencies(empty_project: Project) -> None:
    """Test that removing a dependency preserves other dependencies."""
    # Add three tasks
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

    # Add two dependencies from task1
    dep1 = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task2_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    dep2 = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task3_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, NodeId(task1_id), dep1)
    project = add_dependency(project, NodeId(task1_id), dep2)

    # Remove only dep1
    updated_project = remove_dependency(project, NodeId(task1_id), dep1)

    # Get the task
    persistent_id = updated_project.dag.node_map[NodeId(task1_id)]
    task = updated_project.persistent_tasks[persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Should have only dep2
    assert dep1 not in task.dependencies
    assert dep2 in task.dependencies
    assert len(task.dependencies) == 1
