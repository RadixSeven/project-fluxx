"""Task scheduling logic for simulation engine.

This module contains functions for determining which tasks are eligible to start,
which workers can be assigned, and detecting deadlock conditions. Functions are
designed to be small and focused for easy testing.
"""

from dataclasses import dataclass

import numpy as np

from fluxx.data.models import (
    BranchId,
    Dependency,
    Endpoint,
    NodeId,
    Task,
    TaskId,
    WorkerId,
    type_explode_id,
)
from fluxx.simulation.state import SimulationState


@dataclass
class StartTaskAction:
    """Action to start a task."""

    task_id: TaskId


@dataclass
class ResolveBranchAction:
    """Action to resolve a branch."""

    branch_id: BranchId


# Union type for actions
Action = StartTaskAction | ResolveBranchAction


# Dependency checking functions


def is_dependency_on_task_start(dep: Dependency) -> bool:
    """Check if dependency targets a task's START endpoint."""
    return dep.target_endpoint == Endpoint.START


def is_dependency_on_task_end(dep: Dependency) -> bool:
    """Check if dependency targets a task's END endpoint."""
    return dep.target_endpoint == Endpoint.END


def is_dependency_on_branch(dep: Dependency) -> bool:
    """Check if dependency targets a branch's OCCURRENCE_POINT endpoint."""
    return dep.target_endpoint == Endpoint.OCCURRENCE


def is_task_node(node_id: NodeId, state: SimulationState) -> bool:
    """Check if a node ID refers to a task (not a branch)."""
    if node_id not in state.project.dag.node_map:
        return False
    persistent_id = state.project.dag.node_map[node_id]
    return persistent_id in state.project.persistent_tasks


def is_branch_node(node_id: NodeId, state: SimulationState) -> bool:
    """Check if a node ID refers to a branch (not a task)."""
    if node_id not in state.project.dag.node_map:
        return False
    persistent_id = state.project.dag.node_map[node_id]
    return persistent_id in state.project.persistent_branches


def is_dependency_satisfied(
    dep: Dependency, state: SimulationState, source_task: Task | None = None
) -> bool:
    """Check if a single dependency is satisfied.

    Args:
        dep: The dependency to check
        state: Current simulation state
        source_task: The task that has this dependency (needed for parent task logic)

    Returns:
        True if the dependency is satisfied, False otherwise
    """
    target_node_id = dep.target_node_id
    as_task, as_branch, as_world = type_explode_id(target_node_id)

    # Check if this is a possible world reference (format: "branch_id:world_id")
    if as_world is not None:
        branch_id, world_id = as_world

        # Check that the branch exists
        if not is_branch_node(branch_id, state):
            return False

        # Branch must be resolved to this specific world
        if branch_id not in state.resolved_branches:
            return False
        return state.resolved_branches[branch_id] == world_id

    # Check if target is a task
    if as_task is not None and is_task_node(as_task, state):
        # Get the task to check if it's a parent task
        try:
            target_task = state.get_task(as_task)
        except KeyError:
            return False

        # Handle parent task dependencies specially
        is_parent_task = len(target_task.children) > 0

        if is_dependency_on_task_end(dep):
            if is_parent_task:
                # Parent task END: satisfied when all children complete
                return all(
                    state.is_task_completed(child_id)
                    for child_id in target_task.children
                )
            else:
                # Regular task must be completed
                return state.is_task_completed(as_task)
        elif is_dependency_on_task_start(dep):
            if is_parent_task:
                # Parent task START depends on whether source is a child or not
                # If source is a child: always satisfied (children can start freely)
                # If source is not a child: satisfied when any child has started
                if source_task and source_task.parent_id == as_task:
                    # Source is a child of this parent - always satisfied
                    # This allows children to start, which causes parent to "start"
                    return True
                else:
                    # Source is not a child - parent starts when first child starts
                    return any(
                        state.has_task_started(child_id)
                        for child_id in target_task.children
                    )
            else:
                # Regular task must have started (in progress or completed)
                return state.has_task_started(as_task)
        else:
            # Unknown endpoint for task
            return False

    # Check if target is a branch (just the branch itself, not a specific world)
    elif as_branch is not None and is_branch_node(as_branch, state):
        # This is a branch ID - just check if resolved
        return as_branch in state.resolved_branches

    # Unknown node type
    return False


