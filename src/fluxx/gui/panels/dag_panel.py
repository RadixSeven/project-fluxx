"""Left panel containing DAG visualization and list view."""

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from fluxx.data.models import Project
from fluxx.gui.controller import ProjectController


class DAGPanel(QWidget):
    """Left panel showing DAG visualization or list view.

    This panel will contain:
    - Control bar with history label, view toggle, and Add Root Node button
    - Stacked widget switching between DAG graphics view and list view

    Currently a placeholder for Phase 2 implementation.
    """

    def __init__(self, controller: ProjectController) -> None:
        """Initialize the DAG panel.

        Args:
            controller: Project controller instance
        """
        super().__init__()
        self.controller = controller

        # Placeholder layout
        layout = QVBoxLayout()
        label = QLabel("DAG View - Coming Soon")
        label.setStyleSheet("font-size: 18px; padding: 20px;")
        layout.addWidget(label)
        self.setLayout(layout)

        # Connect to controller signals
        self.controller.project_changed.connect(self._on_project_changed)

    def _on_project_changed(self, project: Project) -> None:
        """Handle project changes.

        Args:
            project: Updated Project instance
        """
        # Placeholder - will update view in Phase 2
        pass
