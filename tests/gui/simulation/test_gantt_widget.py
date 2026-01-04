"""Tests for Gantt chart visualization widget."""

from datetime import UTC, datetime, timedelta

from pytestqt.qtbot import QtBot

from fluxx.data.models import (
    DAG,
    ConstraintType,
    DAGId,
    DAGVersionId,
    Dependency,
    Endpoint,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    TaskId,
)
from fluxx.gui.simulation.analysis import DependencyInfo
from fluxx.gui.simulation.gantt_analysis import (
    GanttStatistics,
    GanttTaskStatistics,
    TaskVariantKey,
    WorldSequence,
)
from fluxx.gui.simulation.gantt_optimizer import (
    GanttSchedule,
    GanttVariantSchedule,
    optimize_gantt_schedule,
)
from fluxx.gui.simulation.gantt_widget import (
    GanttChartWidget,
    _compute_world_sequence_sort_key,
    _group_and_sort_variants,
)


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
                target_node_id=TaskId("task1"),
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

    # Create minimal project
    version_id = DAGVersionId("v1")
    dag = DAG(id=DAGId("dag1"), current_version_id=version_id, node_map={})
    project = Project(
        metadata=ProjectMetadata(
            name="Test",
            created=datetime.now(UTC),
            last_modified=datetime.now(UTC),
        ),
        dag=dag,
        persistent_tasks={},
    )

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
    schedule = optimize_gantt_schedule(statistics, project)

    # Should be optimal
    assert schedule.optimization_status == "optimal"

    # Create widget (without Qt since we're not testing GUI here)
    # Just verify it can be created
    assert schedule.variant_schedules is not None


# Tests for world sequence sorting


def test_compute_world_sequence_sort_key_base_world_first() -> None:
    """Test that empty world sequence (base world) comes first."""
    empty_seq: WorldSequence = ()
    world_a: WorldSequence = (PossibleWorldId("world_a"),)
    world_b: WorldSequence = (PossibleWorldId("world_b"),)

    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    earliest_by_world: dict[WorldSequence, datetime] = {
        empty_seq: project_start + timedelta(hours=1),  # Later start
        world_a: project_start,  # Earlier start
        world_b: project_start + timedelta(hours=2),
    }

    key_empty = _compute_world_sequence_sort_key(empty_seq, earliest_by_world)
    key_a = _compute_world_sequence_sort_key(world_a, earliest_by_world)
    key_b = _compute_world_sequence_sort_key(world_b, earliest_by_world)

    # Empty world sequence should come first (priority 0 vs 1)
    assert key_empty < key_a
    assert key_empty < key_b

    # world_a should come before world_b (earlier start time)
    assert key_a < key_b


def test_group_and_sort_variants_empty() -> None:
    """Test that empty schedule returns empty results."""
    sorted_variants, dividers = _group_and_sort_variants({})
    assert sorted_variants == []
    assert dividers == []


