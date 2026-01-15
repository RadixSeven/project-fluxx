"""Tests for simulation state management."""

from datetime import UTC, datetime, timedelta

import pytest

from fluxx.data.models import (
    DAG,
    BranchId,
    DAGId,
    DAGVersionId,
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
            TaskId("t1"): PersistentObjectId("pt1"),
            TaskId("t2"): PersistentObjectId("pt2"),
            TaskId("t3"): PersistentObjectId("pt3"),
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
        node_id=TaskId("t1"),
        event_type="start",
        timestamp=start_date,
        details={"worker_id": "w1"},
    )

    event2 = TaskEvent(
        node_id=TaskId("t1"),
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

    with pytest.raises(KeyError, match="Task t_nonexistent not found"):
        state.get_task(TaskId("t_nonexistent"))


def test_get_task_not_in_persistent_tasks(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test error when node is in node_map but not in persistent_tasks."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Add a node to node_map that doesn't exist in persistent_tasks
    state.project.dag.node_map[TaskId("t_orphan")] = PersistentObjectId("missing")

    with pytest.raises(KeyError, match="Task t_orphan not found in persistent_tasks"):
        state.get_task(TaskId("t_orphan"))


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
    state.project.dag.node_map[TaskId("t_old")] = PersistentObjectId("pt_old")
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
    nonexistent_task = TaskId("t_nonexistent")

    # Should return False for nonexistent tasks
    assert not state.is_task_reachable(nonexistent_task)


def test_get_jira_sampling_context(start_date: datetime) -> None:
    """Test get_jira_sampling_context returns context and caches it."""
    from fluxx.data.id_generation import generate_dag_id, generate_dag_version_id
    from fluxx.jira.models import (
        EstimateSource,
        JiraConfig,
        JiraDurationHistoryEntry,
        JiraIssueKey,
        JiraSyncMetadata,
    )
    from fluxx.simulation.distributions import JiraSamplingContext

    # Create project with Jira history
    now = start_date
    dag = DAG(
        id=generate_dag_id(),
        current_version_id=generate_dag_version_id(),
        node_map={},
    )
    project = Project(
        version="1.3",
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=dag,
        persistent_tasks={},
        persistent_branches={},
        workers=[],
        simulations=[],
        jira_config=JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=now,
                history_entries=[
                    JiraDurationHistoryEntry(
                        server_url="https://jira.example.com",
                        issue_key=JiraIssueKey(project_key="TEST", issue_number=1),
                        original_estimate_seconds=3600,
                        total_logged_time_seconds=7200,
                        worker_jira_id="user1",
                        issue_type="Story",
                        estimate_source=EstimateSource.FROM_ORIGINAL_ESTIMATE,
                    ),
                ],
            ),
        ),
    )

    workers = [Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)]
    state = SimulationState(project, now, workers)

    # Get context first time - should build it
    context1 = state.get_jira_sampling_context()
    assert isinstance(context1, JiraSamplingContext)
    assert len(context1.all_actuals) == 1
    assert 2.0 in context1.all_actuals  # 7200 seconds = 2 hours

    # Get context second time - should return cached instance
    context2 = state.get_jira_sampling_context()
    assert context1 is context2  # Same object (cached)


def test_add_pending_started_task(
    simple_project: Project, base_workers: list[Worker]
) -> None:
    """Test adding pending started tasks for a worker."""
    now = datetime.now(UTC)
    state = SimulationState(simple_project, now, base_workers)
    worker_id = WorkerId("w1")

    # Initially no pending tasks
    assert not state.has_pending_started_tasks(worker_id)
    assert state.get_pending_started_task_count(worker_id) == 0

    # Add a pending task
    state.add_pending_started_task(worker_id, TaskId("t1"), 10.0)
    assert state.has_pending_started_tasks(worker_id)
    assert state.get_pending_started_task_count(worker_id) == 1

    # Add another pending task
    state.add_pending_started_task(worker_id, TaskId("t2"), 20.0)
    assert state.get_pending_started_task_count(worker_id) == 2


def test_get_next_pending_started_task(
    simple_project: Project, base_workers: list[Worker]
) -> None:
    """Test getting the next pending started task."""
    now = datetime.now(UTC)
    state = SimulationState(simple_project, now, base_workers)
    worker_id = WorkerId("w1")

    # No pending tasks
    assert state.get_next_pending_started_task(worker_id) is None

    # Add tasks
    state.add_pending_started_task(worker_id, TaskId("t1"), 10.0)
    state.add_pending_started_task(worker_id, TaskId("t2"), 20.0)

    # Get tasks in FIFO order
    result = state.get_next_pending_started_task(worker_id)
    assert result is not None
    task_id, remaining = result
    assert task_id == TaskId("t1")
    assert remaining == 10.0

    result = state.get_next_pending_started_task(worker_id)
    assert result is not None
    task_id, remaining = result
    assert task_id == TaskId("t2")
    assert remaining == 20.0

    # No more tasks
    assert state.get_next_pending_started_task(worker_id) is None
    assert not state.has_pending_started_tasks(worker_id)


def test_pending_started_tasks_per_worker(
    simple_project: Project, base_workers: list[Worker]
) -> None:
    """Test that pending tasks are tracked per worker."""
    now = datetime.now(UTC)
    state = SimulationState(simple_project, now, base_workers)
    worker1 = WorkerId("w1")
    worker2 = WorkerId("w2")

    # Add tasks for different workers
    state.add_pending_started_task(worker1, TaskId("t1"), 10.0)
    state.add_pending_started_task(worker2, TaskId("t2"), 20.0)
    state.add_pending_started_task(worker1, TaskId("t3"), 30.0)

    # Check counts per worker
    assert state.get_pending_started_task_count(worker1) == 2
    assert state.get_pending_started_task_count(worker2) == 1

    # Get task for worker1 doesn't affect worker2
    result = state.get_next_pending_started_task(worker1)
    assert result is not None
    assert result[0] == TaskId("t1")
    assert state.get_pending_started_task_count(worker1) == 1
    assert state.get_pending_started_task_count(worker2) == 1


