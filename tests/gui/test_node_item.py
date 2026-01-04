"""Tests for NodeItem graphics items."""

from PySide6.QtWidgets import QGraphicsItem
from pytestqt.qtbot import QtBot

from fluxx.data.models import (
    Branch,
    BranchId,
    PossibleWorld,
    PossibleWorldId,
    Task,
    TaskId,
    Triangular,
)
from fluxx.gui.widgets.dag_view.node_item import (
    BranchNodeItem,
    NodeItem,
    PossibleWorldItem,
    TaskNodeItem,
)


def test_node_item_initialization() -> None:
    """Test NodeItem initialization."""
    node_id = TaskId("task_1")
    title = "Test Task"

    node = NodeItem(node_id, title, width=200, height=80)

    assert node.node_id == node_id
    assert node.title == title
    assert node._width == 200
    assert node._height == 80
    assert node._is_hovered is False


def test_node_item_selectable() -> None:
    """Test that node item is selectable."""
    node = NodeItem(TaskId("task_1"), "Test")

    assert node.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable


def test_node_item_accepts_hover() -> None:
    """Test that node item accepts hover events."""
    node = NodeItem(TaskId("task_1"), "Test")

    assert node.acceptHoverEvents() is True


def test_node_item_hover_state_change() -> None:
    """Test hover state changes."""
    node = NodeItem(TaskId("task_1"), "Test")

    # Initially not hovered
    assert node._is_hovered is False

    # Set hover state
    node._is_hovered = True
    assert node._is_hovered is True

    # Unset hover state
    node._is_hovered = False
    assert node._is_hovered is False


def test_node_item_normal_state() -> None:
    """Test node in normal state."""
    node = NodeItem(TaskId("task_1"), "Test Task")

    # Set normal state
    node._is_hovered = False
    node.setSelected(False)

    # Verify state
    assert node._is_hovered is False
    assert node.isSelected() is False


def test_node_item_hovered_state() -> None:
    """Test node in hovered state."""
    node = NodeItem(TaskId("task_1"), "Test Task")

    # Set hovered state
    node._is_hovered = True
    node.setSelected(False)

    # Verify state
    assert node._is_hovered is True
    assert node.isSelected() is False


def test_node_item_selected_state() -> None:
    """Test node in selected state."""
    node = NodeItem(TaskId("task_1"), "Test Task")

    # Set selected state
    node._is_hovered = False
    node.setSelected(True)

    # Verify state
    assert node._is_hovered is False
    assert node.isSelected() is True


def test_node_item_paint_none_painter() -> None:
    """Test paint with None painter does nothing."""
    from PySide6.QtWidgets import QStyleOptionGraphicsItem

    node = NodeItem(TaskId("task_1"), "Test")

    # Should not raise exception when painter is None
    option = QStyleOptionGraphicsItem()
    node.paint(None, option, None)


def test_task_node_item_initialization() -> None:
    """Test TaskNodeItem initialization."""
    task = Task(
        id=TaskId("task_1"),
        title="Test Task",
        description="Description",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    node = TaskNodeItem(task.id, task)

    assert node.node_id == task.id
    assert node.title == task.title
    assert node.task == task


def test_task_node_item_colors() -> None:
    """Test TaskNodeItem has task-specific colors."""
    task = Task(
        id=TaskId("task_1"),
        title="Test Task",
        description="Description",
    )

    node = TaskNodeItem(task.id, task)

    # Verify task-specific colors are set
    assert node._base_color.red() == 200
    assert node._base_color.green() == 220
    assert node._base_color.blue() == 255


def test_branch_node_item_initialization() -> None:
    """Test BranchNodeItem initialization."""
    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
        possible_worlds=[
            PossibleWorld(
                id=PossibleWorldId("pw_1"),
                title="World 1",
                description="First world",
            ),
        ],
    )

    node = BranchNodeItem(branch.id, branch)

    assert node.node_id == branch.id
    assert node.title == branch.title
    assert node.branch == branch


def test_branch_node_item_colors() -> None:
    """Test BranchNodeItem has branch-specific colors."""
    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )

    node = BranchNodeItem(branch.id, branch)

    # Verify branch-specific colors are set (orange) - updated for circle rendering
    assert node._base_color.red() == 255
    assert node._base_color.green() == 200
    assert node._base_color.blue() == 150


