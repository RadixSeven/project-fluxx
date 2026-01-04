"""Tests for DAG validation."""

from collections.abc import Generator
from datetime import UTC, datetime
from typing import cast

import pytest

from fluxx.data import (
    CycleError,
    EndpointError,
    HierarchyError,
    ValidationError,
    WorkerConstraintError,
    validate_dag,
    validate_dependency,
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
    PersistentBranch,
    PersistentObjectId,
    PersistentTask,
    PossibleWorld,
    PossibleWorldId,
    PossibleWorldReferencePair,
    Project,
    ProjectMetadata,
    Task,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)


@pytest.fixture
def base_project() -> Generator[Project]:
    """Create a base project for testing."""
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


def test_validate_empty_dag(base_project: Project) -> None:
    """Test validating an empty DAG."""
    # Should pass with no nodes
    validate_dag(base_project)


def test_validate_single_task(base_project: Project) -> None:
    """Test validating a DAG with a single task."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    validate_dag(project)


def test_detect_simple_cycle(base_project: Project) -> None:
    """Test detecting a simple cycle (t1 -> t2 -> t1)."""
    # Create a real cycle: task1.end >= task2.start AND task2.start >= task1.end
    # This creates: task2.start -> task1.end -> task2.start (cycle!)
    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t2"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )
    task2 = Task(
        id=TaskId("t2"),
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    persistent_task1 = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task1},
    )
    persistent_task2 = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={base_project.dag.current_version_id: task2},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    TaskId("t2"): PersistentObjectId("pt2"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pt1"): persistent_task1,
            PersistentObjectId("pt2"): persistent_task2,
        },
    )

    with pytest.raises(CycleError, match="Cycle detected"):
        validate_dag(project)


def test_detect_self_cycle(base_project: Project) -> None:
    """Test detecting a self-referencing cycle."""
    # Create a self-loop: task1.end >= task1.end
    # This creates: task1.end -> task1.end (self-cycle!)
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    with pytest.raises(CycleError, match="Cycle detected"):
        validate_dag(project)


def test_validate_parent_child_hierarchy(base_project: Project) -> None:
    """Test validating parent-child task relationships."""
    parent = Task(
        id=TaskId("t_parent"),
        title="Parent",
        description="Test",
        children=[TaskId("t_child")],
    )
    child = Task(
        id=TaskId("t_child"),
        title="Child",
        description="Test",
        parent_id=TaskId("t_parent"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_parent = PersistentTask(
        id=PersistentObjectId("pp"),
        versions={base_project.dag.current_version_id: parent},
    )
    persistent_child = PersistentTask(
        id=PersistentObjectId("pc"),
        versions={base_project.dag.current_version_id: child},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t_parent"): PersistentObjectId("pp"),
                    TaskId("t_child"): PersistentObjectId("pc"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pp"): persistent_parent,
            PersistentObjectId("pc"): persistent_child,
        },
    )

    validate_dag(project)


def test_invalid_parent_reference(base_project: Project) -> None:
    """Test task with non-existent parent."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        parent_id=TaskId("t_nonexistent"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    with pytest.raises(HierarchyError, match="non-existent parent"):
        validate_dag(project)


def test_leaf_task_requires_duration(base_project: Project) -> None:
    """Test that leaf tasks must have duration distribution."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        # Missing duration_distribution
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    with pytest.raises(HierarchyError, match="must have a duration distribution"):
        validate_dag(project)


def test_parent_task_can_have_duration(base_project: Project) -> None:
    """Test parent tasks can have duration (preserved but ignored)."""
    parent = Task(
        id=TaskId("t_parent"),
        title="Parent",
        description="Test",
        children=[TaskId("t_child")],
        duration_distribution=Triangular(
            min=1.0, mode=2.0, max=3.0
        ),  # Valid - preserved but ignored
    )
    child = Task(
        id=TaskId("t_child"),
        title="Child",
        description="Test",
        parent_id=TaskId("t_parent"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_parent = PersistentTask(
        id=PersistentObjectId("pp"),
        versions={base_project.dag.current_version_id: parent},
    )
    persistent_child = PersistentTask(
        id=PersistentObjectId("pc"),
        versions={base_project.dag.current_version_id: child},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t_parent"): PersistentObjectId("pp"),
                    TaskId("t_child"): PersistentObjectId("pc"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pp"): persistent_parent,
            PersistentObjectId("pc"): persistent_child,
        },
    )

    # Should pass - parent tasks can have duration (it's just ignored)
    validate_dag(project)


def test_validate_worker_constraints(base_project: Project) -> None:
    """Test validating worker constraints."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[WorkerId("w1")],  # Valid worker
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    validate_dag(project)


def test_invalid_worker_constraint(base_project: Project) -> None:
    """Test task with non-existent worker."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[WorkerId("nonexistent")],
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    with pytest.raises(WorkerConstraintError, match="non-existent worker"):
        validate_dag(project)


def test_validate_dependency_task_endpoints(base_project: Project) -> None:
    """Test validating task endpoint compatibility."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    # Valid: task with START/END endpoints
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=TaskId("t1"),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    validate_dependency(project, TaskId("t1"), dep)


def test_task_cannot_use_occurrence_endpoint(base_project: Project) -> None:
    """Test that tasks cannot use OCCURRENCE endpoint."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    # Invalid: task with OCCURRENCE endpoint
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=TaskId("t1"),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.EQUAL,
    )

    with pytest.raises(EndpointError, match="cannot use OCCURRENCE"):
        validate_dependency(project, TaskId("t1"), dep)


def test_branch_cannot_use_start_end_endpoint(base_project: Project) -> None:
    """Test that branches cannot use START/END endpoints."""
    branch = Branch(
        id=BranchId("b1"),
        title="Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )

    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={base_project.dag.current_version_id: branch},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_branches", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {BranchId("b1"): PersistentObjectId("pb1")}}
        ),
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    # Invalid: branch with START endpoint
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=BranchId("b1"),
        target_endpoint=Endpoint.OCCURRENCE,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    with pytest.raises(EndpointError, match="cannot use START/END"):
        validate_dependency(project, BranchId("b1"), dep)


def test_cycle_detection_with_branches(base_project: Project) -> None:
    """Test cycle detection that includes branches."""
    # Create a cycle: task1.end >= branch1.occurrence AND
    # branch1.occurrence >= task1.end
    # This creates: branch1.occurrence -> task1.end -> branch1.occurrence (cycle!)
    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=BranchId("b1"),
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )
    branch1 = Branch(
        id=BranchId("b1"),
        title="Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.OCCURRENCE,
                target_node_id=TaskId("t1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task1},
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={base_project.dag.current_version_id: branch1},
    )

    project = Project(
        **base_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    BranchId("b1"): PersistentObjectId("pb1"),
                }
            }
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    with pytest.raises(CycleError, match="Cycle detected"):
        validate_dag(project)


def test_validate_dependency_nonexistent_source(base_project: Project) -> None:
    """Test validating dependency with non-existent source node."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=TaskId("t1"),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    with pytest.raises(ValidationError, match="does not exist"):
        validate_dependency(project, TaskId("t_nonexistent"), dep)


def test_validate_dependency_nonexistent_target(base_project: Project) -> None:
    """Test validating dependency with non-existent target node."""
    task_id = TaskId("t1")
    task = Task(
        id=task_id,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {task_id: PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    nonexistent_task_id = TaskId("t999")
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=nonexistent_task_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    with pytest.raises(ValidationError, match="does not exist"):
        validate_dependency(project, TaskId("t1"), dep)


def test_task_target_cannot_use_occurrence(base_project: Project) -> None:
    """Test that task targets cannot use OCCURRENCE endpoint."""
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

    persistent_task1 = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task1},
    )
    persistent_task2 = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={base_project.dag.current_version_id: task2},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    TaskId("t2"): PersistentObjectId("pt2"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pt1"): persistent_task1,
            PersistentObjectId("pt2"): persistent_task2,
        },
    )

    # Try to use OCCURRENCE on task target
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=TaskId("t2"),
        target_endpoint=Endpoint.OCCURRENCE,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    with pytest.raises(EndpointError, match="cannot use OCCURRENCE"):
        validate_dependency(project, TaskId("t1"), dep)


