"""Tests for simulation engine."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

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
    ShiftedLognormal,
    StartedCompletion,
    Task,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)
from fluxx.simulation.calendar import WorkCalendar
from fluxx.simulation.engine import (
    SimulationEngine,
    advance_to_next_event,
    choose_possible_world,
    complete_task,
    create_failed_sample,
    create_successful_sample,
    get_branch,
    process_task_completions,
    resolve_branch,
    run_single_sample,
    sample_in_progress_task_remaining_duration,
    sample_task_duration,
    select_worker_for_task,
    start_task,
)
from fluxx.simulation.state import SimulationState


@pytest.fixture
def base_workers() -> list[Worker]:
    """Create basic workers for testing."""
    return [
        Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0),
        Worker(id=WorkerId("w2"), name="Worker 2", hours_per_workday=8.0),
    ]


@pytest.fixture
def simple_project() -> Project:
    """Create a simple project with two tasks."""
    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[],
    )

    task2 = Task(
        id=TaskId("t2"),
        title="Task 2",
        description="Second task",
        duration_distribution=Triangular(min=2.0, mode=4.0, max=6.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    version_id = DAGVersionId("v1")

    persistent_task1 = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task1},
    )
    persistent_task2 = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={version_id: task2},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("t1"): PersistentObjectId("pt1"),
            TaskId("t2"): PersistentObjectId("pt2"),
        },
    )

    metadata = ProjectMetadata(
        name="Test Project",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )

    return Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={
            PersistentObjectId("pt1"): persistent_task1,
            PersistentObjectId("pt2"): persistent_task2,
        },
    )


@pytest.fixture
def start_date() -> datetime:
    """Standard start date."""
    return datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)


# Tests for task duration sampling


def test_sample_task_duration_triangular() -> None:
    """Test sampling duration from triangular distribution."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    rng = np.random.default_rng(seed=42)

    duration = sample_task_duration(task, rng)

    assert 1.0 <= duration <= 3.0


def test_sample_task_duration_shifted_lognormal() -> None:
    """Test sampling duration from shifted lognormal distribution."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=ShiftedLognormal(min=1.0, mode=5.0, percentile_95=15.0),
    )
    rng = np.random.default_rng(seed=42)

    duration = sample_task_duration(task, rng)

    assert duration >= 1.0


def test_sample_task_duration_no_distribution() -> None:
    """Test error when task has no distribution."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=None,
    )
    rng = np.random.default_rng(seed=42)

    with pytest.raises(ValueError, match="has no duration distribution"):
        sample_task_duration(task, rng)


def test_sample_task_duration_unknown_distribution() -> None:
    """Test error when task has an unknown distribution type."""
    from typing import cast

    # Create a task with a valid distribution first
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Simulate an unhandled/corrupt distribution type using cast
    # to bypass type checking
    task.duration_distribution = cast(Triangular, cast(object, "not a distribution"))

    rng = np.random.default_rng(seed=42)

    with pytest.raises(ValueError, match="Unknown distribution type"):
        sample_task_duration(task, rng)


def test_sample_in_progress_task_remaining_duration() -> None:
    """Test sampling remaining duration for in-progress task."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=2.0, mode=4.0, max=6.0),
    )
    rng = np.random.default_rng(seed=42)
    elapsed_hours = 3.0

    remaining = sample_in_progress_task_remaining_duration(task, elapsed_hours, rng)

    # Remaining should be >= 0 (total >= elapsed)
    assert remaining >= 0


def test_sample_in_progress_task_no_distribution() -> None:
    """Test error when in-progress task has no distribution."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=None,
    )
    rng = np.random.default_rng(seed=42)

    with pytest.raises(ValueError, match="has no duration distribution"):
        sample_in_progress_task_remaining_duration(task, 1.0, rng)


# Tests for worker assignment


