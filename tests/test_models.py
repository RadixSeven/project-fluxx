"""Tests for data models."""

from datetime import UTC, datetime

import pytest

from fluxx.data.models import (
    DAG,
    Branch,
    BranchId,
    Checkpoint,
    ConstraintType,
    DAGEvent,
    DAGId,
    DAGVersionId,
    Dependency,
    Endpoint,
    EventId,
    EventType,
    NodeId,
    PersistentBranch,
    PersistentObjectId,
    PersistentTask,
    PossibleWorld,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    Sample,
    SampleId,
    ShiftedLognormal,
    Simulation,
    SimulationId,
    SimulationStatus,
    Task,
    TaskEvent,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)


def test_worker_creation() -> None:
    """Test creating a worker."""
    worker = Worker(
        id=WorkerId("w1"), name="Alice", worker_id="alice_1", hours_per_workday=8.0
    )
    assert worker.name == "Alice"
    assert worker.hours_per_workday == 8.0


def test_worker_optional_id() -> None:
    """Test that worker_id is optional."""
    worker = Worker(id=WorkerId("w1"), name="Bob", hours_per_workday=6.0)
    assert worker.worker_id is None


def test_shifted_lognormal_valid() -> None:
    """Test creating a valid shifted lognormal distribution."""
    dist = ShiftedLognormal(min=1.0, mode=5.0, percentile_95=10.0)
    assert dist.min == 1.0
    assert dist.mode == 5.0
    assert dist.percentile_95 == 10.0


def test_shifted_lognormal_mode_validation() -> None:
    """Test that mode must be > min."""
    with pytest.raises(ValueError, match="mode must be greater than min"):
        ShiftedLognormal(min=5.0, mode=3.0, percentile_95=10.0)


def test_shifted_lognormal_percentile_validation() -> None:
    """Test that percentile_95 must be > min."""
    with pytest.raises(ValueError, match="percentile_95 must be greater than min"):
        ShiftedLognormal(min=10.0, mode=15.0, percentile_95=8.0)


def test_triangular_valid() -> None:
    """Test creating a valid triangular distribution."""
    dist = Triangular(min=1.0, mode=5.0, max=10.0)
    assert dist.min == 1.0
    assert dist.mode == 5.0
    assert dist.max == 10.0


def test_triangular_mode_validation() -> None:
    """Test that mode must be > min."""
    with pytest.raises(ValueError, match="mode must be greater than min"):
        Triangular(min=5.0, mode=3.0, max=10.0)


def test_triangular_max_validation() -> None:
    """Test that max must be > mode."""
    with pytest.raises(ValueError, match="max must be greater than mode"):
        Triangular(min=1.0, mode=8.0, max=7.0)


# PossibleWorld Tests


def test_possible_world_creation() -> None:
    """Test creating a possible world."""
    world = PossibleWorld(
        id=PossibleWorldId("pw1"),
        title="Option A",
        description="First option",
        weight=2.0,
    )
    assert world.id == PossibleWorldId("pw1")
    assert world.title == "Option A"
    assert world.weight == 2.0


def test_possible_world_default_values() -> None:
    """Test possible world default values."""
    world = PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")
    assert world.description == ""
    assert world.weight == 1.0


def test_possible_world_weight_validation() -> None:
    """Test that weight must be positive."""
    with pytest.raises(ValueError, match="weight must be positive"):
        PossibleWorld(id=PossibleWorldId("pw1"), title="Option A", weight=0.0)
    with pytest.raises(ValueError, match="weight must be positive"):
        PossibleWorld(id=PossibleWorldId("pw1"), title="Option A", weight=-1.0)


# Dependency Tests


def test_dependency_creation() -> None:
    """Test creating a dependency."""
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId("task2"),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    assert dep.source_endpoint == Endpoint.END
    assert dep.target_node_id == NodeId("task2")
    assert dep.constraint_type == ConstraintType.GREATER_EQUAL


