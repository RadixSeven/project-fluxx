"""Simulation engine for running project simulations.

This module contains functions for orchestrating a single simulation sample,
including task execution, branch resolution, and time management. Functions are
designed to be small and focused for easy testing.
"""

import logging
import time
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
    sample_jira_duration,
    sample_jira_duration_filtered,
    sample_shifted_lognormal,
    sample_triangular,
    sample_with_rejection,
)
from fluxx.simulation.scheduler import (
    ResolveBranchAction,
    StartTaskAction,
    detect_deadlock,
    get_eligible_workers,
    get_incomplete_tasks,
    select_next_action,
)
from fluxx.simulation.state import SimulationState

logger = logging.getLogger(__name__)

# Task duration sampling


def sample_task_duration(
    task: Task, rng: np.random.Generator, state: SimulationState | None = None
) -> float:
    """Sample a duration from a task's distribution.

    Args:
        task: The task to sample duration for
        rng: Random number generator
        state: Simulation state (required for JiraDurationDistribution)

    Returns:
        Sampled duration in work-hours

    Raises:
        ValueError: If ``task`` has no distribution, or it is an unknown type
    """
    if task.duration_distribution is None:
        raise ValueError(f"Task {task.id} has no duration distribution")

    dist = task.duration_distribution

    # Import here to avoid circular dependency issues
    from fluxx.data.models import JiraDurationDistribution, ShiftedLognormal, Triangular

    if isinstance(dist, Triangular):
        return sample_triangular(dist, rng)
    elif isinstance(dist, ShiftedLognormal):
        return sample_shifted_lognormal(dist, rng)
    elif isinstance(dist, JiraDurationDistribution):
        if state is None:
            raise ValueError(
                "SimulationState required for sampling JiraDurationDistribution"
            )
        context = state.get_jira_sampling_context()
        return sample_jira_duration(dist, context, rng)
    else:
        raise ValueError(f"Unknown distribution type: {type(dist)}")


def sample_in_progress_task_remaining_duration(
    task: Task,
    elapsed_hours: float,
    rng: np.random.Generator,
    state: SimulationState | None = None,
) -> float:
    """Sample remaining duration for an in-progress task.

    For JiraDurationDistribution, uses filtered sampling (not rejection sampling).
    For other distributions, uses rejection sampling.

    Args:
        task: The in-progress task
        elapsed_hours: Work-hours already completed
        rng: Random number generator
        state: Simulation state (required for JiraDurationDistribution)

    Returns:
        Remaining duration in work-hours

    Raises:
        ValueError: If task has no distribution
    """
    if task.duration_distribution is None:
        raise ValueError(f"Task {task.id} has no duration distribution")

    dist = task.duration_distribution

    # Import here to avoid circular dependency issues
    from fluxx.data.models import JiraDurationDistribution

    if isinstance(dist, JiraDurationDistribution):
        # Use filtered sampling for Jira distributions
        if state is None:
            raise ValueError(
                "SimulationState required for sampling JiraDurationDistribution"
            )
        context = state.get_jira_sampling_context()
        total_duration = sample_jira_duration_filtered(
            dist, context, rng, elapsed_hours
        )
    else:
        # Use rejection sampling for other distributions
        total_duration = sample_with_rejection(dist, rng, elapsed_hours)

    # Return remaining duration
    return total_duration - elapsed_hours


