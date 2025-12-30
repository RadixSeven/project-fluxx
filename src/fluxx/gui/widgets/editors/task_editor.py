"""Task editor widget for editing task properties."""

from typing import Any

from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fluxx.data.models import (
    DurationDistribution,
    NodeId,
    ShiftedLognormal,
    TaskId,
    Triangular,
)
from fluxx.gui.controller import ProjectController


class TaskEditor(QWidget):
    """Widget for editing task properties.

    Features:
    - Title and description fields
    - Duration distribution type selector and parameters
    - Pending changes tracking
    - Validation with inline error messages
    - Apply/Revert/Delete actions
    """

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
        self.min_field.setPlaceholderText("Minimum")
        self.min_field.textChanged.connect(self._on_distribution_param_changed)
        self.distribution_params_layout.addRow("Min:", self.min_field)

        self.mode_field = QLineEdit()
        self.mode_field.setPlaceholderText("Most likely")
        self.mode_field.textChanged.connect(self._on_distribution_param_changed)
        self.distribution_params_layout.addRow("Mode:", self.mode_field)

        self.max_field = QLineEdit()
        self.max_field.setPlaceholderText("Maximum")
        self.max_field.textChanged.connect(self._on_distribution_param_changed)
        self.distribution_params_layout.addRow("Max:", self.max_field)

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
        self.min_field.setPlaceholderText("Minimum")
        self.min_field.textChanged.connect(self._on_distribution_param_changed)
        self.distribution_params_layout.addRow("Min:", self.min_field)

        self.mode_field = QLineEdit()
        self.mode_field.setPlaceholderText("Most likely")
        self.mode_field.textChanged.connect(self._on_distribution_param_changed)
        self.distribution_params_layout.addRow("Mode:", self.mode_field)

        self.percentile_95_field = QLineEdit()
        self.percentile_95_field.setPlaceholderText("95th percentile")
        self.percentile_95_field.textChanged.connect(
            self._on_distribution_param_changed
        )
        self.distribution_params_layout.addRow("95th %:", self.percentile_95_field)

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

        # Apply changes through controller
        self.controller.update_task(self.current_task_id, **self.pending_changes)

        # Clear pending changes
        self.pending_changes.clear()
        self._update_button_states()

    def _on_revert(self) -> None:
        """Revert pending changes and reload from controller."""
        if self.current_task_id is not None:
            self.load_task(self.current_task_id)

    def _on_delete(self) -> None:
        """Delete the current task."""
        # TODO: Implement task deletion
        # This will require adding a delete_task method to the controller
        pass
