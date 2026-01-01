"""Undo/redo operations using event history."""

from fluxx.data.models import DAGVersionId, NodeId, PersistentObjectId, Project


class UndoError(Exception):
    """Raised when an undo/redo operation fails."""

    pass


def undo(project: Project) -> Project:
    """Undo the last operation by reverting to the parent event's DAG version.

    Args:
        project: The project to undo

    Returns:
        Project with DAG reverted to previous version

    Raises:
        UndoError: If there's nothing to undo
    """
    if project.current_event_id is None:
        raise UndoError("Nothing to undo - no events in history")

    # Find the current event
    current_event = None
    for event in project.history_events:
        if event.id == project.current_event_id:
            current_event = event
            break

    if current_event is None:
        raise UndoError(
            f"Current event {project.current_event_id} not found in history"
        )

    # If at initial event (no parent), revert to initial DAG state
    if current_event.parent_event_id is None:
        # Find the initial version from the first event in history
        # or get it from persistent objects
        initial_version = None

        # Try to find a version that exists before any events
        # Look for the earliest version ID in any persistent object
        all_versions: set[DAGVersionId] = set()
        for ptask in project.persistent_tasks.values():
            all_versions.update(ptask.versions.keys())
        for pbranch in project.persistent_branches.values():
            all_versions.update(pbranch.versions.keys())

        # Find versions that exist but aren't in any event's resulting_dag_version
        event_versions = {e.resulting_dag_version for e in project.history_events}
        pre_event_versions = all_versions - event_versions

        if pre_event_versions:
            # Use one of the pre-event versions
            # (they should all be the same initial state)
            initial_version = sorted(pre_event_versions)[0]
        else:
            # No pre-event versions found, create a minimal initial version ID
            # This shouldn't happen in normal operation
            initial_version = DAGVersionId(str(project.dag.id) + "_initial")

        return project.model_copy(
            update={
                "dag": project.dag.model_copy(
                    update={"current_version_id": initial_version, "node_map": {}}
                ),
                "current_event_id": None,
            }
        )

    # Find the parent event
    parent_event = None
    for event in project.history_events:
        if event.id == current_event.parent_event_id:
            parent_event = event
            break

    if parent_event is None:
        raise UndoError(
            f"Parent event {current_event.parent_event_id} not found in history"
        )

    # Reconstruct node_map for parent version
    parent_version = parent_event.resulting_dag_version
    new_node_map: dict[NodeId, PersistentObjectId] = {}

    # Add tasks that exist in parent version
    for persistent_id, persistent_task in project.persistent_tasks.items():
        if parent_version in persistent_task.versions:
            task = persistent_task.versions[parent_version]
            new_node_map[task.id] = persistent_id

    # Add branches that exist in parent version
    for persistent_id, persistent_branch in project.persistent_branches.items():
        if parent_version in persistent_branch.versions:
            branch = persistent_branch.versions[parent_version]
            new_node_map[branch.id] = persistent_id

    # Revert to parent event's DAG version
    return project.model_copy(
        update={
            "dag": project.dag.model_copy(
                update={
                    "current_version_id": parent_version,
                    "node_map": new_node_map,
                }
            ),
            "current_event_id": parent_event.id,
        }
    )


def redo(project: Project) -> Project:
    """Redo the next operation by moving forward to a child event.

    Args:
        project: The project to redo

    Returns:
        Project with DAG moved to next version

    Raises:
        UndoError: If there's nothing to redo
    """
    # Find events that have the current event as their parent
    # If current_event_id is None, look for events with parent_event_id=None
    child_events = [
        event
        for event in project.history_events
        if event.parent_event_id == project.current_event_id
    ]

    if not child_events:
        raise UndoError("Nothing to redo - no future events")

    # Use the most recent child event (last in the list)
    # This handles the case where there are multiple branches
    next_event = child_events[-1]

    # Reconstruct node_map for next version
    next_version = next_event.resulting_dag_version
    new_node_map: dict[NodeId, PersistentObjectId] = {}

    # Add tasks that exist in next version
    for persistent_id, persistent_task in project.persistent_tasks.items():
        if next_version in persistent_task.versions:
            task = persistent_task.versions[next_version]
            new_node_map[task.id] = persistent_id

    # Add branches that exist in next version
    for persistent_id, persistent_branch in project.persistent_branches.items():
        if next_version in persistent_branch.versions:
            branch = persistent_branch.versions[next_version]
            new_node_map[branch.id] = persistent_id

    # Move to next event's DAG version
    return project.model_copy(
        update={
            "dag": project.dag.model_copy(
                update={
                    "current_version_id": next_version,
                    "node_map": new_node_map,
                }
            ),
            "current_event_id": next_event.id,
        }
    )


def can_undo(project: Project) -> bool:
    """Check if undo is available.

    Args:
        project: The project to check

    Returns:
        True if undo is possible, False otherwise
    """
    if project.current_event_id is None:
        return False

    # If there's a current event, we can always undo (even to initial state)
    return any(event.id == project.current_event_id for event in project.history_events)


def can_redo(project: Project) -> bool:
    """Check if redo is available.

    Args:
        project: The project to check

    Returns:
        True if redo is possible, False otherwise
    """
    # Check if any events have current event as their parent
    # (current_event_id can be None, which means we're at initial state)
    for event in project.history_events:
        if event.parent_event_id == project.current_event_id:
            return True

    return False
