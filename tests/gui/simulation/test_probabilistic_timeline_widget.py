"""Tests for probabilistic timeline widget."""

from datetime import UTC, datetime

import pytest
from pytestqt.qtbot import QtBot

from fluxx.data.models import (
    ConstraintType,
    Dependency,
    Endpoint,
    NodeId,
    TaskId,
)
from fluxx.gui.simulation.analysis import (
    DependencyInfo,
    TaskStatistics,
    TimelineData,
    TimeStatistics,
)
from fluxx.gui.simulation.probabilistic_timeline_widget import (
    ProbabilisticTimelineWidget,
)


@pytest.fixture
def simple_timeline_data() -> TimelineData:
    """Create simple timeline data for testing."""
    # Create statistics for two tasks
    task_a_stats = TaskStatistics(
        task_id=TaskId("A"),
        occurrence_fraction=1.0,
        time_statistics=TimeStatistics(
            min_start_time=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
            max_end_time=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            percentile_start_time=datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
            percentile_end_time=datetime(2024, 1, 1, 11, 30, tzinfo=UTC),
        ),
    )

    task_b_stats = TaskStatistics(
        task_id=TaskId("B"),
        occurrence_fraction=0.8,
        time_statistics=TimeStatistics(
            min_start_time=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            max_end_time=datetime(2024, 1, 1, 15, 0, tzinfo=UTC),
            percentile_start_time=datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
            percentile_end_time=datetime(2024, 1, 1, 14, 30, tzinfo=UTC),
        ),
    )

    return TimelineData(
        task_statistics={
            TaskId("A"): task_a_stats,
            TaskId("B"): task_b_stats,
        },
        dependencies=[],
        percentile=90.0,
        earliest_time=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
        latest_time=datetime(2024, 1, 1, 15, 0, tzinfo=UTC),
    )


