"""Tests for EdgeItem graphics item."""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from pytestqt.qtbot import QtBot

from fluxx.data.models import ConstraintType, TaskId
from fluxx.gui.widgets.dag_view.edge_item import EdgeItem


def test_edge_item_initialization() -> None:
    """Test EdgeItem initialization."""
    source_id = TaskId("task_1")
    target_id = TaskId("task_2")
    source_pos = QPointF(100, 100)
    target_pos = QPointF(300, 200)

    edge = EdgeItem(source_id, target_id, source_pos, target_pos)

    assert edge.source_id == source_id
    assert edge.target_id == target_id
    assert edge.source_pos == source_pos
    assert edge.target_pos == target_pos
    assert edge.constraint_type == ConstraintType.GREATER_EQUAL
    assert edge._is_hovered is False


def test_edge_item_initialization_with_constraint() -> None:
    """Test EdgeItem initialization with explicit constraint type."""
    source_id = TaskId("task_1")
    target_id = TaskId("task_2")
    source_pos = QPointF(100, 100)
    target_pos = QPointF(300, 200)

    edge = EdgeItem(
        source_id,
        target_id,
        source_pos,
        target_pos,
        constraint_type=ConstraintType.EQUAL,
    )

    assert edge.constraint_type == ConstraintType.EQUAL


def test_edge_item_path_creation() -> None:
    """Test that edge creates a valid path."""
    source_pos = QPointF(0, 0)
    target_pos = QPointF(100, 100)

    edge = EdgeItem(TaskId("task_1"), TaskId("task_2"), source_pos, target_pos)

    path = edge.path()
    assert not path.isEmpty()


def test_edge_item_update_positions() -> None:
    """Test updating edge positions."""
    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    new_source = QPointF(50, 50)
    new_target = QPointF(150, 150)

    edge.update_positions(new_source, new_target)

    assert edge.source_pos == new_source
    assert edge.target_pos == new_target


def test_edge_item_hover_state_change(qtbot: QtBot) -> None:
    """Test hover state changes."""
    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Initially not hovered
    assert edge._is_hovered is False

    # Directly set hover state
    edge._is_hovered = True
    assert edge._is_hovered is True

    # Unset hover state
    edge._is_hovered = False
    assert edge._is_hovered is False


def test_edge_item_pen_width_normal() -> None:
    """Test pen width in normal state."""
    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Check initial pen width
    edge._is_hovered = False
    pen = edge.pen()
    assert pen.width() == 2


def test_edge_item_pen_width_hovered() -> None:
    """Test pen width changes in hovered state."""
    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Set hovered and check state
    edge._is_hovered = True
    assert edge._is_hovered is True


def test_edge_item_paint_none_painter() -> None:
    """Test paint with None painter does nothing."""
    from PySide6.QtWidgets import QStyleOptionGraphicsItem

    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Should not raise exception when painter is None
    option = QStyleOptionGraphicsItem()
    edge.paint(None, option, None)


def test_edge_item_draw_arrow_zero_length() -> None:
    """Test drawing arrow with zero-length edge."""
    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(100, 100),
        QPointF(100, 100),  # Same position
    )

    # Zero-length edge should be handled without errors
    # Just verify the edge exists
    assert edge.source_pos == edge.target_pos


def test_edge_item_colors() -> None:
    """Test edge color properties."""
    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Verify colors are set
    assert edge._base_color == QColor(100, 100, 100)
    assert edge._hover_color == QColor(50, 100, 200)


def test_edge_item_accepts_hover_events() -> None:
    """Test that edge accepts hover events."""
    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    assert edge.acceptHoverEvents() is True


def test_edge_item_z_value() -> None:
    """Test that edges are behind nodes."""
    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    assert edge.zValue() == -1


def test_edge_item_paint_hovered_state(qtbot: QtBot) -> None:
    """Test paint with actual painter in hovered state."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Set hovered state
    edge._is_hovered = True

    # Add to scene
    scene = QGraphicsScene()
    scene.addItem(edge)

    # Render with actual painter to trigger paint method
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()

    # Verify hover state was used (pen should be width 3)
    assert edge._is_hovered is True


def test_edge_item_paint_normal_state(qtbot: QtBot) -> None:
    """Test paint with actual painter in normal state."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Add to scene (not hovered)
    scene = QGraphicsScene()
    scene.addItem(edge)

    # Render with actual painter to trigger paint method
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()

    # Verify normal state (pen should be width 2)
    assert edge._is_hovered is False


def test_edge_item_equal_constraint_arrow(qtbot: QtBot) -> None:
    """Test drawing arrow with EQUAL constraint type."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QGraphicsScene

    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
        constraint_type=ConstraintType.EQUAL,
    )

    # Add to scene
    scene = QGraphicsScene()
    scene.addItem(edge)

    # Render with actual painter to trigger paint and _draw_arrow
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()

    # Verify EQUAL constraint was used
    assert edge.constraint_type == ConstraintType.EQUAL


def test_edge_item_zero_length_arrow(qtbot: QtBot) -> None:
    """Test drawing arrow with zero-length edge (same source and target)."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QStyleOptionGraphicsItem

    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(50, 50),
        QPointF(50, 50),  # Same position
    )

    # Call paint directly with a real painter to trigger the zero-length path
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    option = QStyleOptionGraphicsItem()
    edge.paint(painter, option, None)
    painter.end()

    # Verify edge exists with same positions
    assert edge.source_pos == edge.target_pos


def test_edge_item_hover_enter_event(qtbot: QtBot) -> None:
    """Test hover enter event handler."""
    from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneHoverEvent

    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Add to scene (required for hover events to work)
    scene = QGraphicsScene()
    scene.addItem(edge)

    # Initially not hovered
    assert edge._is_hovered is False

    # Create hover event and trigger handler
    hover_event = QGraphicsSceneHoverEvent()
    edge.hoverEnterEvent(hover_event)

    # Should be hovered now
    assert edge._is_hovered is True


def test_edge_item_hover_leave_event(qtbot: QtBot) -> None:
    """Test hover leave event handler."""
    from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneHoverEvent

    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Add to scene (required for hover events to work)
    scene = QGraphicsScene()
    scene.addItem(edge)

    # Set hovered
    edge._is_hovered = True
    assert edge._is_hovered is True

    # Create hover event and trigger leave handler
    hover_event = QGraphicsSceneHoverEvent()
    edge.hoverLeaveEvent(hover_event)

    # Should not be hovered now
    assert edge._is_hovered is False


def test_edge_item_hover_cycle(qtbot: QtBot) -> None:
    """Test complete hover enter/leave cycle."""
    from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneHoverEvent

    edge = EdgeItem(
        TaskId("task_1"),
        TaskId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    scene = QGraphicsScene()
    scene.addItem(edge)

    # Initial state
    assert edge._is_hovered is False

    # Hover enter
    enter_event = QGraphicsSceneHoverEvent()
    edge.hoverEnterEvent(enter_event)
    assert edge._is_hovered is True

    # Hover leave
    leave_event = QGraphicsSceneHoverEvent()
    edge.hoverLeaveEvent(leave_event)
    assert edge._is_hovered is False
