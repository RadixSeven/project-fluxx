"""Pure functions for analyzing simulation results.

This module contains testable logic for computing statistics and distributions
from simulation samples. All functions are pure (no side effects) for easy testing.
"""

from datetime import datetime, timedelta

import numpy as np

from fluxx.data.models import Sample


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
