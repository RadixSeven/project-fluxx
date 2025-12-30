"""Worker editor widget for managing project workers."""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fluxx.gui.controller import ProjectController

if TYPE_CHECKING:
    from fluxx.data.models import Project


class WorkerEditor(QWidget):
    """Editor for managing workers in the project.

    Features:
    - Table showing all workers
    - Add/Remove worker buttons
    - Inline editing of worker properties
    """

    def __init__(self, controller: ProjectController) -> None:
        """Initialize the worker editor.

        Args:
            controller: Project controller instance
        """
        super().__init__()
        self.controller = controller

        self._setup_ui()

        # Connect to controller signals
        self.controller.project_changed.connect(self._on_project_changed)

        # Initial load
        self._load_workers()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Title
        title_label = QLabel("Workers")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        # Workers table
        self.workers_table = QTableWidget()
        self.workers_table.setColumnCount(4)
        self.workers_table.setHorizontalHeaderLabels(
            ["Name", "Worker ID", "Hours/Day", "Description"]
        )
        header = self.workers_table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
        self.workers_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.workers_table.currentCellChanged.connect(self._on_worker_selection_changed)
        self.workers_table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.workers_table)

        # Buttons
        button_layout = QHBoxLayout()
        self.add_worker_button = QPushButton("Add Worker")
        self.add_worker_button.clicked.connect(self._on_add_worker)
        button_layout.addWidget(self.add_worker_button)

        self.remove_worker_button = QPushButton("Remove Worker")
        self.remove_worker_button.setEnabled(False)
        self.remove_worker_button.clicked.connect(self._on_remove_worker)
        button_layout.addWidget(self.remove_worker_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _on_project_changed(self, project: "Project") -> None:  # noqa: F821
        """Handle project changes by reloading workers.

        Args:
            project: Updated project instance
        """
        self._load_workers()

    def _load_workers(self) -> None:
        """Load all workers from the project into the table."""
        workers = self.controller.get_workers()

        # Block signals during load to prevent spurious updates
        self.workers_table.blockSignals(True)
        self.workers_table.setRowCount(len(workers))

        for i, worker in enumerate(workers):
            # Name (editable)
            name_item = QTableWidgetItem(worker.name)
            self.workers_table.setItem(i, 0, name_item)

            # Worker ID (optional, editable)
            worker_id_item = QTableWidgetItem(worker.worker_id or "")
            self.workers_table.setItem(i, 1, worker_id_item)

            # Hours per day (editable)
            hours_item = QTableWidgetItem(str(worker.hours_per_workday))
            self.workers_table.setItem(i, 2, hours_item)

            # Description (optional, editable)
            desc_item = QTableWidgetItem(worker.description or "")
            self.workers_table.setItem(i, 3, desc_item)

            # Store worker ID in row
            name_item_for_data = self.workers_table.item(i, 0)
            if name_item_for_data is not None:
                name_item_for_data.setData(Qt.ItemDataRole.UserRole, worker.id)

        self.workers_table.blockSignals(False)

    def _on_cell_changed(self, row: int, column: int) -> None:
        """Handle cell changes by updating the worker.

        Args:
            row: Row index
            column: Column index
        """
        # Get worker ID from row
        name_item = self.workers_table.item(row, 0)
        if name_item is None:
            return

        worker_id = name_item.data(Qt.ItemDataRole.UserRole)
        if worker_id is None:
            return

        # Get updated values
        name_cell_item = self.workers_table.item(row, 0)
        if name_cell_item is None:
            return
        name = name_cell_item.text()
        worker_optional_id_item = self.workers_table.item(row, 1)
        worker_optional_id = (
            worker_optional_id_item.text() if worker_optional_id_item else None
        )
        if worker_optional_id == "":
            worker_optional_id = None

        hours_item = self.workers_table.item(row, 2)
        try:
            hours = float(hours_item.text()) if hours_item else 8.0
        except ValueError:
            hours = 8.0  # Default if invalid

        desc_item = self.workers_table.item(row, 3)
        description = desc_item.text() if desc_item else None
        if description == "":
            description = None

        # Update the worker
        self.controller.update_worker(
            worker_id=worker_id,
            name=name,
            hours_per_workday=hours,
            worker_optional_id=worker_optional_id,
            description=description,
        )

    def _on_add_worker(self) -> None:
        """Handle add worker button click."""
        # Add a new worker with default values
        self.controller.add_worker(
            name="New Worker",
            hours_per_workday=8.0,
        )

    def _on_remove_worker(self) -> None:
        """Handle remove worker button click."""
        # Get selected row
        current_row = self.workers_table.currentRow()
        if current_row < 0:
            return

        # Get worker ID from row
        name_item = self.workers_table.item(current_row, 0)
        if name_item is None:
            return

        worker_id = name_item.data(Qt.ItemDataRole.UserRole)
        if worker_id is None:
            return

        # Remove the worker
        self.controller.remove_worker(worker_id)

    def _on_worker_selection_changed(
        self,
        current_row: int,
        current_column: int,
        previous_row: int,
        previous_column: int,
    ) -> None:
        """Handle worker table selection changes.

        Args:
            current_row: Current row index
            current_column: Current column index
            previous_row: Previous row index
            previous_column: Previous column index
        """
        # Enable/disable remove button based on selection
        self.remove_worker_button.setEnabled(current_row >= 0)