def test_node_item_paint_via_scene_normal(qtbot: QtBot) -> None:
    """Test NodeItem paint method in normal state via scene rendering."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    scene = QGraphicsScene()
    node = NodeItem(TaskId("task_1"), "Test Task")
    node._is_hovered = False
    node.setSelected(False)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(300, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()


def test_node_item_paint_via_scene_hovered(qtbot: QtBot) -> None:
    """Test NodeItem paint method in hovered state via scene rendering."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    scene = QGraphicsScene()
    node = NodeItem(TaskId("task_1"), "Test Task")
    node._is_hovered = True
    node.setSelected(False)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(300, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()


def test_node_item_paint_via_scene_selected(qtbot: QtBot) -> None:
    """Test NodeItem paint method in selected state via scene rendering."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    scene = QGraphicsScene()
    node = NodeItem(TaskId("task_1"), "Test Task")
    node._is_hovered = False
    node.setSelected(True)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(300, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()


def test_node_item_hover_enter_event() -> None:
    """Test NodeItem hoverEnterEvent updates state."""
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QGraphicsSceneHoverEvent

    node = NodeItem(TaskId("task_1"), "Test Task")
    assert node._is_hovered is False

    # Create hover event
    event = QGraphicsSceneHoverEvent(
        QGraphicsSceneHoverEvent.Type.GraphicsSceneHoverEnter
    )
    event.setPos(QPointF(10, 10))

    node.hoverEnterEvent(event)

    assert node._is_hovered is True


def test_node_item_hover_leave_event() -> None:
    """Test NodeItem hoverLeaveEvent updates state."""
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QGraphicsSceneHoverEvent

    node = NodeItem(TaskId("task_1"), "Test Task")
    node._is_hovered = True

    # Create hover leave event
    event = QGraphicsSceneHoverEvent(
        QGraphicsSceneHoverEvent.Type.GraphicsSceneHoverLeave
    )
    event.setPos(QPointF(10, 10))

    node.hoverLeaveEvent(event)

    assert node._is_hovered is False


def test_branch_node_item_paint_none_painter() -> None:
    """Test BranchNodeItem paint with None painter does nothing."""
    from PySide6.QtWidgets import QStyleOptionGraphicsItem

    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )

    node = BranchNodeItem(branch.id, branch)

    # Should not raise exception when painter is None
    option = QStyleOptionGraphicsItem()
    node.paint(None, option, None)


def test_branch_node_item_paint_via_scene_normal(qtbot: QtBot) -> None:
    """Test BranchNodeItem paint method in normal state via scene rendering."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )

    scene = QGraphicsScene()
    node = BranchNodeItem(branch.id, branch)
    node._is_hovered = False
    node.setSelected(False)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(100, 100, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()


def test_branch_node_item_paint_via_scene_hovered(qtbot: QtBot) -> None:
    """Test BranchNodeItem paint method in hovered state via scene rendering."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )

    scene = QGraphicsScene()
    node = BranchNodeItem(branch.id, branch)
    node._is_hovered = True
    node.setSelected(False)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(100, 100, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()


def test_branch_node_item_paint_via_scene_selected(qtbot: QtBot) -> None:
    """Test BranchNodeItem paint method in selected state via scene rendering."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )

    scene = QGraphicsScene()
    node = BranchNodeItem(branch.id, branch)
    node._is_hovered = False
    node.setSelected(True)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(100, 100, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()


def test_branch_node_item_hover_enter_event() -> None:
    """Test BranchNodeItem hoverEnterEvent updates state."""
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QGraphicsSceneHoverEvent

    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )

    node = BranchNodeItem(branch.id, branch)
    assert node._is_hovered is False

    # Create hover event
    event = QGraphicsSceneHoverEvent(
        QGraphicsSceneHoverEvent.Type.GraphicsSceneHoverEnter
    )
    event.setPos(QPointF(5, 5))

    node.hoverEnterEvent(event)

    assert node._is_hovered is True


def test_branch_node_item_hover_leave_event() -> None:
    """Test BranchNodeItem hoverLeaveEvent updates state."""
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QGraphicsSceneHoverEvent

    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )

    node = BranchNodeItem(branch.id, branch)
    node._is_hovered = True

    # Create hover leave event
    event = QGraphicsSceneHoverEvent(
        QGraphicsSceneHoverEvent.Type.GraphicsSceneHoverLeave
    )
    event.setPos(QPointF(5, 5))

    node.hoverLeaveEvent(event)

    assert node._is_hovered is False


def test_branch_node_item_selectable() -> None:
    """Test that BranchNodeItem is selectable."""
    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )

    node = BranchNodeItem(branch.id, branch)

    assert node.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable


def test_branch_node_item_accepts_hover() -> None:
    """Test that BranchNodeItem accepts hover events."""
    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )

    node = BranchNodeItem(branch.id, branch)

    assert node.acceptHoverEvents() is True


def test_possible_world_item_initialization() -> None:
    """Test PossibleWorldItem initialization."""
    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )
    possible_world = PossibleWorld(
        id=PossibleWorldId("pw_1"),
        title="World 1",
        description="First world",
    )

    node = PossibleWorldItem(branch.id, branch, possible_world)

    assert node.node_id == branch.id
    assert node.branch == branch
    assert node.possible_world == possible_world
    assert node.title == "World 1"


def test_possible_world_item_colors() -> None:
    """Test PossibleWorldItem has specific colors."""
    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )
    possible_world = PossibleWorld(
        id=PossibleWorldId("pw_1"),
        title="World 1",
        description="First world",
    )

    node = PossibleWorldItem(branch.id, branch, possible_world)

    # Verify green colors
    assert node._base_color.red() == 200
    assert node._base_color.green() == 255
    assert node._base_color.blue() == 200


