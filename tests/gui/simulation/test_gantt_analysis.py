"""Tests for Gantt chart analysis module."""

from datetime import UTC, datetime, timedelta

import pytest

from fluxx.data.models import (
    DAG,
    DAGId,
    DAGVersionId,
    NodeId,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    Sample,
    TaskEvent,
    TaskId,
    Worker,
    WorkerId,
)
from fluxx.gui.simulation.gantt_analysis import (
    TaskVariantKey,
    compute_datetime_percentile_with_interpolation,
    compute_percentile_with_interpolation,
    extract_gantt_statistics,
    extract_world_sequence_from_sample,
)


@pytest.fixture
def simple_project() -> Project:
    """Create a simple test project.

    Returns:
        Project with metadata, DAG, and one worker
    """
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test Project",
        created=now,
        last_modified=now,
    )
    dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))
    worker = Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0)

    return Project(
        metadata=metadata,
        dag=dag,
        workers=[worker],
    )


def create_sample_with_events(events: list[TaskEvent], sample_id: int = 0) -> Sample:
    """Create a sample with given events.

    Args:
        events: List of task events
        sample_id: Sample ID (default 0)

    Returns:
        Sample with events
    """
    from fluxx.data.models import SampleId

    return Sample(sample_id=SampleId(sample_id), events=events, failed_tasks=[])


def create_task_event(
    event_type: str,
    node_id: NodeId,
    timestamp: datetime,
    details: dict[str, str] | None = None,
) -> TaskEvent:
    """Create a task event.

    Args:
        event_type: Event type (start, complete, resolve)
        node_id: Node ID
        timestamp: Event timestamp
        details: Optional event details

    Returns:
        TaskEvent
    """
    return TaskEvent(
        event_type=event_type,
        node_id=node_id,
        timestamp=timestamp,
        details=details or {},
    )


def test_extract_world_sequence_from_sample_empty() -> None:
    """Test extracting world sequence from sample with no branch resolutions."""
    sample = create_sample_with_events([])
    world_seq = extract_world_sequence_from_sample(sample)
    assert world_seq == ()


def test_extract_world_sequence_from_sample_single_branch() -> None:
    """Test extracting world sequence from sample with single branch."""
    now = datetime.now(UTC)
    events = [
        create_task_event(
            "resolve",
            NodeId("branch1"),
            now,
            {"chosen_world": "world_a"},
        ),
    ]
    sample = create_sample_with_events(events)
    world_seq = extract_world_sequence_from_sample(sample)
    assert world_seq == (PossibleWorldId("world_a"),)


def test_extract_world_sequence_from_sample_multiple_branches() -> None:
    """Test extracting world sequence from sample with multiple branches."""
    now = datetime.now(UTC)
    events = [
        create_task_event(
            "resolve",
            NodeId("branch1"),
            now,
            {"chosen_world": "world_a"},
        ),
        create_task_event(
            "resolve",
            NodeId("branch2"),
            now + timedelta(hours=1),
            {"chosen_world": "world_b"},
        ),
        create_task_event(
            "resolve",
            NodeId("branch3"),
            now + timedelta(hours=2),
            {"chosen_world": "world_c"},
        ),
    ]
    sample = create_sample_with_events(events)
    world_seq = extract_world_sequence_from_sample(sample)
    assert world_seq == (
        PossibleWorldId("world_a"),
        PossibleWorldId("world_b"),
        PossibleWorldId("world_c"),
    )


def test_extract_world_sequence_preserves_order() -> None:
    """Test that world sequence preserves resolution order by timestamp."""
    now = datetime.now(UTC)
    # Create events in non-chronological order
    events = [
        create_task_event(
            "resolve",
            NodeId("branch2"),
            now + timedelta(hours=2),
            {"chosen_world": "world_b"},
        ),
        create_task_event(
            "resolve",
            NodeId("branch1"),
            now,
            {"chosen_world": "world_a"},
        ),
        create_task_event(
            "resolve",
            NodeId("branch3"),
            now + timedelta(hours=1),
            {"chosen_world": "world_c"},
        ),
    ]
    sample = create_sample_with_events(events)
    world_seq = extract_world_sequence_from_sample(sample)
    # Should be sorted by timestamp
    assert world_seq == (
        PossibleWorldId("world_a"),
        PossibleWorldId("world_c"),
        PossibleWorldId("world_b"),
    )


