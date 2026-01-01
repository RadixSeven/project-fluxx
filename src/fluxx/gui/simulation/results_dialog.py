"""Dialog for displaying simulation results."""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from fluxx.data.models import Project, Sample
from fluxx.gui.simulation.analysis import extract_timeline_data
from fluxx.gui.simulation.gantt_analysis import extract_gantt_statistics
from fluxx.gui.simulation.gantt_optimizer import optimize_gantt_schedule
from fluxx.gui.simulation.gantt_widget import GanttChartWidget
from fluxx.gui.simulation.probabilistic_timeline_widget import (
    ProbabilisticTimelineWidget,
)
from fluxx.gui.simulation.timeline_widget import (
    ProbabilisticTimelineWidget as HistogramWidget,
)


class SimulationResultsDialog(QDialog):
    """Dialog to display simulation results with multiple views."""

    def __init__(
        self,
        samples: list[Sample],
        project: Project,
        percentile: float = 90.0,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the results dialog.

        Args:
            samples: List of simulation samples to visualize
            project: Project containing task definitions
            percentile: Percentile for timeline visualization (default 90.0)
            parent: Parent widget
        """
        super().__init__(parent)
        self.samples = samples
        self.project = project
        self.percentile = percentile

        self.setWindowTitle("Simulation Results")
        self.setModal(False)  # Allow interaction with main window
        self.resize(1200, 800)

        # Create UI
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        # Tab widget for different views
        self.tabs = QTabWidget()

        # Probabilistic timeline (new spec-compliant visualization)
        timeline_data = extract_timeline_data(
            self.samples, self.project, percentile=self.percentile
        )
        self.timeline_widget = ProbabilisticTimelineWidget(timeline_data)
        self.tabs.addTab(self.timeline_widget, "Probabilistic Timeline")

        # Gantt chart (conservative timeline)
        gantt_statistics = extract_gantt_statistics(
            self.samples, self.project, percentile=0.97
        )
        gantt_schedule = optimize_gantt_schedule(gantt_statistics)
        self.gantt_widget = GanttChartWidget(
            gantt_schedule, gantt_statistics.dependencies
        )
        self.tabs.addTab(self.gantt_widget, "Conservative Gantt Chart")

        # Histogram view (completion date distribution)
        self.histogram_widget = HistogramWidget(self.samples)
        self.tabs.addTab(self.histogram_widget, "Completion Date Distribution")

        # Close button
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.close)

    def _create_layout(self) -> None:
        """Create dialog layout."""
        layout = QVBoxLayout()
        layout.addWidget(self.tabs)
        layout.addWidget(self.button_box)
        self.setLayout(layout)
