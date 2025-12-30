"""Left panel containing DAG visualization and list view."""

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from fluxx.gui.controller import ProjectController
from fluxx.gui.widgets.dag_view.dag_graphics_view import DAGGraphicsView


class DAGPanel(QWidget):
    """Left panel showing DAG visualization or list view.

    This panel will contain:
    - Control bar with history label, view toggle, and Add Root Node button
    - Stacked widget switching between DAG graphics view and list view

    Currently showing DAGGraphicsView (Phase 2).
    Control bar and list view will be added in later phases.
    """

    def __init__(self, controller: ProjectController) -> None:
        """Initialize the DAG panel.

        Args:
            controller: Project controller instance
        """
        super().__init__()
        self.controller = controller

        # Create DAG graphics view
        self.dag_view = DAGGraphicsView(controller)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.dag_view)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