def initialize_started_tasks(
    state: SimulationState, calendar: WorkCalendar, rng: np.random.Generator
) -> None:
    """Initialize all StartedCompletion tasks at simulation start.

    Workers with StartedCompletion tasks from Jira have their tasks scheduled
    with proper time-splitting. Each task completes at its own time based on
    its remaining work and the current time-split factor.

    For workers with multiple StartedCompletion tasks:
    - Sample remaining duration for each task
    - Calculate when each completes with time-splitting (remaining * num_tasks)
    - Schedule the task that completes first as current_task
    - Store remaining tasks with updated remaining work (accounting for work
      done while the first task was active)
    - When first task completes, the next is scheduled with updated timing

    Example with tasks A (14h) and B (28h), 7h/day worker:
    - With 2-task split: A completes after 14*2=28 calendar hours (4 days)
    - At that point, B has received 14h of work, so 14h remaining
    - B then runs solo: completes after 14/7 = 2 more days (day 6 total)

    Args:
        state: Simulation state to initialize
        calendar: Work calendar for time calculations
        rng: Random number generator for duration sampling
    """
    tasks_by_worker = state.get_started_completion_tasks_by_worker()

    for worker_id, tasks in tasks_by_worker.items():
        if not tasks:
            continue

        worker_state = state.worker_states[worker_id]
        num_tasks = len(tasks)

        # Sample remaining duration for each task and pair with task
        task_remaining: list[tuple[Task, float]] = []
        for task in tasks:
            completion = task.completion
            if not isinstance(completion, StartedCompletion):
                continue  # Type guard, should always be StartedCompletion
            remaining = sample_in_progress_task_remaining_duration(
                task, completion.hours_logged, rng, state
            )
            task_remaining.append((task, remaining))

        # Sort by remaining hours (task that completes first comes first)
        task_remaining.sort(key=lambda x: x[1])

        # The first task (smallest remaining) completes first
        first_task, first_remaining = task_remaining[0]

        # With time-splitting, calendar time to complete first task
        # = remaining_hours * num_tasks (since time is split equally)
        calendar_hours_first = first_remaining * num_tasks

        # Calculate completion time for first task
        first_completion = add_work_hours(
            state.current_time, calendar_hours_first, worker_state.hours_per_workday
        )

        # Schedule first task
        state.in_progress_tasks.add(first_task.id)
        worker_state.current_task = first_task.id
        worker_state.available_time = first_completion

        # Record start event for first task
        event = TaskEvent(
            node_id=first_task.id,
            event_type="start",
            timestamp=state.current_time,
            details={
                "worker_id": str(worker_id),
                "estimated_completion": first_completion.isoformat(),
                "started_from_jira": True,
                "time_split_factor": num_tasks,
            },
        )
        state.add_event(event)

        logger.debug(
            "Initialized StartedCompletion task %s for worker %s: "
            "remaining=%.2f hrs, time_split=%d, completion=%s",
            first_task.id,
            worker_id,
            first_remaining,
            num_tasks,
            first_completion.isoformat(),
        )

        # Store remaining tasks with updated remaining work
        # While first task runs, each other task receives first_remaining hours of work
        for task, remaining in task_remaining[1:]:
            updated_remaining = remaining - first_remaining
            state.add_pending_started_task(worker_id, task.id, updated_remaining)
            logger.debug(
                "Queued pending StartedCompletion task %s for worker %s: "
                "original=%.2f hrs, after_split=%.2f hrs",
                task.id,
                worker_id,
                remaining,
                updated_remaining,
            )


