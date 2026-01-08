"""Simulation state management for tracking a single simulation sample."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fluxx.data.models import (
    BranchId,
    DoneCompletion,
    PossibleWorldId,
    Project,
    StartedCompletion,
    Task,
    TaskEvent,
    TaskId,
    Worker,
    WorkerId,
    type_explode_id,
)

if TYPE_CHECKING:
    from fluxx.simulation.distributions import JiraSamplingContext

logger = logging.getLogger(__name__)


@dataclass
class WorkerState:
    """State of a worker during simulation."""

    worker_id: WorkerId
    hours_per_workday: float
    current_task: TaskId | None = None
    available_time: datetime = field(default_factory=lambda: datetime.now(UTC))


class SimulationState:
    """Tracks the state of a single simulation sample.

    This class maintains all state information needed during a simulation run,
    including task completion status, branch resolutions, worker assignments,
    and event history.
    """

    def __init__(
        self,
        project: Project,
        start_date: datetime,
        workers: list[Worker],
    ) -> None:
        """Initialize simulation state.

        Args:
            project: The project being simulated
            start_date: When the simulation starts
            workers: List of workers available for the simulation
        """
        self.project = project
        self.current_time = start_date
        self.completed_tasks: set[TaskId] = set()
        self.in_progress_tasks: set[TaskId] = set()
        self.resolved_branches: dict[BranchId, PossibleWorldId] = {}
        self.events: list[TaskEvent] = []
        self.failed_tasks: list[TaskId] = []

        # Pre-populate completed_tasks from existing DoneCompletion states
        # This ensures dependencies on done tasks are satisfied.
        # NOTE: We do NOT pre-populate in_progress_tasks because those tasks
        # still need to be scheduled and worked on in the simulation.
        self._initialize_completed_tasks_from_completions()

        # Initialize worker states
        self.worker_states: dict[WorkerId, WorkerState] = {
            worker.id: WorkerState(
                worker_id=worker.id,
                hours_per_workday=worker.hours_per_workday,
                available_time=start_date,
            )
            for worker in workers
        }

        # Track pending StartedCompletion tasks waiting to be scheduled
        # Maps worker_id to list of (task_id, remaining_hours) tuples
        # These are tasks that have been initialized but not yet scheduled
        self._pending_started_tasks: dict[WorkerId, list[tuple[TaskId, float]]] = {}

        # Lazy-initialized Jira sampling context
        self._jira_sampling_context: JiraSamplingContext | None = None

    def _initialize_completed_tasks_from_completions(self) -> None:
        """Initialize completed_tasks from existing DoneCompletion states.

        Tasks imported from Jira may already be done (DoneCompletion). This
        method ensures those tasks are recognized as completed for dependency
        checking purposes.

        NOTE: We do NOT pre-populate in_progress_tasks for StartedCompletion
        tasks here. Those tasks still need to be scheduled and worked on in
        the simulation. The has_task_started() method checks the task's
        completion status directly to handle dependencies on started tasks.
        """
        current_version_id = self.project.dag.current_version_id

        for persistent_id in self.project.dag.node_map.values():
            if persistent_id not in self.project.persistent_tasks:
                continue

            persistent_task = self.project.persistent_tasks[persistent_id]
            if current_version_id not in persistent_task.versions:
                continue

            task = persistent_task.versions[current_version_id]
            if isinstance(task.completion, DoneCompletion):
                self.completed_tasks.add(task.id)
                logger.debug(
                    "Pre-initialized task %s (%s) as completed from DoneCompletion",
                    task.id,
                    task.title,
                )

    def get_jira_sampling_context(self) -> JiraSamplingContext:
        """Get or build the Jira sampling context.

        Lazily builds the context on first access from project's Jira history.

        Returns:
            JiraSamplingContext for sampling JiraDurationDistribution
        """
        if self._jira_sampling_context is None:
            from fluxx.simulation.distributions import build_jira_sampling_context

            self._jira_sampling_context = build_jira_sampling_context(self.project)
        return self._jira_sampling_context

    def get_started_completion_tasks_by_worker(
        self,
    ) -> dict[WorkerId, list[Task]]:
        """Get all StartedCompletion tasks grouped by their assignee.

        Only includes tasks that:
        - Have StartedCompletion status
        - Are leaf tasks (no children)
        - Have an assignee in the simulation's worker_states

        Returns:
            Dict mapping worker IDs to their StartedCompletion tasks
        """
        from fluxx.simulation.scheduler import are_all_dependencies_satisfied

        tasks_by_worker: dict[WorkerId, list[Task]] = {}
        current_version_id = self.project.dag.current_version_id

        for persistent_id in self.project.dag.node_map.values():
            if persistent_id not in self.project.persistent_tasks:
                continue

            persistent_task = self.project.persistent_tasks[persistent_id]
            if current_version_id not in persistent_task.versions:
                continue

            task = persistent_task.versions[current_version_id]

            # Must be a leaf task with StartedCompletion
            if len(task.children) > 0:
                continue
            if not isinstance(task.completion, StartedCompletion):
                continue

            assignee = task.completion.assignee

            # Assignee must be in the simulation
            if assignee not in self.worker_states:
                logger.debug(
                    "Skipping StartedCompletion task %s: assignee %s not in simulation",
                    task.id,
                    assignee,
                )
                continue

            # Dependencies must be satisfied for the task to be workable
            if not are_all_dependencies_satisfied(task, self):
                logger.debug(
                    "Skipping StartedCompletion task %s: dependencies not satisfied",
                    task.id,
                )
                continue

            if assignee not in tasks_by_worker:
                tasks_by_worker[assignee] = []
            tasks_by_worker[assignee].append(task)

        return tasks_by_worker

    def complete_task(self, task_id: TaskId, completion_time: datetime) -> None:
        """Mark a task as completed.

        Args:
            task_id: ID of the task to complete
            completion_time: When the task was completed
        """
        if task_id in self.in_progress_tasks:
            self.in_progress_tasks.remove(task_id)
        self.completed_tasks.add(task_id)

        # Free up the worker
        for worker_state in self.worker_states.values():
            if worker_state.current_task == task_id:
                logger.debug(
                    "Worker %s now idle after completing task %s",
                    worker_state.worker_id,
                    task_id,
                )
                worker_state.current_task = None
                worker_state.available_time = completion_time
                break

    def start_task(
        self,
        task_id: TaskId,
        worker_id: WorkerId,
        start_time: datetime,
        estimated_completion: datetime,
    ) -> None:
        """Mark a task as started by a worker.

        Args:
            task_id: ID of the task to start
            worker_id: ID of the worker assigned to the task
            start_time: When the task starts
            estimated_completion: When the task is expected to complete
        """
        self.in_progress_tasks.add(task_id)
        worker_state = self.worker_states[worker_id]
        worker_state.current_task = task_id
        worker_state.available_time = estimated_completion

        logger.debug(
            "Worker %s now busy with task %s until %s",
            worker_id,
            task_id,
            estimated_completion.isoformat(),
        )

    def add_pending_started_task(
        self, worker_id: WorkerId, task_id: TaskId, remaining_hours: float
    ) -> None:
        """Add a task to the pending started tasks queue for a worker.

        These are StartedCompletion tasks that have been initialized (duration
        sampled) but not yet scheduled as the worker's current_task.

        Args:
            worker_id: ID of the worker
            task_id: ID of the task
            remaining_hours: Remaining work hours for this task
        """
        if worker_id not in self._pending_started_tasks:
            self._pending_started_tasks[worker_id] = []
        self._pending_started_tasks[worker_id].append((task_id, remaining_hours))

    def get_next_pending_started_task(
        self, worker_id: WorkerId
    ) -> tuple[TaskId, float] | None:
        """Get and remove the next pending started task for a worker.

        Args:
            worker_id: ID of the worker

        Returns:
            Tuple of (task_id, remaining_hours) or None if no pending tasks
        """
        if worker_id not in self._pending_started_tasks:
            return None
        pending = self._pending_started_tasks[worker_id]
        if not pending:
            return None
        return pending.pop(0)

    def has_pending_started_tasks(self, worker_id: WorkerId) -> bool:
        """Check if a worker has pending started tasks.

        Args:
            worker_id: ID of the worker

        Returns:
            True if worker has pending started tasks
        """
        if worker_id not in self._pending_started_tasks:
            return False
        return len(self._pending_started_tasks[worker_id]) > 0

    def get_pending_started_task_count(self, worker_id: WorkerId) -> int:
        """Get the count of pending started tasks for a worker.

        Args:
            worker_id: ID of the worker

        Returns:
            Number of pending started tasks
        """
        if worker_id not in self._pending_started_tasks:
            return 0
        return len(self._pending_started_tasks[worker_id])

    def resolve_branch(
        self, branch_id: BranchId, chosen_world: PossibleWorldId
    ) -> None:
        """Record a branch resolution.

        Args:
            branch_id: ID of the branch being resolved
            chosen_world: ID of the possible world that was chosen
        """
        self.resolved_branches[branch_id] = chosen_world

    def add_event(self, event: TaskEvent) -> None:
        """Add an event to the simulation history.

        Args:
            event: The event to record
        """
        self.events.append(event)

    def get_task(self, task_id: TaskId) -> Task:
        """Retrieve a task from the project.

        Args:
            task_id: ID of the task to retrieve

        Returns:
            The task object

        Raises:
            KeyError: If the task is not found
        """
        # Look up the persistent object ID
        node_id = task_id
        if node_id not in self.project.dag.node_map:
            raise KeyError(f"Task {task_id} not found in node_map")

        persistent_id = self.project.dag.node_map[node_id]

        # Get the persistent task
        if persistent_id not in self.project.persistent_tasks:
            raise KeyError(f"Task {task_id} not found in persistent_tasks")

        persistent_task = self.project.persistent_tasks[persistent_id]

        # Get the task from the current version
        current_version_id = self.project.dag.current_version_id
        if current_version_id not in persistent_task.versions:
            raise KeyError(
                f"Task {task_id} not found in current version {current_version_id}"
            )

        return persistent_task.versions[current_version_id]

    def is_task_completed(self, task_id: TaskId) -> bool:
        """Check if a task has been completed.

        Args:
            task_id: ID of the task to check

        Returns:
            True if the task is completed, False otherwise
        """
        return task_id in self.completed_tasks

    def is_task_in_progress(self, task_id: TaskId) -> bool:
        """Check if a task is currently in progress.

        Args:
            task_id: ID of the task to check

        Returns:
            True if the task is in progress, False otherwise
        """
        return task_id in self.in_progress_tasks

    def has_task_started(self, task_id: TaskId) -> bool:
        """Check if a task has started (either in progress or completed).

        This includes tasks that:
        1. Are currently in progress in the simulation
        2. Have been completed in the simulation
        3. Have StartedCompletion from Jira (already started before simulation)

        Args:
            task_id: ID of the task to check

        Returns:
            True if the task has started, False otherwise
        """
        if self.is_task_in_progress(task_id) or self.is_task_completed(task_id):
            return True

        # Also check if the task has StartedCompletion from Jira
        # This handles the case where a task is already started in real life
        # but hasn't been scheduled yet in the simulation
        try:
            task = self.get_task(task_id)
            return isinstance(task.completion, StartedCompletion)
        except KeyError:
            return False

    def get_available_workers(self) -> list[WorkerId]:
        """Get list of workers that are currently available (idle).

        Returns:
            List of worker IDs for workers with no current task
        """
        return [
            worker_id
            for worker_id, worker_state in self.worker_states.items()
            if worker_state.current_task is None
        ]

    def is_task_reachable(self, task_id: TaskId) -> bool:
        """Check if a task is reachable given current branch resolutions.

        A task is reachable if AT LEAST ONE of its possible world dependencies
        points to a world that was actually chosen (OR semantics).

        Args:
            task_id: ID of the task to check

        Returns:
            True if the task is reachable, False otherwise
        """

        try:
            task = self.get_task(task_id)
        except KeyError:
            # Task doesn't exist
            return False

        # Separate possible world dependencies from other dependencies
        possible_world_deps = []
        for dep in task.dependencies:
            _, _, as_world = type_explode_id(dep.target_node_id)
            if as_world is not None:
                possible_world_deps.append(as_world)

        # If no possible world dependencies, task is reachable
        if not possible_world_deps:
            return True

        # With OR semantics: at least ONE possible world dependency must be
        # satisfied. A dependency is satisfied if:
        # - The branch hasn't been resolved yet (still potentially satisfiable), OR
        # - The branch was resolved to this specific world
        for as_world in possible_world_deps:
            # Check if branch was resolved
            if as_world.branch_id not in self.resolved_branches:
                # Branch not yet resolved - task is still potentially reachable
                return True

            # Check if the branch was resolved to this world
            if self.resolved_branches[as_world.branch_id] == as_world.world_id:
                # This possible world was chosen - task is reachable
                return True

        # All possible world dependencies were resolved to different worlds
        return False

    def all_tasks_completed(self) -> bool:
        """Check if all reachable leaf tasks have been completed.

        Only counts leaf tasks (tasks without children) that are reachable given
        the current branch resolutions. Parent tasks are not counted because they
        are never executed directly - their completion is implicit when all their
        children complete. Tasks that depend on unchosen possible worlds are not
        counted.

        Returns:
            True if all reachable leaf tasks are completed, False otherwise
        """
        # Get all reachable leaf task node IDs from the node map
        reachable_leaf_task_ids: set[TaskId] = set()
        for node_id, persistent_id in self.project.dag.node_map.items():
            # Check if this is a task (not a branch)
            if persistent_id in self.project.persistent_tasks:
                # Check if task exists in current version
                persistent_task = self.project.persistent_tasks[persistent_id]
                if self.project.dag.current_version_id in persistent_task.versions:
                    task = persistent_task.versions[self.project.dag.current_version_id]
                    task_id = TaskId(str(node_id))
                    # Only count leaf tasks (not parent tasks) that are reachable
                    if len(task.children) == 0 and self.is_task_reachable(task_id):
                        reachable_leaf_task_ids.add(task_id)

        # All reachable leaf tasks must be in completed_tasks
        # (completed_tasks may contain additional tasks that became unreachable)
        return reachable_leaf_task_ids.issubset(self.completed_tasks)

    def get_next_event_time(self) -> datetime | None:
        """Get the time of the next scheduled event (task completion).

        Returns:
            The earliest time when a worker becomes available,
            or None if no tasks are in progress
        """
        in_progress_workers = [
            ws for ws in self.worker_states.values() if ws.current_task is not None
        ]

        if not in_progress_workers:
            return None

        return min(ws.available_time for ws in in_progress_workers)