def test_branch_target_cannot_use_start_end(base_project: Project) -> None:
    """Test that branch targets cannot use START/END endpoints."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch = Branch(
        id=BranchId("b1"),
        title="Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={base_project.dag.current_version_id: branch},
    )

    project = Project(
        **base_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    BranchId("b1"): PersistentObjectId("pb1"),
                }
            }
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    # Try to use END endpoint on branch target
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=BranchId("b1"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    with pytest.raises(EndpointError, match="cannot use START/END"):
        validate_dependency(project, TaskId("t1"), dep)


def test_diamond_dependency_no_cycle(base_project: Project) -> None:
    """Test diamond dependencies don't cause false cycle detection."""
    # Create diamond: t1 -> t2, t1 -> t3, t2 -> t4, t3 -> t4
    # This tests the 'black node' early return in DFS
    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t2"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t3"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ],
    )
    task2 = Task(
        id=TaskId("t2"),
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t4"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )
    task3 = Task(
        id=TaskId("t3"),
        title="Task 3",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t4"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )
    task4 = Task(
        id=TaskId("t4"),
        title="Task 4",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_tasks = {
        PersistentObjectId("pt1"): PersistentTask(
            id=PersistentObjectId("pt1"),
            versions={base_project.dag.current_version_id: task1},
        ),
        PersistentObjectId("pt2"): PersistentTask(
            id=PersistentObjectId("pt2"),
            versions={base_project.dag.current_version_id: task2},
        ),
        PersistentObjectId("pt3"): PersistentTask(
            id=PersistentObjectId("pt3"),
            versions={base_project.dag.current_version_id: task3},
        ),
        PersistentObjectId("pt4"): PersistentTask(
            id=PersistentObjectId("pt4"),
            versions={base_project.dag.current_version_id: task4},
        ),
    }

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    TaskId("t2"): PersistentObjectId("pt2"),
                    TaskId("t3"): PersistentObjectId("pt3"),
                    TaskId("t4"): PersistentObjectId("pt4"),
                }
            }
        ),
        persistent_tasks=persistent_tasks,
    )

    # Should pass - no cycle, just multiple paths
    validate_dag(project)


