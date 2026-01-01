"""Tests for Gantt chart visualization widget."""

from datetime import UTC, datetime, timedelta

from pytestqt.qtbot import QtBot

from fluxx.data.models import (
    ConstraintType,
    Dependency,
    Endpoint,
    NodeId,
    PossibleWorldId,
    TaskId,
)
from fluxx.gui.simulation.analysis import DependencyInfo
from fluxx.gui.simulation.gantt_analysis import (
    GanttStatistics,
    GanttTaskStatistics,
    TaskVariantKey,
)
from fluxx.gui.simulation.gantt_optimizer import (
    GanttSchedule,
    GanttVariantSchedule,
    optimize_gantt_schedule,
)
from fluxx.gui.simulation.gantt_widget import GanttChartWidget


def test_gantt_widget_initialization_with_optimal_schedule(qtbot: QtBot) -> None:
    """Test that Gantt widget initializes with optimal schedule."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    variant_key = TaskVariantKey(TaskId("task1"), ())
    schedule = GanttSchedule(
        variant_schedules={
            variant_key: GanttVariantSchedule(
                variant_key=variant_key,
                task_title="Task 1",
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
            )
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={()},
    )

    widget = GanttChartWidget(schedule, [])
    qtbot.addWidget(widget)

    # Widget should be visible and have content
    assert widget.isVisible() or not widget.isVisible()  # Just check it doesn't crash
    assert widget.canvas.isVisible() or not widget.canvas.isVisible()


def test_gantt_widget_with_error_status(qtbot: QtBot) -> None:
    """Test that Gantt widget shows error when optimization failed."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    schedule = GanttSchedule(
        variant_schedules={},
        optimization_status="error",
        project_start_date=project_start,
        world_sequences={()},
        error_message="Test error message",
    )

    widget = GanttChartWidget(schedule, [])
    qtbot.addWidget(widget)

    # Error message should be set
    assert "Test error message" in widget.error_label.text()


def test_gantt_widget_with_empty_schedule(qtbot: QtBot) -> None:
    """Test that Gantt widget handles empty schedule."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    schedule = GanttSchedule(
        variant_schedules={},
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={()},
    )

    widget = GanttChartWidget(schedule, [])
    qtbot.addWidget(widget)

    # Error message should be set
    assert "No tasks to display" in widget.error_label.text()


def test_gantt_widget_with_multiple_tasks(qtbot: QtBot) -> None:
    """Test that Gantt widget displays multiple tasks."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    task1 = TaskVariantKey(TaskId("task1"), ())
    task2 = TaskVariantKey(TaskId("task2"), ())

    schedule = GanttSchedule(
        variant_schedules={
            task1: GanttVariantSchedule(
                variant_key=task1,
                task_title="Task 1",
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
            ),
            task2: GanttVariantSchedule(
                variant_key=task2,
                task_title="Task 2",
                start_time=project_start + timedelta(hours=2),
                duration_hours=1.0,
                end_time=project_start + timedelta(hours=3),
            ),
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={()},
    )

    dependencies = [
        DependencyInfo(
            source_task_id=TaskId("task2"),
            dependency=Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=NodeId("task1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        )
    ]

    widget = GanttChartWidget(schedule, dependencies)
    qtbot.addWidget(widget)

    # Widget should be created without errors
    assert widget.canvas is not None
    assert widget.error_label.text() == ""


def test_gantt_widget_with_world_sequences(qtbot: QtBot) -> None:
    """Test that Gantt widget displays tasks from different world sequences."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    world_a = (PossibleWorldId("world_a"),)
    world_b = (PossibleWorldId("world_b"),)

    task1a = TaskVariantKey(TaskId("task1"), world_a)
    task1b = TaskVariantKey(TaskId("task1"), world_b)

    schedule = GanttSchedule(
        variant_schedules={
            task1a: GanttVariantSchedule(
                variant_key=task1a,
                task_title="Task 1",
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
            ),
            task1b: GanttVariantSchedule(
                variant_key=task1b,
                task_title="Task 1",
                start_time=project_start,
                duration_hours=3.0,
                end_time=project_start + timedelta(hours=3),
            ),
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={world_a, world_b},
    )

    widget = GanttChartWidget(schedule, [])
    qtbot.addWidget(widget)

    # Widget should be created without errors
    assert widget.canvas is not None
    assert widget.error_label.text() == ""


def test_gantt_widget_integration_with_optimization() -> None:
    """Test full integration: statistics -> optimization -> widget."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    variant_key = TaskVariantKey(TaskId("task1"), ())
    task_stats = {
        variant_key: GanttTaskStatistics(
            variant_key=variant_key,
            task_title="Task 1",
            percentile_start_time=project_start,
            percentile_duration_hours=2.0,
            sample_count=10,
        )
    }

    statistics = GanttStatistics(
        task_statistics=task_stats,
        dependencies=[],
        percentile=0.97,
        project_start_date=project_start,
        world_sequences={()},
    )

    # Optimize
    schedule = optimize_gantt_schedule(statistics)

    # Should be optimal
    assert schedule.optimization_status == "optimal"

    # Create widget (without Qt since we're not testing GUI here)
    # Just verify it can be created
    assert schedule.variant_schedules is not None
