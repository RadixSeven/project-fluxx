"""Widget for displaying probabilistic timeline visualization."""

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from fluxx.data.models import Sample
from fluxx.gui.simulation.analysis import (
    calculate_percentiles,
    calculate_statistics,
    calculate_success_rate,
    extract_completion_times,
    prepare_histogram_data,
)


class ProbabilisticTimelineWidget(QWidget):
    """Widget to visualize project completion date distribution.

    Displays:
    - Histogram of completion dates
    - Key percentiles (P10, P50, P90, P95)
    - Success rate
    - Statistical measures (mean, median, std dev)
    """

    def __init__(self, samples: list[Sample], parent: QWidget | None = None) -> None:
        """Initialize the timeline widget.

        Args:
            samples: List of simulation samples to visualize
            parent: Parent widget
        """
        super().__init__(parent)
        self.samples = samples

        # Extract completion times
        self.completion_times = extract_completion_times(samples)

        # Create UI
        self._create_widgets()
        self._create_layout()
        self._update_display()

    def _create_widgets(self) -> None:
        """Create child widgets."""
        # Statistics label at top
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)

        # Matplotlib figure for histogram
        self.figure = Figure(figsize=(8, 6))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)

    def _create_layout(self) -> None:
        """Create widget layout."""
        layout = QVBoxLayout()
        layout.addWidget(self.stats_label)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

    def _update_display(self) -> None:
        """Update statistics and histogram display."""
        self._update_statistics()
        self._update_histogram()

    def _update_statistics(self) -> None:
        """Update statistics label with percentiles and success rate."""
        if not self.completion_times:
            self.stats_label.setText("No successful samples to display")
            return

        # Calculate statistics
        success_rate = calculate_success_rate(self.samples)
        percentiles_dict = calculate_percentiles(
            self.completion_times, [10, 50, 90, 95]
        )
        stats = calculate_statistics(self.completion_times)

        # Format text
        lines = [
            f"<b>Simulation Results</b> ({len(self.samples)} samples)",
            f"Success Rate: {success_rate * 100:.1f}%",
            "",
            "<b>Completion Date Percentiles:</b>",
            f"P10: {percentiles_dict[10].strftime('%Y-%m-%d')}",
            f"P50 (Median): {percentiles_dict[50].strftime('%Y-%m-%d')}",
            f"P90: {percentiles_dict[90].strftime('%Y-%m-%d')}",
            f"P95: {percentiles_dict[95].strftime('%Y-%m-%d')}",
            "",
            "<b>Statistics:</b>",
            f"Mean: {stats['mean'].strftime('%Y-%m-%d')}",
            f"Std Dev: {stats['std_dev'].days} days",
        ]

        self.stats_label.setText("<br>".join(lines))

    def _update_histogram(self) -> None:
        """Update histogram plot."""
        self.ax.clear()

        if not self.completion_times:
            self.ax.text(
                0.5,
                0.5,
                "No successful samples",
                ha="center",
                va="center",
                transform=self.ax.transAxes,
            )
            self.canvas.draw()
            return

        # Prepare histogram data
        bin_edges, counts = prepare_histogram_data(self.completion_times, num_bins=30)

        # Plot histogram
        # bin_edges has len(counts)+1 elements, use bin centers for bar positions
        bin_centers = [
            (bin_edges[i] + bin_edges[i + 1]) / 2 for i in range(len(counts))
        ]
        bin_widths = [bin_edges[i + 1] - bin_edges[i] for i in range(len(counts))]

        self.ax.bar(bin_centers, counts, width=bin_widths, alpha=0.7, edgecolor="black")

        # Add percentile lines
        percentiles_dict = calculate_percentiles(
            self.completion_times, [10, 50, 90, 95]
        )
        earliest = min(self.completion_times)

        colors = {"P10": "green", "P50": "blue", "P90": "orange", "P95": "red"}
        for label, p in [("P10", 10), ("P50", 50), ("P90", 90), ("P95", 95)]:
            days = (percentiles_dict[p] - earliest).total_seconds() / 86400
            self.ax.axvline(
                days, color=colors[label], linestyle="--", linewidth=2, label=label
            )

        # Labels and formatting
        self.ax.set_xlabel("Days from Earliest Completion")
        self.ax.set_ylabel("Number of Samples")
        self.ax.set_title("Project Completion Date Distribution")
        self.ax.legend()
        self.ax.grid(True, alpha=0.3)

        self.figure.tight_layout()
        self.canvas.draw()