def test_parent_is_branch_not_task(base_project: Project) -> None:
    """Test error when task's parent is a branch, not a task."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        parent_id=TaskId("b1"),  # Parent is actually a branch
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch = Branch(
        id=BranchId("b1"),
        title="Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={base_project.dag.current_version_id: branch},
    )

    project = Project(
        **base_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    BranchId("b1"): PersistentObjectId("pb1"),
                }
            }
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    with pytest.raises(HierarchyError, match="is not a task"):
        validate_dag(project)


def test_parent_doesnt_list_child(base_project: Project) -> None:
    """Test error when parent doesn't list task in its children."""
    parent = Task(
        id=TaskId("t_parent"),
        title="Parent",
        description="Test",
        children=[],  # Should include child but doesn't
        duration_distribution=Triangular(
            min=1.0, mode=2.0, max=3.0
        ),  # Needs duration since it has no children
    )
    child = Task(
        id=TaskId("t_child"),
        title="Child",
        description="Test",
        parent_id=TaskId("t_parent"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_parent = PersistentTask(
        id=PersistentObjectId("pp"),
        versions={base_project.dag.current_version_id: parent},
    )
    persistent_child = PersistentTask(
        id=PersistentObjectId("pc"),
        versions={base_project.dag.current_version_id: child},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t_parent"): PersistentObjectId("pp"),
                    TaskId("t_child"): PersistentObjectId("pc"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pp"): persistent_parent,
            PersistentObjectId("pc"): persistent_child,
        },
    )

    with pytest.raises(HierarchyError, match="does not list it as a child"):
        validate_dag(project)


def test_child_is_branch_not_task(base_project: Project) -> None:
    """Test error when task's child is a branch, not a task."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        children=[TaskId("b1")],  # Child is actually a branch
    )
    branch = Branch(
        id=BranchId("b1"),
        title="Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={base_project.dag.current_version_id: branch},
    )

    project = Project(
        **base_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    BranchId("b1"): PersistentObjectId("pb1"),
                }
            }
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    with pytest.raises(HierarchyError, match="child.*is not a task"):
        validate_dag(project)


def test_child_doesnt_reference_parent(base_project: Project) -> None:
    """Test error when child doesn't reference task as its parent."""
    parent = Task(
        id=TaskId("t_parent"),
        title="Parent",
        description="Test",
        children=[TaskId("t_child")],
    )
    child = Task(
        id=TaskId("t_child"),
        title="Child",
        description="Test",
        parent_id=None,  # Should reference parent but doesn't
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_parent = PersistentTask(
        id=PersistentObjectId("pp"),
        versions={base_project.dag.current_version_id: parent},
    )
    persistent_child = PersistentTask(
        id=PersistentObjectId("pc"),
        versions={base_project.dag.current_version_id: child},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t_parent"): PersistentObjectId("pp"),
                    TaskId("t_child"): PersistentObjectId("pc"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pp"): persistent_parent,
            PersistentObjectId("pc"): persistent_child,
        },
    )

    with pytest.raises(HierarchyError, match="does not reference it as parent"):
        validate_dag(project)


def test_excluded_worker_tasks_validation(base_project: Project) -> None:
    """Test validating excluded_worker_tasks references."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        excluded_worker_tasks=[TaskId("t_nonexistent")],  # Non-existent task
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    with pytest.raises(WorkerConstraintError, match="non-existent task"):
        validate_dag(project)


def test_excluded_worker_tasks_requires_dependency(base_project: Project) -> None:
    """Test that excluded_worker_tasks requires the start dependency."""
    # Task 1 excludes task 2's assignee but has no dependency on task 2
    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        excluded_worker_tasks=[TaskId("t2")],  # Missing required dependency
    )
    task2 = Task(
        id=TaskId("t2"),
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_task1 = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task1},
    )
    persistent_task2 = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={base_project.dag.current_version_id: task2},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    TaskId("t2"): PersistentObjectId("pt2"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pt1"): persistent_task1,
            PersistentObjectId("pt2"): persistent_task2,
        },
    )

    with pytest.raises(WorkerConstraintError, match="missing required dependency"):
        validate_dag(project)


def test_excluded_worker_tasks_with_dependency_passes(base_project: Project) -> None:
    """Test that excluded_worker_tasks with required dependency passes validation."""
    # Task 1 excludes task 2's assignee and has the required dependency
    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        excluded_worker_tasks=[TaskId("t2")],
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t2"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )
    task2 = Task(
        id=TaskId("t2"),
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_task1 = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={base_project.dag.current_version_id: task1},
    )
    persistent_task2 = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={base_project.dag.current_version_id: task2},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    TaskId("t2"): PersistentObjectId("pt2"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pt1"): persistent_task1,
            PersistentObjectId("pt2"): persistent_task2,
        },
    )

    # Should pass validation
    validate_dag(project)


def test_has_required_exclusion_dependency() -> None:
    """Test the has_required_exclusion_dependency helper function."""
    from fluxx.data.validation import has_required_exclusion_dependency

    now = datetime.now(UTC)
    metadata = ProjectMetadata(name="Test", created=now, last_modified=now)
    version_id = DAGVersionId("v1")
    dag = DAG(id=DAGId("dag1"), current_version_id=version_id)

    # Task with the required dependency
    task_with_dep = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t2"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Task without the required dependency
    task_without_dep = Task(
        id=TaskId("t3"),
        title="Task 3",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    project = Project(
        metadata=metadata,
        dag=dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    TaskId("t2"): PersistentObjectId("pt2"),
                    TaskId("t3"): PersistentObjectId("pt3"),
                }
            }
        ),
        workers=[],
        persistent_tasks={
            PersistentObjectId("pt1"): PersistentTask(
                id=PersistentObjectId("pt1"),
                versions={version_id: task_with_dep},
            ),
            PersistentObjectId("pt2"): PersistentTask(
                id=PersistentObjectId("pt2"),
                versions={
                    version_id: Task(
                        id=TaskId("t2"),
                        title="Task 2",
                        description="Test",
                        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
                    )
                },
            ),
            PersistentObjectId("pt3"): PersistentTask(
                id=PersistentObjectId("pt3"),
                versions={version_id: task_without_dep},
            ),
        },
    )

    # Task 1 has dependency on Task 2
    assert has_required_exclusion_dependency(project, TaskId("t1"), TaskId("t2"))

    # Task 1 does NOT have dependency on Task 3
    assert not has_required_exclusion_dependency(project, TaskId("t1"), TaskId("t3"))

    # Task 3 has no dependencies at all
    assert not has_required_exclusion_dependency(project, TaskId("t3"), TaskId("t1"))

    # Non-existent task
    assert not has_required_exclusion_dependency(
        project, TaskId("t_nonexistent"), TaskId("t1")
    )


def test_has_required_exclusion_dependency_branch_node() -> None:
    """Test has_required_exclusion_dependency when source is a branch node."""
    from fluxx.data.validation import has_required_exclusion_dependency

    now = datetime.now(UTC)
    metadata = ProjectMetadata(name="Test", created=now, last_modified=now)
    version_id = DAGVersionId("v1")
    dag = DAG(id=DAGId("dag1"), current_version_id=version_id)

    # Create project with a branch (which is in node_map but NOT in persistent_tasks)
    branch = Branch(
        id=BranchId("b1"),
        title="Branch 1",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World", weight=1.0)
        ],
    )

    project = Project(
        metadata=metadata,
        dag=dag.model_copy(
            update={
                "node_map": {
                    BranchId("b1"): PersistentObjectId("pb1"),
                    TaskId("t1"): PersistentObjectId("pt1"),
                }
            }
        ),
        workers=[],
        persistent_branches={
            PersistentObjectId("pb1"): PersistentBranch(
                id=PersistentObjectId("pb1"),
                versions={version_id: branch},
            ),
        },
        persistent_tasks={
            PersistentObjectId("pt1"): PersistentTask(
                id=PersistentObjectId("pt1"),
                versions={
                    version_id: Task(
                        id=TaskId("t1"),
                        title="Task 1",
                        description="Test",
                        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
                    )
                },
            ),
        },
    )

    # This should return False because the source node is a branch, not a task
    # (line 567 - source_persistent_id not in project.persistent_tasks)
    result = has_required_exclusion_dependency(project, TaskId("b1"), TaskId("t1"))
    assert result is False


def test_has_required_exclusion_dependency_task_missing_version() -> None:
    """Test has_required_exclusion_dependency when task missing current version."""
    from fluxx.data.validation import has_required_exclusion_dependency

    now = datetime.now(UTC)
    metadata = ProjectMetadata(name="Test", created=now, last_modified=now)
    version_id = DAGVersionId("v1")
    old_version_id = DAGVersionId("v0")
    dag = DAG(id=DAGId("dag1"), current_version_id=version_id)

    # Task that only exists in old version, not current version
    old_task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    project = Project(
        metadata=metadata,
        dag=dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    TaskId("t2"): PersistentObjectId("pt2"),
                }
            }
        ),
        workers=[],
        persistent_tasks={
            PersistentObjectId("pt1"): PersistentTask(
                id=PersistentObjectId("pt1"),
                versions={old_version_id: old_task},  # Only old version, not current!
            ),
            PersistentObjectId("pt2"): PersistentTask(
                id=PersistentObjectId("pt2"),
                versions={
                    version_id: Task(
                        id=TaskId("t2"),
                        title="Task 2",
                        description="Test",
                        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
                    )
                },
            ),
        },
    )

    # This should return False because the task doesn't have current version
    # (line 572 - current_version not in persistent_task.versions)
    result = has_required_exclusion_dependency(project, TaskId("t1"), TaskId("t2"))
    assert result is False


def test_get_required_exclusion_dependency() -> None:
    """Test the get_required_exclusion_dependency helper function."""
    from fluxx.data.validation import get_required_exclusion_dependency

    dep = get_required_exclusion_dependency(TaskId("t2"))

    assert dep.source_endpoint == Endpoint.START
    assert dep.target_node_id == TaskId("t2")
    assert dep.target_endpoint == Endpoint.START
    assert dep.constraint_type == ConstraintType.GREATER_EQUAL


def test_validate_excluded_assignee_raises_error() -> None:
    """Test that validate_excluded_assignee raises error without dependency."""
    from fluxx.data.validation import validate_excluded_assignee

    now = datetime.now(UTC)
    metadata = ProjectMetadata(name="Test", created=now, last_modified=now)
    version_id = DAGVersionId("v1")
    dag = DAG(id=DAGId("dag1"), current_version_id=version_id)

    # Task without required dependency
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    project = Project(
        metadata=metadata,
        dag=dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt1"),
                    TaskId("t2"): PersistentObjectId("pt2"),
                }
            }
        ),
        workers=[],
        persistent_tasks={
            PersistentObjectId("pt1"): PersistentTask(
                id=PersistentObjectId("pt1"),
                versions={version_id: task},
            ),
            PersistentObjectId("pt2"): PersistentTask(
                id=PersistentObjectId("pt2"),
                versions={
                    version_id: Task(
                        id=TaskId("t2"),
                        title="Task 2",
                        description="Test",
                        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
                    )
                },
            ),
        },
    )

    with pytest.raises(WorkerConstraintError, match="Missing required dependency"):
        validate_excluded_assignee(project, TaskId("t1"), TaskId("t2"))


def test_task_missing_current_version_in_hierarchy_check(
    base_project: Project,
) -> None:
    """Test validation skips tasks missing current version during hierarchy check."""
    # Create a task that exists in node_map but not in current version
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create persistent task with a DIFFERENT version, not current version
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={DAGVersionId("old_version"): task},  # Not current version!
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    # Should pass - validation skips tasks not in current version
    validate_dag(project)


def test_parent_references_child_not_in_node_map(base_project: Project) -> None:
    """Test error when parent references child not in node_map."""
    # Create a parent that claims to have a child, but the child is not in node_map
    parent = Task(
        id=TaskId("t_parent"),
        title="Parent",
        description="Test",
        children=[TaskId("t_nonexistent_child")],  # Child doesn't exist
    )

    persistent_parent = PersistentTask(
        id=PersistentObjectId("pp"),
        versions={base_project.dag.current_version_id: parent},
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t_parent"): PersistentObjectId("pp"),
                    # nonexistent_child is NOT in node_map
                }
            }
        ),
        persistent_tasks={PersistentObjectId("pp"): persistent_parent},
    )

    with pytest.raises(HierarchyError, match="non-existent child"):
        validate_dag(project)


def test_child_missing_current_version_in_hierarchy_check(
    base_project: Project,
) -> None:
    """Test validation skips when child task missing current version."""
    parent = Task(
        id=TaskId("t_parent"),
        title="Parent",
        description="Test",
        children=[TaskId("t_child")],
    )
    child = Task(
        id=TaskId("t_child"),
        title="Child",
        description="Test",
        parent_id=TaskId("t_parent"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_parent = PersistentTask(
        id=PersistentObjectId("pp"),
        versions={base_project.dag.current_version_id: parent},
    )
    # Child exists but not in current version
    persistent_child = PersistentTask(
        id=PersistentObjectId("pc"),
        versions={DAGVersionId("old_version"): child},  # Not current version!
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t_parent"): PersistentObjectId("pp"),
                    TaskId("t_child"): PersistentObjectId("pc"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pp"): persistent_parent,
            PersistentObjectId("pc"): persistent_child,
        },
    )

    # Should pass - validation skips children not in current version
    # Parent has children list, and even though child doesn't exist in current
    # version, the parent is not a leaf task (it has children in its list)
    validate_dag(project)


def test_task_missing_current_version_in_worker_check(
    base_project: Project,
) -> None:
    """Test validation skips tasks missing current version during worker check."""
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[WorkerId("w1")],
    )

    # Create persistent task with a DIFFERENT version, not current version
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={DAGVersionId("old_version"): task},  # Not current version!
    )

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {TaskId("t1"): PersistentObjectId("pt1")}}
        ),
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    # Should pass - validation skips tasks not in current version
    validate_dag(project)


def test_cycle_detection_visits_isolated_end_endpoint(
    base_project: Project,
) -> None:
    """Test that cycle detection visits END endpoints separately from START.

    This ensures line 160 in validation.py (dfs for END endpoint) is covered.
    We create a scenario where:
    - Task X's START is visited during another task's DFS
    - Task X's END is in the graph (has outgoing edges) but wasn't visited yet
    - So when we iterate to task X, START is already black, but END needs DFS
    """
    # Task ordering matters - we'll visit them alphabetically: a, b, x
    # Task A depends on X.start, so DFS from A will visit X.start
    task_a_id = TaskId("t1")
    task_b_id = TaskId("t2")
    task_x_id = TaskId("t3")
    branch_id = BranchId("b1")
    task_a = Task(
        id=task_a_id,
        title="Task A",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=task_x_id,
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )
    # Task X: Its START will be visited by A's DFS, but END has separate edges
    task_x = Task(
        id=task_x_id,
        title="Task X",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=branch_id,
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )
    # Task B: endpoint for X
    task_b = Task(
        id=task_b_id,
        title="Task B",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_tasks = {
        PersistentObjectId("pa"): PersistentTask(
            id=PersistentObjectId("pa"),
            versions={base_project.dag.current_version_id: task_a},
        ),
        PersistentObjectId("px"): PersistentTask(
            id=PersistentObjectId("px"),
            versions={base_project.dag.current_version_id: task_x},
        ),
        PersistentObjectId("pb"): PersistentTask(
            id=PersistentObjectId("pb"),
            versions={base_project.dag.current_version_id: task_b},
        ),
    }

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    task_a_id: PersistentObjectId("pa"),
                    task_x_id: PersistentObjectId("px"),
                    branch_id: PersistentObjectId("pb"),
                }
            }
        ),
        persistent_tasks=persistent_tasks,
    )

    # Should pass - no cycle, ensures END endpoint DFS is triggered separately
    validate_dag(project)


def test_validate_dependency_with_invalid_target_id_pattern(
    base_project: Project,
) -> None:
    """Test that validate_dependency raises error for invalid target ID pattern."""
    from fluxx.data.validation import ValidationError, validate_dependency

    task_id = TaskId("t1")
    # Create task with invalid target ID that doesn't match any pattern
    # Cast is justified: we're testing error handling for malformed data
    task = Task(
        id=task_id,
        title="Test",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("invalid_pattern_xyz"),  # Invalid pattern
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    persistent_tasks = {
        PersistentObjectId("p1"): PersistentTask(
            id=PersistentObjectId("p1"),
            versions={base_project.dag.current_version_id: task},
        ),
    }

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {task_id: PersistentObjectId("p1")}}
        ),
        persistent_tasks=persistent_tasks,
    )

    with pytest.raises(ValidationError, match="does not match a known ID type"):
        validate_dependency(project, task_id, task.dependencies[0])


def test_validate_dependency_with_nonexistent_possible_world_branch(
    base_project: Project,
) -> None:
    """Test validation when possible world references non-existent branch."""
    from fluxx.data.models import PossibleWorldReference
    from fluxx.data.validation import ValidationError, validate_dependency

    task_id = TaskId("t1")
    task = Task(
        id=task_id,
        title="Test",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=PossibleWorldReference("b_nonexistent:pw1"),
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    persistent_tasks = {
        PersistentObjectId("p1"): PersistentTask(
            id=PersistentObjectId("p1"),
            versions={base_project.dag.current_version_id: task},
        ),
    }

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={"node_map": {task_id: PersistentObjectId("p1")}}
        ),
        persistent_tasks=persistent_tasks,
    )

    with pytest.raises(ValidationError, match="non-existent branch"):
        validate_dependency(project, task_id, task.dependencies[0])


def test_validate_dependency_with_task_id_mapped_to_branch(
    base_project: Project,
) -> None:
    """Test validation when persistent ID for branch is in wrong collection."""
    from fluxx.data.models import PossibleWorldReference
    from fluxx.data.validation import ValidationError, validate_dependency

    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    pw_ref = PossibleWorldReference(f"{branch_id}:pw1")

    task = Task(
        id=task_id,
        title="Test",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=pw_ref,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Map branch_id to a task persistent object (wrong type)
    persistent_tasks = {
        PersistentObjectId("p1"): PersistentTask(
            id=PersistentObjectId("p1"),
            versions={base_project.dag.current_version_id: task},
        ),
        PersistentObjectId("pb"): PersistentTask(
            id=PersistentObjectId("pb"),
            versions={
                base_project.dag.current_version_id: Task(
                    id=TaskId("fake"),
                    title="Fake",
                    description="",
                    duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
                )
            },
        ),
    }

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    task_id: PersistentObjectId("p1"),
                    branch_id: PersistentObjectId("pb"),  # Branch ID mapped to task
                }
            }
        ),
        persistent_tasks=persistent_tasks,
    )

    with pytest.raises(ValidationError, match="not a branch"):
        validate_dependency(project, task_id, task.dependencies[0])


def test_validate_dependency_with_branch_not_in_current_version(
    base_project: Project,
) -> None:
    """Test validation when branch exists but not in current version."""
    from fluxx.data.models import (
        Branch,
        PersistentBranch,
        PossibleWorld,
        PossibleWorldReference,
    )
    from fluxx.data.validation import ValidationError, validate_dependency

    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    pw_ref = PossibleWorldReference(f"{branch_id}:pw1")

    task = Task(
        id=task_id,
        title="Test",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=pw_ref,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create branch but only in old version, not current version
    old_version = DAGVersionId("old_v1")
    branch = Branch(
        id=branch_id,
        title="Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="World 1")],
    )

    persistent_tasks = {
        PersistentObjectId("p1"): PersistentTask(
            id=PersistentObjectId("p1"),
            versions={base_project.dag.current_version_id: task},
        ),
    }

    persistent_branches = {
        PersistentObjectId("pb"): PersistentBranch(
            id=PersistentObjectId("pb"),
            versions={old_version: branch},  # Only in old version
        ),
    }

    project = Project(
        **base_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    task_id: PersistentObjectId("p1"),
                    branch_id: PersistentObjectId("pb"),
                }
            }
        ),
        persistent_tasks=persistent_tasks,
        persistent_branches=persistent_branches,
    )

    with pytest.raises(ValidationError, match="does not exist in current version"):
        validate_dependency(project, task_id, task.dependencies[0])


def test_validate_dependency_with_nonexistent_possible_world_in_branch(
    base_project: Project,
) -> None:
    """Test validation when possible world doesn't exist in branch."""
    from fluxx.data.models import (
        Branch,
        PersistentBranch,
        PossibleWorld,
        PossibleWorldReference,
    )
    from fluxx.data.validation import ValidationError, validate_dependency

    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    pw_ref = PossibleWorldReference(f"{branch_id}:pw_nonexistent")

    task = Task(
        id=task_id,
        title="Test",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=pw_ref,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    branch = Branch(
        id=branch_id,
        title="Branch",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1"),
            PossibleWorld(id=PossibleWorldId("pw2"), title="World 2"),
        ],
    )

    persistent_tasks = {
        PersistentObjectId("p1"): PersistentTask(
            id=PersistentObjectId("p1"),
            versions={base_project.dag.current_version_id: task},
        ),
    }

    persistent_branches = {
        PersistentObjectId("pb"): PersistentBranch(
            id=PersistentObjectId("pb"),
            versions={base_project.dag.current_version_id: branch},
        ),
    }

    project = Project(
        **base_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    task_id: PersistentObjectId("p1"),
                    branch_id: PersistentObjectId("pb"),
                }
            }
        ),
        persistent_tasks=persistent_tasks,
        persistent_branches=persistent_branches,
    )

    with pytest.raises(ValidationError, match="non-existent possible world"):
        validate_dependency(project, task_id, task.dependencies[0])