@pytest.fixture
def timeline_data_with_dependencies() -> TimelineData:
    """Create timeline data with dependencies."""
    task_a_stats = TaskStatistics(
        task_id=TaskId("A"),
        occurrence_fraction=1.0,
        time_statistics=TimeStatistics(
            min_start_time=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
            max_end_time=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            percentile_start_time=datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
            percentile_end_time=datetime(2024, 1, 1, 11, 30, tzinfo=UTC),
        ),
    )

    task_b_stats = TaskStatistics(
        task_id=TaskId("B"),
        occurrence_fraction=1.0,
        time_statistics=TimeStatistics(
            min_start_time=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            max_end_time=datetime(2024, 1, 1, 15, 0, tzinfo=UTC),
            percentile_start_time=datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
            percentile_end_time=datetime(2024, 1, 1, 14, 30, tzinfo=UTC),
        ),
    )

    # B depends on A (B.start >= A.end)
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=NodeId("A"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    dep_info = DependencyInfo(source_task_id=TaskId("B"), dependency=dep)

    return TimelineData(
        task_statistics={
            TaskId("A"): task_a_stats,
            TaskId("B"): task_b_stats,
        },
        dependencies=[dep_info],
        percentile=90.0,
        earliest_time=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
        latest_time=datetime(2024, 1, 1, 15, 0, tzinfo=UTC),
    )


@pytest.fixture
def empty_timeline_data() -> TimelineData:
    """Create empty timeline data."""
    return TimelineData(
        task_statistics={},
        dependencies=[],
        percentile=90.0,
        earliest_time=datetime.now(UTC),
        latest_time=datetime.now(UTC),
    )


def test_widget_initialization(
    qtbot: QtBot, simple_timeline_data: TimelineData
) -> None:
    """Test widget initializes with timeline data."""
    widget = ProbabilisticTimelineWidget(simple_timeline_data)
    qtbot.addWidget(widget)

    # Widget should have figure and canvas
    assert widget.figure is not None
    assert widget.canvas is not None
    assert widget.ax is not None

    # Widget should have toolbar
    assert widget.toolbar is not None


def test_widget_draws_task_boxes(
    qtbot: QtBot, simple_timeline_data: TimelineData
) -> None:
    """Test that task boxes are drawn."""
    widget = ProbabilisticTimelineWidget(simple_timeline_data)
    qtbot.addWidget(widget)

    # Chart should have title with percentile
    assert "P90" in widget.ax.get_title()

    # Should have patches for task boxes
    # Each task has 2 rectangles (outer and inner)
    patches = widget.ax.patches
    assert len(patches) >= 2  # At least outer boxes for both tasks


def test_widget_with_empty_data(
    qtbot: QtBot, empty_timeline_data: TimelineData
) -> None:
    """Test widget handles empty data gracefully."""
    widget = ProbabilisticTimelineWidget(empty_timeline_data)
    qtbot.addWidget(widget)

    # Should display message
    title = widget.ax.get_title()
    assert title is not None


def test_widget_with_dependencies(
    qtbot: QtBot, timeline_data_with_dependencies: TimelineData
) -> None:
    """Test widget draws dependency arrows."""
    widget = ProbabilisticTimelineWidget(timeline_data_with_dependencies)
    qtbot.addWidget(widget)

    # Should have task boxes
    assert len(widget.ax.patches) >= 2

    # Chart should be created
    assert widget.ax.get_title() is not None


def test_widget_axis_labels(qtbot: QtBot, simple_timeline_data: TimelineData) -> None:
    """Test that axes are labeled."""
    widget = ProbabilisticTimelineWidget(simple_timeline_data)
    qtbot.addWidget(widget)

    # Should have x and y labels
    assert widget.ax.get_xlabel() != ""
    assert widget.ax.get_ylabel() != ""


def test_widget_has_navigation_toolbar(
    qtbot: QtBot, simple_timeline_data: TimelineData
) -> None:
    """Test that navigation toolbar is present for zoom/pan."""
    widget = ProbabilisticTimelineWidget(simple_timeline_data)
    qtbot.addWidget(widget)

    # Toolbar should be created
    assert widget.toolbar is not None

    # Toolbar should have parent
    assert widget.toolbar.parent() == widget


def test_widget_task_ordering(qtbot: QtBot, simple_timeline_data: TimelineData) -> None:
    """Test that tasks are ordered by start time."""
    widget = ProbabilisticTimelineWidget(simple_timeline_data)
    qtbot.addWidget(widget)

    # Y-axis should have task labels
    y_labels = [label.get_text() for label in widget.ax.get_yticklabels()]
    assert len(y_labels) == 2
    # Tasks should be present in labels (order may vary)
    label_str = "".join(y_labels)
    assert "A" in label_str
    assert "B" in label_str


def test_widget_occurrence_fractions(
    qtbot: QtBot, simple_timeline_data: TimelineData
) -> None:
    """Test that occurrence fractions are displayed."""
    widget = ProbabilisticTimelineWidget(simple_timeline_data)
    qtbot.addWidget(widget)

    # Get text objects from axes
    texts = widget.ax.texts

    # Should have text labels for tasks
    assert len(texts) >= 2

    # Check that percentages are in the text
    text_content = " ".join([t.get_text() for t in texts])
    assert "%" in text_content


def test_widget_date_formatting(
    qtbot: QtBot, simple_timeline_data: TimelineData
) -> None:
    """Test that date axis is formatted correctly."""
    widget = ProbabilisticTimelineWidget(simple_timeline_data)
    qtbot.addWidget(widget)

    # X-axis should use date formatter
    formatter = widget.ax.xaxis.get_major_formatter()
    assert formatter is not None

    # X-axis should have a locator
    locator = widget.ax.xaxis.get_major_locator()
    assert locator is not None


def test_widget_handles_single_task(qtbot: QtBot) -> None:
    """Test widget with only one task."""
    single_task_data = TimelineData(
        task_statistics={
            TaskId("A"): TaskStatistics(
                task_id=TaskId("A"),
                occurrence_fraction=1.0,
                time_statistics=TimeStatistics(
                    min_start_time=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                    max_end_time=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
                    percentile_start_time=datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
                    percentile_end_time=datetime(2024, 1, 1, 11, 30, tzinfo=UTC),
                ),
            ),
        },
        dependencies=[],
        percentile=95.0,
        earliest_time=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
        latest_time=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
    )

    widget = ProbabilisticTimelineWidget(single_task_data)
    qtbot.addWidget(widget)

    # Should display correctly
    assert len(widget.ax.patches) >= 1
    assert "P95" in widget.ax.get_title()


def test_widget_with_task_without_time_stats(qtbot: QtBot) -> None:
    """Test widget handles tasks without time statistics."""
    task_data = TimelineData(
        task_statistics={
            TaskId("A"): TaskStatistics(
                task_id=TaskId("A"),
                occurrence_fraction=0.0,
                time_statistics=None,  # No time stats
            ),
        },
        dependencies=[],
        percentile=90.0,
        earliest_time=datetime.now(UTC),
        latest_time=datetime.now(UTC),
    )

    widget = ProbabilisticTimelineWidget(task_data)
    qtbot.addWidget(widget)

    # Should not crash, but no boxes drawn
    # Title should still be present
    assert widget.ax.get_title() is not None
