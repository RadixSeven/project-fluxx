"""Tests for NodeItem graphics items."""

from PySide6.QtWidgets import QGraphicsItem

from fluxx.data.models import (
    Branch,
    BranchId,
    NodeId,
    PossibleWorld,
    PossibleWorldId,
    Task,
    TaskId,
    Triangular,
)
from fluxx.gui.widgets.dag_view.node_item import BranchNodeItem, NodeItem, TaskNodeItem


def test_node_item_initialization() -> None:
    """Test NodeItem initialization."""
    node_id = NodeId("task_1")
    title = "Test Task"

    node = NodeItem(node_id, title, width=200, height=80)

    assert node.node_id == node_id
    assert node.title == title
    assert node._width == 200
    assert node._height == 80
    assert node._is_hovered is False


def test_node_item_selectable() -> None:
    """Test that node item is selectable."""
    node = NodeItem(NodeId("task_1"), "Test")

    assert node.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable


def test_node_item_accepts_hover() -> None:
    """Test that node item accepts hover events."""
    node = NodeItem(NodeId("task_1"), "Test")

    assert node.acceptHoverEvents() is True


def test_node_item_hover_state_change() -> None:
    """Test hover state changes."""
    node = NodeItem(NodeId("task_1"), "Test")

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
    node = NodeItem(NodeId("task_1"), "Test Task")

    # Set normal state
    node._is_hovered = False
    node.setSelected(False)

    # Verify state
    assert node._is_hovered is False
    assert node.isSelected() is False


def test_node_item_hovered_state() -> None:
    """Test node in hovered state."""
    node = NodeItem(NodeId("task_1"), "Test Task")

    # Set hovered state
    node._is_hovered = True
    node.setSelected(False)

    # Verify state
    assert node._is_hovered is True
    assert node.isSelected() is False


def test_node_item_selected_state() -> None:
    """Test node in selected state."""
    node = NodeItem(NodeId("task_1"), "Test Task")

    # Set selected state
    node._is_hovered = False
    node.setSelected(True)

    # Verify state
    assert node._is_hovered is False
    assert node.isSelected() is True


def test_node_item_paint_none_painter() -> None:
    """Test paint with None painter does nothing."""
    from PySide6.QtWidgets import QStyleOptionGraphicsItem

    node = NodeItem(NodeId("task_1"), "Test")

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

    node = TaskNodeItem(NodeId(task.id), task)

    assert node.node_id == NodeId(task.id)
    assert node.title == task.title
    assert node.task == task


def test_task_node_item_colors() -> None:
    """Test TaskNodeItem has task-specific colors."""
    task = Task(
        id=TaskId("task_1"),
        title="Test Task",
        description="Description",
    )

    node = TaskNodeItem(NodeId(task.id), task)

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

    node = BranchNodeItem(NodeId(branch.id), branch)

    assert node.node_id == NodeId(branch.id)
    assert node.title == branch.title
    assert node.branch == branch


def test_branch_node_item_colors() -> None:
    """Test BranchNodeItem has branch-specific colors."""
    branch = Branch(
        id=BranchId("branch_1"),
        title="Test Branch",
        description="Description",
    )

    node = BranchNodeItem(NodeId(branch.id), branch)

    # Verify branch-specific colors are set (orange)
    assert node._base_color.red() == 255
    assert node._base_color.green() == 220
    assert node._base_color.blue() == 180
