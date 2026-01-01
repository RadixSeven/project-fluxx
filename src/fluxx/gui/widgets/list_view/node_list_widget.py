"""Node list widget for filterable list view of all tasks and branches."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from rapidfuzz import fuzz

from fluxx.data.models import NodeId, PossibleWorldId, Project
from fluxx.gui.controller import ProjectController


class NodeListWidget(QWidget):
    """Filterable list view for navigating tasks, branches, and possible worlds.

    Features:
    - Search box with fuzzy matching
    - Shows all tasks, branches, and possible worlds
    - Click to select node
    - Updates when project changes
    """

    def __init__(self, controller: ProjectController) -> None:
        """Initialize node list widget.

        Args:
            controller: Project controller instance
        """
        super().__init__()
        self.controller = controller

        # Store all selectable items for filtering
        # Each entry is either:
        # - (node_id, title, "Task")
        # - (node_id, title, "Branch")
        # - ((branch_node_id, possible_world_id), title, "PossibleWorld")
        self.all_nodes: list[
            tuple[NodeId | tuple[NodeId, PossibleWorldId], str, str]
        ] = []

        self._setup_ui()

        # Connect to controller signals
        self.controller.project_changed.connect(self._on_project_changed)
        self.controller.selection_changed.connect(self._on_selection_changed)

        # Initial load
        self._load_nodes()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Search box
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search nodes...")
        self.search_field.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_field)

        # Node list
        self.node_list = QListWidget()
        self.node_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.node_list)

        self.setLayout(layout)

    def _on_project_changed(self, project: Project) -> None:
        """Handle project changes by reloading the node list.

        Args:
            project: Updated project instance
        """
        self._load_nodes()

    def _on_selection_changed(self, node_id: NodeId | None) -> None:
        """Handle selection changes by updating list selection.

        Args:
            node_id: Selected node ID or None
        """
        # Clear all selections first
        self.node_list.clearSelection()

        if node_id is None:
            return

        # Find and select the item
        for i in range(self.node_list.count()):
            item = self.node_list.item(i)
            if item is not None:
                item_node_id = item.data(Qt.ItemDataRole.UserRole)
                if item_node_id == node_id:
                    item.setSelected(True)
                    self.node_list.scrollToItem(item)
                    break

    def _load_nodes(self) -> None:
        """Load all nodes and possible worlds from the project."""
        project = self.controller.get_project()
        current_version = project.dag.current_version_id

        self.all_nodes.clear()

        # Load all tasks, branches, and possible worlds
        for node_id, persistent_id in project.dag.node_map.items():
            if persistent_id in project.persistent_tasks:
                persistent_task = project.persistent_tasks[persistent_id]
                if current_version in persistent_task.versions:
                    task = persistent_task.versions[current_version]
                    self.all_nodes.append((node_id, task.title, "Task"))

            elif persistent_id in project.persistent_branches:
                persistent_branch = project.persistent_branches[persistent_id]
                if current_version in persistent_branch.versions:
                    branch = persistent_branch.versions[current_version]
                    # Add branch occurrence point
                    self.all_nodes.append((node_id, branch.title, "Branch"))

                    # Add each possible world as a separate item
                    for pw in branch.possible_worlds:
                        pw_id = PossibleWorldId(pw.id)
                        # Format title to show it's a possible world of this branch
                        pw_display_title = f"{pw.title} (from {branch.title})"
                        self.all_nodes.append(
                            ((node_id, pw_id), pw_display_title, "PossibleWorld")
                        )

        # Sort by title
        self.all_nodes.sort(key=lambda x: x[1].lower())

        # Update display
        self._update_display()

    def _update_display(self) -> None:
        """Update the list display based on current filter."""
        search_text = self.search_field.text().strip()

        # Clear current list
        self.node_list.clear()

        if not search_text:
            # Show all nodes
            for node_id, title, node_type in self.all_nodes:
                self._add_list_item(node_id, title, node_type)
        else:
            # Filter with fuzzy matching
            matches = self._fuzzy_filter(search_text)
            for node_id, title, node_type, _score in matches:
                self._add_list_item(node_id, title, node_type)

        # Restore selection
        selected_node_id = self.controller.get_selected_node_id()
        if selected_node_id is not None:
            self._on_selection_changed(selected_node_id)

    def _fuzzy_filter(
        self, search_text: str
    ) -> list[tuple[NodeId | tuple[NodeId, PossibleWorldId], str, str, float]]:
        """Filter nodes using fuzzy matching.

        Args:
            search_text: Search query

        Returns:
            List of (node_id, title, type, score) tuples sorted by score
        """
        matches: list[
            tuple[NodeId | tuple[NodeId, PossibleWorldId], str, str, float]
        ] = []

        for node_id, title, node_type in self.all_nodes:
            # Calculate fuzzy match score
            score = fuzz.partial_ratio(search_text.lower(), title.lower())

            # Include matches above threshold
            if score > 60:  # Threshold for fuzzy matching
                matches.append((node_id, title, node_type, score))

        # Sort by score (highest first)
        matches.sort(key=lambda x: x[3], reverse=True)

        return matches

    def _add_list_item(
        self,
        node_id: NodeId | tuple[NodeId, PossibleWorldId],
        title: str,
        node_type: str,
    ) -> None:
        """Add an item to the list.

        Args:
            node_id: Node ID or (branch_node_id, possible_world_id) tuple
            title: Display title
            node_type: Node type (Task, Branch, or PossibleWorld)
        """
        # Format display text
        display_text = f"[{node_type}] {title}"

        item = QListWidgetItem(display_text)
        item.setData(Qt.ItemDataRole.UserRole, node_id)

        # Add type-specific styling
        if node_type == "Task":
            item.setForeground(Qt.GlobalColor.blue)
        elif node_type == "Branch":
            item.setForeground(Qt.GlobalColor.darkYellow)
        else:  # PossibleWorld
            item.setForeground(Qt.GlobalColor.darkGreen)

        self.node_list.addItem(item)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text changes.

        Args:
            text: New search text
        """
        self._update_display()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle item clicks.

        Args:
            item: Clicked item
        """
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is not None:
            # Check if this is a possible world (tuple/list) or a node (NodeId)
            # PySide6 may convert tuples to lists when storing in QVariant
            if isinstance(data, (tuple, list)):
                # Possible world: select parent branch
                branch_node_id = data[0]
                self.controller.select_node(branch_node_id)
            else:
                # Task or branch: select normally
                self.controller.select_node(data)
