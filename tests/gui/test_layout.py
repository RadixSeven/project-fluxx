"""Tests for DAG layout algorithm."""

from fluxx.data.models import (
    ConstraintType,
    Dependency,
    Endpoint,
    Triangular,
)
from fluxx.gui.controller import ProjectController
from fluxx.gui.utils.layout import compute_dag_layout


def test_layout_empty_dag() -> None:
    """Test layout with empty DAG."""
    controller = ProjectController()
    project = controller.get_project()

    layout = compute_dag_layout(project)
    assert layout.node_positions == {}
    assert layout.possible_world_positions == {}


def test_layout_single_task() -> None:
    """Test layout with single task."""
    controller = ProjectController()

    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    project = controller.get_project()
    layout = compute_dag_layout(project)
    positions = layout.node_positions

    node_id = task_id
    assert node_id in positions
    # Horizontal layout: x increases with time
    assert positions[node_id].x() >= 0  # Should be at some x position


def test_layout_two_tasks_no_dependency() -> None:
    """Test layout with two independent tasks."""
    controller = ProjectController()

    task_id1 = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id2 = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    project = controller.get_project()
    layout = compute_dag_layout(project)
    positions = layout.node_positions

    node_id1 = task_id1
    node_id2 = task_id2

    assert node_id1 in positions
    assert node_id2 in positions
    # Both should be at the same x position (layer 0) since no dependencies
    assert positions[node_id1].x() == positions[node_id2].x()


def test_layout_two_tasks_with_dependency() -> None:
    """Test layout with two tasks connected by dependency."""
    controller = ProjectController()

    # Create two tasks
    task_id1 = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id2 = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency: Task 1.start >= Task 2.end (Task 1 starts after Task 2 ends)
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task_id2,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task_id1, dep)

    project = controller.get_project()
    layout = compute_dag_layout(project)
    positions = layout.node_positions

    node_id1 = task_id1
    node_id2 = task_id2

    assert node_id1 in positions
    assert node_id2 in positions

    # Task 1 starts after Task 2 ends, so Task 1 should be further right
    assert positions[node_id1].x() > positions[node_id2].x()


def test_layout_three_tasks_chain() -> None:
    """Test layout with three tasks in a chain."""
    controller = ProjectController()

    # Create three tasks
    task_id1 = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id2 = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id3 = controller.create_task(
        title="Task 3",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Chain: Task 1.start >= Task 2.end, Task 2.start >= Task 3.end
    # This creates a sequence: Task 3 -> Task 2 -> Task 1
    dep12 = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task_id2,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    dep23 = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task_id3,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    controller.add_dependency(task_id1, dep12)
    controller.add_dependency(task_id2, dep23)

    project = controller.get_project()
    layout = compute_dag_layout(project)
    positions = layout.node_positions

    node_id1 = task_id1
    node_id2 = task_id2
    node_id3 = task_id3

    assert node_id1 in positions
    assert node_id2 in positions
    assert node_id3 in positions

    # Check layer ordering (time flows left to right)
    assert positions[node_id1].x() > positions[node_id2].x()
    assert positions[node_id2].x() > positions[node_id3].x()


def test_layout_parent_child_tasks() -> None:
    """Test layout with parent and child tasks.

    This test verifies that the layout can handle parent-child relationships,
    which create valid cycles in the node-based graph but not in the endpoint-based
    dependency graph.
    """
    controller = ProjectController()

    # Create a parent task by converting a leaf
    parent_id = controller.create_task(
        title="Parent Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Convert to parent (creates child with dependencies)
    child_id = controller.convert_to_parent(parent_id, "Child Task")

    project = controller.get_project()
    layout = compute_dag_layout(project)
    positions = layout.node_positions

    parent_node_id = parent_id
    child_node_id = child_id

    # Both nodes should have positions
    assert parent_node_id in positions
    assert child_node_id in positions

    # Parent and child should not crash the layout
    # (they create cycles in node graph but not endpoint graph)
    # The specific positioning depends on implementation, but both should exist
    assert positions[parent_node_id] is not None
    assert positions[child_node_id] is not None
