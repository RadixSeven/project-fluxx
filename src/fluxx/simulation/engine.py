"""Simulation engine for running project simulations.

This module contains functions for orchestrating a single simulation sample,
including task execution, branch resolution, and time management. Functions are
designed to be small and focused for easy testing.
"""

from datetime import UTC, datetime

import numpy as np

from fluxx.data.models import (
    Branch,
    BranchId,
    PossibleWorldId,
    Project,
    Sample,
    SampleId,
    StartedCompletion,
    Task,
    TaskEvent,
    TaskId,
    Worker,
    WorkerId,
)
from fluxx.simulation.calendar import WorkCalendar, add_work_hours
from fluxx.simulation.distributions import (
    sample_shifted_lognormal,
    sample_triangular,
    sample_with_rejection,
)
from fluxx.simulation.scheduler import (
    ResolveBranchAction,
    StartTaskAction,
    detect_deadlock,
    get_eligible_workers,
    get_worker_in_progress_task_count,
    select_next_action,
)
from fluxx.simulation.state import SimulationState

# Task duration sampling


def sample_task_duration(task: Task, rng: np.random.Generator) -> float:
    """Sample a duration from a task's distribution.

    Args:
        task: The task to sample duration for
        rng: Random number generator

    Returns:
        Sampled duration in work-hours

    Raises:
        ValueError: If ``task`` has no distribution, or it is an unknown type
    """
    if task.duration_distribution is None:
        raise ValueError(f"Task {task.id} has no duration distribution")

    dist = task.duration_distribution

    # Import here to avoid circular dependency issues
    from fluxx.data.models import ShiftedLognormal, Triangular

    if isinstance(dist, Triangular):
        return sample_triangular(dist, rng)
    elif isinstance(dist, ShiftedLognormal):
        return sample_shifted_lognormal(dist, rng)
    else:
        raise ValueError(f"Unknown distribution type: {type(dist)}")


def sample_in_progress_task_remaining_duration(
    task: Task, elapsed_hours: float, rng: np.random.Generator
) -> float:
    """Sample remaining duration for an in-progress task using rejection sampling.

    Args:
        task: The in-progress task
        elapsed_hours: Work-hours already completed
        rng: Random number generator

    Returns:
        Remaining duration in work-hours

    Raises:
        ValueError: If task has no distribution
    """
    if task.duration_distribution is None:
        raise ValueError(f"Task {task.id} has no duration distribution")

    # Sample total duration >= elapsed using rejection sampling
    total_duration = sample_with_rejection(
        task.duration_distribution, rng, elapsed_hours
    )

    # Return remaining duration
    return total_duration - elapsed_hours


# Worker assignment


def select_worker_for_task(
    task: Task, state: SimulationState, rng: np.random.Generator
) -> WorkerId:
    """Select a worker to assign to a task.

    Args:
        task: The task to assign
        state: Current simulation state
        rng: Random number generator for tie-breaking

    Returns:
        Worker ID to assign

    Raises:
        ValueError: If no eligible workers available
    """
    eligible = get_eligible_workers(task, state)

    if not eligible:
        raise ValueError(f"No eligible workers for task {task.id}")

    # Randomly select one worker
    index = rng.integers(0, len(eligible))
    return eligible[index]


# Task lifecycle


def start_task(
    task: Task, state: SimulationState, calendar: WorkCalendar, rng: np.random.Generator
) -> None:
    """Start a task by assigning it to a worker and scheduling completion.

    For tasks already in progress (StartedCompletion), uses the existing assignee
    and samples remaining duration based on hours_logged. For new tasks, randomly
    selects a worker and samples full duration.

    When a worker has multiple in-progress tasks, time is split equally between
    them. The remaining duration is multiplied by the number of in-progress tasks
    the worker has assigned.

    Args:
        task: The task to start
        state: Current simulation state
        calendar: Work calendar for time calculations
        rng: Random number generator

    Raises:
        ValueError: If no eligible workers or task has no distribution
    """
    # Check if task is already in progress
    if isinstance(task.completion, StartedCompletion):
        # Use existing assignee
        worker_id = task.completion.assignee

        # Sample remaining duration using hours already logged
        duration_hours = sample_in_progress_task_remaining_duration(
            task, task.completion.hours_logged, rng
        )

        # Apply time-splitting if worker has multiple in-progress tasks
        # Count how many in-progress tasks this worker has from project data
        in_progress_count = get_worker_in_progress_task_count(worker_id, state)
        if in_progress_count > 1:
            # Worker splits time equally between tasks, so each takes longer
            duration_hours = duration_hours * in_progress_count
    else:
        # Select worker randomly
        worker_id = select_worker_for_task(task, state, rng)

        # Sample full duration
        duration_hours = sample_task_duration(task, rng)

    # Get worker's hours per day
    worker_state = state.worker_states[worker_id]
    hours_per_day = worker_state.hours_per_workday

    # Calculate completion time
    start_time = max(state.current_time, worker_state.available_time)
    completion_time = add_work_hours(start_time, duration_hours, hours_per_day)

    # Update state
    state.start_task(task.id, worker_id, start_time, completion_time)

    # Record start event
    event = TaskEvent(
        node_id=task.id,
        event_type="start",
        timestamp=start_time,
        details={
            "worker_id": str(worker_id),
            "estimated_duration": duration_hours,
            "estimated_completion": completion_time.isoformat(),
        },
    )
    state.add_event(event)