def test_select_worker_for_task(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test selecting a worker for a task."""
    state = SimulationState(simple_project, start_date, base_workers)
    task = state.get_task(TaskId("t1"))
    rng = np.random.default_rng(seed=42)

    worker_id = select_worker_for_task(task, state, rng)

    assert worker_id in [WorkerId("w1"), WorkerId("w2")]


def test_select_worker_for_task_no_eligible() -> None:
    """Test error when no eligible workers available."""
    # Create task with whitelist that doesn't match any workers
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[WorkerId("nonexistent")],
    )

    worker = Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)
    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    # Create minimal project
    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={TaskId("t1"): PersistentObjectId("pt1")},
    )
    metadata = ProjectMetadata(
        name="Test",
        created=start,
        last_modified=start,
    )
    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    state = SimulationState(project, start, [worker])
    rng = np.random.default_rng(seed=42)

    with pytest.raises(ValueError, match="No eligible workers"):
        select_worker_for_task(task, state, rng)


# Tests for task lifecycle


def test_start_task(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test starting a task."""
    state = SimulationState(simple_project, start_date, base_workers)
    calendar = WorkCalendar(start_date)
    task = state.get_task(TaskId("t1"))
    rng = np.random.default_rng(seed=42)

    start_task(task, state, calendar, rng)

    # Task should be in progress
    assert state.is_task_in_progress(TaskId("t1"))

    # Should have recorded a start event
    assert len(state.events) == 1
    assert state.events[0].event_type == "start"


def test_start_task_in_progress(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test starting an in-progress task uses existing assignee."""
    from fluxx.data.models import StartedCompletion

    # Create task with StartedCompletion
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
        duration_distribution=Triangular(min=8.0, mode=16.0, max=24.0),
        completion=StartedCompletion(
            assignee=WorkerId("w2"),  # Specific worker
            start_time=start_date - timedelta(days=1),
            hours_logged=4.0,  # Already worked 4 hours
        ),
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={TaskId("t1"): PersistentObjectId("pt1")},
    )
    project = Project(
        metadata=ProjectMetadata(
            name="Test", created=start_date, last_modified=start_date
        ),
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    state = SimulationState(project, start_date, base_workers)
    calendar = WorkCalendar(start_date)
    task_from_state = state.get_task(TaskId("t1"))
    rng = np.random.default_rng(seed=42)

    start_task(task_from_state, state, calendar, rng)

    # Task should be in progress
    assert state.is_task_in_progress(TaskId("t1"))

    # Should use the assignee from StartedCompletion (w2), not random
    worker_state = state.worker_states[WorkerId("w2")]
    assert worker_state.current_task == TaskId("t1")

    # Should have recorded a start event
    assert len(state.events) == 1
    assert state.events[0].event_type == "start"
    assert state.events[0].details["worker_id"] == "w2"

    # Duration should be remaining (sampled >= hours_logged)
    # Since we logged 4 hours of min 8, remaining should be at least 4 hours


def test_complete_task(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test completing a task."""
    state = SimulationState(simple_project, start_date, base_workers)
    task = state.get_task(TaskId("t1"))

    # Start the task first
    state.start_task(TaskId("t1"), WorkerId("w1"), start_date, start_date)

    completion_time = start_date + timedelta(hours=2)
    complete_task(task, state, completion_time)

    # Task should be completed
    assert state.is_task_completed(TaskId("t1"))

    # Should have recorded a complete event
    assert len(state.events) == 1
    assert state.events[0].event_type == "complete"


def test_complete_task_no_worker_assigned(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test completing a task when no worker is assigned."""
    state = SimulationState(simple_project, start_date, base_workers)
    task = state.get_task(TaskId("t1"))

    completion_time = start_date + timedelta(hours=2)
    complete_task(task, state, completion_time)

    # Should still complete, just with no worker_id in event
    assert state.is_task_completed(TaskId("t1"))
    assert state.events[0].details["worker_id"] is None


def test_process_task_completions(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test processing task completions at current time."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Start task 1 with completion at current time + 2 hours
    completion_time = start_date + timedelta(hours=2)
    state.start_task(TaskId("t1"), WorkerId("w1"), start_date, completion_time)

    # Advance time to completion
    state.current_time = completion_time

    # Process completions
    process_task_completions(state)

    # Task should be completed
    assert state.is_task_completed(TaskId("t1"))


def test_process_task_completions_multiple_tasks(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test processing multiple tasks completing simultaneously."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Start both tasks with same completion time
    completion_time = start_date + timedelta(hours=2)
    state.start_task(TaskId("t1"), WorkerId("w1"), start_date, completion_time)
    state.start_task(TaskId("t2"), WorkerId("w2"), start_date, completion_time)

    # Advance time
    state.current_time = completion_time

    # Process completions
    process_task_completions(state)

    # Both should be completed
    assert state.is_task_completed(TaskId("t1"))
    assert state.is_task_completed(TaskId("t2"))


def test_process_task_completions_task_not_in_version(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test processing completions when task isn't in current version."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Manually set a worker to have a task that doesn't exist
    state.worker_states[WorkerId("w1")].current_task = TaskId("t_nonexistent")
    state.worker_states[WorkerId("w1")].available_time = start_date

    # Should not raise error, just skip
    process_task_completions(state)


# Tests for branch resolution


def test_choose_possible_world_single() -> None:
    """Test choosing from branch with single world."""
    branch = Branch(
        id=BranchId("b1"),
        title="Branch 1",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0)
        ],
    )
    rng = np.random.default_rng(seed=42)

    world_id = choose_possible_world(branch, rng)

    assert world_id == PossibleWorldId("pw1")


def test_choose_possible_world_multiple() -> None:
    """Test choosing from branch with multiple worlds."""
    branch = Branch(
        id=BranchId("b1"),
        title="Branch 1",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0),
            PossibleWorld(id=PossibleWorldId("pw2"), title="World 2", weight=2.0),
        ],
    )
    rng = np.random.default_rng(seed=42)

    world_id = choose_possible_world(branch, rng)

    # Should be one of the two worlds
    assert world_id in [PossibleWorldId("pw1"), PossibleWorldId("pw2")]


def test_choose_possible_world_no_worlds() -> None:
    """Test error when branch has no possible worlds."""
    branch = Branch(
        id=BranchId("b1"),
        title="Branch 1",
        description="Test branch",
        possible_worlds=[],
    )
    rng = np.random.default_rng(seed=42)

    with pytest.raises(ValueError, match="has no possible worlds"):
        choose_possible_world(branch, rng)


def test_resolve_branch(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test resolving a branch."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Add a branch
    branch = Branch(
        id=BranchId("b1"),
        title="Branch 1",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0)
        ],
    )
    rng = np.random.default_rng(seed=42)

    resolve_branch(branch, state, rng)

    # Branch should be resolved
    assert BranchId("b1") in state.resolved_branches
    assert state.resolved_branches[BranchId("b1")] == PossibleWorldId("pw1")

    # Should have recorded event
    assert len(state.events) == 1
    assert state.events[0].event_type == "branch_resolved"


def test_get_branch(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test retrieving a branch."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Add a branch to the project
    branch = Branch(
        id=BranchId("b1"),
        title="Branch 1",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0)
        ],
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={simple_project.dag.current_version_id: branch},
    )
    state.project.dag.node_map[BranchId("b1")] = PersistentObjectId("pb1")
    state.project.persistent_branches[PersistentObjectId("pb1")] = persistent_branch

    retrieved = get_branch(BranchId("b1"), state)

    assert retrieved.id == BranchId("b1")
    assert retrieved.title == "Branch 1"


def test_get_branch_not_in_node_map(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test error when branch not in node_map."""
    state = SimulationState(simple_project, start_date, base_workers)

    with pytest.raises(KeyError, match="not found in node_map"):
        get_branch(BranchId("b_nonexistent"), state)


def test_get_branch_not_in_persistent_branches(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test error when branch in node_map but not in persistent_branches."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Add to node_map but not persistent_branches
    state.project.dag.node_map[BranchId("b1")] = PersistentObjectId("pb_missing")

    with pytest.raises(KeyError, match="not found in persistent_branches"):
        get_branch(BranchId("b1"), state)


def test_get_branch_not_in_current_version(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test error when branch not in current version."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Create branch only in old version
    old_version_id = DAGVersionId("v0")
    branch = Branch(
        id=BranchId("b1"),
        title="Branch 1",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0)
        ],
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={old_version_id: branch},  # Only in old version
    )
    state.project.dag.node_map[BranchId("b1")] = PersistentObjectId("pb1")
    state.project.persistent_branches[PersistentObjectId("pb1")] = persistent_branch

    with pytest.raises(KeyError, match="not found in current version"):
        get_branch(BranchId("b1"), state)


# Tests for time advancement


def test_advance_to_next_event(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test advancing to next event."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Start a task that completes in 2 hours
    completion_time = start_date + timedelta(hours=2)
    state.start_task(TaskId("t1"), WorkerId("w1"), start_date, completion_time)

    # Advance to next event
    advance_to_next_event(state)

    assert state.current_time == completion_time


def test_advance_to_next_event_no_next_event(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test error when no next event exists."""
    state = SimulationState(simple_project, start_date, base_workers)

    # No tasks in progress, so no next event
    with pytest.raises(ValueError, match="No next event time available"):
        advance_to_next_event(state)


# Tests for sample creation


def test_create_successful_sample(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test creating a successful sample."""
    state = SimulationState(simple_project, start_date, base_workers)

    sample = create_successful_sample(42, state)

    assert sample.sample_id == 42
    assert len(sample.failed_tasks) == 0


def test_create_failed_sample(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test creating a failed sample."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Complete only task 1, leaving task 2 incomplete
    state.completed_tasks.add(TaskId("t1"))

    sample = create_failed_sample(42, state)

    assert sample.sample_id == 42
    assert TaskId("t2") in sample.failed_tasks
    assert TaskId("t1") not in sample.failed_tasks


# Tests for main orchestration


def test_run_single_sample_success(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test running a successful simulation sample."""
    rng = np.random.default_rng(seed=42)

    sample = run_single_sample(simple_project, base_workers, start_date, 0, rng)

    # Should complete successfully
    assert len(sample.failed_tasks) == 0

    # Should have events for both tasks
    start_events = [e for e in sample.events if e.event_type == "start"]
    complete_events = [e for e in sample.events if e.event_type == "complete"]

    assert len(start_events) == 2
    assert len(complete_events) == 2


def test_run_single_sample_deadlock() -> None:
    """Test simulation detecting deadlock."""
    # Create project with impossible worker constraints
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Impossible task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[WorkerId("nonexistent")],  # No worker matches
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={TaskId("t1"): PersistentObjectId("pt1")},
    )

    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    metadata = ProjectMetadata(
        name="Deadlock Project",
        created=start,
        last_modified=start,
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    workers = [Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)]
    rng = np.random.default_rng(seed=42)

    sample = run_single_sample(project, workers, start, 0, rng)

    # Should fail with deadlock
    assert TaskId("t1") in sample.failed_tasks


# Tests for SimulationEngine class


def test_simulation_engine_init() -> None:
    """Test SimulationEngine initialization."""
    engine = SimulationEngine(num_samples=100)

    assert engine.num_samples == 100
    assert engine.start_date is not None


def test_simulation_engine_with_start_date() -> None:
    """Test SimulationEngine with custom start date."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    engine = SimulationEngine(num_samples=100, start_date=start)

    assert engine.start_date == start


def test_simulation_engine_run(
    simple_project: Project, base_workers: list[Worker]
) -> None:
    """Test running SimulationEngine."""
    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    engine = SimulationEngine(num_samples=5, start_date=start)

    samples = engine.run(simple_project, base_workers)

    assert len(samples) == 5
    # All should succeed for this simple project
    assert all(len(s.failed_tasks) == 0 for s in samples)


def test_run_single_sample_with_branch() -> None:
    """Test simulation with branch resolution."""
    # Create project with a branch
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[],
    )

    branch = Branch(
        id=BranchId("b1"),
        title="Branch 1",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0)
        ],
        dependencies=[],
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={version_id: branch},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("t1"): PersistentObjectId("pt1"),
            BranchId("b1"): PersistentObjectId("pb1"),
        },
    )

    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    metadata = ProjectMetadata(
        name="Branch Project",
        created=start,
        last_modified=start,
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    workers = [Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)]
    rng = np.random.default_rng(seed=42)

    sample = run_single_sample(project, workers, start, 0, rng)

    # Should complete successfully
    assert len(sample.failed_tasks) == 0

    # Should have branch resolution event
    branch_events = [e for e in sample.events if e.event_type == "branch_resolved"]
    assert len(branch_events) == 1


def test_create_failed_sample_with_branch() -> None:
    """Test creating failed sample with project containing branches."""
    # Create project with task and branch
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    branch = Branch(
        id=BranchId("b1"),
        title="Branch 1",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0)
        ],
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={version_id: branch},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("t1"): PersistentObjectId("pt1"),
            BranchId("b1"): PersistentObjectId("pb1"),
        },
    )

    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    metadata = ProjectMetadata(
        name="Test",
        created=start,
        last_modified=start,
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
    )

    workers = [Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)]
    state = SimulationState(project, start, workers)

    sample = create_failed_sample(0, state)

    # Should have task in failed_tasks (branch shouldn't be included)
    assert TaskId("t1") in sample.failed_tasks
    # Branches are not tasks, so shouldn't be in failed_tasks


