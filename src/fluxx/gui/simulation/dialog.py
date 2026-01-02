"""Dialog for configuring and running project simulations."""

from datetime import UTC, datetime

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from fluxx.data.models import Project, Sample, Worker, WorkerId
from fluxx.simulation.engine import SimulationEngine


class SimulationDialog(QDialog):
    """Dialog to configure and run a Monte Carlo simulation.

    Allows user to specify:
    - Number of simulation samples
    - Project start date
    - Number of workers
    - Hours per workday for workers

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
        self.resize(400, 300)

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

        self.num_workers_spin = QSpinBox()
        self.num_workers_spin.setMinimum(1)
        self.num_workers_spin.setMaximum(100)
        self.num_workers_spin.setValue(2)

        self.hours_per_day_spin = QSpinBox()
        self.hours_per_day_spin.setMinimum(1)
        self.hours_per_day_spin.setMaximum(24)
        self.hours_per_day_spin.setValue(8)

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

    def _create_layout(self) -> None:
        """Create dialog layout."""
        layout = QVBoxLayout()

        # Form for input fields
        form = QFormLayout()
        form.addRow("Number of samples:", self.num_samples_spin)
        form.addRow("Start date:", self.start_date_edit)
        form.addRow("Number of workers:", self.num_workers_spin)
        form.addRow("Hours per workday:", self.hours_per_day_spin)

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
        num_workers = self.num_workers_spin.value()
        hours_per_day = float(self.hours_per_day_spin.value())

        # Create workers
        workers = self._create_workers(num_workers, hours_per_day)

        # Disable inputs and show progress
        self._set_inputs_enabled(False)
        self.progress_label.show()
        self.progress_bar.show()
        self.progress_bar.setValue(0)

        # Run simulation
        # NOTE: This is synchronous and will block the UI
        # For better UX, this should be moved to a worker thread in the future
        try:
            samples = self._run_simulation(num_samples, start_date, workers)

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

    def _create_workers(self, num_workers: int, hours_per_day: float) -> list[Worker]:
        """Create worker objects for simulation.

        Args:
            num_workers: Number of workers to create
            hours_per_day: Hours per workday for each worker

        Returns:
            List of Worker objects
        """
        return [
            Worker(
                id=WorkerId(f"sim_worker_{i}"),
                name=f"Worker {i + 1}",
                hours_per_workday=hours_per_day,
            )
            for i in range(num_workers)
        ]

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
        self.num_workers_spin.setEnabled(enabled)
        self.hours_per_day_spin.setEnabled(enabled)
        self.run_button.setEnabled(enabled)
