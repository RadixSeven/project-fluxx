"""DAG layout algorithms for node positioning."""

from collections import defaultdict

import networkx as nx
from PySide6.QtCore import QPointF

from fluxx.data.models import Endpoint, NodeId, Project


def compute_dag_layout(project: Project) -> dict[NodeId, QPointF]:
    """Compute positions for all nodes in the DAG using hierarchical layout.

    Uses endpoint-based dependency graph to handle parent-child relationships correctly.
    Layout is horizontal (left-to-right) to match conventional time diagrams.

    Algorithm:
    1. Build endpoint-based directed graph from dependencies
    2. Topological sort on endpoints to assign layers (x-coordinates)
    3. Map endpoint layers back to node layers (max of endpoint layers)
    4. Within each layer, distribute nodes vertically
    5. Return dict mapping node_id to QPointF position

    Args:
        project: Project instance

    Returns:
        Dictionary mapping NodeId to QPointF position in scene coordinates
    """
    # Handle empty DAG
    if not project.dag.node_map:
        return {}

    # Build endpoint-based networkx graph
    # Each node (task/branch) has multiple endpoint nodes in the graph
    graph: nx.DiGraph[tuple[NodeId, Endpoint]] = nx.DiGraph()

    current_version = project.dag.current_version_id

    # Add task endpoints and dependencies
    for persistent_id, persistent_task in project.persistent_tasks.items():
        if current_version not in persistent_task.versions:
            continue

        task = persistent_task.versions[current_version]

        # Find the node_id for this persistent_id
        source_node_id = None
        for nid, pid in project.dag.node_map.items():
            if pid == persistent_id:
                source_node_id = nid
                break

        if source_node_id is None:
            continue

        # Add endpoint nodes
        graph.add_node((source_node_id, Endpoint.START))
        graph.add_node((source_node_id, Endpoint.END))

        # Add implicit dependency: task.start -> task.end
        graph.add_edge((source_node_id, Endpoint.START), (source_node_id, Endpoint.END))

        # Add explicit dependencies
        for dep in task.dependencies:
            # Dependency: source[source_endpoint] >= target[target_endpoint]
            # Creates edge: target[target_endpoint] -> source[source_endpoint]
            graph.add_edge(
                (dep.target_node_id, dep.target_endpoint),
                (source_node_id, dep.source_endpoint),
            )

    # Add branch endpoints and dependencies
    for persistent_id, persistent_branch in project.persistent_branches.items():
        if current_version not in persistent_branch.versions:
            continue

        branch = persistent_branch.versions[current_version]

        # Find the node_id for this persistent_id
        source_node_id = None
        for nid, pid in project.dag.node_map.items():
            if pid == persistent_id:
                source_node_id = nid
                break

        if source_node_id is None:
            continue

        # Add occurrence endpoint node
        graph.add_node((source_node_id, Endpoint.OCCURRENCE))

        # Add possible world endpoint nodes and implicit dependencies
        for pw in branch.possible_worlds:
            pw_node = (NodeId(pw.id), Endpoint.OCCURRENCE)
            graph.add_node(pw_node)
            # Implicit: occurrence -> possible_world
            graph.add_edge((source_node_id, Endpoint.OCCURRENCE), pw_node)

        # Add explicit dependencies
        for dep in branch.dependencies:
            # Dependency: source[source_endpoint] >= target[target_endpoint]
            # Creates edge: target[target_endpoint] -> source[source_endpoint]
            graph.add_edge(
                (dep.target_node_id, dep.target_endpoint),
                (source_node_id, dep.source_endpoint),
            )

    # Compute endpoint layers using topological sort
    endpoint_layers: dict[tuple[NodeId, Endpoint], int] = {}

    try:
        # Topological sort on endpoint graph
        for endpoint in nx.topological_sort(graph):
            predecessors = list(graph.predecessors(endpoint))
            if not predecessors:
                endpoint_layers[endpoint] = 0
            else:
                endpoint_layers[endpoint] = (
                    max(endpoint_layers[pred] for pred in predecessors) + 1
                )
    except (nx.NetworkXError, nx.NetworkXUnfeasible):
        # Graph has cycles - fall back to simple layout
        for endpoint in graph.nodes():
            endpoint_layers[endpoint] = 0

    # Map node layers: position each node based on its START endpoint layer
    # (for tasks) or OCCURRENCE endpoint layer (for branches)
    node_layers: dict[NodeId, int] = {}
    for endpoint_tuple, layer in endpoint_layers.items():
        node_id: NodeId = endpoint_tuple[0]
        endpoint_type: Endpoint = endpoint_tuple[1]
        # Position tasks at their START layer, branches at their OCCURRENCE layer
        if endpoint_type == Endpoint.START or endpoint_type == Endpoint.OCCURRENCE:
            if node_id not in node_layers:
                node_layers[node_id] = layer
            else:
                # If we've seen this node before (shouldn't happen for start/occurrence)
                # take the max
                node_layers[node_id] = max(node_layers[node_id], layer)

    # Group nodes by layer
    nodes_by_layer: dict[int, list[NodeId]] = defaultdict(list)
    for node_id, layer in node_layers.items():
        # Only include nodes that are in the current DAG
        if node_id in project.dag.node_map:
            nodes_by_layer[layer].append(node_id)

    # Compute positions (horizontal layout: x increases with layer)
    positions: dict[NodeId, QPointF] = {}

    # Layout constants
    node_width = 200
    node_height = 80
    horizontal_spacing = 150  # Space between layers (horizontal)
    vertical_spacing = 50  # Space between nodes in same layer (vertical)

    for layer_num, node_ids in nodes_by_layer.items():
        # X position based on layer (time flows left to right)
        x = layer_num * (node_width + horizontal_spacing)

        # Y positions: center the layer vertically
        layer_height = (
            len(node_ids) * node_height + (len(node_ids) - 1) * vertical_spacing
        )
        start_y = -layer_height / 2

        for i, node_id in enumerate(node_ids):
            y = start_y + i * (node_height + vertical_spacing)
            positions[node_id] = QPointF(x, y)

    return positions
