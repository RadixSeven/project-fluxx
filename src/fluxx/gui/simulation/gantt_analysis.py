"""Data extraction for Gantt chart optimization.

Extracts percentile statistics from simulation samples for conservative Gantt chart
generation per spec 8.1.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from fluxx.data.models import (
    NodeId,
    PossibleWorldId,
    Project,
    Sample,
    TaskEvent,
    TaskId,
)
from fluxx.gui.simulation.analysis import DependencyInfo, get_all_tasks_from_project

# Type alias for world sequence (tuple of chosen worlds at each branch)
WorldSequence = tuple[PossibleWorldId, ...]


@dataclass(frozen=True)
class TaskVariantKey:
    """Unique identifier for a task variant (task in specific world sequence)."""

    task_id: TaskId
    world_sequence: WorldSequence  # Which worlds were chosen

    def __hash__(self) -> int:
        """Make hashable for use as dict key."""
        return hash((self.task_id, self.world_sequence))


@dataclass
class GanttTaskStatistics:
    """Percentile statistics for a task variant."""

    variant_key: TaskVariantKey
    task_title: str
    percentile_start_time: datetime  # Pth percentile start (calendar time)
    percentile_duration_hours: float  # Pth percentile duration (calendar hours)
    sample_count: int  # Number of samples with this variant
    jira_issue_key: str | None = None  # Jira issue key if linked (e.g., "CORE-123")


@dataclass
class GanttStatistics:
    """Complete statistics for Gantt chart generation."""

    task_statistics: dict[TaskVariantKey, GanttTaskStatistics]
    dependencies: list[DependencyInfo]  # From project structure
    percentile: float  # e.g., 0.97 for 97%
    project_start_date: datetime  # Min of all start times (handles in-progress tasks)
    world_sequences: set[WorldSequence]  # All observed world sequences


def extract_world_sequence_from_sample(sample: Sample) -> WorldSequence:
    """Extract the sequence of chosen possible worlds from a sample.

    Args:
        sample: Sample to extract world sequence from

    Returns:
        Tuple of PossibleWorldIds in the order branches were resolved
    """
    # Find all branch resolution events
    resolution_events = [
        event for event in sample.events if event.event_type == "branch_resolved"
    ]

    # Sort by timestamp to get resolution order
    resolution_events.sort(key=lambda e: e.timestamp)

    # Extract chosen world from each resolution event
    world_sequence = tuple(
        PossibleWorldId(event.details["chosen_world"]) for event in resolution_events
    )

    return world_sequence


def compute_percentile_with_interpolation(
    values: list[float], percentile: float
) -> float:
    """Compute percentile with linear interpolation when data is sparse.

    Args:
        values: List of values to compute percentile from
        percentile: Percentile as fraction (e.g., 0.97 for 97%)

    Returns:
        Percentile value with linear interpolation
    """
    if not values:
        raise ValueError("Cannot compute percentile from empty list")

    return float(np.percentile(values, percentile * 100, method="linear"))


def compute_datetime_percentile_with_interpolation(
    datetimes: list[datetime], percentile: float
) -> datetime:
    """Compute percentile of datetimes with linear interpolation.

    Args:
        datetimes: List of datetime objects
        percentile: Percentile as fraction (e.g., 0.97 for 97%)

    Returns:
        Percentile datetime with linear interpolation
    """
    if not datetimes:
        raise ValueError("Cannot compute percentile from empty list")

    # Convert to seconds since epoch for interpolation
    epoch = datetime.fromtimestamp(0, tz=datetimes[0].tzinfo)
    seconds = [(dt - epoch).total_seconds() for dt in datetimes]

    percentile_seconds = compute_percentile_with_interpolation(seconds, percentile)

    # Convert back to datetime
    from datetime import timedelta

    return epoch + timedelta(seconds=percentile_seconds)


def extract_gantt_statistics(
    samples: list[Sample],
    project: Project,
    percentile: float = 0.97,
) -> GanttStatistics:
    """Extract Gantt-specific statistics from samples.

    Process:
    1. For each sample:
       - Extract world sequence
       - Extract task start/end times (calendar time) from events
       - Group by (task_id, world_sequence)
    2. For each task variant:
       - Compute Pth percentile start time (with interpolation)
       - Compute Pth percentile duration (calendar hours, with interpolation)
       - Duration = (end_time - start_time).total_seconds() / 3600
    3. Collect dependencies from project
    4. Compute project_start_date = min(all percentile_start_times)
       - Ensures all start times are >= 0 in optimization
       - Handles in-progress tasks that started before simulation

    Args:
        samples: List of simulation samples
        project: Project containing task definitions
        percentile: Percentile as fraction (default 0.97 = 97%)

    Returns:
        GanttStatistics with percentile start/duration for each task variant

    Raises:
        ValueError: If samples is empty or percentile invalid
    """
    if not samples:
        raise ValueError("Cannot extract Gantt statistics from empty samples")
    if not 0 < percentile < 1:
        raise ValueError(f"Percentile must be between 0 and 1, got {percentile}")

    # Group task times by (task_id, world_sequence)
    variant_start_times: dict[TaskVariantKey, list[datetime]] = defaultdict(list)
    variant_end_times: dict[TaskVariantKey, list[datetime]] = defaultdict(list)
    world_sequences: set[WorldSequence] = set()

    # Extract times from each sample
    for sample in samples:
        # Get world sequence for this sample
        world_seq = extract_world_sequence_from_sample(sample)
        world_sequences.add(world_seq)

        # Extract task start/end times from events
        # Group events by task
        task_events: dict[NodeId, list[TaskEvent]] = defaultdict(list)
        for event in sample.events:
            if event.event_type in ("start", "complete"):
                task_events[event.node_id].append(event)

        # Find start and complete events for each task
        for node_id, events in task_events.items():
            # Only process task nodes (not branches)
            try:
                task_id = TaskId(str(node_id))
            except Exception:
                continue

            # Find start and complete events
            start_events = [e for e in events if e.event_type == "start"]
            complete_events = [e for e in events if e.event_type == "complete"]

            # Only include if both start and complete exist
            if start_events and complete_events:
                start_time = min(e.timestamp for e in start_events)
                end_time = max(e.timestamp for e in complete_events)

                variant_key = TaskVariantKey(task_id, world_seq)
                variant_start_times[variant_key].append(start_time)
                variant_end_times[variant_key].append(end_time)

    # Get task titles and Jira issue keys from project
    all_tasks = get_all_tasks_from_project(project)
    task_titles = {task.id: task.title for task in all_tasks}
    jira_issue_keys: dict[TaskId, str] = {
        task.id: str(task.jira_reference.issue_key)
        for task in all_tasks
        if task.jira_reference is not None
    }

    # Compute percentile statistics for each variant
    task_statistics: dict[TaskVariantKey, GanttTaskStatistics] = {}

    for variant_key in variant_start_times:
        start_times = variant_start_times[variant_key]
        end_times = variant_end_times[variant_key]

        # Compute percentile start time
        percentile_start = compute_datetime_percentile_with_interpolation(
            start_times, percentile
        )

        # Compute percentile duration (calendar hours)
        durations_hours = [
            (end - start).total_seconds() / 3600
            for start, end in zip(start_times, end_times, strict=True)
        ]
        percentile_duration = compute_percentile_with_interpolation(
            durations_hours, percentile
        )

        # Get task title and Jira issue key
        task_title = task_titles.get(variant_key.task_id, str(variant_key.task_id))
        jira_issue_key = jira_issue_keys.get(variant_key.task_id)

        task_statistics[variant_key] = GanttTaskStatistics(
            variant_key=variant_key,
            task_title=task_title,
            percentile_start_time=percentile_start,
            percentile_duration_hours=percentile_duration,
            sample_count=len(start_times),
            jira_issue_key=jira_issue_key,
        )

    # Compute project_start_date = min of all percentile start times
    # This ensures all start times in optimization are >= 0
    if task_statistics:
        project_start_date = min(
            stats.percentile_start_time for stats in task_statistics.values()
        )
    else:
        # No tasks - use current time as fallback
        from datetime import UTC

        project_start_date = datetime.now(UTC)

    # Collect dependencies from project
    dependencies: list[DependencyInfo] = []
    occurred_task_ids = {variant_key.task_id for variant_key in task_statistics}

    for task in all_tasks:
        if task.id in occurred_task_ids:
            # Include this task's dependencies with source info
            for dep in task.dependencies:
                dependencies.append(
                    DependencyInfo(source_task_id=task.id, dependency=dep)
                )

    return GanttStatistics(
        task_statistics=task_statistics,
        dependencies=dependencies,
        percentile=percentile,
        project_start_date=project_start_date,
        world_sequences=world_sequences,
    )
