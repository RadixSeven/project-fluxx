"""DAG validation utilities."""

from collections import defaultdict

from fluxx.data.models import (
    ConstraintType,
    DAGVersionId,
    Dependency,
    DependencyTargetId,
    Endpoint,
    NodeId,
    PossibleWorldId,
    Project,
    Task,
    TaskId,
    type_explode_id,
)


class ValidationError(Exception):
    """Base exception for validation errors."""

    pass


class CycleError(ValidationError):
    """Raised when a cycle is detected in the DAG."""

    pass


class EndpointError(ValidationError):
    """Raised when endpoints are incompatible."""

    pass


class WorkerConstraintError(ValidationError):
    """Raised when worker constraints are invalid."""

    pass


class HierarchyError(ValidationError):
    """Raised when task hierarchy is invalid."""

    pass


def validate_dag(project: Project) -> None:
    """Validate the entire DAG for structural correctness.

    Args:
        project: The project to validate

    Raises:
        ValidationError: If the DAG has any structural issues
    """
    # Get current version
    version_id = project.dag.current_version_id

    # Validate no cycles
    _check_for_cycles(project, version_id)

    # Validate task hierarchy
    _validate_task_hierarchy(project, version_id)

    # Validate worker constraints
    _validate_worker_constraints(project, version_id)


def _build_dependency_graph(
    project: Project, version_id: DAGVersionId
) -> dict[
    tuple[NodeId | PossibleWorldId, Endpoint],
    list[tuple[NodeId | PossibleWorldId, Endpoint]],
]:
    """Build the endpoint-based dependency graph for a DAG version.

    The graph uses (node_id, endpoint) tuples as nodes. Each task has START
    and END endpoints, each branch has an OCCURRENCE endpoint, and each
    possible world has an OCCURRENCE endpoint.

    Args:
        project: The project containing the DAG
        version_id: The DAG version to build the graph for

    Returns:
        Adjacency list representation of the dependency graph
    """
    from fluxx.data.models import Endpoint

    graph: dict[
        tuple[NodeId | PossibleWorldId, Endpoint],
        list[tuple[NodeId | PossibleWorldId, Endpoint]],
    ] = defaultdict(list)

    # Get all nodes in the current version
    for node_id, persistent_id in project.dag.node_map.items():
        # Check if it's a task
        if persistent_id in project.persistent_tasks:
            persistent_task = project.persistent_tasks[persistent_id]
            if version_id in persistent_task.versions:
                task = persistent_task.versions[version_id]

                # Add implicit dependency: task.start -> task.end
                graph[(node_id, Endpoint.START)].append((node_id, Endpoint.END))

                # Add explicit dependencies from this task
                for dep in task.dependencies:
                    add_dep_edge(
                        node_id,
                        dep.source_endpoint,
                        dep.target_node_id,
                        dep.target_endpoint,
                        graph,
                    )

        # Check if it's a branch
        elif persistent_id in project.persistent_branches:
            persistent_branch = project.persistent_branches[persistent_id]
            if version_id in persistent_branch.versions:
                branch = persistent_branch.versions[version_id]

                # Add implicit dependencies: occurrence_point -> each possible world
                for pw in branch.possible_worlds:
                    graph[(node_id, Endpoint.OCCURRENCE)].append(
                        (pw.id, Endpoint.OCCURRENCE)
                    )

                # Add explicit dependencies from this branch
                for dep in branch.dependencies:
                    add_dep_edge(
                        node_id,
                        dep.source_endpoint,
                        dep.target_node_id,
                        dep.target_endpoint,
                        graph,
                    )

    return graph


def _detect_cycles_in_graph(
    graph: dict[
        tuple[NodeId | PossibleWorldId, Endpoint],
        list[tuple[NodeId | PossibleWorldId, Endpoint]],
    ],
) -> None:
    """Detect cycles in a dependency graph using DFS.

    Args:
        graph: Adjacency list of the dependency graph

    Raises:
        CycleError: If a cycle is detected in the graph
    """
    # DFS-based cycle detection with three colors
    white, gray, black = 0, 1, 2
    color: dict[tuple[NodeId | PossibleWorldId, Endpoint], int] = defaultdict(
        lambda: white
    )

    def dfs(
        node: tuple[NodeId | PossibleWorldId, Endpoint],
        path: list[tuple[NodeId | PossibleWorldId, Endpoint]],
    ) -> None:
        if color[node] == gray:
            # Found a cycle - node is in current path
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            cycle_str = " -> ".join(
                f"{n_id}.{endpoint.value}" for n_id, endpoint in cycle
            )
            raise CycleError(f"Cycle detected in DAG: {cycle_str}")

        if color[node] == black:
            # Already fully explored
            return

        color[node] = gray
        path.append(node)

        for neighbor in graph[node]:
            dfs(neighbor, path)

        path.pop()
        color[node] = black

    # Check all nodes in the graph, including possible world IDs
    # Convert to list to avoid "dictionary changed size during iteration"
    for node in list(graph.keys()):
        if color[node] == white:
            dfs(node, [])


