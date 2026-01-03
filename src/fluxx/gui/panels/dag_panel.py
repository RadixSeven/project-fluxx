"""Left panel containing DAG visualization and list view."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from fluxx.gui.controller import ProjectController
from fluxx.gui.panels.control_bar import ControlBar
from fluxx.gui.widgets.dag_view.dag_graphics_view import DAGGraphicsView
from fluxx.gui.widgets.list_view.node_list_widget import NodeListWidget


class DAGPanel(QWidget):
    """Left panel showing DAG visualization or list view.

    This panel contains:
    - Control bar with history label and view toggle button
    - Stacked widget switching between DAG graphics view and list view

    Signals:
        edit_workers_requested: Emitted when Edit Workers button is clicked
    """

    edit_workers_requested = Signal()

    def __init__(self, controller: ProjectController) -> None:
        """Initialize the DAG panel.

        Args:
            controller: Project controller instance
        """
        super().__init__()
        self.controller = controller

        # Create control bar
        self.control_bar = ControlBar(controller)
        self.control_bar.view_toggle_button.clicked.connect(self._switch_view)
        self.control_bar.edit_workers_clicked.connect(self.edit_workers_requested.emit)

        # Create stacked widget for views
        self.view_stack = QStackedWidget()

        # Create DAG graphics view
        self.dag_view = DAGGraphicsView(controller)
        self.view_stack.addWidget(self.dag_view)

        # Create list view
        self.list_view = NodeListWidget(controller)
        self.view_stack.addWidget(self.list_view)

        # Start with DAG view
        self.view_stack.setCurrentWidget(self.dag_view)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.control_bar)
        layout.addWidget(self.view_stack)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def _switch_view(self) -> None:
        """Switch between DAG and List views."""
        current_view = self.control_bar.get_current_view()

        if current_view == "list":
            self.view_stack.setCurrentWidget(self.list_view)
        else:
            self.view_stack.setCurrentWidget(self.dag_view)