def test_task_node_item_completion_status_not_started(qtbot: QtBot) -> None:
    """Test TaskNodeItem rendering for not started task."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    from fluxx.data.models import NotStartedCompletion

    task = Task(
        id=TaskId("task_1"),
        title="Test Task",
        description="Description",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=NotStartedCompletion(),
    )

    scene = QGraphicsScene()
    node = TaskNodeItem(task.id, task)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(300, 150, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()

    # Verify default blue color is used
    assert node._base_color.red() == 200
    assert node._base_color.green() == 220
    assert node._base_color.blue() == 255


def test_task_node_item_completion_status_started(qtbot: QtBot) -> None:
    """Test TaskNodeItem rendering for started task has yellow border color."""
    from datetime import UTC, datetime

    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    from fluxx.data.models import StartedCompletion, WorkerId

    task = Task(
        id=TaskId("task_1"),
        title="Test Task",
        description="Description",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=StartedCompletion(
            assignee=WorkerId("worker_1"),
            start_time=datetime.now(UTC),
            hours_logged=1.0,
        ),
    )

    scene = QGraphicsScene()
    node = TaskNodeItem(task.id, task)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(300, 150, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()

    # Verify started border color exists (yellow/gold)
    assert node._started_border_color.red() == 255
    assert node._started_border_color.green() == 200
    assert node._started_border_color.blue() == 0


def test_task_node_item_completion_status_done(qtbot: QtBot) -> None:
    """Test TaskNodeItem rendering for done task has green background."""
    from datetime import UTC, datetime, timedelta

    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    from fluxx.data.models import DoneCompletion, WorkerId

    start_time = datetime.now(UTC)
    task = Task(
        id=TaskId("task_1"),
        title="Test Task",
        description="Description",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        completion=DoneCompletion(
            assignee=WorkerId("worker_1"),
            start_time=start_time,
            hours_logged=2.0,
            end_time=start_time + timedelta(hours=2),
        ),
    )

    scene = QGraphicsScene()
    node = TaskNodeItem(task.id, task)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(300, 150, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()

    # Verify done color exists (light green)
    assert node._done_color.red() == 180
    assert node._done_color.green() == 240
    assert node._done_color.blue() == 180


def test_branch_node_item_resolved_state(qtbot: QtBot) -> None:
    """Test BranchNodeItem rendering when branch is resolved."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw_1"), title="World 1"),
        ],
        chosen_world_id=PossibleWorldId("pw_1"),
    )

    scene = QGraphicsScene()
    node = BranchNodeItem(branch.id, branch)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(100, 100, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()

    # Verify resolved colors exist (light green)
    assert node._resolved_color.red() == 150
    assert node._resolved_color.green() == 220
    assert node._resolved_color.blue() == 150


def test_possible_world_item_chosen_state(qtbot: QtBot) -> None:
    """Test PossibleWorldItem rendering when this world is chosen."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    pw_id = PossibleWorldId("pw_1")
    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
        possible_worlds=[
            PossibleWorld(id=pw_id, title="World 1"),
        ],
        chosen_world_id=pw_id,  # This world is chosen
    )
    possible_world = branch.possible_worlds[0]

    scene = QGraphicsScene()
    node = PossibleWorldItem(branch.id, branch, possible_world)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(300, 100, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()

    # Verify chosen colors exist (bright green)
    assert node._chosen_color.red() == 100
    assert node._chosen_color.green() == 220
    assert node._chosen_color.blue() == 100


def test_possible_world_item_unchosen_state(qtbot: QtBot) -> None:
    """Test PossibleWorldItem rendering when another world is chosen."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    pw1_id = PossibleWorldId("pw_1")
    pw2_id = PossibleWorldId("pw_2")
    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
        possible_worlds=[
            PossibleWorld(id=pw1_id, title="World 1"),
            PossibleWorld(id=pw2_id, title="World 2"),
        ],
        chosen_world_id=pw2_id,  # World 2 is chosen, not World 1
    )
    possible_world = branch.possible_worlds[0]  # World 1 (unchosen)

    scene = QGraphicsScene()
    node = PossibleWorldItem(branch.id, branch, possible_world)
    scene.addItem(node)

    # Render scene to image (exercises paint code path)
    image = QImage(300, 100, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()

    # Verify unchosen colors exist (gray)
    assert node._unchosen_color.red() == 220
    assert node._unchosen_color.green() == 220
    assert node._unchosen_color.blue() == 220


def test_possible_world_item_paint_none_painter() -> None:
    """Test PossibleWorldItem paint with None painter does nothing."""
    from PySide6.QtWidgets import QStyleOptionGraphicsItem

    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )
    possible_world = PossibleWorld(
        id=PossibleWorldId("pw_1"),
        title="World 1",
        description="First world",
    )

    node = PossibleWorldItem(branch.id, branch, possible_world)

    # Should not raise exception when painter is None
    option = QStyleOptionGraphicsItem()
    node.paint(None, option, None)
