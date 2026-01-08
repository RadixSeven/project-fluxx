"""Tests for simulation scheduler logic."""

from datetime import UTC, datetime

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
    PossibleWorldReference,
    Project,
    ProjectMetadata,
    StartedCompletion,
    Task,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)
from fluxx.jira.models import JiraIssueKey, JiraReference
from fluxx.simulation.scheduler import (
    ResolveBranchAction,
    StartTaskAction,
    are_all_dependencies_satisfied,
    are_all_workers_idle,
    are_tasks_remaining,
    detect_deadlock,
    format_task_for_log,
    get_eligible_tasks,
    get_eligible_workers,
    get_incomplete_tasks,
    get_unresolved_branches,
    get_worker_in_progress_task_count,
    has_existing_in_progress_tasks,
    is_branch_node,
    is_dependency_on_branch,
    is_dependency_on_task_end,
    is_dependency_on_task_start,
    is_dependency_satisfied,
    is_task_eligible,
    is_task_node,
    is_worker_allowed_for_task,
    is_worker_excluded_for_task,
    select_next_action,
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
    """Create a simple project with tasks for dependency testing."""
    # Task with no dependencies
    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[],
    )

    # Task depending on t1's END
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


# Tests for dependency endpoint type checking


def test_is_dependency_on_task_start() -> None:
    """Test detecting START endpoint dependencies."""
    dep_start = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t1"),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    dep_end = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t1"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    assert is_dependency_on_task_start(dep_start)
    assert not is_dependency_on_task_start(dep_end)


def test_is_dependency_on_task_end() -> None:
    """Test detecting END endpoint dependencies."""
    dep_start = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t1"),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    dep_end = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t1"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    assert is_dependency_on_task_end(dep_end)
    assert not is_dependency_on_task_end(dep_start)


def test_is_dependency_on_branch() -> None:
    """Test detecting OCCURRENCE_POINT endpoint dependencies."""
    dep_occurrence = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=BranchId("b1"),
        target_endpoint=Endpoint.OCCURRENCE,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    dep_end = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t1"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    assert is_dependency_on_branch(dep_occurrence)
    assert not is_dependency_on_branch(dep_end)


# Tests for node type checking


