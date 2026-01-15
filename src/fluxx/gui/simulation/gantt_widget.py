"""Gantt chart visualization widget for conservative timeline display.

Displays optimized Gantt chart schedule per spec 8.1.
"""

from __future__ import annotations

import functools
from datetime import datetime
from typing import TYPE_CHECKING

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from fluxx.data.models import PossibleWorldId
from fluxx.gui.simulation.analysis import DependencyInfo
from fluxx.gui.simulation.gantt_analysis import TaskVariantKey, WorldSequence
from fluxx.gui.simulation.gantt_optimizer import GanttSchedule, GanttVariantSchedule
from fluxx.gui.simulation.label_utils import truncate_task_label

if TYPE_CHECKING:
    from matplotlib.text import Annotation


def _compute_common_world_prefix(
    world_sequences: list[WorldSequence],
) -> WorldSequence:
    """Compute the longest common prefix across all non-empty world sequences.

    If the same possible worlds appear at the start of every world sequence,
    they can be omitted from labels since they add no distinguishing information.

    Args:
        world_sequences: List of world sequences to find common prefix for

    Returns:
        The longest common prefix as a WorldSequence (tuple of PossibleWorldIds).
        Returns empty tuple if there are fewer than 2 non-empty sequences
        (since a prefix is only meaningful when comparing multiple sequences).
    """
    # Filter out empty sequences - they don't participate in prefix calculation
    non_empty_seqs = [ws for ws in world_sequences if ws]

    if len(non_empty_seqs) < 2:
        # Need at least 2 non-empty sequences to have a meaningful common prefix
        return ()

    # Find minimum length
    min_len = min(len(ws) for ws in non_empty_seqs)

    # Find longest common prefix
    prefix_len = 0
    for i in range(min_len):
        # Check if all sequences have the same element at position i
        first_elem = non_empty_seqs[0][i]
        if all(ws[i] == first_elem for ws in non_empty_seqs):
            prefix_len = i + 1
        else:
            break

    return non_empty_seqs[0][:prefix_len]


def _compute_world_sequence_sort_key(
    world_seq: WorldSequence,
    earliest_start_by_world_seq: dict[WorldSequence, datetime],
) -> tuple[int, datetime, WorldSequence]:
    """Compute sort key for a world sequence.

    Sorting order:
    1. Empty world sequence (base possible world) comes first
    2. Other world sequences sorted by earliest task start time
    3. Tie-breaker: lexicographic order of world sequence tuple

    Args:
        world_seq: The world sequence to compute key for
        earliest_start_by_world_seq: Map of world sequence to earliest task start

    Returns:
        Tuple for sorting: (priority, earliest_start, world_seq)
        - priority: 0 for empty (base world), 1 for others
        - earliest_start: earliest task start time in this world sequence
        - world_seq: for stable tie-breaking
    """
    from datetime import UTC

    if not world_seq:
        # Empty world sequence (base possible world) comes first
        min_dt = datetime.min.replace(tzinfo=UTC)
        return (0, earliest_start_by_world_seq.get(world_seq, min_dt), world_seq)
    else:
        # Other world sequences sorted by earliest task start time
        max_dt = datetime.max.replace(tzinfo=UTC)
        return (1, earliest_start_by_world_seq.get(world_seq, max_dt), world_seq)


