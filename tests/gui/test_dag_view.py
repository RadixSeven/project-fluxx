"""Tests for DAG graphics view."""

from collections.abc import Generator

import pytest
from pytestqt.qtbot import QtBot

from fluxx.data.models import Triangular
from fluxx.gui.controller import ProjectController
from fluxx.gui.widgets.dag_view.dag_graphics_view import DAGGraphicsView


@pytest.fixture
def controller(qtbot: QtBot) -> Generator[ProjectController]:
    """Create a ProjectController for testing.

    Args:
        qtbot: QtBot fixture

    Yields:
        ProjectController instance
    """
    ctrl = ProjectController()
    yield ctrl


@pytest.fixture
def dag_view(qtbot: QtBot, controller: ProjectController) -> Generator[DAGGraphicsView]:
    """Create a DAGGraphicsView for testing.

    Args:
        qtbot: QtBot fixture
        controller: ProjectController fixture

    Yields:
        DAGGraphicsView instance
    """
    view = DAGGraphicsView(controller)
    qtbot.addWidget(view)
    yield view


def test_dag_view_initialization(dag_view: DAGGraphicsView) -> None:
    """Test that DAG view initializes correctly."""
    assert dag_view._scene is not None
    assert dag_view.controller is not None
    assert dag_view.node_items == {}


def test_dag_view_renders_empty_project(dag_view: DAGGraphicsView) -> None:
    """Test rendering an empty project."""
    # Initially empty
    assert len(dag_view.node_items) == 0
    assert dag_view._scene.items() == []


def test_dag_view_renders_single_task(
    dag_view: DAGGraphicsView, controller: ProjectController
) -> None:
    """Test rendering a project with one task."""
    # Create task
    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Should have one node item
    from fluxx.data.models import NodeId

    assert len(dag_view.node_items) == 1
    assert NodeId(task_id) in dag_view.node_items


def test_dag_view_renders_multiple_tasks(
    dag_view: DAGGraphicsView, controller: ProjectController
) -> None:
    """Test rendering a project with multiple tasks."""
    # Create tasks
    task_id1 = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id2 = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Should have two node items
    from fluxx.data.models import NodeId

    assert len(dag_view.node_items) == 2
    assert NodeId(task_id1) in dag_view.node_items
    assert NodeId(task_id2) in dag_view.node_items


def test_dag_view_updates_on_project_change(
    dag_view: DAGGraphicsView, controller: ProjectController
) -> None:
    """Test that DAG view updates when project changes."""
    # Initially empty
    assert len(dag_view.node_items) == 0

    # Create task
    controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Should have one node item
    assert len(dag_view.node_items) == 1

    # Create another task
    controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Should have two node items
    assert len(dag_view.node_items) == 2


def test_dag_view_selection(
    dag_view: DAGGraphicsView, controller: ProjectController
) -> None:
    """Test node selection in DAG view."""
    # Create task
    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    from fluxx.data.models import NodeId

    node_id = NodeId(task_id)

    # Initially not selected
    assert not dag_view.node_items[node_id].isSelected()

    # Select task
    controller.select_node(node_id)

    # Should be selected
    assert dag_view.node_items[node_id].isSelected()

    # Deselect
    controller.select_node(None)

    # Should not be selected
    assert not dag_view.node_items[node_id].isSelected()


def test_dag_view_renders_branch(
    dag_view: DAGGraphicsView, controller: ProjectController
) -> None:
    """Test rendering a project with a branch."""
    # Create branch
    branch_id = controller.create_branch(
        title="Branch 1",
        description="Test branch",
    )

    # Should have one node item
    from fluxx.data.models import NodeId

    assert len(dag_view.node_items) == 1
    assert NodeId(branch_id) in dag_view.node_items


def test_dag_view_renders_tasks_and_branches(
    dag_view: DAGGraphicsView, controller: ProjectController
) -> None:
    """Test rendering a project with tasks and branches."""
    # Create task and branch
    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Branch 1",
        description="Test branch",
    )

    # Should have two node items
    from fluxx.data.models import NodeId

    assert len(dag_view.node_items) == 2
    assert NodeId(task_id) in dag_view.node_items
    assert NodeId(branch_id) in dag_view.node_items


def test_dag_view_renders_dependencies(
    dag_view: DAGGraphicsView, controller: ProjectController
) -> None:
    """Test that dependencies are rendered as edges."""
    # Create two tasks
    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency: task2 depends on task1
    from fluxx.data.models import ConstraintType, Dependency, Endpoint, NodeId

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=NodeId(task1_id),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(NodeId(task2_id), dep)

    # Verify edge is created
    assert len(dag_view.edge_items) == 1

    # Verify edge connects the correct nodes
    edge = dag_view.edge_items[0]
    assert edge.source_id == NodeId(task2_id)
    assert edge.target_id == NodeId(task1_id)
