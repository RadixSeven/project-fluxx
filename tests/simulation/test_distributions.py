"""Tests for distribution sampling functions."""

import numpy as np

from fluxx.data.models import ShiftedLognormal, Triangular
from fluxx.simulation.distributions import (
    convert_shifted_lognormal_params,
    estimate_mean,
    sample_shifted_lognormal,
    sample_triangular,
    sample_with_rejection,
)


def test_convert_shifted_lognormal_params() -> None:
    """Test ShiftedLognormal parameter conversion."""
    min_val = 1.0
    mode = 5.0
    p95 = 10.0

    shift, mu, sigma = convert_shifted_lognormal_params(min_val, mode, p95)

    # Shift should equal minimum
    assert shift == min_val

    # Verify the mode relationship: mode = shift + exp(mu - sigma^2)
    computed_mode = shift + np.exp(mu - sigma**2)
    assert abs(computed_mode - mode) < 0.01

    # Verify p95 relationship: p95 = shift + exp(mu + 1.645*sigma)
    computed_p95 = shift + np.exp(mu + 1.645 * sigma)
    assert abs(computed_p95 - p95) < 0.01


def test_shifted_lognormal_samples_above_min() -> None:
    """Test that ShiftedLognormal samples are always >= min."""
    dist = ShiftedLognormal(min=2.0, mode=5.0, percentile_95=15.0)
    rng = np.random.default_rng(seed=42)

    samples = [sample_shifted_lognormal(dist, rng) for _ in range(1000)]

    # All samples should be >= min
    assert all(s >= dist.min for s in samples)

    # Mean should be reasonable (within expected range)
    mean = np.mean(samples)
    assert 4.0 < mean < 10.0


def test_triangular_samples_in_range() -> None:
    """Test that Triangular samples are in [min, max]."""
    dist = Triangular(min=1.0, mode=3.0, max=8.0)
    rng = np.random.default_rng(seed=42)

    samples = [sample_triangular(dist, rng) for _ in range(1000)]

    # All samples should be in [min, max]
    assert all(dist.min <= s <= dist.max for s in samples)

    # Mean should be close to (min + mode + max) / 3
    mean = np.mean(samples)
    expected_mean = (dist.min + dist.mode + dist.max) / 3.0
    assert abs(mean - expected_mean) < 0.5


def test_rejection_sampling_above_threshold() -> None:
    """Test that rejection sampling produces values >= threshold."""
    dist = Triangular(min=1.0, mode=5.0, max=10.0)
    rng = np.random.default_rng(seed=42)

    threshold = 7.0
    samples = [sample_with_rejection(dist, rng, threshold) for _ in range(100)]

    # All samples should be >= threshold
    assert all(s >= threshold for s in samples)


def test_rejection_sampling_with_min_threshold() -> None:
    """Test rejection sampling when threshold equals min."""
    dist = ShiftedLognormal(min=2.0, mode=5.0, percentile_95=15.0)
    rng = np.random.default_rng(seed=42)

    # Threshold at minimum should work like normal sampling
    samples = [sample_with_rejection(dist, rng, dist.min) for _ in range(100)]

    assert all(s >= dist.min for s in samples)


def test_rejection_sampling_tail_fallback() -> None:
    """Test rejection sampling fallback with threshold way in tail."""
    dist = Triangular(min=1.0, mode=3.0, max=5.0)
    rng = np.random.default_rng(seed=42)

    # Threshold way beyond max will trigger exponential fallback
    threshold = 100.0
    sample = sample_with_rejection(dist, rng, threshold, max_attempts=10)

    # Should use exponential approximation
    assert sample >= threshold
    # Should be reasonably close to threshold (not astronomically large)
    assert sample < threshold * 3


def test_estimate_mean_shifted_lognormal() -> None:
    """Test mean estimation for ShiftedLognormal."""
    dist = ShiftedLognormal(min=1.0, mode=5.0, percentile_95=15.0)
    mean = estimate_mean(dist)

    # Mean should be greater than mode for lognormal
    assert mean > dist.mode
    # Should be reasonable value
    assert 5.0 < mean < 20.0


def test_estimate_mean_triangular() -> None:
    """Test mean estimation for Triangular."""
    dist = Triangular(min=1.0, mode=3.0, max=8.0)
    mean = estimate_mean(dist)

    # Mean should be (min + mode + max) / 3
    expected = (dist.min + dist.mode + dist.max) / 3.0
    assert abs(mean - expected) < 0.01


def test_shifted_lognormal_deterministic() -> None:
    """Test that seeded RNG produces deterministic results."""
    dist = ShiftedLognormal(min=1.0, mode=5.0, percentile_95=15.0)

    rng1 = np.random.default_rng(seed=123)
    rng2 = np.random.default_rng(seed=123)

    sample1 = sample_shifted_lognormal(dist, rng1)
    sample2 = sample_shifted_lognormal(dist, rng2)

    assert sample1 == sample2


def test_triangular_deterministic() -> None:
    """Test that seeded RNG produces deterministic results."""
    dist = Triangular(min=1.0, mode=5.0, max=10.0)

    rng1 = np.random.default_rng(seed=456)
    rng2 = np.random.default_rng(seed=456)

    sample1 = sample_triangular(dist, rng1)
    sample2 = sample_triangular(dist, rng2)

    assert sample1 == sample2


def test_rejection_sampling_deterministic() -> None:
    """Test that rejection sampling is deterministic with seeded RNG."""
    dist = Triangular(min=1.0, mode=5.0, max=10.0)
    threshold = 6.0

    rng1 = np.random.default_rng(seed=789)
    rng2 = np.random.default_rng(seed=789)

    sample1 = sample_with_rejection(dist, rng1, threshold)
    sample2 = sample_with_rejection(dist, rng2, threshold)

    assert sample1 == sample2


def test_estimate_mean_unknown_distribution() -> None:
    """Test that estimate_mean raises error for unknown distribution type."""
    import pytest

    from fluxx.data.models import DurationDistribution

    # Create a mock unknown distribution
    class UnknownDistribution(DurationDistribution):
        value: float = 1.0

    unknown_dist = UnknownDistribution(value=5.0)

    with pytest.raises(ValueError, match="Unknown distribution type"):
        estimate_mean(unknown_dist)


def test_sample_with_rejection_unknown_distribution() -> None:
    """Test that sample_with_rejection raises error for unknown distribution."""
    import pytest

    from fluxx.data.models import DurationDistribution

    # Create a mock unknown distribution
    class UnknownDistribution(DurationDistribution):
        value: float = 1.0

    unknown_dist = UnknownDistribution(value=5.0)
    rng = np.random.default_rng(seed=123)

    with pytest.raises(ValueError, match="Unknown distribution type"):
        sample_with_rejection(unknown_dist, rng, 0.0)
