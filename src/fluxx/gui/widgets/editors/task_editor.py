"""Task editor widget for editing task properties."""

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fluxx.data.models import (
    ConstraintType,
    Dependency,
    DurationDistribution,
    Endpoint,
    NodeId,
    ShiftedLognormal,
    TaskId,
    Triangular,
    WorkerId,
    type_explode_id,
)
from fluxx.data.validation import (
    get_required_exclusion_dependency,
    has_required_exclusion_dependency,
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
        select_excluded_task_requested: Emitted when user wants to select
            a task to exclude (for excluded assignees feature)
    """

    select_dependency_target_requested = Signal()
    select_excluded_task_requested = Signal()

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
        self.dependency_editor.confirmed.connect(self.finish_dependency_editing)
        self.dependency_editor.cancelled.connect(self._on_dependency_cancelled)
        layout.addWidget(self.dependency_editor)

        # Track editing state
        self._editing_dependency_index: int | None = None  # None = adding new

        # Worker Constraints section
        worker_constraints_label = QLabel("Worker Constraints:")
        worker_constraints_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(worker_constraints_label)

        # Allowed Workers subsection
        allowed_workers_label = QLabel("Allowed Workers:")
        layout.addWidget(allowed_workers_label)

        # Container for allowed workers content (switches between message and list)
        self.allowed_workers_container = QWidget()
        allowed_workers_layout = QVBoxLayout()
        allowed_workers_layout.setContentsMargins(0, 0, 0, 0)

        # Empty state message with link
        self.allowed_workers_empty_label = QLabel(
            'All workers allowed. <a href="#">Click to restrict to specific workers</a>'
        )
        self.allowed_workers_empty_label.linkActivated.connect(
            self._on_restrict_workers_clicked
        )
        allowed_workers_layout.addWidget(self.allowed_workers_empty_label)

        # List widget for allowed workers
        self.allowed_workers_list = QListWidget()
        self.allowed_workers_list.setMaximumHeight(80)
        self.allowed_workers_list.itemSelectionChanged.connect(
            self._on_allowed_worker_selection_changed
        )
        self.allowed_workers_list.setVisible(False)
        allowed_workers_layout.addWidget(self.allowed_workers_list)

        # Allowed workers buttons (initially hidden)
        self.allowed_workers_button_container = QWidget()
        allowed_workers_button_layout = QHBoxLayout()
        allowed_workers_button_layout.setContentsMargins(0, 0, 0, 0)

        self.add_allowed_worker_button = QPushButton("Add Worker")
        self.add_allowed_worker_button.clicked.connect(self._on_add_allowed_worker)
        allowed_workers_button_layout.addWidget(self.add_allowed_worker_button)

        self.remove_allowed_worker_button = QPushButton("Remove Worker")
        self.remove_allowed_worker_button.clicked.connect(
            self._on_remove_allowed_worker
        )
        self.remove_allowed_worker_button.setEnabled(False)
        allowed_workers_button_layout.addWidget(self.remove_allowed_worker_button)

        self.allow_all_workers_button = QPushButton("Allow All")
        self.allow_all_workers_button.clicked.connect(self._on_allow_all_workers)
        allowed_workers_button_layout.addWidget(self.allow_all_workers_button)

        allowed_workers_button_layout.addStretch()
        self.allowed_workers_button_container.setLayout(allowed_workers_button_layout)
        self.allowed_workers_button_container.setVisible(False)
        allowed_workers_layout.addWidget(self.allowed_workers_button_container)

        self.allowed_workers_container.setLayout(allowed_workers_layout)
        layout.addWidget(self.allowed_workers_container)

        # Excluded Assignees subsection
        excluded_assignees_label = QLabel("Excluded Assignees:")
        layout.addWidget(excluded_assignees_label)

        # Explanation label
        excluded_explanation = QLabel(
            "Tasks whose assigned workers cannot work on this task"
        )
        excluded_explanation.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(excluded_explanation)

        # List widget for excluded assignee tasks
        self.excluded_assignees_list = QListWidget()
        self.excluded_assignees_list.setMaximumHeight(80)
        self.excluded_assignees_list.itemSelectionChanged.connect(
            self._on_excluded_assignee_selection_changed
        )
        layout.addWidget(self.excluded_assignees_list)

        # Excluded assignees buttons
        excluded_button_layout = QHBoxLayout()

        self.add_excluded_task_button = QPushButton("Add Task")
        self.add_excluded_task_button.clicked.connect(self._on_add_excluded_task)
        excluded_button_layout.addWidget(self.add_excluded_task_button)

        self.remove_excluded_task_button = QPushButton("Remove Task")
        self.remove_excluded_task_button.clicked.connect(self._on_remove_excluded_task)
        self.remove_excluded_task_button.setEnabled(False)
        excluded_button_layout.addWidget(self.remove_excluded_task_button)

        excluded_button_layout.addStretch()
        layout.addLayout(excluded_button_layout)

        # Subtask operations section
        subtask_label = QLabel("Subtask Operations:")
        subtask_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(subtask_label)

        subtask_button_layout = QHBoxLayout()

        self.convert_to_parent_button = QPushButton("Convert to Parent")
        self.convert_to_parent_button.clicked.connect(self._on_convert_to_parent)
        self.convert_to_parent_button.setEnabled(False)
        subtask_button_layout.addWidget(self.convert_to_parent_button)

        self.add_sibling_button = QPushButton("Add Sibling")
        self.add_sibling_button.clicked.connect(self._on_add_sibling)
        self.add_sibling_button.setEnabled(False)
        subtask_button_layout.addWidget(self.add_sibling_button)

        subtask_button_layout.addStretch()
        layout.addLayout(subtask_button_layout)

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
        node_id: NodeId = task_id

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

        # Allowed workers
        self._load_allowed_workers(task.allowed_workers)

        # Excluded assignees
        self._load_excluded_assignees(task.excluded_worker_tasks)

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
            self._clear_distribution_params()
        elif isinstance(distribution, Triangular):
            self.distribution_type.setCurrentText("Triangular")
            self._setup_triangular_fields(distribution)
        elif isinstance(distribution, ShiftedLognormal):
            self.distribution_type.setCurrentText("Shifted Lognormal")
            self._setup_lognormal_fields(distribution)
        else:
            # Fallback for unknown or base class instance
            self.distribution_type.setCurrentText("None")
            self._clear_distribution_params()

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

        # Update subtask operation buttons
        if self.current_task_id is not None:
            project = self.controller.get_project()
            node_id = self.current_task_id

            if node_id in project.dag.node_map:
                persistent_id = project.dag.node_map[node_id]
                if persistent_id in project.persistent_tasks:
                    persistent_task = project.persistent_tasks[persistent_id]
                    current_version = project.dag.current_version_id
                    if current_version in persistent_task.versions:
                        task = persistent_task.versions[current_version]

                        # Convert to Parent: enabled only for leaf tasks (no children)
                        is_leaf = len(task.children) == 0
                        self.convert_to_parent_button.setEnabled(is_leaf)

                        # Add Sibling: enabled only for subtasks (has parent_id)
                        is_subtask = task.parent_id is not None
                        self.add_sibling_button.setEnabled(is_subtask)
                        return

        # If we couldn't find the task, disable both buttons
        self.convert_to_parent_button.setEnabled(False)
        self.add_sibling_button.setEnabled(False)

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
        """Apply pending changes to the task."""
        if self.current_task_id is None:
            return

        if not self._validate_changes():
            return

        # Handle dependencies separately (use add/remove_dependency calls)
        if "dependencies" in self.pending_changes:
            # Get original dependencies
            project = self.controller.get_project()
            node_id = self.current_task_id
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
        current_version = project.dag.current_version_id

        for dep in dependencies:
            # Get target node title
            target_id = dep.target_node_id
            target_title = "Unknown"

            # Determine target type using type-safe function
            try:
                as_task, as_branch, as_world = type_explode_id(target_id)

                if as_world is not None:
                    # Parse possible world reference
                    branch_node_id = as_world.branch_id
                    world_id = as_world.world_id

                    # Find the branch and possible world
                    if branch_node_id in project.dag.node_map:
                        branch_persistent_id = project.dag.node_map[branch_node_id]

                        if branch_persistent_id in project.persistent_branches:
                            persistent_branch = project.persistent_branches[
                                branch_persistent_id
                            ]
                            if current_version in persistent_branch.versions:
                                branch = persistent_branch.versions[current_version]

                                # Find the specific possible world
                                for pw in branch.possible_worlds:
                                    if pw.id == world_id:
                                        target_title = (
                                            f"{pw.title} (from {branch.title})"
                                        )
                                        break
                elif as_task is not None:
                    task_node_id = as_task
                    if task_node_id in project.dag.node_map:
                        persistent_id = project.dag.node_map[task_node_id]

                        if persistent_id in project.persistent_tasks:
                            persistent_task = project.persistent_tasks[persistent_id]
                            if current_version in persistent_task.versions:
                                target_title = persistent_task.versions[
                                    current_version
                                ].title
                elif as_branch is not None:
                    branch_node_id_2 = as_branch
                    if branch_node_id_2 in project.dag.node_map:
                        persistent_id = project.dag.node_map[branch_node_id_2]

                        if persistent_id in project.persistent_branches:
                            persistent_branch = project.persistent_branches[
                                persistent_id
                            ]
                            if current_version in persistent_branch.versions:
                                target_title = persistent_branch.versions[
                                    current_version
                                ].title
            except ValueError:
                # Unknown target type - leave as "Unknown"
                pass

            # Format dependency display
            source_ep = dep.source_endpoint.value
            target_ep = dep.target_endpoint.value
            constraint = dep.constraint_type.value
            if constraint == ">=":
                constraint = "≥"

            item_text = f"{source_ep} {constraint} {target_title}.{target_ep}"
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
            node_id = self.current_task_id
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

    def _is_required_dependency(self, dependency: Dependency) -> bool:
        """Check if a dependency is a required parent-child dependency.

        Args:
            dependency: Dependency to check

        Returns:
            True if the dependency is required (part of parent-child relationship)
        """
        if self.current_task_id is None:
            return False

        project = self.controller.get_project()
        node_id = self.current_task_id

        if node_id not in project.dag.node_map:
            return False

        persistent_id = project.dag.node_map[node_id]
        if persistent_id not in project.persistent_tasks:
            return False

        persistent_task = project.persistent_tasks[persistent_id]
        current_version = project.dag.current_version_id
        if current_version not in persistent_task.versions:
            return False

        task = persistent_task.versions[current_version]

        # Check if this is a subtask's required "start >= parent.start" dependency
        if task.parent_id is not None and (
            dependency.source_endpoint == Endpoint.START
            and dependency.target_node_id == task.parent_id
            and dependency.target_endpoint == Endpoint.START
            and dependency.constraint_type == ConstraintType.GREATER_EQUAL
        ):
            return True

        # Check if this is a parent's required "end >= child.end" dependency
        for child_id in task.children:
            if (
                dependency.source_endpoint == Endpoint.END
                and dependency.target_node_id == child_id
                and dependency.target_endpoint == Endpoint.END
                and dependency.constraint_type == ConstraintType.GREATER_EQUAL
            ):
                return True

        return False

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
            node_id = self.current_task_id
            persistent_id = project.dag.node_map[node_id]
            persistent_task = project.persistent_tasks[persistent_id]
            task = persistent_task.versions[project.dag.current_version_id]
            current_deps = task.dependencies.copy()

        # Check if the dependency is required before removing
        if 0 <= selected_index < len(current_deps):
            dependency = current_deps[selected_index]

            if self._is_required_dependency(dependency):
                QMessageBox.warning(
                    self,
                    "Cannot Remove Dependency",
                    "This dependency is required for the parent-child relationship "
                    "and cannot be removed.",
                )
                return

            # Remove dependency at index
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

    def _on_convert_to_parent(self) -> None:
        """Convert the current task to a parent task with one child."""
        if self.current_task_id is None:
            return

        # Prompt for child title
        child_title, ok = QInputDialog.getText(
            self, "Convert to Parent", "Enter title for the new child task:"
        )

        if not ok or not child_title.strip():
            return  # User cancelled or entered empty title

        try:
            # Call controller method
            self.controller.convert_to_parent(self.current_task_id, child_title)
            # Controller will select the new child, so editor will reload automatically
        except Exception as e:
            # TODO: Show error dialog
            print(f"Error converting to parent: {e}")

    def _on_add_sibling(self) -> None:
        """Add a sibling subtask to the current task."""
        if self.current_task_id is None:
            return

        # Prompt for sibling title
        sibling_title, ok = QInputDialog.getText(
            self, "Add Sibling", "Enter title for the new sibling task:"
        )

        if not ok or not sibling_title.strip():
            return  # User cancelled or entered empty title

        try:
            # Call controller method with no duration distribution
            # User can set it later if needed
            self.controller.add_sibling(self.current_task_id, sibling_title, None)
            # Controller will select the new sibling, so editor will reload
            # automatically
        except Exception as e:
            # TODO: Show error dialog
            print(f"Error adding sibling: {e}")

    # Allowed Workers methods

    def _load_allowed_workers(self, allowed_workers: list[WorkerId] | None) -> None:
        """Load allowed workers into the UI.

        Args:
            allowed_workers: List of allowed worker IDs, or None if all are allowed
        """
        self.allowed_workers_list.clear()

        if allowed_workers is None or len(allowed_workers) == 0:
            # Show empty state
            self.allowed_workers_empty_label.setVisible(True)
            self.allowed_workers_list.setVisible(False)
            self.allowed_workers_button_container.setVisible(False)
        else:
            # Show populated list
            self.allowed_workers_empty_label.setVisible(False)
            self.allowed_workers_list.setVisible(True)
            self.allowed_workers_button_container.setVisible(True)

            # Get worker names from controller
            workers = self.controller.get_workers()
            worker_map = {w.id: w for w in workers}

            for worker_id in allowed_workers:
                if worker_id in worker_map:
                    worker = worker_map[worker_id]
                    display_name = worker.name
                    if worker.worker_id:
                        display_name += f" ({worker.worker_id})"
                    self.allowed_workers_list.addItem(display_name)
                else:
                    # Worker not found - might have been deleted
                    self.allowed_workers_list.addItem(f"Unknown ({worker_id})")

    def _on_restrict_workers_clicked(self, link: str) -> None:
        """Handle click on the 'restrict to specific workers' link.

        Args:
            link: Link URL (ignored, just used to trigger the click)
        """
        # Switch to restricted mode with empty list
        # User will need to add workers
        self.allowed_workers_empty_label.setVisible(False)
        self.allowed_workers_list.setVisible(True)
        self.allowed_workers_button_container.setVisible(True)

        # Set pending change to empty list (will be normalized to None if left empty)
        self.pending_changes["allowed_workers"] = []
        self._update_button_states()

    def _on_allowed_worker_selection_changed(self) -> None:
        """Handle allowed worker list selection changes."""
        has_selection = len(self.allowed_workers_list.selectedItems()) > 0
        self.remove_allowed_worker_button.setEnabled(has_selection)

    def _on_add_allowed_worker(self) -> None:
        """Add a worker to the allowed workers list."""
        # Get all workers
        workers = self.controller.get_workers()
        if not workers:
            QMessageBox.information(
                self,
                "No Workers",
                "There are no workers in the project. "
                "Add workers first using the Edit Workers button.",
            )
            return

        # Get current allowed workers from pending changes or task
        current_allowed: list[WorkerId] = []
        if "allowed_workers" in self.pending_changes:
            current_allowed = list(self.pending_changes["allowed_workers"] or [])
        elif self.current_task_id is not None:
            project = self.controller.get_project()
            node_id = self.current_task_id
            if node_id in project.dag.node_map:
                persistent_id = project.dag.node_map[node_id]
                if persistent_id in project.persistent_tasks:
                    persistent_task = project.persistent_tasks[persistent_id]
                    current_version = project.dag.current_version_id
                    if current_version in persistent_task.versions:
                        task = persistent_task.versions[current_version]
                        current_allowed = list(task.allowed_workers or [])

        # Build list of workers not already in the list
        available_workers = [w for w in workers if w.id not in current_allowed]
        if not available_workers:
            QMessageBox.information(
                self,
                "All Workers Added",
                "All available workers are already in the allowed list.",
            )
            return

        # Show dialog to select a worker
        worker_names = []
        for w in available_workers:
            name = w.name
            if w.worker_id:
                name += f" ({w.worker_id})"
            worker_names.append(name)

        selected_name, ok = QInputDialog.getItem(
            self,
            "Add Allowed Worker",
            "Select a worker to allow:",
            worker_names,
            0,
            False,
        )

        if not ok:
            return

        # Find the selected worker
        selected_index = worker_names.index(selected_name)
        selected_worker = available_workers[selected_index]

        # Add to the list
        current_allowed.append(selected_worker.id)
        self.pending_changes["allowed_workers"] = current_allowed
        self._load_allowed_workers(current_allowed)
        self._update_button_states()

    def _on_remove_allowed_worker(self) -> None:
        """Remove selected worker from the allowed workers list."""
        selected_items = self.allowed_workers_list.selectedItems()
        if not selected_items:
            return

        selected_index = self.allowed_workers_list.row(selected_items[0])

        # Get current allowed workers
        current_allowed: list[WorkerId] = []
        if "allowed_workers" in self.pending_changes:
            current_allowed = list(self.pending_changes["allowed_workers"] or [])
        elif self.current_task_id is not None:
            project = self.controller.get_project()
            node_id = self.current_task_id
            if node_id in project.dag.node_map:
                persistent_id = project.dag.node_map[node_id]
                if persistent_id in project.persistent_tasks:
                    persistent_task = project.persistent_tasks[persistent_id]
                    current_version = project.dag.current_version_id
                    if current_version in persistent_task.versions:
                        task = persistent_task.versions[current_version]
                        current_allowed = list(task.allowed_workers or [])

        if 0 <= selected_index < len(current_allowed):
            current_allowed.pop(selected_index)
            self.pending_changes["allowed_workers"] = current_allowed
            self._load_allowed_workers(current_allowed)
            self._update_button_states()

    def _on_allow_all_workers(self) -> None:
        """Reset to allowing all workers."""
        self.pending_changes["allowed_workers"] = None
        self._load_allowed_workers(None)
        self._update_button_states()

    # Excluded Assignees methods

    def _load_excluded_assignees(self, excluded_tasks: list[TaskId]) -> None:
        """Load excluded assignee tasks into the UI.

        Args:
            excluded_tasks: List of task IDs whose assignees are excluded
        """
        self.excluded_assignees_list.clear()

        if not excluded_tasks:
            return

        project = self.controller.get_project()
        current_version = project.dag.current_version_id

        for task_id in excluded_tasks:
            # Get task title
            node_id: NodeId = task_id
            if node_id in project.dag.node_map:
                persistent_id = project.dag.node_map[node_id]
                if persistent_id in project.persistent_tasks:
                    persistent_task = project.persistent_tasks[persistent_id]
                    if current_version in persistent_task.versions:
                        task = persistent_task.versions[current_version]
                        self.excluded_assignees_list.addItem(task.title)
                        continue

            # Task not found
            self.excluded_assignees_list.addItem(f"Unknown ({task_id})")

    def _on_excluded_assignee_selection_changed(self) -> None:
        """Handle excluded assignee list selection changes."""
        has_selection = len(self.excluded_assignees_list.selectedItems()) > 0
        self.remove_excluded_task_button.setEnabled(has_selection)

    def _get_current_excluded_tasks(self) -> list[TaskId]:
        """Get the current list of excluded task IDs.

        Returns:
            List of task IDs from pending changes or current task
        """
        if "excluded_worker_tasks" in self.pending_changes:
            return list(self.pending_changes["excluded_worker_tasks"])

        if self.current_task_id is None:
            return []

        project = self.controller.get_project()
        node_id = self.current_task_id
        if node_id not in project.dag.node_map:
            return []

        persistent_id = project.dag.node_map[node_id]
        if persistent_id not in project.persistent_tasks:
            return []

        persistent_task = project.persistent_tasks[persistent_id]
        current_version = project.dag.current_version_id
        if current_version not in persistent_task.versions:
            return []

        task = persistent_task.versions[current_version]
        return list(task.excluded_worker_tasks)

    def _get_available_tasks_for_exclusion(self) -> list[tuple[TaskId, str]]:
        """Get list of tasks that can be added to excluded assignees.

        Returns:
            List of (task_id, title) tuples for tasks that can be excluded
        """
        if self.current_task_id is None:
            return []

        project = self.controller.get_project()
        current_version = project.dag.current_version_id
        current_excluded = self._get_current_excluded_tasks()

        available_tasks: list[tuple[TaskId, str]] = []

        for node_id, persistent_id in project.dag.node_map.items():
            # Skip if it's the current task
            if node_id == self.current_task_id:
                continue

            # Skip if not a task
            if persistent_id not in project.persistent_tasks:
                continue

            # Skip if already in the excluded list
            task_id = TaskId(str(node_id))
            if task_id in current_excluded:
                continue

            # Get task title
            persistent_task = project.persistent_tasks[persistent_id]
            if current_version not in persistent_task.versions:
                continue

            task = persistent_task.versions[current_version]
            available_tasks.append((task_id, task.title))

        return available_tasks

    def _on_add_excluded_task(self) -> None:
        """Enter select-task mode to add a task to the excluded assignees list."""
        if self.current_task_id is None:
            return

        # Emit signal to enter select-task mode
        self.select_excluded_task_requested.emit()

    def set_excluded_task(self, node_id: NodeId) -> None:
        """Handle a task selected for exclusion.

        Called by MainWindow when user selects a task in select-task mode.

        Args:
            node_id: The ID of the selected node
        """
        # Validate it's a task (not a branch) using type_explode_id
        as_task, as_branch, _ = type_explode_id(node_id)
        if as_task is None:
            QMessageBox.warning(
                self,
                "Invalid Selection",
                "Please select a task, not a branch.",
            )
            return

        selected_task_id = as_task

        # Check if it's the current task
        if selected_task_id == self.current_task_id:
            QMessageBox.warning(
                self,
                "Invalid Selection",
                "A task cannot exclude its own assignee.",
            )
            return

        # Check if already in exclusion list
        current_excluded = self._get_current_excluded_tasks()
        if selected_task_id in current_excluded:
            QMessageBox.information(
                self,
                "Already Excluded",
                "This task is already in the exclusion list.",
            )
            return

        # Get task name for messages
        project = self.controller.get_project()
        current_version = project.dag.current_version_id
        selected_name = "the selected task"

        persistent_id = project.dag.node_map.get(selected_task_id)
        if persistent_id and persistent_id in project.persistent_tasks:
            persistent_task = project.persistent_tasks[persistent_id]
            if current_version in persistent_task.versions:
                selected_name = persistent_task.versions[current_version].title

        # Check if the required dependency exists
        if self.current_task_id is None:
            return

        has_dep = has_required_exclusion_dependency(
            project, self.current_task_id, selected_task_id
        )

        if not has_dep:
            # Ask user if they want to add the required dependency
            msg = (
                f"To exclude the assignee of '{selected_name}', "
                f"a dependency is required:\n"
                f"  this task.start >= {selected_name}.start\n\n"
                f"This ensures the excluded task's assignee is known "
                f"before this task starts.\n\n"
                f"Would you like to add this dependency automatically?"
            )
            reply = QMessageBox.question(
                self,
                "Required Dependency Missing",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if reply == QMessageBox.StandardButton.Yes:
                # Add the required dependency to pending changes
                required_dep = get_required_exclusion_dependency(selected_task_id)
                self._add_dependency_to_pending(required_dep)
            else:
                return  # User chose not to add, cancel the operation

        # Add to the list
        current_excluded.append(selected_task_id)
        self.pending_changes["excluded_worker_tasks"] = current_excluded
        self._load_excluded_assignees(current_excluded)
        self._update_button_states()

    def _add_dependency_to_pending(self, dependency: Dependency) -> None:
        """Add a dependency to pending changes.

        Args:
            dependency: The dependency to add
        """
        # Get current dependencies
        if "dependencies" in self.pending_changes:
            current_deps = list(self.pending_changes["dependencies"])
        else:
            project = self.controller.get_project()
            if self.current_task_id is None:
                return
            node_id = self.current_task_id
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
            current_deps = list(task.dependencies)

        # Add the new dependency if not already present
        if dependency not in current_deps:
            current_deps.append(dependency)
            self.pending_changes["dependencies"] = current_deps
            self._load_dependencies(current_deps)

    def _on_remove_excluded_task(self) -> None:
        """Remove selected task from the excluded assignees list."""
        selected_items = self.excluded_assignees_list.selectedItems()
        if not selected_items:
            return

        selected_index = self.excluded_assignees_list.row(selected_items[0])
        current_excluded = self._get_current_excluded_tasks()

        if 0 <= selected_index < len(current_excluded):
            current_excluded.pop(selected_index)
            self.pending_changes["excluded_worker_tasks"] = current_excluded
            self._load_excluded_assignees(current_excluded)
            self._update_button_states()
