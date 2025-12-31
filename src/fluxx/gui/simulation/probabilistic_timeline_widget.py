"""Widget for displaying probabilistic timeline visualization per spec 8.2."""

from collections.abc import Sequence
from datetime import datetime, timedelta

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.backends.backend_qtagg import (  # type: ignore[attr-defined]
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget

from fluxx.data.models import Endpoint, TaskId
from fluxx.gui.simulation.analysis import TaskStatistics, TimelineData


class ProbabilisticTimelineWidget(QWidget):
    """Widget to visualize probabilistic timeline per spec 8.2.

    Displays:
    - Task boxes with outer boundaries (min start to max end)
    - Inner percentile markers
    - Occurrence fractions
    - Dependency arrows
    - Multi-row date axis (day, month, year)
    - Zoom and pan controls
    """

    def __init__(
        self, timeline_data: TimelineData, parent: QWidget | None = None
    ) -> None:
        """Initialize the probabilistic timeline widget.

        Args:
            timeline_data: Timeline data to visualize
            parent: Parent widget
        """
        super().__init__(parent)
        self.timeline_data = timeline_data

        # Create UI
        self._create_widgets()
        self._create_layout()
        self._draw_timeline()

    def _create_widgets(self) -> None:
        """Create child widgets."""
        # Matplotlib figure
        self.figure = Figure(figsize=(12, 8))
        self.canvas = FigureCanvasQTAgg(self.figure)  # type: ignore[no-untyped-call]
        self.ax = self.figure.add_subplot(111)

        # Navigation toolbar for zoom/pan
        self.toolbar = NavigationToolbar2QT(self.canvas, self)  # type: ignore[no-untyped-call]

    def _create_layout(self) -> None:
        """Create widget layout."""
        layout = QVBoxLayout()
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

    def _draw_timeline(self) -> None:
        """Draw task boxes, dependency arrows, and labels."""
        self.ax.clear()

        if not self.timeline_data.task_statistics:
            self.ax.text(
                0.5,
                0.5,
                "No tasks to display",
                ha="center",
                va="center",
                transform=self.ax.transAxes,
            )
            self.canvas.draw()  # type: ignore[no-untyped-call]
            return

        # Sort tasks by their earliest start time for vertical layout
        from datetime import UTC

        sorted_tasks: list[tuple[TaskId, TaskStatistics]] = sorted(
            [
                (tid, stats)
                for tid, stats in self.timeline_data.task_statistics.items()
                if stats.time_statistics is not None
            ],
            key=lambda x: x[1].time_statistics.min_start_time
            if x[1].time_statistics
            else datetime.max.replace(tzinfo=UTC),
        )

        # Draw each task
        task_y_positions: dict[TaskId, float] = {}
        for i, (task_id, stats) in enumerate(sorted_tasks):
            y_position = len(sorted_tasks) - i - 1  # Top to bottom
            task_y_positions[task_id] = y_position
            self._draw_task_box(task_id, stats, y_position)

        # Draw dependency arrows
        self._draw_dependencies(task_y_positions)

        # Format axes
        self._format_time_axis()
        self._format_task_axis(sorted_tasks)

        # Set title
        self.ax.set_title(
            f"Probabilistic Timeline (P{self.timeline_data.percentile:.0f})"
        )

        # Tight layout and draw
        self.figure.tight_layout()
        self.canvas.draw()  # type: ignore[no-untyped-call]

    def _draw_task_box(self, task_id: TaskId, stats: object, y_position: float) -> None:
        """Draw a task box with outer and inner markers.

        Args:
            task_id: Task ID
            stats: TaskStatistics object (typed as object to avoid circular import)
            y_position: Vertical position for this task
        """
        from fluxx.gui.simulation.analysis import TaskStatistics

        stats_typed = stats if isinstance(stats, TaskStatistics) else None
        if stats_typed is None or stats_typed.time_statistics is None:
            return

        time_stats = stats_typed.time_statistics

        # Convert datetimes to matplotlib format
        min_start = mdates.date2num(time_stats.min_start_time)  # type: ignore[no-untyped-call]
        max_end = mdates.date2num(time_stats.max_end_time)  # type: ignore[no-untyped-call]
        percentile_start = mdates.date2num(time_stats.percentile_start_time)  # type: ignore[no-untyped-call]
        percentile_end = mdates.date2num(time_stats.percentile_end_time)  # type: ignore[no-untyped-call]

        box_height = 0.6

        # Draw outer box (min start to max end) - light gray
        outer_width = max_end - min_start
        outer_rect = mpatches.Rectangle(
            (min_start, y_position - box_height / 2),
            outer_width,
            box_height,
            linewidth=1,
            edgecolor="black",
            facecolor="lightgray",
            alpha=0.3,
        )
        self.ax.add_patch(outer_rect)

        # Draw inner box (percentile start to percentile end) - darker
        inner_width = percentile_end - percentile_start
        inner_rect = mpatches.Rectangle(
            (percentile_start, y_position - box_height / 2),
            inner_width,
            box_height,
            linewidth=2,
            edgecolor="darkblue",
            facecolor="skyblue",
            alpha=0.6,
        )
        self.ax.add_patch(inner_rect)

        # Add occurrence fraction label
        occurrence_pct = stats_typed.occurrence_fraction * 100
        label = f"{stats_typed.task_title} ({occurrence_pct:.0f}%)"
        self.ax.text(
            min_start,
            y_position,
            label,
            va="center",
            ha="left",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.8},
        )

    def _draw_dependencies(self, task_y_positions: dict[TaskId, float]) -> None:
        """Draw dependency arrows between tasks.

        Args:
            task_y_positions: Mapping of task IDs to their y positions
        """
        for dep_info in self.timeline_data.dependencies:
            source_task_id = dep_info.source_task_id
            dep = dep_info.dependency

            # Skip if source task not in display
            if source_task_id not in task_y_positions:
                continue

            # Get target task ID from dependency
            target_node_str = str(dep.target_node_id)
            # Handle possible world references (format: "branch_id:world_id")
            if ":" in target_node_str:
                # This is a possible world reference, skip for now
                continue

            target_task_id = TaskId(target_node_str)
            if target_task_id not in task_y_positions:
                continue

            # Get positions
            source_y = task_y_positions[source_task_id]
            target_y = task_y_positions[target_task_id]

            # Get source and target task statistics for time positions
            source_stats = self.timeline_data.task_statistics[source_task_id]
            target_stats = self.timeline_data.task_statistics[target_task_id]

            if (
                source_stats.time_statistics is None
                or target_stats.time_statistics is None
            ):
                continue

            # Determine arrow endpoints based on dependency endpoints
            # Source endpoint (where arrow starts from source task)
            if dep.source_endpoint == Endpoint.START:
                source_x = mdates.date2num(  # type: ignore[no-untyped-call]
                    source_stats.time_statistics.min_start_time
                )
            else:  # Endpoint.END
                source_x = mdates.date2num(  # type: ignore[no-untyped-call]
                    source_stats.time_statistics.max_end_time
                )

            # Target endpoint (where arrow points to on target task)
            if dep.target_endpoint == Endpoint.START:
                target_x = mdates.date2num(  # type: ignore[no-untyped-call]
                    target_stats.time_statistics.min_start_time
                )
            else:  # Endpoint.END
                target_x = mdates.date2num(  # type: ignore[no-untyped-call]
                    target_stats.time_statistics.max_end_time
                )

            # Draw arrow
            # Use different arrow styles for different constraint types
            if dep.constraint_type.value == "=":
                # Equality constraint - double-headed arrow
                arrow_style = "<->"
                color = "purple"
            else:  # ">="
                # Greater-than-or-equal - single arrow from target to source
                arrow_style = "->"
                color = "gray"

            self.ax.annotate(
                "",
                xy=(source_x, source_y),
                xytext=(target_x, target_y),
                arrowprops={
                    "arrowstyle": arrow_style,
                    "color": color,
                    "lw": 1.5,
                    "alpha": 0.6,
                },
            )

    def _format_time_axis(self) -> None:
        """Format horizontal time axis with multi-row date labels."""
        # Set x-axis to use date formatting
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%d\n%b\n%Y"))  # type: ignore[no-untyped-call]

        # Determine appropriate time scale
        time_range = self.timeline_data.latest_time - self.timeline_data.earliest_time
        days = time_range.total_seconds() / 86400

        if days <= 7:
            # Daily ticks for short timelines
            self.ax.xaxis.set_major_locator(mdates.DayLocator())  # type: ignore[no-untyped-call]
        elif days <= 60:
            # Weekly ticks for medium timelines
            self.ax.xaxis.set_major_locator(mdates.WeekdayLocator())  # type: ignore[no-untyped-call]
        else:
            # Monthly ticks for long timelines
            self.ax.xaxis.set_major_locator(mdates.MonthLocator())  # type: ignore[no-untyped-call]

        # Rotate labels for readability
        self.figure.autofmt_xdate()

        # Set axis limits with some padding
        padding = timedelta(days=max(1, days * 0.05))
        start_date = self.timeline_data.earliest_time - padding
        end_date = self.timeline_data.latest_time + padding

        self.ax.set_xlim(mdates.date2num(start_date), mdates.date2num(end_date))  # type: ignore[no-untyped-call]

        self.ax.set_xlabel("Time")

    def _format_task_axis(
        self, sorted_tasks: Sequence[tuple[TaskId, TaskStatistics]]
    ) -> None:
        """Format vertical task axis with task names.

        Args:
            sorted_tasks: Sequence of (task_id, stats) tuples in display order
        """
        # Set y-axis labels
        y_ticks = list(range(len(sorted_tasks)))
        y_labels = [stats.task_title for _, stats in reversed(sorted_tasks)]

        self.ax.set_yticks(y_ticks)
        self.ax.set_yticklabels(y_labels)

        # Set y limits with minimum range to avoid singular transformation
        y_min = -0.5
        y_max = max(len(sorted_tasks) - 0.5, 0.5)  # Ensure at least 1 unit range
        self.ax.set_ylim(y_min, y_max)

        self.ax.set_ylabel("Tasks")

        # Add grid for readability
        self.ax.grid(True, alpha=0.3, axis="x")
