"""Task editor widget for editing task properties."""

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fluxx.data.models import (
    Dependency,
    DurationDistribution,
    NodeId,
    ShiftedLognormal,
    TaskId,
    Triangular,
)
from fluxx.gui.controller import ProjectController
from fluxx.gui.widgets.editors.dependency_editor_widget import DependencyEditorWidget


class TaskEditor(QWidget):
    """Widget for editing task properties.

    Features:
    - Title and description fields
    - Duration distribution type selector and parameters
    - Pending changes tracking
    - Validation with inline error messages
    - Apply/Revert/Delete actions

    Signals:
        select_dependency_target_requested: Emitted when user wants to select
            a dependency target from the DAG view
    """

    select_dependency_target_requested = Signal()

    def __init__(self, controller: ProjectController) -> None:
        """Initialize task editor.

        Args:
            controller: Project controller instance
        """
        super().__init__()
        self.controller = controller
        self.current_task_id: TaskId | None = None
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
        self.title_field.setPlaceholderText("Enter task title...")
        self.title_field.textChanged.connect(self._on_title_changed)
        form_layout.addRow("Title:", self.title_field)

        # Description field
        self.description_field = QTextEdit()
        self.description_field.setPlaceholderText("Enter task description...")
        self.description_field.setMaximumHeight(100)
        self.description_field.textChanged.connect(self._on_description_changed)
        form_layout.addRow("Description:", self.description_field)

        # Duration distribution section
        duration_label = QLabel("Duration Distribution:")
        duration_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        form_layout.addRow(duration_label)

        # Distribution type selector
        self.distribution_type = QComboBox()
        self.distribution_type.addItems(["None", "Triangular", "Shifted Lognormal"])
        self.distribution_type.currentTextChanged.connect(
            self._on_distribution_type_changed
        )
        form_layout.addRow("Type:", self.distribution_type)

        # Distribution parameters container
        self.distribution_params_widget = QWidget()
        self.distribution_params_layout = QFormLayout()
        self.distribution_params_widget.setLayout(self.distribution_params_layout)
        form_layout.addRow(self.distribution_params_widget)

        layout.addLayout(form_layout)

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
        self.dependency_editor = DependencyEditorWidget(
            self.controller, is_branch=False
        )
        self.dependency_editor.setVisible(False)
        self.dependency_editor.select_target_requested.connect(
            self._on_dependency_select_target
        )
        self.dependency_editor.dependency_changed.connect(self._on_dependency_changed)
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

    def load_task(self, task_id: TaskId) -> None:
        """Load a task for editing.

        Args:
            task_id: Task ID to load
        """
        self.current_task_id = task_id
        self.pending_changes.clear()

        # Get task from project
        project = self.controller.get_project()
        node_id = NodeId(task_id)

        if node_id not in project.dag.node_map:
            return

        persistent_id = project.dag.node_map[node_id]
        if persistent_id not in project.persistent_tasks:
            return

        persistent_task = project.persistent_tasks[persistent_id]
        current_version = project.dag.current_version_id

        if current_version not in persistent_task.versions:
            return

        task = persistent_task.versions[current_version]

        # Populate fields (block signals to avoid triggering change handlers)
        self.title_field.blockSignals(True)
        self.title_field.setText(task.title)
        self.title_field.blockSignals(False)

        self.description_field.blockSignals(True)
        self.description_field.setPlainText(task.description)
        self.description_field.blockSignals(False)

        # Distribution
        self._load_distribution(task.duration_distribution)

        # Dependencies
        self._load_dependencies(task.dependencies)

        # Update button states
        self._update_button_states()

    def _load_distribution(self, distribution: DurationDistribution | None) -> None:
        """Load duration distribution into UI.

        Args:
            distribution: Duration distribution or None
        """
        self.distribution_type.blockSignals(True)

        if distribution is None:
            self.distribution_type.setCurrentText("None")
        elif isinstance(distribution, Triangular):
            self.distribution_type.setCurrentText("Triangular")
            self._setup_triangular_fields(distribution)
        elif isinstance(distribution, ShiftedLognormal):
            self.distribution_type.setCurrentText("Shifted Lognormal")
            self._setup_lognormal_fields(distribution)

        self.distribution_type.blockSignals(False)

    def _setup_triangular_fields(self, distribution: Triangular | None = None) -> None:
        """Set up fields for triangular distribution.

        Args:
            distribution: Existing distribution to populate, or None for new
        """
        # Clear existing parameter fields
        self._clear_distribution_params()

        # Create fields
        self.min_field = QLineEdit()
        self.min_field.setPlaceholderText("Minimum (work-hours)")
        self.min_field.textChanged.connect(self._on_distribution_param_changed)
        self.distribution_params_layout.addRow("Min (work-hours):", self.min_field)

        self.mode_field = QLineEdit()
        self.mode_field.setPlaceholderText("Most likely (work-hours)")
        self.mode_field.textChanged.connect(self._on_distribution_param_changed)
        self.distribution_params_layout.addRow("Mode (work-hours):", self.mode_field)

        self.max_field = QLineEdit()
        self.max_field.setPlaceholderText("Maximum (work-hours)")
        self.max_field.textChanged.connect(self._on_distribution_param_changed)
        self.distribution_params_layout.addRow("Max (work-hours):", self.max_field)

        # Populate if distribution provided (block signals to avoid triggering changes)
        if distribution is not None:
            self.min_field.blockSignals(True)
            self.mode_field.blockSignals(True)
            self.max_field.blockSignals(True)

            self.min_field.setText(str(distribution.min))
            self.mode_field.setText(str(distribution.mode))
            self.max_field.setText(str(distribution.max))

            self.min_field.blockSignals(False)
            self.mode_field.blockSignals(False)
            self.max_field.blockSignals(False)

    def _setup_lognormal_fields(
        self, distribution: ShiftedLognormal | None = None
    ) -> None:
        """Set up fields for shifted lognormal distribution.

        Args:
            distribution: Existing distribution to populate, or None for new
        """
        # Clear existing parameter fields
        self._clear_distribution_params()

        # Create fields
        self.min_field = QLineEdit()
        self.min_field.setPlaceholderText("Minimum (work-hours)")
        self.min_field.textChanged.connect(self._on_distribution_param_changed)
        self.distribution_params_layout.addRow("Min (work-hours):", self.min_field)

        self.mode_field = QLineEdit()
        self.mode_field.setPlaceholderText("Most likely (work-hours)")
        self.mode_field.textChanged.connect(self._on_distribution_param_changed)
        self.distribution_params_layout.addRow("Mode (work-hours):", self.mode_field)

        self.percentile_95_field = QLineEdit()
        self.percentile_95_field.setPlaceholderText("95th percentile (work-hours)")
        self.percentile_95_field.textChanged.connect(
            self._on_distribution_param_changed
        )
        self.distribution_params_layout.addRow(
            "95th % (work-hours):", self.percentile_95_field
        )

        # Populate if distribution provided (block signals to avoid triggering changes)
        if distribution is not None:
            self.min_field.blockSignals(True)
            self.mode_field.blockSignals(True)
            self.percentile_95_field.blockSignals(True)

            self.min_field.setText(str(distribution.min))
            self.mode_field.setText(str(distribution.mode))
            self.percentile_95_field.setText(str(distribution.percentile_95))

            self.min_field.blockSignals(False)
            self.mode_field.blockSignals(False)
            self.percentile_95_field.blockSignals(False)

    def _clear_distribution_params(self) -> None:
        """Clear all distribution parameter fields."""
        while self.distribution_params_layout.count():
            item = self.distribution_params_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

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

    def _on_distribution_type_changed(self, dist_type: str) -> None:
        """Handle distribution type changes.

        Args:
            dist_type: New distribution type name
        """
        if dist_type == "None":
            self._clear_distribution_params()
            self.pending_changes["duration_distribution"] = None
        elif dist_type == "Triangular":
            self._setup_triangular_fields()
            # Don't set pending change yet - wait for params
        elif dist_type == "Shifted Lognormal":
            self._setup_lognormal_fields()
            # Don't set pending change yet - wait for params

        self._update_button_states()

    def _on_distribution_param_changed(self, text: str) -> None:
        """Handle distribution parameter changes.

        Args:
            text: New parameter value
        """
        # Try to build distribution from current field values
        dist_type = self.distribution_type.currentText()

        try:
            if dist_type == "Triangular":
                min_val = float(self.min_field.text() or "0")
                mode_val = float(self.mode_field.text() or "0")
                max_val = float(self.max_field.text() or "0")
                self.pending_changes["duration_distribution"] = Triangular(
                    min=min_val, mode=mode_val, max=max_val
                )
            elif dist_type == "Shifted Lognormal":
                min_val = float(self.min_field.text() or "0")
                mode_val = float(self.mode_field.text() or "0")
                p95_val = float(self.percentile_95_field.text() or "0")
                self.pending_changes["duration_distribution"] = ShiftedLognormal(
                    min=min_val, mode=mode_val, percentile_95=p95_val
                )
        except (ValueError, AttributeError):
            # Invalid values - don't set pending change
            pass

        self._update_button_states()

    def _update_button_states(self) -> None:
        """Update enabled state of action buttons based on pending changes."""
        has_changes = len(self.pending_changes) > 0
        is_valid = self._validate_changes()

        self.apply_button.setEnabled(has_changes and is_valid)
        self.revert_button.setEnabled(has_changes)
        self.delete_button.setEnabled(self.current_task_id is not None)

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

    def _on_apply(self) -> None:
        """Apply pending changes to the task."""
        if self.current_task_id is None:
            return

        if not self._validate_changes():
            return

        # Handle dependencies separately (use add/remove_dependency calls)
        if "dependencies" in self.pending_changes:
            # Get original dependencies
            project = self.controller.get_project()
            node_id = NodeId(self.current_task_id)
            persistent_id = project.dag.node_map[node_id]
            persistent_task = project.persistent_tasks[persistent_id]
            task = persistent_task.versions[project.dag.current_version_id]
            original_deps = task.dependencies

            new_deps = self.pending_changes["dependencies"]

            # Find dependencies to remove (in original but not in new)
            for dep in original_deps:
                if dep not in new_deps:
                    self.controller.remove_dependency(node_id, dep)

            # Find dependencies to add (in new but not in original)
            for dep in new_deps:
                if dep not in original_deps:
                    self.controller.add_dependency(node_id, dep)

        # Apply non-dependency changes through update_task
        task_changes = {
            k: v for k, v in self.pending_changes.items() if k != "dependencies"
        }
        if task_changes:
            self.controller.update_task(self.current_task_id, **task_changes)

        # Clear pending changes
        self.pending_changes.clear()
        self._update_button_states()

    def _on_revert(self) -> None:
        """Revert pending changes and reload from controller."""
        if self.current_task_id is not None:
            self.load_task(self.current_task_id)

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
            endpoint_str = dep.source_endpoint.value
            item_text = f"{target_title} ({endpoint_str})"
            self.dependencies_list.addItem(item_text)

    def _on_dependency_selection_changed(self) -> None:
        """Handle dependency list selection changes."""
        has_selection = len(self.dependencies_list.selectedItems()) > 0
        self.remove_dependency_button.setEnabled(has_selection)

    def _on_add_dependency(self) -> None:
        """Add a new dependency."""
        if self.current_task_id is None:
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

        if self.current_task_id is None:
            return  # No task loaded

        # Get current dependencies
        if "dependencies" in self.pending_changes:
            current_deps = self.pending_changes["dependencies"].copy()
        else:
            project = self.controller.get_project()
            node_id = NodeId(self.current_task_id)
            persistent_id = project.dag.node_map[node_id]
            persistent_task = project.persistent_tasks[persistent_id]
            task = persistent_task.versions[project.dag.current_version_id]
            current_deps = list(task.dependencies)

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
        if self.current_task_id is None:
            return

        selected_items = self.dependencies_list.selectedItems()
        if not selected_items:
            return

        # Get the index of the selected item
        selected_index = self.dependencies_list.row(selected_items[0])

        # Get current dependencies (from pending changes or task)
        if "dependencies" in self.pending_changes:
            current_deps = self.pending_changes["dependencies"].copy()
        else:
            project = self.controller.get_project()
            node_id = NodeId(self.current_task_id)
            persistent_id = project.dag.node_map[node_id]
            persistent_task = project.persistent_tasks[persistent_id]
            task = persistent_task.versions[project.dag.current_version_id]
            current_deps = task.dependencies.copy()

        # Remove dependency at index
        if 0 <= selected_index < len(current_deps):
            current_deps.pop(selected_index)

            # Update pending changes
            self.pending_changes["dependencies"] = current_deps
            self._load_dependencies(current_deps)
            self._update_button_states()

    def _on_delete(self) -> None:
        """Delete the current task."""
        # TODO: Implement task deletion
        # This will require adding a delete_task method to the controller
        pass
