"""Right panel containing node editors."""

from PySide6.QtWidgets import QLabel, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from fluxx.data.models import BranchId, NodeId, TaskId
from fluxx.gui.controller import ProjectController
from fluxx.gui.widgets.editors.branch_editor import BranchEditor
from fluxx.gui.widgets.editors.task_editor import TaskEditor
from fluxx.gui.widgets.editors.worker_editor import WorkerEditor


class EditorPanel(QWidget):
    """Right panel showing node editors.

    This panel will contain:
    - Stacked widget switching between:
      - Empty state: "Select a node to edit"
      - TaskEditor when task is selected
      - BranchEditor when branch is selected
      - WorkerEditor in workers mode
    """

    def __init__(self, controller: ProjectController) -> None:
        """Initialize the editor panel.

        Args:
            controller: Project controller instance
        """
        super().__init__()
        self.controller = controller

        # Create stacked widget
        self.stack = QStackedWidget()

        # Create empty state widget
        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout()
        empty_label = QLabel("Select a node to edit")
        empty_label.setStyleSheet("font-size: 16px; color: gray; padding: 20px;")
        empty_layout.addWidget(empty_label)
        self.empty_widget.setLayout(empty_layout)
        self.stack.addWidget(self.empty_widget)

        # Create task editor widget
        self.task_editor = TaskEditor(controller)
        self.stack.addWidget(self.task_editor)

        # Create branch editor widget
        self.branch_editor = BranchEditor(controller)
        self.stack.addWidget(self.branch_editor)

        # Create worker editor widget
        self.worker_editor = WorkerEditor(controller)
        self.stack.addWidget(self.worker_editor)

        # Main layout
        layout = QVBoxLayout()
        layout.addWidget(self.stack)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Connect to controller signals
        self.controller.selection_changed.connect(self._on_selection_changed)

        # Register selection validator
        self.controller.set_selection_validator(self._check_unsaved_changes)

        # Initialize view
        self._update_view()

    def _on_selection_changed(self, node_id: NodeId | None) -> None:
        """Handle selection changes.

        Args:
            node_id: Selected node ID or None
        """
        self._update_view()

    def _check_unsaved_changes(self, new_node_id: NodeId | None) -> bool:
        """Check for unsaved changes in the current editor.

        Args:
            new_node_id: The ID of the node being navigated to

        Returns:
            True if it's safe to proceed, False to cancel navigation
        """
        current_widget = self.stack.currentWidget()

        # Only task and branch editors have unsaved changes tracking
        if current_widget not in (self.task_editor, self.branch_editor):
            return True

        # Need to cast to use is_dirty/apply_changes/revert_changes
        # which are common to TaskEditor and BranchEditor
        editor: TaskEditor | BranchEditor = current_widget  # type: ignore

        if not editor.is_dirty():
            return True

        # Ask user
        msg = QMessageBox(self)
        msg.setWindowTitle("Unsaved Changes")
        msg.setText("The current node has unsaved changes.")
        msg.setInformativeText(
            "Do you want to apply them before leaving? "
            "If you don't apply, changes will be lost."
        )

        apply_button = msg.addButton("Apply", QMessageBox.ButtonRole.AcceptRole)
        revert_button = msg.addButton("Revert", QMessageBox.ButtonRole.DestructiveRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)

        msg.setDefaultButton(apply_button)
        msg.exec()

        clicked_button = msg.clickedButton()

        if clicked_button == apply_button:
            return editor.apply_changes()
        elif clicked_button == revert_button:
            editor.revert_changes()
            return True
        else:  # Cancel
            return False

    def _update_view(self) -> None:
        """Update the displayed editor based on selection."""
        selected_node_id = self.controller.get_selected_node_id()

        if selected_node_id is None:
            # Show empty state
            self.stack.setCurrentWidget(self.empty_widget)
        else:
            # Determine if it's a task or branch
            project = self.controller.get_project()

            if selected_node_id not in project.dag.node_map:
                self.stack.setCurrentWidget(self.empty_widget)
                return

            persistent_id = project.dag.node_map[selected_node_id]

            if persistent_id in project.persistent_tasks:
                # Show task editor
                self.task_editor.load_task(TaskId(str(selected_node_id)))
                self.stack.setCurrentWidget(self.task_editor)
            elif persistent_id in project.persistent_branches:
                # Show branch editor
                self.branch_editor.load_branch(BranchId(str(selected_node_id)))
                self.stack.setCurrentWidget(self.branch_editor)
            else:
                # Unknown node type
                self.stack.setCurrentWidget(self.empty_widget)

    def show_worker_editor(self) -> None:
        """Show the worker editor."""
        self.stack.setCurrentWidget(self.worker_editor)