def test_is_task_node(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test checking if a node is a task."""
    state = SimulationState(simple_project, start_date, base_workers)

    assert is_task_node(TaskId("t1"), state)
    assert is_task_node(TaskId("t2"), state)
    assert not is_task_node(TaskId("t_nonexistent"), state)


def test_is_branch_node(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test checking if a node is a branch."""
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

    assert is_branch_node(BranchId("b1"), state)
    assert not is_branch_node(TaskId("t1"), state)
    assert not is_branch_node(BranchId("b_nonexistent"), state)


# Tests for dependency satisfaction


def test_is_dependency_satisfied_task_end(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test dependency on task END endpoint."""
    state = SimulationState(simple_project, start_date, base_workers)

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t1"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # Task not completed -> not satisfied
    assert not is_dependency_satisfied(dep, state)

    # Complete the task -> satisfied
    state.completed_tasks.add(TaskId("t1"))
    assert is_dependency_satisfied(dep, state)


def test_is_dependency_satisfied_task_start(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test dependency on task START endpoint."""
    state = SimulationState(simple_project, start_date, base_workers)

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t1"),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # Task not started -> not satisfied
    assert not is_dependency_satisfied(dep, state)

    # Task in progress -> satisfied
    state.in_progress_tasks.add(TaskId("t1"))
    assert is_dependency_satisfied(dep, state)

    # Task completed -> also satisfied
    state.in_progress_tasks.remove(TaskId("t1"))
    state.completed_tasks.add(TaskId("t1"))
    assert is_dependency_satisfied(dep, state)


def test_is_dependency_satisfied_branch_resolved(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test dependency on branch (just resolved, any world)."""
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
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={simple_project.dag.current_version_id: branch},
    )
    state.project.dag.node_map[BranchId("b1")] = PersistentObjectId("pb1")
    state.project.persistent_branches[PersistentObjectId("pb1")] = persistent_branch

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=BranchId("b1"),
        target_endpoint=Endpoint.OCCURRENCE,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # Branch not resolved -> not satisfied
    assert not is_dependency_satisfied(dep, state)

    # Resolve branch -> satisfied
    state.resolved_branches[BranchId("b1")] = PossibleWorldId("pw1")
    assert is_dependency_satisfied(dep, state)


def test_is_dependency_satisfied_possible_world(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test dependency on specific possible world."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Add a branch
    branch = Branch(
        id=BranchId("b1"),
        title="Branch 1",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0),
            PossibleWorld(id=PossibleWorldId("pw2"), title="World 2", weight=1.0),
        ],
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={simple_project.dag.current_version_id: branch},
    )
    state.project.dag.node_map[BranchId("b1")] = PersistentObjectId("pb1")
    state.project.persistent_branches[PersistentObjectId("pb1")] = persistent_branch

    # Dependency on specific world (pw1)
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=BranchId("b1:pw1"),
        target_endpoint=Endpoint.OCCURRENCE,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # Branch not resolved -> not satisfied
    assert not is_dependency_satisfied(dep, state)

    # Resolve to different world -> not satisfied
    state.resolved_branches[BranchId("b1")] = PossibleWorldId("pw2")
    assert not is_dependency_satisfied(dep, state)

    # Resolve to correct world -> satisfied
    state.resolved_branches[BranchId("b1")] = PossibleWorldId("pw1")
    assert is_dependency_satisfied(dep, state)


def test_is_dependency_satisfied_unknown_node(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test dependency on non-existent node returns False."""
    state = SimulationState(simple_project, start_date, base_workers)

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t_nonexistent"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    assert not is_dependency_satisfied(dep, state)


def test_are_all_dependencies_satisfied(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test checking all dependencies of a task."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Task 1 has no dependencies -> all satisfied
    task1 = state.get_task(TaskId("t1"))
    assert are_all_dependencies_satisfied(task1, state)

    # Task 2 depends on task 1 END
    task2 = state.get_task(TaskId("t2"))
    assert not are_all_dependencies_satisfied(task2, state)

    # Complete task 1 -> task 2 dependencies satisfied
    state.completed_tasks.add(TaskId("t1"))
    assert are_all_dependencies_satisfied(task2, state)


# Tests for worker eligibility


def test_is_worker_allowed_for_task_no_whitelist() -> None:
    """Test worker allowed when no whitelist exists."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=None,  # No whitelist
    )

    assert is_worker_allowed_for_task(task, WorkerId("w1"))
    assert is_worker_allowed_for_task(task, WorkerId("w2"))


def test_is_worker_allowed_for_task_with_whitelist() -> None:
    """Test worker allowed with whitelist."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[WorkerId("w1"), WorkerId("w2")],
    )

    assert is_worker_allowed_for_task(task, WorkerId("w1"))
    assert is_worker_allowed_for_task(task, WorkerId("w2"))
    assert not is_worker_allowed_for_task(task, WorkerId("w3"))


def test_is_worker_excluded_for_task_no_exclusions(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test worker not excluded when no exclusions exist."""
    state = SimulationState(simple_project, start_date, base_workers)

    task = Task(
        id=TaskId("t3"),
        title="Task 3",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        excluded_worker_tasks=[],  # No exclusions
    )

    assert not is_worker_excluded_for_task(task, WorkerId("w1"), state)


def test_is_worker_excluded_for_task_with_exclusion(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test worker excluded due to assignment to excluded task."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Get task1 and create a version with StartedCompletion
    task1 = state.get_task(TaskId("t1"))
    task1_started = task1.model_copy(
        update={
            "completion": StartedCompletion(
                assignee=WorkerId("w1"),
                start_time=start_date,
                hours_logged=0.0,
            )
        }
    )
    # Update the persistent task version with the started task
    persistent_id = simple_project.dag.node_map[TaskId("t1")]
    version_id = simple_project.dag.current_version_id
    simple_project.persistent_tasks[persistent_id].versions[version_id] = task1_started

    # Create a new task that excludes workers assigned to t1
    task_new = Task(
        id=TaskId("t3"),
        title="Task 3",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        excluded_worker_tasks=[TaskId("t1")],
    )

    # Worker w1 should be excluded (assigned to t1)
    assert is_worker_excluded_for_task(task_new, WorkerId("w1"), state)

    # Worker w2 should not be excluded (not assigned to t1)
    assert not is_worker_excluded_for_task(task_new, WorkerId("w2"), state)


def test_is_worker_excluded_nonexistent_task(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test worker exclusion check handles non-existent excluded tasks."""
    state = SimulationState(simple_project, start_date, base_workers)

    task = Task(
        id=TaskId("t3"),
        title="Task 3",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        excluded_worker_tasks=[TaskId("t_nonexistent")],
    )

    # Should not raise error, just skip the nonexistent task
    assert not is_worker_excluded_for_task(task, WorkerId("w1"), state)


def test_get_eligible_workers(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test getting eligible workers for a task."""
    state = SimulationState(simple_project, start_date, base_workers)

    task = Task(
        id=TaskId("t3"),
        title="Task 3",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Both workers available initially
    eligible = get_eligible_workers(task, state)
    assert len(eligible) == 2
    assert WorkerId("w1") in eligible
    assert WorkerId("w2") in eligible

    # Assign w1 to a task -> only w2 eligible
    state.worker_states[WorkerId("w1")].current_task = TaskId("t1")
    eligible = get_eligible_workers(task, state)
    assert len(eligible) == 1
    assert WorkerId("w2") in eligible


def test_get_eligible_workers_with_whitelist(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test getting eligible workers with whitelist."""
    state = SimulationState(simple_project, start_date, base_workers)

    task = Task(
        id=TaskId("t3"),
        title="Task 3",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[WorkerId("w1")],  # Only w1 allowed
    )

    eligible = get_eligible_workers(task, state)
    assert len(eligible) == 1
    assert WorkerId("w1") in eligible


def test_get_eligible_workers_with_exclusion(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test getting eligible workers with exclusions."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Get task1 and create a version with StartedCompletion (assign w1)
    task1 = state.get_task(TaskId("t1"))
    task1_started = task1.model_copy(
        update={
            "completion": StartedCompletion(
                assignee=WorkerId("w1"),
                start_time=start_date,
                hours_logged=0.0,
            )
        }
    )
    # Update the persistent task version with the started task
    persistent_id = simple_project.dag.node_map[TaskId("t1")]
    version_id = simple_project.dag.current_version_id
    simple_project.persistent_tasks[persistent_id].versions[version_id] = task1_started

    # Create task that excludes workers from t1
    task = Task(
        id=TaskId("t3"),
        title="Task 3",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        excluded_worker_tasks=[TaskId("t1")],
    )

    eligible = get_eligible_workers(task, state)
    assert len(eligible) == 1
    assert WorkerId("w2") in eligible  # Only w2, w1 is excluded


# Tests for task eligibility


def test_is_task_eligible_basic(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test basic task eligibility."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Task 1 has no dependencies -> eligible
    task1 = state.get_task(TaskId("t1"))
    assert is_task_eligible(task1, state)

    # Task 2 depends on task 1 -> not eligible
    task2 = state.get_task(TaskId("t2"))
    assert not is_task_eligible(task2, state)


def test_is_task_eligible_already_completed(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test task not eligible if already completed."""
    state = SimulationState(simple_project, start_date, base_workers)

    task1 = state.get_task(TaskId("t1"))
    state.completed_tasks.add(TaskId("t1"))

    assert not is_task_eligible(task1, state)


def test_is_task_eligible_in_progress(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test task not eligible if in progress."""
    state = SimulationState(simple_project, start_date, base_workers)

    task1 = state.get_task(TaskId("t1"))
    state.in_progress_tasks.add(TaskId("t1"))

    assert not is_task_eligible(task1, state)


def test_is_task_eligible_no_workers(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test task not eligible if no workers available."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Assign both workers to other tasks
    state.worker_states[WorkerId("w1")].current_task = TaskId("t1")
    state.worker_states[WorkerId("w2")].current_task = TaskId("t2")

    task1 = state.get_task(TaskId("t1"))
    assert not is_task_eligible(task1, state)


def test_get_eligible_tasks(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test getting all eligible tasks."""
    state = SimulationState(simple_project, start_date, base_workers)

    eligible = get_eligible_tasks(state)

    # Only task 1 is eligible (task 2 depends on task 1)
    assert len(eligible) == 1
    assert eligible[0].id == TaskId("t1")

    # Complete task 1 -> task 2 becomes eligible
    state.completed_tasks.add(TaskId("t1"))
    eligible = get_eligible_tasks(state)

    assert len(eligible) == 1
    assert eligible[0].id == TaskId("t2")


# Tests for branch resolution


def test_get_unresolved_branches_none(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test getting unresolved branches when none exist."""
    state = SimulationState(simple_project, start_date, base_workers)

    unresolved = get_unresolved_branches(state)
    assert len(unresolved) == 0


def test_get_unresolved_branches_exists(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test getting unresolved branches."""
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
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={simple_project.dag.current_version_id: branch},
    )
    state.project.dag.node_map[BranchId("b1")] = PersistentObjectId("pb1")
    state.project.persistent_branches[PersistentObjectId("pb1")] = persistent_branch

    unresolved = get_unresolved_branches(state)
    assert len(unresolved) == 1
    assert unresolved[0] == BranchId("b1")

    # Resolve the branch
    state.resolved_branches[BranchId("b1")] = PossibleWorldId("pw1")
    unresolved = get_unresolved_branches(state)
    assert len(unresolved) == 0


# Tests for action selection


def test_select_next_action_task(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test selecting action when task is available."""
    state = SimulationState(simple_project, start_date, base_workers)
    rng = np.random.default_rng(seed=42)

    action = select_next_action(state, rng)

    assert action is not None
    assert isinstance(action, StartTaskAction)
    assert action.task_id == TaskId("t1")


def test_select_next_action_branch(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test selecting action when branch needs resolution."""
    state = SimulationState(simple_project, start_date, base_workers)
    rng = np.random.default_rng(seed=42)

    # Complete all tasks so only branch resolution is possible
    state.completed_tasks.add(TaskId("t1"))
    state.completed_tasks.add(TaskId("t2"))

    # Add an unresolved branch
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

    action = select_next_action(state, rng)

    assert action is not None
    assert isinstance(action, ResolveBranchAction)
    assert action.branch_id == BranchId("b1")


def test_select_next_action_none(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test selecting action when none available (deadlock)."""
    state = SimulationState(simple_project, start_date, base_workers)
    rng = np.random.default_rng(seed=42)

    # Make task 2 unable to start (no workers)
    state.completed_tasks.add(TaskId("t1"))
    state.worker_states[WorkerId("w1")].current_task = TaskId("t_other")
    state.worker_states[WorkerId("w2")].current_task = TaskId("t_other")

    action = select_next_action(state, rng)

    # Should return None (or task 2 if workers were available)
    # With no workers, task 2 isn't eligible
    assert action is None


def test_select_next_action_random_selection(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test that action selection uses RNG for randomness."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Same seed should give same result
    rng1 = np.random.default_rng(seed=123)
    rng2 = np.random.default_rng(seed=123)

    action1 = select_next_action(state, rng1)
    action2 = select_next_action(state, rng2)

    assert action1 == action2


# Tests for deadlock detection


def test_are_all_workers_idle_true(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test detecting when all workers are idle."""
    state = SimulationState(simple_project, start_date, base_workers)

    assert are_all_workers_idle(state)


def test_are_all_workers_idle_false(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test detecting when workers are busy."""
    state = SimulationState(simple_project, start_date, base_workers)

    state.worker_states[WorkerId("w1")].current_task = TaskId("t1")

    assert not are_all_workers_idle(state)


def test_are_tasks_remaining_true(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test detecting when tasks remain."""
    state = SimulationState(simple_project, start_date, base_workers)

    assert are_tasks_remaining(state)


def test_are_tasks_remaining_false(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test detecting when all tasks complete."""
    state = SimulationState(simple_project, start_date, base_workers)

    state.completed_tasks.add(TaskId("t1"))
    state.completed_tasks.add(TaskId("t2"))

    assert not are_tasks_remaining(state)


def test_detect_deadlock_false_workers_busy(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test no deadlock when workers are busy."""
    state = SimulationState(simple_project, start_date, base_workers)

    state.worker_states[WorkerId("w1")].current_task = TaskId("t1")

    assert not detect_deadlock(state)


def test_detect_deadlock_false_all_complete(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test no deadlock when all tasks complete."""
    state = SimulationState(simple_project, start_date, base_workers)

    state.completed_tasks.add(TaskId("t1"))
    state.completed_tasks.add(TaskId("t2"))

    assert not detect_deadlock(state)


def test_detect_deadlock_true(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test deadlock detection when stuck."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Complete task 1, but make task 2 impossible to start
    # (e.g., by having no eligible workers due to whitelist)
    state.completed_tasks.add(TaskId("t1"))

    # Modify task 2 to only allow non-existent worker
    task2 = state.get_task(TaskId("t2"))
    task2.allowed_workers = [WorkerId("nonexistent")]

    # All workers idle, task remains, but can't start -> deadlock
    assert detect_deadlock(state)


def test_detect_deadlock_false_task_eligible(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test no deadlock when eligible task exists."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Task 1 is eligible, so no deadlock
    assert not detect_deadlock(state)


def test_is_dependency_satisfied_possible_world_invalid_branch(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test dependency on possible world when branch doesn't exist."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Dependency on a possible world for a branch that doesn't exist
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=PossibleWorldReference("nonexistent_branch:pw1"),
        target_endpoint=Endpoint.OCCURRENCE,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # Should return False since branch doesn't exist
    assert not is_dependency_satisfied(dep, state)


def test_is_dependency_satisfied_task_unknown_endpoint(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test dependency on task with unknown endpoint returns False."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Dependency with OCCURRENCE endpoint on a task (invalid)
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t1"),
        target_endpoint=Endpoint.OCCURRENCE,  # Invalid for tasks
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # Should return False for unknown endpoint type
    assert not is_dependency_satisfied(dep, state)


def test_is_dependency_satisfied_task_not_found(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test dependency on task that doesn't exist in current version returns False."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Create a task that exists in persistent_tasks but NOT in current version
    old_version = DAGVersionId("v0")
    old_task = Task(
        id=TaskId("t_old_task"),
        title="Old Task",
        description="Task only in old version",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    persistent_old = PersistentTask(
        id=PersistentObjectId("pt_old"),
        versions={old_version: old_task},  # Only in old version, not current
    )

    # Add to project
    state.project.dag.node_map[TaskId("t_old_task")] = PersistentObjectId("pt_old")
    state.project.persistent_tasks[PersistentObjectId("pt_old")] = persistent_old

    # Now is_task_node() will return True, but get_task() will raise KeyError
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t_old_task"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # Should return False because get_task() will raise KeyError
    assert not is_dependency_satisfied(dep, state)


def test_is_dependency_satisfied_parent_task_end_incomplete(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test parent task END dependency is not satisfied when children incomplete."""
    # Create parent task with children
    parent_task = Task(
        id=TaskId("t_parent"),
        title="Parent",
        description="Parent task",
        duration_distribution=None,
        children=[TaskId("t_child1"), TaskId("t_child2")],
    )

    child1 = Task(
        id=TaskId("t_child1"),
        title="Child 1",
        description="First child",
        parent_id=TaskId("t_parent"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    child2 = Task(
        id=TaskId("t_child2"),
        title="Child 2",
        description="Second child",
        parent_id=TaskId("t_parent"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    version_id = DAGVersionId("v1")
    project = Project(
        metadata=ProjectMetadata(
            name="Test",
            created=datetime(2024, 1, 1, tzinfo=UTC),
            last_modified=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                TaskId("t_parent"): PersistentObjectId("pp"),
                TaskId("t_child1"): PersistentObjectId("pc1"),
                TaskId("t_child2"): PersistentObjectId("pc2"),
            },
        ),
        persistent_tasks={
            PersistentObjectId("pp"): PersistentTask(
                id=PersistentObjectId("pp"), versions={version_id: parent_task}
            ),
            PersistentObjectId("pc1"): PersistentTask(
                id=PersistentObjectId("pc1"), versions={version_id: child1}
            ),
            PersistentObjectId("pc2"): PersistentTask(
                id=PersistentObjectId("pc2"), versions={version_id: child2}
            ),
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # Dependency on parent task END
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t_parent"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # No children completed - dependency not satisfied
    assert not is_dependency_satisfied(dep, state)

    # Complete child1 but not child2 - still not satisfied
    state.completed_tasks.add(TaskId("t_child1"))
    assert not is_dependency_satisfied(dep, state)


def test_is_dependency_satisfied_parent_task_end_complete(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test parent task END dependency is satisfied when all children complete."""
    # Create parent task with children
    parent_task = Task(
        id=TaskId("t_parent"),
        title="Parent",
        description="Parent task",
        duration_distribution=None,
        children=[TaskId("t_child1"), TaskId("t_child2")],
    )

    child1 = Task(
        id=TaskId("t_child1"),
        title="Child 1",
        description="First child",
        parent_id=TaskId("t_parent"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    child2 = Task(
        id=TaskId("t_child2"),
        title="Child 2",
        description="Second child",
        parent_id=TaskId("t_parent"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    version_id = DAGVersionId("v1")
    project = Project(
        metadata=ProjectMetadata(
            name="Test",
            created=datetime(2024, 1, 1, tzinfo=UTC),
            last_modified=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        dag=DAG(
            id=DAGId("dag1"),
            current_version_id=version_id,
            node_map={
                TaskId("t_parent"): PersistentObjectId("pp"),
                TaskId("t_child1"): PersistentObjectId("pc1"),
                TaskId("t_child2"): PersistentObjectId("pc2"),
            },
        ),
        persistent_tasks={
            PersistentObjectId("pp"): PersistentTask(
                id=PersistentObjectId("pp"), versions={version_id: parent_task}
            ),
            PersistentObjectId("pc1"): PersistentTask(
                id=PersistentObjectId("pc1"), versions={version_id: child1}
            ),
            PersistentObjectId("pc2"): PersistentTask(
                id=PersistentObjectId("pc2"), versions={version_id: child2}
            ),
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # Dependency on parent task END
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t_parent"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # Complete both children - dependency satisfied
    state.completed_tasks.add(TaskId("t_child1"))
    state.completed_tasks.add(TaskId("t_child2"))
    assert is_dependency_satisfied(dep, state)


def test_get_eligible_tasks_skips_old_version_tasks(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test that get_eligible_tasks skips tasks not in current version."""
    state = SimulationState(simple_project, start_date, base_workers)

    # Add a task that only exists in an old version
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

    # Get eligible tasks - should not include the old version task
    eligible = get_eligible_tasks(state)

    # Should only include t1 (t2 depends on t1, old task isn't in current version)
    assert len(eligible) == 1
    assert eligible[0].id == TaskId("t1")


def test_is_branch_eligible_nonexistent_branch(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test is_branch_eligible with a nonexistent branch ID."""
    from fluxx.simulation.scheduler import is_branch_eligible

    state = SimulationState(simple_project, start_date, base_workers)

    # Branch that doesn't exist in the project
    nonexistent_branch = BranchId("b_nonexistent")

    # Should return False for nonexistent branches
    assert not is_branch_eligible(nonexistent_branch, state)


def test_is_dependency_satisfied_parent_task_with_no_runnable_children(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test dependency on parent task when all children depend on unresolved worlds."""
    from fluxx.simulation.scheduler import is_dependency_satisfied

    # Create a branch
    branch_id = BranchId("b1")
    branch = Branch(
        id=branch_id,
        title="Branch",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0),
            PossibleWorld(id=PossibleWorldId("pw2"), title="World 2", weight=1.0),
        ],
    )

    # Create parent task
    parent_id = TaskId("t_parent")
    parent = Task(
        id=parent_id,
        title="Parent",
        description="Test",
        children=[TaskId("t_child")],
    )

    # Create child that depends on a specific possible world
    child_id = TaskId("t_child")
    child = Task(
        id=child_id,
        title="Child",
        description="Test",
        parent_id=parent_id,
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=PossibleWorldReference(f"{branch_id}:pw1"),
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create task that depends on parent's END
    dependent_id = TaskId("t_dependent")
    dependent = Task(
        id=dependent_id,
        title="Dependent",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=parent_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Add to project
    project = Project(
        **simple_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=simple_project.dag.model_copy(
            update={
                "node_map": {
                    parent_id: PersistentObjectId("pp"),
                    child_id: PersistentObjectId("pc"),
                    dependent_id: PersistentObjectId("pd"),
                    branch_id: PersistentObjectId("pb"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pp"): PersistentTask(
                id=PersistentObjectId("pp"),
                versions={simple_project.dag.current_version_id: parent},
            ),
            PersistentObjectId("pc"): PersistentTask(
                id=PersistentObjectId("pc"),
                versions={simple_project.dag.current_version_id: child},
            ),
            PersistentObjectId("pd"): PersistentTask(
                id=PersistentObjectId("pd"),
                versions={simple_project.dag.current_version_id: dependent},
            ),
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={simple_project.dag.current_version_id: branch},
            ),
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # Resolve branch to pw2 (NOT pw1 which child depends on)
    state.resolve_branch(branch_id, PossibleWorldId("pw2"))

    # Check if dependency on parent END is satisfied
    # Should return False because child cannot run (depends on pw1 but pw2 was
    # chosen)
    assert not is_dependency_satisfied(dependent.dependencies[0], state, dependent)


def test_is_child_runnable_nonexistent_child(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test is_child_runnable_in_current_world with nonexistent child."""
    from fluxx.simulation.scheduler import is_child_runnable_in_current_world

    state = SimulationState(simple_project, start_date, base_workers)

    # Try to check if nonexistent child is runnable
    nonexistent_child = TaskId("t_nonexistent")
    assert not is_child_runnable_in_current_world(nonexistent_child, state)


def test_is_child_runnable_with_possible_world_dependencies(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test is_child_runnable with possible world dependencies."""
    from fluxx.simulation.scheduler import is_child_runnable_in_current_world

    # Create a branch
    branch_id = BranchId("b1")
    branch = Branch(
        id=branch_id,
        title="Branch",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0),
            PossibleWorld(id=PossibleWorldId("pw2"), title="World 2", weight=1.0),
        ],
    )

    # Create child that depends on possible world
    child_id = TaskId("t_child")
    child = Task(
        id=child_id,
        title="Child",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=PossibleWorldReference(f"{branch_id}:pw1"),
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Add to project
    project = Project(
        **simple_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=simple_project.dag.model_copy(
            update={
                "node_map": {
                    child_id: PersistentObjectId("pc"),
                    branch_id: PersistentObjectId("pb"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pc"): PersistentTask(
                id=PersistentObjectId("pc"),
                versions={simple_project.dag.current_version_id: child},
            ),
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={simple_project.dag.current_version_id: branch},
            ),
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # Before branch resolution, child should be runnable (world is potentially
    # satisfiable)
    assert is_child_runnable_in_current_world(child_id, state)

    # Resolve branch to pw1 (the world child depends on)
    state.resolve_branch(branch_id, PossibleWorldId("pw1"))

    # Child should still be runnable
    assert is_child_runnable_in_current_world(child_id, state)

    # Create new state and resolve to pw2 (different world)
    state2 = SimulationState(project, start_date, base_workers)
    state2.resolve_branch(branch_id, PossibleWorldId("pw2"))

    # Child should NOT be runnable (depends on pw1 but pw2 was chosen)
    assert not is_child_runnable_in_current_world(child_id, state2)


def test_is_child_runnable_with_parent_task_dependency(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test is_child_runnable when dependency is on a parent task."""
    from fluxx.simulation.scheduler import is_child_runnable_in_current_world

    # Create parent task
    parent_id = TaskId("t_parent")
    parent = Task(
        id=parent_id,
        title="Parent",
        description="Test",
        children=[TaskId("t_parent_child")],
    )

    # Create child of parent
    parent_child_id = TaskId("t_parent_child")
    parent_child = Task(
        id=parent_child_id,
        title="Parent Child",
        description="Test",
        parent_id=parent_id,
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create another task that depends on the parent
    dependent_id = TaskId("t_dependent")
    dependent = Task(
        id=dependent_id,
        title="Dependent",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=parent_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Add to project
    project = Project(
        **simple_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=simple_project.dag.model_copy(
            update={
                "node_map": {
                    parent_id: PersistentObjectId("pp"),
                    parent_child_id: PersistentObjectId("ppc"),
                    dependent_id: PersistentObjectId("pd"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pp"): PersistentTask(
                id=PersistentObjectId("pp"),
                versions={simple_project.dag.current_version_id: parent},
            ),
            PersistentObjectId("ppc"): PersistentTask(
                id=PersistentObjectId("ppc"),
                versions={simple_project.dag.current_version_id: parent_child},
            ),
            PersistentObjectId("pd"): PersistentTask(
                id=PersistentObjectId("pd"),
                versions={simple_project.dag.current_version_id: dependent},
            ),
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # Dependent should be runnable because parent's child is runnable
    assert is_child_runnable_in_current_world(dependent_id, state)


def test_is_child_runnable_with_leaf_task_dependency(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test is_child_runnable when dependency is on a leaf task."""
    from fluxx.simulation.scheduler import is_child_runnable_in_current_world

    # Create two tasks where task2 depends on task1
    task1_id = TaskId("t1")
    task1 = Task(
        id=task1_id,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    task2_id = TaskId("t2")
    task2 = Task(
        id=task2_id,
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task1_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Add to project
    project = Project(
        **simple_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=simple_project.dag.model_copy(
            update={
                "node_map": {
                    task1_id: PersistentObjectId("p1"),
                    task2_id: PersistentObjectId("p2"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("p1"): PersistentTask(
                id=PersistentObjectId("p1"),
                versions={simple_project.dag.current_version_id: task1},
            ),
            PersistentObjectId("p2"): PersistentTask(
                id=PersistentObjectId("p2"),
                versions={simple_project.dag.current_version_id: task2},
            ),
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # Task2 should be runnable (task1 is a simple leaf task)
    assert is_child_runnable_in_current_world(task2_id, state)


def test_is_child_runnable_with_parent_dependency_no_runnable_children(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test is_child_runnable when parent dependency has no runnable children."""
    from fluxx.simulation.scheduler import is_child_runnable_in_current_world

    # Create a branch
    branch_id = BranchId("b1")
    branch = Branch(
        id=branch_id,
        title="Branch",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0),
            PossibleWorld(id=PossibleWorldId("pw2"), title="World 2", weight=1.0),
        ],
    )

    # Create parent task
    parent_id = TaskId("t_parent")
    parent = Task(
        id=parent_id,
        title="Parent",
        description="Test",
        children=[TaskId("t_parent_child")],
    )

    # Create child of parent that depends on pw1
    parent_child_id = TaskId("t_parent_child")
    parent_child = Task(
        id=parent_child_id,
        title="Parent Child",
        description="Test",
        parent_id=parent_id,
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=PossibleWorldReference(f"{branch_id}:pw1"),
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create task that depends on parent
    dependent_id = TaskId("t_dependent")
    dependent = Task(
        id=dependent_id,
        title="Dependent",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=parent_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Add to project
    project = Project(
        **simple_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=simple_project.dag.model_copy(
            update={
                "node_map": {
                    parent_id: PersistentObjectId("pp"),
                    parent_child_id: PersistentObjectId("ppc"),
                    dependent_id: PersistentObjectId("pd"),
                    branch_id: PersistentObjectId("pb"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("pp"): PersistentTask(
                id=PersistentObjectId("pp"),
                versions={simple_project.dag.current_version_id: parent},
            ),
            PersistentObjectId("ppc"): PersistentTask(
                id=PersistentObjectId("ppc"),
                versions={simple_project.dag.current_version_id: parent_child},
            ),
            PersistentObjectId("pd"): PersistentTask(
                id=PersistentObjectId("pd"),
                versions={simple_project.dag.current_version_id: dependent},
            ),
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={simple_project.dag.current_version_id: branch},
            ),
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # Resolve branch to pw2 (NOT pw1 which parent's child depends on)
    state.resolve_branch(branch_id, PossibleWorldId("pw2"))

    # Dependent should NOT be runnable because parent has no runnable children
    assert not is_child_runnable_in_current_world(dependent_id, state)


def test_is_child_runnable_leaf_task_not_runnable(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test is_child_runnable when leaf task dependency is not runnable."""
    from fluxx.simulation.scheduler import is_child_runnable_in_current_world

    # Create a branch
    branch_id = BranchId("b1")
    branch = Branch(
        id=branch_id,
        title="Branch",
        description="Test",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0),
            PossibleWorld(id=PossibleWorldId("pw2"), title="World 2", weight=1.0),
        ],
    )

    # Create task1 (leaf) that depends on a specific possible world
    task1_id = TaskId("t1")
    task1 = Task(
        id=task1_id,
        title="Task 1",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=PossibleWorldReference(f"{branch_id}:pw1"),
                target_endpoint=Endpoint.OCCURRENCE,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create task2 that depends on task1 (leaf task dependency)
    task2_id = TaskId("t2")
    task2 = Task(
        id=task2_id,
        title="Task 2",
        description="Test",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task1_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Build project
    project = Project(
        **simple_project.model_dump(
            exclude={"persistent_tasks", "persistent_branches", "dag"}
        ),
        dag=simple_project.dag.model_copy(
            update={
                "node_map": {
                    task1_id: PersistentObjectId("p1"),
                    task2_id: PersistentObjectId("p2"),
                    branch_id: PersistentObjectId("pb"),
                }
            }
        ),
        persistent_tasks={
            PersistentObjectId("p1"): PersistentTask(
                id=PersistentObjectId("p1"),
                versions={simple_project.dag.current_version_id: task1},
            ),
            PersistentObjectId("p2"): PersistentTask(
                id=PersistentObjectId("p2"),
                versions={simple_project.dag.current_version_id: task2},
            ),
        },
        persistent_branches={
            PersistentObjectId("pb"): PersistentBranch(
                id=PersistentObjectId("pb"),
                versions={simple_project.dag.current_version_id: branch},
            ),
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # Resolve branch to pw2 (NOT pw1 which task1 depends on)
    state.resolve_branch(branch_id, PossibleWorldId("pw2"))

    # task2 should NOT be runnable because task1 (leaf) is not runnable
    # This tests line 235-236: recursive check on leaf task fails
    assert not is_child_runnable_in_current_world(task2_id, state)


def test_is_child_runnable_task_dependency_not_in_version(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test is_child_runnable when task dependency exists but not in current version."""
    from fluxx.simulation.scheduler import is_child_runnable_in_current_world

    # Create task in old version only
    old_version_id = DAGVersionId("v0")
    old_task_id = TaskId("t_old")
    old_task = Task(
        id=old_task_id,
        title="Old Task",
        description="Task only in old version",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create task that depends on old task
    new_task_id = TaskId("t_new")
    new_task = Task(
        id=new_task_id,
        title="New Task",
        description="Task that depends on old task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=old_task_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Build project
    project = Project(
        **simple_project.model_dump(exclude={"persistent_tasks", "dag"}),
        dag=simple_project.dag.model_copy(
            update={
                "node_map": {
                    old_task_id: PersistentObjectId("p_old"),
                    new_task_id: PersistentObjectId("p_new"),
                }
            }
        ),
        persistent_tasks={
            # old_task only in old version, not in current version
            PersistentObjectId("p_old"): PersistentTask(
                id=PersistentObjectId("p_old"),
                versions={old_version_id: old_task},
            ),
            # new_task in current version
            PersistentObjectId("p_new"): PersistentTask(
                id=PersistentObjectId("p_new"),
                versions={simple_project.dag.current_version_id: new_task},
            ),
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # new_task should NOT be runnable because old_task dependency raises KeyError
    # This tests line 237-238: KeyError when get_task fails
    assert not is_child_runnable_in_current_world(new_task_id, state)


def test_is_regular_dep_satisfiable_branch_dependency(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test _is_regular_dep_satisfiable returns True for branch dependencies."""
    from fluxx.simulation.scheduler import _is_regular_dep_satisfiable

    state = SimulationState(simple_project, start_date, base_workers)

    # Add a branch to the project
    branch_id = BranchId("b1")
    branch = Branch(
        id=branch_id,
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
    state.project.dag.node_map[branch_id] = PersistentObjectId("pb1")
    state.project.persistent_branches[PersistentObjectId("pb1")] = persistent_branch

    # Dependency on branch (regular dependency, not possible world)
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=branch_id,
        target_endpoint=Endpoint.OCCURRENCE,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    visited: set[TaskId] = set()
    # Branch dependencies are considered satisfiable (return True at line 207)
    assert _is_regular_dep_satisfiable(dep, state, visited)


def test_has_any_satisfiable_possible_world_dep_with_non_pw_dep(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test _has_any_satisfiable_possible_world_dep handles non-PW deps via mocking."""
    from unittest.mock import patch

    from fluxx.simulation.scheduler import _has_any_satisfiable_possible_world_dep

    state = SimulationState(simple_project, start_date, base_workers)

    # Create a dependency that looks like a possible world dep
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("fake_task"),  # Not actually a PW reference
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    # Mock type_explode_id to return None for as_world (simulating malformed input)
    with patch(
        "fluxx.simulation.scheduler.type_explode_id",
        return_value=(None, None, None),
    ):
        # Should return False because no satisfiable deps found (continues past None)
        result = _has_any_satisfiable_possible_world_dep([dep], state)
        assert result is False


# Tests for in-progress task handling


def test_get_worker_in_progress_task_count_no_tasks(
    simple_project: Project, base_workers: list[Worker], start_date: datetime
) -> None:
    """Test counting in-progress tasks when worker has none."""
    state = SimulationState(simple_project, start_date, base_workers)

    count = get_worker_in_progress_task_count(WorkerId("w1"), state)
    assert count == 0


def test_get_worker_in_progress_task_count_one_task(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test counting in-progress tasks when worker has one."""
    # Create a project with an in-progress task
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="In progress task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_date,
            hours_logged=4.0,
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

    count = get_worker_in_progress_task_count(WorkerId("w1"), state)
    assert count == 1

    # Worker 2 should have no in-progress tasks
    count_w2 = get_worker_in_progress_task_count(WorkerId("w2"), state)
    assert count_w2 == 0


def test_get_worker_in_progress_task_count_multiple_tasks(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test counting in-progress tasks when worker has multiple."""
    # Create tasks with same assignee
    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="In progress task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_date,
            hours_logged=2.0,
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
            hours_logged=3.0,
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

    count = get_worker_in_progress_task_count(WorkerId("w1"), state)
    assert count == 2


def test_get_worker_in_progress_task_count_excludes_simulation_in_progress(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test that tasks being processed in simulation are not counted."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="In progress task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_date,
            hours_logged=4.0,
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

    # Before marking as in-progress in simulation
    assert get_worker_in_progress_task_count(WorkerId("w1"), state) == 1

    # Mark task as in-progress in simulation
    state.in_progress_tasks.add(TaskId("t1"))

    # Should now return 0 (task is being processed)
    assert get_worker_in_progress_task_count(WorkerId("w1"), state) == 0


def test_has_existing_in_progress_tasks(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test has_existing_in_progress_tasks helper function."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="In progress task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_date,
            hours_logged=4.0,
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

    # Worker 1 has in-progress task
    assert has_existing_in_progress_tasks(WorkerId("w1"), state) is True

    # Worker 2 has no in-progress tasks
    assert has_existing_in_progress_tasks(WorkerId("w2"), state) is False


def test_get_eligible_workers_excludes_worker_with_in_progress_tasks(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test that get_eligible_workers excludes workers with in-progress tasks."""
    # Create a task that doesn't belong to any worker (new task)
    new_task = Task(
        id=TaskId("t2"),
        title="New Task",
        description="New task to assign",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create an in-progress task assigned to w1
    in_progress_task = Task(
        id=TaskId("t1"),
        title="In Progress Task",
        description="Already started",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_date,
            hours_logged=4.0,
        ),
    )

    version_id = DAGVersionId("v1")
    persistent_task1 = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: in_progress_task},
    )
    persistent_task2 = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={version_id: new_task},
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

    # Get eligible workers for the new task
    eligible = get_eligible_workers(new_task, state)

    # Only w2 should be eligible (w1 has in-progress task)
    assert WorkerId("w1") not in eligible
    assert WorkerId("w2") in eligible


# Tests for format_task_for_log


def test_format_task_for_log_without_jira_reference() -> None:
    """Test formatting a task without Jira reference."""
    task = Task(
        id=TaskId("task_123"),
        title="Test Task",
        description="A task without Jira reference",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    result = format_task_for_log(task)
    assert result == "task_123"


def test_format_task_for_log_with_jira_reference() -> None:
    """Test formatting a task with Jira reference."""
    task = Task(
        id=TaskId("task_456"),
        title="Test Task",
        description="A task with Jira reference",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        jira_reference=JiraReference(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="PROJ", issue_number=123),
        ),
    )

    result = format_task_for_log(task)
    assert result == "task_456 (PROJ-123)"


# Tests for get_incomplete_tasks


def test_get_incomplete_tasks_excludes_completed(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test that get_incomplete_tasks excludes completed tasks."""
    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Incomplete task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    task2 = Task(
        id=TaskId("t2"),
        title="Task 2",
        description="Another incomplete task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
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

    # Initially both tasks are incomplete
    incomplete = get_incomplete_tasks(state)
    assert len(incomplete) == 2
    task_ids = [t.id for t in incomplete]
    assert TaskId("t1") in task_ids
    assert TaskId("t2") in task_ids

    # Mark one task as completed - first start it, then complete it
    estimated_completion = datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC)
    state.start_task(TaskId("t1"), WorkerId("w1"), start_date, estimated_completion)
    state.complete_task(TaskId("t1"), start_date)

    # Now only one task should be incomplete
    incomplete = get_incomplete_tasks(state)
    assert len(incomplete) == 1
    assert incomplete[0].id == TaskId("t2")


def test_get_incomplete_tasks_excludes_parent_tasks(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test that get_incomplete_tasks excludes parent tasks (with children)."""
    child_task = Task(
        id=TaskId("child"),
        title="Child Task",
        description="A child task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        parent_id=TaskId("parent"),
    )

    parent_task = Task(
        id=TaskId("parent"),
        title="Parent Task",
        description="A parent task",
        duration_distribution=None,  # Parent tasks don't need durations
        children=[TaskId("child")],
    )

    version_id = DAGVersionId("v1")
    persistent_child = PersistentTask(
        id=PersistentObjectId("pt_child"),
        versions={version_id: child_task},
    )
    persistent_parent = PersistentTask(
        id=PersistentObjectId("pt_parent"),
        versions={version_id: parent_task},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("child"): PersistentObjectId("pt_child"),
            TaskId("parent"): PersistentObjectId("pt_parent"),
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
            PersistentObjectId("pt_child"): persistent_child,
            PersistentObjectId("pt_parent"): persistent_parent,
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # Only the child task should be in incomplete (parent is excluded)
    incomplete = get_incomplete_tasks(state)
    assert len(incomplete) == 1
    assert incomplete[0].id == TaskId("child")


def test_get_incomplete_tasks_handles_missing_version(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test that get_incomplete_tasks handles tasks without current version."""
    task1 = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Task with current version",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    version_id = DAGVersionId("v1")
    old_version_id = DAGVersionId("v0")

    persistent_task_current = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task1},
    )

    # This task only exists in an old version
    old_task = Task(
        id=TaskId("t2"),
        title="Old Task",
        description="Task from old version",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    persistent_task_old = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={old_version_id: old_task},
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
            PersistentObjectId("pt1"): persistent_task_current,
            PersistentObjectId("pt2"): persistent_task_old,
        },
    )

    state = SimulationState(project, start_date, base_workers)

    # Only task1 should be returned (task2 has no current version)
    incomplete = get_incomplete_tasks(state)
    assert len(incomplete) == 1
    assert incomplete[0].id == TaskId("t1")


# Tests for is_task_already_assigned_to_worker


def test_is_task_already_assigned_to_worker_true() -> None:
    """Test detecting when a task is already assigned to a specific worker."""
    from fluxx.simulation.scheduler import is_task_already_assigned_to_worker

    task = Task(
        id=TaskId("t1"),
        title="In Progress Task",
        description="Task already started by worker",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
            hours_logged=4.0,
        ),
    )

    # Task is assigned to w1
    assert is_task_already_assigned_to_worker(task, WorkerId("w1")) is True

    # Task is not assigned to w2
    assert is_task_already_assigned_to_worker(task, WorkerId("w2")) is False


def test_is_task_already_assigned_to_worker_not_started() -> None:
    """Test that unstarted tasks are not assigned to any worker."""
    from fluxx.simulation.scheduler import is_task_already_assigned_to_worker

    task = Task(
        id=TaskId("t1"),
        title="New Task",
        description="Task not yet started",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        # No completion (defaults to NotStartedCompletion)
    )

    assert is_task_already_assigned_to_worker(task, WorkerId("w1")) is False
    assert is_task_already_assigned_to_worker(task, WorkerId("w2")) is False


# Tests for the bug fix: workers should be able to work on their own in-progress tasks


def test_worker_can_work_on_own_in_progress_task(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test that a worker with in-progress tasks CAN work on their own assigned tasks.

    This is a regression test for a bug where workers with existing in-progress tasks
    (from Jira) were blocked from ALL tasks, including tasks already assigned to them.
    The fix allows workers to continue working on tasks they're already assigned to.
    """
    # Create an in-progress task assigned to w1
    in_progress_task = Task(
        id=TaskId("t1"),
        title="In Progress Task",
        description="Already started by w1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_date,
            hours_logged=4.0,
        ),
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: in_progress_task},
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

    # Worker 1 has an in-progress task (from Jira)
    assert has_existing_in_progress_tasks(WorkerId("w1"), state) is True

    # Get eligible workers for the in-progress task itself
    eligible = get_eligible_workers(in_progress_task, state)

    # CRITICAL: Worker 1 should be eligible for their own in-progress task
    # This is the bug fix - previously w1 would be excluded
    assert WorkerId("w1") in eligible

    # Worker 2 should NOT be eligible (task is assigned to w1, and w2 doesn't have
    # the in-progress exception)
    # Actually w2 doesn't have in-progress tasks, so they could work on it
    # The point is w1 IS eligible for their own task
    assert WorkerId("w2") in eligible  # w2 has no in-progress tasks


def test_worker_blocked_from_new_tasks_when_has_in_progress(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test that workers with in-progress tasks are still blocked from NEW tasks.

    This ensures the fix doesn't accidentally allow workers to take on new work
    when they have existing in-progress tasks - they should only be allowed to
    continue their own assigned tasks.
    """
    # Create an in-progress task assigned to w1
    in_progress_task = Task(
        id=TaskId("t1"),
        title="In Progress Task",
        description="Already started by w1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_date,
            hours_logged=4.0,
        ),
    )

    # Create a new task not assigned to anyone
    new_task = Task(
        id=TaskId("t2"),
        title="New Task",
        description="Not yet started",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        # No completion (NotStartedCompletion)
    )

    version_id = DAGVersionId("v1")
    persistent_task1 = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: in_progress_task},
    )
    persistent_task2 = PersistentTask(
        id=PersistentObjectId("pt2"),
        versions={version_id: new_task},
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

    # Worker 1 has an in-progress task
    assert has_existing_in_progress_tasks(WorkerId("w1"), state) is True

    # Get eligible workers for the NEW task (not assigned to w1)
    eligible = get_eligible_workers(new_task, state)

    # Worker 1 should NOT be eligible for the new task (they have in-progress work)
    assert WorkerId("w1") not in eligible

    # Worker 2 should be eligible (no in-progress tasks)
    assert WorkerId("w2") in eligible


def test_deadlock_avoided_when_worker_can_continue_own_tasks(
    base_workers: list[Worker], start_date: datetime
) -> None:
    """Test deadlock avoided when workers can continue their own in-progress tasks.

    This is the main scenario that was causing deadlocks: all remaining tasks are
    in-progress and assigned to a single worker, but that worker was blocked because
    they had in-progress tasks. With the fix, the worker should be able to continue
    their own tasks, avoiding deadlock.
    """
    # Create in-progress task assigned to w1 (simulates Jira import)
    in_progress_task = Task(
        id=TaskId("t1"),
        title="In Progress Task",
        description="Already started by w1 from Jira",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_date,
            hours_logged=4.0,
        ),
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: in_progress_task},
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

    # The in-progress task should be eligible to start (because w1 can work on it)
    assert is_task_eligible(in_progress_task, state) is True

    # Therefore, no deadlock should be detected
    assert detect_deadlock(state) is False

    # Get eligible tasks - should include the in-progress task
    eligible = get_eligible_tasks(state)
    assert len(eligible) == 1
    assert eligible[0].id == TaskId("t1")