def _check_for_cycles(project: Project, version_id: DAGVersionId) -> None:
    """Check for cycles in the dependency graph.

    The dependency graph is endpoint-based: each task has two nodes (start, end),
    and each branch has nodes for its occurrence point and each possible world.
    Dependencies connect specific endpoints, not whole nodes.

    Args:
        project: The project to check
        version_id: The DAG version to check

    Raises:
        CycleError: If a cycle is detected
    """
    graph = _build_dependency_graph(project, version_id)
    _detect_cycles_in_graph(graph)


def add_dep_edge(
    source_id: NodeId,
    source_endpoint: Endpoint,
    target_id: DependencyTargetId,
    target_endpoint: Endpoint,
    graph: dict[
        tuple[NodeId | PossibleWorldId, Endpoint],
        list[tuple[NodeId | PossibleWorldId, Endpoint]],
    ],
) -> None:
    """
    Add a dependency edge to the graph.

    Dependency: source[source_endpoint] >= target[target_endpoint]
    Creates edge: target[target_endpoint] -> source[source_endpoint]

    Args:
        source_id: ID of the source node.
        source_endpoint: Endpoint of the source node.
        target_id: ID of the target node.
        target_endpoint: Endpoint of the target node.
        graph: Dependency graph (modified)

    Returns:
        None

    Raises:
        ValidationError: If the target ID is invalid.
    """
    try:
        as_task, as_branch, as_world = type_explode_id(target_id)
    except ValueError as ve:
        raise ValidationError(f"Invalid dependency target ID: {target_id}") from ve

    if as_world is not None:
        target_node: NodeId = as_world[0]
        target_endpoint = Endpoint.OCCURRENCE
    elif as_task is not None:
        target_node = as_task
        target_endpoint = target_endpoint
    elif as_branch is not None:
        target_node = as_branch
        target_endpoint = target_endpoint
    else:
        raise ValidationError(f"Forgot dependency target type: {target_id}")

    graph[(target_node, target_endpoint)].append((source_id, source_endpoint))


def _validate_task_hierarchy(project: Project, version_id: DAGVersionId) -> None:
    """Validate task parent/child relationships.

    Args:
        project: The project to validate
        version_id: The DAG version to check

    Raises:
        HierarchyError: If hierarchy is invalid
    """
    for node_id, persistent_id in project.dag.node_map.items():
        if persistent_id not in project.persistent_tasks:
            continue

        persistent_task = project.persistent_tasks[persistent_id]
        if version_id not in persistent_task.versions:
            continue

        task = persistent_task.versions[version_id]

        # If that task has a parent, verify parent exists and lists this as child
        if task.parent_id is not None:
            parent_persistent_id = project.dag.node_map.get(task.parent_id)
            if parent_persistent_id is None:
                raise HierarchyError(
                    f"Task {node_id} references non-existent parent {task.parent_id}"
                )

            if parent_persistent_id not in project.persistent_tasks:
                raise HierarchyError(
                    f"Task {node_id} parent {task.parent_id} is not a task"
                )

            parent_task = project.persistent_tasks[parent_persistent_id].versions[
                version_id
            ]
            if task.id not in parent_task.children:
                raise HierarchyError(
                    f"Task {node_id} parent {task.parent_id} does not list it as a "
                    f"child"
                )

        # Verify all children exist and reference this task as their parent
        for child_id in task.children:
            child_persistent_id = project.dag.node_map.get(child_id)
            if child_persistent_id is None:
                raise HierarchyError(
                    f"Task {node_id} references non-existent child {child_id}"
                )

            if child_persistent_id not in project.persistent_tasks:
                raise HierarchyError(f"Task {node_id} child {child_id} is not a task")

            child_persistent = project.persistent_tasks[child_persistent_id]
            if version_id not in child_persistent.versions:
                continue  # Skip children not in the current version

            child_task = child_persistent.versions[version_id]
            if child_task.parent_id != task.id:
                raise HierarchyError(
                    f"Task {node_id} child {child_id} does not reference it as parent"
                )

        # Leaf tasks should have duration distribution
        if len(task.children) == 0 and task.duration_distribution is None:
            raise HierarchyError(
                f"Leaf task {node_id} must have a duration distribution"
            )

        # Parent tasks can have duration distribution (it's preserved but ignored)