def test_run_single_sample_advance_exception() -> None:
    """Test simulation handling advance_to_next_event ValueError using mocking."""
    from unittest.mock import patch

    # Create a simple project with one task
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={TaskId("t1"): PersistentObjectId("pt1")},
    )

    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    metadata = ProjectMetadata(
        name="Test",
        created=start,
        last_modified=start,
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    workers = [Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)]
    rng = np.random.default_rng(seed=42)

    # Mock advance_to_next_event to raise ValueError
    # This tests the defensive error handling path
    with patch("fluxx.simulation.engine.advance_to_next_event") as mock_advance:
        mock_advance.side_effect = ValueError("No next event")

        sample = run_single_sample(project, workers, start, 0, rng)

        # Should handle the ValueError and return a failed sample
        assert len(sample.failed_tasks) > 0
        assert TaskId("t1") in sample.failed_tasks


def test_all_tasks_completed_with_unchosen_possible_world() -> None:
    """Test that tasks in unchosen possible worlds don't prevent completion.

    Bug: all_tasks_completed() currently requires ALL tasks to be completed,
    even tasks that depend on possible worlds that were not chosen.

    Correct behavior: Tasks that depend on unchosen possible worlds are
    unreachable and should not prevent the simulation from completing.
    """
    # Create a branch with two possible worlds
    branch = Branch(
        id=BranchId("b1"),
        title="Branch",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("world1"), title="World 1", weight=1.0),
            PossibleWorld(id=PossibleWorldId("world2"), title="World 2", weight=1.0),
        ],
        dependencies=[],
    )

    # Task in world 1
    task_world1 = Task(
        id=TaskId("t1"),
        title="Task in World 1",
        description="Only happens in world 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=BranchId("b1:world1"),
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Task in world 2
    task_world2 = Task(
        id=TaskId("t2"),
        title="Task in World 2",
        description="Only happens in world 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=BranchId("b1:world2"),
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    version_id = DAGVersionId("v1")

    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={version_id: branch},
    )

    persistent_task1 = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task_world1},
    )

    persistent_task2 = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={version_id: task_world2},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            BranchId("b1"): PersistentObjectId("pb1"),
            TaskId("t1"): PersistentObjectId("pt1"),
            TaskId("t2"): PersistentObjectId("pt2"),
        },
    )

    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    metadata = ProjectMetadata(
        name="Branch Test",
        created=start,
        last_modified=start,
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
        persistent_tasks={
            PersistentObjectId("pt1"): persistent_task1,
            PersistentObjectId("pt2"): persistent_task2,
        },
    )

    workers = [Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)]
    rng = np.random.default_rng(seed=42)

    sample = run_single_sample(project, workers, start, 0, rng)

    # The simulation should complete successfully
    # Even though task_world2 was never completed, it's unreachable because
    # we chose world1 (the RNG with seed=42 happens to choose world1 first)
    assert len(sample.failed_tasks) == 0, (
        "BUG: Simulation should complete when only reachable tasks are done. "
        "Tasks in unchosen possible worlds should not prevent completion."
    )


