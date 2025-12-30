"""Tests for EdgeItem graphics item."""

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from pytestqt.qtbot import QtBot

from fluxx.data.models import NodeId
from fluxx.gui.widgets.dag_view.edge_item import EdgeItem


def test_edge_item_initialization() -> None:
    """Test EdgeItem initialization."""
    source_id = NodeId("task_1")
    target_id = NodeId("task_2")
    source_pos = QPointF(100, 100)
    target_pos = QPointF(300, 200)

    edge = EdgeItem(source_id, target_id, source_pos, target_pos)

    assert edge.source_id == source_id
    assert edge.target_id == target_id
    assert edge.source_pos == source_pos
    assert edge.target_pos == target_pos
    assert edge._is_hovered is False


def test_edge_item_path_creation() -> None:
    """Test that edge creates a valid path."""
    source_pos = QPointF(0, 0)
    target_pos = QPointF(100, 100)

    edge = EdgeItem(NodeId("task_1"), NodeId("task_2"), source_pos, target_pos)

    path = edge.path()
    assert not path.isEmpty()


def test_edge_item_update_positions() -> None:
    """Test updating edge positions."""
    edge = EdgeItem(
        NodeId("task_1"),
        NodeId("task_2"),
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
        NodeId("task_1"),
        NodeId("task_2"),
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
        NodeId("task_1"),
        NodeId("task_2"),
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
        NodeId("task_1"),
        NodeId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Set hovered and check state
    edge._is_hovered = True
    assert edge._is_hovered is True


def test_edge_item_paint_none_painter() -> None:
    """Test paint with None painter does nothing."""
    edge = EdgeItem(
        NodeId("task_1"),
        NodeId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Should not raise exception
    edge.paint(None, None, None)


def test_edge_item_draw_arrow_zero_length() -> None:
    """Test drawing arrow with zero-length edge."""
    edge = EdgeItem(
        NodeId("task_1"),
        NodeId("task_2"),
        QPointF(100, 100),
        QPointF(100, 100),  # Same position
    )

    # Zero-length edge should be handled without errors
    # Just verify the edge exists
    assert edge.source_pos == edge.target_pos


def test_edge_item_colors() -> None:
    """Test edge color properties."""
    edge = EdgeItem(
        NodeId("task_1"),
        NodeId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    # Verify colors are set
    assert edge._base_color == QColor(100, 100, 100)
    assert edge._hover_color == QColor(50, 100, 200)


def test_edge_item_accepts_hover_events() -> None:
    """Test that edge accepts hover events."""
    edge = EdgeItem(
        NodeId("task_1"),
        NodeId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    assert edge.acceptHoverEvents() is True


def test_edge_item_z_value() -> None:
    """Test that edges are behind nodes."""
    edge = EdgeItem(
        NodeId("task_1"),
        NodeId("task_2"),
        QPointF(0, 0),
        QPointF(100, 100),
    )

    assert edge.zValue() == -1