def _validate_worker_constraints(project: Project, version_id: DAGVersionId) -> None:
    """Validate worker constraints in tasks.

    Args:
        project: The project to validate
        version_id: The DAG version to check

    Raises:
        WorkerConstraintError: If worker constraints are invalid
    """
    # Get all worker IDs
    worker_ids = {worker.id for worker in project.workers}

    for node_id, persistent_id in project.dag.node_map.items():
        if persistent_id not in project.persistent_tasks:
            continue

        persistent_task = project.persistent_tasks[persistent_id]
        if version_id not in persistent_task.versions:
            continue

        task = persistent_task.versions[version_id]

        # Validate allowed_workers reference existing workers
        if task.allowed_workers is not None:
            for worker_id in task.allowed_workers:
                if worker_id not in worker_ids:
                    raise WorkerConstraintError(
                        f"Task {node_id} references non-existent worker {worker_id} "
                        f"in allowed_workers"
                    )

        # Validate excluded_worker_tasks reference existing tasks
        for excluded_task_id in task.excluded_worker_tasks:
            if excluded_task_id not in project.dag.node_map:
                raise WorkerConstraintError(
                    f"Task {node_id} references non-existent task {excluded_task_id} "
                    f"in excluded_worker_tasks"
                )

            # Validate required dependency exists for each exclusion
            # According to spec, if task N excludes assignee of task M,
            # there must be a dependency: N.start >= M.start
            if not _has_required_exclusion_dep(task, excluded_task_id):
                raise WorkerConstraintError(
                    f"Task {node_id} excludes assignee of {excluded_task_id} "
                    f"but missing required dependency: "
                    f"{node_id}.start >= {excluded_task_id}.start"
                )


def _has_required_exclusion_dep(
    task: Task,
    excluded_task_id: TaskId,
) -> bool:
    """Check if task has the required dependency for an exclusion.

    Args:
        task: The task to check
        excluded_task_id: The excluded task ID

    Returns:
        True if the required dependency exists
    """
    for dep in task.dependencies:
        if (
            dep.source_endpoint == Endpoint.START
            and dep.target_node_id == excluded_task_id
            and dep.target_endpoint == Endpoint.START
            and dep.constraint_type == ConstraintType.GREATER_EQUAL
        ):
            return True
    return False


def validate_dependency(
    project: Project,
    source_node_id: NodeId,
    dependency: Dependency,
) -> None:
    """Validate a single dependency for compatibility.

    Args:
        project: The project containing the nodes
        source_node_id: The node ID that has this dependency
        dependency: The dependency to validate

    Raises:
        EndpointError: If endpoints are incompatible
        ValidationError: If nodes don't exist
    """
    # Check source node exists
    source_persistent_id = project.dag.node_map.get(source_node_id)
    if source_persistent_id is None:
        raise ValidationError(f"Source node {source_node_id} does not exist")

    # Determine source node type
    source_is_task = source_persistent_id in project.persistent_tasks
    source_is_branch = source_persistent_id in project.persistent_branches

    # Validate that the target node exists and determine its type
    try:
        as_task, as_branch, as_world = type_explode_id(dependency.target_node_id)
    except ValueError as err:
        raise ValidationError(
            f"Target ID {dependency.target_node_id} does not match a known ID type"
        ) from err

    # Validate target exists based on type
    if as_world is not None:
        # Validate branch exists
        branch_persistent_id = project.dag.node_map.get(as_world.branch_id)
        if branch_persistent_id is None:
            raise ValidationError(
                f"Target {dependency.target_node_id} references non-existent "
                f"branch {as_world.branch_id}"
            )

        if branch_persistent_id not in project.persistent_branches:
            raise ValidationError(
                f"Target {dependency.target_node_id} references {as_world.branch_id} "
                f"which is not a branch"
            )

        # Validate possible world exists in the branch
        current_version = project.dag.current_version_id
        persistent_branch = project.persistent_branches[branch_persistent_id]

        if current_version not in persistent_branch.versions:
            raise ValidationError(
                f"Target branch {as_world.branch_id} does not exist in current version"
            )

        branch = persistent_branch.versions[current_version]
        world_exists = any(as_world.world_id == w.id for w in branch.possible_worlds)

        if not world_exists:
            raise ValidationError(
                f"Target {dependency.target_node_id} references non-existent "
                f"possible world {as_world.world_id} in branch {as_world.branch_id}"
            )
    else:
        if as_task is not None:
            as_node_id: NodeId = as_task
        elif as_branch is not None:
            as_node_id = as_branch
        else:
            ValidationError(f"Forgot to add pattern for: {dependency.target_node_id}")
            raise AssertionError(
                "Forgot to add pattern for: {dependency.target_node_id}"
            )

        target_persistent_id = project.dag.node_map.get(as_node_id)
        if target_persistent_id is None:
            raise ValidationError(f"Target node {as_node_id} does not exist")

        # Verify type matches
        if as_task is not None:
            if target_persistent_id not in project.persistent_tasks:
                raise ValidationError(f"Node {as_node_id} is not a task")
        else:  # BRANCH
            if target_persistent_id not in project.persistent_branches:
                raise ValidationError(f"Node {as_node_id} is not a branch")

    # Validate endpoint compatibility
    # Tasks have START and END endpoints
    # Branches and possible worlds have OCCURRENCE endpoint

    # Source endpoint validation
    if source_is_task and dependency.source_endpoint == Endpoint.OCCURRENCE:
        raise EndpointError(
            f"Task {source_node_id} cannot use OCCURRENCE endpoint (only branches can)"
        )

    if source_is_branch and dependency.source_endpoint in (
        Endpoint.START,
        Endpoint.END,
    ):
        raise EndpointError(
            f"Branch {source_node_id} cannot use START/END endpoint (only tasks can)"
        )

    # Target endpoint validation
    if as_task is not None and dependency.target_endpoint == Endpoint.OCCURRENCE:
        raise EndpointError(
            f"Task {dependency.target_node_id} cannot use OCCURRENCE endpoint "
            f"(only branches/possible worlds can)"
        )

    if as_world is not None and dependency.target_endpoint != Endpoint.OCCURRENCE:
        raise EndpointError(
            f"Possible world {dependency.target_node_id} can only use OCCURRENCE "
            f"endpoint"
        )

    if as_branch is not None and dependency.target_endpoint in (
        Endpoint.START,
        Endpoint.END,
    ):
        raise EndpointError(
            f"Branch {dependency.target_node_id} cannot use START/END endpoint "
            f"(only tasks can)"
        )