def _group_and_sort_variants(
    variant_schedules: dict[TaskVariantKey, GanttVariantSchedule],
) -> tuple[
    list[tuple[TaskVariantKey, GanttVariantSchedule]],
    list[int],
]:
    """Group and sort task variants by world sequence, then by start time.

    Returns:
        Tuple of:
        - List of (variant_key, schedule) sorted by world sequence, then start time
        - List of y-positions where dividers should be drawn (between world groups)
    """
    if not variant_schedules:
        return [], []

    # Compute earliest start time for each world sequence
    earliest_start_by_world_seq: dict[WorldSequence, datetime] = {}
    for variant_key, schedule in variant_schedules.items():
        world_seq = variant_key.world_sequence
        if world_seq not in earliest_start_by_world_seq:
            earliest_start_by_world_seq[world_seq] = schedule.start_time
        else:
            earliest_start_by_world_seq[world_seq] = min(
                earliest_start_by_world_seq[world_seq], schedule.start_time
            )

    # Get sorted list of unique world sequences
    unique_world_seqs = sorted(
        earliest_start_by_world_seq.keys(),
        key=lambda ws: _compute_world_sequence_sort_key(
            ws, earliest_start_by_world_seq
        ),
    )

    # Group variants by world sequence
    variants_by_world_seq: dict[
        WorldSequence, list[tuple[TaskVariantKey, GanttVariantSchedule]]
    ] = {ws: [] for ws in unique_world_seqs}
    for variant_key, schedule in variant_schedules.items():
        variants_by_world_seq[variant_key.world_sequence].append(
            (variant_key, schedule)
        )

    # Sort each group by start time, then end time, then title (for determinism)
    # Reverse so earlier tasks appear at top of chart (higher y-index in matplotlib)
    for world_seq in variants_by_world_seq:
        variants_by_world_seq[world_seq].sort(
            key=lambda item: (item[1].start_time, item[1].end_time, item[1].task_title),
            reverse=True,
        )

    # Flatten into final sorted list and track divider positions
    sorted_variants: list[tuple[TaskVariantKey, GanttVariantSchedule]] = []
    divider_positions: list[int] = []
    current_position = 0

    for i, world_seq in enumerate(unique_world_seqs):
        group = variants_by_world_seq[world_seq]
        sorted_variants.extend(group)

        # Add divider position after this group (except for the last group)
        if i < len(unique_world_seqs) - 1:
            current_position += len(group)
            # Divider goes between positions (current_position - 0.5)
            divider_positions.append(current_position)

    return sorted_variants, divider_positions