def test_validate_dependency_target_is_task_but_persistent_id_is_branch(
    base_project: Project,
) -> None:
    """Test validation when target TaskId is mapped to a branch persistent object."""
    from fluxx.data.models import Branch, PersistentBranch, PossibleWorld
    from fluxx.data.validation import ValidationError, validate_dependency

    task1_id = TaskId("t1")
    task2_id = TaskId("t2")  # Will be mapped to a branch

    task1 = Task(
        id=task1_id,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task2_id,
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    branch = Branch(
        id=BranchId("b_fake"),
        title="Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="World 1")],
    )

    persistent_tasks = {
        PersistentObjectId("p1"): PersistentTask(
            id=PersistentObjectId("p1"),
            versions={base_project.dag.current_version_id: task1},
        ),
    }

    persistent_branches = {
        PersistentObjectId("pb"): PersistentBranch(
            id=PersistentObjectId("pb"),
            versions={base_project.dag.current_version_id: branch},
        ),
    }

    project = Project(
        **base_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    task1_id: PersistentObjectId("p1"),
                    task2_id: PersistentObjectId("pb"),  # Task ID mapped to branch
                }
            }
        ),
        persistent_tasks=persistent_tasks,
        persistent_branches=persistent_branches,
    )

    with pytest.raises(ValidationError, match="not a task"):
        validate_dependency(project, task1_id, task1.dependencies[0])


def test_validate_dependency_target_is_branch_but_persistent_id_is_task(
    base_project: Project,
) -> None:
    """Test validation when target BranchId is mapped to a task persistent object."""
    from fluxx.data.validation import ValidationError, validate_dependency

    task_id = TaskId("t1")
    branch_id = BranchId("b1")  # Will be mapped to a task

    task = Task(
        id=task_id,
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=branch_id,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    fake_task = Task(
        id=TaskId("fake"),
        title="Fake",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_tasks = {
        PersistentObjectId("p1"): PersistentTask(
            id=PersistentObjectId("p1"),
            versions={base_project.dag.current_version_id: task},
        ),
        PersistentObjectId("pfake"): PersistentTask(
            id=PersistentObjectId("pfake"),
            versions={base_project.dag.current_version_id: fake_task},
        ),
    }

    project = Project(
        **base_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    task_id: PersistentObjectId("p1"),
                    branch_id: PersistentObjectId("pfake"),  # Branch ID mapped to task
                }
            }
        ),
        persistent_tasks=persistent_tasks,
    )

    with pytest.raises(ValidationError, match="not a branch"):
        validate_dependency(project, task_id, task.dependencies[0])


