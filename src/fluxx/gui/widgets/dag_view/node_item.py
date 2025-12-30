"""Graphics items for rendering DAG nodes."""

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from fluxx.data.models import Branch, NodeId, Task


class NodeItem(QGraphicsRectItem):
    """Base class for DAG node items.

    Features:
    - Rounded rectangle rendering
    - Title text display
    - Hover highlighting
    - Selection highlighting
    - Click to select
    """

    def __init__(
        self,
        node_id: NodeId,
        title: str,
        width: float = 200,
        height: float = 80,
    ) -> None:
        """Initialize node item.

        Args:
            node_id: Node ID
            title: Node title to display
            width: Node width in pixels
            height: Node height in pixels
        """
        super().__init__(0, 0, width, height)
        self.node_id = node_id
        self.title = title
        self._width = width
        self._height = height

        # Make item selectable and movable by mouse
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        # Enable hover events
        self.setAcceptHoverEvents(True)

        # Style
        self._base_color = QColor(200, 200, 255)  # Light blue
        self._hover_color = QColor(220, 220, 255)  # Lighter blue
        self._selected_color = QColor(100, 150, 255)  # Bright blue
        self._border_color = QColor(100, 100, 200)

        self._is_hovered = False

    def paint(
        self,
        painter: QPainter | None,
        option: Any,
        widget: Any = None,
    ) -> None:
        """Paint the node.

        Args:
            painter: QPainter instance
            option: Style option (unused)
            widget: Widget being painted on (unused)
        """
        if painter is None:
            return

        # Determine colors based on state
        if self.isSelected():
            fill_color = self._selected_color
            border_width = 3.0
        elif self._is_hovered:
            fill_color = self._hover_color
            border_width = 2.0
        else:
            fill_color = self._base_color
            border_width = 2.0

        # Draw rounded rectangle
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(self._border_color, border_width))
        painter.drawRoundedRect(self.rect(), 10, 10)

        # Draw title text
        painter.setPen(QPen(QColor(0, 0, 0)))
        text_rect = self.rect().adjusted(10, 10, -10, -10)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            self.title,
        )

    def hoverEnterEvent(self, event: Any) -> None:  # noqa: N802
        """Handle hover enter.

        Args:
            event: Hover event
        """
        self._is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: Any) -> None:  # noqa: N802
        """Handle hover leave.

        Args:
            event: Hover event
        """
        self._is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)


class TaskNodeItem(NodeItem):
    """Graphics item for rendering a task node.

    Displays:
    - Task title
    - Duration distribution info (if leaf task)
    - Light blue background
    """

    def __init__(self, node_id: NodeId, task: Task) -> None:
        """Initialize task node item.

        Args:
            node_id: Node ID
            task: Task instance
        """
        super().__init__(node_id, task.title)
        self.task = task

        # Task-specific styling
        self._base_color = QColor(200, 220, 255)  # Light blue
        self._hover_color = QColor(220, 235, 255)  # Lighter blue
        self._selected_color = QColor(100, 150, 255)  # Bright blue


class BranchNodeItem(NodeItem):
    """Graphics item for rendering a branch node.

    Displays:
    - Branch title
    - Number of possible worlds
    - Light orange background
    """

    def __init__(self, node_id: NodeId, branch: Branch) -> None:
        """Initialize branch node item.

        Args:
            node_id: Node ID
            branch: Branch instance
        """
        super().__init__(node_id, branch.title)
        self.branch = branch

        # Branch-specific styling
        self._base_color = QColor(255, 220, 180)  # Light orange
        self._hover_color = QColor(255, 235, 200)  # Lighter orange
        self._selected_color = QColor(255, 180, 100)  # Bright orange
        self._border_color = QColor(200, 150, 100)