def schedule_pending_started_task(
    state: SimulationState, worker_id: WorkerId, calendar: WorkCalendar
) -> bool:
    """Schedule the next pending started task for a worker if available.

    Called after a task completes to check if the worker has more
    StartedCompletion tasks waiting to be scheduled.

    Args:
        state: Simulation state
        worker_id: ID of the worker who just became available
        calendar: Work calendar for time calculations

    Returns:
        True if a pending task was scheduled, False otherwise
    """
    pending = state.get_next_pending_started_task(worker_id)
    if pending is None:
        return False

    task_id, remaining_hours = pending
    worker_state = state.worker_states[worker_id]

    # Get remaining pending count (for time-splitting)
    pending_count = state.get_pending_started_task_count(worker_id)
    num_tasks = pending_count + 1  # This task plus remaining pending

    # Calculate calendar time with time-splitting
    calendar_hours = remaining_hours * num_tasks

    # Calculate completion time
    completion_time = add_work_hours(
        state.current_time, calendar_hours, worker_state.hours_per_workday
    )

    # Schedule this task
    state.in_progress_tasks.add(task_id)
    worker_state.current_task = task_id
    worker_state.available_time = completion_time

    # Record start event
    event = TaskEvent(
        node_id=task_id,
        event_type="start",
        timestamp=state.current_time,
        details={
            "worker_id": str(worker_id),
            "estimated_completion": completion_time.isoformat(),
            "started_from_jira": True,
            "time_split_factor": num_tasks,
        },
    )
    state.add_event(event)

    logger.debug(
        "Scheduled pending StartedCompletion task %s for worker %s: "
        "remaining=%.2f hrs, time_split=%d, completion=%s",
        task_id,
        worker_id,
        remaining_hours,
        num_tasks,
        completion_time.isoformat(),
    )

    # Update remaining pending tasks (they receive work while this task runs)
    if pending_count > 0:
        updated_pending: list[tuple[TaskId, float]] = []
        while True:
            next_pending = state.get_next_pending_started_task(worker_id)
            if next_pending is None:
                break
            next_task_id, next_remaining = next_pending
            # This task will receive remaining_hours of work while current runs
            updated_remaining = next_remaining - remaining_hours
            updated_pending.append((next_task_id, updated_remaining))

        # Re-add with updated remaining hours
        for next_task_id, next_remaining in updated_pending:
            state.add_pending_started_task(worker_id, next_task_id, next_remaining)

    return True


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

    Note: Time-splitting for multiple StartedCompletion tasks per worker is handled
    at simulation initialization (initialize_started_tasks). Tasks that reach this
    function with StartedCompletion status were not initialized (e.g., due to
    unsatisfied dependencies at start) and are handled individually.

    Args:
        task: The task to start
        state: Current simulation state
        calendar: Work calendar for time calculations
        rng: Random number generator

    Raises:
        ValueError: If no eligible workers or task has no distribution
    """
    # Check if task is already in progress (StartedCompletion from Jira)
    if isinstance(task.completion, StartedCompletion):
        # Use existing assignee
        worker_id = task.completion.assignee

        # Sample remaining duration using hours already logged
        # Note: No time-splitting applied here - that's handled at initialization
        # for tasks with satisfied dependencies. This task wasn't initialized
        # because its dependencies weren't satisfied at simulation start.
        duration_hours = sample_in_progress_task_remaining_duration(
            task, task.completion.hours_logged, rng, state
        )
    else:
        # Select worker randomly
        worker_id = select_worker_for_task(task, state, rng)

        # Sample full duration
        duration_hours = sample_task_duration(task, rng, state)

    # Get worker's hours per day
    worker_state = state.worker_states[worker_id]
    hours_per_day = worker_state.hours_per_workday

    # Calculate completion time
    start_time = max(state.current_time, worker_state.available_time)
    completion_time = add_work_hours(start_time, duration_hours, hours_per_day)

    # Update state
    state.start_task(task.id, worker_id, start_time, completion_time)

    logger.debug(
        "Task %s started: worker=%s, duration=%.2f hrs, start=%s, completion=%s",
        task.id,
        worker_id,
        duration_hours,
        start_time.isoformat(),
        completion_time.isoformat(),
    )

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

    logger.debug(
        "Task %s completed: worker=%s, time=%s",
        task.id,
        worker_id,
        completion_time.isoformat(),
    )

    # Record completion event
    event = TaskEvent(
        node_id=task.id,
        event_type="complete",
        timestamp=completion_time,
        details={"worker_id": str(worker_id) if worker_id else None},
    )
    state.add_event(event)


def process_task_completions(
    state: SimulationState, calendar: WorkCalendar | None = None
) -> None:
    """Process all tasks that complete at the current simulation time.

    Also schedules any pending StartedCompletion tasks for workers who
    just completed a task.

    Args:
        state: Current simulation state
        calendar: Work calendar (required to schedule pending started tasks)
    """
    # Find tasks that complete at current time, along with their workers
    tasks_to_complete: list[tuple[Task, datetime, WorkerId]] = []

    for worker_id, worker_state in state.worker_states.items():
        if worker_state.current_task is None:
            continue

        # Check if this worker's task completes at current time
        if worker_state.available_time <= state.current_time:
            task_id = worker_state.current_task
            try:
                task = state.get_task(task_id)
                tasks_to_complete.append((task, worker_state.available_time, worker_id))
            except KeyError:
                # Task not in current version, skip
                continue

    # Complete all tasks
    for task, completion_time, worker_id in tasks_to_complete:
        complete_task(task, state, completion_time)

        # Schedule next pending started task for this worker if any
        if calendar is not None:
            schedule_pending_started_task(state, worker_id, calendar)


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
        logger.debug(
            "Branch %s resolved to pre-chosen world %s",
            branch.id,
            chosen_world_id,
        )
    else:
        chosen_world_id = choose_possible_world(branch, rng)
        logger.debug(
            "Branch %s resolved to randomly chosen world %s",
            branch.id,
            chosen_world_id,
        )

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
    logger.debug("Sample %d starting", sample_id)

    # Initialize state
    state = SimulationState(project, start_date, workers)
    calendar = WorkCalendar(start_date)

    # Initialize any StartedCompletion tasks as in-progress from the start
    # This ensures workers with in-progress Jira tasks are properly "busy"
    initialize_started_tasks(state, calendar, rng)

    # Main simulation loop - guaranteed to terminate (see docstring proof)
    while True:
        # Process any tasks that complete at current time
        process_task_completions(state, calendar)

        # Check if all tasks completed
        if state.all_tasks_completed():
            logger.debug("Sample %d completed successfully", sample_id)
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
            failed_sample = create_failed_sample(sample_id, state)
            incomplete_count = len(get_incomplete_tasks(state))
            logger.debug(
                "Sample %d failed (deadlock): %d tasks incomplete",
                sample_id,
                incomplete_count,
            )
            return failed_sample

        # Advance time to next event
        try:
            advance_to_next_event(state)
        except ValueError:
            # Defensive: No next event and no actions - deadlock
            # This should always be caught by detect_deadlock above,
            # but we handle it defensively in case of logic errors.
            failed_sample = create_failed_sample(sample_id, state)
            incomplete_count = len(get_incomplete_tasks(state))
            logger.debug(
                "Sample %d failed (no next event): %d tasks incomplete",
                sample_id,
                incomplete_count,
            )
            return failed_sample


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
        logger.info(
            "Simulation starting: num_samples=%d, start_date=%s, workers=%d",
            self.num_samples,
            self.start_date.isoformat(),
            len(workers),
        )
        start_time = time.monotonic()

        samples: list[Sample] = []

        for i in range(self.num_samples):
            # Create RNG with unique seed for each sample
            rng = np.random.default_rng(seed=i)

            sample = run_single_sample(project, workers, self.start_date, i, rng)
            samples.append(sample)

        elapsed = time.monotonic() - start_time
        failed_count = sum(1 for s in samples if s.failed_tasks)
        failure_rate = failed_count / len(samples) if samples else 0.0

        logger.info(
            "Simulation complete: elapsed=%.2fs, samples=%d, failed=%d (%.1f%%)",
            elapsed,
            len(samples),
            failed_count,
            failure_rate * 100,
        )

        return samples
