"""Graphics items for rendering DAG nodes."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSceneHoverEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from fluxx.data.models import (
    Branch,
    DoneCompletion,
    NodeId,
    PossibleWorld,
    StartedCompletion,
    Task,
)


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
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the node.

        Args:
            painter: QPainter instance
            option: Style option
            widget: Widget being painted on
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

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: N802
        """Handle hover enter.

        Args:
            event: Hover event
        """
        self._is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: N802
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
    - Completion status indicator (border color and icon)
    """

    def __init__(self, node_id: NodeId, task: Task) -> None:
        """Initialize task node item.

        Args:
            node_id: Node ID
            task: Task instance
        """
        super().__init__(node_id, task.title)
        self.task = task

        # Task-specific styling (defaults for not started)
        self._base_color = QColor(200, 220, 255)  # Light blue
        self._hover_color = QColor(220, 235, 255)  # Lighter blue
        self._selected_color = QColor(100, 150, 255)  # Bright blue

        # Completion status colors
        self._started_border_color = QColor(255, 200, 0)  # Yellow/gold
        self._done_color = QColor(180, 240, 180)  # Light green
        self._done_border_color = QColor(80, 180, 80)  # Green

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the task node with completion status indicator.

        Args:
            painter: QPainter instance
            option: Style option
            widget: Widget being painted on
        """
        if painter is None:
            return

        completion = self.task.completion
        is_done = isinstance(completion, DoneCompletion)
        is_started = isinstance(completion, StartedCompletion)

        # Determine colors based on state
        if self.isSelected():
            fill_color = self._selected_color
            border_width = 3.0
            border_color = self._border_color
        elif self._is_hovered:
            fill_color = self._hover_color
            border_width = 2.0
            border_color = self._border_color
        else:
            if is_done:
                fill_color = self._done_color
                border_color = self._done_border_color
            else:
                fill_color = self._base_color
                border_color = self._border_color
            border_width = 2.0

        # Started tasks get a yellow/gold border
        if is_started and not self.isSelected():
            border_color = self._started_border_color
            border_width = 3.0

        # Draw rounded rectangle
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(border_color, border_width))
        painter.drawRoundedRect(self.rect(), 10, 10)

        # Draw title text
        painter.setPen(QPen(QColor(0, 0, 0)))
        text_rect = self.rect().adjusted(10, 10, -10, -10)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            self.title,
        )

        # Draw checkmark for completed tasks
        if is_done:
            self._draw_checkmark(painter)

    def _draw_checkmark(self, painter: QPainter) -> None:
        """Draw a checkmark in the top-right corner of the node.

        Args:
            painter: QPainter instance
        """
        # Position checkmark in top-right corner
        rect = self.rect()
        check_size = 16
        x = rect.right() - check_size - 8
        y = rect.top() + 8

        # Draw a green checkmark
        painter.setPen(QPen(QColor(40, 160, 40), 3.0))
        # Draw the checkmark path: short leg then long leg
        painter.drawLine(
            int(x + 2),
            int(y + check_size / 2),
            int(x + check_size / 3),
            int(y + check_size - 2),
        )
        painter.drawLine(
            int(x + check_size / 3),
            int(y + check_size - 2),
            int(x + check_size - 2),
            int(y + 2),
        )


class BranchNodeItem(QGraphicsEllipseItem):
    """Graphics item for rendering a branch occurrence point as a dot.

    Displays:
    - Small circle representing the branch occurrence point
    - Light orange fill (unresolved) or green fill (resolved)
    """

    def __init__(self, node_id: NodeId, branch: Branch) -> None:
        """Initialize branch node item.

        Args:
            node_id: Node ID
            branch: Branch instance
        """
        # Create small circle (diameter 20 pixels)
        diameter = 20.0
        super().__init__(0, 0, diameter, diameter)
        self.node_id = node_id
        self.branch = branch
        self.title = branch.title

        # Make item selectable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        # Enable hover events
        self.setAcceptHoverEvents(True)

        # Branch-specific styling (unresolved)
        self._base_color = QColor(255, 200, 150)  # Light orange
        self._hover_color = QColor(255, 220, 180)  # Lighter orange
        self._selected_color = QColor(255, 150, 80)  # Bright orange
        self._border_color = QColor(200, 150, 100)

        # Resolved styling
        self._resolved_color = QColor(150, 220, 150)  # Light green
        self._resolved_border_color = QColor(80, 160, 80)  # Green

        self._is_hovered = False

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the branch occurrence point as a dot.

        Args:
            painter: QPainter instance
            option: Style option
            widget: Widget being painted on
        """
        if painter is None:
            return

        is_resolved = self.branch.chosen_world_id is not None

        # Determine colors based on state
        if self.isSelected():
            fill_color = self._selected_color
            border_width = 3.0
            border_color = self._border_color
        elif self._is_hovered:
            fill_color = self._hover_color
            border_width = 2.0
            border_color = self._border_color
        elif is_resolved:
            fill_color = self._resolved_color
            border_width = 2.0
            border_color = self._resolved_border_color
        else:
            fill_color = self._base_color
            border_width = 2.0
            border_color = self._border_color

        # Draw circle
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(border_color, border_width))
        painter.drawEllipse(self.rect())

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: N802
        """Handle hover enter.

        Args:
            event: Hover event
        """
        self._is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: N802
        """Handle hover leave.

        Args:
            event: Hover event
        """
        self._is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)