def has_required_exclusion_dependency(
    project: Project,
    source_task_id: TaskId,
    excluded_task_id: TaskId,
) -> bool:
    """Check if the required dependency for an exclusion exists.

    According to the spec, if task N excludes the assignee of task M, there must be
    a dependency: N.start >= M.start. This ensures M's assignee is known before N
    starts in the simulation.

    Args:
        project: The project containing the tasks
        source_task_id: The task that has the exclusion (task N)
        excluded_task_id: The task whose assignee is excluded (task M)

    Returns:
        True if the required dependency exists, False otherwise
    """
    # Get source task
    source_node_id: NodeId = source_task_id
    source_persistent_id = project.dag.node_map.get(source_node_id)
    if source_persistent_id is None:
        return False

    if source_persistent_id not in project.persistent_tasks:
        return False

    persistent_task = project.persistent_tasks[source_persistent_id]
    current_version = project.dag.current_version_id
    if current_version not in persistent_task.versions:
        return False

    task = persistent_task.versions[current_version]

    # Check if the required dependency exists:
    # source_task.start >= excluded_task.start
    for dep in task.dependencies:
        if (
            dep.source_endpoint == Endpoint.START
            and dep.target_node_id == excluded_task_id
            and dep.target_endpoint == Endpoint.START
            and dep.constraint_type == ConstraintType.GREATER_EQUAL
        ):
            return True

    return False


def validate_excluded_assignee(
    project: Project,
    source_task_id: TaskId,
    excluded_task_id: TaskId,
) -> None:
    """Validate that an excluded assignee can be added.

    This checks that the required dependency (source.start >= excluded.start) exists.

    Args:
        project: The project containing the tasks
        source_task_id: The task that will have the exclusion
        excluded_task_id: The task whose assignee will be excluded

    Raises:
        WorkerConstraintError: If the required dependency doesn't exist
    """
    if not has_required_exclusion_dependency(project, source_task_id, excluded_task_id):
        raise WorkerConstraintError(
            f"Cannot exclude assignee of task {excluded_task_id}: "
            f"Missing required dependency. Add dependency "
            f"'{source_task_id}.start >= {excluded_task_id}.start' first."
        )


def get_required_exclusion_dependency(
    excluded_task_id: TaskId,
) -> Dependency:
    """Get the dependency required for an exclusion.

    Args:
        excluded_task_id: The task whose assignee will be excluded

    Returns:
        The dependency that must exist on the source task
    """
    return Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=excluded_task_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