def complete_task(
    task: Task, state: SimulationState, completion_time: datetime
) -> None:
    """Complete a task and record the event.

    Args:
        task: The task to complete
        state: Current simulation state
        completion_time: When the task completed
    """
    # Find which worker was assigned
    worker_id = None
    for wid, ws in state.worker_states.items():
        if ws.current_task == task.id:
            worker_id = wid
            break

    # Update state
    state.complete_task(task.id, completion_time)

    # Record completion event
    event = TaskEvent(
        node_id=task.id,
        event_type="complete",
        timestamp=completion_time,
        details={"worker_id": str(worker_id) if worker_id else None},
    )
    state.add_event(event)


def process_task_completions(state: SimulationState) -> None:
    """Process all tasks that complete at the current simulation time.

    Args:
        state: Current simulation state
    """
    # Find tasks that complete at current time
    tasks_to_complete: list[tuple[Task, datetime]] = []

    for _worker_id, worker_state in state.worker_states.items():
        if worker_state.current_task is None:
            continue

        # Check if this worker's task completes at current time
        if worker_state.available_time <= state.current_time:
            task_id = worker_state.current_task
            try:
                task = state.get_task(task_id)
                tasks_to_complete.append((task, worker_state.available_time))
            except KeyError:
                # Task not in current version, skip
                continue

    # Complete all tasks
    for task, completion_time in tasks_to_complete:
        complete_task(task, state, completion_time)


# Branch resolution


def choose_possible_world(branch: Branch, rng: np.random.Generator) -> PossibleWorldId:
    """Randomly choose a possible world from a branch based on weights.

    Args:
        branch: The branch to choose from
        rng: Random number generator

    Returns:
        The chosen possible world ID

    Raises:
        ValueError: If branch has no possible worlds
    """
    if not branch.possible_worlds:
        raise ValueError(f"Branch {branch.id} has no possible worlds")

    # Extract weights
    weights = np.array([pw.weight for pw in branch.possible_worlds])

    # Normalize to probabilities
    probabilities = weights / weights.sum()

    # Randomly select based on probabilities
    index = rng.choice(len(branch.possible_worlds), p=probabilities)

    return branch.possible_worlds[index].id


def resolve_branch(
    branch: Branch, state: SimulationState, rng: np.random.Generator
) -> None:
    """Resolve a branch by choosing a possible world.

    If the branch already has a chosen_world_id set (pre-resolved), use that.
    Otherwise, randomly choose based on weights.

    Args:
        branch: The branch to resolve
        state: Current simulation state
        rng: Random number generator
    """
    # Use pre-chosen world if set, otherwise randomly choose
    if branch.chosen_world_id is not None:
        chosen_world_id = branch.chosen_world_id
    else:
        chosen_world_id = choose_possible_world(branch, rng)

    # Update state
    state.resolve_branch(branch.id, chosen_world_id)

    # Record event
    event = TaskEvent(
        node_id=branch.id,
        event_type="branch_resolved",
        timestamp=state.current_time,
        details={"chosen_world": str(chosen_world_id)},
    )
    state.add_event(event)


def get_branch(branch_id: BranchId, state: SimulationState) -> Branch:
    """Retrieve a branch from the project.

    Args:
        branch_id: ID of the branch to retrieve
        state: Current simulation state

    Returns:
        The branch object

    Raises:
        KeyError: If the branch is not found
    """
    # Look up the persistent object ID
    node_id = branch_id
    if node_id not in state.project.dag.node_map:
        raise KeyError(f"Branch {branch_id} not found in node_map")

    persistent_id = state.project.dag.node_map[node_id]

    # Get the persistent branch
    if persistent_id not in state.project.persistent_branches:
        raise KeyError(f"Branch {branch_id} not found in persistent_branches")

    persistent_branch = state.project.persistent_branches[persistent_id]

    # Get the branch from the current version
    current_version_id = state.project.dag.current_version_id
    if current_version_id not in persistent_branch.versions:
        raise KeyError(
            f"Branch {branch_id} not found in current version {current_version_id}"
        )

    return persistent_branch.versions[current_version_id]


# Time advancement


def advance_to_next_event(state: SimulationState) -> None:
    """Advance simulation time to the next scheduled event.

    Args:
        state: Current simulation state

    Raises:
        ValueError: If no next event exists (simulation stuck)
    """
    next_event_time = state.get_next_event_time()

    if next_event_time is None:
        raise ValueError("No next event time available (simulation stuck)")

    state.current_time = next_event_time


