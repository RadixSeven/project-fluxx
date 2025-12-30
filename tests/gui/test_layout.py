"""Tests for DAG layout algorithm."""

from fluxx.data.models import (
    ConstraintType,
    Dependency,
    Endpoint,
    NodeId,
    Triangular,
)
from fluxx.gui.controller import ProjectController
from fluxx.gui.utils.layout import compute_dag_layout


def test_layout_empty_dag() -> None:
    """Test layout with empty DAG."""
    controller = ProjectController()
    project = controller.get_project()

    positions = compute_dag_layout(project)
    assert positions == {}


def test_layout_single_task() -> None:
    """Test layout with single task."""
    controller = ProjectController()

    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    project = controller.get_project()
    positions = compute_dag_layout(project)

    node_id = NodeId(task_id)
    assert node_id in positions
    assert positions[node_id].y() == 0  # First layer


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
    positions = compute_dag_layout(project)

    node_id1 = NodeId(task_id1)
    node_id2 = NodeId(task_id2)

    assert node_id1 in positions
    assert node_id2 in positions
    # Both should be at layer 0
    assert positions[node_id1].y() == 0
    assert positions[node_id2].y() == 0


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

    # Add dependency: Task 1 depends on Task 2
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task_id2),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(NodeId(task_id1), dep)

    project = controller.get_project()
    positions = compute_dag_layout(project)

    node_id1 = NodeId(task_id1)
    node_id2 = NodeId(task_id2)

    assert node_id1 in positions
    assert node_id2 in positions

    # Task 1 depends on Task 2, so Task 1 should be at a higher layer
    assert positions[node_id1].y() > positions[node_id2].y()


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

    # Task 1 -> Task 2 -> Task 3
    dep12 = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task_id2),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    dep23 = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task_id3),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    controller.add_dependency(NodeId(task_id1), dep12)
    controller.add_dependency(NodeId(task_id2), dep23)

    project = controller.get_project()
    positions = compute_dag_layout(project)

    node_id1 = NodeId(task_id1)
    node_id2 = NodeId(task_id2)
    node_id3 = NodeId(task_id3)

    assert node_id1 in positions
    assert node_id2 in positions
    assert node_id3 in positions

    # Check layer ordering
    assert positions[node_id1].y() > positions[node_id2].y()
    assert positions[node_id2].y() > positions[node_id3].y()