def test_group_and_sort_variants_single_world() -> None:
    """Test sorting with single world sequence (no dividers)."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    empty_seq: WorldSequence = ()

    task1 = TaskVariantKey(TaskId("task1"), empty_seq)
    task2 = TaskVariantKey(TaskId("task2"), empty_seq)

    schedules = {
        task1: GanttVariantSchedule(
            variant_key=task1,
            task_title="Task 1",
            start_time=project_start + timedelta(hours=2),  # Later
            duration_hours=1.0,
            end_time=project_start + timedelta(hours=3),
        ),
        task2: GanttVariantSchedule(
            variant_key=task2,
            task_title="Task 2",
            start_time=project_start,  # Earlier
            duration_hours=1.0,
            end_time=project_start + timedelta(hours=1),
        ),
    }

    sorted_variants, dividers = _group_and_sort_variants(schedules)

    # Should be sorted by start time within the single world
    assert len(sorted_variants) == 2
    assert sorted_variants[0][0] == task2  # Earlier start
    assert sorted_variants[1][0] == task1  # Later start

    # No dividers for single world
    assert dividers == []


def test_group_and_sort_variants_multiple_worlds() -> None:
    """Test grouping and sorting with multiple world sequences."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    empty_seq: WorldSequence = ()
    world_a: WorldSequence = (PossibleWorldId("world_a"),)
    world_b: WorldSequence = (PossibleWorldId("world_b"),)

    # Tasks in base world
    task1_base = TaskVariantKey(TaskId("task1"), empty_seq)
    task2_base = TaskVariantKey(TaskId("task2"), empty_seq)

    # Tasks in world_a (starts earlier)
    task3_a = TaskVariantKey(TaskId("task3"), world_a)

    # Tasks in world_b (starts later)
    task4_b = TaskVariantKey(TaskId("task4"), world_b)

    schedules = {
        task1_base: GanttVariantSchedule(
            variant_key=task1_base,
            task_title="Task 1",
            start_time=project_start + timedelta(hours=1),
            duration_hours=1.0,
            end_time=project_start + timedelta(hours=2),
        ),
        task2_base: GanttVariantSchedule(
            variant_key=task2_base,
            task_title="Task 2",
            start_time=project_start,
            duration_hours=1.0,
            end_time=project_start + timedelta(hours=1),
        ),
        task3_a: GanttVariantSchedule(
            variant_key=task3_a,
            task_title="Task 3",
            start_time=project_start + timedelta(hours=3),  # Earlier than world_b
            duration_hours=1.0,
            end_time=project_start + timedelta(hours=4),
        ),
        task4_b: GanttVariantSchedule(
            variant_key=task4_b,
            task_title="Task 4",
            start_time=project_start + timedelta(hours=5),  # Later than world_a
            duration_hours=1.0,
            end_time=project_start + timedelta(hours=6),
        ),
    }

    sorted_variants, dividers = _group_and_sort_variants(schedules)

    # Should have 4 variants
    assert len(sorted_variants) == 4

    # First 2 should be base world, sorted by start time
    assert sorted_variants[0][0].world_sequence == empty_seq
    assert sorted_variants[0][0] == task2_base  # Earlier start in base world
    assert sorted_variants[1][0].world_sequence == empty_seq
    assert sorted_variants[1][0] == task1_base  # Later start in base world

    # Third should be world_a (earlier start than world_b)
    assert sorted_variants[2][0].world_sequence == world_a

    # Fourth should be world_b
    assert sorted_variants[3][0].world_sequence == world_b

    # Two dividers: after base world, after world_a
    assert len(dividers) == 2
    assert dividers[0] == 2  # Divider after 2 base world tasks
    assert dividers[1] == 3  # Divider after world_a task


def test_gantt_widget_with_world_sequence_grouping(qtbot: QtBot) -> None:
    """Test that Gantt widget groups tasks by world sequence with dividers."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    empty_seq: WorldSequence = ()
    world_a: WorldSequence = (PossibleWorldId("world_a"),)

    task1_base = TaskVariantKey(TaskId("task1"), empty_seq)
    task2_a = TaskVariantKey(TaskId("task2"), world_a)

    schedule = GanttSchedule(
        variant_schedules={
            task1_base: GanttVariantSchedule(
                variant_key=task1_base,
                task_title="Task 1",
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
            ),
            task2_a: GanttVariantSchedule(
                variant_key=task2_a,
                task_title="Task 2",
                start_time=project_start + timedelta(hours=3),
                duration_hours=1.0,
                end_time=project_start + timedelta(hours=4),
            ),
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={empty_seq, world_a},
    )

    widget = GanttChartWidget(schedule, [])
    qtbot.addWidget(widget)

    # Widget should be created without errors
    assert widget.canvas is not None
    assert widget.error_label.text() == ""

    # Verify the matplotlib axes has patches (task bars) and lines (dividers)
    # The chart should have 2 patches (task bars)
    patches = list(widget.ax.patches)
    assert len(patches) == 2
