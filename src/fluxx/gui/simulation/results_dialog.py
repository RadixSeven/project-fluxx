"""Dialog for displaying simulation results."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget

from fluxx.data.models import Sample
from fluxx.gui.simulation.timeline_widget import ProbabilisticTimelineWidget


class SimulationResultsDialog(QDialog):
    """Dialog to display probabilistic timeline results."""

    def __init__(self, samples: list[Sample], parent: QWidget | None = None) -> None:
        """Initialize the results dialog.

        Args:
            samples: List of simulation samples to visualize
            parent: Parent widget
        """
        super().__init__(parent)
        self.samples = samples

        self.setWindowTitle("Simulation Results")
        self.setModal(False)  # Allow interaction with main window
        self.resize(900, 700)

        # Create UI
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        # Timeline widget
        self.timeline_widget = ProbabilisticTimelineWidget(self.samples)

        # Close button
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.close)

    def _create_layout(self) -> None:
        """Create dialog layout."""
        layout = QVBoxLayout()
        layout.addWidget(self.timeline_widget)
        layout.addWidget(self.button_box)
        self.setLayout(layout)
