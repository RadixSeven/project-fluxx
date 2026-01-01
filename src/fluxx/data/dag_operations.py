"""DAG operations for managing nodes, dependencies, and versions."""

from datetime import UTC, datetime

from fluxx.data.id_generation import (
    generate_branch_id,
    generate_dag_version_id,
    generate_event_id,
    generate_persistent_object_id,
    generate_task_id,
)
from fluxx.data.models import (
    Branch,
    BranchId,
    DAGEvent,
    DAGVersionId,
    Dependency,
    DurationDistribution,
    EventId,
    EventType,
    NodeId,
    PersistentBranch,
    PersistentObjectId,
    PersistentTask,
    PossibleWorld,
    Project,
    ShiftedLognormal,
    Task,
    TaskId,
    Triangular,
    WorkerId,
)
from fluxx.data.validation import validate_dag, validate_dependency


class DAGOperationError(Exception):
    """Raised when a DAG operation fails."""

    pass


def _finalize_dag_operation(
    project: Project,
    new_version_id: DAGVersionId,
    event_id: EventId,
    event_type: EventType,
    affected_nodes: list[NodeId],
    new_persistent_tasks: dict[PersistentObjectId, PersistentTask],
    new_persistent_branches: dict[PersistentObjectId, PersistentBranch],
    operation_name: str,
) -> Project:
    """Create and validate a new project version after a DAG operation.

    This helper function handles the common steps of:
    1. Creating a DAGEvent
    2. Creating an updated Project with new persistent objects
    3. Validating the updated DAG
    4. Returning the validated project

    Args:
        project: The original project
        new_version_id: The new DAG version ID
        event_id: The event ID for this operation
        event_type: The type of event being created
        affected_nodes: List of node IDs affected by this operation
        new_persistent_tasks: Updated persistent tasks dictionary
        new_persistent_branches: Updated persistent branches dictionary
        operation_name: Name of the operation (for error messages)

    Returns:
        The validated updated project

    Raises:
        DAGOperationError: If validation fails
    """
    # Create event
    event = DAGEvent(
        id=event_id,
        timestamp=datetime.now(UTC),
        parent_event_id=project.current_event_id,
        event_type=event_type,
        affected_nodes=affected_nodes,
        resulting_dag_version=new_version_id,
    )

    # Create updated project
    updated_project = project.model_copy(
        update={
            "metadata": project.metadata.model_copy(
                update={"last_modified": datetime.now(UTC)}
            ),
            "dag": project.dag.model_copy(
                update={"current_version_id": new_version_id}
            ),
            "persistent_tasks": new_persistent_tasks,
            "persistent_branches": new_persistent_branches,
            "history_events": project.history_events + [event],
            "current_event_id": event_id,
        }
    )

    # Validate the updated project
    try:
        validate_dag(updated_project)
    except Exception as e:
        raise DAGOperationError(f"Failed to {operation_name}: {e}") from e

    return updated_project