def test_validate_dependency_possible_world_with_non_occurrence_endpoint(
    base_project: Project,
) -> None:
    """Test that possible world dependencies must use OCCURRENCE endpoint."""
    from fluxx.data.models import (
        Branch,
        PersistentBranch,
        PossibleWorld,
        PossibleWorldReference,
    )
    from fluxx.data.validation import EndpointError, validate_dependency

    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    pw_ref = PossibleWorldReference(f"{branch_id}:pw1")

    task = Task(
        id=task_id,
        title="Test",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=pw_ref,
                target_endpoint=Endpoint.START,  # Invalid for possible world
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    branch = Branch(
        id=branch_id,
        title="Branch",
        description="Test",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="World 1")],
    )

    persistent_tasks = {
        PersistentObjectId("p1"): PersistentTask(
            id=PersistentObjectId("p1"),
            versions={base_project.dag.current_version_id: task},
        ),
    }

    persistent_branches = {
        PersistentObjectId("pb"): PersistentBranch(
            id=PersistentObjectId("pb"),
            versions={base_project.dag.current_version_id: branch},
        ),
    }

    project = Project(
        **base_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    task_id: PersistentObjectId("p1"),
                    branch_id: PersistentObjectId("pb"),
                }
            }
        ),
        persistent_tasks=persistent_tasks,
        persistent_branches=persistent_branches,
    )

    with pytest.raises(EndpointError, match="can only use OCCURRENCE endpoint"):
        validate_dependency(project, task_id, task.dependencies[0])


def test_add_dep_edge_with_invalid_target_id() -> None:
    """Test add_dep_edge with invalid target ID pattern."""
    from collections import defaultdict

    from fluxx.data.models import Endpoint, NodeId, PossibleWorldId
    from fluxx.data.validation import ValidationError, add_dep_edge

    graph: dict[
        tuple[NodeId | PossibleWorldId, Endpoint],
        list[tuple[NodeId | PossibleWorldId, Endpoint]],
    ] = defaultdict(list)

    source_id = TaskId("t1")
    target_id = TaskId("invalid_xyz")  # Invalid pattern

    with pytest.raises(ValidationError, match="Invalid dependency target ID"):
        add_dep_edge(
            source_id,
            Endpoint.START,
            target_id,
            Endpoint.START,
            graph,
        )


def test_add_dep_edge_with_possible_world_reference() -> None:
    """Test add_dep_edge correctly handles possible world references."""
    from collections import defaultdict

    from fluxx.data.models import (
        Endpoint,
        NodeId,
        PossibleWorldId,
        PossibleWorldReference,
    )
    from fluxx.data.validation import add_dep_edge

    graph: dict[
        tuple[NodeId | PossibleWorldId, Endpoint],
        list[tuple[NodeId | PossibleWorldId, Endpoint]],
    ] = defaultdict(list)

    source_id = TaskId("t1")
    branch_id = BranchId("b1")
    pw_ref = PossibleWorldReference(f"{branch_id}:pw1")

    # Should add edge from branch OCCURRENCE to task START
    add_dep_edge(
        source_id,
        Endpoint.START,
        pw_ref,
        Endpoint.END,  # This will be overridden to OCCURRENCE for possible worlds
        graph,
    )

    # Check that the edge was added correctly
    # Edge should be: (branch_id, OCCURRENCE) -> (source_id, START)
    assert (source_id, Endpoint.START) in graph[(branch_id, Endpoint.OCCURRENCE)]


def test_add_dep_edge_with_all_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test add_dep_edge defensive error handling.

    Tests the case when type_explode_id returns all None.
    """
    from collections import defaultdict

    from fluxx.data import validation
    from fluxx.data.models import DependencyTargetId, Endpoint, NodeId, PossibleWorldId
    from fluxx.data.validation import ValidationError, add_dep_edge

    graph: dict[
        tuple[NodeId | PossibleWorldId, Endpoint],
        list[tuple[NodeId | PossibleWorldId, Endpoint]],
    ] = defaultdict(list)

    source_id = TaskId("t1")
    target_id = TaskId("t2")

    # Mock type_explode_id to return all None (impossible in reality)
    def mock_type_explode_id(
        ref: DependencyTargetId,
    ) -> tuple[TaskId | None, BranchId | None, PossibleWorldReferencePair | None]:
        return None, None, None

    monkeypatch.setattr(validation, "type_explode_id", mock_type_explode_id)

    with pytest.raises(ValidationError, match="Forgot dependency target type"):
        add_dep_edge(
            source_id,
            Endpoint.START,
            target_id,
            Endpoint.START,
            graph,
        )


def test_validate_dependency_with_all_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test validate_dependency defensive error handling.

    Tests the case when type_explode_id returns all None.
    """
    from fluxx.data import validation

    # Create minimal project
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test",
        created=now,
        last_modified=now,
    )
    dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))
    worker = Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0)

    task_id = TaskId("t1")
    task = Task(
        id=task_id,
        title="Test",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t2"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    project = Project(
        metadata=metadata,
        dag=dag.model_copy(update={"node_map": {task_id: PersistentObjectId("p1")}}),
        workers=[worker],
        persistent_tasks={
            PersistentObjectId("p1"): PersistentTask(
                id=PersistentObjectId("p1"),
                versions={dag.current_version_id: task},
            ),
        },
    )

    # Mock type_explode_id to return all None (impossible in reality)
    from fluxx.data.models import DependencyTargetId as DepTargetId

    def mock_type_explode_id(
        ref: DepTargetId,
    ) -> tuple[TaskId | None, BranchId | None, PossibleWorldReferencePair | None]:
        return None, None, None

    monkeypatch.setattr(validation, "type_explode_id", mock_type_explode_id)

    # This should raise AssertionError from the defensive code
    with pytest.raises(AssertionError, match="Forgot to add pattern"):
        validation.validate_dependency(project, task_id, task.dependencies[0])


def test_cycle_detection_dfs_visits_end_endpoint_separately() -> None:
    """Test that cycle detection DFS visits END endpoint when it has its own edges.

    This covers line 173 in validation.py - the DFS call for END endpoints.
    """
    from fluxx.data.validation import validate_dag

    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test",
        created=now,
        last_modified=now,
    )
    dag_id = DAGId("dag1")
    version_id = DAGVersionId("v1")
    dag = DAG(id=dag_id, current_version_id=version_id)
    worker = Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0)

    # Create tasks where:
    # - Task A's START is visited first (via DFS from another task)
    # - Task A's END has its own dependencies and must be visited separately
    task_a_id = TaskId("t1")
    task_b_id = TaskId("t2")
    task_c_id = TaskId("t3")

    # Task A has dependency from its END endpoint
    task_a = Task(
        id=task_a_id,
        title="Task A",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            # Dependency from END endpoint
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=task_c_id,
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Task B depends on Task A's START
    task_b = Task(
        id=task_b_id,
        title="Task B",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task_a_id,
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    task_c = Task(
        id=task_c_id,
        title="Task C",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    project = Project(
        metadata=metadata,
        dag=dag.model_copy(
            update={
                "node_map": {
                    task_a_id: PersistentObjectId("pa"),
                    task_b_id: PersistentObjectId("pb"),
                    task_c_id: PersistentObjectId("pc"),
                }
            }
        ),
        workers=[worker],
        persistent_tasks={
            PersistentObjectId("pa"): PersistentTask(
                id=PersistentObjectId("pa"),
                versions={version_id: task_a},
            ),
            PersistentObjectId("pb"): PersistentTask(
                id=PersistentObjectId("pb"),
                versions={version_id: task_b},
            ),
            PersistentObjectId("pc"): PersistentTask(
                id=PersistentObjectId("pc"),
                versions={version_id: task_c},
            ),
        },
    )

    # Should validate without cycles
    # This exercises the END endpoint DFS when:
    # - task_a.START is visited first during another DFS
    # - task_a.END needs separate DFS because it has outgoing edges
    validate_dag(project)


# =============================================================================
# Completion Validation Tests
# =============================================================================


def test_validate_completion_change_no_dependencies() -> None:
    """Test that a task with no dependencies can be started."""

    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    worker_id = WorkerId("w1")

    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={task_id: PersistentObjectId("p1")},
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("p1"): PersistentTask(
                id=PersistentObjectId("p1"),
                versions={version_id: task},
            ),
        },
    )

    # Should be able to start the task
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert errors == []


def test_validate_completion_change_depends_on_incomplete_task() -> None:
    """Test that starting fails if depending on incomplete task's end."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_a_id = TaskId("t1")
    task_b_id = TaskId("t2")
    worker_id = WorkerId("w1")

    # Task A is not started
    task_a = Task(
        id=task_a_id,
        title="Task A",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    # Task B depends on Task A's end
    task_b = Task(
        id=task_b_id,
        title="Task B",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task_a_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_a_id: PersistentObjectId("pa"),
                task_b_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pa"): PersistentTask(
                id=PersistentObjectId("pa"),
                versions={version_id: task_a},
            ),
            PersistentObjectId("pb"): PersistentTask(
                id=PersistentObjectId("pb"),
                versions={version_id: task_b},
            ),
        },
    )

    # Try to start Task B - should fail because Task A is not complete
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_b_id, new_completion)
    assert len(errors) == 1
    assert "Task A" in errors[0]
    assert "not yet complete" in errors[0]


def test_validate_completion_change_depends_on_unstarted_task() -> None:
    """Test that starting fails if depending on unstarted task's start."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_a_id = TaskId("t1")
    task_b_id = TaskId("t2")
    worker_id = WorkerId("w1")

    # Task A is not started
    task_a = Task(
        id=task_a_id,
        title="Task A",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    # Task B depends on Task A's start
    task_b = Task(
        id=task_b_id,
        title="Task B",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task_a_id,
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_a_id: PersistentObjectId("pa"),
                task_b_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pa"): PersistentTask(
                id=PersistentObjectId("pa"),
                versions={version_id: task_a},
            ),
            PersistentObjectId("pb"): PersistentTask(
                id=PersistentObjectId("pb"),
                versions={version_id: task_b},
            ),
        },
    )

    # Try to start Task B - should fail because Task A has not started
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_b_id, new_completion)
    assert len(errors) == 1
    assert "Task A" in errors[0]
    assert "not started yet" in errors[0]


