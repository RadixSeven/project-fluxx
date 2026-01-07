"""Simulation state management for tracking a single simulation sample."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fluxx.data.models import (
    BranchId,
    PossibleWorldId,
    Project,
    Task,
    TaskEvent,
    TaskId,
    Worker,
    WorkerId,
    type_explode_id,
)

if TYPE_CHECKING:
    from fluxx.simulation.distributions import JiraSamplingContext


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

        # Initialize worker states
        self.worker_states: dict[WorkerId, WorkerState] = {
            worker.id: WorkerState(
                worker_id=worker.id,
                hours_per_workday=worker.hours_per_workday,
                available_time=start_date,
            )
            for worker in workers
        }

        # Lazy-initialized Jira sampling context
        self._jira_sampling_context: JiraSamplingContext | None = None

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

        Args:
            task_id: ID of the task to check

        Returns:
            True if the task has started, False otherwise
        """
        return self.is_task_in_progress(task_id) or self.is_task_completed(task_id)

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

        return reachable_leaf_task_ids == self.completed_tasks

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
