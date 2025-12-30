"""Widget for editing a single dependency inline."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fluxx.data.models import ConstraintType, Dependency, Endpoint, NodeId
from fluxx.gui.controller import ProjectController


class DependencyEditorWidget(QWidget):
    """Inline widget for editing a dependency.

    Signals:
        select_target_requested: Emitted when user clicks Select Target button
        dependency_changed: Emitted when dependency fields change
        confirmed: Emitted when user confirms the dependency
        cancelled: Emitted when user cancels editing
    """

    select_target_requested = Signal()
    dependency_changed = Signal()
    confirmed = Signal()
    cancelled = Signal()

    def __init__(
        self,
        controller: ProjectController,
        is_branch: bool = False,
        parent: QWidget | None = None,
    ):
        """Initialize dependency editor widget.

        Args:
            controller: Project controller
            is_branch: True if editing a branch dependency (source is always occurrence)
            parent: Parent widget
        """
        super().__init__(parent)
        self.controller = controller
        self.is_branch = is_branch
        self._target_node_id: NodeId | None = None

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Group box for dependency editing
        group = QGroupBox("Dependency")
        group_layout = QVBoxLayout()

        # Source endpoint (only for tasks, branches always use occurrence)
        if not self.is_branch:
            source_label = QLabel("Source Endpoint:")
            self.source_endpoint_combo = QComboBox()
            self.source_endpoint_combo.addItem("Start", Endpoint.START)
            self.source_endpoint_combo.addItem("End", Endpoint.END)
            self.source_endpoint_combo.currentIndexChanged.connect(
                self._on_field_changed
            )
            group_layout.addWidget(source_label)
            group_layout.addWidget(self.source_endpoint_combo)

        # Constraint type
        constraint_label = QLabel("Constraint Type:")
        self.constraint_type_combo = QComboBox()
        self.constraint_type_combo.addItem("Greater Than or Equal (>=)", ">=")
        self.constraint_type_combo.addItem("Equal (=)", "=")
        self.constraint_type_combo.currentIndexChanged.connect(self._on_field_changed)
        group_layout.addWidget(constraint_label)
        group_layout.addWidget(self.constraint_type_combo)

        # Target node selection
        target_label = QLabel("Target Node:")
        self.target_display = QLabel("<Not selected>")
        self.target_display.setStyleSheet("color: gray; font-style: italic;")

        select_button = QPushButton("Select Target")
        select_button.clicked.connect(self._on_select_target)

        target_layout = QHBoxLayout()
        target_layout.addWidget(self.target_display, 1)
        target_layout.addWidget(select_button)

        group_layout.addWidget(target_label)
        group_layout.addLayout(target_layout)

        # Target endpoint
        target_endpoint_label = QLabel("Target Endpoint:")
        self.target_endpoint_combo = QComboBox()
        self.target_endpoint_combo.addItem("Start", Endpoint.START)
        self.target_endpoint_combo.addItem("End", Endpoint.END)
        self.target_endpoint_combo.addItem("Occurrence", Endpoint.OCCURRENCE)
        self.target_endpoint_combo.currentIndexChanged.connect(self._on_field_changed)
        group_layout.addWidget(target_endpoint_label)
        group_layout.addWidget(self.target_endpoint_combo)

        # Buttons
        button_layout = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self._on_cancel)
        button_layout.addWidget(cancel_button)
        button_layout.addStretch()

        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self._on_add)
        self.add_button.setEnabled(False)  # Disabled until target is selected
        button_layout.addWidget(self.add_button)

        group_layout.addLayout(button_layout)

        group.setLayout(group_layout)
        layout.addWidget(group)

        self.setLayout(layout)

    def _on_select_target(self) -> None:
        """Handle Select Target button click."""
        self.select_target_requested.emit()

    def _on_field_changed(self) -> None:
        """Handle field value changes."""
        # Enable Add button only if target is selected
        self.add_button.setEnabled(self._target_node_id is not None)
        self.dependency_changed.emit()

    def _on_add(self) -> None:
        """Handle Add button click."""
        # Only emit if we have a valid dependency
        if self.get_dependency() is not None:
            self.confirmed.emit()

    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        self.cancelled.emit()

    def set_target_node(self, node_id: NodeId) -> None:
        """Set the selected target node.

        Args:
            node_id: ID of the selected target node
        """
        self._target_node_id = node_id

        # Get node info to display
        project = self.controller.get_project()
        persistent_id = project.dag.node_map.get(node_id)
        if persistent_id is None:
            self.target_display.setText("<Invalid node>")
            self.target_display.setStyleSheet("color: red; font-style: italic;")
            return

        # Check if it's a task or branch
        current_version = project.dag.current_version_id

        if persistent_id in project.persistent_tasks:
            persistent_task = project.persistent_tasks[persistent_id]
            if current_version in persistent_task.versions:
                task = persistent_task.versions[current_version]
                self.target_display.setText(f"Task: {task.title}")
                self.target_display.setStyleSheet("color: black;")
                # Enable start/end, disable occurrence
                model = self.target_endpoint_combo.model()
                if isinstance(model, QStandardItemModel):
                    model.item(0).setEnabled(True)  # Start
                    model.item(1).setEnabled(True)  # End
                    model.item(2).setEnabled(False)  # Occurrence
                if (
                    self.target_endpoint_combo.currentData() == Endpoint.OCCURRENCE
                ):  # Reset if was occurrence
                    self.target_endpoint_combo.setCurrentIndex(0)

        elif persistent_id in project.persistent_branches:
            persistent_branch = project.persistent_branches[persistent_id]
            if current_version in persistent_branch.versions:
                branch = persistent_branch.versions[current_version]
                self.target_display.setText(f"Branch: {branch.title}")
                self.target_display.setStyleSheet("color: black;")
                # Disable start/end, enable only occurrence
                model = self.target_endpoint_combo.model()
                if isinstance(model, QStandardItemModel):
                    model.item(0).setEnabled(False)  # Start
                    model.item(1).setEnabled(False)  # End
                    model.item(2).setEnabled(True)  # Occurrence
                # Auto-select occurrence for branches
                self.target_endpoint_combo.setCurrentIndex(2)

        self._on_field_changed()

    def get_dependency(self) -> Dependency | None:
        """Get the configured dependency.

        Returns:
            Configured Dependency object or None if incomplete
        """
        if self._target_node_id is None:
            return None

        # Get source endpoint
        if self.is_branch:
            source_endpoint = Endpoint.OCCURRENCE
        else:
            source_endpoint = self.source_endpoint_combo.currentData()

        # Get constraint type
        constraint_str = self.constraint_type_combo.currentData()
        constraint_type = (
            ConstraintType.GREATER_EQUAL
            if constraint_str == ">="
            else ConstraintType.EQUAL
        )

        # Get target endpoint
        target_endpoint = self.target_endpoint_combo.currentData()

        return Dependency(
            source_endpoint=source_endpoint,
            target_node_id=self._target_node_id,
            target_endpoint=target_endpoint,
            constraint_type=constraint_type,
        )

    def load_dependency(self, dependency: Dependency) -> None:
        """Load an existing dependency for editing.

        Args:
            dependency: Dependency to load
        """
        # Set source endpoint (if not branch)
        if not self.is_branch:
            if dependency.source_endpoint == Endpoint.START:
                self.source_endpoint_combo.setCurrentIndex(0)
            else:  # END
                self.source_endpoint_combo.setCurrentIndex(1)

        # Set constraint type
        if dependency.constraint_type == ConstraintType.GREATER_EQUAL:
            self.constraint_type_combo.setCurrentIndex(0)
        else:  # EQUAL
            self.constraint_type_combo.setCurrentIndex(1)

        # Set target node
        self.set_target_node(dependency.target_node_id)

        # Set target endpoint
        if dependency.target_endpoint == Endpoint.START:
            self.target_endpoint_combo.setCurrentIndex(0)
        elif dependency.target_endpoint == Endpoint.END:
            self.target_endpoint_combo.setCurrentIndex(1)
        else:  # OCCURRENCE
            self.target_endpoint_combo.setCurrentIndex(2)

    def clear(self) -> None:
        """Clear the editor fields."""
        self._target_node_id = None
        self.target_display.setText("<Not selected>")
        self.target_display.setStyleSheet("color: gray; font-style: italic;")

        if not self.is_branch:
            self.source_endpoint_combo.setCurrentIndex(0)

        self.constraint_type_combo.setCurrentIndex(0)
        self.target_endpoint_combo.setCurrentIndex(0)

        # Disable Add button when cleared
        self.add_button.setEnabled(False)