class GanttChartWidget(QWidget):
    """Widget to visualize optimized Gantt chart per spec 8.1."""

    def __init__(
        self,
        gantt_schedule: GanttSchedule,
        dependencies: list[DependencyInfo],
        world_titles: dict[PossibleWorldId, str],
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the Gantt chart widget.

        Args:
            gantt_schedule: Optimized Gantt schedule to visualize
            dependencies: List of dependency info from project
            world_titles: Mapping from PossibleWorldId to human-readable title
            parent: Parent widget
        """
        super().__init__(parent)
        self.gantt_schedule = gantt_schedule
        self.dependencies = dependencies
        self.world_titles = world_titles

        # Store full labels for tooltips (populated during draw)
        self._full_labels: list[str] = []
        self._tooltip_annotation: Annotation | None = None

        self._create_widgets()
        self._create_layout()
        self._draw_gantt()
        self._setup_hover_tooltips()

    def _create_widgets(self) -> None:
        """Create matplotlib figure and canvas."""
        self.figure = Figure(figsize=(12, 8))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.toolbar = NavigationToolbar(self.canvas, self)

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

        # Sort task variants by world sequence (base world first), then by start time
        sorted_variants, divider_positions = _group_and_sort_variants(
            self.gantt_schedule.variant_schedules
        )

        # Compute common world sequence prefix to strip from labels
        all_world_seqs = [vk.world_sequence for vk, _ in sorted_variants]
        common_prefix = _compute_common_world_prefix(all_world_seqs)
        prefix_len = len(common_prefix)

        # Create y-position mapping (task names on y-axis)
        y_positions: dict[TaskVariantKey, int] = {}
        task_labels: list[str] = []
        self._full_labels = []
        for i, (variant_key, schedule) in enumerate(sorted_variants):
            y_positions[variant_key] = i
            # Include world sequence info in label if not empty (after stripping prefix)
            display_world_seq = variant_key.world_sequence[prefix_len:]
            if display_world_seq:
                # Use human-readable titles if available, fall back to IDs
                world_titles_list = [
                    self.world_titles.get(w, str(w)) for w in display_world_seq
                ]
                world_str = ", ".join(world_titles_list)
                base_label = f"{schedule.task_title} ({world_str})"
            else:
                base_label = schedule.task_title

            # Truncate label with Jira issue key prefix if available
            truncated_label, full_label = truncate_task_label(
                base_label, schedule.jira_issue_key
            )
            task_labels.append(truncated_label)
            self._full_labels.append(full_label)

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

        # Draw horizontal divider lines between world sequence groups
        self._draw_world_dividers(divider_positions, earliest_time, latest_time)

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
        self.canvas.draw()

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
        start_num = mdates.date2num(start_time)
        end_num = mdates.date2num(end_time)

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

    def _draw_world_dividers(
        self,
        divider_positions: list[int],
        earliest_time: datetime,
        latest_time: datetime,
    ) -> None:
        """Draw horizontal divider lines between possible world groups.

        Args:
            divider_positions: List of y-positions where dividers should be drawn
            earliest_time: Earliest task start time (for line start x)
            latest_time: Latest task end time (for line end x)
        """
        if not divider_positions:
            return

        from datetime import timedelta

        # Extend lines slightly beyond the chart bounds for visibility
        duration = latest_time - earliest_time
        days = duration.total_seconds() / 86400
        padding = timedelta(days=max(1, days * 0.05))

        start_x = mdates.date2num(earliest_time - padding)
        end_x = mdates.date2num(latest_time + padding)

        # Draw divider lines with distinct color (orange-red for visibility)
        for y_pos in divider_positions:
            # Position line between rows (at y_pos - 0.5)
            y = y_pos - 0.5
            self.ax.hlines(
                y=y,
                xmin=start_x,
                xmax=end_x,
                colors="#E67E22",  # Orange color - distinct from grid and bars
                linewidth=2,
                linestyle="-",
                alpha=0.8,
                zorder=1,  # Draw below task bars
            )

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
            target_end_num = mdates.date2num(target_schedule.end_time)
            source_start_num = mdates.date2num(source_schedule.start_time)

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
        date_formatter = mdates.DateFormatter("%Y-%m-%d")
        self.ax.xaxis.set_major_formatter(date_formatter)

        # Auto-format dates
        self.figure.autofmt_xdate()

        # Set locator for better tick spacing
        self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())

        # Set axis limits with some padding
        duration = latest_time - earliest_time
        days = duration.total_seconds() / 86400
        padding = timedelta(days=max(1, days * 0.05))
        start_date = earliest_time - padding
        end_date = latest_time + padding

        self.ax.set_xlim(
            mdates.date2num(start_date),
            mdates.date2num(end_date),
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

    def _setup_hover_tooltips(self) -> None:
        """Set up hover tooltips for y-axis labels."""
        # Create annotation for tooltip (hidden initially)
        self._tooltip_annotation = self.ax.annotate(
            "",
            xy=(0, 0),
            xytext=(10, 10),
            textcoords="offset points",
            bbox={
                "boxstyle": "round,pad=0.3",
                "facecolor": "lightyellow",
                "alpha": 0.9,
            },
            fontsize=9,
            visible=False,
            zorder=100,
        )

        self.canvas.mpl_connect(
            "motion_notify_event", functools.partial(_on_hover, self)
        )


def _on_hover(widget: GanttChartWidget, event: MouseEvent) -> None:
    """Handle mouse motion to show/hide tooltips on y-axis labels.

    Args:
        widget: The GanttChartWidget instance
        event: The matplotlib mouse event
    """
    if event.inaxes != widget.ax:
        if widget._tooltip_annotation is not None:
            widget._tooltip_annotation.set_visible(False)
            widget.canvas.draw_idle()
        return

    # Check if mouse is near the y-axis (left side of plot)
    # Get the axes bounding box in display coordinates
    bbox = widget.ax.get_position()
    fig_width = widget.figure.get_figwidth() * widget.figure.dpi

    # Only show tooltip when hovering near the left edge (y-axis area)
    if event.x is None or event.x > bbox.x0 * fig_width + 50:
        if widget._tooltip_annotation is not None:
            widget._tooltip_annotation.set_visible(False)
            widget.canvas.draw_idle()
        return

    # Find the closest y-tick
    if event.ydata is None:
        return

    y_pos = int(round(event.ydata))
    if 0 <= y_pos < len(widget._full_labels):
        full_label = widget._full_labels[y_pos]

        if widget._tooltip_annotation is not None:
            widget._tooltip_annotation.set_text(full_label)
            # Position tooltip at the y-axis label position
            widget._tooltip_annotation.xy = (widget.ax.get_xlim()[0], y_pos)
            widget._tooltip_annotation.set_visible(True)
            widget.canvas.draw_idle()
    else:
        if widget._tooltip_annotation is not None:
            widget._tooltip_annotation.set_visible(False)
            widget.canvas.draw_idle()
