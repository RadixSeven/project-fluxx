"""Pure functions for analyzing simulation results.

This module contains testable logic for computing statistics and distributions
from simulation samples. All functions are pure (no side effects) for easy testing.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NewType

import numpy as np

from fluxx.data.models import Dependency, NodeId, Project, Sample, Task, TaskId


def extract_completion_times(samples: list[Sample]) -> list[datetime]:
    """Extract completion times from successful simulation samples.

    Only includes samples that completed successfully (no failed tasks).
    Completion time is the timestamp of the last event in the sample.

    Args:
        samples: List of simulation samples

    Returns:
        List of completion timestamps (only from successful samples)
    """
    completion_times: list[datetime] = []

    for sample in samples:
        # Skip failed samples
        if len(sample.failed_tasks) > 0:
            continue

        # Find last event timestamp
        if len(sample.events) == 0:
            continue

        last_event = max(sample.events, key=lambda e: e.timestamp)
        completion_times.append(last_event.timestamp)

    return completion_times


def calculate_percentiles(
    times: list[datetime], percentiles: list[float]
) -> dict[float, datetime]:
    """Calculate percentile values for completion times.

    Args:
        times: List of completion timestamps
        percentiles: List of percentile values (0-100), e.g., [10, 50, 90, 95]

    Returns:
        Dictionary mapping percentile to timestamp

    Raises:
        ValueError: If times is empty
    """
    if not times:
        raise ValueError("Cannot calculate percentiles from empty list")

    # Convert times to seconds since epoch for numpy
    epoch = datetime.fromtimestamp(0, tz=times[0].tzinfo)
    times_seconds = np.array([(t - epoch).total_seconds() for t in times])

    # Calculate percentiles
    percentile_seconds = np.percentile(times_seconds, percentiles)

    # Convert back to datetime
    result: dict[float, datetime] = {}
    for p, seconds in zip(percentiles, percentile_seconds, strict=True):
        result[p] = epoch + timedelta(seconds=float(seconds))

    return result


def calculate_success_rate(samples: list[Sample]) -> float:
    """Calculate the success rate (percentage of samples that completed).

    Args:
        samples: List of simulation samples

    Returns:
        Success rate as a float between 0.0 and 1.0

    Raises:
        ValueError: If samples is empty
    """
    if not samples:
        raise ValueError("Cannot calculate success rate from empty list")

    successful = sum(1 for s in samples if len(s.failed_tasks) == 0)
    return successful / len(samples)


def calculate_statistics(
    times: list[datetime],
) -> dict[str, datetime | timedelta]:
    """Calculate statistical measures for completion times.

    Args:
        times: List of completion timestamps

    Returns:
        Dictionary with keys:
        - 'mean': Mean completion time
        - 'median': Median completion time
        - 'std_dev': Standard deviation as timedelta

    Raises:
        ValueError: If times is empty
    """
    if not times:
        raise ValueError("Cannot calculate statistics from empty list")

    # Convert to seconds since epoch
    epoch = datetime.fromtimestamp(0, tz=times[0].tzinfo)
    times_seconds = np.array([(t - epoch).total_seconds() for t in times])

    # Calculate statistics
    mean_seconds = float(np.mean(times_seconds))
    median_seconds = float(np.median(times_seconds))
    std_dev_seconds = float(np.std(times_seconds))

    return {
        "mean": epoch + timedelta(seconds=mean_seconds),
        "median": epoch + timedelta(seconds=median_seconds),
        "std_dev": timedelta(seconds=std_dev_seconds),
    }


def prepare_histogram_data(
    times: list[datetime], num_bins: int = 30
) -> tuple[list[float], list[int]]:
    """Prepare data for histogram visualization.

    Args:
        times: List of completion timestamps
        num_bins: Number of histogram bins

    Returns:
        Tuple of (bin_edges_as_days, counts) where:
        - bin_edges_as_days: Bin edges as days since earliest completion
        - counts: Number of samples in each bin

    Raises:
        ValueError: If times is empty or num_bins < 1
    """
    if not times:
        raise ValueError("Cannot prepare histogram from empty list")
    if num_bins < 1:
        raise ValueError("num_bins must be at least 1")

    # Convert to days since earliest time
    earliest = min(times)
    days_since_earliest = [(t - earliest).total_seconds() / 86400 for t in times]

    # Create histogram
    counts_array, bin_edges_array = np.histogram(days_since_earliest, bins=num_bins)

    return list(bin_edges_array), list(counts_array)


# Probabilistic Timeline Analysis


# Type alias for per-sample task times
SampleTaskTimes = NewType("SampleTaskTimes", dict[TaskId, tuple[datetime, datetime]])


@dataclass
class TimeStatistics:
    """Time statistics for a task that occurred in at least one sample."""

    min_start_time: datetime
    max_end_time: datetime
    percentile_start_time: datetime  # (1-P)th percentile
    percentile_end_time: datetime  # Pth percentile


@dataclass
class TaskStatistics:
    """Statistics for a single task across all samples."""

    task_id: TaskId
    occurrence_fraction: float  # 0.0 to 1.0
    time_statistics: TimeStatistics | None  # None if never occurred


@dataclass
class TimelineData:
    """Complete data for probabilistic timeline visualization."""

    task_statistics: dict[TaskId, TaskStatistics]
    dependencies: list[Dependency]  # From project (filtered to visible tasks)
    percentile: float  # e.g., 90.0
    earliest_time: datetime  # For axis scaling
    latest_time: datetime


def get_task_from_project(task_id: TaskId, project: Project) -> Task:
    """Get a task from the project by ID.

    Args:
        task_id: ID of the task to retrieve
        project: Project containing the task

    Returns:
        The task object

    Raises:
        KeyError: If task not found
    """
    node_id = NodeId(str(task_id))
    if node_id not in project.dag.node_map:
        raise KeyError(f"Task {task_id} not found in node_map")

    persistent_id = project.dag.node_map[node_id]
    if persistent_id not in project.persistent_tasks:
        raise KeyError(f"Task {task_id} persistent object not found")

    persistent_task = project.persistent_tasks[persistent_id]
    current_version_id = project.dag.current_version_id

    if current_version_id not in persistent_task.versions:
        raise KeyError(f"Task {task_id} version {current_version_id} not found")

    return persistent_task.versions[current_version_id]


def get_all_tasks_from_project(project: Project) -> list[Task]:
    """Get all tasks from the current project version.

    Args:
        project: Project to extract tasks from

    Returns:
        List of all tasks in current version
    """
    tasks: list[Task] = []
    current_version_id = project.dag.current_version_id

    for _node_id, persistent_id in project.dag.node_map.items():
        if persistent_id not in project.persistent_tasks:
            continue

        persistent_task = project.persistent_tasks[persistent_id]
        if current_version_id in persistent_task.versions:
            tasks.append(persistent_task.versions[current_version_id])

    return tasks


def extract_leaf_task_times(samples: list[Sample]) -> list[SampleTaskTimes]:
    """Extract times for leaf tasks from events, organized by sample.

    Finds "start" and "complete" events for each task in each sample.

    Args:
        samples: List of simulation samples

    Returns:
        List where index corresponds to sample index, value is dict of task times
    """
    sample_times_list: list[SampleTaskTimes] = []

    for sample in samples:
        task_times: dict[TaskId, tuple[datetime, datetime]] = {}

        # Group events by task
        task_events: dict[TaskId, list[tuple[str, datetime]]] = {}
        for event in sample.events:
            task_id = TaskId(str(event.node_id))
            if task_id not in task_events:
                task_events[task_id] = []
            task_events[task_id].append((event.event_type, event.timestamp))

        # Extract (start, end) pairs
        for task_id, events in task_events.items():
            start_time = None
            end_time = None

            for event_type, timestamp in events:
                if event_type == "start":
                    start_time = timestamp
                elif event_type == "complete":
                    end_time = timestamp

            # Only record if we have both start and end
            if start_time is not None and end_time is not None:
                task_times[task_id] = (start_time, end_time)

        sample_times_list.append(SampleTaskTimes(task_times))

    return sample_times_list


def compute_parent_times_per_sample(
    parent_id: TaskId,
    children_ids: list[TaskId],
    sample_times: SampleTaskTimes,
) -> tuple[datetime, datetime] | None:
    """Compute parent (start, end) for one sample based on children.

    Args:
        parent_id: ID of parent task
        children_ids: IDs of child tasks
        sample_times: Task times for this sample

    Returns:
        (min_child_start, max_child_end) if any child occurred, else None
    """
    child_times = [sample_times[cid] for cid in children_ids if cid in sample_times]

    if not child_times:
        return None

    starts = [t[0] for t in child_times]
    ends = [t[1] for t in child_times]

    return (min(starts), max(ends))


def get_parent_processing_order(project: Project) -> list[TaskId]:
    """Get parent tasks in processing order (children before parents).

    Uses topological sort on parent-child relationships.
    Deterministic ordering via sorted() for reproducibility.

    Args:
        project: Project containing tasks

    Returns:
        List of parent task IDs ordered so all children are processed first

    Raises:
        ValueError: If there's a cycle in parent hierarchy
    """
    all_tasks = get_all_tasks_from_project(project)
    parents = [t for t in all_tasks if len(t.children) > 0]
    parent_ids = {p.id for p in parents}  # All parent task IDs (never changes)

    result: list[TaskId] = []
    placed_in_result: set[TaskId] = set()  # O(1) membership checks
    remaining = parent_ids.copy()
    parent_children = {p.id: set(p.children) for p in parents}

    while remaining:
        added_this_round: set[TaskId] = set()

        for parent_id in remaining:
            children = parent_children[parent_id]
            # Children that are also parents
            children_that_are_parents = children & parent_ids
            # All parent children must be placed before this parent
            if children_that_are_parents.issubset(placed_in_result):
                added_this_round.add(parent_id)

        if not added_this_round:
            raise ValueError(f"Cycle in parent hierarchy: {remaining}")

        # Sort for deterministic ordering
        result.extend(sorted(added_this_round))
        placed_in_result |= added_this_round
        remaining -= added_this_round

    return result


def add_parent_task_times(
    sample_times_list: list[SampleTaskTimes], project: Project
) -> None:
    """Add parent task times to sample_times_list in-place.

    Mutates sample_times_list by adding computed parent times.
    Processes parents in correct order so nested parents work.

    Args:
        sample_times_list: List of per-sample task times (initially leaf tasks only)
        project: Project with task hierarchy
    """
    parent_order = get_parent_processing_order(project)

    for parent_id in parent_order:
        parent_task = get_task_from_project(parent_id, project)
        children_ids = parent_task.children

        for sample_times in sample_times_list:
            parent_time = compute_parent_times_per_sample(
                parent_id, children_ids, sample_times
            )
            if parent_time is not None:
                # Add to this sample's times (enables grandparent computation)
                sample_times[parent_id] = parent_time


def compute_time_statistics(
    time_pairs: list[tuple[datetime, datetime]], percentile: float
) -> TimeStatistics:
    """Compute time statistics from (start, end) pairs.

    Args:
        time_pairs: List of (start, end) tuples
        percentile: Percentile for inner markers (e.g., 90.0)

    Returns:
        TimeStatistics with min/max and percentiles

    Raises:
        ValueError: If time_pairs is empty or percentile invalid
    """
    if not time_pairs:
        raise ValueError("Cannot compute time statistics from empty list")
    if not 0 < percentile < 100:
        raise ValueError(f"Percentile must be between 0 and 100, got {percentile}")

    starts = [t[0] for t in time_pairs]
    ends = [t[1] for t in time_pairs]

    # Min/max are absolute bounds
    min_start = min(starts)
    max_end = max(ends)

    # Compute percentiles
    # (1-P)th percentile for start (e.g., 10th percentile for P=90)
    lower_percentile = 100 - percentile

    # Convert to seconds for numpy
    epoch = datetime.fromtimestamp(0, tz=starts[0].tzinfo)
    starts_seconds = np.array([(s - epoch).total_seconds() for s in starts])
    ends_seconds = np.array([(e - epoch).total_seconds() for e in ends])

    percentile_start_seconds = np.percentile(starts_seconds, lower_percentile)
    percentile_end_seconds = np.percentile(ends_seconds, percentile)

    percentile_start = epoch + timedelta(seconds=float(percentile_start_seconds))
    percentile_end = epoch + timedelta(seconds=float(percentile_end_seconds))

    return TimeStatistics(
        min_start_time=min_start,
        max_end_time=max_end,
        percentile_start_time=percentile_start,
        percentile_end_time=percentile_end,
    )


def calculate_task_statistics(
    sample_times_list: list[SampleTaskTimes], num_samples: int, percentile: float
) -> dict[TaskId, TaskStatistics]:
    """Calculate statistics for all tasks across samples.

    Args:
        sample_times_list: Per-sample task times (includes leaf and parent tasks)
        num_samples: Total number of samples (for occurrence fraction)
        percentile: Percentile for inner markers (e.g., 90.0)

    Returns:
        Dictionary mapping task ID to its statistics
    """
    # Collect all time pairs for each task
    task_time_pairs: dict[TaskId, list[tuple[datetime, datetime]]] = {}

    for sample_times in sample_times_list:
        for task_id, time_pair in sample_times.items():
            if task_id not in task_time_pairs:
                task_time_pairs[task_id] = []
            task_time_pairs[task_id].append(time_pair)

    # Compute statistics for each task
    result: dict[TaskId, TaskStatistics] = {}

    for task_id, time_pairs in task_time_pairs.items():
        occurrence_count = len(time_pairs)
        occurrence_fraction = occurrence_count / num_samples

        if occurrence_count > 0:
            time_stats = compute_time_statistics(time_pairs, percentile)
        else:
            time_stats = None

        result[task_id] = TaskStatistics(
            task_id=task_id,
            occurrence_fraction=occurrence_fraction,
            time_statistics=time_stats,
        )

    return result


def extract_timeline_data(
    samples: list[Sample], project: Project, percentile: float = 90.0
) -> TimelineData:
    """Extract complete timeline data from samples and project.

    Main entry point for probabilistic timeline analysis.

    Args:
        samples: Simulation samples
        project: Project definition (for dependencies, hierarchy)
        percentile: Percentile for inner markers (default 90.0)

    Returns:
        TimelineData ready for visualization

    Raises:
        ValueError: If samples is empty or percentile invalid
    """
    if not samples:
        raise ValueError("Cannot extract timeline data from empty samples")
    if not 0 < percentile < 100:
        raise ValueError(f"Percentile must be between 0 and 100, got {percentile}")

    # Extract leaf task times from events
    sample_times_list = extract_leaf_task_times(samples)

    # Add parent task times
    add_parent_task_times(sample_times_list, project)

    # Calculate statistics for all tasks
    num_samples = len(samples)
    task_statistics = calculate_task_statistics(
        sample_times_list, num_samples, percentile
    )

    # Find earliest and latest times for axis scaling
    all_times: list[datetime] = []
    for stats in task_statistics.values():
        if stats.time_statistics is not None:
            all_times.append(stats.time_statistics.min_start_time)
            all_times.append(stats.time_statistics.max_end_time)

    if not all_times:
        # No tasks occurred in any sample - use current time as default
        from datetime import UTC

        now = datetime.now(UTC)
        earliest_time = now
        latest_time = now
    else:
        earliest_time = min(all_times)
        latest_time = max(all_times)

    # Collect dependencies from all tasks that occurred
    dependencies: list[Dependency] = []
    all_tasks = get_all_tasks_from_project(project)
    occurred_task_ids = set(task_statistics.keys())

    for task in all_tasks:
        if task.id in occurred_task_ids:
            # Include this task's dependencies
            dependencies.extend(task.dependencies)

    return TimelineData(
        task_statistics=task_statistics,
        dependencies=dependencies,
        percentile=percentile,
        earliest_time=earliest_time,
        latest_time=latest_time,
    )