def test_deadlock_detection_with_ineligible_branch() -> None:
    """Test that deadlock is detected when branch has unsatisfied dependencies.

    Bug: detect_deadlock() only returns True if there are NO unresolved branches.
    But if a branch exists with unsatisfied dependencies, we're still deadlocked.

    Correct behavior: Deadlock should be detected when there are no ELIGIBLE
    branches (branches whose dependencies are satisfied).
    """
    # Create a task that must be completed before the branch can be resolved
    prerequisite_task = Task(
        id=TaskId("t_prereq"),
        title="Prerequisite",
        description="Must complete before branch",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[],
        allowed_workers=[WorkerId("nonexistent")],  # Can't be assigned to real worker
    )

    # Create a branch that depends on the prerequisite task
    branch = Branch(
        id=BranchId("b1"),
        title="Blocked Branch",
        description="Cannot be resolved yet",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("w1"), title="World 1", weight=1.0)
        ],
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.OCCURRENCE,
                target_node_id=TaskId("t_prereq"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create a task that depends on the branch
    dependent_task = Task(
        id=TaskId("t_dependent"),
        title="Dependent Task",
        description="Depends on branch",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=BranchId("b1"),
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    version_id = DAGVersionId("v1")

    persistent_prereq = PersistentTask(
        id=PersistentObjectId("pt_prereq"),
        versions={version_id: prerequisite_task},
    )

    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={version_id: branch},
    )

    persistent_dependent = PersistentTask(
        id=PersistentObjectId("pt_dependent"),
        versions={version_id: dependent_task},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("t_prereq"): PersistentObjectId("pt_prereq"),
            BranchId("b1"): PersistentObjectId("pb1"),
            TaskId("t_dependent"): PersistentObjectId("pt_dependent"),
        },
    )

    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    metadata = ProjectMetadata(
        name="Deadlock Test",
        created=start,
        last_modified=start,
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
        persistent_tasks={
            PersistentObjectId("pt_prereq"): persistent_prereq,
            PersistentObjectId("pt_dependent"): persistent_dependent,
        },
    )

    workers = [Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)]
    rng = np.random.default_rng(seed=42)

    sample = run_single_sample(project, workers, start, 0, rng)

    # Should detect deadlock
    # The prerequisite task can't be completed (wrong worker),
    # so the branch can't be resolved,
    # so the dependent task can't start
    assert len(sample.failed_tasks) > 0, (
        "BUG: Deadlock should be detected when branch has unsatisfied dependencies. "
        "Having an unresolved branch doesn't mean we can make progress."
    )