def add_task(
    project: Project,
    title: str,
    description: str,
    parent_id: TaskId | None = None,
    duration_distribution: Triangular | ShiftedLognormal | None = None,
    allowed_workers: list[WorkerId] | None = None,
) -> tuple[Project, TaskId]:
    """Add a new task to the project.

    Creates a new DAG version and records the event in history.

    Args:
        project: The project to modify
        title: Task title
        description: Task description
        parent_id: Optional parent task ID
        duration_distribution: Duration distribution (required for leaf tasks)
        allowed_workers: Optional list of allowed worker IDs

    Returns:
        Tuple of (updated project, new task ID)

    Raises:
        DAGOperationError: If the operation fails validation
    """
    # Generate IDs
    task_id = generate_task_id()
    persistent_id = generate_persistent_object_id()
    new_version_id = generate_dag_version_id()
    event_id = generate_event_id()

    # Create task
    task = Task(
        id=task_id,
        title=title,
        description=description,
        parent_id=parent_id,
        duration_distribution=duration_distribution,
        allowed_workers=allowed_workers,
    )

    # Create persistent task with new version
    persistent_task = PersistentTask(
        id=persistent_id,
        versions={new_version_id: task},
    )

    # Copy all existing persistent objects with new version
    new_persistent_tasks = {}
    for pid, ptask in project.persistent_tasks.items():
        # Get task from current version (skip if doesn't exist in current version)
        if project.dag.current_version_id not in ptask.versions:
            new_persistent_tasks[pid] = ptask
            continue

        current_task = ptask.versions[project.dag.current_version_id]
        # Add to new version
        new_versions = dict(ptask.versions)
        new_versions[new_version_id] = current_task

        # If this is the parent, add new task to its children
        # (keep duration_distribution - preserved for if children removed)
        if parent_id is not None and current_task.id == parent_id:
            updated_task = current_task.model_copy(
                update={"children": current_task.children + [task_id]}
            )
            new_versions[new_version_id] = updated_task

        new_persistent_tasks[pid] = PersistentTask(id=pid, versions=new_versions)

    # Add new persistent task
    new_persistent_tasks[persistent_id] = persistent_task

    # Copy persistent branches with new version
    new_persistent_branches = {}
    for pid, pbranch in project.persistent_branches.items():
        # Skip if doesn't exist in current version
        if project.dag.current_version_id not in pbranch.versions:
            new_persistent_branches[pid] = pbranch
            continue

        current_branch = pbranch.versions[project.dag.current_version_id]
        new_versions_branch: dict[DAGVersionId, Branch] = dict(pbranch.versions)
        new_versions_branch[new_version_id] = current_branch
        new_persistent_branches[pid] = PersistentBranch(
            id=pid, versions=new_versions_branch
        )

    # Update node map
    new_node_map = dict(project.dag.node_map)
    new_node_map[task_id] = persistent_id

    # Create event
    event = DAGEvent(
        id=event_id,
        timestamp=datetime.now(UTC),
        parent_event_id=project.current_event_id,
        event_type=EventType.NODE_CREATED,
        affected_nodes=[task_id],
        resulting_dag_version=new_version_id,
    )

    # Create updated project
    updated_project = project.model_copy(
        update={
            "metadata": project.metadata.model_copy(
                update={"last_modified": datetime.now(UTC)}
            ),
            "dag": project.dag.model_copy(
                update={"current_version_id": new_version_id, "node_map": new_node_map}
            ),
            "persistent_tasks": new_persistent_tasks,
            "persistent_branches": new_persistent_branches,
            "history_events": project.history_events + [event],
            "current_event_id": event_id,
        }
    )

    # Validate the updated project
    try:
        validate_dag(updated_project)
    except Exception as e:
        raise DAGOperationError(f"Failed to add task: {e}") from e

    return updated_project, task_id


