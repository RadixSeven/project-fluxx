"""Tests for simulation state management."""

from datetime import UTC, datetime, timedelta

import pytest

from fluxx.data.models import (
    DAG,
    BranchId,
    DAGId,
    DAGVersionId,
    NodeId,
    PersistentObjectId,
    PersistentTask,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    Task,
    TaskEvent,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)
from fluxx.simulation.state import SimulationState, WorkerState


@pytest.fixture
def base_workers() -> list[Worker]:
    """Create a basic list of workers for testing."""
    return [
        Worker(
            id=WorkerId("w1"),
            name="Worker 1",
            hours_per_workday=8.0,
        ),
        Worker(
            id=WorkerId("w2"),
            name="Worker 2",
            hours_per_workday=6.0,
        ),
    ]


@pytest.fixture
def simple_project() -> Project:
    """Create a simple project with a few tasks for testing."""
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
        dependencies=[],
    )
    task3 = Task(
        id=TaskId("t3"),
        title="Task 3",
        description="Third task",
        duration_distribution=Triangular(min=3.0, mode=5.0, max=8.0),
        dependencies=[],
    )

    version_id = DAGVersionId("v1")

    # Create persistent tasks
    persistent_task1 = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task1},
    )
    persistent_task2 = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={version_id: task2},
    )
    persistent_task3 = PersistentTask(
        id=PersistentObjectId("pt3"),
        versions={version_id: task3},
    )

    # Create DAG
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            NodeId("t1"): PersistentObjectId("pt1"),
            NodeId("t2"): PersistentObjectId("pt2"),
            NodeId("t3"): PersistentObjectId("pt3"),
        },
    )

    # Create metadata
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
            PersistentObjectId("pt3"): persistent_task3,
        },
    )


@pytest.fixture
def start_date() -> datetime:
    """Standard start date for simulations."""
    return datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)


def test_worker_state_initialization() -> None:
    """Test WorkerState dataclass initialization."""
    worker_id = WorkerId("w1")
    hours = 8.0
    task_id = TaskId("t1")
    available_time = datetime(2024, 1, 1, 17, 0, 0, tzinfo=UTC)

    # Test default initialization
    ws1 = WorkerState(worker_id=worker_id, hours_per_workday=hours)
    assert ws1.worker_id == worker_id
    assert ws1.hours_per_workday == hours
    assert ws1.current_task is None
    assert ws1.available_time is not None  # Has default value

    # Test with explicit values
    ws2 = WorkerState(
        worker_id=worker_id,
        hours_per_workday=hours,
        current_task=task_id,
        available_time=available_time,
    )
    assert ws2.worker_id == worker_id
    assert ws2.hours_per_workday == hours
    assert ws2.current_task == task_id
    assert ws2.available_time == available_time


