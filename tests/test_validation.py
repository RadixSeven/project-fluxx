"""Tests for DAG validation."""

from collections.abc import Generator
from datetime import UTC, datetime

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
        id=TaskId("parent"),
        title="Parent",
        description="Test",
        children=[TaskId("child")],
    )
    child = Task(
        id=TaskId("child"),
        title="Child",
        description="Test",
        parent_id=TaskId("parent"),
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
                    TaskId("parent"): PersistentObjectId("pp"),
                    TaskId("child"): PersistentObjectId("pc"),
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
        parent_id=TaskId("nonexistent"),
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
        id=TaskId("parent"),
        title="Parent",
        description="Test",
        children=[TaskId("child")],
        duration_distribution=Triangular(
            min=1.0, mode=2.0, max=3.0
        ),  # Valid - preserved but ignored
    )
    child = Task(
        id=TaskId("child"),
        title="Child",
        description="Test",
        parent_id=TaskId("parent"),
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
                    TaskId("parent"): PersistentObjectId("pp"),
                    TaskId("child"): PersistentObjectId("pc"),
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
        validate_dependency(project, TaskId("nonexistent"), dep)


def test_validate_dependency_nonexistent_target(base_project: Project) -> None:
    """Test validating dependency with non-existent target node."""
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
        target_node_id=TaskId("nonexistent"),
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
        id=TaskId("parent"),
        title="Parent",
        description="Test",
        children=[],  # Should include child but doesn't
        duration_distribution=Triangular(
            min=1.0, mode=2.0, max=3.0
        ),  # Needs duration since it has no children
    )
    child = Task(
        id=TaskId("child"),
        title="Child",
        description="Test",
        parent_id=TaskId("parent"),
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
                    TaskId("parent"): PersistentObjectId("pp"),
                    TaskId("child"): PersistentObjectId("pc"),
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
        id=TaskId("parent"),
        title="Parent",
        description="Test",
        children=[TaskId("child")],
    )
    child = Task(
        id=TaskId("child"),
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
                    TaskId("parent"): PersistentObjectId("pp"),
                    TaskId("child"): PersistentObjectId("pc"),
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
        excluded_worker_tasks=[TaskId("nonexistent")],  # Non-existent task
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
        id=TaskId("parent"),
        title="Parent",
        description="Test",
        children=[TaskId("nonexistent_child")],  # Child doesn't exist
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
                    TaskId("parent"): PersistentObjectId("pp"),
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
        id=TaskId("parent"),
        title="Parent",
        description="Test",
        children=[TaskId("child")],
    )
    child = Task(
        id=TaskId("child"),
        title="Child",
        description="Test",
        parent_id=TaskId("parent"),
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
                    TaskId("parent"): PersistentObjectId("pp"),
                    TaskId("child"): PersistentObjectId("pc"),
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
    task_a = Task(
        id=TaskId("a"),
        title="Task A",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("x"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )
    # Task X: Its START will be visited by A's DFS, but END has separate edges
    task_x = Task(
        id=TaskId("x"),
        title="Task X",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=BranchId("b"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )
    # Task B: endpoint for X
    task_b = Task(
        id=TaskId("b"),
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
                    TaskId("a"): PersistentObjectId("pa"),
                    TaskId("x"): PersistentObjectId("px"),
                    BranchId("b"): PersistentObjectId("pb"),
                }
            }
        ),
        persistent_tasks=persistent_tasks,
    )

    # Should pass - no cycle, ensures END endpoint DFS is triggered separately
    validate_dag(project)
