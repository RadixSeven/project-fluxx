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
    Task,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)
from fluxx.simulation.scheduler import (
    ResolveBranchAction,
    StartTaskAction,
    are_all_dependencies_satisfied,
    are_all_workers_idle,
    are_tasks_remaining,
    detect_deadlock,
    get_eligible_tasks,
    get_eligible_workers,
    get_unresolved_branches,
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

    # Get task1 and assign worker w1 to it
    task1 = state.get_task(TaskId("t1"))
    # Modify the task to have actual_assignee
    task1.actual_assignee = WorkerId("w1")

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

    # Assign w1 to task1
    task1 = state.get_task(TaskId("t1"))
    task1.actual_assignee = WorkerId("w1")

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
