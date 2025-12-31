"""Branch editor widget for editing branch properties."""

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fluxx.data.id_generation import generate_possible_world_id
from fluxx.data.models import (
    BranchId,
    Dependency,
    NodeId,
    PossibleWorld,
)
from fluxx.gui.controller import ProjectController
from fluxx.gui.widgets.editors.dependency_editor_widget import DependencyEditorWidget


class BranchEditor(QWidget):
    """Widget for editing branch properties.

    Features:
    - Title and description fields
    - Possible worlds table (editable)
    - Dependencies list
    - Pending changes tracking
    - Validation with inline error messages
    - Apply/Revert/Delete actions

    Signals:
        select_dependency_target_requested: Emitted when user wants to select
            a dependency target from the DAG view
    """

    select_dependency_target_requested = Signal()

    def __init__(self, controller: ProjectController) -> None:
        """Initialize branch editor.

        Args:
            controller: Project controller instance
        """
        super().__init__()
        self.controller = controller
        self.current_branch_id: BranchId | None = None
        self.pending_changes: dict[str, Any] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Form layout for fields
        form_layout = QFormLayout()

        # Title field
        self.title_field = QLineEdit()
        self.title_field.setPlaceholderText("Enter branch title...")
        self.title_field.textChanged.connect(self._on_title_changed)
        form_layout.addRow("Title:", self.title_field)

        # Description field
        self.description_field = QTextEdit()
        self.description_field.setPlaceholderText("Enter branch description...")
        self.description_field.setMaximumHeight(100)
        self.description_field.textChanged.connect(self._on_description_changed)
        form_layout.addRow("Description:", self.description_field)

        layout.addLayout(form_layout)

        # Possible worlds section
        worlds_label = QLabel("Possible Worlds:")
        worlds_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(worlds_label)

        # Possible worlds table
        self.worlds_table = QTableWidget()
        self.worlds_table.setColumnCount(4)
        self.worlds_table.setHorizontalHeaderLabels(
            ["Title", "Description", "Weight", "Probability"]
        )
        self.worlds_table.setMaximumHeight(200)
        self.worlds_table.cellChanged.connect(self._on_world_cell_changed)
        self.worlds_table.currentCellChanged.connect(self._on_world_selection_changed)

        # Make probability column read-only by setting it later
        header = self.worlds_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.worlds_table)

        # Worlds buttons
        worlds_button_layout = QHBoxLayout()
        self.add_world_button = QPushButton("Add World")
        self.add_world_button.clicked.connect(self._on_add_world)
        worlds_button_layout.addWidget(self.add_world_button)

        self.remove_world_button = QPushButton("Remove World")
        self.remove_world_button.clicked.connect(self._on_remove_world)
        self.remove_world_button.setEnabled(False)
        worlds_button_layout.addWidget(self.remove_world_button)

        worlds_button_layout.addStretch()
        layout.addLayout(worlds_button_layout)

        # Dependencies section
        dependencies_label = QLabel("Dependencies:")
        dependencies_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(dependencies_label)

        # Dependencies list
        self.dependencies_list = QListWidget()
        self.dependencies_list.setMaximumHeight(100)
        self.dependencies_list.itemSelectionChanged.connect(
            self._on_dependency_selection_changed
        )
        layout.addWidget(self.dependencies_list)

        # Dependencies buttons
        dependencies_button_layout = QHBoxLayout()
        self.add_dependency_button = QPushButton("Add Dependency")
        self.add_dependency_button.clicked.connect(self._on_add_dependency)
        dependencies_button_layout.addWidget(self.add_dependency_button)

        self.remove_dependency_button = QPushButton("Remove Dependency")
        self.remove_dependency_button.clicked.connect(self._on_remove_dependency)
        self.remove_dependency_button.setEnabled(False)
        dependencies_button_layout.addWidget(self.remove_dependency_button)

        dependencies_button_layout.addStretch()
        layout.addLayout(dependencies_button_layout)

        # Dependency editor (initially hidden)
        self.dependency_editor = DependencyEditorWidget(self.controller, is_branch=True)
        self.dependency_editor.setVisible(False)
        self.dependency_editor.select_target_requested.connect(
            self._on_dependency_select_target
        )
        self.dependency_editor.dependency_changed.connect(self._on_dependency_changed)
        self.dependency_editor.confirmed.connect(self.finish_dependency_editing)
        self.dependency_editor.cancelled.connect(self._on_dependency_cancelled)
        layout.addWidget(self.dependency_editor)

        # Track editing state
        self._editing_dependency_index: int | None = None  # None = adding new

        # Spacer
        layout.addStretch()

        # Action buttons
        button_layout = QHBoxLayout()

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._on_apply)
        self.apply_button.setEnabled(False)
        button_layout.addWidget(self.apply_button)

        self.revert_button = QPushButton("Revert")
        self.revert_button.clicked.connect(self._on_revert)
        self.revert_button.setEnabled(False)
        button_layout.addWidget(self.revert_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._on_delete)
        button_layout.addWidget(self.delete_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def load_branch(self, branch_id: BranchId) -> None:
        """Load a branch for editing.

        Args:
            branch_id: Branch ID to load
        """
        self.current_branch_id = branch_id
        self.pending_changes.clear()

        # Get branch from project
        project = self.controller.get_project()
        node_id = NodeId(branch_id)

        if node_id not in project.dag.node_map:
            return

        persistent_id = project.dag.node_map[node_id]
        if persistent_id not in project.persistent_branches:
            return

        persistent_branch = project.persistent_branches[persistent_id]
        current_version = project.dag.current_version_id

        if current_version not in persistent_branch.versions:
            return

        branch = persistent_branch.versions[current_version]

        # Populate fields (block signals to avoid triggering change handlers)
        self.title_field.blockSignals(True)
        self.title_field.setText(branch.title)
        self.title_field.blockSignals(False)

        self.description_field.blockSignals(True)
        self.description_field.setPlainText(branch.description)
        self.description_field.blockSignals(False)

        # Possible worlds
        self._load_possible_worlds(branch.possible_worlds)

        # Dependencies
        self._load_dependencies(branch.dependencies)

        # Update button states
        self._update_button_states()

    def _load_possible_worlds(self, worlds: list[PossibleWorld]) -> None:
        """Load possible worlds into the table.

        Args:
            worlds: List of possible worlds
        """
        # Block signals to avoid triggering change handlers
        self.worlds_table.blockSignals(True)

        self.worlds_table.setRowCount(len(worlds))

        # Calculate total weight for probability
        total_weight = sum(w.weight for w in worlds)

        for i, world in enumerate(worlds):
            # Title
            title_item = QTableWidgetItem(world.title)
            self.worlds_table.setItem(i, 0, title_item)

            # Description
            desc_item = QTableWidgetItem(world.description)
            self.worlds_table.setItem(i, 1, desc_item)

            # Weight
            weight_item = QTableWidgetItem(str(world.weight))
            self.worlds_table.setItem(i, 2, weight_item)

            # Probability (read-only, computed)
            prob = world.weight / total_weight if total_weight > 0 else 0
            prob_item = QTableWidgetItem(f"{prob:.2%}")
            prob_item.setFlags(
                prob_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )  # Read-only
            self.worlds_table.setItem(i, 3, prob_item)

        self.worlds_table.blockSignals(False)

    def _load_dependencies(self, dependencies: list[Dependency]) -> None:
        """Load dependencies into the list widget.

        Args:
            dependencies: List of dependencies to display
        """
        self.dependencies_list.clear()

        project = self.controller.get_project()

        for dep in dependencies:
            # Get target node title
            target_id = dep.target_node_id
            target_title = "Unknown"

            if target_id in project.dag.node_map:
                persistent_id = project.dag.node_map[target_id]

                if persistent_id in project.persistent_tasks:
                    persistent_task = project.persistent_tasks[persistent_id]
                    current_version = project.dag.current_version_id
                    if current_version in persistent_task.versions:
                        target_title = persistent_task.versions[current_version].title
                elif persistent_id in project.persistent_branches:
                    persistent_branch = project.persistent_branches[persistent_id]
                    current_version = project.dag.current_version_id
                    if current_version in persistent_branch.versions:
                        target_title = persistent_branch.versions[current_version].title

            # Format dependency display
            source_ep = dep.source_endpoint.value
            target_ep = dep.target_endpoint.value
            constraint = dep.constraint_type.value
            if constraint == ">=":
                constraint = "≥"

            item_text = f"{source_ep} {constraint} {target_title}.{target_ep}"
            self.dependencies_list.addItem(item_text)

    def _on_title_changed(self, text: str) -> None:
        """Handle title field changes.

        Args:
            text: New title text
        """
        self.pending_changes["title"] = text
        self._update_button_states()

    def _on_description_changed(self) -> None:
        """Handle description field changes."""
        self.pending_changes["description"] = self.description_field.toPlainText()
        self._update_button_states()

    def _on_world_cell_changed(self, row: int, column: int) -> None:
        """Handle cell changes in the possible worlds table.

        Args:
            row: Row that changed
            column: Column that changed
        """
        # Skip probability column (read-only)
        if column == 3:
            return

        # Get all worlds from table
        worlds = self._get_worlds_from_table()
        if worlds is not None:
            self.pending_changes["possible_worlds"] = worlds
            self._update_probabilities()
            self._update_button_states()

    def _get_worlds_from_table(self) -> list[PossibleWorld] | None:
        """Extract possible worlds from the table.

        Returns:
            List of possible worlds or None if invalid
        """
        worlds: list[PossibleWorld] = []

        for i in range(self.worlds_table.rowCount()):
            title_item = self.worlds_table.item(i, 0)
            desc_item = self.worlds_table.item(i, 1)
            weight_item = self.worlds_table.item(i, 2)

            if title_item is None or weight_item is None:
                continue

            title = title_item.text().strip()
            description = desc_item.text().strip() if desc_item else ""

            try:
                weight = float(weight_item.text())
                if weight <= 0:
                    return None  # Invalid weight

                world = PossibleWorld(
                    id=generate_possible_world_id(),
                    title=title,
                    description=description,
                    weight=weight,
                )
                worlds.append(world)
            except (ValueError, TypeError):
                return None  # Invalid weight format

        return worlds

    def _update_probabilities(self) -> None:
        """Update the probability column based on weights."""
        worlds = self._get_worlds_from_table()
        if worlds is None:
            return

        total_weight = sum(w.weight for w in worlds)

        self.worlds_table.blockSignals(True)

        for i, world in enumerate(worlds):
            prob = world.weight / total_weight if total_weight > 0 else 0
            prob_item = QTableWidgetItem(f"{prob:.2%}")
            prob_item.setFlags(
                prob_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )  # Read-only
            self.worlds_table.setItem(i, 3, prob_item)

        self.worlds_table.blockSignals(False)

    def _on_world_selection_changed(
        self,
        current_row: int,
        current_column: int,
        previous_row: int,
        previous_column: int,
    ) -> None:
        """Handle world table selection changes.

        Args:
            current_row: Current row
            current_column: Current column
            previous_row: Previous row
            previous_column: Previous column
        """
        # Update remove world button state
        self.remove_world_button.setEnabled(current_row >= 0)

    def _on_add_world(self) -> None:
        """Add a new possible world row."""
        row_count = self.worlds_table.rowCount()
        self.worlds_table.setRowCount(row_count + 1)

        # Add default values
        self.worlds_table.setItem(row_count, 0, QTableWidgetItem("New World"))
        self.worlds_table.setItem(row_count, 1, QTableWidgetItem(""))
        self.worlds_table.setItem(row_count, 2, QTableWidgetItem("1.0"))

        # Trigger update
        self._on_world_cell_changed(row_count, 0)

    def _on_remove_world(self) -> None:
        """Remove selected possible world row."""
        current_row = self.worlds_table.currentRow()
        if current_row >= 0:
            self.worlds_table.removeRow(current_row)
            # Trigger update
            self._on_world_cell_changed(0, 0)

    def _on_dependency_selection_changed(self) -> None:
        """Handle dependency list selection changes."""
        has_selection = len(self.dependencies_list.selectedItems()) > 0
        self.remove_dependency_button.setEnabled(has_selection)

    def _on_add_dependency(self) -> None:
        """Add a new dependency."""
        if self.current_branch_id is None:
            return

        # Enter dependency editing mode (adding new)
        self._editing_dependency_index = None
        self.dependency_editor.clear()
        self.dependency_editor.setVisible(True)

        # Disable other controls while editing dependency
        self.add_dependency_button.setEnabled(False)
        self.remove_dependency_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.revert_button.setEnabled(False)

    def _on_dependency_select_target(self) -> None:
        """Handle Select Target button click in dependency editor."""
        # Emit signal to parent (MainWindow) to enter select-target-node mode
        self.select_dependency_target_requested.emit()

    def _on_dependency_changed(self) -> None:
        """Handle dependency editor field changes."""
        # Could add validation here if needed
        pass

    def _on_dependency_cancelled(self) -> None:
        """Handle dependency editing cancelled."""
        self._editing_dependency_index = None
        self.dependency_editor.setVisible(False)

        # Re-enable controls
        self.add_dependency_button.setEnabled(True)
        self._on_dependency_selection_changed()  # Update remove button state
        self._update_button_states()

    def set_dependency_target(self, node_id: NodeId) -> None:
        """Set the target node for the dependency being edited.

        Called from parent window when user selects a node in DAG view.

        Args:
            node_id: Selected node ID
        """
        self.dependency_editor.set_target_node(node_id)

    def finish_dependency_editing(self) -> None:
        """Finish editing the current dependency and save it."""
        dependency = self.dependency_editor.get_dependency()
        if dependency is None:
            return  # Incomplete dependency

        if self.current_branch_id is None:
            return  # No branch loaded

        # Get current dependencies
        if "dependencies" in self.pending_changes:
            current_deps = self.pending_changes["dependencies"].copy()
        else:
            project = self.controller.get_project()
            node_id = NodeId(self.current_branch_id)
            persistent_id = project.dag.node_map[node_id]
            persistent_branch = project.persistent_branches[persistent_id]
            branch = persistent_branch.versions[project.dag.current_version_id]
            current_deps = list(branch.dependencies)

        # Add or update dependency
        if self._editing_dependency_index is None:
            # Adding new
            current_deps.append(dependency)
        else:
            # Updating existing
            if 0 <= self._editing_dependency_index < len(current_deps):
                current_deps[self._editing_dependency_index] = dependency

        # Update pending changes
        self.pending_changes["dependencies"] = current_deps
        self._load_dependencies(current_deps)

        # Exit editing mode
        self._editing_dependency_index = None
        self.dependency_editor.setVisible(False)

        # Re-enable controls
        self.add_dependency_button.setEnabled(True)
        self._on_dependency_selection_changed()
        self._update_button_states()

    def _on_remove_dependency(self) -> None:
        """Remove selected dependency."""
        if self.current_branch_id is None:
            return

        selected_items = self.dependencies_list.selectedItems()
        if not selected_items:
            return

        # Get the index of the selected item
        selected_index = self.dependencies_list.row(selected_items[0])

        # Get current dependencies (from pending changes or branch)
        if "dependencies" in self.pending_changes:
            current_deps = self.pending_changes["dependencies"].copy()
        else:
            project = self.controller.get_project()
            node_id = NodeId(self.current_branch_id)
            persistent_id = project.dag.node_map[node_id]
            persistent_branch = project.persistent_branches[persistent_id]
            branch = persistent_branch.versions[project.dag.current_version_id]
            current_deps = branch.dependencies.copy()

        # Remove dependency at index
        if 0 <= selected_index < len(current_deps):
            current_deps.pop(selected_index)

            # Update pending changes
            self.pending_changes["dependencies"] = current_deps
            self._load_dependencies(current_deps)
            self._update_button_states()

    def _update_button_states(self) -> None:
        """Update enabled state of action buttons based on pending changes."""
        has_changes = len(self.pending_changes) > 0
        is_valid = self._validate_changes()

        self.apply_button.setEnabled(has_changes and is_valid)
        self.revert_button.setEnabled(has_changes)
        self.delete_button.setEnabled(self.current_branch_id is not None)

        # Update remove world button
        self.remove_world_button.setEnabled(self.worlds_table.currentRow() >= 0)

    def _validate_changes(self) -> bool:
        """Validate pending changes.

        Returns:
            True if all pending changes are valid
        """
        # Title is required and must not be empty
        return not (
            "title" in self.pending_changes
            and not self.pending_changes["title"].strip()
        )

    def is_dirty(self) -> bool:
        """Check if the editor has unsaved changes.

        Returns:
            True if there are pending changes
        """
        return len(self.pending_changes) > 0

    def apply_changes(self) -> bool:
        """Apply pending changes.

        Returns:
            True if changes were applied successfully
        """
        if not self.is_dirty():
            return True
        self._on_apply()
        return not self.is_dirty()

    def revert_changes(self) -> None:
        """Revert pending changes."""
        self._on_revert()

    def _on_apply(self) -> None:
        """Apply pending changes to the branch."""
        if self.current_branch_id is None:
            return

        if not self._validate_changes():
            return

        # Handle dependencies separately (use add/remove_dependency calls)
        if "dependencies" in self.pending_changes:
            # Get original dependencies
            project = self.controller.get_project()
            node_id = NodeId(self.current_branch_id)
            persistent_id = project.dag.node_map[node_id]
            persistent_branch = project.persistent_branches[persistent_id]
            branch = persistent_branch.versions[project.dag.current_version_id]
            original_deps = branch.dependencies

            new_deps = self.pending_changes["dependencies"]

            # Find dependencies to remove (in original but not in new)
            for dep in original_deps:
                if dep not in new_deps:
                    self.controller.remove_dependency(node_id, dep)

            # Find dependencies to add (in new but not in original)
            for dep in new_deps:
                if dep not in original_deps:
                    self.controller.add_dependency(node_id, dep)

        # Apply non-dependency changes through update_branch
        branch_changes = {
            k: v for k, v in self.pending_changes.items() if k != "dependencies"
        }
        if branch_changes:
            self.controller.update_branch(self.current_branch_id, **branch_changes)

        # Clear pending changes
        self.pending_changes.clear()
        self._update_button_states()

    def _on_revert(self) -> None:
        """Revert pending changes and reload from controller."""
        if self.current_branch_id is not None:
            self.load_branch(self.current_branch_id)

    def _on_delete(self) -> None:
        """Delete the current branch."""
        # TODO: Implement branch deletion
        # This will require adding a delete_branch method to the controller
        pass
