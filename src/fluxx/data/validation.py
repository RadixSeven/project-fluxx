"""DAG validation utilities."""

from collections import defaultdict

from fluxx.data.models import (
    DAGVersionId,
    Dependency,
    Endpoint,
    NodeId,
    Project,
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
    # Build adjacency list from dependencies using (node_id, endpoint) as graph nodes
    from fluxx.data.models import Endpoint

    graph: dict[tuple[NodeId, Endpoint], list[tuple[NodeId, Endpoint]]] = defaultdict(
        list
    )

    # Get all nodes in current version
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
                    # Dependency: source[source_endpoint] >= target[target_endpoint]
                    # Creates edge: target[target_endpoint] -> source[source_endpoint]
                    graph[(dep.target_node_id, dep.target_endpoint)].append(
                        (node_id, dep.source_endpoint)
                    )

        # Check if it's a branch
        elif persistent_id in project.persistent_branches:
            persistent_branch = project.persistent_branches[persistent_id]
            if version_id in persistent_branch.versions:
                branch = persistent_branch.versions[version_id]

                # Add implicit dependencies: occurrence_point -> each possible world
                for pw in branch.possible_worlds:
                    graph[(node_id, Endpoint.OCCURRENCE)].append(
                        (NodeId(pw.id), Endpoint.OCCURRENCE)
                    )

                # Add explicit dependencies from this branch
                for dep in branch.dependencies:
                    # Dependency: source[source_endpoint] >= target[target_endpoint]
                    # Creates edge: target[target_endpoint] -> source[source_endpoint]
                    graph[(dep.target_node_id, dep.target_endpoint)].append(
                        (node_id, dep.source_endpoint)
                    )

    # DFS-based cycle detection
    white, gray, black = 0, 1, 2
    color: dict[tuple[NodeId, Endpoint], int] = defaultdict(lambda: white)

    def dfs(node: tuple[NodeId, Endpoint], path: list[tuple[NodeId, Endpoint]]) -> None:
        if color[node] == gray:
            # Found a cycle
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            cycle_str = " -> ".join(
                f"{node_id}.{endpoint.value}" for node_id, endpoint in cycle
            )
            raise CycleError(f"Cycle detected in DAG: {cycle_str}")

        if color[node] == black:
            return

        color[node] = gray
        path.append(node)

        for neighbor in graph[node]:
            dfs(neighbor, path)

        path.pop()
        color[node] = black

    # Check all endpoint nodes
    for node_id in project.dag.node_map:
        # Check task endpoints
        if (node_id, Endpoint.START) in graph and color[
            (node_id, Endpoint.START)
        ] == white:
            dfs((node_id, Endpoint.START), [])
        if (node_id, Endpoint.END) in graph and color[(node_id, Endpoint.END)] == white:
            dfs((node_id, Endpoint.END), [])
        # Check branch endpoints
        if (node_id, Endpoint.OCCURRENCE) in graph and color[
            (node_id, Endpoint.OCCURRENCE)
        ] == white:
            dfs((node_id, Endpoint.OCCURRENCE), [])


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

        # If task has parent, verify parent exists and lists this as child
        if task.parent_id is not None:
            parent_persistent_id = project.dag.node_map.get(NodeId(task.parent_id))
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

        # Verify all children exist and reference this task as parent
        for child_id in task.children:
            child_persistent_id = project.dag.node_map.get(NodeId(child_id))
            if child_persistent_id is None:
                raise HierarchyError(
                    f"Task {node_id} references non-existent child {child_id}"
                )

            if child_persistent_id not in project.persistent_tasks:
                raise HierarchyError(f"Task {node_id} child {child_id} is not a task")

            child_persistent = project.persistent_tasks[child_persistent_id]
            if version_id not in child_persistent.versions:
                continue  # Skip children not in current version

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
            if NodeId(excluded_task_id) not in project.dag.node_map:
                raise WorkerConstraintError(
                    f"Task {node_id} references non-existent task {excluded_task_id} "
                    f"in excluded_worker_tasks"
                )


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

    # Check target node exists
    # Special handling for possible world references (format: "branch_id:world_id")
    target_str = str(dependency.target_node_id)
    target_is_possible_world = False

    if ":" in target_str:
        # Parse possible world reference
        branch_id_str, world_id_str = target_str.split(":", 1)
        branch_node_id = NodeId(branch_id_str)

        # Validate branch exists
        branch_persistent_id = project.dag.node_map.get(branch_node_id)
        if branch_persistent_id is None:
            raise ValidationError(
                f"Target node {dependency.target_node_id} references non-existent "
                f"branch {branch_id_str}"
            )

        if branch_persistent_id not in project.persistent_branches:
            raise ValidationError(
                f"Target node {dependency.target_node_id} references {branch_id_str} "
                f"which is not a branch"
            )

        # Validate possible world exists in branch
        current_version = project.dag.current_version_id
        persistent_branch = project.persistent_branches[branch_persistent_id]

        if current_version not in persistent_branch.versions:
            raise ValidationError(
                f"Target branch {branch_id_str} does not exist in current version"
            )

        branch = persistent_branch.versions[current_version]
        world_exists = any(pw.id == world_id_str for pw in branch.possible_worlds)

        if not world_exists:
            raise ValidationError(
                f"Target node {dependency.target_node_id} references non-existent "
                f"possible world {world_id_str} in branch {branch_id_str}"
            )

        target_is_possible_world = True
        target_is_task = False
    else:
        # Regular node reference
        target_persistent_id = project.dag.node_map.get(dependency.target_node_id)
        if target_persistent_id is None:
            raise ValidationError(
                f"Target node {dependency.target_node_id} does not exist"
            )

        # Determine target node type
        target_is_task = target_persistent_id in project.persistent_tasks

    # Determine source node type
    source_is_task = source_persistent_id in project.persistent_tasks

    # Validate endpoint compatibility
    # Tasks have START and END endpoints
    # Branches and possible worlds have OCCURRENCE endpoint

    # Source endpoint validation
    if source_is_task and dependency.source_endpoint == Endpoint.OCCURRENCE:
        raise EndpointError(
            f"Task {source_node_id} cannot use OCCURRENCE endpoint (only branches can)"
        )

    if not source_is_task and dependency.source_endpoint in (
        Endpoint.START,
        Endpoint.END,
    ):
        raise EndpointError(
            f"Branch {source_node_id} cannot use START/END endpoint (only tasks can)"
        )

    # Target endpoint validation
    if target_is_task and dependency.target_endpoint == Endpoint.OCCURRENCE:
        raise EndpointError(
            f"Task {dependency.target_node_id} cannot use OCCURRENCE endpoint "
            f"(only branches can)"
        )

    if target_is_possible_world and dependency.target_endpoint != Endpoint.OCCURRENCE:
        raise EndpointError(
            f"Possible world {dependency.target_node_id} can only use OCCURRENCE "
            f"endpoint"
        )

    if (
        not target_is_task
        and not target_is_possible_world
        and dependency.target_endpoint in (Endpoint.START, Endpoint.END)
    ):
        raise EndpointError(
            f"Branch {dependency.target_node_id} cannot use START/END endpoint "
            f"(only tasks can)"
        )