def test_validate_completion_change_start_time_before_dependency() -> None:
    """Test that start time before dependency's start time fails."""
    from datetime import timedelta

    from fluxx.data.models import StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_a_id = TaskId("t1")
    task_b_id = TaskId("t2")
    worker_id = WorkerId("w1")

    # Task A is started
    task_a = Task(
        id=task_a_id,
        title="Task A",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=StartedCompletion(
            assignee=worker_id,
            start_time=now,
            hours_logged=0.0,
        ),
    )

    # Task B depends on Task A's start
    task_b = Task(
        id=task_b_id,
        title="Task B",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task_a_id,
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=StartedCompletion(
            assignee=worker_id,
            start_time=now + timedelta(hours=1),
            hours_logged=0.0,
        ),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_a_id: PersistentObjectId("pa"),
                task_b_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pa"): PersistentTask(
                id=PersistentObjectId("pa"),
                versions={version_id: task_a},
            ),
            PersistentObjectId("pb"): PersistentTask(
                id=PersistentObjectId("pb"),
                versions={version_id: task_b},
            ),
        },
    )

    # Try to change Task B's start time to before Task A started
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now - timedelta(hours=1),  # Before Task A started
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_b_id, new_completion)
    assert len(errors) == 1
    assert "must be after" in errors[0]
    assert "Task A" in errors[0]


def test_validate_completion_change_depends_on_unresolved_branch() -> None:
    """Test that starting fails if depending on unresolved branch."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    worker_id = WorkerId("w1")

    # Branch is not resolved
    branch = Branch(
        id=branch_id,
        title="Branch",
        description="",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("w1"), title="World 1", weight=1.0),
            PossibleWorld(id=PossibleWorldId("w2"), title="World 2", weight=1.0),
        ],
        dependencies=[],
        chosen_world_id=None,
    )

    # Task depends on the branch
    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=branch_id,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pt"),
                branch_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={version_id: task},
            ),
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={version_id: branch},
            ),
        },
    )

    # Try to start the task - should fail because branch is not resolved
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert len(errors) == 1
    assert "Branch" in errors[0]
    assert "not yet resolved" in errors[0]


def test_validate_completion_change_depends_on_wrong_possible_world() -> None:
    """Test that starting fails if depending on unchosen possible world."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    worker_id = WorkerId("w1")
    world_1_id = PossibleWorldId("world_1")
    world_2_id = PossibleWorldId("world_2")

    # Branch is resolved to World 2
    branch = Branch(
        id=branch_id,
        title="Branch",
        description="",
        possible_worlds=[
            PossibleWorld(id=world_1_id, title="World 1", weight=1.0),
            PossibleWorld(id=world_2_id, title="World 2", weight=1.0),
        ],
        dependencies=[],
        chosen_world_id=world_2_id,
    )

    # Task depends on World 1 (which was not chosen)
    # Use string format for possible world reference: branch_id:world_id
    from fluxx.data.models import PossibleWorldReference

    world_ref = PossibleWorldReference(f"{branch_id}:{world_1_id}")
    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=world_ref,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pt"),
                branch_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={version_id: task},
            ),
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={version_id: branch},
            ),
        },
    )

    # Try to start the task - should fail because World 1 was not chosen
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert len(errors) == 1
    assert "World 1" in errors[0]
    assert "World 2" in errors[0]


def test_validate_completion_change_satisfied_dependencies() -> None:
    """Test that starting succeeds with all dependencies satisfied."""
    from datetime import timedelta

    from fluxx.data.models import (
        DoneCompletion,
        NotStartedCompletion,
        StartedCompletion,
    )
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_a_id = TaskId("t1")
    task_b_id = TaskId("t2")
    worker_id = WorkerId("w1")

    # Task A is done
    task_a = Task(
        id=task_a_id,
        title="Task A",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=DoneCompletion(
            assignee=worker_id,
            start_time=now - timedelta(days=1),
            hours_logged=8.0,
            end_time=now - timedelta(hours=1),
        ),
    )

    # Task B depends on Task A's end
    task_b = Task(
        id=task_b_id,
        title="Task B",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task_a_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_a_id: PersistentObjectId("pa"),
                task_b_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pa"): PersistentTask(
                id=PersistentObjectId("pa"),
                versions={version_id: task_a},
            ),
            PersistentObjectId("pb"): PersistentTask(
                id=PersistentObjectId("pb"),
                versions={version_id: task_b},
            ),
        },
    )

    # Start Task B after Task A ended - should succeed
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,  # After Task A ended
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_b_id, new_completion)
    assert errors == []


def test_validate_completion_change_task_not_found() -> None:
    """Test validation fails for non-existent task."""
    from fluxx.data.models import StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    worker_id = WorkerId("w1")

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={},
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
    )

    # Try to start a non-existent task
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(
        project, TaskId("t_nonexistent"), new_completion
    )
    assert len(errors) == 1
    assert "not found" in errors[0]


def test_validate_completion_change_start_time_before_end_dependency() -> None:
    """Test that start time before dependency's end time fails."""
    from datetime import timedelta

    from fluxx.data.models import (
        DoneCompletion,
        NotStartedCompletion,
        StartedCompletion,
    )
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_a_id = TaskId("t1")
    task_b_id = TaskId("t2")
    worker_id = WorkerId("w1")

    # Task A is completed
    task_a = Task(
        id=task_a_id,
        title="Task A",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=DoneCompletion(
            assignee=worker_id,
            start_time=now - timedelta(days=1),
            hours_logged=8.0,
            end_time=now,
        ),
    )

    # Task B depends on Task A's end
    task_b = Task(
        id=task_b_id,
        title="Task B",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task_a_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_a_id: PersistentObjectId("pa"),
                task_b_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pa"): PersistentTask(
                id=PersistentObjectId("pa"),
                versions={version_id: task_a},
            ),
            PersistentObjectId("pb"): PersistentTask(
                id=PersistentObjectId("pb"),
                versions={version_id: task_b},
            ),
        },
    )

    # Try to start Task B before Task A ended
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now - timedelta(hours=1),  # Before Task A ended
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_b_id, new_completion)
    assert len(errors) == 1
    assert "must be after" in errors[0]
    assert "Task A" in errors[0]
    assert "completed at" in errors[0]


