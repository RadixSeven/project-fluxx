"""Dialog for configuring and running project simulations."""

from datetime import UTC, datetime

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from fluxx.data.models import Project, Sample, Worker
from fluxx.simulation.engine import SimulationEngine


class SimulationDialog(QDialog):
    """Dialog to configure and run a Monte Carlo simulation.

    Allows user to specify:
    - Number of simulation samples
    - Project start date

    Uses the workers defined in the project.

    Runs the simulation and emits results when complete.

    Signals:
        simulation_completed: Emitted when simulation finishes successfully,
            with list of Sample objects as parameter
    """

    simulation_completed: Signal = Signal(list)

    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        """Initialize the simulation dialog.

        Args:
            project: The project to simulate
            parent: Parent widget
        """
        super().__init__(parent)
        self.project = project

        self.setWindowTitle("Run Simulation")
        self.setModal(True)
        self.resize(400, 250)

        # Create UI
        self._create_widgets()
        self._create_layout()
        self._connect_signals()

    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        # Input fields
        self.num_samples_spin = QSpinBox()
        self.num_samples_spin.setMinimum(1)
        self.num_samples_spin.setMaximum(1000000)
        self.num_samples_spin.setValue(1000)

        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        today = datetime.now(UTC).date()
        self.start_date_edit.setDate(QDate(today.year, today.month, today.day))

        # Workers info label
        worker_count = len(self.project.workers)
        if worker_count == 0:
            workers_text = "No workers defined (add workers first)"
        elif worker_count == 1:
            workers_text = f"1 worker: {self.project.workers[0].name}"
        else:
            worker_names = ", ".join(w.name for w in self.project.workers[:3])
            if worker_count > 3:
                worker_names += f", ... (+{worker_count - 3} more)"
            workers_text = f"{worker_count} workers: {worker_names}"
        self.workers_label = QLabel(workers_text)

        # Progress widgets (initially hidden)
        self.progress_label = QLabel("Running simulation...")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_label.hide()
        self.progress_bar.hide()

        # Buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.run_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        assert self.run_button is not None
        self.run_button.setText("Run")

        # Disable Run button if no workers and add tooltip
        if worker_count == 0:
            self.run_button.setEnabled(False)
            self.run_button.setToolTip("Add workers to the project to run a simulation")

    def _create_layout(self) -> None:
        """Create dialog layout."""
        layout = QVBoxLayout()

        # Form for input fields
        form = QFormLayout()
        form.addRow("Number of samples:", self.num_samples_spin)
        form.addRow("Start date:", self.start_date_edit)
        form.addRow("Workers:", self.workers_label)

        layout.addLayout(form)
        layout.addSpacing(20)

        # Progress widgets
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        layout.addStretch()

        # Buttons
        layout.addWidget(self.button_box)

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.button_box.accepted.connect(self._on_run)
        self.button_box.rejected.connect(self.reject)

    def _on_run(self) -> None:
        """Handle Run button click."""
        # Check for workers
        if not self.project.workers:
            QMessageBox.warning(
                self,
                "No Workers",
                "Please add workers to the project before running a simulation.",
            )
            return

        # Get parameters
        num_samples = self.num_samples_spin.value()
        start_date_qdate = self.start_date_edit.date()
        start_date = datetime(
            start_date_qdate.year(),
            start_date_qdate.month(),
            start_date_qdate.day(),
            9,
            0,
            0,
            tzinfo=UTC,
        )

        # Disable inputs and show progress
        self._set_inputs_enabled(False)
        self.progress_label.show()
        self.progress_bar.show()
        self.progress_bar.setValue(0)

        # Run simulation using project workers
        # NOTE: This is synchronous and will block the UI
        # For better UX, this should be moved to a worker thread in the future
        try:
            samples = self._run_simulation(
                num_samples, start_date, list(self.project.workers)
            )

            # Emit results
            self.simulation_completed.emit(samples)

            # Close dialog
            self.accept()
        except Exception:
            # Re-enable inputs on error
            self._set_inputs_enabled(True)
            self.progress_label.hide()
            self.progress_bar.hide()
            # Re-raise to let caller handle
            raise

    def _run_simulation(
        self, num_samples: int, start_date: datetime, workers: list[Worker]
    ) -> list[Sample]:
        """Run the simulation.

        Args:
            num_samples: Number of samples to generate
            start_date: Project start date
            workers: List of workers

        Returns:
            List of simulation samples
        """
        engine = SimulationEngine(num_samples=num_samples, start_date=start_date)
        samples = engine.run(self.project, workers)
        self.progress_bar.setValue(100)
        return samples

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """Enable or disable input widgets.

        Args:
            enabled: Whether to enable inputs
        """
        self.num_samples_spin.setEnabled(enabled)
        self.start_date_edit.setEnabled(enabled)
        # Only enable Run button if there are workers
        if enabled and not self.project.workers:
            self.run_button.setEnabled(False)
        else:
            self.run_button.setEnabled(enabled)