def test_initialize_completed_tasks_from_done_completion(
    base_workers: list[Worker],
) -> None:
    """Test that DoneCompletion tasks are pre-initialized as completed."""
    from fluxx.data.models import DoneCompletion

    start_date = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    version_id = DAGVersionId("v1")

    # Task with DoneCompletion
    done_task = Task(
        id=TaskId("t_done"),
        title="Done Task",
        description="Already completed",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=DoneCompletion(
            assignee=WorkerId("w1"),
            start_time=datetime(2023, 12, 1, tzinfo=UTC),
            end_time=datetime(2023, 12, 5, tzinfo=UTC),
            hours_logged=32.0,
        ),
    )

    # Normal pending task
    pending_task = Task(
        id=TaskId("t_pending"),
        title="Pending Task",
        description="Not started",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_done = PersistentTask(
        id=PersistentObjectId("pt_done"),
        versions={version_id: done_task},
    )
    persistent_pending = PersistentTask(
        id=PersistentObjectId("pt_pending"),
        versions={version_id: pending_task},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("t_done"): PersistentObjectId("pt_done"),
            TaskId("t_pending"): PersistentObjectId("pt_pending"),
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
            PersistentObjectId("pt_done"): persistent_done,
            PersistentObjectId("pt_pending"): persistent_pending,
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # Done task should be pre-initialized as completed
    assert state.is_task_completed(TaskId("t_done"))
    # Pending task should not be completed
    assert not state.is_task_completed(TaskId("t_pending"))


def test_get_started_completion_tasks_assignee_not_in_workers(
    base_workers: list[Worker],
) -> None:
    """Test get_started_completion_tasks_by_worker skips tasks with unknown assignee."""
    from fluxx.data.models import StartedCompletion

    start_date = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    version_id = DAGVersionId("v1")

    # Task assigned to a worker not in the simulation
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Assigned to unknown worker",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("unknown_worker"),  # Not in base_workers
            hours_logged=2.0,
            start_time=datetime(2023, 12, 15, tzinfo=UTC),
        ),
    )

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
        name="Test Project",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    state = SimulationState(project, start_date, base_workers)
    tasks_by_worker = state.get_started_completion_tasks_by_worker()

    # Task should be skipped because assignee is not in workers
    assert WorkerId("unknown_worker") not in tasks_by_worker
    assert len(tasks_by_worker) == 0


def test_get_started_completion_tasks_unsatisfied_dependencies(
    base_workers: list[Worker],
) -> None:
    """Test get_started_completion_tasks_by_worker skips tasks with unsatisfied deps."""
    from fluxx.data.models import (
        ConstraintType,
        Dependency,
        Endpoint,
        StartedCompletion,
    )

    start_date = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    version_id = DAGVersionId("v1")

    # Prerequisite task (not completed)
    prereq_task = Task(
        id=TaskId("t_prereq"),
        title="Prerequisite",
        description="Must be completed first",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Task that depends on prerequisite
    dependent_task = Task(
        id=TaskId("t_dependent"),
        title="Dependent Task",
        description="Has unsatisfied dependency",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            hours_logged=2.0,
            start_time=datetime(2023, 12, 15, tzinfo=UTC),
        ),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t_prereq"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    persistent_prereq = PersistentTask(
        id=PersistentObjectId("pt_prereq"),
        versions={version_id: prereq_task},
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
            TaskId("t_dependent"): PersistentObjectId("pt_dependent"),
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
            PersistentObjectId("pt_prereq"): persistent_prereq,
            PersistentObjectId("pt_dependent"): persistent_dependent,
        },
    )

    state = SimulationState(project, start_date, base_workers)
    tasks_by_worker = state.get_started_completion_tasks_by_worker()

    # Dependent task should be skipped because prerequisite is not completed
    assert WorkerId("w1") not in tasks_by_worker


def test_has_task_started_nonexistent_task(
    simple_project: Project,
    base_workers: list[Worker],
    start_date: datetime,
) -> None:
    """Test has_task_started returns False for non-existent task."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Task that doesn't exist
    nonexistent_task = TaskId("t_nonexistent")

    # Should return False without raising an error
    assert not state.has_task_started(nonexistent_task)


def test_get_started_completion_tasks_not_in_version(
    base_workers: list[Worker],
) -> None:
    """Test get_started_completion_tasks_by_worker skips old-version tasks."""
    from fluxx.data.models import StartedCompletion

    start_date = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    version_id = DAGVersionId("v1")
    old_version_id = DAGVersionId("v0")

    # Task only in old version
    task = Task(
        id=TaskId("t1"),
        title="Old Task",
        description="Only in old version",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            hours_logged=2.0,
            start_time=datetime(2023, 12, 15, tzinfo=UTC),
        ),
    )

    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={old_version_id: task},  # Only in old version
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,  # Current version is v1
        node_map={TaskId("t1"): PersistentObjectId("pt1")},
    )

    metadata = ProjectMetadata(
        name="Test Project",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    state = SimulationState(project, start_date, base_workers)
    tasks_by_worker = state.get_started_completion_tasks_by_worker()

    # Task should be skipped because it's not in current version
    assert len(tasks_by_worker) == 0