def add_branch(
    project: Project,
    title: str,
    description: str,
    possible_worlds: list[PossibleWorld],
) -> tuple[Project, BranchId]:
    """Add a new branch to the project.

    Creates a new DAG version and records the event in history.

    Args:
        project: The project to modify
        title: Branch title
        description: Branch description
        possible_worlds: List of possible world outcomes

    Returns:
        Tuple of (updated project, new branch ID)

    Raises:
        DAGOperationError: If the operation fails validation
    """
    # Generate IDs
    branch_id = generate_branch_id()
    persistent_id = generate_persistent_object_id()
    new_version_id = generate_dag_version_id()
    event_id = generate_event_id()

    # Create branch
    branch = Branch(
        id=branch_id,
        title=title,
        description=description,
        possible_worlds=possible_worlds,
    )

    # Create persistent branch with new version
    persistent_branch = PersistentBranch(
        id=persistent_id,
        versions={new_version_id: branch},
    )

    # Copy all existing persistent objects with new version
    new_persistent_tasks = {}
    for pid, ptask in project.persistent_tasks.items():
        # Skip if doesn't exist in current version
        if project.dag.current_version_id not in ptask.versions:
            new_persistent_tasks[pid] = ptask
            continue

        current_task = ptask.versions[project.dag.current_version_id]
        new_versions = dict(ptask.versions)
        new_versions[new_version_id] = current_task
        new_persistent_tasks[pid] = PersistentTask(id=pid, versions=new_versions)

    new_persistent_branches = {}
    for pid, pbranch in project.persistent_branches.items():
        # Skip if doesn't exist in current version
        if project.dag.current_version_id not in pbranch.versions:
            new_persistent_branches[pid] = pbranch
            continue

        current_branch = pbranch.versions[project.dag.current_version_id]
        new_versions_branch: dict[DAGVersionId, Branch] = dict(pbranch.versions)
        new_versions_branch[new_version_id] = current_branch
        new_persistent_branches[pid] = PersistentBranch(
            id=pid, versions=new_versions_branch
        )

    # Add new persistent branch
    new_persistent_branches[persistent_id] = persistent_branch

    # Update node map
    new_node_map = dict(project.dag.node_map)
    new_node_map[branch_id] = persistent_id

    # Create event
    event = DAGEvent(
        id=event_id,
        timestamp=datetime.now(UTC),
        parent_event_id=project.current_event_id,
        event_type=EventType.NODE_CREATED,
        affected_nodes=[branch_id],
        resulting_dag_version=new_version_id,
    )

    # Create updated project
    updated_project = project.model_copy(
        update={
            "metadata": project.metadata.model_copy(
                update={"last_modified": datetime.now(UTC)}
            ),
            "dag": project.dag.model_copy(
                update={"current_version_id": new_version_id, "node_map": new_node_map}
            ),
            "persistent_tasks": new_persistent_tasks,
            "persistent_branches": new_persistent_branches,
            "history_events": project.history_events + [event],
            "current_event_id": event_id,
        }
    )

    # Validate the updated project
    try:
        validate_dag(updated_project)
    except Exception as e:
        raise DAGOperationError(f"Failed to add branch: {e}") from e

    return updated_project, branch_id


def add_dependency(
    project: Project,
    source_node_id: NodeId,
    dependency: Dependency,
) -> Project:
    """Add a dependency to a node.

    Creates a new DAG version and records the event in history.

    Args:
        project: The project to modify
        source_node_id: The node to add the dependency to
        dependency: The dependency to add

    Returns:
        Updated project

    Raises:
        DAGOperationError: If the operation fails validation
    """
    # Validate dependency first
    try:
        validate_dependency(project, source_node_id, dependency)
    except Exception as e:
        raise DAGOperationError(f"Invalid dependency: {e}") from e

    # Generate IDs
    new_version_id = generate_dag_version_id()
    event_id = generate_event_id()

    # Find the persistent object ID
    persistent_id = project.dag.node_map.get(source_node_id)
    if persistent_id is None:
        # Currently unreachable because validate_dependency (above)
        # ensures that project.dag.node_map.get(source_node_id) is
        # not None.
        raise DAGOperationError(f"Node {source_node_id} not found")  # pragma: no cover

    # Copy all persistent objects with new version
    new_persistent_tasks = {}
    for pid, ptask in project.persistent_tasks.items():
        # Skip if doesn't exist in current version
        if project.dag.current_version_id not in ptask.versions:
            new_persistent_tasks[pid] = ptask
            continue

        current_task = ptask.versions[project.dag.current_version_id]
        new_versions = dict(ptask.versions)

        # If this is the source node, add the dependency
        if pid == persistent_id:
            updated_task = current_task.model_copy(
                update={"dependencies": current_task.dependencies + [dependency]}
            )
            new_versions[new_version_id] = updated_task
        else:
            new_versions[new_version_id] = current_task

        new_persistent_tasks[pid] = PersistentTask(id=pid, versions=new_versions)

    new_persistent_branches = {}
    for pid, pbranch in project.persistent_branches.items():
        # Skip if doesn't exist in current version
        if project.dag.current_version_id not in pbranch.versions:
            new_persistent_branches[pid] = pbranch
            continue

        current_branch = pbranch.versions[project.dag.current_version_id]
        new_versions_branch: dict[DAGVersionId, Branch] = dict(pbranch.versions)

        # If this is the source node, add the dependency
        if pid == persistent_id:
            updated_branch = current_branch.model_copy(
                update={"dependencies": current_branch.dependencies + [dependency]}
            )
            new_versions_branch[new_version_id] = updated_branch
        else:
            new_versions_branch[new_version_id] = current_branch

        new_persistent_branches[pid] = PersistentBranch(
            id=pid, versions=new_versions_branch
        )

    return _finalize_dag_operation(
        project=project,
        new_version_id=new_version_id,
        event_id=event_id,
        event_type=EventType.NODE_MODIFIED,
        affected_nodes=[source_node_id],
        new_persistent_tasks=new_persistent_tasks,
        new_persistent_branches=new_persistent_branches,
        operation_name="add dependency",
    )


