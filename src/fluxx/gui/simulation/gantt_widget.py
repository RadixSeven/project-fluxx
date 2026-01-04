"""Gantt chart visualization widget for conservative timeline display.

Displays optimized Gantt chart schedule per spec 8.1.
"""

from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import (  # type: ignore[attr-defined]
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from fluxx.gui.simulation.analysis import DependencyInfo
from fluxx.gui.simulation.gantt_analysis import TaskVariantKey
from fluxx.gui.simulation.gantt_optimizer import GanttSchedule


class GanttChartWidget(QWidget):
    """Widget to visualize optimized Gantt chart per spec 8.1."""

    def __init__(
        self,
        gantt_schedule: GanttSchedule,
        dependencies: list[DependencyInfo],
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the Gantt chart widget.

        Args:
            gantt_schedule: Optimized Gantt schedule to visualize
            dependencies: List of dependency info from project
            parent: Parent widget
        """
        super().__init__(parent)
        self.gantt_schedule = gantt_schedule
        self.dependencies = dependencies

        self._create_widgets()
        self._create_layout()
        self._draw_gantt()

    def _create_widgets(self) -> None:
        """Create matplotlib figure and canvas."""
        self.figure = Figure(figsize=(12, 8))
        self.canvas = FigureCanvasQTAgg(self.figure)  # type: ignore[no-untyped-call]
        self.ax = self.figure.add_subplot(111)
        self.toolbar = NavigationToolbar(self.canvas, self)  # type: ignore[no-untyped-call]

        # Error label (hidden by default)
        self.error_label = QLabel()
        self.error_label.setStyleSheet(
            "QLabel { color: red; font-size: 14px; padding: 20px; }"
        )
        self.error_label.setWordWrap(True)
        self.error_label.hide()

    def _create_layout(self) -> None:
        """Create widget layout."""
        layout = QVBoxLayout()
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        layout.addWidget(self.error_label)
        self.setLayout(layout)

    def _draw_gantt(self) -> None:
        """Draw Gantt chart bars and dependencies."""
        # Check for error status
        if self.gantt_schedule.optimization_status != "optimal":
            self._show_error(
                f"Unable to generate Gantt chart: "
                f"{self.gantt_schedule.error_message or 'Unknown error'}"
            )
            return

        # Check for empty schedule
        if not self.gantt_schedule.variant_schedules:
            self._show_error("No tasks to display in Gantt chart.")
            return

        # Sort task variants by start time for vertical positioning
        sorted_variants = sorted(
            self.gantt_schedule.variant_schedules.items(),
            key=lambda item: item[1].start_time,
        )

        # Create y-position mapping (task names on y-axis)
        y_positions = {}
        task_labels = []
        for i, (variant_key, schedule) in enumerate(sorted_variants):
            y_positions[variant_key] = i
            # Include world sequence info in label if not empty
            if variant_key.world_sequence:
                world_str = ", ".join(str(w) for w in variant_key.world_sequence)
                label = f"{schedule.task_title} ({world_str})"
            else:
                label = schedule.task_title
            task_labels.append(label)

        # Draw task bars
        for variant_key, schedule in sorted_variants:
            y_pos = y_positions[variant_key]
            self._draw_task_bar(schedule.start_time, schedule.end_time, y_pos)

        # Draw dependency arrows
        self._draw_dependencies(y_positions)

        # Compute date range for x-axis limits
        all_start_times = [sched.start_time for _, sched in sorted_variants]
        all_end_times = [sched.end_time for _, sched in sorted_variants]
        earliest_time = min(all_start_times)
        latest_time = max(all_end_times)

        # Format time axis (x-axis) with proper limits
        self._format_time_axis(earliest_time, latest_time)

        # Format task axis (y-axis)
        self.ax.set_yticks(range(len(task_labels)))
        self.ax.set_yticklabels(task_labels)
        self.ax.set_ylim(-0.5, len(task_labels) - 0.5)

        # Set labels and title
        self.ax.set_xlabel("Date")
        self.ax.set_ylabel("Tasks")
        self.ax.set_title("Conservative Gantt Chart (97th Percentile)")

        # Grid
        self.ax.grid(True, axis="x", alpha=0.3)

        # Tight layout
        self.figure.tight_layout()

        # Refresh canvas
        self.canvas.draw()  # type: ignore[no-untyped-call]

    def _draw_task_bar(
        self, start_time: datetime, end_time: datetime, y_position: float
    ) -> None:
        """Draw a single task bar.

        Args:
            start_time: Task start time
            end_time: Task end time
            y_position: Vertical position for this task
        """
        # Convert to matplotlib dates
        start_num = mdates.date2num(start_time)  # type: ignore[no-untyped-call]
        end_num = mdates.date2num(end_time)  # type: ignore[no-untyped-call]

        # Single solid bar (no inner/outer like probabilistic timeline)
        bar_height = 0.6
        rect = mpatches.Rectangle(
            (start_num, y_position - bar_height / 2),
            end_num - start_num,
            bar_height,
            linewidth=1,
            edgecolor="black",
            facecolor="steelblue",
            alpha=0.8,
        )
        self.ax.add_patch(rect)

    def _draw_dependencies(self, y_positions: dict[TaskVariantKey, int]) -> None:
        """Draw dependency arrows between tasks.

        Only draws start >= end dependencies (finish-to-start dependencies),
        which represent "source can only start after target completes".

        Args:
            y_positions: Mapping from variant keys to y-axis positions
        """
        from fluxx.data.models import ConstraintType, Endpoint

        # For each dependency, draw arrow if both tasks are visible
        for dep_info in self.dependencies:
            dep = dep_info.dependency

            # Only draw start >= end dependencies (finish-to-start)
            if (
                dep.source_endpoint != Endpoint.START
                or dep.target_endpoint != Endpoint.END
                or dep.constraint_type != ConstraintType.GREATER_EQUAL
            ):
                continue

            source_task_id = dep_info.source_task_id
            target_node_id = dep.target_node_id

            # Find variants for source and target
            # Note: This is simplified - in reality we'd need to match world sequences
            source_schedule = None
            target_schedule = None
            source_key = None
            target_key = None

            for variant_key, schedule in self.gantt_schedule.variant_schedules.items():
                if str(variant_key.task_id) == str(source_task_id):
                    source_schedule = schedule
                    source_key = variant_key
                if str(variant_key.task_id) == str(target_node_id):
                    target_schedule = schedule
                    target_key = variant_key

            if not source_schedule or not target_schedule:
                continue

            if source_key is None or target_key is None:
                continue

            # Get y positions
            source_y = y_positions.get(source_key)
            target_y = y_positions.get(target_key)

            if source_y is None or target_y is None:
                continue

            # Draw arrow from target end to source start
            # (target must finish before source can start)
            target_end_num = mdates.date2num(target_schedule.end_time)  # type: ignore[no-untyped-call]
            source_start_num = mdates.date2num(source_schedule.start_time)  # type: ignore[no-untyped-call]

            self.ax.annotate(
                "",
                xy=(source_start_num, source_y),
                xytext=(target_end_num, target_y),
                arrowprops={
                    "arrowstyle": "->",
                    "color": "gray",
                    "lw": 1,
                    "alpha": 0.6,
                },
            )

    def _format_time_axis(self, earliest_time: datetime, latest_time: datetime) -> None:
        """Format the time axis with appropriate date formatting.

        Args:
            earliest_time: Earliest task start time
            latest_time: Latest task end time
        """
        from datetime import timedelta

        # Use date formatter
        date_formatter = mdates.DateFormatter("%Y-%m-%d")  # type: ignore[no-untyped-call]
        self.ax.xaxis.set_major_formatter(date_formatter)

        # Auto-format dates
        self.figure.autofmt_xdate()

        # Set locator for better tick spacing
        self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())  # type: ignore[no-untyped-call]

        # Set axis limits with some padding
        duration = latest_time - earliest_time
        days = duration.total_seconds() / 86400
        padding = timedelta(days=max(1, days * 0.05))
        start_date = earliest_time - padding
        end_date = latest_time + padding

        self.ax.set_xlim(
            mdates.date2num(start_date),  # type: ignore[no-untyped-call]
            mdates.date2num(end_date),  # type: ignore[no-untyped-call]
        )

    def _show_error(self, message: str) -> None:
        """Show error message instead of Gantt chart.

        Args:
            message: Error message to display
        """
        self.error_label.setText(message)
        self.error_label.show()
        self.canvas.hide()
        self.toolbar.hide()
