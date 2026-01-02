"""Tests for simulation result analysis functions."""

from datetime import UTC, datetime, timedelta

import pytest

from fluxx.data.models import Sample, SampleId, TaskEvent, TaskId
from fluxx.gui.simulation.analysis import (
    calculate_percentiles,
    calculate_statistics,
    calculate_success_rate,
    extract_completion_times,
    prepare_histogram_data,
)


@pytest.fixture
def successful_sample() -> Sample:
    """Create a successful simulation sample."""
    events = [
        TaskEvent(
            node_id=TaskId("t1"),
            event_type="start",
            timestamp=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),
            details={},
        ),
        TaskEvent(
            node_id=TaskId("t1"),
            event_type="complete",
            timestamp=datetime(2024, 1, 3, 17, 0, 0, tzinfo=UTC),
            details={},
        ),
    ]
    return Sample(sample_id=SampleId(0), events=events, failed_tasks=[])


@pytest.fixture
def failed_sample() -> Sample:
    """Create a failed simulation sample."""
    events = [
        TaskEvent(
            node_id=TaskId("t1"),
            event_type="start",
            timestamp=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),
            details={},
        ),
    ]
    return Sample(
        sample_id=SampleId(1), events=events, failed_tasks=[TaskId("t2"), TaskId("t3")]
    )


def test_extract_completion_times_all_successful(
    successful_sample: Sample,
) -> None:
    """Test extracting completion times from all successful samples."""
    # Create 3 successful samples with different completion times
    samples = [successful_sample]
    samples.append(
        Sample(
            sample_id=SampleId(1),
            events=[
                TaskEvent(
                    node_id=TaskId("t1"),
                    event_type="complete",
                    timestamp=datetime(2024, 1, 5, 17, 0, 0, tzinfo=UTC),
                    details={},
                )
            ],
            failed_tasks=[],
        )
    )
    samples.append(
        Sample(
            sample_id=SampleId(2),
            events=[
                TaskEvent(
                    node_id=TaskId("t1"),
                    event_type="complete",
                    timestamp=datetime(2024, 1, 2, 17, 0, 0, tzinfo=UTC),
                    details={},
                )
            ],
            failed_tasks=[],
        )
    )

    times = extract_completion_times(samples)

    assert len(times) == 3
    assert times[0] == datetime(2024, 1, 3, 17, 0, 0, tzinfo=UTC)
    assert times[1] == datetime(2024, 1, 5, 17, 0, 0, tzinfo=UTC)
    assert times[2] == datetime(2024, 1, 2, 17, 0, 0, tzinfo=UTC)


def test_extract_completion_times_mixed(
    successful_sample: Sample, failed_sample: Sample
) -> None:
    """Test extracting completion times with mix of successful and failed samples."""
    samples = [successful_sample, failed_sample]

    times = extract_completion_times(samples)

    # Only one successful sample
    assert len(times) == 1
    assert times[0] == datetime(2024, 1, 3, 17, 0, 0, tzinfo=UTC)


def test_extract_completion_times_all_failed(failed_sample: Sample) -> None:
    """Test extracting completion times from all failed samples."""
    samples = [failed_sample]

    times = extract_completion_times(samples)

    assert len(times) == 0


def test_extract_completion_times_empty_events() -> None:
    """Test extracting completion times from sample with no events."""
    sample = Sample(sample_id=SampleId(0), events=[], failed_tasks=[])

    times = extract_completion_times([sample])

    assert len(times) == 0


def test_calculate_percentiles() -> None:
    """Test percentile calculation."""
    # Create times spanning 10 days
    base = datetime(2024, 1, 1, 17, 0, 0, tzinfo=UTC)
    times = [base + timedelta(days=i) for i in range(11)]  # Days 0-10

    percentiles_dict = calculate_percentiles(times, [0, 25, 50, 75, 100])

    # Check approximate values (numpy percentile uses linear interpolation)
    assert percentiles_dict[0] == base  # Min
    assert abs((percentiles_dict[50] - (base + timedelta(days=5))).total_seconds()) < 1
    assert percentiles_dict[100] == base + timedelta(days=10)  # Max


def test_calculate_percentiles_empty_list() -> None:
    """Test percentile calculation with empty list raises ValueError."""
    with pytest.raises(ValueError, match="Cannot calculate percentiles from empty"):
        calculate_percentiles([], [50])


def test_calculate_success_rate_all_successful(successful_sample: Sample) -> None:
    """Test success rate calculation with all successful samples."""
    samples = [successful_sample, successful_sample, successful_sample]

    rate = calculate_success_rate(samples)

    assert rate == 1.0


def test_calculate_success_rate_all_failed(failed_sample: Sample) -> None:
    """Test success rate calculation with all failed samples."""
    samples = [failed_sample, failed_sample]

    rate = calculate_success_rate(samples)

    assert rate == 0.0


def test_calculate_success_rate_mixed(
    successful_sample: Sample, failed_sample: Sample
) -> None:
    """Test success rate calculation with mixed results."""
    samples = [successful_sample, failed_sample, successful_sample, failed_sample]

    rate = calculate_success_rate(samples)

    assert rate == 0.5


def test_calculate_success_rate_empty_list() -> None:
    """Test success rate with empty list raises ValueError."""
    with pytest.raises(ValueError, match="Cannot calculate success rate from empty"):
        calculate_success_rate([])


def test_calculate_statistics() -> None:
    """Test statistical calculations."""
    # Create times: 1, 2, 3, 4, 5 days from base
    base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    times = [base + timedelta(days=i) for i in [1, 2, 3, 4, 5]]

    stats = calculate_statistics(times)

    # Mean should be 3 days from base
    expected_mean = base + timedelta(days=3)
    assert abs((stats["mean"] - expected_mean).total_seconds()) < 1

    # Median should be 3 days from base
    expected_median = base + timedelta(days=3)
    assert abs((stats["median"] - expected_median).total_seconds()) < 1

    # Std dev should be approximately sqrt(2) days ≈ 1.41 days
    std_dev = stats["std_dev"]
    assert abs(std_dev.total_seconds() / 86400 - 1.414) < 0.1


def test_calculate_statistics_empty_list() -> None:
    """Test statistics with empty list raises ValueError."""
    with pytest.raises(ValueError, match="Cannot calculate statistics from empty"):
        calculate_statistics([])


def test_prepare_histogram_data() -> None:
    """Test histogram data preparation."""
    # Create times spanning 0, 1, 2, 3, 4 days
    base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    times = [base + timedelta(days=i) for i in [0, 1, 2, 3, 4]]

    bin_edges, counts = prepare_histogram_data(times, num_bins=4)

    # Should have num_bins+1 edges and num_bins counts
    assert len(bin_edges) == 5
    assert len(counts) == 4

    # First edge should be 0 (earliest time)
    assert bin_edges[0] == 0.0

    # Last edge should be 4 days
    assert abs(bin_edges[-1] - 4.0) < 0.01

    # Total counts should equal number of samples
    assert sum(counts) == 5


def test_prepare_histogram_data_empty_list() -> None:
    """Test histogram with empty list raises ValueError."""
    with pytest.raises(ValueError, match="Cannot prepare histogram from empty"):
        prepare_histogram_data([], num_bins=10)


def test_prepare_histogram_data_invalid_bins() -> None:
    """Test histogram with invalid number of bins raises ValueError."""
    base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    times = [base]

    with pytest.raises(ValueError, match="num_bins must be at least 1"):
        prepare_histogram_data(times, num_bins=0)

    with pytest.raises(ValueError, match="num_bins must be at least 1"):
        prepare_histogram_data(times, num_bins=-5)