def update_task(
    project: Project,
    task_id: TaskId,
    title: str | None = None,
    description: str | None = None,
    duration_distribution: DurationDistribution | None = None,
    allowed_workers: list[WorkerId] | None = None,
    excluded_worker_tasks: list[TaskId] | None = None,
    assigned_worker: WorkerId | None = None,
    actual_duration: float | None = None,
) -> Project:
    """Update an existing task's properties.

    Creates a new DAG version and records the event in history.
    Only updates properties that are explicitly provided (not None).

    Args:
        project: The project to modify
        task_id: The task to update
        title: New title (if provided)
        description: New description (if provided)
        duration_distribution: New duration distribution (if provided)
        allowed_workers: New allowed workers list (if provided)
        excluded_worker_tasks: New excluded worker tasks (if provided)
        assigned_worker: New assigned worker (if provided)
        actual_duration: New actual duration (if provided)

    Returns:
        Updated project

    Raises:
        DAGOperationError: If the operation fails validation
    """
    # Find the task
    node_id = task_id
    persistent_id = project.dag.node_map.get(node_id)
    if persistent_id is None:
        raise DAGOperationError(f"Task {task_id} not found")

    if persistent_id not in project.persistent_tasks:
        raise DAGOperationError(f"Node {task_id} is not a task")

    # Get current task
    persistent_task = project.persistent_tasks[persistent_id]
    current_task = persistent_task.versions[project.dag.current_version_id]

    # Build updated task with only changed properties
    update_dict: dict[str, object] = {}
    if title is not None:
        update_dict["title"] = title
    if description is not None:
        update_dict["description"] = description
    if duration_distribution is not None:
        update_dict["duration_distribution"] = duration_distribution
    if allowed_workers is not None:
        update_dict["allowed_workers"] = allowed_workers
    if excluded_worker_tasks is not None:
        update_dict["excluded_worker_tasks"] = excluded_worker_tasks
    if assigned_worker is not None:
        update_dict["actual_assignee"] = assigned_worker
    if actual_duration is not None:
        update_dict["actual_duration"] = actual_duration

    # If nothing to update, return unchanged project
    if not update_dict:
        return project

    updated_task = current_task.model_copy(update=update_dict)

    # Generate IDs
    new_version_id = generate_dag_version_id()
    event_id = generate_event_id()

    # Copy all persistent objects with new version
    new_persistent_tasks = {}
    for pid, ptask in project.persistent_tasks.items():
        # Skip if doesnt exist in current version
        if project.dag.current_version_id not in ptask.versions:
            new_persistent_tasks[pid] = ptask
            continue

        current = ptask.versions[project.dag.current_version_id]
        new_versions = dict(ptask.versions)

        # If this is the task being updated, use the updated version
        if pid == persistent_id:
            new_versions[new_version_id] = updated_task
        else:
            new_versions[new_version_id] = current

        new_persistent_tasks[pid] = PersistentTask(id=pid, versions=new_versions)

    new_persistent_branches = {}
    for pid, pbranch in project.persistent_branches.items():
        # Skip if doesn't exist in current version
        if project.dag.current_version_id not in pbranch.versions:
            new_persistent_branches[pid] = pbranch
            continue

        current_branch = pbranch.versions[project.dag.current_version_id]
        new_versions_branch: dict[DAGVersionId, Branch] = dict(pbranch.versions)
        new_versions_branch[new_version_id] = current_branch
        new_persistent_branches[pid] = PersistentBranch(
            id=pid, versions=new_versions_branch
        )

    return _finalize_dag_operation(
        project=project,
        new_version_id=new_version_id,
        event_id=event_id,
        event_type=EventType.NODE_MODIFIED,
        affected_nodes=[node_id],
        new_persistent_tasks=new_persistent_tasks,
        new_persistent_branches=new_persistent_branches,
        operation_name="update task",
    )