def test_simulation_state_initialization(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test SimulationState initialization."""
    state = SimulationState(
        project=simple_project,
        start_date=start_date,
        workers=base_workers,
    )

    assert state.project == simple_project
    assert state.current_time == start_date
    assert len(state.completed_tasks) == 0
    assert len(state.in_progress_tasks) == 0
    assert len(state.resolved_branches) == 0
    assert len(state.events) == 0
    assert len(state.failed_tasks) == 0
    assert len(state.worker_states) == 2

    # Check worker states are initialized correctly
    assert WorkerId("w1") in state.worker_states
    assert WorkerId("w2") in state.worker_states

    ws1 = state.worker_states[WorkerId("w1")]
    assert ws1.worker_id == WorkerId("w1")
    assert ws1.hours_per_workday == 8.0
    assert ws1.current_task is None
    assert ws1.available_time == start_date

    ws2 = state.worker_states[WorkerId("w2")]
    assert ws2.worker_id == WorkerId("w2")
    assert ws2.hours_per_workday == 6.0


def test_complete_task(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test completing a task."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Start a task first
    task_id = TaskId("t1")
    worker_id = WorkerId("w1")
    completion_time = start_date + timedelta(hours=2)

    state.start_task(task_id, worker_id, start_date, completion_time)
    assert task_id in state.in_progress_tasks
    assert state.worker_states[worker_id].current_task == task_id

    # Complete the task
    state.complete_task(task_id, completion_time)

    assert task_id not in state.in_progress_tasks
    assert task_id in state.completed_tasks
    assert state.worker_states[worker_id].current_task is None
    assert state.worker_states[worker_id].available_time == completion_time


def test_complete_task_not_in_progress(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test completing a task that was never started (shouldn't error)."""
    state = SimulationState(simple_project, start_date, base_workers)

    task_id = TaskId("t1")
    completion_time = start_date + timedelta(hours=2)

    # Complete task that was never started - should work
    state.complete_task(task_id, completion_time)

    assert task_id in state.completed_tasks
    assert task_id not in state.in_progress_tasks


def test_start_task(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test starting a task."""
    state = SimulationState(simple_project, start_date, base_workers)

    task_id = TaskId("t1")
    worker_id = WorkerId("w1")
    estimated_completion = start_date + timedelta(hours=4)

    state.start_task(task_id, worker_id, start_date, estimated_completion)

    assert task_id in state.in_progress_tasks
    assert state.worker_states[worker_id].current_task == task_id
    assert state.worker_states[worker_id].available_time == estimated_completion


def test_resolve_branch(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test resolving a branch."""
    state = SimulationState(simple_project, start_date, base_workers)

    branch_id = BranchId("b1")
    world_id = PossibleWorldId("pw1")

    state.resolve_branch(branch_id, world_id)

    assert branch_id in state.resolved_branches
    assert state.resolved_branches[branch_id] == world_id


def test_add_event(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test adding events to the simulation history."""
    state = SimulationState(simple_project, start_date, base_workers)

    event1 = TaskEvent(
        node_id=NodeId("t1"),
        event_type="start",
        timestamp=start_date,
        details={"worker_id": "w1"},
    )

    event2 = TaskEvent(
        node_id=NodeId("t1"),
        event_type="complete",
        timestamp=start_date + timedelta(hours=2),
        details={"worker_id": "w1"},
    )

    state.add_event(event1)
    state.add_event(event2)

    assert len(state.events) == 2
    assert state.events[0] == event1
    assert state.events[1] == event2


def test_get_task(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test retrieving a task from the project."""
    state = SimulationState(simple_project, start_date, base_workers)

    task = state.get_task(TaskId("t1"))
    assert task.id == TaskId("t1")
    assert task.title == "Task 1"

    task2 = state.get_task(TaskId("t2"))
    assert task2.id == TaskId("t2")
    assert task2.title == "Task 2"


def test_get_task_not_found(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test retrieving a non-existent task raises KeyError."""
    state = SimulationState(simple_project, start_date, base_workers)

    with pytest.raises(KeyError, match="Task nonexistent not found"):
        state.get_task(TaskId("nonexistent"))


def test_get_task_not_in_persistent_tasks(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test error when node is in node_map but not in persistent_tasks."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Add a node to node_map that doesn't exist in persistent_tasks
    state.project.dag.node_map[NodeId("orphan")] = PersistentObjectId("missing")

    with pytest.raises(KeyError, match="Task orphan not found in persistent_tasks"):
        state.get_task(TaskId("orphan"))


def test_get_task_not_in_current_version(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test error when task exists but not in current version."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Create a task that only exists in an old version
    old_version_id = DAGVersionId("v0")
    task_old = Task(
        id=TaskId("t_old"),
        title="Old Task",
        description="Task only in old version",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt_old"),
        versions={old_version_id: task_old},  # Only in old version
    )

    # Add to project
    state.project.dag.node_map[NodeId("t_old")] = PersistentObjectId("pt_old")
    state.project.persistent_tasks[PersistentObjectId("pt_old")] = persistent_task

    with pytest.raises(KeyError, match="Task t_old not found in current version"):
        state.get_task(TaskId("t_old"))


def test_is_task_completed(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test checking if a task is completed."""
    state = SimulationState(simple_project, start_date, base_workers)

    task_id = TaskId("t1")
    assert not state.is_task_completed(task_id)

    state.completed_tasks.add(task_id)
    assert state.is_task_completed(task_id)


def test_is_task_in_progress(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test checking if a task is in progress."""
    state = SimulationState(simple_project, start_date, base_workers)

    task_id = TaskId("t1")
    assert not state.is_task_in_progress(task_id)

    state.in_progress_tasks.add(task_id)
    assert state.is_task_in_progress(task_id)


def test_has_task_started(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test checking if a task has started (in progress or completed)."""
    state = SimulationState(simple_project, start_date, base_workers)

    task_id = TaskId("t1")
    assert not state.has_task_started(task_id)

    # Task in progress counts as started
    state.in_progress_tasks.add(task_id)
    assert state.has_task_started(task_id)

    # Task completed also counts as started
    state.in_progress_tasks.remove(task_id)
    state.completed_tasks.add(task_id)
    assert state.has_task_started(task_id)


def test_get_available_workers(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test getting list of available workers."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Initially all workers available
    available = state.get_available_workers()
    assert len(available) == 2
    assert WorkerId("w1") in available
    assert WorkerId("w2") in available

    # Assign a task to w1
    state.worker_states[WorkerId("w1")].current_task = TaskId("t1")
    available = state.get_available_workers()
    assert len(available) == 1
    assert WorkerId("w2") in available
    assert WorkerId("w1") not in available

    # Assign a task to w2
    state.worker_states[WorkerId("w2")].current_task = TaskId("t2")
    available = state.get_available_workers()
    assert len(available) == 0


def test_all_tasks_completed(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test checking if all tasks are completed."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Initially no tasks completed
    assert not state.all_tasks_completed()

    # Complete some tasks
    state.completed_tasks.add(TaskId("t1"))
    assert not state.all_tasks_completed()

    state.completed_tasks.add(TaskId("t2"))
    assert not state.all_tasks_completed()

    # Complete all tasks
    state.completed_tasks.add(TaskId("t3"))
    assert state.all_tasks_completed()


def test_get_next_event_time(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test getting the next event time."""
    state = SimulationState(simple_project, start_date, base_workers)

    # No tasks in progress -> no next event
    assert state.get_next_event_time() is None

    # Start one task
    time1 = start_date + timedelta(hours=2)
    state.worker_states[WorkerId("w1")].current_task = TaskId("t1")
    state.worker_states[WorkerId("w1")].available_time = time1

    assert state.get_next_event_time() == time1

    # Start another task that completes earlier
    time2 = start_date + timedelta(hours=1)
    state.worker_states[WorkerId("w2")].current_task = TaskId("t2")
    state.worker_states[WorkerId("w2")].available_time = time2

    # Should return the earliest time
    assert state.get_next_event_time() == time2

    # Complete the first task
    state.worker_states[WorkerId("w2")].current_task = None

    # Should now return the next earliest time
    assert state.get_next_event_time() == time1


def test_multiple_workers_same_task_completion_time(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test next event time when multiple workers finish simultaneously."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Both workers finish at the same time
    completion_time = start_date + timedelta(hours=2)
    state.worker_states[WorkerId("w1")].current_task = TaskId("t1")
    state.worker_states[WorkerId("w1")].available_time = completion_time
    state.worker_states[WorkerId("w2")].current_task = TaskId("t2")
    state.worker_states[WorkerId("w2")].available_time = completion_time

    assert state.get_next_event_time() == completion_time


def test_is_task_reachable_nonexistent_task(
    simple_project: Project, start_date: datetime, base_workers: list[Worker]
) -> None:
    """Test is_task_reachable with a nonexistent task ID."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Task that doesn't exist in the project
    nonexistent_task = TaskId("nonexistent")

    # Should return False for nonexistent tasks
    assert not state.is_task_reachable(nonexistent_task)