# Sample creation


def create_successful_sample(sample_id: int, state: SimulationState) -> Sample:
    """Create a Sample object for a successful simulation run.

    Args:
        sample_id: ID for this sample
        state: Final simulation state

    Returns:
        Sample object with all events
    """
    return Sample(
        sample_id=SampleId(sample_id),
        events=state.events,
        failed_tasks=[],  # Empty list indicates success
    )


def create_failed_sample(sample_id: int, state: SimulationState) -> Sample:
    """Create a Sample object for a failed simulation run.

    Args:
        sample_id: ID for this sample
        state: Final simulation state

    Returns:
        Sample object with events and failed task IDs
    """
    # Identify which tasks couldn't be completed
    failed_task_ids = []

    for node_id, persistent_id in state.project.dag.node_map.items():
        if persistent_id not in state.project.persistent_tasks:
            continue

        task_id = TaskId(str(node_id))
        if not state.is_task_completed(task_id):
            failed_task_ids.append(task_id)

    return Sample(
        sample_id=SampleId(sample_id),
        events=state.events,
        failed_tasks=failed_task_ids,  # Non-empty list indicates failure
    )


# Main simulation orchestration


def run_single_sample(
    project: Project,
    workers: list[Worker],
    start_date: datetime,
    sample_id: int,
    rng: np.random.Generator,
) -> Sample:
    """Run a single simulation sample.

    This is the main orchestration function that executes one Monte Carlo sample.
    It's self-contained with no shared state, making it safe for parallelization.
    The function is deterministic given the same RNG seed, but mutates the rng
    parameter and internal state during execution.

    The simulation loop is guaranteed to terminate through one of two paths:
    1. Success: All tasks complete (all_tasks_completed returns True)
    2. Failure: Deadlock detected (no progress possible)

    Progress is proven because each iteration does ONE of the following:
    - Completes tasks that finish at current time (process_task_completions)
    - Starts a new task (progress toward completion)
    - Resolves a branch (progress toward task eligibility)
    - Advances time to next task completion (progress toward completion)
    - Detects deadlock and exits (when no progress is possible)

    Since tasks have finite durations and the DAG is acyclic, the simulation
    must eventually either complete all tasks or reach a deadlock state.

    Args:
        project: The project to simulate
        workers: List of workers available for the simulation
        start_date: When the simulation starts
        sample_id: Unique ID for this sample
        rng: Random number generator (mutated during execution)

    Returns:
        Sample object containing all events and success status
    """
    # Initialize state
    state = SimulationState(project, start_date, workers)
    calendar = WorkCalendar(start_date)

    # Main simulation loop - guaranteed to terminate (see docstring proof)
    while True:
        # Process any tasks that complete at current time
        process_task_completions(state)

        # Check if all tasks completed
        if state.all_tasks_completed():
            return create_successful_sample(sample_id, state)

        # Select next action (start task or resolve branch)
        action = select_next_action(state, rng)

        if action is not None:
            if isinstance(action, StartTaskAction):
                task = state.get_task(action.task_id)
                start_task(task, state, calendar, rng)
            elif isinstance(action, ResolveBranchAction):
                branch = get_branch(action.branch_id, state)
                resolve_branch(branch, state, rng)
            continue

        # No actions possible - check for deadlock
        if detect_deadlock(state):
            return create_failed_sample(sample_id, state)

        # Advance time to next event
        try:
            advance_to_next_event(state)
        except ValueError:
            # Defensive: No next event and no actions - deadlock
            # This should always be caught by detect_deadlock above,
            # but we handle it defensively in case of logic errors.
            return create_failed_sample(sample_id, state)


# SimulationEngine class (for convenience)


class SimulationEngine:
    """Engine for running Monte Carlo simulations of project timelines."""

    def __init__(
        self,
        num_samples: int = 1000,
        start_date: datetime | None = None,
        num_parallel_processes: int | None = None,
    ) -> None:
        """Initialize the simulation engine.

        Args:
            num_samples: Number of simulation runs to execute
            start_date: Project start date (defaults to now)
            num_parallel_processes: Number of parallel processes
                (defaults to 2 * CPU count, not implemented yet)
        """
        self.num_samples = num_samples
        self.start_date = start_date or datetime.now(UTC)
        self.num_parallel_processes = num_parallel_processes

    def run(self, project: Project, workers: list[Worker]) -> list[Sample]:
        """Run the simulation sequentially.

        Args:
            project: The project to simulate
            workers: List of workers available

        Returns:
            List of Sample objects, one per simulation run
        """
        samples: list[Sample] = []

        for i in range(self.num_samples):
            # Create RNG with unique seed for each sample
            rng = np.random.default_rng(seed=i)

            sample = run_single_sample(project, workers, self.start_date, i, rng)
            samples.append(sample)

        return samples