def update_branch(
    project: Project,
    branch_id: BranchId,
    title: str | None = None,
    description: str | None = None,
    possible_worlds: list[PossibleWorld] | None = None,
) -> Project:
    """Update an existing branch's properties.

    Creates a new DAG version and records the event in history.
    Only updates properties that are explicitly provided (not None).

    Args:
        project: The project to modify
        branch_id: The branch to update
        title: New title (if provided)
        description: New description (if provided)
        possible_worlds: New possible worlds (if provided)

    Returns:
        Updated project

    Raises:
        DAGOperationError: If the operation fails validation
    """
    # Find the branch
    node_id = branch_id
    persistent_id = project.dag.node_map.get(node_id)
    if persistent_id is None:
        raise DAGOperationError(f"Branch {branch_id} not found")

    if persistent_id not in project.persistent_branches:
        raise DAGOperationError(f"Node {branch_id} is not a branch")

    # Get current branch
    persistent_branch = project.persistent_branches[persistent_id]
    current_branch = persistent_branch.versions[project.dag.current_version_id]

    # Build updated branch with only changed properties
    update_dict: dict[str, object] = {}
    if title is not None:
        update_dict["title"] = title
    if description is not None:
        update_dict["description"] = description
    if possible_worlds is not None:
        update_dict["possible_worlds"] = possible_worlds

    # If nothing to update, return unchanged project
    if not update_dict:
        return project

    updated_branch = current_branch.model_copy(update=update_dict)

    # Generate IDs
    new_version_id = generate_dag_version_id()
    event_id = generate_event_id()

    # Copy all persistent objects with new version
    new_persistent_tasks = {}
    for pid, ptask in project.persistent_tasks.items():
        # Skip if doesnt exist in current version
        if project.dag.current_version_id not in ptask.versions:
            new_persistent_tasks[pid] = ptask
            continue

        current = ptask.versions[project.dag.current_version_id]
        new_versions = dict(ptask.versions)
        new_versions[new_version_id] = current
        new_persistent_tasks[pid] = PersistentTask(id=pid, versions=new_versions)

    new_persistent_branches = {}
    for pid, pbranch in project.persistent_branches.items():
        # Skip if doesn't exist in current version
        if project.dag.current_version_id not in pbranch.versions:
            new_persistent_branches[pid] = pbranch
            continue

        current_branch = pbranch.versions[project.dag.current_version_id]
        new_versions_branch: dict[DAGVersionId, Branch] = dict(pbranch.versions)

        # If this is the branch being updated, use the updated version
        if pid == persistent_id:
            new_versions_branch[new_version_id] = updated_branch
        else:
            new_versions_branch[new_version_id] = current_branch

        new_persistent_branches[pid] = PersistentBranch(
            id=pid, versions=new_versions_branch
        )

    return _finalize_dag_operation(
        project=project,
        new_version_id=new_version_id,
        event_id=event_id,
        event_type=EventType.NODE_MODIFIED,
        affected_nodes=[node_id],
        new_persistent_tasks=new_persistent_tasks,
        new_persistent_branches=new_persistent_branches,
        operation_name="update branch",
    )