class PossibleWorldItem(NodeItem):
    """Graphics item for rendering a possible world box.

    Displays:
    - Possible world title
    - Light green background (normal)
    - Bright green when chosen, gray when unchosen (resolved branch)
    - Connected to parent branch occurrence point
    """

    def __init__(
        self,
        node_id: NodeId,
        branch: Branch,
        possible_world: PossibleWorld,
        width: float = 180,
        height: float = 60,
    ) -> None:
        """Initialize possible world item.

        Args:
            node_id: Parent branch node ID
            branch: Parent branch instance
            possible_world: Possible world instance
            width: Box width in pixels
            height: Box height in pixels
        """
        super().__init__(node_id, possible_world.title, width, height)
        self.branch = branch
        self.possible_world = possible_world

        # Possible world-specific styling (unresolved)
        self._base_color = QColor(200, 255, 200)  # Light green
        self._hover_color = QColor(220, 255, 220)  # Lighter green
        self._selected_color = QColor(150, 255, 150)  # Bright green
        self._border_color = QColor(100, 200, 100)

        # Chosen world styling (when branch is resolved and this is chosen)
        self._chosen_color = QColor(100, 220, 100)  # Bright green
        self._chosen_border_color = QColor(60, 160, 60)  # Darker green

        # Unchosen world styling (when branch is resolved and this is not chosen)
        self._unchosen_color = QColor(220, 220, 220)  # Gray
        self._unchosen_border_color = QColor(160, 160, 160)  # Dark gray

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the possible world with resolution status indicator.

        Args:
            painter: QPainter instance
            option: Style option
            widget: Widget being painted on
        """
        if painter is None:
            return

        chosen_world_id = self.branch.chosen_world_id
        is_resolved = chosen_world_id is not None
        is_chosen = chosen_world_id == self.possible_world.id

        # Determine colors based on state
        if self.isSelected():
            fill_color = self._selected_color
            border_width = 3.0
            border_color = self._border_color
        elif self._is_hovered:
            fill_color = self._hover_color
            border_width = 2.0
            border_color = self._border_color
        elif is_resolved:
            if is_chosen:
                fill_color = self._chosen_color
                border_color = self._chosen_border_color
            else:
                fill_color = self._unchosen_color
                border_color = self._unchosen_border_color
            border_width = 2.0
        else:
            fill_color = self._base_color
            border_color = self._border_color
            border_width = 2.0

        # Draw rounded rectangle
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(border_color, border_width))
        painter.drawRoundedRect(self.rect(), 10, 10)

        # Draw title text (darker for unchosen)
        if is_resolved and not is_chosen and not self.isSelected():
            painter.setPen(QPen(QColor(120, 120, 120)))  # Gray text
        else:
            painter.setPen(QPen(QColor(0, 0, 0)))
        text_rect = self.rect().adjusted(10, 10, -10, -10)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            self.title,
        )
