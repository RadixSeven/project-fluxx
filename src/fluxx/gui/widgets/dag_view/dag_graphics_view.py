"""Graphics view for DAG visualization."""

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from fluxx.data.models import NodeId, Project
from fluxx.gui.controller import ProjectController
from fluxx.gui.utils.layout import compute_dag_layout
from fluxx.gui.widgets.dag_view.node_item import BranchNodeItem, NodeItem, TaskNodeItem


class DAGGraphicsView(QGraphicsView):
    """Graphics view for displaying the DAG.

    Features:
    - Pan: Drag with mouse
    - Zoom: Mouse wheel
    - Auto-layout using hierarchical algorithm
    - Click nodes to select
    - Updates when project changes
    """

    def __init__(self, controller: ProjectController) -> None:
        """Initialize DAG graphics view.

        Args:
            controller: Project controller instance
        """
        super().__init__()
        self.controller = controller

        # Create scene (use private attribute to avoid conflict with scene() method)
        self._scene = QGraphicsScene()
        self.setScene(self._scene)

        # Enable dragging to pan
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

        # Set rendering hints for better quality
        self.setRenderHint(self.renderHints() | self.renderHints())

        # Store node items for later reference
        self.node_items: dict[NodeId, NodeItem] = {}

        # Connect to controller signals
        self.controller.project_changed.connect(self._on_project_changed)
        self.controller.selection_changed.connect(self._on_selection_changed)

        # Initial render
        self._render_dag()

    def _on_project_changed(self, project: Project) -> None:
        """Handle project changes by re-rendering the DAG.

        Args:
            project: Updated project instance
        """
        self._render_dag()

    def _on_selection_changed(self, node_id: NodeId | None) -> None:
        """Handle selection changes by updating node visual state.

        Args:
            node_id: Selected node ID or None
        """
        # Clear all selections first
        for item in self.node_items.values():
            item.setSelected(False)

        # Select the specified node
        if node_id is not None and node_id in self.node_items:
            self.node_items[node_id].setSelected(True)

    def _render_dag(self) -> None:
        """Render the DAG by creating node items and positioning them."""
        # Clear scene
        self._scene.clear()
        self.node_items.clear()

        project = self.controller.get_project()
        current_version = project.dag.current_version_id

        # Compute layout
        positions = compute_dag_layout(project)

        # Create node items
        for node_id, persistent_id in project.dag.node_map.items():
            item: NodeItem | None = None

            # Check if it's a task or branch
            if persistent_id in project.persistent_tasks:
                persistent_task = project.persistent_tasks[persistent_id]
                if current_version not in persistent_task.versions:
                    continue
                task = persistent_task.versions[current_version]
                item = TaskNodeItem(node_id, task)
            elif persistent_id in project.persistent_branches:
                persistent_branch = project.persistent_branches[persistent_id]
                if current_version not in persistent_branch.versions:
                    continue
                branch = persistent_branch.versions[current_version]
                item = BranchNodeItem(node_id, branch)

            # Skip if no valid item was created
            if item is None:
                continue

            # Position the item
            if node_id in positions:
                pos = positions[node_id]
                item.setPos(pos)

            # Add to scene and store reference
            self._scene.addItem(item)
            self.node_items[node_id] = item

        # Update selection state
        selected_node_id = self.controller.get_selected_node_id()
        if selected_node_id is not None and selected_node_id in self.node_items:
            self.node_items[selected_node_id].setSelected(True)

        # Fit view to show all nodes
        if self.node_items:
            self.fitInView(
                self._scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio
            )

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        """Handle mouse press to select nodes.

        Args:
            event: Mouse event
        """
        # Let the base class handle the event first
        super().mousePressEvent(event)

        # Check if we clicked on a node
        item = self.itemAt(event.pos())
        if isinstance(item, NodeItem):
            # Notify controller of selection
            self.controller.select_node(item.node_id)
        else:
            # Clicked on empty space - clear selection
            self.controller.select_node(None)

    def wheelEvent(self, event: QWheelEvent | None) -> None:  # noqa: N802
        """Handle mouse wheel for zooming.

        Args:
            event: Wheel event
        """
        if event is None:
            return

        # Zoom factor
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor

        # Get the current scale and determine zoom direction
        scale_factor = zoom_in_factor if event.angleDelta().y() > 0 else zoom_out_factor

        # Apply zoom
        self.scale(scale_factor, scale_factor)