def remove_dependency(
    project: Project,
    source_node_id: NodeId,
    dependency: Dependency,
) -> Project:
    """Remove a dependency from a node.

    Creates a new DAG version and records the event in history.

    Args:
        project: The project to modify
        source_node_id: The node to remove the dependency from
        dependency: The dependency to remove

    Returns:
        Updated project

    Raises:
        DAGOperationError: If the operation fails
    """
    # Find the persistent object ID
    persistent_id = project.dag.node_map.get(source_node_id)
    if persistent_id is None:
        raise DAGOperationError(f"Node {source_node_id} not found")

    # Generate IDs
    new_version_id = generate_dag_version_id()
    event_id = generate_event_id()

    # Copy all persistent objects with new version
    new_persistent_tasks = {}
    for pid, ptask in project.persistent_tasks.items():
        # Skip if doesnt exist in current version
        if project.dag.current_version_id not in ptask.versions:
            new_persistent_tasks[pid] = ptask
            continue

        current_task = ptask.versions[project.dag.current_version_id]
        new_versions = dict(ptask.versions)

        # If this is the source node, remove the dependency
        if pid == persistent_id:
            new_deps = [d for d in current_task.dependencies if d != dependency]
            updated_task = current_task.model_copy(update={"dependencies": new_deps})
            new_versions[new_version_id] = updated_task
        else:
            new_versions[new_version_id] = current_task

        new_persistent_tasks[pid] = PersistentTask(id=pid, versions=new_versions)

    new_persistent_branches = {}
    for pid, pbranch in project.persistent_branches.items():
        # Skip if doesn't exist in current version
        if project.dag.current_version_id not in pbranch.versions:
            new_persistent_branches[pid] = pbranch
            continue

        current_branch = pbranch.versions[project.dag.current_version_id]
        new_versions_branch: dict[DAGVersionId, Branch] = dict(pbranch.versions)

        # If this is the source node, remove the dependency
        if pid == persistent_id:
            new_deps = [d for d in current_branch.dependencies if d != dependency]
            updated_branch = current_branch.model_copy(
                update={"dependencies": new_deps}
            )
            new_versions_branch[new_version_id] = updated_branch
        else:
            new_versions_branch[new_version_id] = current_branch

        new_persistent_branches[pid] = PersistentBranch(
            id=pid, versions=new_versions_branch
        )

    return _finalize_dag_operation(
        project=project,
        new_version_id=new_version_id,
        event_id=event_id,
        event_type=EventType.NODE_MODIFIED,
        affected_nodes=[source_node_id],
        new_persistent_tasks=new_persistent_tasks,
        new_persistent_branches=new_persistent_branches,
        operation_name="remove dependency",
    )