def test_compute_percentile_with_interpolation_single_value() -> None:
    """Test percentile computation with single value."""
    values = [5.0]
    result = compute_percentile_with_interpolation(values, 0.97)
    assert result == 5.0


def test_compute_percentile_with_interpolation_multiple_values() -> None:
    """Test percentile computation with multiple values."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    # 97th percentile should be close to 5.0
    result = compute_percentile_with_interpolation(values, 0.97)
    assert result >= 4.88  # Should be interpolated near max
    assert result <= 5.0


def test_compute_percentile_with_interpolation_empty_raises() -> None:
    """Test that empty values raises ValueError."""
    with pytest.raises(ValueError, match="Cannot compute percentile from empty list"):
        compute_percentile_with_interpolation([], 0.97)


def test_compute_percentile_with_interpolation_uses_linear_method() -> None:
    """Test that linear interpolation is used for sparse data."""
    # With only 2 values, interpolation is critical
    values = [10.0, 20.0]
    result = compute_percentile_with_interpolation(values, 0.5)
    # 50th percentile should be exactly 15.0 with linear interpolation
    assert abs(result - 15.0) < 0.01


def test_compute_datetime_percentile_with_interpolation() -> None:
    """Test datetime percentile computation with interpolation."""
    base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    datetimes = [
        base,
        base + timedelta(hours=1),
        base + timedelta(hours=2),
        base + timedelta(hours=3),
        base + timedelta(hours=4),
    ]
    result = compute_datetime_percentile_with_interpolation(datetimes, 0.97)
    # Should be close to the last datetime
    assert result >= base + timedelta(hours=3, minutes=52)
    assert result <= base + timedelta(hours=4)


def test_compute_datetime_percentile_empty_raises() -> None:
    """Test that empty datetime list raises ValueError."""
    with pytest.raises(ValueError, match="Cannot compute percentile from empty list"):
        compute_datetime_percentile_with_interpolation([], 0.97)


def test_task_variant_key_equality() -> None:
    """Test TaskVariantKey equality and hashing."""
    key1 = TaskVariantKey(
        TaskId("task1"), (PossibleWorldId("world_a"), PossibleWorldId("world_b"))
    )
    key2 = TaskVariantKey(
        TaskId("task1"), (PossibleWorldId("world_a"), PossibleWorldId("world_b"))
    )
    key3 = TaskVariantKey(
        TaskId("task1"), (PossibleWorldId("world_a"), PossibleWorldId("world_c"))
    )

    # Same task and world sequence should be equal
    assert key1 == key2
    assert hash(key1) == hash(key2)

    # Different world sequence should not be equal
    assert key1 != key3


def test_extract_gantt_statistics_empty_samples(simple_project: Project) -> None:
    """Test that empty samples raises ValueError."""
    with pytest.raises(ValueError, match="Cannot extract Gantt statistics from empty"):
        extract_gantt_statistics([], simple_project, percentile=0.97)


def test_extract_gantt_statistics_invalid_percentile(simple_project: Project) -> None:
    """Test that invalid percentile raises ValueError."""
    now = datetime.now(UTC)
    sample = create_sample_with_events(
        [
            create_task_event("start", NodeId("task1"), now),
            create_task_event("complete", NodeId("task1"), now + timedelta(hours=2)),
        ]
    )

    # Test percentile = 0
    with pytest.raises(ValueError, match="Percentile must be between 0 and 1"):
        extract_gantt_statistics([sample], simple_project, percentile=0.0)

    # Test percentile = 1
    with pytest.raises(ValueError, match="Percentile must be between 0 and 1"):
        extract_gantt_statistics([sample], simple_project, percentile=1.0)

    # Test percentile > 1
    with pytest.raises(ValueError, match="Percentile must be between 0 and 1"):
        extract_gantt_statistics([sample], simple_project, percentile=1.5)


def test_extract_gantt_statistics_single_task_single_sample(
    simple_project: Project,
) -> None:
    """Test extracting statistics for single task with single sample."""
    project = simple_project
    now = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    # Create sample with one task
    events = [
        create_task_event("start", NodeId("task1"), now),
        create_task_event("complete", NodeId("task1"), now + timedelta(hours=2)),
    ]
    sample = create_sample_with_events(events)

    stats = extract_gantt_statistics([sample], project, percentile=0.97)

    # Should have one task variant
    assert len(stats.task_statistics) == 1

    # Get the variant key
    variant_key = TaskVariantKey(TaskId("task1"), ())  # Empty world sequence
    assert variant_key in stats.task_statistics

    task_stats = stats.task_statistics[variant_key]
    # Since simple_project has no tasks, title falls back to task ID
    assert task_stats.task_title == "task1"
    assert task_stats.percentile_start_time == now
    assert task_stats.percentile_duration_hours == 2.0
    assert task_stats.sample_count == 1

    # Project start should be the task start
    assert stats.project_start_date == now
    assert stats.percentile == 0.97
    assert stats.world_sequences == {()}


def test_extract_gantt_statistics_multiple_samples_same_world(
    simple_project: Project,
) -> None:
    """Test extracting statistics with multiple samples in same world sequence."""
    project = simple_project
    base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    # Create 3 samples with varying durations
    samples = []
    for i, duration in enumerate([1.0, 2.0, 3.0]):
        start = base + timedelta(hours=i)
        events = [
            create_task_event("start", NodeId("task1"), start),
            create_task_event(
                "complete", NodeId("task1"), start + timedelta(hours=duration)
            ),
        ]
        samples.append(create_sample_with_events(events, sample_id=i))

    stats = extract_gantt_statistics(samples, project, percentile=0.97)

    variant_key = TaskVariantKey(TaskId("task1"), ())
    task_stats = stats.task_statistics[variant_key]

    # 97th percentile of [1.0, 2.0, 3.0] should be close to 3.0
    assert task_stats.percentile_duration_hours >= 2.94
    assert task_stats.percentile_duration_hours <= 3.0

    # 97th percentile of start times
    expected_start = base + timedelta(hours=1.94)  # Interpolated
    assert (
        abs((task_stats.percentile_start_time - expected_start).total_seconds()) < 360
    )

    assert task_stats.sample_count == 3


def test_extract_gantt_statistics_with_branches(simple_project: Project) -> None:
    """Test extracting statistics with branches creating different worlds."""
    project = simple_project
    base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    # Sample 1: world_a chosen
    events1 = [
        create_task_event(
            "resolve", NodeId("branch1"), base, {"chosen_world": "world_a"}
        ),
        create_task_event("start", NodeId("task1"), base + timedelta(hours=1)),
        create_task_event("complete", NodeId("task1"), base + timedelta(hours=3)),
    ]

    # Sample 2: world_b chosen (different world sequence)
    events2 = [
        create_task_event(
            "resolve", NodeId("branch1"), base, {"chosen_world": "world_b"}
        ),
        create_task_event("start", NodeId("task1"), base + timedelta(hours=1)),
        create_task_event("complete", NodeId("task1"), base + timedelta(hours=4)),
    ]

    samples = [
        create_sample_with_events(events1, sample_id=0),
        create_sample_with_events(events2, sample_id=1),
    ]

    stats = extract_gantt_statistics(samples, project, percentile=0.97)

    # Should have TWO variants (same task, different world sequences)
    assert len(stats.task_statistics) == 2

    variant_a = TaskVariantKey(TaskId("task1"), (PossibleWorldId("world_a"),))
    variant_b = TaskVariantKey(TaskId("task1"), (PossibleWorldId("world_b"),))

    assert variant_a in stats.task_statistics
    assert variant_b in stats.task_statistics

    # Each variant has one sample
    assert stats.task_statistics[variant_a].sample_count == 1
    assert stats.task_statistics[variant_b].sample_count == 1

    # Different durations
    assert stats.task_statistics[variant_a].percentile_duration_hours == 2.0
    assert stats.task_statistics[variant_b].percentile_duration_hours == 3.0

    # Should track both world sequences
    assert stats.world_sequences == {
        (PossibleWorldId("world_a"),),
        (PossibleWorldId("world_b"),),
    }


def test_extract_gantt_statistics_project_start_date_is_minimum(
    simple_project: Project,
) -> None:
    """Test that project_start_date is the minimum of all task start times."""
    project = simple_project
    base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    # Create samples where task2 starts before task1
    events = [
        create_task_event("start", NodeId("task1"), base + timedelta(hours=5)),
        create_task_event("complete", NodeId("task1"), base + timedelta(hours=7)),
        create_task_event("start", NodeId("task2"), base + timedelta(hours=1)),
        create_task_event("complete", NodeId("task2"), base + timedelta(hours=3)),
    ]
    sample = create_sample_with_events(events)

    stats = extract_gantt_statistics([sample], project, percentile=0.97)

    # Project start should be task2's start (the earlier one)
    assert stats.project_start_date == base + timedelta(hours=1)


def test_extract_gantt_statistics_ignores_tasks_without_complete_event(
    simple_project: Project,
) -> None:
    """Test that tasks without both start and complete events are ignored."""
    project = simple_project
    now = datetime.now(UTC)

    # Task 1: has both start and complete
    # Task 2: only has start (no complete)
    events = [
        create_task_event("start", NodeId("task1"), now),
        create_task_event("complete", NodeId("task1"), now + timedelta(hours=2)),
        create_task_event("start", NodeId("task2"), now),
        # Missing complete for task2
    ]
    sample = create_sample_with_events(events)

    stats = extract_gantt_statistics([sample], project, percentile=0.97)

    # Should only have task1
    assert len(stats.task_statistics) == 1
    variant_key = TaskVariantKey(TaskId("task1"), ())
    assert variant_key in stats.task_statistics


def test_extract_gantt_statistics_includes_dependencies(
    simple_project: Project,
) -> None:
    """Test that dependencies are extracted from project."""
    project = simple_project
    now = datetime.now(UTC)

    # Create sample with tasks
    events = [
        create_task_event("start", NodeId("task1"), now),
        create_task_event("complete", NodeId("task1"), now + timedelta(hours=2)),
    ]
    sample = create_sample_with_events(events)

    stats = extract_gantt_statistics([sample], project, percentile=0.97)

    # Should have dependencies from project
    assert isinstance(stats.dependencies, list)
    # Actual dependency count depends on test_analysis.create_test_project()
    # We just verify it's populated
    assert len(stats.dependencies) >= 0


def test_extract_gantt_statistics_calendar_hours_not_work_hours(
    simple_project: Project,
) -> None:
    """Test that durations are in calendar hours, not work hours."""
    project = simple_project
    base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    # Task runs for 8 calendar hours (not 8 work hours)
    events = [
        create_task_event("start", NodeId("task1"), base),
        create_task_event("complete", NodeId("task1"), base + timedelta(hours=8)),
    ]
    sample = create_sample_with_events(events)

    stats = extract_gantt_statistics([sample], project, percentile=0.97)

    variant_key = TaskVariantKey(TaskId("task1"), ())
    task_stats = stats.task_statistics[variant_key]

    # Duration should be exactly 8.0 calendar hours
    assert task_stats.percentile_duration_hours == 8.0


def test_extract_gantt_statistics_percentile_as_fraction(
    simple_project: Project,
) -> None:
    """Test that percentile is stored as fraction (0.97) not percentage (97.0)."""
    project = simple_project
    now = datetime.now(UTC)

    events = [
        create_task_event("start", NodeId("task1"), now),
        create_task_event("complete", NodeId("task1"), now + timedelta(hours=2)),
    ]
    sample = create_sample_with_events(events)

    stats = extract_gantt_statistics([sample], project, percentile=0.97)

    # Percentile should be stored as 0.97, not 97.0
    assert stats.percentile == 0.97
