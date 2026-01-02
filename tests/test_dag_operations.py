"""Tests for DAG operations."""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest

from fluxx.data import (
    DAGOperationError,
    add_branch,
    add_dependency,
    add_sibling_subtask,
    add_task,
    convert_to_parent_task,
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
    PersistentObjectId,
    PersistentTask,
    PossibleWorld,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    Task,
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
    assert task_id in updated_project.dag.node_map

    # Event should be recorded
    assert len(updated_project.history_events) == 1
    event = updated_project.history_events[0]
    assert event.event_type == EventType.NODE_CREATED
    assert task_id in event.affected_nodes

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
    parent_persistent_id = updated_project.dag.node_map[parent_id]
    parent_task = updated_project.persistent_tasks[parent_persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Parent should list child
    assert child_id in parent_task.children
    # Parent still has duration (preserved but ignored)
    assert parent_task.duration_distribution == Triangular(min=1.0, mode=2.0, max=3.0)

    # Get the child task
    child_persistent_id = updated_project.dag.node_map[child_id]
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
    persistent_id = updated_project.dag.node_map[task_id]
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
    assert branch_id in updated_project.dag.node_map

    # Event should be recorded
    assert len(updated_project.history_events) == 1
    event = updated_project.history_events[0]
    assert event.event_type == EventType.NODE_CREATED
    assert branch_id in event.affected_nodes


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
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    updated_project = add_dependency(project, task1_id, dep)

    # Version should change
    assert updated_project.dag.current_version_id != initial_version

    # Task should have the dependency
    persistent_id = updated_project.dag.node_map[task1_id]
    task = updated_project.persistent_tasks[persistent_id].versions[
        updated_project.dag.current_version_id
    ]
    assert dep in task.dependencies

    # Event should be recorded
    last_event = updated_project.history_events[-1]
    assert last_event.event_type == EventType.NODE_MODIFIED
    assert task1_id in last_event.affected_nodes


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

    # Add dependency: task1.end >= task2.start
    dep1 = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, task1_id, dep1)

    # Try to add dependency that creates cycle: task2.end >= task1.end
    # This creates: task2.start -> task2.end -> task1.end (via dep2)
    #               task1.end -> task2.start (via dep1 reversed)
    # Wait, that's not quite right. Let me create a clearer cycle:
    # dep2: task2.start >= task1.end means task1.end -> task2.start
    # Combined with implicit task2.start -> task2.end,
    # and dep1 which is task1.end >= task2.start means task2.start -> task1.end
    # This creates: task1.end -> task2.start -> task1.end (cycle!)
    dep2 = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    with pytest.raises(DAGOperationError, match="Cycle detected"):
        add_dependency(project, task2_id, dep2)


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
        target_node_id=task_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.EQUAL,
    )

    with pytest.raises(DAGOperationError, match="cannot use OCCURRENCE"):
        add_dependency(project, task_id, dep)


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
    persistent_id = project.dag.node_map[task1_id]
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
    assert branch_id in updated_project.dag.node_map
    assert task_id in updated_project.dag.node_map


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
    assert task_id in updated_project.dag.node_map
    assert branch_id in updated_project.dag.node_map


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
    assert branch1_id in updated_project.dag.node_map
    assert branch2_id in updated_project.dag.node_map


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
        target_node_id=task_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    with pytest.raises(DAGOperationError, match="Source node.*does not exist"):
        add_dependency(project, TaskId("t_nonexistent"), dep)


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
        target_node_id=task_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    updated_project = add_dependency(project, branch_id, dep)

    # Branch should have the dependency
    persistent_id = updated_project.dag.node_map[branch_id]
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
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    updated_project = add_dependency(project, task1_id, dep)

    # Branch should still exist in new version
    assert branch_id in updated_project.dag.node_map


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
        id=BranchId("b_corrupt"),
        title="Corrupt",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw2"), title="Option B"),
        ],
        dependencies=[
            # Self-reference creates a cycle
            Dependency(
                source_endpoint=Endpoint.OCCURRENCE,
                target_node_id=BranchId("b_corrupt"),
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
                    BranchId("b_corrupt"): persistent_corrupt.id,
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
    persistent_id = updated_project.dag.node_map[task_id]
    task = updated_project.persistent_tasks[persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Title should be updated, description unchanged
    assert task.title == "New Title"
    assert task.description == "Test"

    # Event should be recorded
    last_event = updated_project.history_events[-1]
    assert last_event.event_type == EventType.NODE_MODIFIED
    assert task_id in last_event.affected_nodes


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
    persistent_id = updated_project.dag.node_map[task_id]
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
            TaskId("t_nonexistent"),
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
    persistent_id = updated_project.dag.node_map[branch_id]
    branch = updated_project.persistent_branches[persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Title should be updated, description unchanged
    assert branch.title == "New Title"
    assert branch.description == "Test"

    # Event should be recorded
    last_event = updated_project.history_events[-1]
    assert last_event.event_type == EventType.NODE_MODIFIED
    assert branch_id in last_event.affected_nodes


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
    persistent_id = updated_project.dag.node_map[branch_id]
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
            BranchId("b_nonexistent"),
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
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, task1_id, dep)

    initial_version = project.dag.current_version_id

    # Remove the dependency
    updated_project = remove_dependency(project, task1_id, dep)

    # Version should change
    assert updated_project.dag.current_version_id != initial_version

    # Task should no longer have the dependency
    persistent_id = updated_project.dag.node_map[task1_id]
    task = updated_project.persistent_tasks[persistent_id].versions[
        updated_project.dag.current_version_id
    ]
    assert dep not in task.dependencies
    assert len(task.dependencies) == 0

    # Event should be recorded
    last_event = updated_project.history_events[-1]
    assert last_event.event_type == EventType.NODE_MODIFIED
    assert task1_id in last_event.affected_nodes


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
        target_node_id=task_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, branch_id, dep)

    # Remove the dependency
    updated_project = remove_dependency(project, branch_id, dep)

    # Branch should no longer have the dependency
    persistent_id = updated_project.dag.node_map[branch_id]
    branch = updated_project.persistent_branches[persistent_id].versions[
        updated_project.dag.current_version_id
    ]
    assert dep not in branch.dependencies
    assert len(branch.dependencies) == 0


def test_remove_dependency_nonexistent_node(empty_project: Project) -> None:
    """Test that removing a dependency from a non-existent node raises error."""
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=TaskId("task_123"),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    with pytest.raises(DAGOperationError, match="Node.*not found"):
        remove_dependency(empty_project, TaskId("t_nonexistent"), dep)


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
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    dep2 = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=task3_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    project = add_dependency(project, task1_id, dep1)
    project = add_dependency(project, task1_id, dep2)

    # Remove only dep1
    updated_project = remove_dependency(project, task1_id, dep1)

    # Get the task
    persistent_id = updated_project.dag.node_map[task1_id]
    task = updated_project.persistent_tasks[persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Should have only dep2
    assert dep1 not in task.dependencies
    assert dep2 in task.dependencies
    assert len(task.dependencies) == 1


def test_convert_to_parent_creates_child(empty_project: Project) -> None:
    """Test that converting a task to parent creates a child with dependencies."""
    # Add a leaf task
    project, task_id = add_task(
        empty_project,
        title="Parent Task",
        description="Will become parent",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Convert to parent
    updated_project, child_id = convert_to_parent_task(project, task_id, "Child Task")

    # Get parent task
    parent_node_id = task_id
    parent_persistent_id = updated_project.dag.node_map[parent_node_id]
    parent_task = updated_project.persistent_tasks[parent_persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Parent should have child
    assert len(parent_task.children) == 1
    assert parent_task.children[0] == child_id

    # Parent should have no duration
    assert parent_task.duration_distribution is None

    # Get child task
    child_node_id = child_id
    child_persistent_id = updated_project.dag.node_map[child_node_id]
    child_task = updated_project.persistent_tasks[child_persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Child should have parent_id
    assert child_task.parent_id == task_id

    # Child should have parent's duration
    assert child_task.duration_distribution == Triangular(min=1.0, mode=2.0, max=3.0)

    # Child should have dependency: child.start >= parent.start
    assert len(child_task.dependencies) == 1
    child_dep = child_task.dependencies[0]
    assert child_dep.source_endpoint == Endpoint.START
    assert child_dep.target_node_id == task_id
    assert child_dep.target_endpoint == Endpoint.START
    assert child_dep.constraint_type == ConstraintType.GREATER_EQUAL

    # Parent should have dependency: parent.end >= child.end
    assert len(parent_task.dependencies) == 1
    parent_dep = parent_task.dependencies[0]
    assert parent_dep.source_endpoint == Endpoint.END
    assert parent_dep.target_node_id == child_id
    assert parent_dep.target_endpoint == Endpoint.END
    assert parent_dep.constraint_type == ConstraintType.GREATER_EQUAL


def test_convert_to_parent_fails_if_already_parent(empty_project: Project) -> None:
    """Test that converting a task that already has children fails."""
    # Create a parent task by converting a leaf
    project, leaf_id = add_task(
        empty_project,
        title="Leaf Task",
        description="Will become parent",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Convert to parent (now it has a child)
    project, child_id = convert_to_parent_task(project, leaf_id, "First Child")

    # Try to convert to parent again - should fail
    with pytest.raises(DAGOperationError, match="already has children"):
        convert_to_parent_task(project, leaf_id, "Another Child")


def test_convert_to_parent_fails_if_task_not_found(empty_project: Project) -> None:
    """Test that converting a non-existent task fails."""
    with pytest.raises(DAGOperationError, match="not found"):
        convert_to_parent_task(empty_project, TaskId("t_nonexistent"), "Child")


def test_add_sibling_creates_sibling(empty_project: Project) -> None:
    """Test that adding a sibling creates a task with same parent."""
    # Create a parent task by converting a leaf
    project, parent_id = add_task(
        empty_project,
        title="Parent Task",
        description="Will become parent",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Convert to parent (creates first child)
    project, child1_id = convert_to_parent_task(project, parent_id, "Child 1")

    # Add sibling
    updated_project, sibling_id = add_sibling_subtask(
        project, child1_id, "Child 2", Triangular(min=2.0, mode=3.0, max=4.0)
    )

    # Get parent task
    parent_node_id = parent_id
    parent_persistent_id = updated_project.dag.node_map[parent_node_id]
    parent_task = updated_project.persistent_tasks[parent_persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Parent should have both children
    assert len(parent_task.children) == 2
    assert child1_id in parent_task.children
    assert sibling_id in parent_task.children

    # Get sibling task
    sibling_node_id = sibling_id
    sibling_persistent_id = updated_project.dag.node_map[sibling_node_id]
    sibling_task = updated_project.persistent_tasks[sibling_persistent_id].versions[
        updated_project.dag.current_version_id
    ]

    # Sibling should have same parent
    assert sibling_task.parent_id == parent_id

    # Sibling should have its own duration
    assert sibling_task.duration_distribution == Triangular(min=2.0, mode=3.0, max=4.0)

    # Sibling should have dependency: sibling.start >= parent.start
    assert len(sibling_task.dependencies) == 1
    sibling_dep = sibling_task.dependencies[0]
    assert sibling_dep.source_endpoint == Endpoint.START
    assert sibling_dep.target_node_id == parent_id
    assert sibling_dep.target_endpoint == Endpoint.START
    assert sibling_dep.constraint_type == ConstraintType.GREATER_EQUAL

    # Parent should have dependency to new sibling: parent.end >= sibling.end
    # Check that it has dependencies to both children
    assert len(parent_task.dependencies) == 2


def test_add_sibling_fails_if_not_subtask(empty_project: Project) -> None:
    """Test that adding a sibling to a non-subtask fails."""
    # Add a standalone task (no parent)
    project, task_id = add_task(
        empty_project,
        title="Standalone Task",
        description="Has no parent",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Try to add sibling - should fail
    with pytest.raises(DAGOperationError, match="not a subtask"):
        add_sibling_subtask(project, task_id, "Sibling", None)


def test_add_sibling_fails_if_task_not_found(empty_project: Project) -> None:
    """Test that adding a sibling to a non-existent task fails."""
    with pytest.raises(DAGOperationError, match="not found"):
        add_sibling_subtask(empty_project, TaskId("t_nonexistent"), "Sibling", None)


def test_convert_to_parent_fails_if_branch_not_task(empty_project: Project) -> None:
    """Test that converting a branch to parent fails."""
    from fluxx.data.models import (
        Branch,
        BranchId,
        PersistentBranch,
        PossibleWorld,
        PossibleWorldId,
    )

    # Create a branch
    branch = Branch(
        id=BranchId("b1"),
        title="Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )

    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={empty_project.dag.current_version_id: branch},
    )

    project = Project(
        **empty_project.model_dump(exclude={"persistent_branches", "dag"}),
        dag=empty_project.dag.model_copy(
            update={"node_map": {BranchId("b1"): PersistentObjectId("pb1")}}
        ),
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    # Try to convert branch to parent - should fail
    with pytest.raises(DAGOperationError, match="is not a task"):
        convert_to_parent_task(project, TaskId("b1"), "Child")


def test_convert_to_parent_fails_if_not_in_current_version(
    empty_project: Project,
) -> None:
    """Test that converting a task not in current version fails."""
    # Create a task in an old version, not in current version
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={DAGVersionId("old_version"): task},  # Not current version
    )

    project = Project(
        **empty_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=empty_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    with pytest.raises(DAGOperationError, match="not in current version"):
        convert_to_parent_task(project, TaskId("t1"), "Child")


def test_convert_to_parent_uses_default_distribution_when_none(
    empty_project: Project,
) -> None:
    """Test that converting a task with no distribution uses default for child."""
    from fluxx.data.models import ShiftedLognormal

    # Create a leaf task with no distribution
    leaf_id = TaskId("t1")
    leaf = Task(
        id=leaf_id,
        title="Leaf",
        description="Test",
        duration_distribution=None,  # No distribution
    )
    persistent_leaf = PersistentTask(
        id=PersistentObjectId("pl"),
        versions={empty_project.dag.current_version_id: leaf},
    )

    project_with_leaf = Project(
        **empty_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=empty_project.dag.model_copy(
            update={"node_map": {leaf_id: PersistentObjectId("pl")}}
        ),
        persistent_tasks={PersistentObjectId("pl"): persistent_leaf},
    )

    # Convert to parent - should use default distribution for child
    updated_project, child_id = convert_to_parent_task(
        project_with_leaf, leaf_id, "New Child"
    )

    # Verify child has the default distribution
    child_persistent_id = updated_project.dag.node_map[child_id]
    child_persistent = updated_project.persistent_tasks[child_persistent_id]
    child_task = child_persistent.versions[updated_project.dag.current_version_id]

    assert child_task.duration_distribution is not None
    assert isinstance(child_task.duration_distribution, ShiftedLognormal)
    # Check default values: min=0.25, mode=6.0, percentile_95=24.0
    assert child_task.duration_distribution.min == 0.25
    assert child_task.duration_distribution.mode == 6.0
    assert child_task.duration_distribution.percentile_95 == 24.0


def test_convert_to_parent_with_old_version_tasks_and_branches(
    empty_project: Project,
) -> None:
    """Test converting to parent when project has old-version tasks/branches."""
    from fluxx.data.models import (
        Branch,
        BranchId,
        PersistentBranch,
        PossibleWorld,
        PossibleWorldId,
    )

    # Create a task to convert
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create an old task that's not in current version
    old_task = Task(
        id=TaskId("t_old_task"),
        title="Old Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create an old branch that's not in current version
    old_branch = Branch(
        id=BranchId("b_old_branch"),
        title="Old Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={empty_project.dag.current_version_id: task},
    )
    persistent_old_task = PersistentTask(
        id=PersistentObjectId("pot"),
        versions={DAGVersionId("old_version"): old_task},  # Not in current version
    )
    persistent_old_branch = PersistentBranch(
        id=PersistentObjectId("pob"),
        versions={DAGVersionId("old_version"): old_branch},  # Not in current version
    )

    project = Project(
        **empty_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=empty_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    TaskId("t_old_task"): PersistentObjectId("pot"),
                    BranchId("b_old_branch"): PersistentObjectId("pob"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pt1"): persistent_task,
            PersistentObjectId("pot"): persistent_old_task,
        },
        persistent_branches={PersistentObjectId("pob"): persistent_old_branch},
    )

    # Convert to parent - should succeed and handle old versions
    updated_project, child_id = convert_to_parent_task(project, TaskId("t1"), "Child")

    # Verify old task/branch are still in result
    assert PersistentObjectId("pot") in updated_project.persistent_tasks
    assert PersistentObjectId("pob") in updated_project.persistent_branches


def test_add_sibling_fails_if_branch_not_task(empty_project: Project) -> None:
    """Test that adding sibling to a branch fails."""
    from fluxx.data.models import (
        Branch,
        BranchId,
        PersistentBranch,
        PossibleWorld,
        PossibleWorldId,
    )

    # Create a branch
    branch = Branch(
        id=BranchId("b1"),
        title="Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )

    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={empty_project.dag.current_version_id: branch},
    )

    project = Project(
        **empty_project.model_dump(exclude={"persistent_branches", "dag"}),
        dag=empty_project.dag.model_copy(
            update={"node_map": {BranchId("b1"): PersistentObjectId("pb1")}}
        ),
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    # Try to add sibling to branch - should fail
    with pytest.raises(DAGOperationError, match="is not a task"):
        add_sibling_subtask(project, TaskId("b1"), "Sibling", None)


def test_add_sibling_fails_if_not_in_current_version(empty_project: Project) -> None:
    """Test that adding sibling to task not in current version fails."""
    # Create a task in an old version, not in current version
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        parent_id=TaskId("t_parent"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={DAGVersionId("old_version"): task},  # Not current version
    )

    project = Project(
        **empty_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=empty_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    with pytest.raises(DAGOperationError, match="not in current version"):
        add_sibling_subtask(project, TaskId("t1"), "Sibling", None)


def test_add_sibling_with_old_version_tasks_and_branches(
    empty_project: Project,
) -> None:
    """Test adding sibling when project has old-version tasks/branches."""
    from fluxx.data.models import (
        Branch,
        BranchId,
        PersistentBranch,
        PossibleWorld,
        PossibleWorldId,
    )

    # Create parent and child
    parent_id = TaskId("t100")
    child1_id = TaskId("t200")
    parent = Task(
        id=parent_id,
        title="Parent",
        description="Test",
        children=[child1_id],
    )
    child1 = Task(
        id=child1_id,
        title="Child 1",
        description="Test",
        parent_id=parent_id,
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create an old task that's not in current version
    old_task_id = TaskId("t0")
    old_task = Task(
        id=old_task_id,
        title="Old Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create an old branch that's not in current version
    old_branch_id = BranchId("b0")
    old_branch = Branch(
        id=old_branch_id,
        title="Old Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )

    persistent_parent = PersistentTask(
        id=PersistentObjectId("pp"),
        versions={empty_project.dag.current_version_id: parent},
    )
    persistent_child1 = PersistentTask(
        id=PersistentObjectId("pc1"),
        versions={empty_project.dag.current_version_id: child1},
    )
    persistent_old_task = PersistentTask(
        id=PersistentObjectId("pot"),
        versions={DAGVersionId("old_version"): old_task},  # Not in current version
    )
    persistent_old_branch = PersistentBranch(
        id=PersistentObjectId("pob"),
        versions={DAGVersionId("old_version"): old_branch},  # Not in current version
    )

    project = Project(
        **empty_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=empty_project.dag.model_copy(
            update={
                "node_map": {
                    parent_id: PersistentObjectId("pp"),
                    child1_id: PersistentObjectId("pc1"),
                    old_task_id: PersistentObjectId("pot"),
                    old_branch_id: PersistentObjectId("pob"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pp"): persistent_parent,
            PersistentObjectId("pc1"): persistent_child1,
            PersistentObjectId("pot"): persistent_old_task,
        },
        persistent_branches={PersistentObjectId("pob"): persistent_old_branch},
    )

    # Add sibling - should succeed and handle old versions
    updated_project, sibling_id = add_sibling_subtask(
        project, child1_id, "Child 2", None
    )

    # Verify old task/branch are still in result
    assert PersistentObjectId("pot") in updated_project.persistent_tasks
    assert PersistentObjectId("pob") in updated_project.persistent_branches


def test_convert_to_parent_with_multiple_current_version_tasks(
    empty_project: Project,
) -> None:
    """Test converting to parent when project has multiple tasks in current version.

    This ensures line 861 is covered (copying tasks that aren't the parent).
    """
    from fluxx.data.models import (
        Branch,
        BranchId,
        PersistentBranch,
        PossibleWorld,
        PossibleWorldId,
    )

    # Create multiple tasks in current version
    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2 = Task(
        id=TaskId("t2"),
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    # Create a branch in current version too
    branch_current = Branch(
        id=BranchId("b1"),
        title="Current Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )
    # And an old version of the same branch
    branch_old = Branch(
        id=BranchId("b1"),
        title="Old Branch",
        description="Old Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )

    persistent_task1 = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={empty_project.dag.current_version_id: task1},
    )
    persistent_task2 = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={empty_project.dag.current_version_id: task2},
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={
            DAGVersionId("old_version"): branch_old,  # Old version
            empty_project.dag.current_version_id: branch_current,  # Current version
        },
    )

    project = Project(
        **empty_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=empty_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    TaskId("t2"): PersistentObjectId("pt2"),
                    BranchId("b1"): PersistentObjectId("pb1"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pt1"): persistent_task1,
            PersistentObjectId("pt2"): persistent_task2,
        },
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    # Convert t1 to parent - t2 and branch should be copied to new version
    updated_project, child_id = convert_to_parent_task(project, TaskId("t1"), "Child")

    # Verify t2 is in the new version
    pt2_versions = updated_project.persistent_tasks[PersistentObjectId("pt2")].versions
    assert updated_project.dag.current_version_id in pt2_versions

    # Verify branch has both old and new versions
    pb1_versions = updated_project.persistent_branches[
        PersistentObjectId("pb1")
    ].versions
    assert DAGVersionId("old_version") in pb1_versions
    assert updated_project.dag.current_version_id in pb1_versions


def test_add_sibling_with_multiple_current_version_tasks(
    empty_project: Project,
) -> None:
    """Test adding sibling when project has multiple tasks in current version.

    This ensures line 1045-1048 is covered (copying branches with both old and
    current versions).
    """
    from fluxx.data.models import (
        Branch,
        BranchId,
        PersistentBranch,
        PossibleWorld,
        PossibleWorldId,
    )

    # Create parent and child
    parent_id = TaskId("t100")
    child1_id = TaskId("t200")
    parent = Task(
        id=parent_id,
        title="Parent",
        description="Test",
        children=[child1_id],
    )
    child1 = Task(
        id=child1_id,
        title="Child 1",
        description="Test",
        parent_id=parent_id,
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create a branch with both old and current versions
    branch_id = BranchId("b1")
    branch_old = Branch(
        id=branch_id,
        title="Old Branch",
        description="Old",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )
    branch_current = Branch(
        id=branch_id,
        title="Current Branch",
        description="Current",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )

    persistent_parent = PersistentTask(
        id=PersistentObjectId("pp"),
        versions={empty_project.dag.current_version_id: parent},
    )
    persistent_child1 = PersistentTask(
        id=PersistentObjectId("pc1"),
        versions={empty_project.dag.current_version_id: child1},
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={
            DAGVersionId("old_version"): branch_old,
            empty_project.dag.current_version_id: branch_current,
        },
    )

    project = Project(
        **empty_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=empty_project.dag.model_copy(
            update={
                "node_map": {
                    parent_id: PersistentObjectId("pp"),
                    child1_id: PersistentObjectId("pc1"),
                    branch_id: PersistentObjectId("pb1"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pp"): persistent_parent,
            PersistentObjectId("pc1"): persistent_child1,
        },
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    # Add sibling - branch should be copied to new version
    updated_project, sibling_id = add_sibling_subtask(
        project, child1_id, "Child 2", None
    )

    # Verify branch has old version and new current version
    pb1_versions = updated_project.persistent_branches[
        PersistentObjectId("pb1")
    ].versions
    assert DAGVersionId("old_version") in pb1_versions
    assert updated_project.dag.current_version_id in pb1_versions


def test_convert_to_parent_validation_error(
    empty_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that convert_to_parent raises DAGOperationError when validation fails."""
    from fluxx.data import dag_operations, validation

    # Create a task
    project, task_id = add_task(
        empty_project,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Mock validate_dag to raise an exception
    def mock_validate_dag(project: Project) -> None:
        raise validation.ValidationError("Mock validation error")

    # Patch in dag_operations module where it's imported
    monkeypatch.setattr(dag_operations, "validate_dag", mock_validate_dag)

    # Should raise DAGOperationError wrapping the validation error
    with pytest.raises(DAGOperationError, match="Failed to convert to parent"):
        convert_to_parent_task(project, task_id, "Child")


def test_add_sibling_validation_error(
    empty_project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that add_sibling raises DAGOperationError when validation fails."""
    from fluxx.data import dag_operations, validation

    # Create a parent with a child
    project, parent_id = add_task(
        empty_project,
        title="Parent",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    project, child_id = convert_to_parent_task(project, parent_id, "Child 1")

    # Mock validate_dag to raise an exception
    def mock_validate_dag(project: Project) -> None:
        raise validation.ValidationError("Mock validation error")

    # Patch in dag_operations module where it's imported
    monkeypatch.setattr(dag_operations, "validate_dag", mock_validate_dag)

    # Should raise DAGOperationError wrapping the validation error
    with pytest.raises(DAGOperationError, match="Failed to add sibling subtask"):
        add_sibling_subtask(project, child_id, "Child 2", None)
