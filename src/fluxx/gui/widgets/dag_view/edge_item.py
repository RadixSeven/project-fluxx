"""Edge item for rendering dependencies between nodes."""

from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsPathItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from fluxx.data.models import NodeId


class EdgeItem(QGraphicsPathItem):
    """Graphics item for rendering a dependency edge between two nodes.

    The edge is drawn as a curved line with an arrow pointing to the target.
    """

    def __init__(
        self,
        source_id: NodeId,
        target_id: NodeId,
        source_pos: QPointF,
        target_pos: QPointF,
    ) -> None:
        """Initialize edge item.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            source_pos: Source node center position
            target_pos: Target node center position
        """
        super().__init__()
        self.source_id = source_id
        self.target_id = target_id
        self.source_pos = source_pos
        self.target_pos = target_pos

        # Hover state
        self._is_hovered = False

        # Enable hover events
        self.setAcceptHoverEvents(True)

        # Set visual properties
        self._base_color = QColor(100, 100, 100)
        self._hover_color = QColor(50, 100, 200)  # Blue when hovered
        pen = QPen(self._base_color)
        pen.setWidth(2)
        self.setPen(pen)

        # Make edges appear behind nodes
        self.setZValue(-1)

        # Update the path
        self._update_path()

    def _update_path(self) -> None:
        """Update the edge path."""
        path = QPainterPath()

        # Start from source position
        path.moveTo(self.source_pos)

        # Calculate control points for a smooth curve
        dx = self.target_pos.x() - self.source_pos.x()

        # Use cubic Bezier curve for smooth edge
        control1 = QPointF(self.source_pos.x() + dx * 0.5, self.source_pos.y())
        control2 = QPointF(self.target_pos.x() - dx * 0.5, self.target_pos.y())

        path.cubicTo(control1, control2, self.target_pos)

        self.setPath(path)

    def update_positions(self, source_pos: QPointF, target_pos: QPointF) -> None:
        """Update edge positions when nodes move.

        Args:
            source_pos: New source node center position
            target_pos: New target node center position
        """
        self.source_pos = source_pos
        self.target_pos = target_pos
        self._update_path()

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the edge.

        Args:
            painter: Painter to use
            option: Style options
            widget: Widget being painted on
        """
        if painter is None:
            return

        # Update pen color based on hover state
        if self._is_hovered:
            pen = QPen(self._hover_color)
            pen.setWidth(3)
        else:
            pen = QPen(self._base_color)
            pen.setWidth(2)
        self.setPen(pen)

        # Draw the curved line
        super().paint(painter, option, widget)

        # Draw arrow at the end
        self._draw_arrow(painter)

    def _draw_arrow(self, painter: QPainter) -> None:
        """Draw an arrowhead at the target end.

        Args:
            painter: Painter to use
        """
        # Calculate arrow direction
        dx = self.target_pos.x() - self.source_pos.x()
        dy = self.target_pos.y() - self.source_pos.y()

        # Normalize
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return

        dx /= length
        dy /= length

        # Arrow size
        arrow_size = 10.0

        # Arrow tip position (slightly before target to avoid overlapping node)
        tip_offset = 30.0  # Half the node width
        tip_x = self.target_pos.x() - dx * tip_offset
        tip_y = self.target_pos.y() - dy * tip_offset

        # Calculate arrow wing points
        # Perpendicular vector
        perp_x = -dy
        perp_y = dx

        # Wing points
        wing1_x = tip_x - dx * arrow_size + perp_x * (arrow_size / 2)
        wing1_y = tip_y - dy * arrow_size + perp_y * (arrow_size / 2)

        wing2_x = tip_x - dx * arrow_size - perp_x * (arrow_size / 2)
        wing2_y = tip_y - dy * arrow_size - perp_y * (arrow_size / 2)

        # Draw filled arrow triangle
        arrow_path = QPainterPath()
        arrow_path.moveTo(tip_x, tip_y)
        arrow_path.lineTo(wing1_x, wing1_y)
        arrow_path.lineTo(wing2_x, wing2_y)
        arrow_path.closeSubpath()

        # Use hover color if hovered
        arrow_color = self._hover_color if self._is_hovered else self._base_color
        painter.fillPath(arrow_path, arrow_color)

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
