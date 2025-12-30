"""DAG layout algorithms for node positioning."""

from collections import defaultdict

import networkx as nx
from PySide6.QtCore import QPointF

from fluxx.data.models import NodeId, Project


def compute_dag_layout(project: Project) -> dict[NodeId, QPointF]:
    """Compute positions for all nodes in the DAG using hierarchical layout.

    Algorithm:
    1. Build directed graph from dependencies
    2. Topological sort to assign layers (y-coordinates)
    3. Within each layer, distribute nodes horizontally
    4. Return dict mapping node_id to QPointF position

    Args:
        project: Project instance

    Returns:
        Dictionary mapping NodeId to QPointF position in scene coordinates
    """
    # Handle empty DAG
    if not project.dag.node_map:
        return {}

    # Build networkx graph from dependencies
    graph: nx.DiGraph[NodeId] = nx.DiGraph()

    # Add all nodes
    for node_id in project.dag.node_map:
        graph.add_node(node_id)

    # Add edges from dependencies
    # Dependencies are stored on tasks and branches
    current_version = project.dag.current_version_id

    # Add task dependencies
    for persistent_id, persistent_task in project.persistent_tasks.items():
        if current_version not in persistent_task.versions:
            continue

        task = persistent_task.versions[current_version]
        source_node_id = None

        # Find the node_id for this persistent_id
        for node_id, pid in project.dag.node_map.items():
            if pid == persistent_id:
                source_node_id = node_id
                break

        if source_node_id is None:
            continue

        # Add edges for dependencies
        for dep in task.dependencies:
            # If this task has a dependency on another node,
            # the other node must complete first.
            # Edge goes from dependency target to this task (target -> source)
            graph.add_edge(dep.target_node_id, source_node_id)

    # Add branch dependencies
    for persistent_id, persistent_branch in project.persistent_branches.items():
        if current_version not in persistent_branch.versions:
            continue

        branch = persistent_branch.versions[current_version]
        source_node_id = None

        # Find the node_id for this persistent_id
        for node_id, pid in project.dag.node_map.items():
            if pid == persistent_id:
                source_node_id = node_id
                break

        if source_node_id is None:
            continue

        # Add edges for dependencies
        for dep in branch.dependencies:
            # If this branch has a dependency on another node,
            # the other node must complete first.
            # Edge goes from dependency target to this branch (target -> source)
            graph.add_edge(dep.target_node_id, source_node_id)

    # Compute layers using topological sort
    # Nodes with no incoming edges are at layer 0
    # Each node is at max(predecessor_layers) + 1
    layers: dict[NodeId, int] = {}

    try:
        # Try topological sort (works if DAG is acyclic)
        for node_id in nx.topological_sort(graph):
            predecessors = list(graph.predecessors(node_id))
            if not predecessors:
                layers[node_id] = 0
            else:
                layers[node_id] = max(layers[pred] for pred in predecessors) + 1
    except nx.NetworkXError:
        # Graph has cycles - fall back to simple layout
        # Assign all nodes to layer 0
        for node_id in graph.nodes():
            layers[node_id] = 0

    # Group nodes by layer
    nodes_by_layer: dict[int, list[NodeId]] = defaultdict(list)
    for node_id, layer in layers.items():
        nodes_by_layer[layer].append(node_id)

    # Compute positions
    positions: dict[NodeId, QPointF] = {}

    # Layout constants
    node_width = 200
    node_height = 80
    horizontal_spacing = 50
    vertical_spacing = 100

    for layer_num, node_ids in nodes_by_layer.items():
        # Y position based on layer
        y = layer_num * (node_height + vertical_spacing)

        # X positions: center the layer horizontally
        layer_width = (
            len(node_ids) * node_width + (len(node_ids) - 1) * horizontal_spacing
        )
        start_x = -layer_width / 2

        for i, node_id in enumerate(node_ids):
            x = start_x + i * (node_width + horizontal_spacing)
            positions[node_id] = QPointF(x, y)

    return positions