def convert_to_parent_task(
    project: Project,
    task_id: TaskId,
    child_title: str,
) -> tuple[Project, TaskId]:
    """Convert a leaf task to a parent task with one child.

    The child task inherits the duration distribution. Two required dependencies
    are created:
    - child.start >= parent.start (added to child)
    - parent.end >= child.end (added to parent)

    Args:
        project: The project to modify
        task_id: ID of the task to convert to parent
        child_title: Title for the new child task

    Returns:
        Tuple of (updated project, new child task ID)

    Raises:
        DAGOperationError: If the task is already a parent or doesn't exist
    """
    # Validate task exists and is a leaf
    node_id = task_id
    if node_id not in project.dag.node_map:
        raise DAGOperationError(f"Task {task_id} not found")

    persistent_id = project.dag.node_map[node_id]
    if persistent_id not in project.persistent_tasks:
        raise DAGOperationError(f"Task {task_id} is not a task")

    persistent_task = project.persistent_tasks[persistent_id]
    current_version = project.dag.current_version_id

    if current_version not in persistent_task.versions:
        raise DAGOperationError(f"Task {task_id} not in current version")

    parent_task = persistent_task.versions[current_version]

    if parent_task.children:
        raise DAGOperationError(f"Task {task_id} already has children")

    # Generate IDs for child and new version
    child_id = generate_task_id()
    child_persistent_id = generate_persistent_object_id()
    new_version_id = generate_dag_version_id()
    event_id = generate_event_id()

    # Create child task with parent's duration distribution
    from fluxx.data.models import ConstraintType, Endpoint

    # Use parent's distribution, or default if parent has none
    child_distribution = parent_task.duration_distribution
    if child_distribution is None:
        child_distribution = ShiftedLognormal(min=0.25, mode=6.0, percentile_95=24.0)

    child_task = Task(
        id=child_id,
        title=child_title,
        description="",
        parent_id=task_id,
        duration_distribution=child_distribution,
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=task_id,
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create persistent child task
    persistent_child = PersistentTask(
        id=child_persistent_id,
        versions={new_version_id: child_task},
    )

    # Update parent task: remove duration, add child, add dependency
    updated_parent = parent_task.model_copy(
        update={
            "children": [child_id],
            "duration_distribution": None,
            "dependencies": parent_task.dependencies
            + [
                Dependency(
                    source_endpoint=Endpoint.END,
                    target_node_id=child_id,
                    target_endpoint=Endpoint.END,
                    constraint_type=ConstraintType.GREATER_EQUAL,
                )
            ],
        }
    )

    # Copy all persistent tasks with new version
    new_persistent_tasks = {}
    for pid, ptask in project.persistent_tasks.items():
        if current_version not in ptask.versions:
            new_persistent_tasks[pid] = ptask
            continue

        current_task = ptask.versions[current_version]
        new_versions = dict(ptask.versions)

        # Update the parent task
        if pid == persistent_id:
            new_versions[new_version_id] = updated_parent
        else:
            new_versions[new_version_id] = current_task

        new_persistent_tasks[pid] = PersistentTask(id=pid, versions=new_versions)

    # Add new child persistent task
    new_persistent_tasks[child_persistent_id] = persistent_child

    # Copy persistent branches with new version
    new_persistent_branches = {}
    for pid, pbranch in project.persistent_branches.items():
        if current_version not in pbranch.versions:
            new_persistent_branches[pid] = pbranch
            continue

        current_branch = pbranch.versions[current_version]
        new_versions_branch: dict[DAGVersionId, Branch] = dict(pbranch.versions)
        new_versions_branch[new_version_id] = current_branch
        new_persistent_branches[pid] = PersistentBranch(
            id=pid, versions=new_versions_branch
        )

    # Update node map
    new_node_map = dict(project.dag.node_map)
    new_node_map[child_id] = child_persistent_id

    # Create event
    event = DAGEvent(
        id=event_id,
        timestamp=datetime.now(UTC),
        parent_event_id=project.current_event_id,
        event_type=EventType.NODE_MODIFIED,
        affected_nodes=[task_id, child_id],
        resulting_dag_version=new_version_id,
    )

    # Create updated project
    updated_project = project.model_copy(
        update={
            "metadata": project.metadata.model_copy(
                update={"last_modified": datetime.now(UTC)}
            ),
            "dag": project.dag.model_copy(
                update={"current_version_id": new_version_id, "node_map": new_node_map}
            ),
            "persistent_tasks": new_persistent_tasks,
            "persistent_branches": new_persistent_branches,
            "history_events": project.history_events + [event],
            "current_event_id": event_id,
        }
    )

    # Validate
    try:
        validate_dag(updated_project)
    except Exception as e:
        raise DAGOperationError(f"Failed to convert to parent: {e}") from e

    return updated_project, child_id


def add_sibling_subtask(
    project: Project,
    task_id: TaskId,
    sibling_title: str,
    duration_distribution: Triangular | ShiftedLognormal | None = None,
) -> tuple[Project, TaskId]:
    """Add a sibling subtask to an existing subtask.

    Creates a new task with the same parent as the given task. Two required
    dependencies are created:
    - sibling.start >= parent.start (added to sibling)
    - parent.end >= sibling.end (added to parent)

    Args:
        project: The project to modify
        task_id: ID of an existing subtask (to get parent)
        sibling_title: Title for the new sibling task
        duration_distribution: Duration distribution for the new sibling

    Returns:
        Tuple of (updated project, new sibling task ID)

    Raises:
        DAGOperationError: If the task doesn't have a parent or doesn't exist
    """
    # Validate task exists and has a parent
    node_id = task_id
    if node_id not in project.dag.node_map:
        raise DAGOperationError(f"Task {task_id} not found")

    persistent_id = project.dag.node_map[node_id]
    if persistent_id not in project.persistent_tasks:
        raise DAGOperationError(f"Task {task_id} is not a task")

    persistent_task = project.persistent_tasks[persistent_id]
    current_version = project.dag.current_version_id

    if current_version not in persistent_task.versions:
        raise DAGOperationError(f"Task {task_id} not in current version")

    existing_task = persistent_task.versions[current_version]

    if existing_task.parent_id is None:
        raise DAGOperationError(f"Task {task_id} is not a subtask (has no parent)")

    parent_id = existing_task.parent_id

    # Generate IDs
    sibling_id = generate_task_id()
    sibling_persistent_id = generate_persistent_object_id()
    new_version_id = generate_dag_version_id()
    event_id = generate_event_id()

    # Create sibling task
    from fluxx.data.models import ConstraintType, Endpoint

    # Use default distribution if none provided
    if duration_distribution is None:
        duration_distribution = ShiftedLognormal(min=0.25, mode=6.0, percentile_95=24.0)

    sibling_task = Task(
        id=sibling_id,
        title=sibling_title,
        description="",
        parent_id=parent_id,
        duration_distribution=duration_distribution,
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=parent_id,
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create persistent sibling task
    persistent_sibling = PersistentTask(
        id=sibling_persistent_id,
        versions={new_version_id: sibling_task},
    )

    # Copy all persistent tasks with new version
    new_persistent_tasks = {}
    for pid, ptask in project.persistent_tasks.items():
        if current_version not in ptask.versions:
            new_persistent_tasks[pid] = ptask
            continue

        current_task = ptask.versions[current_version]
        new_versions = dict(ptask.versions)

        # Update parent task: add child and dependency
        if current_task.id == parent_id:
            updated_parent = current_task.model_copy(
                update={
                    "children": current_task.children + [sibling_id],
                    "dependencies": current_task.dependencies
                    + [
                        Dependency(
                            source_endpoint=Endpoint.END,
                            target_node_id=sibling_id,
                            target_endpoint=Endpoint.END,
                            constraint_type=ConstraintType.GREATER_EQUAL,
                        )
                    ],
                }
            )
            new_versions[new_version_id] = updated_parent
        else:
            new_versions[new_version_id] = current_task

        new_persistent_tasks[pid] = PersistentTask(id=pid, versions=new_versions)

    # Add new sibling persistent task
    new_persistent_tasks[sibling_persistent_id] = persistent_sibling

    # Copy persistent branches with new version
    new_persistent_branches = {}
    for pid, pbranch in project.persistent_branches.items():
        if current_version not in pbranch.versions:
            new_persistent_branches[pid] = pbranch
            continue

        current_branch = pbranch.versions[current_version]
        new_versions_branch: dict[DAGVersionId, Branch] = dict(pbranch.versions)
        new_versions_branch[new_version_id] = current_branch
        new_persistent_branches[pid] = PersistentBranch(
            id=pid, versions=new_versions_branch
        )

    # Update node map
    new_node_map = dict(project.dag.node_map)
    new_node_map[sibling_id] = sibling_persistent_id

    # Create event
    event = DAGEvent(
        id=event_id,
        timestamp=datetime.now(UTC),
        parent_event_id=project.current_event_id,
        event_type=EventType.NODE_CREATED,
        affected_nodes=[parent_id, sibling_id],
        resulting_dag_version=new_version_id,
    )

    # Create updated project
    updated_project = project.model_copy(
        update={
            "metadata": project.metadata.model_copy(
                update={"last_modified": datetime.now(UTC)}
            ),
            "dag": project.dag.model_copy(
                update={"current_version_id": new_version_id, "node_map": new_node_map}
            ),
            "persistent_tasks": new_persistent_tasks,
            "persistent_branches": new_persistent_branches,
            "history_events": project.history_events + [event],
            "current_event_id": event_id,
        }
    )

    # Validate
    try:
        validate_dag(updated_project)
    except Exception as e:
        raise DAGOperationError(f"Failed to add sibling subtask: {e}") from e

    return updated_project, sibling_id
