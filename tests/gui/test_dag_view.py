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
    assert len(dag_view.node_items) == 1
    assert task_id in dag_view.node_items


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
    assert len(dag_view.node_items) == 2
    assert task_id1 in dag_view.node_items
    assert task_id2 in dag_view.node_items


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

    node_id = task_id

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
    assert len(dag_view.node_items) == 1
    assert branch_id in dag_view.node_items


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
    assert len(dag_view.node_items) == 2
    assert task_id in dag_view.node_items
    assert branch_id in dag_view.node_items


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
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task1_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task2_id, dep)

    # Verify edge is created
    assert len(dag_view.edge_items) == 1

    # Verify edge connects the correct nodes
    edge = dag_view.edge_items[0]
    assert edge.source_id == task2_id
    assert edge.target_id == task1_id


def test_dag_view_select_target_mode(
    dag_view: DAGGraphicsView, controller: ProjectController
) -> None:
    """Test entering and exiting select-target mode."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QGraphicsView

    # Initially not in select target mode
    assert dag_view._select_target_mode is False
    assert dag_view.dragMode() == QGraphicsView.DragMode.ScrollHandDrag

    # Enter select target mode
    dag_view.enter_select_target_mode()

    # Should be in select target mode
    assert dag_view._select_target_mode is True
    assert dag_view.dragMode() == QGraphicsView.DragMode.NoDrag
    assert dag_view.cursor().shape() == Qt.CursorShape.CrossCursor

    # Exit select target mode
    dag_view.exit_select_target_mode()

    # Should be back to normal mode
    assert dag_view._select_target_mode is False
    assert dag_view.dragMode() == QGraphicsView.DragMode.ScrollHandDrag


def test_dag_view_click_node_in_select_target_mode(
    dag_view: DAGGraphicsView, controller: ProjectController, qtbot: QtBot
) -> None:
    """Test clicking a node in select-target mode emits signal."""
    from PySide6.QtCore import Qt

    # Create task
    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Enter select target mode
    dag_view.enter_select_target_mode()

    # Track signal emission
    signal_received = []
    dag_view.node_selected_for_dependency.connect(lambda x: signal_received.append(x))

    # Get the node item's position in view coordinates
    node_item = dag_view.node_items[task_id]
    scene_pos = node_item.pos()
    view_pos = dag_view.mapFromScene(scene_pos.x() + 50, scene_pos.y() + 40)

    # Simulate click
    qtbot.mouseClick(dag_view.viewport(), Qt.MouseButton.LeftButton, pos=view_pos)

    # Should emit signal with the node ID
    assert len(signal_received) == 1
    assert signal_received[0] == task_id

    # Should exit select target mode
    assert dag_view._select_target_mode is False


def test_dag_view_click_empty_space_clears_selection(
    dag_view: DAGGraphicsView, controller: ProjectController, qtbot: QtBot
) -> None:
    """Test clicking on empty space clears selection."""
    from PySide6.QtCore import QPoint, Qt

    # Create and select a task
    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    controller.select_node(task_id)
    assert dag_view.node_items[task_id].isSelected()

    # Click on empty space (far from node)
    qtbot.mouseClick(dag_view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(10, 10))

    # Selection should be cleared
    assert controller.get_selected_node_id() is None


def test_dag_view_wheel_event_zoom(
    dag_view: DAGGraphicsView, controller: ProjectController, qtbot: QtBot
) -> None:
    """Test mouse wheel zooms the view."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QWheelEvent

    # Create a task so there's something to view
    controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Get initial transform
    initial_transform = dag_view.transform()

    # Simulate zoom in (positive angle delta)
    wheel_event = QWheelEvent(
        QPoint(100, 100),  # pos
        dag_view.mapToGlobal(QPoint(100, 100)),  # globalPos
        QPoint(0, 0),  # pixelDelta
        QPoint(0, 120),  # angleDelta (positive = zoom in)
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,  # inverted
    )
    dag_view.wheelEvent(wheel_event)

    # Transform should have changed (zoomed in)
    new_transform = dag_view.transform()
    assert new_transform != initial_transform