def test_dependency_with_occurrence_point() -> None:
    """Test dependency with occurrence point."""
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=NodeId("branch1"),
        target_endpoint=Endpoint.OCCURRENCE,
        constraint_type=ConstraintType.EQUAL,
    )
    assert dep.source_endpoint == Endpoint.OCCURRENCE


# Task Tests


def test_task_creation() -> None:
    """Test creating a task."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
    )
    assert task.id == TaskId("t1")
    assert task.title == "Task 1"
    assert task.node_type == "task"
    assert task.dependencies == []


def test_task_with_distribution() -> None:
    """Test task with duration distribution."""
    dist = Triangular(min=1.0, mode=3.0, max=5.0)
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
        duration_distribution=dist,
    )
    assert task.duration_distribution is not None
    assert isinstance(task.duration_distribution, Triangular)
    assert task.duration_distribution.min == 1.0


def test_task_with_dependencies() -> None:
    """Test task with dependencies."""
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=NodeId("t2"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
        dependencies=[dep],
    )
    assert len(task.dependencies) == 1
    assert task.dependencies[0].target_node_id == NodeId("t2")


def test_task_completion_tracking() -> None:
    """Test task completion tracking."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
        actual_start_time="2024-01-15T10:00:00Z",
        actual_assignee=WorkerId("w1"),
        actual_duration=8.0,
    )
    assert task.actual_start_time is not None
    assert task.actual_assignee == WorkerId("w1")
    assert task.actual_duration == 8.0


# Branch Tests


def test_branch_creation() -> None:
    """Test creating a branch."""
    branch = Branch(
        id=BranchId("b1"),
        title="Decision Point",
        description="Choose option",
    )
    assert branch.id == BranchId("b1")
    assert branch.node_type == "branch"
    assert branch.possible_worlds == []


def test_branch_with_possible_worlds() -> None:
    """Test branch with possible worlds."""
    world1 = PossibleWorld(id=PossibleWorldId("pw1"), title="Option A", weight=1.0)
    world2 = PossibleWorld(id=PossibleWorldId("pw2"), title="Option B", weight=2.0)
    branch = Branch(
        id=BranchId("b1"),
        title="Decision",
        description="Choose",
        possible_worlds=[world1, world2],
    )
    assert len(branch.possible_worlds) == 2
    assert branch.possible_worlds[1].weight == 2.0


def test_branch_chosen_world() -> None:
    """Test branch with chosen world."""
    branch = Branch(
        id=BranchId("b1"),
        title="Decision",
        description="Choose",
        chosen_world_id=PossibleWorldId("pw1"),
    )
    assert branch.chosen_world_id == PossibleWorldId("pw1")


# DAG Tests


def test_dag_creation() -> None:
    """Test creating a DAG."""
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=DAGVersionId("v1"),
        node_map={
            NodeId("t1"): PersistentObjectId("pt1"),
            NodeId("b1"): PersistentObjectId("pb1"),
        },
    )
    assert dag.id == DAGId("dag1")
    assert dag.current_version_id == DAGVersionId("v1")
    assert len(dag.node_map) == 2


# DAGEvent Tests


def test_dag_event_creation() -> None:
    """Test creating a DAG event."""
    now = datetime.now(UTC)
    event = DAGEvent(
        id=EventId("e1"),
        timestamp=now,
        event_type=EventType.NODE_CREATED,
        affected_nodes=[NodeId("t1")],
        resulting_dag_version=DAGVersionId("v2"),
    )
    assert event.event_type == EventType.NODE_CREATED
    assert len(event.affected_nodes) == 1


def test_dag_event_with_parent() -> None:
    """Test DAG event with parent."""
    now = datetime.now(UTC)
    event = DAGEvent(
        id=EventId("e2"),
        timestamp=now,
        parent_event_id=EventId("e1"),
        event_type=EventType.NODE_MODIFIED,
        resulting_dag_version=DAGVersionId("v3"),
    )
    assert event.parent_event_id == EventId("e1")