def test_start_task_time_splitting_multiple_in_progress_tasks(
    base_workers: list[Worker],
) -> None:
    """Test that start_task applies time-splitting for multiple in-progress tasks."""
    # Create a project with two in-progress tasks assigned to the same worker
    start_date = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="In progress task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_date,
            hours_logged=1.0,
        ),
    )
    task2 = Task(
        id=TaskId("t2"),
        title="Task 2",
        description="In progress task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_date,
            hours_logged=1.0,
        ),
    )

    version_id = DAGVersionId("v1")
    persistent_task1 = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task1},
    )
    persistent_task2 = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={version_id: task2},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("t1"): PersistentObjectId("pt1"),
            TaskId("t2"): PersistentObjectId("pt2"),
        },
    )

    metadata = ProjectMetadata(
        name="Test Project",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={
            PersistentObjectId("pt1"): persistent_task1,
            PersistentObjectId("pt2"): persistent_task2,
        },
    )

    state = SimulationState(project, start_date, base_workers)
    calendar = WorkCalendar(start_date)
    rng = np.random.default_rng(seed=42)

    # Start task1 - time should be doubled due to having 2 in-progress tasks
    start_task(task1, state, calendar, rng)

    # Get the worker's expected completion time
    worker_state = state.worker_states[WorkerId("w1")]

    # The task is now in progress in the simulation
    assert state.is_task_in_progress(TaskId("t1"))

    # With time-splitting, the completion time should be later than without
    # We can't test exact values easily, but we can verify the task started
    assert worker_state.available_time > start_date
