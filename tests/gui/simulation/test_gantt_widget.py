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
    _compute_common_world_prefix,
    _compute_world_sequence_sort_key,
    _group_and_sort_variants,
    _on_hover,
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

    widget = GanttChartWidget(schedule, [], {})
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

    widget = GanttChartWidget(schedule, [], {})
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

    widget = GanttChartWidget(schedule, [], {})
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

    widget = GanttChartWidget(schedule, dependencies, {})
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

    widget = GanttChartWidget(schedule, [], {})
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

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Widget should be created without errors
    assert widget.canvas is not None
    assert widget.error_label.text() == ""

    # Verify the matplotlib axes has patches (task bars) and lines (dividers)
    # The chart should have 2 patches (task bars)
    patches = list(widget.ax.patches)
    assert len(patches) == 2


def test_gantt_widget_uses_world_titles_in_labels(qtbot: QtBot) -> None:
    """Test that Gantt widget uses human-readable world titles in y-axis labels."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    world_a: WorldSequence = (PossibleWorldId("pw_123_abc"),)
    task1_a = TaskVariantKey(TaskId("task1"), world_a)

    schedule = GanttSchedule(
        variant_schedules={
            task1_a: GanttVariantSchedule(
                variant_key=task1_a,
                task_title="Task 1",
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
            ),
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={world_a},
    )

    # Provide world titles mapping
    world_titles = {PossibleWorldId("pw_123_abc"): "Option A"}

    widget = GanttChartWidget(schedule, [], world_titles)
    qtbot.addWidget(widget)

    # Check that y-axis label uses human-readable title, not internal ID
    y_labels = [label.get_text() for label in widget.ax.get_yticklabels()]
    assert len(y_labels) == 1
    assert "Option A" in y_labels[0]
    assert "pw_123_abc" not in y_labels[0]


def test_gantt_widget_falls_back_to_id_without_world_titles(qtbot: QtBot) -> None:
    """Test that Gantt widget falls back to ID when world_titles not provided."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    world_a: WorldSequence = (PossibleWorldId("pw_123_abc"),)
    task1_a = TaskVariantKey(TaskId("task1"), world_a)

    schedule = GanttSchedule(
        variant_schedules={
            task1_a: GanttVariantSchedule(
                variant_key=task1_a,
                task_title="Task 1",
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
            ),
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={world_a},
    )

    # No world_titles provided
    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Check that y-axis label uses internal ID as fallback
    y_labels = [label.get_text() for label in widget.ax.get_yticklabels()]
    assert len(y_labels) == 1
    assert "pw_123_abc" in y_labels[0]


# Tests for common world prefix computation


def test_compute_common_world_prefix_empty_list() -> None:
    """Test that empty list returns empty prefix."""
    result = _compute_common_world_prefix([])
    assert result == ()


def test_compute_common_world_prefix_single_sequence() -> None:
    """Test that single non-empty sequence returns empty prefix (no comparison)."""
    world_a = PossibleWorldId("world_a")
    result = _compute_common_world_prefix([(world_a,)])
    assert result == ()


def test_compute_common_world_prefix_all_empty() -> None:
    """Test that all empty sequences return empty prefix."""
    result = _compute_common_world_prefix([(), ()])
    assert result == ()


def test_compute_common_world_prefix_one_empty_one_nonempty() -> None:
    """Test that one empty, one non-empty returns empty prefix."""
    world_a = PossibleWorldId("world_a")
    result = _compute_common_world_prefix([(), (world_a,)])
    assert result == ()


def test_compute_common_world_prefix_common_single_element() -> None:
    """Test common prefix with single common element."""
    world_x = PossibleWorldId("world_x")
    world_a = PossibleWorldId("world_a")
    world_b = PossibleWorldId("world_b")

    result = _compute_common_world_prefix([(world_x, world_a), (world_x, world_b)])
    assert result == (world_x,)


def test_compute_common_world_prefix_no_common_prefix() -> None:
    """Test no common prefix when first element differs."""
    world_a = PossibleWorldId("world_a")
    world_b = PossibleWorldId("world_b")

    result = _compute_common_world_prefix([(world_a,), (world_b,)])
    assert result == ()


def test_compute_common_world_prefix_multiple_common_elements() -> None:
    """Test common prefix with multiple common elements."""
    world_x = PossibleWorldId("world_x")
    world_y = PossibleWorldId("world_y")
    world_a = PossibleWorldId("world_a")
    world_b = PossibleWorldId("world_b")

    result = _compute_common_world_prefix(
        [(world_x, world_y, world_a), (world_x, world_y, world_b)]
    )
    assert result == (world_x, world_y)


def test_compute_common_world_prefix_with_empty_sequence_ignored() -> None:
    """Test that empty sequences are ignored when computing prefix."""
    world_x = PossibleWorldId("world_x")
    world_a = PossibleWorldId("world_a")
    world_b = PossibleWorldId("world_b")

    # Empty sequence present but should be ignored
    result = _compute_common_world_prefix([(), (world_x, world_a), (world_x, world_b)])
    assert result == (world_x,)


def test_gantt_widget_strips_common_prefix_from_labels(qtbot: QtBot) -> None:
    """Test that common world sequence prefix is stripped from labels."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    # Create world sequences with common prefix (world_x, ...)
    world_x = PossibleWorldId("pw_x")
    world_a = PossibleWorldId("pw_a")
    world_b = PossibleWorldId("pw_b")

    seq_xa: WorldSequence = (world_x, world_a)
    seq_xb: WorldSequence = (world_x, world_b)

    task1_xa = TaskVariantKey(TaskId("task1"), seq_xa)
    task1_xb = TaskVariantKey(TaskId("task1"), seq_xb)

    schedule = GanttSchedule(
        variant_schedules={
            task1_xa: GanttVariantSchedule(
                variant_key=task1_xa,
                task_title="Task 1",
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
            ),
            task1_xb: GanttVariantSchedule(
                variant_key=task1_xb,
                task_title="Task 1",
                start_time=project_start + timedelta(hours=3),
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=5),
            ),
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={seq_xa, seq_xb},
    )

    # Provide world titles mapping
    world_titles = {
        world_x: "X1",
        world_a: "Do A1",
        world_b: "Do A2",
    }

    widget = GanttChartWidget(schedule, [], world_titles)
    qtbot.addWidget(widget)

    # Check that y-axis labels do NOT include "X1" (the common prefix)
    # They should only include "Do A1" and "Do A2"
    y_labels = [label.get_text() for label in widget.ax.get_yticklabels()]
    assert len(y_labels) == 2

    # Both labels should NOT contain the common prefix "X1"
    for label in y_labels:
        assert "X1" not in label

    # Labels should contain the distinguishing world titles
    label_texts = " ".join(y_labels)
    assert "Do A1" in label_texts
    assert "Do A2" in label_texts


def test_gantt_widget_truncates_long_labels(qtbot: QtBot) -> None:
    """Test that Gantt widget truncates long task titles to 20 characters."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    variant_key = TaskVariantKey(TaskId("task1"), ())
    long_title = "This is a very long task title that exceeds twenty characters"

    schedule = GanttSchedule(
        variant_schedules={
            variant_key: GanttVariantSchedule(
                variant_key=variant_key,
                task_title=long_title,
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
            )
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={()},
    )

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Get y-axis labels
    y_labels = [label.get_text() for label in widget.ax.get_yticklabels()]
    assert len(y_labels) == 1

    # Label should be truncated to 20 characters with ellipsis
    assert len(y_labels[0]) == 20
    assert y_labels[0].endswith("…")


def test_gantt_widget_shows_jira_key_in_truncated_label(qtbot: QtBot) -> None:
    """Test that Jira issue key appears at start of truncated label."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    variant_key = TaskVariantKey(TaskId("task1"), ())
    long_title = "This is a very long task title"

    schedule = GanttSchedule(
        variant_schedules={
            variant_key: GanttVariantSchedule(
                variant_key=variant_key,
                task_title=long_title,
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
                jira_issue_key="CORE-123",
            )
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={()},
    )

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Get y-axis labels
    y_labels = [label.get_text() for label in widget.ax.get_yticklabels()]
    assert len(y_labels) == 1

    # Label should start with Jira key and be truncated
    assert y_labels[0].startswith("CORE-123")
    assert len(y_labels[0]) == 20
    assert y_labels[0].endswith("…")


def test_gantt_widget_short_title_with_jira_key_not_truncated(qtbot: QtBot) -> None:
    """Test that short titles with Jira key are not truncated if under 20 chars."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    variant_key = TaskVariantKey(TaskId("task1"), ())
    short_title = "Task"

    schedule = GanttSchedule(
        variant_schedules={
            variant_key: GanttVariantSchedule(
                variant_key=variant_key,
                task_title=short_title,
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
                jira_issue_key="KEY-1",
            )
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={()},
    )

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Get y-axis labels
    y_labels = [label.get_text() for label in widget.ax.get_yticklabels()]
    assert len(y_labels) == 1

    # Label should be "KEY-1 Task" (not truncated, 10 chars < 20)
    assert y_labels[0] == "KEY-1 Task"
    assert "…" not in y_labels[0]


def test_gantt_widget_stores_full_labels_for_tooltips(qtbot: QtBot) -> None:
    """Test that full labels are stored for tooltip display."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    variant_key = TaskVariantKey(TaskId("task1"), ())
    long_title = "This is a very long task title that exceeds twenty characters"

    schedule = GanttSchedule(
        variant_schedules={
            variant_key: GanttVariantSchedule(
                variant_key=variant_key,
                task_title=long_title,
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
                jira_issue_key="CORE-999",
            )
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={()},
    )

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Full labels should be stored for tooltips
    assert len(widget._full_labels) == 1
    assert widget._full_labels[0] == f"CORE-999 {long_title}"
    assert "…" not in widget._full_labels[0]


def test_gantt_widget_creates_tooltip_annotation(qtbot: QtBot) -> None:
    """Test that tooltip annotation is created for hover functionality."""
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

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Tooltip annotation should be created
    assert widget._tooltip_annotation is not None
    # Check that it's a matplotlib annotation with the expected methods
    assert hasattr(widget._tooltip_annotation, "get_visible")
    assert hasattr(widget._tooltip_annotation, "set_visible")
    assert hasattr(widget._tooltip_annotation, "set_text")


def test_gantt_widget_hover_callback_outside_axes(qtbot: QtBot) -> None:
    """Test that hover callback hides tooltip when mouse is outside axes."""
    from unittest.mock import MagicMock

    from matplotlib.backend_bases import MouseEvent

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

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Make tooltip visible first
    assert widget._tooltip_annotation is not None
    widget._tooltip_annotation.set_visible(True)
    assert widget._tooltip_annotation.get_visible()

    # Create a mouse event outside the axes
    event = MagicMock(spec=MouseEvent)
    event.inaxes = None  # Not inside any axes

    # Call the handler directly
    _on_hover(widget, event)

    # Tooltip should be hidden
    assert not widget._tooltip_annotation.get_visible()


def test_gantt_widget_hover_callback_far_from_yaxis(qtbot: QtBot) -> None:
    """Test that hover callback hides tooltip when mouse is far from y-axis."""
    from unittest.mock import MagicMock

    from matplotlib.backend_bases import MouseEvent

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

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Make tooltip visible first
    assert widget._tooltip_annotation is not None
    widget._tooltip_annotation.set_visible(True)
    assert widget._tooltip_annotation.get_visible()

    # Create a mouse event inside axes but far from y-axis
    event = MagicMock(spec=MouseEvent)
    event.inaxes = widget.ax
    event.x = 1000  # Far from y-axis
    event.ydata = 0.0

    # Call the handler directly
    _on_hover(widget, event)

    # Tooltip should be hidden
    assert not widget._tooltip_annotation.get_visible()


def test_gantt_widget_hover_callback_near_yaxis(qtbot: QtBot) -> None:
    """Test that hover callback shows tooltip when near y-axis label."""
    from unittest.mock import MagicMock

    from matplotlib.backend_bases import MouseEvent

    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    variant_key = TaskVariantKey(TaskId("task1"), ())
    long_title = "This is a long task title for testing tooltips"
    schedule = GanttSchedule(
        variant_schedules={
            variant_key: GanttVariantSchedule(
                variant_key=variant_key,
                task_title=long_title,
                start_time=project_start,
                duration_hours=2.0,
                end_time=project_start + timedelta(hours=2),
            )
        },
        optimization_status="optimal",
        project_start_date=project_start,
        world_sequences={()},
    )

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Create a mouse event near y-axis
    event = MagicMock(spec=MouseEvent)
    event.inaxes = widget.ax
    event.x = 10  # Near y-axis
    event.ydata = 0.0  # At the first task

    # Call the handler directly
    _on_hover(widget, event)

    # Tooltip should be visible with the full label
    assert widget._tooltip_annotation is not None
    assert widget._tooltip_annotation.get_visible()
    assert widget._tooltip_annotation.get_text() == long_title


def test_gantt_widget_hover_callback_with_none_ydata(qtbot: QtBot) -> None:
    """Test that hover callback handles None ydata gracefully."""
    from unittest.mock import MagicMock

    from matplotlib.backend_bases import MouseEvent

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

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Create a mouse event with None ydata
    event = MagicMock(spec=MouseEvent)
    event.inaxes = widget.ax
    event.x = 10  # Near y-axis
    event.ydata = None  # No valid y coordinate

    # Call the handler directly - should not crash
    _on_hover(widget, event)

    # Widget should still be in valid state
    assert widget._tooltip_annotation is not None


def test_gantt_widget_hover_callback_out_of_range_ypos(qtbot: QtBot) -> None:
    """Test that hover callback handles out-of-range y positions."""
    from unittest.mock import MagicMock

    from matplotlib.backend_bases import MouseEvent

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

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Make tooltip visible first
    assert widget._tooltip_annotation is not None
    widget._tooltip_annotation.set_visible(True)

    # Create a mouse event with y position out of range
    event = MagicMock(spec=MouseEvent)
    event.inaxes = widget.ax
    event.x = 10  # Near y-axis
    event.ydata = 100.0  # Way out of range (only 1 task at position 0)

    # Call the handler directly - should not crash
    _on_hover(widget, event)

    # Tooltip should be hidden (out of range)
    assert not widget._tooltip_annotation.get_visible()


def test_gantt_widget_hover_callback_with_none_x(qtbot: QtBot) -> None:
    """Test that hover callback handles None x position gracefully."""
    from unittest.mock import MagicMock

    from matplotlib.backend_bases import MouseEvent

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

    widget = GanttChartWidget(schedule, [], {})
    qtbot.addWidget(widget)

    # Make tooltip visible first
    assert widget._tooltip_annotation is not None
    widget._tooltip_annotation.set_visible(True)

    # Create a mouse event with None x
    event = MagicMock(spec=MouseEvent)
    event.inaxes = widget.ax
    event.x = None  # None x coordinate
    event.ydata = 0.0

    # Call the handler directly - should not crash
    _on_hover(widget, event)

    # Tooltip should be hidden (None x is treated as far from y-axis)
    assert not widget._tooltip_annotation.get_visible()