# Persistent Object Tests


def test_persistent_task_creation() -> None:
    """Test creating a persistent task."""
    task = Task(id=TaskId("t1"), title="Task", description="Test")
    persistent = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={DAGVersionId("v1"): task},
    )
    assert persistent.id == PersistentObjectId("pt1")
    assert len(persistent.versions) == 1


def test_persistent_branch_creation() -> None:
    """Test creating a persistent branch."""
    branch = Branch(id=BranchId("b1"), title="Branch", description="Test")
    persistent = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={DAGVersionId("v1"): branch},
    )
    assert persistent.id == PersistentObjectId("pb1")
    assert len(persistent.versions) == 1


# Simulation Tests


def test_task_event_creation() -> None:
    """Test creating a task event."""
    now = datetime.now(UTC)
    event = TaskEvent(
        timestamp=now,
        node_id=NodeId("t1"),
        event_type="start",
        details={"worker": "w1"},
    )
    assert event.node_id == NodeId("t1")
    assert event.details["worker"] == "w1"


def test_sample_creation() -> None:
    """Test creating a sample."""
    sample = Sample(
        sample_id=SampleId(1),
        events=[],
        failed_tasks=[],
    )
    assert sample.sample_id == SampleId(1)
    assert len(sample.events) == 0
    assert len(sample.failed_tasks) == 0


def test_sample_with_failure() -> None:
    """Test sample with failed tasks."""
    sample = Sample(
        sample_id=SampleId(1),
        events=[],
        failed_tasks=[TaskId("t3"), TaskId("t4")],
    )
    assert len(sample.failed_tasks) == 2


def test_checkpoint_creation() -> None:
    """Test creating a checkpoint."""
    now = datetime.now(UTC)
    checkpoint = Checkpoint(
        timestamp=now,
        completed_samples=100,
        rng_state=[{"state": "data"}],
    )
    assert checkpoint.completed_samples == 100
    assert len(checkpoint.rng_state) == 1


def test_simulation_creation() -> None:
    """Test creating a simulation."""
    now = datetime.now(UTC)
    sim = Simulation(
        id=SimulationId("sim1"),
        dag_version_id=DAGVersionId("v1"),
        start_date=now,
        num_samples=1000,
        num_parallel_processes=4,
        status=SimulationStatus.RUNNING,
    )
    assert sim.num_samples == 1000
    assert sim.status == SimulationStatus.RUNNING
    assert sim.completed_samples == 0


def test_simulation_with_checkpoint() -> None:
    """Test simulation with checkpoint."""
    now = datetime.now(UTC)
    checkpoint = Checkpoint(
        timestamp=now,
        completed_samples=500,
        rng_state=[],
    )
    sim = Simulation(
        id=SimulationId("sim1"),
        dag_version_id=DAGVersionId("v1"),
        start_date=now,
        num_samples=1000,
        num_parallel_processes=4,
        status=SimulationStatus.INTERRUPTED,
        completed_samples=500,
        last_checkpoint=checkpoint,
    )
    assert sim.last_checkpoint is not None
    assert sim.last_checkpoint.completed_samples == 500


# Project Tests


def test_project_metadata_creation() -> None:
    """Test creating project metadata."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test Project",
        created=now,
        last_modified=now,
    )
    assert metadata.name == "Test Project"


def test_project_creation() -> None:
    """Test creating a project."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test Project",
        created=now,
        last_modified=now,
    )
    dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))
    project = Project(
        metadata=metadata,
        dag=dag,
    )
    assert project.version == "1.0"
    assert project.metadata.name == "Test Project"
    assert len(project.workers) == 0
    assert len(project.simulations) == 0


def test_project_with_workers() -> None:
    """Test project with workers."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test Project",
        created=now,
        last_modified=now,
    )
    dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))
    worker = Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0)
    project = Project(
        metadata=metadata,
        dag=dag,
        workers=[worker],
    )
    assert len(project.workers) == 1
    assert project.workers[0].name == "Alice"