def are_all_dependencies_satisfied(task: Task, state: SimulationState) -> bool:
    """Check if all dependencies of a task are satisfied.

    Args:
        task: The task to check
        state: Current simulation state

    Returns:
        True if all dependencies are satisfied, False otherwise
    """
    return all(
        is_dependency_satisfied(dep, state, source_task=task)
        for dep in task.dependencies
    )


# Worker eligibility functions


def is_worker_allowed_for_task(task: Task, worker_id: WorkerId) -> bool:
    """Check if a worker is allowed to work on a task (whitelist check).

    Args:
        task: The task to check
        worker_id: The worker ID to check

    Returns:
        True if worker is allowed (or no whitelist exists), False otherwise
    """
    # If no whitelist (None), all workers are allowed
    # Note: Empty lists are normalized to None by the Task model validator
    if task.allowed_workers is None:
        return True

    # Otherwise, worker must be in whitelist
    return worker_id in task.allowed_workers


def is_worker_excluded_for_task(
    task: Task, worker_id: WorkerId, state: SimulationState
) -> bool:
    """Check if a worker is excluded from a task (due to other task assignments).

    Args:
        task: The task to check
        worker_id: The worker ID to check
        state: Current simulation state

    Returns:
        True if worker is excluded, False if worker can be assigned
    """
    # Check each excluded task
    for excluded_task_id in task.excluded_worker_tasks:
        # Get the task's actual assignee (if it has been assigned)
        try:
            excluded_task = state.get_task(excluded_task_id)
            if excluded_task.actual_assignee == worker_id:
                # This worker was assigned to an excluded task
                return True
        except KeyError:
            # Task doesn't exist in current version, skip
            continue

    return False


def get_eligible_workers(task: Task, state: SimulationState) -> list[WorkerId]:
    """Get list of workers eligible to work on a task.

    A worker is eligible if:
    1. They are not currently assigned to a task (available)
    2. They pass the allowed_workers whitelist (if it exists)
    3. They are not excluded due to excluded_worker_tasks constraints

    Args:
        task: The task to find workers for
        state: Current simulation state

    Returns:
        List of eligible worker IDs
    """
    eligible: list[WorkerId] = []

    available_workers = state.get_available_workers()

    for worker_id in available_workers:
        # Check whitelist
        if not is_worker_allowed_for_task(task, worker_id):
            continue

        # Check exclusions
        if is_worker_excluded_for_task(task, worker_id, state):
            continue

        eligible.append(worker_id)

    return eligible


# Task eligibility


def is_task_eligible(task: Task, state: SimulationState) -> bool:
    """Check if a task is eligible to start.

    A task is eligible if:
    1. It is not a parent task (parent tasks are never executed directly)
    2. It has not already been completed
    3. It is not currently in progress
    4. All its dependencies are satisfied
    5. At least one eligible worker is available

    Args:
        task: The task to check
        state: Current simulation state

    Returns:
        True if task can start, False otherwise
    """
    task_id = task.id

    # Parent tasks (tasks with children) are never executed directly
    # Their start/end times are determined by their children
    if len(task.children) > 0:
        return False

    # Must not be completed
    if state.is_task_completed(task_id):
        return False

    # Must not be in progress
    if state.is_task_in_progress(task_id):
        return False

    # All dependencies must be satisfied
    if not are_all_dependencies_satisfied(task, state):
        return False

    # Must have at least one eligible worker
    eligible_workers = get_eligible_workers(task, state)
    return bool(eligible_workers)


def get_eligible_tasks(state: SimulationState) -> list[Task]:
    """Get all tasks that are eligible to start.

    Args:
        state: Current simulation state

    Returns:
        List of eligible tasks
    """
    eligible: list[Task] = []

    # Iterate through all tasks in current version
    for _node_id, persistent_id in state.project.dag.node_map.items():
        # Skip if not a task
        if persistent_id not in state.project.persistent_tasks:
            continue

        # Get task from current version
        persistent_task = state.project.persistent_tasks[persistent_id]
        current_version_id = state.project.dag.current_version_id

        if current_version_id not in persistent_task.versions:
            continue

        task = persistent_task.versions[current_version_id]

        # Check if eligible
        if is_task_eligible(task, state):
            eligible.append(task)

    return eligible


