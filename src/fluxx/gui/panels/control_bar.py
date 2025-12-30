"""Control bar for DAG panel."""

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from fluxx.gui.controller import ProjectController


class ControlBar(QWidget):
    """Control bar with view toggle and other controls.

    Features:
    - View toggle button (DAG/List)
    - History label
    - Add root node button (future)
    """

    def __init__(self, controller: ProjectController) -> None:
        """Initialize control bar.

        Args:
            controller: Project controller instance
        """
        super().__init__()
        self.controller = controller
        self.is_list_view = False  # Start with DAG view

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # History label (placeholder for future history navigation)
        self.history_label = QLabel("Current Version")
        layout.addWidget(self.history_label)

        layout.addStretch()

        # View toggle button
        self.view_toggle_button = QPushButton("List View")
        self.view_toggle_button.setToolTip("Switch between DAG and List views")
        self.view_toggle_button.clicked.connect(self._on_toggle_view)
        layout.addWidget(self.view_toggle_button)

        # Add root node button (future feature)
        # self.add_root_button = QPushButton("Add Root Node")
        # layout.addWidget(self.add_root_button)

        self.setLayout(layout)

    def _on_toggle_view(self) -> None:
        """Handle view toggle button click."""
        self.is_list_view = not self.is_list_view

        # Update button text
        if self.is_list_view:
            self.view_toggle_button.setText("DAG View")
        else:
            self.view_toggle_button.setText("List View")

        # Emit signal to parent to switch views
        # (This will be handled by DAGPanel directly)

    def get_current_view(self) -> str:
        """Get the current view type.

        Returns:
            "list" or "dag"
        """
        return "list" if self.is_list_view else "dag"