def test_validate_completion_change_resolved_branch_dependency() -> None:
    """Test that starting succeeds when depending on resolved branch."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    worker_id = WorkerId("w1")

    # Branch is resolved
    branch = Branch(
        id=branch_id,
        title="Branch",
        description="",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("w1"), title="World 1", weight=1.0),
            PossibleWorld(id=PossibleWorldId("w2"), title="World 2", weight=1.0),
        ],
        dependencies=[],
        chosen_world_id=PossibleWorldId("w1"),
    )

    # Task depends on the branch
    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=branch_id,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pt"),
                branch_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={version_id: task},
            ),
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={version_id: branch},
            ),
        },
    )

    # Start the task - should succeed because branch is resolved
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert errors == []


def test_validate_completion_change_chosen_possible_world() -> None:
    """Test that starting succeeds when depending on chosen possible world."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    worker_id = WorkerId("w1")
    world_1_id = PossibleWorldId("world_1")
    world_2_id = PossibleWorldId("world_2")

    # Branch is resolved to World 1
    branch = Branch(
        id=branch_id,
        title="Branch",
        description="",
        possible_worlds=[
            PossibleWorld(id=world_1_id, title="World 1", weight=1.0),
            PossibleWorld(id=world_2_id, title="World 2", weight=1.0),
        ],
        dependencies=[],
        chosen_world_id=world_1_id,
    )

    # Task depends on World 1 (which IS chosen)
    from fluxx.data.models import PossibleWorldReference

    world_ref = PossibleWorldReference(f"{branch_id}:{world_1_id}")
    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=world_ref,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pt"),
                branch_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={version_id: task},
            ),
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={version_id: branch},
            ),
        },
    )

    # Start the task - should succeed because World 1 is chosen
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert errors == []


def test_validate_completion_change_unresolved_possible_world() -> None:
    """Test that starting fails for possible world of unresolved branch."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    worker_id = WorkerId("w1")
    world_1_id = PossibleWorldId("world_1")
    world_2_id = PossibleWorldId("world_2")

    # Branch is NOT resolved
    branch = Branch(
        id=branch_id,
        title="Branch",
        description="",
        possible_worlds=[
            PossibleWorld(id=world_1_id, title="World 1", weight=1.0),
            PossibleWorld(id=world_2_id, title="World 2", weight=1.0),
        ],
        dependencies=[],
        chosen_world_id=None,
    )

    # Task depends on World 1
    from fluxx.data.models import PossibleWorldReference

    world_ref = PossibleWorldReference(f"{branch_id}:{world_1_id}")
    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=world_ref,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pt"),
                branch_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={version_id: task},
            ),
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={version_id: branch},
            ),
        },
    )

    # Try to start the task - should fail because branch is not resolved
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert len(errors) == 1
    assert "unresolved" in errors[0]


def test_validate_completion_change_node_is_branch_not_task() -> None:
    """Test that validating a branch ID (not task) returns error."""
    from fluxx.data.models import StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    branch_id = BranchId("b1")
    worker_id = WorkerId("w1")

    branch = Branch(
        id=branch_id,
        title="Branch",
        description="",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("world_1"), title="World 1", weight=1.0),
        ],
        dependencies=[],
        chosen_world_id=None,
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                branch_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={},
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={version_id: branch},
            ),
        },
    )

    # Try to validate a branch ID as if it were a task
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    # Pass branch_id where task_id is expected
    errors = validate_completion_change(project, TaskId(branch_id), new_completion)
    assert len(errors) == 1
    assert "not a task" in errors[0]


def test_validate_completion_change_task_not_in_current_version() -> None:
    """Test validation when task exists but not in current version."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    other_version = DAGVersionId("v2")
    task_id = TaskId("t1")
    worker_id = WorkerId("w1")

    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    # Task exists but only in a different version (not current)
    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,  # Current version is v1
            node_map={
                task_id: PersistentObjectId("pt"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={other_version: task},  # But task is only in v2
            ),
        },
        persistent_branches={},
    )

    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert len(errors) == 1
    assert "not in current version" in errors[0]


def test_validate_completion_change_skips_end_dependencies() -> None:
    """Test that END endpoint dependencies are skipped during validation."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task1_id = TaskId("t1")
    task2_id = TaskId("t2")
    worker_id = WorkerId("w1")

    # Task 2 is NOT started - would fail START dependency validation
    task2 = Task(
        id=task2_id,
        title="Task 2",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    # Task 1 has END dependency on task 2 (END >= task2.END)
    # This should be skipped, not validated
    task1 = Task(
        id=task1_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,  # END dependency, not START
                target_node_id=task2_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task1_id: PersistentObjectId("pt1"),
                task2_id: PersistentObjectId("pt2"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt1"): PersistentTask(
                id=PersistentObjectId("pt1"),
                versions={version_id: task1},
            ),
            PersistentObjectId("pt2"): PersistentTask(
                id=PersistentObjectId("pt2"),
                versions={version_id: task2},
            ),
        },
        persistent_branches={},
    )

    # Starting task1 should succeed because END dependencies are skipped
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task1_id, new_completion)
    assert errors == []


def test_validate_completion_change_skips_equal_constraints() -> None:
    """Test that EQUAL constraint types are skipped during validation."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task1_id = TaskId("t1")
    task2_id = TaskId("t2")
    worker_id = WorkerId("w1")

    # Task 2 is NOT started
    task2 = Task(
        id=task2_id,
        title="Task 2",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    # Task 1 has EQUAL constraint (START == task2.START)
    # This should be skipped, not validated
    task1 = Task(
        id=task1_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task2_id,
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.EQUAL,  # EQUAL, not GREATER_EQUAL
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task1_id: PersistentObjectId("pt1"),
                task2_id: PersistentObjectId("pt2"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt1"): PersistentTask(
                id=PersistentObjectId("pt1"),
                versions={version_id: task1},
            ),
            PersistentObjectId("pt2"): PersistentTask(
                id=PersistentObjectId("pt2"),
                versions={version_id: task2},
            ),
        },
        persistent_branches={},
    )

    # Starting task1 should succeed because EQUAL constraints are skipped
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task1_id, new_completion)
    assert errors == []


def test_validate_completion_change_branch_dependency_not_found() -> None:
    """Test validation when branch dependency target doesn't exist."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    worker_id = WorkerId("w1")

    # Task depends on a branch that doesn't exist
    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=branch_id,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    # Branch is NOT in node_map (doesn't exist)
    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pt"),
                # branch_id is NOT in node_map
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={version_id: task},
            ),
        },
        persistent_branches={},
    )

    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert len(errors) == 1
    assert "non-existent branch" in errors[0]


def test_validate_completion_change_possible_world_branch_not_found() -> None:
    """Test validation when possible world's branch doesn't exist."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    world_id = PossibleWorldId("world_1")
    worker_id = WorkerId("w1")

    from fluxx.data.models import PossibleWorldReference

    world_ref = PossibleWorldReference(f"{branch_id}:{world_id}")

    # Task depends on a possible world whose branch doesn't exist
    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=world_ref,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    # Branch doesn't exist
    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pt"),
                # branch_id is NOT in node_map
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={version_id: task},
            ),
        },
        persistent_branches={},
    )

    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert len(errors) == 1
    assert "non-existent branch" in errors[0]