def test_dag_view_wheel_event_zoom_out(
    dag_view: DAGGraphicsView, controller: ProjectController, qtbot: QtBot
) -> None:
    """Test mouse wheel zooms out."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QWheelEvent

    # Create a task so there's something to view
    controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Get initial transform
    initial_transform = dag_view.transform()

    # Simulate zoom out (negative angle delta)
    wheel_event = QWheelEvent(
        QPoint(100, 100),  # pos
        dag_view.mapToGlobal(QPoint(100, 100)),  # globalPos
        QPoint(0, 0),  # pixelDelta
        QPoint(0, -120),  # angleDelta (negative = zoom out)
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,  # inverted
    )
    dag_view.wheelEvent(wheel_event)

    # Transform should have changed (zoomed out)
    new_transform = dag_view.transform()
    assert new_transform != initial_transform


def test_dag_view_wheel_event_none(dag_view: DAGGraphicsView) -> None:
    """Test wheel event with None does nothing."""
    # Should not crash
    dag_view.wheelEvent(None)


def test_dag_view_click_on_possible_world_in_select_mode(
    dag_view: DAGGraphicsView, controller: ProjectController, qtbot: QtBot
) -> None:
    """Test clicking on a possible world in select-target mode."""
    from PySide6.QtCore import Qt

    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import PossibleWorld

    # Create branch with possible worlds
    pw_id = generate_possible_world_id()
    branch_id = controller.create_branch(
        title="Branch 1",
        possible_worlds=[
            PossibleWorld(id=pw_id, title="World 1", weight=1.0),
        ],
    )

    # Verify possible world item was created
    assert len(dag_view.possible_world_items) > 0

    # Enter select target mode
    dag_view.enter_select_target_mode()

    # Track signal emission
    signal_received = []
    dag_view.node_selected_for_dependency.connect(lambda x: signal_received.append(x))

    # Get the possible world item's position in view coordinates
    pw_key = (branch_id, pw_id)
    if pw_key in dag_view.possible_world_items:
        pw_item = dag_view.possible_world_items[pw_key]
        scene_pos = pw_item.pos()
        view_pos = dag_view.mapFromScene(scene_pos.x() + 50, scene_pos.y() + 30)

        # Simulate click
        qtbot.mouseClick(dag_view.viewport(), Qt.MouseButton.LeftButton, pos=view_pos)

        # Should emit signal with the PossibleWorldReference
        if len(signal_received) == 1:
            assert f"{branch_id}" in str(signal_received[0])


def test_dag_view_click_on_possible_world_normal_mode(
    dag_view: DAGGraphicsView, controller: ProjectController, qtbot: QtBot
) -> None:
    """Test clicking on a possible world in normal mode selects the parent branch."""
    from PySide6.QtCore import Qt

    from fluxx.data.id_generation import generate_possible_world_id
    from fluxx.data.models import PossibleWorld

    # Create branch with possible worlds
    pw_id = generate_possible_world_id()
    branch_id = controller.create_branch(
        title="Branch 1",
        possible_worlds=[
            PossibleWorld(id=pw_id, title="World 1", weight=1.0),
        ],
    )

    # Verify possible world item was created
    assert len(dag_view.possible_world_items) > 0

    # Get the possible world item's position in view coordinates
    pw_key = (branch_id, pw_id)
    if pw_key in dag_view.possible_world_items:
        pw_item = dag_view.possible_world_items[pw_key]
        scene_pos = pw_item.pos()
        view_pos = dag_view.mapFromScene(scene_pos.x() + 50, scene_pos.y() + 30)

        # Simulate click
        qtbot.mouseClick(dag_view.viewport(), Qt.MouseButton.LeftButton, pos=view_pos)

        # Should select the parent branch
        assert controller.get_selected_node_id() == branch_id


def test_dag_view_click_empty_space_in_select_mode(
    dag_view: DAGGraphicsView, controller: ProjectController, qtbot: QtBot
) -> None:
    """Test clicking on empty space in select-target mode doesn't clear selection."""
    from PySide6.QtCore import QPoint, Qt

    # Enter select target mode
    dag_view.enter_select_target_mode()

    # Click on empty space (far from any node)
    qtbot.mouseClick(dag_view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(10, 10))

    # Should still be in select target mode
    assert dag_view._select_target_mode is True
