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
    EventType,
    NodeId,
    PersistentBranch,
    PersistentTask,
    PossibleWorld,
    Project,
    Task,
    TaskId,
    WorkerId,
)
from fluxx.data.validation import validate_dag, validate_dependency


class DAGOperationError(Exception):
    """Raised when a DAG operation fails."""

    pass


def add_task(
    project: Project,
    title: str,
    description: str,
    parent_id: TaskId | None = None,
    duration_distribution: DurationDistribution | None = None,
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
        # Get task from current version
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
        current_branch = pbranch.versions[project.dag.current_version_id]
        new_versions_branch: dict[DAGVersionId, Branch] = dict(pbranch.versions)
        new_versions_branch[new_version_id] = current_branch
        new_persistent_branches[pid] = PersistentBranch(
            id=pid, versions=new_versions_branch
        )

    # Update node map
    new_node_map = dict(project.dag.node_map)
    new_node_map[NodeId(task_id)] = persistent_id

    # Create event
    event = DAGEvent(
        id=event_id,
        timestamp=datetime.now(UTC),
        parent_event_id=project.current_event_id,
        event_type=EventType.NODE_CREATED,
        affected_nodes=[NodeId(task_id)],
        resulting_dag_version=new_version_id,
    )

    # Create updated project
    updated_project = Project(
        **project.model_dump(
            exclude={
                "dag",
                "persistent_tasks",
                "persistent_branches",
                "history_events",
                "current_event_id",
                "metadata",
            }
        ),
        metadata=project.metadata.model_copy(
            update={"last_modified": datetime.now(UTC)}
        ),
        dag=project.dag.model_copy(
            update={"current_version_id": new_version_id, "node_map": new_node_map}
        ),
        persistent_tasks=new_persistent_tasks,
        persistent_branches=new_persistent_branches,
        history_events=project.history_events + [event],
        current_event_id=event_id,
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
        current_task = ptask.versions[project.dag.current_version_id]
        new_versions = dict(ptask.versions)
        new_versions[new_version_id] = current_task
        new_persistent_tasks[pid] = PersistentTask(id=pid, versions=new_versions)

    new_persistent_branches = {}
    for pid, pbranch in project.persistent_branches.items():
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
    new_node_map[NodeId(branch_id)] = persistent_id

    # Create event
    event = DAGEvent(
        id=event_id,
        timestamp=datetime.now(UTC),
        parent_event_id=project.current_event_id,
        event_type=EventType.NODE_CREATED,
        affected_nodes=[NodeId(branch_id)],
        resulting_dag_version=new_version_id,
    )

    # Create updated project
    updated_project = Project(
        **project.model_dump(
            exclude={
                "dag",
                "persistent_tasks",
                "persistent_branches",
                "history_events",
                "current_event_id",
                "metadata",
            }
        ),
        metadata=project.metadata.model_copy(
            update={"last_modified": datetime.now(UTC)}
        ),
        dag=project.dag.model_copy(
            update={"current_version_id": new_version_id, "node_map": new_node_map}
        ),
        persistent_tasks=new_persistent_tasks,
        persistent_branches=new_persistent_branches,
        history_events=project.history_events + [event],
        current_event_id=event_id,
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
        current_task = ptask.versions[project.dag.current_version_id]
        new_versions = dict(ptask.versions)

        # If this is the source node, add the dependency
        if pid == persistent_id:
            updated_task = Task(
                **current_task.model_dump(exclude={"dependencies"}),
                dependencies=current_task.dependencies + [dependency],
            )
            new_versions[new_version_id] = updated_task
        else:
            new_versions[new_version_id] = current_task

        new_persistent_tasks[pid] = PersistentTask(id=pid, versions=new_versions)

    new_persistent_branches = {}
    for pid, pbranch in project.persistent_branches.items():
        current_branch = pbranch.versions[project.dag.current_version_id]
        new_versions_branch: dict[DAGVersionId, Branch] = dict(pbranch.versions)

        # If this is the source node, add the dependency
        if pid == persistent_id:
            updated_branch = Branch(
                **current_branch.model_dump(exclude={"dependencies"}),
                dependencies=current_branch.dependencies + [dependency],
            )
            new_versions_branch[new_version_id] = updated_branch
        else:
            new_versions_branch[new_version_id] = current_branch

        new_persistent_branches[pid] = PersistentBranch(
            id=pid, versions=new_versions_branch
        )

    # Create event
    event = DAGEvent(
        id=event_id,
        timestamp=datetime.now(UTC),
        parent_event_id=project.current_event_id,
        event_type=EventType.NODE_MODIFIED,
        affected_nodes=[source_node_id],
        resulting_dag_version=new_version_id,
    )

    # Create updated project
    updated_project = Project(
        **project.model_dump(
            exclude={
                "dag",
                "persistent_tasks",
                "persistent_branches",
                "history_events",
                "current_event_id",
                "metadata",
            }
        ),
        metadata=project.metadata.model_copy(
            update={"last_modified": datetime.now(UTC)}
        ),
        dag=project.dag.model_copy(update={"current_version_id": new_version_id}),
        persistent_tasks=new_persistent_tasks,
        persistent_branches=new_persistent_branches,
        history_events=project.history_events + [event],
        current_event_id=event_id,
    )

    # Validate the updated project for cycles
    try:
        validate_dag(updated_project)
    except Exception as e:
        raise DAGOperationError(f"Failed to add dependency: {e}") from e

    return updated_project
