"""Right panel containing node editors."""

from PyQt6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from fluxx.data.models import NodeId
from fluxx.gui.controller import ProjectController


class EditorPanel(QWidget):
    """Right panel showing node editors.

    This panel will contain:
    - Stacked widget switching between:
      - Empty state: "Select a node to edit"
      - TaskEditor when task is selected
      - BranchEditor when branch is selected
      - WorkerEditor in workers mode

    Currently a placeholder for Phase 3 implementation.
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

        # Create placeholder editor widget
        self.editor_widget = QWidget()
        editor_layout = QVBoxLayout()
        editor_label = QLabel("Editor - Coming Soon")
        editor_label.setStyleSheet("font-size: 16px; padding: 20px;")
        editor_layout.addWidget(editor_label)
        self.editor_widget.setLayout(editor_layout)
        self.stack.addWidget(self.editor_widget)

        # Main layout
        layout = QVBoxLayout()
        layout.addWidget(self.stack)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Connect to controller signals
        self.controller.selection_changed.connect(self._on_selection_changed)

        # Initialize view
        self._update_view()

    def _on_selection_changed(self, node_id: NodeId | None) -> None:
        """Handle selection changes.

        Args:
            node_id: Selected node ID or None
        """
        self._update_view()

    def _update_view(self) -> None:
        """Update the displayed editor based on selection."""
        selected_node_id = self.controller.get_selected_node_id()

        if selected_node_id is None:
            # Show empty state
            self.stack.setCurrentWidget(self.empty_widget)
        else:
            # Show placeholder editor
            # In Phase 3, this will switch to TaskEditor or BranchEditor
            self.stack.setCurrentWidget(self.editor_widget)
