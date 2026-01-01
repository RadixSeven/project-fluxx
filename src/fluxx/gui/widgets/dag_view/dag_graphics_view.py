"""Graphics view for DAG visualization."""

from typing import cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPen, QWheelEvent
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene, QGraphicsView

from fluxx.data.models import (
    BranchId,
    NodeId,
    PossibleWorldId,
    PossibleWorldReference,
    Project,
)
from fluxx.gui.controller import ProjectController
from fluxx.gui.utils.layout import compute_dag_layout
from fluxx.gui.widgets.dag_view.edge_item import EdgeItem
from fluxx.gui.widgets.dag_view.node_item import (
    BranchNodeItem,
    NodeItem,
    PossibleWorldItem,
    TaskNodeItem,
)


class DAGGraphicsView(QGraphicsView):
    """Graphics view for displaying the DAG.

    Features:
    - Pan: Drag with mouse
    - Zoom: Mouse wheel
    - Auto-layout using hierarchical algorithm
    - Click nodes to select
    - Updates when project changes
    - Select-target-node mode for dependency editing

    Signals:
        node_selected_for_dependency: Emitted when a node is selected in
            select-target-node mode
    """

    node_selected_for_dependency = Signal(object)  # Emits NodeId

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
        self.node_items: dict[NodeId, NodeItem | BranchNodeItem] = {}

        # Store possible world items for later reference
        self.possible_world_items: dict[
            tuple[NodeId, PossibleWorldId], PossibleWorldItem
        ] = {}

        # Store edge items for later reference
        self.edge_items: list[EdgeItem] = []

        # Select-target-node mode for dependency editing
        self._select_target_mode: bool = False

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
        self.possible_world_items.clear()
        self.edge_items.clear()

        project = self.controller.get_project()
        current_version = project.dag.current_version_id

        # Compute layout
        layout = compute_dag_layout(project)
        positions = layout.node_positions
        pw_positions = layout.possible_world_positions

        # Create node items
        for node_id, persistent_id in project.dag.node_map.items():
            item: NodeItem | BranchNodeItem | None = None

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

        # Create possible world items for branches
        for node_id, persistent_id in project.dag.node_map.items():
            if persistent_id in project.persistent_branches:
                persistent_branch = project.persistent_branches[persistent_id]
                if current_version not in persistent_branch.versions:
                    continue
                branch = persistent_branch.versions[current_version]

                # Create item for each possible world
                for pw in branch.possible_worlds:
                    pw_id = PossibleWorldId(pw.id)
                    pw_key = (node_id, pw_id)

                    if pw_key in pw_positions:
                        pw_item = PossibleWorldItem(node_id, branch, pw)
                        pw_item.setPos(pw_positions[pw_key])
                        self._scene.addItem(pw_item)
                        self.possible_world_items[pw_key] = pw_item

                        # Draw line from branch to possible world
                        if node_id in self.node_items:
                            branch_item = self.node_items[node_id]
                            # Get center of branch circle
                            branch_pos = branch_item.pos()
                            branch_center_x = branch_pos.x() + 10  # radius
                            branch_center_y = branch_pos.y() + 10  # radius

                            # Get left edge of possible world box
                            pw_pos = pw_item.pos()
                            pw_left_x = pw_pos.x()
                            pw_center_y = pw_pos.y() + 30  # half of height (60/2)

                            # Draw line
                            line = QGraphicsLineItem(
                                branch_center_x,
                                branch_center_y,
                                pw_left_x,
                                pw_center_y,
                            )
                            line.setPen(QPen(Qt.GlobalColor.gray, 2))
                            self._scene.addItem(line)

        # Create edges for dependencies
        for node_id, persistent_id in project.dag.node_map.items():
            # Get dependencies for this node
            dependencies = []

            if persistent_id in project.persistent_tasks:
                persistent_task = project.persistent_tasks[persistent_id]
                if current_version in persistent_task.versions:
                    task = persistent_task.versions[current_version]
                    dependencies = task.dependencies
            elif persistent_id in project.persistent_branches:
                persistent_branch = project.persistent_branches[persistent_id]
                if current_version in persistent_branch.versions:
                    branch = persistent_branch.versions[current_version]
                    dependencies = branch.dependencies

            # Create edge items for each dependency
            for dep in dependencies:
                # Skip if source or target node not in view
                target_str = str(dep.target_node_id)
                target_node_id: NodeId
                if ":" in target_str:
                    branch_id_str, _ = target_str.split(":", 1)
                    target_node_id = BranchId(branch_id_str)
                else:
                    target_node_id = cast(NodeId, dep.target_node_id)

                if (
                    node_id not in self.node_items
                    or target_node_id not in self.node_items
                ):
                    continue

                # Get node positions (center of nodes)
                source_item = self.node_items[node_id]
                target_item = self.node_items[target_node_id]

                source_pos = source_item.pos()
                target_pos = target_item.pos()

                # Create edge item
                edge = EdgeItem(
                    node_id,
                    target_node_id,
                    source_pos,
                    target_pos,
                    dep.constraint_type,
                )
                self._scene.addItem(edge)
                self.edge_items.append(edge)

        # Update selection state
        selected_node_id = self.controller.get_selected_node_id()
        if selected_node_id is not None and selected_node_id in self.node_items:
            self.node_items[selected_node_id].setSelected(True)

        # Fit view to show all nodes
        if self.node_items:
            self.fitInView(
                self._scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio
            )

    def enter_select_target_mode(self) -> None:
        """Enter select-target-node mode for dependency editing."""
        self._select_target_mode = True
        # Disable panning while in select mode
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        # Change cursor to indicate selection mode
        self.setCursor(Qt.CursorShape.CrossCursor)

    def exit_select_target_mode(self) -> None:
        """Exit select-target-node mode."""
        self._select_target_mode = False
        # Re-enable panning
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        # Restore default cursor
        self.unsetCursor()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Handle mouse press to select nodes.

        Args:
            event: Mouse event
        """
        # Check if we clicked on a node or possible world
        item = self.itemAt(event.pos())

        if isinstance(item, PossibleWorldItem):
            if self._select_target_mode:
                # In select-target mode: emit signal for possible world and exit mode
                # Format: "branch_id:world_id" for simulation compatibility
                pw_ref = PossibleWorldReference(
                    f"{item.node_id}:{item.possible_world.id}"
                )
                self.node_selected_for_dependency.emit(pw_ref)
                self.exit_select_target_mode()
            else:
                # Normal mode: select parent branch (per spec 5.2.2)
                self.controller.select_node(item.node_id)
        elif isinstance(item, NodeItem):
            if self._select_target_mode:
                # In select-target mode: emit signal and exit mode
                self.node_selected_for_dependency.emit(item.node_id)
                self.exit_select_target_mode()
            else:
                # Normal mode: notify controller of selection
                self.controller.select_node(item.node_id)
        else:
            # Clicked on empty space
            if not self._select_target_mode:
                # Normal mode: clear selection
                self.controller.select_node(None)

        # Let the base class handle the event (for panning, etc.)
        if not self._select_target_mode:
            super().mousePressEvent(event)

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