# Branch resolution


def get_unresolved_branches(state: SimulationState) -> list[BranchId]:
    """Get all branches that have not yet been resolved.

    Args:
        state: Current simulation state

    Returns:
        List of unresolved branch IDs
    """
    unresolved: list[BranchId] = []

    # Iterate through all branches in current version
    for node_id, persistent_id in state.project.dag.node_map.items():
        # Skip if not a branch
        if persistent_id not in state.project.persistent_branches:
            continue

        # Get branch ID
        branch_id = BranchId(str(node_id))

        # Check if already resolved
        if branch_id not in state.resolved_branches:
            unresolved.append(branch_id)

    return unresolved


def is_branch_eligible(branch_id: BranchId, state: SimulationState) -> bool:
    """Check if a branch is eligible to be resolved.

    A branch is eligible if all of its dependencies are satisfied.

    Args:
        branch_id: The branch ID to check
        state: Current simulation state

    Returns:
        True if branch can be resolved, False otherwise
    """
    # Get the branch
    from fluxx.simulation.engine import get_branch

    try:
        branch = get_branch(branch_id, state)
    except KeyError:
        return False

    # Check all dependencies
    return all(is_dependency_satisfied(dep, state) for dep in branch.dependencies)


def get_eligible_branches(state: SimulationState) -> list[BranchId]:
    """Get all branches that are eligible to be resolved.

    A branch is eligible if it hasn't been resolved and all its dependencies
    are satisfied.

    Args:
        state: Current simulation state

    Returns:
        List of eligible branch IDs
    """
    eligible: list[BranchId] = []

    unresolved = get_unresolved_branches(state)
    for branch_id in unresolved:
        if is_branch_eligible(branch_id, state):
            eligible.append(branch_id)

    return eligible


# Action selection


def select_next_action(
    state: SimulationState, rng: np.random.Generator
) -> Action | None:
    """Select the next action to take in the simulation.

    Randomly chooses between eligible tasks and eligible branches.
    Returns None if no actions are possible.

    Args:
        state: Current simulation state
        rng: Random number generator for tie-breaking

    Returns:
        Action to take, or None if no actions possible
    """
    eligible_tasks = get_eligible_tasks(state)
    eligible_branches = get_eligible_branches(state)

    # Combine all possible actions
    actions: list[Action] = []

    for task in eligible_tasks:
        actions.append(StartTaskAction(task_id=task.id))

    for branch_id in eligible_branches:
        actions.append(ResolveBranchAction(branch_id=branch_id))

    # If no actions possible, return None
    if not actions:
        return None

    # Randomly select one action
    index = rng.integers(0, len(actions))
    return actions[index]


# Deadlock detection


def are_all_workers_idle(state: SimulationState) -> bool:
    """Check if all workers are currently idle (no tasks in progress).

    Args:
        state: Current simulation state

    Returns:
        True if all workers are idle, False otherwise
    """
    return all(ws.current_task is None for ws in state.worker_states.values())


def are_tasks_remaining(state: SimulationState) -> bool:
    """Check if there are uncompleted tasks.

    Args:
        state: Current simulation state

    Returns:
        True if uncompleted tasks exist, False otherwise
    """
    return not state.all_tasks_completed()


def detect_deadlock(state: SimulationState) -> bool:
    """Detect if simulation is in a deadlock state.

    Deadlock occurs when:
    1. All workers are idle (no tasks in progress)
    2. There are still uncompleted reachable tasks
    3. No tasks are eligible to start
    4. No branches are eligible for resolution

    Args:
        state: Current simulation state

    Returns:
        True if deadlocked, False otherwise
    """
    # All workers must be idle
    if not are_all_workers_idle(state):
        return False

    # There must be uncompleted reachable tasks
    if not are_tasks_remaining(state):
        return False

    # No actions should be possible
    eligible_tasks = get_eligible_tasks(state)
    eligible_branches = get_eligible_branches(state)

    return len(eligible_tasks) == 0 and len(eligible_branches) == 0