def test_validate_completion_change_target_task_not_found() -> None:
    """Test validation when target task dependency doesn't exist."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task1_id = TaskId("t1")
    task2_id = TaskId("t2")
    worker_id = WorkerId("w1")

    # Task 1 depends on task 2 which doesn't exist
    task1 = Task(
        id=task1_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task2_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    # task2_id is NOT in node_map
    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task1_id: PersistentObjectId("pt1"),
                # task2_id NOT in node_map
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt1"): PersistentTask(
                id=PersistentObjectId("pt1"),
                versions={version_id: task1},
            ),
        },
        persistent_branches={},
    )

    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task1_id, new_completion)
    assert len(errors) == 1
    assert "non-existent task" in errors[0]


def test_validate_hierarchy_with_branch_in_node_map(base_project: Project) -> None:
    """Test that validate_hierarchy skips branches in node_map."""
    # Create a valid project with both a task and a branch
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    branch = Branch(
        id=BranchId("b1"),
        title="Branch",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("world_1"), title="World 1", weight=1.0),
        ],
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt"),
        versions={base_project.dag.current_version_id: task},
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb"),
        versions={base_project.dag.current_version_id: branch},
    )

    project = Project(
        **base_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=base_project.dag.model_copy(
            update={
                "node_map": {
                    TaskId("t1"): PersistentObjectId("pt"),
                    BranchId("b1"): PersistentObjectId("pb"),  # Branch in node_map
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pt"): persistent_task,
        },
        persistent_branches={
            PersistentObjectId("pb"): persistent_branch,
        },
    )

    # Should pass - branch should be skipped, only tasks are validated
    validate_dag(project)


def test_validate_worker_constraints_with_branch_in_node_map() -> None:
    """Test that validate_worker_constraints skips branches in node_map."""
    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")

    # Task with specific worker constraint that would fail if branch was checked
    task = Task(
        id=TaskId("t1"),
        title="Task",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=[WorkerId("w1")],  # Use allowed_workers to trigger validation
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
    )

    branch = Branch(
        id=BranchId("b1"),
        title="Branch",
        description="",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("world_1"), title="World 1", weight=1.0),
        ],
        dependencies=[],
        chosen_world_id=None,
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                TaskId("t1"): PersistentObjectId("pt"),
                BranchId("b1"): PersistentObjectId("pb"),  # Branch in node_map
            },
        ),
        workers=[Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={version_id: task},
            ),
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={version_id: branch},
            ),
        },
    )

    # Should pass - branch should be skipped, only tasks are validated
    validate_dag(project)


def test_validate_completion_task_persistent_id_not_in_tasks() -> None:
    """Test when persistent_id exists but is not in persistent_tasks."""
    from fluxx.data.models import StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    worker_id = WorkerId("w1")

    # Task has persistent_id in node_map but that ID is not in persistent_tasks
    # (it's a branch ID being used where a task ID should be)
    branch = Branch(
        id=BranchId("t1"),  # Using same ID as task
        title="Branch",
        description="",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("world_1"), title="World 1", weight=1.0),
        ],
        dependencies=[],
        chosen_world_id=None,
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pb"),  # Points to a branch
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={},  # No tasks
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={version_id: branch},
            ),
        },
    )

    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert len(errors) == 1
    assert "not a task" in errors[0]


def test_validate_completion_target_task_not_in_persistent_tasks() -> None:
    """Test when dependency target has persistent_id not in persistent_tasks."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task1_id = TaskId("t1")
    task2_id = TaskId("t2")
    worker_id = WorkerId("w1")

    # Task 1 depends on task 2, but task 2's persistent_id is a branch
    task1 = Task(
        id=task1_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task2_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    branch = Branch(
        id=BranchId("t2"),  # Same as task2_id
        title="Branch",
        description="",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("world_1"), title="World 1", weight=1.0),
        ],
        dependencies=[],
        chosen_world_id=None,
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task1_id: PersistentObjectId("pt1"),
                task2_id: PersistentObjectId("pb"),  # task2 points to a branch
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt1"): PersistentTask(
                id=PersistentObjectId("pt1"),
                versions={version_id: task1},
            ),
            # No pt2 - task2's persistent_id points to a branch
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={version_id: branch},
            ),
        },
    )

    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task1_id, new_completion)
    assert len(errors) == 1
    assert "non-existent task" in errors[0]


def test_validate_completion_target_task_not_in_version() -> None:
    """Test when dependency target exists but not in current version."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    other_version = DAGVersionId("v2")
    task1_id = TaskId("t1")
    task2_id = TaskId("t2")
    worker_id = WorkerId("w1")

    # Task 1 depends on task 2, but task 2 is only in a different version
    task1 = Task(
        id=task1_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task2_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    task2 = Task(
        id=task2_id,
        title="Task 2",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task1_id: PersistentObjectId("pt1"),
                task2_id: PersistentObjectId("pt2"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt1"): PersistentTask(
                id=PersistentObjectId("pt1"),
                versions={version_id: task1},  # task1 in v1
            ),
            PersistentObjectId("pt2"): PersistentTask(
                id=PersistentObjectId("pt2"),
                versions={other_version: task2},  # task2 only in v2
            ),
        },
        persistent_branches={},
    )

    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task1_id, new_completion)
    assert len(errors) == 1
    assert "non-existent task" in errors[0]


def test_validate_completion_branch_not_in_persistent_branches() -> None:
    """Test when branch dependency has persistent_id not in persistent_branches."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    worker_id = WorkerId("w1")

    # Task depends on branch, but branch's persistent_id is a task
    task1 = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=branch_id,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    task2 = Task(
        id=TaskId("b1"),  # Same ID as branch
        title="Task 2",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pt1"),
                branch_id: PersistentObjectId("pt2"),  # branch points to a task
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt1"): PersistentTask(
                id=PersistentObjectId("pt1"),
                versions={version_id: task1},
            ),
            PersistentObjectId("pt2"): PersistentTask(
                id=PersistentObjectId("pt2"),
                versions={version_id: task2},
            ),
        },
        persistent_branches={},  # No branches
    )

    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert len(errors) == 1
    assert "non-existent branch" in errors[0]


def test_validate_completion_branch_not_in_version() -> None:
    """Test when branch dependency exists but not in current version."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    other_version = DAGVersionId("v2")
    task_id = TaskId("t1")
    branch_id = BranchId("b1")
    worker_id = WorkerId("w1")

    # Task depends on branch, but branch is only in a different version
    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=branch_id,
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    branch = Branch(
        id=branch_id,
        title="Branch",
        description="",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("world_1"), title="World 1", weight=1.0),
        ],
        dependencies=[],
        chosen_world_id=PossibleWorldId("world_1"),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pt"),
                branch_id: PersistentObjectId("pb"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={version_id: task},
            ),
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={other_version: branch},  # Branch only in v2
            ),
        },
    )

    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert len(errors) == 1
    assert "non-existent branch" in errors[0]


def test_validate_completion_invalid_dependency_target() -> None:
    """Test validation with malformed dependency target ID."""
    from fluxx.data.models import (
        DependencyTargetId,
        NotStartedCompletion,
        StartedCompletion,
    )
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    worker_id = WorkerId("w1")

    # Create a dependency with an invalid target ID format
    # "invalid_format" doesn't match task, branch, or possible world patterns
    invalid_target: DependencyTargetId = cast(TaskId, "invalid_format")

    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=invalid_target,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pt"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={version_id: task},
            ),
        },
        persistent_branches={},
    )

    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, task_id, new_completion)
    assert len(errors) == 1
    assert "Invalid dependency target" in errors[0]


def test_validate_completion_child_can_start_before_parent() -> None:
    """Test that a child task can start even if parent hasn't started."""
    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    parent_id = TaskId("t_parent")
    child_id = TaskId("t_child")
    worker_id = WorkerId("w1")

    # Parent task is NOT started
    parent_task = Task(
        id=parent_id,
        title="Parent Task",
        description="",
        duration_distribution=None,  # Parent has no duration
        dependencies=[],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[child_id],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    # Child task with implicit dependency on parent.START
    child_task = Task(
        id=child_id,
        title="Child Task",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=parent_id,
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=parent_id,  # This is a child of parent_task
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                parent_id: PersistentObjectId("pp"),
                child_id: PersistentObjectId("pc"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pp"): PersistentTask(
                id=PersistentObjectId("pp"),
                versions={version_id: parent_task},
            ),
            PersistentObjectId("pc"): PersistentTask(
                id=PersistentObjectId("pc"),
                versions={version_id: child_task},
            ),
        },
        persistent_branches={},
    )

    # Starting the child should succeed even though parent hasn't started
    # (because the parent's start is implicitly defined by the child's start)
    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )
    errors = validate_completion_change(project, child_id, new_completion)
    assert errors == []


def test_validate_completion_unknown_dependency_type() -> None:
    """Test validation when type_explode_id returns all None (mocked)."""
    from unittest.mock import patch

    from fluxx.data.models import NotStartedCompletion, StartedCompletion
    from fluxx.data.validation import validate_completion_change

    now = datetime.now(UTC)
    version_id = DAGVersionId("v1")
    task_id = TaskId("t1")
    task2_id = TaskId("t2")
    worker_id = WorkerId("w1")

    task = Task(
        id=task_id,
        title="Task 1",
        description="",
        duration_distribution=Triangular(min=1, mode=2, max=3),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task2_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
        allowed_workers=None,
        excluded_worker_tasks=[],
        children=[],
        parent_id=None,
        completion=NotStartedCompletion(),
    )

    project = Project(
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                task_id: PersistentObjectId("pt"),
            },
        ),
        workers=[Worker(id=worker_id, name="Worker 1", hours_per_workday=8.0)],
        persistent_tasks={
            PersistentObjectId("pt"): PersistentTask(
                id=PersistentObjectId("pt"),
                versions={version_id: task},
            ),
        },
        persistent_branches={},
    )

    new_completion = StartedCompletion(
        assignee=worker_id,
        start_time=now,
        hours_logged=0.0,
    )

    # Mock type_explode_id to return (None, None, None)
    with (
        patch("fluxx.data.validation.type_explode_id", return_value=(None, None, None)),
        pytest.raises(ValueError, match="Unknown dependency target type"),
    ):
        validate_completion_change(project, task_id, new_completion)
